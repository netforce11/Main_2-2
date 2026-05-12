"""
order_amend_cancel.py — 정정·취소 주문 로직 v6.6
════════════════════════════════════════════════════════
포함 내용:
  - OrderAmendCancelMixin
      _amend_order()    정정 주문 전송 (Contract 소실 방어 포함)
      _cancel_order()   취소 주문 전송
════════════════════════════════════════════════════════
[v6.6 수정]
  ② 정정 주문 Contract 소실 방지:
     - 재시작 후 _open_orders_buf 비어있으면 자동 조회 후 5초 뒤 재시도
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox


class OrderAmendCancelMixin:
    """정정·취소 주문 로직. CallPutGrid에 mixin된다."""

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

            buf     = getattr(self, '_open_orders_buf', [])
            matched = next((o for o in buf if o["oid"] == oid), None)

            # [v6.6 ②] Contract 소실 방지: 버퍼 비어있으면 자동 조회 후 재시도
            if matched is None or matched.get("contract") is None:
                if not buf:
                    self._log("⚠ 정정: _open_orders_buf 비어있음 → 미체결 자동 조회 후 재시도")
                    if hasattr(self, '_fetch_open_orders'):
                        self._fetch_open_orders()
                    QTimer.singleShot(5000, self._amend_order)
                    self.lbl_amend_status.setText("⏳ 미체결 조회 중… 5초 후 재시도")
                    self.lbl_amend_status.setStyleSheet(
                        "color:#ffbb00;font-size:11px;"
                        "border:1px solid #333;border-radius:3px;padding:2px;")
                else:
                    QMessageBox.warning(self, "정정 오류",
                        f"OID={oid} 의 contract 정보를 찾을 수 없습니다.\n"
                        "'미체결 주문 조회'를 먼저 클릭하세요.")
                return

            contract = matched["contract"]

            ibord = IbOrder()
            ibord.action        = matched["action"]   # ERR 321 fix
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = matched.get("tif", "DAY")
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
        ret = QMessageBox.question(
            self, "취소 확인",
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
