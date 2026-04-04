"""
chart_history.py — HistoryMixin: daily/intraday fetch + render  [S6]
Changes:
  - draw_ohlc_candles / _bars_to_rows / timezone helpers → chart_ohlc.py
  - VlineMixin → chart_history_vline.py
  - Calendar dateChanged fires _on_intra_date_fetch immediately (no button)
"""

import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any

from chart_utils import polygon_aggs, _FetchSignal
from chart_ibkr import IbkrHistMixin
from chart_history_vline import VlineMixin
from chart_ohlc import draw_ohlc_candles, _bars_to_rows


# ──────────────────────────────────────────────────────────────
# HistoryMixin
# ──────────────────────────────────────────────────────────────
class HistoryMixin(VlineMixin, IbkrHistMixin):

    def _on_und_label_clicked(self):
        from core import is_market_open
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self, '_chart_tabs') else 1

        if is_market_open():
            if cur_tab == 2:
                self._fetch_intraday()
            else:
                self._log("⚡ 장 운영 중 — 실시간 탭으로 전환합니다.")
                if hasattr(self, '_chart_tabs'):
                    self._chart_tabs.setCurrentIndex(0)
            return

        if cur_tab == 2:
            self._fetch_intraday()
        else:
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)
            self._fetch_daily(on_done_extra=self._fetch_intraday)

    # ── Daily ─────────────────────────────────────────────────
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

    # ── Intraday — IBKR only ──────────────────────────────────
    def _fetch_intraday(self, end_date: str = ""):
        if not getattr(self, 'mw', None) or not self.mw.connected:
            if hasattr(self, 'lbl_intra_status'):
                self.lbl_intra_status.setText("❌ TWS/Gateway 연결 필요")
            return

        if hasattr(self, '_hist_router') and 9801 in self._hist_router:
            self._hist_router[9801]["done"] = True
            try:
                self.mw.ib.cancelHistoricalData(9801)
            except Exception:
                pass

        sym = self._get_chart_sym()
        tf_map = {"1분": 1, "5분": 5, "15분": 15, "30분": 30, "60분": 60}
        tf = tf_map.get(self.combo_intra_tf.currentText(), 1)
        max_bars = (self.spin_intra_bars.value()
                    if hasattr(self, 'spin_intra_bars') else 399)

        need_days = max(1, int(max_bars * tf / 390))
        if need_days <= 1:   dur = "1 D"
        elif need_days <= 2: dur = "2 D"
        elif need_days <= 5: dur = "1 W"
        else:                dur = "2 W"

        bar_size = ("1 min" if tf == 1 else
                    f"{tf} mins" if tf < 60 else "1 hour")

        date_label = f"  [{end_date[:8]}]" if end_date else ""
        self.lbl_intra_status.setText(
            f"⏳ IBKR {bar_size} 조회 중… {sym} (최대 {max_bars}봉){date_label}")

        self._intra_cache_sym     = sym
        self._intra_cache_tf      = tf
        self._intra_cache_bars    = None
        self._intra_cache_maxbars = max_bars

        def _on_done(bars):
            self._intra_cache_bars = bars
            self._on_intra_done(bars, sym, tf, max_bars)

        ibkr_kwargs = {"end_date_time": end_date} if end_date else {}
        self._ibkr_hist(sym, dur, bar_size, 9801,
                        _on_done, self.lbl_intra_status,
                        on_timeout=None, **ibkr_kwargs)

    # ── [S6] Calendar date fetch — fired by dateChanged signal ──
    def _on_intra_date_fetch(self):
        """Immediate fetch when calendar date changes (no button required)."""
        if not hasattr(self, 'intra_date_edit'):
            return
        qdate = self.intra_date_edit.date()
        end_dt = qdate.toString("yyyyMMdd") + " 23:59:59 US/Eastern"
        self._fetch_intraday(end_date=end_dt)

    def _on_intra_done(self, bars: list, sym: str, tf: int, max_bars: int = 399):
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
        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas is None:
            self.lbl_intra_status.setText("⚠ MiniChartCanvas 미초기화")
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
                canvas.plot_candles(times, opens, highs, lows, closes, volumes=vols)
            else:
                canvas.plot_line(times, closes, volumes=vols)
        except Exception as e:
            self.lbl_intra_status.setText(f"⚠ 차트 오류: {e}")

    def _redraw_intraday_cache(self):
        bars = getattr(self, '_intra_cache_bars', None)
        if not bars:
            return
        self._on_intra_done(bars,
                            getattr(self, '_intra_cache_sym', ""),
                            getattr(self, '_intra_cache_tf', 1),
                            getattr(self, '_intra_cache_maxbars', 399))

    # ── Tick Chart ────────────────────────────────────────────
    def _fetch_tick_chart(self):
        if not getattr(self, 'mw', None) or not self.mw.connected:
            if hasattr(self, 'lbl_tick_status'):
                self.lbl_tick_status.setText("❌ TWS/Gateway 연결 필요")
            return
        sym       = self._get_chart_sym()
        num_ticks = getattr(self.spin_tick_count, 'value', lambda: 20)()

        def _on_done(ticks):
            n = len(ticks)
            self.lbl_tick_status.setText(f"✅ {sym}  {n}틱 수신")
            if not hasattr(self, '_pw_tick'):
                return
            try:
                import pyqtgraph as pg
                xs = list(range(n))
                ys = [t["p"] for t in ticks]
                sz = [max(1, min(int(t["s"]) // 10, 20)) for t in ticks]
                self._tick_line.setData(xs, ys)
                self._tick_dots.setData(x=xs, y=ys, size=sz,
                    brush=[pg.mkBrush('#00e676') for _ in ticks])
                if ys:
                    pad = (max(ys) - min(ys)) * 0.1 or min(ys) * 0.001
                    self._pw_tick.setYRange(min(ys) - pad, max(ys) + pad, padding=0)
            except Exception as e:
                self.lbl_tick_status.setText(f"⚠ 틱 차트 오류: {e}")

        self._ibkr_tick_chart(sym, num_ticks, 9802,
                              _on_done, self.lbl_tick_status)
