# call_put_tab/tab_options_chain_mode.py
"""
체인 모드 선택 (A/B 라디오 버튼) UI + 상태 관리
- A: 기존 체인 표시
- B: 행사가|현재가|등락률|델타|이론가|차이 (블랙숄즈)
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout,
                              QRadioButton, QButtonGroup, QLabel)
from PyQt5.QtCore import pyqtSignal

CHAIN_MODE_A = "A"
CHAIN_MODE_B = "B"


class ChainModeWidget(QWidget):
    """
    좌측 하단에 배치되는 A/B 라디오 버튼 위젯.
    모드가 바뀌면 mode_changed(str) 시그널을 emit.
    """
    mode_changed = pyqtSignal(str)   # "A" or "B"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = CHAIN_MODE_A
        self._build_ui()

    # ──────────────────────────────────────────────────────
    # UI 구성
    # ──────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(8)

        lbl = QLabel("체인 모드:")
        lbl.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(lbl)

        self._grp = QButtonGroup(self)
        for name in (CHAIN_MODE_A, CHAIN_MODE_B):
            rb = QRadioButton(name)
            rb.setStyleSheet(
                "QRadioButton{color:#ddd; font-size:11px;}"
                "QRadioButton::indicator{width:13px; height:13px;}"
            )
            rb.setChecked(name == CHAIN_MODE_A)
            self._grp.addButton(rb)
            lay.addWidget(rb)

        lay.addStretch()
        self._grp.buttonClicked.connect(self._on_click)

    # ──────────────────────────────────────────────────────
    # 내부 슬롯
    # ──────────────────────────────────────────────────────
    def _on_click(self, btn: QRadioButton):
        new_mode = btn.text()
        if new_mode != self._mode:
            self._mode = new_mode
            self.mode_changed.emit(self._mode)

    # ──────────────────────────────────────────────────────
    # 외부 인터페이스
    # ──────────────────────────────────────────────────────
    @property
    def mode(self) -> str:
        """현재 선택된 모드 ("A" or "B")"""
        return self._mode

    def set_mode(self, mode: str):
        """코드에서 모드 강제 변경 (시그널도 emit)"""
        if mode not in (CHAIN_MODE_A, CHAIN_MODE_B):
            return
        for btn in self._grp.buttons():
            if btn.text() == mode:
                btn.setChecked(True)
                if mode != self._mode:
                    self._mode = mode
                    self.mode_changed.emit(self._mode)
                break
