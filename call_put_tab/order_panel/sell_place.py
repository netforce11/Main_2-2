"""
order_panel/sell_place.py — LMT SELL 공통 주문 전송 헬퍼
════════════════════════════════════════════════════════
포함:
  SellPlaceMixin
    _place_sell_lmt()  contract 생성 → placeOrder → 상태 라벨 갱신
"""

from PyQt5.QtCore import QTimer

from order_panel.helpers import _spx_tag


class SellPlaceMixin:
    """LMT SELL 공통 주문 전송 로직. SellActionsMixin에 mixin된다."""

    def _place_sell_lmt(self, side, strike_txt, sym, qty, price, lbl, msg):
        """공통 LMT SELL 주문 전송."""
        try:
            from ibapi.order import Order as IbOrder
            from core import make_opt_contract
            expiry = getattr(self, '_ps_expiry', None)
            if not expiry:
                expiry, tag = self._get_expiry()
                if expiry is None:
                    if lbl: lbl.setText("❌ 만기일을 확인할 수 없습니다")
                    return
            else:
                tag = _spx_tag(sym, expiry)

            contract        = make_opt_contract(sym, float(strike_txt), side, expiry, tag)
            ibord           = IbOrder()
            ibord.action    = "SELL"; ibord.orderType     = "LMT"
            ibord.totalQuantity = qty; ibord.lmtPrice     = price
            ibord.tif       = "DAY";  ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            oid = self.mw.ib.get_next_id()
            if oid is None:
                if lbl: lbl.setText("❌ 주문 ID 없음"); return

            _orig_err = getattr(self.mw.ib, 'error', None)
            def _catch_err(reqId, errorCode, errorString, *a):
                self._log(
                    f"‼ IB ERROR  reqId={reqId}  code={errorCode}  msg={errorString}")
                if _orig_err:
                    try: _orig_err(reqId, errorCode, errorString, *a)
                    except Exception: pass
            self.mw.ib.error = _catch_err

            self.mw.ib.placeOrder(oid, contract, ibord)
            result_msg = f"✅ 빠른매도: {msg}  (OID={oid})"
            if lbl:
                lbl.setStyleSheet(
                    "color:#ff6666;font-size:11px;"
                    "border:1px solid #333;border-radius:3px;padding:2px;")
                lbl.setText(result_msg)
            self._log(f"📤 {result_msg}")
            QTimer.singleShot(1500, self._fetch_open_orders)
        except Exception as e:
            if lbl: lbl.setText(f"❌ 오류: {e}")
            self._log(f"❌ 빠른매도 오류: {e}")
