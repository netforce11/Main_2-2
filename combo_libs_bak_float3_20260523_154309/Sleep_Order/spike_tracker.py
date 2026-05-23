"""
spike_tracker.py — 급락 캐치 기준가 트래커  v1.0
════════════════════════════════════════
PriceRefTracker    : 틱 N개 평균 (mode=tick)
PriceTimeRefTracker: 시간 기준 최고가 확정 (mode=time)
"""
from __future__ import annotations
import threading
import time as _time
from collections import deque
from typing import List, Optional, Tuple


class PriceRefTracker:
    """최근 N개 틱 평균을 ref_price 로 사용."""

    def __init__(self, window: int = 7):
        self._window = max(1, window)
        self._prices: deque = deque(maxlen=self._window)
        self._lock = threading.Lock()

    def set_window(self, window: int) -> None:
        with self._lock:
            self._window = max(1, window)
            self._prices = deque(list(self._prices)[-self._window:],
                                 maxlen=self._window)

    def update(self, price: float) -> None:
        if price <= 0:
            return
        with self._lock:
            self._prices.append(price)

    @property
    def ref_price(self) -> Optional[float]:
        with self._lock:
            if not self._prices:
                return None
            return sum(self._prices) / len(self._prices)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._prices)

    def reset(self) -> None:
        with self._lock:
            self._prices.clear()


class PriceTimeRefTracker:
    """
    감시 시작 후 N분간 수신된 가격 중 최고가를 기준가로 확정.
    N분 경과 전에는 ref_price = None (수집 중).
    확정 후 reset() 전까지 변경되지 않음.
    """

    def __init__(self, minutes: int = 3):
        self._minutes = max(1, minutes)
        self._samples: List[Tuple[float, float]] = []
        self._ref_fixed: Optional[float] = None
        self._lock = threading.Lock()

    def set_minutes(self, minutes: int) -> None:
        with self._lock:
            self._minutes = max(1, minutes)
            self._ref_fixed = None
            self._prune()

    def update(self, price: float) -> None:
        if price <= 0:
            return
        with self._lock:
            if self._ref_fixed is not None:
                return
            now = _time.monotonic()
            self._samples.append((now, price))
            self._prune()
            if self._samples:
                elapsed = now - self._samples[0][0]
                if elapsed >= self._minutes * 60:
                    self._ref_fixed = max(p for _, p in self._samples)
                    print(f"[SpikeTracker] 기준가 확정 ${self._ref_fixed:.2f}"
                          f"  ({len(self._samples)}샘플 / {elapsed/60:.1f}분)")

    def _prune(self) -> None:
        if not self._samples:
            return
        cutoff = _time.monotonic() - self._minutes * 60
        self._samples = [(t, p) for t, p in self._samples if t >= cutoff]

    @property
    def ref_price(self) -> Optional[float]:
        with self._lock:
            return self._ref_fixed

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def seconds_until_ready(self) -> float:
        with self._lock:
            if self._ref_fixed is not None:
                return 0.0
            if not self._samples:
                return float(self._minutes * 60)
            elapsed = _time.monotonic() - self._samples[0][0]
            return max(0.0, self._minutes * 60 - elapsed)

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._ref_fixed = None


def build_tracker(ref_mode: str, minutes: int, window: int):
    """설정값으로 트래커 생성. spike_catcher 에서 사용."""
    if ref_mode == "time":
        return PriceTimeRefTracker(minutes=minutes)
    return PriceRefTracker(window=window)
