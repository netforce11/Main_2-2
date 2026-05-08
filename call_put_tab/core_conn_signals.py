"""
core_conn_signals.py — 연결 시그널·Watchdog·재연결·체결콜백·로그  v6.5
[버그 수정]
  #1: 풋옵션 TickRouter 등록 범위 26개로 제한 (불필요한 slot 호출 제거)
  #2: 체결 통보 누락 — _hook_fill_callbacks 패치 강화
  #3: TickRouter 등록 범위 하드코딩 25 (REQ_*+25 = 26개)
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

        # ── [#1 #3 수정] TickRouter 등록 범위: 26개 (0~25) 하드코딩 ──
        # 기존: REQ_CALL + self._MAX_STRIKES - 1  (최대 99, 실사용 64까지)
        # 수정: REQ_CALL + 25  (정확히 26개, TWS 100개 한도 내)
        _MAX_IDX = 25  # 26개 인덱스: 0~25
        router.register_price(REQ_UND,  REQ_UND,          self._on_tick_price)
        router.register_price(REQ_CALL, REQ_CALL + _MAX_IDX, self._on_tick_price)
        router.register_price(REQ_PUT,  REQ_PUT  + _MAX_IDX, self._on_tick_price)
        router.register_option(REQ_CALL, REQ_CALL + _MAX_IDX, self._on_tick_option)
        router.register_option(REQ_PUT,  REQ_PUT  + _MAX_IDX, self._on_tick_option)
        self._watch_timer.start()

        # [S11] 미체결 시그널 연결
        bridge.open_order_sig.connect(self._on_bridge_open_order)

        # ── [v6.5-1] 데이터 생존 감시 타이머 (3초마다) ─────────────
        self._last_tick_time  = None
        self._mdt_verify_mode = False
        self._exec_id_cache   = deque(maxlen=20)  # [v6.5-2] 중복 체결 방지
        self._reconnecting    = False

        # ── [#2 수정] 체결 콜백 전용 캐시 초기화 ──────────────────
        self._order_fill_cache   = set()   # orderStatus 전용 중복 방지
        self._fill_hooks_applied = False   # 패치 적용 여부 플래그

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(3000)
        self._watchdog_timer.timeout.connect(self._watch_dog)
        self._watchdog_timer.start()

        # ── [#2 수정] 체결 콜백 등록: 3000 → 1000ms ───────────────
        # 기존: QTimer.singleShot(3000, self._hook_fill_callbacks)
        # 수정: 1000ms — 주문 후 즉시 체결(네이키드) 놓치지 않도록
        QTimer.singleShot(1000, self._hook_fill_callbacks)

    # ── [v6.5-1] 데이터 생존 감시 ───────────────────────────────
    def _watch_dog(self):
        """3초마다 호출 — 마지막 틱 수신 시각 기준으로 상태 경고."""
        if not self.mw.connected: return
        if self._last_tick_time is None: return

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
            cur = self.lbl_status.text()
            if cur in ("● 데이터 멈춤!", "● 지연 발생"):
                self.lbl_status.setText("● 연결됨")
                self.lbl_status.setStyleSheet(
                    "color:#00ff88;font-weight:bold;border:none;")

    # ── [v6.5-4] 자동 재연결 흐름 ───────────────────────────────
    def _reconnect_flow(self):
        if getattr(self, '_reconnecting', False):
            self._log("⚠ 재연결 이미 진행 중 — 중복 요청 무시")
            return
        self._reconnecting = True

        self._log("🔄 재연결 흐름 시작: 전체 구독 해지 중…")
        self.lbl_status.setText("● 재연결 중…")
        self.lbl_status.setStyleSheet(
            "color:#ff9800;font-weight:bold;border:none;")

        try:
            if self.mw.ib:
                self.mw.ib.cancelMktData(REQ_UND)
                for i in range(26):  # [#3 수정] 26개 범위만 취소
                    self.mw.ib.cancelMktData(REQ_CALL + i)
                    self.mw.ib.cancelMktData(REQ_PUT  + i)
        except Exception as e:
            self._log(f"구독 해지 오류 (무시): {e}")

        def _do_reconnect():
            self._log("🔄 TWS 재연결 시도…")
            try:
                self.mw.disconnect_ibkr()
            except Exception:
                pass
            QTimer.singleShot(2000, lambda: self.mw.connect_ibkr(silent=True))

        def _do_resubscribe():
            self._reconnecting = False
            if not self.mw.connected:
                self._log("⚠ 재연결 실패 — 수동으로 연결 버튼을 눌러주세요.")
                return
            self._log("🔄 재구독 시작…")
            sym = self.edit_sym.text().strip().upper() or "SPX"
            self._req_und(sym)
            QTimer.singleShot(1000, self._fetch)
            if hasattr(self, '_on_pos_reconnect_hook'):
                QTimer.singleShot(1500, self._on_pos_reconnect_hook)

        QTimer.singleShot(5000,  _do_reconnect)
        QTimer.singleShot(10000, _do_resubscribe)

    # ── 체결 콜백 등록 ───────────────────────────────────────────
    def _hook_fill_callbacks(self):
        """
        [버그 #2 수정] 체결(execDetails) 및 주문상태(orderStatus) 콜백 패치.

        수정 사항:
          1) _fill_hooks_applied 플래그로 재패치 방지 (재연결 시 _on_connected 에서 초기화)
          2) _order_fill_cache — orderStatus 전용 중복 방지 set
          3) orderStatus 에서 lastFillPrice 우선 사용, avgFillPrice=0 허용
          4) execDetails 처리 OID를 _order_fill_cache 에 마킹 → orderStatus 중복 억제
        """
        if not self.mw.connected or not self.mw.ib:
            return

        # ── [#2 수정] 이미 패치됐으면 재패치 안 함 ─────────────
        if getattr(self, '_fill_hooks_applied', False):
            return
        self._fill_hooks_applied = True

        ib = self.mw.ib

        # ── [#2 수정] orderStatus 전용 캐시 초기화 ──────────────
        if not hasattr(self, '_order_fill_cache'):
            self._order_fill_cache = set()

        _orig_exec = getattr(ib, 'execDetails', lambda *a: None)

        def _on_exec(reqId, contract, execution):
            try:
                _orig_exec(reqId, contract, execution)
            except Exception:
                pass

            # ── [v6.5-2] execId 중복 체크 ──────────────────────
            exec_id = getattr(execution, 'execId', None)
            if exec_id and exec_id in self._exec_id_cache:
                return
            if exec_id:
                self._exec_id_cache.append(exec_id)

            sym  = (getattr(contract, 'localSymbol', '')
                    or getattr(contract, 'symbol', ''))
            qty  = getattr(execution, 'shares', 0)
            side = getattr(execution, 'side', '')
            px   = getattr(execution, 'price', 0)
            oid  = getattr(execution, 'orderId', None)

            # ── [#2 수정] 이 OID는 execDetails 처리됨 → orderStatus 중복 억제 ─
            if oid is not None:
                self._order_fill_cache.add(oid)

            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._on_fill_event(sym, qty, side, px))

        ib.execDetails = _on_exec

        _orig_status = getattr(ib, 'orderStatus', lambda *a: None)

        def _on_status(orderId, status, filled, remaining, avgFillPrice,
                       permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
            try:
                _orig_status(orderId, status, filled, remaining, avgFillPrice,
                             permId, parentId, lastFillPrice, clientId,
                             whyHeld, mktCapPrice)
            except Exception:
                pass

            if status != 'Filled' or filled <= 0:
                return

            # ── [#2 수정] execDetails 가 이미 처리한 OID는 건너뜀 ──
            if orderId in self._order_fill_cache:
                self._order_fill_cache.discard(orderId)
                return

            # execDetails 미수신 → orderStatus 단독 체결 통보
            # lastFillPrice 우선, 없으면 avgFillPrice (0이어도 통보)
            fill_px = lastFillPrice if lastFillPrice and lastFillPrice > 0 else avgFillPrice
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._on_fill_event(
                f"OID={orderId}", filled, "", fill_px))

        ib.orderStatus = _on_status
        self._log("✅ 체결 콜백 패치 완료 (execDetails + orderStatus)")

    def _on_fill_event(self, sym, qty, side, price):
        """체결 이벤트 공통 처리: 로그 출력 + 잔고창 자동 팝업 + 포지션 갱신."""
        side_str = f" {side}" if side else ""
        self._log(f"✅ 체결 완료: {sym}{side_str} {qty}계약  @{price:.2f}")
        if hasattr(self, 'btn_pos_toggle'):
            if not getattr(self, '_pos_float_win', None) or \
               not self._pos_float_win.isVisible():
                self.btn_pos_toggle.setChecked(True)
                self._on_pos_toggle()
        if hasattr(self, '_refresh_positions'):
            QTimer.singleShot(500, self._refresh_positions)

    def _log(self, msg):
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 200:
            self.log.setPlainText("\n".join(lines[-150:]))

    # ── [v6.5-1] 틱 수신 시 타임스탬프 갱신 ────────────────────
    def _on_tick_price(self, reqId, tickType, price, attrib=None):
        self._last_tick_time = datetime.now()

        if self._mdt_verify_mode and reqId == REQ_UND:
            self._mdt_verify_mode = False
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

        super()._on_tick_price(reqId, tickType, price, attrib)