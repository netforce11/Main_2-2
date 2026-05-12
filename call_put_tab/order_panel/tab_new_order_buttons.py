"""
order_panel/tab_new_order_buttons.py — 신규 탭 버튼 영역 빌드
════════════════════════════════════════════════════════════
포함:
  build_new_order_buttons(mixin, root_v)
    - 매수/매도 버튼
    - +1호가 매수 버튼
    - 긴급매도 버튼 (ALL / 잔고만 / 미체결만)
    - 상태 라벨
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
)
from PyQt5.QtCore import Qt

from .helpers import _animate_press


def build_new_order_buttons(m, root_v) -> None:
    """매수/매도·긴급매도 버튼과 상태 라벨을 root_v에 추가."""

    # ── 매수/매도 버튼 ───────────────────────────────────────
    _buy_s  = ("QPushButton{background:#1a5c2e;color:#00ff88;font-size:16px;"
               "font-weight:bold;padding:10px 4px;border-radius:4px;}"
               "QPushButton:pressed{background:#0a3c1e;padding-top:12px;padding-bottom:8px;}")
    _sell_s = ("QPushButton{background:#6b1a1a;color:#ff6666;font-size:16px;"
               "font-weight:bold;padding:10px 4px;border-radius:4px;}"
               "QPushButton:pressed{background:#4b0a0a;padding-top:12px;padding-bottom:8px;}")
    btn_row = QHBoxLayout(); btn_row.setSpacing(4)
    m.btn_qord_buy  = QPushButton("▲ 매수"); m.btn_qord_buy.setStyleSheet(_buy_s)
    m.btn_qord_sell = QPushButton("▼ 매도"); m.btn_qord_sell.setStyleSheet(_sell_s)
    m.btn_qord_buy.clicked.connect(lambda _: (
        _animate_press(m.btn_qord_buy), m._qord_place("BUY")))
    m.btn_qord_sell.clicked.connect(lambda _: (
        _animate_press(m.btn_qord_sell), m._qord_place("SELL")))
    btn_row.addWidget(m.btn_qord_buy, 1); btn_row.addWidget(m.btn_qord_sell, 1)
    root_v.addLayout(btn_row)

    # ── +1호가 매수 버튼 ─────────────────────────────────────
    _p1_s = ("QPushButton{background:#1a3a5c;color:#90caf9;font-size:13px;"
             "font-weight:bold;padding:5px;border-radius:4px;border:1px solid #2a5a8c;}"
             "QPushButton:hover{background:#2a4a7c;}"
             "QPushButton:pressed{background:#0a2a4c;padding-top:7px;padding-bottom:3px;}")
    m.btn_plus1tick = QPushButton("+1호가 매수"); m.btn_plus1tick.setStyleSheet(_p1_s)
    m.btn_plus1tick.setToolTip("미체결 주문 중 최고가 매수 주문을 +$0.05 올려 정정")
    m.btn_plus1tick.clicked.connect(lambda: (
        _animate_press(m.btn_plus1tick), m._plus1tick_buy()))
    root_v.addWidget(m.btn_plus1tick)

    # ── 긴급 매도 버튼들 ─────────────────────────────────────
    sep = QLabel(); sep.setFixedHeight(1); sep.setStyleSheet("background:#4a1a1a;border:none;")
    root_v.addWidget(sep)

    _emrg_all_s = ("QPushButton{background:#8b0000;color:#ff4444;font-size:13px;"
                   "font-weight:bold;padding:6px;border-radius:4px;border:2px solid #ff4444;}"
                   "QPushButton:hover{background:#aa0000;}"
                   "QPushButton:pressed{background:#660000;padding-top:8px;padding-bottom:4px;}")
    _emrg_pos_s = ("QPushButton{background:#5a0a0a;color:#ff8888;font-size:12px;"
                   "font-weight:bold;padding:4px;border-radius:3px;border:1px solid #aa4444;}"
                   "QPushButton:hover{background:#7a1a1a;}"
                   "QPushButton:pressed{background:#3a0000;padding-top:6px;padding-bottom:2px;}")

    m.btn_emrg_all = QPushButton("🚨 긴급매도 ALL (잔고+미체결)")
    m.btn_emrg_all.setStyleSheet(_emrg_all_s)
    m.btn_emrg_all.setToolTip("보유 포지션 전체 시장가 매도 + 미체결 매수 취소")
    m.btn_emrg_all.clicked.connect(lambda: (
        _animate_press(m.btn_emrg_all), m._emergency_sell_all()))
    root_v.addWidget(m.btn_emrg_all)

    emrg_row = QHBoxLayout(); emrg_row.setSpacing(4)
    m.btn_emrg_pos  = QPushButton("잔고만 매도"); m.btn_emrg_pos.setStyleSheet(_emrg_pos_s)
    m.btn_emrg_open = QPushButton("미체결만 취소"); m.btn_emrg_open.setStyleSheet(_emrg_pos_s)
    m.btn_emrg_pos.clicked.connect(lambda: (
        _animate_press(m.btn_emrg_pos), m._emergency_sell_positions()))
    m.btn_emrg_open.clicked.connect(lambda: (
        _animate_press(m.btn_emrg_open), m._emergency_cancel_orders()))
    emrg_row.addWidget(m.btn_emrg_pos, 1); emrg_row.addWidget(m.btn_emrg_open, 1)
    root_v.addLayout(emrg_row)

    m.lbl_qord_status = QPushButton("대기 중")   # dummy QPushButton placeholder
    from PyQt5.QtWidgets import QLabel as _L
    m.lbl_qord_status = _L("대기 중")
    m.lbl_qord_status.setAlignment(Qt.AlignCenter)
    m.lbl_qord_status.setStyleSheet(
        "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
    root_v.addWidget(m.lbl_qord_status)
    root_v.addStretch()
