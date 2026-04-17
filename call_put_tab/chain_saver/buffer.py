"""
chain_saver/buffer.py — 메모리 버퍼 관리
════════════════════════════════════════
역할:
  - call_data / put_data (스트림) 로부터 최신값 수집
  - 스냅샷 tick 수신 시 병합
  - flush() 호출 시 저장용 row 리스트 반환
  - 이론가(theo) / 중간가(mid) / 저고평가%(mispct) 자동 계산
  - Greeks_Matrix 콜백 브로드캐스트

구조:
  _buf[(expiry, strike, side)] = {bid, ask, last, iv, delta,
                                   gamma, vega, theta, source,
                                   mid, theo, mispct}
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, date
from typing import Callable, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_Key = Tuple[str, float, str]   # (expiry, strike, side)

# ── 미국 동부 시간 (ET) 유틸 ─────────────────────────────────
# pytz 없이 동작하도록 UTC 오프셋 직접 계산.
# 서머타임(DST): 3월 둘째 일요일 ~ 11월 첫째 일요일 → EDT = UTC-4
# 겨울(EST): 그 외 → EST = UTC-5
# KST = UTC+9  →  KST - ET = 13(DST) or 14(EST)

def _et_offset_hours() -> int:
    """현재 ET UTC 오프셋 반환: DST이면 -4, 겨울이면 -5."""
    from datetime import timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    # 3월 둘째 일요일
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar1 + timedelta(days=(6 - mar1.weekday()) % 7 + 7)
    dst_start = dst_start.replace(hour=7)   # 02:00 ET = 07:00 UTC
    # 11월 첫째 일요일
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    dst_end = dst_end.replace(hour=6)       # 02:00 ET = 06:00 UTC
    return -4 if dst_start <= now_utc < dst_end else -5

def now_et() -> datetime:
    """현재 ET 시각 반환."""
    from datetime import timezone, timedelta
    return datetime.now(timezone.utc) + timedelta(hours=_et_offset_hours())

def today_et() -> date:
    """현재 ET 날짜 반환."""
    return now_et().date()

def et_to_kst(et_str: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' ET → KST 문자열 변환."""
    from datetime import timezone, timedelta
    try:
        dt_et = datetime.strptime(et_str, "%Y-%m-%d %H:%M:%S")
        dt_kst = dt_et + timedelta(hours=_et_offset_hours() + 9)
        return dt_kst.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return et_str

# ── 무위험 금리 ──────────────────────────────────────────────
_RISK_FREE_RATE = 0.053

def set_rate(r: float):
    global _RISK_FREE_RATE
    _RISK_FREE_RATE = r


# ── Black-Scholes ────────────────────────────────────────────
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def calc_bs(S: float, K: float, T: float, iv: float,
            side: str, r: float = _RISK_FREE_RATE) -> Optional[float]:
    """
    Black-Scholes 이론가.
    S: 기초자산가  K: 행사가  T: 연환산 만기  iv: 내재변동성(소수)
    """
    try:
        if S <= 0 or K <= 0 or T <= 0 or iv <= 0 or iv > 10:
            return None
        sqrt_t = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * sqrt_t)
        d2 = d1 - iv * sqrt_t
        disc = math.exp(-r * T)
        if side == "C":
            return S * _norm_cdf(d1) - K * disc * _norm_cdf(d2)
        else:
            return K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
    except (ValueError, ZeroDivisionError):
        return None


def _days_to_expiry(expiry: str) -> float:
    """'YYYYMMDD' → 연환산 만기 (ET 기준, 당일이면 1/365)."""
    try:
        exp_date = datetime.strptime(expiry, "%Y%m%d").date()
        delta = (exp_date - today_et()).days   # ★ ET 날짜 기준
        return max(delta, 1) / 365.0
    except ValueError:
        return 0.0


# ── ChainBuffer ──────────────────────────────────────────────
class ChainBuffer:
    def __init__(self):
        self._buf: Dict[_Key, dict] = {}
        self._sym       = ""
        self._und_price = 0.0

        # Greeks_Matrix 브로드캐스트 콜백
        # 시그니처: fn(expiry, strike, side, data: dict)
        self._greeks_subscribers: List[Callable] = []

        # 수신 통계
        self._stat_price     = 0
        self._stat_greeks    = 0
        self._stat_snap      = 0
        self._stat_theo_ok   = 0
        self._stat_theo_fail = 0

    # ── 구독 등록/해제 ───────────────────────────────────────
    def register_greeks_subscriber(self, callback: Callable):
        """Greeks_Matrix 에서 1회 호출."""
        if callback not in self._greeks_subscribers:
            self._greeks_subscribers.append(callback)
            log.info("[Buffer] Greeks 구독 등록: %s", callback)

    def unregister_greeks_subscriber(self, callback: Callable):
        self._greeks_subscribers = [
            c for c in self._greeks_subscribers if c != callback
        ]

    def set_context(self, sym: str, und_price: float):
        self._sym       = sym
        self._und_price = und_price

    # ── 스트림 tick ──────────────────────────────────────────
    def update_price(self, expiry: str, strike: float, side: str,
                     bid=None, ask=None, last=None):
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        if bid  is not None: entry["bid"]  = bid
        if ask  is not None: entry["ask"]  = ask
        if last is not None: entry["last"] = last
        entry["source"] = "stream"
        entry["_side"]  = side   # ★ recalc 전에 side 저장
        self._stat_price += 1
        self._recalc(expiry, strike, entry)
        self._broadcast(expiry, strike, side, entry)

    def update_greeks(self, expiry: str, strike: float, side: str,
                      iv=None, delta=None, gamma=None,
                      vega=None, theta=None):
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        if iv    is not None: entry["iv"]    = iv
        if delta is not None: entry["delta"] = delta
        if gamma is not None: entry["gamma"] = gamma
        if vega  is not None: entry["vega"]  = vega
        if theta is not None: entry["theta"] = theta
        entry.setdefault("source", "stream")
        entry["_side"]  = side   # ★ recalc 전에 side 저장
        self._stat_greeks += 1
        self._recalc(expiry, strike, entry)
        self._broadcast(expiry, strike, side, entry)

    # ── 스냅샷 tick ──────────────────────────────────────────
    def update_snapshot(self, expiry: str, strike: float, side: str,
                        bid=None, ask=None, last=None,
                        iv=None, delta=None, gamma=None,
                        vega=None, theta=None):
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        for k, v in [("bid", bid), ("ask", ask), ("last", last),
                     ("iv", iv), ("delta", delta), ("gamma", gamma),
                     ("vega", vega), ("theta", theta)]:
            if v is not None:
                entry[k] = v
        entry["source"] = "snapshot"
        entry["_side"]  = side   # ★ recalc 전에 side 저장
        self._stat_snap += 1
        self._recalc(expiry, strike, entry)
        self._broadcast(expiry, strike, side, entry)

    # ── 이론가 계산 (내부) ───────────────────────────────────
    def _recalc(self, expiry: str, strike: float, entry: dict):
        """bid/ask/iv/und_price 가 모두 존재할 때만 계산."""
        und = self._und_price
        iv  = entry.get("iv")
        bid = entry.get("bid")
        ask = entry.get("ask")
        side = entry.get("side", "C")   # update_snapshot 경우 key 에서 가져옴

        if not (und > 0 and iv and bid is not None and ask is not None):
            return

        mid = (bid + ask) / 2.0
        entry["mid"] = round(mid, 4)

        T = _days_to_expiry(expiry)
        # side 를 key 에서 직접 쓰기 위해 caller 가 넘겨줘야 하므로
        # entry 에 side 저장되어 있지 않으면 계산 생략
        stored_side = entry.get("_side")
        if not stored_side:
            return

        theo = calc_bs(und, strike, T, iv, stored_side)
        if theo is not None and theo > 0:
            entry["theo"]   = round(theo, 4)
            entry["mispct"] = round((mid - theo) / theo * 100, 2)
            self._stat_theo_ok += 1
        else:
            entry["theo"]   = None
            entry["mispct"] = None
            self._stat_theo_fail += 1

    # ── 브로드캐스트 ─────────────────────────────────────────
    def _broadcast(self, expiry: str, strike: float, side: str,
                   entry: dict):
        if not self._greeks_subscribers:
            return
        # side 를 entry 에 캐싱 (recalc 에서 재사용)
        entry["_side"] = side
        snapshot = dict(entry)
        for cb in self._greeks_subscribers:
            try:
                cb(expiry, strike, side, snapshot)
            except Exception as e:
                log.warning("[Buffer] broadcast 오류: %s", e)

    # ── flush ────────────────────────────────────────────────
    def flush(self) -> List[dict]:
        if not self._buf:
            return []
        ts  = now_et().strftime("%Y-%m-%d %H:%M:%S")   # ★ ET 기준
        sym = self._sym
        und = self._und_price
        rows = []
        for (expiry, strike, side), d in self._buf.items():
            rows.append({
                "ts":        ts,
                "sym":       sym,
                "expiry":    expiry,
                "strike":    strike,
                "side":      side,
                "bid":       d.get("bid"),
                "ask":       d.get("ask"),
                "last":      d.get("last"),
                "iv":        d.get("iv"),
                "delta":     d.get("delta"),
                "gamma":     d.get("gamma"),
                "vega":      d.get("vega"),
                "theta":     d.get("theta"),
                "und_price": und,
                "source":    d.get("source", "stream"),
                "mid":       d.get("mid"),
                "theo":      d.get("theo"),
                "mispct":    d.get("mispct"),
            })
        return rows

    def clear(self):
        self._buf.clear()
        self.reset_stats()

    def size(self) -> int:
        return len(self._buf)

    # ── 수신 통계 ────────────────────────────────────────────
    def stats(self) -> dict:
        """
        수신 현황 요약 반환.
        scheduler 상태 라벨 or 디버그 콘솔에서 호출 가능.

        반환 예시:
          {
            'entries': 82,
            'price_ticks': 341, 'greeks_ticks': 280, 'snap_ticks': 120,
            'theo_ok': 78, 'theo_fail': 4, 'theo_coverage': '95.1%'
          }
        """
        total = self._stat_theo_ok + self._stat_theo_fail
        coverage = (
            f"{self._stat_theo_ok / total * 100:.1f}%"
            if total > 0 else "N/A"
        )
        return {
            "entries":       len(self._buf),
            "price_ticks":   self._stat_price,
            "greeks_ticks":  self._stat_greeks,
            "snap_ticks":    self._stat_snap,
            "theo_ok":       self._stat_theo_ok,
            "theo_fail":     self._stat_theo_fail,
            "theo_coverage": coverage,
        }

    def reset_stats(self):
        self._stat_price = self._stat_greeks = self._stat_snap = 0
        self._stat_theo_ok = self._stat_theo_fail = 0