"""
chart_panel_builder.py — _build_chart_panel() 및 _wrap_tbl() UI 빌더
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QCheckBox, QComboBox,
    QTabWidget, QPushButton, QSpinBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from chart_utils import (
    CB_STYLE      as _CB_STYLE,
    SB_STYLE      as _SB_STYLE,
    BTN_STYLE     as _BTN_STYLE,
    QUERY_BTN_STYLE as _QUERY_BTN_STYLE,
    TAB_STYLE     as _TAB_STYLE,
)


def _lbl(text):
    """미니 레이블 헬퍼."""
    return QLabel(text, styleSheet="color:#aaa;font-size:11px;border:none;")


# ──────────────────────────────────────────────────────────────
# 탭1: 실시간
# ──────────────────────────────────────────────────────────────
def _build_realtime_tab(host):
    rt_w = QWidget()
    rt_v = QVBoxLayout(rt_w)
    rt_v.setContentsMargins(0, 2, 0, 0)
    rt_v.setSpacing(2)

    ctrl_row = QHBoxLayout()
    ctrl_row.setSpacing(6)

    host.radio_chart_line   = QRadioButton("라인")
    host.radio_chart_candle = QRadioButton("캔들")
    host.radio_chart_line.setChecked(True)
    for rb in (host.radio_chart_line, host.radio_chart_candle):
        rb.setStyleSheet("color:#ffd700;font-size:11px;")
    cg = QButtonGroup(host)
    cg.addButton(host.radio_chart_line)
    cg.addButton(host.radio_chart_candle)
    host.radio_chart_line.toggled.connect(host._on_chart_type_toggle)

    host.chk_kst = QCheckBox("KST")
    host.chk_kst.setStyleSheet("color:#90caf9;font-size:11px;")
    host.chk_kst.stateChanged.connect(host._on_tz_toggle)

    host.combo_bar = QComboBox()
    host.combo_bar.addItems(["1분", "5분", "15분"])
    host.combo_bar.setFixedWidth(52)
    host.combo_bar.setFixedHeight(22)
    host.combo_bar.setStyleSheet(_CB_STYLE)

    for w in (_lbl("타입:"), host.radio_chart_line, host.radio_chart_candle,
              host.chk_kst, _lbl("봉:"), host.combo_bar):
        ctrl_row.addWidget(w)
    ctrl_row.addStretch()
    rt_v.addLayout(ctrl_row)

    host._pw1 = pg.PlotWidget()
    host._pw1.showGrid(x=True, y=True, alpha=0.2)
    host._pw1.setLabel('left', '프리미엄 ($)')
    host._x_axis_line = pg.DateAxisItem(orientation='bottom')
    host._pw1.setAxisItems({'bottom': host._x_axis_line})
    host._c_p  = host._pw1.plot(pen=pg.mkPen('#ffd700', width=2), name="Price")
    host._c_ma = host._pw1.plot(
        pen=pg.mkPen('#ff8800', width=1, style=Qt.DashLine), name="MA10")
    host._c_und = host._pw1.plot(
        pen=pg.mkPen('#5dade2', width=1, style=Qt.DotLine), name="UND")
    host._price_line = pg.InfiniteLine(
        angle=0, movable=False,
        pen=pg.mkPen('#00e676', width=1, style=Qt.DashLine))
    host._pw1.addItem(host._price_line)

    host._pw_candle = pg.PlotWidget()
    host._pw_candle.showGrid(x=True, y=True, alpha=0.2)
    host._pw_candle.setLabel('left', '프리미엄 ($)')
    host._x_axis_candle = pg.DateAxisItem(orientation='bottom')
    host._pw_candle.setAxisItems({'bottom': host._x_axis_candle})
    host._candle_bars = {}
    host._candle_items = []
    host._pw_candle.setVisible(False)

    rt_v.addWidget(host._pw1, 1)
    rt_v.addWidget(host._pw_candle, 1)
    return rt_w


# ──────────────────────────────────────────────────────────────
# 탭2: 일봉
# ──────────────────────────────────────────────────────────────
def _build_daily_tab(host):
    daily_w = QWidget()
    daily_v = QVBoxLayout(daily_w)
    daily_v.setContentsMargins(0, 2, 0, 0)
    daily_v.setSpacing(2)

    d_ctrl = QHBoxLayout()
    d_ctrl.setSpacing(6)

    host.combo_daily_period = QComboBox()
    host.combo_daily_period.addItems(["1개월", "3개월", "6개월", "1년"])
    host.combo_daily_period.setCurrentIndex(2)
    host.combo_daily_period.setFixedWidth(70)
    host.combo_daily_period.setFixedHeight(22)
    host.combo_daily_period.setStyleSheet(_CB_STYLE)

    btn_daily = QPushButton("▶ 조회")
    btn_daily.setFixedHeight(22)
    btn_daily.setStyleSheet(_QUERY_BTN_STYLE)
    btn_daily.clicked.connect(host._fetch_daily)

    host.lbl_daily_status = QLabel("기초자산 클릭 시 자동 조회")
    host.lbl_daily_status.setStyleSheet("color:#666;font-size:10px;border:none;")

    for w in (_lbl("기간:"), host.combo_daily_period,
              btn_daily, host.lbl_daily_status):
        d_ctrl.addWidget(w)
    d_ctrl.addStretch()
    daily_v.addLayout(d_ctrl)

    host._pw_daily = pg.PlotWidget()
    host._pw_daily.showGrid(x=True, y=True, alpha=0.2)
    host._pw_daily.setLabel('left', '가격')
    host._pw_daily.getPlotItem().setContentsMargins(10, 4, 10, 4)
    host._daily_items = []
    daily_v.addWidget(host._pw_daily, 1)
    return daily_w


# ──────────────────────────────────────────────────────────────
# 탭3: 분봉
# ──────────────────────────────────────────────────────────────
def _build_intraday_tab(host):
    intra_w = QWidget()
    intra_v = QVBoxLayout(intra_w)
    intra_v.setContentsMargins(0, 2, 0, 0)
    intra_v.setSpacing(2)

    i_ctrl = QHBoxLayout()
    i_ctrl.setSpacing(6)

    host.combo_intra_tf = QComboBox()
    host.combo_intra_tf.addItems(["1분", "5분", "15분", "30분", "60분"])
    host.combo_intra_tf.setCurrentIndex(0)
    host.combo_intra_tf.setFixedWidth(60)
    host.combo_intra_tf.setFixedHeight(22)
    host.combo_intra_tf.setStyleSheet(_CB_STYLE)

    host.spin_intra_bars = QSpinBox()
    host.spin_intra_bars.setRange(10, 9999)
    host.spin_intra_bars.setValue(399)
    host.spin_intra_bars.setFixedWidth(62)
    host.spin_intra_bars.setFixedHeight(22)
    host.spin_intra_bars.setStyleSheet(_SB_STYLE)

    btn_1d = QPushButton("1일"); btn_1d.setFixedHeight(22); btn_1d.setFixedWidth(34)
    btn_2d = QPushButton("2일"); btn_2d.setFixedHeight(22); btn_2d.setFixedWidth(34)
    btn_3d = QPushButton("3일"); btn_3d.setFixedHeight(22); btn_3d.setFixedWidth(34)
    for b in (btn_1d, btn_2d, btn_3d):
        b.setStyleSheet(_BTN_STYLE)
    btn_1d.clicked.connect(lambda: (host.spin_intra_bars.setValue(399),  host._fetch_intraday()))
    btn_2d.clicked.connect(lambda: (host.spin_intra_bars.setValue(798),  host._fetch_intraday()))
    btn_3d.clicked.connect(lambda: (host.spin_intra_bars.setValue(1197), host._fetch_intraday()))

    host.chk_intra_ext = QCheckBox("시간외 포함")
    host.chk_intra_ext.setStyleSheet("color:#90caf9;font-size:11px;")
    host.chk_intra_ext.setChecked(False)

    btn_intra = QPushButton("▶ 조회")
    btn_intra.setFixedHeight(22)
    btn_intra.setStyleSheet(_QUERY_BTN_STYLE)
    btn_intra.clicked.connect(host._fetch_intraday)

    host.lbl_intra_status = QLabel("기초자산 클릭 시 자동 조회")
    host.lbl_intra_status.setStyleSheet("color:#666;font-size:10px;border:none;")

    for w in (_lbl("봉:"), host.combo_intra_tf,
              _lbl("개수:"), host.spin_intra_bars,
              btn_1d, btn_2d, btn_3d,
              host.chk_intra_ext, btn_intra, host.lbl_intra_status):
        i_ctrl.addWidget(w)
    i_ctrl.addStretch()
    intra_v.addLayout(i_ctrl)

    host._pw_intra = pg.PlotWidget()
    host._pw_intra.showGrid(x=True, y=True, alpha=0.2)
    host._pw_intra.setLabel('left', '가격')
    host._pw_intra.getPlotItem().setContentsMargins(10, 4, 10, 4)
    host._intra_items = []
    intra_v.addWidget(host._pw_intra, 1)
    return intra_w


# ──────────────────────────────────────────────────────────────
# 메인 빌더 (ChartMixin에서 호출)
# ──────────────────────────────────────────────────────────────
def build_chart_panel(host):
    outer = QWidget()
    v = QVBoxLayout(outer)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)

    hdr = QHBoxLayout()
    host.chart_lbl = QLabel(
        "차트: ―  (옵션체인 클릭 → 차트선택 / 기초자산 클릭 → 히스토리)")
    host.chart_lbl.setStyleSheet(
        "color:#5dade2;font-weight:bold;font-size:11px;border:none;")
    host.lbl_pv = QLabel("Price: ―")
    host.lbl_pv.setStyleSheet(
        "color:#ffd700;font-weight:bold;font-size:11px;padding:0 8px;border:none;")
    hdr.addWidget(host.chart_lbl)
    hdr.addStretch()
    hdr.addWidget(host.lbl_pv)
    v.addLayout(hdr)

    if not PG:
        v.addWidget(QLabel("pip install pyqtgraph"))
        host._chart_outer = outer
        return outer

    pg.setConfigOption('background', '#06060e')
    pg.setConfigOption('foreground', '#ccc')

    host._chart_tabs = QTabWidget()
    host._chart_tabs.setStyleSheet(_TAB_STYLE)
    host._chart_tabs.addTab(_build_realtime_tab(host), "⚡ 실시간")
    host._chart_tabs.addTab(_build_daily_tab(host),   "📅 일봉")
    host._chart_tabs.addTab(_build_intraday_tab(host), "🕐 분봉")
    host._chart_tabs.setCurrentIndex(2)   # ✅ 기본값: 분봉 탭

    v.addWidget(host._chart_tabs, 1)
    host._chart_outer = outer
    return outer


def wrap_tbl(host, tbl, title, color):
    """테이블 위에 컬러 제목을 달아주는 래퍼."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(1)
    lbl = QLabel(title)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"color:{color};font-weight:bold;border:none;")
    v.addWidget(lbl)
    v.addWidget(tbl)
    return w
