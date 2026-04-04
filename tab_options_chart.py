"""
tab_options_chart.py — 차트 패널 + Tick 수신 처리  v6.5 (리팩토링)
════════════════════════════════════════════════════════════════
  파일 구조:
  - chart_utils.py        : Polygon API, DST/KST, QSS 상수, FetchSignal
  - chart_ibkr.py         : IBKR reqHistoricalData fallback
  - chart_history.py      : 일봉/분봉 조회, OHLC 캔들 렌더러
  - chart_panel_builder.py: _build_chart_panel() UI 빌더
  - chart_tick.py         : Tick 수신 (가격 / Greeks)
  - tab_options_chart.py  : ChartMixin (통합 진입점) ← 현재 파일
════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta

from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import REQ_UND, REQ_CALL, REQ_PUT, tbl_set
from chart_utils import is_dst, et_to_kst
from chart_panel_builder import build_chart_panel, wrap_tbl
from chart_history import HistoryMixin
from chart_tick import TickMixin


class ChartMixin(HistoryMixin, TickMixin):
    """차트 + Tick 수신 전용 메서드 모음. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 차트 패널 빌더 (위임)
    # ─────────────────────────────────────────────────────────
    def _build_chart_panel(self):
        return build_chart_panel(self)

    def _wrap_tbl(self, tbl, title, color):
        return wrap_tbl(self, tbl, title, color)

    # ─────────────────────────────────────────────────────────
    # 실시간 차트 전환
    # ─────────────────────────────────────────────────────────
    def _on_chart_type_toggle(self):
        if not PG:
            return
        is_line = self.radio_chart_line.isChecked()
        self._pw1.setVisible(is_line)
        self._pw_candle.setVisible(not is_line)

    def _on_tz_toggle(self):
        self._redraw_chart_axes()

    def _redraw_chart_axes(self):
        pass

    # ─────────────────────────────────────────────────────────
    # DST / KST 유틸
    # ─────────────────────────────────────────────────────────
    def _is_dst(self, dt=None):
        return is_dst(dt)

    def _et_to_kst(self, dt_et):
        return et_to_kst(dt_et)

    def _fmt_chart_time(self, dt_et):
        use_kst = self.chk_kst.isChecked() if hasattr(self, 'chk_kst') else False
        return (self._et_to_kst(dt_et).strftime("%H:%M\nKST")
                if use_kst else dt_et.strftime("%H:%M\nET"))

    # ─────────────────────────────────────────────────────────
    # 실시간 가격 Push
    # ─────────────────────────────────────────────────────────
    def _push_price(self, price):
        if not PG:
            return
        now_et   = datetime.utcnow() - timedelta(hours=4 if self._is_dst() else 5)
        now_unix = now_et.timestamp()
        self._prices.append(price)
        self._price_times.append(now_unix)
        if len(self._prices) > self._BUF:
            del self._prices[0]; del self._price_times[0]

        min_len = min(len(self._prices), len(self._price_times))
        xs = self._price_times[-min_len:]
        ys = self._prices[-min_len:]
        if not xs:
            return

        self._c_p.setData(x=xs, y=ys)
        ma = [sum(ys[max(0, i - 9):i + 1]) / min(i + 1, 10) for i in range(len(ys))]
        self._c_ma.setData(x=xs, y=ma)
        self.lbl_pv.setText(f"Price: {price:.2f}")
        if hasattr(self, '_price_line'):
            self._price_line.setValue(price)

        bar_sec = {"1분": 60, "5분": 300, "15분": 900}.get(
            self.combo_bar.currentText() if hasattr(self, 'combo_bar') else "1분", 60)
        bar_key = int(now_unix // bar_sec) * bar_sec
        if bar_key in self._candle_bars:
            b = self._candle_bars[bar_key]
            b['h'] = max(b['h'], price); b['l'] = min(b['l'], price); b['c'] = price
        else:
            self._candle_bars[bar_key] = {
                'o': price, 'h': price, 'l': price, 'c': price, 't': bar_key}
        self._redraw_candles()

    def _redraw_candles(self):
        if not PG or not hasattr(self, '_pw_candle'):
            return
        for it in self._candle_items:
            try: self._pw_candle.removeItem(it)
            except Exception: pass
        self._candle_items.clear()
        bars = sorted(self._candle_bars.values(), key=lambda b: b['t'])
        if not bars:
            return
        for b in bars:
            t = b['t']; o, h, l, c = b['o'], b['h'], b['l'], b['c']
            color = '#00e676' if c >= o else '#ff5252'
            wick = pg.PlotDataItem(x=[t + 30, t + 30], y=[l, h],
                                   pen=pg.mkPen(color, width=1))
            self._pw_candle.addItem(wick); self._candle_items.append(wick)
            body_h = abs(c - o) or 0.001
            rect = pg.QtWidgets.QGraphicsRectItem(t, min(o, c), 55, body_h)
            rect.setBrush(pg.mkBrush(color)); rect.setPen(pg.mkPen(color))
            self._pw_candle.addItem(rect); self._candle_items.append(rect)

    def _push_greeks(self, delta):
        if not PG:
            return
        self._deltas.append(delta)
        if len(self._deltas) > self._BUF:
            del self._deltas[0]

    # ─────────────────────────────────────────────────────────
    # 기초자산 실시간 표시
    # ─────────────────────────────────────────────────────────
    def _update_und_display(self):
        price = self.und_price
        if price is None:
            return
        self.lbl_und.setText(f"{price:,.2f}")
        if self.und_prev and self.und_prev > 0:
            chg  = price - self.und_prev
            pct  = chg / self.und_prev * 100
            sign = "+" if chg >= 0 else ""
            col  = "#00e676" if chg >= 0 else "#ff5252"
            self.lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
            self.lbl_chg.setStyleSheet(f"color:{col};font-weight:bold;border:none;")
        if PG:
            self._und_hist.append(price)
            if len(self._und_hist) > self._BUF:
                del self._und_hist[0]
            if hasattr(self, '_c_und'):
                self._c_und.setData(self._und_hist)
        if hasattr(self, '_update_price_panel'):
            self._update_price_panel()

    def _upd_spread(self):
        c = self.call_data.get(REQ_CALL, {}).get("last")
        p = self.put_data.get(REQ_PUT,  {}).get("last")
        if c and p and PG:
            self._spreads.append(c - p)
            if len(self._spreads) > self._BUF:
                del self._spreads[0]

    # ─────────────────────────────────────────────────────────
    # 장외 Polygon fallback 종가
    # ─────────────────────────────────────────────────────────
    def _fetch_fallback_close(self, sym):
        if self.und_price is not None:
            return

        def _run():
            from chart_utils import polygon_aggs
            from PyQt5.QtCore import QTimer
            query_sym = "SPY" if sym in ("SPX", "SPXW") else sym
            end   = datetime.today().date()
            start = end - timedelta(days=7)
            bars  = polygon_aggs(query_sym, start, end, 1, "day")
            if bars:
                last_close = bars[-1]["c"]
                if sym in ("SPX", "SPXW"):
                    last_close *= 10.0
                QTimer.singleShot(0, lambda: self._apply_fallback_price(last_close, query_sym))
            else:
                QTimer.singleShot(0, lambda: self._log(
                    f"🌙 장외 시간: Polygon 우회 조회 실패 ({query_sym} 데이터 없음)"))

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _apply_fallback_price(self, price, source_sym):
        if self.und_price is None:
            self.und_price = price
            self.und_prev  = price
            self._update_und_display()
            self._log(
                f"🌙 장외 시간: Polygon {source_sym} 종가 기반({price:,.2f})으로 체인 조회 진행")
