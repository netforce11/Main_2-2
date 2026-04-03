"""
tab_options_core.py — 연결·조회·만기·Zone 로직  v6.4
════════════════════════════════════════════════════════════════
  CallPutGrid 에서 분리 (tab_options.py 에 mixin으로 사용)

  포함 기능:
  - _connect_signals()
  - _log()
  - _on_connected() / _auto_fetch_spxw_today()
  - _on_error() / _apply_mdt() / _apply_mdt_manual()
  - _build_spxw_combo() / _on_spxw_select()
  - _on_zone_change() / _on_exp_change()
  - _open_calendar() / _on_date_edit_changed() / _get_expiry()
  - _strikes_for_zone()
  - _req_und() / _refresh_und()
  - _fetch() / _init_tbl()
  - _tbl_click() / _tbl_dbl()
  - _on_watch_dbl() / _w_add() / _w_del()
════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta, date as _date

from PyQt5.QtWidgets import (
    QMessageBox, QInputDialog, QTableWidgetItem,
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, tbl_set, ts,
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_UND, REQ_CALL, REQ_PUT,
    build_expiry_list, make_opt_contract, make_und_contract,
    SAVE_DIR, auto_mdt, is_trading_day,
)


class CoreMixin:
    """연결·조회·만기·Zone·테이블클릭 전용 메서드. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 시그널 연결
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.btn_conn.clicked.connect(self.mw.connect_ibkr)
        self.btn_disc.clicked.connect(self.mw.disconnect_ibkr)
        self.btn_fetch.clicked.connect(self._fetch)
        bridge.connected.connect(self._on_connected)
        bridge.error_sig.connect(self._on_error)
        router.register_price(REQ_UND, REQ_UND, self._on_tick_price)
        router.register_price(REQ_CALL, REQ_CALL+self._MAX_STRIKES-1, self._on_tick_price)
        router.register_price(REQ_PUT,  REQ_PUT +self._MAX_STRIKES-1, self._on_tick_price)
        router.register_option(REQ_CALL, REQ_CALL+self._MAX_STRIKES-1, self._on_tick_option)
        router.register_option(REQ_PUT,  REQ_PUT +self._MAX_STRIKES-1, self._on_tick_option)
        self._watch_timer.start()

    # ─────────────────────────────────────────────────────────
    # 로그
    # ─────────────────────────────────────────────────────────
    def _log(self, msg):
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 200:
            self.log.setPlainText("\n".join(lines[-150:]))

    # ─────────────────────────────────────────────────────────
    # 연결 / 에러 / MDT
    # ─────────────────────────────────────────────────────────
    def _on_connected(self):
        self.lbl_status.setText("● 연결됨")
        self.lbl_status.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        self._log("TWS 연결 성공 ✓")
        self._apply_mdt()
        self._req_und(self.edit_sym.text().upper())
        self._und_timer.start()
        self._auto_fetch_spxw_today()

    def _auto_fetch_spxw_today(self):
        today = datetime.today().date()
        if not is_trading_day(today):
            self._log("오늘은 거래일이 아닙니다. SPXW 자동 조회 건너뜀.")
            return
        today_str = today.strftime("%Y%m%d")
        found_idx = next(
            (i for i in range(self.combo_spxw.count())
             if self.combo_spxw.itemData(i) == today_str), -1)
        if found_idx < 0:
            self._log(f"SPXW 0DTE 오늘({today_str}) 항목 없음."); return
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.setCurrentIndex(found_idx)
        self.combo_spxw.blockSignals(False)
        self._on_spxw_select(found_idx)
        self._log(f"🔄 SPXW 0DTE 자동 선택: {today_str}")
        QTimer.singleShot(2000, self._fetch)

    def _on_error(self, rid, code, msg):
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        self._log(f"ERR {code}: {msg}")

    def _apply_mdt(self):
        if not self.mw.connected: return
        mdt = auto_mdt(self.mw.ib)
        self.radio_delay.blockSignals(True); self.radio_live.blockSignals(True)
        self.radio_live.setChecked(mdt == 1); self.radio_delay.setChecked(mdt != 1)
        self.radio_delay.blockSignals(False); self.radio_live.blockSignals(False)

    def _apply_mdt_manual(self):
        if not self.mw.connected: return
        mdt = 1 if self.radio_live.isChecked() else 3
        try: self.mw.ib.reqMarketDataType(mdt)
        except Exception as e: self._log(f"MDT 전환 실패: {e}")

    # ─────────────────────────────────────────────────────────
    # SPXW 0DTE 콤보
    # ─────────────────────────────────────────────────────────
    def _build_spxw_combo(self):
        from datetime import timedelta
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.clear()
        self.combo_spxw.addItem("── 0DTE 선택 ──", "")
        today = datetime.today().date()
        d = today - timedelta(days=3)
        days = []
        while d <= today + timedelta(days=14):
            if is_trading_day(d): days.append(d)
            d += timedelta(days=1)
        for d in days:
            label = ("오늘 " if d == today else
                     "어제 " if d == today - timedelta(days=1) else
                     "내일 " if d == today + timedelta(days=1) else "")
            label += d.strftime("%m/%d(%a)")
            self.combo_spxw.addItem(label, d.strftime("%Y%m%d"))
        self.combo_spxw.blockSignals(False)

    def _on_spxw_select(self, idx):
        expiry = self.combo_spxw.itemData(idx)
        if not expiry: return
        # SPXW → SPX 자동 처리
        self.edit_sym.setText("SPXW")
        custom_idx = next((i for i,(_, c, _) in enumerate(self._expiry_list)
                           if c == "CUSTOM"), len(self._expiry_list)-1)
        self.combo_exp.blockSignals(True)
        self.combo_exp.setCurrentIndex(custom_idx)
        self.combo_exp.blockSignals(False)
        self.edit_custom.setVisible(False)
        self.edit_custom.setText(expiry)
        y, m, d = int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8])
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(QDate(y, m, d))
        self.date_edit.blockSignals(False)
        self.date_edit.setVisible(True)
        self._log(f"SPXW 0DTE 선택: {expiry}")

    # ─────────────────────────────────────────────────────────
    # Zone / 만기
    # ─────────────────────────────────────────────────────────
    def _on_zone_change(self, btn):
        for z, rb in self._zone_btns.items():
            if rb is btn: self._zone = z
        if self.und_price is not None: self._fetch()

    def _on_exp_change(self, idx):
        _, code, _ = self._expiry_list[idx]
        is_custom = (code == "CUSTOM")
        self.edit_custom.setVisible(False)
        self.date_edit.setVisible(is_custom)
        self.btn_cal.setVisible(True)

    def _open_calendar(self):
        custom_idx = next(
            (i for i, (_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list) - 1)
        self.combo_exp.blockSignals(True)
        self.combo_exp.setCurrentIndex(custom_idx)
        self.combo_exp.blockSignals(False)
        self.edit_custom.setVisible(False)
        self.date_edit.setVisible(True)
        try: self.date_edit.calendarWidget()
        except: pass
        self.date_edit.setFocus()

    def _on_date_edit_changed(self, qdate):
        self.edit_custom.setText(qdate.toString("yyyyMMdd"))

    def _get_expiry(self):
        idx = self.combo_exp.currentIndex()
        _, code, tag = self._expiry_list[idx]
        if code == "CUSTOM":
            raw = (self.date_edit.date().toString("yyyyMMdd")
                   if self.date_edit.isVisible()
                   else self.edit_custom.text().strip())
            if len(raw)==8 and raw.isdigit(): return raw, ""
            QMessageBox.warning(self,"만기일 오류","형식: YYYYMMDD"); return None, ""
        return code, tag

    def _strikes_for_zone(self, atm, step, n):
        if self._zone == "ITM":
            call_s = [atm - i*step for i in range(n)]
            put_s  = [atm + i*step for i in range(n)]
        elif self._zone == "ATM":
            call_s = [atm + i*step for i in range(n)]
            put_s  = [atm - i*step for i in range(n)]
        else:
            skip = max(1, round(100 / step))
            call_s = [atm + (skip+i)*step for i in range(n)]
            put_s  = [atm - (skip+i)*step for i in range(n)]
        return call_s, put_s

    # ─────────────────────────────────────────────────────────
    # 기초자산 요청
    # ─────────────────────────────────────────────────────────
    def _req_und(self, sym):
        # SPXW → SPX 자동 변환
        sym = sym.upper().replace("SPXW", "SPX")
        if not self.mw.connected: return
        try: self.mw.ib.cancelMktData(REQ_UND)
        except: pass
        auto_mdt(self.mw.ib)
        self.mw.ib.reqMktData(REQ_UND, make_und_contract(sym), "232", False, False, [])

    def _refresh_und(self):
        if not self.mw.connected: return
        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
        self._req_und(sym)

    # ─────────────────────────────────────────────────────────
    # 조회
    # ─────────────────────────────────────────────────────────
    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","먼저 TWS에 연결하세요."); return
        if self.und_price is None:
            sym = self.edit_sym.text().strip().upper() or "SPX"
            self._log(f"현재가 수신 중… ({sym}) 잠시 후 재시도합니다.")
            self._req_und(sym); QTimer.singleShot(2000, self._fetch); return
        expiry, tag = self._get_expiry()
        if not expiry: return
        sym = self.edit_sym.text().strip().upper() or "SPX"
        n   = self.spin_n.value(); self._n_strikes = n

        from core import _resolve_spx_trading_class
        display_tc = (_resolve_spx_trading_class(sym, expiry, tag)
                      if sym in ("SPX","SPXW") else sym)
        _,_,_,step = SYMBOL_CFG.get(sym if sym != "SPXW" else "SPX", DEFAULT_CFG)

        try:
            self.mw.ib.cancelMktData(REQ_UND)
            for i in range(self._MAX_STRIKES):
                self.mw.ib.cancelMktData(REQ_CALL+i)
                self.mw.ib.cancelMktData(REQ_PUT+i)
        except: pass

        self.call_data.clear(); self.put_data.clear()
        if PG: self._prices.clear(); self._deltas.clear(); self._spreads.clear()

        atm = round(self.und_price/step)*step
        self.call_strikes, self.put_strikes = self._strikes_for_zone(atm, step, n)

        self._init_tbl(self.tbl_call, self.call_strikes)
        self._init_tbl(self.tbl_put,  self.put_strikes)

        ticks = "100,101,106"
        if self.call_strikes:
            _c0 = make_opt_contract(sym, self.call_strikes[0], "C", expiry, tag)
            self._log(f"계약: symbol={_c0.symbol} tc={getattr(_c0,'tradingClass','')} "
                      f"exch={_c0.exchange} zone={self._zone} n={n}")
        for i, st in enumerate(self.call_strikes):
            rid = REQ_CALL+i; self.call_data[rid] = {"row":i}
            self.mw.ib.reqMktData(rid, make_opt_contract(sym,st,"C",expiry,tag), ticks, False, False, [])
        for i, st in enumerate(self.put_strikes):
            rid = REQ_PUT+i; self.put_data[rid] = {"row":i}
            self.mw.ib.reqMktData(rid, make_opt_contract(sym,st,"P",expiry,tag), ticks, False, False, [])

        self._req_und(sym)
        self._und_timer.start()
        self._log(f"{display_tc}  ATM={atm}  만기={expiry}  Zone={self._zone}  n={n}")

    def _init_tbl(self, tbl, strikes):
        from tab_options import _mk
        tbl.clearContents(); tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r,0,_mk(str(int(s)),"#ffd700"))
            for c in range(1,6): tbl.setItem(r,c,_mk("―"))

    # ─────────────────────────────────────────────────────────
    # 테이블 클릭
    # ─────────────────────────────────────────────────────────
    def _tbl_click(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            self._prices.clear(); self._deltas.clear()
            self._price_times.clear(); self._candle_bars.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        self.chart_lbl.setText(f"차트: {label}  {int(strikes[row])}  (실시간 추적 중)")
        self._log(f"차트 선택: {label} {int(strikes[row])}")
        self.watch_side.setText(side)
        self.watch_strike.setText(str(int(strikes[row])))
        tbl = self.tbl_call if side == "C" else self.tbl_put
        price_item = tbl.item(row, 1)
        cur_price = None
        if price_item:
            try: cur_price = float(price_item.text())
            except: pass
        self._qord_fill(side, str(int(strikes[row])), cur_price, source="← 테이블 클릭")

    def _tbl_dbl(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            self._prices.clear(); self._deltas.clear()
            self._price_times.clear(); self._candle_bars.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        self.chart_lbl.setText(f"차트: {label}  {int(strikes[row])}  ✔ 확정")
        self._log(f"차트 확정: {label} {int(strikes[row])}")

    # ─────────────────────────────────────────────────────────
    # 관심종목
    # ─────────────────────────────────────────────────────────
    def _on_watch_dbl(self, item):
        sym = item.text().strip().upper().replace("SPXW", "SPX")
        self.edit_sym.setText(sym)
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        self.und_price = None; self.lbl_und.setText("조회 중…")
        self._req_und(sym); QTimer.singleShot(1000, self._fetch)

    def _on_watch_single_click(self, item):
        """단일클릭 → 기초자산 현재가 + 차트 갱신."""
        sym = item.text().strip().upper().replace("SPXW", "SPX")
        self._req_und(sym)
        if PG:
            self._und_hist.clear()
            self._c_und.setData([])
        self._log(f"관심종목 선택: {sym}  (기초자산 차트 갱신)")

    def _w_add(self):
        t, ok = QInputDialog.getText(self,"추가","심볼:")
        if ok and t.strip(): self.watchlist.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watchlist.currentRow()
        if r >= 0: self.watchlist.takeItem(r)