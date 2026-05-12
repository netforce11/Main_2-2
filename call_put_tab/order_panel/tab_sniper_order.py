"""
order_panel/tab_sniper_order.py — 스나이퍼 주문 설정·버튼·목록 빌드
════════════════════════════════════════════════════════════════
포함:
  build_sniper_order_section(mixin, sn_v)
    - 방향 / 유형 / 주문가 / 수량 입력
    - 등록/저장/전체해제 버튼
    - 활성 스나이퍼 테이블 + 상태 라벨
    - 스나이퍼 내부 상태 초기화 (dict/timer/load)
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QTableWidget, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer


def build_sniper_order_section(m, sn_v) -> None:
    """방향·유형·수량 입력, 등록/저장/해제 버튼, 목록 테이블을 sn_v에 추가."""
    _sn_ls = "color:#aaa;font-size:13px;border:none;"
    _sn_es = ("color:#ffd700;font-weight:bold;font-size:14px;"
              "background:#0a0a1e;border:1px solid #444;")
    _cmb13 = ("QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
              "font-size:13px;font-weight:bold;}"
              "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
              "QComboBox::drop-down{border:none;}")

    # ── 방향 / 유형 / 주문가 / 수량 ─────────────────────────
    sep2 = QLabel(); sep2.setFixedHeight(1)
    sep2.setStyleSheet("background:#2a2a4a;border:none;")
    sn_v.addWidget(sep2)

    sn_g3 = QGridLayout(); sn_g3.setSpacing(4)
    sn_g3.addWidget(QLabel("방향:", styleSheet=_sn_ls), 0, 0)
    m.snp_action = QComboBox(); m.snp_action.addItems(["BUY", "SELL"])
    m.snp_action.setStyleSheet(_cmb13); sn_g3.addWidget(m.snp_action, 0, 1)
    sn_g3.addWidget(QLabel("유형:", styleSheet=_sn_ls), 0, 2)
    m.snp_otype = QComboBox(); m.snp_otype.addItems(["LMT", "MKT"])
    m.snp_otype.setStyleSheet(_cmb13); sn_g3.addWidget(m.snp_otype, 0, 3)
    sn_g3.addWidget(QLabel("주문가:", styleSheet=_sn_ls), 1, 0)
    m.snp_oprice = QLineEdit(); m.snp_oprice.setPlaceholderText("LMT 가격 (MKT=생략)")
    m.snp_oprice.setStyleSheet(_sn_es); sn_g3.addWidget(m.snp_oprice, 1, 1)
    sn_g3.addWidget(QLabel("수량:", styleSheet=_sn_ls), 1, 2)
    m.snp_qty = QSpinBox(); m.snp_qty.setRange(1, 9999); m.snp_qty.setValue(1)
    m.snp_qty.setFixedHeight(26)
    m.snp_qty.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:13px;")
    sn_g3.addWidget(m.snp_qty, 1, 3)
    sn_v.addLayout(sn_g3)

    # ── 등록/저장/전체해제 버튼 ─────────────────────────────
    sn_btn_row = QHBoxLayout(); sn_btn_row.setSpacing(4)
    for lbl_txt, slot, style in [
        ("＋ 등록", m._sniper_add,
         "QPushButton{background:#1a6b3c;color:#00ff88;font-size:13px;"
         "font-weight:bold;padding:6px;border-radius:3px;}"
         "QPushButton:hover{background:#2a8b5c;}"
         "QPushButton:pressed{background:#0a4b1c;}"),
        ("💾 저장", m._sniper_save,
         "QPushButton{background:#1a3a6b;color:#90caf9;font-size:13px;"
         "font-weight:bold;padding:6px;border-radius:3px;}"
         "QPushButton:hover{background:#2a4a8b;}"
         "QPushButton:pressed{background:#0a2a4b;}"),
        ("🗑 전체해제", m._sniper_clear_all,
         "QPushButton{background:#6b1a1a;color:#ff6666;font-size:13px;"
         "font-weight:bold;padding:6px;border-radius:3px;}"
         "QPushButton:hover{background:#8b2a2a;}"
         "QPushButton:pressed{background:#4b0a0a;}"),
    ]:
        btn = QPushButton(lbl_txt); btn.setStyleSheet(style)
        btn.clicked.connect(slot); sn_btn_row.addWidget(btn, 2)
    sn_v.addLayout(sn_btn_row)

    # ── 활성 스나이퍼 목록 ───────────────────────────────────
    sn_v.addWidget(QLabel("▼ 활성 스나이퍼  (행 클릭 → 개별 해제)",
        styleSheet="color:#5dade2;font-size:11px;font-weight:bold;border:none;"))

    m.snp_tbl = QTableWidget(0, 5)
    m.snp_tbl.setHorizontalHeaderLabels(["행사가", "조건", "현재가", "시간(KST)", "상태"])
    m.snp_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    m.snp_tbl.verticalHeader().setVisible(False)
    m.snp_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    m.snp_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    m.snp_tbl.setMaximumHeight(150)
    m.snp_tbl.setStyleSheet(
        "QTableWidget{background:#05050f;color:#ccc;gridline-color:#1a1a3a;font-size:12px;}"
        "QHeaderView::section{background:#0a0a1e;color:#5dade2;"
        "border:1px solid #1a1a3a;font-size:11px;}"
        "QTableWidget::item:selected{background:#1a3a2a;color:#00ff88;}")
    m.snp_tbl.cellClicked.connect(m._sniper_row_click)
    sn_v.addWidget(m.snp_tbl)

    m.snp_status = QLabel("대기 중")
    m.snp_status.setAlignment(Qt.AlignCenter)
    m.snp_status.setStyleSheet(
        "color:#aaa;font-size:11px;border:1px solid #333;border-radius:3px;padding:2px;")
    sn_v.addWidget(m.snp_status)
    sn_v.addStretch()

    # ── 스나이퍼 내부 상태 초기화 ────────────────────────────
    m._snipers         = {}
    m._sniper_next_rid = 8100
    m._sniper_timer    = QTimer(m)
    m._sniper_timer.setInterval(2000)
    m._sniper_timer.timeout.connect(m._sniper_check)
    QTimer.singleShot(800, m._sniper_load)
