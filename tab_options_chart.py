"""
tab_options_chart.py — 차트 패널 + Tick 수신 처리  v6.5
════════════════════════════════════════════════════════════════
  포함 기능:
  - _build_chart_panel()   탭 구조 (⚡실시간 | 📅일봉 | 🕐분봉)
  - _wrap_tbl()
  - _on_und_label_clicked() 기초자산 클릭 → 히스토리 자동 조회
  - _fetch_daily()          Polygon 일봉 (실패 시 IBKR fallback)
  - _fetch_intraday()       Polygon 분봉 (실패 시 IBKR fallback)
  - _draw_ohlc_candles()    OHLC 캔들 공통 렌더러
  - Tick 수신 / 실시간 라인·캔들
════════════════════════════════════════════════════════════════
"""

import os
import threading
from datetime import datetime, timedelta, date as _date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QRadioButton, QButtonGroup, QCheckBox,
    QComboBox, QTabWidget, QPushButton, QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import REQ_UND, REQ_CALL, REQ_PUT, tbl_set


def _polygon_key() -> str:
    """
    Polygon.io API 키 로드 순서:
    1. 실행 폴더의 stock_api_key 파일 (첫 번째 줄)
    2. core.py 의 POLYGON_API_KEY 상수
    3. 환경변수 POLYGON_API_KEY
    """
    # 1. stock_api_key 파일 (같은 폴더)
    try:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "stock_api_key")
        with open(key_file, "r", encoding="utf-8") as f:
            key = f.readline().strip()
        if key:
            return key
    except Exception:
        pass
    # 2. core.py 상수
    try:
        from core import POLYGON_API_KEY
        if POLYGON_API_KEY:
            return POLYGON_API_KEY
    except ImportError:
        pass
    # 3. 환경변수
    return os.environ.get("POLYGON_API_KEY", "")


class _FetchSignal(QObject):
    done = pyqtSignal(list)
    err  = pyqtSignal(str)


class ChartMixin:
    """차트 + Tick 수신 전용 메서드 모음. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 차트 패널 빌더
    # ─────────────────────────────────────────────────────────
    def _build_chart_panel(self):
        outer = QWidget()
        v = QVBoxLayout(outer)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)

        hdr = QHBoxLayout()
        self.chart_lbl = QLabel(
            "차트: ―  (옵션체인 클릭 → 차트선택 / 기초자산 클릭 → 히스토리)")
        self.chart_lbl.setStyleSheet(
            "color:#5dade2;font-weight:bold;font-size:11px;border:none;")
        self.lbl_pv = QLabel("Price: ―")
        self.lbl_pv.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;padding:0 8px;border:none;")
        hdr.addWidget(self.chart_lbl); hdr.addStretch(); hdr.addWidget(self.lbl_pv)
        v.addLayout(hdr)

        if not PG:
            v.addWidget(QLabel("pip install pyqtgraph"))
            self._chart_outer = outer
            return outer

        pg.setConfigOption('background', '#06060e')
        pg.setConfigOption('foreground', '#ccc')

        _tab_s = (
            "QTabWidget::pane{border:1px solid #2a2a5a;background:#06060e;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 10px;"
            "border:1px solid #2a2a5a;border-bottom:none;font-size:11px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;font-weight:bold;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
        self._chart_tabs = QTabWidget()
        self._chart_tabs.setStyleSheet(_tab_s)

        # ── 탭1: 실시간 옵션 프리미엄 ───────────────────────
        rt_w  = QWidget(); rt_v = QVBoxLayout(rt_w)
        rt_v.setContentsMargins(0, 2, 0, 0); rt_v.setSpacing(2)

        ctrl_row = QHBoxLayout(); ctrl_row.setSpacing(6)
        self.radio_chart_line   = QRadioButton("라인")
        self.radio_chart_candle = QRadioButton("캔들")
        self.radio_chart_line.setChecked(True)
        self.radio_chart_line.setStyleSheet("color:#ffd700;font-size:11px;")
        self.radio_chart_candle.setStyleSheet("color:#ffd700;font-size:11px;")
        cg = QButtonGroup(self)
        cg.addButton(self.radio_chart_line); cg.addButton(self.radio_chart_candle)
        self.radio_chart_line.toggled.connect(self._on_chart_type_toggle)
        self.chk_kst = QCheckBox("KST")
        self.chk_kst.setStyleSheet("color:#90caf9;font-size:11px;")
        self.chk_kst.stateChanged.connect(self._on_tz_toggle)
        self.combo_bar = QComboBox()
        self.combo_bar.addItems(["1분","5분","15분"])
        self.combo_bar.setFixedWidth(52); self.combo_bar.setFixedHeight(22)
        self.combo_bar.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "font-size:11px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
            "QComboBox::drop-down{border:none;}")
        for w in (QLabel("타입:", styleSheet="color:#aaa;font-size:11px;border:none;"),
                  self.radio_chart_line, self.radio_chart_candle,
                  self.chk_kst,
                  QLabel("봉:", styleSheet="color:#aaa;font-size:11px;border:none;"),
                  self.combo_bar):
            ctrl_row.addWidget(w)
        ctrl_row.addStretch()
        rt_v.addLayout(ctrl_row)

        self._pw1 = pg.PlotWidget()
        self._pw1.showGrid(x=True, y=True, alpha=0.2)
        self._pw1.setLabel('left', '프리미엄 ($)')
        self._x_axis_line = pg.DateAxisItem(orientation='bottom')
        self._pw1.setAxisItems({'bottom': self._x_axis_line})
        self._c_p  = self._pw1.plot(pen=pg.mkPen('#ffd700', width=2), name="Price")
        self._c_ma = self._pw1.plot(
            pen=pg.mkPen('#ff8800', width=1, style=Qt.DashLine), name="MA10")
        # 기초자산 실시간 라인 (우측 Y축)
        self._c_und = self._pw1.plot(
            pen=pg.mkPen('#5dade2', width=1, style=Qt.DotLine), name="UND")
        self._price_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen('#00e676', width=1, style=Qt.DashLine))
        self._pw1.addItem(self._price_line)
        self._pw_candle = pg.PlotWidget()
        self._pw_candle.showGrid(x=True, y=True, alpha=0.2)
        self._pw_candle.setLabel('left', '프리미엄 ($)')
        self._x_axis_candle = pg.DateAxisItem(orientation='bottom')
        self._pw_candle.setAxisItems({'bottom': self._x_axis_candle})
        self._candle_bars = {}; self._candle_items = []
        self._pw_candle.setVisible(False)
        rt_v.addWidget(self._pw1, 1)
        rt_v.addWidget(self._pw_candle, 1)
        self._chart_tabs.addTab(rt_w, "⚡ 실시간")

        # ── 탭2: 일봉 ────────────────────────────────────────
        daily_w = QWidget(); daily_v = QVBoxLayout(daily_w)
        daily_v.setContentsMargins(0, 2, 0, 0); daily_v.setSpacing(2)
        d_ctrl = QHBoxLayout(); d_ctrl.setSpacing(6)
        self.combo_daily_period = QComboBox()
        self.combo_daily_period.addItems(["1개월","3개월","6개월","1년"])
        self.combo_daily_period.setCurrentIndex(2)   # 기본 6개월
        self.combo_daily_period.setFixedWidth(70); self.combo_daily_period.setFixedHeight(22)
        self.combo_daily_period.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "font-size:11px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
            "QComboBox::drop-down{border:none;}")
        btn_daily = QPushButton("▶ 조회"); btn_daily.setFixedHeight(22)
        btn_daily.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:11px;"
            "font-weight:bold;padding:1px 8px;border-radius:3px;")
        btn_daily.clicked.connect(self._fetch_daily)
        self.lbl_daily_status = QLabel("기초자산 클릭 시 자동 조회")
        self.lbl_daily_status.setStyleSheet("color:#666;font-size:10px;border:none;")
        for w in (QLabel("기간:", styleSheet="color:#aaa;font-size:11px;border:none;"),
                  self.combo_daily_period, btn_daily, self.lbl_daily_status):
            d_ctrl.addWidget(w)
        d_ctrl.addStretch()
        daily_v.addLayout(d_ctrl)
        self._pw_daily = pg.PlotWidget()
        self._pw_daily.showGrid(x=True, y=True, alpha=0.2)
        self._pw_daily.setLabel('left', '가격')
        self._pw_daily.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self._daily_items = []
        daily_v.addWidget(self._pw_daily, 1)
        self._chart_tabs.addTab(daily_w, "📅 일봉")

        # ── 탭3: 분봉 ────────────────────────────────────────
        intra_w = QWidget(); intra_v = QVBoxLayout(intra_w)
        intra_v.setContentsMargins(0, 2, 0, 0); intra_v.setSpacing(2)
        i_ctrl = QHBoxLayout(); i_ctrl.setSpacing(6)
        _cb_s = ("QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
                 "font-size:11px;padding:1px;}"
                 "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
                 "QComboBox::drop-down{border:none;}")
        _sb_s = ("QSpinBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
                 "font-size:11px;padding:1px;}"
                 "QSpinBox::up-button,QSpinBox::down-button{width:14px;}")
        _btn_s = ("QPushButton{background:#1a3a5c;color:#90caf9;font-size:11px;"
                  "font-weight:bold;padding:1px 7px;border-radius:3px;"
                  "border:1px solid #2a5a8a;}"
                  "QPushButton:hover{background:#2a4a7c;}")
        self.combo_intra_tf = QComboBox()
        self.combo_intra_tf.addItems(["1분","5분","15분","30분","60분"])
        self.combo_intra_tf.setCurrentIndex(0)
        self.combo_intra_tf.setFixedWidth(60); self.combo_intra_tf.setFixedHeight(22)
        self.combo_intra_tf.setStyleSheet(_cb_s)
        # 봉 수 스핀박스 (기본 399 = 하루치 1분봉, 최대 999)
        self.spin_intra_bars = QSpinBox()
        self.spin_intra_bars.setRange(10, 9999)
        self.spin_intra_bars.setValue(399)
        self.spin_intra_bars.setFixedWidth(62); self.spin_intra_bars.setFixedHeight(22)
        self.spin_intra_bars.setStyleSheet(_sb_s)
        # 2일/3일 빠른 버튼 (399×N)
        btn_1d = QPushButton("1일"); btn_1d.setFixedHeight(22); btn_1d.setFixedWidth(34)
        btn_2d = QPushButton("2일"); btn_2d.setFixedHeight(22); btn_2d.setFixedWidth(34)
        btn_3d = QPushButton("3일"); btn_3d.setFixedHeight(22); btn_3d.setFixedWidth(34)
        for b in (btn_1d, btn_2d, btn_3d): b.setStyleSheet(_btn_s)
        btn_1d.clicked.connect(lambda: (self.spin_intra_bars.setValue(399),  self._fetch_intraday()))
        btn_2d.clicked.connect(lambda: (self.spin_intra_bars.setValue(798),  self._fetch_intraday()))
        btn_3d.clicked.connect(lambda: (self.spin_intra_bars.setValue(1197), self._fetch_intraday()))
        # 정규장/시간외 체크박스
        self.chk_intra_ext = QCheckBox("시간외 포함")
        self.chk_intra_ext.setStyleSheet("color:#90caf9;font-size:11px;")
        self.chk_intra_ext.setChecked(False)
        btn_intra = QPushButton("▶ 조회"); btn_intra.setFixedHeight(22)
        btn_intra.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:11px;"
            "font-weight:bold;padding:1px 8px;border-radius:3px;")
        btn_intra.clicked.connect(self._fetch_intraday)
        self.lbl_intra_status = QLabel("기초자산 클릭 시 자동 조회")
        self.lbl_intra_status.setStyleSheet("color:#666;font-size:10px;border:none;")
        for w in (QLabel("봉:", styleSheet="color:#aaa;font-size:11px;border:none;"),
                  self.combo_intra_tf,
                  QLabel("개수:", styleSheet="color:#aaa;font-size:11px;border:none;"),
                  self.spin_intra_bars,
                  btn_1d, btn_2d, btn_3d,
                  self.chk_intra_ext,
                  btn_intra, self.lbl_intra_status):
            i_ctrl.addWidget(w)
        i_ctrl.addStretch()
        intra_v.addLayout(i_ctrl)
        self._pw_intra = pg.PlotWidget()
        self._pw_intra.showGrid(x=True, y=True, alpha=0.2)
        self._pw_intra.setLabel('left', '가격')
        self._pw_intra.setAxisItems({'bottom': pg.DateAxisItem(orientation='bottom')})
        self._intra_items = []
        intra_v.addWidget(self._pw_intra, 1)
        self._chart_tabs.addTab(intra_w, "🕐 분봉")
        self._chart_tabs.setCurrentIndex(2)   # ✅ 기본값: 분봉 탭

        v.addWidget(self._chart_tabs, 1)
        self._chart_outer = outer
        return outer

    # ─────────────────────────────────────────────────────────
    # 기초자산 클릭 → 일봉/분봉 자동 조회
    # ─────────────────────────────────────────────────────────
    def _on_und_label_clicked(self):
        from core import is_market_open
        if is_market_open():
            # 장 중에는 실시간 탭만 사용 → 히스토리 조회 차단
            self._log("⚡ 장 운영 중 — 히스토리 차트는 장외 시간에만 조회됩니다.")
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(0)   # 실시간 탭 유지
            return
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self,'_chart_tabs') else 1
        if cur_tab == 2:   # 분봉 탭이 선택된 상태면 분봉만 조회
            self._fetch_intraday()
        else:              # 일봉 탭(또는 실시간) → 일봉+분봉 조회 후 일봉 탭 고정
            self._fetch_daily()
            self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)

    # ─────────────────────────────────────────────────────────
    # 일봉 조회
    # ─────────────────────────────────────────────────────────
    def _fetch_daily(self):
        sym = self.edit_sym.text().strip().upper().replace("SPXW","SPX") \
              if hasattr(self,'edit_sym') else "SPX"
        days_map = {"1개월":30,"3개월":90,"6개월":180,"1년":365}
        days  = days_map.get(self.combo_daily_period.currentText(), 365)
        end   = datetime.today().date()
        start = end - timedelta(days=days)
        self.lbl_daily_status.setText(f"조회 중… {sym} 일봉")

        sig = _FetchSignal()
        sig.done.connect(lambda bars: self._on_daily_done(bars, sym))
        sig.err.connect(lambda e: self._on_daily_err(e, sym, start, end))

        def _run():
            bars = self._polygon_aggs(sym, start, end, 1, "day")
            if bars: sig.done.emit(bars)
            else:    sig.err.emit("Polygon 실패 → IBKR 시도")
        threading.Thread(target=_run, daemon=True).start()

    def _on_daily_done(self, bars, sym):
        self.lbl_daily_status.setText(f"✅ {sym} 일봉  {len(bars)}봉")
        self._draw_ohlc_candles(self._pw_daily, self._daily_items, bars,
                                bar_width_sec=60*60*18)

    def _on_daily_err(self, msg, sym, start, end):
        self.lbl_daily_status.setText(f"⚠ {msg}")
        # 선택된 기간에 맞춰 IBKR duration 설정
        days_map = {"1개월":"1 M","3개월":"3 M","6개월":"6 M","1년":"1 Y"}
        dur = days_map.get(self.combo_daily_period.currentText(), "6 M")
        self._ibkr_hist(sym, dur, "1 day", 9800,
                        self._on_daily_done, self.lbl_daily_status)

    # ─────────────────────────────────────────────────────────
    # 분봉 조회
    # ─────────────────────────────────────────────────────────
    def _fetch_intraday(self):
        sym = self.edit_sym.text().strip().upper().replace("SPXW","SPX") \
              if hasattr(self,'edit_sym') else "SPX"
        tf_map = {"1분":1,"5분":5,"15분":15,"30분":30,"60분":60}
        tf     = tf_map.get(self.combo_intra_tf.currentText(), 1)
        max_bars = getattr(self, 'spin_intra_bars', None)
        max_bars = max_bars.value() if max_bars else 399

        # 봉 수로부터 필요한 기간 자동 계산
        # 하루 거래 시간 = 6.5시간 = 390분, 봉 수 × tf분 ÷ 390분/일 + 여유 3일
        trading_mins_per_day = 390
        need_days = max(1, int(max_bars * tf / trading_mins_per_day) + 3)
        end   = datetime.today().date()
        start = end - timedelta(days=need_days)
        self.lbl_intra_status.setText(f"조회 중… {sym} {tf}분봉 (최대 {max_bars}봉)")

        sig = _FetchSignal()
        sig.done.connect(lambda bars: self._on_intra_done(bars, sym, tf, max_bars))
        sig.err.connect(lambda e: self._on_intra_err(e, sym, tf, need_days, max_bars))

        def _run():
            bars = self._polygon_aggs(sym, start, end, tf, "minute")
            if bars: sig.done.emit(bars)
            else:    sig.err.emit("Polygon 실패 → IBKR 시도")
        threading.Thread(target=_run, daemon=True).start()

    def _on_intra_done(self, bars, sym, tf, max_bars=399):
        # 정규장 필터 (시간외 제외 시 ET 09:30~16:00 봉만 유지)
        ext = getattr(self, 'chk_intra_ext', None)
        include_ext = ext.isChecked() if ext else False
        if not include_ext:
            from datetime import timezone
            import time as _time
            def _is_regular(ts_unix):
                # UTC 기준 → ET 변환 (DST 단순 처리: 3월~11월 UTC-4, 나머지 UTC-5)
                from datetime import datetime as _dt
                dt = _dt.utcfromtimestamp(ts_unix)
                offset = 4 if 3 <= dt.month <= 10 else 5
                et = dt.hour * 60 + dt.minute - offset * 60  # 분 단위 ET 시각
                return 570 <= et < 960   # 09:30(570) ~ 16:00(960)
            bars = [b for b in bars if _is_regular(b["t"])]
        # 최신 max_bars 개만 표시
        if len(bars) > max_bars:
            bars = bars[-max_bars:]
        ext_label = "(정규+시간외)" if include_ext else "(정규장)"
        self.lbl_intra_status.setText(f"✅ {sym} {tf}분봉  {len(bars)}봉 {ext_label}")
        self._draw_ohlc_candles(self._pw_intra, self._intra_items, bars,
                                bar_width_sec=tf * 60 * 0.7)

    def _on_intra_err(self, msg, sym, tf, need_days, max_bars=399):
        self.lbl_intra_status.setText(f"⚠ {msg}")
        # IBKR duration 문자열: 일 수 기반
        if need_days <= 1:   dur = "1 D"
        elif need_days <= 2: dur = "2 D"
        elif need_days <= 5: dur = "1 W"
        else:                dur = "2 W"
        bar_size = ("1 min" if tf == 1 else f"{tf} mins") if tf < 60 else "1 hour"
        self._ibkr_hist(sym, dur, bar_size, 9801,
                        lambda bars: self._on_intra_done(bars, sym, tf, max_bars),
                        self.lbl_intra_status)

    # ─────────────────────────────────────────────────────────
    # Polygon REST 공통
    # ─────────────────────────────────────────────────────────
    def _polygon_aggs(self, sym: str, start: _date, end: _date,
                      multiplier: int, timespan: str) -> list:
        key = _polygon_key()
        if not key: return []
        # 인덱스 심볼은 I: prefix 필요, 나머지는 그대로
        _INDEX_SET = {"SPX","NDX","VIX","RUT","DJX","XSP","MID","GSPC"}
        ticker_map = {
            "SPX":"I:SPX","NDX":"I:NDX","VIX":"I:VIX","RUT":"I:RUT",
            "DJX":"I:DJX","XSP":"I:XSP","MID":"I:MID",
            "QQQ":"QQQ","SPY":"SPY","AAPL":"AAPL","TSLA":"TSLA","NVDA":"NVDA",
        }
        # ticker_map에 없는 인덱스 심볼도 I: prefix 붙임
        if sym in _INDEX_SET:
            ticker = ticker_map.get(sym, f"I:{sym}")
        else:
            ticker = ticker_map.get(sym, sym)
        url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}"
               f"/range/{multiplier}/{timespan}"
               f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
               f"?adjusted=true&sort=asc&limit=5000&apiKey={key}")
        try:
            import urllib.request, json
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            return [{"t":b["t"]/1000,"o":b["o"],"h":b["h"],
                     "l":b["l"],"c":b["c"],"v":b.get("v",0)}
                    for b in data.get("results",[])]
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────
    # IBKR reqHistoricalData fallback  (백그라운드 스레드 방식)
    # ─────────────────────────────────────────────────────────
    def _ibkr_hist(self, sym, duration, bar_size, req_id, on_done, lbl):
        """
        reqHistoricalData 를 백그라운드 스레드에서 실행하여 UI 프리징 방지.
        - historicalData / historicalDataEnd 콜백을 threading.Event 로 수집
        - 완료 후 QTimer.singleShot(0, ...) 로 메인스레드에서 렌더링
        """
        if not self.mw.connected:
            lbl.setText("❌ Polygon 키 또는 TWS 연결 필요"); return

        lbl.setText(f"⏳ IBKR {bar_size} 조회 중… {sym}")

        import threading as _threading
        from PyQt5.QtCore import QTimer as _QTimer

        def _run():
            try:
                from core import make_und_contract
                contract  = make_und_contract(sym)
                hist_buf  = []
                done_evt  = _threading.Event()
                is_daily  = "day" in bar_size

                orig_hd  = getattr(self.mw.ib, 'historicalData',    lambda *a: None)
                orig_hde = getattr(self.mw.ib, 'historicalDataEnd', lambda *a: None)

                def _on_bar(rId, bar):
                    if rId != req_id: return
                    try:
                        fmt = "%Y%m%d" if is_daily else "%Y%m%d %H:%M:%S"
                        raw = bar.date
                        # IBKR 일봉은 "YYYYMMDD", 분봉은 "YYYYMMDD HH:MM:SS"
                        t = datetime.strptime(raw[:len(fmt)], fmt)
                        hist_buf.append({"t": t.timestamp(), "o": bar.open,
                                         "h": bar.high, "l": bar.low,
                                         "c": bar.close, "v": bar.volume})
                    except Exception:
                        pass

                def _on_end(rId, *_):
                    if rId != req_id: return
                    self.mw.ib.historicalData    = orig_hd
                    self.mw.ib.historicalDataEnd = orig_hde
                    done_evt.set()

                self.mw.ib.historicalData    = _on_bar
                self.mw.ib.historicalDataEnd = _on_end
                self.mw.ib.reqHistoricalData(
                    req_id, contract, "", duration, bar_size,
                    "TRADES", 1, 1, False, [])

                # 최대 15초 대기 (응답 없으면 타임아웃)
                done_evt.wait(timeout=15)

                if hist_buf:
                    bars_copy = list(hist_buf)
                    _QTimer.singleShot(0, lambda: on_done(bars_copy))
                else:
                    _QTimer.singleShot(0, lambda: lbl.setText("❌ IBKR 응답 없음"))

            except Exception as e:
                _QTimer.singleShot(0, lambda: lbl.setText(f"❌ IBKR 오류: {e}"))

        _threading.Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────────────────────
    # OHLC 캔들 공통 렌더러
    # ─────────────────────────────────────────────────────────
    def _draw_ohlc_candles(self, pw, items_list: list, bars: list,
                           bar_width_sec: float = 3600):
        if not PG or not bars: return
        for it in items_list:
            try: pw.removeItem(it)
            except: pass
        items_list.clear()

        half = bar_width_sec * 0.45
        xs, ys = [], []
        for b in bars:
            t = b["t"]; o,h,l,c = b["o"],b["h"],b["l"],b["c"]
            color = "#00e676" if c >= o else "#ff5252"
            wick = pg.PlotDataItem(x=[t,t], y=[l,h], pen=pg.mkPen(color, width=1))
            pw.addItem(wick); items_list.append(wick)
            body_h = abs(c-o) or max((h-l)*0.05, 0.01)
            rect = pg.QtWidgets.QGraphicsRectItem(t-half, min(o,c), half*2, body_h)
            rect.setBrush(pg.mkBrush(color)); rect.setPen(pg.mkPen(color, width=0.5))
            pw.addItem(rect); items_list.append(rect)
            xs.append(t); ys.append(c)

        if len(xs) > 1:
            cl = pw.plot(x=xs, y=ys, pen=pg.mkPen('#ffffff', width=0.5, style=Qt.DotLine))
            items_list.append(cl)
        pw.autoRange()

    # ─────────────────────────────────────────────────────────
    # 실시간 차트 전환
    # ─────────────────────────────────────────────────────────
    def _on_chart_type_toggle(self):
        if not PG: return
        is_line = self.radio_chart_line.isChecked()
        self._pw1.setVisible(is_line); self._pw_candle.setVisible(not is_line)

    def _on_tz_toggle(self): self._redraw_chart_axes()

    # ─────────────────────────────────────────────────────────
    # DST / KST 유틸
    # ─────────────────────────────────────────────────────────
    def _is_dst(self, dt=None):
        if dt is None: dt = datetime.utcnow()
        y = dt.year
        dst_start = datetime(y,3,8)  + timedelta(days=(6-datetime(y,3,8).weekday())%7)
        dst_end   = datetime(y,11,1) + timedelta(days=(6-datetime(y,11,1).weekday())%7)
        return dst_start <= dt < dst_end

    def _et_to_kst(self, dt_et):
        return dt_et + timedelta(hours=13 if self._is_dst(dt_et) else 14)

    def _fmt_chart_time(self, dt_et):
        use_kst = self.chk_kst.isChecked() if hasattr(self,'chk_kst') else False
        return (self._et_to_kst(dt_et).strftime("%H:%M\nKST")
                if use_kst else dt_et.strftime("%H:%M\nET"))

    def _wrap_tbl(self, tbl, title, color):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(0,0,0,0); v.setSpacing(1)
        lbl = QLabel(title); lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color:{color};font-weight:bold;border:none;")
        v.addWidget(lbl); v.addWidget(tbl)
        return w

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        if price <= 0: return
        QTimer.singleShot(0, lambda: self._apply_tick_price(rid, tt, price))

    def _apply_tick_price(self, rid, tt, price):
        if rid == REQ_UND:
            if tt in (4,68,75,14,9):
                self.und_price = price
                if tt == 9: self.und_prev = price
                self._update_und_display()
            # Bid/Ask 호가를 현재가 패널에 저장
            # tt=1(Bid Live), tt=2(Ask Live), tt=66(DelayedBid), tt=67(DelayedAsk)
            if tt in (1, 66) and hasattr(self, '_pp_bid'):
                self._pp_bid = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            elif tt in (2, 67) and hasattr(self, '_pp_ask'):
                self._pp_ask = price
                if hasattr(self, '_update_price_panel'):
                    self._update_price_panel()
            return
        if REQ_CALL <= rid < REQ_CALL+self._MAX_STRIKES:
            row = rid-REQ_CALL
            if row >= len(self.call_strikes): return
            if tt in (4,68):
                tbl_set(self.tbl_call,row,1,f"{price:.2f}","#33aaff")
                self.call_data[rid]["last"] = price; self._upd_spread()
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    self._push_price(price)
                    # 현재가 패널 옵션 모드 호가 업데이트
                    if tt in (4,68) and hasattr(self, '_pp_opt_ask'):
                        if tt == 4: self._pp_opt_ask = price
                        self._refresh_opt_panel("C", self.call_strikes[row])
                for idx,rule in enumerate(self._watch_rules):
                    if rule["side"]=="C" and abs(float(rule["strike"])-self.call_strikes[row])<0.5:
                        self._watch_prev.setdefault(idx,{})["price"] = price
            elif tt in (1, 66):   # Bid / DelayedBid
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (2, 67):   # Ask / DelayedAsk
                if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("C", self.call_strikes[row])
            elif tt in (9,75): tbl_set(self.tbl_call,row,2,f"{price:.2f}","#aaa")
        elif REQ_PUT <= rid < REQ_PUT+self._MAX_STRIKES:
            row = rid-REQ_PUT
            if row >= len(self.put_strikes): return
            if tt in (4,68):
                tbl_set(self.tbl_put,row,1,f"{price:.2f}","#ff6666")
                self.put_data[rid]["last"] = price; self._upd_spread()
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    self._push_price(price)
                for idx,rule in enumerate(self._watch_rules):
                    if rule["side"]=="P" and abs(float(rule["strike"])-self.put_strikes[row])<0.5:
                        self._watch_prev.setdefault(idx,{})["price"] = price
            elif tt in (1, 66):   # Bid / DelayedBid
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    if hasattr(self, '_pp_opt_bid'): self._pp_opt_bid = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (2, 67):   # Ask / DelayedAsk
                if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                    if hasattr(self, '_pp_opt_ask'): self._pp_opt_ask = price
                    self._refresh_opt_panel("P", self.put_strikes[row])
            elif tt in (9,75): tbl_set(self.tbl_put,row,2,f"{price:.2f}","#aaa")

    def _refresh_opt_panel(self, side: str, strike: float):
        """선택된 옵션의 Bid/Ask Tick이 오면 현재가 패널 옵션 모드를 갱신."""
        if not hasattr(self, '_pp_mode') or self._pp_mode != 'opt': return
        if getattr(self, '_pp_opt_side', '') != side: return
        try:
            if abs(float(getattr(self, '_pp_opt_strike', '0')) - strike) > 0.5: return
        except: return
        if hasattr(self, '_update_price_panel_opt'):
            delta = None
            # 현재 delta 가져오기 (테이블에서)
            try:
                tbl = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                row = min(range(len(strikes)), key=lambda i: abs(strikes[i]-strike))
                delta_item = tbl.item(row, 3)
                if delta_item and delta_item.text() not in ("―",""):
                    delta = float(delta_item.text())
            except: pass
            self._update_price_panel_opt(
                side, str(int(strike)),
                self._pp_opt_bid, self._pp_opt_ask, delta)

    def _on_tick_option(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10,11,12,13,80,81): return
        try:
            if delta is None or abs(delta)>1.5: return
        except: return
        QTimer.singleShot(0, lambda: self._apply_tick_option(rid,tt,delta,theta,gamma))

    def _apply_tick_option(self, rid, tt, delta, theta, gamma):
        if REQ_CALL <= rid < REQ_CALL+self._MAX_STRIKES:
            row = rid-REQ_CALL
            if row >= len(self.call_strikes): return
            tbl_set(self.tbl_call,row,3,f"{delta:+.4f}","#aaddff")
            tbl_set(self.tbl_call,row,4,f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_call,row,5,f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike==self.call_strikes[row] and self._chart_side=="C":
                self._push_greeks(delta)
            self._update_watch_prev("C",self.call_strikes[row],delta,theta,gamma)
        elif REQ_PUT <= rid < REQ_PUT+self._MAX_STRIKES:
            row = rid-REQ_PUT
            if row >= len(self.put_strikes): return
            tbl_set(self.tbl_put,row,3,f"{delta:+.4f}","#ffaaaa")
            tbl_set(self.tbl_put,row,4,f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_put,row,5,f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike==self.put_strikes[row] and self._chart_side=="P":
                self._push_greeks(delta)
            self._update_watch_prev("P",self.put_strikes[row],delta,theta,gamma)

    def _update_watch_prev(self, side, strike, delta, theta, gamma):
        for idx,rule in enumerate(self._watch_rules):
            if rule["side"]==side and abs(float(rule["strike"])-strike)<0.5:
                self._watch_prev.setdefault(idx,{})
                self._watch_prev[idx].update({"delta":delta,"theta":theta,"gamma":gamma})

    def _update_und_display(self):
        price = self.und_price
        if price is None: return
        self.lbl_und.setText(f"{price:,.2f}")
        if self.und_prev and self.und_prev>0:
            chg=price-self.und_prev; pct=chg/self.und_prev*100
            sign="+" if chg>=0 else ""; col="#00e676" if chg>=0 else "#ff5252"
            self.lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
            self.lbl_chg.setStyleSheet(f"color:{col};font-weight:bold;border:none;")
        if PG:
            self._und_hist.append(price)
            if len(self._und_hist)>self._BUF: del self._und_hist[0]
            if hasattr(self, '_c_und'):
                self._c_und.setData(self._und_hist)
        # 현재가 패널 연동
        if hasattr(self, '_update_price_panel'):
            self._update_price_panel()

    def _upd_spread(self):
        c=self.call_data.get(REQ_CALL,{}).get("last")
        p=self.put_data.get(REQ_PUT,{}).get("last")
        if c and p and PG:
            self._spreads.append(c-p)
            if len(self._spreads)>self._BUF: del self._spreads[0]

    def _push_price(self, price):
        if not PG: return
        now_et   = datetime.utcnow()-timedelta(hours=4 if self._is_dst() else 5)
        now_unix = now_et.timestamp()
        self._prices.append(price); self._price_times.append(now_unix)
        if len(self._prices)>self._BUF:
            del self._prices[0]; del self._price_times[0]

        # ✅ X/Y 배열 길이 강제 동기화 (비동기 tick 타이밍 불일치 방어)
        min_len = min(len(self._prices), len(self._price_times))
        xs = self._price_times[-min_len:]
        ys = self._prices[-min_len:]
        if len(xs) == 0: return

        self._c_p.setData(x=xs, y=ys)
        ma=[sum(ys[max(0,i-9):i+1])/min(i+1,10) for i in range(len(ys))]
        self._c_ma.setData(x=xs, y=ma)
        self.lbl_pv.setText(f"Price: {price:.2f}")
        if hasattr(self,'_price_line'): self._price_line.setValue(price)
        bar_sec={"1분":60,"5분":300,"15분":900}.get(
            self.combo_bar.currentText() if hasattr(self,'combo_bar') else "1분",60)
        bar_key=int(now_unix//bar_sec)*bar_sec
        if bar_key in self._candle_bars:
            b=self._candle_bars[bar_key]
            b['h']=max(b['h'],price); b['l']=min(b['l'],price); b['c']=price
        else:
            self._candle_bars[bar_key]={'o':price,'h':price,'l':price,'c':price,'t':bar_key}
        self._redraw_candles()

    def _redraw_candles(self):
        if not PG or not hasattr(self,'_pw_candle'): return
        for it in self._candle_items:
            try: self._pw_candle.removeItem(it)
            except: pass
        self._candle_items.clear()
        bars=sorted(self._candle_bars.values(),key=lambda b:b['t'])
        if not bars: return
        for b in bars:
            t=b['t']; o,h,l,c=b['o'],b['h'],b['l'],b['c']
            color='#00e676' if c>=o else '#ff5252'
            wick=pg.PlotDataItem(x=[t+30,t+30],y=[l,h],pen=pg.mkPen(color,width=1))
            self._pw_candle.addItem(wick); self._candle_items.append(wick)
            body_h=abs(c-o) or 0.001
            rect=pg.QtWidgets.QGraphicsRectItem(t,min(o,c),55,body_h)
            rect.setBrush(pg.mkBrush(color)); rect.setPen(pg.mkPen(color))
            self._pw_candle.addItem(rect); self._candle_items.append(rect)

    def _redraw_chart_axes(self): pass

    def _push_greeks(self, delta):
        if not PG: return
        self._deltas.append(delta)
        if len(self._deltas)>self._BUF: del self._deltas[0]

        # ─────────────────────────────────────────────────────────
        # 장외 시간 기초자산 종가 Fallback (Polygon SPY 우회 활용)
        # ─────────────────────────────────────────────────────────
    def _fetch_fallback_close(self, sym):
            """실시간 틱이 안 올 때 Polygon에서 SPY 전일 종가를 가져와 SPX ATM 계산을 뚫어줌."""
            # 이미 가격이 수신되었다면 실행할 필요 없음
            if self.und_price is not None: return

            def _run():
                from datetime import datetime, timedelta
                from PyQt5.QtCore import QTimer

                # SPX/SPXW인 경우 SPY로 우회하여 조회 (주식 스타터팩 권한 활용)
                query_sym = "SPY" if sym in ("SPX", "SPXW") else sym

                # 최근 7일(휴일/주말 포함) 일봉을 가져와 가장 마지막 종가 사용
                end = datetime.today().date()
                start = end - timedelta(days=7)

                # Polygon 조회 (multiplier=1, timespan="day")
                bars = self._polygon_aggs(query_sym, start, end, 1, "day")

                if bars:
                    last_close = bars[-1]["c"]
                    # SPY 가격을 가져왔다면 SPX 스케일(약 10배)로 보정
                    if sym in ("SPX", "SPXW"):
                        last_close = last_close * 10.0

                    # 메인 스레드에서 UI 및 변수 업데이트
                    QTimer.singleShot(0, lambda: self._apply_fallback_price(last_close, query_sym))
                else:
                    QTimer.singleShot(0, lambda: self._log(f"🌙 장외 시간: Polygon 우회 조회 실패 ({query_sym} 데이터 없음)"))

            import threading
            threading.Thread(target=_run, daemon=True).start()

    def _apply_fallback_price(self, price, source_sym):
            # 비동기 처리 중 그 사이(1~2초)에 IBKR 틱이 왔다면 덮어쓰지 않음
            if self.und_price is None:
                self.und_price = price
                self.und_prev = price
                self._update_und_display()
                self._log(f"🌙 장외 시간: Polygon {source_sym} 종가 기반({price:,.2f})으로 체인 조회 진행")