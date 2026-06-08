"""
chart_build_side_bottom.py — 사이드바 하단 섹션 빌더 (메모)
[분리] chart_build_side.py 에서 분리
v6.8 변경:
  - 📈 일봉 추가 보기 버튼 제거 (일봉은 p1 오버레이로 자동 표시)
  - 메모 패널 항상 열린 상태로 크게 확장
"""
from PyQt5.QtWidgets import QPushButton, QWidget, QScrollArea, QFrame
from PyQt5.QtCore import Qt
from chart_memo import build_memo_panel

def _build_bottom_section(self, side):
    # ════════════════════════════════════════════════════
    # v6.8: 메모 패널 — 항상 표시, 크기 확장
    # ════════════════════════════════════════════════════
    side.addWidget(_make_sep())

    # ── [체결 마커 v2] UI 패널 ─────────────────────────────
    from chart_exec_marker_ui import build_exec_marker_panel
    side.addWidget(build_exec_marker_panel(self))
    side.addWidget(_make_sep())
    # ── [체결 마커 v2] 끝 ─────────────────────────────────

    self.btn_memo_toggle = QPushButton("📝 메모")
    self.btn_memo_toggle.setCheckable(True)
    self.btn_memo_toggle.setChecked(True)   # 기본: 열린 상태
    self.btn_memo_toggle.setFixedHeight(28)
    self.btn_memo_toggle.setToolTip(
        "메모 패널을 열고 닫습니다.\n"
        "캘린더 날짜 클릭 시 해당일 메모가 자동 로드됩니다.")
    self.btn_memo_toggle.setStyleSheet(
        "QPushButton{"
        "  background:#162032;color:#5dade2;"
        "  border:1px solid #5dade2;border-radius:3px;"
        "  font-weight:bold;padding:4px 8px;}"
        "QPushButton:hover{"
        "  background:#1a2a3e;}"
        "QPushButton:checked{"
        "  background:#162032;color:#5dade2;"
        "  border:1px solid #5dade2;}"
        "QPushButton:not(:checked){"
        "  background:#1a1a2e;color:#9e9e9e;"
        "  border:1px solid #3a3a5a;}"
    )
    self.btn_memo_toggle.clicked.connect(self._toggle_memo_panel)
    side.addWidget(self.btn_memo_toggle)

    # 메모 패널 — 기본 열린 상태, 크기 확장
    _memo_widget = build_memo_panel(self)
    _memo_widget.show()                 # 기본 표시
    self._memo_panel = _memo_widget     # toggle 함수가 참조
    side.addWidget(_memo_widget)

    # ════════════════════════════════════════════════════
    # v6.4 일봉 추가 보기 버튼 제거
    # (일봉은 p1 우측 상단 오버레이로 자동 표시됨)
    # 아래 코드는 참고용으로 주석 처리
    # ════════════════════════════════════════════════════
    # side.addWidget(_make_sep())
    # self.btn_daily = QPushButton("📈 일봉 추가 보기")
    # ...
    # side.addWidget(self.btn_daily)

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