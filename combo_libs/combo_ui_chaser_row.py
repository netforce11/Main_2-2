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


def _pal():
    try:
        import core_theme as _core
        return _core.THEME_PALETTES.get(_core.CURRENT_THEME,
                                        _core.THEME_PALETTES["light"])
    except Exception:
        return {"group_bg": "#e5e7eb", "group_title": "#1e40af",
                "widget_fg": "#111827", "input_border": "#cbd5e1",
                "btn_hover": "#e2e8f0", "btn_hover_bdr": "#94a3b8"}


def _build_chaser_row(self) -> QWidget:
    t = _pal()
    container = QWidget()
    cv = QVBoxLayout(container)
    cv.setContentsMargins(0, 2, 0, 2)
    cv.setSpacing(3)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    # 수동/자동 라디오
    self._rb_chaser_manual = QRadioButton("수동")
    self._rb_chaser_auto   = QRadioButton("자동")
    self._rb_chaser_manual.setChecked(True)
    _rb_s = (f"QRadioButton{{color:{t['group_title']};font-size:11px;}}"
             f"QRadioButton:checked{{color:#ffd700;}}")
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
        f"QPushButton{{background:{t['group_bg']};color:{t['group_title']};font-size:12px;"
        f"font-weight:bold;padding:3px 10px;border-radius:6px;"
        f"border:1px solid {t['input_border']};}}"
        f"QPushButton:hover{{background:{t['btn_hover']};}}"
        f"QPushButton:disabled{{color:{t['input_border']};border-color:{t['input_border']};}}")
    self.btn_chase.clicked.connect(lambda: self.on_chase_click())
    btn_row.addWidget(self.btn_chase)

    # ✕ 주문 취소 버튼
    self.btn_cancel_bag = QPushButton("✕ 주문 취소")
    self.btn_cancel_bag.setFixedHeight(26)
    self.btn_cancel_bag.setEnabled(False)
    self.btn_cancel_bag.setStyleSheet(
        f"QPushButton{{background:{t['group_bg']};color:#ff5555;font-size:12px;"
        f"font-weight:bold;padding:3px 10px;border-radius:6px;"
        f"border:1px solid #8a1a1a;}}"
        f"QPushButton:disabled{{color:{t['input_border']};border-color:{t['input_border']};}}")
    self.btn_cancel_bag.clicked.connect(lambda: self._on_cancel_bag_order())
    btn_row.addWidget(self.btn_cancel_bag)

    btn_row.addStretch()
    cv.addLayout(btn_row)

    self._lbl_chaser_desc = QLabel("수동: Chase 클릭 시 1틱 정정")
    self._lbl_chaser_desc.setStyleSheet(
        f"color:{t['group_title']};font-size:10px;border:none;")
    cv.addWidget(self._lbl_chaser_desc)

    return container