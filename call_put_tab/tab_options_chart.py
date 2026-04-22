"""
tab_options_chart.py — ChartMixin entry point  [S9]
ChartMixin(HistoryMixin) — delegates chart panel build + history fetch to sub-modules.

[장외 선물 전환 UI 연동] v6.5-FUT
  - _update_und_display(): _und_is_futures=True 이면 lbl_und 에 "[/ES]" 뱃지 추가
  - _fetch_fallback_close(): _und_is_futures=True 이면 Polygon fallback 스킵
    (IBKR TWS 선물 틱이 이미 수신되므로 불필요)
"""

import threading
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QRadioButton, QButtonGroup, QCheckBox,
    QComboBox, QTabWidget, QPushButton, QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from chart_panel_builder import build_chart_panel as _build_chart_panel_ext

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import REQ_UND, REQ_CALL, REQ_PUT, tbl_set

from chart_history import HistoryMixin


class ChartMixin(HistoryMixin):
    """차트 + Tick 수신 전용 메서드 모음. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 차트 패널 빌더
    # ─────────────────────────────────────────────────────────
    def _build_chart_panel(self):
        return _build_chart_panel_ext(self)

    # ─────────────────────────────────────────────────────────
    # 기초자산 클릭 → 일봉/분봉 자동 조회
    # ─────────────────────────────────────────────────────────
    def _on_und_label_clicked(self):
        live_checked = (getattr(self, 'chk_live', None) is not None
                        and self.chk_live.isChecked())
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self, '_chart_tabs') else 1

        if live_checked:
            if cur_tab == 2:
                self._fetch_intraday()
            else:
                self._log("⚡ 실시간 모드 — 분봉 탭으로 전환합니다.")
                if hasattr(self, '_chart_tabs'):
                    self._chart_tabs.setCurrentIndex(2)
            return

        if cur_tab == 2:
            self._fetch_intraday()
        else:
            self._fetch_daily()
            self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)

    # ─────────────────────────────────────────────────────────
    # 실시간 차트 전환
    # ─────────────────────────────────────────────────────────
    def _on_chart_type_toggle(self):
        if not PG: return
        is_line = self.radio_chart_line.isChecked()
        self._pw1.setVisible(is_line)
        self._pw_candle.setVisible(not is_line)

    def _on_tz_toggle(self):
        self._redraw_chart_axes()

    # ─────────────────────────────────────────────────────────
    # DST / KST 유틸
    # ─────────────────────────────────────────────────────────
    def _is_dst(self, dt=None):
        if dt is None: dt = datetime.utcnow()
        y = dt.year
        dst_start = datetime(y, 3, 8)  + timedelta(days=(6 - datetime(y, 3, 8).weekday()) % 7)
        dst_end   = datetime(y, 11, 1) + timedelta(days=(6 - datetime(y, 11, 1).weekday()) % 7)
        return dst_start <= dt < dst_end

    def _et_to_kst(self, dt_et):
        return dt_et + timedelta(hours=13 if self._is_dst(dt_et) else 14)

    def _fmt_chart_time(self, dt_et):
        use_kst = self.chk_kst.isChecked() if hasattr(self, 'chk_kst') else False
        return (self._et_to_kst(dt_et).strftime("%H:%M\nKST")
                if use_kst else dt_et.strftime("%H:%M\nET"))

    def _wrap_tbl(self, tbl, title, color):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        lbl = QLabel(title)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color:{color};font-weight:bold;border:none;")
        v.addWidget(lbl)
        v.addWidget(tbl)
        return w

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price, attrib=None):
        # attrib=None: TWS가 4번째 인자(TickAttrib)를 전달할 수 있음.
        # ConnSignalsMixin._on_tick_price 와 시그니처를 맞춰 TypeError 방지.
        if price <= 0: return
        QTimer.singleShot(0, lambda: self._apply_tick_price(rid, tt, price))

    def _apply_tick_price(self, rid, tt, price):
        # QTimer.singleShot 딜레이 사이에 위젯이 파괴될 수 있음 → 즉시 체크
        try:
            self.objectName()
        except RuntimeError:
            return
        if rid == REQ_UND:
            if tt in (4, 68, 75, 14, 9):
                self.und_price = price
                if tt == 9:
                    self.und_prev = price
                self._update_und_display()

                sym = getattr(self, 'edit_sym', None)
                sym_txt = sym.text().strip().upper().replace("SPXW", "SPX") if sym else ""

                if sym_txt == "VIX" and tt in (4, 68, 75, 14):
                    vix_prev = getattr(self, '_vix_prev', None)
                    if vix_prev is not None and hasattr(self, 'feed_vix_to_watch'):
                        self.feed_vix_to_watch(price, vix_prev)
                    self._vix_prev = price

                if sym_txt in ("SPX", "SPXW", "") and tt in (4, 68, 75, 14):
                    if hasattr(self, 'feed_spx_to_watch'):
                        self.feed_spx_to_watch(price)

            if tt in (1, 66) and hasattr(self, '_pp_bid'):
                self._pp_bid = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            elif tt in (2, 67) and hasattr(self, '_pp_ask'):
                self._pp_ask = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            return

        if REQ_CALL <= rid < REQ_CALL + self._MAX_STRIKES:
            row = rid - REQ_CALL
            if row >= len(self.call_strikes): return
            if tt in (4, 68):
                tbl_set(self.tbl_call, row, 1, f"{price:.2f}", "#33aaff")
                self.call_data[rid]["last"] = price
                self._upd_spread()
                self._buf_update_price(rid, "C", row, last=price)
                if self._chart_strike == self.call_strikes[row] and self._chart_side == "C":
                    self._push_price(price)
                    if tt in (4, 68) and hasattr(self, '_pp_opt_ask'):
                        if tt == 4: self._pp_opt_ask = price
                        self._refresh_opt_panel("C", self.call_strikes[row])
                for idx, rule in enumerate(self._watch_rules):
                    if rule["side"] == "C" and abs(float(rule["strike"]) - self.call_strikes[row]) < 0.5:
                        self._watch_prev.setdefault(idx, {})["price"] = price
                if hasattr(self, 'feed_opt_to_watch'):
                    prev = self.call_data[rid].get("_prev_last")
                    if prev is not None:
                        self.feed_opt_to_watch(self.call_strikes[row], "C", price, prev)
                    self.call_data[rid]["_prev_last"] = price
            elif tt in (1, 66):
                self.call_data[rid]["bid"] = price
                self._buf_update_price(rid, "C", row, bid=price)
                if self._chart_strike == self.call_strikes[row] and self._chart_side == "C":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (2, 67):
                self.call_data[rid]["ask"] = price
                self._buf_update_price(rid, "C", row, ask=price)
                if self._chart_strike == self.call_strikes[row] and self._chart_side == "C":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (9, 75):
                tbl_set(self.tbl_call, row, 2, f"{price:.2f}", "#aaa")

        elif REQ_PUT <= rid < REQ_PUT + self._MAX_STRIKES:
            row = rid - REQ_PUT
            if row >= len(self.put_strikes): return
            if tt in (4, 68):
                tbl_set(self.tbl_put, row, 1, f"{price:.2f}", "#ff6666")
                self.put_data[rid]["last"] = price
                self._upd_spread()
                self._buf_update_price(rid, "P", row, last=price)
                if self._chart_strike == self.put_strikes[row] and self._chart_side == "P":
                    self._push_price(price)
                for idx, rule in enumerate(self._watch_rules):
                    if rule["side"] == "P" and abs(float(rule["strike"]) - self.put_strikes[row]) < 0.5:
                        self._watch_prev.setdefault(idx, {})["price"] = price
                if hasattr(self, 'feed_opt_to_watch'):
                    prev = self.put_data[rid].get("_prev_last")
                    if prev is not None:
                        self.feed_opt_to_watch(self.put_strikes[row], "P", price, prev)
                    self.put_data[rid]["_prev_last"] = price
            elif tt in (1, 66):
                self.put_data[rid]["bid"] = price
                self._buf_update_price(rid, "P", row, bid=price)
                if self._chart_strike == self.put_strikes[row] and self._chart_side == "P":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (2, 67):
                self.put_data[rid]["ask"] = price
                self._buf_update_price(rid, "P", row, ask=price)
                if self._chart_strike == self.put_strikes[row] and self._chart_side == "P":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (9, 75):
                tbl_set(self.tbl_put, row, 2, f"{price:.2f}", "#aaa")

    def _buf_update_price(self, rid, side, row, bid=None, ask=None, last=None):
        """ChainBuffer 에 가격 업데이트."""
        sched = getattr(getattr(self, 'mw', None), 'chain_scheduler', None)
        if not sched: return
        expiry, _ = self._get_expiry(silent=True)
        if not expiry: return
        strikes = self.call_strikes if side == "C" else self.put_strikes
        if row >= len(strikes): return
        sched._buf.update_price(expiry, strikes[row], side, bid=bid, ask=ask, last=last)

    def _refresh_opt_panel(self, side: str, strike: float):
        """선택된 옵션의 Bid/Ask Tick이 오면 현재가 패널 옵션 모드를 갱신."""
        if not hasattr(self, '_pp_mode') or self._pp_mode != 'opt': return
        if getattr(self, '_pp_opt_side', '') != side: return
        try:
            if abs(float(getattr(self, '_pp_opt_strike', '0')) - strike) > 0.5: return
        except:
            return
        if hasattr(self, '_update_price_panel_opt'):
            delta = None
            try:
                tbl = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                row = min(range(len(strikes)), key=lambda i: abs(strikes[i] - strike))
                delta_item = tbl.item(row, 3)
                if delta_item and delta_item.text() not in ("―", ""):
                    delta = float(delta_item.text())
            except:
                pass
            self._update_price_panel_opt(
                side, str(int(strike)),
                self._pp_opt_bid, self._pp_opt_ask, delta)

    def _on_tick_option(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10, 11, 12, 13, 80, 81): return
        try:
            if delta is None or abs(delta) > 1.5: return
        except:
            return
        _iv   = iv   if (iv   and 0 < iv   < 10)   else None
        _vega = vega if (vega and abs(vega) < 1e6) else None
        QTimer.singleShot(0, lambda: self._apply_tick_option(
            rid, tt, delta, theta, gamma, iv=_iv, vega=_vega))

    def _apply_tick_option(self, rid, tt, delta, theta, gamma, iv=None, vega=None):
        if REQ_CALL <= rid < REQ_CALL + self._MAX_STRIKES:
            row = rid - REQ_CALL
            if row >= len(self.call_strikes): return
            tbl_set(self.tbl_call, row, 3, f"{delta:+.4f}", "#aaddff")
            tbl_set(self.tbl_call, row, 4, f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_call, row, 5, f"{gamma:.6f}" if gamma else "―")
            entry = self.call_data.get(rid)
            if entry is not None:
                entry.update(delta=delta, theta=theta, gamma=gamma)
                if iv   is not None: entry["iv"]   = iv
                if vega is not None: entry["vega"] = vega
            if self._chart_strike == self.call_strikes[row] and self._chart_side == "C":
                self._push_greeks(delta)
            self._update_watch_prev("C", self.call_strikes[row], delta, theta, gamma)
            self._buf_update_greeks(rid, "C", row, iv, delta, gamma, vega, theta)

        elif REQ_PUT <= rid < REQ_PUT + self._MAX_STRIKES:
            row = rid - REQ_PUT
            if row >= len(self.put_strikes): return
            tbl_set(self.tbl_put, row, 3, f"{delta:+.4f}", "#ffaaaa")
            tbl_set(self.tbl_put, row, 4, f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_put, row, 5, f"{gamma:.6f}" if gamma else "―")
            entry = self.put_data.get(rid)
            if entry is not None:
                entry.update(delta=delta, theta=theta, gamma=gamma)
                if iv   is not None: entry["iv"]   = iv
                if vega is not None: entry["vega"] = vega
            if self._chart_strike == self.put_strikes[row] and self._chart_side == "P":
                self._push_greeks(delta)
            self._update_watch_prev("P", self.put_strikes[row], delta, theta, gamma)
            self._buf_update_greeks(rid, "P", row, iv, delta, gamma, vega, theta)

    def _buf_update_greeks(self, rid, side, row, iv, delta, gamma, vega, theta):
        """ChainBuffer 에 Greeks 업데이트."""
        sched = getattr(getattr(self, 'mw', None), 'chain_scheduler', None)
        if not sched: return
        expiry, _ = self._get_expiry(silent=True)
        if not expiry: return
        strikes = self.call_strikes if side == "C" else self.put_strikes
        if row >= len(strikes): return
        sched._buf.update_greeks(
            expiry, strikes[row], side,
            iv=iv, delta=delta, gamma=gamma, vega=vega, theta=theta)

    def _update_watch_prev(self, side, strike, delta, theta, gamma):
        for idx, rule in enumerate(self._watch_rules):
            if rule["side"] == side and abs(float(rule["strike"]) - strike) < 0.5:
                self._watch_prev.setdefault(idx, {})
                self._watch_prev[idx].update({"delta": delta, "theta": theta, "gamma": gamma})

    def _update_und_display(self):
        """
        기초자산 가격 라벨 갱신.

        [장외 선물 뱃지]
        _und_is_futures=True 이면:
          - lbl_und  : "{price:,.2f}  [/ES]"  (황색 뱃지)
          - lbl_chg  : 등락 표시 + "(선물)" 접미사
          - 사이드바 _side_und_sym: "/ES" 표시
        _und_is_futures=False (기본):
          - 기존 동작과 동일
        """
        price = self.und_price
        if price is None:
            return

        is_fut = getattr(self, '_und_is_futures', False)

        # ── lbl_und (컨트롤 바 우측 현재가 라벨) ─────────────────
        if is_fut:
            self.lbl_und.setText(f"{price:,.2f}  [/ES]")
            self.lbl_und.setStyleSheet(
                "color:#ffd700;font-weight:bold;border:none;"
                "font-size:13px;")
        else:
            self.lbl_und.setText(f"{price:,.2f}")
            self.lbl_und.setStyleSheet(
                "color:#ffd700;font-weight:bold;border:none;")

        # ── lbl_chg (등락 라벨) ───────────────────────────────────
        if self.und_prev and self.und_prev > 0:
            chg = price - self.und_prev
            pct = chg / self.und_prev * 100
            sign = "+" if chg >= 0 else ""
            col  = "#00e676" if chg >= 0 else "#ff5252"
            suffix = "  (선물)" if is_fut else ""
            self.lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%){suffix}")
            self.lbl_chg.setStyleSheet(f"color:{col};font-weight:bold;border:none;")

        # ── 사이드바 기초자산 패널 ────────────────────────────────
        if hasattr(self, '_side_und_price'):
            self._side_und_price.setText(f"{price:,.2f}")
        if hasattr(self, '_side_und_sym'):
            sym_display = "/ES (선물)" if is_fut else (
                self.edit_sym.text().strip().upper()
                if hasattr(self, 'edit_sym') else "SPX")
            self._side_und_sym.setText(sym_display)
            if is_fut:
                self._side_und_sym.setStyleSheet(
                    "color:#ffd700;font-size:12px;font-weight:bold;border:none;")
            else:
                self._side_und_sym.setStyleSheet(
                    "color:#5dade2;font-size:12px;font-weight:bold;border:none;")
        if hasattr(self, '_side_und_chg') and self.und_prev and self.und_prev > 0:
            chg = price - self.und_prev
            pct = chg / self.und_prev * 100
            sign = "+" if chg >= 0 else ""
            col  = "#00e676" if chg >= 0 else "#ff5252"
            self._side_und_chg.setText(f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)")
            self._side_und_chg.setStyleSheet(f"color:{col};font-size:10px;border:none;")

        # ── pyqtgraph 실시간 차트 ─────────────────────────────────
        if PG:
            self._und_hist.append(price)
            if len(self._und_hist) > self._BUF:
                del self._und_hist[0]
            if hasattr(self, '_c_und'):
                self._c_und.setData(self._und_hist)

        # ── 현재가 패널 연동 ──────────────────────────────────────
        if hasattr(self, '_update_price_panel'):
            self._update_price_panel()

    def _upd_spread(self):
        c = self.call_data.get(REQ_CALL, {}).get("last")
        p = self.put_data.get(REQ_PUT, {}).get("last")
        if c and p and PG:
            self._spreads.append(c - p)
            if len(self._spreads) > self._BUF:
                del self._spreads[0]

    def _push_price(self, price):
        if not PG: return
        now_et   = datetime.utcnow() - timedelta(hours=4 if self._is_dst() else 5)
        now_unix = now_et.timestamp()
        self._prices.append(price)
        self._price_times.append(now_unix)
        if len(self._prices) > self._BUF:
            del self._prices[0]
            del self._price_times[0]

        min_len = min(len(self._prices), len(self._price_times))
        xs = self._price_times[-min_len:]
        ys = self._prices[-min_len:]
        if len(xs) == 0: return

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
            b['h'] = max(b['h'], price)
            b['l'] = min(b['l'], price)
            b['c'] = price
        else:
            self._candle_bars[bar_key] = {'o': price, 'h': price, 'l': price, 'c': price, 't': bar_key}
        self._redraw_candles()

    def _redraw_candles(self):
        if not PG or not hasattr(self, '_pw_candle'): return
        for it in self._candle_items:
            try:
                self._pw_candle.removeItem(it)
            except:
                pass
        self._candle_items.clear()
        bars = sorted(self._candle_bars.values(), key=lambda b: b['t'])
        if not bars: return
        for b in bars:
            t = b['t']
            o, h, l, c = b['o'], b['h'], b['l'], b['c']
            color = '#00e676' if c >= o else '#ff5252'
            wick = pg.PlotDataItem(x=[t + 30, t + 30], y=[l, h], pen=pg.mkPen(color, width=1))
            self._pw_candle.addItem(wick)
            self._candle_items.append(wick)
            body_h = abs(c - o) or 0.001
            rect = pg.QtWidgets.QGraphicsRectItem(t, min(o, c), 55, body_h)
            rect.setBrush(pg.mkBrush(color))
            rect.setPen(pg.mkPen(color))
            self._pw_candle.addItem(rect)
            self._candle_items.append(rect)

    def _redraw_chart_axes(self):
        pass

    def _push_greeks(self, delta):
        if not PG: return
        self._deltas.append(delta)
        if len(self._deltas) > self._BUF:
            del self._deltas[0]

    # ─────────────────────────────────────────────────────────
    # 장외 시간 기초자산 종가 Fallback (Polygon SPY 우회)
    # ─────────────────────────────────────────────────────────
    def _fetch_fallback_close(self, sym):
        """
        실시간 틱이 안 올 때 Polygon에서 SPY 전일 종가를 가져와 SPX ATM 계산을 뚫어줌.

        [선물 전환 우선순위]
        _und_is_futures=True 이면 IBKR TWS /ES 틱이 수신 중이므로
        Polygon fallback 을 실행하지 않는다.
        """
        if self.und_price is not None:
            return

        # /ES 선물 구독 중이면 Polygon fallback 불필요 — TWS 틱 대기
        if getattr(self, '_und_is_futures', False):
            self._log("🌙 장외 시간: /ES 선물 구독 중 — Polygon fallback 스킵 (TWS 틱 대기)")
            return

        def _run():
            from datetime import datetime, timedelta
            from PyQt5.QtCore import QTimer

            query_sym = "SPY" if sym in ("SPX", "SPXW") else sym
            end   = datetime.today().date()
            start = end - timedelta(days=7)
            bars  = self._polygon_aggs(query_sym, start, end, 1, "day")

            if bars:
                last_close = bars[-1]["c"]
                if sym in ("SPX", "SPXW"):
                    last_close = last_close * 10.0
                QTimer.singleShot(0, lambda: self._apply_fallback_price(last_close, query_sym))
            else:
                QTimer.singleShot(0, lambda: self._log(
                    f"🌙 장외 시간: Polygon 우회 조회 실패 ({query_sym} 데이터 없음)"))

        threading.Thread(target=_run, daemon=True).start()

    def _apply_fallback_price(self, price, source_sym):
        if self.und_price is None:
            self.und_price = price
            self.und_prev  = price
            self._update_und_display()
            self._log(f"🌙 장외 시간: Polygon {source_sym} 종가 기반({price:,.2f})으로 체인 조회 진행")
    # ─────────────────────────────────────────────────────────
    # 텔레그램 차트 캡처
    # ─────────────────────────────────────────────────────────
    def grab_chart_image(self) -> bytes:
        """
        현재 보이는 실시간 차트를 PNG bytes로 캡처.
        - 라인모드: _pw1 (기본)
        - 캔들모드: _pw_candle
        - 둘 다 없으면: _chart_outer (차트 패널 전체) fallback
        반드시 Qt 메인 스레드에서 호출할 것.
        """
        if not PG:
            return b""
        try:
            from PyQt5.QtCore import QBuffer, QByteArray, QIODevice

            # _chart_tabs 현재 탭을 통째로 grab (가장 확실한 방법)
            ct = getattr(self, '_chart_tabs', None)
            if ct:
                widget = ct.currentWidget()
            elif hasattr(self, '_pw1'):
                widget = self._pw1
            else:
                widget = getattr(self, '_chart_outer', None)
                if widget is None:
                    return b""

            pixmap = widget.grab()

            if pixmap.isNull():
                return b""
            ba  = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            pixmap.save(buf, "PNG")
            buf.close()
            return bytes(ba.data())
        except Exception as e:
            print(f"[ChartMixin] grab_chart_image error: {e}")
            return b""