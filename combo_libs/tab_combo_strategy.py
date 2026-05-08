"""
tab_combo_strategy.py — 탭4: 복합 전략  v2.3
════════════════════════════════════════════════════════════════
[FIX-H] bridge.connected 중복 연결 방지
  - _connect_signals() 가 재호출될 때(탭 재활성화, 위젯 재생성 등)
    동일 슬롯이 중복 연결되면 Qt 는 연결 수 만큼 다중 호출함.
  - _signals_connected 플래그로 최초 1회만 연결.
  - 연결 해제가 필요한 경우 _disconnect_signals() 를 먼저 호출.
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer

from core import bridge, build_expiry_list, ts, REQ_UND

from combo_constants      import SPLITTER_STYLE
from combo_ui_left        import LeftPanelMixin
from combo_ui_right_panel import RightPanelMixin
from combo_logic          import PnlLogicMixin
from combo_optimizer      import OptimizerPanelMixin
from combo_trend_panel    import TrendScorePanel
from tab_combo_shortcut   import ShortcutMixin


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
        # [FIX-H] 중복 연결 방지 플래그
        self._signals_connected = False

        from combo_order_chaser import init_chaser_state
        init_chaser_state(self)

        self._build()
        self._connect_signals()

        try:
            from combo_order_logic import _init_synthetic_panel_callbacks
            _init_synthetic_panel_callbacks(self)
        except Exception as _e:
            print(f"[ComboStrategyGrid] 콜백 초기화 오류: {_e}")

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

        self._main_hsplit.addWidget(self._build_left_with_trend())
        self._main_hsplit.addWidget(self._build_right_with_optimizer())
        self._main_hsplit.setSizes([380, 900])
        root.addWidget(self._main_hsplit, 1)
        root.addWidget(self._build_log_panel())

        self._on_strat_change(0)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(3000)
        self._sync_timer.timeout.connect(self._auto_sync_chain)
        self._sync_timer.start()

        self._install_shortcuts()

    def _build_left_with_trend(self) -> QSplitter:
        self._left_vsplit = QSplitter(Qt.Vertical)
        self._left_vsplit.setHandleWidth(6)
        self._left_vsplit.setStyleSheet(SPLITTER_STYLE)
        self._left_vsplit.setChildrenCollapsible(False)
        self._left_vsplit.addWidget(self._build_left_panel())
        self._trend_panel = TrendScorePanel(self.mw)
        self._left_vsplit.addWidget(self._trend_panel)
        self._left_vsplit.setSizes([540, 160])
        return self._left_vsplit

    def _build_right_with_optimizer(self) -> QWidget:
        return self._build_right_panel()

    def set_trend_df(self, df):
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
        """
        [FIX-H] _signals_connected 플래그로 중복 연결 완전 차단.
        Qt 는 같은 시그널에 같은 슬롯을 여러 번 connect() 하면
        연결 수만큼 다중 호출하므로 반드시 1회만 연결해야 한다.
        """
        if self._signals_connected:
            return

        bridge.tick_price.connect(self._on_tick_price)
        bridge.connected.connect(self._refresh_account_display)
        bridge.connected.connect(self._on_pos_reconnect_hook)

        self._signals_connected = True

    def _disconnect_signals(self):
        """
        위젯 소멸 또는 재구성 전 시그널 연결 해제.
        closeEvent 또는 탭 재생성 시 호출.
        """
        if not self._signals_connected:
            return
        try:
            bridge.tick_price.disconnect(self._on_tick_price)
        except Exception:
            pass
        try:
            bridge.connected.disconnect(self._refresh_account_display)
        except Exception:
            pass
        try:
            bridge.connected.disconnect(self._on_pos_reconnect_hook)
        except Exception:
            pass
        self._signals_connected = False

    def closeEvent(self, event):
        """위젯 닫힐 때 시그널 해제."""
        self._disconnect_signals()
        super().closeEvent(event)

    # ──────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        REQ_COMBO_UND = 8500
        if rid in (REQ_UND, REQ_COMBO_UND) and tt in (4, 68, 75) and price > 0:
            self._und_price = price
            QTimer.singleShot(0, lambda: self.lbl_sym_price.setText(
                f"현재가: {price:,.2f}"))

    def _on_pos_reconnect_hook(self):
        """재연결 후 합성 잔고 복원 — combo_order_logic 으로 위임."""
        try:
            from combo_order_logic import _on_pos_reconnect_hook as _hook
            _hook(self)
        except Exception as e:
            self._log(f"⚠ 잔고 복원 오류: {e}")

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
