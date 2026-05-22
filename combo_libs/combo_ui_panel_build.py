"""combo_ui_panel_build.py — SyntheticStatusPanel UI 빌드 메서드

SyntheticStatusPanel 클래스의 UI 구성 전용 믹스인.
직접 인스턴스화하지 않고 SyntheticStatusPanel 이 상속해 사용.

포함 메서드:
    _build_ui()
    _build_margin_tab()
    _build_position_tab()
    _build_close_control_row()
    _build_open_orders_tab()

[테마 연동 수정]
- 모든 하드코딩 색상(#07070f, #1a1a3a 등) 제거
- _pal() 헬퍼로 CURRENT_THEME 팔레트를 런타임 참조
- refresh_theme() 메서드 추가 → 테마 전환 시 호출하면 전체 재적용
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QTableWidget, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QPushButton, QDoubleSpinBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from combo_ui_panel_constants import _f, get_tab_style, get_tbl_style
from combo_ui_scenario_tab import ScenarioTab
    _HAS_SPIKE_TAB = False


# ── 팔레트 헬퍼 ───────────────────────────────────────────────
def _pal() -> dict:
    try:
        import core_theme as _core
        return _core.THEME_PALETTES.get(_core.CURRENT_THEME,
                                        _core.THEME_PALETTES["light"])
    except Exception:
        return {
            "win_bg": "#ffffff", "group_bg": "#e5e7eb",
            "widget_fg": "#111827", "group_border": "#a1a1aa",
            "group_title": "#1e40af", "btn_bg": "#f3f4f6",
            "btn_fg": "#111827", "btn_border": "#cbd5e1",
            "btn_hover": "#e2e8f0", "btn_hover_bdr": "#94a3b8",
            "input_bg": "#ffffff", "input_fg": "#111827",
            "input_border": "#cbd5e1", "splitter": "#cbd5e1",
            "tab_sel_fg": "#1d4ed8",
        }


class _SyntheticPanelBuildMixin:
    """UI 빌드 전용 믹스인. SyntheticStatusPanel 이 단독으로 상속."""

    # ══════════════════════════════════════════════════════════
    # 최상위 UI 조립
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        t = _pal()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── 증거금 모드 + 예약 주문 버튼 행 ──────────────────
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(6, 4, 6, 2); mode_row.setSpacing(8)

        lbl = QLabel("💰 증거금:")
        lbl.setStyleSheet(f"color:{t['group_title']};font-size:11px;border:none;")
        mode_row.addWidget(lbl)

        self._rb_margin_local  = QRadioButton("🖥 로컬")
        self._rb_margin_server = QRadioButton("☁ 서버")
        self._rb_margin_local.setChecked(True)
        _rb_ss = (f"color:{t['widget_fg']};font-size:11px;border:none;"
                  "QRadioButton::indicator{width:12px;height:12px;}")
        for rb in (self._rb_margin_local, self._rb_margin_server):
            rb.setStyleSheet(_rb_ss)
        self._margin_grp = QButtonGroup(self)
        self._margin_grp.addButton(self._rb_margin_local,  0)
        self._margin_grp.addButton(self._rb_margin_server, 1)
        mode_row.addWidget(self._rb_margin_local)
        mode_row.addWidget(self._rb_margin_server)

        self._lbl_margin_mode_desc = QLabel("즉시 계산")
        self._lbl_margin_mode_desc.setStyleSheet(
            f"color:{t['group_title']};font-size:10px;border:none;")
        mode_row.addWidget(self._lbl_margin_mode_desc)

        # [SLEEP] 예약 주문 버튼
        try:
            import sys, os as _os
            _this_dir = _os.path.dirname(_os.path.abspath(__file__))
            if _this_dir not in sys.path:
                sys.path.insert(0, _this_dir)
            from Sleep_Order.sleep_order_ui import SleepOrderButton
            self._sleep_btn = SleepOrderButton(ref=None, parent=self)
            mode_row.addWidget(self._sleep_btn)
        except Exception as _e:
            print(f"[SyntheticPanel] sleep_order 버튼 오류: {_e}")
            import traceback; traceback.print_exc()

        mode_row.addStretch()

        self._rb_margin_local.toggled.connect(self._on_margin_mode_toggle)
        self._rb_margin_server.toggled.connect(self._on_margin_mode_toggle)

        self._mode_widget = QWidget()
        self._mode_widget.setStyleSheet(f"background:{t['group_bg']};")
        self._mode_widget.setLayout(mode_row)
        root.addWidget(self._mode_widget)

        self._sep_top = QFrame(); self._sep_top.setFrameShape(QFrame.HLine)
        self._sep_top.setFixedHeight(1)
        self._sep_top.setStyleSheet(
            f"background-color:{t['group_border']};border:none;")
        root.addWidget(self._sep_top)

        # ── 탭 위젯 ──────────────────────────────────────────
        self._tabs = QTabWidget()
        # 탭 5개 — 스크롤 버튼 + 폰트 축소로 한 줄에 표시
        self._tabs.setUsesScrollButtons(True)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.tabBar().setFont(_f(10, bold=False))
        self._tabs.setStyleSheet(get_tab_style() +
            "QTabBar::tab{padding:4px 6px;font-size:10px;}"
            "QTabBar::tab:selected{font-weight:bold;}"
            "QTabBar::scroller{width:16px;}"
            "QTabBar QToolButton{background:#1c1c3a;color:#aaa;"
            "border:1px solid #3a3a7a;min-width:14px;}")
        self._tabs.addTab(self._build_margin_tab(),      "증거금")
        self._tabs.addTab(self._build_position_tab(),    "잔고")
        self._tabs.addTab(self._build_open_orders_tab(), "미체결")

        self._scenario_tab = ScenarioTab()
        self._tabs.addTab(self._scenario_tab, "시나리오")

        root.addWidget(self._tabs)

    # ══════════════════════════════════════════════════════════
    # 테마 갱신 (테마 전환 버튼 클릭 시 외부에서 호출)
    # ══════════════════════════════════════════════════════════

    def refresh_theme(self):
        """현재 CURRENT_THEME 으로 전체 위젯 색상 재적용."""
        t = _pal()
        tbl_ss = get_tbl_style()
        tab_ss = get_tab_style()

        # 모드 행 배경 / 구분선
        if hasattr(self, '_mode_widget'):
            self._mode_widget.setStyleSheet(f"background:{t['group_bg']};")
        if hasattr(self, '_sep_top'):
            self._sep_top.setStyleSheet(
                f"background-color:{t['group_border']};border:none;")

        # 탭 위젯
        if hasattr(self, '_tabs'):
            self._tabs.setStyleSheet(tab_ss)

        # 라디오 버튼
        _rb_ss = (f"color:{t['widget_fg']};font-size:11px;border:none;"
                  "QRadioButton::indicator{width:12px;height:12px;}")
        for rb_name in ('_rb_margin_local', '_rb_margin_server',
                        '_rb_chaser_auto', '_rb_chaser_manual'):
            rb = getattr(self, rb_name, None)
            if rb:
                rb.setStyleSheet(_rb_ss)

        # 테이블
        for tbl_name in ('_tbl_pos', '_tbl_open_orders'):
            tbl = getattr(self, tbl_name, None)
            if tbl:
                tbl.setStyleSheet(tbl_ss)

        # 구분선
        for sep_name in ('_sep_top', '_sep1', '_sep2'):
            sep = getattr(self, sep_name, None)
            if sep:
                sep.setStyleSheet(
                    f"background-color:{t['group_border']};border:none;")

        # 탭 패널 배경
        for w_name in ('_margin_tab_w', '_position_tab_w',
                       '_open_orders_tab_w', '_close_ctrl_w'):
            w = getattr(self, w_name, None)
            if w:
                w.setStyleSheet(f"background:{t['group_bg']};")

        # 증거금 상태 레이블
        if hasattr(self, '_lbl_margin_status'):
            self._lbl_margin_status.setStyleSheet(
                f"color:{t['group_title']};padding:7px;"
                f"border:1px solid {t['group_border']};"
                f"border-radius:6px;background:{t['win_bg']};")

        # 스핀박스
        _spin_ss = (f"background:{t['input_bg']};color:{t['group_title']};"
                    f"border:1px solid {t['input_border']};"
                    "border-radius:4px;font-size:12px;font-weight:bold;")
        for sp_name in ('_spin_close_price', '_spin_manual_price'):
            sp = getattr(self, sp_name, None)
            if sp:
                sp.setStyleSheet(_spin_ss)

        # 액션 버튼
        self._apply_action_btn_styles(t)

    def _apply_action_btn_styles(self, t: dict):
        """액션 버튼(청산/정정/취소)에 의미색 + 테마 배경 조합 적용."""
        def _btn_style(fg, border):
            return (f"background:{t['group_bg']};color:{fg};font-size:12px;"
                    f"font-weight:bold;border:1px solid {border};"
                    "border-radius:6px;padding:2px 10px;")

        def _btn_style_sm(fg, border):
            return (f"background:{t['group_bg']};color:{fg};font-size:11px;"
                    f"font-weight:bold;border:1px solid {border};"
                    "border-radius:6px;padding:2px 8px;")

        if hasattr(self, '_btn_close_lmt'):
            self._btn_close_lmt.setStyleSheet(_btn_style("#44cc44", "#3a7a2a"))
        if hasattr(self, '_btn_close_mkt'):
            self._btn_close_mkt.setStyleSheet(_btn_style("#ff5555", "#8a1a1a"))
        if hasattr(self, '_btn_cancel_pos'):
            self._btn_cancel_pos.setStyleSheet(_btn_style("#ffaa33", "#8a5a0a"))
        if hasattr(self, '_btn_refresh_orders'):
            self._btn_refresh_orders.setStyleSheet(
                _btn_style_sm(t['group_title'], t['input_border']))
        if hasattr(self, '_btn_modify_p1'):
            self._btn_modify_p1.setStyleSheet(_btn_style_sm("#44cc44", "#3a7a2a"))
        if hasattr(self, '_btn_modify_m1'):
            self._btn_modify_m1.setStyleSheet(_btn_style_sm("#ffaa33", "#8a5a0a"))
        if hasattr(self, '_btn_cancel_all'):
            self._btn_cancel_all.setStyleSheet(_btn_style_sm("#ff4444", "#8a1a1a"))
        if hasattr(self, '_btn_manual_send'):
            self._btn_manual_send.setStyleSheet(
                f"background:{t['group_bg']};color:#44cc44;font-size:11px;"
                "font-weight:bold;border:1px solid #3a7a2a;border-radius:6px;")

    # ══════════════════════════════════════════════════════════
    # 증거금 탭
    # ══════════════════════════════════════════════════════════

    def _build_margin_tab(self) -> QWidget:
        t = _pal()
        w = QWidget(); w.setStyleSheet(f"background:{t['group_bg']};")
        self._margin_tab_w = w
        lay = QVBoxLayout(w); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(5)

        def kv(label):
            row = QHBoxLayout()
            lk = QLabel(label)
            lk.setStyleSheet(f"color:{t['group_title']};border:none;")
            lk.setFont(_f(12))
            lv = QLabel("―")
            lv.setStyleSheet(f"color:{t['widget_fg']};border:none;")
            lv.setFont(_f(13, True))
            row.addWidget(lk); row.addStretch(); row.addWidget(lv)
            return row, lv

        row_s, self._lbl_m_strategy  = kv("전략명")
        row_c, self._lbl_m_cost      = kv("순 비용")
        row_a, self._lbl_m_available = kv("주문가능")
        row_r, self._lbl_m_required  = kv("필요증거금")

        for row in (row_s, row_c):
            lay.addLayout(row)

        self._sep1 = QFrame(); self._sep1.setFrameShape(QFrame.HLine)
        self._sep1.setFixedHeight(1)
        self._sep1.setStyleSheet(
            f"background-color:{t['group_border']};border:none;")
        lay.addWidget(self._sep1)

        for row in (row_a, row_r):
            lay.addLayout(row)

        self._sep2 = QFrame(); self._sep2.setFrameShape(QFrame.HLine)
        self._sep2.setFixedHeight(1)
        self._sep2.setStyleSheet(
            f"background-color:{t['group_border']};border:none;")
        lay.addWidget(self._sep2)

        self._lbl_margin_status = QLabel("―")
        self._lbl_margin_status.setAlignment(Qt.AlignCenter)
        self._lbl_margin_status.setFont(_f(13, bold=True))
        self._lbl_margin_status.setStyleSheet(
            f"color:{t['group_title']};padding:7px;"
            f"border:1px solid {t['group_border']};"
            f"border-radius:6px;background:{t['win_bg']};")
        lay.addWidget(self._lbl_margin_status)
        lay.addStretch()
        return w

    # ══════════════════════════════════════════════════════════
    # 합성 잔고 탭
    # ══════════════════════════════════════════════════════════

    def _build_position_tab(self) -> QWidget:
        t = _pal()
        w = QWidget(); w.setStyleSheet(f"background:{t['group_bg']};")
        self._position_tab_w = w
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        summary = QHBoxLayout()
        lk = QLabel("총 손익")
        lk.setStyleSheet(f"color:{t['group_title']};border:none;")
        lk.setFont(_f(12))
        self._lbl_total_pnl = QLabel("$0.00")
        self._lbl_total_pnl.setStyleSheet(f"color:{t['widget_fg']};border:none;")
        self._lbl_total_pnl.setFont(_f(14, bold=True))
        summary.addWidget(lk); summary.addStretch()
        summary.addWidget(self._lbl_total_pnl)
        lay.addLayout(summary)

        self._lbl_no_pos = QLabel("합성 주문 내역이 없습니다.")
        self._lbl_no_pos.setAlignment(Qt.AlignCenter)
        self._lbl_no_pos.setFont(_f(12))
        self._lbl_no_pos.setStyleSheet(
            f"color:{t['group_title']};padding:14px;")
        lay.addWidget(self._lbl_no_pos)

        self._tbl_pos = QTableWidget(0, 10)
        self._tbl_pos.setHorizontalHeaderLabels(
            ["만기", "전략명", "수량", "진입가", "현재가", "손익", "수익률", "5P손익(%)", "상태", "청산예약"])
        self._tbl_pos.setFont(_f(12))
        self._tbl_pos.horizontalHeader().setFont(_f(11, bold=True))
        self._tbl_pos.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self._tbl_pos.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        for c in range(2, 10):
            self._tbl_pos.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._tbl_pos.verticalHeader().setVisible(False)
        self._tbl_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_pos.setAlternatingRowColors(True)
        self._tbl_pos.setStyleSheet(get_tbl_style())
        self._tbl_pos.setVisible(False)
        self._tbl_pos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_pos.cellClicked.connect(self._on_pos_row_clicked)
        lay.addWidget(self._tbl_pos, 1)

        lay.addWidget(self._build_close_control_row())

        # [FIX-BANNER] Wolf + 수익률 배너 서브 레이아웃
        self._banner_layout = QVBoxLayout()
        self._banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_layout.setSpacing(2)
        lay.addLayout(self._banner_layout)

        return w

    def _build_close_control_row(self) -> QWidget:
        """[FIX-J] 지정가/MKT 청산 컨트롤 행."""
        t = _pal()
        w = QWidget(); w.setStyleSheet(f"background:{t['group_bg']};")
        self._close_ctrl_w = w
        row = QHBoxLayout(w)
        row.setContentsMargins(2, 2, 2, 2); row.setSpacing(6)

        self._lbl_pos_hint = QLabel("행을 클릭하세요")
        self._lbl_pos_hint.setStyleSheet(
            f"color:{t['group_title']};font-size:11px;border:none;")
        row.addWidget(self._lbl_pos_hint)
        row.addStretch()

        lbl_price = QLabel("가격:")
        lbl_price.setStyleSheet(
            f"color:{t['group_title']};font-size:11px;border:none;")
        row.addWidget(lbl_price)

        _spin_ss = (f"background:{t['input_bg']};color:{t['group_title']};"
                    f"border:1px solid {t['input_border']};"
                    "border-radius:4px;font-size:12px;font-weight:bold;")

        self._spin_close_price = QDoubleSpinBox()
        self._spin_close_price.setRange(0.01, 999.99)
        self._spin_close_price.setSingleStep(0.05)
        self._spin_close_price.setDecimals(2)
        self._spin_close_price.setPrefix("$")
        self._spin_close_price.setFixedWidth(80)
        self._spin_close_price.setFixedHeight(26)
        self._spin_close_price.setEnabled(False)
        self._spin_close_price.setStyleSheet(_spin_ss)
        row.addWidget(self._spin_close_price)

        def _abtn(text, fg, border, cb):
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.setEnabled(False)
            b.setStyleSheet(
                f"background:{t['group_bg']};color:{fg};font-size:12px;"
                f"font-weight:bold;border:1px solid {border};"
                "border-radius:6px;padding:2px 10px;")
            b.clicked.connect(cb)
            return b

        self._btn_close_lmt  = _abtn("📌 지정가 청산", "#44cc44", "#3a7a2a",
                                     self._on_close_lmt)
        self._btn_close_mkt  = _abtn("🔴 MKT 청산",   "#ff5555", "#8a1a1a",
                                     self._on_close_mkt)
        self._btn_cancel_pos = _abtn("✖ 주문 취소",   "#ffaa33", "#8a5a0a",
                                     self._on_cancel_pos_order)

        row.addWidget(self._btn_close_lmt)
        row.addWidget(self._btn_close_mkt)
        row.addWidget(self._btn_cancel_pos)
        return w

    # ══════════════════════════════════════════════════════════
    # 미체결 탭
    # ══════════════════════════════════════════════════════════

    def _build_open_orders_tab(self) -> QWidget:
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        t = _pal()
        w = QWidget(); w.setStyleSheet(f"background:{t['group_bg']};")
        self._open_orders_tab_w = w
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        chaser_row = QHBoxLayout(); chaser_row.setSpacing(6)
        mode_lbl = QLabel("정정 모드:")
        mode_lbl.setStyleSheet(
            f"color:{t['group_title']};border:none;font-size:11px;")
        chaser_row.addWidget(mode_lbl)

        self._rb_chaser_auto   = QRadioButton("🤖 자동")
        self._rb_chaser_manual = QRadioButton("✏ 수동")
        self._rb_chaser_manual.setChecked(True)
        _rb_ss = f"color:{t['widget_fg']};font-size:11px;border:none;"
        for rb in (self._rb_chaser_auto, self._rb_chaser_manual):
            rb.setStyleSheet(_rb_ss)
        self._chaser_mode_grp = QButtonGroup(w)
        self._chaser_mode_grp.addButton(self._rb_chaser_auto,   0)
        self._chaser_mode_grp.addButton(self._rb_chaser_manual, 1)
        chaser_row.addWidget(self._rb_chaser_auto)
        chaser_row.addWidget(self._rb_chaser_manual)

        _spin_ss = (f"background:{t['input_bg']};color:{t['group_title']};"
                    f"border:1px solid {t['input_border']};"
                    "border-radius:4px;font-size:12px;font-weight:bold;")

        self._spin_manual_price = QDoubleSpinBox()
        self._spin_manual_price.setRange(0.01, 999.99)
        self._spin_manual_price.setSingleStep(0.05)
        self._spin_manual_price.setDecimals(2)
        self._spin_manual_price.setPrefix("$")
        self._spin_manual_price.setFixedWidth(80)
        self._spin_manual_price.setFixedHeight(24)
        self._spin_manual_price.setVisible(False)
        self._spin_manual_price.setStyleSheet(_spin_ss)
        chaser_row.addWidget(self._spin_manual_price)

        self._btn_manual_send = QPushButton("전송")
        self._btn_manual_send.setFixedSize(46, 24)
        self._btn_manual_send.setVisible(False)
        self._btn_manual_send.setStyleSheet(
            f"background:{t['group_bg']};color:#44cc44;font-size:11px;"
            "font-weight:bold;border:1px solid #3a7a2a;border-radius:6px;")
        self._btn_manual_send.clicked.connect(self._on_manual_price_send)
        chaser_row.addWidget(self._btn_manual_send)
        chaser_row.addStretch()
        lay.addLayout(chaser_row)

        self._rb_chaser_auto.toggled.connect(self._on_chaser_mode_toggle)
        self._rb_chaser_manual.toggled.connect(self._on_chaser_mode_toggle)

        self._lbl_chaser_desc = QLabel("⏱ 미체결 5초 후 자동 1틱 정정 (최대 3회)")
        self._lbl_chaser_desc.setStyleSheet(
            f"color:{t['group_title']};font-size:10px;border:none;")
        lay.addWidget(self._lbl_chaser_desc)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)

        def _sbtn(text, fg, border, cb=None):
            b = QPushButton(text)
            b.setFixedHeight(24)
            b.setStyleSheet(
                f"background:{t['group_bg']};color:{fg};font-size:11px;"
                f"font-weight:bold;border:1px solid {border};"
                "border-radius:6px;padding:2px 8px;")
            if cb:
                b.clicked.connect(cb)
            return b

        self._btn_refresh_orders = _sbtn(
            "↺ 조회", t['group_title'], t['input_border'])
        self._btn_modify_p1 = _sbtn(
            "+1호가 정정", "#44cc44", "#3a7a2a",
            lambda: self._on_modify_tick(+1))
        self._btn_modify_m1 = _sbtn(
            "-1호가 정정", "#ffaa33", "#8a5a0a",
            lambda: self._on_modify_tick(-1))
        self._btn_cancel_all = _sbtn(
            "✖ 전체 취소", "#ff4444", "#8a1a1a")

        btn_row.addWidget(self._btn_refresh_orders)
        btn_row.addWidget(self._btn_modify_p1)
        btn_row.addWidget(self._btn_modify_m1)
        btn_row.addWidget(self._btn_cancel_all)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._tbl_open_orders = QTableWidget(0, 6)
        self._tbl_open_orders.setHorizontalHeaderLabels(
            ["OID", "종목", "방향", "수량", "지정가", "상태"])
        self._tbl_open_orders.setFont(_f(11))
        self._tbl_open_orders.horizontalHeader().setFont(_f(10, bold=True))
        self._tbl_open_orders.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._tbl_open_orders.verticalHeader().setVisible(False)
        self._tbl_open_orders.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_open_orders.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_open_orders.setAlternatingRowColors(True)
        self._tbl_open_orders.setStyleSheet(get_tbl_style())
        self._tbl_open_orders.cellClicked.connect(self._on_order_row_clicked)
        lay.addWidget(self._tbl_open_orders, 1)
        return w
