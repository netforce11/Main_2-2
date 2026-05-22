"""
watch_alert_tab.py  — SPX 감시 패널 (독립 창)
패치 버전: v1.4-patch
변경 사항:
  1. 앱 시작 시 타이틀바만 우측 하단에 노출 (몸통 숨김)
  2. 더블클릭으로 패널 펼침 / 다시 숨김 토글
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QApplication
)
from PyQt5.QtCore import Qt, QTimer


class SpxAlertPanel(QDialog):
    """SPX 감시 패널 — 독립 창 (QDialog)
    
    기존 코드에 아래 두 가지 패치가 적용되었습니다:
      [패치 1] __init__ 끝에서 _snap_to_bottom_right() 호출
      [패치 2] 위치 제어 메서드 + mouseDoubleClickEvent 추가
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SPX 감시 패널")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint
        )
        self.resize(520, 400)

        # ── UI 구성 (기존 코드 그대로 유지) ──
        self._build_ui()

        # ── [패치 1] 타이틀바만 우측 하단에 1cm 노출 ──
        self._title_only_mode = True
        QTimer.singleShot(200, self._snap_to_bottom_right)

    # ── 기존 UI 빌더 (변경 없음) ─────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 타이틀 영역
        title_bar = QHBoxLayout()
        lbl = QLabel("📡 SPX 실시간 감시")
        lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#00BFFF;")
        title_bar.addWidget(lbl)
        title_bar.addStretch()
        layout.addLayout(title_bar)

        # 알람 조건 그룹 (기존 watch_alert_tab 레이아웃 그대로)
        grp = QGroupBox("감시 조건")
        layout.addWidget(grp)

        # 하단 버튼
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self._snap_to_bottom_right)
        layout.addWidget(btn_close)

    # ── [패치 2] 우측 하단 타이틀바 노출 메서드 ──────────────────

    def _snap_to_bottom_right(self):
        """타이틀바(약 30 px)만 화면 우측 하단에 보이도록 위치/크기 조정.
        
        화면 구조:
          ┌─────────────────────────────────────────┐  ← 모니터 상단
          │                                         │
          │              (바탕화면)                  │
          │                                         │
          │                         ┌─────────────┐ │  ← 타이틀바만 보임
          └─────────────────────────┴─────────────┴─┘  ← 작업표시줄
        
        패널 몸통은 작업표시줄 아래로 숨겨진 상태.
        """
        screen = QApplication.primaryScreen().availableGeometry()

        title_h   = self._get_title_bar_height()   # 보통 28~32 px (OS마다 다름)
        expose_px = title_h                         # 딱 타이틀바 높이만큼 노출

        w = self.width()    # 현재 패널 너비 유지
        h = self.height()   # 현재 패널 높이 유지 (몸통은 화면 밖으로)

        # x: 우측 정렬, 우측 여백 10 px
        # y: 타이틀바 상단이 "화면 하단 - 타이틀높이" 위치
        x = screen.right()  - w - 10
        y = screen.bottom() - expose_px

        self.setGeometry(x, y, w, h)
        self._title_only_mode = True

    def _get_title_bar_height(self) -> int:
        """OS 타이틀바 높이를 추정.
        
        프레임 포함 높이 - 클라이언트 영역 높이 = 타이틀바 높이.
        창이 아직 표시되기 전이거나 frameless면 기본값 30 반환.
        """
        frame_h  = self.frameGeometry().height()
        client_h = self.geometry().height()
        diff     = frame_h - client_h
        return diff if diff > 4 else 30   # 4px 미만은 측정 오류로 간주

    def _expand_panel(self):
        """패널을 우측 하단 화면 내에 완전히 펼쳐서 표시."""
        screen = QApplication.primaryScreen().availableGeometry()
        w = self.width()
        h = self.height()
        x = screen.right()  - w - 10
        y = screen.bottom() - h - 10   # 작업표시줄 10 px 위
        self.setGeometry(x, y, w, h)
        self._title_only_mode = False

    def mouseDoubleClickEvent(self, event):
        """더블클릭: 숨김(타이틀만) ↔ 펼침 토글."""
        if self._title_only_mode:
            self._expand_panel()
        else:
            self._snap_to_bottom_right()
        super().mouseDoubleClickEvent(event)
