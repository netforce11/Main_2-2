"""
core_conn_signals.py — 연결 시그널·Watchdog·재연결·체결콜백·로그  v6.5
"""

from datetime import datetime
from collections import deque
from PyQt5.QtCore import QTimer
from core import bridge, router, ts, REQ_UND, REQ_CALL, REQ_PUT


class ConnSignalsMixin:
    """연결 시그널·Watchdog·재연결·체결콜백·로그. CoreConnMixin에 통합된다."""

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
        self._reconnecting    = False              # guard: prevent duplicate reconnect

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
        Called on ERR 1100/100.
        Guard: _reconnecting flag prevents duplicate runs.
        Flow: cancel all → reconnect after 5s → resubscribe after 10s.
        """
        if getattr(self, '_reconnecting', False):
            self._log("⚠ 재연결 이미 진행 중 — 중복 요청 무시")
            return
        self._reconnecting = True

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
            # Clear flag regardless of success so future errors can re-trigger
            self._reconnecting = False
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

        # ── 실제 가격 처리: ChartMixin._on_tick_price 로 위임 ──
        super()._on_tick_price(reqId, tickType, price, attrib)