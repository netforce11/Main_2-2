"""
combo_trend_panel.py — 추세 점수판 패널 위젯  v1.3
════════════════════════════════════════════════════════════════
v1.3 변경:
  - QGroupBox 내부에 QTabWidget 추가
  - 탭 1: 📊 추세 점수  (기존 내용 그대로)
  - 탭 2: ⚡ 급변 감시  (SpikeMonitorTab 임베드)

v1.2 변경:
  - 300초(5분) 자동 갱신 QTimer 추가
  - DF 수신 시 타이머 자동 시작
  - [⏸ 자동중지] / [▶ 자동시작] 토글 버튼 추가
  - 다음 갱신까지 남은 시간 카운트다운 표시
  - 버튼 수동 클릭도 여전히 동작 (핫-리로드 포함)

자동 갱신 흐름:
  Tab7 차트 조회 완료
    → set_df(df) 호출 → 타이머 시작 (또는 재시작)
      → 300초마다 _on_refresh() 자동 실행
        → importlib.reload(combo_second_logic)
          → execute_logic(df) → UI 갱신
════════════════════════════════════════════════════════════════
"""

import importlib
import sys

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGridLayout, QFrame,
    QTabWidget, QWidget,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


AUTO_INTERVAL_SEC = 300   # 자동 갱신 주기 (초) — 필요 시 변경


# ── 점수 → 색상 ──────────────────────────────────────────────────
def _score_color(score: int) -> str:
    if score >= 85: return "#00e676"
    if score >= 60: return "#ffeb3b"
    if score >= 40: return "#ff9800"
    return "#ff5252"


def _bar_html(score: int, max_score: int, color: str) -> str:
    pct = min(100, int(score / max(max_score, 1) * 100))
    return (
        f'<div style="background:#1a1a2e;border-radius:3px;height:10px;width:100%;">'
        f'<div style="background:{color};width:{pct}%;height:10px;border-radius:3px;"></div>'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════════
class TrendScorePanel(QGroupBox):

    def __init__(self, mw, parent=None):
        super().__init__("📊 추세 점수판 (Trend Score)", parent)
        self.mw   = mw
        self._df  = None
        self._auto_on    = False          # 자동 갱신 활성 여부
        self._countdown  = 0             # 다음 갱신까지 남은 초

        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #2a2a4a;
                border-radius: 4px;
                margin-top: 6px;
                color: #aaaacc;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                color: #7c7cff;
                font-weight: bold;
            }
            QTabWidget::pane {
                border: 1px solid #2a2a4a;
                background: #0a0a18;
            }
            QTabBar::tab {
                background: #0e0e1e;
                color: #8888aa;
                border: 1px solid #2a2a4a;
                border-bottom: none;
                padding: 4px 10px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #1a1a3a;
                color: #aaaaff;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: #16162e;
                color: #ccccff;
            }
        """)
        self._build_ui()
        self._init_timers()

    # ── UI 구성 ──────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 14, 4, 4)
        root.setSpacing(2)

        # ── 탭 위젯 ──────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # 탭 1: 추세 점수 (기존 내용)
        self._tab_trend = QWidget()
        self._build_trend_tab(self._tab_trend)
        self._tabs.addTab(self._tab_trend, "📊 추세 점수")

        # 탭 2: 급변 감시
        self._tab_spike = self._build_spike_tab()
        self._tabs.addTab(self._tab_spike, "⚡ 급변 감시")

        root.addWidget(self._tabs)

    # ── 추세 점수 탭 내용 (기존 _build_ui 내용 그대로) ────────────
    def _build_trend_tab(self, container: QWidget):
        root = QVBoxLayout(container)
        root.setContentsMargins(6, 8, 6, 6)
        root.setSpacing(4)

        # 총점
        top = QHBoxLayout()
        self.lbl_total = QLabel("총점: ―")
        self.lbl_total.setFont(QFont("Arial", 16, QFont.Bold))
        self.lbl_total.setStyleSheet("color:#ffffff; border:none;")
        self.lbl_grade = QLabel("―")
        self.lbl_grade.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_grade.setStyleSheet("color:#aaaacc; font-size:12px; border:none;")
        top.addWidget(self.lbl_total)
        top.addStretch()
        top.addWidget(self.lbl_grade)
        root.addLayout(top)

        root.addWidget(self._hline())

        # 항목별 점수 그리드
        grid = QGridLayout()
        grid.setSpacing(4)
        for col, txt in enumerate(["항목", "점수", "만점", "게이지"]):
            lbl = QLabel(txt)
            lbl.setStyleSheet("color:#555577; font-size:11px; border:none;")
            grid.addWidget(lbl, 0, col)

        self._rows = {}
        for r, (key, label, max_s) in enumerate([
            ("direction", "📐 방향 (정배열)",   30),
            ("strength",  "💪 강도 (ADX)",      40),
            ("energy",    "⚡ 에너지 (RSI/BB)", 30),
        ], start=1):
            lbl_name  = QLabel(label)
            lbl_score = QLabel("―")
            lbl_max   = QLabel(f"/{max_s}")
            lbl_bar   = QLabel("")
            lbl_bar.setTextFormat(Qt.RichText)
            for w in (lbl_name, lbl_score, lbl_max, lbl_bar):
                w.setStyleSheet("border:none; color:#ccccdd; font-size:12px;")
            grid.addWidget(lbl_name,  r, 0)
            grid.addWidget(lbl_score, r, 1)
            grid.addWidget(lbl_max,   r, 2)
            grid.addWidget(lbl_bar,   r, 3)
            self._rows[key] = (lbl_score, lbl_bar, max_s)
        root.addLayout(grid)

        root.addWidget(self._hline())

        # 신호 요약
        sig = QHBoxLayout()
        self.lbl_adx   = self._sig_lbl("ADX: ―")
        self.lbl_rsi   = self._sig_lbl("RSI: ―")
        self.lbl_align = self._sig_lbl("정배열: ―")
        self.lbl_bb    = self._sig_lbl("BB돌파: ―")
        for w in (self.lbl_adx, self.lbl_rsi, self.lbl_align, self.lbl_bb):
            sig.addWidget(w)
        root.addLayout(sig)

        root.addWidget(self._hline())

        # ── 버튼 행 ──────────────────────────────────────────────
        btn_row = QHBoxLayout()

        # 수동 실행 버튼
        self.btn_refresh = QPushButton("🔄 지금 분석")
        self.btn_refresh.setFixedHeight(26)
        self.btn_refresh.setStyleSheet(self._btn_style("#1a1a4a", "#7c7cff", "#3a3a7a"))
        self.btn_refresh.clicked.connect(self._on_refresh)

        # 자동 갱신 토글 버튼
        self.btn_auto = QPushButton("▶ 자동시작")
        self.btn_auto.setFixedHeight(26)
        self.btn_auto.setFixedWidth(90)
        self.btn_auto.setStyleSheet(self._btn_style("#0a2a0a", "#00e676", "#1a4a1a"))
        self.btn_auto.clicked.connect(self._toggle_auto)

        # 카운트다운 라벨
        self.lbl_countdown = QLabel("")
        self.lbl_countdown.setStyleSheet("color:#555577; font-size:11px; border:none;")

        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_auto)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_countdown)
        root.addLayout(btn_row)

        # 상태 라벨
        self.lbl_status = QLabel("Tab7에서 차트 조회 후 DF 자동 수신")
        self.lbl_status.setStyleSheet("color:#555577; font-size:11px; border:none;")
        root.addWidget(self.lbl_status)

    # ── 급변 감시 탭 (SpikeMonitorTab 임베드) ────────────────────
    def _build_spike_tab(self) -> QWidget:
        try:
            from combo_ui_spike_tab import SpikeMonitorTab
            return SpikeMonitorTab()
        except Exception as e:
            # 임포트 실패 시 오류 안내 위젯 반환
            w = QWidget()
            lay = QVBoxLayout(w)
            lbl = QLabel(f"⚠ SpikeMonitorTab 로드 실패:\n{e}")
            lbl.setStyleSheet("color:#ff5252; font-size:12px; border:none;")
            lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(lbl)
            return w

    # ── 타이머 초기화 ────────────────────────────────────────────
    def _init_timers(self):
        # 자동 갱신 타이머 (300초마다 _on_refresh 실행)
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_INTERVAL_SEC * 1000)
        self._auto_timer.timeout.connect(self._on_refresh)

        # 카운트다운 표시 타이머 (1초마다 숫자 감소)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._on_tick)

    # ── DF 수신 ──────────────────────────────────────────────────
    def set_df(self, df):
        """
        Tab7 차트 조회 완료 시 자동 호출.
        DF 수신 즉시 분석 실행 + 자동 갱신 타이머 재시작.
        """
        self._df = df
        n = len(df) if df is not None else 0
        self.lbl_status.setText(f"DF 수신: {n}봉")

        # DF 수신 즉시 1회 분석
        self._on_refresh()

        # 자동 갱신이 켜져 있으면 타이머 재시작 (카운트 리셋)
        if self._auto_on:
            self._start_auto()

    # ── 자동 갱신 토글 ───────────────────────────────────────────
    def _toggle_auto(self):
        if self._auto_on:
            self._stop_auto()
        else:
            self._start_auto()

    def _start_auto(self):
        self._auto_on = True
        self._countdown = AUTO_INTERVAL_SEC
        self._auto_timer.start()
        self._tick_timer.start()
        self.btn_auto.setText("⏸ 자동중지")
        self.btn_auto.setStyleSheet(self._btn_style("#2a0a0a", "#ff5252", "#4a1a1a"))
        self._update_countdown()

    def _stop_auto(self):
        self._auto_on = False
        self._auto_timer.stop()
        self._tick_timer.stop()
        self.btn_auto.setText("▶ 자동시작")
        self.btn_auto.setStyleSheet(self._btn_style("#0a2a0a", "#00e676", "#1a4a1a"))
        self.lbl_countdown.setText("")

    # ── 1초 틱 — 카운트다운 표시 ─────────────────────────────────
    def _on_tick(self):
        self._countdown -= 1
        if self._countdown < 0:
            self._countdown = AUTO_INTERVAL_SEC
        self._update_countdown()

    def _update_countdown(self):
        m, s = divmod(self._countdown, 60)
        self.lbl_countdown.setText(f"다음 갱신: {m:02d}:{s:02d}")

    # ── 분석 실행 (수동 버튼 + 자동 타이머 공용) ─────────────────
    def _on_refresh(self):
        # ① 핫-리로드
        try:
            if "combo_second_logic" in sys.modules:
                importlib.reload(sys.modules["combo_second_logic"])
            import combo_second_logic as csl
        except Exception as e:
            self.lbl_status.setText(f"❌ 리로드 실패: {e}")
            return

        # ② DF 확인
        if self._df is None:
            self.lbl_status.setText("⚠ DF 없음 — Tab7에서 먼저 차트 조회")
            return

        # ③ 점수 계산
        try:
            result = csl.execute_logic(self._df)
        except Exception as e:
            self.lbl_status.setText(f"❌ 분석 오류: {e}")
            return

        # ④ UI 갱신
        self._apply_result(result)

        # ⑤ 카운트다운 리셋 (수동 클릭 시에도 타이머 리셋)
        if self._auto_on:
            self._auto_timer.start()          # restart
            self._countdown = AUTO_INTERVAL_SEC
            self._update_countdown()

        # ⑥ Tab4 로그 출력
        try:
            combo = getattr(self.mw, 'tab_combo', None)
            if combo and hasattr(combo, '_log'):
                combo._log(
                    f"[추세분석] 총점={result['total_score']}  "
                    f"{result.get('message', '')}"
                )
        except Exception:
            pass

    # ── 결과 → UI 반영 ───────────────────────────────────────────
    def _apply_result(self, result: dict):
        from datetime import datetime
        total   = result.get("total_score", 0)
        details = result.get("details", {})
        signals = result.get("signals", {})
        message = result.get("message", "")

        color = _score_color(total)
        self.lbl_total.setText(f"총점: {total} / 100")
        self.lbl_total.setStyleSheet(
            f"color:{color}; border:none; font-size:16px; font-weight:bold;")
        self.lbl_grade.setText(message)

        for key, (lbl_score, lbl_bar, max_s) in self._rows.items():
            s = details.get(key, 0)
            c = _score_color(int(s / max_s * 100)) if max_s else "#555577"
            lbl_score.setText(str(s))
            lbl_score.setStyleSheet(f"border:none; color:{c}; font-size:12px;")
            lbl_bar.setText(_bar_html(s, max_s, c))

        adx   = signals.get("adx", 0)
        rsi   = signals.get("rsi", 0)
        align = signals.get("is_alignment", False)
        bb    = signals.get("bb_break", False)

        self.lbl_adx.setText(f"ADX: {adx}")
        self.lbl_adx.setStyleSheet(self._sig_style("#00e676" if adx >= 25 else "#ff5252"))
        self.lbl_rsi.setText(f"RSI: {rsi}")
        self.lbl_rsi.setStyleSheet(self._sig_style("#00e676" if rsi > 60 else "#aaaacc"))
        self.lbl_align.setText("정배열: ✅" if align else "정배열: ✗")
        self.lbl_align.setStyleSheet(self._sig_style("#00e676" if align else "#ff5252"))
        self.lbl_bb.setText("BB돌파: ✅" if bb else "BB돌파: ✗")
        self.lbl_bb.setStyleSheet(self._sig_style("#00e676" if bb else "#aaaacc"))

        now = datetime.now().strftime("%H:%M:%S")
        self.lbl_status.setText(f"✅ 갱신: {now}")

    # ── 스타일 헬퍼 ──────────────────────────────────────────────
    @staticmethod
    def _hline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color:#2a2a4a;")
        return f

    @staticmethod
    def _sig_lbl(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "background:#0d0d1f; border:1px solid #2a2a4a; "
            "border-radius:3px; padding:2px 6px; "
            "color:#aaaacc; font-size:11px;")
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    @staticmethod
    def _sig_style(color: str) -> str:
        return (
            f"background:#0d0d1f; border:1px solid #2a2a4a; "
            f"border-radius:3px; padding:2px 6px; "
            f"color:{color}; font-size:11px;"
        )

    @staticmethod
    def _btn_style(bg: str, fg: str, border: str) -> str:
        return (
            f"QPushButton {{ background:{bg}; color:{fg}; "
            f"border:1px solid {border}; border-radius:3px; font-size:12px; }}"
            f"QPushButton:hover {{ background:{border}; }}"
            f"QPushButton:pressed {{ background:#000020; }}"
        )
