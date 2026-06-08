"""
order_panel/sell_actions.py — 빠른매도·지정가매도·bump·잔고패널·+1호가 로직
════════════════════════════════════════════════════════════════════
[수정]
  _pos_sell_execute(): 화면 만기 → 보유 포지션 실제 만기 사용
                       _place_sell_lmt() 경로로 통일 (conId 주입 포함)
"""
from PyQt5.QtWidgets import QMessageBox
from .sell_place import SellPlaceMixin


class SellActionsMixin(SellPlaceMixin):
    """빠른매도·잔고패널·+1호가 로직. OrderPanelMixin에 mixin된다."""

    # ── 잔고 매도 패널 ───────────────────────────────────────
    def _show_pos_sell_panel(self, side, strike, qty=1, price=None):
        label = "CALL" if side == "C" else "PUT"
        self._ps_lbl_title.setText(f"▼ 잔고 청산 매도  [{label}]")
        self._ps_lbl_sym.setText(f"{label}  {strike}")
        self._ps_qty.setValue(max(1, qty))
        self._ps_price.setText(f"{price:.2f}" if price else "")
        self._ps_side   = side
        self._ps_strike = strike
        self._pos_sell_panel.setVisible(True)
        tab_w = getattr(self, '_qord_tab_widget', None)
        if tab_w:
            for i in range(tab_w.count()):
                if "매도" in tab_w.tabText(i):
                    tab_w.setCurrentIndex(i); break
        if getattr(self, 'sell_price', None) and price:
            self.sell_price.setText(f"{price:.2f}")
        if getattr(self, 'sell_qty', None):
            self.sell_qty.setValue(max(1, qty))
        lbl = getattr(self, 'lbl_sell_status', None)
        if lbl:
            lbl.setStyleSheet(
                "color:#ffa500;font-size:12px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            lbl.setText(f"선택: {label} {strike}  {qty}계약  — 가격 확인 후 매도")

    def _pos_sell_execute(self):
        """
        잔고 청산 매도 — 보유 포지션의 실제 만기/심볼 사용.
        _place_sell_lmt() 경로로 통일하여 conId 주입·error 핸들러 복원 포함.
        """
        side   = getattr(self, '_ps_side',   None)
        strike = getattr(self, '_ps_strike', None)
        if not side or not strike:
            self._log("⚠ 매도 대상 없음 — 잔고 테이블을 다시 클릭하세요.")
            return

        # ── 만기/심볼: 보유 포지션 기준 ──────────────────────
        expiry = getattr(self, '_ps_expiry', None)
        sym    = getattr(self, '_ps_sym',    None)
        if not expiry:
            expiry, _ = self._get_expiry()
        if not expiry:
            self._log("⚠ 만기 정보 없음 — 잔고 테이블을 다시 클릭하세요.")
            return
        if not sym:
            sym = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""

        # Monthly 만기는 SPX 티커로
        try:
            from call_put_tab.core_expiry_utils import _is_monthly_expiry
            if _is_monthly_expiry(expiry):
                sym = "SPX"
        except Exception:
            pass

        qty       = self._ps_qty.value()
        price_txt = self._ps_price.text().strip()
        is_lmt    = bool(price_txt)
        try:
            price = float(price_txt) if is_lmt else 0.0
        except ValueError:
            self._log("⚠ 가격 형식 오류")
            return

        if not is_lmt:
            self._log("⚠ 가격을 입력하세요 (시장가 미지원)")
            lbl = getattr(self, 'lbl_sell_status', None)
            if lbl: lbl.setText("⚠ 매도 가격을 입력하세요")
            return

        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
            return

        label      = "CALL" if side == "C" else "PUT"
        msg        = f"매도 LMT  {sym} {label} {strike}  {qty}계약  ${price:.2f}"
        lbl        = getattr(self, 'lbl_sell_status', None)

        # _place_sell_lmt()로 통일 → conId 주입 + error 핸들러 복원 포함
        self._place_sell_lmt(side, strike, sym, qty, price, lbl, msg)
        self._pos_sell_panel.setVisible(False)

    # ── +1호가 매수 ──────────────────────────────────────────
    def _plus1tick_buy(self):
        if not self.mw.connected:
            self._log("⚠ +1호가: 미연결"); return
        orders     = getattr(self, '_open_orders_buf', [])
        buy_orders = [o for o in orders if o.get('action') == 'BUY' and o.get('price', 0) > 0]
        if not buy_orders:
            self._log("⚠ +1호가: 미체결 BUY 없음 (먼저 [미체결 조회] 클릭)"); return
        target    = max(buy_orders, key=lambda o: o['oid'])
        new_price = round(target['price'] + 0.05, 2)
        self._log(f"+1호가: OID={target['oid']}  {target['price']:.2f} → {new_price:.2f}")
        try:
            from ibapi.order import Order as IBOrder
            order = IBOrder()
            order.action        = "BUY";  order.orderType     = "LMT"
            order.totalQuantity = target['qty']; order.lmtPrice = new_price
            order.tif           = target.get('tif', 'DAY')
            order.eTradeOnly    = False; order.firmQuoteOnly = False
            self.mw.ib.placeOrder(target['oid'], target['contract'], order)
            self._log(f"✅ +1호가 정정 전송: {new_price:.2f}")
            if hasattr(self, 'lbl_amend_status'):
                self.lbl_amend_status.setText(f"+1호가 정정 → {new_price:.2f}")
        except Exception as e:
            self._log(f"❌ +1호가 정정 오류: {e}")

    # ── 빠른매도: Bid LMT ────────────────────────────────────
    def _sell_selected_order(self):
        side       = getattr(self, '_ps_side',   None)
        strike_txt = getattr(self, '_ps_strike', None)
        lbl        = getattr(self, 'lbl_sell_status', None)
        sell_qty_w = getattr(self, 'sell_qty',   None)
        self._log(f"📤 빠른매도: _ps_side={side} _ps_strike={strike_txt}")
        if not side or not strike_txt:
            if lbl: lbl.setText("⚠ 잔고 행을 먼저 클릭하세요"); return
        if not sell_qty_w:
            msg = "❌ 수량 위젯 초기화 안 됨 — 탭을 닫았다 다시 여세요"
            if lbl: lbl.setText(msg)
            self._log("❌ 빠른매도 중단: sell_qty 위젯 없음"); return
        qty = sell_qty_w.value()
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        bid_price = getattr(self, '_pp_opt_bid', None)
        if bid_price and bid_price > 0:
            price = round(float(bid_price), 2); price_src = f"Bid ${price:.2f}"
        else:
            sell_price_w = getattr(self, 'sell_price', None)
            price_txt    = sell_price_w.text().strip() if sell_price_w else ""
            if price_txt:
                try:
                    price = round(float(price_txt), 2)
                    if price <= 0: raise ValueError
                    price_src = f"입력가 ${price:.2f}"
                except ValueError:
                    if lbl: lbl.setText("⚠ 유효한 가격을 입력하거나 체인을 클릭하세요"); return
            else:
                if lbl: lbl.setText("⚠ Bid 가격 없음 — 체인 행 클릭 or 가격 직접 입력")
                self._log("⚠ 빠른매도: _pp_opt_bid 없고 sell_price 비어있음"); return
        sym = getattr(self, '_ps_sym', None) or (
              self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "")
        msg = f"매도 LMT  {sym} {'CALL' if side=='C' else 'PUT'} {strike_txt}  {qty}계약  {price_src}"
        self._place_sell_lmt(side, strike_txt, sym, qty, price, lbl, msg)

    # ── 빠른매도: 지정가 ─────────────────────────────────────
    def _sell_limit_order(self):
        side         = getattr(self, '_ps_side',   None)
        strike_txt   = getattr(self, '_ps_strike', None)
        lbl          = getattr(self, 'lbl_sell_status', None)
        sell_price_w = getattr(self, 'sell_price', None)
        sell_qty_w   = getattr(self, 'sell_qty',   None)
        self._log(f"📤 지정가매도: _ps_side={side} _ps_strike={strike_txt}")
        if not side or not strike_txt:
            if lbl: lbl.setText("⚠ 잔고 행을 먼저 클릭하세요"); return
        price_txt = sell_price_w.text().strip() if sell_price_w else ""
        if not sell_qty_w:
            if lbl: lbl.setText("❌ 수량 위젯 초기화 안 됨 — 탭을 닫았다 다시 여세요")
            self._log("❌ 지정가매도 중단: sell_qty 위젯 없음"); return
        qty = sell_qty_w.value()
        if not price_txt:
            if lbl: lbl.setText("⚠ 매도 가격을 입력하세요"); return
        try:
            price = float(price_txt)
            if price <= 0: raise ValueError
        except ValueError:
            if lbl: lbl.setText("⚠ 유효한 가격을 입력하세요"); return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        sym = getattr(self, '_ps_sym', None) or (
              self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "")
        msg = f"매도 LMT  {sym} {'CALL' if side=='C' else 'PUT'} {strike_txt}  {qty}계약  ${price:.2f}"
        self._place_sell_lmt(side, strike_txt, sym, qty, price, lbl, msg)

    # ── 전체 미체결 bump ─────────────────────────────────────
    def _bump_sell_price(self, delta: float):
        buf = getattr(self, '_open_orders_buf', [])
        lbl = getattr(self, 'lbl_sell_status', None)
        if not buf:
            if lbl: lbl.setText("⚠ 미체결 주문 없음 — 먼저 조회하세요"); return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        sign_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
        success, fail = 0, 0
        for o in buf:
            new_price = round(o["price"] + delta, 2)
            if new_price <= 0: fail += 1; continue
            try:
                from ibapi.order import Order as IbOrder
                ibord = IbOrder()
                ibord.action        = "SELL"; ibord.orderType = "LMT"
                ibord.totalQuantity = o["qty"]; ibord.lmtPrice = new_price
                ibord.tif           = o.get("tif", "DAY")
                ibord.eTradeOnly    = False; ibord.firmQuoteOnly = False
                self.mw.ib.placeOrder(o["oid"], o["contract"], ibord)
                o["price"] = new_price
                if o["oid"] == getattr(self, '_sell_selected_oid', None):
                    if getattr(self, 'sell_price', None):
                        self.sell_price.setText(f"{new_price:.2f}")
                success += 1
            except Exception as e:
                self._log(f"❌ OID={o['oid']} bump 오류: {e}"); fail += 1
        msg = f"✅ 전체 bump({sign_str}): {success}건 성공"
        if fail: msg += f" / {fail}건 실패"
        if lbl: lbl.setText(msg)
        self._log(msg)
