"""
tab_chart.py — 1분봉 차트 탭  v6.2
════════════════════════════════════════════════════════════════
과거 조회: Polygon.io REST API + data_io.py pickle/CSV 캐시
실시간   : IBKR reqHistoricalData (5초 BAR) 또는
           Polygon WebSocket (AM 이벤트)

StockChartTab 전체 이식 (common.py / data_io.py 참조)
════════════════════════════════════════════════════════════════
그리드 배치 (12×4):
  [0,0-1] 소스 모드   [0,2-4] 심볼·RT버튼  [0,5-7] 필터
  [0,8-9] 피크1       [0,10-11] 피크2
  [1,0-1] 관심·캘린더  [1,2-11] 캔들 차트
  [2,0-1] 다크·홀딩   [2,2-11] 데이터 테이블(좌)
  [3,0-5] 대량체결(우)  [3,6-11] 피크3 다중선택
"""

import os, sys, json, asyncio, threading, requests
from datetime import datetime, timedelta, time, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QTextEdit, QCheckBox, QSpinBox,QSplitter,
    QAbstractItemView, QHeaderView, QMessageBox,
    QCalendarWidget, QFrame, QRadioButton, QButtonGroup,
    QInputDialog, QTableWidget, QTableWidgetItem, QFileDialog,
    QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate
from PyQt5.QtGui import QFont, QColor, QBrush, QPicture, QPainter

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False
    pd = None

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, make_table, tbl_set, ts,
    REQ_HIST, SAVE_DIR, INDEX_SYM,
    make_und_contract,
    auto_mdt, is_market_open,
)

# ── data_io / common 경로 참조 ────────────────────────────────
try:
    from common import (DATA_ROOT, API_KEY_FILE, WATCHLIST_FILE,
                        DARK_BG, PANEL_BG, CARD_BG, BLUE, RED,
                        GREEN, ORANGE, GRAY, TEXT, GLOBAL_STYLE)
    _USE_COMMON = True
except Exception:
    DATA_ROOT      = Path(r"C:\data\US_StockData")
    API_KEY_FILE   = DATA_ROOT / "stock_api_key"
    WATCHLIST_FILE = DATA_ROOT / "watchlist.json"
    DARK_BG = "#0d0d1a"; PANEL_BG = "#12122a"; CARD_BG = "#1a1a2e"
    BLUE="#00c8ff"; RED="#ff4c6a"; GREEN="#00e676"
    ORANGE="#ff9800"; GRAY="#444466"; TEXT="#e0e0ff"
    GLOBAL_STYLE = ""
    _USE_COMMON = False

try:
    from data_io import (load_month, fetch_polygon_month,
                         fetch_polygon_daily, sym_dir)
    _USE_DATA_IO = True
except Exception:
    _USE_DATA_IO = False

CHART_WATCHLIST = SAVE_DIR / "chart_watchlist.json"

# ── 차트탭 전용 다크/라이트 팔레트 ──────────────────────────
_THEME = {
    True: dict(   # 다크
        widget_bg   = "#1e1e1e",
        panel_bg    = "#2b2b2b",
        fg          = "#e8e8e8",
        border      = "#444444",
        accent      = "#90caf9",
        tbl_bg      = "#1a1a2a",
        tbl_sel     = "#1c3a6a",
        hdr_bg      = "#141430",
        hdr_fg      = "#5dade2",
        chart_bg    = (30, 30, 30),
        candle_up   = "#3c78ff",
        candle_dn   = "#ff3c3c",
        row_hi      = "#7f1f1f",
        row_mid     = "#7f4f1f",
        row_lo      = "#5f5f10",
        scrollbar   = "#444",
    ),
    False: dict(  # 라이트
        widget_bg   = "#f5f5f5",
        panel_bg    = "#ffffff",
        fg          = "#111111",
        border      = "#cccccc",
        accent      = "#1565c0",
        tbl_bg      = "#ffffff",
        tbl_sel     = "#bbdefb",
        hdr_bg      = "#e3f2fd",
        hdr_fg      = "#1565c0",
        chart_bg    = (245, 245, 245),
        candle_up   = "#3c78ff",
        candle_dn   = "#ff3c3c",
        row_hi      = "#ffcccc",
        row_mid     = "#ffe0b2",
        row_lo      = "#fff9c4",
        scrollbar   = "#bbb",
    ),
}


# ══════════════════════════════════════════════════════════════
# 캔들스틱 아이템 (pyqtgraph)
# ══════════════════════════════════════════════════════════════
if PG:
    class CandlestickItem(pg.GraphicsObject):
        def __init__(self, data, up="#3c78ff", dn="#ff3c3c"):
            pg.GraphicsObject.__init__(self)
            self.data=data; self.up=up; self.dn=dn; self._gen()

        def _gen(self):
            self.picture=QPicture(); p=QPainter(self.picture)
            for t,o,c,lo,hi in self.data:
                col=QColor(self.up if c>=o else self.dn)
                p.setPen(pg.mkPen(col,width=1)); p.setBrush(pg.mkBrush(col))
                p.drawLine(pg.QtCore.QPointF(t,lo),pg.QtCore.QPointF(t,hi))
                p.drawRect(pg.QtCore.QRectF(t-0.3,o,0.6,c-o))
            p.end()

        def paint(self,p,*a): p.drawPicture(0,0,self.picture)
        def boundingRect(self): return pg.QtCore.QRectF(self.picture.boundingRect())


# ══════════════════════════════════════════════════════════════
# Polygon WebSocket 워커
# ══════════════════════════════════════════════════════════════
class PolygonWorker(QThread):
    data_received = pyqtSignal(dict)

    def __init__(self, api_key, symbol):
        super().__init__()
        self.api_key=api_key; self.symbol=symbol.upper(); self._run=True

    def run(self):
        loop=asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        try: loop.run_until_complete(self._main())
        except: pass

    async def _main(self):
        try:
            import websockets
            uri="wss://socket.polygon.io/stocks"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"action":"auth","params":self.api_key}))
                await ws.send(json.dumps({"action":"subscribe","params":f"AM.{self.symbol}"}))
                while self._run:
                    try:
                        raw=await asyncio.wait_for(ws.recv(),timeout=1.0)
                        for d in json.loads(raw):
                            if d.get('ev')=='AM' and d.get('sym')==self.symbol:
                                self.data_received.emit(d)
                    except asyncio.TimeoutError: continue
                    except: break
        except ImportError:
            print("[ChartTab] websockets 미설치 → pip install websockets")

    def stop(self): self._run=False


# ══════════════════════════════════════════════════════════════
# IBKR 실시간 분봉 타이머 (5초마다 reqHistoricalData)
# ══════════════════════════════════════════════════════════════
class IBKRBarTimer(QTimer):
    bar_updated=pyqtSignal(dict)

    def __init__(self, ib, symbol, parent=None):
        super().__init__(parent)
        self.ib=ib; self.symbol=symbol; self._rid=REQ_HIST
        self.timeout.connect(self._fetch)
        # hist_bar는 범위 기반이 아닌 rid 일치로 처리 — bridge 직접 연결 유지
        bridge.hist_bar.connect(self._on_bar)

    def _fetch(self):
        if not self.ib or not hasattr(self.ib,'reqHistoricalData'): return
        c=make_und_contract(self.symbol)
        self.ib.reqHistoricalData(
            self._rid,c,"","3600 S","1 min","TRADES",1,1,True,[])

    def _on_bar(self, rid, bar):
        if rid!=self._rid: return
        try:
            dt=datetime.strptime(bar.date,"%Y%m%d  %H:%M:%S")
            self.bar_updated.emit({
                "t":int(dt.timestamp()*1000),"o":bar.open,
                "h":bar.high,"l":bar.low,"c":bar.close,"v":bar.volume})
        except: pass

    def stop(self):
        try: bridge.hist_bar.disconnect(self._on_bar)
        except: pass
        super().stop()


# ══════════════════════════════════════════════════════════════
# Tab 7: 1분봉 차트 (StockChart.py v9.1 사이드바 레이아웃)
# ══════════════════════════════════════════════════════════════
class ChartGrid(QWidget):
    def __init__(self, mw):
        super().__init__()   # QWidget.__init__
        self.mw          = mw
        self.api_key     = self._load_api_key()
        self.worker      = None
        self.ibkr_timer  = None
        self.mode        = "polygon"    # "polygon" | "ibkr"
        self.df_raw      = []           # list of bar dicts
        self.df          = None         # pd.DataFrame (if PANDAS)
        self.is_rt       = False
        self.selected_date  = None
        self.current_sym = "SPY"
        self._right_row  = 0
        self.current_processed = []     # [(bar_dict, et_dt, eok)]
        self.dark_mode          = False  # 기본값: 라이트 모드
        self._multi_day_active  = False
        self._multi_day_count   = 1
        # 차트 가로 라인 저장소: 슬롯 기반 (build에서 초기화)
        self._hlines: dict = {}
        self._time_markers: dict = {}
        self._build()
        self._load_watchlist()
        # 초기 라이트 테마 적용
        self._apply_theme()

    # ── API 키 / 관심종목 ─────────────────────────────────────────
    def _load_api_key(self):
        try: return API_KEY_FILE.read_text(encoding="utf-8").strip()
        except: return ""

    def _load_watchlist(self):
        try:
            if CHART_WATCHLIST.exists():
                items=json.loads(CHART_WATCHLIST.read_text(encoding="utf-8"))
                for sym in items: self.watch_list.addItem(sym)
        except: pass

    def _save_watchlist(self):
        items=[self.watch_list.item(i).text() for i in range(self.watch_list.count())]
        CHART_WATCHLIST.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")

    # ── Splitter 비율 저장/복원 (TabWrapper 연동) ─────────────────
    def _get_extra_settings(self) -> dict:
        d = {}
        try:
            d["h_split"]   = list(self._h_splitter.sizes())
            d["v_split"]   = list(self._v_splitter.sizes())
            d["tbl_split"] = list(self._tbl_splitter.sizes())
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        def _restore():
            try:
                if s.get("h_split"):
                    self._h_splitter.setSizes(s["h_split"])
                if s.get("v_split"):
                    self._v_splitter.setSizes(s["v_split"])
                if s.get("tbl_split"):
                    self._tbl_splitter.setSizes(s["tbl_split"])
            except Exception:
                pass
        # 위젯이 완전히 표시된 뒤 복원 (100ms 지연)
        QTimer.singleShot(100, _restore)

    # ── UI 빌드 (StockChart.py v9.1 사이드바 레이아웃) ──────────
    def _build(self):
        # ══════════════════════════════════════════════════════
        # 최상위: 수평 QSplitter (사이드바 | 콘텐츠)
        # ══════════════════════════════════════════════════════
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        self._h_splitter = QSplitter(Qt.Horizontal)
        self._h_splitter.setHandleWidth(5)
        self._h_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        # ══════════════════════════════════════════════════════
        # 좌측 사이드바
        # ══════════════════════════════════════════════════════
        side = QVBoxLayout()
        side.setSpacing(3)
        side.setContentsMargins(4, 4, 4, 4)

        # 데이터 소스 (Polygon / IBKR)
        src_grp = QGroupBox("데이터 소스"); src_v = QVBoxLayout(src_grp)
        src_v.setSpacing(2); src_v.setContentsMargins(6, 4, 6, 4)
        self.radio_polygon = QRadioButton("Polygon.io")
        self.radio_ibkr    = QRadioButton("IBKR API")
        self.radio_polygon.setChecked(True)
        mg = QButtonGroup(self)
        mg.addButton(self.radio_polygon); mg.addButton(self.radio_ibkr)
        self.radio_polygon.toggled.connect(self._on_mode_change)
        self.lbl_mode = QLabel("Polygon.io")
        self.lbl_mode.setStyleSheet("color:#aaa;font-size:11px;")
        src_v.addWidget(self.radio_polygon); src_v.addWidget(self.radio_ibkr)
        src_v.addWidget(self.lbl_mode)
        side.addWidget(src_grp)

        # 종목 / 관심종목
        sym_grp = QGroupBox("종목 / 관심종목"); sym_v = QVBoxLayout(sym_grp)
        sym_v.setSpacing(2); sym_v.setContentsMargins(6, 4, 6, 4)
        self.sym_in = QLineEdit("SPY")
        sym_v.addWidget(self.sym_in)
        self.watch_list = QListWidget()
        self.watch_list.setMaximumHeight(80)
        self.watch_list.itemClicked.connect(lambda it: self.start_stream(it.text()))
        sym_v.addWidget(self.watch_list)
        brow = QHBoxLayout(); brow.setSpacing(2)
        ba = QPushButton("추가"); ba.setFixedHeight(22); ba.clicked.connect(self._w_add)
        bd = QPushButton("삭제"); bd.setFixedHeight(22); bd.clicked.connect(self._w_del)
        brow.addWidget(ba); brow.addWidget(bd)
        sym_v.addLayout(brow)
        side.addWidget(sym_grp)

        # 환율 / 필터
        flt_grp = QGroupBox("환율 / 필터"); flt_v = QVBoxLayout(flt_grp)
        flt_v.setSpacing(2); flt_v.setContentsMargins(6, 4, 6, 4)
        fr = QHBoxLayout()
        fr.addWidget(QLabel("환율(원)")); self.fx_in = QLineEdit("1480")
        self.fx_in.setFixedWidth(60); fr.addWidget(self.fx_in)
        fr.addWidget(QLabel("필터(억)")); self.high_in = QLineEdit("3000")
        self.high_in.setFixedWidth(60); fr.addWidget(self.high_in)
        flt_v.addLayout(fr)
        fg = QGridLayout(); fg.setSpacing(2)
        for idx, val in enumerate(["1000", "3000", "5000", "7500"]):
            btn = QPushButton(f"{val}억"); btn.setFixedHeight(20)
            btn.clicked.connect(lambda _, v=val: self.high_in.setText(v))
            fg.addWidget(btn, 0, idx)
        flt_v.addLayout(fg)
        side.addWidget(flt_grp)

        # 실시간 / 캔들 갯수 / 상태
        rt_grp = QGroupBox("실시간"); rt_v = QVBoxLayout(rt_grp)
        rt_v.setSpacing(2); rt_v.setContentsMargins(6, 4, 6, 4)
        self.btn_rt = QPushButton("▶ 실시간 시작")
        self.btn_rt.setCheckable(True)
        self.btn_rt.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
        self.btn_rt.clicked.connect(self._on_rt_btn)
        rt_v.addWidget(self.btn_rt)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("캔들:"))
        self.candle_spin = QSpinBox()
        self.candle_spin.setRange(10, 2000); self.candle_spin.setValue(180)
        crow.addWidget(self.candle_spin); crow.addStretch()
        rt_v.addLayout(crow)
        self.status_lbl = QLabel("상태: 대기")
        self.status_lbl.setStyleSheet("font-weight:bold;font-size:11px;")
        rt_v.addWidget(self.status_lbl)
        side.addWidget(rt_grp)

        # 옵션 체크박스
        opt_grp = QGroupBox("보기 옵션"); opt_v = QVBoxLayout(opt_grp)
        opt_v.setSpacing(2); opt_v.setContentsMargins(6, 4, 6, 4)
        self.holding_chk = QCheckBox("종가홀딩 보기")
        self.holding_chk.stateChanged.connect(lambda _: self._update_display())
        opt_v.addWidget(self.holding_chk)
        hi = QLabel("  15:00~마감 + 다음날 시초~10:30")
        hi.setStyleSheet("color:gray;font-size:10px;")
        opt_v.addWidget(hi)
        multi_row = QHBoxLayout(); multi_row.setSpacing(4)
        multi_row.addWidget(QLabel("연속:"))
        self.multi_chks = {}
        for days in [2, 3, 4]:
            chk = QCheckBox(f"{days}일"); chk.setChecked(False)
            chk.stateChanged.connect(
                lambda state, d=days, c=chk: self._on_multi_chk(d, c, state))
            multi_row.addWidget(chk)
            self.multi_chks[days] = chk
        opt_v.addLayout(multi_row)
        side.addWidget(opt_grp)

        # 캘린더
        cal_grp = QGroupBox("과거 복기"); cal_v = QVBoxLayout(cal_grp)
        cal_v.setSpacing(2); cal_v.setContentsMargins(4, 4, 4, 4)
        self.calendar = QCalendarWidget()
        self.calendar.setMaximumHeight(185)
        self.calendar.clicked.connect(self._on_calendar)
        cal_v.addWidget(self.calendar)
        side.addWidget(cal_grp)

        # 수급 피크 검색
        pk_grp = QGroupBox("수급 피크 검색"); pk_v = QVBoxLayout(pk_grp)
        pk_v.setSpacing(3); pk_v.setContentsMargins(6, 4, 6, 4)

        pk_v.addWidget(QLabel("① ±30분 최대"))
        p1r = QHBoxLayout(); p1r.setSpacing(3)
        self.pk1_in = QLineEdit(); self.pk1_in.setPlaceholderText("10:30 (ET)")
        self.pk1_in.setFixedHeight(22)
        b1 = QPushButton("검색"); b1.setFixedHeight(22); b1.setFixedWidth(44)
        b1.clicked.connect(self._peak1)
        p1r.addWidget(self.pk1_in); p1r.addWidget(b1)
        pk_v.addLayout(p1r)
        self.pk1_lbl = QLabel("결과: ―"); self.pk1_lbl.setWordWrap(True)
        self.pk1_lbl.setStyleSheet("color:#c62828;font-weight:bold;font-size:11px;")
        pk_v.addWidget(self.pk1_lbl)

        pk_v.addWidget(QLabel("② 구간 합산"))
        p2r = QHBoxLayout(); p2r.setSpacing(2)
        self.pk2_s = QLineEdit(); self.pk2_s.setPlaceholderText("09:30")
        self.pk2_s.setFixedHeight(22)
        self.pk2_e = QLineEdit(); self.pk2_e.setPlaceholderText("10:30")
        self.pk2_e.setFixedHeight(22)
        b2 = QPushButton("합산"); b2.setFixedHeight(22); b2.setFixedWidth(44)
        b2.clicked.connect(self._peak2)
        p2r.addWidget(self.pk2_s); p2r.addWidget(QLabel("~"))
        p2r.addWidget(self.pk2_e); p2r.addWidget(b2)
        pk_v.addLayout(p2r)
        self.pk2_lbl = QLabel("합산: ―"); self.pk2_lbl.setWordWrap(True)
        self.pk2_lbl.setStyleSheet("color:#1b5e20;font-weight:bold;font-size:11px;")
        pk_v.addWidget(self.pk2_lbl)

        pk_v.addWidget(QLabel("③ 테이블 다중선택"))
        self.pk3_lbl = QLabel("선택 합산: 0.00억")
        self.pk3_lbl.setWordWrap(True)
        self.pk3_lbl.setStyleSheet(
            "font-weight:bold;font-size:12px;"
            "border:1px solid #9c27b0;padding:3px;border-radius:4px;")
        pk_v.addWidget(self.pk3_lbl)
        side.addWidget(pk_grp)

        side.addStretch(1)

        # 사이드바 → ScrollArea
        side_w = QWidget(); side_w.setLayout(side)
        side_w.setMinimumWidth(220)
        scroll = QScrollArea()
        scroll.setWidget(side_w); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumWidth(230); scroll.setMaximumWidth(320)
        scroll.setFrameShape(QFrame.NoFrame)
        self._h_splitter.addWidget(scroll)

        # ══════════════════════════════════════════════════════
        # 우측: 수직 QSplitter (테이블 영역 | 차트 영역)
        # ══════════════════════════════════════════════════════
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(5)
        self._v_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        # ── 테이블 영역: 수평 QSplitter (좌 테이블 | 우 테이블) ──
        self._tbl_splitter = QSplitter(Qt.Horizontal)
        self._tbl_splitter.setHandleWidth(4)
        self._tbl_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        # 좌측 테이블
        lw = QWidget(); lbox = QVBoxLayout(lw)
        lbox.setContentsMargins(0, 0, 0, 0); lbox.setSpacing(2)
        lbox.addWidget(QLabel("▶ 데이터 테이블 (좌)"))
        self.table_l = make_table(["시간(ET)", "시가", "고가", "저가", "종가", "거래대금(억)"])
        self.table_l.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table_l.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_l.itemSelectionChanged.connect(lambda: self._update_peak3(self.table_l))
        lbox.addWidget(self.table_l)
        self._tbl_splitter.addWidget(lw)

        # 우측 테이블
        rw = QWidget(); rbox = QVBoxLayout(rw)
        rbox.setContentsMargins(0, 0, 0, 0); rbox.setSpacing(2)
        rtitle_row = QHBoxLayout()
        rtitle_row.addWidget(QLabel("▶ 대량체결 / FTD / 공매도 테이블 (우)"))
        rtitle_row.addStretch()
        btn_clr = QPushButton("초기화"); btn_clr.setFixedWidth(60); btn_clr.setFixedHeight(22)
        btn_clr.clicked.connect(self._clr_right)
        rtitle_row.addWidget(btn_clr)
        rbox.addLayout(rtitle_row)
        load_row = QHBoxLayout(); load_row.setSpacing(4)
        self.file_type_combo = QComboBox()
        self.file_type_combo.addItems(["FTD (미결제)", "공매도 (Short Volume)"])
        self.file_type_combo.setFixedWidth(155); self.file_type_combo.setFixedHeight(22)
        load_row.addWidget(self.file_type_combo)
        self.file_sym_in = QLineEdit()
        self.file_sym_in.setPlaceholderText("종목 (예: spy)")
        self.file_sym_in.setFixedWidth(80); self.file_sym_in.setFixedHeight(22)
        load_row.addWidget(self.file_sym_in)
        btn_load = QPushButton("📂 불러오기"); btn_load.setFixedWidth(85); btn_load.setFixedHeight(22)
        btn_load.clicked.connect(self._load_aux_file); load_row.addWidget(btn_load)
        self.file_status_lbl = QLabel("")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:gray;")
        load_row.addWidget(self.file_status_lbl); load_row.addStretch()
        rbox.addLayout(load_row)
        self.table_r = make_table(["시간(ET)", "시가", "고가", "저가", "종가", "거래대금(억)", "구분"])
        self.table_r.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table_r.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_r.itemSelectionChanged.connect(lambda: self._update_peak3(self.table_r))
        rbox.addWidget(self.table_r)
        self._tbl_splitter.addWidget(rw)
        self._tbl_splitter.setSizes([500, 500])

        self._v_splitter.addWidget(self._tbl_splitter)

        # ── 차트 영역 ─────────────────────────────────────────
        chart_w = QWidget(); chart_v = QVBoxLayout(chart_w)
        chart_v.setContentsMargins(0, 0, 0, 0); chart_v.setSpacing(2)

        if PG:
            # 컨트롤 바
            line_bar = QHBoxLayout(); line_bar.setSpacing(6)
            self.btn_hline = QPushButton("✏ 가로 라인")
            self.btn_hline.setCheckable(True); self.btn_hline.setFixedHeight(24)
            self.btn_hline.setStyleSheet(
                "QPushButton{background:#1c1c3a;color:#aaa;"
                "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
                "QPushButton:checked{background:#2a4a2a;color:#00e676;"
                "border-color:#00e676;}")
            line_bar.addWidget(self.btn_hline)

            self.time_marker_in = QLineEdit()
            self.time_marker_in.setPlaceholderText("HH:MM (마커)")
            self.time_marker_in.setFixedWidth(95); self.time_marker_in.setFixedHeight(24)
            btn_marker = QPushButton("▼ 마커")
            btn_marker.setFixedHeight(24); btn_marker.setFixedWidth(58)
            btn_marker.clicked.connect(self._add_time_marker)
            line_bar.addWidget(self.time_marker_in); line_bar.addWidget(btn_marker)

            self.kst_chk = QCheckBox("KST")
            self.kst_chk.setFixedHeight(24)
            self.kst_chk.setStyleSheet("color:#ffd700;font-weight:bold;font-size:11px;")
            self.kst_chk.stateChanged.connect(lambda _: self._update_display())
            line_bar.addWidget(self.kst_chk)

            self.lbl_hline_info = QLabel("라인/마커: 체크 해제로 삭제")
            self.lbl_hline_info.setStyleSheet("color:#666;font-size:11px;")
            line_bar.addWidget(self.lbl_hline_info)
            line_bar.addStretch()
            chart_v.addLayout(line_bar)

            # 체크박스 바 (라인 + 마커)
            chk_bar = QHBoxLayout(); chk_bar.setSpacing(3)
            chk_bar.addWidget(QLabel("라인:"))
            self._hline_slots = 10
            self._hline_chks  = []
            for i in range(self._hline_slots):
                chk = QCheckBox(str(i+1))
                chk.setEnabled(False); chk.setFixedWidth(34)
                chk.setStyleSheet("color:#444;font-size:10px;")
                slot_idx = i
                chk.stateChanged.connect(
                    lambda state, idx=slot_idx: self._on_hline_chk(idx, state))
                chk_bar.addWidget(chk); self._hline_chks.append(chk)

            chk_bar.addWidget(QLabel("  마커:"))
            self._marker_slots = 5
            self._marker_chks  = []
            for i in range(self._marker_slots):
                chk = QCheckBox(str(i+1))
                chk.setEnabled(False); chk.setFixedWidth(34)
                chk.setStyleSheet("color:#444;font-size:10px;")
                slot_idx = i
                chk.stateChanged.connect(
                    lambda state, idx=slot_idx: self._on_marker_chk(idx, state))
                chk_bar.addWidget(chk); self._marker_chks.append(chk)

            chk_bar.addStretch()
            self.lbl_zoom_time = QLabel("")
            self.lbl_zoom_time.setStyleSheet(
                "color:#ffd700;font-size:11px;font-weight:bold;border:none;")
            chk_bar.addWidget(self.lbl_zoom_time)
            chart_v.addLayout(chk_bar)

            self._hlines: dict = {}
            self._time_markers: dict = {}

            self.gfx = pg.GraphicsLayoutWidget()
            self.p1  = self.gfx.addPlot(row=0, col=0)
            self.p2  = self.gfx.addPlot(row=1, col=0)
            self.p2.setFixedHeight(110); self.p2.setXLink(self.p1)
            self.p1.scene().sigMouseClicked.connect(self._on_chart_click)
            self.p1.getViewBox().sigRangeChanged.connect(self._on_range_changed)
            chart_v.addWidget(self.gfx, 1)
        else:
            chart_v.addWidget(QLabel("pip install pyqtgraph"))

        self._v_splitter.addWidget(chart_w)
        self._v_splitter.setSizes([280, 520])

        self._h_splitter.addWidget(self._v_splitter)
        self._h_splitter.setSizes([255, 1200])

        root.addWidget(self._h_splitter)

    # ── 관심종목 ──────────────────────────────────────────────────
    def _w_add(self):
        t,ok=QInputDialog.getText(self,"추가","심볼:")
        if ok and t.strip(): self.watch_list.addItem(t.strip().upper()); self._save_watchlist()

    def _w_del(self):
        r=self.watch_list.currentRow()
        if r>=0: self.watch_list.takeItem(r); self._save_watchlist()

    # ── 다크/라이트 테마 ─────────────────────────────────────────
    # ── 차트 확대/축소 시 시간대 표시 ────────────────────────────
    def _on_range_changed(self, vb, ranges):
        """p1 ViewBox 범위 변경 → 현재 보이는 시간대를 상단에 표시."""
        if not hasattr(self, 'lbl_zoom_time'): return
        if not hasattr(self, '_x_time_map') or not self._x_time_map: return
        try:
            xmin, xmax = ranges[0]
            keys = sorted(self._x_time_map.keys())
            # 범위 안에 있는 키들만
            vis = [k for k in keys if xmin <= k <= xmax]
            if vis:
                t_start = self._x_time_map.get(vis[0], "")
                t_end   = self._x_time_map.get(vis[-1], "")
                self.lbl_zoom_time.setText(f"📊 {t_start} ~ {t_end}  ({len(vis)}봉)")
        except Exception as e:
            pass

    # ── KST 변환 유틸 ───────────────────────────────────────────
    def _et_to_kst_str(self, et_dt) -> str:
        """ET datetime → KST 시간 문자열 (섬머타임 자동 적용).
        섬머타임: 3월 둘째 일요일 ~ 11월 첫째 일요일
        2025년: 3/9 ~ 11/2  /  2026년: 3/8 ~ 11/1
        ET→UTC +5h(EDT) 또는 +4h(EST), UTC→KST +9h
        """
        try:
            d = et_dt.date() if hasattr(et_dt, 'date') else et_dt
            year = d.year
            # 3월 둘째 일요일 계산
            mar1 = date(year, 3, 1)
            sun_count = 0
            for day_offset in range(31):
                dd = mar1 + timedelta(days=day_offset)
                if dd.weekday() == 6:
                    sun_count += 1
                    if sun_count == 2:
                        dst_start = dd; break
            # 11월 첫째 일요일 계산
            nov1 = date(year, 11, 1)
            for day_offset in range(7):
                dd = nov1 + timedelta(days=day_offset)
                if dd.weekday() == 6:
                    dst_end = dd; break
            is_dst = dst_start <= d < dst_end
            offset_h = 13 if is_dst else 14   # KST = ET + 13h(EDT) / +14h(EST)
            kst = et_dt + timedelta(hours=offset_h)
            return kst.strftime('%m/%d %H:%M')
        except Exception:
            return "??:??"

    def _fmt_time(self, et_dt) -> str:
        """KST 체크박스 상태에 따라 ET 또는 KST 문자열 반환."""
        use_kst = hasattr(self, 'kst_chk') and self.kst_chk.isChecked()
        if use_kst:
            return self._et_to_kst_str(et_dt)
        return et_dt.strftime('%m/%d %H:%M')

    # ── 시간 마커 추가 (슬롯 기반) ──────────────────────────────
    def _add_time_marker(self):
        """입력된 HH:MM 시간에 수직 마커 라인을 긋는다 (슬롯 1-5)."""
        if not PG or not hasattr(self, 'p1'):
            self.lbl_hline_info.setText("⚠ 차트 미초기화"); return
        if not hasattr(self, '_x_time_map') or not self._x_time_map:
            self.lbl_hline_info.setText("⚠ 차트 데이터 없음 — 먼저 데이터를 로드하세요"); return
        txt = self.time_marker_in.text().strip()
        if not txt:
            self.lbl_hline_info.setText("⚠ 시간을 입력하세요 (예: 10:30)"); return
        try:
            h, m = map(int, txt.split(":"))
        except:
            self.lbl_hline_info.setText("⚠ 형식 오류: HH:MM 으로 입력 (예: 10:30)"); return

        target_time = f"{h:02d}:{m:02d}"
        target_min  = h * 60 + m

        # KST 모드이면 입력값도 KST로 간주 → ET로 역변환해서 탐색
        use_kst = hasattr(self, 'kst_chk') and self.kst_chk.isChecked()

        best_x, best_t, best_diff = None, None, float('inf')
        for x, t_str in self._x_time_map.items():
            t_part = t_str[-5:]  # HH:MM (ET 또는 KST, 표시 방식과 동일)
            diff = abs(self._time_to_min(t_part) - target_min)
            if diff < best_diff:
                best_diff = diff; best_x = x; best_t = t_part
        if best_x is None:
            self.lbl_hline_info.setText("⚠ 해당 시간 데이터 없음"); return

        # 빈 슬롯 탐색
        slot = None
        for i in range(self._marker_slots):
            if i not in self._time_markers:
                slot = i; break
        if slot is None:
            self.lbl_hline_info.setText("⚠ 마커 슬롯 5개 꽉 참 — 체크 해제로 삭제"); return

        pen = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
        marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
        marker._marker_time = target_time
        marker._marker_slot = slot
        try:
            marker.setLabel(target_time, position=0.95,
                            color='#ff9800', fill=(50,30,0,120))
        except AttributeError:
            try:
                lbl = pg.InfLineLabel(marker, target_time, position=0.95,
                                      color='#ff9800', fill=(50,30,0,120))
                marker._inf_label = lbl
            except Exception:
                pass
        self.p1.addItem(marker)
        self._time_markers[slot] = {'time': target_time, 'line': marker}

        # 체크박스 활성화
        chk = self._marker_chks[slot]
        chk.blockSignals(True)
        chk.setChecked(True)
        chk.setEnabled(True)
        chk.setStyleSheet("color:#ff9800;font-size:10px;font-weight:bold;")
        chk.setToolTip(target_time)
        chk.blockSignals(False)
        self.lbl_hline_info.setText(
            f"마커[{slot+1}] {target_time} → x={best_x}  (총 {len(self._time_markers)}개)")

    def _on_marker_chk(self, slot_idx: int, state: int):
        """마커 체크박스 해제 → 해당 슬롯 마커 삭제."""
        if state == Qt.Checked: return
        if slot_idx not in self._time_markers: return
        info = self._time_markers.pop(slot_idx)
        try: self.p1.removeItem(info['line'])
        except: pass
        chk = self._marker_chks[slot_idx]
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.setEnabled(False)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.setToolTip("")
        chk.blockSignals(False)
        self.lbl_hline_info.setText(
            f"마커 [{slot_idx+1}] 삭제됨  (남은 {len(self._time_markers)}개)")

    def _time_to_min(self, t_str):
        try:
            h, m = map(int, t_str.split(":"))
            return h*60 + m
        except:
            return 0

    # ── 차트 가로 라인 긋기 (슬롯 기반) ─────────────────────────
    def _on_chart_click(self, event):
        """p1 클릭 → 라인 긋기 모드일 때 빈 슬롯에 수평선 추가."""
        if not hasattr(self, 'btn_hline'): return
        if not self.btn_hline.isChecked(): return
        try:
            pos   = self.p1.vb.mapSceneToView(event.scenePos())
            price = round(pos.y(), 2)
            # 이미 같은 가격이면 무시
            for s in self._hlines.values():
                if abs(s['price'] - price) < 0.01: return
            # 빈 슬롯 탐색
            slot = None
            for i in range(self._hline_slots):
                if i not in self._hlines:
                    slot = i; break
            if slot is None:
                self.lbl_hline_info.setText("⚠ 슬롯 10개 꽉 참 — 체크 해제로 삭제")
                return
            pen  = pg.mkPen('#00e5ff', width=1, style=Qt.DashLine)
            line = pg.InfiniteLine(pos=price, angle=0, pen=pen, movable=True)
            line.setToolTip(f"[{slot+1}] {price:,.2f}")
            self.p1.addItem(line)
            self._hlines[slot] = {'price': price, 'line': line}
            # 체크박스 활성화
            chk = self._hline_chks[slot]
            chk.blockSignals(True)
            chk.setChecked(True)
            chk.setEnabled(True)
            chk.setStyleSheet(f"color:#00e5ff;font-size:10px;font-weight:bold;")
            chk.setToolTip(f"{price:,.2f}")
            chk.blockSignals(False)
            self.lbl_hline_info.setText(
                f"[{slot+1}] {price:,.2f}  (총 {len(self._hlines)}개)")
        except Exception as e:
            print(f"[hline] {e}")

    def _on_hline_chk(self, slot_idx: int, state: int):
        """체크박스 해제 → 해당 슬롯 라인 삭제."""
        if state == Qt.Checked: return   # 체크할 때는 무시
        if slot_idx not in self._hlines: return
        info = self._hlines.pop(slot_idx)
        try: self.p1.removeItem(info['line'])
        except: pass
        chk = self._hline_chks[slot_idx]
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.setEnabled(False)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.setToolTip("")
        chk.blockSignals(False)
        self.lbl_hline_info.setText(f"라인 [{slot_idx+1}] 삭제됨  (남은 {len(self._hlines)}개)")

    def _del_hlines(self):
        """등록된 가로 라인 전체 삭제 (하위 호환용, 더이상 버튼 없음)."""
        for info in self._hlines.values():
            try: self.p1.removeItem(info['line'])
            except: pass
        self._hlines.clear()
        for i, chk in enumerate(self._hline_chks):
            chk.blockSignals(True)
            chk.setChecked(False); chk.setEnabled(False)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.blockSignals(False)
        if hasattr(self,'lbl_hline_info'):
            self.lbl_hline_info.setText("라인 전체 삭제 완료")

    def _redraw_hlines(self):
        """차트 재렌더링 후 저장된 라인을 다시 그림."""
        for slot, info in list(self._hlines.items()):
            price = info['price']
            try: self.p1.removeItem(info['line'])
            except: pass
            pen  = pg.mkPen('#00e5ff', width=1, style=Qt.DashLine)
            line = pg.InfiniteLine(pos=price, angle=0, pen=pen, movable=True)
            line.setToolTip(f"[{slot+1}] {price:,.2f}")
            self.p1.addItem(line)
            self._hlines[slot]['line'] = line

    def _redraw_time_markers(self):
        """차트 재렌더링 후 시간 마커를 다시 그림 (슬롯 dict 기반)."""
        if not hasattr(self, '_time_markers'): return
        if not hasattr(self, '_x_time_map') or not self._x_time_map: return
        for slot, info in list(self._time_markers.items()):
            try: self.p1.removeItem(info['line'])
            except: pass
            m_time = info['time']
            target_min = self._time_to_min(m_time)
            best_x, best_diff = None, float('inf')
            for x, t_str in self._x_time_map.items():
                t_part = t_str[-5:]
                diff = abs(self._time_to_min(t_part) - target_min)
                if diff < best_diff:
                    best_diff = diff; best_x = x
            if best_x is None: continue
            pen = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
            marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
            marker._marker_time = m_time
            marker._marker_slot = slot
            try:
                marker.setLabel(m_time, position=0.95,
                                color='#ff9800', fill=(50,30,0,120))
            except AttributeError:
                try:
                    pg.InfLineLabel(marker, m_time, position=0.95,
                                    color='#ff9800', fill=(50,30,0,120))
                except Exception:
                    pass
            self.p1.addItem(marker)
            self._time_markers[slot]['line'] = marker

    def _on_dark(self, dark: bool = None):
        """TabWrapper에서 dark_mode를 설정한 뒤 호출하거나, 직접 bool 전달."""
        if dark is not None:
            self.dark_mode = dark
        self._apply_theme()
        self._update_display()

    def _apply_theme(self):
        C = _THEME[self.dark_mode]
        # ── 전체 위젯 스타일시트
        self.setStyleSheet(f"""
            QWidget      {{ background:{C['widget_bg']}; color:{C['fg']}; }}
            QGroupBox    {{ border:1px solid {C['border']}; border-radius:4px;
                           margin-top:8px; padding-top:6px; font-weight:bold; }}
            QGroupBox::title {{ subcontrol-origin:margin; left:6px; color:{C['accent']}; }}
            QLineEdit, QSpinBox, QListWidget, QCalendarWidget
                         {{ background:{C['panel_bg']}; color:{C['fg']};
                            border:1px solid {C['border']}; border-radius:3px; }}
            QPushButton  {{ background:{C['panel_bg']}; color:{C['fg']};
                            border:1px solid {C['border']}; border-radius:3px;
                            padding:2px 6px; }}
            QPushButton:hover {{ background:{C['accent']}; color:#ffffff; }}
            QComboBox    {{ background:{C['panel_bg']}; color:{C['fg']};
                            border:1px solid {C['border']}; border-radius:3px; }}
            QComboBox QAbstractItemView
                         {{ background:{C['panel_bg']}; color:{C['fg']};
                            selection-background-color:{C['tbl_sel']}; }}
            QTableWidget {{ background:{C['tbl_bg']}; color:{C['fg']};
                            gridline-color:{C['border']}; border:1px solid {C['border']}; }}
            QTableWidget::item:selected {{ background:{C['tbl_sel']}; }}
            QHeaderView::section {{ background:{C['hdr_bg']}; color:{C['hdr_fg']};
                                    border:1px solid {C['border']}; padding:3px; }}
            QCheckBox, QRadioButton {{ color:{C['fg']}; background:transparent; }}
            QLabel       {{ color:{C['fg']}; background:transparent; }}
            QFrame[frameShape="4"] {{ color:{C['border']}; }}
            QScrollArea  {{ border:none; background:{C['widget_bg']}; }}
            QScrollBar:vertical {{ background:{C['widget_bg']}; width:8px; }}
            QScrollBar::handle:vertical {{ background:{C['scrollbar']};
                                          border-radius:4px; min-height:20px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        # ── 차트 배경
        if PG and hasattr(self, 'gfx'):
            self.gfx.setBackground(C['chart_bg'])
            for pl in (self.p1, self.p2):
                pl.getAxis('bottom').setPen(pg.mkPen(C['fg']))
                pl.getAxis('left').setPen(pg.mkPen(C['fg']))
                pl.getAxis('bottom').setTextPen(pg.mkPen(C['fg']))
                pl.getAxis('left').setTextPen(pg.mkPen(C['fg']))
        # ── 실시간 버튼은 고유색 유지 (테마 덮어쓰기 방지)
        if self.is_rt:
            self.btn_rt.setStyleSheet(
                "background:#8b0000;color:#fff;font-weight:bold;"
                "padding:4px;border-radius:3px;")
        else:
            self.btn_rt.setStyleSheet(
                "background:#1a6b3c;color:#fff;font-weight:bold;"
                "padding:4px;border-radius:3px;")

    def _c_up(self): return _THEME[self.dark_mode]['candle_up']
    def _c_dn(self): return _THEME[self.dark_mode]['candle_dn']

    # ── 모드 변경 ────────────────────────────────────────────────
    def _on_mode_change(self):
        self.mode="ibkr" if self.radio_ibkr.isChecked() else "polygon"
        self.lbl_mode.setText("IBKR API" if self.mode=="ibkr" else "Polygon.io")

    # ── 실시간 시작/중지 ─────────────────────────────────────────
    def _on_rt_btn(self):
        if self.is_rt: self._stop_rt()
        else: self.start_stream(self.sym_in.text())

    def start_stream(self, symbol):
        symbol=symbol.upper().strip()
        if not symbol: return
        self.sym_in.setText(symbol); self.current_sym=symbol
        self._stop_rt(); self.is_rt=True; self.selected_date=None; self._right_row=0
        if self.mode=="ibkr":
            if not self.mw.connected:
                QMessageBox.warning(self,"미연결","TWS에 연결하세요.")
                self.is_rt=False; return
            auto_mdt(self.mw.ib)      # 장외/주말 → DELAYED 자동 전환
            self.ibkr_timer=IBKRBarTimer(self.mw.ib,symbol,parent=self)
            self.ibkr_timer.bar_updated.connect(self._on_bar_in)
            self.ibkr_timer.start(5000); self.lbl_mode.setText(f"▶ IBKR {symbol}")
        else:
            if not self.api_key:
                QMessageBox.warning(self,"API 키 없음","api_key.txt에 Polygon API 키를 저장하세요.")
                self.is_rt=False; return
            self._fetch_missing_polygon(symbol)
            self.worker=PolygonWorker(self.api_key,symbol)
            self.worker.data_received.connect(self._on_bar_in)
            self.worker.start(); self.lbl_mode.setText(f"▶ Polygon {symbol}")
        self.btn_rt.setText("⏹ 중지"); self.btn_rt.setChecked(True)
        self.btn_rt.setStyleSheet(
            "background:#8b0000;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
        self.status_lbl.setText(f"▶ {symbol} 실시간 (ET)")

    def _stop_rt(self):
        if self.worker: self.worker.stop(); self.worker.wait(); self.worker=None
        if self.ibkr_timer: self.ibkr_timer.stop(); self.ibkr_timer=None
        self.is_rt=False
        self.btn_rt.setText("▶ 실시간 시작"); self.btn_rt.setChecked(False)
        self.btn_rt.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
        self.lbl_mode.setText("Polygon.io" if self.mode=="polygon" else "IBKR API")
        self.status_lbl.setText("⏹ 중지됨")

    # ── 바 수신 ──────────────────────────────────────────────────
    def _on_bar_in(self, data):
        if isinstance(data, dict):
            self.df_raw.append(data)
        fx=float(self.fx_in.text() or 1480); limit=float(self.high_in.text() or 3000)
        c=data.get('c',data.get('close',0)); v=data.get('v',data.get('volume',0))
        eok=(c*v*fx)/100_000_000
        if eok>=limit: self._append_right(data,eok)
        self._update_display()

    # ── Polygon 과거 보완 ─────────────────────────────────────────
    def _fetch_missing_polygon(self, symbol):
        if not PANDAS: return
        now=datetime.now()
        if _USE_DATA_IO:
            df=load_month(symbol,now.year,now.month)
            if not df.empty:
                self.df=df; self.df_raw=df.to_dict('records'); return
        url=(f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
             f"/{(now-timedelta(days=2)).strftime('%Y-%m-%d')}/{now.strftime('%Y-%m-%d')}"
             f"?apiKey={self.api_key}&limit=50000")
        try:
            r=requests.get(url,timeout=10).json()
            if 'results' in r: self.df_raw.extend(r['results'])
        except Exception as e: print(f"[ChartTab] Polygon 보완: {e}")

    # ── 캘린더 과거 조회 ─────────────────────────────────────────
    def _on_calendar(self, qdate=None):
        self._stop_rt()
        qd = self.calendar.selectedDate()
        tgt = date(qd.year(), qd.month(), qd.day())
        self.selected_date = tgt
        sym = self.sym_in.text().upper()

        # 연속보기 활성 시 분기
        if self._multi_day_active:
            self._do_multi_day(self._multi_day_count)
            return

        if self.mode == "ibkr" and self.mw.connected:
            self._fetch_ibkr_history(sym, tgt)
        else:
            self._fetch_polygon_history(sym, tgt)

    # ── 연속보기 체크박스 ─────────────────────────────────────────
    def _on_multi_chk(self, days: int, chk, state: int):
        if state == Qt.Checked:
            # 다른 체크박스 해제
            for d, c in self.multi_chks.items():
                if d != days:
                    c.blockSignals(True); c.setChecked(False); c.blockSignals(False)
            self._multi_day_active = True
            self._multi_day_count  = days
            self._do_multi_day(days)
        else:
            self._multi_day_active = False
            self._multi_day_count  = 1
            self._on_calendar()

    def _do_multi_day(self, num_days: int):
        symbol = self.sym_in.text().upper().strip()
        qd = self.calendar.selectedDate()
        end_date = date(qd.year(), qd.month(), qd.day())

        frames, collected, d, attempts = [], 0, end_date, 0
        while collected < num_days and attempts < num_days + 14:
            attempts += 1
            f = self._load_day_df(symbol, d)
            if f is not None and not f.empty:
                frames.insert(0, f); collected += 1
            d -= timedelta(days=1)

        if not frames:
            QMessageBox.warning(self, "데이터 없음", "연속 데이터를 불러올 수 없습니다.")
            return

        self.df_raw = []
        for f in frames:
            self.df_raw.extend(f.to_dict('records'))
        self.selected_date = end_date
        self.status_lbl.setText(f"📅 {num_days}일 연속 (ET, 정규장)")
        self._update_display(force_regular=True)
        if PG: self.p1.autoRange()
        self._push_trend_df()              # ← [v6.3 추가] Tab4 push

    def _fetch_ibkr_history(self, symbol, tgt):
        if not self.mw.connected: QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        auto_mdt(self.mw.ib)          # 과거 데이터도 장외엔 DELAYED 필요
        c=make_und_contract(symbol)
        end_s=datetime.combine(tgt,time(23,59,59)).strftime("%Y%m%d %H:%M:%S")
        self.df_raw.clear()
        self.mw.ib.reqHistoricalData(REQ_HIST,c,end_s,"1 D","1 min","TRADES",1,1,False,[])
        bridge.hist_bar.connect(self._on_ibkr_hist_bar)
        bridge.hist_end.connect(self._on_ibkr_hist_end)

    def _on_ibkr_hist_bar(self, rid, bar):
        if rid!=REQ_HIST: return
        try:
            dt=datetime.strptime(bar.date,"%Y%m%d  %H:%M:%S")
            self.df_raw.append({"t":int(dt.timestamp()*1000),
                "o":bar.open,"h":bar.high,"l":bar.low,"c":bar.close,"v":bar.volume})
        except: pass

    def _on_ibkr_hist_end(self, rid):
        if rid!=REQ_HIST: return
        try: bridge.hist_bar.disconnect(self._on_ibkr_hist_bar)
        except: pass
        try: bridge.hist_end.disconnect(self._on_ibkr_hist_end)
        except: pass
        self._update_display()
        # ── [v6.3 추가] IBKR 수신 완료 후 Tab4 push ──────────────
        if PANDAS and self.df_raw:
            try:
                self.df = pd.DataFrame(self.df_raw)
            except Exception:
                pass
        self._push_trend_df()

    # ── [v9.1 이식] 데이터 로드 — pickle → CSV → API 삼단 fallback ──
    def _load_day_df(self, symbol: str, tgt) -> "pd.DataFrame | None":
        """
        우선순위:
          1) data_io.py 스타일 pickle
             DATA_ROOT/{SYM}/minute/{year}/{month:02d}/{SYM}_{year}_{month:02d}.pkl
          2) 레거시 CSV
             DATA_ROOT/{SYM}/{YYYYMM}.csv
          3) Polygon REST API → CSV 저장
        """
        if not PANDAS: return None
        symbol_up = symbol.upper()
        year, month = tgt.year, tgt.month

        # ① pickle (data_io 포맷)
        pkl_dir  = DATA_ROOT / symbol_up / "minute" / str(year) / f"{month:02d}"
        pkl_path = pkl_dir / f"{symbol_up}_{year}_{month:02d}.pkl"
        if pkl_path.exists():
            try:
                full = pd.read_pickle(str(pkl_path))
                full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                              .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
                res = full[full['_d'] == tgt].copy()
                if not res.empty:
                    return res.drop(columns=['_d'])
            except Exception as ex:
                print(f"[ChartTab] pickle 읽기 실패 ({pkl_path}): {ex}")

        # ② 레거시 CSV
        month_str = tgt.strftime("%Y%m")
        csv_dir  = DATA_ROOT / symbol_up
        csv_path = csv_dir / f"{month_str}.csv"
        if csv_path.exists():
            try:
                full = pd.read_csv(str(csv_path))
                full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                              .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
                res = full[full['_d'] == tgt].copy()
                if not res.empty:
                    return res.drop(columns=['_d'])
            except Exception as ex:
                print(f"[ChartTab] CSV 읽기 실패 ({csv_path}): {ex}")

        # ③ API 다운로드 → CSV 저장
        self._download_day(symbol_up, tgt, csv_path)
        if csv_path.exists():
            try:
                full = pd.read_csv(str(csv_path))
                full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                              .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
                res = full[full['_d'] == tgt].copy()
                if not res.empty:
                    return res.drop(columns=['_d'])
            except Exception as ex:
                print(f"[ChartTab] API 다운로드 후 CSV 읽기 실패: {ex}")
        return None

    def _download_day(self, symbol: str, tgt, fp: "Path"):
        """특정 날짜 1분봉을 Polygon REST API에서 받아 CSV에 병합 저장"""
        if not self.api_key: return
        ds = tgt.strftime("%Y-%m-%d")
        url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/minute"
               f"/{ds}/{ds}?apiKey={self.api_key}&limit=50000")
        try:
            r = requests.get(url, timeout=15).json()
            if 'results' in r and r['results']:
                ndf = pd.DataFrame(r['results'])
                fp.parent.mkdir(parents=True, exist_ok=True)
                if fp.exists():
                    ndf = (pd.concat([pd.read_csv(str(fp)), ndf])
                           .drop_duplicates(subset=['t']).reset_index(drop=True))
                ndf.to_csv(str(fp), index=False)
        except Exception as e:
            print(f"[ChartTab] _download_day: {e}")

    # ── [v6.3 추가] Tab4 추세판으로 DF push ──────────────────────
    def _push_trend_df(self):
        """
        현재 self.df (1분봉 DataFrame)를 Tab4 TrendScorePanel로 전달.
        df 컬럼: t(ms timestamp), o, h, l, c, v
                 → TrendAnalyzer 내부에서 소문자 컬럼으로 rename됨
        """
        if not PANDAS or self.df is None or self.df.empty:
            return
        try:
            combo = getattr(self.mw, 'tab_combo', None)
            if combo and hasattr(combo, 'set_trend_df'):
                # Polygon/IBKR 컬럼명 통일 (o→open 등)
                col_map = {'o':'open','h':'high','l':'low','c':'close','v':'volume'}
                df_out = self.df.rename(columns=col_map)
                combo.set_trend_df(df_out)
        except Exception as e:
            print(f"[ChartGrid] _push_trend_df 오류: {e}")

    def _fetch_polygon_history(self, symbol, tgt):
        """캘린더 클릭 → _load_day_df 삼단 fallback 사용"""
        df = self._load_day_df(symbol, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict('records')
            self.status_lbl.setText(f"📅 {tgt} 복기 (ET)")
            self._update_display()
            self.p1.autoRange()
            self._push_trend_df()          # ← [v6.3 추가] Tab4 push
        else:
            QMessageBox.warning(self, "데이터 없음",
                                f"{tgt} 데이터가 없습니다.\n(휴장일 또는 API 오류)")

    # ── 디스플레이 업데이트 (ET 필터링 + 캔들 렌더링) ───────────
    def _update_display(self, force_regular=False):
        raw=self.df_raw
        if not raw: return
        if not PG: return
        fx=float(self.fx_in.text() or 1480); limit=float(self.high_in.text() or 3000)

        def get_et(r):
            try:
                if PANDAS:
                    return pd.Timestamp(r['t'],unit='ms',tz='UTC').tz_convert('America/New_York')
                else:
                    return datetime.utcfromtimestamp(r['t']/1000)
            except: return None

        holding=(self.holding_chk.isChecked() and not self.is_rt and not force_regular)
        filtered=[]
        for r in sorted(raw,key=lambda x:x.get('t',0)):
            et=get_et(r)
            if et is None: continue
            et_t=et.time() if PANDAS else et.time()
            if holding:
                if not ((time(15,0)<=et_t<time(16,0)) or (time(9,30)<=et_t<=time(10,30))):
                    continue
            else:
                if not (time(9,30)<=et_t<time(16,0)): continue
            filtered.append((r,et))
        if not filtered: return
        if self.is_rt: filtered=filtered[-self.candle_spin.value():]

        self.p1.clear(); self.p2.clear()
        p_data=[]; v_h=[]; v_b=[]; x_t=[]
        hi_rows=[]; prev_d=None; date_bounds=[]
        # x 인덱스 → 시간 문자열 전체 매핑 (스크롤/줌 시 시간대 표시용)
        self._x_time_map = {}
        for i,(r,et) in enumerate(filtered):
            o=r.get('o',r.get('open',0)); c_=r.get('c',r.get('close',0))
            lo=r.get('l',r.get('low',0)); hi=r.get('h',r.get('high',0))
            v=r.get('v',r.get('volume',0))
            eok=(c_*v*fx)/100_000_000
            cur_d=et.date() if PANDAS else et.date()
            if prev_d and cur_d!=prev_d: date_bounds.append(i-0.5)
            prev_d=cur_d
            p_data.append((i,o,c_,lo,hi))
            v_h.append(v); v_b.append(self._c_up() if c_>=o else self._c_dn())
            t_str = self._fmt_time(et)
            self._x_time_map[i] = t_str   # 전체 매핑
            if i%30==0: x_t.append((i, t_str))
            if eok>=limit: hi_rows.append((i,r,et,eok))
        self.p1.addItem(CandlestickItem(p_data,self._c_up(),self._c_dn()))
        self.p2.addItem(pg.BarGraphItem(x=range(len(v_h)),height=v_h,width=0.6,brushes=v_b))
        for bx in date_bounds:
            for pl in (self.p1,self.p2):
                pl.addItem(pg.InfiniteLine(pos=bx,angle=90,
                    pen=pg.mkPen('#ff6600',width=2,style=Qt.DashLine)))
        for pl in (self.p1,self.p2): pl.getAxis('bottom').setTicks([x_t])
        # 시간 마커 재그리기 (차트 갱신 후)
        self._redraw_time_markers()
        # 저장된 가로 라인 재그리기
        self._redraw_hlines()
        self.current_processed=[(r,et,eok) for _,r,et,eok in hi_rows]
        # 왼쪽 테이블 (숫자에 , 구분자 적용)
        hi_sorted=sorted(hi_rows,key=lambda x:-x[3])
        C = _THEME[self.dark_mode]
        self.table_l.setRowCount(len(hi_sorted))
        for ri,(i,r,et,eok) in enumerate(hi_sorted):
            et_s=et.strftime('%H:%M:%S')
            vals=[et_s,
                  f"{r.get('o',0):,.2f}",f"{r.get('h',0):,.2f}",
                  f"{r.get('l',0):,.2f}",f"{r.get('c',0):,.2f}",
                  f"{eok:,.2f}"]
            for ci,v in enumerate(vals):
                it=QTableWidgetItem(str(v)); it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(C['fg']))
                self.table_l.setItem(ri,ci,it)
                if ci==5:
                    bg=(C['row_hi'] if eok>=5000 else (C['row_mid'] if eok>=3000 else C['row_lo']))
                    self.table_l.item(ri,ci).setBackground(QColor(bg))

    # ── 대량체결 우측 테이블 ─────────────────────────────────────
    def _append_right(self, data, eok):
        C = _THEME[self.dark_mode]
        try: et_s=(pd.Timestamp(data['s'],unit='ms',tz='UTC')
                   .tz_convert('America/New_York').strftime('%H:%M:%S') if PANDAS else ts())
        except: et_s=ts()
        r=self.table_r.rowCount(); self.table_r.insertRow(r)
        vals=[et_s,
              f"{data.get('o',0):,.2f}",f"{data.get('h',0):,.2f}",
              f"{data.get('l',0):,.2f}",f"{data.get('c',0):,.2f}",
              f"{eok:,.2f}","실시간"]
        for ci,v in enumerate(vals):
            it=QTableWidgetItem(str(v)); it.setTextAlignment(Qt.AlignCenter)
            it.setForeground(QColor(C['fg']))
            self.table_r.setItem(r,ci,it)
            if ci==5:
                bg=(C['row_hi'] if eok>=5000 else (C['row_mid'] if eok>=3000 else C['row_lo']))
                self.table_r.item(r,ci).setBackground(QColor(bg))
        self.table_r.scrollToBottom()

    def _clr_right(self): self.table_r.setRowCount(0)

    # ── [v9.1 이식] FTD / 공매도 보조 파일 (7컬럼 풀버전) ─────────
    def _load_aux_file(self):
        C = _THEME[self.dark_mode]           # 현재 테마 팔레트
        sym = self.file_sym_in.text().strip().lower() or self.sym_in.text().strip().lower()
        if not sym:
            self.file_status_lbl.setText("⚠ 종목을 입력하세요"); return
        file_type = self.file_type_combo.currentIndex()
        if file_type == 0:
            fp = DATA_ROOT / f"nyse-{sym}.fails_to_deliver.csv"; label = "FTD"
        else:
            fp = DATA_ROOT / f"nyse-{sym}.short_volume.csv";     label = "공매도"
        if not fp.exists():
            self.file_status_lbl.setText(f"❌ 파일 없음: {fp.name}")
            self.file_status_lbl.setStyleSheet("font-size:11px;color:red;"); return
        if not PANDAS:
            self.file_status_lbl.setText("❌ pandas 미설치"); return

        df = None
        try:
            df = pd.read_csv(str(fp), encoding='latin-1', sep=None, engine='python')
        except Exception:
            try:
                from io import StringIO
                with open(str(fp), 'rb') as f:
                    raw = f.read().decode('latin-1', errors='replace')
                df = pd.read_csv(StringIO(raw), sep=None, engine='python')
            except Exception as ex:
                self.file_status_lbl.setText(f"❌ 파일 읽기 실패: {str(ex)[:50]}")
                self.file_status_lbl.setStyleSheet("font-size:11px;color:red;"); return

        df.columns = [c.strip() for c in df.columns]

        def clean(val):
            v = str(val).strip().replace(",", "").replace(" ", "")
            return v if v not in ("", "-") else "0"

        self.table_r.setRowCount(0)

        # 날짜 셀 클릭 → 차트 이동
        try:
            self.table_r.cellClicked.disconnect(self._on_aux_date_click)
        except Exception:
            pass
        self.table_r.cellClicked.connect(self._on_aux_date_click)

        try:
            if file_type == 0:
                # ── FTD ─────────────────────────────────────────
                date_col = "settlement"
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(
                        df[date_col].astype(str).str.strip(),
                        format="%Y%m%d", errors='coerce')
                    df = df.sort_values(date_col, ascending=False).reset_index(drop=True)

                self.table_r.setColumnCount(7)
                self.table_r.setHorizontalHeaderLabels(
                    ["결제일", "FTD수량", "가격($)", "변화량", "명목금액($)", "T+35일", "구분"])

                for _, row in df.iterrows():
                    ri = self.table_r.rowCount(); self.table_r.insertRow(ri)
                    raw_d = row.get(date_col, None)
                    settle_val = (raw_d.strftime("%Y-%m-%d")
                                  if pd.notna(raw_d) and hasattr(raw_d, 'strftime')
                                  else str(row.get(date_col, "-")).strip())
                    vals = [settle_val,
                            clean(row.get("ftd", row.get(" ftd ", "0"))),
                            clean(row.get("price", "0")),
                            clean(row.get("change", "0")),
                            clean(row.get("notional", row.get(" notional ", "0"))),
                            str(row.get("t35", "-")).strip(), label]
                    for j, v in enumerate(vals):
                        it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter)
                        it.setForeground(QColor(C['fg']))
                        if j == 1:
                            try:
                                q = float(v)
                                if   q >= 500_000: it.setBackground(QColor(C['row_hi']))
                                elif q >= 100_000: it.setBackground(QColor(C['row_mid']))
                                elif q >= 10_000:  it.setBackground(QColor(C['row_lo']))
                            except: pass
                        if j == 3:
                            try:
                                fv = float(v)
                                if fv < 0: it.setForeground(QColor("#ff5555"))
                                elif fv > 0: it.setForeground(QColor("#55cc55"))
                            except: pass
                        self.table_r.setItem(ri, j, it)

            else:
                # ── 공매도 ──────────────────────────────────────
                date_col = "Date"
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(
                        df[date_col].astype(str).str.strip(),
                        infer_datetime_format=True, errors='coerce')
                    df = df.sort_values(date_col, ascending=False).reset_index(drop=True)

                self.table_r.setColumnCount(7)
                self.table_r.setHorizontalHeaderLabels(
                    ["날짜", "총보고량", "총공매도", "총롱", "공매도비율(%)", "FINRA", "구분"])

                for _, row in df.iterrows():
                    ri = self.table_r.rowCount(); self.table_r.insertRow(ri)
                    raw_d = row.get(date_col, None)
                    date_val = (raw_d.strftime("%Y-%m-%d")
                                if pd.notna(raw_d) and hasattr(raw_d, 'strftime')
                                else str(row.get(date_col, "-")).strip())
                    reported = clean(row.get("total_reported", "0"))
                    short    = clean(row.get("total_short",    "0"))
                    long_    = clean(row.get("total_long",     "0"))
                    finra    = clean(row.get("FINRA",          "0"))
                    ratio_r  = row.get("Short_ratio", None)
                    if ratio_r is not None and str(ratio_r).strip() not in ("", "-"):
                        try:   ratio_val = f"{float(str(ratio_r).replace(',','')):.2f}"
                        except: ratio_val = "0.00"
                    else:
                        try:
                            s = float(short); rep = float(reported)
                            ratio_val = f"{s/rep*100:.2f}" if rep > 0 else "0.00"
                        except: ratio_val = "0.00"
                    vals = [date_val, reported, short, long_, ratio_val, finra, label]
                    for j, v in enumerate(vals):
                        it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter)
                        it.setForeground(QColor(C['fg']))
                        if j == 4:
                            try:
                                rv = float(v)
                                if   rv >= 60: it.setBackground(QColor(C['row_hi']))
                                elif rv >= 50: it.setBackground(QColor(C['row_mid']))
                                elif rv >= 40: it.setBackground(QColor(C['row_lo']))
                            except: pass
                        if j == 2:
                            try:
                                sv = float(v.replace(",", ""))
                                if   sv >= 50_000_000: it.setBackground(QColor(C['row_hi']))
                                elif sv >= 20_000_000: it.setBackground(QColor(C['row_mid']))
                                elif sv >= 10_000_000: it.setBackground(QColor(C['row_lo']))
                            except: pass
                        self.table_r.setItem(ri, j, it)

            count = self.table_r.rowCount()
            self.file_status_lbl.setText(f"✅ {label} {count}행 로드 (최신순)")
            self.file_status_lbl.setStyleSheet("font-size:11px;color:green;")
            self.table_r.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table_r.scrollToTop()

        except Exception as ex:
            self.file_status_lbl.setText(f"❌ 파싱 오류: {str(ex)[:60]}")
            self.file_status_lbl.setStyleSheet("font-size:11px;color:red;")
            import traceback; traceback.print_exc()

    def _on_aux_date_click(self, row: int, col: int):
        """FTD/공매도 테이블 날짜 셀 클릭 → 해당 날짜 차트 자동 이동"""
        if col != 0: return
        item = self.table_r.item(row, col)
        if not item: return
        date_str = item.text().strip()
        if not date_str or date_str == "-": return

        tgt = None
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                tgt = datetime.strptime(date_str, fmt).date(); break
            except ValueError: continue
        if tgt is None:
            self.file_status_lbl.setText(f"⚠ 날짜 파싱 실패: {date_str}"); return

        sym = self.file_sym_in.text().strip().upper() or self.sym_in.text().strip().upper()
        if not sym:
            self.file_status_lbl.setText("⚠ 종목을 입력하세요"); return

        self._stop_rt()
        self.sym_in.setText(sym)
        self.calendar.setSelectedDate(QDate(tgt.year, tgt.month, tgt.day))

        df = self._load_day_df(sym, tgt)
        if df is None or df.empty:
            self.file_status_lbl.setText(f"⚠ {tgt} 차트 데이터 없음 (휴장일?)")
            self.file_status_lbl.setStyleSheet("font-size:11px;color:orange;"); return

        self.df = df
        self.df_raw = df.to_dict('records')
        self.selected_date = tgt
        self.file_status_lbl.setText(f"✅ {tgt} 차트 로드 완료")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:green;")
        self._update_display()
        if PG: self.p1.autoRange()

    # ── 수급 피크 검색 ────────────────────────────────────────────
    def _peak1(self):
        if not self.current_processed: self.pk1_lbl.setText("데이터 없음"); return
        try:
            t0=datetime.strptime(self.pk1_in.text().strip(),"%H:%M")
            s=(t0-timedelta(minutes=30)).time(); e=(t0+timedelta(minutes=30)).time()
            w=[(r,et,eok) for r,et,eok in self.current_processed if s<=et.time()<=e]
            if not w: self.pk1_lbl.setText("데이터 없음"); return
            mx=max(w,key=lambda x:x[2])
            self.pk1_lbl.setText(f"피크: {mx[1].strftime('%H:%M')}\n최대: {mx[2]:.2f}억")
        except: self.pk1_lbl.setText("형식 오류 (HH:MM)")

    def _peak2(self):
        if not self.current_processed: self.pk2_lbl.setText("데이터 없음"); return
        try:
            s=datetime.strptime(self.pk2_s.text().strip(),"%H:%M").time()
            e=datetime.strptime(self.pk2_e.text().strip(),"%H:%M").time()
            w=[(r,et,eok) for r,et,eok in self.current_processed if s<=et.time()<=e]
            if not w: self.pk2_lbl.setText("데이터 없음"); return
            tot=sum(x[2] for x in w); mx=max(w,key=lambda x:x[2])
            self.pk2_lbl.setText(
                f"합산: {tot:.2f}억 ({len(w)}봉)\n"
                f"피크: {mx[1].strftime('%H:%M')} ({mx[2]:.2f}억)")
        except: self.pk2_lbl.setText("형식 오류 (HH:MM)")

    def _update_peak3(self, tbl):
        rows=set(it.row() for it in tbl.selectedItems())
        total=0.0; times=[]
        for r in sorted(rows):
            ei=tbl.item(r,5); ti=tbl.item(r,0)
            if ei and ti:
                try: total+=float(ei.text()); times.append(ti.text()[:5])
                except: pass
        if rows:
            self.pk3_lbl.setText(
                f"선택 {len(rows)}봉 합산:\n{total:.2f}억\n"
                f"({', '.join(times[:6])}{'...' if len(times)>6 else ''})")
        else: self.pk3_lbl.setText("선택 합산: 0.00억")