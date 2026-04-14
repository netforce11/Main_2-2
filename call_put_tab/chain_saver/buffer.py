"""
chain_saver/buffer.py — 메모리 버퍼 관리
════════════════════════════════════════
역할:
  - call_data / put_data (스트림) 로부터 최신값 수집
  - 스냅샷 tick 수신 시 병합
  - flush() 호출 시 저장용 row 리스트 반환 후 초기화

구조:
  _buf[(expiry, strike, side)] = {bid, ask, last, iv, delta,
                                   gamma, vega, theta, source}
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Tuple

# 버퍼 키 타입
_Key = Tuple[str, float, str]   # (expiry, strike, side)


class ChainBuffer:
    def __init__(self):
        self._buf: Dict[_Key, dict] = {}
        self._sym       = ""
        self._und_price = 0.0

    def set_context(self, sym: str, und_price: float):
        """종목·기초자산가 업데이트 (scheduler에서 주기적으로 호출)."""
        self._sym       = sym
        self._und_price = und_price

    # ── 스트림 tick 업데이트 ─────────────────────────────────
    def update_price(self, expiry: str, strike: float, side: str,
                     bid=None, ask=None, last=None):
        """_on_tick_price 에서 호출."""
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        if bid  is not None: entry["bid"]  = bid
        if ask  is not None: entry["ask"]  = ask
        if last is not None: entry["last"] = last
        entry["source"] = "stream"

    def update_greeks(self, expiry: str, strike: float, side: str,
                      iv=None, delta=None, gamma=None,
                      vega=None, theta=None):
        """_on_tick_option 에서 호출."""
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        if iv    is not None: entry["iv"]    = iv
        if delta is not None: entry["delta"] = delta
        if gamma is not None: entry["gamma"] = gamma
        if vega  is not None: entry["vega"]  = vega
        if theta is not None: entry["theta"] = theta
        # source 는 이미 update_price 에서 설정됨; 없으면 stream 기본값
        entry.setdefault("source", "stream")

    # ── 스냅샷 tick 병합 ─────────────────────────────────────
    def update_snapshot(self, expiry: str, strike: float, side: str,
                        bid=None, ask=None, last=None,
                        iv=None, delta=None, gamma=None,
                        vega=None, theta=None):
        """스냅샷 응답 tick 에서 호출 — source='snapshot'."""
        key = (expiry, strike, side)
        entry = self._buf.setdefault(key, {})
        for k, v in [("bid",bid),("ask",ask),("last",last),
                     ("iv",iv),("delta",delta),("gamma",gamma),
                     ("vega",vega),("theta",theta)]:
            if v is not None:
                entry[k] = v
        entry["source"] = "snapshot"

    # ── flush: 저장용 row 리스트 반환 ────────────────────────
    def flush(self) -> List[dict]:
        """
        현재 버퍼를 row 리스트로 변환 후 반환.
        버퍼는 비우지 않음 — 스트림 데이터는 계속 누적.
        (저장 후에도 최신값 유지 → 다음 저장 때 덮어쓰기 방식)
        """
        if not self._buf:
            return []
        ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            })
        return rows

    def clear(self):
        """종목 전환 시 버퍼 초기화."""
        self._buf.clear()

    def size(self) -> int:
        return len(self._buf)
