"""
order_amend_cancel.py — 정정·취소 주문 로직 v6.7
════════════════════════════════════════════════════════
[v6.7 추가]
  _cancel_all_orders(): 조회된 미체결 목록 전체 루프 취소
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
            if matched is None or matched.get("contract") is None:
                if not buf:
                    retry = getattr(self, '_amend_retry_count', 0)
                    if retry >= 3:
                        self._amend_retry_count = 0
                        self.lbl_amend_status.setStyleSheet(
                            "color:#ff6666;font-size:11px;"
                            "border:1px solid #333;border-radius:3px;padding:2px;")
                        self.lbl_amend_status.setText(
                            "❌ 미체결 주문 조회 실패 — 수동으로 [미체결 조회] 클릭")
                        self._log("❌ 정정 재시도 3회 초과")
                        QMessageBox.warning(self, "정정 실패",
                            f"OID={oid} 의 미체결 주문을 자동으로 찾지 못했습니다.\n"
                            "'미체결 주문 조회' 버튼을 먼저 클릭하세요.")
                        return
                    self._amend_retry_count = retry + 1
                    self._log(
                        f"⚠ 정정: 버퍼 비어있음 → 자동 조회 후 재시도 "
                        f"({self._amend_retry_count}/3)")
                    if hasattr(self, '_fetch_open_orders'):
                        self._fetch_open_orders()
                    QTimer.singleShot(5000, self._amend_order)
                    self.lbl_amend_status.setText(
                        f"⏳ 미체결 조회 중… 5초 후 재시도 ({self._amend_retry_count}/3)")
                    self.lbl_amend_status.setStyleSheet(
                        "color:#ffbb00;font-size:11px;"
                        "border:1px solid #333;border-radius:3px;padding:2px;")
                else:
                    self._amend_retry_count = 0
                    QMessageBox.warning(self, "정정 오류",
                        f"OID={oid} 의 contract 정보를 찾을 수 없습니다.\n"
                        "'미체결 주문 조회'를 먼저 클릭하세요.")
                return
            contract = matched["contract"]
            ibord = IbOrder()
            ibord.action        = matched["action"]
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = matched.get("tif", "DAY")
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            self.mw.ib.placeOrder(oid, contract, ibord)
            self._amend_retry_count = 0
            self.lbl_amend_status.setStyleSheet(
                "color:#90caf9;font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_amend_status.setText(f"전송: OID={oid} @ ${price:.2f} ×{qty}")
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

    def _cancel_all_orders(self):
        """조회된 미체결 목록 전체를 루프로 취소."""
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        buf = getattr(self, '_open_orders_buf', [])
        if not buf:
            QMessageBox.warning(self, "미체결 없음",
                "미체결 주문이 없습니다.\n먼저 [미체결 조회] 버튼을 클릭하세요.")
            return
        ret = QMessageBox.question(
            self, "미체결 전체 취소",
            f"조회된 미체결 주문 {len(buf)}건을 모두 취소하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        success, fail = 0, 0
        for o in buf:
            try:
                self.mw.ib.cancelOrder(o["oid"])
                self._log(f"✕ 취소: OID={o['oid']}")
                success += 1
            except Exception as e:
                self._log(f"❌ OID={o['oid']} 취소 오류: {e}")
                fail += 1
        msg = f"✅ 미체결 전체 취소: {success}건 전송"
        if fail: msg += f" / {fail}건 실패"
        self.lbl_cancel_status.setStyleSheet(
            "color:#ff6666;font-size:11px;"
            "border:1px solid #333;border-radius:3px;padding:2px;")
        self.lbl_cancel_status.setText(msg)
        self._log(msg)
        # 2초 후 미체결 재조회
        QTimer.singleShot(2000, self._fetch_open_orders)
