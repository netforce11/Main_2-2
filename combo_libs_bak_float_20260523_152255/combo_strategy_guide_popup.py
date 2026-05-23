"""
combo_strategy_guide_popup.py — 전략 구성 가이드 팝업
═══════════════════════════════════════════════════════
v3.0 신규

전략 선택 시 자동으로 표시되는 단계별 구성 안내 팝업.
- 단계별 레그 입력 방법 안내
- 팁(Tips) 및 주의사항(Warning) 표시
- 반투명 오버레이 + 우하단 고정 위치
- "다시 표시 안 함" 토글 지원 (세션 내)
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame, QScrollArea, QWidget,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, QTimer
from PyQt5.QtGui import QFont, QColor

# 세션 내 "다시 표시 안 함" 전략 목록
_SUPPRESS_SET: set = set()


class StrategyGuidePopup(QDialog):
    """전략 구성 단계별 안내 팝업 다이얼로그."""

    def __init__(self, guide: dict, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint)
        self._guide = guide
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.97)
        self._build_ui()
        self._position_popup()

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_ui(self):
        guide  = self._guide
        title  = guide.get("title", "전략 구성 가이드")
        steps  = guide.get("steps", [])
        tips   = guide.get("tips", [])
        warning = guide.get("warning")

        self.setStyleSheet("""
            QDialog {
                background: transparent;
            }
        """)

        # 최외곽 컨테이너 (시각적 카드)
        outer = QFrame(self)
        outer.setObjectName("guideCard")
        outer.setStyleSheet("""
            QFrame#guideCard {
                background: #0d1225;
                border: 1px solid #2a3a6a;
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(outer)

        root = QVBoxLayout(outer)
        root.setSpacing(8)
        root.setContentsMargins(14, 12, 14, 12)

        # ── 타이틀 행 ──────────────────────────────────────────
        title_row = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setFont(QFont("Arial", 13, QFont.Bold))
        lbl_title.setStyleSheet("color:#ffd700;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setStyleSheet(
            "QPushButton{background:#2a1a1a;color:#ff6666;border:1px solid #5a1a1a;"
            "border-radius:4px;font-size:12px;}"
            "QPushButton:hover{background:#4a1a1a;}")
        btn_close.clicked.connect(self.close)
        title_row.addWidget(btn_close)
        root.addLayout(title_row)

        # ── 구분선 ─────────────────────────────────────────────
        line = QFrame(); line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#2a3a6a;")
        root.addWidget(line)

        # ── 스크롤 영역 (단계 + 팁 + 경고) ──────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(320)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{background:#0a0a1e;width:6px;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#3a3a6a;border-radius:3px;}"
        )
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(content)
        cv.setSpacing(6)
        cv.setContentsMargins(0, 0, 4, 0)

        # 단계별 안내
        if steps:
            lbl_steps_hdr = QLabel("📋 구성 단계")
            lbl_steps_hdr.setStyleSheet(
                "color:#90caf9;font-size:12px;font-weight:bold;")
            cv.addWidget(lbl_steps_hdr)
            for i, step_text in enumerate(steps):
                step_frame = QFrame()
                step_frame.setStyleSheet(
                    f"QFrame{{background:#0a1428;border-left:3px solid "
                    f"{_step_color(i)};border-radius:3px;padding:2px;}}")
                sf_layout = QVBoxLayout(step_frame)
                sf_layout.setContentsMargins(8, 4, 4, 4)
                sf_layout.setSpacing(0)
                lbl = QLabel(step_text)
                lbl.setStyleSheet("color:#ddd;font-size:12px;border:none;")
                lbl.setWordWrap(True)
                sf_layout.addWidget(lbl)
                cv.addWidget(step_frame)

        # 팁
        if tips:
            cv.addSpacing(4)
            lbl_tips_hdr = QLabel("💡 Tips")
            lbl_tips_hdr.setStyleSheet(
                "color:#44cc88;font-size:12px;font-weight:bold;")
            cv.addWidget(lbl_tips_hdr)
            for tip in tips:
                lbl_tip = QLabel(tip)
                lbl_tip.setStyleSheet(
                    "color:#aaffbb;font-size:11px;padding-left:6px;border:none;")
                lbl_tip.setWordWrap(True)
                cv.addWidget(lbl_tip)

        # 경고
        if warning:
            cv.addSpacing(4)
            warn_frame = QFrame()
            warn_frame.setStyleSheet(
                "QFrame{background:#1a0a0a;border:1px solid #aa3333;"
                "border-radius:4px;}")
            wf = QVBoxLayout(warn_frame)
            wf.setContentsMargins(8, 6, 8, 6)
            lbl_warn = QLabel(warning)
            lbl_warn.setStyleSheet(
                "color:#ff8888;font-size:12px;font-weight:bold;border:none;")
            lbl_warn.setWordWrap(True)
            wf.addWidget(lbl_warn)
            cv.addWidget(warn_frame)

        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── 하단 행: 체크박스 + 확인 버튼 ─────────────────────
        bottom_row = QHBoxLayout()
        self._chk_suppress = QCheckBox("이 전략은 다시 표시 안 함")
        self._chk_suppress.setStyleSheet(
            "QCheckBox{color:#888;font-size:11px;}"
            "QCheckBox::indicator{width:13px;height:13px;}"
            "QCheckBox::indicator:checked{background:#1a5c2e;border:1px solid #00ff88;}"
            "QCheckBox::indicator:unchecked{background:#1a1a3a;border:1px solid #3a3a6a;}")
        bottom_row.addWidget(self._chk_suppress)
        bottom_row.addStretch()
        btn_ok = QPushButton("확인  ✓")
        btn_ok.setFixedHeight(28)
        btn_ok.setStyleSheet(
            "QPushButton{background:#1a3a5a;color:#90caf9;font-size:12px;"
            "font-weight:bold;border:1px solid #3a5a8a;border-radius:4px;"
            "padding:2px 16px;}"
            "QPushButton:hover{background:#2a4a7a;}")
        btn_ok.clicked.connect(self._on_confirm)
        bottom_row.addWidget(btn_ok)
        root.addLayout(bottom_row)

        self.setMinimumWidth(420)

    # ── 버튼 핸들러 ───────────────────────────────────────────
    def _on_confirm(self):
        if self._chk_suppress.isChecked():
            title = self._guide.get("title", "")
            _SUPPRESS_SET.add(title)
        self.close()

    # ── 위치 설정 (부모 우하단) ───────────────────────────────
    def _position_popup(self):
        parent = self.parent()
        if parent is None:
            self.move(100, 100)
            return
        pg = parent.geometry()
        self.adjustSize()
        pw, ph = self.width(), self.height()
        margin = 20
        x = pg.x() + pg.width()  - pw - margin
        y = pg.y() + pg.height() - ph - margin
        self.move(max(0, x), max(0, y))

    # ── show 오버라이드: suppress 체크 시 표시 안 함 ─────────
    def show(self):
        title = self._guide.get("title", "")
        if title in _SUPPRESS_SET:
            return
        super().show()
        # 페이드인 애니메이션
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(0.97)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        self._fade_anim = anim   # GC 방지


# ── 단계별 색상 유틸 ─────────────────────────────────────────

def _step_color(idx: int) -> str:
    """레그 순서에 따른 강조 색상 (LEG_COLORS 동기화)."""
    colors = ["#ffd700", "#33aaff", "#ff6666", "#88ff44",
              "#ff88ff", "#44ffdd", "#ffaa33", "#bb88ff"]
    return colors[idx % len(colors)]


# ── 외부에서 suppress 목록 초기화 ────────────────────────────

def reset_suppress():
    """세션 suppress 목록 초기화 (테스트용)."""
    _SUPPRESS_SET.clear()
