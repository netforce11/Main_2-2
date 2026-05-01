"""
tab_combo_strategy.py — 탭4: 복합 전략  v2.3
════════════════════════════════════════════════════════════════
v2.3 변경:
  - 관심종목 패널 제거 (combo_ui_left.py)
  - 추세점수판(TrendScorePanel)을 우측 상단 → 좌측 하단으로 이동
  - _build_left_with_trend() 추가: 옵션체인(상단) + 추세점수판(하단)
  - _build_right_with_optimizer() 에서 추세점수판 제거

v2.2 변경:
  - TrendScorePanel (combo_trend_panel.py) 연결
  - set_trend_df() 추가 → Tab7(ChartGrid)에서 DF push 가능

v2.1 — Cost Optimizer 패널 추가
v2.0 — 파일 분리 (200줄 단위 기능별)

모듈 구조:
  combo_constants.py    — 상수 / 전략 목록 / 전략 설명 / 공통 유틸
  combo_ui_left.py      — 좌측 패널 (옵션 체인) Mixin
  combo_ui_right_panel.py — 우측 패널 (전략 설정 + 결과) Mixin
  combo_logic.py        — 손익 계산 로직 Mixin
  combo_optimizer.py    — Cost Optimizer 패널 + 탐색 로직 Mixin
  combo_trend_panel.py  — 추세 점수판 UI 위젯
  combo_second_logic.py — 추세 점수 연산 모듈
  tab_combo_strategy.py — 메인 조립 클래스 (이 파일)

레이아웃 (v2.3):
  수평 스플리터
  ├── 좌측 (수직 스플리터)
  │     ├── 옵션 체인 (콜/풋)
  │     └── 추세 점수판  ← v2.3: 우측에서 이동
  └── 우측 (수직 스플리터)
        ├── 전략 설정
        ├── Cost Optimizer
        ├── 손익 결과
        └── 차트
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer

from core import bridge, build_expiry_list, ts, REQ_UND

from combo_constants   import SPLITTER_STYLE
from combo_ui_left     import LeftPanelMixin
from combo_ui_right_panel import RightPanelMixin
from combo_logic       import PnlLogicMixin
from combo_optimizer   import OptimizerPanelMixin
from combo_trend_panel import TrendScorePanel
from tab_combo_shortcut import ShortcutMixin


# ══════════════════════════════════════════════════════════════
class ComboStrategyGrid(
    ShortcutMixin,
    LeftPanelMixin,
    RightPanelMixin,
    PnlLogicMixin,
    OptimizerPanelMixin,
    QWidget,
):
    """복합 전략 손익 분석 탭 (탭4)."""

    def __init__(self, mw):
        super().__init__()
        self.mw = mw

        self._expiry_list      = build_expiry_list()
        self._und_price        = None
        self._chain_call       = {}
        self._chain_put        = {}
        self._call_strikes     = []
        self._put_strikes      = []
        self._opt_results      = []
        self._opt_selected_row = -1

        self._trend_panel: TrendScorePanel | None = None

        # [S11] Chaser 상태 미리 초기화 — _on_chase_click 방어
        from combo_order_chaser import init_chaser_state
        init_chaser_state(self)

        self._build()
        self._connect_signals()

        # synthetic_panel 콜백 연결 (margin_mode, close_pos, chaser 등)
        try:
            from combo_order_logic import _init_synthetic_panel_callbacks
            _init_synthetic_panel_callbacks(self)
        except Exception as _e:
            print(f"[ComboStrategyGrid] 콜백 초기화 오류: {_e}")

        # [S11] 연결 시 계좌 표시 갱신 — 이미 연결된 경우 즉시 시도
        QTimer.singleShot(500, self._refresh_account_display)

    # ──────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        self._main_hsplit = QSplitter(Qt.Horizontal)
        self._main_hsplit.setHandleWidth(6)
        self._main_hsplit.setStyleSheet(SPLITTER_STYLE)
        self._main_hsplit.setChildrenCollapsible(False)

        self._main_hsplit.addWidget(self._build_left_with_trend())   # ← v2.3
        self._main_hsplit.addWidget(self._build_right_with_optimizer())
        self._main_hsplit.setSizes([380, 900])
        root.addWidget(self._main_hsplit, 1)
        root.addWidget(self._build_log_panel())

        self._on_strat_change(0)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(3000)
        self._sync_timer.timeout.connect(self._auto_sync_chain)
        self._sync_timer.start()

        # 단축키 이벤트 필터 설치 (ShortcutMixin)
        self._install_shortcuts()

    # ── v2.3: 좌측 = 옵션 체인(상단) + 추세점수판(하단) ────────
    def _build_left_with_trend(self) -> QSplitter:
        """좌측 수직 스플리터: 옵션 체인 + 추세점수판."""
        self._left_vsplit = QSplitter(Qt.Vertical)
        self._left_vsplit.setHandleWidth(6)
        self._left_vsplit.setStyleSheet(SPLITTER_STYLE)
        self._left_vsplit.setChildrenCollapsible(False)

        # 상단: 옵션 체인
        self._left_vsplit.addWidget(self._build_left_panel())

        # 하단: 추세 점수판
        self._trend_panel = TrendScorePanel(self.mw)
        self._left_vsplit.addWidget(self._trend_panel)

        self._left_vsplit.setSizes([540, 160])
        return self._left_vsplit

    # ── 우측 패널: RightPanelMixin._build_right_panel() 에 위임 (v2.6) ──
    def _build_right_with_optimizer(self) -> QWidget:
        """
        RightPanelMixin._build_right_panel() 으로 통합.
        계좌바 / 전략설정 / 손익결과|곡선 / Optimizer 슬라이드
        모두 combo_ui_right_panel.py 에서 빌드.
        """
        return self._build_right_panel()

    # ── Tab7(ChartGrid) → DF 수신 진입점 ───────────────────────
    def set_trend_df(self, df):
        """
        Tab7(ChartGrid)에서 1분봉 DF를 이 탭으로 push할 때 호출.

        tab_chart.py 연결 예시
        ─────────────────────
        # tab_chart.py 의 _on_bar_close() 또는 _fetch_done() 안에서:

            combo = getattr(self.mw, 'tab_combo', None)
            if combo and hasattr(combo, 'set_trend_df'):
                combo.set_trend_df(self._df_1min)

        DF 컬럼 (소문자 통일):
            open, high, low, close, volume
        """
        if self._trend_panel:
            self._trend_panel.set_df(df)

    # ──────────────────────────────────────────────────────────
    def _build_log_panel(self) -> QGroupBox:
        gb = QGroupBox("로그")
        from PyQt5.QtWidgets import QVBoxLayout as VL
        v  = VL(gb); v.setContentsMargins(2, 2, 2, 2)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        fm = self.log_box.fontMetrics()
        self.log_box.setFixedHeight(fm.height() * 2 + 10)
        self.log_box.setStyleSheet(
            "background:#05050f;color:#00e676;font-size:13px;border:none;")
        v.addWidget(self.log_box)
        return gb

    # ──────────────────────────────────────────────────────────
    def _connect_signals(self):
        bridge.tick_price.connect(self._on_tick_price)
        # [S11] 연결/재연결 시 계좌 표시 자동 갱신
        bridge.connected.connect(self._refresh_account_display)

    def _on_tick_price(self, rid, tt, price):
        REQ_COMBO_UND = 8500  # 콤보탭 전용 기초자산 reqId (combo_ui_left._req_sym_price 참조)
        if rid in (REQ_UND, REQ_COMBO_UND) and tt in (4, 68, 75) and price > 0:
            self._und_price = price
            QTimer.singleShot(0, lambda: self.lbl_sym_price.setText(
                f"현재가: {price:,.2f}"))

    def _log(self, msg: str):
        self.log_box.append(f"[{ts()}] {msg}")
        lines = self.log_box.toPlainText().split("\n")
        if len(lines) > 200:
            self.log_box.setPlainText("\n".join(lines[-150:]))

    # ──────────────────────────────────────────────────────────
    def _get_extra_settings(self) -> dict:
        d = {"strat_idx": self.combo_strat.currentIndex()}
        try:
            d["main_hsplit"] = list(self._main_hsplit.sizes())
            d["left_vsplit"] = list(self._left_vsplit.sizes())
            d["mid_hsplit"]  = list(self._mid_hsplit.sizes())
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        if s.get("strat_idx") is not None:
            idx = int(s["strat_idx"])
            self.combo_strat.blockSignals(True)
            self.combo_strat.setCurrentIndex(idx)
            self.combo_strat.blockSignals(False)
            self._on_strat_change(idx)

        def _restore():
            try:
                if s.get("main_hsplit"):
                    self._main_hsplit.setSizes(s["main_hsplit"])
                if s.get("left_vsplit"):
                    self._left_vsplit.setSizes(s["left_vsplit"])
                if s.get("mid_hsplit"):
                    self._mid_hsplit.setSizes(s["mid_hsplit"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)