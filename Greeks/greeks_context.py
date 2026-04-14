# greeks_context.py  — 콜↔풋 연관 이상 감지
# Python 3.8 호환  |  S11 신규 파일  |  200줄 이내
# -------------------------------------------------------
# 목적:
#   ① 오늘 콜 IV 폭등 감지
#   ② 전일 마감 기준선 대비 다음날 풋 IV 이탈 감지
#   ③ 지수 상승 + 콜 급등 → 다음날 풋 IV 기준선 이탈 경고
# -------------------------------------------------------
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import greeks_db as gdb

log = logging.getLogger(__name__)

# ── 임계값 ──────────────────────────────────────────────
CALL_IV_SURGE_PCT  = 20.0   # 콜 IV 급등 기준 (20분 내 %)
PUT_IV_BASELINE_DEV = 0.10   # 전일 기준 대비 풋 IV 이탈 (10%)
INDEX_RISE_PCT     = 0.50   # 지수 상승 기준 (0.5%)
MIN_SAMPLES        = 3      # 평균 계산 최소 샘플 수


class ContextDetector:
    """
    호출 방법:
        ctx = ContextDetector()
        events = ctx.detect(current_rows, day, sym)
    """

    def __init__(self):
        self._prev_und: float        = 0.0
        self._call_iv_hist: Dict[Tuple, List[float]] = {}
        # (expiry, strike) → [iv 시계열]
        self._triggered_pairs: set   = set()  # 중복 알림 방지

    # ── 메인 감지 ────────────────────────────────────────
    def detect(self, rows: List[Dict], day: str, sym: str) -> List[str]:
        """
        rows: 현재 시점 snapshot (tab_greeks._do_save 에서 전달)
        반환: 이벤트 메시지 리스트
        """
        events: List[str] = []

        # rows를 side별로 분리
        call_rows = [r for r in rows if r.get("side") == "C"]
        put_rows  = [r for r in rows if r.get("side") == "P"]
        und_price = rows[0].get("und_price", 0.0) if rows else 0.0

        # ─ ① 콜 IV 급등 감지 ────────────────────────────
        surge_strikes = self._detect_call_surge(call_rows)

        # ─ ② 전일 기준선 대비 풋 IV 이탈 ────────────────
        baseline_events = self._detect_put_baseline_dev(put_rows, day, sym)
        events.extend(baseline_events)

        # ─ ③ 지수 상승 + 콜 급등 → 풋 기준선 이탈 경고 ──
        index_rose = self._is_index_rising(und_price)
        if surge_strikes and index_rose:
            msg = (f"[콜↔풋 연관] 지수 상승({und_price:.0f}) + "
                   f"콜 IV 급등(strikes={surge_strikes}) → "
                   f"내일 풋 IV 기준선 이탈 모니터링 필요")
            log.warning(msg)
            events.append(msg)

        # ─ ④ 콜 급등 단독 알림 ──────────────────────────
        for s in surge_strikes:
            k = ("call_surge", s)
            if k not in self._triggered_pairs:
                events.append(f"[콜 IV↑] strike={s} 콜 IV 급등 감지")
                self._triggered_pairs.add(k)

        self._prev_und = und_price
        return events

    # ── 콜 IV 급등 감지 ──────────────────────────────────
    def _detect_call_surge(self, call_rows: List[Dict]) -> List[float]:
        """20분 내 콜 IV 가 CALL_IV_SURGE_PCT% 이상 상승한 행사가 반환"""
        surge: List[float] = []
        for r in call_rows:
            iv = r.get("iv")
            if not iv:
                continue
            k = (r.get("expiry",""), r.get("strike", 0.0))
            hist = self._call_iv_hist.setdefault(k, [])
            hist.append(iv)
            if len(hist) > 20:      # 최대 20개 샘플 유지
                hist.pop(0)
            if len(hist) < MIN_SAMPLES:
                continue
            base = hist[0]
            if base > 0 and (iv - base) / base * 100 >= CALL_IV_SURGE_PCT:
                surge.append(r["strike"])
        return surge

    # ── 전일 기준선 대비 풋 IV 이탈 ──────────────────────
    def _detect_put_baseline_dev(self, put_rows: List[Dict],
                                  day: str, sym: str) -> List[str]:
        """
        전일 마감 기준선(baseline.db) 대비 풋 IV 이탈 감지.
        baseline은 전일(=day 이전 영업일) 데이터를 참조.
        """
        prev_day = self._prev_trading_day(day)
        if not prev_day:
            return []

        baseline = gdb.load_baseline(prev_day, sym)
        if not baseline:
            log.debug("[ContextDetector] 전일 기준선 없음 (day=%s)", prev_day)
            return []

        # 기준선 인덱스 {(expiry, strike, side): iv_avg}
        bl_idx: Dict[Tuple, float] = {
            (r["expiry"], r["strike"], r["side"]): r["iv_avg"]
            for r in baseline
        }

        events: List[str] = []
        for r in put_rows:
            iv = r.get("iv")
            if not iv:
                continue
            k = (r.get("expiry",""), r.get("strike",0.0), "P")
            bl_iv = bl_idx.get(k)
            if bl_iv is None or bl_iv == 0:
                continue
            dev = (iv - bl_iv) / bl_iv      # 양수 = 상승, 음수 = 하락
            if abs(dev) >= PUT_IV_BASELINE_DEV:
                direction = "↑" if dev > 0 else "↓"
                msg = (f"[풋 IV 기준선 이탈{direction}] "
                       f"strike={r['strike']} "
                       f"IV={iv:.3f} vs 전일={bl_iv:.3f} "
                       f"({dev*100:+.1f}%)")
                # 중복 방지 (같은 strike 하루 1회)
                dedup_k = ("put_dev", r["strike"])
                if dedup_k not in self._triggered_pairs:
                    events.append(msg)
                    self._triggered_pairs.add(dedup_k)
                    log.warning(msg)
        return events

    # ── 지수 상승 여부 ───────────────────────────────────
    def _is_index_rising(self, und_price: float) -> bool:
        if self._prev_und <= 0:
            return False
        return (und_price - self._prev_und) / self._prev_und * 100 >= INDEX_RISE_PCT

    # ── 유틸: 전 영업일 ──────────────────────────────────
    @staticmethod
    def _prev_trading_day(day: str) -> Optional[str]:
        """
        'YYYYMMDD' 문자열 기준 전 영업일 반환.
        단순 역산 (공휴일 미반영 — 필요 시 trading_calendar 연동).
        """
        try:
            d = datetime.strptime(day, "%Y%m%d").date()
        except ValueError:
            return None
        d -= timedelta(days=1)
        # 주말 스킵
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        # DB에 실제 데이터가 있는 날만 반환
        available = set(gdb.available_days())
        target = d.strftime("%Y%m%d")
        return target if target in available else None
