"""
tab_options.py — 탭1 콜-풋 메인 위젯  v6.6  [S6]
════════════════════════════════════════════════════════════════
  Layout: QSplitter nested (_wrap() applied to ALL splitter children)
  [S6 Fix] _v_splitter itself is also wrapped before adding to _h_main
            → eliminates nested-splitter handle deactivation bug completely
  Panels moved to tab_options_panels.py (ctrl/tbl/bot builders)
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox, QRadioButton, QButtonGroup,
    QSplitter, QListWidget, QTextEdit, QGroupBox,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDateEdit, QSizePolicy, QScrollArea,
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

from call_put_tab.tab_options_chart    import ChartMixin
from call_put_tab.watch_cond_widget    import WatchCondMixin
from call_put_tab.watch_log_widget     import WatchLogMixin
from call_put_tab.watch_logic          import WatchLogicMixin
from call_put_tab.order_panel          import OrderPanelMixin
from call_put_tab.order_logic          import OrderLogicMixin
from call_put_tab.order_panel_util     import OrderUtilMixin
from call_put_tab.core_conn            import CoreConnMixin
from call_put_tab.core_fetch           import CoreFetchMixin
from call_put_tab.tab_options_settings import SettingsMixin
from call_put_tab.tab_options_panels   import PanelsMixin


def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


class CallPutGrid(
    ChartMixin,
    WatchCondMixin,
    WatchLogMixin,
    WatchLogicMixin,
    OrderPanelMixin,
    OrderUtilMixin,
    OrderLogicMixin,
    CoreConnMixin,
    CoreFetchMixin,
    SettingsMixin,
    PanelsMixin,
    QWidget,
):
    _MAX_STRIKES = 100

    def __init__(self, mw):
        super().__init__()
        self.mw = mw

        self.und_price = None
        self.und_prev  = None
        self.call_data: dict = {}
        self.put_data:  dict = {}
        self.call_strikes: list = []
        self.put_strikes:  list = []
        self._zone          = "ATM"
        self._n_strikes     = 10
        self._chart_strike  = None
        self._chart_side    = "C"
        self._alert_sound_path  = ""
        self._watch_rules:  list = []
        self._watch_prev:   dict = {}
        self._watch_log_file = str(SAVE_DIR / "watch_alerts.txt")
        self._open_orders_buf: list = []

        if PG:
            self._BUF           = 500
            self._prices:       list = []
            self._price_times:  list = []
            self._deltas:       list = []
            self._spreads:      list = []
            self._und_hist:     list = []
            self._candle_bars:  dict = {}
            self._candle_items: list = []

        self._expiry_list = build_expiry_list("SPX")

        self._und_timer = QTimer(self)
        self._und_timer.setInterval(5000)
        self._und_timer.timeout.connect(self._refresh_und)

        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(2000)
        self._watch_timer.timeout.connect(self._check_watch_rules)

        self._build()
        self._connect_signals()

    # ── Splitter style ────────────────────────────────────────
    def _spl_style(self) -> str:
        return (
            "QSplitter::handle:horizontal{"
            "background:#3a3a7a;border-left:1px solid #5a5aaa;"
            "border-right:1px solid #5a5aaa;width:5px;margin:2px 0;}"
            "QSplitter::handle:horizontal:hover{"
            "background:#5dade2;border-left:1px solid #00e676;"
            "border-right:1px solid #00e676;}"
            "QSplitter::handle:vertical{"
            "background:#3a3a7a;border-top:1px solid #5a5aaa;"
            "border-bottom:1px solid #5a5aaa;height:5px;margin:0 2px;}"
            "QSplitter::handle:vertical:hover{"
            "background:#5dade2;border-top:1px solid #00e676;"
            "border-bottom:1px solid #00e676;}"
        )

    def _spl(self, orient) -> QSplitter:
        s = QSplitter(orient)
        s.setHandleWidth(5)
        s.setStyleSheet(self._spl_style())
        s.setChildrenCollapsible(False)
        return s

    @staticmethod
    def _wrap(widget) -> QWidget:
        """Plain wrap: Ignored size policy so splitter handles move freely.
        Used for _v_splitter itself (no scroll needed at that level).
        """
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        w.setMinimumHeight(0)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(widget)
        return w

    @staticmethod
    def _wrap_scroll(widget, *, horizontal: bool = False) -> QScrollArea:
        """Scroll-wrap: panel shrinks cleanly without breaking internal widgets.
        Vertical scroll appears when panel is too small; horizontal optional.
        Use for panels whose contents must not overlap when squeezed.
        """
        sa = QScrollArea()
        sa.setWidget(widget)
        sa.setWidgetResizable(True)
        sa.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        sa.setMinimumHeight(0)
        sa.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QScrollBar:vertical{width:6px;background:#06060e;}"
            "QScrollBar::handle:vertical{background:#3a3a7a;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sa.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if horizontal else Qt.ScrollBarAlwaysOff)
        return sa

    # ── Main layout ───────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 2)
        root.setSpacing(3)

        self._h_main = self._spl(Qt.Horizontal)
        self._h_main.addWidget(self._build_watchlist_panel())

        # ctrl: horizontal splitter — vertical scroll would be odd; plain wrap
        ctrl_w = self._wrap(self._build_ctrl_panel())
        # tbl: tables have their own scroll; plain wrap avoids double-scroll
        tbl_w  = self._wrap(self._build_tbl_panel())
        # bot: chart+watch panel — scroll prevents widget overlap when squeezed
        bot_w  = self._wrap_scroll(self._build_bot_panel())

        self._v_splitter = self._spl(Qt.Vertical)
        self._v_splitter.addWidget(ctrl_w)
        self._v_splitter.addWidget(tbl_w)
        self._v_splitter.addWidget(bot_w)

        for i in range(3):
            self._v_splitter.setCollapsible(i, False)

        self._v_splitter.setSizes([55, 480, 285])
        self._v_splitter.setStretchFactor(0, 1)
        self._v_splitter.setStretchFactor(1, 1)
        self._v_splitter.setStretchFactor(2, 1)

        self._h_main.addWidget(self._wrap(self._v_splitter))
        self._h_main.setSizes([130, 1400])

        root.addWidget(self._h_main, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(44)
        self.log.setStyleSheet(
            "background:#03030a;color:#00e676;font-size:13px;"
            "border:1px solid #1a1a3a;font-family:Consolas,monospace;")
        root.addWidget(self.log)

    # ── Watchlist sidebar ─────────────────────────────────────
    def _build_watchlist_panel(self) -> QWidget:
        """관심종목(상단) + 기초자산(하단) 수직 QSplitter 컨테이너."""

        _gb_ss = (
            "QGroupBox{font-size:11px;color:#5dade2;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")

        # ── 상단: 관심종목 ────────────────────────────────────
        gb_watch = QGroupBox("관심종목")
        gb_watch.setStyleSheet(_gb_ss)
        v = QVBoxLayout(gb_watch)
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

        # ── 하단: 기초자산 패널 ───────────────────────────────
        gb_und = QGroupBox("기초자산")
        gb_und.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffd700;font-weight:bold;"
            "border:1px solid #2a2a4a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        vu = QVBoxLayout(gb_und)
        vu.setContentsMargins(4, 8, 4, 6); vu.setSpacing(4)

        # 종목명
        self._side_und_sym = QLabel("SPX")
        self._side_und_sym.setAlignment(Qt.AlignCenter)
        self._side_und_sym.setStyleSheet(
            "color:#5dade2;font-size:12px;font-weight:bold;border:none;")
        vu.addWidget(self._side_und_sym)

        # 현재가 (클릭 → 히스토리)
        self._side_und_price = QLabel("―")
        self._side_und_price.setAlignment(Qt.AlignCenter)
        self._side_und_price.setStyleSheet(
            "color:#ffd700;font-size:17px;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "background:#08080f;padding:2px 4px;")
        self._side_und_price.setCursor(Qt.PointingHandCursor)
        self._side_und_price.setToolTip("클릭 → 히스토리 조회")
        self._side_und_price.mousePressEvent = lambda e: self._on_und_label_clicked()
        vu.addWidget(self._side_und_price)

        # 등락
        self._side_und_chg = QLabel("― (―%)")
        self._side_und_chg.setAlignment(Qt.AlignCenter)
        self._side_und_chg.setStyleSheet("color:#aaa;font-size:10px;border:none;")
        vu.addWidget(self._side_und_chg)

        # 구분선
        from PyQt5.QtWidgets import QFrame
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        vu.addWidget(sep)

        # 만기
        self._side_und_exp = QLabel("만기: ―")
        self._side_und_exp.setAlignment(Qt.AlignCenter)
        self._side_und_exp.setStyleSheet("color:#90caf9;font-size:10px;border:none;")
        vu.addWidget(self._side_und_exp)

        # Zone 현황 표시
        self._side_und_zone = QLabel("Zone: ATM")
        self._side_und_zone.setAlignment(Qt.AlignCenter)
        self._side_und_zone.setStyleSheet("color:#ffd700;font-size:10px;border:none;")
        vu.addWidget(self._side_und_zone)

        vu.addStretch()

        # ── 저장 상태 라벨 (chain_saver 연동) ────────────────
        self._side_save_status = QLabel("⏸ 저장 대기")
        self._side_save_status.setAlignment(Qt.AlignCenter)
        self._side_save_status.setStyleSheet(
            "color:#555;font-size:10px;border:none;")
        vu.addWidget(self._side_save_status)

        # ── 수직 스플리터 조립 ────────────────────────────────
        spl = self._spl(Qt.Vertical)
        spl.addWidget(gb_watch)
        spl.addWidget(gb_und)
        spl.setSizes([300, 140])      # 관심종목 ~70% / 기초자산 ~30%
        spl.setCollapsible(0, False)
        spl.setCollapsible(1, False)

        # 폭 제한 컨테이너
        container = QWidget()
        container.setMinimumWidth(80)
        container.setMaximumWidth(220)
        cv = QVBoxLayout(container)
        cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(0)
        cv.addWidget(spl)
        return container