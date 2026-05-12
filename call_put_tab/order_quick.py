"""
order_quick.py — 빠른주문(qord) 및 수량 계산 로직 v6.6
════════════════════════════════════════════════════════
포함 내용:
  - OrderQuickMixin
      _qord_fill()                주문창 자동 입력
      _qord_place()               신규 주문 전송 (옵션·주식 자동 판별)
      _get_current_price_for_qty() 현재가 반환 헬퍼
      _calc_qty_max()             잔고 기준 최대 수량 계산
      _calc_qty_200()             $200 기준 수량 계산
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QMessageBox

from core import make_opt_contract


class OrderQuickMixin:
    """빠른주문 및 수량 계산 로직. CallPutGrid에 mixin된다."""

    def _qord_fill(self, side: str, strike: str,
                   price: float = None, source: str = ""):
        """주문창 필드 자동 입력."""
        self.qord_side.setText(side)
        self.qord_strike.setText(strike)
        if price is not None:
            self.qord_price.setText(f"{price:.2f}")
        self.lbl_qord_src.setText(source)

    def _qord_place(self, action: str):
        """신규 주문 전송. 옵션(C/P+행사가) vs 주식(현물) 자동 판별."""
        side      = self.qord_side.text().strip()
        strike    = self.qord_strike.text().strip()
        qty       = self.qord_qty.value()
        is_lmt    = self.qord_lmt.isChecked()
        price_txt = self.qord_price.text().strip()
        tif       = self.qord_tif.currentText()
        sym       = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""

        is_option = (side in ("C", "P")) and bool(strike)
        is_stock  = not is_option

        if is_stock:
            if not sym:
                QMessageBox.warning(self, "입력 오류", "종목이 선택되지 않았습니다.")
                return
        else:
            if is_lmt and not price_txt:
                QMessageBox.warning(self, "입력 오류", "지정가를 입력하세요.")
                return

        order_type = "LMT" if is_lmt else "MKT"
        try:
            price = float(price_txt) if is_lmt and price_txt else 0.0
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "유효한 가격을 입력하세요.")
            return

        action_kr  = "매수" if action == "BUY" else "매도"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"

        if is_option:
            label = "CALL" if side == "C" else "PUT"
            msg   = (f"{action_kr} {order_type}  "
                     f"{sym} {label} {strike}  {qty}계약  {price_disp}  {tif}")
        else:
            msg = (f"{action_kr} {order_type}  "
                   f"{sym}  {qty}주  {price_disp}  {tif}")

        skip_confirm = getattr(self, '_skip_order_confirm', False)
        if not skip_confirm:
            dlg = QMessageBox(self)
            dlg.setWindowTitle(f"주문 확인 — {action_kr}")
            dlg.setText(f"⚠ 아래 주문을 전송합니다.\n\n{msg}\n\n계속하시겠습니까?")
            dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            dlg.setDefaultButton(QMessageBox.Yes)
            yes_btn = dlg.button(QMessageBox.Yes)
            if yes_btn:
                yes_btn.setStyleSheet(
                    "QPushButton{background:#1a5c2e;color:#00ff88;"
                    "font-weight:bold;padding:4px 16px;border-radius:4px;"
                    "border:1px solid #00ff88;}"
                    "QPushButton:hover{background:#2a7c3e;}")
            if dlg.exec_() != QMessageBox.Yes:
                return

        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
            return

        try:
            from ibapi.order import Order as IbOrder
            from ibapi.contract import Contract

            ibord = IbOrder()
            ibord.action        = action
            ibord.orderType     = order_type
            ibord.totalQuantity = qty
            ibord.tif           = tif
            ibord.eTradeOnly    = False   # ERR 10268 fix
            ibord.firmQuoteOnly = False   # ERR 10268 fix
            if is_lmt and price:
                ibord.lmtPrice = price

            if is_option:
                expiry, tag = self._get_expiry()
                if expiry is None: return
                contract = make_opt_contract(sym, float(strike), side, expiry, tag)
            else:
                from core import INDEX_SYM
                contract = Contract()
                contract.symbol   = sym
                contract.currency = "USD"
                contract.exchange = "SMART"
                if sym in INDEX_SYM:
                    QMessageBox.warning(self, "주문 불가",
                        f"{sym}은 지수로 직접 거래할 수 없습니다.\n"
                        "ETF(SPY/QQQ 등)나 선물(ES/NQ)로 주문하세요.")
                    return
                contract.secType = "STK"

            oid = self.mw.ib.get_next_id()
            if oid is None:
                QMessageBox.warning(self, "주문 오류", "주문 ID를 가져올 수 없습니다.")
                return
            self.mw.ib.placeOrder(oid, contract, ibord)

            col = "#00ff88" if action == "BUY" else "#ff6666"
            self.lbl_qord_status.setStyleSheet(
                f"color:{col};font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_qord_status.setText(f"전송: {msg}")
            self._log(f"📤 빠른주문: {msg}  (OID={oid})")
        except Exception as e:
            self.lbl_qord_status.setText(f"오류: {e}")
            self._log(f"❌ 주문 오류: {e}")

    def _get_current_price_for_qty(self):
        """현재 주문창 가격 반환. 없으면 테이블 선택 종목 Last 가격."""
        try:
            p = float(self.qord_price.text().strip())
            if p > 0: return p
        except Exception:
            pass
        side       = self.qord_side.text().strip()
        strike_txt = self.qord_strike.text().strip()
        if side and strike_txt:
            try:
                tbl     = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                target  = float(strike_txt)
                row     = min(range(len(strikes)), key=lambda i: abs(strikes[i] - target))
                item    = tbl.item(row, 1)
                if item: return float(item.text())
            except Exception:
                pass
        return None

    def _calc_qty_max(self):
        """잔고 기준 최대 수량 계산 → qord_qty 자동 입력."""
        if not self.mw.connected:
            self._log("❌ MAX 수량: TWS 연결 필요"); return
        price = self._get_current_price_for_qty()
        if not price or price <= 0:
            self._log("❌ MAX 수량: 가격을 먼저 입력하세요."); return

        av_funds = [None]
        orig_as  = getattr(self.mw.ib, 'accountSummary',    lambda *a: None)
        orig_ase = getattr(self.mw.ib, 'accountSummaryEnd', lambda *a: None)

        def _on_summary(reqId, account, tag, value, currency):
            if tag == "AvailableFunds":
                try: av_funds[0] = float(value)
                except Exception: pass

        self.mw.ib.accountSummary    = _on_summary
        self.mw.ib.accountSummaryEnd = lambda *a: None
        try:
            self.mw.ib.reqAccountSummary(9900, "All", "AvailableFunds")
        except Exception as e:
            self._log(f"❌ 잔고 조회 오류: {e}"); return

        from PyQt5.QtCore import QTimer

        def _apply():
            self.mw.ib.accountSummary    = orig_as
            self.mw.ib.accountSummaryEnd = orig_ase
            if av_funds[0] is None:
                self._log("❌ MAX 수량: 잔고 수신 실패 (재시도)"); return
            contract_cost = price * 100
            qty = max(1, int(av_funds[0] / contract_cost))
            self.qord_qty.setValue(qty)
            self._log(
                f"💰 MAX 수량: 잔고 ${av_funds[0]:,.0f} ÷ "
                f"계약비용 ${contract_cost:.0f} → {qty}계약")

        QTimer.singleShot(1500, _apply)

    def _calc_qty_200(self):
        """$200 기준 수량 계산 → qord_qty 자동 입력."""
        price = self._get_current_price_for_qty()
        if not price or price <= 0:
            self._log("❌ $200 수량: 가격을 먼저 입력하세요."); return
        budget        = 200.0
        contract_cost = price * 100
        qty           = max(1, int(budget / contract_cost))
        self.qord_qty.setValue(qty)
        self._log(
            f"💵 $200 수량: ${budget:.0f} ÷ "
            f"계약비용 ${contract_cost:.0f} → {qty}계약")
