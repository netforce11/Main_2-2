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
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import SPLITTER_STYLE, get_splitter_style, STRATEGIES, STRATEGY_DESC, LEG_COLORS
from combo_ui_synthetic_panel import SyntheticStatusPanel
from combo_ui_leg_panel       import _build_leg_left          # noqa: F401

# [v1.2] 콜-풋 체인 자동 동기화 타이머 — left_panel 생성 후 1회 attach
try:
    from combo_ui_left_chain_sync import attach_chain_sync_timer as _attach_chain_sync
except ImportError:
    def _attach_chain_sync(panel): pass  # 모듈 없을 경우 무시
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

        # [v1.2] left_panel 체인 동기화 타이머 — UI 빌드 완료 후 attach
        from PyQt5.QtCore import QTimer as _QT_chain
        _QT_chain.singleShot(0, self._attach_left_chain_sync)

        self._mid_hsplit = QSplitter(Qt.Horizontal)
        self._mid_hsplit.setHandleWidth(6)
        self._mid_hsplit.setStyleSheet(get_splitter_style())
        self._mid_hsplit.setChildrenCollapsible(False)
        self._mid_hsplit.addWidget(self._build_result_panel())
        self._mid_hsplit.addWidget(self._build_spread_chart_panel())
        self._mid_hsplit.setSizes([500, 500])
        cv.addWidget(self._mid_hsplit, 1)

        return container

    # ── 전략 설정 패널 ────────────────────────────────────────
    def _build_strategy_input_panel(self) -> QGroupBox:
        gb = QGroupBox("📋 전략 설정")
        outer = QVBoxLayout(gb)
        outer.setSpacing(4); outer.setContentsMargins(6, 6, 6, 6)

        hsplit = QSplitter(Qt.Horizontal)
        hsplit.setHandleWidth(5); hsplit.setStyleSheet(get_splitter_style())
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
        from combo_constants import _pal as _cp2
        _t2 = _cp2()
        self.edit_stock_price.setStyleSheet(
            f"background:{_t2['input_bg']};color:{_t2['group_title']};"
            f"border:1px solid {_t2['input_border']};"
            "border-radius:4px;font-size:12px;")
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

        from combo_ui_panel_constants import _pal as _rp_pal
        _t = _rp_pal()
        _is_dark = _t.get("win_bg", "#fff")[1:3].lower() < "88"

        # [THEME] 역할별 색상 — 테마에 따라 밝기 자동 조정
        _ROLE_COLORS = {
            "gain":    ("#00bb66", "#166534"),   # (다크, 라이트)
            "gold":    ("#d4a017", "#92610a"),
            "danger":  ("#5a1a1a", "#fca5a5"),
            "info":    ("#1a2a4a", "#1e40af"),
            "warn":    ("#2a1a0a", "#d97706"),
            "cancel":  ("#2a0a0a", "#dc2626"),
        }
        def _role_bg(role):
            idx = 0 if _is_dark else 1
            return _ROLE_COLORS.get(role, ("#222", "#eee"))[idx]

        def _mk_btn(text, bg, fg, fn, obj_name=None, role=None):
            b = QPushButton(text)
            b.setFixedHeight(28)
            # role 지정 시 테마 기반 색상, 아니면 전달된 값 그대로
            _bg = _role_bg(role) if role else bg
            _fg = fg  # fg(텍스트)는 의미색이라 유지
            nm = obj_name or ""
            if nm:
                b.setObjectName(nm)
                b.setStyleSheet(
                    f"QPushButton#{nm}{{background:{_bg};color:{_fg};"
                    f"border:1px solid {_fg};border-radius:4px;font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;}}"
                    f"QPushButton#{nm}:hover{{background:{_fg};color:{_t.get('win_bg','#000')};}}"
                    f"QPushButton#{nm}:disabled{{background:{_t.get('group_bg','#222')};"
                    f"color:{_t.get('tbl_grid','#555')};border-color:{_t.get('group_border','#333')};}}")
            else:
                b.setStyleSheet(
                    f"background:{_bg};color:{_fg};font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;border-radius:4px;"
                    f"border:1px solid {_fg};")
            b.clicked.connect(fn)
            return b

        grp_a.addWidget(_mk_btn("📊 손익 계산",  "#1a5c2e", "#00ff88", self._calc_pnl, role="gain"))
        grp_a.addWidget(_mk_btn("💰 증거금 조회", "#1a1a0e", "#ffd700", self._on_check_margin, "btn_check_margin", role="gold"))
        self.btn_check_margin = grp_a.itemAt(1).widget()
        grp_a.addWidget(_mk_btn("🗑 초기화",      "#5a1a1a", "#ff6666", self._reset_legs, role="danger"))
        grp_a.addWidget(_mk_btn("🔍 Optimiser ▼", "#1a2a4a", "#90caf9", self._toggle_optimizer_panel, role="info"))
        self._btn_opt_toggle = grp_a.itemAt(3).widget()

        # 구분선
        sep = QLabel("│")
        sep.setStyleSheet(f"color:{_t.get('group_border','#333')};font-size:16px;border:none;")
        sep.setFixedWidth(12)
        sep.setAlignment(Qt.AlignCenter)
        grp_a.addWidget(sep)

        # ════════════════════════════════════════════════════
        # 버튼 그룹 B: 합성주문 / 미체결 / 정정 / 취소
        # ════════════════════════════════════════════════════
        self.btn_synthetic_order = _mk_btn(
            "⚡ 합성 주문", "#0e2e1a", "#00ff88",
            self._on_synthetic_order, "btn_synthetic_order", role="gain")
        grp_a.addWidget(self.btn_synthetic_order)

        self.btn_open_orders = _mk_btn(
            "📋 미체결", "#1a1a3a", "#aabbff",
            self._on_open_orders, "btn_open_orders", role="info")
        grp_a.addWidget(self.btn_open_orders)

        self.btn_modify_order = _mk_btn(
            "✏ 정정", "#2a1a0a", "#ffaa44",
            self._on_modify_order, "btn_modify_order", role="warn")
        grp_a.addWidget(self.btn_modify_order)

        self.btn_cancel_order = _mk_btn(
            "✖ 취소", "#2a0a0a", "#ff4444",
            self._on_cancel_order, "btn_cancel_order", role="cancel")
        grp_a.addWidget(self.btn_cancel_order)

        v.addLayout(grp_a)

        # ── 버튼 행 2: Smart Chaser ─────────────────────────────
        v.addWidget(self._build_chaser_row())

        self.synthetic_panel = SyntheticStatusPanel(self)
        v.addWidget(self.synthetic_panel, 0)

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
        from combo_constants import _pal as _cpal
        t = _cpal()
        bar = QFrame()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"QFrame{{background:{t['group_bg']};border-bottom:1px solid {t['group_border']};}}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 2, 8, 2); h.setSpacing(8)

        # 연결 상태 점
        self._acct_dot = QLabel("●")
        self._acct_dot.setStyleSheet(
            f"color:{t['group_title']};font-size:13px;border:none;")
        h.addWidget(self._acct_dot)

        # 계좌 번호 / 모드
        self._acct_lbl = QLabel("미연결")
        self._acct_lbl.setStyleSheet(
            f"color:{t['group_title']};font-size:12px;font-weight:bold;border:none;")
        h.addWidget(self._acct_lbl)

        # 모드 뱃지
        self._acct_mode_lbl = QLabel("")
        self._acct_mode_lbl.setStyleSheet(
            f"color:{t['group_title']};font-size:11px;border:none;")
        h.addWidget(self._acct_mode_lbl)

        h.addStretch()

        # 실계좌 경고 아이콘 (평소 숨김)
        self._acct_warn_lbl = QLabel("⚠ 실계좌 — 주문 전 반드시 확인")
        # 경고색은 의미색이라 테마 무관하게 주황 유지 (단, 배경은 테마 적용)
        self._acct_warn_lbl.setStyleSheet(
            f"color:#ff9800;font-size:11px;font-weight:bold;border:none;"
            f"background:transparent;")
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

    def _attach_left_chain_sync(self) -> None:
        """[v1.2] left_panel 의 _auto_sync_chain 을 3초 타이머에 연결.
        _build_right_panel() 의 singleShot(0) 콜백으로 호출 — UI 완전 빌드 후 실행.
        left_panel 후보: self._left_panel / self.left_panel / mw.tab_combo._left_panel
        """
        candidates = [
            getattr(self, '_left_panel', None),
            getattr(self, 'left_panel', None),
            getattr(getattr(self, 'mw', None), 'tab_combo', None),
            self,  # LeftPanelMixin 을 self 가 직접 상속하는 경우
        ]
        for panel in candidates:
            if panel is not None and hasattr(panel, '_auto_sync_chain'):
                timer = _attach_chain_sync(panel)
                if timer is not None:
                    self._log("[ChainSync] ✅ 체인 자동 동기화 타이머 연결 완료 (3초 주기)")
                return
        self._log("[ChainSync] ⚠ left_panel._auto_sync_chain 을 찾지 못함 — 수동 동기화만 사용")

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

# combo_order_open 핸들러는 클래스 메서드(_on_open_orders / _on_modify_order / _on_cancel_order)
# 로 구현되어 있으므로 여기서 별도 바인딩하지 않음.

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

        # ── 필요 증거금: 전략 구조 기반 계산 + 장외 할증 ──────────
        # IB의 InitMarginReq는 보유 포지션 기준이라 주문 전엔 0.
        # 전략별 실질 위험 기준으로 직접 산출.
        required = 0.0
        if legs:
            from combo_order_logic import _is_after_hours, _AFTER_HOURS_SURCHARGE
            required = _calc_required_margin(legs)
            if _is_after_hours():
                required = round(required * (1 + _AFTER_HOURS_SURCHARGE), 2)
                self._log("⚠ 장외 시간 — 증거금 25% 할증 적용")

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

# ── v2.8: 유틸 함수 중복 정의 제거 ──────────────────────────────
# _parse_legs_from_table / _parse_expiry_display / _calc_required_margin 은
# combo_order_utils.py 가 정본(데빗 스프레드 버그픽스 + [0DTE] 형식 지원 완료).
# 이 파일에 중복 정의하지 않음.
from combo_order_utils import (  # noqa: F401
    _parse_legs_from_table,
    _parse_expiry_display,
    _calc_required_margin,
)

# ── 구버전 _place_combo_legs / _place_bag_with_conids 제거 완료 ──
# v2.9 이후 combo_order_bag.py 에서 전담. 이 파일에 중복 정의하지 않음.

# 유틸 함수 바인딩
RightPanelMixin._request_margin_then_order = _request_margin_then_order  # type: ignore[attr-defined]
RightPanelMixin._parse_legs_from_table     = _parse_legs_from_table      # type: ignore[attr-defined]
RightPanelMixin._calc_required_margin      = _calc_required_margin       # type: ignore[attr-defined]
RightPanelMixin._parse_expiry_display      = _parse_expiry_display       # type: ignore[attr-defined]