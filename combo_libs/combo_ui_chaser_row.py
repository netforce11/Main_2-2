"""
combo_ui_chaser_row.py — Chaser 라디오+버튼 행 UI
────────────────────────────────────────────────────
포함:
  _build_chaser_row — 수동/자동 라디오 + Chase 버튼 + ✕ 취소 버튼

변경 (v2.6):
  - ✕ 주문 취소 버튼 추가 (btn_cancel_bag)
  - 주문 전송 전: 비활성(회색), 주문 후: 활성(빨간색)
  - combo_order_chaser._update_cancel_ui() 가 자동 갱신
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QRadioButton, QButtonGroup, QLabel,
)


def _build_chaser_row(self) -> QWidget:
    """
    Chaser 제어 행 빌드.

    레이아웃:
      ┌─────────────────────────────────────────────────────┐
      │ ◉ 수동  ○ 자동    🎯 Chase    ✕ 주문 취소          │
      │ 자동: 5초마다 1틱 개선, 최대 3회                    │
      └─────────────────────────────────────────────────────┘
    """
    container = QWidget()
    cv = QVBoxLayout(container)
    cv.setContentsMargins(0, 2, 0, 2)
    cv.setSpacing(3)

    # ── 버튼 행 ──────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    # 수동/자동 라디오
    self._rb_chaser_manual = QRadioButton("수동")
    self._rb_chaser_auto   = QRadioButton("자동")
    self._rb_chaser_manual.setChecked(True)
    _rb_s = "QRadioButton{color:#aaa;font-size:11px;} QRadioButton:checked{color:#ffd700;}"
    self._rb_chaser_manual.setStyleSheet(_rb_s)
    self._rb_chaser_auto.setStyleSheet(_rb_s)
    _grp = QButtonGroup(container)
    _grp.addButton(self._rb_chaser_manual)
    _grp.addButton(self._rb_chaser_auto)
    self._rb_chaser_manual.toggled.connect(
        lambda checked: self._on_chaser_mode_changed(self._rb_chaser_manual))
    self._rb_chaser_auto.toggled.connect(
        lambda checked: self._on_chaser_mode_changed(self._rb_chaser_auto))
    btn_row.addWidget(self._rb_chaser_manual)
    btn_row.addWidget(self._rb_chaser_auto)

    # 🎯 Chase 버튼
    self.btn_chase = QPushButton("🎯 Chase")
    self.btn_chase.setFixedHeight(26)
    self.btn_chase.setStyleSheet(
        "QPushButton{background:#1a2a4a;color:#90caf9;font-size:12px;"
        "font-weight:bold;padding:3px 10px;border-radius:3px;"
        "border:1px solid #3a5a9a;}"
        "QPushButton:hover{background:#2a3a6a;}"
        "QPushButton:disabled{background:#0a0a1a;color:#333;border-color:#222;}")
    self.btn_chase.clicked.connect(lambda: self.on_chase_click())
    btn_row.addWidget(self.btn_chase)

    # ✕ 주문 취소 버튼 (신규)
    self.btn_cancel_bag = QPushButton("✕ 주문 취소")
    self.btn_cancel_bag.setFixedHeight(26)
    self.btn_cancel_bag.setEnabled(False)   # 주문 전 비활성
    self.btn_cancel_bag.setStyleSheet(
        "QPushButton{background:#1a1a2a;color:#555;font-size:12px;"
        "font-weight:bold;padding:3px 10px;border-radius:3px;"
        "border:1px solid #333;}"
        "QPushButton:disabled{background:#0a0a1a;color:#333;border-color:#222;}")
    self.btn_cancel_bag.clicked.connect(lambda: self._on_cancel_bag_order())
    btn_row.addWidget(self.btn_cancel_bag)

    btn_row.addStretch()
    cv.addLayout(btn_row)

    # ── 설명 라벨 ─────────────────────────────────────────────
    self._lbl_chaser_desc = QLabel("수동: Chase 클릭 시 1틱 정정")
    self._lbl_chaser_desc.setStyleSheet(
        "color:#555;font-size:10px;border:none;")
    cv.addWidget(self._lbl_chaser_desc)

    return container