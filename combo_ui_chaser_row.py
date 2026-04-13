"""
combo_ui_chaser_row.py — Smart Chaser UI 행 빌드
────────────────────────────────────────────────
포함: _build_chaser_row (RightPanelMixin mixin)
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QRadioButton, QButtonGroup


def _build_chaser_row(self) -> QWidget:
    """Smart Chaser 행: 수동/자동 라디오 + Chase 버튼."""
    _RB = ("QRadioButton{color:#aaa;font-size:11px;font-weight:bold;spacing:4px;}"
           "QRadioButton::indicator{width:13px;height:13px;border-radius:7px;"
           "border:2px solid #444;background:#0a0a1e;}"
           "QRadioButton::indicator:checked{background:#00aaff;border-color:#00aaff;}"
           "QRadioButton:checked{color:#00aaff;}")
    _SEP = "background:#1a1a3a;color:#1a1a3a;padding:0 2px;"

    row = QWidget()
    row.setStyleSheet("background:#0a0a18;border:1px solid #1a1a3a;border-radius:4px;")
    h = QHBoxLayout(row); h.setContentsMargins(6, 3, 6, 3); h.setSpacing(6)

    lbl = QLabel("🎯 Chaser")
    lbl.setStyleSheet("color:#888;font-size:11px;font-weight:bold;border:none;")
    h.addWidget(lbl)

    sep1 = QLabel("|"); sep1.setStyleSheet(_SEP); h.addWidget(sep1)

    self._rb_chaser_manual = QRadioButton("수동")
    self._rb_chaser_manual.setStyleSheet(_RB)
    self._rb_chaser_manual.setChecked(True)
    h.addWidget(self._rb_chaser_manual)

    self._rb_chaser_auto = QRadioButton("자동")
    self._rb_chaser_auto.setStyleSheet(_RB)
    h.addWidget(self._rb_chaser_auto)

    self._chaser_mode_grp = QButtonGroup(self)
    self._chaser_mode_grp.addButton(self._rb_chaser_manual, 0)
    self._chaser_mode_grp.addButton(self._rb_chaser_auto,   1)
    self._chaser_mode_grp.buttonClicked.connect(self._on_chaser_mode_changed)

    sep2 = QLabel("|"); sep2.setStyleSheet(_SEP); h.addWidget(sep2)

    self.btn_chase = QPushButton("🎯 Chase")
    self.btn_chase.setObjectName("btn_chase")
    self.btn_chase.setFixedHeight(26)
    self.btn_chase.setStyleSheet(
        "QPushButton#btn_chase{background:#0e1a2e;color:#00aaff;"
        "border:1px solid #00aaff;border-radius:4px;font-size:11px;"
        "font-weight:bold;padding:3px 10px;}"
        "QPushButton#btn_chase:hover{background:#00aaff;color:#000;}"
        "QPushButton#btn_chase:disabled{background:#111;color:#333;border-color:#222;}")
    self.btn_chase.clicked.connect(self._on_chase_click)
    h.addWidget(self.btn_chase)

    self._lbl_chaser_info = QLabel("미체결 5초 후 1틱 자동 추격  (최대 3회)")
    self._lbl_chaser_info.setStyleSheet(
        "color:#444;font-size:10px;border:none;font-style:italic;")
    self._lbl_chaser_info.setVisible(False)
    h.addWidget(self._lbl_chaser_info)

    h.addStretch()
    return row
