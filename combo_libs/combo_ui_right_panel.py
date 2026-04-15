"""
combo_ui_right_panel.py — 우측 패널 UI 빌드 전담
────────────────────────────────────────────────
포함: RightPanelMixin (UI 구조만)
의존: combo_constants, combo_ui_synthetic_panel, pyqtgraph(optional)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox, QSplitter, QSpinBox,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import SPLITTER_STYLE, STRATEGIES, STRATEGY_DESC, LEG_COLORS
from combo_ui_synthetic_panel import SyntheticStatusPanel
from combo_ui_leg_panel       import _build_leg_left          # noqa: F401
from combo_ui_chaser_row      import _build_chaser_row        # noqa: F401
from combo_ui_right_panels_ext import (                       # noqa: F401
    _build_result_panel, _build_spread_chart_panel,
    _show_strat_desc, _toggle_optimizer_panel,
)


class RightPanelMixin:
    """우측 패널 UI 빌드 Mixin (전략설정 / 손익결과 / 차트)."""

    # ── 최상위 ────────────────────────────────────────────────
    def _build_right_panel(self) -> QWidget:
        container = QWidget()
        cv = QVBoxLayout(container)
        cv.setSpacing(4); cv.setContentsMargins(0, 0, 0, 0)

        # ── [S11] 계좌 안전장치 바 ─────────────────────────────
        cv.addWidget(self._build_account_safety_bar())

        cv.addWidget(self._build_strategy_input_panel())

        self._mid_hsplit = QSplitter(Qt.Horizontal)
        self._mid_hsplit.setHandleWidth(6)
        self._mid_hsplit.setStyleSheet(SPLITTER_STYLE)
        self._mid_hsplit.setChildrenCollapsible(False)
        self._mid_hsplit.addWidget(self._build_result_panel())
        self._mid_hsplit.addWidget(self._build_spread_chart_panel())
        self._mid_hsplit.setSizes([1, 1])
        cv.addWidget(self._mid_hsplit, 1)

        self._opt_wrapper = QWidget()
        self._opt_wrapper.setMaximumHeight(0)
        ow = QVBoxLayout(self._opt_wrapper)
        ow.setContentsMargins(0, 4, 0, 0)
        ow.addWidget(self._build_optimizer_panel())
        cv.addWidget(self._opt_wrapper)
        return container

    # ── 전략 설정 패널 ────────────────────────────────────────
    def _build_strategy_input_panel(self) -> QGroupBox:
        gb = QGroupBox("📋 전략 설정")
        outer = QVBoxLayout(gb)
        outer.setSpacing(4); outer.setContentsMargins(6, 6, 6, 6)

        hsplit = QSplitter(Qt.Horizontal)
        hsplit.setHandleWidth(5); hsplit.setStyleSheet(SPLITTER_STYLE)
        hsplit.setChildrenCollapsible(False)
        hsplit.addWidget(self._build_leg_left())
        hsplit.addWidget(self._build_leg_right())
        hsplit.setSizes([1, 1])

        outer.addWidget(hsplit, 1)
        gb.setMinimumHeight(220)
        return gb

    # _build_leg_left    → combo_ui_leg_panel._build_leg_left (모듈 레벨 import)
    # _build_result_panel / _build_spread_chart_panel / _show_strat_desc
    # _toggle_optimizer_panel → combo_ui_right_panels_ext (모듈 레벨 import)

    def _build_leg_right(self) -> QWidget:
        """우측: 기초자산 입력 + 버튼 + Chase 행 + SyntheticStatusPanel."""
        w = QWidget(); v = QVBoxLayout(w)
        v.setSpacing(4); v.setContentsMargins(4, 2, 2, 2)

        # 주식 현재가
        sr = QHBoxLayout(); sr.setSpacing(6)
        sr.addWidget(QLabel("주식 현재가:"))
        self.edit_stock_price = QLineEdit()
        self.edit_stock_price.setPlaceholderText("커버드콜·프로텍티브풋")
        self.edit_stock_price.setFixedHeight(26)
        self.edit_stock_price.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;")
        sr.addWidget(self.edit_stock_price, 1)
        sr.addWidget(QLabel("수량:"))
        self.spin_stock_qty = QSpinBox()
        self.spin_stock_qty.setRange(1, 100000)
        self.spin_stock_qty.setValue(100)
        self.spin_stock_qty.setSuffix(" 주")
        self.spin_stock_qty.setFixedHeight(26)
        sr.addWidget(self.spin_stock_qty)
        v.addLayout(sr)

        # ════════════════════════════════════════════════════
        # 버튼 그룹 A: 손익계산 / 증거금조회 / 초기화
        # ════════════════════════════════════════════════════
        grp_a = QHBoxLayout(); grp_a.setSpacing(4)

        def _mk_btn(text, bg, fg, fn, obj_name=None):
            b = QPushButton(text)
            b.setFixedHeight(28)
            nm = obj_name or ""
            if nm:
                b.setObjectName(nm)
                b.setStyleSheet(
                    f"QPushButton#{nm}{{background:{bg};color:{fg};"
                    f"border:1px solid {fg};border-radius:4px;font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;}}"
                    f"QPushButton#{nm}:hover{{background:{fg};color:#000;}}"
                    f"QPushButton#{nm}:disabled{{background:#111;color:#444;border-color:#333;}}")
            else:
                b.setStyleSheet(
                    f"background:{bg};color:{fg};font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;border-radius:4px;")
            b.clicked.connect(fn)
            return b

        grp_a.addWidget(_mk_btn("📊 손익 계산",  "#1a5c2e", "#00ff88", self._calc_pnl))
        grp_a.addWidget(_mk_btn("💰 증거금 조회", "#1a1a0e", "#ffd700", self._on_check_margin, "btn_check_margin"))
        self.btn_check_margin = grp_a.itemAt(1).widget()
        grp_a.addWidget(_mk_btn("🗑 초기화",      "#5a1a1a", "#ff6666", self._reset_legs))
        grp_a.addWidget(_mk_btn("🔍 Optimiser ▼", "#1a2a4a", "#90caf9", self._toggle_optimizer_panel))
        self._btn_opt_toggle = grp_a.itemAt(3).widget()

        # 구분선
        sep = QLabel("│")
        sep.setStyleSheet("color:#333;font-size:16px;border:none;")
        sep.setFixedWidth(12)
        sep.setAlignment(Qt.AlignCenter)
        grp_a.addWidget(sep)

        # ════════════════════════════════════════════════════
        # 버튼 그룹 B: 합성주문 / 미체결 / 정정 / 취소
        # ════════════════════════════════════════════════════
        self.btn_synthetic_order = _mk_btn(
            "⚡ 합성 주문", "#0e2e1a", "#00ff88",
            self._on_synthetic_order, "btn_synthetic_order")
        grp_a.addWidget(self.btn_synthetic_order)

        self.btn_open_orders = _mk_btn(
            "📋 미체결", "#1a1a3a", "#aabbff",
            self._on_open_orders, "btn_open_orders")
        grp_a.addWidget(self.btn_open_orders)

        self.btn_modify_order = _mk_btn(
            "✏ 정정", "#2a1a0a", "#ffaa44",
            self._on_modify_order, "btn_modify_order")
        grp_a.addWidget(self.btn_modify_order)

        self.btn_cancel_order = _mk_btn(
            "✖ 취소", "#2a0a0a", "#ff4444",
            self._on_cancel_order, "btn_cancel_order")
        grp_a.addWidget(self.btn_cancel_order)

        v.addLayout(grp_a)

        # ── 버튼 행 2: Smart Chaser ─────────────────────────────
        v.addWidget(self._build_chaser_row())

        self.synthetic_panel = SyntheticStatusPanel()
        v.addWidget(self.synthetic_panel, 1)

        # ── synthetic_panel 콜백 연결 (생성 직후 1회) ──────────
        # _init_synthetic_panel_callbacks가 외부에서 호출되지 않을 경우 대비
        try:
            from combo_order_logic import _init_synthetic_panel_callbacks
            _init_synthetic_panel_callbacks(self)
        except Exception as _e:
            print(f"[ComboUI] 콜백 초기화 오류: {_e}")

        return w

    # ── 미체결 / 정정 / 취소 핸들러 ─────────────────────────────
    def _on_open_orders(self):
        """미체결 주문 조회 → SyntheticStatusPanel 미체결 탭으로 이동."""
        from combo_order_open import on_open_orders, _modify_tick, _cancel_selected
        panel = getattr(self, 'synthetic_panel', None)
        if panel:
            panel._tabs.setCurrentIndex(2)
            # 조회 버튼 연결 (최초 1회)
            if not getattr(self, '_open_orders_btn_connected', False):
                panel._btn_refresh_orders.clicked.connect(
                    lambda: on_open_orders(self))
                panel._btn_modify_p1.clicked.connect(
                    lambda: _modify_tick(self, +1))
                panel._btn_modify_m1.clicked.connect(
                    lambda: _modify_tick(self, -1))
                panel._btn_cancel_all.clicked.connect(
                    lambda: _cancel_selected(self))
                self._open_orders_btn_connected = True
        on_open_orders(self)

    def _on_modify_order(self):
        """정정 주문 — 미체결 조회 후 선택 정정."""
        from combo_order_open import on_modify_order
        on_modify_order(self)

    def _on_cancel_order(self):
        """취소 — 미체결 조회 후 탭에서 선택 취소."""
        from combo_order_open import _cancel_selected
        _cancel_selected(self)

    def _on_chaser_mode_changed(self, btn):
        """수동/자동 라디오 전환 시 UI 업데이트."""
        is_auto = self._rb_chaser_auto.isChecked()
        self._lbl_chaser_desc.setVisible(is_auto)
        chaser_active = getattr(self, '_chaser_active', False)
        self.btn_chase.setEnabled(not is_auto or not chaser_active)

    # ── [S11] 계좌 안전장치 바 ─────────────────────────────────
    def _build_account_safety_bar(self) -> QWidget:
        """
        복합 전략 탭 최상단 — 현재 연결 계좌 표시 + 실계좌 경고.

        동작:
          • bridge.connected 수신 후 managedAccounts 콜백으로 계좌번호 자동 갱신
          • DU로 시작 → 🟢 모의투자  /  그 외 → 🔴 실계좌 (주황 경고)
          • 실계좌 상태에서 합성 주문 버튼 클릭 시 확인 팝업 (별도 guard)
        """
        from PyQt5.QtWidgets import QFrame
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            "QFrame{background:#0a0a1a;border-bottom:1px solid #2a2a4a;}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 2, 8, 2); h.setSpacing(8)

        # 연결 상태 점
        self._acct_dot = QLabel("●")
        self._acct_dot.setStyleSheet(
            "color:#444;font-size:13px;border:none;")
        h.addWidget(self._acct_dot)

        # 계좌 번호 / 모드
        self._acct_lbl = QLabel("미연결")
        self._acct_lbl.setStyleSheet(
            "color:#666;font-size:12px;font-weight:bold;border:none;")
        h.addWidget(self._acct_lbl)

        # 모드 뱃지
        self._acct_mode_lbl = QLabel("")
        self._acct_mode_lbl.setStyleSheet(
            "color:#666;font-size:11px;border:none;")
        h.addWidget(self._acct_mode_lbl)

        h.addStretch()

        # 실계좌 경고 아이콘 (평소 숨김)
        self._acct_warn_lbl = QLabel("⚠ 실계좌 — 주문 전 반드시 확인")
        self._acct_warn_lbl.setStyleSheet(
            "color:#ff9800;font-size:11px;font-weight:bold;border:none;")
        self._acct_warn_lbl.setVisible(False)
        h.addWidget(self._acct_warn_lbl)

        # bridge.connected 수신 시 계좌 갱신
        try:
            from core import bridge
            bridge.connected.connect(self._refresh_account_display)
        except Exception:
            pass

        return bar

    def _refresh_account_display(self):
        """
        연결 직후 호출 — managedAccounts 콜백에서 계좌번호 수신.
        ib.reqManagedAccts()로 트리거 후 콜백에서 _set_account_info() 호출.
        """
        ib = getattr(self, 'mw', None)
        ib = getattr(ib, 'ib', None) if ib else None
        if ib is None:
            return

        # managedAccounts 콜백 패치 (1회성)
        _orig = getattr(ib, 'managedAccounts', lambda a: None)

        def _on_managed(accounts_str: str):
            try: _orig(accounts_str)
            except Exception: pass
            # 첫 번째 계좌 사용
            acct = accounts_str.split(",")[0].strip() if accounts_str else ""
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._set_account_info(acct))
            # 콜백 원복
            ib.managedAccounts = _orig

        ib.managedAccounts = _on_managed
        try:
            ib.reqManagedAccts()
        except Exception:
            pass

    def _set_account_info(self, acct: str):
        """계좌번호 기반 UI 갱신 — 모의/실계좌 분기."""
        if not acct:
            return
        is_paper = acct.upper().startswith("DU")

        if is_paper:
            dot_col   = "#00e676"
            mode_text = "🟢 모의투자 (Paper)"
            mode_col  = "#00e676"
            warn_vis  = False
        else:
            dot_col   = "#ff5252"
            mode_text = "🔴 실계좌 (Live)"
            mode_col  = "#ff5252"
            warn_vis  = True

        self._acct_dot.setStyleSheet(
            f"color:{dot_col};font-size:13px;border:none;")
        self._acct_lbl.setText(acct)
        self._acct_lbl.setStyleSheet(
            f"color:{dot_col};font-size:12px;font-weight:bold;border:none;")
        self._acct_mode_lbl.setText(mode_text)
        self._acct_mode_lbl.setStyleSheet(
            f"color:{mode_col};font-size:11px;border:none;")
        self._acct_warn_lbl.setVisible(warn_vis)

        # 실계좌 여부 캐싱 (주문 guard에서 사용)
        self._is_live_account = not is_paper
        self._current_account = acct

    def _guard_live_order(self) -> bool:
        """
        실계좌일 때 합성 주문 직전 확인 팝업.
        True → 주문 진행 / False → 취소.
        모의계좌면 묻지 않고 True 반환.
        """
        if not getattr(self, '_is_live_account', False):
            return True   # 모의계좌 → 바로 통과

        acct = getattr(self, '_current_account', '실계좌')
        from PyQt5.QtWidgets import QMessageBox
        ret = QMessageBox.warning(
            self,
            "⚠ 실계좌 주문 확인",
            f"현재 <b>{acct}</b> (실계좌)에 연결되어 있습니다.<br><br>"
            f"합성 주문을 실행하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,   # 기본값: No (실수 방지)
        )
        return ret == QMessageBox.Yes

    def _on_chase_click(self):
        """Chase 버튼 → combo_order_chaser.on_chase_click 위임."""
        from combo_order_chaser import on_chase_click, init_chaser_state
        # _chaser_active 미초기화 방어 — 최초 클릭 시 안전하게 초기화
        if not hasattr(self, '_chaser_active'):
            init_chaser_state(self)
        on_chase_click(self)

    # ── ext 모듈 함수를 클래스 메서드로 바인딩 ────────────────────
    # (모듈 레벨 import 후 클래스 바디에 직접 할당)


# 클래스 정의 완료 후 외부 함수 mixin 바인딩
RightPanelMixin._build_leg_left           = _build_leg_left           # type: ignore[attr-defined]
RightPanelMixin._build_chaser_row         = _build_chaser_row         # type: ignore[attr-defined]
RightPanelMixin._build_result_panel       = _build_result_panel       # type: ignore[attr-defined]
RightPanelMixin._build_spread_chart_panel = _build_spread_chart_panel # type: ignore[attr-defined]
RightPanelMixin._show_strat_desc          = _show_strat_desc          # type: ignore[attr-defined]
RightPanelMixin._toggle_optimizer_panel   = _toggle_optimizer_panel   # type: ignore[attr-defined]

# combo_order_open 핸들러 — 런타임 바인딩
import types as _types
def _on_open_orders(self):
    from combo_order_open import on_open_orders; on_open_orders(self)
def _on_modify_order(self):
    from combo_order_open import on_modify_order; on_modify_order(self)
def _on_cancel_order(self):
    from combo_order_open import on_cancel_order; on_cancel_order(self)

RightPanelMixin._on_open_orders  = _on_open_orders   # type: ignore[attr-defined]
RightPanelMixin._on_modify_order = _on_modify_order  # type: ignore[attr-defined]
RightPanelMixin._on_cancel_order = _on_cancel_order  # type: ignore[attr-defined]

# combo_ui_leg_logic 핸들러 바인딩
from combo_ui_leg_logic import (
    _on_strat_change, _get_leg_template, _rebuild_legs,
    _reset_legs, _set_leg_mode,
)
RightPanelMixin._on_strat_change  = _on_strat_change   # type: ignore[attr-defined]
RightPanelMixin._get_leg_template = _get_leg_template  # type: ignore[attr-defined]
RightPanelMixin._rebuild_legs     = _rebuild_legs       # type: ignore[attr-defined]
RightPanelMixin._reset_legs       = _reset_legs         # type: ignore[attr-defined]
RightPanelMixin._set_leg_mode     = _set_leg_mode       # type: ignore[attr-defined]

# combo_ui_leg_extra 바인딩 (v2.6 — manual/extra 레그 버튼)
from combo_ui_leg_extra import (
    _manual_add_leg, _manual_del_leg,
    _extra_add_leg, _extra_del_leg,
)
RightPanelMixin._manual_add_leg = _manual_add_leg  # type: ignore[attr-defined]
RightPanelMixin._manual_del_leg = _manual_del_leg  # type: ignore[attr-defined]
RightPanelMixin._extra_add_leg  = _extra_add_leg   # type: ignore[attr-defined]
RightPanelMixin._extra_del_leg  = _extra_del_leg   # type: ignore[attr-defined]

# combo_order_logic 핸들러 바인딩
from combo_order_logic import _on_synthetic_order as _orig_synthetic_order
from combo_order_logic import _on_check_margin

def _on_synthetic_order_guarded(self):
    """실계좌 guard 확인 후 원래 합성 주문 실행."""
    if not self._guard_live_order():
        self._log("⚠ 합성 주문 취소 (사용자 취소)")
        return
    _orig_synthetic_order(self)

RightPanelMixin._on_synthetic_order = _on_synthetic_order_guarded  # type: ignore[attr-defined]
RightPanelMixin._on_check_margin    = _on_check_margin     # type: ignore[attr-defined]

# ── whatIf 콜백 전체를 combo_order_whatif.py 에서 임포트 ────────
from combo_order_whatif import (
    _on_whatif_acct_value, _on_whatif_acct_end,
    _on_whatif_result, _finish_whatif, _send_whatif_order,
)
RightPanelMixin._on_whatif_acct_value = _on_whatif_acct_value  # type: ignore[attr-defined]
RightPanelMixin._on_whatif_acct_end   = _on_whatif_acct_end    # type: ignore[attr-defined]
RightPanelMixin._on_whatif_result     = _on_whatif_result       # type: ignore[attr-defined]
RightPanelMixin._finish_whatif        = _finish_whatif          # type: ignore[attr-defined]
RightPanelMixin._send_whatif_order    = _send_whatif_order      # type: ignore[attr-defined]

# v2.6 추가 바인딩
from combo_ui_right_panels_ext import _calc_pnl
RightPanelMixin._calc_pnl = _calc_pnl  # type: ignore[attr-defined]

from combo_order_chaser import cancel_bag_order
RightPanelMixin._on_cancel_bag_order = cancel_bag_order  # type: ignore[attr-defined]

# ── 만기 포맷 유틸 ────────────────────────────────────────────



# ── combo_ui_right.py 에서 이전된 유틸 함수들 ────────────────

def _request_margin_then_order(self, legs, strat, cost_str, confirm=False):
    """
    IB reqAccountSummary() 로 실제 BuyingPower / InitMarginReq 조회.
    조회 완료 후 panel.update_margin() 호출.
    confirm=True 면 주문 확인 다이얼로그 표시 후 placeOrder.
    """
    from PyQt5.QtCore import QTimer as _QTimer
    ib    = self.mw.ib
    panel = getattr(self, 'synthetic_panel', None)

    _buf = {}
    REQ_ID = 9901   # 복합전략 전용 reqId

    def _on_acct_value(reqId, account, tag, value, currency):
        try:
            v = float(value)
        except (ValueError, TypeError):
            return
        # 수신된 모든 태그 raw 저장 (디버그용)
        _buf.setdefault("_raw", {})[tag] = v
        # 가용 증거금: 우선순위 AvailableFunds > BuyingPower > NetLiquidation
        if tag == "AvailableFunds":
            _buf["available_af"] = v
        elif tag == "BuyingPower":
            _buf["available_bp"] = v
        elif tag == "NetLiquidation":
            _buf["available_nl"] = v
        elif tag == "InitMarginReq":
            _buf["init_margin"] = v
        elif tag == "MaintMarginReq":
            _buf["maint_margin"] = v

    def _on_acct_end(reqId):
        # 콜백 원복
        try:
            ib.accountSummary    = ib._orig_acct_summary
            ib.accountSummaryEnd = ib._orig_acct_summary_end
            del ib._orig_acct_summary
            del ib._orig_acct_summary_end
        except Exception:
            pass
        try:
            ib.cancelAccountSummary(REQ_ID)
        except Exception:
            pass

        # 가용 증거금: AvailableFunds 우선, 없으면 BuyingPower, 없으면 NetLiquidation
        available = (
            _buf.get("available_af") or
            _buf.get("available_bp") or
            _buf.get("available_nl") or
            0.0
        )

        # 수신된 태그 전체 로그 (디버그)
        raw_log = "  ".join(f"{k}={v:,.2f}" for k, v in _buf.get("_raw", {}).items())
        self._log(f"💰 수신 태그: {raw_log}" if raw_log else "💰 수신된 계좌 태그 없음")

        # ── 필요 증거금: 전략 구조 기반 계산 ────────────────────
        # IB의 InitMarginReq는 보유 포지션 기준이라 주문 전엔 0.
        # 전략별 실질 위험 기준으로 직접 산출.
        required = 0.0
        if legs:
            required = _calc_required_margin(legs)

        if panel:
            panel.update_margin(
                available=available,
                required=required,
                strategy=strat,
                cost=cost_str,
            )

        self._log(f"💰 증거금 조회 완료: 가용={available:,.2f}  필요={required:,.2f}")

        if confirm and legs:
            # 주문가능 여부에 따라 확인창 표시
            if available < required:
                QMessageBox.warning(
                    self, "증거금 부족",
                    f"가용 증거금: ${available:,.2f}\n"
                    f"필요 증거금: ${required:,.2f}\n\n"
                    f"증거금이 부족합니다. 주문을 취소합니다.")
                return

            leg_summary = "\n".join(
                f"  레그{i+1}: {lg['dir']} {lg['qty']}계약  "
                f"{lg['cp']} {lg['strike']}  ${lg['prem']}  만기:{lg['expiry']}"
                for i, lg in enumerate(legs)
            )
            reply = QMessageBox.question(
                self, "⚡ 합성 주문 확인",
                f"전략: {strat}\n"
                f"순비용: {cost_str}\n\n"
                f"{leg_summary}\n\n"
                f"가용 증거금: ${available:,.2f}\n"
                f"총 {len(legs)}개 레그를 주문하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                _place_combo_legs(self, legs, strat)

    # 콜백 주입
    ib._orig_acct_summary     = getattr(ib, 'accountSummary',    lambda *a: None)
    ib._orig_acct_summary_end = getattr(ib, 'accountSummaryEnd', lambda *a: None)
    ib.accountSummary    = _on_acct_value
    ib.accountSummaryEnd = _on_acct_end

    try:
        ib.reqAccountSummary(REQ_ID, "All", "BuyingPower,AvailableFunds,InitMarginReq")
        self._log("💰 IB reqAccountSummary 요청...")
    except Exception as e:
        self._log(f"❌ reqAccountSummary 오류: {e}")
        # 원복
        ib.accountSummary    = ib._orig_acct_summary
        ib.accountSummaryEnd = ib._orig_acct_summary_end

    # 5초 후 타임아웃 안전망 (콜백 미수신 대비)
    from PyQt5.QtCore import QTimer as _QT2
    def _timeout():
        if not _buf:
            self._log("⚠ 증거금 조회 타임아웃 — TWS 연결 상태를 확인하세요.")
            try:
                ib.accountSummary    = ib._orig_acct_summary
                ib.accountSummaryEnd = ib._orig_acct_summary_end
                del ib._orig_acct_summary
                del ib._orig_acct_summary_end
                ib.cancelAccountSummary(REQ_ID)
            except Exception:
                pass
    _QT2.singleShot(5000, _timeout)

def _parse_legs_from_table(self) -> list:
    """
    tbl_legs 에서 레그 정보 파싱.
    반환: [{"dir","cp","strike","prem","qty","expiry"}, ...]
    빈 행 또는 행사가 미입력 행은 제외.
    """
    legs = []
    for r in range(self.tbl_legs.rowCount()):
        def cell(c):
            it = self.tbl_legs.item(r, c)
            return it.text().strip() if it else ""

        direction = cell(1)
        cp        = cell(2)
        strike    = cell(3)
        prem      = cell(4)
        qty       = cell(5)
        expiry    = cell(6)

        if not strike or strike in ("―", ""):
            continue   # 행사가 미입력 → 건너뜀

        # 만기: MM/DD → 오늘 연도 기반 YYYYMMDD 복원
        raw_expiry = _parse_expiry_display(expiry)
        if not raw_expiry:
            self._log(f"⚠ 레그{r+1} 만기 파싱 실패: '{expiry}'")
            continue

        try:
            qty_int = int(qty) if qty else 1
        except ValueError:
            qty_int = 1

        try:
            strike_f = float(strike)
        except ValueError:
            self._log(f"⚠ 레그{r+1} 행사가 파싱 실패: '{strike}'")
            continue

        legs.append({
            "dir":    direction.upper() if direction else "BUY",
            "cp":     cp.upper() if cp else "C",
            "strike": strike_f,
            "prem":   prem or "0",
            "qty":    qty_int,
            "expiry": raw_expiry,
        })
    return legs

def _calc_required_margin(legs: list) -> float:
    """
    전략 구조 기반 증거금 추정.
    IB InitMarginReq는 주문 전에는 0이므로 직접 계산.

    규칙:
      1. 매도 레그와 매수 레그를 C/P별로 분리
      2. 매수가 매도를 완전 커버하는 스프레드 → 행사가 차이 × 커버수 × 100
      3. 매수가 매도보다 많은 백 스프레드 → 초과 매수분 프리미엄 + 스프레드 증거금
      4. 커버 없는 네이키드 매도 → 행사가 × 0.20 × 100 (표준 20% 룰)
    """
    import math

    # C/P별로 분리
    calls_sell = sorted([l for l in legs if l["cp"].upper()=="C" and l["dir"]=="SELL"],
                        key=lambda x: x["strike"])
    calls_buy  = sorted([l for l in legs if l["cp"].upper()=="C" and l["dir"]=="BUY"],
                        key=lambda x: x["strike"])
    puts_sell  = sorted([l for l in legs if l["cp"].upper()=="P" and l["dir"]=="SELL"],
                        key=lambda x: x["strike"], reverse=True)
    puts_buy   = sorted([l for l in legs if l["cp"].upper()=="P" and l["dir"]=="BUY"],
                        key=lambda x: x["strike"], reverse=True)

    total_margin = 0.0

    for sell_legs, buy_legs, is_call in [
        (calls_sell, calls_buy, True),
        (puts_sell,  puts_buy,  False),
    ]:
        sell_qty = sum(int(l.get("qty", 1)) for l in sell_legs)
        buy_qty  = sum(int(l.get("qty", 1)) for l in buy_legs)

        if sell_qty == 0:
            continue  # 매도 없음 → 증거금 없음

        if buy_qty >= sell_qty:
            # 매수가 매도를 완전 커버 (스프레드 or 백 스프레드)
            # 증거금 = 행사가 차이 × 커버된 매도수 × 100
            if sell_legs and buy_legs:
                s_strike = sell_legs[0]["strike"]
                b_strike = buy_legs[0]["strike"]
                spread   = abs(s_strike - b_strike)
                covered  = min(sell_qty, buy_qty)
                total_margin += spread * covered * 100
                # 초과 매수분(백 스프레드) → 프리미엄 비용 추가
                excess = buy_qty - sell_qty
                if excess > 0:
                    avg_prem = sum(
                        float(l.get("prem", 0) or 0) * int(l.get("qty", 1))
                        for l in buy_legs
                    ) / buy_qty
                    total_margin += avg_prem * excess * 100
        else:
            # 매수가 매도보다 적음 (레이쇼 스프레드 매도쪽 초과)
            # 커버된 부분: 스프레드 증거금
            if buy_legs:
                s_strike = sell_legs[0]["strike"]
                b_strike = buy_legs[0]["strike"]
                spread   = abs(s_strike - b_strike)
                total_margin += spread * buy_qty * 100
            # 커버 안 된 네이키드 매도: 행사가 × 20% × 100
            naked_qty = sell_qty - buy_qty
            naked_strike = sell_legs[0]["strike"]
            total_margin += naked_strike * 0.20 * naked_qty * 100

    return total_margin

def _parse_expiry_display(display: str) -> str:
    """
    다양한 만기 입력 형식 → YYYYMMDD 복원.
    지원 형식:
      MM/DD   → 04/13  (앞 0 있음)
      M/DD    → 4/13   (앞 0 없음)
      MM/D    → 04/3
      YYYYMMDD → 20260413 (이미 완성)
      YYYY-MM-DD → 2026-04-13
    """
    from datetime import date
    if not display or display in ("―", ""):
        return ""
    # 이미 완성된 YYYYMMDD (숫자 8자리)
    digits = "".join(c for c in display if c.isdigit())
    if len(digits) == 8:
        return digits
    # 구분자(/ - .) 기준으로 분리 시도
    import re
    parts = re.split(r"[/\-\.]", display.strip())
    today = date.today()
    try:
        if len(parts) == 3:          # YYYY/MM/DD 또는 MM/DD/YYYY
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if y > 1000:             # YYYY/MM/DD
                return date(y, m, d).strftime("%Y%m%d")
            else:                    # MM/DD/YYYY
                return date(d, y, m).strftime("%Y%m%d")
        if len(parts) == 2:          # MM/DD 또는 M/DD 또는 MM/D
            mm, dd = int(parts[0]), int(parts[1])
            candidate = date(today.year, mm, dd)
            if candidate < today:
                candidate = date(today.year + 1, mm, dd)
            return candidate.strftime("%Y%m%d")
    except (ValueError, TypeError):
        pass
    return ""

def _place_combo_legs(self, legs: list, strat: str):
    """
    BAG(Combo) 계약으로 묶어서 단일 주문 전송.
    - 모든 레그를 1개 BAG 계약으로 묶음 → 동시 체결 보장
    - lmtPrice = net 프리미엄 (데빗 양수 / 크레딧 음수)
    """
    try:
        from core_contract import make_opt_contract
        from ibapi.order import Order as IbOrder
        from ibapi.contract import Contract, ComboLeg
    except ImportError as e:
        self._log(f"❌ import 오류: {e}")
        QMessageBox.critical(self, "오류", f"모듈 import 실패: {e}")
        return

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"

    # ── Step1: 각 레그의 conId 조회 필요 여부 확인 ───────────
    # BAG 주문은 ComboLeg에 conId가 필요.
    # conId를 모르면 reqContractDetails로 조회해야 하지만
    # make_opt_contract()로 만든 contract를 그대로 사용하면
    # TWS가 자동으로 resolve해줌 (conId=0 허용).
    # ── Step2: BAG 계약 구성 ─────────────────────────────────
    bag = Contract()
    bag.symbol   = symbol.replace("SPXW", "SPX")
    bag.secType  = "BAG"
    bag.currency = "USD"
    bag.exchange = "SMART"

    combo_legs = []
    for leg in legs:
        opt_contract = make_opt_contract(
            symbol=symbol,
            strike=leg["strike"],
            right=leg["cp"],
            expiry=leg["expiry"],
        )
        cl = ComboLeg()
        cl.conId     = 0          # TWS가 자동 resolve
        cl.ratio     = int(leg["qty"])
        cl.action    = leg["dir"]  # "BUY" | "SELL"
        cl.exchange  = "SMART"
        # conId 없이 strike/right/expiry로 식별하기 위해
        # contract 정보를 designatedLocation에 인코딩 (대안: reqContractDetails)
        # → 실용적 방법: conId 조회 후 전송 (아래 _place_bag_with_conids 사용)
        combo_legs.append((cl, opt_contract))

    # conId가 없으면 TWS가 거부할 수 있으므로
    # reqContractDetails로 조회 후 전송
    _place_bag_with_conids(self, bag, combo_legs, legs, strat)

def _place_bag_with_conids(self, bag, combo_legs, legs, strat):
    """
    각 레그의 conId를 reqContractDetails로 조회한 뒤 BAG 주문 전송.
    조회 완료 순서대로 conId를 채우고, 전체 완료 시 placeOrder.
    """
    from ibapi.contract import ComboLeg
    from ibapi.order import Order as IbOrder
    from PyQt5.QtCore import QTimer as _QT
    import re as _re

    ib    = self.mw.ib
    total = len(combo_legs)
    resolved = {}   # idx → conId

    # reqContractDetails reqId 범위: 9910~9929
    base_rid = 9910

    def _on_contract_details(reqId, contractDetails):
        idx = reqId - base_rid
        if 0 <= idx < total:
            resolved[idx] = contractDetails.contract.conId

    def _on_contract_details_end(reqId):
        idx = reqId - base_rid
        if idx not in resolved:
            resolved[idx] = 0   # 조회 실패 → 0으로 폴백
        if len(resolved) >= total:
            _QT.singleShot(0, _send_bag)

    # 콜백 주입 (bridge 경유 없이 직접 — contractDetails는 bridge에 없음)
    ib._orig_cd    = getattr(ib, 'contractDetails',    lambda *a: None)
    ib._orig_cd_end= getattr(ib, 'contractDetailsEnd', lambda *a: None)
    ib.contractDetails    = _on_contract_details
    ib.contractDetailsEnd = _on_contract_details_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        rid = base_rid + i
        try:
            ib.reqContractDetails(rid, opt_contract)
            self._log(f"🔍 conId 조회: 레그{i+1} "
                      f"{opt_contract.right} {int(opt_contract.strike)} {opt_contract.lastTradeDateOrContractMonth}")
        except Exception as e:
            self._log(f"❌ reqContractDetails 레그{i+1} 오류: {e}")
            resolved[i] = 0

    # 10초 타임아웃
    _QT.singleShot(10000, lambda: _on_timeout())

    def _on_timeout():
        for i in range(total):
            if i not in resolved:
                resolved[i] = 0
        if len(resolved) >= total:
            _send_bag()

    def _send_bag():
        # 콜백 원복
        try:
            ib.contractDetails    = ib._orig_cd
            ib.contractDetailsEnd = ib._orig_cd_end
        except Exception:
            pass

        # BAG ComboLeg conId 채우기
        cl_list = []
        for i, (cl, _) in enumerate(combo_legs):
            cl.conId = resolved.get(i, 0)
            cl_list.append(cl)
            self._log(f"  레그{i+1} conId={cl.conId}  "
                      f"{legs[i]['dir']} {legs[i]['qty']}  "
                      f"{legs[i]['cp']} {int(legs[i]['strike'])}")

        bag.comboLegs = cl_list

        # net 프리미엄 계산
        net = 0.0
        for leg in legs:
            try:
                pm  = float(leg.get("prem", 0) or 0)
                qty = int(leg.get("qty", 1))
                mul = 1 if leg["dir"] == "BUY" else -1
                net += mul * pm * qty
            except (ValueError, TypeError):
                pass
        # IB BAG: 데빗(지불)=양수, 크레딧(수취)=음수
        lmt_price = round(abs(net), 2) if net >= 0 else round(-abs(net), 2)

        oid = ib.get_next_id()
        if oid is None:
            self._log("❌ nextOrderId 없음")
            return

        ibord = IbOrder()
        ibord.action        = "BUY"   # BAG는 항상 BUY (방향은 ComboLeg.action으로)
        ibord.orderType     = "LMT"
        ibord.totalQuantity = 1       # BAG 단위
        ibord.lmtPrice      = lmt_price
        ibord.tif           = "DAY"
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True

        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(
                f"⚡ BAG 주문 전송: OID={oid}  net=${lmt_price:.2f}  "
                f"({'데빗' if net >= 0 else '크레딧'})  레그{total}개")

            # 합성 잔고 패널 갱신
            panel = getattr(self, 'synthetic_panel', None)
            if panel:
                panel.add_position({
                    "strategy": strat,
                    "qty":      1,
                    "entry":    abs(net),
                    "current":  abs(net),
                })
        except Exception as e:
            self._log(f"❌ BAG 주문 오류: {e}")


# 유틸 함수 바인딩
RightPanelMixin._request_margin_then_order = _request_margin_then_order  # type: ignore[attr-defined]
RightPanelMixin._parse_legs_from_table = _parse_legs_from_table  # type: ignore[attr-defined]
RightPanelMixin._calc_required_margin = _calc_required_margin  # type: ignore[attr-defined]
RightPanelMixin._parse_expiry_display = _parse_expiry_display  # type: ignore[attr-defined]
RightPanelMixin._place_combo_legs = _place_combo_legs  # type: ignore[attr-defined]
RightPanelMixin._place_bag_with_conids = _place_bag_with_conids  # type: ignore[attr-defined]