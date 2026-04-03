"""
tab_options.py — 탭1 콜-풋 메인 위젯  v6.5
════════════════════════════════════════════════════════════════
  CallPutGrid: 10개 Mixin 조립
  레이아웃: QSplitter 중첩 (SniperGrid 동일 패턴)

  root (QVBoxLayout)
  ├── _h_main  (수평 QSplitter)
  │   ├── 관심종목 사이드바  QGroupBox
  │   └── _v_splitter  (수직 QSplitter)
  │       ├── _ctrl_splitter  (수평 QSplitter) ← 컨트롤 블록 7개
  │       ├── _tbl_splitter   (수평 QSplitter) ← CALL | PUT | 빠른주문
  │       └── _bot_splitter   (수평 QSplitter) ← 차트 | 감시
  └── 로그 QTextEdit (하단 고정 44px)
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QRadioButton, QButtonGroup,
    QSplitter, QListWidget, QTextEdit, QGroupBox, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDateEdit,
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    REQ_UND, REQ_CALL, REQ_PUT,
    make_table, tbl_set, ts,
    build_expiry_list, SAVE_DIR,
)

from tab_options_chart    import ChartMixin
from watch_cond_widget    import WatchCondMixin
from watch_log_widget     import WatchLogMixin
from watch_logic          import WatchLogicMixin
from order_panel          import OrderPanelMixin
from order_logic          import OrderLogicMixin
from core_conn            import CoreConnMixin
from core_fetch           import CoreFetchMixin
from tab_options_settings import SettingsMixin


# ── 셀 아이템 헬퍼 (order_panel.py 등에서 from tab_options import _mk) ──
def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


# ══════════════════════════════════════════════════════════════
# CallPutGrid
# ══════════════════════════════════════════════════════════════
class CallPutGrid(
    ChartMixin,
    WatchCondMixin,
    WatchLogMixin,
    WatchLogicMixin,
    OrderPanelMixin,
    OrderLogicMixin,
    CoreConnMixin,
    CoreFetchMixin,
    SettingsMixin,
    QWidget,
):
    _MAX_STRIKES = 100

    def __init__(self, mw):
        super().__init__()
        self.mw = mw

        # ── 데이터 버퍼 ──────────────────────────────────────
        self.und_price = None
        self.und_prev  = None
        self.call_data: dict = {}
        self.put_data:  dict = {}
        self.call_strikes: list = []
        self.put_strikes:  list = []
        self._zone          = "ATM"
        self._n_strikes     = 20
        self._chart_strike  = None
        self._chart_side    = "C"
        self._alert_sound_path  = ""
        self._watch_rules:  list = []
        self._watch_prev:   dict = {}
        self._watch_log_file = str(SAVE_DIR / "watch_alerts.txt")
        self._open_orders_buf: list = []

        # ── pyqtgraph 버퍼 ───────────────────────────────────
        if PG:
            self._BUF           = 500
            self._prices:       list = []
            self._price_times:  list = []
            self._deltas:       list = []
            self._spreads:      list = []
            self._und_hist:     list = []
            self._candle_bars:  dict = {}
            self._candle_items: list = []

        # ── 만기 목록 ────────────────────────────────────────
        # 기본값 SPX; 종목 변경 시 _refresh_expiry_list() 호출로 갱신
        self._expiry_list = build_expiry_list("SPX")

        # ── 타이머 ───────────────────────────────────────────
        self._und_timer = QTimer(self)
        self._und_timer.setInterval(5000)
        self._und_timer.timeout.connect(self._refresh_und)

        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(2000)
        self._watch_timer.timeout.connect(self._check_watch_rules)

        # ── UI 조립 ──────────────────────────────────────────
        self._build()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────
    # 스플리터 공통 스타일
    # ─────────────────────────────────────────────────────────
    def _spl_style(self) -> str:
        return (
            "QSplitter::handle:horizontal{"
            "background:#3a3a7a;"
            "border-left:1px solid #5a5aaa;"
            "border-right:1px solid #5a5aaa;"
            "width:5px;margin:2px 0;}"
            "QSplitter::handle:horizontal:hover{"
            "background:#5dade2;"
            "border-left:1px solid #00e676;"
            "border-right:1px solid #00e676;}"
            "QSplitter::handle:vertical{"
            "background:#3a3a7a;"
            "border-top:1px solid #5a5aaa;"
            "border-bottom:1px solid #5a5aaa;"
            "height:5px;margin:0 2px;}"
            "QSplitter::handle:vertical:hover{"
            "background:#5dade2;"
            "border-top:1px solid #00e676;"
            "border-bottom:1px solid #00e676;}"
        )

    def _spl(self, orient) -> QSplitter:
        s = QSplitter(orient)
        s.setHandleWidth(5)
        s.setStyleSheet(self._spl_style())
        s.setChildrenCollapsible(False)
        return s

    # ─────────────────────────────────────────────────────────
    # 전체 레이아웃 조립
    # ─────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 2)
        root.setSpacing(3)

        # 최상위: 사이드바 | 본체
        self._h_main = self._spl(Qt.Horizontal)
        self._h_main.addWidget(self._build_watchlist_panel())

        # 본체: 컨트롤 / 테이블 / 차트+감시
        self._v_splitter = self._spl(Qt.Vertical)
        self._v_splitter.addWidget(self._build_ctrl_panel())
        self._v_splitter.addWidget(self._build_tbl_panel())
        self._v_splitter.addWidget(self._build_bot_panel())
        self._v_splitter.setSizes([60, 520, 240])

        self._h_main.addWidget(self._v_splitter)
        self._h_main.setSizes([130, 1400])

        root.addWidget(self._h_main, 1)

        # 하단 로그 (고정)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(44)
        self.log.setStyleSheet(
            "background:#03030a;color:#00e676;font-size:13px;"
            "border:1px solid #1a1a3a;font-family:Consolas,monospace;")
        root.addWidget(self.log)

    # ─────────────────────────────────────────────────────────
    # ① 관심종목 사이드바
    # ─────────────────────────────────────────────────────────
    def _build_watchlist_panel(self) -> QGroupBox:
        gb = QGroupBox("관심종목")
        gb.setMinimumWidth(80)
        gb.setMaximumWidth(220)
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#5dade2;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(4, 6, 4, 4); v.setSpacing(3)

        self.watchlist = QListWidget()
        self.watchlist.setStyleSheet(
            "QListWidget{background:#05050f;color:#ffd700;font-size:13px;"
            "border:1px solid #2a2a5a;border-radius:3px;}"
            "QListWidget::item:selected{background:#1c3a6a;color:#fff;}"
            "QListWidget::item:hover{background:#12122a;}")
        for sym in ["SPX","NDX","RUT","VIX","SPY","QQQ",
                    "AAPL","NVDA","TSLA","AMZN","META","MSFT"]:
            self.watchlist.addItem(sym)
        self.watchlist.itemClicked.connect(self._on_watch_single_click)
        self.watchlist.itemDoubleClicked.connect(self._on_watch_dbl)
        v.addWidget(self.watchlist, 1)

        btn_row = QHBoxLayout(); btn_row.setSpacing(3)
        for lbl, slot, bg, fg in [
            ("＋ 추가", self._w_add, "#1a3a1a", "#00ff88"),
            ("－ 삭제", self._w_del, "#3a1a1a", "#ff6666"),
        ]:
            b = QPushButton(lbl); b.setFixedHeight(24)
            b.setStyleSheet(
                f"background:{bg};color:{fg};font-size:11px;"
                "font-weight:bold;border-radius:3px;")
            b.clicked.connect(slot); btn_row.addWidget(b)
        v.addLayout(btn_row)
        return gb

    # ─────────────────────────────────────────────────────────
    # ② 컨트롤 바 — 수평 QSplitter (블록 7개, 드래그 조절)
    # ─────────────────────────────────────────────────────────
    def _build_ctrl_panel(self) -> QSplitter:
        self._ctrl_splitter = self._spl(Qt.Horizontal)
        self._ctrl_splitter.setMinimumHeight(44)

        _gb = (
            "QGroupBox{font-size:10px;color:#5dade2;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;top:0px;}")
        _btn = (
            "QPushButton{background:#1c1c3a;color:#dde0f0;"
            "border:1px solid #3a3a7a;border-radius:3px;"
            "padding:2px 7px;font-size:11px;}"
            "QPushButton:hover{background:#2a2a5a;}"
            "QPushButton:pressed{background:#0e0e2a;}")

        def _gb_widget(title):
            g = QGroupBox(title); g.setStyleSheet(_gb)
            h = QHBoxLayout(g)
            h.setContentsMargins(5, 10, 5, 2); h.setSpacing(4)
            return g, h

        # 블록1: IBKR 연결
        g1, h1 = _gb_widget("IBKR")
        self.btn_conn = QPushButton("🔌 연결"); self.btn_conn.setStyleSheet(_btn)
        self.btn_disc = QPushButton("⏏ 해제");  self.btn_disc.setStyleSheet(_btn)
        self.lbl_status = QLabel("● 미연결")
        self.lbl_status.setStyleSheet(
            "color:#ff5252;font-weight:bold;border:none;font-size:11px;")
        for w in (self.btn_conn, self.btn_disc, self.lbl_status): h1.addWidget(w)
        self._ctrl_splitter.addWidget(g1)

        # 블록2: 시세모드
        g2, h2 = _gb_widget("시세모드")
        self.radio_live  = QRadioButton("실시간")
        self.radio_delay = QRadioButton("지연")
        self.radio_live.setChecked(True)
        mdt_grp = QButtonGroup(self)
        for rb in (self.radio_live, self.radio_delay):
            rb.setStyleSheet("color:#ffd700;font-size:11px;")
            rb.toggled.connect(self._apply_mdt_manual)
            mdt_grp.addButton(rb); h2.addWidget(rb)
        self._ctrl_splitter.addWidget(g2)

        # 블록3: SPXW 0DTE
        g3, h3 = _gb_widget("SPXW 0DTE")
        self.combo_spxw = QComboBox(); self.combo_spxw.setFixedHeight(24)
        self.combo_spxw.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;"
            "border:1px solid #3a3a6a;font-size:11px;padding:1px 3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        self._build_spxw_combo()
        self.combo_spxw.currentIndexChanged.connect(self._on_spxw_select)
        h3.addWidget(self.combo_spxw)
        self._ctrl_splitter.addWidget(g3)

        # 블록4: 종목 / 만기
        g4, h4 = _gb_widget("종목 / 만기  📅")
        self.edit_sym = QLineEdit("SPX")
        self.edit_sym.setFixedWidth(66); self.edit_sym.setFixedHeight(24)
        self.edit_sym.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;"
            "font-size:12px;font-weight:bold;padding:2px;")
        # ✅ 종목 변경 시 만기 콤보 자동 갱신
        self.edit_sym.editingFinished.connect(self._refresh_expiry_list)
        self.combo_exp = QComboBox(); self.combo_exp.setFixedHeight(24)
        self.combo_exp.setMinimumWidth(92)
        self.combo_exp.setStyleSheet(
            "QComboBox{background:#12122a;color:#90caf9;"
            "border:1px solid #3a3a6a;font-size:11px;padding:1px 3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#90caf9;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        for label, code, tag in self._expiry_list:
            self.combo_exp.addItem(label)
        self.combo_exp.currentIndexChanged.connect(self._on_exp_change)
        self.edit_custom = QLineEdit()
        self.edit_custom.setPlaceholderText("YYYYMMDD")
        self.edit_custom.setFixedWidth(78); self.edit_custom.setFixedHeight(24)
        self.edit_custom.setVisible(False)
        self.edit_custom.setStyleSheet(
            "background:#0a0a18;color:#ffd700;"
            "border:1px solid #2e3060;font-size:11px;")
        self.date_edit = QDateEdit(); self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate()); self.date_edit.setFixedHeight(24)
        self.date_edit.setVisible(False)
        self.date_edit.setStyleSheet(
            "background:#0a0a18;color:#ffd700;"
            "border:1px solid #2e3060;font-size:11px;")
        self.date_edit.dateChanged.connect(self._on_date_edit_changed)
        self.btn_cal = QPushButton("📅"); self.btn_cal.setFixedSize(26, 24)
        self.btn_cal.setStyleSheet(_btn); self.btn_cal.setToolTip("날짜 선택")
        self.btn_cal.clicked.connect(self._open_calendar)
        for w in (self.edit_sym, self.combo_exp,
                  self.edit_custom, self.date_edit, self.btn_cal):
            h4.addWidget(w)
        self._ctrl_splitter.addWidget(g4)

        # 블록5: Zone
        g5, h5 = _gb_widget("Zone")
        self._zone_btns: dict = {}
        zone_grp = QButtonGroup(self)
        for z, col in [("ITM","#ff8800"),("ATM","#ffd700"),("OTM","#00e676")]:
            rb = QRadioButton(z)
            rb.setStyleSheet(f"color:{col};font-size:11px;")
            if z == "ATM": rb.setChecked(True)
            zone_grp.addButton(rb)
            rb.toggled.connect(
                lambda checked, b=rb: checked and self._on_zone_change(b))
            self._zone_btns[z] = rb; h5.addWidget(rb)
        self._ctrl_splitter.addWidget(g5)

        # 블록6: 행수 + 조회
        g6, h6 = _gb_widget("조회")
        h6.addWidget(QLabel("행:",
            styleSheet="color:#aaa;font-size:11px;border:none;"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, self._MAX_STRIKES); self.spin_n.setValue(20)
        self.spin_n.setFixedWidth(50); self.spin_n.setFixedHeight(24)
        self.spin_n.setStyleSheet(
            "background:#0a0a18;color:#ffd700;"
            "border:1px solid #2e3060;font-size:12px;")
        self.btn_fetch = QPushButton("🔍 조회"); self.btn_fetch.setFixedHeight(26)
        self.btn_fetch.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:12px;"
            "font-weight:bold;padding:2px 10px;border-radius:4px;")
        h6.addWidget(self.spin_n); h6.addWidget(self.btn_fetch)
        self._ctrl_splitter.addWidget(g6)

        # 블록7: 기초자산 현재가
        g7, h7 = _gb_widget("기초자산  (클릭→히스토리)")
        self.lbl_und = QLabel("―")
        self.lbl_und.setStyleSheet(
            "color:#ffd700;font-size:16px;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "padding:1px 8px;background:#08080f;")
        self.lbl_und.setCursor(Qt.PointingHandCursor)
        self.lbl_und.setToolTip("클릭 → 일봉/분봉 히스토리 조회")
        self.lbl_und.mousePressEvent = lambda e: self._on_und_label_clicked()
        self.lbl_chg = QLabel("")
        self.lbl_chg.setStyleSheet("color:#aaa;font-size:12px;border:none;")
        h7.addWidget(self.lbl_und); h7.addWidget(self.lbl_chg)
        self._ctrl_splitter.addWidget(g7)

        self._ctrl_splitter.setSizes([150, 110, 165, 275, 145, 160, 210])
        return self._ctrl_splitter

    # ─────────────────────────────────────────────────────────
    # ③ 테이블 행: CALL | PUT | 빠른주문
    # ─────────────────────────────────────────────────────────
    def _build_tbl_panel(self) -> QSplitter:
        self.tbl_call = make_table(
            ["행사가", "가격", "전일", "Delta", "Theta", "Gamma", "잔고"])
        self.tbl_call.setMinimumHeight(80)
        # ✅ 잔고 컬럼(6) 클릭 시 시각적 구분을 위해 배경색 강조
        self.tbl_call.horizontalHeader().sectionClicked.connect(
            lambda col: None)  # 헤더 클릭은 무시
        self.tbl_call.cellClicked.connect(
            lambda r, c: self._tbl_click(r, c, "C"))
        self.tbl_call.cellDoubleClicked.connect(
            lambda r, c: self._tbl_dbl(r, c, "C"))

        self.tbl_put = make_table(
            ["행사가", "가격", "전일", "Delta", "Theta", "Gamma", "잔고"])
        self.tbl_put.setMinimumHeight(80)
        self.tbl_put.cellClicked.connect(
            lambda r, c: self._tbl_click(r, c, "P"))
        self.tbl_put.cellDoubleClicked.connect(
            lambda r, c: self._tbl_dbl(r, c, "P"))

        self._tbl_splitter = self._spl(Qt.Horizontal)
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_call, "CALL", "#33aaff"))
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_put,  "PUT",  "#ff6666"))

        # ✅ 현재가 패널 + 잔고 패널을 수직으로 묶어 하나의 컨테이너로
        _ppc = QWidget()
        _ppc_v = QVBoxLayout(_ppc)
        _ppc_v.setContentsMargins(0, 0, 0, 0)
        _ppc_v.setSpacing(3)
        _ppc_v.addWidget(self._build_price_panel())
        _ppc_v.addWidget(self._build_position_panel())
        self._tbl_splitter.addWidget(_ppc)

        self._tbl_splitter.addWidget(self._build_quick_order_panel())
        self._tbl_splitter.setSizes([460, 460, 180, 220])
        return self._tbl_splitter

    # ─────────────────────────────────────────────────────────
    # ④ 하단 행: 차트 | 감시
    # ─────────────────────────────────────────────────────────
    def _build_bot_panel(self) -> QSplitter:
        self._bot_splitter = self._spl(Qt.Horizontal)
        self._bot_splitter.addWidget(self._build_chart_panel())
        self._bot_splitter.addWidget(self._build_watch_widget())
        self._bot_splitter.setSizes([820, 500])
        # settings 호환: _watch_splitter = _bot_splitter 참조
        self._watch_splitter = self._bot_splitter
        return self._bot_splitter

    # ─────────────────────────────────────────────────────────
    # ⑤ 현재가 패널 (PUT 우측)
    #    - 종목명 / 현재가 / 등락 / Bid·Ask 호가 표시
    #    - 호가 클릭 → 주문창 가격 자동 입력
    #    - 관심종목 클릭·기초자산 Tick 수신 시 자동 갱신
    # ─────────────────────────────────────────────────────────
    def _build_price_panel(self) -> QGroupBox:
        gb = QGroupBox("📌 현재가")
        gb.setMinimumWidth(120)
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffd700;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")

        v = QVBoxLayout(gb)
        v.setContentsMargins(5, 8, 5, 5)
        v.setSpacing(4)

        # 종목명
        self._pp_lbl_sym = QLabel("―")
        self._pp_lbl_sym.setAlignment(Qt.AlignCenter)
        self._pp_lbl_sym.setStyleSheet(
            "color:#5dade2;font-size:14px;font-weight:bold;border:none;")
        v.addWidget(self._pp_lbl_sym)

        # 현재가 (대형)
        self._pp_lbl_price = QLabel("―")
        self._pp_lbl_price.setAlignment(Qt.AlignCenter)
        self._pp_lbl_price.setStyleSheet(
            "color:#ffd700;font-size:22px;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "background:#08080f;padding:4px;")
        v.addWidget(self._pp_lbl_price)

        # 등락
        self._pp_lbl_chg = QLabel("― (―%)")
        self._pp_lbl_chg.setAlignment(Qt.AlignCenter)
        self._pp_lbl_chg.setStyleSheet(
            "color:#aaa;font-size:14px;border:none;")
        v.addWidget(self._pp_lbl_chg)

        # 구분선
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        v.addWidget(sep1)

        # Bid / Ask 호가 테이블
        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;"
            "gridline-color:#1a1a3a;font-size:13px;border:1px solid #2a2a5a;}"
            "QHeaderView::section{background:#0a0a1e;color:#5dade2;"
            "border:1px solid #1a1a3a;font-size:11px;padding:2px;}"
            "QTableWidget::item{padding:3px;}"
            "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}"
            "QTableWidget::item:hover{background:#12122a;cursor:pointer;}")

        self._pp_tbl_quote = QTableWidget(2, 2)
        self._pp_tbl_quote.setHorizontalHeaderLabels(["호가", "값"])
        self._pp_tbl_quote.setVerticalHeaderLabels(["Ask", "Bid"])
        self._pp_tbl_quote.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._pp_tbl_quote.verticalHeader().setVisible(True)
        self._pp_tbl_quote.verticalHeader().setDefaultSectionSize(32)
        self._pp_tbl_quote.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._pp_tbl_quote.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._pp_tbl_quote.setFixedHeight(90)
        self._pp_tbl_quote.setStyleSheet(_tbl_s)
        # 초기값
        self._pp_tbl_quote.setItem(0, 0, _mk("Ask", "#ff6666"))
        self._pp_tbl_quote.setItem(0, 1, _mk("―",   "#ff6666"))
        self._pp_tbl_quote.setItem(1, 0, _mk("Bid",  "#33aaff"))
        self._pp_tbl_quote.setItem(1, 1, _mk("―",   "#33aaff"))
        # 호가 클릭 → 주문창 입력
        self._pp_tbl_quote.cellClicked.connect(self._on_pp_quote_click)
        v.addWidget(self._pp_tbl_quote)

        # 힌트
        hint = QLabel("↑ 클릭 → 주문창 가격 입력")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#444;font-size:9px;border:none;")
        v.addWidget(hint)

        # 구분선
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        v.addWidget(sep2)

        # 스프레드 / 옵션 정보 행
        spread_row = QHBoxLayout()
        spread_row.addWidget(QLabel("스프레드:",
            styleSheet="color:#aaa;font-size:10px;border:none;"))
        self._pp_lbl_spread = QLabel("―")
        self._pp_lbl_spread.setStyleSheet(
            "color:#ffd700;font-size:13px;border:none;font-weight:bold;")
        spread_row.addWidget(self._pp_lbl_spread)
        spread_row.addStretch()
        v.addLayout(spread_row)

        # 옵션 모드 정보 (행사가 / C·P / Delta)
        self._pp_lbl_opt_info = QLabel("")
        self._pp_lbl_opt_info.setAlignment(Qt.AlignCenter)
        self._pp_lbl_opt_info.setStyleSheet(
            "color:#90caf9;font-size:11px;border:none;")
        v.addWidget(self._pp_lbl_opt_info)

        v.addStretch()

        # 갱신 시각
        self._pp_lbl_time = QLabel("―")
        self._pp_lbl_time.setAlignment(Qt.AlignCenter)
        self._pp_lbl_time.setStyleSheet(
            "color:#333;font-size:9px;border:none;")
        v.addWidget(self._pp_lbl_time)

        # 내부 상태
        self._pp_bid  = None
        self._pp_ask  = None
        self._pp_mode  = "und"   # "und" = 기초자산, "opt" = 옵션
        self._pp_opt_side   = ""
        self._pp_opt_strike = ""
        self._pp_opt_bid  = None
        self._pp_opt_ask  = None

        return gb

    def _update_price_panel(self):
        """기초자산 Tick 수신 시 현재가 패널 갱신 (und 모드)."""
        from datetime import datetime
        if not hasattr(self, '_pp_lbl_price'): return

        # und 모드가 아니면 기초자산 데이터로 덮어쓰지 않음
        if getattr(self, '_pp_mode', 'und') != 'und': return

        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "―"
        price = getattr(self, 'und_price', None)
        prev  = getattr(self, 'und_prev',  None)

        self._pp_lbl_sym.setText(sym)
        if price:
            self._pp_lbl_price.setText(f"{price:,.2f}")
            if prev and prev > 0:
                chg = price - prev; pct = chg / prev * 100
                sign = "+" if chg >= 0 else ""
                col  = "#00e676" if chg >= 0 else "#ff5252"
                self._pp_lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
                self._pp_lbl_chg.setStyleSheet(
                    f"color:{col};font-size:14px;border:none;")
            else:
                self._pp_lbl_chg.setText("― (―%)")
        else:
            self._pp_lbl_price.setText("―")

        ask = self._pp_ask; bid = self._pp_bid
        self._pp_tbl_quote.setItem(0, 1, _mk(f"{ask:.2f}" if ask else "―", "#ff6666"))
        self._pp_tbl_quote.setItem(1, 1, _mk(f"{bid:.2f}" if bid else "―", "#33aaff"))
        if ask and bid:
            self._pp_lbl_spread.setText(f"{ask - bid:.2f}")
        else:
            self._pp_lbl_spread.setText("―")
        self._pp_lbl_opt_info.setText("")
        self._pp_lbl_time.setText(datetime.now().strftime("갱신 %H:%M:%S"))

    def _update_price_panel_opt(self, side, strike, bid, ask, delta=None):
        """옵션 체인 행사가 클릭 시 현재가 패널을 옵션 모드로 갱신."""
        from datetime import datetime
        if not hasattr(self, '_pp_lbl_price'): return

        self._pp_mode       = "opt"
        self._pp_opt_side   = side
        self._pp_opt_strike = strike
        self._pp_opt_bid    = bid
        self._pp_opt_ask    = ask

        label = "CALL" if side == "C" else "PUT"
        col   = "#33aaff" if side == "C" else "#ff6666"
        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""

        self._pp_lbl_sym.setText(f"{sym}  {label}")
        self._pp_lbl_sym.setStyleSheet(
            f"color:{col};font-size:14px;font-weight:bold;border:none;")

        # 현재가 = Mid
        if bid and ask:
            mid = (bid + ask) / 2
            self._pp_lbl_price.setText(f"{mid:.2f}")
            self._pp_lbl_spread.setText(f"{ask - bid:.2f}")
        elif ask:
            self._pp_lbl_price.setText(f"{ask:.2f}")
            self._pp_lbl_spread.setText("―")
        else:
            self._pp_lbl_price.setText("―")
            self._pp_lbl_spread.setText("―")

        self._pp_lbl_chg.setText(f"행사가  {strike}")
        self._pp_lbl_chg.setStyleSheet(
            f"color:{col};font-size:14px;border:none;font-weight:bold;")

        self._pp_tbl_quote.setItem(0, 1, _mk(f"{ask:.2f}" if ask else "―", "#ff6666"))
        self._pp_tbl_quote.setItem(1, 1, _mk(f"{bid:.2f}" if bid else "―", "#33aaff"))

        delta_str = f"Δ {delta:+.4f}" if delta is not None else ""
        self._pp_lbl_opt_info.setText(delta_str)
        self._pp_lbl_time.setText(datetime.now().strftime("갱신 %H:%M:%S"))

    def _pp_switch_to_und(self):
        """현재가 패널을 기초자산 모드로 복귀."""
        self._pp_mode = "und"
        self._pp_lbl_sym.setStyleSheet(
            "color:#5dade2;font-size:14px;font-weight:bold;border:none;")
        self._pp_lbl_chg.setStyleSheet(
            "color:#aaa;font-size:14px;border:none;")
        self._pp_lbl_opt_info.setText("")
        self._update_price_panel()

    # ─────────────────────────────────────────────────────────
    # ⑥ 잔고 패널 (현재가 패널 하단 고정)
    #    - IBKR 보유 포지션 목록 표시
    #    - 행 클릭 → 빠른주문 매도 자동 입력
    # ─────────────────────────────────────────────────────────
    def _build_position_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 잔고")
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffa500;font-weight:bold;"
            "border:1px solid #3a2a1a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(4, 8, 4, 4); v.setSpacing(3)

        # 조회 버튼
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 조회")
        btn_refresh.setFixedHeight(22)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffa500;font-size:11px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_refresh.clicked.connect(self._refresh_positions)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        v.addLayout(btn_row)

        # 포지션 테이블
        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;"
            "gridline-color:#2a1a0a;font-size:12px;border:1px solid #3a2a1a;}"
            "QHeaderView::section{background:#0a0805;color:#ffa500;"
            "border:1px solid #2a1a0a;font-size:11px;padding:2px;}"
            "QTableWidget::item{padding:2px;}"
            "QTableWidget::item:selected{background:#3a2a0a;color:#ffd700;}"
            "QTableWidget::item:hover{background:#1a1005;cursor:pointer;}")
        self.tbl_positions = QTableWidget(0, 4)
        self.tbl_positions.setHorizontalHeaderLabels(["C/P", "행사가", "수량", "평균가"])
        self.tbl_positions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_positions.verticalHeader().setVisible(False)
        self.tbl_positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_positions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_positions.setStyleSheet(_tbl_s)
        # 행 클릭 → 매도 주문창 자동 입력
        self.tbl_positions.cellClicked.connect(self._on_position_row_click)
        v.addWidget(self.tbl_positions)

        # 힌트
        hint = QLabel("↑ 클릭 → 매도 주문창")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#444;font-size:9px;border:none;")
        v.addWidget(hint)

        return gb

    def _on_position_row_click(self, row: int, col: int):
        """잔고 테이블 행 클릭 → 빠른주문 매도 자동 입력 + 매도 패널 표시."""
        tbl = self.tbl_positions
        cp_item    = tbl.item(row, 0)
        strike_item= tbl.item(row, 1)
        qty_item   = tbl.item(row, 2)
        price_item = tbl.item(row, 3)
        if not cp_item or not strike_item: return

        side   = "C" if "C" in cp_item.text() else "P"
        strike = strike_item.text().strip()
        try:    qty = abs(int(qty_item.text())) if qty_item else 1
        except: qty = 1
        try:    price = float(price_item.text()) if price_item else None
        except: price = None

        if hasattr(self, '_show_pos_sell_panel'):
            self._show_pos_sell_panel(side, strike, qty=qty, price=price)

    def _on_pp_quote_click(self, row: int, col: int):
        """호가 테이블 클릭 → 빠른주문 가격란에 자동 입력."""
        if not hasattr(self, 'qord_price'): return
        mode = getattr(self, '_pp_mode', 'und')
        if mode == 'opt':
            val = self._pp_opt_ask if row == 0 else self._pp_opt_bid
        else:
            val = self._pp_ask if row == 0 else self._pp_bid
        if val:
            self.qord_price.setText(f"{val:.2f}")
            src = "Ask" if row == 0 else "Bid"
            if hasattr(self, 'lbl_qord_src'):
                self.lbl_qord_src.setText(f"← 현재가 {src} 클릭")
            if hasattr(self, '_log'):
                self._log(f"주문가격 자동입력: {src} {val:.2f}")