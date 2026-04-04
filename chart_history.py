"""
chart_history.py — 일봉/분봉 히스토리 조회 + OHLC 캔들 렌더러
"""

import threading
from datetime import datetime, timedelta, date as _date

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from chart_utils import polygon_aggs, _FetchSignal
from chart_ibkr import IbkrHistMixin


# ──────────────────────────────────────────────────────────────
# X축 틱 간격 계산
# ──────────────────────────────────────────────────────────────
def _calc_x_tick_interval(n: int) -> int:
    if n <= 30:  return 5
    if n <= 100: return 10
    if n <= 300: return 30
    return 60


# ──────────────────────────────────────────────────────────────
# OHLC 캔들 공통 렌더러
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
        pw.addItem(wick)
        items_list.append(wick)

        body_h = abs(c - o) or max((h - l) * 0.05, 0.01)
        rect = pg.QtWidgets.QGraphicsRectItem(t - half, min(o, c), half * 2, body_h)
        rect.setBrush(pg.mkBrush(color))
        rect.setPen(pg.mkPen(color, width=0.5))
        pw.addItem(rect)
        items_list.append(rect)

        xs.append(t)
        ys_close.append(c)
        y_all += [l, h]

    if len(xs) > 1:
        cl = pw.plot(x=xs, y=ys_close,
                     pen=pg.mkPen('#ffffff', width=0.5, style=Qt.DotLine))
        items_list.append(cl)

    if y_all:
        y_min, y_max = min(y_all), max(y_all)
        pad = (y_max - y_min) * 0.05 or y_min * 0.005
        pw.setYRange(y_min - pad, y_max + pad, padding=0)

    n = len(xs)
    step = _calc_x_tick_interval(n)

    if bar_width_sec >= 60 * 60 * 12:
        fmt = "%m/%d"
    elif bar_width_sec >= 60 * 60:
        fmt = "%m/%d\n%H:%M"
    else:
        fmt = "%H:%M"

    ticks = []
    for i in range(0, n, step):
        try:
            label = datetime.utcfromtimestamp(xs[i]).strftime(fmt)
        except Exception:
            label = ""
        ticks.append((xs[i], label))

    if xs and (n - 1) % step != 0:
        try:
            label = datetime.utcfromtimestamp(xs[-1]).strftime(fmt)
        except Exception:
            label = ""
        ticks.append((xs[-1], label))

    ax = pw.getAxis('bottom')
    ax.setTicks([ticks])
    ax.setStyle(tickFont=QFont("Consolas", 8),
                tickTextOffset=4,
                autoExpandTextSpace=False,
                tickTextWidth=52,
                tickTextHeight=28,
                stopAxisAtTick=(True, True))
    try:
        ax.setRotation(-45)
    except AttributeError:
        pass

    if xs:
        margin = bar_width_sec * 2
        pw.setXRange(xs[0] - margin, xs[-1] + margin, padding=0)


# ──────────────────────────────────────────────────────────────
# HistoryMixin — 일봉/분봉 조회 메서드 (ChartMixin에 포함)
# ──────────────────────────────────────────────────────────────
class HistoryMixin(IbkrHistMixin):

    # ── 기초자산 클릭 ──────────────────────────────────────────
    def _on_und_label_clicked(self):
        from core import is_market_open
        if is_market_open():
            self._log("⚡ 장 운영 중 — 히스토리 차트는 장외 시간에만 조회됩니다.")
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(0)
            return
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self, '_chart_tabs') else 1
        if cur_tab == 2:
            self._fetch_intraday()
        else:
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)
            self._fetch_daily(on_done_extra=self._fetch_intraday)

    # ── 일봉 조회 ─────────────────────────────────────────────
    def _fetch_daily(self, on_done_extra=None):
        sym = (self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
               if hasattr(self, 'edit_sym') else "SPX")
        days_map = {"1개월": 30, "3개월": 90, "6개월": 180, "1년": 365}
        days  = days_map.get(self.combo_daily_period.currentText(), 365)
        end   = datetime.today().date()
        start = end - timedelta(days=days)
        self.lbl_daily_status.setText(f"조회 중… {sym} 일봉")

        sig = _FetchSignal()

        def _done(bars):
            self._on_daily_done(bars, sym)
            if callable(on_done_extra):
                on_done_extra()

        def _err(e):
            self._on_daily_err(e, sym, start, end, on_done_extra=on_done_extra)

        sig.done.connect(_done)
        sig.err.connect(_err)

        def _run():
            bars = polygon_aggs(sym, start, end, 1, "day")
            if bars: sig.done.emit(bars)
            else:    sig.err.emit("Polygon 실패 → IBKR 시도")

        threading.Thread(target=_run, daemon=True).start()

    def _on_daily_done(self, bars, sym):
        self.lbl_daily_status.setText(f"✅ {sym} 일봉  {len(bars)}봉")
        draw_ohlc_candles(self._pw_daily, self._daily_items, bars,
                          bar_width_sec=60 * 60 * 18)

    def _on_daily_err(self, msg, sym, start, end, on_done_extra=None):
        self.lbl_daily_status.setText(f"⚠ {msg}")
        days_map = {"1개월": "1 M", "3개월": "3 M", "6개월": "6 M", "1년": "1 Y"}
        dur = days_map.get(self.combo_daily_period.currentText(), "6 M")

        def _after_ibkr(bars):
            self._on_daily_done(bars, sym)
            if callable(on_done_extra):
                on_done_extra()

        self._ibkr_hist(sym, dur, "1 day", 9800,
                        _after_ibkr, self.lbl_daily_status,
                        on_timeout=on_done_extra)

    # ── 분봉 조회 ─────────────────────────────────────────────
    def _fetch_intraday(self):
        sym = (self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
               if hasattr(self, 'edit_sym') else "SPX")
        tf_map = {"1분": 1, "5분": 5, "15분": 15, "30분": 30, "60분": 60}
        tf = tf_map.get(self.combo_intra_tf.currentText(), 1)
        max_bars = getattr(self, 'spin_intra_bars', None)
        max_bars = max_bars.value() if max_bars else 399

        need_days = max(1, int(max_bars * tf / 390) + 3)
        end   = datetime.today().date()
        start = end - timedelta(days=need_days)
        self.lbl_intra_status.setText(f"조회 중… {sym} {tf}분봉 (최대 {max_bars}봉)")

        sig = _FetchSignal()
        sig.done.connect(lambda bars: self._on_intra_done(bars, sym, tf, max_bars))
        sig.err.connect(lambda e: self._on_intra_err(e, sym, tf, need_days, max_bars))

        def _run():
            bars = polygon_aggs(sym, start, end, tf, "minute")
            if bars: sig.done.emit(bars)
            else:    sig.err.emit("Polygon 실패 → IBKR 시도")

        threading.Thread(target=_run, daemon=True).start()

    def _on_intra_done(self, bars, sym, tf, max_bars=399):
        ext = getattr(self, 'chk_intra_ext', None)
        include_ext = ext.isChecked() if ext else False

        if not include_ext:
            def _is_regular(ts_unix):
                dt = datetime.utcfromtimestamp(ts_unix)
                offset = 4 if 3 <= dt.month <= 10 else 5
                et = dt.hour * 60 + dt.minute - offset * 60
                return 570 <= et < 960
            bars = [b for b in bars if _is_regular(b["t"])]

        if len(bars) > max_bars:
            bars = bars[-max_bars:]

        ext_label = "(정규+시간외)" if include_ext else "(정규장)"
        self.lbl_intra_status.setText(f"✅ {sym} {tf}분봉  {len(bars)}봉 {ext_label}")
        draw_ohlc_candles(self._pw_intra, self._intra_items, bars,
                          bar_width_sec=tf * 60 * 0.7)

    def _on_intra_err(self, msg, sym, tf, need_days, max_bars=399):
        self.lbl_intra_status.setText(f"⚠ {msg}")
        if need_days <= 1:   dur = "1 D"
        elif need_days <= 2: dur = "2 D"
        elif need_days <= 5: dur = "1 W"
        else:                dur = "2 W"
        bar_size = ("1 min" if tf == 1 else f"{tf} mins") if tf < 60 else "1 hour"
        self._ibkr_hist(sym, dur, bar_size, 9801,
                        lambda bars: self._on_intra_done(bars, sym, tf, max_bars),
                        self.lbl_intra_status,
                        on_timeout=None)

