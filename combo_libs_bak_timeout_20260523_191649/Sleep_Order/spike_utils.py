"""
spike_utils.py — 급락 캐치 공통 유틸  v1.0
════════════════════════════════════════
_tg, _tick_size, _in_time_window
spike_catcher_debit / single 양쪽에서 import.
"""
from __future__ import annotations


def tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[SpikeUtil] TG 실패: {e}")


def tick_size(price: float) -> float:
    return 0.10 if price >= 3.0 else 0.05


def in_time_window(start: str, end: str) -> bool:
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.utcnow()
        sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
        n = now.hour * 60 + now.minute
        s = sh * 60 + sm;  e = eh * 60 + em
        return (s <= n <= e) if s <= e else (n >= s or n <= e)
    except Exception:
        return False


def calc_lmt(price: float, ask: float, order_mode: str,
             fixed_price: float) -> float:
    """주문가 계산 (ask+1 or 고정). 공통 로직."""
    if order_mode == "ask+1":
        base = ask if ask > 0 else price
        return round(base + tick_size(base), 2)
    return fixed_price


def calc_qty(lmt: float, budget: int) -> int:
    cost = lmt * 100
    return max(1, int(budget // cost)) if cost > 0 else 1
