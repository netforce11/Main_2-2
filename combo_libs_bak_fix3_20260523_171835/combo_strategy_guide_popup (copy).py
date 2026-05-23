"""
combo_strategy_guide_popup.py — 전략 구성 가이드 팝업
═══════════════════════════════════════════════════════
v3.1 버그 수정:
  BUG-3  위치 계산을 show() 이후 QTimer.singleShot(0)으로 지연 → 실제 크기 기반
  BUG-12 anim 덮어쓰기 전 기존 애니메이션 stop() 선행
  BUG-13 가이드 없는 전략의 📋 버튼 처리 방식을 hide로 통일
         (combo_ui_leg_panel._update_guide_btn_state 연동)
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame, QScrollArea, QWidget,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QFont

# 세션 내 "다시 표시 안 함" 전략 목록
_SUPPRESS_SET: set = set()


class StrategyGuidePopup(QDialog):
    """전략 구성 단계별 안내 팝업 다이얼로그."""

    def __init__(self, guide: dict, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint)
        self._guide     = guide
        self._fade_anim = None          # BUG-12: 명시적 초기화
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.0)      # BUG-3: 초기 투명 (위치 확정 전 깜빡임 방지)
        self._build_ui()
        # BUG-3: 위치 계산은 show() 이후 singleShot으로 지연
        # → _position_popup은 show() 내부에서 예약

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_ui(self):
        guide   = self._guide
        title   = guide.get("title", "전략 구성 가이드")
        steps   = guide.get("steps", [])
        tips    = guide.get("tips", [])
        warning = guide.get("warning")

        self.setStyleSheet("QDialog { background: transparent; }")

        outer = QFrame(self)
        outer.setObjectName("guideCard")
        outer.setStyleSheet(
            "QFrame#guideCard {"
            "  background: #0d1225;"
            "  border: 1px solid #2a3a6a;"
            "  border-radius: 10px;"
            "}")
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

        # ── 스크롤 영역 ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(320)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{background:#0a0a1e;width:6px;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#3a3a6a;border-radius:3px;}")
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(content)
        cv.setSpacing(6)
        cv.setContentsMargins(0, 0, 4, 0)

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

        # ── 하단 행 ────────────────────────────────────────────
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
            _SUPPRESS_SET.add(self._guide.get("title", ""))
        self.close()

    # ── 위치 설정 (부모 우하단) ───────────────────────────────
    def _position_popup(self):
        """
        BUG-3 수정: show() 이후 QTimer.singleShot(0)으로 예약되어
        실제 렌더링된 크기(adjustSize 완료 후)를 기반으로 계산.
        """
        self.adjustSize()
        parent = self.parent()
        if parent is None:
            self.move(100, 100)
        else:
            pg = parent.geometry()
            margin = 20
            x = pg.x() + pg.width()  - self.width()  - margin
            y = pg.y() + pg.height() - self.height() - margin
            self.move(max(0, x), max(0, y))

    # ── show 오버라이드 ───────────────────────────────────────
    def show(self):
        """
        BUG-3: super().show() 후 singleShot(0)으로 위치 계산 지연.
        BUG-12: 기존 anim이 실행 중이면 stop() 후 새 anim 시작.
        """
        # suppress는 _maybe_show_setup_guide에서 이미 검사됨.
        # 직접 호출(📋 버튼) 경로는 suppress를 미리 discard하므로 통과.
        super().show()

        # BUG-3: 레이아웃 확정 후 위치 결정
        QTimer.singleShot(0, self._position_popup)

        # BUG-12: 이전 애니메이션 정지 후 새 애니메이션 시작
        if self._fade_anim is not None:
            self._fade_anim.stop()

        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(0.97)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.start()
        self._fade_anim = anim   # 참조 유지 (GC 방지)


# ── 단계별 색상 유틸 ─────────────────────────────────────────

def _step_color(idx: int) -> str:
    colors = ["#ffd700", "#33aaff", "#ff6666", "#88ff44",
              "#ff88ff", "#44ffdd", "#ffaa33", "#bb88ff"]
    return colors[idx % len(colors)]


# ── suppress 목록 초기화 ────────────────────────────────────

def reset_suppress():
    """세션 suppress 목록 초기화 (테스트용)."""
    _SUPPRESS_SET.clear()
