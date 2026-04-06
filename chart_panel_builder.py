"""
chart_panel_builder.py — build_chart_panel() entry + realtime/daily tab builders
[S6] Changes:
  - Chart margins minimized (ContentsMargins → 0 everywhere)
  - Date/time/vline UI merged INTO intraday/tick control rows (chart_panel_tabs.py)
  - No separate date_row — chart area maximized
  - Tabs: realtime/daily here; intraday/tick in chart_panel_tabs.py
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QCheckBox, QComboBox,
    QTabWidget, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from chart_utils import (
    CB_STYLE        as _CB_STYLE,
    QUERY_BTN_STYLE as _QUERY_BTN_STYLE,
    TAB_STYLE       as _TAB_STYLE,
)
from chart_panel_tabs import _build_intraday_tab, _build_tick_tab


def _lbl(text):
    return QLabel(text, styleSheet="color:#aaa;font-size:11px;border:none;")


# ──────────────────────────────────────────────────────────────
# Tab 1: Realtime (pyqtgraph)
# ──────────────────────────────────────────────────────────────
def _build_realtime_tab(host):
    rt_w = QWidget()
    rt_v = QVBoxLayout(rt_w)
    rt_v.setContentsMargins(0, 0, 0, 0)
    rt_v.setSpacing(1)

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

    btn_rt_fetch = QPushButton("▶ 조회")
    btn_rt_fetch.setFixedHeight(22)
    btn_rt_fetch.setStyleSheet(_QUERY_BTN_STYLE)
    btn_rt_fetch.clicked.connect(host._fetch_intraday)

    for w in (_lbl("타입:"), host.radio_chart_line, host.radio_chart_candle,
              host.chk_kst, _lbl("봉:"), host.combo_bar, btn_rt_fetch):
        ctrl_row.addWidget(w)
    ctrl_row.addStretch()
    rt_v.addLayout(ctrl_row)

    if PG:
        pg.setConfigOption('background', '#06060e')
        pg.setConfigOption('foreground', '#ccc')

        host._pw1 = pg.PlotWidget()
        host._pw1.showGrid(x=True, y=True, alpha=0.2)
        host._pw1.getPlotItem().setContentsMargins(0, 0, 0, 0)
        host._x_axis_line = pg.DateAxisItem(orientation='bottom')
        host._pw1.setAxisItems({'bottom': host._x_axis_line})
        # Y축 좌우 교체
        host._pw1.showAxis('right')
        host._pw1.showAxis('left')
        host._pw1.getAxis('right').setStyle(showValues=True)
        host._pw1.getAxis('left').setStyle(showValues=False)
        host._pw1.setLabel('right', '프리미엄 ($)')

        host._c_p   = host._pw1.plot(pen=pg.mkPen('#ffd700', width=2), name="Price")
        host._c_ma  = host._pw1.plot(
            pen=pg.mkPen('#ff8800', width=1, style=Qt.DashLine), name="MA10")
        host._c_und = host._pw1.plot(
            pen=pg.mkPen('#5dade2', width=1, style=Qt.DotLine), name="UND")
        host._price_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen('#00e676', width=1, style=Qt.DashLine))
        host._pw1.addItem(host._price_line)

        host._pw_candle = pg.PlotWidget()
        host._pw_candle.showGrid(x=True, y=True, alpha=0.2)
        host._pw_candle.getPlotItem().setContentsMargins(0, 0, 0, 0)
        host._x_axis_candle = pg.DateAxisItem(orientation='bottom')
        host._pw_candle.setAxisItems({'bottom': host._x_axis_candle})
        # Y축 좌우 교체
        host._pw_candle.showAxis('right')
        host._pw_candle.showAxis('left')
        host._pw_candle.getAxis('right').setStyle(showValues=True)
        host._pw_candle.getAxis('left').setStyle(showValues=False)
        host._pw_candle.setLabel('right', '프리미엄 ($)')
        host._candle_bars  = {}
        host._candle_items = []
        host._pw_candle.setVisible(False)

        rt_v.addWidget(host._pw1, 1)
        rt_v.addWidget(host._pw_candle, 1)
    else:
        rt_v.addWidget(QLabel("pip install pyqtgraph  (실시간 탭 전용)"))

    return rt_w


# ──────────────────────────────────────────────────────────────
# Tab 2: Daily (pyqtgraph)
# ──────────────────────────────────────────────────────────────
def _build_daily_tab(host):
    daily_w = QWidget()
    daily_v = QVBoxLayout(daily_w)
    daily_v.setContentsMargins(0, 0, 0, 0)
    daily_v.setSpacing(1)

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

    if PG:
        host._pw_daily = pg.PlotWidget()
        host._pw_daily.showGrid(x=True, y=True, alpha=0.2)
        host._pw_daily.getPlotItem().setContentsMargins(0, 0, 0, 0)
        # Y축 좌우 교체
        host._pw_daily.showAxis('right')
        host._pw_daily.showAxis('left')
        host._pw_daily.getAxis('right').setStyle(showValues=True)
        host._pw_daily.getAxis('left').setStyle(showValues=False)
        host._pw_daily.setLabel('right', '가격')
        host._daily_items = []
        daily_v.addWidget(host._pw_daily, 1)
    else:
        daily_v.addWidget(QLabel("pip install pyqtgraph  (일봉 탭 전용)"))

    return daily_w


# ──────────────────────────────────────────────────────────────
# Main builder (called from ChartMixin)
# ──────────────────────────────────────────────────────────────
def build_chart_panel(host):
    outer = QWidget()
    v = QVBoxLayout(outer)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)

    hdr = QHBoxLayout()
    hdr.setContentsMargins(0, 0, 0, 0)
    host.chart_lbl = QLabel(
        "차트: ―  (옵션체인 클릭 → 차트선택 / 기초자산 클릭 → 히스토리)")
    host.chart_lbl.setStyleSheet(
        "color:#5dade2;font-weight:bold;font-size:11px;border:none;")

    # Price 라벨 (폰트 16)
    host.lbl_pv = QLabel("Price: ―")
    host.lbl_pv.setFont(QFont("Arial", 16, QFont.Bold))
    host.lbl_pv.setStyleSheet(
        "color:#ffd700;padding:0 4px;border:none;")

    # 현재 시간 라벨 (차트 시간대 기준)
    host.lbl_chart_time = QLabel("―")
    host.lbl_chart_time.setFont(QFont("Arial", 12))
    host.lbl_chart_time.setStyleSheet(
        "color:#aaaaaa;padding:0 4px;border:none;")

    # 우측 상단 Price + 시간 세로 배치
    rhs = QVBoxLayout()
    rhs.setSpacing(0)
    rhs.setContentsMargins(0, 0, 0, 0)
    rhs.addWidget(host.lbl_pv)
    rhs.addWidget(host.lbl_chart_time)

    hdr.addWidget(host.chart_lbl)
    hdr.addStretch()
    hdr.addLayout(rhs)
    v.addLayout(hdr)

    # 1초마다 시간 갱신
    def _update_time():
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo
            except ImportError:
                import pytz as _pytz
                class ZoneInfo:
                    def __new__(cls, key): return _pytz.timezone(key)
        from datetime import datetime as _dt
        use_kst = getattr(host, 'chk_kst', None) and host.chk_kst.isChecked()
        if use_kst:
            now = _dt.now(ZoneInfo("Asia/Seoul"))
            host.lbl_chart_time.setText(now.strftime("%H:%M:%S KST"))
        else:
            now = _dt.now(ZoneInfo("America/New_York"))
            host.lbl_chart_time.setText(now.strftime("%H:%M:%S ET"))

    host._chart_time_timer = QTimer()
    host._chart_time_timer.setInterval(1000)
    host._chart_time_timer.timeout.connect(_update_time)
    host._chart_time_timer.start()
    _update_time()  # 즉시 한 번 실행

    host._chart_tabs = QTabWidget()
    host._chart_tabs.setStyleSheet(_TAB_STYLE)
    host._chart_tabs.addTab(_build_realtime_tab(host), "⚡ 실시간")
    host._chart_tabs.addTab(_build_daily_tab(host),    "📅 일봉")
    host._chart_tabs.addTab(_build_intraday_tab(host), "🕐 분봉")
    host._chart_tabs.addTab(_build_tick_tab(host),     "⚡ 틱차트")
    host._chart_tabs.setCurrentIndex(2)

    v.addWidget(host._chart_tabs, 1)
    host._chart_outer = outer
    return outer


def wrap_tbl(host, tbl, title, color):
    """Wrap a table widget with a colored title label."""
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