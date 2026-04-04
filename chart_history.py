"""
chart_history.py — daily/intraday history fetch + OHLC renderers
Changes:
  - _fetch_intraday()  : IBKR-only (Polygon fallback removed)
  - _on_intra_done()   : renders via MiniChartCanvas (matplotlib candle/line)
                         matching spxw_core / spxw_1min_tab style
  - _redraw_intraday_cache(): re-render on chart-mode toggle without re-fetch
  - Daily tab rendering unchanged (pyqtgraph draw_ohlc_candles)
"""

import threading
from datetime import datetime, timedelta, date as _date
from typing import List, Dict, Any

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
# X-axis tick interval helper
# ──────────────────────────────────────────────────────────────
def _calc_x_tick_interval(n: int) -> int:
    if n <= 30:  return 5
    if n <= 100: return 10
    if n <= 300: return 30
    return 60


# ──────────────────────────────────────────────────────────────
# OHLC candle renderer for pyqtgraph (daily tab — unchanged)
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

    n    = len(xs)
    step = _calc_x_tick_interval(n)
    fmt  = "%m/%d" if bar_width_sec >= 60*60*12 else (
           "%m/%d\n%H:%M" if bar_width_sec >= 3600 else "%H:%M")

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
# Convert pyqtgraph-style bar dicts to spxw_core row dicts
# Input : [{"t": unix_sec, "o":, "h":, "l":, "c":, "v":}, ...]
# Output: [{"time": "HH:MM", "open":, "high":, "low":, "close":, "volume":}, ...]
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


def _utc_to_et(unix_sec: float) -> datetime:
    """UTC unix timestamp → ET-aware datetime."""
    from datetime import timezone
    utc_dt = datetime.fromtimestamp(unix_sec, tz=timezone.utc)
    return utc_dt.astimezone(_ET_ZONE)


def _bars_to_rows(bars: List[Dict[str, Any]],
                  include_ext: bool = False,
                  tf_min: int = 1) -> List[Dict[str, Any]]:
    """
    Convert IBKR bar list to MiniChartCanvas row format.
    - Timestamps are converted UTC → ET before display.
    - Regular session filter (09:30-16:00 ET) applied when include_ext=False.
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

    rows = []
    for b in bars:
        try:
            et = _utc_to_et(b["t"])
            rows.append({
                "time":   et.strftime("%H:%M"),   # ET 기준 시각
                "open":   float(b.get("o", 0)),
                "high":   float(b.get("h", 0)),
                "low":    float(b.get("l", 0)),
                "close":  float(b.get("c", 0)),
                "volume": float(b.get("v", 0)),
            })
        except Exception:
            continue

    return rows


# ──────────────────────────────────────────────────────────────
# HistoryMixin
# ──────────────────────────────────────────────────────────────
class HistoryMixin(IbkrHistMixin):

    # ── underlying label click ────────────────────────────────
    def _on_und_label_clicked(self):
        from core import is_market_open
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self, '_chart_tabs') else 1

        if is_market_open():
            # 장중: 분봉 탭이면 그대로 조회, 아니면 실시간 탭으로 전환
            if cur_tab == 2:
                self._fetch_intraday()
            else:
                self._log("⚡ 장 운영 중 — 실시간 탭으로 전환합니다.")
                if hasattr(self, '_chart_tabs'):
                    self._chart_tabs.setCurrentIndex(0)
            return

        # 장외: 분봉 탭이면 바로 조회, 아니면 일봉 -> 분봉 순서로 조회
        if cur_tab == 2:
            self._fetch_intraday()
        else:
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)
            self._fetch_daily(on_done_extra=self._fetch_intraday)

    # ── Daily (pyqtgraph — unchanged) ────────────────────────
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

    def _get_chart_sym(self) -> str:
        """
        현재 선택된 심볼을 반환. 여러 속성명을 순서대로 탐색한다.
          edit_sym  : 콜-풋 탭 (QLineEdit)
          _current_sym / _chart_sym / und_sym : 기타 탭 문자열 속성
        모두 없으면 "SPX" 반환.
        """
        for attr in ("edit_sym",):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    return w.text().strip().upper().replace("SPXW", "SPX") or "SPX"
                except AttributeError:
                    pass
        for attr in ("_current_sym", "_chart_sym", "und_sym", "_sym"):
            v = getattr(self, attr, None)
            if isinstance(v, str) and v.strip():
                return v.strip().upper().replace("SPXW", "SPX")
        return "SPX"

    # ── Intraday — IBKR only, MiniChartCanvas render ─────────
    def _fetch_intraday(self):
        """
        Request intraday bars directly from IBKR (no Polygon fallback).
        체인 구독(_fetch_busy)과 완전히 독립 — 체인 구독 중에도 호출 가능.
        진행 중인 이전 분봉 요청은 취소 후 새 요청 시작.
        """
        # 연결 체크 — _fetch_busy 와 무관하게 독립 판단
        if not getattr(self, 'mw', None) or not self.mw.connected:
            if hasattr(self, 'lbl_intra_status'):
                self.lbl_intra_status.setText("❌ TWS/Gateway 연결 필요")
            return

        # 진행 중인 분봉 요청 취소 (req_id=9801 고정)
        if hasattr(self, '_hist_router') and 9801 in self._hist_router:
            self._hist_router[9801]["done"] = True   # 폴링 타이머 즉시 종료
            try:
                self.mw.ib.cancelHistoricalData(9801)
            except Exception:
                pass

        sym = self._get_chart_sym()

        tf_map = {"1분": 1, "5분": 5, "15분": 15, "30분": 30, "60분": 60}
        tf = tf_map.get(self.combo_intra_tf.currentText(), 1)

        max_bars = (self.spin_intra_bars.value()
                    if hasattr(self, 'spin_intra_bars') else 399)

        # Duration string for IBKR reqHistoricalData
        need_days = max(1, int(max_bars * tf / 390))
        if need_days <= 1:    dur = "1 D"
        elif need_days <= 2:  dur = "2 D"
        elif need_days <= 5:  dur = "1 W"
        else:                 dur = "2 W"

        bar_size = ("1 min" if tf == 1 else
                    f"{tf} mins" if tf < 60 else "1 hour")

        self.lbl_intra_status.setText(
            f"⏳ IBKR {bar_size} 조회 중… {sym} (최대 {max_bars}봉)")

        # Cache params for re-render on mode toggle
        self._intra_cache_sym     = sym
        self._intra_cache_tf      = tf
        self._intra_cache_bars    = None
        self._intra_cache_maxbars = max_bars

        def _on_done(bars):
            self._intra_cache_bars = bars
            self._on_intra_done(bars, sym, tf, max_bars)

        self._ibkr_hist(sym, dur, bar_size, 9801,
                        _on_done,
                        self.lbl_intra_status,
                        on_timeout=None)

    def _on_intra_done(self, bars: list, sym: str, tf: int, max_bars: int = 399):
        """
        Render intraday bars on MiniChartCanvas.
        Mirrors spxw_1min_tab._render_rows() behaviour.
        """
        include_ext = (self.chk_intra_ext.isChecked()
                       if hasattr(self, 'chk_intra_ext') else False)

        rows = _bars_to_rows(bars, include_ext=include_ext, tf_min=tf)

        if len(rows) > max_bars:
            rows = rows[-max_bars:]

        if not rows:
            self.lbl_intra_status.setText(f"❌ {sym} — 데이터 없음")
            return

        t0, t1 = rows[0]["time"], rows[-1]["time"]
        ext_label = "(시간외포함)" if include_ext else "(정규장)"
        self.lbl_intra_status.setText(
            f"✅ {sym}  {tf}분봉  {len(rows)}봉  ({t0}~{t1})  {ext_label}")

        self._render_mini_chart(rows)

    def _render_mini_chart(self, rows: List[Dict[str, Any]]):
        """
        Push rows into MiniChartCanvas (candle or line).
        Identical pattern to spxw_1min_tab._render_rows().
        """
        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas is None:
            self.lbl_intra_status.setText("⚠ MiniChartCanvas 미초기화 — spxw_core 로드 실패")
            return

        times  = [r["time"]          for r in rows]
        opens  = [r["open"]          for r in rows]
        highs  = [r["high"]          for r in rows]
        lows   = [r["low"]           for r in rows]
        closes = [r["close"]         for r in rows]
        vols   = [r.get("volume", 0) for r in rows]

        try:
            mode = (self.combo_intra_chart_mode.currentText()
                    if hasattr(self, 'combo_intra_chart_mode') else "캔들")
            if mode == "캔들":
                canvas.plot_candles(
                    times, opens, highs, lows, closes, volumes=vols)
            else:
                canvas.plot_line(times, closes, volumes=vols)
        except Exception as e:
            self.lbl_intra_status.setText(f"⚠ 차트 오류: {e}")

    def _redraw_intraday_cache(self):
        """Re-render cached bars when chart mode combo changes (no re-fetch)."""
        bars = getattr(self, '_intra_cache_bars', None)
        if not bars:
            return
        sym      = getattr(self, '_intra_cache_sym',     "")
        tf       = getattr(self, '_intra_cache_tf',      1)
        max_bars = getattr(self, '_intra_cache_maxbars', 399)
        self._on_intra_done(bars, sym, tf, max_bars)