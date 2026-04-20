"""
watch_dog/alert_engine.py — SPX 감시 엔진  v2.0
════════════════════════════════════════════════════
변경 (v1 → v2):
  - 조건A: 단일 window → 다중 행 리스트 (CondARow 리스트)
  - 조건B: 단일 옵션가 → 행사가별 독립 감시 (CondBRow 딕셔너리)
  - push_spx(minutes_ago, price_then, price_now) 인터페이스
  - push_opt(strike, opt_type, price_now, price_prev) 인터페이스
  - push_vix(vix_now, vix_prev) 인터페이스
  - 조건별 독립 쿨다운·알람 횟수 관리
  - is_running → property (괄호 없이 사용)
Python 3.8 호환
════════════════════════════════════════════════════
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List
import time


# ─────────────────────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────────────────────

@dataclass
class CondARow:
    """조건A 한 행 — SPX N분 전 대비 등락 감시."""
    minutes:   int   = 5       # 몇 분 전 대비
    points:    float = 10.0    # 기준 포인트
    direction: str  = "양방향" # "하락" | "상승" | "양방향"
    enabled:   bool = True
    # 내부 상태
    _last_alert_ts: float = field(default=0.0, repr=False)
    _alert_count:   int   = field(default=0,   repr=False)

@dataclass
class CondBRow:
    """조건B 한 행 — 특정 행사가 옵션 등락률 감시."""
    strike:    float = 0.0
    opt_type:  str  = "C"      # "C" | "P"
    pct:       float = 300.0   # 기준 등락률 (%)
    direction: str  = "양방향" # "상승" | "하락" | "양방향"
    # 내부 상태
    _last_alert_ts: float = field(default=0.0, repr=False)
    _alert_count:   int   = field(default=0,   repr=False)


# ─────────────────────────────────────────────────────────────
# AlertEngine
# ─────────────────────────────────────────────────────────────

class AlertEngine:
    """
    SPX 감시 엔진 v2.
    외부(tab_options_chart.py)에서 tick 수신 시마다 push_* 호출.

    인터페이스:
        engine.push_spx(minutes_ago, price_then, price_now)
        engine.push_opt(strike, opt_type, price_now, price_prev)
        engine.push_vix(vix_now, vix_prev)
    """

    MAX_ALERT_COUNT = 5    # 조건별 최대 알람 횟수 (이후 억제)
    COOLDOWN_SEC    = 60   # 동일 조건 재발생 쿨다운 (초)

    def __init__(
        self,
        on_alert: Optional[Callable] = None,  # (level: int, msg: str) → None
    ):
        self.on_alert = on_alert

        # 조건A 리스트 (CondARow)
        self.cond_a: List[CondARow] = []

        # 조건B 딕셔너리  key=(strike, opt_type)
        self.cond_b: Dict[tuple, CondBRow] = {}

        # 조건C (VIX) 단일 설정
        self.vix_pct:       float = 3.0    # 급등 기준 %
        self._vix_last_ts:  float = 0.0
        self._vix_count:    int   = 0

        # SPX tick 누적 버퍼 (timestamp, price) — 최대 90분치
        self._spx_buf: deque = deque(maxlen=5400)

        self._running: bool = False

    # ── 제어 ─────────────────────────────────────────────────

    def start(self) -> None:
        self._spx_buf.clear()
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def reset_counts(self) -> None:
        """알람 횟수 전체 초기화."""
        for row in self.cond_a:
            row._alert_count  = 0
            row._last_alert_ts = 0.0
        for row in self.cond_b.values():
            row._alert_count  = 0
            row._last_alert_ts = 0.0
        self._vix_count   = 0
        self._vix_last_ts = 0.0

    # ── 조건B 행사가 관리 ─────────────────────────────────────

    def add_strike(self, strike: float, opt_type: str,
                   pct: float, direction: str) -> bool:
        """조건B 행사가 추가. 최대 5개."""
        if len(self.cond_b) >= 5:
            return False
        key = (strike, opt_type.upper())
        self.cond_b[key] = CondBRow(
            strike=strike, opt_type=opt_type.upper(),
            pct=pct, direction=direction)
        return True

    def remove_strike(self, strike: float, opt_type: str) -> None:
        key = (strike, opt_type.upper())
        self.cond_b.pop(key, None)

    def clear_strikes(self) -> None:
        self.cond_b.clear()

    # ── 데이터 수신 (외부 호출) ───────────────────────────────

    def push_spx(self, price: float) -> None:
        """
        SPX tick 수신 시 호출. (price: 현재가)
        내부 deque 에 (timestamp, price) 누적.
        각 조건A 행의 minutes 설정에 따라 N분 전 가격과 비교.
        """
        if not self._running or price <= 0:
            return
        now = time.time()
        self._spx_buf.append((now, price))

        for row in self.cond_a:
            if not row.enabled:
                continue
            if row._alert_count >= self.MAX_ALERT_COUNT:
                continue
            # deque 에서 row.minutes 분 전 가격 탐색
            target_ts = now - row.minutes * 60.0
            price_then = None
            for ts, px in self._spx_buf:
                if ts <= target_ts:
                    price_then = px
            if price_then is None:
                continue  # 아직 N분치 데이터 미확보
            self._eval_cond_a(row, price_then, price)

    def push_opt(self, strike: float, opt_type: str,
                 price_now: float, price_prev: float) -> None:
        """옵션 tick 수신 시 호출."""
        if not self._running or price_prev <= 0:
            return
        key = (float(strike), opt_type.upper())
        row = self.cond_b.get(key)
        if row is None:
            return
        if row._alert_count >= self.MAX_ALERT_COUNT:
            return
        self._eval_cond_b(row, price_now, price_prev)

    def push_vix(self, vix_now: float, vix_prev: float) -> None:
        """VIX tick 수신 시 호출."""
        if not self._running or vix_prev <= 0:
            return
        if self._vix_count >= self.MAX_ALERT_COUNT:
            return
        chg_pct = (vix_now / vix_prev - 1.0) * 100.0
        if abs(chg_pct) >= self.vix_pct:
            now = time.time()
            if now - self._vix_last_ts < self.COOLDOWN_SEC:
                return
            self._vix_last_ts = now
            self._vix_count  += 1
            sign = "▲" if chg_pct > 0 else "▼"
            self._fire(2, f"조건C VIX {sign}{abs(chg_pct):.1f}% "
                          f"({vix_prev:.2f}→{vix_now:.2f})")

    # ── 내부 평가 ─────────────────────────────────────────────

    def _eval_cond_a(self, row: CondARow,
                     price_then: float, price_now: float) -> None:
        diff = price_now - price_then      # 양수=상승, 음수=하락
        abs_diff = abs(diff)
        if abs_diff < row.points:
            return

        dir_ok = False
        if row.direction == "양방향":
            dir_ok = True
        elif row.direction == "하락" and diff < 0:
            dir_ok = True
        elif row.direction == "상승" and diff > 0:
            dir_ok = True
        if not dir_ok:
            return

        now = time.time()
        if now - row._last_alert_ts < self.COOLDOWN_SEC:
            return
        row._last_alert_ts = now
        row._alert_count  += 1

        sign = "▼" if diff < 0 else "▲"
        label = f"{row.minutes}분" if row.minutes > 0 else "전일종가"
        self._fire(1, f"조건A SPX {sign}{abs_diff:.1f}pt "
                      f"({label} 대비, {price_then:.1f}→{price_now:.1f})")

    def _eval_cond_b(self, row: CondBRow,
                     price_now: float, price_prev: float) -> None:
        if price_prev <= 0:
            return
        chg_pct = (price_now / price_prev - 1.0) * 100.0
        abs_pct = abs(chg_pct)
        if abs_pct < row.pct:
            return

        dir_ok = False
        if row.direction == "양방향":
            dir_ok = True
        elif row.direction == "상승" and chg_pct > 0:
            dir_ok = True
        elif row.direction == "하락" and chg_pct < 0:
            dir_ok = True
        if not dir_ok:
            return

        now = time.time()
        if now - row._last_alert_ts < self.COOLDOWN_SEC:
            return
        row._last_alert_ts = now
        row._alert_count  += 1

        sign = "▲" if chg_pct > 0 else "▼"
        self._fire(2, f"조건B {row.opt_type} {row.strike:.0f} "
                      f"{sign}{abs_pct:.0f}% "
                      f"({price_prev:.2f}→{price_now:.2f})")

    def _fire(self, level: int, msg: str) -> None:
        if self.on_alert:
            try:
                self.on_alert(level, msg)
            except Exception:
                pass