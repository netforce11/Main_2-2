"""
core_conn.py — 연결·MDT·SPXW·Zone·만기 로직  v6.5
════════════════════════════════════════════════════════
v6.5 개선 사항:
  [1] 데이터 생존 감시 (_watch_dog)
      - _last_tick_time 타임스탬프 기록
      - 3초 이상: 황색 "● 지연 발생" 경고
      - 10초 이상: 적색 "● 데이터 멈춤!" 경고
  [2] 체결 이벤트 중복 방지 (execId 체크)
      - 최근 20개 execId 캐시로 Race Condition 차단
  [3] MDT 전환 후 틱타입 검증
      - 첫 틱 수신 시 실시간/지연 구분 → "권한 없음" 알림
  [4] 자동 재연결 흐름 (_reconnect_flow)
      - ERR 1100/100 발생 시 전체 구독 해지 → 재연결 → 재구독

포함 메서드:
  _connect_signals() / _log()
  _on_connected() / _auto_fetch_spxw_today()
  _on_error() / _apply_mdt() / _apply_mdt_manual()
  _build_spxw_combo() / _on_spxw_select()
  _on_zone_change() / _on_exp_change()
  _open_calendar() / _on_date_edit_changed() / _get_expiry()
  _strikes_for_zone()
  _watch_dog()            ← NEW v6.5
  _reconnect_flow()       ← NEW v6.5
════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta
from collections import deque

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

        # [S11] 미체결 시그널 연결
        bridge.open_order_sig.connect(self._on_bridge_open_order)

        # ── [v6.5-1] 데이터 생존 감시 타이머 (3초마다) ─────────────
        self._last_tick_time  = None          # 마지막 틱 수신 시각
        self._mdt_verify_mode = False         # MDT 검증 대기 중 플래그
        self._exec_id_cache   = deque(maxlen=20)  # [v6.5-2] 중복 체결 방지

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(3000)
        self._watchdog_timer.timeout.connect(self._watch_dog)
        self._watchdog_timer.start()

        # ✅ 체결 콜백 등록 (연결 후 ib 객체에 직접 패치)
        QTimer.singleShot(3000, self._hook_fill_callbacks)

    # ── [v6.5-1] 데이터 생존 감시 ───────────────────────────────
    def _watch_dog(self):
        """3초마다 호출 — 마지막 틱 수신 시각 기준으로 상태 경고."""
        if not self.mw.connected: return
        if self._last_tick_time is None: return   # 아직 틱 미수신

        elapsed = (datetime.now() - self._last_tick_time).total_seconds()

        if elapsed > 10:
            self.lbl_status.setText("● 데이터 멈춤!")
            self.lbl_status.setStyleSheet(
                "color:#ff4444;font-weight:bold;border:none;")
        elif elapsed > 3:
            self.lbl_status.setText("● 지연 발생")
            self.lbl_status.setStyleSheet(
                "color:#ffbb00;font-weight:bold;border:none;")
        else:
            # 정상 — 연결됨 표시 복원
            cur = self.lbl_status.text()
            if cur in ("● 데이터 멈춤!", "● 지연 발생"):
                self.lbl_status.setText("● 연결됨")
                self.lbl_status.setStyleSheet(
                    "color:#00ff88;font-weight:bold;border:none;")

    # ── [v6.5-4] 자동 재연결 흐름 ───────────────────────────────
    def _reconnect_flow(self):
        """
        ERR 1100/100 발생 시 호출.
        전체 구독 해지 → 5초 후 재연결 → 3초 후 재구독.
        """
        self._log("🔄 재연결 흐름 시작: 전체 구독 해지 중…")
        self.lbl_status.setText("● 재연결 중…")
        self.lbl_status.setStyleSheet(
            "color:#ff9800;font-weight:bold;border:none;")

        # ① 전체 구독 해지
        try:
            if self.mw.ib:
                self.mw.ib.cancelMktData(REQ_UND)
                for i in range(getattr(self, '_MAX_STRIKES', 20)):
                    self.mw.ib.cancelMktData(REQ_CALL + i)
                    self.mw.ib.cancelMktData(REQ_PUT  + i)
        except Exception as e:
            self._log(f"구독 해지 오류 (무시): {e}")

        # ② 5초 후 재연결 시도
        def _do_reconnect():
            self._log("🔄 TWS 재연결 시도…")
            try:
                self.mw.disconnect_ibkr()
            except Exception:
                pass
            QTimer.singleShot(2000, lambda: self.mw.connect_ibkr(silent=True))

        # ③ 재연결 후 3초 뒤 재구독
        def _do_resubscribe():
            if not self.mw.connected:
                self._log("⚠ 재연결 실패 — 수동으로 연결 버튼을 눌러주세요.")
                return
            self._log("🔄 재구독 시작…")
            sym = self.edit_sym.text().strip().upper() or "SPX"
            self._req_und(sym)
            QTimer.singleShot(1000, self._fetch)
            # [v1.1] 재연결 후 잔고 자동 재조회
            if hasattr(self, '_on_pos_reconnect_hook'):
                QTimer.singleShot(1500, self._on_pos_reconnect_hook)

        QTimer.singleShot(5000,  _do_reconnect)
        QTimer.singleShot(10000, _do_resubscribe)

    # ── 체결 콜백 등록 ───────────────────────────────────────────
    def _hook_fill_callbacks(self):
        """체결(execDetails) 및 주문상태(orderStatus) 콜백을 ib 객체에 패치."""
        if not self.mw.connected or not self.mw.ib: return
        ib = self.mw.ib

        _orig_exec = getattr(ib, 'execDetails', lambda *a: None)
        def _on_exec(reqId, contract, execution):
            try: _orig_exec(reqId, contract, execution)
            except: pass

            # ── [v6.5-2] execId 중복 체크 ──────────────────────
            exec_id = getattr(execution, 'execId', None)
            if exec_id and exec_id in self._exec_id_cache:
                return   # 중복 체결 이벤트 무시
            if exec_id:
                self._exec_id_cache.append(exec_id)

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
        if hasattr(self, 'btn_pos_toggle'):
            if not getattr(self, '_pos_float_win', None) or \
               not self._pos_float_win.isVisible():
                self.btn_pos_toggle.setChecked(True)
                self._on_pos_toggle()
        # 체결 후 잔고 갱신 (기존 500ms 딜레이 유지)
        if hasattr(self, '_refresh_positions'):
            QTimer.singleShot(500, self._refresh_positions)

    def _log(self, msg):
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 200:
            self.log.setPlainText("\n".join(lines[-150:]))

    # ── [v6.5-1] 틱 수신 시 타임스탬프 갱신 ────────────────────
    def _on_tick_price(self, reqId, tickType, price, attrib=None):
        """
        기존 _on_tick_price 앞단에 타임스탬프 갱신 삽입.
        실제 틱 처리는 super() 또는 CallPutGrid의 동일 메서드로 위임.
        ※ CallPutGrid._on_tick_price 가 이 메서드를 오버라이드하므로,
          CallPutGrid._on_tick_price 첫 줄에 아래 한 줄 추가해도 동일:
          self._last_tick_time = datetime.now()
        """
        self._last_tick_time = datetime.now()

        # ── [v6.5-3] MDT 검증: 첫 틱 타입으로 실시간/지연 확인 ─
        if self._mdt_verify_mode and reqId == REQ_UND:
            self._mdt_verify_mode = False
            # 실시간 틱: 1~21 / 지연 틱: 66~76
            is_live_tick = tickType < 66
            requested_live = getattr(self, '_requested_live', False)
            if requested_live and not is_live_tick:
                self._log(
                    "⚠ 실시간 시세 권한 없음 — 지연 데이터로 수신 중입니다. "
                    "TWS에서 시세 구독 권한을 확인하세요.")
                self.lbl_status.setText("● 권한 없음(지연)")
                self.lbl_status.setStyleSheet(
                    "color:#ff9800;font-weight:bold;border:none;")
            elif is_live_tick:
                self._log("✅ 실시간 시세 정상 수신")

    def _on_connected(self):
        self.lbl_status.setText("● 연결됨")
        self.lbl_status.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        self._log("TWS 연결 성공 ✓")

        # ✅ 이전 세션 잔류값 초기화
        self.und_price = None
        self.und_prev  = None
        self._last_tick_time = None   # [v6.5-1] 타임스탬프 리셋
        if hasattr(self, 'lbl_und'):
            self.lbl_und.setText("조회 중…")

        def _step2_req_und():
            self._apply_mdt()
            self._req_und(self.edit_sym.text().upper())
            from core import is_market_open
            if not is_market_open():
                self._und_timer.start()

        def _step3_setup():
            self._auto_fetch_spxw_today()
            # [v1.1] 초기 연결 시 잔고 자동 조회
            if hasattr(self, '_on_pos_reconnect_hook'):
                QTimer.singleShot(1500, self._on_pos_reconnect_hook)

        QTimer.singleShot(300,  _step2_req_und)
        QTimer.singleShot(2500, _step3_setup)

        # [S11] 계좌번호 → lbl_acct_mode 갱신 (즉시 시도 + 500ms 재시도)
        self._fetch_and_show_account()
        QTimer.singleShot(500, self._fetch_and_show_account)

    def _auto_fetch_spxw_today(self):
        """연결 후 SPXW 0DTE 콤보만 자동 선택."""
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
        # 정상 알림 / 무해한 에러 무시
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        if code == 354:
            cnt = getattr(self, '_err354_count', 0) + 1
            self._err354_count = cnt
            if cnt <= 3:
                self._log(f"ERR 354 ({cnt}/3): MDT 타이밍 이슈 — 데이터 수신 중이면 무시")
            return
        self._err354_count = 0

        # ── [v6.5-4] 치명적 에러 → 자동 재연결 흐름 ────────────
        if code in (1100, 100):
            self._log(f"🚨 ERR {code}: {msg} — 자동 재연결 시작")
            QTimer.singleShot(1000, self._reconnect_flow)
            return

        self._log(f"ERR {code}: {msg}")

    def _apply_mdt(self):
        if not self.mw.connected: return
        mdt = auto_mdt(self.mw.ib)
        self.radio_delay.blockSignals(True); self.radio_live.blockSignals(True)
        self.radio_live.setChecked(mdt == 1)
        self.radio_delay.setChecked(mdt != 1)
        self.radio_delay.blockSignals(False); self.radio_live.blockSignals(False)

    def _apply_mdt_manual(self):
        """
        수동 MDT 전환.
        [v6.5-3] 전환 후 첫 틱 타입으로 실제 실시간/지연 여부 검증.
        """
        if not self.mw.connected: return
        mdt = 1 if self.radio_live.isChecked() else 3
        self._requested_live  = (mdt == 1)   # [v6.5-3] 검증용 플래그
        self._mdt_verify_mode = True          # [v6.5-3] 다음 틱에서 검증
        try:
            self.mw.ib.reqMarketDataType(mdt)
            self._log(f"시세모드 전환: {'실시간(1)' if mdt==1 else '지연(3)'} — 첫 틱 수신 후 검증")
        except Exception as e:
            self._log(f"MDT 전환 실패: {e}")
            self._mdt_verify_mode = False
            return
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(300, lambda: self._req_und(self.edit_sym.text().upper()))

    # ── SPXW 0DTE 콤보 ──────────────────────────────────────────
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

    # ── Zone / 만기 ─────────────────────────────────────────────
    def _on_zone_change(self, btn):
        for z, rb in self._zone_btns.items():
            if rb is btn: self._zone = z
        if self.und_price is not None: self._fetch()

    def _refresh_expiry_list(self):
        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
        self._expiry_list = build_expiry_list(sym)
        self.combo_exp.blockSignals(True)
        self.combo_exp.clear()
        for label, _, _ in self._expiry_list:
            self.combo_exp.addItem(label)
        self.combo_exp.blockSignals(False)

        if not self._expiry_list:
            return

        from datetime import datetime as _dt
        today_str = _dt.today().strftime("%Y%m%d")
        best_idx = 0
        for i, (_, code, _) in enumerate(self._expiry_list):
            if code == "CUSTOM":
                continue
            best_idx = i
            break
        self.combo_exp.setCurrentIndex(best_idx)
        _, code, best_date = self._expiry_list[best_idx]

        if code == "CUSTOM":
            today = datetime.today().date()
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(today.year, today.month, today.day))
            self.date_edit.blockSignals(False)
            self.date_edit.setVisible(True)
        else:
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

    def _get_expiry(self, silent: bool = False):
        """
        현재 선택된 만기일 (code, tag) 반환.
        silent=True 또는 UI 초기화 중일 때는 QMessageBox 없이
        None 반환만 하고 로그에만 기록한다 (시작 시 랙 방지).
        """
        if not getattr(self, '_expiry_list', None):
            return None, ""

        idx = self.combo_exp.currentIndex()
        if idx < 0 or idx >= len(self._expiry_list):
            return None, ""

        _, code, tag = self._expiry_list[idx]
        if code == "CUSTOM":
            raw = (self.date_edit.date().toString("yyyyMMdd")
                   if self.date_edit.isVisible()
                   else self.edit_custom.text().strip())
            if len(raw) == 8 and raw.isdigit():
                return raw, ""
            # ★ QMessageBox 대신 로그만 — 초기화/자동호출 시 팝업·랙 방지
            if not silent:
                self._log("⚠ 만기일 형식 오류 (YYYYMMDD). 날짜를 다시 선택하세요.")
            return None, ""
        return code, tag

    def _strikes_for_zone(self, atm, step, n):
        if self._zone == "ITM":
            return ([atm - i*step for i in range(n)],
                    [atm + i*step for i in range(n)])
        elif self._zone == "ATM":
            return ([atm + i*step for i in range(n)],
                    [atm - i*step for i in range(n)])
        else:   # OTM — [v6.5] 비율 기반 동적 skip (atm의 1.5%)
            dynamic_skip_pt = atm * 0.015
            skip = max(1, round(dynamic_skip_pt / step))
            return ([atm + (skip+i)*step for i in range(n)],
                    [atm - (skip+i)*step for i in range(n)])
    # ═══════════════════════════════════════════════════════════
    # [S11] 모의/실제 모드 포트 전환 지원
    # ═══════════════════════════════════════════════════════════

    # 포트 매핑 상수
    _PORT_MAP = {
        # (is_live, use_gateway)
        (True,  False): 7496,   # TWS 실계좌
        (False, False): 7497,   # TWS 모의계좌
        (True,  True):  4001,   # IB Gateway 실계좌
        (False, True):  4002,   # IB Gateway 모의계좌
    }

    def get_trading_port(self, is_live: bool, use_gateway: bool = False) -> int:
        """is_live / use_gateway 조합에 맞는 포트 번호 반환."""
        return self._PORT_MAP.get((is_live, use_gateway), 7497)

    def set_trading_mode(self, is_live: bool, use_gateway: bool = False):
        """
        [S11-7] 거래 모드 전환.
        1) core.TWS_PORT 갱신
        2) lbl_status 색상 변경
        3) 로그 출력
        """
        import core as _core
        port = self.get_trading_port(is_live, use_gateway)
        _core.TWS_PORT = port

        if hasattr(self, 'mw') and self.mw and hasattr(self.mw, 'tws_port'):
            self.mw.tws_port = port

        mode_str = "🔴 실제 거래" if is_live else "🟢 모의투자"
        gw_str   = " (IB Gateway)" if use_gateway else " (TWS)"
        self._log(f"{mode_str}{gw_str}  →  Port {port}")

        # lbl_status 색상 갱신
        if hasattr(self, 'lbl_status'):
            col = "#ff5252" if is_live else "#00e676"
            tag = "실계좌" if is_live else "모의계좌"
            self.lbl_status.setStyleSheet(
                f"color:{col};font-weight:bold;border:none;font-size:11px;")
            if not self.mw.connected:
                self.lbl_status.setText(f"● 미연결 ({tag})")

    def reconnect_with_mode(self, is_live: bool, use_gateway: bool = False):
        """
        모드 전환 후 재연결 실행.
        strategy_panel._apply_trading_mode() 에서 호출.
        """
        self.set_trading_mode(is_live, use_gateway)
        port = self.get_trading_port(is_live, use_gateway)

        def _do():
            try:
                self.mw.disconnect_ibkr()
            except Exception:
                pass
            QTimer.singleShot(1000, lambda: self._connect_to_port(port))

        QTimer.singleShot(200, _do)

    def _connect_to_port(self, port: int):
        """지정된 포트로 connect_ibkr 호출 — port 인자 지원 여부 자동 판별."""
        if not hasattr(self, 'mw') or not self.mw: return
        try:
            self.mw.connect_ibkr(port=port)
        except TypeError:
            # 기존 connect_ibkr(port=) 시그니처 미지원 → 전역 상수만 변경 후 재연결
            self.mw.connect_ibkr()

    # ── [S11] 미체결 시그널 버퍼링 & 테이블 갱신 ────────────────
    def _on_bridge_open_order(self, oid: int, sym: str, side: str,
                               action: str, qty: float, price: float, status: str):
        """
        bridge.open_order_sig → 버퍼에 누적 후 200ms 뒤 일괄 갱신.
        open_order_sig(int, str, str, str, float, float, str)
        """
        buf = getattr(self, '_open_orders_buf', [])

        # C/P 판별 — localSymbol 마지막 C/P 문자 또는 side 값
        cp = "C" if side.upper() in ("C", "CALL") else "P"

        entry = (str(oid), cp, sym, action, str(int(qty)), f"{price:.2f}", status)
        # 동일 oid 갱신
        updated = False
        for i, row in enumerate(buf):
            if row[0] == str(oid):
                buf[i] = entry; updated = True; break
        if not updated:
            buf.append(entry)

        self._open_orders_buf = buf

        # 디바운스: 200ms 후 일괄 반영
        t = getattr(self, '_oo_flush_timer', None)
        if t is None:
            self._oo_flush_timer = QTimer(self)
            self._oo_flush_timer.setSingleShot(True)
            self._oo_flush_timer.timeout.connect(self._flush_open_orders)
        self._oo_flush_timer.start(200)

    def _flush_open_orders(self):
        """버퍼에 쌓인 미체결 항목을 tbl_open_orders에 일괄 반영."""
        if hasattr(self, '_on_open_orders_received'):
            self._on_open_orders_received(list(self._open_orders_buf))

    # ── [S11] 계좌번호 조회 + 빠른 주문 패널 라벨 갱신 ──────────
    def _fetch_and_show_account(self):
        """
        연결 후 계좌번호 수신 → lbl_acct_mode 갱신.

        우선순위:
          1) mw.account_id  — Dashboard가 이미 설정한 값 (가장 빠름)
          2) mw.ib.account  — IBapi 객체 속성
          3) reqManagedAccts 콜백 — 위 둘 다 없을 때 폴백
        """
        # ① mw.account_id 직접 참조 (콘솔 로그 기준 여기서 이미 설정됨)
        acct = getattr(getattr(self, 'mw', None), 'account_id', None)
        if acct:
            self._apply_account_label(str(acct).strip())
            return

        # ② mw.ib.account
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        acct = getattr(ib, 'account', None) if ib else None
        if acct:
            self._apply_account_label(str(acct).strip())
            return

        # ③ reqManagedAccts 폴백
        if ib is None:
            return
        _orig = getattr(ib, 'managedAccounts', lambda a: None)

        def _on_managed(accounts_str: str):
            try: _orig(accounts_str)
            except Exception: pass
            acct = (accounts_str.split(",")[0].strip()
                    if accounts_str else "")
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._apply_account_label(acct))
            ib.managedAccounts = _orig

        ib.managedAccounts = _on_managed
        try:
            ib.reqManagedAccts()
        except Exception:
            pass

    def _apply_account_label(self, acct: str):
        """계좌번호 → lbl_acct_mode 스타일 + 텍스트 갱신."""
        if not acct:
            return
        is_paper = acct.upper().startswith("DU")
        if is_paper:
            text = f"🟢 {acct}  모의"
            col  = "#00e676"
            bg   = "#0a1a0a"
        else:
            text = f"🔴 {acct}  실계좌"
            col  = "#ff5252"
            bg   = "#1a0a0a"

        # 빠른 주문 패널 라벨
        lbl = getattr(self, 'lbl_acct_mode', None)
        if lbl:
            lbl.setText(text)
            lbl.setStyleSheet(
                f"color:{col};font-size:11px;font-weight:bold;border:none;"
                f"background:{bg};border-radius:3px;padding:1px 5px;")
            lbl.setToolTip(
                f"계좌: {acct}\n"
                f"{'모의투자 (Paper Trading)' if is_paper else '⚠ 실계좌 (Live Trading)'}")

        # 사이드바 Zone 라벨 재사용 가능 영역에도 저장
        self._connected_account = acct
        self._is_paper_account  = is_paper

        mode = "모의투자" if is_paper else "실계좌"
        self._log(f"💳 계좌: {acct}  ({mode})")