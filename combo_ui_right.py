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
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView,QTableWidgetItem,
    QSplitter, QSpinBox, QMessageBox,
)
from PyQt5.QtCore import Qt
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
    def _build_right_panel(self) -> QSplitter:
        self._right_vsplit = QSplitter(Qt.Vertical)
        self._right_vsplit.setHandleWidth(6)
        self._right_vsplit.setStyleSheet(SPLITTER_STYLE)
        self._right_vsplit.setChildrenCollapsible(False)

        self._right_vsplit.addWidget(self._build_strategy_input_panel())
        self._right_vsplit.addWidget(self._build_result_panel())
        self._right_vsplit.addWidget(self._build_spread_chart_panel())
        self._right_vsplit.setSizes([260, 300, 220])
        return self._right_vsplit

    # ──────────────────────────────────────────────────────────
    # 전략 설정 패널
    # ──────────────────────────────────────────────────────────
    def _build_strategy_input_panel(self) -> QGroupBox:
        gb = QGroupBox("📋 전략 설정")
        v  = QVBoxLayout(gb)
        v.setSpacing(5); v.setContentsMargins(8, 8, 8, 8)

        # 전략 유형 선택 행
        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("전략 유형:"))

        self.combo_strat = QComboBox()
        self.combo_strat.addItems(STRATEGIES)
        self.combo_strat.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;padding:3px;min-width:260px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;font-size:12px;}"
            "QComboBox::drop-down{border:none;}")
        self.combo_strat.currentIndexChanged.connect(self._on_strat_change)
        strat_row.addWidget(self.combo_strat)

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
        strat_row.addStretch()
        v.addLayout(strat_row)

        # 레그 설정 테이블
        leg_lbl = QLabel("레그 설정  (체인 클릭 → 자동 입력 / 직접 수정 가능)")
        leg_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        v.addWidget(leg_lbl)

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
        self.tbl_legs.setMaximumHeight(160)
        v.addWidget(self.tbl_legs)

        # 기초자산 입력 (커버드콜·프로텍티브풋)
        stock_row = QHBoxLayout(); stock_row.setSpacing(8)
        stock_row.addWidget(QLabel("주식 현재가:"))
        self.edit_stock_price = QLineEdit()
        self.edit_stock_price.setPlaceholderText("주식 가격 (커버드콜·프로텍티브풋)")
        self.edit_stock_price.setFixedHeight(26)
        self.edit_stock_price.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;")
        stock_row.addWidget(self.edit_stock_price)
        stock_row.addWidget(QLabel("주식 수량:"))
        self.spin_stock_qty = QSpinBox()
        self.spin_stock_qty.setRange(1, 100000)
        self.spin_stock_qty.setValue(100)
        self.spin_stock_qty.setSuffix(" 주")
        self.spin_stock_qty.setFixedHeight(26)
        stock_row.addWidget(self.spin_stock_qty)
        stock_row.addStretch()
        v.addLayout(stock_row)

        # 계산 / 초기화 버튼
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        btn_calc = QPushButton("📊 손익 계산")
        btn_calc.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:13px;"
            "font-weight:bold;padding:8px 16px;border-radius:4px;")
        btn_calc.clicked.connect(self._calc_pnl)
        btn_reset = QPushButton("🗑 초기화")
        btn_reset.setStyleSheet(
            "background:#5a1a1a;color:#ff6666;font-weight:bold;padding:8px 12px;")
        btn_reset.clicked.connect(self._reset_legs)
        btn_row.addWidget(btn_calc)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        v.addLayout(btn_row)

        gb.setMinimumHeight(180)
        return gb

    # ──────────────────────────────────────────────────────────
    # 손익 분석 결과 패널
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

        # 시나리오 테이블
        scenario_lbl = QLabel("행사가별 손익 시나리오")
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
    # 스프레드 계산 + 손익 차트 패널
    # ──────────────────────────────────────────────────────────
    def _build_spread_chart_panel(self) -> QGroupBox:
        gb = QGroupBox("📉 스프레드 계산 & 손익 곡선")
        v  = QVBoxLayout(gb)
        v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        spread_grid = QGridLayout(); spread_grid.setSpacing(8)
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
            lbl_k.setStyleSheet("color:#aaa;font-size:11px;border:none;")
            lbl_v = QLabel("―")
            lbl_v.setStyleSheet(
                "color:#ffd700;font-size:12px;font-weight:bold;border:none;")
            spread_grid.addWidget(lbl_k, i // 2, (i % 2) * 2)
            spread_grid.addWidget(lbl_v, i // 2, (i % 2) * 2 + 1)
            self._spread_labels[key] = lbl_v
        v.addLayout(spread_grid)

        if PG:
            pg.setConfigOption('background', '#06060e')
            pg.setConfigOption('foreground', '#ccc')
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
