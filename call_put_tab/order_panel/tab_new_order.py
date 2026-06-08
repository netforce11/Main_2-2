"""
order_panel/tab_new_order.py — 탭1 「⚡ 신규」 UI 빌드
════════════════════════════════════════════════════════
[수정] 가격·수량·TIF 한 줄 압축 / 예상 수수료 라벨 제거
포함:
  build_new_order_tab(mixin) → QWidget
    상단: 대상(side/strike) + 주문확인 + 계좌모드
    중단: 유형·어댑티브·MAX/$200 / 가격|수량|TIF 한 줄
    하단: 매수/매도·+1호가·긴급매도 버튼 (tab_new_order_buttons.py)
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QRadioButton, QButtonGroup, QSpinBox, QCheckBox,
)
from PyQt5.QtCore import Qt
from .helpers import _animate_press
from .tab_new_order_buttons import build_new_order_buttons


def build_new_order_tab(m) -> QWidget:
    """신규 주문 탭 위젯 전체를 생성하여 반환."""
    new_w  = QWidget()
    root_v = QVBoxLayout(new_w)
    root_v.setSpacing(4); root_v.setContentsMargins(6, 6, 6, 4)

    # ── 대상 행 ─────────────────────────────────────────────
    tgt_row = QHBoxLayout()
    tgt_row.addWidget(QLabel("대상:"))
    m.qord_side = QLineEdit(); m.qord_side.setReadOnly(True); m.qord_side.setFixedWidth(28)
    m.qord_side.setStyleSheet(
        "color:#ffd700;font-weight:bold;font-size:15px;"
        "background:#0a0a1e;border:1px solid #333;")
    m.qord_strike = QLineEdit(); m.qord_strike.setReadOnly(True); m.qord_strike.setFixedWidth(62)
    m.qord_strike.setStyleSheet(
        "color:#ffd700;font-weight:bold;font-size:15px;"
        "background:#0a0a1e;border:1px solid #333;")
    tgt_row.addWidget(m.qord_side); tgt_row.addWidget(m.qord_strike)
    m.chk_order_confirm = QCheckBox("주문확인"); m.chk_order_confirm.setChecked(True)
    m.chk_order_confirm.setStyleSheet(
        "QCheckBox{color:#aaa;font-size:12px;spacing:4px;}"
        "QCheckBox::indicator{width:14px;height:14px;"
        "border:1px solid #555;border-radius:3px;background:#0a0a1e;}"
        "QCheckBox::indicator:checked{background:#1a5c2e;border:1px solid #00ff88;}"
        "QCheckBox::indicator:checked:hover{background:#2a7c3e;}")
    m.chk_order_confirm.setToolTip("체크: 주문 전 확인창 표시\n미체크: 바로 주문 전송")
    m.chk_order_confirm.toggled.connect(
        lambda on: setattr(m, '_skip_order_confirm', not on))
    tgt_row.addWidget(m.chk_order_confirm)
    m.lbl_acct_mode = QLabel("계좌: ―")
    m.lbl_acct_mode.setStyleSheet(
        "color:#666;font-size:11px;font-weight:bold;border:none;"
        "background:#0a0a1e;border-radius:3px;padding:1px 5px;")
    m.lbl_acct_mode.setToolTip("연결된 계좌번호 / 모드 (DU=모의투자)")
    tgt_row.addStretch(); tgt_row.addWidget(m.lbl_acct_mode)
    root_v.addLayout(tgt_row)

    m.lbl_qord_src = QLabel("")
    m.lbl_qord_src.setStyleSheet("color:#ff8800;font-size:12px;border:none;")
    m.lbl_qord_src.setWordWrap(True)
    root_v.addWidget(m.lbl_qord_src)

    line = QLabel(); line.setFixedHeight(1); line.setStyleSheet("background:#333;border:none;")
    root_v.addWidget(line)

    # ── 유형 + 어댑티브 + MAX/$200 ──────────────────────────
    _ls = "color:#aaa;font-size:13px;border:none;"
    type_w = QWidget(); type_h = QHBoxLayout(type_w)
    type_h.setContentsMargins(0, 0, 0, 0); type_h.setSpacing(6)
    m.qord_lmt = QRadioButton("지정가"); m.qord_mkt = QRadioButton("시장가")
    m.qord_lmt.setChecked(True)
    m.qord_lmt.setStyleSheet("color:#ffd700;font-size:13px;")
    m.qord_mkt.setStyleSheet("color:#ffd700;font-size:13px;")
    qord_grp = QButtonGroup(m); qord_grp.addButton(m.qord_lmt); qord_grp.addButton(m.qord_mkt)
    m.qord_lmt.toggled.connect(m._on_qord_type_toggle)
    type_h.addWidget(m.qord_lmt); type_h.addWidget(m.qord_mkt)

    m.lbl_adapt_dot = QLabel("●"); m.lbl_adapt_dot.setFixedWidth(12)
    m.lbl_adapt_dot.setStyleSheet("color:#1a1a3a;font-size:10px;border:none;")
    m.chk_adaptive = QCheckBox("어댑티브")
    m.chk_adaptive.setStyleSheet(
        "QCheckBox{color:#a0c4ff;font-size:12px;font-weight:bold;spacing:3px;}"
        "QCheckBox::indicator{width:13px;height:13px;"
        "border:1px solid #4a6a9a;border-radius:2px;background:#0a0a1e;}"
        "QCheckBox::indicator:checked{background:#3060cc;border:1px solid #60a0ff;}")
    m.chk_adaptive.setToolTip(
        "IBKR Adaptive Algorithm 사용\nNormal: 체결률 우선  |  Urgent: 속도 우선")
    m.combo_adapt_priority = QComboBox()
    m.combo_adapt_priority.addItems(["Normal", "Urgent"])
    m.combo_adapt_priority.setFixedHeight(22); m.combo_adapt_priority.setFixedWidth(64)
    m.combo_adapt_priority.setEnabled(False)
    m.combo_adapt_priority.setStyleSheet(
        "QComboBox{background:#0d0d22;color:#a0c4ff;border:1px solid #2a4a6a;"
        "font-size:11px;padding:1px 3px;}"
        "QComboBox QAbstractItemView{background:#0d0d22;color:#a0c4ff;font-size:11px;}"
        "QComboBox::drop-down{border:none;width:10px;}"
        "QComboBox:disabled{color:#4a6a8a;border:1px solid #1a2a4a;background:#08081a;}")
    def _on_adpt_toggle(checked):
        m.combo_adapt_priority.setEnabled(checked)
        m.lbl_adapt_dot.setStyleSheet(
            "color:#00ff88;font-size:10px;border:none;" if checked else
            "color:#1a1a3a;font-size:10px;border:none;")
    m.chk_adaptive.toggled.connect(_on_adpt_toggle)
    type_h.addSpacing(6)
    type_h.addWidget(m.lbl_adapt_dot); type_h.addWidget(m.chk_adaptive)
    type_h.addWidget(m.combo_adapt_priority); type_h.addStretch()

    _abtn_s = ("QPushButton{background:#1a2a3a;color:#90caf9;font-size:12px;"
               "font-weight:bold;padding:1px 5px;border-radius:3px;border:1px solid #2a4a6a;}"
               "QPushButton:hover{background:#2a3a5a;}"
               "QPushButton:pressed{background:#0a1a2a;}")
    m.btn_qty_max = QPushButton("MAX"); m.btn_qty_max.setFixedHeight(22); m.btn_qty_max.setFixedWidth(38)
    m.btn_qty_200 = QPushButton("$200"); m.btn_qty_200.setFixedHeight(22); m.btn_qty_200.setFixedWidth(38)
    m.btn_qty_max.setStyleSheet(_abtn_s); m.btn_qty_200.setStyleSheet(_abtn_s)
    m.btn_qty_max.clicked.connect(m._calc_qty_max)
    m.btn_qty_200.clicked.connect(m._calc_qty_200)
    type_h.addWidget(m.btn_qty_max); type_h.addWidget(m.btn_qty_200)
    root_v.addWidget(type_w)

    # ── 가격 | 수량 1,5,10 | TIF 한 줄 ─────────────────────
    _QS = ("QPushButton{background:#2d2d5e;color:#ffd700;"
           "border:1px solid #4a4a8a;border-radius:3px;font-size:13px;font-weight:bold;}"
           "QPushButton:hover{background:#3d4d6e;}"
           "QPushButton:pressed{background:#1d1d4e;}")

    compact_row = QHBoxLayout(); compact_row.setSpacing(4)

    # 가격
    m.qord_price = QLineEdit(); m.qord_price.setPlaceholderText("가격")
    m.qord_price.setFixedHeight(26); m.qord_price.setFixedWidth(80)
    m.qord_price.setStyleSheet(
        "color:#ffd700;font-weight:bold;font-size:14px;"
        "background:#0a0a1e;border:1px solid #444;")
    compact_row.addWidget(m.qord_price)

    # 구분선
    sep = QLabel("|"); sep.setStyleSheet("color:#444;border:none;font-size:14px;")
    compact_row.addWidget(sep)

    # 수량
    m.qord_qty = QSpinBox(); m.qord_qty.setRange(1, 9999); m.qord_qty.setValue(1)
    m.qord_qty.setFixedHeight(26); m.qord_qty.setFixedWidth(54)
    m.qord_qty.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:14px;")
    compact_row.addWidget(m.qord_qty)

    # 1, 5, 10 버튼
    for lbl2, v2 in [("1", 1), ("5", 5), ("10", 10)]:
        bq = QPushButton(lbl2); bq.setFixedWidth(28); bq.setFixedHeight(26)
        bq.setStyleSheet(_QS)
        bq.clicked.connect(lambda _, v=v2: m.qord_qty.setValue(v))
        compact_row.addWidget(bq)

    # 구분선
    sep2 = QLabel("|"); sep2.setStyleSheet("color:#444;border:none;font-size:14px;")
    compact_row.addWidget(sep2)

    # TIF
    tif_lbl = QLabel("TIF:"); tif_lbl.setStyleSheet(_ls)
    compact_row.addWidget(tif_lbl)
    m.qord_tif = QComboBox(); m.qord_tif.addItems(["DAY", "GTC", "IOC", "GTD"])
    m.qord_tif.setFixedHeight(26); m.qord_tif.setFixedWidth(58)
    m.qord_tif.setStyleSheet(
        "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
        "font-size:13px;padding:1px;}"
        "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
        "QComboBox::drop-down{border:none;}")
    compact_row.addWidget(m.qord_tif)
    compact_row.addStretch()

    root_v.addLayout(compact_row)

    # ── 예상 수수료 — 숨김 처리 (로직 유지, UI 제거) ────────
    m.lbl_commission = QLabel("")
    m.lbl_commission.setVisible(False)   # 화면에서 제거, 참조는 유지
    m.qord_qty.valueChanged.connect(m._update_commission_label)
    m._update_commission_label(m.qord_qty.value())

    # ── 버튼 영역 (별도 모듈) ────────────────────────────────
    build_new_order_buttons(m, root_v)

    # ── 잔고 인라인 패널 ─────────────────────────────────────
    root_v.addWidget(m._build_inline_position_panel())

    return new_w
