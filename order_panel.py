"""
order_panel.py — 빠른 주문 패널 UI  v6.4
════════════════════════════════════════════════════════
수정 대상: 신규주문·정정·취소 탭 레이아웃, 미체결조회 테이블
포함 메서드:
  _build_quick_order_panel()   GroupBox + QTabWidget(신규/정정/취소)
  _on_qord_type_toggle()
  _fetch_open_orders()         reqOpenOrders()
  _populate_open_order_tables()
  _fill_amend_from_table()
  _fill_cancel_from_table()
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QRadioButton, QButtonGroup,
    QSpinBox, QTabWidget,
    QTableWidget, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer


class OrderPanelMixin:
    """빠른 주문 패널 UI. CallPutGrid에 mixin된다."""

    def _build_quick_order_panel(self) -> QWidget:
        """GroupBox 안에 신규/정정/취소 QTabWidget."""
        gb = QGroupBox("⚡ 빠른 주문")
        gb_v = QVBoxLayout(gb)
        gb_v.setSpacing(3); gb_v.setContentsMargins(4, 6, 4, 4)

        _tab_s = (
            "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
            "border:1px solid #2a2a4a;border-bottom:none;font-size:13px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
        tab_w = QTabWidget(); tab_w.setStyleSheet(_tab_s)

        # ── 탭1: 신규 주문 ────────────────────────────────
        new_w  = QWidget()
        root_v = QVBoxLayout(new_w)
        root_v.setSpacing(5); root_v.setContentsMargins(6, 6, 6, 6)

        tgt_row = QHBoxLayout()
        tgt_row.addWidget(QLabel("대상:"))
        self.qord_side = QLineEdit(); self.qord_side.setReadOnly(True)
        self.qord_side.setFixedWidth(28)
        self.qord_side.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #333;")
        self.qord_strike = QLineEdit(); self.qord_strike.setReadOnly(True)
        self.qord_strike.setFixedWidth(62)
        self.qord_strike.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #333;")
        tgt_row.addWidget(self.qord_side)
        tgt_row.addWidget(self.qord_strike)
        tgt_row.addStretch()
        root_v.addLayout(tgt_row)

        self.lbl_qord_src = QLabel("")
        self.lbl_qord_src.setStyleSheet(
            "color:#ff8800;font-size:12px;border:none;")
        self.lbl_qord_src.setWordWrap(True)
        root_v.addWidget(self.lbl_qord_src)

        line = QLabel(); line.setFixedHeight(1)
        line.setStyleSheet("background:#333;border:none;")
        root_v.addWidget(line)

        gl = QGridLayout(); gl.setSpacing(4)
        _ls = "color:#aaa;font-size:13px;border:none;"

        type_w = QWidget(); type_h = QHBoxLayout(type_w)
        type_h.setContentsMargins(0,0,0,0); type_h.setSpacing(6)
        self.qord_lmt = QRadioButton("지정가")
        self.qord_mkt = QRadioButton("시장가")
        self.qord_lmt.setChecked(True)
        self.qord_lmt.setStyleSheet("color:#ffd700;font-size:13px;")
        self.qord_mkt.setStyleSheet("color:#ffd700;font-size:13px;")
        qord_grp = QButtonGroup(self)
        qord_grp.addButton(self.qord_lmt)
        qord_grp.addButton(self.qord_mkt)
        self.qord_lmt.toggled.connect(self._on_qord_type_toggle)
        type_h.addWidget(self.qord_lmt); type_h.addWidget(self.qord_mkt)
        type_h.addStretch()
        # ✅ 자동계산 버튼 2개 (유형 행 우측)
        _abtn_s = ("QPushButton{background:#1a2a3a;color:#90caf9;font-size:12px;"
                   "font-weight:bold;padding:1px 5px;border-radius:3px;"
                   "border:1px solid #2a4a6a;}"
                   "QPushButton:hover{background:#2a3a5a;}")
        self.btn_qty_max  = QPushButton("MAX")
        self.btn_qty_200  = QPushButton("$200")
        self.btn_qty_max.setFixedHeight(22); self.btn_qty_max.setFixedWidth(38)
        self.btn_qty_200.setFixedHeight(22); self.btn_qty_200.setFixedWidth(38)
        self.btn_qty_max.setStyleSheet(_abtn_s)
        self.btn_qty_200.setStyleSheet(_abtn_s)
        self.btn_qty_max.setToolTip("잔고 조회 후 최대 수량 자동 계산")
        self.btn_qty_200.setToolTip("$200 기준 수량 자동 계산")
        self.btn_qty_max.clicked.connect(self._calc_qty_max)
        self.btn_qty_200.clicked.connect(self._calc_qty_200)
        type_h.addWidget(self.btn_qty_max)
        type_h.addWidget(self.btn_qty_200)

        self.qord_price = QLineEdit()
        self.qord_price.setPlaceholderText("가격 입력")
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;")

        qty_w = QWidget(); qty_h = QHBoxLayout(qty_w)
        qty_h.setContentsMargins(0,0,0,0); qty_h.setSpacing(3)
        self.qord_qty = QSpinBox()
        self.qord_qty.setRange(1, 9999); self.qord_qty.setValue(1)
        self.qord_qty.setFixedHeight(26)
        self.qord_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:14px;")
        _QS = ("QPushButton{background:#2d2d5e;color:#ffd700;"
               "border:1px solid #4a4a8a;border-radius:3px;"
               "font-size:13px;font-weight:bold;}"
               "QPushButton:hover{background:#3d4d6e;}")
        for lbl2, v2 in [("1",1),("5",5),("10",10)]:
            bq = QPushButton(lbl2); bq.setFixedWidth(28); bq.setFixedHeight(26)
            bq.setStyleSheet(_QS)
            bq.clicked.connect(lambda _, v=v2: self.qord_qty.setValue(v))
            qty_h.addWidget(bq)
        qty_h.insertWidget(0, self.qord_qty)

        gl.addWidget(QLabel("유형:", styleSheet=_ls), 0, 0)
        gl.addWidget(type_w,                           0, 1)
        gl.addWidget(QLabel("가격:", styleSheet=_ls), 1, 0)
        gl.addWidget(self.qord_price,                  1, 1)
        gl.addWidget(QLabel("수량:", styleSheet=_ls), 2, 0)
        gl.addWidget(qty_w,                            2, 1)
        root_v.addLayout(gl)

        # ── 수수료 예상 레이블 ────────────────────────────────
        self.lbl_commission = QLabel("")
        self.lbl_commission.setStyleSheet(
            "color:#FFA500;font-size:13px;border:none;"
            "background:#0d0d20;padding:2px 4px;border-radius:3px;")
        self.lbl_commission.setAlignment(Qt.AlignRight)
        root_v.addWidget(self.lbl_commission)
        self.qord_qty.valueChanged.connect(self._update_commission_label)
        self._update_commission_label(self.qord_qty.value())  # 초기값 표시

        tif_row = QHBoxLayout()
        tif_row.addWidget(QLabel("TIF:", styleSheet=_ls))
        self.qord_tif = QComboBox()
        self.qord_tif.addItems(["DAY","GTC","IOC","GTD"])
        self.qord_tif.setFixedHeight(24)
        self.qord_tif.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:13px;padding:1px;}"
            "QComboBox QAbstractItemView{"
            "background:#0a0a1e;color:#ffd700;font-size:13px;}"
            "QComboBox::drop-down{border:none;}")
        tif_row.addWidget(self.qord_tif); tif_row.addStretch()
        root_v.addLayout(tif_row)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self.btn_qord_buy = QPushButton("▲ 매수")
        self.btn_qord_buy.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:16px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_buy.clicked.connect(lambda _: self._qord_place("BUY"))
        self.btn_qord_sell = QPushButton("▼ 매도")
        self.btn_qord_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:16px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_sell.clicked.connect(lambda _: self._qord_place("SELL"))
        btn_row.addWidget(self.btn_qord_buy, 1)
        btn_row.addWidget(self.btn_qord_sell, 1)
        root_v.addLayout(btn_row)

        self.lbl_qord_status = QLabel("대기 중")
        self.lbl_qord_status.setAlignment(Qt.AlignCenter)
        self.lbl_qord_status.setStyleSheet(
            "color:#888;font-size:13px;"
            "border:1px solid #333;border-radius:3px;padding:2px;")
        root_v.addWidget(self.lbl_qord_status)
        root_v.addStretch()
        tab_w.addTab(new_w, "⚡ 신규")

        # ── 탭2: 정정 / 탭3: 취소 공통 테이블 스타일 ────────
        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;"
            "gridline-color:#1a1a3a;font-size:13px;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-size:12px;}"
            "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}")
        _es = ("background:#0a0a1e;color:#ffd700;"
               "border:1px solid #444;font-size:15px;")
        _ls2 = "color:#aaa;font-size:13px;border:none;"
        _fetch_s = (
            "background:#1a3a1a;color:#00ff88;font-size:13px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")

        def _make_order_tbl(sel_color="#1a3a6b"):
            tbl = QTableWidget(0, 4)
            tbl.setHorizontalHeaderLabels(["OID","종목","방향","가격"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            tbl.setMaximumHeight(110)
            tbl.setStyleSheet(_tbl_s.replace("#1a3a6b", sel_color))
            return tbl

        # ── 탭2: 정정 ────────────────────────────────────────
        amend_w = QWidget()
        av = QVBoxLayout(amend_w); av.setSpacing(5); av.setContentsMargins(8,8,8,8)

        btn_fetch_a = QPushButton("📋 미체결 주문 조회 (클릭)")
        btn_fetch_a.setStyleSheet(_fetch_s)
        btn_fetch_a.clicked.connect(self._fetch_open_orders)
        av.addWidget(btn_fetch_a)

        self.tbl_open_orders_a = _make_order_tbl("#1a3a6b")
        self.tbl_open_orders_a.cellClicked.connect(
            lambda r, c: self._fill_amend_from_table(r))
        av.addWidget(self.tbl_open_orders_a)

        av.addWidget(QLabel("주문 ID:", styleSheet=_ls2))
        self.amend_oid = QLineEdit()
        self.amend_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.amend_oid.setStyleSheet(_es); self.amend_oid.setFixedHeight(26)
        av.addWidget(self.amend_oid)

        av.addWidget(QLabel("새 가격:", styleSheet=_ls2))
        self.amend_price = QLineEdit()
        self.amend_price.setPlaceholderText("새 지정가")
        self.amend_price.setStyleSheet(_es); self.amend_price.setFixedHeight(26)
        av.addWidget(self.amend_price)

        av.addWidget(QLabel("새 수량:", styleSheet=_ls2))
        self.amend_qty = QSpinBox()
        self.amend_qty.setRange(1, 9999); self.amend_qty.setValue(1)
        self.amend_qty.setFixedHeight(26)
        self.amend_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:15px;")
        av.addWidget(self.amend_qty)

        btn_amend = QPushButton("✏ 정정 전송")
        btn_amend.setStyleSheet(
            "background:#1a4a6b;color:#90caf9;font-size:15px;"
            "font-weight:bold;padding:8px;border-radius:4px;")
        btn_amend.clicked.connect(self._amend_order)
        av.addWidget(btn_amend)

        self.lbl_amend_status = QLabel("대기 중")
        self.lbl_amend_status.setAlignment(Qt.AlignCenter)
        self.lbl_amend_status.setStyleSheet(
            "color:#888;font-size:13px;"
            "border:1px solid #333;border-radius:3px;padding:2px;")
        av.addWidget(self.lbl_amend_status); av.addStretch()
        tab_w.addTab(amend_w, "✏ 정정")

        # ── 탭3: 취소 ────────────────────────────────────────
        cancel_w = QWidget()
        cv = QVBoxLayout(cancel_w); cv.setSpacing(5); cv.setContentsMargins(8,8,8,8)

        btn_fetch_c = QPushButton("📋 미체결 주문 조회 (클릭)")
        btn_fetch_c.setStyleSheet(_fetch_s)
        btn_fetch_c.clicked.connect(self._fetch_open_orders)
        cv.addWidget(btn_fetch_c)

        self.tbl_open_orders_c = _make_order_tbl("#3a1a1a")
        self.tbl_open_orders_c.setStyleSheet(
            _tbl_s + "QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
        self.tbl_open_orders_c.cellClicked.connect(
            lambda r, c: self._fill_cancel_from_table(r))
        cv.addWidget(self.tbl_open_orders_c)

        cv.addWidget(QLabel("주문 ID:", styleSheet=_ls2))
        self.cancel_oid = QLineEdit()
        self.cancel_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.cancel_oid.setStyleSheet(_es); self.cancel_oid.setFixedHeight(26)
        cv.addWidget(self.cancel_oid)

        btn_cancel = QPushButton("✕ 취소 전송")
        btn_cancel.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:15px;"
            "font-weight:bold;padding:10px;border-radius:4px;")
        btn_cancel.clicked.connect(self._cancel_order)
        cv.addWidget(btn_cancel)

        self.lbl_cancel_status = QLabel("대기 중")
        self.lbl_cancel_status.setAlignment(Qt.AlignCenter)
        self.lbl_cancel_status.setStyleSheet(
            "color:#888;font-size:13px;"
            "border:1px solid #333;border-radius:3px;padding:2px;")
        cv.addWidget(self.lbl_cancel_status); cv.addStretch()
        tab_w.addTab(cancel_w, "✕ 취소")

        gb_v.addWidget(tab_w)

        # ── 잔고 매도 패널 (테이블 잔고 클릭 시 슬라이드업) ───
        self._pos_sell_panel = QWidget()
        self._pos_sell_panel.setVisible(False)
        self._pos_sell_panel.setStyleSheet(
            "background:#1a0a0a;border:1px solid #6b1a1a;border-radius:4px;")
        ps_v = QVBoxLayout(self._pos_sell_panel)
        ps_v.setContentsMargins(6, 5, 6, 5); ps_v.setSpacing(4)

        # 헤더
        ps_hdr = QHBoxLayout()
        self._ps_lbl_title = QLabel("▼ 잔고 청산 매도")
        self._ps_lbl_title.setStyleSheet(
            "color:#ff6666;font-weight:bold;font-size:13px;border:none;")
        ps_btn_close = QPushButton("✕")
        ps_btn_close.setFixedSize(18, 18)
        ps_btn_close.setStyleSheet(
            "background:#3a1a1a;color:#ff6666;border:none;"
            "font-size:11px;border-radius:2px;")
        ps_btn_close.clicked.connect(lambda: self._pos_sell_panel.setVisible(False))
        ps_hdr.addWidget(self._ps_lbl_title); ps_hdr.addStretch()
        ps_hdr.addWidget(ps_btn_close)
        ps_v.addLayout(ps_hdr)

        # 종목/행사가 표시
        ps_info_row = QHBoxLayout()
        self._ps_lbl_sym = QLabel("―")
        self._ps_lbl_sym.setStyleSheet(
            "color:#ffd700;font-size:13px;font-weight:bold;border:none;")
        ps_info_row.addWidget(QLabel("종목:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_info_row.addWidget(self._ps_lbl_sym); ps_info_row.addStretch()
        ps_v.addLayout(ps_info_row)

        # 수량 행
        ps_qty_row = QHBoxLayout()
        self._ps_qty = QSpinBox()
        self._ps_qty.setRange(1, 9999); self._ps_qty.setValue(1)
        self._ps_qty.setFixedHeight(24)
        self._ps_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #6b1a1a;font-size:13px;")
        ps_qty_row.addWidget(QLabel("수량:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_qty_row.addWidget(self._ps_qty); ps_qty_row.addStretch()
        ps_v.addLayout(ps_qty_row)

        # 가격 행
        ps_price_row = QHBoxLayout()
        self._ps_price = QLineEdit()
        self._ps_price.setPlaceholderText("지정가 (비워두면 시장가)")
        self._ps_price.setFixedHeight(24)
        self._ps_price.setStyleSheet(
            "color:#ffd700;font-size:13px;"
            "background:#0a0a1e;border:1px solid #6b1a1a;")
        ps_price_row.addWidget(QLabel("가격:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_price_row.addWidget(self._ps_price)
        ps_v.addLayout(ps_price_row)

        # 매도 버튼
        ps_btn_sell = QPushButton("▼ 매도 주문 전송")
        ps_btn_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:14px;"
            "font-weight:bold;padding:8px;border-radius:4px;")
        ps_btn_sell.clicked.connect(self._pos_sell_execute)
        ps_v.addWidget(ps_btn_sell)

        gb_v.addWidget(self._pos_sell_panel)
        return gb

    # ─────────────────────────────────────────────────────
    # 수수료 예상 계산 (IBKR 기준: $0.65/계약, 최소 $1.00)
    # ─────────────────────────────────────────────────────
    def _update_commission_label(self, qty: int = 1):
        """수량 변경 시 IBKR 옵션 수수료 예상액 계산 및 표시."""
        RATE_PER_CONTRACT = 0.65   # USD
        MIN_FEE           = 1.00   # USD
        fee = max(qty * RATE_PER_CONTRACT, MIN_FEE)
        self.lbl_commission.setText(
            f"예상 수수료: ${fee:.2f}  ({qty}계약 × $0.65)"
        )

    # ─────────────────────────────────────────────────────
    # 지정가/시장가 토글
    # ─────────────────────────────────────────────────────
    def _on_qord_type_toggle(self):
        is_lmt = self.qord_lmt.isChecked()
        self.qord_price.setEnabled(is_lmt)
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;"
            if is_lmt else
            "color:#555;font-weight:bold;font-size:15px;"
            "background:#070710;border:1px solid #222;")

    # ─────────────────────────────────────────────────────
    # 미체결 주문 조회
    # ─────────────────────────────────────────────────────
    def _fetch_open_orders(self):
        from PyQt5.QtWidgets import QMessageBox
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        self._open_orders_buf = []
        ib = self.mw.ib

        def _on_open_order(orderId, contract, order, orderState):
            self._open_orders_buf.append({
                "oid":      orderId,
                "symbol":   getattr(contract,"localSymbol","") or
                            getattr(contract,"symbol",""),
                "action":   getattr(order,"action",""),
                "price":    getattr(order,"lmtPrice",0.0),
                "qty":      getattr(order,"totalQuantity",0),
                "type":     getattr(order,"orderType",""),
                "tif":      getattr(order,"tif","DAY"),   # ✅ 정정 시 TIF 유지용
                "contract": contract,   # ✅ 정정 시 재사용
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
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush
        from tab_options import _mk
        orders = getattr(self, '_open_orders_buf', [])
        for tbl in (self.tbl_open_orders_a, self.tbl_open_orders_c):
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
        oid_item = tbl.item(row, 0); prc_item = tbl.item(row, 3)
        dir_item = tbl.item(row, 2)
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
    # ─────────────────────────────────────────────────────
    # 잔고 청산 매도 패널 제어
    # ─────────────────────────────────────────────────────
    def _show_pos_sell_panel(self, side: str, strike: str,
                              qty: int = 1, price: float = None):
        """테이블 잔고 컬럼 클릭 시 호출. 매도 패널을 채워서 표시."""
        label = "CALL" if side == "C" else "PUT"
        self._ps_lbl_title.setText(f"▼ 잔고 청산 매도  [{label}]")
        self._ps_lbl_sym.setText(f"{label}  {strike}")
        self._ps_qty.setValue(max(1, qty))
        self._ps_price.setText(f"{price:.2f}" if price else "")
        self._ps_side   = side
        self._ps_strike = strike
        self._pos_sell_panel.setVisible(True)

    def _pos_sell_execute(self):
        """잔고 매도 패널에서 매도 주문 전송."""
        side   = getattr(self, '_ps_side',   None)
        strike = getattr(self, '_ps_strike', None)
        if not side or not strike:
            self._log("⚠ 매도 대상이 없습니다. 테이블 잔고를 다시 클릭하세요."); return
        price_txt = self._ps_price.text().strip()
        self._qord_fill(side, strike,
                        float(price_txt) if price_txt else None,
                        source="← 잔고 청산")
        self.qord_qty.setValue(self._ps_qty.value())
        self._pos_sell_panel.setVisible(False)
        self._qord_place("SELL")