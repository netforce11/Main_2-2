"""
combo_ui_right_panel.py — 우측 패널 UI 빌드 전담
────────────────────────────────────────────────
포함: RightPanelMixin (UI 구조만)
의존: combo_constants, combo_ui_synthetic_panel, pyqtgraph(optional)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QGroupBox, QTableWidget,
    QHeaderView, QAbstractItemView, QSplitter, QSpinBox, QMessageBox,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import SPLITTER_STYLE, STRATEGIES, STRATEGY_DESC, LEG_COLORS
from combo_ui_synthetic_panel import SyntheticStatusPanel


class RightPanelMixin:
    """우측 패널 UI 빌드 Mixin (전략설정 / 손익결과 / 차트)."""

    # ── 최상위 ────────────────────────────────────────────────
    def _build_right_panel(self) -> QWidget:
        container = QWidget()
        cv = QVBoxLayout(container)
        cv.setSpacing(4); cv.setContentsMargins(0, 0, 0, 0)
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

    def _build_leg_left(self) -> QWidget:
        """좌측: 전략 유형 콤보 + 레그 모드 + 테이블."""
        w = QWidget(); v = QVBoxLayout(w)
        v.setSpacing(4); v.setContentsMargins(2, 2, 4, 2)

        # 전략 유형 행
        row = QHBoxLayout()
        row.addWidget(QLabel("전략 유형:"))
        self.combo_strat = QComboBox()
        self.combo_strat.addItems(STRATEGIES)
        self.combo_strat.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;padding:3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;}"
            "QComboBox::drop-down{border:none;}")
        self.combo_strat.currentIndexChanged.connect(self._on_strat_change)
        row.addWidget(self.combo_strat, 1)

        btn_info = QPushButton("❓")
        btn_info.setFixedSize(26, 26)
        btn_info.setStyleSheet(
            "QPushButton{background:#1a2a4a;color:#90caf9;border:1px solid #3a3a6a;"
            "border-radius:4px;font-size:14px;font-weight:bold;}"
            "QPushButton:hover{background:#2a3a6a;color:#ffd700;}")
        btn_info.clicked.connect(self._show_strat_desc)
        row.addWidget(btn_info)
        v.addLayout(row)

        # 레그 모드 행
        mode_row = QHBoxLayout(); mode_row.setSpacing(4)
        mode_row.addWidget(QLabel("레그 설정"))
        mode_row.addStretch()
        _btn_style_on  = ("QPushButton{background:#1a5c2e;color:#00ff88;font-size:10px;"
                          "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #00ff88;}"
                          "QPushButton:!checked{background:#0a0a1e;color:#555;border:1px solid #333;}"
                          "QPushButton:hover{background:#2a8a4a;}")
        _btn_style_off = ("QPushButton{background:#0a0a1e;color:#555;font-size:10px;"
                          "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #333;}"
                          "QPushButton:checked{background:#2a1a5a;color:#ffd700;border:1px solid #ffd700;}"
                          "QPushButton:hover{background:#1a1a3a;}")
        self._btn_leg_auto   = QPushButton("🔗 자동 입력")
        self._btn_leg_manual = QPushButton("✏ 수동 입력")
        for btn, style, checked in [
            (self._btn_leg_auto, _btn_style_on, True),
            (self._btn_leg_manual, _btn_style_off, False),
        ]:
            btn.setCheckable(True); btn.setChecked(checked)
            btn.setFixedHeight(22); btn.setStyleSheet(style)
        self._btn_leg_auto.clicked.connect(lambda: self._set_leg_mode("auto"))
        self._btn_leg_manual.clicked.connect(lambda: self._set_leg_mode("manual"))
        mode_row.addWidget(self._btn_leg_auto)
        mode_row.addWidget(self._btn_leg_manual)
        v.addLayout(mode_row)
        self._leg_mode = "auto"

        # 레그 테이블
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
        v.addWidget(self.tbl_legs, 1)

        # 수동 모드 버튼 행
        self._manual_btn_row = QWidget()
        mbh = QHBoxLayout(self._manual_btn_row)
        mbh.setContentsMargins(0, 1, 0, 1); mbh.setSpacing(4)
        for text, style, fn in [
            ("➕ 레그 추가",
             "background:#1a2a4a;color:#90caf9;font-size:10px;font-weight:bold;"
             "padding:2px 8px;border-radius:3px;border:1px solid #3a5a9a;",
             self._manual_add_leg),
            ("➖ 레그 제거",
             "background:#2a0a1a;color:#ff6666;font-size:10px;font-weight:bold;"
             "padding:2px 8px;border-radius:3px;border:1px solid #5a1a1a;",
             self._manual_del_leg),
        ]:
            btn = QPushButton(text); btn.setFixedHeight(22)
            btn.setStyleSheet(style); btn.clicked.connect(fn)
            mbh.addWidget(btn)
        mbh.addWidget(QLabel("방향·C/P·행사가·프리미엄·수량·만기 직접 입력"))
        mbh.addStretch()
        self._manual_btn_row.setVisible(False)
        v.addWidget(self._manual_btn_row)
        return w

    def _build_leg_right(self) -> QWidget:
        """우측: 기초자산 입력 + 버튼 + SyntheticStatusPanel."""
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

        # 버튼 행
        br = QHBoxLayout(); br.setSpacing(5)
        buttons = [
            ("📊 손익 계산",   "#1a5c2e", "#00ff88", self._calc_pnl),
            ("🗑 초기화",      "#5a1a1a", "#ff6666", self._reset_legs),
            ("🔍 Optimiser ▼","#1a2a4a", "#90caf9", self._toggle_optimizer_panel),
        ]
        for text, bg, fg, fn in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(
                f"background:{bg};color:{fg};font-size:12px;"
                f"font-weight:bold;padding:6px 10px;border-radius:4px;")
            btn.clicked.connect(fn)
            br.addWidget(btn)
        self._btn_opt_toggle = br.itemAt(2).widget()  # Optimiser 버튼 참조 저장

        # 합성 주문 버튼
        self.btn_synthetic_order = QPushButton("⚡ 합성 주문")
        self.btn_synthetic_order.setObjectName("btn_synthetic_order")
        self.btn_synthetic_order.setStyleSheet(
            "QPushButton#btn_synthetic_order{background:#0e2e1a;color:#00ff88;"
            "border:1px solid #00ff88;border-radius:4px;font-size:12px;"
            "font-weight:bold;padding:6px 10px;}"
            "QPushButton#btn_synthetic_order:hover{background:#00ff88;color:#000;}"
            "QPushButton#btn_synthetic_order:disabled{background:#111;color:#444;border-color:#333;}")
        self.btn_synthetic_order.clicked.connect(self._on_synthetic_order)
        br.addWidget(self.btn_synthetic_order)

        # 증거금 조회 버튼
        self.btn_check_margin = QPushButton("💰 증거금 조회")
        self.btn_check_margin.setObjectName("btn_check_margin")
        self.btn_check_margin.setStyleSheet(
            "QPushButton#btn_check_margin{background:#1a1a0e;color:#ffd700;"
            "border:1px solid #ffd700;border-radius:4px;font-size:12px;"
            "font-weight:bold;padding:6px 10px;}"
            "QPushButton#btn_check_margin:hover{background:#ffd700;color:#000;}"
            "QPushButton#btn_check_margin:disabled{background:#111;color:#444;border-color:#333;}")
        self.btn_check_margin.clicked.connect(self._on_check_margin)
        br.addWidget(self.btn_check_margin)
        v.addLayout(br)

        self.synthetic_panel = SyntheticStatusPanel()
        v.addWidget(self.synthetic_panel, 1)
        return w

    # ── 손익 분석 결과 패널 ────────────────────────────────────
    def _build_result_panel(self) -> QGroupBox:
        from PyQt5.QtGui import QFont as _QFont
        gb = QGroupBox("📈 손익 분석 결과")
        v  = QVBoxLayout(gb); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        kpi_row = QHBoxLayout(); kpi_row.setSpacing(8); self._kpi_widgets = {}
        _KPI = [("max_profit","최대 이익","#00ff88"),("max_loss","최대 손실","#ff4444"),
                ("breakeven1","손익분기①","#ffd700"),("breakeven2","손익분기②","#ffd700"),
                ("cost","순 비용","#90caf9"),("rr","R:R","#ff8844")]
        for key, label, col in _KPI:
            box = QWidget(); bv = QVBoxLayout(box); bv.setContentsMargins(6,4,6,4)
            box.setStyleSheet("border:1px solid #2a2a4a;border-radius:5px;background:#0a0a1e;")
            lk = QLabel(label); lk.setStyleSheet(f"color:{col};font-size:10px;font-weight:bold;border:none;")
            lv = QLabel("―"); lv.setFont(_QFont("Arial",13,_QFont.Bold))
            lv.setStyleSheet(f"color:{col};border:none;"); lv.setAlignment(Qt.AlignCenter)
            bv.addWidget(lk); bv.addWidget(lv); self._kpi_widgets[key]=lv; kpi_row.addWidget(box)
        v.addLayout(kpi_row)

        sg = QGridLayout(); sg.setSpacing(6); self._spread_labels = {}
        _SG = [("call_spread","콜 스프레드"),("put_spread","풋 스프레드"),
               ("buy_cost","매수 비용"),("max_gain","최대 이익"),
               ("credit","수취 크레딧"),("margin","예상 증거금")]
        for i,(key,label) in enumerate(_SG):
            lk = QLabel(label+":"); lk.setStyleSheet("color:#aaa;font-size:10px;border:none;")
            lv = QLabel("―"); lv.setStyleSheet("color:#ffd700;font-size:11px;font-weight:bold;border:none;")
            sg.addWidget(lk,i//2,(i%2)*2); sg.addWidget(lv,i//2,(i%2)*2+1)
            self._spread_labels[key]=lv
        v.addLayout(sg)

        v.addWidget(QLabel("행사가별 손익  (BEP 근처)"))
        self.tbl_scenario = QTableWidget(0, 6)
        self.tbl_scenario.setHorizontalHeaderLabels(
            ["기초자산 가격","총 PnL ($)","PnL (×100)","수익률 (%)","콜 레그","풋 레그"])
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

    # ── 손익 곡선 패널 (fallback) ─────────────────────────────
    def _build_spread_chart_panel(self) -> QGroupBox:
        gb = QGroupBox("📉 손익 곡선")
        v  = QVBoxLayout(gb); v.setContentsMargins(4, 6, 4, 4)
        self._spread_labels = getattr(self, "_spread_labels", {})
        if PG:
            self._pw_pnl = pg.PlotWidget()
            self._pw_pnl.showGrid(x=True, y=True, alpha=0.2)
            self._pw_pnl.setLabel('left', 'PnL ($)')
            self._pw_pnl.setLabel('bottom', '기초자산 가격')
            self._pw_pnl.addLine(y=0, pen=pg.mkPen('#444', width=1))
            self._curve_pnl = self._pw_pnl.plot(pen=pg.mkPen('#00ff88', width=2), name="PnL")
            self._curve_be  = self._pw_pnl.plot(pen=pg.mkPen('#ffd700', width=1, style=Qt.DashLine))
            v.addWidget(self._pw_pnl, 1)
        else:
            v.addWidget(QLabel("pip install pyqtgraph"))
        gb.setMinimumHeight(160)
        return gb

    # ── 전략 설명 팝업 ────────────────────────────────────────
    def _show_strat_desc(self):
        strat = self.combo_strat.currentText()
        desc  = STRATEGY_DESC.get(strat, "설명 정보가 없습니다.")
        dlg = QMessageBox(self)
        dlg.setWindowTitle("전략 설명")
        dlg.setText(desc)
        dlg.setStyleSheet(
            "QMessageBox{background:#0d0d22;color:#ccc;}"
            "QLabel{color:#ffd700;font-size:13px;min-width:480px;}"
            "QPushButton{background:#1a2a4a;color:#90caf9;border:1px solid #3a3a6a;"
            "border-radius:4px;padding:6px 18px;font-size:12px;}"
            "QPushButton:hover{background:#2a3a6a;}")
        dlg.exec_()

    # ── Optimizer 토글 ────────────────────────────────────────
    def _toggle_optimizer_panel(self):
        collapsed = (self._opt_wrapper.maximumHeight() == 0)
        anim = QPropertyAnimation(self._opt_wrapper, b"maximumHeight")
        anim.setDuration(220)
        anim.setStartValue(self._opt_wrapper.maximumHeight())
        anim.setEndValue(420 if collapsed else 0)
        anim.setEasingCurve(QEasingCurve.OutCubic if collapsed else QEasingCurve.InCubic)
        self._opt_anim = anim; anim.start()
        if hasattr(self, "_btn_opt_toggle"):
            self._btn_opt_toggle.setText(
                "🔍 Cost Optimiser  ▲" if collapsed else "🔍 Cost Optimiser  ▼")
