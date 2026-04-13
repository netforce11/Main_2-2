"""
combo_ui_right.py — 복합 전략 탭: 우측 패널
════════════════════════════════════════════════════════════════
포함:
  - RightPanelMixin : 전략 설정 / 레그 테이블 / 손익 결과 / 차트 빌드
  - 전략 변경 핸들러 (_on_strat_change, _get_leg_template, _rebuild_legs)
  - 레그 초기화 (_reset_legs)
  - 전략 설명 팝업 (_show_strat_desc)
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem,
    QSplitter, QSpinBox, QDoubleSpinBox, QMessageBox, QFrame,
    QTabWidget, QSizePolicy,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from combo_constants import (
    SPLITTER_STYLE, STRATEGIES, STRATEGY_DESC,
    LEG_COLORS, mk_item,
)


class RightPanelMixin:
    """우측 패널(전략 설정 + 결과 + 차트) 빌드·로직 Mixin."""

    # ──────────────────────────────────────────────────────────
    # 최상위 빌드
    # ──────────────────────────────────────────────────────────
    def _build_right_panel(self) -> QWidget:
        """
        레이아웃:
          [전략 설정]
          [손익 결과 (좌) | 손익 곡선 (우)]  ← QSplitter 좌우 대칭
          [Cost Optimizer 슬라이드-인 패널]   ← 버튼 토글
        """
        container = QWidget()
        cv = QVBoxLayout(container)
        cv.setSpacing(4)
        cv.setContentsMargins(0, 0, 0, 0)

        cv.addWidget(self._build_strategy_input_panel())

        # ── 좌우 대칭: 손익결과 | 손익곡선 ───────────────────
        self._mid_hsplit = QSplitter(Qt.Horizontal)
        self._mid_hsplit.setHandleWidth(6)
        self._mid_hsplit.setStyleSheet(SPLITTER_STYLE)
        self._mid_hsplit.setChildrenCollapsible(False)
        self._mid_hsplit.addWidget(self._build_result_panel())
        self._mid_hsplit.addWidget(self._build_spread_chart_panel())
        self._mid_hsplit.setSizes([1, 1])   # 50:50  (synthetic_panel 은 전략설정 우측에 위치)
        cv.addWidget(self._mid_hsplit, 1)

        # ── Cost Optimizer 토글 영역 ─────────────────────────
        self._opt_wrapper = QWidget()
        self._opt_wrapper.setMaximumHeight(0)   # 초기: 접힘
        self._opt_wrapper.setMinimumHeight(0)
        ow = QVBoxLayout(self._opt_wrapper)
        ow.setContentsMargins(0, 4, 0, 0)
        ow.setSpacing(0)
        ow.addWidget(self._build_optimizer_panel())
        cv.addWidget(self._opt_wrapper)

        return container

    # ──────────────────────────────────────────────────────────
    # Cost Optimizer 토글 (버튼 → 슬라이드 인/아웃)
    # ──────────────────────────────────────────────────────────
    def _toggle_optimizer_panel(self):
        """Optimizer 패널을 애니메이션으로 열고 닫기."""
        collapsed = (self._opt_wrapper.maximumHeight() == 0)
        target_h  = 420 if collapsed else 0

        anim = QPropertyAnimation(self._opt_wrapper, b"maximumHeight")
        anim.setDuration(220)
        anim.setStartValue(self._opt_wrapper.maximumHeight())
        anim.setEndValue(target_h)
        anim.setEasingCurve(
            QEasingCurve.OutCubic if collapsed else QEasingCurve.InCubic)
        # 참조 보관 (GC 방지)
        self._opt_anim = anim
        anim.start()

        # 버튼 텍스트 갱신
        if hasattr(self, "_btn_opt_toggle"):
            self._btn_opt_toggle.setText(
                "🔍 Cost Optimiser  ▲" if collapsed
                else "🔍 Cost Optimiser  ▼")

    # ──────────────────────────────────────────────────────────
    # 전략 설정 패널
    # ──────────────────────────────────────────────────────────
    def _build_strategy_input_panel(self) -> QGroupBox:
        """
        v2.3: 전략 설정 패널을 좌/우 2파트 QSplitter 로 분할.
          좌(1/2): 전략 유형 선택 + 레그 설정 테이블
          우(1/2): 기초자산 입력 + 계산/초기화/Optimizer 버튼
                   + ⚡합성 주문 버튼 + 증거금확인/합성잔고 탭
        """
        gb = QGroupBox("📋 전략 설정")
        outer = QVBoxLayout(gb)
        outer.setSpacing(4); outer.setContentsMargins(6, 6, 6, 6)

        # ── 좌우 스플리터 ─────────────────────────────────────
        hsplit = QSplitter(Qt.Horizontal)
        hsplit.setHandleWidth(5)
        hsplit.setStyleSheet(SPLITTER_STYLE)
        hsplit.setChildrenCollapsible(False)

        # ════════════════════════════════
        # 좌측 파트: 전략 유형 + 레그 테이블
        # ════════════════════════════════
        left_w = QWidget()
        left_v = QVBoxLayout(left_w)
        left_v.setSpacing(4); left_v.setContentsMargins(2, 2, 4, 2)

        # 전략 유형 선택 행
        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("전략 유형:"))

        self.combo_strat = QComboBox()
        self.combo_strat.addItems(STRATEGIES)
        self.combo_strat.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;padding:3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;font-size:12px;}"
            "QComboBox::drop-down{border:none;}")
        self.combo_strat.currentIndexChanged.connect(self._on_strat_change)
        strat_row.addWidget(self.combo_strat, 1)

        # ❓ 전략 설명 팝업 버튼
        self.btn_strat_info = QPushButton("❓")
        self.btn_strat_info.setFixedSize(26, 26)
        self.btn_strat_info.setToolTip("전략 설명 보기")
        self.btn_strat_info.setStyleSheet(
            "QPushButton{background:#1a2a4a;color:#90caf9;border:1px solid #3a3a6a;"
            "border-radius:4px;font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#2a3a6a;color:#ffd700;}")
        self.btn_strat_info.clicked.connect(self._show_strat_desc)
        strat_row.addWidget(self.btn_strat_info)
        left_v.addLayout(strat_row)

        # 레그 설정: 수동/자동 모드 행
        leg_mode_row = QHBoxLayout(); leg_mode_row.setSpacing(4)
        self._leg_mode_lbl = QLabel("레그 설정")
        self._leg_mode_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        leg_mode_row.addWidget(self._leg_mode_lbl)
        leg_mode_row.addStretch()

        self._btn_leg_auto = QPushButton("🔗 자동 입력")
        self._btn_leg_auto.setCheckable(True)
        self._btn_leg_auto.setChecked(True)
        self._btn_leg_auto.setFixedHeight(22)
        self._btn_leg_auto.setStyleSheet(
            "QPushButton{background:#1a5c2e;color:#00ff88;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #00ff88;}"
            "QPushButton:!checked{background:#0a0a1e;color:#555;border:1px solid #333;}"
            "QPushButton:hover{background:#2a8a4a;}")
        self._btn_leg_manual = QPushButton("✏ 수동 입력")
        self._btn_leg_manual.setCheckable(True)
        self._btn_leg_manual.setChecked(False)
        self._btn_leg_manual.setFixedHeight(22)
        self._btn_leg_manual.setStyleSheet(
            "QPushButton{background:#0a0a1e;color:#555;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #333;}"
            "QPushButton:checked{background:#2a1a5a;color:#ffd700;border:1px solid #ffd700;}"
            "QPushButton:hover{background:#1a1a3a;}")
        self._btn_leg_auto.clicked.connect(lambda: self._set_leg_mode("auto"))
        self._btn_leg_manual.clicked.connect(lambda: self._set_leg_mode("manual"))
        leg_mode_row.addWidget(self._btn_leg_auto)
        leg_mode_row.addWidget(self._btn_leg_manual)
        left_v.addLayout(leg_mode_row)

        self._leg_mode = "auto"   # "auto" | "manual"

        self.tbl_legs = QTableWidget(0, 7)
        self.tbl_legs.setHorizontalHeaderLabels(
            ["레그", "방향", "C/P", "행사가", "프리미엄($)", "수량", "만기"])
        self.tbl_legs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_legs.verticalHeader().setVisible(False)
        self.tbl_legs.setAlternatingRowColors(True)
        self.tbl_legs.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-weight:bold;}")
        left_v.addWidget(self.tbl_legs, 1)

        # 수동 모드 전용: 레그 추가/제거 버튼 행
        self._manual_btn_row = QWidget()
        manual_btn_h = QHBoxLayout(self._manual_btn_row)
        manual_btn_h.setContentsMargins(0, 1, 0, 1); manual_btn_h.setSpacing(4)
        btn_add_leg = QPushButton("➕ 레그 추가")
        btn_add_leg.setFixedHeight(22)
        btn_add_leg.setStyleSheet(
            "background:#1a2a4a;color:#90caf9;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #3a5a9a;")
        btn_add_leg.clicked.connect(self._manual_add_leg)
        btn_del_leg = QPushButton("➖ 레그 제거")
        btn_del_leg.setFixedHeight(22)
        btn_del_leg.setStyleSheet(
            "background:#2a0a1a;color:#ff6666;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #5a1a1a;")
        btn_del_leg.clicked.connect(self._manual_del_leg)
        lbl_manual_hint = QLabel("방향·C/P·행사가·프리미엄·수량·만기 직접 입력")
        lbl_manual_hint.setStyleSheet("color:#555577;font-size:9px;border:none;")
        manual_btn_h.addWidget(btn_add_leg)
        manual_btn_h.addWidget(btn_del_leg)
        manual_btn_h.addWidget(lbl_manual_hint)
        manual_btn_h.addStretch()
        self._manual_btn_row.setVisible(False)   # 기본 숨김 (자동 모드)
        left_v.addWidget(self._manual_btn_row)

        hsplit.addWidget(left_w)

        # ════════════════════════════════
        # 우측 파트: 입력 + 버튼 + 상태 탭
        # ════════════════════════════════
        right_w = QWidget()
        right_v = QVBoxLayout(right_w)
        right_v.setSpacing(4); right_v.setContentsMargins(4, 2, 2, 2)

        # 기초자산 입력 (커버드콜·프로텍티브풋)
        stock_row = QHBoxLayout(); stock_row.setSpacing(6)
        stock_row.addWidget(QLabel("주식 현재가:"))
        self.edit_stock_price = QLineEdit()
        self.edit_stock_price.setPlaceholderText("커버드콜·프로텍티브풋")
        self.edit_stock_price.setFixedHeight(26)
        self.edit_stock_price.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;")
        stock_row.addWidget(self.edit_stock_price, 1)
        stock_row.addWidget(QLabel("수량:"))
        self.spin_stock_qty = QSpinBox()
        self.spin_stock_qty.setRange(1, 100000)
        self.spin_stock_qty.setValue(100)
        self.spin_stock_qty.setSuffix(" 주")
        self.spin_stock_qty.setFixedHeight(26)
        stock_row.addWidget(self.spin_stock_qty)
        right_v.addLayout(stock_row)

        # ── 버튼 헬퍼 ─────────────────────────────────────────
        def _mk_btn(text, bg, fg, fn, obj_name=None):
            b = QPushButton(text)
            b.setFixedHeight(28)
            if obj_name:
                b.setObjectName(obj_name)
                b.setStyleSheet(
                    f"QPushButton#{obj_name}{{background:{bg};color:{fg};"
                    f"border:1px solid {fg};border-radius:4px;font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;}}"
                    f"QPushButton#{obj_name}:hover{{background:{fg};color:#000;}}"
                    f"QPushButton#{obj_name}:disabled{{background:#111;color:#444;border-color:#333;}}")
            else:
                b.setStyleSheet(
                    f"background:{bg};color:{fg};font-size:11px;"
                    f"font-weight:bold;padding:3px 8px;border-radius:4px;")
            b.clicked.connect(fn)
            return b

        # ── 그룹 A: 손익계산 / 증거금조회 / 초기화 / Optimiser ──
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        btn_row.addWidget(_mk_btn("📊 손익 계산",  "#1a5c2e", "#00ff88", self._calc_pnl))
        self.btn_check_margin = _mk_btn("💰 증거금 조회", "#1a1a0e", "#ffd700", self._on_check_margin, "btn_check_margin")
        btn_row.addWidget(self.btn_check_margin)
        btn_row.addWidget(_mk_btn("🗑 초기화", "#5a1a1a", "#ff6666", self._reset_legs))
        self._btn_opt_toggle = _mk_btn("🔍 Optimiser ▼", "#1a2a4a", "#90caf9", self._toggle_optimizer_panel)
        btn_row.addWidget(self._btn_opt_toggle)

        # 구분선
        sep = QLabel("│")
        sep.setStyleSheet("color:#333;font-size:16px;border:none;")
        sep.setFixedWidth(10); sep.setAlignment(Qt.AlignCenter)
        btn_row.addWidget(sep)

        # ── 그룹 B: 합성주문 / 미체결 / 정정 / 취소 ──────────────
        self.btn_synthetic_order = _mk_btn("⚡ 합성 주문", "#0e2e1a", "#00ff88", self._on_synthetic_order, "btn_synthetic_order")
        btn_row.addWidget(self.btn_synthetic_order)
        self.btn_open_orders  = _mk_btn("📋 미체결", "#1a1a3a", "#aabbff", self._on_open_orders,  "btn_open_orders")
        self.btn_modify_order = _mk_btn("✏ 정정",   "#2a1a0a", "#ffaa44", self._on_modify_order, "btn_modify_order")
        self.btn_cancel_order = _mk_btn("✖ 취소",   "#2a0a0a", "#ff4444", self._on_cancel_order, "btn_cancel_order")
        btn_row.addWidget(self.btn_open_orders)
        btn_row.addWidget(self.btn_modify_order)
        btn_row.addWidget(self.btn_cancel_order)
        right_v.addLayout(btn_row)

        # ★ v2.3 증거금확인 / 합성잔고 탭 (우측 하단)
        self.synthetic_panel = SyntheticStatusPanel()
        right_v.addWidget(self.synthetic_panel, 1)

        hsplit.addWidget(right_w)
        hsplit.setSizes([1, 1])   # 50:50

        outer.addWidget(hsplit, 1)
        gb.setMinimumHeight(220)
        return gb

    # ──────────────────────────────────────────────────────────
    # 손익 분석 결과 패널 (★ v2.3: 스프레드 계산 그리드 통합 · 좌측)
    # ──────────────────────────────────────────────────────────
    def _build_result_panel(self) -> QGroupBox:
        gb = QGroupBox("📈 손익 분석 결과")
        v  = QVBoxLayout(gb)
        v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        # KPI 빅 넘버
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(8)
        self._kpi_widgets = {}
        for key, label, col in [
            ("max_profit", "최대 이익",  "#00ff88"),
            ("max_loss",   "최대 손실",  "#ff4444"),
            ("breakeven1", "손익분기①", "#ffd700"),
            ("breakeven2", "손익분기②", "#ffd700"),
            ("cost",       "순 비용",    "#90caf9"),
            ("rr",         "R:R",        "#ff8844"),
        ]:
            box = QWidget()
            bv  = QVBoxLayout(box); bv.setContentsMargins(6, 4, 6, 4)
            box.setStyleSheet(
                "border:1px solid #2a2a4a;border-radius:5px;background:#0a0a1e;")
            lbl_k = QLabel(label)
            lbl_k.setStyleSheet(
                f"color:{col};font-size:10px;font-weight:bold;border:none;")
            lbl_v = QLabel("―")
            lbl_v.setFont(QFont("Arial", 13, QFont.Bold))
            lbl_v.setStyleSheet(f"color:{col};border:none;")
            lbl_v.setAlignment(Qt.AlignCenter)
            bv.addWidget(lbl_k); bv.addWidget(lbl_v)
            self._kpi_widgets[key] = lbl_v
            kpi_row.addWidget(box)
        v.addLayout(kpi_row)

        # ── 스프레드 계산 수치 (★ v2.3: 차트 패널에서 이동) ──
        spread_grid = QGridLayout(); spread_grid.setSpacing(6)
        self._spread_labels = {}
        for i, (key, label) in enumerate([
            ("call_spread", "콜 스프레드 (너비)"),
            ("put_spread",  "풋 스프레드 (너비)"),
            ("buy_cost",    "매수 비용 (총)"),
            ("max_gain",    "최대 이익 (총)"),
            ("credit",      "수취 크레딧"),
            ("margin",      "예상 증거금"),
        ]):
            lbl_k = QLabel(label + ":")
            lbl_k.setStyleSheet("color:#aaa;font-size:10px;border:none;")
            lbl_v = QLabel("―")
            lbl_v.setStyleSheet(
                "color:#ffd700;font-size:11px;font-weight:bold;border:none;")
            spread_grid.addWidget(lbl_k, i // 2, (i % 2) * 2)
            spread_grid.addWidget(lbl_v, i // 2, (i % 2) * 2 + 1)
            self._spread_labels[key] = lbl_v
        v.addLayout(spread_grid)

        # 시나리오 테이블 (BEP 근처만 표시 — 필터는 _update_scenario_table)
        scenario_lbl = QLabel("행사가별 손익  (BEP 근처)")
        scenario_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        v.addWidget(scenario_lbl)

        self.tbl_scenario = QTableWidget(0, 6)
        self.tbl_scenario.setHorizontalHeaderLabels([
            "기초자산 가격", "총 PnL ($)", "PnL (×100)", "수익률 (%)",
            "콜 레그", "풋 레그"])
        self.tbl_scenario.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_scenario.verticalHeader().setVisible(False)
        self.tbl_scenario.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_scenario.setAlternatingRowColors(True)
        self.tbl_scenario.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-weight:bold;}")
        v.addWidget(self.tbl_scenario, 1)

        gb.setMinimumHeight(200)
        return gb

    # ──────────────────────────────────────────────────────────
    # 스프레드 계산 & 손익 차트 패널 — base 구현 (우측)
    # combo_logic.PnlLogicMixin 이 MRO 앞에 있으면 자동 오버라이드됨.
    # ──────────────────────────────────────────────────────────
    def _build_spread_chart_panel(self) -> QGroupBox:
        """Base: pyqtgraph 미설치 환경용 fallback."""
        gb = QGroupBox("📉 손익 곡선")
        v  = QVBoxLayout(gb); v.setContentsMargins(4, 6, 4, 4)
        self._spread_labels = getattr(self, "_spread_labels", {})
        if PG:
            self._pw_pnl = pg.PlotWidget()
            self._pw_pnl.showGrid(x=True, y=True, alpha=0.2)
            self._pw_pnl.setLabel('left', 'PnL ($)')
            self._pw_pnl.setLabel('bottom', '기초자산 가격')
            self._pw_pnl.addLine(y=0, pen=pg.mkPen('#444', width=1))
            self._curve_pnl = self._pw_pnl.plot(
                pen=pg.mkPen('#00ff88', width=2), name="PnL")
            self._curve_be  = self._pw_pnl.plot(
                pen=pg.mkPen('#ffd700', width=1, style=Qt.DashLine), name="손익분기")
            v.addWidget(self._pw_pnl, 1)
        else:
            v.addWidget(QLabel("pip install pyqtgraph"))
        gb.setMinimumHeight(160)
        return gb

    # ──────────────────────────────────────────────────────────
    # 전략 설명 팝업
    # ──────────────────────────────────────────────────────────
    def _show_strat_desc(self):
        strat = self.combo_strat.currentText()
        desc  = STRATEGY_DESC.get(strat, "설명 정보가 없습니다.")
        dlg   = QMessageBox(self)
        dlg.setWindowTitle(f"전략 설명")
        dlg.setText(desc)
        dlg.setStyleSheet(
            "QMessageBox{background:#0d0d22;color:#ccc;}"
            "QLabel{color:#ffd700;font-size:13px;min-width:480px;}"
            "QPushButton{background:#1a2a4a;color:#90caf9;"
            "border:1px solid #3a3a6a;border-radius:4px;"
            "padding:6px 18px;font-size:12px;}"
            "QPushButton:hover{background:#2a3a6a;}")
        dlg.exec_()

    # ──────────────────────────────────────────────────────────
    # 전략 변경 → 레그 재구성
    # ──────────────────────────────────────────────────────────
    def _on_strat_change(self, idx: int):
        strat = self.combo_strat.currentText()
        legs  = self._get_leg_template(strat)
        self._rebuild_legs(legs)

        needs_stock = "커버드" in strat or "프로텍티브" in strat
        self.edit_stock_price.setEnabled(needs_stock)
        self.spin_stock_qty.setEnabled(needs_stock)
        self.edit_stock_price.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;"
            if needs_stock else
            "background:#070710;color:#555;border:1px solid #222;")

    def _get_leg_template(self, strat: str) -> list:
        """전략별 기본 레그 정의 반환."""
        # ── 만기: YYYYMMDD 형식으로 첫 번째 항목 사용 ─────────
        expiry_default = (
            self._expiry_list[0][0]
            if self._expiry_list else ""
        )
        base = {"qty": "1", "expiry": expiry_default}

        templates = {
            "커버드 콜": [
                {**base, "leg": "레그1", "dir": "SELL", "cp": "C",
                 "strike": "", "prem": ""},
            ],
            "프로텍티브 풋": [
                {**base, "leg": "레그1", "dir": "BUY", "cp": "P",
                 "strike": "", "prem": ""},
            ],
            "콜 스프레드": [
                {**base, "leg": "레그1", "dir": "BUY",  "cp": "C",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그2", "dir": "SELL", "cp": "C",
                 "strike": "", "prem": ""},
            ],
            "풋 스프레드": [
                {**base, "leg": "레그1", "dir": "BUY",  "cp": "P",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그2", "dir": "SELL", "cp": "P",
                 "strike": "", "prem": ""},
            ],
            # ── 신규: 콜 데빗 스프레드 ────────────────────────
            "콜 데빗 스프레드": [
                {**base, "leg": "레그1", "dir": "BUY",  "cp": "C",
                 "strike": "", "prem": ""},   # ATM/ITM 매수
                {**base, "leg": "레그2", "dir": "SELL", "cp": "C",
                 "strike": "", "prem": ""},   # OTM 매도
            ],
            # ── 신규: 풋 데빗 스프레드 ────────────────────────
            "풋 데빗 스프레드": [
                {**base, "leg": "레그1", "dir": "BUY",  "cp": "P",
                 "strike": "", "prem": ""},   # ATM/ITM 매수
                {**base, "leg": "레그2", "dir": "SELL", "cp": "P",
                 "strike": "", "prem": ""},   # OTM 매도
            ],
            "스트래들": [
                {**base, "leg": "레그1", "dir": "BUY", "cp": "C",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그2", "dir": "BUY", "cp": "P",
                 "strike": "", "prem": ""},
            ],
            "스트랭글": [
                {**base, "leg": "레그1", "dir": "BUY", "cp": "C",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그2", "dir": "BUY", "cp": "P",
                 "strike": "", "prem": ""},
            ],
            "아이언 콘도르": [
                {**base, "leg": "레그1", "dir": "BUY",  "cp": "P",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그2", "dir": "SELL", "cp": "P",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그3", "dir": "SELL", "cp": "C",
                 "strike": "", "prem": ""},
                {**base, "leg": "레그4", "dir": "BUY",  "cp": "C",
                 "strike": "", "prem": ""},
            ],
            # ── 신규: 콜 백 스프레드 ──────────────────────────
            # 구조: OTM 콜 매도(1계약) + ATM/ITM 콜 매수(2계약) — 강한 상승에 수익
            "콜 백 스프레드 (콜매도×1 + 콜매수×2 / 강한상승)": [
                {**base, "leg": "레그1", "dir": "SELL", "cp": "C",
                 "qty": "1", "strike": "", "prem": ""},   # OTM 콜 매도 (1계약)
                {**base, "leg": "레그2", "dir": "BUY",  "cp": "C",
                 "qty": "2", "strike": "", "prem": ""},   # 더 낮은 행사가 콜 매수 (2계약)
            ],
            # ── 신규: 풋 백 스프레드 ──────────────────────────
            # 구조: OTM 풋 매도(1계약) + ATM/ITM 풋 매수(2계약) — 강한 하락에 수익
            "풋 백 스프레드 (풋매도×1 + 풋매수×2 / 강한하락)": [
                {**base, "leg": "레그1", "dir": "SELL", "cp": "P",
                 "qty": "1", "strike": "", "prem": ""},   # OTM 풋 매도 (1계약)
                {**base, "leg": "레그2", "dir": "BUY",  "cp": "P",
                 "qty": "2", "strike": "", "prem": ""},   # 더 높은 행사가 풋 매수 (2계약)
            ],
        }

        # 부분 매칭으로 키 검색
        for key, tmpl in templates.items():
            if key in strat:
                return tmpl
        return []

    def _rebuild_legs(self, legs: list):
        """레그 테이블 재구성. 만기 칼럼(6)은 YYYYMMDD → MM/DD 표시."""
        self.tbl_legs.setRowCount(0)
        for i, leg in enumerate(legs):
            r = self.tbl_legs.rowCount()
            self.tbl_legs.insertRow(r)
            col = LEG_COLORS[i % len(LEG_COLORS)]

            # 0: 레그명 (읽기전용)
            it0 = QTableWidgetItem(leg["leg"])
            it0.setTextAlignment(Qt.AlignCenter)
            it0.setForeground(QBrush(QColor(col)))
            it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
            self.tbl_legs.setItem(r, 0, it0)

            # 1: 방향 (읽기전용, 색상)
            dir_col = "#00ff88" if leg["dir"] == "BUY" else "#ff6666"
            it1 = QTableWidgetItem(leg["dir"])
            it1.setTextAlignment(Qt.AlignCenter)
            it1.setForeground(QBrush(QColor(dir_col)))
            it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
            self.tbl_legs.setItem(r, 1, it1)

            # 2~5: cp, strike, prem, qty (편집 가능)
            for c, key in enumerate(["cp", "strike", "prem", "qty"], 2):
                it = QTableWidgetItem(str(leg.get(key, "")))
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl_legs.setItem(r, c, it)

            # 6: 만기 — YYYYMMDD → MM/DD 로 표시
            raw_expiry = str(leg.get("expiry", ""))
            display_expiry = _fmt_expiry(raw_expiry)
            it_exp = QTableWidgetItem(display_expiry)
            it_exp.setTextAlignment(Qt.AlignCenter)
            it_exp.setForeground(QBrush(QColor("#aaffaa")))
            self.tbl_legs.setItem(r, 6, it_exp)

    def _reset_legs(self):
        """레그 입력 + 결과 초기화."""
        self._on_strat_change(self.combo_strat.currentIndex())
        self.tbl_scenario.setRowCount(0)
        for v in self._kpi_widgets.values():
            v.setText("―")
        for v in self._spread_labels.values():
            v.setText("―")
        if PG:
            self._curve_pnl.setData([], [])
        self._log("초기화 완료")

    def _on_whatif_acct_value(self, tag: str, value: str, currency: str, account: str):
        """bridge.acct_value 슬롯 — whatIf 세션 중일 때만 버퍼 저장."""
        if self._whatif_session == -1:
            return
        try:
            v = float(value)
            buf = getattr(self, '_whatif_acct_buf', {})
            if tag == "AvailableFunds":
                buf["af"] = v
            elif tag == "BuyingPower":
                buf["bp"] = v
            self._whatif_acct_buf = buf
        except (ValueError, TypeError):
            pass

    def _on_whatif_acct_end(self):
        """bridge.acct_end 슬롯 — 가용 증거금 확정 후 whatIf 레그 전송."""
        if self._whatif_session == -1:
            return
        buf = getattr(self, '_whatif_acct_buf', {})
        available = buf.get("af") or buf.get("bp") or 0.0
        self._whatif_available = available
        self._log(f"💰 가용 증거금: ${available:,.2f}")
        send_fn = getattr(self, '_whatif_send_legs', None)
        if send_fn:
            send_fn()

    def _on_whatif_result(self, oid, init_before, init_after,
                          maint_before, maint_after, commission):
        """
        whatif_sig 수신 슬롯 — 항상 메인 스레드에서 실행 (QueuedConnection).
        현재 세션 OID만 처리.

        IB는 레그당 2번 콜백을 보냄:
          1번째: initBefore=0, initAfter=0  (미확정 — 무시)
          2번째: initBefore=0, initAfter=실제값  (← 이게 정답)
        → initAfter > 0 인 콜백만 저장, 항상 최신값으로 덮어씀.
        """
        oids = getattr(self, '_whatif_oids', [])
        if oid not in oids:
            return

        # 첫 번째 미확정 콜백 필터:
        # - SELL 레그: initAfter=0이면 미확정 → 무시
        # - BUY  레그: initAfter=0이 정상값 → 통과시켜야 함
        # 판별: _whatif_legs에서 해당 oid 인덱스의 dir 확인
        legs_info  = getattr(self, '_whatif_legs', [])
        oids       = getattr(self, '_whatif_oids', [])
        leg_idx    = oids.index(oid) if oid in oids else -1
        leg_dir    = legs_info[leg_idx]["dir"] if 0 <= leg_idx < len(legs_info) else "BUY"

        if leg_dir == "SELL" and init_after <= 0 and init_before <= 0:
            return  # SELL 레그 미확정값 무시

        buf = getattr(self, '_whatif_buf', {})
        buf[oid] = {
            "init_before":  init_before,
            "init_after":   init_after,
            "maint_before": maint_before,
            "maint_after":  maint_after,
            "commission":   commission,
        }
        self._whatif_buf = buf
        self._log(f"🔍 whatIf oid={oid}: initAfter=${init_after:,.2f}")

        # 모든 레그 유효값 수신 완료 → 처리
        if len(buf) >= len(oids):
            sid = getattr(self, '_whatif_session', -1)
            self._finish_whatif(sid)

    def _finish_whatif(self, session_id: int):
        """whatIf 결과 최종 처리 — 메인 스레드에서만 호출."""
        if session_id != getattr(self, '_whatif_session', -1):
            return  # 이미 다른 세션이 시작됨
        # 세션 무효화 (중복 실행 방지)
        self._whatif_session = -1

        buf   = getattr(self, '_whatif_buf', {})
        oids  = getattr(self, '_whatif_oids', [])
        panel = getattr(self, 'synthetic_panel', None)
        strat    = getattr(self, '_whatif_strat',    "―")
        cost_str = getattr(self, '_whatif_cost_str', "―")
        available= getattr(self, '_whatif_available', 0.0)
        on_done  = getattr(self, '_whatif_on_done',  None)

        if not buf:
            self._log("⚠ whatIf 결과 없음 — TWS 응답 확인 필요")
            return

        # 마지막 레그의 after - before = 이 주문으로 증가하는 증거금
        last = buf.get(oids[-1], buf[list(buf.keys())[-1]])
        init_before = last.get("init_before", 0.0)
        init_after  = last.get("init_after",  0.0)
        required    = max(0.0, init_after - init_before)
        commission  = last.get("commission", "―")

        self._log(
            f"💰 whatIf 완료: 가용=${available:,.2f}  "
            f"initBefore=${init_before:,.2f}  initAfter=${init_after:,.2f}  "
            f"필요증거금=${required:,.2f}  예상수수료={commission}")

        if panel:
            panel.update_margin(
                available=available,
                required=required,
                strategy=strat,
                cost=cost_str,
            )

        if on_done:
            margin_ok = (available >= required) if required > 0 else True
            on_done(available, required, margin_ok)


# ── 만기 포맷 유틸 ────────────────────────────────────────────
def _fmt_expiry(raw: str) -> str:
    """YYYYMMDD 또는 다양한 형식 → MM/DD 표시.

    입력 예시:
        "20260117"  → "01/17"
        "2026-01-17"→ "01/17"
        "오늘"       → "오늘"
        ""          → "―"
    """
    if not raw:
        return "―"
    # 숫자만 남기기
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 8:          # YYYYMMDD
        return f"{digits[4:6]}/{digits[6:8]}"
    if len(digits) == 6:          # YYMMDD
        return f"{digits[2:4]}/{digits[4:6]}"
    return raw  # 파싱 불가 → 원본 반환

# ════════════════════════════════════════════════════════════════
#  SyntheticStatusPanel  (v2.3 신규)
#  전략설정 패널 우측 하단 — [📊 증거금 확인] / [📋 합성 잔고] 2탭
# ════════════════════════════════════════════════════════════════

_TAB_STYLE = """
QTabWidget::pane { border:1px solid #1a1a3a; background:#07070f; }
QTabBar::tab {
    background:#0d0d22; color:#666688;
    padding:3px 10px; border:1px solid #1a1a3a; border-bottom:none; font-size:11px;
}
QTabBar::tab:selected { background:#07070f; color:#e0e0ff; border-top:2px solid #00ff88; }
QTabBar::tab:hover { color:#aaaacc; }
"""

_TBL_STYLE_SYN = """
QTableWidget {
    background:#07070f; alternate-background-color:#0c0c20;
    color:#cccccc; gridline-color:#1a1a3a; border:none; font-size:11px;
}
QTableWidget::item:selected { background:#1a1a3a; color:#ffffff; }
QHeaderView::section {
    background:#0a0a1e; color:#90caf9; border:1px solid #1a1a3a;
    font-weight:bold; padding:2px 4px; font-size:10px;
}
"""


class SyntheticStatusPanel(QWidget):
    """
    합성 주문 상태 패널 (v2.3).
    전략설정 패널 우측 하단에 embed.

    Public API
    ----------
    update_margin(available, required, strategy, cost)
        증거금 확인 탭 갱신. ⚡ 합성 주문 버튼 클릭 시 호출.
    add_position(fill_info: dict)
        체결 후 합성 잔고 탭에 포지션 추가.
    update_position_prices(strategy, current_price)
        잔고 탭 현재가·손익 실시간 갱신.
    clear_positions()
        잔고 초기화.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("synthetic_status_panel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#07070f;")
        self._positions = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        root.addWidget(self._tabs)

        self._tabs.addTab(self._build_margin_tab(),   "📊 증거금 확인")
        self._tabs.addTab(self._build_position_tab(), "📋 합성 잔고")

    # ── 탭1: 증거금 확인 ────────────────────────────────────────
    def _build_margin_tab(self):
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(5)

        def kv(label):
            row = QHBoxLayout()
            lk = QLabel(label); lk.setStyleSheet("color:#888;font-size:10px;border:none;")
            lv = QLabel("―");   lv.setStyleSheet("color:#e0e0e0;font-size:11px;font-weight:bold;border:none;")
            row.addWidget(lk); row.addStretch(); row.addWidget(lv)
            return row, lv

        row_s, self._lbl_m_strategy = kv("전략명")
        row_c, self._lbl_m_cost     = kv("순 비용")
        lay.addLayout(row_s); lay.addLayout(row_c)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color:#1a1a3a; max-height:1px;")
        lay.addWidget(sep1)

        row_a, self._lbl_m_available = kv("주문가능")
        row_r, self._lbl_m_required  = kv("필요증거금")
        lay.addLayout(row_a); lay.addLayout(row_r)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#1a1a3a; max-height:1px;")
        lay.addWidget(sep2)

        self._lbl_margin_status = QLabel("―")
        self._lbl_margin_status.setAlignment(Qt.AlignCenter)
        self._lbl_margin_status.setStyleSheet(
            "font-size:11px;font-weight:bold;color:#555577;"
            "padding:5px;border:1px solid #2a2a4a;border-radius:4px;background:#0a0a1e;")
        lay.addWidget(self._lbl_margin_status)
        lay.addStretch()
        return w

    # ── 탭2: 합성 잔고 ──────────────────────────────────────────
    def _build_position_tab(self):
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        summary = QHBoxLayout()
        lbl_ttl = QLabel("총 손익"); lbl_ttl.setStyleSheet("color:#888;font-size:10px;border:none;")
        self._lbl_total_pnl = QLabel("$0.00")
        self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;font-size:12px;font-weight:bold;border:none;")
        summary.addWidget(lbl_ttl); summary.addStretch(); summary.addWidget(self._lbl_total_pnl)
        lay.addLayout(summary)

        self._lbl_no_pos = QLabel("체결된 합성 포지션이 없습니다.")
        self._lbl_no_pos.setAlignment(Qt.AlignCenter)
        self._lbl_no_pos.setStyleSheet("color:#333355;font-size:11px;padding:14px;")
        lay.addWidget(self._lbl_no_pos)

        self._tbl_pos = QTableWidget(0, 5)
        self._tbl_pos.setHorizontalHeaderLabels(["전략명","수량","진입가","현재가","손익"])
        self._tbl_pos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            self._tbl_pos.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_pos.verticalHeader().setVisible(False)
        self._tbl_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_pos.setAlternatingRowColors(True)
        self._tbl_pos.setStyleSheet(_TBL_STYLE_SYN)
        self._tbl_pos.setVisible(False)
        lay.addWidget(self._tbl_pos, 1)
        return w

    # ── Public API ───────────────────────────────────────────────
    def update_margin(self, available: float, required: float,
                      strategy: str = "―", cost: str = "―"):
        self._lbl_m_strategy.setText(strategy or "―")
        self._lbl_m_cost.setText(cost or "―")
        self._lbl_m_available.setText(f"${available:,.2f}")
        self._lbl_m_required.setText(f"${required:,.2f}")
        if required <= 0:
            self._lbl_margin_status.setText("— 데이터 없음 —")
            self._lbl_margin_status.setStyleSheet(
                "font-size:11px;font-weight:bold;color:#555577;"
                "padding:5px;border:1px solid #2a2a4a;border-radius:4px;background:#0a0a1e;")
        elif available >= required:
            surplus = available - required
            self._lbl_margin_status.setText(f"✅  주문 가능  (여유 ${surplus:,.2f})")
            self._lbl_margin_status.setStyleSheet(
                "font-size:11px;font-weight:bold;color:#00ff88;"
                "padding:5px;border:1px solid #00ff88;border-radius:4px;background:#071a0e;")
        else:
            shortage = required - available
            self._lbl_margin_status.setText(f"❌  증거금 부족  (${shortage:,.2f} 부족)")
            self._lbl_margin_status.setStyleSheet(
                "font-size:11px;font-weight:bold;color:#ff4444;"
                "padding:5px;border:1px solid #ff4444;border-radius:4px;background:#1a0707;")
        self._tabs.setCurrentIndex(0)

    def add_position(self, fill_info: dict):
        """fill_info = {strategy, qty, entry, current(optional)}"""
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def update_position_prices(self, strategy: str, current_price: float):
        for pos in self._positions:
            if pos.get("strategy") == strategy:
                pos["current"] = current_price
        self._refresh_pos_table()

    def clear_positions(self):
        self._positions.clear()
        self._refresh_pos_table()

    def _refresh_pos_table(self):
        tbl = self._tbl_pos
        tbl.setRowCount(0)
        if not self._positions:
            self._lbl_no_pos.setVisible(True)
            tbl.setVisible(False)
            self._lbl_total_pnl.setText("$0.00")
            self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;font-size:12px;font-weight:bold;border:none;")
            return
        self._lbl_no_pos.setVisible(False)
        tbl.setVisible(True)
        tbl.setRowCount(len(self._positions))
        total_pnl = 0.0

        for r, pos in enumerate(self._positions):
            strategy = pos.get("strategy", "―")
            qty      = pos.get("qty", 1)
            entry    = pos.get("entry", 0.0)
            current  = pos.get("current", entry)
            pnl      = (current - entry) * qty * 100
            total_pnl += pnl
            pnl_col = "#00ff88" if pnl > 0 else "#ff4444" if pnl < 0 else "#888899"

            def _it(text, color="#cccccc", align=Qt.AlignCenter):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            tbl.setItem(r, 0, _it(strategy,          "#e0e0ff", Qt.AlignLeft | Qt.AlignVCenter))
            tbl.setItem(r, 1, _it(str(qty),           "#aaaaaa"))
            tbl.setItem(r, 2, _it(f"${entry:.2f}",    "#aaaaaa"))
            tbl.setItem(r, 3, _it(f"${current:.2f}",  "#e0e0e0"))
            tbl.setItem(r, 4, _it(f"${pnl:+,.2f}",   pnl_col))

        tc = "#00ff88" if total_pnl > 0 else "#ff4444" if total_pnl < 0 else "#888899"
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};font-size:12px;font-weight:bold;border:none;")


# ════════════════════════════════════════════════════════════════
#  _on_synthetic_order — RightPanelMixin 에 동적 주입 (v2.3)
# ════════════════════════════════════════════════════════════════

def _on_synthetic_order(self):
    """
    ⚡ 합성 주문 버튼 핸들러 (v2.4: 실제 IB placeOrder 연동).
    흐름:
      1. 레그 테이블 파싱 → Contract 리스트 + Order 리스트 생성
      2. 증거금 확인 탭에 결과 표시
      3. 사용자 확인 → mw.ib.placeOrder() 레그별 전송
    """
    panel = getattr(self, 'synthetic_panel', None)
    if panel is None:
        self._log("⚠ synthetic_panel 없음")
        return

    # ── 연결 확인 ──────────────────────────────────────────────
    connected = getattr(getattr(self, 'mw', None), 'connected', False)
    if not connected:
        QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.\n연결 후 합성 주문을 전송할 수 있습니다.")
        return

    strat    = self.combo_strat.currentText() if hasattr(self, 'combo_strat') else "―"
    cost_str = "―"
    kpi = getattr(self, '_kpi_widgets', {})
    if 'cost' in kpi:
        cost_str = kpi['cost'].text()

    # ── 레그 파싱 ─────────────────────────────────────────────
    legs = _parse_legs_from_table(self)
    if not legs:
        QMessageBox.warning(self, "레그 오류",
            "레그 설정이 비어있거나 행사가/만기가 입력되지 않았습니다.\n"
            "체인 클릭 또는 수동 입력 후 다시 시도하세요.")
        return

    # ── whatIf 증거금 확인 → 사용자 확인 → 실제 주문 ─────────
    def _on_margin_checked(available, required, margin_ok):
        if not margin_ok:
            QMessageBox.warning(
                self, "증거금 부족",
                f"가용 증거금: ${available:,.2f}\n"
                f"필요 증거금: ${required:,.2f}\n\n"
                f"증거금이 부족합니다. 주문을 취소합니다.")
            return
        leg_summary = "\n".join(
            f"  레그{i+1}: {lg['dir']} {lg['qty']}계약  "
            f"{lg['cp']} {lg['strike']}  @${lg['prem']}  만기:{lg['expiry']}"
            for i, lg in enumerate(legs)
        )
        reply = QMessageBox.question(
            self, "⚡ 합성 주문 확인",
            f"전략: {strat}\n"
            f"순비용: {cost_str}\n\n"
            f"{leg_summary}\n\n"
            f"가용 증거금: ${available:,.2f}\n"
            f"필요 증거금: ${required:,.2f}\n\n"
            f"총 {len(legs)}개 레그를 주문하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            _place_combo_legs(self, legs, strat)

    _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)



def _on_open_orders(self):
    """미체결 주문 조회 → 팝업 테이블 표시."""
    from combo_order_open import on_open_orders
    on_open_orders(self)

def _on_modify_order(self):
    """정정 주문 — 미체결 조회 후 선택 정정."""
    from combo_order_open import on_modify_order
    on_modify_order(self)

def _on_cancel_order(self):
    """취소 주문 — 미체결 조회 후 선택 취소."""
    from combo_order_open import on_cancel_order
    on_cancel_order(self)


def _on_check_margin(self):
    """
    💰 증거금 조회 버튼 핸들러 (v2.4+: whatIf=True 주문으로 실제 증거금 조회).
    실제 주문은 전송되지 않고, IB 서버가 openOrder 콜백으로
    initMarginBefore/After, maintMarginBefore/After 를 반환.
    """
    connected = getattr(getattr(self, 'mw', None), 'connected', False)
    if not connected:
        QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
        return

    strat    = self.combo_strat.currentText() if hasattr(self, 'combo_strat') else "―"
    cost_str = "―"
    kpi = getattr(self, '_kpi_widgets', {})
    if 'cost' in kpi:
        cost_str = kpi['cost'].text()

    legs = _parse_legs_from_table(self)
    if not legs:
        QMessageBox.warning(self, "레그 오류",
            "레그 설정이 비어있거나 행사가/만기가 입력되지 않았습니다.\n"
            "행사가·프리미엄·만기를 입력한 후 다시 시도하세요.")
        return

    self._log("💰 whatIf 증거금 조회 요청 중...")
    _send_whatif_order(self, legs, strat, cost_str, on_done=None)


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


def _send_whatif_order(self, legs: list, strat: str, cost_str: str, on_done=None):
    """
    whatIf=True 주문으로 IB 서버에서 실제 증거금 계산.

    스레드 안전 원칙:
      - IB 콜백은 bridge 시그널(emit)만 사용 — 콜백 교체 없음
      - bridge.acct_value / acct_end / whatif_sig 모두 고정 슬롯
      - 세션 ID로 현재 요청 결과만 필터링
    """
    from core_contract import make_opt_contract
    from ibapi.order import Order as IbOrder
    from core import bridge
    from PyQt5.QtCore import QTimer as _QT
    import time

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"

    # ── 세션 ID (이전 요청 결과 무시) ────────────────────────
    session_id = int(time.time() * 1000)
    self._whatif_session   = session_id
    self._whatif_buf       = {}
    self._whatif_oids      = []
    self._whatif_available = 0.0
    self._whatif_on_done   = on_done
    self._whatif_strat     = strat
    self._whatif_cost_str  = cost_str

    # ── 고정 슬롯 최초 1회 등록 ──────────────────────────────
    if not getattr(self, '_whatif_slots_connected', False):
        bridge.acct_value.connect(self._on_whatif_acct_value, Qt.QueuedConnection)
        bridge.acct_end.connect(self._on_whatif_acct_end,     Qt.QueuedConnection)
        bridge.whatif_sig.connect(self._on_whatif_result,     Qt.QueuedConnection)
        self._whatif_slots_connected = True

    # ── Step1: 가용 증거금 조회 ──────────────────────────────
    self._whatif_acct_buf = {}
    REQ_ACCT = 9902
    try:
        ib.reqAccountSummary(REQ_ACCT, "All", "AvailableFunds,BuyingPower")
        self._log("🔍 가용 증거금 조회 중...")
    except Exception as e:
        self._log(f"❌ reqAccountSummary 오류: {e}")
        return

    # ── Step2: acct_end 수신 후 whatIf 전송 (_on_whatif_acct_end 에서) ──
    # ── Step3: whatIf 결과 수신 (_on_whatif_result 에서) ─────────────────
    # 모든 흐름은 고정 슬롯 메서드에서 처리

    # 10초 전체 타임아웃
    _QT.singleShot(10000, lambda: _check_timeout(session_id))

    def _check_timeout(sid):
        if sid != self._whatif_session:
            return
        if not getattr(self, '_whatif_buf', {}):
            self._log("⚠ whatIf 전체 타임아웃 — TWS 응답 없음")
            self._whatif_session = -1
        elif len(self._whatif_buf) < len(self._whatif_oids):
            self._log("⚠ whatIf 일부 타임아웃 — 수신된 레그로 계산")
            self._finish_whatif(sid)

    # whatIf 레그 전송 함수 (acct_end 후 호출됨)
    def _send_legs():
        self._whatif_buf  = {}
        self._whatif_oids = []
        for i, leg in enumerate(legs):
            oid = ib.get_next_id()
            if oid is None:
                self._log("❌ nextOrderId 없음")
                return
            self._whatif_oids.append(oid)
            try:
                contract = make_opt_contract(
                    symbol=symbol,
                    strike=leg["strike"],
                    right=leg["cp"],
                    expiry=leg["expiry"],
                )
                ibord = IbOrder()
                ibord.action        = leg["dir"]
                ibord.orderType     = "LMT"
                ibord.totalQuantity = leg["qty"]
                try:
                    ibord.lmtPrice = float(leg["prem"]) if leg["prem"] else 0.0
                except (ValueError, TypeError):
                    ibord.lmtPrice = 0.0
                ibord.tif           = "DAY"
                ibord.eTradeOnly    = False
                ibord.firmQuoteOnly = False
                ibord.whatIf        = True
                ib.placeOrder(oid, contract, ibord)
                self._log(f"🔍 whatIf 레그{i+1}: {leg['dir']} {leg['qty']}  "
                          f"{leg['cp']} {int(leg['strike'])}  만기:{leg['expiry']}")
            except Exception as e:
                self._log(f"❌ whatIf 레그{i+1} 오류: {e}")

    # send_legs를 인스턴스에 저장 (acct_end 슬롯에서 호출)
    self._whatif_send_legs = _send_legs


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


def _set_leg_mode(self, mode: str):
    """수동/자동 입력 모드 전환."""
    self._leg_mode = mode
    is_manual = (mode == "manual")

    self._btn_leg_auto.setChecked(not is_manual)
    self._btn_leg_manual.setChecked(is_manual)
    self._manual_btn_row.setVisible(is_manual)

    if is_manual:
        # 수동 모드: 모든 셀 편집 가능 (방향·레그명 포함)
        for r in range(self.tbl_legs.rowCount()):
            for c in range(self.tbl_legs.columnCount()):
                it = self.tbl_legs.item(r, c)
                if it:
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
        self._log("✏ 수동 입력 모드: 모든 셀 직접 편집 가능")
    else:
        # 자동 모드: 레그명(0)·방향(1) 읽기전용
        for r in range(self.tbl_legs.rowCount()):
            for c in (0, 1):
                it = self.tbl_legs.item(r, c)
                if it:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self._log("🔗 자동 입력 모드: 체인 클릭으로 자동 입력")


def _manual_add_leg(self):
    """수동 모드: 빈 레그 행 추가."""
    r = self.tbl_legs.rowCount()
    self.tbl_legs.insertRow(r)
    from combo_constants import LEG_COLORS
    col = LEG_COLORS[r % len(LEG_COLORS)]
    defaults = [f"레그{r+1}", "BUY", "C", "", "0.00", "1", "―"]
    for c, val in enumerate(defaults):
        it = QTableWidgetItem(val)
        it.setTextAlignment(Qt.AlignCenter)
        if c == 0:
            from PyQt5.QtGui import QColor, QBrush
            it.setForeground(QBrush(QColor(col)))
        elif c == 1:
            from PyQt5.QtGui import QColor, QBrush
            it.setForeground(QBrush(QColor("#00ff88")))
        self.tbl_legs.setItem(r, c, it)
    self._log(f"➕ 레그{r+1} 추가 (수동)")


def _manual_del_leg(self):
    """수동 모드: 선택 행 또는 마지막 행 제거."""
    row = self.tbl_legs.currentRow()
    if row < 0:
        row = self.tbl_legs.rowCount() - 1
    if row >= 0:
        self.tbl_legs.removeRow(row)
        self._log(f"➖ 레그{row+1} 제거 (수동)")


RightPanelMixin._on_synthetic_order   = _on_synthetic_order
RightPanelMixin._on_check_margin      = _on_check_margin
RightPanelMixin._set_leg_mode         = _set_leg_mode
RightPanelMixin._manual_add_leg       = _manual_add_leg
RightPanelMixin._manual_del_leg       = _manual_del_leg