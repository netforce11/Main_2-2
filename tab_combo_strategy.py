"""
tab_combo_strategy.py — 탭4: 복합 전략  v2.1
════════════════════════════════════════════════════════════════
변경:
  v2.1 — Cost Optimizer 패널 추가
           (허용 손실 + 최소 수익률 기반 행사가 탐색)
  v2.0 — 파일 분리 (200줄 단위 기능별)
         콜 데빗 스프레드 / 풋 데빗 스프레드 신규 추가
         전략 선택 시 ❓ 버튼 → 설명 팝업
         레그 테이블 "만기" 칼럼 날짜 포맷 수정 (YYYYMMDD → MM/DD)

모듈 구조:
  combo_constants.py    — 상수 / 전략 목록 / 전략 설명 / 공통 유틸
  combo_ui_left.py      — 좌측 패널 (옵션 체인 + 관심종목) Mixin
  combo_ui_right.py     — 우측 패널 (전략 설정 + 결과) Mixin
  combo_logic.py        — 손익 계산 로직 Mixin
  combo_optimizer.py    — Cost Optimizer 패널 + 탐색 로직 Mixin
  tab_combo_strategy.py — 메인 조립 클래스 (이 파일)

레이아웃:
  수평 스플리터
  ├── 좌측: 옵션 체인 / 관심종목
  └── 우측: 전략 설정 → Cost Optimizer → 손익 결과 → 차트
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer

from core import bridge, build_expiry_list, ts, REQ_UND

from combo_constants  import SPLITTER_STYLE
from combo_ui_left    import LeftPanelMixin
from combo_ui_right   import RightPanelMixin
from combo_logic      import PnlLogicMixin
from combo_optimizer  import OptimizerPanelMixin


# ══════════════════════════════════════════════════════════════
class ComboStrategyGrid(
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

        self._build()
        self._connect_signals()

    # ──────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        self._main_hsplit = QSplitter(Qt.Horizontal)
        self._main_hsplit.setHandleWidth(6)
        self._main_hsplit.setStyleSheet(SPLITTER_STYLE)
        self._main_hsplit.setChildrenCollapsible(False)

        self._main_hsplit.addWidget(self._build_left_panel())
        self._main_hsplit.addWidget(self._build_right_with_optimizer())
        self._main_hsplit.setSizes([380, 900])
        root.addWidget(self._main_hsplit, 1)
        root.addWidget(self._build_log_panel())

        self._on_strat_change(0)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(3000)
        self._sync_timer.timeout.connect(self._auto_sync_chain)
        self._sync_timer.start()

    def _build_right_with_optimizer(self) -> QSplitter:
        """전략설정 | Optimizer | 결과 | 차트 — 4분할."""
        self._right_vsplit = QSplitter(Qt.Vertical)
        self._right_vsplit.setHandleWidth(6)
        self._right_vsplit.setStyleSheet(SPLITTER_STYLE)
        self._right_vsplit.setChildrenCollapsible(False)

        self._right_vsplit.addWidget(self._build_strategy_input_panel())
        self._right_vsplit.addWidget(self._build_optimizer_panel())
        self._right_vsplit.addWidget(self._build_result_panel())
        self._right_vsplit.addWidget(self._build_spread_chart_panel())
        self._right_vsplit.setSizes([220, 260, 260, 200])
        return self._right_vsplit

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

    def _on_tick_price(self, rid, tt, price):
        if rid == REQ_UND and tt in (4, 68, 75) and price > 0:
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
            d["main_hsplit"]  = list(self._main_hsplit.sizes())
            d["left_vsplit"]  = list(self._left_vsplit.sizes())
            d["right_vsplit"] = list(self._right_vsplit.sizes())
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
                if s.get("right_vsplit"):
                    self._right_vsplit.setSizes(s["right_vsplit"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)