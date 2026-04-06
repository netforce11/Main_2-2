"""
tab_combo_strategy.py — 탭4: 복합 전략  v1.1
════════════════════════════════════════════════════════════════
변경:
  v1.1 — ValueError 수정 (_on_chain_click price format)
         로그 폰트 크기 13px로 증가
════════════════════════════════════════════════════════════════
레이아웃 (QSplitter 기반):

┌──────────────────────────────────────────────────────────────┐
│  수평 스플리터 (최상위)                                       │
│  ├── 좌측 패널 (수직 스플리터)                                │
│  │   ├── 옵션 체인 (콜-풋 탭 동기화)                         │
│  │   └── 관심종목 + 현재가 조회                              │
│  └── 우측 패널 (수직 스플리터)                                │
│      ├── 전략 입력 (레그 설정)                               │
│      ├── 손익 분석 테이블                                     │
│      └── 스프레드 계산 결과                                   │
└──────────────────────────────────────────────────────────────┘

지원 전략:
  - 커버드 콜 (주식 매수 + 콜 매도)
  - 프로텍티브 풋 (주식 매수 + 풋 매수)
  - 콜 스프레드 (콜 매수 + 콜 매도)
  - 풋 스프레드 (풋 매수 + 풋 매도)
  - 스트래들 (콜 매수 + 풋 매수, 동일 행사가)
  - 스트랭글 (콜 매수 + 풋 매수, 다른 행사가)
  - 아이언 콘도르 (4레그)
════════════════════════════════════════════════════════════════
"""

from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QTextEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QSpinBox, QCheckBox,
    QRadioButton, QButtonGroup, QInputDialog,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, GridTab, make_table, tbl_set, ts,
    REQ_UND, REQ_CALL, REQ_PUT,
    SYMBOL_CFG, DEFAULT_CFG,
    build_expiry_list, make_opt_contract, make_und_contract,
    save_json, load_json, SAVE_DIR,
    auto_mdt,
)

# ── 스플리터 핸들 스타일 (공통) ────────────────────────────────
_SH = (
    "QSplitter::handle:horizontal{background:#5a5a9a;"
    "border-left:1px solid #00aaff;border-right:1px solid #00aaff;margin:4px 0;}"
    "QSplitter::handle:horizontal:hover{background:#5dade2;"
    "border-left:1px solid #00e676;border-right:1px solid #00e676;}"
    "QSplitter::handle:vertical{background:#5a5a9a;"
    "border-top:1px solid #00aaff;border-bottom:1px solid #00aaff;margin:0 4px;}"
    "QSplitter::handle:vertical:hover{background:#5dade2;"
    "border-top:1px solid #00e676;border-bottom:1px solid #00e676;}"
)

# ── 전략 정의 ──────────────────────────────────────────────────
STRATEGIES = [
    "커버드 콜 (주식매수 + 콜매도)",
    "프로텍티브 풋 (주식매수 + 풋매수)",
    "콜 스프레드 (콜매수 + 콜매도)",
    "풋 스프레드 (풋매수 + 풋매도)",
    "콜 백 스프레드 (콜매도 ATM + 콜매수 OTM×2)",
    "풋 백 스프레드 (풋매도 ATM + 풋매수 OTM×2)",
    "스트래들 (콜매수 + 풋매수 / ATM)",
    "스트랭글 (콜매수 + 풋매수 / OTM)",
    "아이언 콘도르 (4레그)",
]

# ── 레그 컬러 ──────────────────────────────────────────────────
_LEG_COLORS = ["#ffd700", "#33aaff", "#ff6666", "#88ff44"]


def _mk(text, color=None):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    if color:
        it.setForeground(QBrush(QColor(color)))
    return it


# ══════════════════════════════════════════════════════════════
# Tab 4: 복합 전략
# ══════════════════════════════════════════════════════════════
class ComboStrategyGrid(QWidget):
    """복합 전략 손익 분석 탭."""

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self._expiry_list = build_expiry_list()
        self._und_price   = None   # 현재 기초자산 가격
        self._chain_call  = {}     # strike → last price (콜)
        self._chain_put   = {}     # strike → last price (풋)
        self._call_strikes = []
        self._put_strikes  = []
        self._build()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────
    # 빌드
    # ─────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # ── 최상위 수평 스플리터 ──────────────────────────────
        self._main_hsplit = QSplitter(Qt.Horizontal)
        self._main_hsplit.setHandleWidth(6)
        self._main_hsplit.setStyleSheet(_SH)
        self._main_hsplit.setChildrenCollapsible(False)

        # ────────────────────────────────────────────────────
        # 좌측: 수직 스플리터 (옵션 체인 | 관심종목)
        # ────────────────────────────────────────────────────
        self._left_vsplit = QSplitter(Qt.Vertical)
        self._left_vsplit.setHandleWidth(6)
        self._left_vsplit.setStyleSheet(_SH)
        self._left_vsplit.setChildrenCollapsible(False)

        # ── 옵션 체인 패널 ────────────────────────────────────
        gb_chain = QGroupBox("📊 옵션 체인  (콜-풋 탭 3초 동기화)")
        v_chain  = QVBoxLayout(gb_chain)
        v_chain.setSpacing(2); v_chain.setContentsMargins(4,4,4,4)

        # 헤더 정보
        chain_hdr = QHBoxLayout()
        self.lbl_chain_sym   = QLabel("종목: ―  |  현재가: ―")
        self.lbl_chain_sym.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        btn_sync = QPushButton("↺ 즉시 동기화")
        btn_sync.setFixedHeight(22)
        btn_sync.clicked.connect(self._sync_chain)
        chain_hdr.addWidget(self.lbl_chain_sym)
        chain_hdr.addStretch()
        chain_hdr.addWidget(btn_sync)
        v_chain.addLayout(chain_hdr)

        # 체인 내부 수평 분할 (콜 | 풋)
        chain_inner = QSplitter(Qt.Horizontal)
        chain_inner.setHandleWidth(4)
        chain_inner.setStyleSheet(_SH)
        chain_inner.setChildrenCollapsible(False)

        # CALL 체인
        call_w = QWidget(); call_v = QVBoxLayout(call_w)
        call_v.setContentsMargins(0,0,0,0); call_v.setSpacing(1)
        lbl_c = QLabel("▲ CALL")
        lbl_c.setStyleSheet("color:#33aaff;font-weight:bold;border:none;")
        lbl_c.setAlignment(Qt.AlignCenter)
        self.tbl_chain_call = QTableWidget(0, 3)
        self.tbl_chain_call.setHorizontalHeaderLabels(["행사가","현재가","IV"])
        self.tbl_chain_call.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_chain_call.verticalHeader().setVisible(False)
        self.tbl_chain_call.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_chain_call.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_chain_call.setAlternatingRowColors(True)
        self.tbl_chain_call.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-weight:bold;}")
        self.tbl_chain_call.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "C"))
        call_v.addWidget(lbl_c)
        call_v.addWidget(self.tbl_chain_call)
        chain_inner.addWidget(call_w)

        # PUT 체인
        put_w = QWidget(); put_v = QVBoxLayout(put_w)
        put_v.setContentsMargins(0,0,0,0); put_v.setSpacing(1)
        lbl_p = QLabel("▼ PUT")
        lbl_p.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        lbl_p.setAlignment(Qt.AlignCenter)
        self.tbl_chain_put = QTableWidget(0, 3)
        self.tbl_chain_put.setHorizontalHeaderLabels(["행사가","현재가","IV"])
        self.tbl_chain_put.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_chain_put.verticalHeader().setVisible(False)
        self.tbl_chain_put.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_chain_put.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_chain_put.setAlternatingRowColors(True)
        self.tbl_chain_put.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#ff9999;"
            "border:1px solid #1a1a3a;font-weight:bold;}")
        self.tbl_chain_put.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "P"))
        put_v.addWidget(lbl_p)
        put_v.addWidget(self.tbl_chain_put)
        chain_inner.addWidget(put_w)
        chain_inner.setSizes([300, 300])

        v_chain.addWidget(chain_inner, 1)
        gb_chain.setMinimumWidth(300)
        self._left_vsplit.addWidget(gb_chain)

        # ── 관심종목 + 현재가 조회 ─────────────────────────────
        gb_watch = QGroupBox("관심종목")
        v_watch  = QVBoxLayout(gb_watch)
        v_watch.setSpacing(3); v_watch.setContentsMargins(4,4,4,4)

        # 종목 입력 + 조회
        sym_row = QHBoxLayout()
        self.edit_sym_combo = QLineEdit("SPX")
        self.edit_sym_combo.setFixedHeight(24)
        self.edit_sym_combo.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-weight:bold;")
        btn_req = QPushButton("▶ 현재가 조회")
        btn_req.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-weight:bold;padding:3px 8px;")
        btn_req.clicked.connect(self._req_sym_price)
        self.lbl_sym_price = QLabel("현재가: ―")
        self.lbl_sym_price.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_sym_price.setStyleSheet("color:#ffd700;border:none;")
        sym_row.addWidget(QLabel("종목:"))
        sym_row.addWidget(self.edit_sym_combo)
        sym_row.addWidget(btn_req)
        v_watch.addLayout(sym_row)
        v_watch.addWidget(self.lbl_sym_price)

        self.watchlist_combo = QListWidget()
        self.watchlist_combo.addItems([
            "SPX","SPXW","NDX","QQQ","SPY","AAPL","TSLA","NVDA"])
        self.watchlist_combo.itemClicked.connect(self._on_watchlist_click)
        v_watch.addWidget(self.watchlist_combo, 1)

        wa = QHBoxLayout()
        ba = QPushButton("추가"); bd = QPushButton("삭제")
        ba.setFixedHeight(22); bd.setFixedHeight(22)
        ba.clicked.connect(self._w_add); bd.clicked.connect(self._w_del)
        wa.addWidget(ba); wa.addWidget(bd)
        v_watch.addLayout(wa)
        gb_watch.setMinimumHeight(120)
        self._left_vsplit.addWidget(gb_watch)

        self._left_vsplit.setSizes([500, 200])
        self._main_hsplit.addWidget(self._left_vsplit)

        # ────────────────────────────────────────────────────
        # 우측: 수직 스플리터 (전략입력 | 분석결과 | 차트)
        # ────────────────────────────────────────────────────
        self._right_vsplit = QSplitter(Qt.Vertical)
        self._right_vsplit.setHandleWidth(6)
        self._right_vsplit.setStyleSheet(_SH)
        self._right_vsplit.setChildrenCollapsible(False)

        # ── 전략 선택 + 레그 입력 ─────────────────────────────
        gb_input = QGroupBox("📋 전략 설정")
        v_input  = QVBoxLayout(gb_input)
        v_input.setSpacing(5); v_input.setContentsMargins(8,8,8,8)

        # 전략 선택
        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("전략 유형:"))
        self.combo_strat = QComboBox()
        self.combo_strat.addItems(STRATEGIES)
        self.combo_strat.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:12px;padding:3px;min-width:250px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;font-size:12px;}"
            "QComboBox::drop-down{border:none;}")
        self.combo_strat.currentIndexChanged.connect(self._on_strat_change)
        strat_row.addWidget(self.combo_strat)
        strat_row.addStretch()
        v_input.addLayout(strat_row)

        # ── 레그 입력 테이블 ──────────────────────────────────
        leg_lbl = QLabel("레그 설정  (체인 클릭 → 자동 입력 / 직접 수정 가능)")
        leg_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        v_input.addWidget(leg_lbl)

        self.tbl_legs = QTableWidget(0, 7)
        self.tbl_legs.setHorizontalHeaderLabels([
            "레그", "방향", "C/P", "행사가", "프리미엄($)", "수량", "만기"])
        self.tbl_legs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_legs.verticalHeader().setVisible(False)
        self.tbl_legs.setAlternatingRowColors(True)
        self.tbl_legs.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-weight:bold;}")
        self.tbl_legs.setMaximumHeight(160)
        v_input.addWidget(self.tbl_legs)

        # 기초자산 입력 (커버드 콜 등)
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
        v_input.addLayout(stock_row)

        # 계산 버튼
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
        v_input.addLayout(btn_row)

        gb_input.setMinimumHeight(180)
        self._right_vsplit.addWidget(gb_input)

        # ── 손익 분석 결과 테이블 ─────────────────────────────
        gb_result = QGroupBox("📈 손익 분석 결과")
        v_result  = QVBoxLayout(gb_result)
        v_result.setSpacing(4); v_result.setContentsMargins(6,6,6,6)

        # 핵심 지표 (빅 넘버)
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
            bv  = QVBoxLayout(box); bv.setContentsMargins(6,4,6,4)
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
        v_result.addLayout(kpi_row)

        # 시나리오 분석 테이블 (행사가별 PnL)
        scenario_lbl = QLabel("행사가별 손익 시나리오")
        scenario_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        v_result.addWidget(scenario_lbl)

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
        v_result.addWidget(self.tbl_scenario, 1)

        gb_result.setMinimumHeight(200)
        self._right_vsplit.addWidget(gb_result)

        # ── 스프레드 계산 + 손익 차트 ─────────────────────────
        gb_spread = QGroupBox("📉 스프레드 계산 & 손익 곡선")
        v_spread  = QVBoxLayout(gb_spread)
        v_spread.setSpacing(4); v_spread.setContentsMargins(6,6,6,6)

        # 스프레드 계산 결과
        spread_grid = QGridLayout()
        spread_grid.setSpacing(8)
        self._spread_labels = {}
        for i, (key, label) in enumerate([
            ("call_spread",  "콜 스프레드 (너비)"),
            ("put_spread",   "풋 스프레드 (너비)"),
            ("buy_cost",     "매수 비용 (총)"),
            ("max_gain",     "최대 이익 (총)"),
            ("credit",       "수취 크레딧"),
            ("margin",       "예상 증거금"),
        ]):
            lbl_k = QLabel(label + ":")
            lbl_k.setStyleSheet("color:#aaa;font-size:11px;border:none;")
            lbl_v = QLabel("―")
            lbl_v.setStyleSheet(
                "color:#ffd700;font-size:12px;font-weight:bold;border:none;")
            spread_grid.addWidget(lbl_k, i // 2, (i % 2) * 2)
            spread_grid.addWidget(lbl_v, i // 2, (i % 2) * 2 + 1)
            self._spread_labels[key] = lbl_v
        v_spread.addLayout(spread_grid)

        # 손익 곡선 차트
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
                pen=pg.mkPen('#ffd700', width=1,
                             style=Qt.DashLine), name="손익분기")
            v_spread.addWidget(self._pw_pnl, 1)
        else:
            v_spread.addWidget(QLabel("pip install pyqtgraph"))

        gb_spread.setMinimumHeight(160)
        self._right_vsplit.addWidget(gb_spread)

        # ── Cost Optimizer ────────────────────────────────────
        self._right_vsplit.addWidget(self._build_optimizer_panel())

        self._right_vsplit.setSizes([260, 300, 200, 220])
        self._main_hsplit.addWidget(self._right_vsplit)

        self._main_hsplit.setSizes([380, 900])
        root.addWidget(self._main_hsplit, 1)

        # ── 로그 (하단 고정 2줄) — 폰트 13px ─────────────────
        gb_log = QGroupBox("로그"); v_log = QVBoxLayout(gb_log)
        v_log.setContentsMargins(2,2,2,2)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True)
        fm = self.log_box.fontMetrics()
        self.log_box.setFixedHeight(fm.height() * 2 + 10)
        self.log_box.setStyleSheet(
            "background:#05050f;color:#00e676;font-size:13px;border:none;")
        v_log.addWidget(self.log_box)
        root.addWidget(gb_log)

        # 초기 전략 레그 세팅
        self._on_strat_change(0)

        # 체인 동기화 타이머 (3초)
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(3000)
        self._sync_timer.timeout.connect(self._auto_sync_chain)
        self._sync_timer.start()

    # ─────────────────────────────────────────────────────────
    # 시그널 연결
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        bridge.tick_price.connect(self._on_tick_price)

    def _log(self, msg: str):
        self.log_box.append(f"[{ts()}] {msg}")
        lines = self.log_box.toPlainText().split("\n")
        if len(lines) > 200:
            self.log_box.setPlainText("\n".join(lines[-150:]))

    # ─────────────────────────────────────────────────────────
    # 관심종목
    # ─────────────────────────────────────────────────────────
    def _on_watchlist_click(self, item):
        sym = item.text().strip()
        self.edit_sym_combo.setText(sym)
        self._req_sym_price()

    def _w_add(self):
        t, ok = QInputDialog.getText(self, "추가", "심볼:")
        if ok and t.strip():
            self.watchlist_combo.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watchlist_combo.currentRow()
        if r >= 0:
            self.watchlist_combo.takeItem(r)

    def _req_sym_price(self):
        """관심종목 클릭 → 현재가 조회 후 레그 입력 필드 자동 채우기."""
        sym = self.edit_sym_combo.text().strip().upper()
        if not sym:
            return
        # 콜-풋 탭에서 현재가 가져오기
        cp = self.mw.tab_callput
        if cp and cp.und_price and cp.edit_sym.text().strip().upper() == sym:
            price = cp.und_price
            self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
            self.edit_stock_price.setText(f"{price:.2f}")
            self._und_price = price
            self._log(f"현재가 수신 (콜-풋탭): {sym} = {price:,.2f}")
        else:
            self.lbl_sym_price.setText("현재가: 조회 중…")
            self._log(f"콜-풋 탭에서 {sym} 먼저 조회하세요.")

    # ─────────────────────────────────────────────────────────
    # 옵션 체인 동기화 (콜-풋 탭 → 이 탭)
    # ─────────────────────────────────────────────────────────
    def _auto_sync_chain(self):
        """3초마다 콜-풋 탭 체인 데이터 자동 동기화."""
        cp = self.mw.tab_callput
        if not cp or (not cp.call_strikes and not cp.put_strikes):
            return
        self._sync_chain_from_cp(cp, silent=True)

    def _sync_chain(self):
        """수동 동기화 버튼."""
        cp = self.mw.tab_callput
        if not cp:
            return
        if not cp.call_strikes and not cp.put_strikes:
            QMessageBox.information(self, "안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_chain_from_cp(cp, silent=False)

    def _sync_chain_from_cp(self, cp, silent=False):
        """콜-풋 탭 → 체인 테이블 동기화."""
        from core import REQ_CALL, REQ_PUT
        sym       = cp.edit_sym.text().strip().upper()
        und_price = cp.und_price

        # 콜-풋 탭 만기 동기화
        self._synced_expiry = ""
        try:
            idx = cp.combo_exp.currentIndex()
            if 0 <= idx < len(cp._expiry_list):
                self._synced_expiry = cp._expiry_list[idx][0]
        except Exception:
            pass

        header = f"종목: {sym}  |  현재가: {und_price:,.2f}" if und_price else f"종목: {sym}"
        if self._synced_expiry:
            header += f"  |  만기: {self._synced_expiry}"
        self.lbl_chain_sym.setText(header)

        if und_price:
            self._und_price = und_price
            self.lbl_sym_price.setText(f"현재가: {und_price:,.2f}")
            if not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{und_price:.2f}")

        # CALL 체인 갱신
        self._call_strikes = list(cp.call_strikes)
        self._chain_call   = {}
        self.tbl_chain_call.setRowCount(0)
        for i, st in enumerate(cp.call_strikes):
            rid = REQ_CALL + i
            lp  = cp.call_data.get(rid, {}).get("last")
            self._chain_call[st] = lp
            r = self.tbl_chain_call.rowCount()
            self.tbl_chain_call.insertRow(r)
            self.tbl_chain_call.setItem(r, 0, _mk(f"{int(st)}", "#ffd700"))
            self.tbl_chain_call.setItem(r, 1, _mk(f"{lp:.2f}" if lp else "―", "#33aaff"))
            self.tbl_chain_call.setItem(r, 2, _mk("―"))

        # PUT 체인 갱신
        self._put_strikes = list(cp.put_strikes)
        self._chain_put   = {}
        self.tbl_chain_put.setRowCount(0)
        for i, st in enumerate(cp.put_strikes):
            rid = REQ_PUT + i
            lp  = cp.put_data.get(rid, {}).get("last")
            self._chain_put[st] = lp
            r = self.tbl_chain_put.rowCount()
            self.tbl_chain_put.insertRow(r)
            self.tbl_chain_put.setItem(r, 0, _mk(f"{int(st)}", "#ffd700"))
            self.tbl_chain_put.setItem(r, 1, _mk(f"{lp:.2f}" if lp else "―", "#ff6666"))
            self.tbl_chain_put.setItem(r, 2, _mk("―"))

        if not silent:
            self._log(f"체인 동기화: {sym}  C{len(cp.call_strikes)} / P{len(cp.put_strikes)}"
                      + (f"  만기={self._synced_expiry}" if self._synced_expiry else ""))

    # ─────────────────────────────────────────────────────────
    # 체인 클릭 → 레그 자동 입력
    # ─────────────────────────────────────────────────────────
    def _on_chain_click(self, row: int, col: int, side: str):
        """체인 테이블 클릭 → 현재 활성 레그(편집 대상)에 자동 입력."""
        tbl = self.tbl_chain_call if side == "C" else self.tbl_chain_put
        strikes = self._call_strikes if side == "C" else self._put_strikes
        prices  = self._chain_call   if side == "C" else self._chain_put

        if row >= len(strikes):
            return
        strike = strikes[row]
        price  = prices.get(strike)

        # 레그 테이블 중 현재 선택된 행 → 또는 첫 번째 빈 행에 입력
        leg_row = self.tbl_legs.currentRow()
        if leg_row < 0:
            leg_row = 0
        if leg_row >= self.tbl_legs.rowCount():
            return

        # C/P 칼럼(2), 행사가(3), 프리미엄(4), 만기(6) 자동 입력
        self.tbl_legs.item(leg_row, 2).setText(side)
        self.tbl_legs.item(leg_row, 3).setText(str(int(strike)))
        if price:
            self.tbl_legs.item(leg_row, 4).setText(f"{price:.2f}")
        expiry = getattr(self, '_synced_expiry', "")
        if expiry and self.tbl_legs.item(leg_row, 6):
            self.tbl_legs.item(leg_row, 6).setText(expiry)

        # ✅ Fix: price가 None일 때 ValueError 방지
        price_str = f"{price:.2f}" if price else "0.00"
        self._log(f"레그{leg_row+1} 자동 입력: {side} {int(strike)}  ${price_str}")

    # ─────────────────────────────────────────────────────────
    # 틱 수신 (현재가 업데이트)
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        if rid == REQ_UND and tt in (4, 68, 75) and price > 0:
            self._und_price = price
            QTimer.singleShot(0, lambda: self.lbl_sym_price.setText(
                f"현재가: {price:,.2f}"))

    # ─────────────────────────────────────────────────────────
    # 전략 변경 → 레그 테이블 재구성
    # ─────────────────────────────────────────────────────────
    def _on_strat_change(self, idx: int):
        """전략 선택 변경 시 레그 테이블 초기화."""
        strat = self.combo_strat.currentText()
        legs  = self._get_leg_template(strat)
        self._rebuild_legs(legs)

        # 주식 관련 전략이면 주식 입력 활성화
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
        expiry_default = self._expiry_list[0][0] if self._expiry_list else "오늘"
        base = {"qty": "1", "expiry": expiry_default}

        if "커버드 콜" in strat:
            return [
                {**base, "leg":"레그1", "dir":"SELL", "cp":"C", "strike":"", "prem":""},
            ]
        elif "프로텍티브 풋" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY",  "cp":"P", "strike":"", "prem":""},
            ]
        elif "콜 스프레드" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY",  "cp":"C", "strike":"", "prem":""},
                {**base, "leg":"레그2", "dir":"SELL", "cp":"C", "strike":"", "prem":""},
            ]
        elif "풋 스프레드" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY",  "cp":"P", "strike":"", "prem":""},
                {**base, "leg":"레그2", "dir":"SELL", "cp":"P", "strike":"", "prem":""},
            ]
        elif "콜 백 스프레드" in strat:
            return [
                {**base, "leg":"레그1(매도)", "dir":"SELL", "cp":"C", "strike":"", "prem":"", "qty":"1"},
                {**base, "leg":"레그2(매수)", "dir":"BUY",  "cp":"C", "strike":"", "prem":"", "qty":"2"},
            ]
        elif "풋 백 스프레드" in strat:
            return [
                {**base, "leg":"레그1(매도)", "dir":"SELL", "cp":"P", "strike":"", "prem":"", "qty":"1"},
                {**base, "leg":"레그2(매수)", "dir":"BUY",  "cp":"P", "strike":"", "prem":"", "qty":"2"},
            ]
        elif "스트래들" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY", "cp":"C", "strike":"", "prem":""},
                {**base, "leg":"레그2", "dir":"BUY", "cp":"P", "strike":"", "prem":""},
            ]
        elif "스트랭글" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY", "cp":"C", "strike":"", "prem":""},
                {**base, "leg":"레그2", "dir":"BUY", "cp":"P", "strike":"", "prem":""},
            ]
        elif "아이언 콘도르" in strat:
            return [
                {**base, "leg":"레그1", "dir":"BUY",  "cp":"P", "strike":"", "prem":""},
                {**base, "leg":"레그2", "dir":"SELL", "cp":"P", "strike":"", "prem":""},
                {**base, "leg":"레그3", "dir":"SELL", "cp":"C", "strike":"", "prem":""},
                {**base, "leg":"레그4", "dir":"BUY",  "cp":"C", "strike":"", "prem":""},
            ]
        return []

    def _rebuild_legs(self, legs: list):
        """레그 테이블 재구성."""
        self.tbl_legs.setRowCount(0)
        for i, leg in enumerate(legs):
            r = self.tbl_legs.rowCount()
            self.tbl_legs.insertRow(r)
            col = _LEG_COLORS[i % len(_LEG_COLORS)]
            # 레그명 (읽기전용)
            it0 = QTableWidgetItem(leg["leg"])
            it0.setTextAlignment(Qt.AlignCenter)
            it0.setForeground(QBrush(QColor(col)))
            it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
            self.tbl_legs.setItem(r, 0, it0)
            # 방향 (읽기전용, 색상)
            dir_col = "#00ff88" if leg["dir"] == "BUY" else "#ff6666"
            it1 = QTableWidgetItem(leg["dir"])
            it1.setTextAlignment(Qt.AlignCenter)
            it1.setForeground(QBrush(QColor(dir_col)))
            it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
            self.tbl_legs.setItem(r, 1, it1)
            # 나머지 편집 가능
            for c, key in enumerate(["cp", "strike", "prem", "qty", "expiry"], 2):
                it = QTableWidgetItem(str(leg.get(key, "")))
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl_legs.setItem(r, c, it)

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

    # ─────────────────────────────────────────────────────────
    # 손익 계산
    # ─────────────────────────────────────────────────────────
    def _read_legs(self) -> list:
        """레그 테이블에서 레그 데이터 읽기."""
        legs = []
        for r in range(self.tbl_legs.rowCount()):
            def cell(c):
                it = self.tbl_legs.item(r, c)
                return it.text().strip() if it else ""
            try:
                leg = {
                    "leg":    cell(0),
                    "dir":    cell(1),
                    "cp":     cell(2),
                    "strike": float(cell(3)) if cell(3) else None,
                    "prem":   float(cell(4)) if cell(4) else None,
                    "qty":    int(cell(5))   if cell(5) else 1,
                }
                legs.append(leg)
            except (ValueError, TypeError):
                pass
        return legs

    def _calc_pnl(self):
        """전략 손익 계산 및 시나리오 테이블 + 차트 업데이트."""
        strat = self.combo_strat.currentText()
        legs  = self._read_legs()

        if not legs:
            QMessageBox.warning(self, "입력 오류", "레그 정보를 입력하세요.")
            return

        # 주식 가격 (커버드콜 등)
        try:
            stock_price = float(self.edit_stock_price.text()) \
                if self.edit_stock_price.isEnabled() else None
            stock_qty = self.spin_stock_qty.value() \
                if self.edit_stock_price.isEnabled() else 0
        except ValueError:
            stock_price = None; stock_qty = 0

        # 현재가 기준 범위 설정
        ref_price = self._und_price or stock_price
        if ref_price is None:
            # 행사가 평균을 기준으로
            valid_strikes = [l["strike"] for l in legs if l["strike"]]
            ref_price = sum(valid_strikes) / len(valid_strikes) if valid_strikes else 100.0

        # 시나리오: ref_price ± 30% 범위
        lo = ref_price * 0.70
        hi = ref_price * 1.30
        step = (hi - lo) / 40
        prices = [lo + i * step for i in range(41)]

        scenarios = []
        for p in prices:
            pnl_call_legs = 0.0
            pnl_put_legs  = 0.0
            for leg in legs:
                if leg["strike"] is None or leg["prem"] is None:
                    continue
                k   = leg["strike"]
                pm  = leg["prem"]
                qty = leg["qty"]
                cp  = leg["cp"].upper()
                mul = 1 if leg["dir"] == "BUY" else -1

                if cp == "C":
                    intrinsic = max(0.0, p - k)
                    leg_pnl   = mul * (intrinsic - pm) * qty * 100
                    pnl_call_legs += leg_pnl
                else:
                    intrinsic = max(0.0, k - p)
                    leg_pnl   = mul * (intrinsic - pm) * qty * 100
                    pnl_put_legs += leg_pnl

            # 주식 컴포넌트
            stock_pnl = 0.0
            if stock_price and stock_qty:
                stock_pnl = (p - stock_price) * stock_qty

            total = pnl_call_legs + pnl_put_legs + stock_pnl
            cost_basis = sum(
                l["prem"] * l["qty"] * 100
                * (1 if l["dir"] == "BUY" else -1)
                for l in legs if l["prem"]
            )
            pct = (total / abs(cost_basis) * 100) if cost_basis else 0.0
            scenarios.append((p, total, total / 100, pct,
                               pnl_call_legs, pnl_put_legs))

        # ── 시나리오 테이블 갱신 ──────────────────────────────
        self.tbl_scenario.setRowCount(0)
        for p, tot, tot100, pct, c_leg, p_leg in scenarios:
            r = self.tbl_scenario.rowCount()
            self.tbl_scenario.insertRow(r)
            col = "#00ff88" if tot >= 0 else "#ff4444"
            self.tbl_scenario.setItem(r, 0, _mk(f"{p:,.2f}", "#ffd700"))
            self.tbl_scenario.setItem(r, 1, _mk(f"${tot:,.2f}", col))
            self.tbl_scenario.setItem(r, 2, _mk(f"${tot100:,.2f}", col))
            self.tbl_scenario.setItem(r, 3, _mk(f"{pct:.1f}%", col))
            self.tbl_scenario.setItem(r, 4, _mk(f"${c_leg:,.2f}",
                "#00ff88" if c_leg >= 0 else "#ff4444"))
            self.tbl_scenario.setItem(r, 5, _mk(f"${p_leg:,.2f}",
                "#00ff88" if p_leg >= 0 else "#ff4444"))

        # ── KPI 계산 ────────────────────────────────────────
        pnls = [s[1] for s in scenarios]
        max_profit = max(pnls)
        max_loss   = min(pnls)

        # 손익분기점 (부호 변경 지점)
        breakevens = []
        for i in range(len(scenarios) - 1):
            p1, t1 = scenarios[i][0], scenarios[i][1]
            p2, t2 = scenarios[i+1][0], scenarios[i+1][1]
            if t1 * t2 <= 0 and t1 != t2:
                be = p1 + (p2 - p1) * (-t1 / (t2 - t1))
                breakevens.append(be)

        # 순 비용 / 크레딧
        cost_basis = sum(
            l["prem"] * l["qty"] * 100 * (1 if l["dir"] == "BUY" else -1)
            for l in legs if l["prem"]
        )
        rr = abs(max_profit / max_loss) if max_loss != 0 else float('inf')

        self._kpi_widgets["max_profit"].setText(
            f"${max_profit:,.2f}" if max_profit < 999999 else "무제한")
        self._kpi_widgets["max_loss"].setText(
            f"${max_loss:,.2f}" if max_loss > -999999 else "무제한")
        self._kpi_widgets["breakeven1"].setText(
            f"{breakevens[0]:,.2f}" if len(breakevens) > 0 else "―")
        self._kpi_widgets["breakeven2"].setText(
            f"{breakevens[1]:,.2f}" if len(breakevens) > 1 else "―")
        self._kpi_widgets["cost"].setText(
            f"${abs(cost_basis):,.2f} {'수취' if cost_basis < 0 else '지불'}")
        self._kpi_widgets["rr"].setText(
            f"{rr:.2f}:1" if rr < 999 else "∞")

        # ── 스프레드 계산 ────────────────────────────────────
        call_legs = [l for l in legs if l.get("cp", "").upper() == "C" and l["strike"]]
        put_legs  = [l for l in legs if l.get("cp", "").upper() == "P" and l["strike"]]
        if call_legs:
            call_strikes = sorted(l["strike"] for l in call_legs)
            c_spread = call_strikes[-1] - call_strikes[0] if len(call_strikes) > 1 else 0
            self._spread_labels["call_spread"].setText(
                f"${c_spread:.2f}" if c_spread else "단일 레그")
        if put_legs:
            put_strikes = sorted(l["strike"] for l in put_legs)
            p_spread = put_strikes[-1] - put_strikes[0] if len(put_strikes) > 1 else 0
            self._spread_labels["put_spread"].setText(
                f"${p_spread:.2f}" if p_spread else "단일 레그")
        self._spread_labels["buy_cost"].setText(
            f"${abs(cost_basis):,.2f}")
        self._spread_labels["max_gain"].setText(
            f"${max_profit:,.2f}" if max_profit < 999999 else "무제한")
        credit = -cost_basis if cost_basis < 0 else 0
        self._spread_labels["credit"].setText(
            f"${credit:,.2f}" if credit > 0 else "―")
        # 증거금 추정: 스프레드 너비 × 수량 × 100 - 크레딧
        if call_legs and len(call_strikes) > 1:
            margin = c_spread * max(l["qty"] for l in call_legs) * 100 - credit
        elif put_legs and len(put_strikes) > 1:
            margin = p_spread * max(l["qty"] for l in put_legs) * 100 - credit
        else:
            margin = abs(cost_basis)
        self._spread_labels["margin"].setText(f"~${margin:,.2f}")

        # ── 손익 곡선 차트 ───────────────────────────────────
        if PG:
            xs = [s[0] for s in scenarios]
            ys = [s[1] for s in scenarios]
            self._curve_pnl.setData(xs, ys)
            # 손익분기 수직선
            if breakevens:
                self._curve_be.setData(
                    [breakevens[0], breakevens[0]],
                    [min(ys) * 1.1, max(ys) * 1.1])

        self._log(f"손익 계산 완료 — {strat}  "
                  f"최대이익=${max_profit:,.2f}  최대손실=${max_loss:,.2f}  "
                  f"손익분기={[f'{b:.2f}' for b in breakevens]}")

    # ─────────────────────────────────────────────────────────
    # Cost Optimizer
    # ─────────────────────────────────────────────────────────
    def _build_optimizer_panel(self) -> QGroupBox:
        """💰 Cost Optimizer 패널 빌드."""
        gb = QGroupBox("💰 Cost Optimizer  —  순 비용 이하 행사가 자동 탐색")
        gb.setStyleSheet(
            "QGroupBox{font-size:12px;color:#c084fc;font-weight:bold;"
            "border:1px solid #3a1a5a;border-radius:5px;"
            "margin-top:8px;padding-top:6px;background:#08080f;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(8, 10, 8, 8); v.setSpacing(6)

        _S_LBL  = "color:#aaa;font-size:12px;border:none;"
        _S_SPIN = ("background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
                   "font-size:13px;font-weight:bold;border-radius:3px;padding:2px;")
        _S_COMBO = ("QComboBox{background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
                    "font-size:12px;padding:2px 6px;border-radius:3px;}"
                    "QComboBox QAbstractItemView{background:#0c0c22;color:#ffd700;font-size:12px;}"
                    "QComboBox::drop-down{border:none;width:14px;}")
        _S_BTN  = ("QPushButton{background:#2a0a4a;color:#c084fc;font-size:12px;"
                   "font-weight:bold;border:1px solid #5a2a8a;border-radius:4px;padding:5px 14px;}"
                   "QPushButton:hover{background:#3a1a6a;}"
                   "QPushButton:pressed{background:#1a0a2a;}")

        # 입력 행
        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        ctrl.addWidget(QLabel("최대 순 비용 $", styleSheet=_S_LBL))
        self._opt_max_cost = QSpinBox()
        self._opt_max_cost.setRange(0, 99999); self._opt_max_cost.setValue(700)
        self._opt_max_cost.setSingleStep(50); self._opt_max_cost.setFixedHeight(28)
        self._opt_max_cost.setFixedWidth(90); self._opt_max_cost.setStyleSheet(_S_SPIN)
        ctrl.addWidget(self._opt_max_cost)

        ctrl.addWidget(QLabel("전략", styleSheet=_S_LBL))
        self._opt_strat_combo = QComboBox()
        self._opt_strat_combo.addItems([
            "콜 백 스프레드 (1×2)", "풋 백 스프레드 (1×2)",
            "콜 백 스프레드 (1×1.5)", "풋 백 스프레드 (1×1.5)",
            "콜 스프레드", "풋 스프레드",
        ])
        self._opt_strat_combo.setFixedHeight(28)
        self._opt_strat_combo.setStyleSheet(_S_COMBO)
        ctrl.addWidget(self._opt_strat_combo, 1)

        btn_run = QPushButton("🔍 탐색")
        btn_run.setFixedHeight(28); btn_run.setStyleSheet(_S_BTN)
        btn_run.clicked.connect(self._run_optimizer)
        ctrl.addWidget(btn_run)
        v.addLayout(ctrl)

        # 결과 테이블
        self._opt_tbl = QTableWidget(0, 6)
        self._opt_tbl.setHorizontalHeaderLabels([
            "매도 행사가", "매수 행사가", "순 비용 $", "BEP ①", "BEP ②", "전략 요약"])
        self._opt_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._opt_tbl.verticalHeader().setVisible(False)
        self._opt_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._opt_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._opt_tbl.setAlternatingRowColors(True)
        self._opt_tbl.setMinimumHeight(120)
        self._opt_tbl.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0d0d20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#c084fc;"
            "border:1px solid #1a1a3a;font-weight:bold;font-size:11px;}"
            "QTableWidget::item:selected{background:#2a1a4a;color:#fff;}")
        self._opt_tbl.cellClicked.connect(self._on_optimizer_row_click)
        v.addWidget(self._opt_tbl, 1)

        # 선택 행 요약 레이블
        self._opt_summary = QLabel("← 행 클릭 시 레그 테이블에 자동 입력")
        self._opt_summary.setStyleSheet(
            "color:#888;font-size:11px;border:none;font-style:italic;")
        v.addWidget(self._opt_summary)
        return gb

    def _run_optimizer(self):
        """체인 데이터에서 순 비용 조건 만족하는 행사가 조합 탐색."""
        max_cost = self._opt_max_cost.value()
        strat    = self._opt_strat_combo.currentText()
        mult     = 100  # 옵션 승수

        is_call   = "콜" in strat
        is_spread = "스프레드" in strat and "백" not in strat
        ratio_b   = 2.0 if "1×2" in strat else (1.5 if "1×1.5" in strat else 1.0)

        strikes = self._call_strikes if is_call else self._put_strikes
        prices  = self._chain_call   if is_call else self._chain_put

        if not strikes:
            self._log("⚠ 체인 데이터 없음 — 먼저 콜-풋 탭에서 조회하세요.")
            return

        results = []
        n = len(strikes)

        for i in range(n):
            for j in range(i + 1, n):
                ka, kb = strikes[i], strikes[j]
                pa = prices.get(ka) or 0.0
                pb = prices.get(kb) or 0.0
                if pa == 0.0 and pb == 0.0:
                    continue

                if is_spread:
                    # 일반 스프레드: 낮은 매수 + 높은 매도 (콜) / 높은 매수 + 낮은 매도 (풋)
                    net = (pa - pb) * mult  # 콜: pa>pb → 비용, 풋: pb>pa → 비용
                else:
                    # 백 스프레드: ka 매도 1계약 + kb 매수 ratio_b계약
                    net = (pb * ratio_b - pa) * mult

                if net < 0:
                    net = 0.0  # 크레딧 전략은 비용 0으로 처리

                if net > max_cost:
                    continue

                # BEP 계산
                if is_spread:
                    if is_call:
                        bep1 = ka + (pa - pb)
                        bep2 = None
                    else:
                        bep1 = ka - (pa - pb)
                        bep2 = None
                else:
                    net_per = net / mult
                    if is_call:
                        bep1 = ka + pa - pb * ratio_b  # 하단 BEP (손실 구간 상단)
                        bep2 = kb + net_per            # 상단 BEP (이익 구간 진입)
                    else:
                        bep1 = kb - net_per            # 하단 BEP
                        bep2 = ka - pa + pb * ratio_b  # 상단 BEP

                results.append({
                    "sell": int(ka), "buy": int(kb),
                    "net": net, "bep1": bep1, "bep2": bep2,
                    "ratio": ratio_b,
                })

        # 순 비용 오름차순 정렬, 최대 30개
        results.sort(key=lambda x: x["net"])
        results = results[:30]

        self._opt_tbl.setRowCount(0)
        for res in results:
            r = self._opt_tbl.rowCount()
            self._opt_tbl.insertRow(r)
            cost_col = "#00e676" if res["net"] == 0 else "#ffd700"
            bep2_txt = f"{res['bep2']:.1f}" if res["bep2"] else "―"
            summary  = (f"{res['sell']}{'C' if is_call else 'P'} 매도 × 1  +  "
                        f"{res['buy']}{'C' if is_call else 'P'} 매수 × {res['ratio']}")
            self._opt_tbl.setItem(r, 0, _mk(str(res["sell"]), "#ff6666"))
            self._opt_tbl.setItem(r, 1, _mk(str(res["buy"]),  "#33aaff"))
            self._opt_tbl.setItem(r, 2, _mk(f"${res['net']:,.0f}", cost_col))
            self._opt_tbl.setItem(r, 3, _mk(f"{res['bep1']:.1f}", "#c084fc"))
            self._opt_tbl.setItem(r, 4, _mk(bep2_txt, "#c084fc"))
            self._opt_tbl.setItem(r, 5, _mk(summary, "#aaa"))

        self._log(f"Cost Optimizer: {strat}  최대비용=${max_cost}  "
                  f"조합 {len(results)}개 발견")
        if not results:
            self._opt_summary.setText("⚠ 조건 만족 조합 없음 — 최대 비용을 높이거나 전략을 바꿔보세요.")
        else:
            best = results[0]
            bep_txt = (f"BEP {best['bep1']:.1f} / {best['bep2']:.1f}"
                       if best["bep2"] else f"BEP {best['bep1']:.1f}")
            self._opt_summary.setText(
                f"✅ 최저비용: {best['sell']}{'C' if is_call else 'P'} 매도 + "
                f"{best['buy']}{'C' if is_call else 'P'} 매수  순비용 ${best['net']:,.0f}  {bep_txt}")

    def _on_optimizer_row_click(self, row: int, col: int):
        """결과 행 클릭 → 레그 테이블에 자동 입력 후 손익 계산."""
        sell_item = self._opt_tbl.item(row, 0)
        buy_item  = self._opt_tbl.item(row, 1)
        if not sell_item or not buy_item:
            return

        strat    = self._opt_strat_combo.currentText()
        is_call  = "콜" in strat
        cp       = "C" if is_call else "P"
        ratio_b  = 2.0 if "1×2" in strat else (1.5 if "1×1.5" in strat else 1.0)
        sell_k   = int(sell_item.text())
        buy_k    = int(buy_item.text())
        prices   = self._chain_call if is_call else self._chain_put
        sell_p   = prices.get(sell_k) or 0.0
        buy_p    = prices.get(buy_k)  or 0.0
        expiry   = getattr(self, '_synced_expiry', "")

        is_back  = "백" in strat
        if is_back:
            template = [
                {"leg": "레그1(매도)", "dir": "SELL", "cp": cp,
                 "strike": str(sell_k), "prem": f"{sell_p:.2f}", "qty": "1",    "expiry": expiry},
                {"leg": "레그2(매수)", "dir": "BUY",  "cp": cp,
                 "strike": str(buy_k),  "prem": f"{buy_p:.2f}",  "qty": str(int(ratio_b)) if ratio_b == int(ratio_b) else str(ratio_b), "expiry": expiry},
            ]
            # 백 스프레드 전략 콤보 동기화
            target = "콜 백 스프레드" if is_call else "풋 백 스프레드"
        else:
            template = [
                {"leg": "레그1", "dir": "BUY",  "cp": cp,
                 "strike": str(sell_k), "prem": f"{sell_p:.2f}", "qty": "1", "expiry": expiry},
                {"leg": "레그2", "dir": "SELL", "cp": cp,
                 "strike": str(buy_k),  "prem": f"{buy_p:.2f}",  "qty": "1", "expiry": expiry},
            ]
            target = "콜 스프레드" if is_call else "풋 스프레드"

        # 전략 콤보 동기화
        for i in range(self.combo_strat.count()):
            if target in self.combo_strat.itemText(i):
                self.combo_strat.blockSignals(True)
                self.combo_strat.setCurrentIndex(i)
                self.combo_strat.blockSignals(False)
                break

        self._rebuild_legs(template)
        self.edit_stock_price.setEnabled(False)
        self.spin_stock_qty.setEnabled(False)
        self._log(f"Optimizer 선택: {sell_k}{cp} 매도 + {buy_k}{cp} 매수 ×{ratio_b}")
        # 자동으로 손익 계산 실행
        QTimer.singleShot(50, self._calc_pnl)

    # ─────────────────────────────────────────────────────────
    # 설정 저장/복원
    # ─────────────────────────────────────────────────────────
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
                if s.get("main_hsplit"):  self._main_hsplit.setSizes(s["main_hsplit"])
                if s.get("left_vsplit"):  self._left_vsplit.setSizes(s["left_vsplit"])
                if s.get("right_vsplit"): self._right_vsplit.setSizes(s["right_vsplit"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)