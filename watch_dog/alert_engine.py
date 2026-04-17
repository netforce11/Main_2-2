"""
alert_engine.py — 감시 조건 A/B/C 처리 엔진
- 조건A: SPX 등락 (행 1/2 각각 독립, 방향 선택)
- 조건B: 선택 행사가 옵션 등락률 500% 이상 (최대 5개)
- 조건C: VIX 급등 %
- 알람 5회 도달 시 해당 조건만 중지 (감시는 유지)
- 콜백으로 알람 통보 → alert_notifier.py 가 처리
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

MAX_ALERT_COUNT = 5          # 조건별 최대 알람 횟수
COOLDOWN_SEC    = 60         # 동일 조건 재발생 쿨다운(초)


# ── 데이터 클래스 ─────────────────────────────────────────

@dataclass
class CondARow:
    """조건A 한 행 (두 행 독립 운영)"""
    minutes: int   = 5        # N분 전 대비
    points: float  = 5.0      # 포인트 기준
    direction: str = "하락"   # "상승" | "하락" | "양방향"
    enabled: bool  = True

@dataclass
class CondBStrike:
    """조건B 행사가 하나"""
    strike: float
    opt_type: str             # "C" | "P"
    pct_threshold: float = 500.0
    direction: str = "양방향" # "상승" | "하락" | "양방향"

@dataclass
class CondC:
    pct_threshold: float = 20.0
    enabled: bool = True

@dataclass
class AlertState:
    """조건별 발생 횟수 및 마지막 시각"""
    count: int = 0
    last_ts: Optional[datetime] = None

    def is_suppressed(self) -> bool:
        return self.count >= MAX_ALERT_COUNT

    def can_fire(self) -> bool:
        if self.is_suppressed():
            return False
        if self.last_ts is None:
            return True
        elapsed = (datetime.now() - self.last_ts).total_seconds()
        return elapsed >= COOLDOWN_SEC

    def record(self):
        self.count += 1
        self.last_ts = datetime.now()


# ── 엔진 ──────────────────────────────────────────────────

class AlertEngine:
    """
    외부에서 push_spx / push_opt / push_vix 로 최신 데이터를 밀어준다.
    조건 충족 시 on_alert(level, msg) 콜백 호출.
    """

    def __init__(self, on_alert: Callable[[int, str], None]):
        self.on_alert = on_alert

        # 조건 설정
        self.cond_a: List[CondARow] = [CondARow(), CondARow()]
        self.cond_b: List[CondBStrike] = []   # 최대 5개
        self.cond_c: CondC = CondC()

        # 상태 추적
        self._spx_history: Dict[int, float] = {}  # minutes → price
        self._opt_prev: Dict[float, float]  = {}  # strike → prev_price
        self._vix_prev: Optional[float]     = None

        # 알람 카운터 (키: "A0","A1","B{strike}","C")
        self._states: Dict[str, AlertState] = {}

        self._running = False

    # ── 공개 제어 ──────────────────────────────────────────

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def reset_counts(self):
        self._states.clear()

    # ── 조건B 행사가 관리 ──────────────────────────────────

    def add_strike(self, strike: float, opt_type: str,
                   pct: float = 500.0, direction: str = "양방향") -> bool:
        if len(self.cond_b) >= 5:
            return False
        if any(b.strike == strike and b.opt_type == opt_type for b in self.cond_b):
            return False
        self.cond_b.append(CondBStrike(strike, opt_type, pct, direction))
        return True

    def remove_strike(self, strike: float, opt_type: str):
        self.cond_b = [b for b in self.cond_b
                       if not (b.strike == strike and b.opt_type == opt_type)]

    # ── 데이터 수신 ────────────────────────────────────────

    def push_spx(self, minutes_ago: int, price_then: float, price_now: float):
        """N분 전 가격과 현재 가격을 받아 조건A 행별로 평가"""
        if not self._running:
            return
        change = price_now - price_then  # 양수=상승, 음수=하락
        for idx, row in enumerate(self.cond_a):
            if not row.enabled or row.minutes != minutes_ago:
                continue
            self._eval_cond_a(idx, row, change)

    def push_opt(self, strike: float, opt_type: str,
                 price_now: float, price_prev: float):
        """옵션 현재/이전 가격 → 조건B 평가"""
        if not self._running:
            return
        if price_prev <= 0:
            return
        pct = (price_now - price_prev) / price_prev * 100
        for b in self.cond_b:
            if b.strike == strike and b.opt_type == opt_type:
                self._eval_cond_b(b, pct)

    def push_vix(self, vix_now: float, vix_prev: float):
        """VIX 현재/이전 → 조건C 평가"""
        if not self._running or not self.cond_c.enabled:
            return
        if vix_prev <= 0:
            return
        pct = (vix_now - vix_prev) / vix_prev * 100
        if abs(pct) >= self.cond_c.pct_threshold:
            self._fire("C", 3, f"VIX 급등 {pct:+.1f}%")

    # ── 내부 평가 ──────────────────────────────────────────

    def _eval_cond_a(self, idx: int, row: CondARow, change: float):
        direction_ok = (
            row.direction == "양방향"
            or (row.direction == "하락" and change <= -row.points)
            or (row.direction == "상승" and change >= row.points)
        )
        if not direction_ok:
            return
        if abs(change) < row.points:
            return
        arrow = "▼" if change < 0 else "▲"
        msg = (f"[조건A-{idx+1}] SPX {arrow}{abs(change):.1f}pt "
               f"({row.minutes}분 전 대비) | 기준 {row.points}pt/{row.direction}")
        level = 1
        self._fire(f"A{idx}", level, msg)

    def _eval_cond_b(self, b: CondBStrike, pct: float):
        direction_ok = (
            b.direction == "양방향"
            or (b.direction == "상승" and pct >= b.pct_threshold)
            or (b.direction == "하락" and pct <= -b.pct_threshold)
        )
        if not direction_ok or abs(pct) < b.pct_threshold:
            return
        arrow = "▲" if pct > 0 else "▼"
        msg = (f"[조건B] {b.opt_type} {b.strike} "
               f"{arrow}{abs(pct):.0f}% | 기준 {b.pct_threshold:.0f}%/{b.direction}")
        key = f"B{b.strike}{b.opt_type}"
        self._fire(key, 2, msg)

    def _fire(self, key: str, level: int, msg: str):
        state = self._states.setdefault(key, AlertState())
        if not state.can_fire():
            if state.is_suppressed():
                logger.debug("억제됨 key=%s count=%d", key, state.count)
            return
        state.record()
        suppressed_note = ""
        if state.count >= MAX_ALERT_COUNT:
            suppressed_note = f" [이 조건 알람 {MAX_ALERT_COUNT}회 도달 → 이후 억제]"
        full_msg = f"LV{level} {msg}{suppressed_note}"
        logger.info(full_msg)
        self.on_alert(level, full_msg)

    # ── 조회 ──────────────────────────────────────────────

    def get_counts(self) -> Dict[str, int]:
        return {k: s.count for k, s in self._states.items()}

    def total_alert_count(self) -> int:
        return sum(s.count for s in self._states.values())

    def is_running(self) -> bool:
        return self._running