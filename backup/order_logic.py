"""
order_logic.py — 주문 실행 로직  v6.4
════════════════════════════════════════════════════════
수정 대상: 주문 전송 동작, TIF, 확인 팝업
포함 메서드:
  _amend_order()   정정 전송
  _cancel_order()  취소 전송
  _qord_fill()     주문창 자동 입력
  _qord_place()    신규 주문 전송
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QMessageBox

from core import make_opt_contract


class OrderLogicMixin:
    """주문 실행 로직. CallPutGrid에 mixin된다."""

    def _amend_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            oid   = int(self.amend_oid.text().strip())
            price = float(self.amend_price.text().strip())
            qty   = self.amend_qty.value()
        except ValueError:
            QMessageBox.warning(self, "입력 오류",
                "주문ID와 새 가격을 올바르게 입력하세요."); return
        try:
            from ibapi.order import Order as IbOrder

            # ✅ 미체결 버퍼에서 OID에 해당하는 contract 조회
            buf = getattr(self, '_open_orders_buf', [])
            matched = next((o for o in buf if o["oid"] == oid), None)
            if matched is None or matched.get("contract") is None:
                QMessageBox.warning(self, "정정 오류",
                    f"OID={oid} 의 contract 정보를 찾을 수 없습니다.\n"
                    "'미체결 주문 조회'를 먼저 클릭하세요.")
                return
            contract = matched["contract"]

            ibord = IbOrder()
            ibord.action        = matched["action"]   # ✅ ERR 321 fix — BUY/SELL 반드시 설정
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = matched.get("tif", "DAY")   # 원래 TIF 유지, 없으면 DAY
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            self.mw.ib.placeOrder(oid, contract, ibord)
            self.lbl_amend_status.setStyleSheet(
                "color:#90caf9;font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_amend_status.setText(
                f"전송: OID={oid} @ ${price:.2f} ×{qty}")
            self._log(f"✏ 정정: OID={oid}  새가격=${price:.2f}  수량={qty}")
        except Exception as e:
            self.lbl_amend_status.setText(f"오류: {e}")
            self._log(f"❌ 정정 오류: {e}")

    def _cancel_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            oid = int(self.cancel_oid.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "주문ID를 입력하세요."); return
        ret = QMessageBox.question(self, "취소 확인",
            f"주문 OID={oid} 를 취소하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        try:
            self.mw.ib.cancelOrder(oid)
            self.lbl_cancel_status.setStyleSheet(
                "color:#ff6666;font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_cancel_status.setText(f"취소 전송: OID={oid}")
            self._log(f"✕ 취소: OID={oid}")
        except Exception as e:
            self.lbl_cancel_status.setText(f"오류: {e}")
            self._log(f"❌ 취소 오류: {e}")

    def _qord_fill(self, side: str, strike: str,
                   price: float = None, source: str = ""):
        self.qord_side.setText(side)
        self.qord_strike.setText(strike)
        if price is not None:
            self.qord_price.setText(f"{price:.2f}")
        self.lbl_qord_src.setText(source)

    def _qord_place(self, action: str):
        side      = self.qord_side.text().strip()
        strike    = self.qord_strike.text().strip()
        qty       = self.qord_qty.value()
        is_lmt    = self.qord_lmt.isChecked()
        price_txt = self.qord_price.text().strip()
        tif       = self.qord_tif.currentText()
        sym       = self.edit_sym.text().strip().upper() if hasattr(self,'edit_sym') else ""

        # ── 주식/지수 vs 옵션 자동 판별 ──────────────────────
        # 현재가 패널이 옵션 모드이거나, side가 C/P이면 옵션 주문
        pp_mode   = getattr(self, '_pp_mode', 'und')
        is_option = (side in ("C","P")) and bool(strike)
        is_stock  = not is_option

        if is_stock:
            # 주식/ETF/지수 현물 주문 (side/strike 없어도 됨)
            if not sym:

                QMessageBox.warning(self,"입력 오류","종목이 선택되지 않았습니다.")
                return
        else:
            if is_lmt and not price_txt:

                QMessageBox.warning(self,"입력 오류","지정가를 입력하세요.")
                return

        order_type = "LMT" if is_lmt else "MKT"
        try:
            price = float(price_txt) if is_lmt and price_txt else 0.0
        except ValueError:

            QMessageBox.warning(self,"입력 오류","유효한 가격을 입력하세요.")
            return

        action_kr  = "매수" if action == "BUY" else "매도"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"

        if is_option:
            label = "CALL" if side=="C" else "PUT"
            msg = (f"{action_kr} {order_type}  "
                   f"{sym} {label} {strike}  {qty}계약  {price_disp}  {tif}")
        else:
            msg = (f"{action_kr} {order_type}  "
                   f"{sym}  {qty}주  {price_disp}  {tif}")

        # chk_order_confirm OFF 시 _skip_order_confirm=True → 팝업 건너뜀
        skip_confirm = getattr(self, '_skip_order_confirm', False)
        if not skip_confirm:
            ret = QMessageBox.question(self, f"주문 확인 — {action_kr}",
                f"⚠ 아래 주문을 전송합니다.\n\n{msg}\n\n계속하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes: return
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 먼저 연결하세요.")
            return

        try:
            from ibapi.order import Order as IbOrder
            from ibapi.contract import Contract

            ibord = IbOrder()
            ibord.action        = action
            ibord.orderType     = order_type
            ibord.totalQuantity = qty
            ibord.tif           = tif
            ibord.eTradeOnly    = False   # ✅ ERR 10268 fix
            ibord.firmQuoteOnly = False   # ✅ ERR 10268 fix
            if is_lmt and price: ibord.lmtPrice = price

            if is_option:
                # 옵션 계약
                expiry, tag = self._get_expiry()   # ✅ CUSTOM 포함 실제 날짜 반환
                if expiry is None: return           # 만기일 오류 시 중단
                contract = make_opt_contract(sym, float(strike), side, expiry, tag)
            else:
                # 주식/ETF 계약
                from core import INDEX_SYM
                contract = Contract()
                contract.symbol   = sym
                contract.currency = "USD"
                contract.exchange = "SMART"
                if sym in INDEX_SYM:
                    # 지수는 현물 거래 불가 — CFD or 선물로 안내
                    QMessageBox.warning(self,"주문 불가",
                        f"{sym}은 지수로 직접 거래할 수 없습니다.\n"
                        "ETF(SPY/QQQ 등)나 선물(ES/NQ)로 주문하세요.")
                    return
                contract.secType  = "STK"

            oid = self.mw.ib.get_next_id()
            if oid is None:
                QMessageBox.warning(self,"주문 오류","주문 ID를 가져올 수 없습니다.")
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

    # ─────────────────────────────────────────────────────────
    # 수량 자동 계산 버튼
    # ─────────────────────────────────────────────────────────
    def _get_current_price_for_qty(self):
        """현재 주문창 가격 반환. 없으면 테이블 선택 종목 Last 가격."""
        try:
            p = float(self.qord_price.text().strip())
            if p > 0: return p
        except: pass
        side = self.qord_side.text().strip()
        strike_txt = self.qord_strike.text().strip()
        if side and strike_txt:
            try:
                tbl = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                target = float(strike_txt)
                row = min(range(len(strikes)), key=lambda i: abs(strikes[i]-target))
                item = tbl.item(row, 1)
                if item: return float(item.text())
            except: pass
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
                except: pass

        def _on_summary_end(reqId):
            pass

        self.mw.ib.accountSummary    = _on_summary
        self.mw.ib.accountSummaryEnd = _on_summary_end
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
            contract_cost = price * 100   # 옵션 1계약 = premium × 100주
            qty = max(1, int(av_funds[0] / contract_cost))
            self.qord_qty.setValue(qty)
            self._log(f"💰 MAX 수량: 잔고 ${av_funds[0]:,.0f} ÷ 계약비용 ${contract_cost:.0f} → {qty}계약")
        QTimer.singleShot(1500, _apply)

    def _calc_qty_200(self):
        """$200 기준 수량 계산 → qord_qty 자동 입력."""
        price = self._get_current_price_for_qty()
        if not price or price <= 0:
            self._log("❌ $200 수량: 가격을 먼저 입력하세요."); return
        budget = 200.0
        contract_cost = price * 100
        qty = max(1, int(budget / contract_cost))
        self.qord_qty.setValue(qty)
        self._log(f"💵 $200 수량: ${budget:.0f} ÷ 계약비용 ${contract_cost:.0f} → {qty}계약")