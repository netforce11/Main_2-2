"""
tab_trading.py — 9번 탭: 통합 주문/잔고 패널  v1.0
════════════════════════════════════════════════════════════════
레이아웃 (12열 × 4행):
  [0] 지수 현재가 + 미니 라인차트
  [1] 주문1(호가 클릭) | 주문2(직접 입력) | 주문 상태 로그
  [2] 잔고 테이블 | 미체결 테이블 | 정정 패널
  [3] 버튼 바
════════════════════════════════════════════════════════════════
주문 흐름:
  - 호가 클릭 주문(1): 호가 테이블 행 더블클릭 → 자동 가격 채움 → 주문
  - 호가 입력 주문(2): 심볼/가격/수량/방향 직접 입력 → 주문
  - 잔고 더블클릭    → 매도 주문 자동 세팅
  - 미체결 더블클릭  → 정정/취소 주문 자동 세팅
"""

import json
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QTextEdit, QMessageBox, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView, QRadioButton,
    QButtonGroup, QFrame, QSpinBox, QDoubleSpinBox, QInputDialog,
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
    SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM,
    REQ_UND, SAVE_DIR,
    make_und_contract, make_opt_contract,
    build_expiry_list, auto_mdt, is_market_open,
    save_json, load_json,
)
try:
    from ibapi.order import Order as IBOrder
    from ibapi.contract import Contract as IBContract
    IBAPI_AVAILABLE = True
except ImportError:
    IBAPI_AVAILABLE = False

# ── 9번 탭 전용 reqId 범위 ──────────────────────────────────
REQ_TRADE_UND  = 8000   # 지수 현재가 (8000~8009)
REQ_TRADE_BID  = 8010   # 호가 테이블 (8010~8019)
REQ_TRADE_POS  = 8020   # 잔고 시세  (8020~8049)

# ── 주문 유형 ────────────────────────────────────────────────
ORDER_TYPES = ["LMT", "MKT", "STP", "STP LMT"]
ACTIONS     = ["BUY", "SELL"]


def _mk(text, color=None):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    if color: it.setForeground(QBrush(QColor(color)))
    return it


# ══════════════════════════════════════════════════════════════
# 주문 팩토리
# ══════════════════════════════════════════════════════════════
def make_order(action: str, qty: int, order_type: str,
               lmt_price: float = 0.0, aux_price: float = 0.0):
    """IBKR Order 객체 생성."""
    if not IBAPI_AVAILABLE:
        class _FakeOrder:
            pass
        o = _FakeOrder()
    else:
        o = IBOrder()
    o.action        = action.upper()
    o.totalQuantity = qty
    o.orderType     = order_type.upper()
    o.lmtPrice      = lmt_price
    o.auxPrice      = aux_price
    o.tif           = "DAY"
    o.eTradeOnly    = False
    o.firmQuoteOnly = False
    return o


def make_stock_contract(symbol: str):
    """주식 Contract 생성."""
    if not IBAPI_AVAILABLE:
        class _C: pass
        c = _C()
        c.symbol = symbol.upper(); c.secType = "STK"
        c.exchange = "SMART"; c.currency = "USD"
        return c
    c = IBContract()
    c.symbol   = symbol.upper()
    c.secType  = "STK"
    c.exchange = "SMART"
    c.currency = "USD"
    return c


# ══════════════════════════════════════════════════════════════
# Tab 9: 통합 주문/잔고 패널
# ══════════════════════════════════════════════════════════════
class TradingGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw

        # 상태
        self._index_sym  = "SPX"
        self._index_hist = []          # 라인차트 버퍼
        self._index_prev = None        # 전일 종가
        self._index_cur  = None        # 현재가
        self._positions  = {}          # {sym: {qty, avg_cost, ...}}
        self._open_orders= {}          # {orderId: {...}}
        self._bid_data   = []          # 호가 테이블 데이터
        self._order_log  = []          # 주문 로그

        self._BUF = 200
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh_data)

        self._build()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────
    # UI 빌드
    # ─────────────────────────────────────────────────────────
    def _build(self):

        # ══ [0] 상단: 지수 현재가 + 라인차트 ══════════════════
        self.add(self._build_index_panel(), 0, 0, 1, 12)

        # ══ [1,0-2] 주문1: 호가 클릭 주문 ═════════════════════
        self.add(self._build_order1_panel(), 1, 0, 1, 3)

        # ══ [1,3-7] 주문2: 직접 입력 주문 ═════════════════════
        self.add(self._build_order2_panel(), 1, 3, 1, 5)

        # ══ [1,9-11] 주문 상태 로그 ════════════════════════════
        gb_log = QGroupBox("주문 로그")
        vl = QVBoxLayout(gb_log)
        self.order_log_w = QTextEdit(); self.order_log_w.setReadOnly(True)
        vl.addWidget(self.order_log_w)
        self.add(gb_log, 1, 9, 1, 3)

        # ══ [2,0-4] 잔고 ════════════════════════════════════════
        self.add(self._build_position_panel(), 2, 0, 1, 5)

        # ══ [2,5-8] 미체결 ══════════════════════════════════════
        self.add(self._build_openorder_panel(), 2, 5, 1, 4)

        # ══ [2,9-11] 정정/취소 ══════════════════════════════════
        self.add(self._build_amend_panel(), 2, 9, 1, 3)

        # ══ [3] 버튼 바 ══════════════════════════════════════════
        br = QWidget(); bh = QHBoxLayout(br); bh.setSpacing(8)
        btn_pos  = QPushButton("🔄 잔고 새로고침")
        btn_open = QPushButton("🔄 미체결 새로고침")
        btn_clr  = QPushButton("🗑 로그 초기화")
        self.lbl_conn = QLabel("● 미연결")
        self.lbl_conn.setStyleSheet("color:#ff4444;font-weight:bold;border:none;")
        btn_pos.clicked.connect(self._req_positions)
        btn_open.clicked.connect(self._req_open_orders)
        btn_clr.clicked.connect(lambda: self.order_log_w.clear())
        for w in (btn_pos, btn_open, btn_clr): bh.addWidget(w)
        bh.addStretch(); bh.addWidget(self.lbl_conn)
        self.add(br, 3, 0, 1, 12)

    # ─────────────────────────────────────────────────────────
    # 패널 빌더들
    # ─────────────────────────────────────────────────────────
    def _build_index_panel(self):
        gb = QGroupBox("지수 현재가"); h = QHBoxLayout(gb)

        # 심볼 선택
        sym_v = QVBoxLayout()
        self.idx_combo = QComboBox()
        self.idx_combo.addItems(["SPX","NDX","RUT","VIX","DJX"])
        self.idx_combo.currentTextChanged.connect(self._on_index_change)
        sym_v.addWidget(QLabel("지수 선택"))
        sym_v.addWidget(self.idx_combo)
        h.addLayout(sym_v)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine); h.addWidget(sep)

        # 현재가 + 등락
        price_v = QVBoxLayout()
        self.lbl_idx_price = QLabel("―")
        self.lbl_idx_price.setFont(QFont("Arial", 28, QFont.Bold))
        self.lbl_idx_price.setStyleSheet("color:#ffd700;border:none;")
        self.lbl_idx_chg   = QLabel("")
        self.lbl_idx_chg.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_idx_chg.setStyleSheet("color:#aaa;border:none;")
        price_v.addWidget(self.lbl_idx_price)
        price_v.addWidget(self.lbl_idx_chg)
        h.addLayout(price_v)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine); h.addWidget(sep2)

        # 라인차트
        if PG:
            self._idx_plot = pg.PlotWidget()
            self._idx_plot.setMaximumHeight(80)
            self._idx_plot.setMinimumWidth(400)
            self._idx_plot.showGrid(x=False, y=True, alpha=0.15)
            self._idx_plot.setBackground((15,15,25))
            self._idx_plot.getAxis('bottom').setStyle(showValues=False)
            self._idx_curve = self._idx_plot.plot(
                pen=pg.mkPen('#ffd700', width=2))
            h.addWidget(self._idx_plot, 1)

        return gb

    def _build_order1_panel(self):
        """호가 클릭 주문 — 호가 테이블 더블클릭 → 가격 자동 세팅."""
        gb = QGroupBox("① 호가 클릭 주문  (더블클릭→가격 자동입력)")
        v  = QVBoxLayout(gb)

        # 심볼 조회
        sym_row = QHBoxLayout()
        self.bid_sym = QLineEdit(); self.bid_sym.setPlaceholderText("심볼 (예: AAPL, SPY)")
        btn_bid = QPushButton("호가 조회"); btn_bid.setFixedWidth(80)
        btn_bid.clicked.connect(self._req_bid_ask)
        self.bid_sym.returnPressed.connect(self._req_bid_ask)
        sym_row.addWidget(self.bid_sym); sym_row.addWidget(btn_bid)
        v.addLayout(sym_row)

        # 호가 테이블 (Bid/Ask × 5레벨)
        self.tbl_bid = QTableWidget(10, 3)
        self.tbl_bid.setHorizontalHeaderLabels(["구분","가격","수량"])
        self.tbl_bid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_bid.verticalHeader().setVisible(False)
        self.tbl_bid.setMaximumHeight(220)
        self.tbl_bid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_bid.cellDoubleClicked.connect(self._on_bid_dbl)
        for r in range(10):
            kind = "ASK" if r < 5 else "BID"
            col  = "#ff5555" if r < 5 else "#55aaff"
            self.tbl_bid.setItem(r, 0, _mk(kind, col))
            self.tbl_bid.setItem(r, 1, _mk("―"))
            self.tbl_bid.setItem(r, 2, _mk("―"))
        v.addWidget(self.tbl_bid)

        # 주문 파라미터
        param_g = QGridLayout()
        param_g.addWidget(QLabel("방향:"), 0, 0)
        self.o1_action = QComboBox(); self.o1_action.addItems(ACTIONS)
        self.o1_action.setStyleSheet("QComboBox{font-weight:bold;}")
        param_g.addWidget(self.o1_action, 0, 1)
        param_g.addWidget(QLabel("가격:"), 0, 2)
        self.o1_price = QLineEdit(); self.o1_price.setPlaceholderText("0.00")
        param_g.addWidget(self.o1_price, 0, 3)
        param_g.addWidget(QLabel("수량:"), 1, 0)
        self.o1_qty = QSpinBox(); self.o1_qty.setRange(1, 10000); self.o1_qty.setValue(1)
        param_g.addWidget(self.o1_qty, 1, 1)
        param_g.addWidget(QLabel("유형:"), 1, 2)
        self.o1_type = QComboBox(); self.o1_type.addItems(ORDER_TYPES)
        param_g.addWidget(self.o1_type, 1, 3)
        v.addLayout(param_g)

        btn_o1 = QPushButton("📤 주문 전송")
        btn_o1.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;font-size:13px;padding:6px;")
        btn_o1.clicked.connect(self._place_order1)
        v.addWidget(btn_o1)
        return gb

    def _build_order2_panel(self):
        """직접 입력 주문."""
        gb = QGroupBox("② 직접 입력 주문")
        g  = QGridLayout(gb); g.setSpacing(6)

        g.addWidget(QLabel("심볼:"), 0, 0)
        self.o2_sym = QLineEdit(); self.o2_sym.setPlaceholderText("AAPL / SPX")
        g.addWidget(self.o2_sym, 0, 1, 1, 2)

        g.addWidget(QLabel("종류:"), 1, 0)
        self.o2_sec = QComboBox()
        self.o2_sec.addItems(["STK (주식)", "OPT (옵션)"])
        g.addWidget(self.o2_sec, 1, 1, 1, 2)

        # 옵션 전용 필드 (STK 선택 시 숨김)
        self.o2_opt_w = QWidget()
        og = QGridLayout(self.o2_opt_w); og.setContentsMargins(0,0,0,0)
        og.addWidget(QLabel("만기:"), 0, 0)
        self.o2_expiry = QLineEdit(); self.o2_expiry.setPlaceholderText("YYYYMMDD")
        og.addWidget(self.o2_expiry, 0, 1)
        og.addWidget(QLabel("행사가:"), 1, 0)
        self.o2_strike = QLineEdit(); self.o2_strike.setPlaceholderText("5500")
        og.addWidget(self.o2_strike, 1, 1)
        og.addWidget(QLabel("C/P:"), 2, 0)
        self.o2_right = QComboBox(); self.o2_right.addItems(["C","P"])
        og.addWidget(self.o2_right, 2, 1)
        g.addWidget(self.o2_opt_w, 2, 0, 1, 3)
        self.o2_opt_w.setVisible(False)
        self.o2_sec.currentIndexChanged.connect(
            lambda i: self.o2_opt_w.setVisible(i == 1))

        g.addWidget(QLabel("방향:"), 3, 0)
        self.o2_action = QComboBox(); self.o2_action.addItems(ACTIONS)
        self.o2_action.setStyleSheet("QComboBox{font-weight:bold;}")
        g.addWidget(self.o2_action, 3, 1, 1, 2)

        g.addWidget(QLabel("가격:"), 4, 0)
        self.o2_price = QLineEdit(); self.o2_price.setPlaceholderText("0.00 (MKT=0)")
        g.addWidget(self.o2_price, 4, 1, 1, 2)

        g.addWidget(QLabel("수량:"), 5, 0)
        self.o2_qty = QSpinBox(); self.o2_qty.setRange(1, 10000); self.o2_qty.setValue(1)
        g.addWidget(self.o2_qty, 5, 1)

        g.addWidget(QLabel("유형:"), 6, 0)
        self.o2_type = QComboBox(); self.o2_type.addItems(ORDER_TYPES)
        g.addWidget(self.o2_type, 6, 1, 1, 2)

        btn_o2 = QPushButton("📤 주문 전송")
        btn_o2.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;font-size:13px;padding:6px;")
        btn_o2.clicked.connect(self._place_order2)
        g.addWidget(btn_o2, 7, 0, 1, 3)

        btn_mkt = QPushButton("⚡ 시장가 즉시 매도")
        btn_mkt.setStyleSheet(
            "background:#8b0000;color:#fff;font-weight:bold;padding:4px;")
        btn_mkt.clicked.connect(self._market_sell)
        g.addWidget(btn_mkt, 8, 0, 1, 3)

        return gb

    def _build_position_panel(self):
        """잔고 테이블 — 더블클릭 → 매도 주문 자동 세팅."""
        gb = QGroupBox("잔고  (더블클릭 → 매도 주문 자동 세팅)")
        v  = QVBoxLayout(gb)
        self.tbl_pos = make_table(
            ["심볼","수량","평균단가","현재가","평가손익","손익률"])
        self.tbl_pos.setMinimumHeight(120)
        self.tbl_pos.cellDoubleClicked.connect(self._on_pos_dbl)
        v.addWidget(self.tbl_pos)
        return gb

    def _build_openorder_panel(self):
        """미체결 테이블 — 더블클릭 → 정정 주문 자동 세팅."""
        gb = QGroupBox("미체결  (더블클릭 → 정정/취소 자동 세팅)")
        v  = QVBoxLayout(gb)
        self.tbl_open = make_table(
            ["OrderID","심볼","방향","수량","가격","상태"])
        self.tbl_open.setMinimumHeight(120)
        self.tbl_open.cellDoubleClicked.connect(self._on_open_dbl)
        v.addWidget(self.tbl_open)
        return gb

    def _build_amend_panel(self):
        """정정/취소 주문 패널."""
        gb = QGroupBox("정정 / 취소")
        v  = QVBoxLayout(gb); v.setSpacing(6)

        v.addWidget(QLabel("OrderID:"))
        self.amd_oid = QLineEdit(); self.amd_oid.setPlaceholderText("주문ID")
        v.addWidget(self.amd_oid)

        v.addWidget(QLabel("새 가격:"))
        self.amd_price = QLineEdit(); self.amd_price.setPlaceholderText("0.00")
        v.addWidget(self.amd_price)

        v.addWidget(QLabel("새 수량:"))
        self.amd_qty = QSpinBox(); self.amd_qty.setRange(1, 10000)
        self.amd_qty.setValue(1)
        v.addWidget(self.amd_qty)

        btn_amd = QPushButton("✏ 정정 주문")
        btn_amd.setStyleSheet(
            "background:#1a3a6b;color:#fff;font-weight:bold;padding:5px;")
        btn_amd.clicked.connect(self._amend_order)
        v.addWidget(btn_amd)

        btn_cxl = QPushButton("❌ 주문 취소")
        btn_cxl.setStyleSheet(
            "background:#7a1a1a;color:#fff;font-weight:bold;padding:5px;")
        btn_cxl.clicked.connect(self._cancel_order)
        v.addWidget(btn_cxl)

        v.addStretch()

        # 체결 요약
        self.lbl_fill = QLabel("체결: ―")
        self.lbl_fill.setStyleSheet(
            "color:#00e676;font-weight:bold;font-size:12px;border:none;")
        self.lbl_fill.setWordWrap(True)
        v.addWidget(self.lbl_fill)

        return gb

    # ─────────────────────────────────────────────────────────
    # 시그널 연결
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        bridge.connected.connect(self._on_connected)
        bridge.error_sig.connect(self._on_error)
        bridge.position_sig.connect(self._on_position)
        bridge.position_end.connect(self._on_position_end)
        bridge.open_order_sig.connect(self._on_open_order)
        bridge.exec_sig.connect(self._on_exec)
        bridge.order_status_sig.connect(self._on_order_status)
        router.register_price(REQ_TRADE_UND, REQ_TRADE_UND+9,  self._on_index_tick)
        router.register_price(REQ_TRADE_POS, REQ_TRADE_POS+29, self._on_pos_tick)

    # ─────────────────────────────────────────────────────────
    # 연결 / 에러
    # ─────────────────────────────────────────────────────────
    def _on_connected(self):
        self.lbl_conn.setText("● 연결됨")
        self.lbl_conn.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        auto_mdt(self.mw.ib)
        self._req_index()
        self._req_positions()
        self._req_open_orders()
        self._refresh_timer.start()

    def _on_error(self, rid, code, msg):
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        self._log(f"ERR {code}: {msg}")

    def _log(self, msg):
        self.order_log_w.append(f"[{ts()}] {msg}")
        self._order_log.append({"time":ts(),"msg":msg})

    # ─────────────────────────────────────────────────────────
    # 지수 현재가
    # ─────────────────────────────────────────────────────────
    def _on_index_change(self, sym):
        self._index_sym = sym
        self._index_hist.clear(); self._index_prev = None; self._index_cur = None
        self.lbl_idx_price.setText("―"); self.lbl_idx_chg.setText("")
        if self.mw.connected: self._req_index()

    def _req_index(self):
        sym = self.idx_combo.currentText()
        try: self.mw.ib.cancelMktData(REQ_TRADE_UND)
        except: pass
        self.mw.ib.reqMktData(
            REQ_TRADE_UND, make_und_contract(sym), "232", False, False, [])

    def _on_index_tick(self, rid, tt, price):
        if rid != REQ_TRADE_UND or price <= 0: return
        if tt in (4, 68, 75, 14):
            self._index_cur = price
            self.lbl_idx_price.setText(f"{price:,.2f}")
            self._index_hist.append(price)
            if len(self._index_hist) > self._BUF: del self._index_hist[0]
            if PG and hasattr(self, '_idx_curve'):
                self._idx_curve.setData(self._index_hist)
            # 등락률
            if self._index_prev and self._index_prev > 0:
                chg = price - self._index_prev; pct = chg / self._index_prev * 100
                sign = "+" if chg >= 0 else ""
                col  = "#00e676" if chg >= 0 else "#ff5252"
                self.lbl_idx_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
                self.lbl_idx_chg.setStyleSheet(
                    f"color:{col};font-weight:bold;border:none;")
        elif tt == 9:
            self._index_prev = price

    def _refresh_data(self):
        if not self.mw.connected: return
        self._req_index()

    # ─────────────────────────────────────────────────────────
    # 호가 조회 (Level 1 Bid/Ask)
    # ─────────────────────────────────────────────────────────
    def _req_bid_ask(self):
        sym = self.bid_sym.text().strip().upper()
        if not sym: return
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        auto_mdt(self.mw.ib)
        try: self.mw.ib.cancelMktData(REQ_TRADE_BID)
        except: pass
        # Level 1 호가 (233=RTVolume, 105=AvgOptVol)
        self.mw.ib.reqMktData(
            REQ_TRADE_BID, make_und_contract(sym), "233", False, False, [])
        # 임시: Bid(1)/Ask(2) 단일 레벨만 표시
        router.register_price(REQ_TRADE_BID, REQ_TRADE_BID, self._on_bid_tick)

    def _on_bid_tick(self, rid, tt, price):
        if price <= 0: return
        # tt=1=Bid, tt=2=Ask, tt=4=Last
        row_map = {1:5, 2:0, 4:7}   # Bid→row5, Ask→row0, Last→row7
        row = row_map.get(tt)
        if row is not None and row < 10:
            self.tbl_bid.setItem(row, 1, _mk(f"{price:.2f}",
                "#55aaff" if tt==1 else "#ff5555" if tt==2 else "#ffd700"))

    def _on_bid_dbl(self, row, col):
        """호가 테이블 더블클릭 → 주문1 가격 자동 세팅."""
        it = self.tbl_bid.item(row, 1)
        if it and it.text() != "―":
            self.o1_price.setText(it.text())
            kind = self.tbl_bid.item(row, 0)
            if kind:
                self.o1_action.setCurrentText(
                    "BUY" if kind.text() == "ASK" else "SELL")

    # ─────────────────────────────────────────────────────────
    # 주문 전송
    # ─────────────────────────────────────────────────────────
    def _place_order1(self):
        """호가 클릭 주문."""
        sym = self.bid_sym.text().strip().upper()
        if not sym:
            QMessageBox.warning(self,"오류","심볼을 입력하세요."); return
        self._send_order(
            contract  = make_stock_contract(sym),
            action    = self.o1_action.currentText(),
            qty       = self.o1_qty.value(),
            order_type= self.o1_type.currentText(),
            price_str = self.o1_price.text().strip(),
            label     = f"호가주문 {sym}"
        )

    def _place_order2(self):
        """직접 입력 주문."""
        sym = self.o2_sym.text().strip().upper()
        if not sym:
            QMessageBox.warning(self,"오류","심볼을 입력하세요."); return
        is_opt = self.o2_sec.currentIndex() == 1
        if is_opt:
            exp = self.o2_expiry.text().strip()
            stk = self.o2_strike.text().strip()
            rgt = self.o2_right.currentText()
            if not exp or not stk:
                QMessageBox.warning(self,"오류","만기일/행사가를 입력하세요."); return
            try:
                contract = make_opt_contract(sym, float(stk), rgt, exp)
            except Exception as e:
                QMessageBox.warning(self,"계약 오류",str(e)); return
        else:
            contract = make_stock_contract(sym)
        self._send_order(
            contract  = contract,
            action    = self.o2_action.currentText(),
            qty       = self.o2_qty.value(),
            order_type= self.o2_type.currentText(),
            price_str = self.o2_price.text().strip(),
            label     = f"직접주문 {sym}"
        )

    def _market_sell(self):
        """선택된 잔고 심볼을 시장가 매도."""
        rows = set(it.row() for it in self.tbl_pos.selectedItems())
        if not rows:
            QMessageBox.information(self,"안내","잔고 테이블에서 종목을 선택하세요.")
            return
        for r in rows:
            sym_it = self.tbl_pos.item(r, 0)
            qty_it = self.tbl_pos.item(r, 1)
            if not sym_it or not qty_it: continue
            sym = sym_it.text().strip()
            try: qty = int(float(qty_it.text().replace(",","")))
            except: qty = 1
            self._send_order(
                contract   = make_stock_contract(sym),
                action     = "SELL", qty=qty,
                order_type = "MKT", price_str="0",
                label      = f"시장가매도 {sym}")

    def _send_order(self, contract, action, qty, order_type,
                    price_str, label="주문"):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        try:   lmt = float(price_str) if price_str else 0.0
        except: lmt = 0.0
        oid = self.mw.ib.get_next_id()
        if oid is None:
            QMessageBox.warning(self,"오류","OrderID 없음. 잠시 후 재시도."); return
        order = make_order(action, qty, order_type, lmt_price=lmt)
        try:
            self.mw.ib.placeOrder(oid, contract, order)
            self._log(f"✅ {label} 전송 — {action} {qty} @ {lmt:.2f} ({order_type}) oid={oid}")
        except Exception as e:
            self._log(f"❌ 주문 실패: {e}")
        QTimer.singleShot(500, self._req_open_orders)

    # ─────────────────────────────────────────────────────────
    # 정정 / 취소
    # ─────────────────────────────────────────────────────────
    def _amend_order(self):
        oid_t = self.amd_oid.text().strip()
        if not oid_t:
            QMessageBox.warning(self,"오류","OrderID를 입력하세요."); return
        try: oid = int(oid_t)
        except: QMessageBox.warning(self,"오류","OrderID는 숫자여야 합니다."); return
        if oid not in self._open_orders:
            QMessageBox.warning(self,"오류",f"OrderID {oid}를 미체결에서 찾을 수 없습니다."); return
        info = self._open_orders[oid]
        try:   new_price = float(self.amd_price.text().strip())
        except: new_price = 0.0
        new_qty = self.amd_qty.value()
        contract = make_stock_contract(info.get("sym",""))
        order    = make_order(
            info.get("action","BUY"), new_qty,
            info.get("order_type","LMT"), lmt_price=new_price)
        try:
            self.mw.ib.placeOrder(oid, contract, order)
            self._log(f"✏ 정정 — oid={oid}  qty={new_qty}  price={new_price:.2f}")
        except Exception as e:
            self._log(f"❌ 정정 실패: {e}")
        QTimer.singleShot(500, self._req_open_orders)

    def _cancel_order(self):
        oid_t = self.amd_oid.text().strip()
        if not oid_t:
            QMessageBox.warning(self,"오류","OrderID를 입력하세요."); return
        try: oid = int(oid_t)
        except: QMessageBox.warning(self,"오류","OrderID는 숫자여야 합니다."); return
        ret = QMessageBox.question(
            self,"취소 확인",f"OrderID {oid}를 취소합니까?",
            QMessageBox.Yes|QMessageBox.No)
        if ret != QMessageBox.Yes: return
        try:
            self.mw.ib.cancelOrder(oid)
            self._log(f"❌ 취소 요청 — oid={oid}")
        except Exception as e:
            self._log(f"❌ 취소 실패: {e}")
        QTimer.singleShot(500, self._req_open_orders)

    # ─────────────────────────────────────────────────────────
    # 잔고
    # ─────────────────────────────────────────────────────────
    def _req_positions(self):
        if not self.mw.connected: return
        self._positions.clear(); self.tbl_pos.setRowCount(0)
        self.mw.ib.reqPositions()

    def _on_position(self, acct, sym, right, qty, avg_cost):
        if qty == 0: return
        self._positions[sym] = {
            "qty": qty, "avg_cost": avg_cost, "right": right}
        r = self.tbl_pos.rowCount(); self.tbl_pos.insertRow(r)
        self.tbl_pos.setItem(r,0,_mk(sym,"#ffd700"))
        self.tbl_pos.setItem(r,1,_mk(f"{int(qty):,}"))
        self.tbl_pos.setItem(r,2,_mk(f"{avg_cost:,.2f}"))
        self.tbl_pos.setItem(r,3,_mk("조회중","#aaa"))
        self.tbl_pos.setItem(r,4,_mk("―"))
        self.tbl_pos.setItem(r,5,_mk("―"))

    def _on_position_end(self):
        self._log(f"잔고 {self.tbl_pos.rowCount()}건 수신")
        # 잔고 종목 현재가 요청
        for i, (sym, d) in enumerate(self._positions.items()):
            if i >= 30: break
            rid = REQ_TRADE_POS + i
            try: self.mw.ib.cancelMktData(rid)
            except: pass
            self.mw.ib.reqMktData(
                rid, make_und_contract(sym), "232", False, False, [])
            d["rid"] = rid; d["row"] = i

    def _on_pos_tick(self, rid, tt, price):
        if price <= 0: return
        if tt not in (4, 68, 75, 14): return
        for sym, d in self._positions.items():
            if d.get("rid") != rid: continue
            r = d.get("row", 0)
            avg = d.get("avg_cost", 0); qty = d.get("qty", 0)
            pnl = (price - avg) * qty if avg > 0 else 0
            pct = (price - avg) / avg * 100 if avg > 0 else 0
            col_pnl = "#00e676" if pnl >= 0 else "#ff5252"
            self.tbl_pos.setItem(r,3,_mk(f"{price:,.2f}","#00ff88"))
            self.tbl_pos.setItem(r,4,_mk(f"{pnl:+,.2f}",col_pnl))
            self.tbl_pos.setItem(r,5,_mk(f"{pct:+.2f}%",col_pnl))
            break

    def _on_pos_dbl(self, row, col):
        """잔고 더블클릭 → 주문2에 매도 자동 세팅."""
        sym_it = self.tbl_pos.item(row, 0)
        qty_it = self.tbl_pos.item(row, 1)
        if not sym_it: return
        sym = sym_it.text().strip()
        try: qty = int(float(qty_it.text().replace(",",""))) if qty_it else 1
        except: qty = 1
        # 주문2 패널에 자동 세팅
        self.o2_sym.setText(sym)
        self.o2_sec.setCurrentIndex(0)   # STK
        self.o2_action.setCurrentText("SELL")
        self.o2_qty.setValue(abs(qty))
        self.o2_type.setCurrentText("LMT")
        cur_it = self.tbl_pos.item(row, 3)
        if cur_it and cur_it.text() not in ("―","조회중"):
            self.o2_price.setText(cur_it.text().replace(",",""))
        self._log(f"잔고 더블클릭 → 매도 세팅: {sym} {qty}주")

    # ─────────────────────────────────────────────────────────
    # 미체결
    # ─────────────────────────────────────────────────────────
    def _req_open_orders(self):
        if not self.mw.connected: return
        self._open_orders.clear(); self.tbl_open.setRowCount(0)
        self.mw.ib.reqAllOpenOrders()

    def _on_open_order(self, oid, sym, right, action, qty, price, status):
        self._open_orders[oid] = {
            "sym":sym,"action":action,"qty":qty,
            "price":price,"status":status,"order_type":"LMT"}
        r = self.tbl_open.rowCount(); self.tbl_open.insertRow(r)
        col_a = "#00e676" if action=="BUY" else "#ff5252"
        self.tbl_open.setItem(r,0,_mk(str(oid),"#aaa"))
        self.tbl_open.setItem(r,1,_mk(sym,"#ffd700"))
        self.tbl_open.setItem(r,2,_mk(action,col_a))
        self.tbl_open.setItem(r,3,_mk(f"{int(qty):,}"))
        self.tbl_open.setItem(r,4,_mk(f"{price:,.2f}" if price else "MKT"))
        col_s = ("#00e676" if "Filled" in status
                 else "#ff8800" if "Submit" in status else "#aaa")
        self.tbl_open.setItem(r,5,_mk(status,col_s))

    def _on_open_dbl(self, row, col):
        """미체결 더블클릭 → 정정 패널에 자동 세팅."""
        oid_it = self.tbl_open.item(row, 0)
        qty_it = self.tbl_open.item(row, 3)
        prc_it = self.tbl_open.item(row, 4)
        if not oid_it: return
        oid = oid_it.text().strip()
        self.amd_oid.setText(oid)
        if qty_it:
            try: self.amd_qty.setValue(int(float(qty_it.text().replace(",",""))))
            except: pass
        if prc_it and prc_it.text() not in ("MKT","―"):
            self.amd_price.setText(prc_it.text().replace(",",""))
        self._log(f"미체결 더블클릭 → 정정 세팅: oid={oid}")
        self.lbl_fill.setText(f"정정 대기: oid={oid}")

    # ─────────────────────────────────────────────────────────
    # 체결 / 주문 상태 콜백
    # ─────────────────────────────────────────────────────────
    def _on_exec(self, oid, sym, side, qty, price):
        msg = f"✅ 체결: oid={oid}  {sym}  {side}  {int(qty)}주  @ {price:,.2f}"
        self._log(msg)
        self.lbl_fill.setText(
            f"체결: {sym} {side} {int(qty)}주 @ {price:,.2f}")
        self.lbl_fill.setStyleSheet(
            "color:#00e676;font-weight:bold;font-size:12px;border:none;")
        # 체결 후 잔고/미체결 갱신
        QTimer.singleShot(1000, self._req_positions)
        QTimer.singleShot(1000, self._req_open_orders)

    def _on_order_status(self, oid, status, filled, remaining):
        # 미체결 테이블 상태 업데이트
        for r in range(self.tbl_open.rowCount()):
            oid_it = self.tbl_open.item(r, 0)
            if oid_it and oid_it.text() == str(oid):
                col = ("#00e676" if "Filled" in status
                       else "#ff8800" if "Submit" in status else "#aaa")
                self.tbl_open.setItem(r, 5, _mk(status, col))
                break
        if "Filled" in status:
            self._log(f"주문 완전체결: oid={oid}  filled={int(filled)}")

    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 테이블 재스타일."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        for tbl in (self.tbl_bid, self.tbl_pos, self.tbl_open):
            _apply_table_theme(tbl, dark)