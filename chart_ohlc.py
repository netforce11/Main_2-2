"""
chart_ohlc.py — OHLC renderer + bar conversion helpers  [NEW — S6]
Extracted from chart_history.py to keep both files ≤ 300 lines.
"""

from datetime import datetime
from typing import List, Dict, Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False


# ──────────────────────────────────────────────────────────────
# X-axis tick interval helper
# ──────────────────────────────────────────────────────────────
def _calc_x_tick_interval(n: int) -> int:
    if n <= 30:  return 5
    if n <= 100: return 10
    if n <= 300: return 30
    return 60


# ──────────────────────────────────────────────────────────────
# OHLC candle renderer for pyqtgraph (daily tab)
# ──────────────────────────────────────────────────────────────
def draw_ohlc_candles(pw, items_list: list, bars: list,
                      bar_width_sec: float = 3600):
    if not PG or not bars:
        return

    for it in items_list:
        try:
            pw.removeItem(it)
        except Exception:
            pass
    items_list.clear()

    half = bar_width_sec * 0.45
    xs, ys_close, y_all = [], [], []

    for b in bars:
        t = b["t"]
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        color = "#00e676" if c >= o else "#ff5252"

        wick = pg.PlotDataItem(x=[t, t], y=[l, h], pen=pg.mkPen(color, width=1))
        pw.addItem(wick); items_list.append(wick)

        body_h = abs(c - o) or max((h - l) * 0.05, 0.01)
        rect = pg.QtWidgets.QGraphicsRectItem(t - half, min(o, c), half * 2, body_h)
        rect.setBrush(pg.mkBrush(color))
        rect.setPen(pg.mkPen(color, width=0.5))
        pw.addItem(rect); items_list.append(rect)

        xs.append(t); ys_close.append(c); y_all += [l, h]

    if len(xs) > 1:
        cl = pw.plot(x=xs, y=ys_close,
                     pen=pg.mkPen('#ffffff', width=0.5, style=Qt.DotLine))
        items_list.append(cl)

    if y_all:
        y_min, y_max = min(y_all), max(y_all)
        pad = (y_max - y_min) * 0.05 or y_min * 0.005
        pw.setYRange(y_min - pad, y_max + pad, padding=0)

    n    = len(xs)
    step = _calc_x_tick_interval(n)
    fmt  = "%m/%d" if bar_width_sec >= 60*60*12 else (
           "%m/%d\n%H:%M" if bar_width_sec >= 3600 else "%H:%M")

    ticks = []
    for i in range(0, n, step):
        try:   label = datetime.utcfromtimestamp(xs[i]).strftime(fmt)
        except Exception: label = ""
        ticks.append((xs[i], label))
    if xs and (n - 1) % step != 0:
        try:   label = datetime.utcfromtimestamp(xs[-1]).strftime(fmt)
        except Exception: label = ""
        ticks.append((xs[-1], label))

    ax = pw.getAxis('bottom')
    ax.setTicks([ticks])
    ax.setStyle(tickFont=QFont("Consolas", 8), tickTextOffset=4,
                autoExpandTextSpace=False, tickTextWidth=52,
                tickTextHeight=28, stopAxisAtTick=(True, True))
    try:
        ax.setRotation(-45)
    except AttributeError:
        pass
    if xs:
        pw.setXRange(xs[0] - bar_width_sec * 2,
                     xs[-1] + bar_width_sec * 2, padding=0)


# ──────────────────────────────────────────────────────────────
# Timezone helper
# ──────────────────────────────────────────────────────────────
try:
    from zoneinfo import ZoneInfo as _ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo as _ZoneInfo
    except ImportError:
        import pytz as _pytz
        class _ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

_ET_ZONE = _ZoneInfo("America/New_York")
_KST_ZONE = _ZoneInfo("Asia/Seoul")


def _utc_to_et(unix_sec: float) -> datetime:
    from datetime import timezone
    utc_dt = datetime.fromtimestamp(unix_sec, tz=timezone.utc)
    return utc_dt.astimezone(_ET_ZONE)


def _utc_to_kst(unix_sec: float) -> datetime:
    from datetime import timezone
    utc_dt = datetime.fromtimestamp(unix_sec, tz=timezone.utc)
    return utc_dt.astimezone(_KST_ZONE)


def _bars_to_rows(bars: List[Dict[str, Any]],
                  include_ext: bool = False,
                  tf_min: int = 1,
                  use_kst: bool = False) -> List[Dict[str, Any]]:
    """Convert IBKR bar list to MiniChartCanvas row format.
    use_kst=True → timestamps shown in KST (Korea Standard Time).
    """
    def _is_regular(unix_sec: float) -> bool:
        try:
            et = _utc_to_et(unix_sec)
            et_min = et.hour * 60 + et.minute
            return 570 <= et_min < 960   # 09:30=570, 16:00=960
        except Exception:
            return True

    if not include_ext:
        filtered = [b for b in bars if _is_regular(b["t"])]
        if filtered:
            bars = filtered

    _convert = _utc_to_kst if use_kst else _utc_to_et

    rows = []
    for b in bars:
        try:
            dt = _convert(b["t"])
            rows.append({
                "time":   dt.strftime("%H:%M"),
                "open":   float(b.get("o", 0)),
                "high":   float(b.get("h", 0)),
                "low":    float(b.get("l", 0)),
                "close":  float(b.get("c", 0)),
                "volume": float(b.get("v", 0)),
            })
        except Exception:
            continue
    return rows
