"""order_panel_tabs.py — OrderTabsMixin: tab builder methods  [NEW S6]
신규탭/_build_amend_tab/_build_cancel_tab/_build_sell_tab/잔고/pos_sell/util
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QComboBox, QRadioButton, QButtonGroup,
    QSpinBox, QCheckBox, QGroupBox, QFrame,
    QTableWidget, QHeaderView, QAbstractItemView, QMessageBox,
)
from PyQt5.QtCore import Qt

from order_panel import _make_order_tbl, _LS, _ES, _FETCH_S, _TBL_S
from order_panel import _BUMP_UP, _BUMP_DN, _SELL_UP, _SELL_DN


class OrderTabsMixin:
    """Tab builder methods for OrderPanelMixin."""
    # ── 신규 탭 ───────────────────────────────────────────────
    def _build_new_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        # 대상 행
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
        tgt_row.addWidget(self.qord_side); tgt_row.addWidget(self.qord_strike)
        tgt_row.addStretch()
        v.addLayout(tgt_row)

        self.lbl_qord_src = QLabel("")
        self.lbl_qord_src.setStyleSheet("color:#ff8800;font-size:12px;border:none;")
        self.lbl_qord_src.setWordWrap(True)
        v.addWidget(self.lbl_qord_src)

        sep = QLabel(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:#333;border:none;")
        v.addWidget(sep)

        # 유형/가격/수량 그리드
        gl = QGridLayout(); gl.setSpacing(4)

        type_w = QWidget(); type_h = QHBoxLayout(type_w)
        type_h.setContentsMargins(0,0,0,0); type_h.setSpacing(6)
        self.qord_lmt = QRadioButton("지정가"); self.qord_mkt = QRadioButton("시장가")
        self.qord_lmt.setChecked(True)
        for rb in (self.qord_lmt, self.qord_mkt):
            rb.setStyleSheet("color:#ffd700;font-size:13px;")
        qord_grp = QButtonGroup(self)
        qord_grp.addButton(self.qord_lmt); qord_grp.addButton(self.qord_mkt)
        self.qord_lmt.toggled.connect(self._on_qord_type_toggle)
        type_h.addWidget(self.qord_lmt); type_h.addWidget(self.qord_mkt)
        type_h.addStretch()

        _abtn = ("QPushButton{background:#1a2a3a;color:#90caf9;font-size:12px;"
                 "font-weight:bold;padding:1px 5px;border-radius:3px;"
                 "border:1px solid #2a4a6a;}QPushButton:hover{background:#2a3a5a;}")
        self.btn_qty_max = QPushButton("MAX"); self.btn_qty_200 = QPushButton("$200")
        self.btn_qty_max.setFixedSize(38, 22); self.btn_qty_200.setFixedSize(38, 22)
        self.btn_qty_max.setStyleSheet(_abtn); self.btn_qty_200.setStyleSheet(_abtn)
        self.btn_qty_max.setToolTip("최대 수량 자동 계산")
        self.btn_qty_200.setToolTip("$200 기준 수량 자동 계산")
        self.btn_qty_max.clicked.connect(self._calc_qty_max)
        self.btn_qty_200.clicked.connect(self._calc_qty_200)
        type_h.addWidget(self.btn_qty_max); type_h.addWidget(self.btn_qty_200)

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
        _qs = ("QPushButton{background:#2d2d5e;color:#ffd700;"
               "border:1px solid #4a4a8a;border-radius:3px;"
               "font-size:13px;font-weight:bold;}"
               "QPushButton:hover{background:#3d4d6e;}")
        for lbl2, v2 in [("1",1),("5",5),("10",10)]:
            bq = QPushButton(lbl2); bq.setFixedSize(28, 26); bq.setStyleSheet(_qs)
            bq.clicked.connect(lambda _, vv=v2: self.qord_qty.setValue(vv))
            qty_h.addWidget(bq)
        qty_h.insertWidget(0, self.qord_qty)

        gl.addWidget(QLabel("유형:", styleSheet=_LS), 0, 0); gl.addWidget(type_w, 0, 1)
        gl.addWidget(QLabel("가격:", styleSheet=_LS), 1, 0); gl.addWidget(self.qord_price, 1, 1)
        gl.addWidget(QLabel("수량:", styleSheet=_LS), 2, 0); gl.addWidget(qty_w, 2, 1)
        v.addLayout(gl)

        self.lbl_commission = QLabel("")
        self.lbl_commission.setStyleSheet(
            "color:#FFA500;font-size:13px;border:none;"
            "background:#0d0d20;padding:2px 4px;border-radius:3px;")
        self.lbl_commission.setAlignment(Qt.AlignRight)
        v.addWidget(self.lbl_commission)
        self.qord_qty.valueChanged.connect(self._update_commission_label)
        self._update_commission_label(self.qord_qty.value())

        tif_row = QHBoxLayout()
        tif_row.addWidget(QLabel("TIF:", styleSheet=_LS))
        self.qord_tif = QComboBox(); self.qord_tif.addItems(["DAY","GTC","IOC","GTD"])
        self.qord_tif.setFixedHeight(24)
        self.qord_tif.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:13px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
            "QComboBox::drop-down{border:none;}")
        tif_row.addWidget(self.qord_tif); tif_row.addStretch()
        v.addLayout(tif_row)

        # 매수/매도 버튼
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self.btn_qord_buy = QPushButton("▲ 매수")
        self.btn_qord_buy.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:16px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_buy.clicked.connect(lambda: self._qord_place_validated("BUY"))
        self.btn_qord_sell = QPushButton("▼ 매도")
        self.btn_qord_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:16px;"
            "font-weight:bold;padding:10px 4px;border-radius:4px;")
        self.btn_qord_sell.clicked.connect(lambda: self._qord_place_validated("SELL"))
        btn_row.addWidget(self.btn_qord_buy, 1); btn_row.addWidget(self.btn_qord_sell, 1)
        v.addLayout(btn_row)

        self.lbl_qord_status = QLabel("대기 중")
        self.lbl_qord_status.setAlignment(Qt.AlignCenter)
        self.lbl_qord_status.setStyleSheet(
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        v.addWidget(self.lbl_qord_status)

        # 주문확인 체크 + 빠른가격정정
        confirm_row = QHBoxLayout()
        self.chk_order_confirm = QCheckBox("주문 확인창")
        self.chk_order_confirm.setChecked(True)
        self.chk_order_confirm.setToolTip("ON: 주문 전 확인 팝업 / OFF: 즉시 주문")
        self.chk_order_confirm.setStyleSheet(
            "QCheckBox{color:#90caf9;font-size:12px;}"
            "QCheckBox::indicator{width:14px;height:14px;}"
            "QCheckBox::indicator:checked{background:#1a4a6b;border:1px solid #90caf9;border-radius:2px;}"
            "QCheckBox::indicator:unchecked{background:#0a0a1e;border:1px solid #444;border-radius:2px;}")
        confirm_row.addStretch(); confirm_row.addWidget(self.chk_order_confirm)
        v.addLayout(confirm_row)

        v.addWidget(QLabel("빠른 가격 정정", styleSheet="color:#aaa;font-size:11px;border:none;"))
        bump_row = QHBoxLayout(); bump_row.setSpacing(3)
        for lbl, delta, st in [("+0.05",+0.05,_BUMP_UP),("+0.10",+0.10,_BUMP_UP),
                                ("-0.05",-0.05,_BUMP_DN),("-0.10",-0.10,_BUMP_DN)]:
            b = QPushButton(lbl); b.setFixedHeight(24); b.setStyleSheet(st)
            b.clicked.connect(lambda _, d=delta: self._bump_price_and_amend(d))
            bump_row.addWidget(b)
        v.addLayout(bump_row)

        self.lbl_bump_status = QLabel("")
        self.lbl_bump_status.setAlignment(Qt.AlignCenter)
        self.lbl_bump_status.setStyleSheet("color:#666;font-size:11px;border:none;")
        v.addWidget(self.lbl_bump_status)

        # [S6] 잔고 패널 인라인 (신규 탭 하단)
        v.addWidget(self._build_inline_position_panel())
        return w

    # ── 정정 탭 ───────────────────────────────────────────────
    def _build_amend_tab(self) -> QWidget:
        w = QWidget()
        av = QVBoxLayout(w); av.setSpacing(5); av.setContentsMargins(8,8,8,8)

        btn_fetch = QPushButton("📋 미체결 주문 조회")
        btn_fetch.setStyleSheet(_FETCH_S)
        btn_fetch.clicked.connect(self._fetch_open_orders)
        av.addWidget(btn_fetch)

        self.tbl_open_orders_a = _make_order_tbl("#1a3a6b")
        self.tbl_open_orders_a.cellClicked.connect(
            lambda r, c: self._fill_amend_from_table(r))
        av.addWidget(self.tbl_open_orders_a)

        av.addWidget(QLabel("주문 ID:", styleSheet=_LS))
        self.amend_oid = QLineEdit()
        self.amend_oid.setPlaceholderText("목록 클릭 or 직접 입력")
        self.amend_oid.setStyleSheet(_ES); self.amend_oid.setFixedHeight(26)
        av.addWidget(self.amend_oid)

        av.addWidget(QLabel("새 가격:", styleSheet=_LS))
        self.amend_price = QLineEdit()
        self.amend_price.setPlaceholderText("새 지정가")
        self.amend_price.setStyleSheet(_ES); self.amend_price.setFixedHeight(26)
        av.addWidget(self.amend_price)

        av.addWidget(QLabel("새 수량:", styleSheet=_LS))
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
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        av.addWidget(self.lbl_amend_status)
        av.addStretch()
        return w

    # ── 취소 탭 ───────────────────────────────────────────────
    def _build_cancel_tab(self) -> QWidget:
        w = QWidget()
        cv = QVBoxLayout(w); cv.setSpacing(5); cv.setContentsMargins(8,8,8,8)

        btn_fetch = QPushButton("📋 미체결 주문 조회")
        btn_fetch.setStyleSheet(_FETCH_S)
        btn_fetch.clicked.connect(self._fetch_open_orders)
        cv.addWidget(btn_fetch)

        self.tbl_open_orders_c = _make_order_tbl("#3a1a1a")
        self.tbl_open_orders_c.setStyleSheet(
            _TBL_S + "QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
        self.tbl_open_orders_c.cellClicked.connect(
            lambda r, c: self._fill_cancel_from_table(r))
        cv.addWidget(self.tbl_open_orders_c)

        cv.addWidget(QLabel("주문 ID:", styleSheet=_LS))
        self.cancel_oid = QLineEdit()
        self.cancel_oid.setPlaceholderText("목록 클릭 or 직접 입력")
        self.cancel_oid.setStyleSheet(_ES); self.cancel_oid.setFixedHeight(26)
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
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        cv.addWidget(self.lbl_cancel_status)
        cv.addStretch()
        return w

    # ── [S6] 빠른매도 탭 ──────────────────────────────────────
    def _build_sell_tab(self) -> QWidget:
        """빠른 매도 전용 탭: 미체결 주문 기준 즉시 매도 + 가격 bump."""
        w = QWidget()
        sv = QVBoxLayout(w); sv.setSpacing(6); sv.setContentsMargins(8,8,8,8)

        sv.addWidget(QLabel("📋 미체결 주문 → 선택 후 매도 정정",
            styleSheet="color:#ff8800;font-size:12px;font-weight:bold;border:none;"))

        btn_fetch = QPushButton("📋 미체결 주문 조회")
        btn_fetch.setStyleSheet(_FETCH_S)
        btn_fetch.clicked.connect(self._fetch_open_orders)
        sv.addWidget(btn_fetch)

        self.tbl_open_orders_s = _make_order_tbl("#3a1a1a")
        self.tbl_open_orders_s.setStyleSheet(
            _TBL_S + "QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
        self.tbl_open_orders_s.cellClicked.connect(
            lambda r, c: self._fill_sell_from_table(r))
        sv.addWidget(self.tbl_open_orders_s)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none;background:#3a1a1a;max-height:1px;")
        sv.addWidget(sep)

        sv.addWidget(QLabel("빠른 매도 가격 조정",
            styleSheet="color:#aaa;font-size:11px;border:none;"))

        # +0.05 / +0.10 → 가격 올려서 매도 (더 비싸게)
        # -0.05 / -0.10 → 가격 내려서 매도 (더 싸게 = 빠른 체결)
        sell_bump_row = QHBoxLayout(); sell_bump_row.setSpacing(3)
        for lbl, delta, st, tip in [
            ("+0.05", +0.05, _SELL_DN, "매도가 +0.05 (더 비싸게)"),
            ("+0.10", +0.10, _SELL_DN, "매도가 +0.10 (더 비싸게)"),
            ("-0.05", -0.05, _SELL_UP, "매도가 -0.05 (빠른 체결)"),
            ("-0.10", -0.10, _SELL_UP, "매도가 -0.10 (빠른 체결)"),
        ]:
            b = QPushButton(lbl); b.setFixedHeight(26); b.setStyleSheet(st)
            b.setToolTip(tip)
            b.clicked.connect(lambda _, d=delta: self._bump_sell_price(d))
            sell_bump_row.addWidget(b)
        sv.addLayout(sell_bump_row)

        sv.addWidget(QLabel("선택 주문 즉시 매도",
            styleSheet="color:#aaa;font-size:11px;border:none;"))

        btn_sell_now = QPushButton("▼ 선택 주문 즉시 매도 전송")
        btn_sell_now.setFixedHeight(40)
        btn_sell_now.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff6666;font-size:15px;"
            "font-weight:bold;border-radius:4px;border:1px solid #9a2a2a;}"
            "QPushButton:hover{background:#8b2a2a;}")
        btn_sell_now.clicked.connect(self._sell_selected_order)
        sv.addWidget(btn_sell_now)

        self.lbl_sell_status = QLabel("미체결 주문 조회 후 행 선택 → 매도")
        self.lbl_sell_status.setAlignment(Qt.AlignCenter)
        self.lbl_sell_status.setStyleSheet(
            "color:#888;font-size:12px;border:1px solid #333;border-radius:3px;padding:2px;")
        sv.addWidget(self.lbl_sell_status)
        sv.addStretch()
        return w

