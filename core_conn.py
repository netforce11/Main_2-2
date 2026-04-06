"""
core_conn.py — 연결·MDT·SPXW·Zone·만기 로직  v6.4
════════════════════════════════════════════════════════
수정 대상: 연결 동작, SPXW 0DTE 콤보, Zone/만기 처리
포함 메서드:
  _connect_signals() / _log()
  _on_connected() / _auto_fetch_spxw_today()
  _on_error() / _apply_mdt() / _apply_mdt_manual()
  _build_spxw_combo() / _on_spxw_select()
  _on_zone_change() / _on_exp_change()
  _open_calendar() / _on_date_edit_changed() / _get_expiry()
  _strikes_for_zone()
════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta

from PyQt5.QtCore import QDate, QTimer
from PyQt5.QtWidgets import QMessageBox

from core import (
    bridge, router, ts,
    REQ_UND, REQ_CALL, REQ_PUT,
    build_expiry_list, make_und_contract,
    auto_mdt, is_trading_day,
)


class CoreConnMixin:
    """연결·MDT·SPXW·Zone·만기 로직. CallPutGrid에 mixin된다."""

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
        # ✅ 체결 콜백 등록 (연결 후 ib 객체에 직접 패치)
        QTimer.singleShot(3000, self._hook_fill_callbacks)

    def _hook_fill_callbacks(self):
        """체결(execDetails) 및 주문상태(orderStatus) 콜백을 ib 객체에 패치."""
        if not self.mw.connected or not self.mw.ib: return
        ib = self.mw.ib

        _orig_exec = getattr(ib, 'execDetails', lambda *a: None)
        def _on_exec(reqId, contract, execution):
            try: _orig_exec(reqId, contract, execution)
            except: pass
            sym  = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
            qty  = getattr(execution, 'shares', 0)
            side = getattr(execution, 'side', '')
            px   = getattr(execution, 'price', 0)
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._on_fill_event(sym, qty, side, px))
        ib.execDetails = _on_exec

        _orig_status = getattr(ib, 'orderStatus', lambda *a: None)
        def _on_status(orderId, status, filled, remaining, avgFillPrice,
                       permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
            try: _orig_status(orderId, status, filled, remaining, avgFillPrice,
                              permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
            except: pass
            if status == 'Filled' and filled > 0:
                from PyQt5.QtCore import QTimer as _QT
                _QT.singleShot(0, lambda: self._on_fill_event(
                    f"OID={orderId}", filled, "", avgFillPrice))
        ib.orderStatus = _on_status

    def _on_fill_event(self, sym, qty, side, price):
        """체결 이벤트 공통 처리: 로그 출력 + 잔고창 자동 팝업 + 포지션 갱신."""
        side_str = f" {side}" if side else ""
        self._log(f"✅ 체결 완료: {sym}{side_str} {qty}계약  @{price:.2f}")
        # 잔고창 자동 팝업 (항상 위로)
        if hasattr(self, 'btn_pos_toggle'):
            if not getattr(self, '_pos_float_win', None) or \
               not self._pos_float_win.isVisible():
                self.btn_pos_toggle.setChecked(True)
                self._on_pos_toggle()
            # 잔고 갱신
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(500, self._refresh_positions)

    def _log(self, msg):
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 200:
            self.log.setPlainText("\n".join(lines[-150:]))

    def _on_connected(self):
        self.lbl_status.setText("● 연결됨")
        self.lbl_status.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        self._log("TWS 연결 성공 ✓")

        # ✅ 이전 세션 잔류값 초기화 — ATM 오계산 방지
        self.und_price = None
        self.und_prev  = None
        if hasattr(self, 'lbl_und'):
            self.lbl_und.setText("조회 중…")

        # ✅ Step1: MDT 설정 먼저 (reqMarketDataType은 비동기 → 300ms 후 구독 시작)
        # _apply_mdt()를 즉시 호출하면 TWS 핸드셰이크 전이라 씹힘 → step2로 이동

        def _step2_req_und():
            # Step2: MDT 반영 후 현재가 구독
            self._apply_mdt()          # 여기서 호출해야 reqMarketDataType이 반영됨
            self._req_und(self.edit_sym.text().upper())
            from core import is_market_open
            if not is_market_open():
                self._und_timer.start()

        def _step3_setup():
            # Step3: SPXW 콤보 선택만 설정 (테이블 자동 조회는 하지 않음)
            # 사용자가 직접 조회 버튼을 눌러야 _fetch() 실행됨
            self._auto_fetch_spxw_today()

        QTimer.singleShot(300,  _step2_req_und)   # 300ms: MDT 반영 대기
        QTimer.singleShot(2500, _step3_setup)      # 2.5초 후 SPXW 콤보만 셋업

    def _auto_fetch_spxw_today(self):
        """연결 후 SPXW 0DTE 콤보만 자동 선택. 테이블 조회는 사용자가 직접 버튼 클릭."""
        today = datetime.today().date()
        if not is_trading_day(today):
            self._log("오늘은 거래일이 아닙니다. SPXW 자동 선택 건너뜀."); return
        today_str = today.strftime("%Y%m%d")
        found_idx = next(
            (i for i in range(self.combo_spxw.count())
             if self.combo_spxw.itemData(i) == today_str), -1)
        if found_idx < 0:
            self._log(f"SPXW 0DTE 오늘({today_str}) 항목 없음 — 조회 버튼으로 수동 조회하세요."); return
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.setCurrentIndex(found_idx)
        self.combo_spxw.blockSignals(False)
        self._on_spxw_select(found_idx)
        self._log(f"🔄 SPXW 0DTE 자동 선택: {today_str}  ← 조회 버튼을 눌러 체인을 로드하세요.")

    def _on_error(self, rid, code, msg):
        # 정상 알림 / 타이밍 이슈로 발생하는 무해한 에러 무시
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        # ERR 354: reqMarketDataType 반영 전 타이밍 or 옵션체인 일부 드랍
        # 구독권이 있고 데이터가 정상 수신되면 무시해도 됨
        # 로그 스팸 방지를 위해 카운터로 첫 3회만 출력
        if code == 354:
            cnt = getattr(self, '_err354_count', 0) + 1
            self._err354_count = cnt
            if cnt <= 3:
                self._log(f"ERR 354 ({cnt}/3): MDT 타이밍 이슈 — 데이터 수신 중이면 무시")
            return
        self._err354_count = 0
        self._log(f"ERR {code}: {msg}")

    def _apply_mdt(self):
        if not self.mw.connected: return
        mdt = auto_mdt(self.mw.ib)
        self.radio_delay.blockSignals(True); self.radio_live.blockSignals(True)
        self.radio_live.setChecked(mdt == 1)
        self.radio_delay.setChecked(mdt != 1)
        self.radio_delay.blockSignals(False); self.radio_live.blockSignals(False)

    def _apply_mdt_manual(self):
        if not self.mw.connected: return
        mdt = 1 if self.radio_live.isChecked() else 3
        try:
            self.mw.ib.reqMarketDataType(mdt)
            self._log(f"시세모드 전환: {'실시간(1)' if mdt==1 else '지연(3)'}")
        except Exception as e:
            self._log(f"MDT 전환 실패: {e}")
            return
        # MDT 변경 후 현재가 재구독 (300ms 딜레이로 반영 대기)
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(300, lambda: self._req_und(self.edit_sym.text().upper()))

    # ── SPXW 0DTE 콤보 ──────────────────────────────────────
    def _build_spxw_combo(self):
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
        self.edit_sym.setText("SPXW")
        # ✅ SPXW 선택 시 만기 콤보를 SPX 기준으로 재구성 (더블클릭 잔류값 방지)
        if hasattr(self, '_refresh_expiry_list'):
            self._refresh_expiry_list()
        custom_idx = next(
            (i for i,(_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list)-1)
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

    # ── Zone / 만기 ─────────────────────────────────────────
    def _on_zone_change(self, btn):
        for z, rb in self._zone_btns.items():
            if rb is btn: self._zone = z
        if self.und_price is not None: self._fetch()

    def _refresh_expiry_list(self):
        """종목 변경 시 만기 콤보를 해당 종목에 맞게 재구성.
        오늘 이후 가장 가까운 만기를 자동 선택한다."""
        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
        self._expiry_list = build_expiry_list(sym)
        self.combo_exp.blockSignals(True)
        self.combo_exp.clear()
        for label, _, _ in self._expiry_list:
            self.combo_exp.addItem(label)
        self.combo_exp.blockSignals(False)

        if not self._expiry_list:
            return

        # ✅ 가장 가까운 만기 자동 선택 (CUSTOM 제외)
        # 오늘 날짜를 _expiry_list에서 찾지 않고, 순수하게 첫 번째 비-CUSTOM 항목 선택
        # (build_expiry_list가 이미 오늘 이후 순서로 정렬된 목록을 반환함)
        from datetime import datetime as _dt
        today_str = _dt.today().strftime("%Y%m%d")
        best_idx = 0
        for i, (_, code, _) in enumerate(self._expiry_list):
            if code == "CUSTOM":
                continue
            # 첫 번째 비-CUSTOM 항목을 사용 (build_expiry_list가 미래 순으로 정렬)
            best_idx = i
            break
        self.combo_exp.setCurrentIndex(best_idx)
        _, code, best_date = self._expiry_list[best_idx]

        # ✅ date_edit 항상 선택된 만기 날짜로 동기화 (잔류값 방지)
        if code == "CUSTOM":
            # CUSTOM이면 오늘 날짜로 리셋
            today = datetime.today().date()
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(today.year, today.month, today.day))
            self.date_edit.blockSignals(False)
            self.date_edit.setVisible(True)
        else:
            # 실제 만기 날짜를 date_edit에 반영 (잔류값 덮어씌우기)
            try:
                y,m,d = int(code[:4]),int(code[4:6]),int(code[6:8])
                self.date_edit.blockSignals(True)
                self.date_edit.setDate(QDate(y, m, d))
                self.date_edit.blockSignals(False)
            except: pass
            self.date_edit.setVisible(False)

    def _on_exp_change(self, idx):
        _, code, _ = self._expiry_list[idx]
        self.edit_custom.setVisible(False)
        self.date_edit.setVisible(code == "CUSTOM")
        self.btn_cal.setVisible(True)

    def _open_calendar(self):
        custom_idx = next(
            (i for i,(_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list)-1)
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
            QMessageBox.warning(self,"만기일 오류","형식: YYYYMMDD")
            return None, ""
        return code, tag

    def _strikes_for_zone(self, atm, step, n):
        if self._zone == "ITM":
            return ([atm - i*step for i in range(n)],
                    [atm + i*step for i in range(n)])
        elif self._zone == "ATM":
            return ([atm + i*step for i in range(n)],
                    [atm - i*step for i in range(n)])
        else:   # OTM
            skip = max(1, round(100/step))
            return ([atm + (skip+i)*step for i in range(n)],
                    [atm - (skip+i)*step for i in range(n)])