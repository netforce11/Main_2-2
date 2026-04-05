"""order_panel_amend.py — AmendPanelMixin: 미체결조회, 정정/취소/빠른매도 로직 [S6]"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox


class AmendPanelMixin:
    """미체결 주문 조회·정정·취소·빠른매도 로직."""

    # ── 미체결 주문 조회 ──────────────────────────────────────
    def _fetch_open_orders(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        self._open_orders_buf = []
        ib = self.mw.ib

        def _on_open_order(orderId, contract, order, orderState):
            self._open_orders_buf.append({
                "oid":      orderId,
                "symbol":   getattr(contract,"localSymbol","") or getattr(contract,"symbol",""),
                "action":   getattr(order,"action",""),
                "price":    getattr(order,"lmtPrice", 0.0),
                "qty":      getattr(order,"totalQuantity", 0),
                "type":     getattr(order,"orderType",""),
                "tif":      getattr(order,"tif","DAY"),
                "contract": contract,
            })

        def _on_open_order_end():
            QTimer.singleShot(0, self._populate_open_order_tables)

        ib._orig_openOrder    = getattr(ib,'openOrder',    lambda *a: None)
        ib._orig_openOrderEnd = getattr(ib,'openOrderEnd', lambda: None)
        ib.openOrder    = _on_open_order
        ib.openOrderEnd = _on_open_order_end
        try:
            ib.reqOpenOrders()
            self._log("📋 미체결 주문 조회 요청...")
        except Exception as e:
            self._log(f"❌ 주문 조회 오류: {e}")
        QTimer.singleShot(2000, lambda: (
            setattr(ib,'openOrder',    ib._orig_openOrder),
            setattr(ib,'openOrderEnd', ib._orig_openOrderEnd)))

    def _populate_open_order_tables(self):
        from tab_options import _mk
        orders = getattr(self, '_open_orders_buf', [])
        # 정정/취소 테이블
        tbls = [t for t in [
            getattr(self,'tbl_open_orders_a', None),
            getattr(self,'tbl_open_orders_c', None),
            getattr(self,'tbl_open_orders_s', None),
        ] if t is not None]
        for tbl in tbls:
            tbl.setRowCount(0)
            for o in orders:
                r = tbl.rowCount(); tbl.insertRow(r)
                price_str = f"{o['price']:.2f}" if o['price'] else o['type']
                col = "#00ff88" if o['action'] == "BUY" else "#ff6666"
                tbl.setItem(r, 0, _mk(str(o['oid']),               "#ffd700"))
                tbl.setItem(r, 1, _mk(o['symbol'],                 "#ccc"))
                tbl.setItem(r, 2, _mk(f"{o['action']} {o['qty']}", col))
                tbl.setItem(r, 3, _mk(price_str,                   "#90caf9"))
        self._log(f"📋 미체결 주문 {len(orders)}건 수신")

    def _fill_amend_from_table(self, row: int):
        tbl = self.tbl_open_orders_a
        oid_item = tbl.item(row, 0); prc_item = tbl.item(row, 3); dir_item = tbl.item(row, 2)
        if oid_item: self.amend_oid.setText(oid_item.text())
        if prc_item:
            try: self.amend_price.setText(f"{float(prc_item.text()):.2f}")
            except ValueError: pass
        if dir_item:
            parts = dir_item.text().split()
            if len(parts) >= 2:
                try: self.amend_qty.setValue(int(parts[1]))
                except ValueError: pass

    def _fill_cancel_from_table(self, row: int):
        oid_item = self.tbl_open_orders_c.item(row, 0)
        if oid_item: self.cancel_oid.setText(oid_item.text())

    # ── 빠른매도 테이블 선택 ──────────────────────────────────
    def _fill_sell_from_table(self, row: int):
        """빠른매도 탭: 테이블 행 선택 시 내부 상태 저장."""
        tbl = getattr(self, 'tbl_open_orders_s', None)
        if tbl is None: return
        oid_item = tbl.item(row, 0)
        if oid_item:
            self._sell_selected_oid = int(oid_item.text())
            lbl = getattr(self, 'lbl_sell_status', None)
            if lbl: lbl.setText(f"✅ OID {self._sell_selected_oid} 선택됨 — 매도 버튼 누르세요")

    def _sell_selected_order(self):
        """빠른매도 탭: 선택된 미체결 매수 주문을 매도로 전환."""
        oid = getattr(self, '_sell_selected_oid', None)
        buf = getattr(self, '_open_orders_buf', [])
        lbl = getattr(self, 'lbl_sell_status', None)

        if oid is None:
            if lbl: lbl.setText("⚠ 테이블에서 주문 행을 먼저 선택하세요")
            return
        matched = next((o for o in buf if o["oid"] == oid), None)
        if matched is None:
            if lbl: lbl.setText(f"⚠ OID={oid} 계약 정보 없음 — 재조회 후 시도")
            return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            from ibapi.order import Order as IbOrder
            ibord = IbOrder()
            ibord.action        = "SELL"
            ibord.orderType     = "LMT"
            ibord.totalQuantity = matched["qty"]
            ibord.lmtPrice      = matched["price"]
            ibord.tif           = matched.get("tif","DAY")
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            self.mw.ib.placeOrder(oid, matched["contract"], ibord)
            msg = f"✅ 빠른매도 전송: OID={oid}  SELL {matched['qty']}  @{matched['price']:.2f}"
            if lbl: lbl.setText(msg)
            self._log(msg)
        except Exception as e:
            if lbl: lbl.setText(f"❌ 빠른매도 오류: {e}")

    def _bump_sell_price(self, delta: float):
        """빠른매도 탭: 선택 주문 가격에 delta 적용 후 매도 재전송."""
        oid = getattr(self, '_sell_selected_oid', None)
        buf = getattr(self, '_open_orders_buf', [])
        lbl = getattr(self, 'lbl_sell_status', None)
        if oid is None:
            if lbl: lbl.setText("⚠ 주문 행을 먼저 선택하세요"); return
        matched = next((o for o in buf if o["oid"] == oid), None)
        if matched is None:
            if lbl: lbl.setText(f"⚠ OID={oid} 없음 — 재조회 후 시도"); return
        new_price = round(matched["price"] + delta, 2)
        if new_price <= 0:
            if lbl: lbl.setText("⚠ 정정가가 0 이하"); return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            from ibapi.order import Order as IbOrder
            ibord = IbOrder()
            ibord.action        = "SELL"
            ibord.orderType     = "LMT"
            ibord.totalQuantity = matched["qty"]
            ibord.lmtPrice      = new_price
            ibord.tif           = matched.get("tif","DAY")
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            self.mw.ib.placeOrder(oid, matched["contract"], ibord)
            sign = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
            msg = f"✅ 매도 정정: OID={oid}  {matched['price']:.2f}→{new_price:.2f} ({sign})"
            matched["price"] = new_price  # 버퍼 갱신
            if lbl: lbl.setText(msg)
            self._log(msg)
        except Exception as e:
            if lbl: lbl.setText(f"❌ 매도 정정 오류: {e}")

    # ── 빠른 가격 정정 (신규 탭 bump 버튼) ──────────────────
    def _bump_price_and_amend(self, delta: float):
        price_edit = getattr(self, 'qord_price', None)
        try:
            cur_price = float(price_edit.text().strip())
            if cur_price <= 0: raise ValueError
        except (ValueError, TypeError):
            lbl = getattr(self, 'lbl_bump_status', None)
            if lbl: lbl.setText("⚠ 가격을 먼저 입력하세요"); return

        new_price = round(cur_price + delta, 2)
        if new_price <= 0:
            lbl = getattr(self, 'lbl_bump_status', None)
            if lbl: lbl.setText("⚠ 정정가가 0 이하"); return

        oid = None
        buf = getattr(self, '_open_orders_buf', [])
        if buf: oid = buf[-1]["oid"]
        if oid is None:
            amend_edit = getattr(self, 'amend_oid', None)
            try: oid = int(amend_edit.text().strip()) if amend_edit else None
            except (ValueError, TypeError): pass
        if oid is None:
            lbl = getattr(self, 'lbl_bump_status', None)
            if lbl: lbl.setText("⚠ 미체결 주문 조회 후 시도하세요"); return

        chk = getattr(self, 'chk_order_confirm', None)
        if chk and chk.isChecked():
            sign = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
            reply = QMessageBox.question(
                self, "빠른 정정 확인",
                f"OID={oid}  ${cur_price:.2f} → ${new_price:.2f}  ({sign})\n정정하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes: return

        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            matched = next((o for o in buf if o["oid"] == oid), None)
            if matched is None:
                lbl = getattr(self, 'lbl_bump_status', None)
                if lbl: lbl.setText(f"⚠ OID={oid} 없음 — 조회 먼저"); return
            from ibapi.order import Order as IbOrder
            ibord = IbOrder()
            ibord.action        = matched["action"]
            ibord.orderType     = "LMT"
            ibord.totalQuantity = matched["qty"]
            ibord.lmtPrice      = new_price
            ibord.tif           = matched.get("tif","DAY")
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            self.mw.ib.placeOrder(oid, matched["contract"], ibord)
            if price_edit: price_edit.setText(f"{new_price:.2f}")
            sign_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
            msg = f"✅ 정정: OID={oid}  ${cur_price:.2f}→${new_price:.2f} ({sign_str})"
            lbl = getattr(self, 'lbl_bump_status', None)
            if lbl: lbl.setText(msg)
            self._log(msg)
        except Exception as e:
            lbl = getattr(self, 'lbl_bump_status', None)
            if lbl: lbl.setText(f"❌ 정정 오류: {e}")
