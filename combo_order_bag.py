"""
combo_order_bag.py — BAG(Combo) 주문 전송 로직
──────────────────────────────────────────────
포함:
  _place_combo_legs      — BAG 주문 진입점
  _place_bag_with_conids — conId 조회 → placeOrder
──────────────────────────────────────────────
"""

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer
from combo_order_chaser import register_chaser


def _place_combo_legs(self, legs: list, strat: str):
    """BAG(Combo) 계약 주문 진입점."""
    try:
        from core_contract import make_opt_contract
        from ibapi.contract import Contract, ComboLeg
    except ImportError as e:
        return QMessageBox.critical(self, "오류", f"모듈 import 실패: {e}")

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = (sym_w.text().strip().upper() if sym_w else "SPX")

    bag = Contract()
    bag.symbol  = symbol.replace("SPXW", "SPX")
    bag.secType = "BAG"; bag.currency = "USD"; bag.exchange = "SMART"

    combo_legs = []
    for leg in legs:
        opt_contract = make_opt_contract(
            symbol=symbol, strike=leg["strike"],
            right=leg["cp"], expiry=leg["expiry"])
        cl = ComboLeg()
        cl.conId = 0; cl.ratio = int(leg["qty"])
        cl.action = leg["dir"]; cl.exchange = "SMART"
        combo_legs.append((cl, opt_contract))

    _place_bag_with_conids(self, bag, combo_legs, legs, strat)


def _place_bag_with_conids(self, bag, combo_legs, legs, strat):
    """conId 조회 완료 후 BAG placeOrder 전송."""
    from ibapi.order import Order as IbOrder

    ib       = self.mw.ib
    total    = len(combo_legs)
    resolved = {}
    base_rid = 9910

    def _on_cd(reqId, contractDetails):
        idx = reqId - base_rid
        if 0 <= idx < total:
            resolved[idx] = contractDetails.contract.conId

    def _on_cd_end(reqId):
        idx = reqId - base_rid
        if idx not in resolved:
            resolved[idx] = 0
        if len(resolved) >= total:
            QTimer.singleShot(0, _send_bag)

    ib._orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
    ib._orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)
    ib.contractDetails    = _on_cd
    ib.contractDetailsEnd = _on_cd_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        try:
            ib.reqContractDetails(base_rid + i, opt_contract)
            self._log(f"🔍 conId 조회: 레그{i+1} "
                      f"{opt_contract.right} {int(opt_contract.strike)}")
        except Exception as e:
            self._log(f"❌ reqContractDetails 레그{i+1}: {e}")
            resolved[i] = 0

    def _on_timeout():
        for i in range(total):
            if i not in resolved:
                resolved[i] = 0
        _send_bag()
    QTimer.singleShot(10000, _on_timeout)

    def _send_bag():
        # ── 콜백 복구 ──────────────────────────────────────────
        try:
            ib.contractDetails    = ib._orig_cd
            ib.contractDetailsEnd = ib._orig_cd_end
        except Exception:
            pass

        for i, (cl, _) in enumerate(combo_legs):
            cl.conId = resolved.get(i, 0)
            self._log(f"  레그{i+1} conId={cl.conId}  "
                      f"{legs[i]['dir']} {legs[i]['cp']} {int(legs[i]['strike'])}")
        bag.comboLegs = [cl for cl, _ in combo_legs]

        # ── lmtPrice 계산 ──────────────────────────────────────
        # combo_ui_leg_panel._recalc_net_price() 로 통일
        # (행사가 클릭 시 Mid-price 자동 조회 → 이미 프리미엄 셀에 반영됨)
        try:
            from combo_ui_leg_panel import _recalc_net_price
            lmt_price = _recalc_net_price(self) or 0.0
        except Exception:
            lmt_price = 0.0

        if lmt_price == 0.0:
            # 폴백: 테이블 직접 합산 (프리미엄 미조회 시 대비)
            buy_total  = sum(float(lg.get("prem", 0) or 0) * int(lg.get("qty", 1))
                             for lg in legs if lg["dir"] == "BUY")
            sell_total = sum(float(lg.get("prem", 0) or 0) * int(lg.get("qty", 1))
                             for lg in legs if lg["dir"] == "SELL")
            net        = round(buy_total - sell_total, 2)
            lmt_price  = round(abs(net), 2)
        else:
            buy_total  = sum(float(lg.get("prem", 0) or 0) * int(lg.get("qty", 1))
                             for lg in legs if lg["dir"] == "BUY")
            sell_total = sum(float(lg.get("prem", 0) or 0) * int(lg.get("qty", 1))
                             for lg in legs if lg["dir"] == "SELL")
            net        = round(buy_total - sell_total, 2)

        bag_action = "BUY" if net >= 0 else "SELL"
        type_str   = f"{'데빗' if net >= 0 else '크레딧'} ${lmt_price:.2f}"

        oid = ib.get_next_id()
        if oid is None:
            return self._log("❌ nextOrderId 없음")

        ibord = IbOrder()
        ibord.action        = bag_action; ibord.orderType = "LMT"
        ibord.totalQuantity = 1;          ibord.lmtPrice  = lmt_price
        ibord.tif           = "DAY";      ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False;       ibord.transmit      = True

        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(f"⚡ BAG 주문 전송: OID={oid}  {type_str}  레그{total}개")
            self._log(f"   BUY합계=${buy_total:.2f}  SELL합계=${sell_total:.2f}  net=${net:+.2f}")

            # ── Chaser 등록 ────────────────────────────────────
            self._chaser_bag_contract = bag
            register_chaser(self, oid=oid, price=lmt_price, action=bag_action)

            panel = getattr(self, 'synthetic_panel', None)
            if panel:
                panel.add_position({
                    "strategy": strat, "qty": 1,
                    "entry": lmt_price, "current": lmt_price,
                    "side": bag_action,
                })
        except Exception as e:
            self._log(f"❌ BAG 주문 오류: {e}")
