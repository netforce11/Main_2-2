"""
core_conn_account.py — 포트 전환·계좌 조회·미체결 버퍼링  v6.5
"""

from PyQt5.QtCore import QTimer


class ConnAccountMixin:
    """포트 전환·계좌 조회·미체결 버퍼링. CoreConnMixin에 통합된다."""

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
        # 동일 oid 갱신 — dict / tuple 혼재 방어
        updated = False
        for i, row in enumerate(buf):
            try:
                # dict 형식 (order_panel._fetch_open_orders 가 넣은 경우)
                row_oid = str(row["oid"]) if isinstance(row, dict) else str(row[0])
            except (KeyError, IndexError, TypeError):
                continue
            if row_oid == str(oid):
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