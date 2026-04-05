"""
chart_panel_tabs.py — Intraday (분봉) & Tick tab UI builders  [NEW — S6]
Changes:
  - Date picker, time input, vline controls moved INTO each tab's ctrl_row
    (right side of 분봉/틱 control bar) — eliminates separate date_row
  - Calendar date click → immediate fetch (no extra button needed)
  - Chart widget ContentsMargins = 0 throughout
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QComboBox, QPushButton, QSpinBox,
    QDateEdit, QLineEdit, QScrollArea, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QRegExp

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from spxw_core import MiniChartCanvas

from chart_utils import (
    CB_STYLE        as _CB_STYLE,
    SB_STYLE        as _SB_STYLE,
    BTN_STYLE       as _BTN_STYLE,
    QUERY_BTN_STYLE as _QUERY_BTN_STYLE,
)


def _lbl(text):
    return QLabel(text, styleSheet="color:#aaa;font-size:11px;border:none;")


def _vsep():
    """Thin vertical separator for control rows."""
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setStyleSheet("color:#2a2a5a;max-width:1px;")
    return sep


# ──────────────────────────────────────────────────────────────
# Tab 3: Intraday — MiniChartCanvas (matplotlib) IBKR-only
# [S6] Date/time/vline controls merged into single ctrl_row (right side)
#      Calendar dateChanged → immediate fetch (no "날짜 조회" button)
# ──────────────────────────────────────────────────────────────
def _build_intraday_tab(host):
    intra_w = QWidget()
    intra_v = QVBoxLayout(intra_w)
    intra_v.setContentsMargins(0, 0, 0, 0)
    intra_v.setSpacing(2)

    # ── Single unified control row ────────────────────────────
    i_ctrl = QHBoxLayout()
    i_ctrl.setSpacing(5)

    # Left: bar type / count / day shortcuts / ext / mode / fetch
    host.combo_intra_tf = QComboBox()
    host.combo_intra_tf.addItems(["1분", "5분", "15분", "30분", "60분"])
    host.combo_intra_tf.setCurrentIndex(0)
    host.combo_intra_tf.setFixedWidth(54)
    host.combo_intra_tf.setFixedHeight(22)
    host.combo_intra_tf.setStyleSheet(_CB_STYLE)

    host.spin_intra_bars = QSpinBox()
    host.spin_intra_bars.setRange(10, 9999)
    host.spin_intra_bars.setValue(300)
    host.spin_intra_bars.setFixedWidth(60)
    host.spin_intra_bars.setFixedHeight(22)
    host.spin_intra_bars.setStyleSheet(_SB_STYLE)

    btn_1d = QPushButton("1일"); btn_1d.setFixedHeight(22); btn_1d.setFixedWidth(30)
    btn_2d = QPushButton("2일"); btn_2d.setFixedHeight(22); btn_2d.setFixedWidth(30)
    btn_3d = QPushButton("3일"); btn_3d.setFixedHeight(22); btn_3d.setFixedWidth(30)
    for b in (btn_1d, btn_2d, btn_3d):
        b.setStyleSheet(_BTN_STYLE)
    btn_1d.clicked.connect(lambda: (host.spin_intra_bars.setValue(300),  host._fetch_intraday()))
    btn_2d.clicked.connect(lambda: (host.spin_intra_bars.setValue(600),  host._fetch_intraday()))
    btn_3d.clicked.connect(lambda: (host.spin_intra_bars.setValue(900),  host._fetch_intraday()))

    host.chk_intra_ext = QCheckBox("시간외")
    host.chk_intra_ext.setStyleSheet("color:#90caf9;font-size:11px;")
    host.chk_intra_ext.setChecked(False)

    host.combo_intra_chart_mode = QComboBox()
    host.combo_intra_chart_mode.addItems(["캔들", "라인"])
    host.combo_intra_chart_mode.setFixedWidth(46)
    host.combo_intra_chart_mode.setFixedHeight(22)
    host.combo_intra_chart_mode.setStyleSheet(_CB_STYLE)
    host.combo_intra_chart_mode.currentIndexChanged.connect(
        lambda: host._redraw_intraday_cache())

    btn_intra = QPushButton("▶")
    btn_intra.setFixedHeight(22); btn_intra.setFixedWidth(28)
    btn_intra.setStyleSheet(_QUERY_BTN_STYLE)
    btn_intra.clicked.connect(host._fetch_intraday)

    # Right: date picker (immediate fetch on change) | time vline controls
    # [S6] Calendar click fires _on_intra_date_fetch immediately
    host.intra_date_edit = QDateEdit()
    host.intra_date_edit.setCalendarPopup(True)
    host.intra_date_edit.setDate(QDate.currentDate())
    host.intra_date_edit.setDisplayFormat("MM-dd")
    host.intra_date_edit.setFixedWidth(72)
    host.intra_date_edit.setFixedHeight(22)
    host.intra_date_edit.setStyleSheet(
        "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;"
        "font-size:11px;padding:1px 2px;")
    # dateChanged fires when user picks from calendar popup → immediate fetch
    host.intra_date_edit.dateChanged.connect(host._on_intra_date_fetch)

    host.intra_time_input = QLineEdit()
    host.intra_time_input.setPlaceholderText("HH:MM")
    host.intra_time_input.setFixedWidth(52)
    host.intra_time_input.setFixedHeight(22)
    host.intra_time_input.setMaxLength(5)
    host.intra_time_input.setStyleSheet(
        "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;"
        "font-size:11px;padding:1px 2px;")
    host.intra_time_input.setValidator(
        QRegExpValidator(QRegExp(r"\d{0,2}:?\d{0,2}"), host.intra_time_input))
    host.intra_time_input.textChanged.connect(host._on_intra_time_changed)
    host.intra_time_input.returnPressed.connect(host._on_add_vline)

    btn_vline = QPushButton("선+")
    btn_vline.setFixedHeight(22); btn_vline.setFixedWidth(34)
    btn_vline.setStyleSheet(_BTN_STYLE)
    btn_vline.clicked.connect(host._on_add_vline)

    btn_vline_clear = QPushButton("전삭")
    btn_vline_clear.setFixedHeight(22); btn_vline_clear.setFixedWidth(34)
    btn_vline_clear.setStyleSheet(
        "QPushButton{background:#3a1a1a;color:#ff6666;font-size:11px;"
        "border:1px solid #6a2a2a;border-radius:3px;}"
        "QPushButton:hover{background:#5a2a2a;}")
    btn_vline_clear.clicked.connect(host._on_clear_all_vlines)

    # KST toggle checkbox
    host.chk_kst = QCheckBox("한국시간")
    host.chk_kst.setStyleSheet("color:#80deea;font-size:11px;")
    host.chk_kst.setChecked(False)
    host.chk_kst.stateChanged.connect(lambda: host._redraw_intraday_cache())

    # Volume threshold input
    host.spin_vol_threshold = QSpinBox()
    host.spin_vol_threshold.setRange(0, 99999)
    host.spin_vol_threshold.setValue(100)
    host.spin_vol_threshold.setSuffix("만주")
    host.spin_vol_threshold.setFixedWidth(82)
    host.spin_vol_threshold.setFixedHeight(22)
    host.spin_vol_threshold.setStyleSheet(_SB_STYLE)
    host.spin_vol_threshold.setToolTip("이 수량 이상의 거래량 봉을 굵게 강조 표시 (단위: 만주)")
    host.spin_vol_threshold.valueChanged.connect(lambda: host._redraw_intraday_cache())

    host.lbl_intra_status = QLabel("▶ 조회")
    host.lbl_intra_status.setStyleSheet("color:#666;font-size:10px;border:none;")

    for w in (_lbl("봉:"), host.combo_intra_tf,
              _lbl("개수:"), host.spin_intra_bars,
              btn_1d, btn_2d, btn_3d,
              host.chk_intra_ext,
              host.combo_intra_chart_mode, btn_intra,
              _vsep(),
              _lbl("📅"), host.intra_date_edit,
              _lbl("⏱"), host.intra_time_input,
              btn_vline, btn_vline_clear,
              _vsep(),
              host.chk_kst,
              _lbl("📊"), host.spin_vol_threshold,
              host.lbl_intra_status):
        i_ctrl.addWidget(w)
    i_ctrl.addStretch()
    intra_v.addLayout(i_ctrl)

    # ── Vline checkbox scroll panel (30px fixed height) ───────
    host._vline_panel_widget = QWidget()
    host._vline_panel_widget.setStyleSheet("background:transparent;")
    host._vline_panel_layout = QHBoxLayout(host._vline_panel_widget)
    host._vline_panel_layout.setContentsMargins(4, 1, 4, 1)
    host._vline_panel_layout.setSpacing(8)
    host._vline_panel_layout.addStretch()

    vline_scroll = QScrollArea()
    vline_scroll.setWidget(host._vline_panel_widget)
    vline_scroll.setWidgetResizable(True)
    vline_scroll.setFixedHeight(26)
    vline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    vline_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    vline_scroll.setStyleSheet(
        "QScrollArea{background:#06060e;border:1px solid #1a1a3a;border-radius:2px;}")
    intra_v.addWidget(vline_scroll)

    host._vlines = []
    host._vline_counter = 0

    # ── MiniChartCanvas ──────────────────────────────────────
    host.mini_chart_intra = MiniChartCanvas(parent=intra_w, width=7, height=3, dpi=100)
    host.mini_chart_intra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    intra_v.addWidget(host.mini_chart_intra, 1)

    return intra_w


# ──────────────────────────────────────────────────────────────
# Tab 4: Tick Chart — reqHistoricalTicks
# [S6] No extra rows; single ctrl_row only
# ──────────────────────────────────────────────────────────────
def _build_tick_tab(host):
    tick_w = QWidget()
    tick_v = QVBoxLayout(tick_w)
    tick_v.setContentsMargins(0, 0, 0, 0)
    tick_v.setSpacing(2)

    t_ctrl = QHBoxLayout()
    t_ctrl.setSpacing(6)

    host.spin_tick_count = QSpinBox()
    host.spin_tick_count.setRange(5, 1000)
    host.spin_tick_count.setValue(20)
    host.spin_tick_count.setFixedWidth(62)
    host.spin_tick_count.setFixedHeight(22)
    host.spin_tick_count.setStyleSheet(_SB_STYLE)

    btn_tick = QPushButton("▶ 조회")
    btn_tick.setFixedHeight(22)
    btn_tick.setStyleSheet(_QUERY_BTN_STYLE)
    btn_tick.clicked.connect(host._fetch_tick_chart)

    host.lbl_tick_status = QLabel("▶ 조회 버튼으로 IBKR 틱 요청")
    host.lbl_tick_status.setStyleSheet("color:#666;font-size:10px;border:none;")

    for w in (_lbl("틱 수:"), host.spin_tick_count,
              btn_tick, host.lbl_tick_status):
        t_ctrl.addWidget(w)
    t_ctrl.addStretch()
    tick_v.addLayout(t_ctrl)

    if PG:
        host._pw_tick = pg.PlotWidget(background="#06060e")
        host._pw_tick.showGrid(x=True, y=True, alpha=0.2)
        host._pw_tick.setLabel('left', '가격')
        host._pw_tick.setLabel('bottom', '틱 인덱스')
        host._pw_tick.getPlotItem().setContentsMargins(0, 0, 0, 0)
        host._tick_line = host._pw_tick.plot(
            pen=pg.mkPen('#ffd700', width=1.5), name="Price")
        host._tick_dots = pg.ScatterPlotItem(
            size=6, brush=pg.mkBrush('#00e676'))
        host._pw_tick.addItem(host._tick_dots)
        tick_v.addWidget(host._pw_tick, 1)
    else:
        tick_v.addWidget(QLabel("pip install pyqtgraph  (틱 탭 전용)"))

    return tick_w
