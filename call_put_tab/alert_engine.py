"""
alert_engine.py — SPX 지수 변동 감시 엔진  v1.0
════════════════════════════════════════════════════
역할:
  - und_price 를 push() 받아 20분 롤링 버퍼에 누적
  - 조건 A (지수 낙폭) / B (옵션 급등) / C (VIX 급등) 평가
  - 조건 충족 시 AlertLogger 로 기록 + UI 콜백 호출
Python 3.8 호환 (deque, Optional, Callable)
════════════════════════════════════════════════════
"""

from __future__ import annotations
from collections import deque
from typing import Optional, Callable
import time


# ── 기본 설정값 ───────────────────────────────────────────────
DEFAULT_CFG = {
    "window_min": 20,    # 조건 A: 몇 분 전 대비
    "drop_pt":    15.0,  # 조건 A: 낙폭 기준 (포인트)
    "opt_pct":    200.0, # 조건 B: 옵션 급등 기준 (%)
    "vix_pct":    3.0,   # 조건 C: VIX 급등 기준 (%)
    "min_level":  1,     # 최소 알람 레벨 (1=A만, 2=A+B, 3=A+B+C)
    "cooldown_s": 60,    # 중복 알람 방지 쿨다운 (초)
}


class AlertEngine:
    """
    SPX 지수 변동 감시 엔진.
    외부에서 1분마다 push_spx() 호출 → 조건 평가 → 로그 기록.

    사용 예:
        engine = AlertEngine(cfg, logger, on_alert=self._on_alert)
        engine.push_spx(5820.0)
        engine.push_opt(3.50)   # 옵션가 (선택)
        engine.push_vix(18.5)   # VIX   (선택)
    """

    def __init__(
        self,
        cfg:      dict,
        logger,                          # AlertLogger 인스턴스
        on_alert: Optional[Callable] = None,  # UI 콜백 (level, msg) → None
    ):
        self.cfg      = {**DEFAULT_CFG, **cfg}
        self.logger   = logger
        self.on_alert = on_alert

        maxlen = self.cfg["window_min"]
        self._spx_buf: deque = deque(maxlen=maxlen)  # (timestamp, price)
        self._vix_buf: deque = deque(maxlen=5)       # vix price

        self._opt_base:  Optional[float] = None
        self._opt_price: Optional[float] = None
        self._last_alert_ts: float = 0.0
        self._running: bool = False

    # ── 공개 제어 메서드 ─────────────────────────────────────

    def start(self) -> None:
        self._spx_buf.clear()
        self._vix_buf.clear()
        self._opt_base  = None
        self._opt_price = None
        self._last_alert_ts = 0.0
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 데이터 수신 메서드 (외부에서 호출) ───────────────────

    def push_spx(self, price: float) -> None:
        """SPX 현재가 수신 (1분 단위 권장)."""
        if not self._running:
            return
        self._spx_buf.append((time.time(), price))
        self._evaluate()

    def push_opt(self, price: float) -> None:
        """0DTE 풋옵션 현재가 수신."""
        if not self._running:
            return
        if self._opt_base is None:
            self._opt_base = price   # 감시 시작 시점 기준가
        self._opt_price = price

    def push_vix(self, price: float) -> None:
        """VIX 현재가 수신."""
        if not self._running:
            return
        self._vix_buf.append(price)

    # ── 내부 평가 로직 ───────────────────────────────────────

    def _evaluate(self) -> None:
        if len(self._spx_buf) < 2:
            return

        now_price  = self._spx_buf[-1][1]
        past_price = self._spx_buf[0][1]
        drop       = past_price - now_price   # 양수 = 하락

        cond_a = drop >= self.cfg["drop_pt"]
        cond_b = self._check_opt_spike()
        cond_c = self._check_vix_spike()

        level = self._resolve_level(cond_a, cond_b, cond_c)
        if level is None:
            return
        if not self._cooldown_ok():
            return

        self._fire(level, drop, cond_b, cond_c)

    def _check_opt_spike(self) -> bool:
        if self._opt_base is None or self._opt_price is None:
            return False
        if self._opt_base <= 0:
            return False
        pct = (self._opt_price / self._opt_base - 1.0) * 100.0
        return pct >= self.cfg["opt_pct"]

    def _check_vix_spike(self) -> bool:
        if len(self._vix_buf) < 2:
            return False
        base = self._vix_buf[0]
        if base <= 0:
            return False
        chg = (self._vix_buf[-1] / base - 1.0) * 100.0
        return chg >= self.cfg["vix_pct"]

    def _resolve_level(self, a: bool, b: bool, c: bool) -> Optional[str]:
        min_lvl = self.cfg["min_level"]
        if a and b and c and min_lvl <= 3:
            return "LV3"
        if a and b and min_lvl <= 2:
            return "LV2"
        if a and min_lvl <= 1:
            return "LV1"
        return None

    def _cooldown_ok(self) -> bool:
        now = time.time()
        if now - self._last_alert_ts < self.cfg["cooldown_s"]:
            return False
        self._last_alert_ts = now
        return True

    def _fire(self, level: str, drop: float, cond_b: bool, cond_c: bool) -> None:
        window = self.cfg["window_min"]
        parts  = [f"SPX -{drop:.1f}P ({window}분 대비)"]
        if cond_b:
            pct = 0.0
            if self._opt_base and self._opt_price:
                pct = (self._opt_price / self._opt_base - 1.0) * 100.0
            parts.append(f"풋옵션 +{pct:.0f}%")
        if cond_c and len(self._vix_buf) >= 2:
            vix_chg = (self._vix_buf[-1] / self._vix_buf[0] - 1.0) * 100.0
            parts.append(f"VIX +{vix_chg:.1f}%")

        msg = " | ".join(parts)
        self.logger.write(level, msg)

        if self.on_alert:
            try:
                self.on_alert(level, msg)
            except Exception:
                pass

    # ── 현재 상태 조회 (UI 표시용) ───────────────────────────

    def status_text(self) -> str:
        """현재 버퍼 상태 한 줄 요약."""
        if not self._running:
            return "중지"
        n   = len(self._spx_buf)
        cap = self._spx_buf.maxlen or 0
        if n < 2:
            return f"수집 중 ({n}/{cap}분)"
        drop = self._spx_buf[0][1] - self._spx_buf[-1][1]
        return f"감시 중 | {n}/{cap}분 | 현재 낙폭 {drop:+.1f}P"
