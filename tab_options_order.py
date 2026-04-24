"""
tab_options_order.py — 빠른 주문 시스템  v6.5
════════════════════════════════════════════════════════════════
  CallPutGrid 에서 분리 (tab_options.py 에 mixin으로 사용)

  포함 기능:
  - _build_quick_order_panel()  신규/정정/취소 탭 위젯
  - _on_qord_type_toggle()
  - _fetch_open_orders() / _populate_open_order_tables()
  - _fill_amend_from_table() / _fill_cancel_from_table()
  - _amend_order() / _cancel_order()
  - _qord_fill() / _qord_place()

  어댑티브 알고리즘 기능:
  - tab_options_order_adaptive.py → AdaptiveMixin 으로 분리
    · _build_adaptive_ui(tif_row)  UI 위젯 삽입
    · _apply_adaptive(ibord)       주문 객체에 algoStrategy 적용
    · _adaptive_label()            확인창 / 상태바 태그 문자열
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QRadioButton, QButtonGroup, QMessageBox,
    QSpinBox, QTabWidget,
    QTableWidget, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer

from core import make_opt_contract, ts
from tab_options_order_adapted import AdaptiveMixin


class OrderMixin(AdaptiveMixin):
    """빠른 주문 전용 메서드 모음. CallPutGrid 에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 빠른 주문 GroupBox (신규 / 정정 / 취소 탭)
    # ─────────────────────────────────────────────────────────
    def _build_quick_order_panel(self) -> QWidget:
        gb = QGroupBox("⚡ 빠른 주문")
        gb_v = QVBoxLayout(gb)
        gb_v.setSpacing(3); gb_v.setContentsMargins(4, 6, 4, 4)

        _tab_style = (
            "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
            "border:1px solid #2a2a4a;border-bottom:none;font-size:11px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
        tab_w = QTabWidget(); tab_w.setStyleSheet(_tab_style)

        # ── 탭1: 신규 주문 ────────────────────────────────────
        new_w  = QWidget()
        root_v = QVBoxLayout(new_w)
        root_v.setSpacing(5); root_v.setContentsMargins(6, 6, 6, 6)

        tgt_row = QHBoxLayout()
        tgt_row.addWidget(QLabel("대상:"))
        self.qord_side = QLineEdit(); self.qord_side.setReadOnly(True)
        self.qord_side.setFixedWidth(28)
        self.qord_side.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:13px;"
            "background:#0a0a1e;border:1px solid #333;")
        self.qord_strike = QLineEdit(); self.qord_strike.setReadOnly(True)
        self.qord_strike.setFixedWidth(62)
        self.qord_strike.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:13px;"
            "background:#0a0a1e;border:1px solid #333;")
        tgt_row.addWidget(self.qord_side); tgt_row.addWidget(self.qord_strike)
        tgt_row.addStretch()
        root_v.addLayout(tgt_row)

        self.lbl_qord_src = QLabel("")
        self.lbl_qord_src.setStyleSheet("color:#ff8800;font-size:10px;border:none;")
        self.lbl_qord_src.setWordWrap(True)
        root_v.addWidget(self.lbl_qord_src)

        line = QLabel(); line.setFixedHeight(1)
        line.setStyleSheet("background:#333;border:none;")
        root_v.addWidget(line)

        gl = QGridLayout(); gl.setSpacing(4)
        lbl_style = "color:#aaa;font-size:11px;border:none;"

        # ── 유형 행: [지정가] [시장가]  [어댑티브🟢] [Normal▼]  [MAX] [$200] ──
        type_w = QWidget(); type_h = QHBoxLayout(type_w)
        type_h.setContentsMargins(0,0,0,0); type_h.setSpacing(5)
        self.qord_lmt = QRadioButton("지정가"); self.qord_mkt = QRadioButton("시장가")
        self.qord_lmt.setChecked(True)
        self.qord_lmt.setStyleSheet("color:#ffd700;font-size:11px;")
        self.qord_mkt.setStyleSheet("color:#ffd700;font-size:11px;")
        qord_grp = QButtonGroup(self)
        qord_grp.addButton(self.qord_lmt); qord_grp.addButton(self.qord_mkt)
        self.qord_lmt.toggled.connect(self._on_qord_type_toggle)
        type_h.addWidget(self.qord_lmt); type_h.addWidget(self.qord_mkt)

        # 어댑티브 체크박스 + 콤보 (AdaptiveMixin)
        self._build_adaptive_ui(type_h)

        # MAX / $200 버튼
        _abtn_s = ("QPushButton{background:#1a2a3a;color:#90caf9;font-size:10px;"
                   "font-weight:bold;padding:1px 4px;border-radius:3px;"
                   "border:1px solid #2a4a6a;}"
                   "QPushButton:hover{background:#2a3a5a;}")
        self.btn_qty_max = QPushButton("MAX")
        self.btn_qty_200 = QPushButton("$200")
        self.btn_qty_max.setFixedSize(34, 22); self.btn_qty_200.setFixedSize(34, 22)
        self.btn_qty_max.setStyleSheet(_abtn_s); self.btn_qty_200.setStyleSheet(_abtn_s)
        self.btn_qty_max.setToolTip("잔고 조회 후 최대 수량 자동 계산")
        self.btn_qty_200.setToolTip("$200 기준 수량 자동 계산")
        self.btn_qty_max.clicked.connect(self._calc_qty_max)
        self.btn_qty_200.clicked.connect(self._calc_qty_200)
        type_h.addStretch()
        type_h.addWidget(self.btn_qty_max)
        type_h.addWidget(self.btn_qty_200)

        self.qord_price = QLineEdit(); self.qord_price.setPlaceholderText("가격 입력")
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:13px;"
            "background:#0a0a1e;border:1px solid #444;")

        qty_w = QWidget(); qty_h = QHBoxLayout(qty_w)
        qty_h.setContentsMargins(0,0,0,0); qty_h.setSpacing(3)
        self.qord_qty = QSpinBox()
        self.qord_qty.setRange(1, 9999); self.qord_qty.setValue(1)
        self.qord_qty.setFixedHeight(26)
        self.qord_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:12px;")
        _QS = ("QPushButton{background:#2d2d5e;color:#ffd700;"
               "border:1px solid #4a4a8a;border-radius:3px;"
               "font-size:11px;font-weight:bold;}"
               "QPushButton:hover{background:#3d4d6e;}")
        for lbl2, v2 in [("1",1),("5",5),("10",10)]:
            bq = QPushButton(lbl2); bq.setFixedWidth(28); bq.setFixedHeight(26)
            bq.setStyleSheet(_QS)
            bq.clicked.connect(lambda _, v=v2: self.qord_qty.setValue(v))
            qty_h.addWidget(bq)
        qty_h.insertWidget(0, self.qord_qty)

        gl.addWidget(QLabel("유형:", styleSheet=lbl_style), 0, 0)
        gl.addWidget(type_w,                                 0, 1)
        gl.addWidget(QLabel("가격:", styleSheet=lbl_style), 1, 0)
        gl.addWidget(self.qord_price,                        1, 1)
        gl.addWidget(QLabel("수량:", styleSheet=lbl_style), 2, 0)
        gl.addWidget(qty_w,                                  2, 1)
        root_v.addLayout(gl)

        tif_row = QHBoxLayout()
        tif_row.addWidget(QLabel("TIF:", styleSheet=lbl_style))
        self.qord_tif = QComboBox(); self.qord_tif.addItems(["DAY","GTC","IOC","GTD"])
        self.qord_tif.setFixedHeight(24)
        self.qord_tif.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:11px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:11px;}"
            "QComboBox::drop-down{border:none;}")
        tif_row.addWidget(self.qord_tif)
        tif_row.addStretch()
        root_v.addLayout(tif_row)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self.btn_qord_buy = QPushButton("▲ 매수")
        self.btn_qord_buy.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:14px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_buy.clicked.connect(lambda: self._qord_place("BUY"))
        self.btn_qord_sell = QPushButton("▼ 매도")
        self.btn_qord_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:14px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_sell.clicked.connect(lambda: self._qord_place("SELL"))
        btn_row.addWidget(self.btn_qord_buy, 1); btn_row.addWidget(self.btn_qord_sell, 1)
        root_v.addLayout(btn_row)

        self.lbl_qord_status = QLabel("대기 중")
        self.lbl_qord_status.setAlignment(Qt.AlignCenter)
        self.lbl_qord_status.setStyleSheet(
            "color:#888;font-size:11px;border:1px solid #333;border-radius:3px;padding:2px;")
        root_v.addWidget(self.lbl_qord_status)
        root_v.addStretch()
        tab_w.addTab(new_w, "⚡ 신규")

        # ── 탭2: 정정 주문 ────────────────────────────────────
        amend_w = QWidget()
        av = QVBoxLayout(amend_w); av.setSpacing(5); av.setContentsMargins(8, 8, 8, 8)
        _ls = "color:#aaa;font-size:11px;border:none;"
        _es = "background:#0a0a1e;color:#ffd700;border:1px solid #444;font-size:13px;"

        btn_fetch_a = QPushButton("📋 미체결 주문 조회 (클릭)")
        btn_fetch_a.setStyleSheet(
            "background:#1a3a1a;color:#00ff88;font-size:11px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")
        btn_fetch_a.clicked.connect(self._fetch_open_orders)
        av.addWidget(btn_fetch_a)

        self.tbl_open_orders_a = QTableWidget(0, 4)
        self.tbl_open_orders_a.setHorizontalHeaderLabels(["OID","종목","방향","가격"])
        self.tbl_open_orders_a.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_open_orders_a.verticalHeader().setVisible(False)
        self.tbl_open_orders_a.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_open_orders_a.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_open_orders_a.setMaximumHeight(110)
        self.tbl_open_orders_a.setStyleSheet(
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#1a1a3a;font-size:11px;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-size:10px;}"
            "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}")
        self.tbl_open_orders_a.cellClicked.connect(lambda r, c: self._fill_amend_from_table(r))
        av.addWidget(self.tbl_open_orders_a)

        av.addWidget(QLabel("주문 ID:", styleSheet=_ls))
        self.amend_oid = QLineEdit(); self.amend_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.amend_oid.setStyleSheet(_es); self.amend_oid.setFixedHeight(26)
        av.addWidget(self.amend_oid)

        av.addWidget(QLabel("새 가격:", styleSheet=_ls))
        self.amend_price = QLineEdit(); self.amend_price.setPlaceholderText("새 지정가")
        self.amend_price.setStyleSheet(_es); self.amend_price.setFixedHeight(26)
        av.addWidget(self.amend_price)

        av.addWidget(QLabel("새 수량:", styleSheet=_ls))
        self.amend_qty = QSpinBox()
        self.amend_qty.setRange(1, 9999); self.amend_qty.setValue(1); self.amend_qty.setFixedHeight(26)
        self.amend_qty.setStyleSheet("background:#0a0a1e;color:#fff;border:1px solid #444;font-size:13px;")
        av.addWidget(self.amend_qty)

        btn_amend = QPushButton("✏ 정정 전송")
        btn_amend.setStyleSheet(
            "background:#1a4a6b;color:#90caf9;font-size:13px;"
            "font-weight:bold;padding:8px;border-radius:4px;")
        btn_amend.clicked.connect(self._amend_order); av.addWidget(btn_amend)

        self.lbl_amend_status = QLabel("대기 중")
        self.lbl_amend_status.setAlignment(Qt.AlignCenter)
        self.lbl_amend_status.setStyleSheet(
            "color:#888;font-size:11px;border:1px solid #333;border-radius:3px;padding:2px;")
        av.addWidget(self.lbl_amend_status); av.addStretch()
        tab_w.addTab(amend_w, "✏ 정정")

        # ── 탭3: 취소 주문 ────────────────────────────────────
        cancel_w = QWidget()
        cv = QVBoxLayout(cancel_w); cv.setSpacing(5); cv.setContentsMargins(8, 8, 8, 8)

        btn_fetch_c = QPushButton("📋 미체결 주문 조회 (클릭)")
        btn_fetch_c.setStyleSheet(
            "background:#1a3a1a;color:#00ff88;font-size:11px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")
        btn_fetch_c.clicked.connect(self._fetch_open_orders)
        cv.addWidget(btn_fetch_c)

        self.tbl_open_orders_c = QTableWidget(0, 4)
        self.tbl_open_orders_c.setHorizontalHeaderLabels(["OID","종목","방향","가격"])
        self.tbl_open_orders_c.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_open_orders_c.verticalHeader().setVisible(False)
        self.tbl_open_orders_c.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_open_orders_c.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_open_orders_c.setMaximumHeight(110)
        self.tbl_open_orders_c.setStyleSheet(
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#1a1a3a;font-size:11px;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-size:10px;}"
            "QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
        self.tbl_open_orders_c.cellClicked.connect(lambda r, c: self._fill_cancel_from_table(r))
        cv.addWidget(self.tbl_open_orders_c)

        cv.addWidget(QLabel("주문 ID:", styleSheet=_ls))
        self.cancel_oid = QLineEdit(); self.cancel_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.cancel_oid.setStyleSheet(_es); self.cancel_oid.setFixedHeight(26)
        cv.addWidget(self.cancel_oid)

        btn_cancel = QPushButton("✕ 취소 전송")
        btn_cancel.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:13px;"
            "font-weight:bold;padding:10px;border-radius:4px;")
        btn_cancel.clicked.connect(self._cancel_order); cv.addWidget(btn_cancel)

        self.lbl_cancel_status = QLabel("대기 중")
        self.lbl_cancel_status.setAlignment(Qt.AlignCenter)
        self.lbl_cancel_status.setStyleSheet(
            "color:#888;font-size:11px;border:1px solid #333;border-radius:3px;padding:2px;")
        cv.addWidget(self.lbl_cancel_status); cv.addStretch()
        tab_w.addTab(cancel_w, "✕ 취소")

        gb_v.addWidget(tab_w)
        return gb

    # ─────────────────────────────────────────────────────────
    # 주문 로직
    # ─────────────────────────────────────────────────────────
    def _on_qord_type_toggle(self):
        is_lmt = self.qord_lmt.isChecked()
        self.qord_price.setEnabled(is_lmt)
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:13px;"
            "background:#0a0a1e;border:1px solid #444;"
            if is_lmt else
            "color:#555;font-weight:bold;font-size:13px;"
            "background:#070710;border:1px solid #222;")

    def _fetch_open_orders(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        self._open_orders_buf = []
        ib = self.mw.ib

        def _on_open_order(orderId, contract, order, orderState):
            self._open_orders_buf.append({
                "oid":    orderId,
                "symbol": getattr(contract, "localSymbol", "") or getattr(contract, "symbol", ""),
                "action": getattr(order, "action", ""),
                "price":  getattr(order, "lmtPrice", 0.0),
                "qty":    getattr(order, "totalQuantity", 0),
                "type":   getattr(order, "orderType", ""),
            })

        def _on_open_order_end():
            QTimer.singleShot(0, self._populate_open_order_tables)

        ib._orig_openOrder    = getattr(ib, 'openOrder',    lambda *a: None)
        ib._orig_openOrderEnd = getattr(ib, 'openOrderEnd', lambda: None)
        ib.openOrder    = _on_open_order
        ib.openOrderEnd = _on_open_order_end
        try:
            ib.reqOpenOrders()
            self._log("📋 미체결 주문 조회 요청...")
        except Exception as e:
            self._log(f"❌ 주문 조회 오류: {e}")
        QTimer.singleShot(2000, lambda: (
            setattr(ib, 'openOrder',    ib._orig_openOrder),
            setattr(ib, 'openOrderEnd', ib._orig_openOrderEnd)))

    def _populate_open_order_tables(self):
        from core import make_table
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush
        orders = getattr(self, '_open_orders_buf', [])
        for tbl in (self.tbl_open_orders_a, self.tbl_open_orders_c):
            tbl.setRowCount(0)
            for o in orders:
                r = tbl.rowCount(); tbl.insertRow(r)
                price_str = f"{o['price']:.2f}" if o['price'] else o['type']
                col = "#00ff88" if o['action'] == "BUY" else "#ff6666"
                from tab_options import _mk
                tbl.setItem(r, 0, _mk(str(o['oid']),              "#ffd700"))
                tbl.setItem(r, 1, _mk(o['symbol'],                "#ccc"))
                tbl.setItem(r, 2, _mk(f"{o['action']} {o['qty']}", col))
                tbl.setItem(r, 3, _mk(price_str,                  "#90caf9"))
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

    def _amend_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            oid   = int(self.amend_oid.text().strip())
            price = float(self.amend_price.text().strip())
            qty   = self.amend_qty.value()
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "주문ID와 새 가격을 올바르게 입력하세요."); return
        try:
            from ibapi.order import Order as IbOrder
            ibord = IbOrder()
            ibord.orderType = "LMT"; ibord.totalQuantity = qty
            ibord.lmtPrice  = price; ibord.tif = "DAY"
            self.mw.ib.placeOrder(oid, None, ibord)
            self.lbl_amend_status.setStyleSheet(
                "color:#90caf9;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
            self.lbl_amend_status.setText(f"전송: OID={oid} @ ${price:.2f} ×{qty}")
            self._log(f"✏ 정정: OID={oid}  새가격=${price:.2f}  수량={qty}")
        except Exception as e:
            self.lbl_amend_status.setText(f"오류: {e}")
            self._log(f"❌ 정정 오류: {e}")

    def _cancel_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try: oid = int(self.cancel_oid.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "주문ID를 입력하세요."); return
        ret = QMessageBox.question(self, "취소 확인", f"주문 OID={oid} 를 취소하시겠습니까?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        try:
            self.mw.ib.cancelOrder(oid)
            self.lbl_cancel_status.setStyleSheet(
                "color:#ff6666;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
            self.lbl_cancel_status.setText(f"취소 전송: OID={oid}")
            self._log(f"✕ 취소: OID={oid}")
        except Exception as e:
            self.lbl_cancel_status.setText(f"오류: {e}")
            self._log(f"❌ 취소 오류: {e}")

    def _qord_fill(self, side: str, strike: str, price: float = None, source: str = ""):
        self.qord_side.setText(side); self.qord_strike.setText(strike)
        if price is not None: self.qord_price.setText(f"{price:.2f}")
        self.lbl_qord_src.setText(source)

    def _qord_place(self, action: str):
        side = self.qord_side.text().strip(); strike = self.qord_strike.text().strip()
        qty  = self.qord_qty.value(); is_lmt = self.qord_lmt.isChecked()
        price_txt = self.qord_price.text().strip(); tif = self.qord_tif.currentText()
        if not side or not strike:
            QMessageBox.warning(self, "입력 오류",
                "테이블 행을 클릭하거나 감시 조건이 성립될 때까지 대기하세요."); return
        if is_lmt and not price_txt:
            QMessageBox.warning(self, "입력 오류", "지정가를 입력하세요."); return
        order_type = "LMT" if is_lmt else "MKT"
        try: price = float(price_txt) if is_lmt else 0.0
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "유효한 가격을 입력하세요."); return
        action_kr  = "매수" if action == "BUY" else "매도"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"
        msg = f"{action_kr} {order_type}  {side} {strike}  {qty}계약  {price_disp}  {tif}{self._adaptive_label()}"
        ret = QMessageBox.question(self, f"주문 확인 — {action_kr}",
            f"⚠ 아래 주문을 전송합니다.\n\n{msg}\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            from ibapi.order import Order as IbOrder
            idx = self.combo_exp.currentIndex()
            _, expiry, tag = self._expiry_list[idx]
            sym = self.edit_sym.text().strip().upper()
            contract = make_opt_contract(sym, float(strike), side, expiry, tag)
            ibord = IbOrder()
            ibord.action = action; ibord.orderType = order_type
            ibord.totalQuantity = qty; ibord.tif = tif
            if is_lmt: ibord.lmtPrice = price

            # ── 어댑티브 알고리즘 적용 → AdaptiveMixin 으로 위임 ─
            adapt_tag = self._adaptive_label() if self._apply_adaptive(ibord) else ""

            oid = self.mw.ib.nextOrderId()
            self.mw.ib.nextOrderId = lambda: oid + 1
            self.mw.ib.placeOrder(oid, contract, ibord)
            col = "#00ff88" if action == "BUY" else "#ff6666"
            self.lbl_qord_status.setStyleSheet(
                f"color:{col};font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_qord_status.setText(f"전송: {msg}{adapt_tag}")
            self._log(f"📤 빠른주문: {msg}{adapt_tag}  (OID={oid})")
        except Exception as e:
            self.lbl_qord_status.setText(f"오류: {e}")
            self._log(f"❌ 주문 오류: {e}")