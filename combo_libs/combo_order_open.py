"""
combo_order_open.py — 미체결 조회 / 정정 / 취소 로직
────────────────────────────────────────────────────
on_open_orders  : 미체결 주문 조회 → SyntheticStatusPanel + 로그
on_modify_order : 정정 다이얼로그 → 가격 수정 후 placeOrder
on_cancel_order : 취소 다이얼로그 → cancelOrder
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDoubleSpinBox,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush


# ── 공통 스타일 유틸 ─────────────────────────────────────────────
def _mk(text, color="#ccc"):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it

_DLG_SS = """
QDialog{background:#0a0a1e;color:#dde0f0;}
QLabel{border:none;color:#dde0f0;}
QTableWidget{background:#07070f;color:#ccc;gridline-color:#1a1a3a;
             border:1px solid #2a2a5a;}
QHeaderView::section{background:#0a0a1e;color:#90caf9;
                     border:1px solid #1a1a3a;font-weight:bold;}
QPushButton{background:#1c1c3a;color:#dde0f0;border:1px solid #3a3a7a;
            border-radius:4px;padding:4px 12px;}
QPushButton:hover{background:#2a2a5a;}
QDoubleSpinBox{background:#0a0a18;color:#ffd700;border:1px solid #3a3a6a;
               border-radius:3px;padding:3px;}
"""


# ── 미체결 주문 조회 ─────────────────────────────────────────────
def on_open_orders(self):
    """
    IB reqOpenOrders() → 수신된 미체결 주문을 팝업 테이블로 표시.
    combo_* 탭에서 발행한 BAG 주문만 필터링.
    """
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return

    collected = []
    _orig_open  = getattr(ib, 'openOrder',    lambda *a: None)
    _orig_end   = getattr(ib, 'openOrdersEnd', lambda *a: None)

    def _on_open_order(oid, contract, order, state):
        try: _orig_open(oid, contract, order, state)
        except: pass
        collected.append({
            "oid":    oid,
            "sym":    getattr(contract, 'symbol', ''),
            "sec":    getattr(contract, 'secType', ''),
            "action": getattr(order,    'action', ''),
            "qty":    getattr(order,    'totalQuantity', 0),
            "lmt":    getattr(order,    'lmtPrice', 0.0),
            "status": getattr(state,    'status', ''),
            "order":  order,
            "contract": contract,
        })

    def _on_end():
        try: _orig_end()
        except: pass
        ib.openOrder    = _orig_open
        ib.openOrdersEnd = _orig_end
        QTimer.singleShot(0, lambda: _show_open_orders_dialog(self, collected))

    ib.openOrder     = _on_open_order
    ib.openOrdersEnd = _on_end

    # 3초 타임아웃
    def _timeout():
        if ib.openOrdersEnd is _on_end:
            ib.openOrder     = _orig_open
            ib.openOrdersEnd = _orig_end
            QTimer.singleShot(0, lambda: _show_open_orders_dialog(self, collected))
    QTimer.singleShot(3000, _timeout)

    try:
        ib.reqOpenOrders()
        self._log("📋 미체결 주문 조회 중…")
    except Exception as e:
        ib.openOrder     = _orig_open
        ib.openOrdersEnd = _orig_end
        self._log(f"❌ reqOpenOrders: {e}")


def _show_open_orders_dialog(self, orders):
    """미체결 주문 팝업 테이블."""
    dlg = QDialog(self)
    dlg.setWindowTitle("📋 미체결 주문")
    dlg.setMinimumSize(620, 320)
    dlg.setStyleSheet(_DLG_SS)

    v = QVBoxLayout(dlg)

    if not orders:
        v.addWidget(QLabel("  미체결 주문 없음"))
        btn = QPushButton("닫기"); btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec_()
        return

    tbl = QTableWidget(len(orders), 6)
    tbl.setHorizontalHeaderLabels(["OID", "종목", "구분", "수량", "지정가", "상태"])
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)

    for r, o in enumerate(orders):
        action_col = "#00ff88" if o["action"] == "BUY" else "#ff6666"
        tbl.setItem(r, 0, _mk(o["oid"], "#aaa"))
        tbl.setItem(r, 1, _mk(o["sym"], "#ffd700"))
        tbl.setItem(r, 2, _mk(o["action"], action_col))
        tbl.setItem(r, 3, _mk(o["qty"]))
        tbl.setItem(r, 4, _mk(f"{o['lmt']:.2f}" if o['lmt'] else "MKT", "#ffaa44"))
        tbl.setItem(r, 5, _mk(o["status"],
            "#00ff88" if "Submit" in o["status"] else
            "#ffaa44" if "Pending" in o["status"] else "#aaa"))

    v.addWidget(tbl)
    v.addWidget(QLabel(f"  총 {len(orders)}건의 미체결 주문"))

    # 하단 버튼
    br = QHBoxLayout()
    btn_mod = QPushButton("✏ 선택 정정")
    btn_mod.setStyleSheet("background:#2a1a0a;color:#ffaa44;border:1px solid #ffaa44;border-radius:4px;padding:4px 12px;")
    btn_can = QPushButton("✖ 선택 취소")
    btn_can.setStyleSheet("background:#2a0a0a;color:#ff4444;border:1px solid #ff4444;border-radius:4px;padding:4px 12px;")
    btn_close = QPushButton("닫기")

    def _do_modify():
        row = tbl.currentRow()
        if row < 0:
            QMessageBox.warning(dlg, "안내", "정정할 주문을 선택하세요.")
            return
        dlg.accept()
        _show_modify_dialog(self, orders[row])

    def _do_cancel():
        row = tbl.currentRow()
        if row < 0:
            QMessageBox.warning(dlg, "안내", "취소할 주문을 선택하세요.")
            return
        o = orders[row]
        reply = QMessageBox.question(
            dlg, "주문 취소 확인",
            f"OID {o['oid']}  {o['sym']} {o['action']} {o['qty']}계약\n취소하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            _do_cancel_order(self, o["oid"])
            dlg.accept()

    btn_mod.clicked.connect(_do_modify)
    btn_can.clicked.connect(_do_cancel)
    btn_close.clicked.connect(dlg.accept)

    br.addWidget(btn_mod); br.addWidget(btn_can)
    br.addStretch(); br.addWidget(btn_close)
    v.addLayout(br)
    dlg.exec_()

    if orders:
        self._log(f"📋 미체결 {len(orders)}건 조회 완료")
    # SyntheticStatusPanel 미체결 탭 갱신
    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'update_open_orders'):
        panel.update_open_orders(orders)
    # 조회 결과 캐시 (정정/취소용)
    self._cached_open_orders = orders


# ── 정정 주문 ────────────────────────────────────────────────────
def on_modify_order(self):
    """정정 버튼 클릭 → 먼저 미체결 조회 후 선택."""
    on_open_orders(self)   # 미체결 팝업에서 정정 선택


def _show_modify_dialog(self, order_info: dict):
    """선택된 주문의 지정가 수정 다이얼로그."""
    dlg = QDialog(self)
    dlg.setWindowTitle("✏ 정정 주문")
    dlg.setFixedSize(360, 200)
    dlg.setStyleSheet(_DLG_SS)

    v = QVBoxLayout(dlg)
    oid   = order_info["oid"]
    sym   = order_info["sym"]
    act   = order_info["action"]
    qty   = order_info["qty"]
    cur_p = order_info["lmt"] or 0.0

    v.addWidget(QLabel(
        f"  OID {oid}  |  {sym}  {act}  {qty}계약\n"
        f"  현재 지정가: {cur_p:.2f}"))

    pr = QHBoxLayout()
    pr.addWidget(QLabel("  새 지정가:"))
    spin = QDoubleSpinBox()
    spin.setRange(0.01, 99999.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setValue(cur_p)
    spin.setFixedHeight(28)
    pr.addWidget(spin)
    v.addLayout(pr)

    br = QHBoxLayout()
    btn_ok  = QPushButton("✏ 정정 전송")
    btn_ok.setStyleSheet("background:#2a1a0a;color:#ffaa44;border:1px solid #ffaa44;border-radius:4px;padding:4px 14px;")
    btn_no  = QPushButton("취소")

    def _send():
        new_price = spin.value()
        ib = getattr(self, 'mw', None)
        ib = getattr(ib, 'ib', None) if ib else None
        if not ib:
            self._log("❌ IB 미연결"); dlg.accept(); return
        try:
            order = order_info["order"]
            order.lmtPrice = new_price
            ib.placeOrder(oid, order_info["contract"], order)
            self._log(f"✏ 정정 전송: OID {oid}  {sym} {act} {qty}계약  새가격={new_price:.2f}")
        except Exception as e:
            self._log(f"❌ 정정 오류: {e}")
        dlg.accept()

    btn_ok.clicked.connect(_send)
    btn_no.clicked.connect(dlg.reject)
    br.addWidget(btn_ok); br.addStretch(); br.addWidget(btn_no)
    v.addLayout(br)
    dlg.exec_()


# ── 취소 주문 ────────────────────────────────────────────────────
def on_cancel_order(self):
    """취소 버튼 클릭 → 미체결 조회 후 선택 취소."""
    on_open_orders(self)   # 미체결 팝업에서 취소 선택


def _do_cancel_order(self, oid: int):
    """실제 cancelOrder 전송."""
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결"); return
    try:
        ib.cancelOrder(oid)
        self._log(f"✖ 취소 전송: OID {oid}")
        # Chaser도 비활성화
        try:
            from combo_order_chaser import deactivate_chaser
            deactivate_chaser(self, reason="수동 취소")
        except Exception:
            pass
    except Exception as e:
        self._log(f"❌ cancelOrder: {e}")


# ── +1/-1호가 정정 ────────────────────────────────────────────
def _modify_tick(self, direction: int):
    """
    미체결 탭에서 선택된 주문을 +1 또는 -1 호가로 정정.
    direction: +1 또는 -1
    """
    panel = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])
    if not orders:
        self._log("⚠ 미체결 주문 없음 — 먼저 조회하세요.")
        return

    row = panel.get_selected_order() if panel else -1
    if row < 0 or row >= len(orders):
        self._log("⚠ 정정할 주문을 선택하세요.")
        return

    o = orders[row]
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결"); return

    cur_price = o.get("lmt", 0.0) or 0.0
    # 틱 크기: $3 이상 = 0.10, 미만 = 0.05
    tick = 0.10 if cur_price >= 3.0 else 0.05
    new_price = round(cur_price + direction * tick, 2)
    if new_price <= 0:
        self._log("⚠ 가격이 0 이하로 내려갈 수 없음"); return

    try:
        order = o["order"]
        order.lmtPrice = new_price
        ib.placeOrder(o["oid"], o["contract"], order)
        sign = "+" if direction > 0 else ""
        self._log(f"✏ {sign}{direction}호가 정정: OID {o['oid']}  "
                  f"{cur_price:.2f} → {new_price:.2f}")
        # 캐시 업데이트
        orders[row]["lmt"] = new_price
        if panel:
            panel.update_open_orders(orders)
    except Exception as e:
        self._log(f"❌ 정정 오류: {e}")


# ── 자동 취소 ─────────────────────────────────────────────────
def _cancel_selected(self):
    """미체결 탭 선택 항목 취소 (없으면 전체 취소)."""
    panel  = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])

    if not orders:
        # 캐시 없으면 먼저 조회 후 취소
        def _after_fetch():
            orders2 = getattr(self, '_cached_open_orders', [])
            for o in orders2:
                _do_cancel_order(self, o["oid"])
            if orders2:
                self._log(f"✖ 전체 취소 완료: {len(orders2)}건")
            if panel:
                panel.update_open_orders([])
        on_open_orders(self)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(3500, _after_fetch)
        return

    row = panel.get_selected_order() if panel else -1
    if row >= 0 and row < len(orders):
        o = orders[row]
        _do_cancel_order(self, o["oid"])
        orders.pop(row)
        self._log(f"✖ 취소: OID {o['oid']}")
    else:
        # 선택 없으면 전체
        for o in orders:
            _do_cancel_order(self, o["oid"])
        self._log(f"✖ 전체 취소: {len(orders)}건")
        orders.clear()

    if panel:
        panel.update_open_orders(orders)
