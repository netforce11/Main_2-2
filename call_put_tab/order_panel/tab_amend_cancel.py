"""
order_panel/tab_amend_cancel.py — 탭2 「✏ 정정」 / 탭3 「✕ 취소」 UI 빌드
════════════════════════════════════════════════════════════════════════
포함:
  build_amend_tab(mixin, tab_w)  → 정정 탭 위젯을 tab_w에 추가
  build_cancel_tab(mixin, tab_w) → 취소 탭 위젯을 tab_w에 추가
  _make_order_tbl(tbl_s)         → 공통 미체결 주문 테이블 생성
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QTableWidget, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt

from .helpers import _animate_press, _kst_now

_TBL_S = (
    "QTableWidget{background:#05050f;color:#ccc;"
    "gridline-color:#1a1a3a;font-size:13px;}"
    "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
    "border:1px solid #1a1a3a;font-size:12px;}"
    "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}"
)
_ES      = "background:#0a0a1e;color:#ffd700;border:1px solid #444;font-size:15px;"
_LS      = "color:#aaa;font-size:13px;border:none;"
_FETCH_S = ("background:#1a3a1a;color:#00ff88;font-size:13px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")


def _make_order_tbl(sel_color: str = "#1a3a6b") -> QTableWidget:
    tbl = QTableWidget(0, 4)
    tbl.setHorizontalHeaderLabels(["OID", "종목", "방향", "가격"])
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setMaximumHeight(110)
    tbl.setStyleSheet(_TBL_S.replace("#1a3a6b", sel_color))
    return tbl


def build_amend_tab(m, tab_w) -> None:
    """정정 탭 위젯을 생성하여 tab_w에 추가."""
    amend_w = QWidget()
    av = QVBoxLayout(amend_w); av.setSpacing(5); av.setContentsMargins(8, 8, 8, 8)

    ah = QHBoxLayout()
    btn_fetch_a = QPushButton("📋 미체결 주문 조회"); btn_fetch_a.setStyleSheet(_FETCH_S)
    btn_fetch_a.clicked.connect(lambda: (
        _animate_press(btn_fetch_a), m._fetch_open_orders()))
    ah.addWidget(btn_fetch_a, 1)
    m.lbl_amend_time = QLabel(_kst_now())
    m.lbl_amend_time.setStyleSheet(
        "color:#5dade2;font-size:13px;font-weight:bold;border:none;")
    ah.addWidget(m.lbl_amend_time)
    av.addLayout(ah)

    m.tbl_open_orders_a = _make_order_tbl("#1a3a6b")
    m.tbl_open_orders_a.cellClicked.connect(lambda r, c: m._fill_amend_from_table(r))
    av.addWidget(m.tbl_open_orders_a)

    av.addWidget(QLabel("주문 ID:", styleSheet=_LS))
    m.amend_oid = QLineEdit(); m.amend_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
    m.amend_oid.setStyleSheet(_ES); m.amend_oid.setFixedHeight(26); av.addWidget(m.amend_oid)

    av.addWidget(QLabel("새 가격:", styleSheet=_LS))
    m.amend_price = QLineEdit(); m.amend_price.setPlaceholderText("새 지정가")
    m.amend_price.setStyleSheet(_ES); m.amend_price.setFixedHeight(26); av.addWidget(m.amend_price)

    av.addWidget(QLabel("새 수량:", styleSheet=_LS))
    m.amend_qty = QSpinBox(); m.amend_qty.setRange(1, 9999); m.amend_qty.setValue(1)
    m.amend_qty.setFixedHeight(26)
    m.amend_qty.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:15px;")
    av.addWidget(m.amend_qty)

    btn_amend = QPushButton("✏ 정정 전송")
    btn_amend.setStyleSheet(
        "QPushButton{background:#1a4a6b;color:#90caf9;font-size:15px;"
        "font-weight:bold;padding:8px;border-radius:4px;}"
        "QPushButton:pressed{background:#0a2a4b;padding-top:10px;padding-bottom:6px;}")
    btn_amend.clicked.connect(lambda: (_animate_press(btn_amend), m._amend_order()))
    av.addWidget(btn_amend)

    m.lbl_amend_status = QLabel("대기 중")
    m.lbl_amend_status.setAlignment(Qt.AlignCenter)
    m.lbl_amend_status.setStyleSheet(
        "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
    av.addWidget(m.lbl_amend_status)
    av.addStretch()
    tab_w.addTab(amend_w, "✏ 정정")


def build_cancel_tab(m, tab_w) -> None:
    """취소 탭 위젯을 생성하여 tab_w에 추가."""
    cancel_w = QWidget()
    cv = QVBoxLayout(cancel_w); cv.setSpacing(5); cv.setContentsMargins(8, 8, 8, 8)

    ch = QHBoxLayout()
    btn_fetch_c = QPushButton("📋 미체결 주문 조회"); btn_fetch_c.setStyleSheet(_FETCH_S)
    btn_fetch_c.clicked.connect(lambda: (
        _animate_press(btn_fetch_c), m._fetch_open_orders()))
    ch.addWidget(btn_fetch_c, 1)
    m.lbl_cancel_time = QLabel(_kst_now())
    m.lbl_cancel_time.setStyleSheet(
        "color:#5dade2;font-size:13px;font-weight:bold;border:none;")
    ch.addWidget(m.lbl_cancel_time)
    cv.addLayout(ch)

    m.tbl_open_orders_c = _make_order_tbl("#3a1a1a")
    m.tbl_open_orders_c.setStyleSheet(
        _TBL_S + "QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
    m.tbl_open_orders_c.cellClicked.connect(lambda r, c: m._fill_cancel_from_table(r))
    cv.addWidget(m.tbl_open_orders_c)

    cv.addWidget(QLabel("주문 ID:", styleSheet=_LS))
    m.cancel_oid = QLineEdit(); m.cancel_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
    m.cancel_oid.setStyleSheet(_ES); m.cancel_oid.setFixedHeight(26); cv.addWidget(m.cancel_oid)

    btn_cancel = QPushButton("✕ 취소 전송")
    btn_cancel.setStyleSheet(
        "QPushButton{background:#6b1a1a;color:#ff6666;font-size:15px;"
        "font-weight:bold;padding:10px;border-radius:4px;}"
        "QPushButton:pressed{background:#4b0a0a;padding-top:12px;padding-bottom:8px;}")
    btn_cancel.clicked.connect(lambda: (_animate_press(btn_cancel), m._cancel_order()))
    cv.addWidget(btn_cancel)

    m.lbl_cancel_status = QLabel("대기 중")
    m.lbl_cancel_status.setAlignment(Qt.AlignCenter)
    m.lbl_cancel_status.setStyleSheet(
        "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
    cv.addWidget(m.lbl_cancel_status)

    sep_gc = QLabel(); sep_gc.setFixedHeight(1)
    sep_gc.setStyleSheet("background:#5a2a2a;border:none;margin-top:4px;")
    cv.addWidget(sep_gc)

    btn_global_cancel = QPushButton("🚨 전체 주문 강제 취소 (reqGlobalCancel)")
    btn_global_cancel.setFixedHeight(38)
    btn_global_cancel.setStyleSheet(
        "QPushButton{background:#8B0000;color:#ffffff;font-size:13px;"
        "font-weight:bold;border-radius:4px;border:1px solid #cc2222;}"
        "QPushButton:hover{background:#aa0000;}"
        "QPushButton:pressed{background:#660000;}")
    btn_global_cancel.setToolTip(
        "현재 API 세션의 모든 미체결 주문을 즉시 취소합니다.\n"
        "TWS UI 상태와 무관하게 서버에 직접 전달됩니다.")
    btn_global_cancel.clicked.connect(m._on_global_cancel)
    cv.addWidget(btn_global_cancel)

    cv.addStretch()
    tab_w.addTab(cancel_w, "✕ 취소")
