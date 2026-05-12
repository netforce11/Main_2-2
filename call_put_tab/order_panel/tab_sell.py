"""
order_panel/tab_sell.py — 탭4 「▼ 빠른매도」 UI 빌드
════════════════════════════════════════════════════
포함:
  build_sell_tab(mixin, tab_w) → 빠른매도 탭 위젯을 tab_w에 추가
    - bump 버튼 (+0.05 / +0.10 / -0.05 / -0.10)
    - 매도가격·수량 입력
    - Bid가 즉시매도(LMT) 버튼
    - 지정가 매도 전송 버튼
    - 상태 라벨
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
)
from PyQt5.QtCore import Qt


def build_sell_tab(m, tab_w) -> None:
    """빠른매도 탭 위젯을 생성하여 tab_w에 추가."""
    sell_w = QWidget()
    sv = QVBoxLayout(sell_w); sv.setSpacing(4); sv.setContentsMargins(8, 2, 8, 8)

    # ── bump 버튼 ────────────────────────────────────────────
    _sell_up = ("QPushButton{background:#1a3a1a;color:#00cc66;font-size:12px;"
                "font-weight:bold;border:1px solid #2a6a2a;border-radius:3px;}"
                "QPushButton:hover{background:#2a5a2a;}")
    _sell_dn = ("QPushButton{background:#3a1a1a;color:#ff6666;font-size:12px;"
                "font-weight:bold;border:1px solid #6a2a2a;border-radius:3px;}"
                "QPushButton:hover{background:#5a2a2a;}")
    bump_row = QHBoxLayout(); bump_row.setSpacing(3)
    for lbl3, delta, st2 in [("+0.05", +0.05, _sell_dn), ("+0.10", +0.10, _sell_dn),
                              ("-0.05", -0.05, _sell_up), ("-0.10", -0.10, _sell_up)]:
        b2 = QPushButton(lbl3); b2.setFixedHeight(26); b2.setStyleSheet(st2)
        b2.clicked.connect(lambda _, d=delta: m._bump_sell_price(d))
        bump_row.addWidget(b2)
    sv.addLayout(bump_row)

    sep = QLabel(); sep.setFixedHeight(1)
    sep.setStyleSheet("background:#3a1a1a;border:none;")
    sv.addWidget(sep)

    # ── 가격·수량 ────────────────────────────────────────────
    _ls = "color:#aaa;font-size:13px;border:none;"
    sell_gl = QGridLayout(); sell_gl.setSpacing(4)

    m.sell_price = QLineEdit(); m.sell_price.setPlaceholderText("매도가격")
    m.sell_price.setStyleSheet(
        "color:#ff9999;font-weight:bold;font-size:15px;"
        "background:#0a0a1e;border:1px solid #6a2a2a;")

    sell_qty_w = QWidget(); sell_qty_h = QHBoxLayout(sell_qty_w)
    sell_qty_h.setContentsMargins(0, 0, 0, 0); sell_qty_h.setSpacing(3)
    m.sell_qty = QSpinBox(); m.sell_qty.setRange(1, 9999); m.sell_qty.setValue(1)
    m.sell_qty.setFixedHeight(26)
    m.sell_qty.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #6a2a2a;font-size:14px;")
    sell_qty_h.addWidget(m.sell_qty)

    sell_gl.addWidget(QLabel("매도가격:", styleSheet=_ls), 0, 0)
    sell_gl.addWidget(m.sell_price, 0, 1)
    sell_gl.addWidget(QLabel("수량:", styleSheet=_ls), 1, 0)
    sell_gl.addWidget(sell_qty_w, 1, 1)
    sv.addLayout(sell_gl)

    # ── 매도 버튼 2개 ────────────────────────────────────────
    btn_sell_mkt = QPushButton("▼ Bid가 즉시 매도 (LMT)")
    btn_sell_mkt.setFixedHeight(40); btn_sell_mkt.setMaximumHeight(40)
    btn_sell_mkt.setStyleSheet(
        "QPushButton{background:#8b0000;color:#ff4444;font-size:15px;"
        "font-weight:bold;border-radius:4px;border:2px solid #ff4444;}"
        "QPushButton:hover{background:#aa1a1a;}"
        "QPushButton:pressed{background:#5a0000;}")
    btn_sell_mkt.clicked.connect(m._sell_selected_order)
    sv.addWidget(btn_sell_mkt)

    btn_sell_lmt = QPushButton("▼ 지정가 매도 전송")
    btn_sell_lmt.setFixedHeight(36); btn_sell_lmt.setMaximumHeight(36)
    btn_sell_lmt.setStyleSheet(
        "QPushButton{background:#6b1a1a;color:#ff9999;font-size:14px;"
        "font-weight:bold;border-radius:4px;border:1px solid #9a2a2a;}"
        "QPushButton:hover{background:#8b2a2a;}"
        "QPushButton:pressed{background:#4b0a0a;}")
    btn_sell_lmt.clicked.connect(m._sell_limit_order)
    sv.addWidget(btn_sell_lmt)

    m.lbl_sell_status = QLabel("잔고창(📊 잔고) 행 클릭 → 자동입력 후 매도")
    m.lbl_sell_status.setAlignment(Qt.AlignCenter)
    m.lbl_sell_status.setStyleSheet(
        "color:#888;font-size:12px;border:1px solid #333;border-radius:3px;padding:2px;")
    sv.addWidget(m.lbl_sell_status)
    sv.addStretch()
    tab_w.addTab(sell_w, "▼ 빠른매도")
