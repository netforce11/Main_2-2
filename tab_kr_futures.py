"""
tab_kr_futures.py — 10번 탭: 한국 선물옵션 (KOSPI200)  v2.0
════════════════════════════════════════════════════════════════
레이아웃 (12열 × 5행):
  Row 0 (compact ~50px): 연결|환율/주문가능|만기|행수|▶조회|K200지수
  Row 1-2 (span):
    [1-2, 0-2]  호가창 (체인 클릭 시 갱신)
    [1-2, 3-7]  옵션 체인 (콜 위 / 풋 아래, 세로 절반씩)
    [1-2, 8-11] 잔고 / 미체결 / 정정 탭
  Row 3:
    [3, 0-2]  선택 종목 (Delta·Theta·1계약가 font=15)
    [3, 3-11] 캔들 차트 (pyqtgraph)
  Row 4 (compact): 로그 (2줄 높이)
════════════════════════════════════════════════════════════════
한국 옵션: 1계약 = 250,000원 × pt  /  위클리 화·목 / 월물 2nd목요일
════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta, date as _date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QTextEdit, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSpinBox, QMessageBox, QInputDialog, QSplitter,
    QRadioButton, QButtonGroup, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False


from core import (
    bridge, router,
    GridTab, make_table, tbl_set, ts,
    IBAPI_AVAILABLE,
    save_json, load_json, SAVE_DIR,
    _apply_table_theme,
)

# 구버전 이름 호환 alias
_table_apply_dark = _apply_table_theme

try:
    from ibapi.contract import Contract as IBContract
    from ibapi.order import Order as IBOrder
except ImportError:
    pass

# ── reqId 범위 ──────────────────────────────────────────────
REQ_KR_UND  = 9000
REQ_KR_CALL = 9100   # 9100~9149
REQ_KR_PUT  = 9200   # 9200~9249

KR_MULTIPLIER = 250_000
KR_STEP       = 2.5
KR_CURRENCY   = "KRW"
MON, TUE, WED, THU, FRI = 0, 1, 2, 3, 4


# ══════════════════════════════════════════════════════════════
# 계약 팩토리
# ══════════════════════════════════════════════════════════════
def _make_kr_opt(strike: float, right: str, expiry: str):
    if not IBAPI_AVAILABLE:
        class _C: pass
        c = _C()
    else:
        c = IBContract()
    c.symbol     = "K200"
    c.secType    = "OPT"
    c.exchange   = "KSE"
    c.currency   = KR_CURRENCY
    c.strike     = float(strike)
    c.right      = "C" if right.upper() in ("C","CALL") else "P"
    c.multiplier = "250000"
    c.lastTradeDateOrContractMonth = expiry
    return c

def _make_kr_und():
    if not IBAPI_AVAILABLE:
        class _C: pass
        c = _C()
    else:
        c = IBContract()
    c.symbol   = "K200"; c.secType = "IND"
    c.exchange = "KSE";  c.currency = KR_CURRENCY
    return c

def _make_kr_order(action, qty, otype, lmt=0.0):
    if not IBAPI_AVAILABLE:
        class _O: pass
        o = _O()
    else:
        o = IBOrder()
    o.action        = action.upper()
    o.totalQuantity = qty
    o.orderType     = otype.upper()
    o.lmtPrice      = lmt
    o.tif           = "DAY"
    o.eTradeOnly    = False
    o.firmQuoteOnly = False
    return o


# ══════════════════════════════════════════════════════════════
# 만기일 유틸
# ══════════════════════════════════════════════════════════════
def _kr_2nd_thu(year, month):
    d = _date(year, month, 1); n = 0
    while True:
        if d.weekday() == THU:
            n += 1
            if n == 2: return d
        d += timedelta(days=1)

def build_kr_expiry_list():
    today = _date.today(); seen = set(); entries = []
    for offset in range(28):
        d = today + timedelta(days=offset)
        if d.weekday() in (TUE, THU):
            key = d.strftime("%Y%m%d")
            if key in seen: continue
            seen.add(key)
            wk  = "화" if d.weekday() == TUE else "목"
            pre = "오늘 " if d==today else ("내일 " if d==today+timedelta(1) else "")
            entries.append((f"[위클리{wk}] {pre}{d.strftime('%m/%d')}", key,
                            "W-TUE" if d.weekday()==TUE else "W-THU"))
    for rel in range(2):
        m = today.month + rel; y = today.year
        if m > 12: m -= 12; y += 1
        thu2 = _kr_2nd_thu(y, m)
        key  = thu2.strftime("%Y%m%d")
        if key not in seen:
            seen.add(key)
            entries.append((f"[월물] {thu2.strftime('%Y/%m 2nd목')}", key, "M"))
    entries.sort(key=lambda x: x[1])
    entries.append(("직접입력 YYYYMMDD", "CUSTOM", ""))
    return entries


# ══════════════════════════════════════════════════════════════
# 헬퍼
# ══════════════════════════════════════════════════════════════
def _mk(text, color=None):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    if color: it.setForeground(QBrush(QColor(color)))
    return it

def _kr_table(headers, rows=0):
    t = QTableWidget(rows, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    _table_apply_dark(t, True)
    return t


# ══════════════════════════════════════════════════════════════
# 캔들 아이템
# ══════════════════════════════════════════════════════════════
if PG:
    class _CandleItem(pg.GraphicsObject):
        def __init__(self):
            super().__init__()
            self._data = []; self.picture = None; self._gen()

        def setData(self, data):
            self._data = data; self._gen(); self.update()

        def _gen(self):
            from PyQt5.QtGui import QPainter, QPicture
            self.picture = QPicture()
            if not self._data: return
            p = QPainter(self.picture); w = 0.3
            for (t, o, h, l, c) in self._data:
                p.setPen(pg.mkPen('#666'))
                p.drawLine(pg.Point(t, l), pg.Point(t, h))
                clr = '#26a69a' if c >= o else '#ef5350'
                p.setBrush(pg.mkBrush(clr)); p.setPen(pg.mkPen(clr))
                p.drawRect(pg.QtCore.QRectF(t-w, min(o,c), w*2, abs(c-o)+0.001))
            p.end(); self.informViewBoundsChanged()

        def paint(self, p, *a):
            if self.picture: p.drawPicture(0, 0, self.picture)

        def boundingRect(self):
            if self.picture: return pg.QtCore.QRectF(self.picture.boundingRect())
            return pg.QtCore.QRectF(0,0,1,1)
else:
    class _CandleItem:
        pass


# ══════════════════════════════════════════════════════════════
# Tab 10: KRFuturesGrid
# ══════════════════════════════════════════════════════════════
class KRFuturesGrid(QWidget):
    MAX_CHAIN = 20

    def __init__(self, mw):
        super().__init__()
        self.mw           = mw
        self.und_price    = None
        self.und_prev     = None
        self.und_hist     = []
        self.exch_rate    = 1500.0
        self.call_strikes = []
        self.put_strikes  = []
        self.call_data    = {}   # rid → {row, strike, last, delta, theta}
        self.put_data     = {}
        self._expiry_list = build_kr_expiry_list()
        self._chart_strike = None
        self._chart_side   = None
        self._candle_buf   = []
        self._candle_rid   = -1
        self._positions    = {}
        self._open_orders  = {}
        self._BUF = 300

        self._build()
        self._connect_signals()
        QTimer(self, interval=600_000, timeout=self._refresh_expiry).start()
        QTimer(self, interval=30_000,  timeout=self._req_positions).start()

    # ─────────────────────────────────────────────────────────
    # BUILD  (QSplitter 기반)
    # ─────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        _sh = (  # splitter 핸들 스타일
            "QSplitter::handle:horizontal{"
            "background:#5a5a9a;border-left:2px solid #00aaff;"
            "border-right:2px solid #00aaff;margin:4px 0;}"
            "QSplitter::handle:horizontal:hover{"
            "background:#5dade2;border-left:2px solid #00e676;"
            "border-right:2px solid #00e676;}"
            "QSplitter::handle:vertical{"
            "background:#5a5a9a;border-top:2px solid #00aaff;"
            "border-bottom:2px solid #00aaff;margin:0 4px;}"
            "QSplitter::handle:vertical:hover{"
            "background:#5dade2;border-top:2px solid #00e676;"
            "border-bottom:2px solid #00e676;}"
        )
        _combo_ss = (  # 만기 콤보 드롭다운 색상 (흰색 방지)
            "QComboBox{background:#12122a;color:#ffd700;"
            "border:1px solid #3a3a6a;border-radius:3px;font-size:11px;padding:2px;}"
            "QComboBox QAbstractItemView{"
            "background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;"
            "selection-color:#ffffff;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
        )

        # ── 컨트롤바 ─────────────────────────────────────────
        ctrl = QHBoxLayout(); ctrl.setSpacing(6); ctrl.setContentsMargins(0,0,0,0)

        # 연결
        gb_conn = QGroupBox("IBKR"); hc = QHBoxLayout(gb_conn)
        hc.setSpacing(3); hc.setContentsMargins(4,2,4,2)
        self.btn_conn = QPushButton("연결"); self.btn_conn.setFixedSize(46,22)
        self.lbl_conn = QLabel("● 미연결")
        self.lbl_conn.setStyleSheet("color:#ff4444;font-weight:bold;border:none;")
        # 실시간/지연 표시
        self.lbl_mdt = QLabel("")
        self.lbl_mdt.setStyleSheet("color:#aaa;font-size:10px;border:none;")
        hc.addWidget(self.btn_conn); hc.addWidget(self.lbl_conn)
        hc.addWidget(self.lbl_mdt)
        ctrl.addWidget(gb_conn)

        # 환율 / 주문가능
        gb_exch = QGroupBox("환율/가용"); he = QHBoxLayout(gb_exch)
        he.setSpacing(3); he.setContentsMargins(4,2,4,2)
        he.addWidget(QLabel("환율:"))
        self.edit_exch = QLineEdit("1500"); self.edit_exch.setFixedSize(54,22)
        he.addWidget(self.edit_exch)
        self.lbl_avail = QLabel("주문가능: ―")
        self.lbl_avail.setStyleSheet("color:#00cfff;font-weight:bold;font-size:11px;border:none;")
        he.addWidget(self.lbl_avail)
        ctrl.addWidget(gb_exch)

        # 만기
        gb_exp = QGroupBox("만기"); hx = QHBoxLayout(gb_exp)
        hx.setSpacing(3); hx.setContentsMargins(4,2,4,2)
        self.combo_exp = QComboBox(); self.combo_exp.setFixedHeight(22)
        self.combo_exp.setMinimumWidth(145)
        self.combo_exp.setStyleSheet(_combo_ss)
        for lbl,_,_ in self._expiry_list: self.combo_exp.addItem(lbl)
        self.combo_exp.currentIndexChanged.connect(self._on_exp_change)
        self.edit_custom = QLineEdit()
        self.edit_custom.setPlaceholderText("YYYYMMDD")
        self.edit_custom.setFixedSize(76,22); self.edit_custom.setVisible(False)
        hx.addWidget(self.combo_exp); hx.addWidget(self.edit_custom)
        ctrl.addWidget(gb_exp)

        # 행수 + 조회
        gb_fetch = QGroupBox("조회"); hf = QHBoxLayout(gb_fetch)
        hf.setSpacing(3); hf.setContentsMargins(4,2,4,2)
        hf.addWidget(QLabel("행수:"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(5, self.MAX_CHAIN); self.spin_n.setValue(20)
        self.spin_n.setSuffix("개"); self.spin_n.setFixedSize(62,22)
        hf.addWidget(self.spin_n)
        self.btn_fetch = QPushButton("▶ 조회")
        self.btn_fetch.setFixedSize(58,28)
        self.btn_fetch.setStyleSheet("background:#1a6b3c;color:#fff;font-weight:bold;")
        self.btn_fetch.clicked.connect(self._fetch_chain)
        hf.addWidget(self.btn_fetch)
        ctrl.addWidget(gb_fetch)

        # Zone (ITM / ATM / OTM)
        gb_zone = QGroupBox("Zone"); hz = QHBoxLayout(gb_zone)
        hz.setSpacing(4); hz.setContentsMargins(4,2,4,2)
        self._zone = "ATM"
        self._zone_grp = QButtonGroup(self); self._zone_btns = {}
        for z, lbl_z, col_z in [("ITM","ITM","#aaddff"),
                                  ("ATM","ATM","#ffd700"),
                                  ("OTM","OTM","#ffaaaa")]:
            rb = QRadioButton(lbl_z)
            rb.setStyleSheet(f"color:{col_z};font-weight:bold;font-size:11px;")
            self._zone_grp.addButton(rb); self._zone_btns[z] = rb
            hz.addWidget(rb)
        self._zone_btns["ATM"].setChecked(True)
        self._zone_grp.buttonClicked.connect(self._on_zone_change)
        ctrl.addWidget(gb_zone)

        # 지수 직접 입력
        gb_idx = QGroupBox("기준 지수"); hi = QHBoxLayout(gb_idx)
        hi.setSpacing(3); hi.setContentsMargins(4,2,4,2)
        self.edit_idx_override = QLineEdit()
        self.edit_idx_override.setPlaceholderText("직접입력(예:380.00)")
        self.edit_idx_override.setFixedSize(110, 22)
        self.edit_idx_override.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #4a4a7a;"
            "border-radius:3px;font-size:11px;padding:1px;")
        lbl_idx_help = QLabel("비워두면 K200 자동")
        lbl_idx_help.setStyleSheet("color:#666;font-size:9px;border:none;")
        hi.addWidget(self.edit_idx_override); hi.addWidget(lbl_idx_help)
        ctrl.addWidget(gb_idx)

        # K200 지수
        gb_und = QGroupBox("K200 지수"); hu = QHBoxLayout(gb_und)
        hu.setSpacing(6); hu.setContentsMargins(6,2,6,2)
        self.lbl_und = QLabel("K200: ―")
        self.lbl_und.setFont(QFont("Arial",15,QFont.Bold))
        self.lbl_und.setStyleSheet("color:#ffd700;border:none;")
        self.lbl_und_chg = QLabel("")
        self.lbl_und_chg.setStyleSheet("color:#aaa;font-weight:bold;font-size:11px;border:none;")
        hu.addWidget(self.lbl_und); hu.addWidget(self.lbl_und_chg)
        if PG:
            self._pw_und = pg.PlotWidget(); self._pw_und.setFixedSize(110,40)
            self._pw_und.showGrid(x=False,y=False)
            self._pw_und.getAxis('bottom').setStyle(showValues=False)
            self._pw_und.getAxis('left').setStyle(showValues=False)
            self._pw_und.setBackground((10,10,20))
            self._c_und = self._pw_und.plot(pen=pg.mkPen('#ffd700',width=2))
            hu.addWidget(self._pw_und)
        ctrl.addWidget(gb_und, 1)

        ctrl_w = QWidget(); ctrl_w.setLayout(ctrl)
        ctrl_w.setMinimumHeight(44); ctrl_w.setMaximumHeight(110)

        # ── 수직 splitter ─────────────────────────────────────
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(8)
        self._v_splitter.setStyleSheet(_sh)
        self._v_splitter.setChildrenCollapsible(False)
        self._v_splitter.addWidget(ctrl_w)

        # ── 중단: 수평 splitter (호가 | 체인 | 잔고탭) ───────
        self._mid_splitter = QSplitter(Qt.Horizontal)
        self._mid_splitter.setHandleWidth(8)
        self._mid_splitter.setStyleSheet(_sh)
        self._mid_splitter.setChildrenCollapsible(False)

        # 호가창
        gb_hoga = QGroupBox("호가"); v_hoga = QVBoxLayout(gb_hoga)
        v_hoga.setSpacing(2); v_hoga.setContentsMargins(4,4,4,4)
        self.lbl_hoga_title = QLabel("행사가: ―  |  ―")
        self.lbl_hoga_title.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        v_hoga.addWidget(self.lbl_hoga_title)
        hh = QHBoxLayout()
        cov = QVBoxLayout()
        cov.addWidget(QLabel("▲ CALL"))
        self.tbl_hoga_call = _kr_table(["가격","잔량"],5)
        self.tbl_hoga_call.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        cov.addWidget(self.tbl_hoga_call)
        puv = QVBoxLayout()
        puv.addWidget(QLabel("▼ PUT"))
        self.tbl_hoga_put = _kr_table(["가격","잔량"],5)
        self.tbl_hoga_put.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        puv.addWidget(self.tbl_hoga_put)
        hh.addLayout(cov); hh.addLayout(puv)
        v_hoga.addLayout(hh)
        gb_hoga.setMinimumWidth(150)
        self._mid_splitter.addWidget(gb_hoga)

        # 옵션 체인
        gb_chain = QGroupBox("옵션 체인"); v_chain = QVBoxLayout(gb_chain)
        v_chain.setSpacing(2); v_chain.setContentsMargins(4,4,4,4)
        lbl_c = QLabel("▲ CALL")
        lbl_c.setStyleSheet("color:#33aaff;font-weight:bold;border:none;")
        self.tbl_call = _kr_table(["행사가","현재가","Δ","Θ"])
        self.tbl_call.cellClicked.connect(lambda r,c: self._chain_click(r,c,"C"))
        self.tbl_call.cellDoubleClicked.connect(lambda r,c: self._chain_dbl(r,c,"C"))
        lbl_p = QLabel("▼ PUT")
        lbl_p.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        self.tbl_put = _kr_table(["행사가","현재가","Δ","Θ"])
        self.tbl_put.cellClicked.connect(lambda r,c: self._chain_click(r,c,"P"))
        self.tbl_put.cellDoubleClicked.connect(lambda r,c: self._chain_dbl(r,c,"P"))
        v_chain.addWidget(lbl_c); v_chain.addWidget(self.tbl_call)
        v_chain.addWidget(lbl_p); v_chain.addWidget(self.tbl_put)
        gb_chain.setMinimumWidth(200)
        self._mid_splitter.addWidget(gb_chain)

        # 잔고탭
        self._acct_tab = QTabWidget()
        self._acct_tab.setTabPosition(QTabWidget.North)
        bw = QWidget(); bv = QVBoxLayout(bw); bv.setContentsMargins(2,2,2,2)
        self.tbl_balance = _kr_table(["종목","C/P","수량","평균단가","현재가","PnL(원)"])
        self.tbl_balance.cellDoubleClicked.connect(self._on_bal_dbl)
        bv.addWidget(self.tbl_balance)
        self._acct_tab.addTab(bw,"💼 잔고")
        ow = QWidget(); ov = QVBoxLayout(ow); ov.setContentsMargins(2,2,2,2)
        ov.addWidget(QLabel("더블클릭: 취소"))
        self.tbl_open = _kr_table(["OID","C/P","행사가","수량","주문가","상태"])
        self.tbl_open.cellDoubleClicked.connect(self._on_open_dbl)
        ov.addWidget(self.tbl_open)
        self._acct_tab.addTab(ow,"⏳ 미체결")
        aw = QWidget(); av = QVBoxLayout(aw); av.setContentsMargins(2,2,2,2)
        av.addWidget(QLabel("더블클릭: 정정"))
        self.tbl_amend = _kr_table(["OID","C/P","행사가","수량","주문가","새가격"])
        self.tbl_amend.cellDoubleClicked.connect(self._on_amend_dbl)
        av.addWidget(self.tbl_amend)
        self._acct_tab.addTab(aw,"\u270f\ufe0f 정정")
        self._acct_tab.setMinimumWidth(200)

        # ── 잔고탭 우측 수직 스플리터 (잔고탭 | 빈 공간) ────────
        self._acct_right_splitter = QSplitter(Qt.Horizontal)
        self._acct_right_splitter.setHandleWidth(6)
        self._acct_right_splitter.setStyleSheet(_sh)
        self._acct_right_splitter.setChildrenCollapsible(False)
        self._acct_right_splitter.addWidget(self._acct_tab)

        # 우측 빈 영역 (사용자 자유 활용)
        self._acct_right_panel = QGroupBox("\U0001f4cc 메모 / 추가 정보")
        _arp_v = QVBoxLayout(self._acct_right_panel)
        _arp_v.setContentsMargins(4,4,4,4)
        self._acct_memo = QTextEdit()
        self._acct_memo.setPlaceholderText(
            "이 공간은 자유롭게 활용하세요.\n"
            "예) 매매 메모, 전략 노트, 체크리스트 등\n\n"
            "스플리터를 드래그해 크기를 조절할 수 있습니다.")
        self._acct_memo.setStyleSheet(
            "background:#05050f;color:#ccc;font-size:11px;"
            "border:1px solid #2a2a4a;")
        _arp_v.addWidget(self._acct_memo)
        self._acct_right_panel.setMinimumWidth(60)
        self._acct_right_splitter.addWidget(self._acct_right_panel)
        self._acct_right_splitter.setSizes([300, 0])

        self._mid_splitter.addWidget(self._acct_right_splitter)
        self._mid_splitter.setSizes([200, 400, 300])

        self._v_splitter.addWidget(self._mid_splitter)

        # ── 하단: 수평 splitter (선택종목 | 캔들차트) ─────────
        self._bot_splitter = QSplitter(Qt.Horizontal)
        self._bot_splitter.setHandleWidth(8)
        self._bot_splitter.setStyleSheet(_sh)
        self._bot_splitter.setChildrenCollapsible(False)

        # 선택 종목
        gb_sel = QGroupBox("선택 종목"); v_sel = QVBoxLayout(gb_sel)
        v_sel.setSpacing(4); v_sel.setContentsMargins(6,6,6,6)
        self.lbl_sel_kind   = QLabel("종류: ―")
        self.lbl_sel_strike = QLabel("행사가: ―")
        self.lbl_sel_price  = QLabel("현재가: ―")
        for lb in (self.lbl_sel_kind, self.lbl_sel_strike, self.lbl_sel_price):
            lb.setStyleSheet("color:#dde0f0;border:none;font-size:11px;")
            v_sel.addWidget(lb)
        self.lbl_sel_delta = QLabel("Δ: ―")
        self.lbl_sel_theta = QLabel("Θ: ―")
        self.lbl_sel_krw   = QLabel("1계약가: ―")
        for lb in (self.lbl_sel_delta, self.lbl_sel_theta, self.lbl_sel_krw):
            lb.setFont(QFont("Arial",14,QFont.Bold))
            lb.setStyleSheet("color:#ffd700;border:none;")
            v_sel.addWidget(lb)
        bh = QHBoxLayout(); bh.setSpacing(4)
        self.spin_qty = QSpinBox(); self.spin_qty.setRange(1,999)
        self.spin_qty.setValue(1); self.spin_qty.setFixedWidth(52)
        self.btn_buy  = QPushButton("매수")
        self.btn_sell = QPushButton("매도")
        self.btn_buy.setStyleSheet("background:#1a6b3c;color:#fff;font-weight:bold;padding:3px;")
        self.btn_sell.setStyleSheet("background:#8b0000;color:#fff;font-weight:bold;padding:3px;")
        self.btn_buy.clicked.connect(lambda: self._quick_order("BUY"))
        self.btn_sell.clicked.connect(lambda: self._quick_order("SELL"))
        bh.addWidget(self.spin_qty)
        bh.addWidget(self.btn_buy); bh.addWidget(self.btn_sell)
        v_sel.addLayout(bh); v_sel.addStretch()
        gb_sel.setMinimumWidth(140); gb_sel.setMaximumWidth(280)
        self._bot_splitter.addWidget(gb_sel)

        # 캔들 차트
        gb_chart = QGroupBox("캔들 차트  (더블클릭 종목 선택 / KST)")
        v_chart = QVBoxLayout(gb_chart); v_chart.setContentsMargins(2,2,2,2)
        if PG:
            self._candle_plot = pg.PlotWidget()
            self._candle_plot.showGrid(x=True,y=True,alpha=0.2)
            self._candle_plot.setBackground((8,8,18))
            self._candle_plot.setLabel('left','pt')
            # X축: 한국시간 문자열 표시용 커스텀 axis
            self._x_labels = {}   # x_idx → "HH:MM" (KST)
            ax = self._candle_plot.getAxis('bottom')
            ax.setTicks([])
            self._candle_item = _CandleItem()
            self._candle_plot.addItem(self._candle_item)
            v_chart.addWidget(self._candle_plot)
        else:
            v_chart.addWidget(QLabel("pip install pyqtgraph"))
        # ── 캔들차트 우측 수직 스플리터 (차트 | 빈 공간) ──────
        self._chart_right_splitter = QSplitter(Qt.Horizontal)
        self._chart_right_splitter.setHandleWidth(6)
        self._chart_right_splitter.setStyleSheet(_sh)
        self._chart_right_splitter.setChildrenCollapsible(False)
        self._chart_right_splitter.addWidget(gb_chart)

        # 차트 우측 빈 패널
        self._chart_right_panel = QGroupBox("\U0001f4ca 추가 분석")
        _crp_v = QVBoxLayout(self._chart_right_panel)
        _crp_v.setContentsMargins(4,4,4,4)
        self._chart_extra = QTextEdit()
        self._chart_extra.setPlaceholderText(
            "차트 우측 공간 — 자유롭게 활용하세요.\n"
            "예) 지지/저항 메모, 분석 노트 등\n\n"
            "스플리터를 드래그해 크기를 조절할 수 있습니다.")
        self._chart_extra.setStyleSheet(
            "background:#05050f;color:#ccc;font-size:11px;"
            "border:1px solid #2a2a4a;")
        _crp_v.addWidget(self._chart_extra)
        self._chart_right_panel.setMinimumWidth(60)
        self._chart_right_splitter.addWidget(self._chart_right_panel)
        self._chart_right_splitter.setSizes([820, 0])

        self._bot_splitter.addWidget(self._chart_right_splitter)
        self._bot_splitter.setSizes([180, 820])

        self._v_splitter.addWidget(self._bot_splitter)
        self._v_splitter.setSizes([55, 500, 180])

        root.addWidget(self._v_splitter, 1)

        # ── 로그 (고정 하단) ──────────────────────────────────
        gb_log = QGroupBox("로그"); v_log = QVBoxLayout(gb_log)
        v_log.setContentsMargins(2,2,2,2)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        fm = self.log.fontMetrics()
        self.log.setFixedHeight(fm.height()*2+10)
        self.log.setStyleSheet(
            "background:#050510;color:#00e676;font-size:10px;border:none;")
        v_log.addWidget(self.log)
        root.addWidget(gb_log)

    # ─────────────────────────────────────────────────────────
    # 시그널
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.btn_conn.clicked.connect(self.mw.connect_ibkr)
        bridge.connected.connect(self._on_connected)
        bridge.error_sig.connect(self._on_error)
        bridge.acct_value.connect(self._on_acct_value)
        bridge.position_sig.connect(self._on_position)
        bridge.position_end.connect(lambda: self._refresh_balance())
        bridge.open_order_sig.connect(self._on_open_order)
        bridge.order_status_sig.connect(self._on_order_status)
        bridge.hist_bar.connect(self._on_hist_bar)
        bridge.hist_end.connect(self._on_hist_end)
        self.edit_exch.textChanged.connect(self._upd_exch)
        router.register_price(REQ_KR_UND, REQ_KR_UND, self._on_tick_und)
        router.register_price(REQ_KR_CALL, REQ_KR_CALL+self.MAX_CHAIN, self._on_tick_call)
        router.register_price(REQ_KR_PUT,  REQ_KR_PUT +self.MAX_CHAIN, self._on_tick_put)
        router.register_option(REQ_KR_CALL, REQ_KR_CALL+self.MAX_CHAIN, self._on_opt_call)
        router.register_option(REQ_KR_PUT,  REQ_KR_PUT +self.MAX_CHAIN, self._on_opt_put)

    # ─────────────────────────────────────────────────────────
    def _log(self, msg):
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 300: self.log.setPlainText("\n".join(lines[-200:]))

    # ─────────────────────────────────────────────────────────
    # 연결
    # ─────────────────────────────────────────────────────────
    def _on_connected(self):
        self.lbl_conn.setText("● 연결됨")
        self.lbl_conn.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        self._log("TWS 연결 ✓ — 한국선물옵션")
        # 실시간/지연 표시
        try:
            from core import auto_mdt
            mdt = auto_mdt(self.mw.ib)
            if mdt == 1:
                self.lbl_mdt.setText("● 실시간")
                self.lbl_mdt.setStyleSheet("color:#00e676;font-size:10px;font-weight:bold;border:none;")
            else:
                self.lbl_mdt.setText("● 지연")
                self.lbl_mdt.setStyleSheet("color:#ffaa00;font-size:10px;font-weight:bold;border:none;")
        except Exception:
            pass
        QTimer.singleShot(500,  self._req_und)
        QTimer.singleShot(1000, self._req_positions)
        QTimer.singleShot(1500, self._req_open_orders)

    def _on_error(self, rid, code, msg):
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        if REQ_KR_UND <= rid <= REQ_KR_PUT+self.MAX_CHAIN:
            self._log(f"ERR {code} rid={rid}: {msg}")

    # ─────────────────────────────────────────────────────────
    # 환율
    # ─────────────────────────────────────────────────────────
    def _upd_exch(self, txt):
        try:
            r = float(txt)
            if r > 0: self.exch_rate = r; self._upd_avail()
        except: pass

    def _upd_avail(self, usd=None):
        if usd is not None: self._usd_bp = usd
        bp  = getattr(self, '_usd_bp', 0.0)
        krw = bp * self.exch_rate
        self.lbl_avail.setText(f"주문가능: ₩{krw:,.0f}")

    def _on_acct_value(self, tag, val, cur, acct):
        if tag == "BuyingPower":
            try: self._upd_avail(float(val))
            except: pass

    # ─────────────────────────────────────────────────────────
    # 만기
    # ─────────────────────────────────────────────────────────
    def _on_exp_change(self, idx):
        if idx < len(self._expiry_list):
            _, code, _ = self._expiry_list[idx]
            self.edit_custom.setVisible(code == "CUSTOM")

    def _on_zone_change(self, btn):
        """Zone 라디오버튼 변경 처리."""
        for z, rb in self._zone_btns.items():
            if rb is btn:
                self._zone = z
        # 현재 체인이 로드된 상태면 자동 재조회
        if self.und_price is not None and self.call_strikes:
            self._fetch_chain()

    def _get_expiry(self):
        idx = self.combo_exp.currentIndex()
        if idx >= len(self._expiry_list): return None,""
        _, code, kind = self._expiry_list[idx]
        if code == "CUSTOM":
            raw = self.edit_custom.text().strip()
            if len(raw)==8 and raw.isdigit(): return raw, kind
            QMessageBox.warning(self,"만기 오류","형식: YYYYMMDD"); return None,""
        return code, kind

    def _refresh_expiry(self):
        self._expiry_list = build_kr_expiry_list()
        cur = self.combo_exp.currentIndex()
        self.combo_exp.blockSignals(True); self.combo_exp.clear()
        for lbl,_,_ in self._expiry_list: self.combo_exp.addItem(lbl)
        self.combo_exp.setCurrentIndex(min(cur, len(self._expiry_list)-1))
        self.combo_exp.blockSignals(False)

    # ─────────────────────────────────────────────────────────
    # KOSPI200 현재가
    # ─────────────────────────────────────────────────────────
    def _req_und(self):
        if not self.mw.connected: return
        try: self.mw.ib.cancelMktData(REQ_KR_UND)
        except: pass
        try: self.mw.ib.reqMktData(REQ_KR_UND, _make_kr_und(), "232", False, False, [])
        except Exception as e: self._log(f"K200 시세 요청 실패: {e}")

    def _on_tick_und(self, rid, tt, price):
        if rid != REQ_KR_UND or price <= 0: return
        if tt not in (4,68,75,14,9): return
        if tt == 9: self.und_prev = price
        self.und_price = price
        self.lbl_und.setText(f"K200: {price:.2f}")
        if self.und_prev and self.und_prev > 0:
            chg = price - self.und_prev; pct = chg/self.und_prev*100
            s = "+" if chg >= 0 else ""
            col = "#00e676" if chg >= 0 else "#ff5252"
            self.lbl_und_chg.setText(f"{s}{chg:.2f} ({s}{pct:.2f}%)")
            self.lbl_und_chg.setStyleSheet(
                f"color:{col};font-weight:bold;font-size:11px;border:none;")
        if PG:
            self.und_hist.append(price)
            if len(self.und_hist) > self._BUF: del self.und_hist[0]
            self._c_und.setData(self.und_hist)

    # ─────────────────────────────────────────────────────────
    # 체인 조회
    # ─────────────────────────────────────────────────────────
    def _fetch_chain(self):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return

        # 기준 지수: 직접입력 우선, 없으면 K200 실시간
        idx_txt = self.edit_idx_override.text().strip()
        if idx_txt:
            try:
                base_price = float(idx_txt)
                self._log(f"기준 지수 직접입력 사용: {base_price:.2f}")
            except ValueError:
                QMessageBox.warning(self,"입력 오류","지수값은 숫자로 입력하세요."); return
        else:
            if self.und_price is None:
                self._log("K200 현재가 수신 대기… 재시도")
                self._req_und(); QTimer.singleShot(2000, self._fetch_chain); return
            base_price = self.und_price

        expiry, kind = self._get_expiry()
        if not expiry: return
        n   = self.spin_n.value()
        atm = round(base_price / KR_STEP) * KR_STEP

        for i in range(self.MAX_CHAIN+1):
            try: self.mw.ib.cancelMktData(REQ_KR_CALL+i)
            except: pass
            try: self.mw.ib.cancelMktData(REQ_KR_PUT+i)
            except: pass
        self.call_data.clear(); self.put_data.clear()

        # Zone에 따라 행사가 범위 결정
        zone = getattr(self, '_zone', 'ATM')
        if zone == "ATM":
            # ATM: 중심(ATM)에서 콜↑ 풋↓ 각 n개
            self.call_strikes = [round(atm + i*KR_STEP, 1) for i in range(n)]
            self.put_strikes  = [round(atm - i*KR_STEP, 1) for i in range(n)]
        elif zone == "ITM":
            # ITM: 콜은 ATM 아래(이미 내가격), 풋은 ATM 위(이미 내가격)
            self.call_strikes = [round(atm - i*KR_STEP, 1) for i in range(n)]
            self.put_strikes  = [round(atm + i*KR_STEP, 1) for i in range(n)]
        else:  # OTM
            # OTM: 콜은 ATM 위 (외가격), 풋은 ATM 아래 (외가격), ATM 자체 건너뜀
            skip = max(1, round(10.0 / KR_STEP))  # 10pt 이격
            self.call_strikes = [round(atm + (skip+i)*KR_STEP, 1) for i in range(n)]
            self.put_strikes  = [round(atm - (skip+i)*KR_STEP, 1) for i in range(n)]

        self._init_tbl(self.tbl_call, self.call_strikes)
        self._init_tbl(self.tbl_put,  self.put_strikes)
        ticks = "100,101,106"
        for i, st in enumerate(self.call_strikes):
            rid = REQ_KR_CALL + i
            self.call_data[rid] = {"row":i,"strike":st}
            QTimer.singleShot(i*50, lambda r=rid,s=st,e=expiry:
                self._req_one(r,s,"C",e,ticks))
        for i, st in enumerate(self.put_strikes):
            rid = REQ_KR_PUT + i
            self.put_data[rid] = {"row":i,"strike":st}
            QTimer.singleShot(i*50+200, lambda r=rid,s=st,e=expiry:
                self._req_one(r,s,"P",e,ticks))
        self._log(f"체인: ATM={atm:.1f} Zone={zone} 만기={expiry}({kind}) n={n} "
                  f"{'[직접입력]' if idx_txt else '[K200 자동]'}")

    def _req_one(self, rid, strike, right, expiry, ticks):
        if not self.mw.connected: return
        try:
            self.mw.ib.reqMktData(
                rid, _make_kr_opt(strike,right,expiry), ticks, False, False, [])
        except Exception as e:
            self._log(f"req 실패 rid={rid}: {e}")

    def _init_tbl(self, tbl, strikes):
        tbl.clearContents(); tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r,0,_mk(f"{s:.1f}","#ffd700"))
            for c in range(1,4): tbl.setItem(r,c,_mk("―"))

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_call(self, rid, tt, price):
        if price <= 0: return
        d = self.call_data.get(rid)
        if not d: return
        row = d["row"]
        if row >= len(self.call_strikes): return
        if tt in (4,68):
            tbl_set(self.tbl_call, row, 1, f"{price:.2f}", "#33aaff")
            d["last"] = price
            if self._chart_strike == self.call_strikes[row] and self._chart_side=="C":
                self._upd_sidebar("C", row)

    def _on_tick_put(self, rid, tt, price):
        if price <= 0: return
        d = self.put_data.get(rid)
        if not d: return
        row = d["row"]
        if row >= len(self.put_strikes): return
        if tt in (4,68):
            tbl_set(self.tbl_put, row, 1, f"{price:.2f}", "#ff6666")
            d["last"] = price
            if self._chart_strike == self.put_strikes[row] and self._chart_side=="P":
                self._upd_sidebar("P", row)

    def _on_opt_call(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10,11,12,13,80,81): return
        if delta is None or abs(delta) > 1.5: return
        d = self.call_data.get(rid)
        if not d: return
        row = d["row"]
        if row >= len(self.call_strikes): return
        tbl_set(self.tbl_call, row, 2, f"{delta:+.3f}", "#aaddff")
        tbl_set(self.tbl_call, row, 3, f"{theta:.3f}" if theta else "―")
        d["delta"] = delta; d["theta"] = theta
        if self._chart_strike == self.call_strikes[row] and self._chart_side=="C":
            self._upd_sidebar("C", row)

    def _on_opt_put(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10,11,12,13,80,81): return
        if delta is None or abs(delta) > 1.5: return
        d = self.put_data.get(rid)
        if not d: return
        row = d["row"]
        if row >= len(self.put_strikes): return
        tbl_set(self.tbl_put, row, 2, f"{delta:+.3f}", "#ffaaaa")
        tbl_set(self.tbl_put, row, 3, f"{theta:.3f}" if theta else "―")
        d["delta"] = delta; d["theta"] = theta
        if self._chart_strike == self.put_strikes[row] and self._chart_side=="P":
            self._upd_sidebar("P", row)

    # ─────────────────────────────────────────────────────────
    # 체인 클릭
    # ─────────────────────────────────────────────────────────
    def _chain_click(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        st = strikes[row]
        self.lbl_hoga_title.setText(
            f"행사가: {st:.1f}  |  {'CALL ▲' if side=='C' else 'PUT ▼'}")
        self._upd_sidebar(side, row)

    def _chain_dbl(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        self._chain_click(row, col, side)
        self._req_candle(strikes[row], side)

    # ─────────────────────────────────────────────────────────
    # 사이드바
    # ─────────────────────────────────────────────────────────
    def _upd_sidebar(self, side, row):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        st  = strikes[row]
        rid = (REQ_KR_CALL+row) if side=="C" else (REQ_KR_PUT+row)
        d   = (self.call_data if side=="C" else self.put_data).get(rid, {})
        price = d.get("last"); delta = d.get("delta"); theta = d.get("theta")
        self.lbl_sel_kind.setText(f"종류: {'CALL ▲' if side=='C' else 'PUT ▼'}")
        self.lbl_sel_strike.setText(f"행사가: {st:.1f}")
        self.lbl_sel_price.setText(f"현재가: {price:.2f}pt" if price else "현재가: ―")
        self.lbl_sel_delta.setText(f"Δ: {delta:+.3f}" if delta is not None else "Δ: ―")
        self.lbl_sel_theta.setText(f"Θ: {theta:.3f}" if theta else "Θ: ―")
        if price: self.lbl_sel_krw.setText(f"1계약가: ₩{price*KR_MULTIPLIER:,.0f}")

    # ─────────────────────────────────────────────────────────
    # 캔들 히스토리
    # ─────────────────────────────────────────────────────────
    def _req_candle(self, strike, side):
        if not self.mw.connected or not PG: return
        expiry, _ = self._get_expiry()
        if not expiry: return
        strikes = self.call_strikes if side=="C" else self.put_strikes
        try:    row = strikes.index(strike)
        except: return
        rid = ((REQ_KR_CALL+row) if side=="C" else (REQ_KR_PUT+row)) + 500
        try:
            self.mw.ib.reqHistoricalData(
                rid, _make_kr_opt(strike, side, expiry),
                "", "1 D", "1 min", "TRADES", 1, 1, False, [])
            self._candle_rid = rid; self._candle_buf = []
        except Exception as e: self._log(f"캔들 요청 실패: {e}")

    @staticmethod
    def _to_kst(bar_date_str: str) -> str:
        """IBKR bar.date → KST HH:MM 문자열 (UTC+9)."""
        try:
            # IBKR 1분봉: "20240315 09:30:00" (현지시간) or UTC
            dt = datetime.strptime(bar_date_str.strip(), "%Y%m%d %H:%M:%S")
            # IBKR histData는 reqHistoricalData useRTH=1 → 한국시간 그대로
            # useRTH=0이면 UTC → +9
            return dt.strftime("%H:%M")
        except Exception:
            return bar_date_str[-5:] if len(bar_date_str) >= 5 else bar_date_str

    def _on_hist_bar(self, rid, bar):
        if rid != self._candle_rid: return
        try:
            t = datetime.strptime(bar.date.strip(), "%Y%m%d %H:%M:%S").timestamp()
            self._candle_buf.append((t, bar.open, bar.high, bar.low, bar.close))
            self._x_labels[len(self._candle_buf)-1] = self._to_kst(bar.date)
        except Exception:
            pass

    def _on_hist_end(self, rid):
        if rid != self._candle_rid: return
        if not self._candle_buf or not PG: return
        # 빠른 렌더링: _CandleItem.setData + X축 KST 레이블
        self._candle_item.setData(self._candle_buf)
        # X축: 인덱스 기반으로 변환해서 KST 표시
        n = len(self._candle_buf)
        x_ticks = []
        step = max(1, n // 12)
        for i in range(0, n, step):
            t_unix = self._candle_buf[i][0]
            # KST = UTC+9
            kst = datetime.utcfromtimestamp(t_unix + 9*3600)
            x_ticks.append((self._candle_buf[i][0], kst.strftime("%H:%M")))
        self._candle_plot.getAxis('bottom').setTicks([x_ticks])
        self._log(f"캔들 {n}봉 완료 (KST)")

    # ─────────────────────────────────────────────────────────
    # 잔고 / 주문
    # ─────────────────────────────────────────────────────────
    def _req_positions(self):
        if not self.mw.connected: return
        try: self.mw.ib.reqPositions()
        except: pass

    def _req_open_orders(self):
        if not self.mw.connected: return
        try: self.mw.ib.reqAllOpenOrders()
        except: pass

    def _on_position(self, acct, sym, right, qty, avg_cost):
        if "K200" not in sym and "KOSPI" not in sym.upper(): return
        self._positions[f"{sym}_{right}"] = dict(
            sym=sym, right=right, qty=qty, avg_cost=avg_cost)
        self._refresh_balance()

    def _refresh_balance(self):
        self.tbl_balance.setRowCount(0)
        for key, pos in self._positions.items():
            r = self.tbl_balance.rowCount(); self.tbl_balance.insertRow(r)
            col = "#33aaff" if pos['right']=="C" else "#ff6666"
            avg_krw = pos['avg_cost'] * KR_MULTIPLIER
            tbl_set(self.tbl_balance, r, 0, pos['sym'])
            tbl_set(self.tbl_balance, r, 1, pos['right'], col)
            tbl_set(self.tbl_balance, r, 2, str(int(pos['qty'])), "#ffd700")
            tbl_set(self.tbl_balance, r, 3, f"₩{avg_krw:,.0f}")
            tbl_set(self.tbl_balance, r, 4, "―"); tbl_set(self.tbl_balance, r, 5, "―")

    def _on_open_order(self, oid, sym, right, action, qty, price, status):
        if "K200" not in sym and "KOSPI" not in sym.upper(): return
        self._open_orders[oid] = dict(
            sym=sym, right=right, action=action, qty=qty, price=price, status=status)
        self._refresh_orders()

    def _on_order_status(self, oid, status, filled, remaining):
        if oid in self._open_orders:
            self._open_orders[oid]["status"] = status; self._refresh_orders()

    def _refresh_orders(self):
        self.tbl_open.setRowCount(0); self.tbl_amend.setRowCount(0)
        for oid, od in self._open_orders.items():
            if od["status"] in ("Filled","Cancelled"): continue
            col = "#33aaff" if od["right"]=="C" else "#ff6666"
            r = self.tbl_open.rowCount(); self.tbl_open.insertRow(r)
            tbl_set(self.tbl_open, r, 0, str(oid))
            tbl_set(self.tbl_open, r, 1, od["right"], col)
            tbl_set(self.tbl_open, r, 2, "―")
            tbl_set(self.tbl_open, r, 3, str(int(od["qty"])))
            tbl_set(self.tbl_open, r, 4, f"{od['price']:.2f}" if od['price'] else "MKT")
            sc = "#ffd700" if "Submit" in od["status"] else "#aaa"
            tbl_set(self.tbl_open, r, 5, od["status"], sc)
            if od["status"] in ("Submitted","PreSubmitted"):
                ra = self.tbl_amend.rowCount(); self.tbl_amend.insertRow(ra)
                tbl_set(self.tbl_amend, ra, 0, str(oid))
                tbl_set(self.tbl_amend, ra, 1, od["right"], col)
                tbl_set(self.tbl_amend, ra, 2, "―")
                tbl_set(self.tbl_amend, ra, 3, str(int(od["qty"])))
                tbl_set(self.tbl_amend, ra, 4,
                        f"{od['price']:.2f}" if od['price'] else "MKT")
                tbl_set(self.tbl_amend, ra, 5, "👆클릭")

    def _on_bal_dbl(self, row, col):
        if not self.mw.connected: return
        it_s = self.tbl_balance.item(row,0)
        it_q = self.tbl_balance.item(row,2)
        if not it_s or not it_q: return
        qty = abs(int(it_q.text().replace(",","")))
        if QMessageBox.question(self,"매도 확인",
            f"{it_s.text()} {qty}계약 시장가 매도?",
            QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            self._log(f"매도 주문: {it_s.text()} {qty}계약")

    def _on_open_dbl(self, row, col):
        it = self.tbl_open.item(row,0)
        if not it: return
        oid = int(it.text())
        if QMessageBox.question(self,"취소 확인",
            f"OrderID {oid} 취소?",
            QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            try: self.mw.ib.cancelOrder(oid); self._log(f"취소: oid={oid}")
            except Exception as e: self._log(f"취소 실패: {e}")

    def _on_amend_dbl(self, row, col):
        it = self.tbl_amend.item(row,0)
        if not it: return
        oid = int(it.text()); od = self._open_orders.get(oid,{})
        cur = od.get("price",0.0)
        new_p, ok = QInputDialog.getDouble(
            self,"정정 가격",f"OrderID {oid}  현재:{cur:.2f}\n새 가격:",
            value=cur, min=0.0, max=9999.0, decimals=2)
        if ok:
            try:
                self.mw.ib.placeOrder(
                    oid, _make_kr_und(),
                    _make_kr_order(od["action"], int(od["qty"]), "LMT", new_p))
                self._log(f"정정: oid={oid} 새가격={new_p:.2f}")
            except Exception as e: self._log(f"정정 실패: {e}")

    def _quick_order(self, action):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        if self._chart_strike is None:
            QMessageBox.warning(self,"미선택","체인을 클릭하세요."); return
        expiry, _ = self._get_expiry()
        if not expiry: return
        side = self._chart_side; st = self._chart_strike; qty = self.spin_qty.value()
        strikes = self.call_strikes if side=="C" else self.put_strikes
        try:    row = strikes.index(st)
        except: return
        rid   = (REQ_KR_CALL+row) if side=="C" else (REQ_KR_PUT+row)
        price = (self.call_data if side=="C" else self.put_data).get(rid,{}).get("last",0.0)
        if QMessageBox.question(self,f"{action} 확인",
            f"{'콜' if side=='C' else '풋'} {st:.1f}  {qty}계약\n"
            f"{action} 지정가 {price:.2f}pt (₩{price*KR_MULTIPLIER:,.0f})",
            QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            try:
                oid = self.mw.ib.get_next_id()
                if oid:
                    self.mw.ib.placeOrder(oid,
                        _make_kr_opt(st,side,expiry),
                        _make_kr_order(action,qty,"LMT",price))
                    self._log(f"{'콜' if side=='C' else '풋'} {action} "
                              f"{st:.1f} {qty}계약 {price:.2f}pt oid={oid}")
            except Exception as e: self._log(f"주문 실패: {e}")

    # ─────────────────────────────────────────────────────────
    # 다크모드
    # ─────────────────────────────────────────────────────────
    def _apply_theme(self):
        dark = getattr(self, 'dark_mode', True)
        for tbl in (self.tbl_call, self.tbl_put,
                    self.tbl_hoga_call, self.tbl_hoga_put,
                    self.tbl_balance, self.tbl_open, self.tbl_amend):
            _table_apply_dark(tbl, dark)

    # ─────────────────────────────────────────────────────────
    # 설정 저장/복원
    # ─────────────────────────────────────────────────────────
    def _get_extra_settings(self):
        idx = self.combo_exp.currentIndex()
        _, code, _ = (self._expiry_list[idx]
                      if idx < len(self._expiry_list) else ("","",""))
        d = {
            "expiry":       code,
            "n":            self.spin_n.value(),
            "exch":         self.edit_exch.text(),
            "zone":         getattr(self, '_zone', 'ATM'),
            "idx_override": self.edit_idx_override.text().strip(),
        }
        try:
            d["v_split"]           = list(self._v_splitter.sizes())
            d["mid_split"]         = list(self._mid_splitter.sizes())
            d["bot_split"]         = list(self._bot_splitter.sizes())
            d["acct_right_split"]  = list(self._acct_right_splitter.sizes())
            d["chart_right_split"] = list(self._chart_right_splitter.sizes())
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s):
        if s.get("exch"): self.edit_exch.setText(s["exch"])
        if s.get("n"):    self.spin_n.setValue(int(s["n"]))
        if s.get("idx_override"):
            self.edit_idx_override.setText(s["idx_override"])
        # Zone 복원
        zone = s.get("zone", "ATM")
        if zone in self._zone_btns:
            self._zone = zone
            self._zone_btns[zone].blockSignals(True)
            self._zone_btns[zone].setChecked(True)
            self._zone_btns[zone].blockSignals(False)
        for i,(_,code,_) in enumerate(self._expiry_list):
            if code == s.get("expiry",""):
                self.combo_exp.blockSignals(True)
                self.combo_exp.setCurrentIndex(i)
                self.combo_exp.blockSignals(False); break
        def _restore():
            try:
                if s.get("v_split"):           self._v_splitter.setSizes(s["v_split"])
                if s.get("mid_split"):         self._mid_splitter.setSizes(s["mid_split"])
                if s.get("bot_split"):         self._bot_splitter.setSizes(s["bot_split"])
                if s.get("acct_right_split"):  self._acct_right_splitter.setSizes(s["acct_right_split"])
                if s.get("chart_right_split"): self._chart_right_splitter.setSizes(s["chart_right_split"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)