"""
chart_foldable_group.py — 접기/펼치기 가능한 그룹 패널 위젯
[분리] chart_build_side.py 에서 분리 (_FoldableGroup)
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton

class _FoldableGroup(QWidget):
    """
    접기/펼치기 가능한 그룹 패널.
    header_text: 상단 토글 버튼에 표시될 제목
    content    : 펼쳤을 때 보여줄 QWidget
    """
    def __init__(self, header_text: str, content: QWidget, parent=None,
                 collapsed: bool = False):
        super().__init__(parent)
        self._collapsed = collapsed
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 헤더 토글 버튼
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(not collapsed)
        self._btn.setFixedHeight(24)
        self._btn.setStyleSheet(
            "QPushButton{"
            "  background:#141430; color:#5dade2;"
            "  border:1px solid #2e3060; border-radius:3px;"
            "  text-align:left; padding:0 6px;"
            "  font-weight:bold; font-size:12px;"
            "}"
            "QPushButton:hover{ background:#1c1c3a; }"
        )
        self._btn.clicked.connect(self._toggle)
        root.addWidget(self._btn)

        # 컨텐츠 영역
        self._content = content
        root.addWidget(self._content)

        self._update_label(header_text)
        self._content.setVisible(not collapsed)

    def _update_label(self, text: str):
        self._header_text = text
        arrow = "▼" if self._btn.isChecked() else "▶"
        self._btn.setText(f"  {arrow}  {text}")

    def _toggle(self, checked: bool):
        self._content.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self._btn.setText(f"  {arrow}  {self._header_text}")


