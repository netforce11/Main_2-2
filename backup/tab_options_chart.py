"""
tab_options_chart.py — ChartMixin entry point  [S9]
ChartMixin(HistoryMixin) — delegates chart panel build + history fetch to sub-modules.
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
        # [S6] Delegate to chart_panel_builder — 4 tabs: 실시간/일봉/분봉/틱차트
        return _build_chart_panel_ext(self)

    # ─────────────────────────────────────────────────────────
    # 기초자산 클릭 → 일봉/분봉 자동 조회
    # ─────────────────────────────────────────────────────────
    def _on_und_label_clicked(self):
        # [S10] 실시간 체크박스 상태로 판단 (is_market_open 제거)
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

        # 실시간 미체크 → 과거 조회
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
        self._pw1.setVisible(is_line); self._pw_candle.setVisible(not is_line)

    def _on_tz_toggle(self): self._redraw_chart_axes()

    # ─────────────────────────────────────────────────────────
    # DST / KST 유틸
    # ─────────────────────────────────────────────────────────
    def _is_dst(self, dt=None):
        if dt is None: dt = datetime.utcnow()
        y = dt.year
        dst_start = datetime(y,3,8)  + timedelta(days=(6-datetime(y,3,8).weekday())%7)
        dst_end   = datetime(y,11,1) + timedelta(days=(6-datetime(y,11,1).weekday())%7)
        return dst_start <= dt < dst_end

    def _et_to_kst(self, dt_et):
        return dt_et + timedelta(hours=13 if self._is_dst(dt_et) else 14)

    def _fmt_chart_time(self, dt_et):
        use_kst = self.chk_kst.isChecked() if hasattr(self,'chk_kst') else False
        return (self._et_to_kst(dt_et).strftime("%H:%M\nKST")
                if use_kst else dt_et.strftime("%H:%M\nET"))

    def _wrap_tbl(self, tbl, title, color):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(0,0,0,0); v.setSpacing(1)
        lbl = QLabel(title); lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color:{color};font-weight:bold;border:none;")
        v.addWidget(lbl); v.addWidget(tbl)
        return w

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        if price <= 0: return
        QTimer.singleShot(0, lambda: self._apply_tick_price(rid, tt, price))

    def _apply_tick_price(self, rid, tt, price):
        if rid == REQ_UND:
            if tt in (4,68,75,14,9):
                self.und_price = price
                if tt == 9: self.und_prev = price
                self._update_und_display()
            # Bid/Ask 호가를 현재가 패널에 저장
            # tt=1(Bid Live), tt=2(Ask Live), tt=66(DelayedBid), tt=67(DelayedAsk)
            if tt in (1, 66) and hasattr(self, '_pp_bid'):
                self._pp_bid = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            elif tt in (2, 67) and hasattr(self, '_pp_ask'):
                self._pp_ask = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            return
        if REQ_CALL <= rid < REQ_CALL+self._MAX_STRIKES:
            row = rid-REQ_CALL
            if row >= len(self.call_strikes): return
            if tt in (4,68):
                tbl_set(self.tbl_call,row,1,f"{price:.2f}","#33aaff")
                self.call_data[rid]["last"] = price; self._upd_spread()
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    self._push_price(price)
                    # 현재가 패널 옵션 모드 호가 업데이트
                    if tt in (4,68) and hasattr(self, '_pp_opt_ask'):
                        if tt == 4: self._pp_opt_ask = price
                        self._refresh_opt_panel("C", self.call_strikes[row])
                for idx,rule in enumerate(self._watch_rules):
                    if rule["side"]=="C" and abs(float(rule["strike"])-self.call_strikes[row])<0.5:
                        self._watch_prev.setdefault(idx,{})["price"] = price
            elif tt in (1, 66):   # Bid / DelayedBid
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (2, 67):   # Ask / DelayedAsk
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (9,75): tbl_set(self.tbl_call,row,2,f"{price:.2f}","#aaa")
        elif REQ_PUT <= rid < REQ_PUT+self._MAX_STRIKES:
            row = rid-REQ_PUT
            if row >= len(self.put_strikes): return
            if tt in (4,68):
                tbl_set(self.tbl_put,row,1,f"{price:.2f}","#ff6666")
                self.put_data[rid]["last"] = price; self._upd_spread()
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    self._push_price(price)
                for idx,rule in enumerate(self._watch_rules):
                    if rule["side"]=="P" and abs(float(rule["strike"])-self.put_strikes[row])<0.5:
                        self._watch_prev.setdefault(idx,{})["price"] = price
            elif tt in (1, 66):   # Bid / DelayedBid
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (2, 67):   # Ask / DelayedAsk
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (9,75): tbl_set(self.tbl_put,row,2,f"{price:.2f}","#aaa")

    def _refresh_opt_panel(self, side: str, strike: float):
        """선택된 옵션의 Bid/Ask Tick이 오면 현재가 패널 옵션 모드를 갱신."""
        if not hasattr(self, '_pp_mode') or self._pp_mode != 'opt': return
        if getattr(self, '_pp_opt_side', '') != side: return
        try:
            if abs(float(getattr(self, '_pp_opt_strike', '0')) - strike) > 0.5: return
        except: return
        if hasattr(self, '_update_price_panel_opt'):
            delta = None
            # 현재 delta 가져오기 (테이블에서)
            try:
                tbl = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                row = min(range(len(strikes)), key=lambda i: abs(strikes[i]-strike))
                delta_item = tbl.item(row, 3)
                if delta_item and delta_item.text() not in ("―",""):
                    delta = float(delta_item.text())
            except: pass
            self._update_price_panel_opt(
                side, str(int(strike)),
                self._pp_opt_bid, self._pp_opt_ask, delta)

    def _on_tick_option(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10,11,12,13,80,81): return
        try:
            if delta is None or abs(delta)>1.5: return
        except: return
        QTimer.singleShot(0, lambda: self._apply_tick_option(rid,tt,delta,theta,gamma))

    def _apply_tick_option(self, rid, tt, delta, theta, gamma):
        if REQ_CALL <= rid < REQ_CALL+self._MAX_STRIKES:
            row = rid-REQ_CALL
            if row >= len(self.call_strikes): return
            tbl_set(self.tbl_call,row,3,f"{delta:+.4f}","#aaddff")
            tbl_set(self.tbl_call,row,4,f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_call,row,5,f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                self._push_greeks(delta)
            self._update_watch_prev("C",self.call_strikes[row],delta,theta,gamma)
        elif REQ_PUT <= rid < REQ_PUT+self._MAX_STRIKES:
            row = rid-REQ_PUT
            if row >= len(self.put_strikes): return
            tbl_set(self.tbl_put,row,3,f"{delta:+.4f}","#ffaaaa")
            tbl_set(self.tbl_put,row,4,f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_put,row,5,f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                self._push_greeks(delta)
            self._update_watch_prev("P",self.put_strikes[row],delta,theta,gamma)

    def _update_watch_prev(self, side, strike, delta, theta, gamma):
        for idx,rule in enumerate(self._watch_rules):
            if rule["side"]==side and abs(float(rule["strike"])-strike)<0.5:
                self._watch_prev.setdefault(idx,{})
                self._watch_prev[idx].update({"delta":delta,"theta":theta,"gamma":gamma})

    def _update_und_display(self):
        price = self.und_price
        if price is None: return
        self.lbl_und.setText(f"{price:,.2f}")
        if self.und_prev and self.und_prev>0:
            chg=price-self.und_prev; pct=chg/self.und_prev*100
            sign="+" if chg>=0 else ""; col="#00e676" if chg>=0 else "#ff5252"
            self.lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
            self.lbl_chg.setStyleSheet(f"color:{col};font-weight:bold;border:none;")
        if PG:
            self._und_hist.append(price)
            if len(self._und_hist)>self._BUF: del self._und_hist[0]
            if hasattr(self, '_c_und'):
                self._c_und.setData(self._und_hist)
        # 현재가 패널 연동
        if hasattr(self, '_update_price_panel'):
            self._update_price_panel()

    def _upd_spread(self):
        c=self.call_data.get(REQ_CALL,{}).get("last")
        p=self.put_data.get(REQ_PUT,{}).get("last")
        if c and p and PG:
            self._spreads.append(c-p)
            if len(self._spreads)>self._BUF: del self._spreads[0]

    def _push_price(self, price):
        if not PG: return
        now_et   = datetime.utcnow()-timedelta(hours=4 if self._is_dst() else 5)
        now_unix = now_et.timestamp()
        self._prices.append(price); self._price_times.append(now_unix)
        if len(self._prices)>self._BUF:
            del self._prices[0]; del self._price_times[0]

        # ✅ X/Y 배열 길이 강제 동기화 (비동기 tick 타이밍 불일치 방어)
        min_len = min(len(self._prices), len(self._price_times))
        xs = self._price_times[-min_len:]
        ys = self._prices[-min_len:]
        if len(xs) == 0: return

        self._c_p.setData(x=xs, y=ys)
        ma=[sum(ys[max(0,i-9):i+1])/min(i+1,10) for i in range(len(ys))]
        self._c_ma.setData(x=xs, y=ma)
        self.lbl_pv.setText(f"Price: {price:.2f}")
        if hasattr(self,'_price_line'): self._price_line.setValue(price)
        bar_sec={"1분":60,"5분":300,"15분":900}.get(
            self.combo_bar.currentText() if hasattr(self,'combo_bar') else "1분",60)
        bar_key=int(now_unix//bar_sec)*bar_sec
        if bar_key in self._candle_bars:
            b=self._candle_bars[bar_key]
            b['h']=max(b['h'],price); b['l']=min(b['l'],price); b['c']=price
        else:
            self._candle_bars[bar_key]={'o':price,'h':price,'l':price,'c':price,'t':bar_key}
        self._redraw_candles()

    def _redraw_candles(self):
        if not PG or not hasattr(self,'_pw_candle'): return
        for it in self._candle_items:
            try: self._pw_candle.removeItem(it)
            except: pass
        self._candle_items.clear()
        bars=sorted(self._candle_bars.values(),key=lambda b:b['t'])
        if not bars: return
        for b in bars:
            t=b['t']; o,h,l,c=b['o'],b['h'],b['l'],b['c']
            color='#00e676' if c>=o else '#ff5252'
            wick=pg.PlotDataItem(x=[t+30,t+30],y=[l,h],pen=pg.mkPen(color,width=1))
            self._pw_candle.addItem(wick); self._candle_items.append(wick)
            body_h=abs(c-o) or 0.001
            rect=pg.QtWidgets.QGraphicsRectItem(t,min(o,c),55,body_h)
            rect.setBrush(pg.mkBrush(color)); rect.setPen(pg.mkPen(color))
            self._pw_candle.addItem(rect); self._candle_items.append(rect)

    def _redraw_chart_axes(self): pass

    def _push_greeks(self, delta):
        if not PG: return
        self._deltas.append(delta)
        if len(self._deltas)>self._BUF: del self._deltas[0]

        # ─────────────────────────────────────────────────────────
        # 장외 시간 기초자산 종가 Fallback (Polygon SPY 우회 활용)
        # ─────────────────────────────────────────────────────────
    def _fetch_fallback_close(self, sym):
            """실시간 틱이 안 올 때 Polygon에서 SPY 전일 종가를 가져와 SPX ATM 계산을 뚫어줌."""
            # 이미 가격이 수신되었다면 실행할 필요 없음
            if self.und_price is not None: return

            def _run():
                from datetime import datetime, timedelta
                from PyQt5.QtCore import QTimer

                # SPX/SPXW인 경우 SPY로 우회하여 조회 (주식 스타터팩 권한 활용)
                query_sym = "SPY" if sym in ("SPX", "SPXW") else sym

                # 최근 7일(휴일/주말 포함) 일봉을 가져와 가장 마지막 종가 사용
                end = datetime.today().date()
                start = end - timedelta(days=7)

                # Polygon 조회 (multiplier=1, timespan="day")
                bars = self._polygon_aggs(query_sym, start, end, 1, "day")

                if bars:
                    last_close = bars[-1]["c"]
                    # SPY 가격을 가져왔다면 SPX 스케일(약 10배)로 보정
                    if sym in ("SPX", "SPXW"):
                        last_close = last_close * 10.0

                    # 메인 스레드에서 UI 및 변수 업데이트
                    QTimer.singleShot(0, lambda: self._apply_fallback_price(last_close, query_sym))
                else:
                    QTimer.singleShot(0, lambda: self._log(f"🌙 장외 시간: Polygon 우회 조회 실패 ({query_sym} 데이터 없음)"))

            import threading
            threading.Thread(target=_run, daemon=True).start()

    def _apply_fallback_price(self, price, source_sym):
            # 비동기 처리 중 그 사이(1~2초)에 IBKR 틱이 왔다면 덮어쓰지 않음
            if self.und_price is None:
                self.und_price = price
                self.und_prev = price
                self._update_und_display()
                self._log(f"🌙 장외 시간: Polygon {source_sym} 종가 기반({price:,.2f})으로 체인 조회 진행")