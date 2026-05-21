"""
tg_config_widget_patch.py
==========================
기존 tg_config_widget.py 의 _SettingsPanel 에 적용할 패치.

[적용 방법]
1. _make_watch_level_group() 메서드 복붙
2. _save_watch_levels() 메서드 복붙
3. _build_ui() 마지막 v.addStretch() 바로 앞에 한 줄 추가:
       v.addWidget(self._make_watch_level_group())
4. _save() 끝, self._cfg.save() 바로 앞에 한 줄 추가:
       self._save_watch_levels()

[버그 수정]
- [FIX-3] _save_watch_levels() 에 hasattr 방어 추가
          → _make_watch_level_group() 호출 전 _save() 가 먼저 불려도 안전
"""

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QCheckBox,
)
from PyQt5.QtGui import QFont

_F = 12


def _make_watch_level_group(self) -> QGroupBox:
    """
    감시 알람 레벨별 전송 설정 UI.

    ┌──────────────────────────────────────────────────┐
    │ 감시 알람 레벨 설정                               │
    │  🔴 LV3 (강)  [✅전송]  [15.0 pt 이상]  [무음□] │
    │  🟡 LV2 (중)  [✅전송]  [ 8.0 pt 이상]  [무음□] │
    │  🔵 LV1 (약)  [✅전송]  [ 3.0 pt 이상]  [무음✅]│
    │  ※ 0pt = 모든 알람 전송  |  LV3 무음 불가        │
    └──────────────────────────────────────────────────┘
    """
    grp = QGroupBox("감시 알람 레벨 설정")
    grp.setFont(QFont("", _F, QFont.Bold))
    vb  = QVBoxLayout(grp)

    cfg = self._cfg   # TgConfig 싱글톤 (기존 _SettingsPanel 에 이미 있음)

    LEVELS = [
        (3, "🔴 LV3 (강)"),
        (2, "🟡 LV2 (중)"),
        (1, "🔵 LV1 (약)"),
    ]

    # [FIX-3] 초기화를 메서드 시작 시점에 확실히 수행
    self._watch_lv_widgets = {}

    for lv, label in LEVELS:
        hb     = QHBoxLayout()
        lv_cfg = cfg.watch_level(lv)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setFont(QFont("", _F))

        enabled_chk = QCheckBox("전송")
        enabled_chk.setFont(QFont("", _F))
        enabled_chk.setChecked(lv_cfg.get("enabled", True))

        min_pt_sp = QDoubleSpinBox()
        min_pt_sp.setRange(0.0, 999.0)
        min_pt_sp.setSingleStep(0.5)
        min_pt_sp.setSuffix(" pt 이상")
        min_pt_sp.setFixedWidth(110)
        min_pt_sp.setFont(QFont("", _F))
        _defaults = {3: 15.0, 2: 8.0, 1: 3.0}
        min_pt_sp.setValue(lv_cfg.get("min_pt", _defaults[lv]))
        min_pt_sp.setToolTip("이 pt 미만 알람은 텔레그램 전송 안 함\n(0 = 모든 알람 전송)")

        silent_chk = QCheckBox("무음")
        silent_chk.setFont(QFont("", _F))
        silent_chk.setChecked(lv_cfg.get("silent", lv == 1))
        silent_chk.setToolTip("체크 시 알림음 없이 조용히 전송")

        # LV3 는 무음 강제 해제 (중요 알람이므로)
        if lv == 3:
            silent_chk.setEnabled(False)
            silent_chk.setChecked(False)

        hb.addWidget(lbl)
        hb.addWidget(enabled_chk)
        hb.addWidget(min_pt_sp)
        hb.addWidget(silent_chk)
        hb.addStretch()
        vb.addLayout(hb)

        self._watch_lv_widgets[lv] = (enabled_chk, min_pt_sp, silent_chk)

    note = QLabel("※ 임계값 0pt = 모든 알람 전송  |  LV3 무음 불가")
    note.setFont(QFont("", 10))
    note.setStyleSheet("QLabel { color: #9ca3af; }")
    vb.addWidget(note)

    return grp


def _save_watch_levels(self):
    """
    _save() 끝에서 호출.
    [FIX-3] hasattr 방어: _watch_lv_widgets 가 없으면 조용히 스킵
    """
    if not hasattr(self, "_watch_lv_widgets"):
        return
    for lv, (enabled_chk, min_pt_sp, silent_chk) in self._watch_lv_widgets.items():
        self._cfg.set_watch_level(
            level   = lv,
            enabled = enabled_chk.isChecked(),
            min_pt  = min_pt_sp.value(),
            silent  = silent_chk.isChecked(),
        )
