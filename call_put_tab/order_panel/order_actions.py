"""
order_panel/order_actions.py — 미체결 조회·테이블 갱신·KST·수수료·유형토글
════════════════════════════════════════════════════════════════════
[v6.7 수정]
  reqOpenOrders() → reqAllOpenOrders()
  : 현재 API 세션 주문만 조회 → TWS 전체 미체결 조회 (수동 주문 포함)
"""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from PyQt5.QtGui import QColor
from .helpers import _kst_now


class OrderActionsMixin:
    """미체결 조회·테이블·KST·수수료 로직. OrderPanelMixin에 mixin된다."""

    def _update_kst_labels(self):
        t = _kst_now()
        if hasattr(self, 'lbl_amend_time'):  self.lbl_amend_time.setText(t)
        if hasattr(self, 'lbl_cancel_time'): self.lbl_cancel_time.setText(t)

    def _update_commission_label(self, qty=1):
        fee = max(qty * 0.65, 1.00)
        self.lbl_commission.setText(f"예상 수수료: ${fee:.2f}  ({qty}계약 × $0.65)")

    def _on_qord_type_toggle(self):
        is_lmt = self.qord_lmt.isChecked()
        self.qord_price.setEnabled(is_lmt)
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;" if is_lmt else
            "color:#555;font-weight:bold;font-size:15px;"
            "background:#070710;border:1px solid #222;")

    def _fetch_open_orders(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        self._open_orders_buf = []
        self._fetch_oo_done   = False
        ib = self.mw.ib

        def _on_open_order(orderId, contract, order, orderState):
            self._open_orders_buf.append({
                "oid":      orderId,
                "symbol":   getattr(contract, "localSymbol", "") or getattr(contract, "symbol", ""),
                "action":   getattr(order, "action", ""),
                "price":    getattr(order, "lmtPrice", 0.0),
                "qty":      getattr(order, "totalQuantity", 0),
                "type":     getattr(order, "orderType", ""),
                "tif":      getattr(order, "tif", "DAY"),
                "contract": contract,
            })

        def _restore_handlers():
            if not self._fetch_oo_done:
                self._fetch_oo_done = True
                ib.openOrder    = ib._orig_openOrder
                ib.openOrderEnd = ib._orig_openOrderEnd

        def _on_open_order_end():
            t = getattr(self, '_oo_timeout_timer', None)
            if t is not None:
                t.stop()
            _restore_handlers()
            QTimer.singleShot(0, self._populate_open_order_tables)

        ib._orig_openOrder    = getattr(ib, 'openOrder',    lambda *a: None)
        ib._orig_openOrderEnd = getattr(ib, 'openOrderEnd', lambda: None)
        ib.openOrder    = _on_open_order
        ib.openOrderEnd = _on_open_order_end

        try:
            # [v6.7] reqOpenOrders → reqAllOpenOrders
            # reqOpenOrders    : 현재 API 세션 주문만 반환 (TWS 수동 주문 누락)
            # reqAllOpenOrders : TWS 전체 미체결 반환 (수동 주문 + 재시작 전 주문 포함)
            ib.reqAllOpenOrders()
            self._log("📋 미체결 주문 조회 요청 (reqAllOpenOrders)...")
        except Exception as e:
            self._log(f"❌ 주문 조회 오류: {e}")

        if not hasattr(self, '_oo_timeout_timer'):
            self._oo_timeout_timer = QTimer(self)
            self._oo_timeout_timer.setSingleShot(True)
        else:
            self._oo_timeout_timer.stop()

        self._oo_timeout_timer.timeout.disconnect() if self._oo_timeout_timer.receivers(
            self._oo_timeout_timer.timeout) > 0 else None
        self._oo_timeout_timer.timeout.connect(lambda: (
            _restore_handlers(),
            self._populate_open_order_tables()
        ) if not self._fetch_oo_done else None)
        self._oo_timeout_timer.start(5000)

    def _populate_open_order_tables(self):
        def _mk(text, color="#ccc"):
            item = QTableWidgetItem(str(text))
            item.setForeground(QColor(color))
            return item
        orders = getattr(self, '_open_orders_buf', [])
        for tbl in (self.tbl_open_orders_a, self.tbl_open_orders_c):
            tbl.setRowCount(0)
            for o in orders:
                r = tbl.rowCount(); tbl.insertRow(r)
                price_str = f"{o['price']:.2f}" if o['price'] else o['type']
                col = "#00ff88" if o['action'] == "BUY" else "#ff6666"
                tbl.setItem(r, 0, _mk(str(o['oid']),                "#ffd700"))
                tbl.setItem(r, 1, _mk(o['symbol'],                  "#ccc"))
                tbl.setItem(r, 2, _mk(f"{o['action']} {o['qty']}", col))
                tbl.setItem(r, 3, _mk(price_str,                    "#90caf9"))
        self._log(f"📋 미체결 주문 {len(orders)}건 수신")

    def _fill_amend_from_table(self, row):
        tbl      = self.tbl_open_orders_a
        oid_item = tbl.item(row, 0)
        prc_item = tbl.item(row, 3)
        dir_item = tbl.item(row, 2)
        if oid_item: self.amend_oid.setText(oid_item.text())
        if prc_item:
            try:
                self.amend_price.setText(f"{float(prc_item.text()):.2f}")
            except ValueError:
                pass
        if dir_item:
            parts = dir_item.text().split()
            if len(parts) >= 2:
                try:
                    self.amend_qty.setValue(int(parts[1]))
                except ValueError:
                    pass

    def _fill_cancel_from_table(self, row):
        oid_item = self.tbl_open_orders_c.item(row, 0)
        if oid_item:
            self.cancel_oid.setText(oid_item.text())

    def _try_connect_exec_refresh(self):
        """연결 상태 확인 후 _connect_exec_auto_refresh 호출."""
        if getattr(getattr(self, 'mw', None), 'connected', False):
            self._connect_exec_auto_refresh()
        else:
            if not getattr(self, '_exec_refresh_hook_set', False):
                self._exec_refresh_hook_set = True
                _orig = getattr(self, '_on_connected', None)
                if _orig:
                    def _hooked_on_connected(*a, **kw):
                        _orig(*a, **kw)
                        self._connect_exec_auto_refresh()
                    self._on_connected = _hooked_on_connected
