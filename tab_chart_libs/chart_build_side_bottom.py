"""
chart_build_side_bottom.py — 사이드바 하단 섹션 빌더 (메모 + 일봉 버튼)
[분리] chart_build_side.py 에서 분리
"""
from PyQt5.QtWidgets import QPushButton, QWidget, QScrollArea, QFrame
from PyQt5.QtCore import Qt
from chart_memo import build_memo_panel

def _build_bottom_section(self, side):
    # ════════════════════════════════════════════════════
    # v6.7: 메모 패널 토글 버튼 + 패널
    # ════════════════════════════════════════════════════
    side.addWidget(_make_sep())

    self.btn_memo_toggle = QPushButton("📝 메모 열기")
    self.btn_memo_toggle.setCheckable(True)
    self.btn_memo_toggle.setChecked(False)
    self.btn_memo_toggle.setFixedHeight(28)
    self.btn_memo_toggle.setToolTip(
        "선택된 날짜의 메모를 열고 닫습니다.\n"
        "캘린더 날짜 클릭 시 해당일 메모가 자동 로드됩니다.")
    self.btn_memo_toggle.setStyleSheet(
        "QPushButton{"
        "  background:#1a1a2e;color:#9e9e9e;"
        "  border:1px solid #3a3a5a;border-radius:3px;"
        "  font-weight:bold;padding:4px 8px;}"
        "QPushButton:hover{"
        "  background:#22223a;color:#bdbdbd;"
        "  border-color:#5a5a8a;}"
        "QPushButton:checked{"
        "  background:#162032;color:#5dade2;"
        "  border:1px solid #5dade2;}"
        "QPushButton:checked:hover{"
        "  background:#1a2a3e;}"
    )
    self.btn_memo_toggle.clicked.connect(self._toggle_memo_panel)
    side.addWidget(self.btn_memo_toggle)

    # 메모 패널 (초기 숨김)
    _memo_widget = build_memo_panel(self)
    side.addWidget(_memo_widget)

    # ════════════════════════════════════════════════════
    # v6.4: 일봉 추가 보기 버튼
    # ════════════════════════════════════════════════════
    side.addWidget(_make_sep())

    self.btn_daily = QPushButton("📈 일봉 추가 보기")
    self.btn_daily.setCheckable(True)
    self.btn_daily.setChecked(False)
    self.btn_daily.setFixedHeight(30)
    self.btn_daily.setToolTip(
        "캘린더 날짜 기준 일봉 차트를 표시합니다.\n"
        "분차트 테이블이 일시적으로 숨겨집니다.\n"
        "다시 클릭하면 분차트 테이블로 복귀합니다."
    )
    self.btn_daily.setStyleSheet(
        "QPushButton{"
        "  background:#1c2a1c;color:#aaaaaa;"
        "  border:1px solid #3a5a3a;border-radius:3px;"
        "  font-weight:bold;padding:4px 8px;}"
        "QPushButton:hover{"
        "  background:#243024;color:#cccccc;"
        "  border-color:#4a7a4a;}"
        "QPushButton:checked{"
        "  background:#1a3a2a;color:#26a69a;"
        "  border:1px solid #26a69a;}"
        "QPushButton:checked:hover{"
        "  background:#1e4a34;}"
    )
    self.btn_daily.clicked.connect(self._toggle_daily_view)
    side.addWidget(self.btn_daily)

    side.addStretch(1)

    side_w = QWidget(); side_w.setLayout(side)
    side_w.setMinimumWidth(220)
    scroll = QScrollArea()
    scroll.setWidget(side_w); scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setMinimumWidth(230); scroll.setMaximumWidth(320)
    scroll.setFrameShape(QFrame.NoFrame)
    return scroll




def _make_sep():
    """구분선 헬퍼"""
    sep = QFrame()