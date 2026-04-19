"""
trade_log/price_buffer.py — 기초자산 가격 타임스탬프 버퍼
_update_price_panel() 틱마다 push → 체결 시 5분/10분 전 값 조회

사용:
    from trade_log.price_buffer import UndBuffer
    _und_buf = UndBuffer()          # 전역 1개
    _und_buf.push(5480.5)           # 틱마다 호출
    ctx = _und_buf.get_context()    # 체결 시 호출
    # → {und_price, und_5m, und_10m, chg_5m, chg_10m}
"""

from __future__ import annotations
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Optional

_ET = timezone(timedelta(hours=-5))
_5M  = timedelta(minutes=5)
_10M = timedelta(minutes=10)


class UndBuffer:
    """
    (datetime, price) 쌍을 최대 15분치 보관.
    5초마다 틱이 온다고 가정 → 15분 = 180개 → maxlen=200 여유분 포함.
    """
    def __init__(self, maxlen: int = 200):
        self._buf: deque[tuple[datetime, float]] = deque(maxlen=maxlen)

    def push(self, price: float) -> None:
        """기초자산 가격 1개 push. _update_price_panel() 에서 호출."""
        if price and price > 0:
            self._buf.append((datetime.now(_ET), price))

    def get_context(self) -> dict:
        """
        체결 시점에 호출.
        반환: {und_price, und_5m, und_10m, chg_5m, chg_10m}
        값 없으면 None.
        """
        if not self._buf:
            return {k: None for k in
                    ("und_price", "und_5m", "und_10m", "chg_5m", "chg_10m")}

        now      = datetime.now(_ET)
        cur      = self._buf[-1][1]
        p_5m     = self._closest_before(now - _5M)
        p_10m    = self._closest_before(now - _10M)
        chg_5m   = round(cur - p_5m,  2) if p_5m  else None
        chg_10m  = round(cur - p_10m, 2) if p_10m else None

        return {
            "und_price": cur,
            "und_5m":    p_5m,
            "und_10m":   p_10m,
            "chg_5m":    chg_5m,
            "chg_10m":   chg_10m,
        }

    def _closest_before(self, target: datetime) -> Optional[float]:
        """target 시각 이전의 가장 가까운 가격 반환."""
        result = None
        for ts, price in self._buf:
            if ts <= target:
                result = price
            else:
                break
        return result


# ── 전역 싱글턴 ───────────────────────────────────────────────
_global_buf = UndBuffer()

def push(price: float) -> None:
    _global_buf.push(price)

def get_context() -> dict:
    return _global_buf.get_context()
