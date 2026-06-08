"""
chart_daily_render.py — 일봉 렌더링 + 캘린더 중심 이동
[분리] chart_daily.py 에서 분리
  render_daily, center_on_calendar, _draw_cal_vline
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from chart_daily import _DailyCandle

def render_daily(self, df):
    """
    df: pd.DataFrame  columns=[t, o, h, l, c, v]
    daily_container 안을 비우고 캔들 + 볼륨 플롯 렌더링.
    캘린더 날짜가 x축 중앙에 오도록 범위 설정.
    """
    if df is None or (PANDAS and df.empty):
        self.status_lbl.setText("일봉 데이터 없음.")
        return

    layout = self.daily_container.layout()
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w: w.deleteLater()

    bars = list(df[["t","o","h","l","c","v"]].itertuples(index=False, name=None))

    candle_plot = pg.PlotWidget(background="#1a1a2e")
    candle_plot.setMenuEnabled(False)
    candle_plot.showGrid(x=False, y=True, alpha=0.15)
    candle_plot.getAxis("left").setTextPen(pg.mkPen("#aaaaaa"))
    candle_plot.getAxis("bottom").hide()
    candle_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    vol_plot = pg.PlotWidget(background="#1a1a2e")
    vol_plot.setMenuEnabled(False)
    vol_plot.setFixedHeight(80)
    vol_plot.getAxis("left").setTextPen(pg.mkPen("#888888"))

    dates = [datetime.fromtimestamp(b[0] / 1000).strftime("%y/%m/%d")
             for b in bars]
    step  = max(1, len(bars) // 10)
    ticks = [(i, dates[i]) for i in range(0, len(bars), step)]
    vol_plot.getAxis("bottom").setTicks([ticks])
    vol_plot.getAxis("bottom").setTextPen(pg.mkPen("#777777"))

    candle_plot.setXLink(vol_plot)

    candle_data = [(i, b[1], b[2], b[3], b[4]) for i, b in enumerate(bars)]
    candle_plot.addItem(_DailyCandle(candle_data, body_w=0.55))

    for i, b in enumerate(bars):
        col = "#26a69a" if b[4] >= b[1] else "#ef5350"
        vol_plot.addItem(pg.BarGraphItem(
            x=[i], height=[b[5]], width=0.6,
            brush=pg.mkBrush(col), pen=pg.mkPen(None)))

    center_on_calendar(self, candle_plot, bars)

    candle_plot.getViewBox().disableAutoRange()
    vol_plot.getViewBox().disableAutoRange()

    layout.addWidget(candle_plot, stretch=4)
    layout.addWidget(vol_plot,    stretch=1)

    sym      = self.sym_in.text().strip().upper()
    cal_date = self.calendar.selectedDate().toString("yyyy-MM-dd")
    self.status_lbl.setText(
        f"📈 일봉  {sym}  ·  {cal_date} 중심  ·  {len(bars)}봉")


def center_on_calendar(self, plot, bars):
    """캘린더 선택 날짜가 x축 중앙에 오도록 뷰 범위 설정."""
    cal_date = self.calendar.selectedDate().toPyDate()

    best_idx, best_delta = None, timedelta(days=9999)
    for i, b in enumerate(bars):
        delta = abs(datetime.fromtimestamp(b[0] / 1000).date() - cal_date)
        if delta < best_delta:
            best_delta = delta; best_idx = i

    if best_idx is None:
        return

    half  = 50
    x_min = max(0, best_idx - half)
    x_max = min(len(bars) - 1, best_idx + half)
    plot.setXRange(x_min, x_max, padding=0.02)

    visible = bars[x_min: x_max + 1]
    if visible:
        y_lo = min(b[3] for b in visible)
        y_hi = max(b[2] for b in visible)
        margin = (y_hi - y_lo) * 0.06
        plot.setYRange(y_lo - margin, y_hi + margin, padding=0)

    if hasattr(plot, '_cal_vline') and plot._cal_vline is not None:
        try:
            plot.removeItem(plot._cal_vline)
        except Exception:
            pass
    plot._cal_vline = None
    for i, b in enumerate(bars):
        if datetime.fromtimestamp(b[0] / 1000).date() == cal_date:
            vline = pg.InfiniteLine(
                pos=i, angle=90,
                pen=pg.mkPen("#f9a825", width=1, style=Qt.DashLine),
                label=str(cal_date),
                labelOpts={"color": "#f9a825", "position": 0.92})
            plot.addItem(vline)
            plot._cal_vline = vline
            break


def _draw_cal_vline(plot, bars, calendar):
    cal_date = calendar.selectedDate().toPyDate()
    for i, b in enumerate(bars):
        if datetime.fromtimestamp(b[0] / 1000).date() == cal_date:
            plot.addItem(pg.InfiniteLine(
                pos=i, angle=90,
                pen=pg.mkPen("#f9a825", width=1, style=Qt.DashLine),
                label=str(cal_date),
                labelOpts={"color": "#f9a825", "position": 0.92}))
            break