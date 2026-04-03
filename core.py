"""
core.py — 공통 상수 / 시그널 브릿지 / IBKR 래퍼 / 헬퍼 함수
════════════════════════════════════════════════════════════════
모든 탭 모듈이 이 파일에서 import 합니다.
변경 사항: 설정 상수, reqId 범위, 종목 파라미터, 스타일
"""

import os, json, csv
from datetime import datetime, timedelta, time as dt_time, date as dt_date
from pathlib import Path
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo   # pip install backports.zoneinfo
    except ImportError:
        # 최후 fallback: pytz 사용
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

# ── ibapi ─────────────────────────────────────────────────────
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IBAPI_AVAILABLE = True
except ModuleNotFoundError:
    IBAPI_AVAILABLE = False
    print("[경고] ibapi 미설치 → pip install ibapi")

# ── pyqtgraph ─────────────────────────────────────────────────
try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QPushButton, QSlider, QSizeGrip, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QBrush

# ══════════════════════════════════════════════════════════════
# 1. 전역 설정 상수
# ══════════════════════════════════════════════════════════════
TWS_HOST   = "127.0.0.1"
TWS_PORT   = 4001
CLIENT_ID  = 1
SAVE_DIR   = Path("data")          # 저장 디렉터리
SAVE_DIR.mkdir(exist_ok=True)

DEFAULT_FONT_SIZE  = 16
ALERT_COOLDOWN     = 600           # 추적기 재알림 쿨다운 (초)
N_STRIKES          = 30            # 콜/풋 테이블 최대 행 수 (SpinBox로 실제 사용 수 조절)
GREEKS_MATRIX_N    = 20            # Greeks Matrix ATM 기준 상하 개수
GREEKS_AUTOSAVE_S  = 15            # Greeks 자동저장 주기 (초)

# ── reqId 범위 (겹치지 않게 100 단위로 구분) ──────────────────
REQ_UND       = 1          # 기초자산 현재가
REQ_CALL      = 1000       # 콜 옵션 1000~1099
REQ_PUT       = 2000       # 풋 옵션 2000~2099
REQ_MULTI     = 3000       # 복수현재가 3000~3299 (슬롯당 100)
REQ_CHAIN     = 4000       # Greeks Matrix 콜 4000~4199
REQ_CHAIN_P   = 4200       # Greeks Matrix 풋 4200~4399
REQ_OI        = 5000       # OI 조회 5000~5499
REQ_HIST      = 6000       # IBKR 히스토리 6000~6099
REQ_SNIPER    = 7000       # 스나이퍼 시세 7000~7499
REQ_ACCT      = 9001

# ── 종목 파라미터 ─────────────────────────────────────────────
# symbol → (secType, exchange, multiplier, strike_step)
SYMBOL_CFG = {
    # symbol → (secType, exchange, multiplier, strike_step)
    # exchange는 reqMktData 기준 → 인덱스/주식 옵션 모두 SMART
    # tradingClass는 make_opt_contract에서 별도 설정
    "SPX":   ("OPT", "SMART", "100",  5),
    "SPXW":  ("OPT", "SMART", "100",  5),
    "NDX":   ("OPT", "SMART", "100", 25),
    "RUT":   ("OPT", "SMART", "100",  5),
    "VIX":   ("OPT", "SMART", "100",  1),
    "XSP":   ("OPT", "SMART", "100",  1),
    "AAPL":  ("OPT", "SMART", "100",  1),
    "TSLA":  ("OPT", "SMART", "100",  2),
    "NVDA":  ("OPT", "SMART", "100",  2),
    "AMZN":  ("OPT", "SMART", "100",  2),
    "MSFT":  ("OPT", "SMART", "100",  2),
    "META":  ("OPT", "SMART", "100",  2),
    "GOOG":  ("OPT", "SMART", "100",  2),
    "GOOGL": ("OPT", "SMART", "100",  2),
    "QQQ":   ("OPT", "SMART", "100",  1),
    "SPY":   ("OPT", "SMART", "100",  1),
    "IWM":   ("OPT", "SMART", "100",  1),
}
DEFAULT_CFG  = ("OPT", "SMART", "100", 1)
INDEX_SYM    = {"SPX","SPXW","NDX","RUT","VIX","DJX","XSP"}

ACCT_TAGS = ("NetLiquidation,TotalCashValue,BuyingPower,"
             "UnrealizedPnL,RealizedPnL,GrossPositionValue,"
             "MaintMarginReq,InitMarginReq")

# ══════════════════════════════════════════════════════════════
# 2. 스타일
# ══════════════════════════════════════════════════════════════
BASE_STYLE = """
QMainWindow,QDialog{{background:#0e0e1a;}}
QWidget{{background:#0e0e1a;color:#dde0f0;font-size:{fs}px;}}
QGroupBox{{border:1px solid #2e3060;border-radius:5px;
           margin-top:10px;padding-top:6px;font-weight:bold;}}
QGroupBox::title{{subcontrol-origin:margin;left:8px;color:#5dade2;}}
QPushButton{{background:#1c1c3a;color:#dde0f0;border:1px solid #3a3a7a;
             border-radius:4px;padding:4px 10px;font-size:{fs}px;}}
QPushButton:hover{{background:#2a2a5a;}}
QPushButton:pressed{{background:#0e0e2a;}}
QLineEdit,QComboBox,QSpinBox{{background:#0a0a18;border:1px solid #2e3060;
              border-radius:4px;padding:3px;color:#dde0f0;font-size:{fs}px;}}
QComboBox::drop-down{{border:none;}}
QComboBox QAbstractItemView{{background:#0a0a18;color:#dde0f0;
                              selection-background-color:#1c1c3a;}}
QListWidget{{background:#0a0a18;border:1px solid #2e3060;border-radius:4px;
             font-size:{fs}px;}}
QTextEdit{{background:#050510;border:1px solid #2e3060;border-radius:4px;
           color:#00e676;font-family:Consolas,monospace;font-size:{logfs}px;}}
QTableWidget{{background:#08080f;gridline-color:#1e1e3a;
              border:1px solid #2e3060;font-size:{fs}px;}}
QTableWidget::item{{padding:2px;}}
QTableWidget::item:selected{{background:#1c3a6a;}}
QHeaderView::section{{background:#141430;color:#5dade2;
                      border:1px solid #1e1e3a;padding:3px;font-size:{fs}px;}}
QRadioButton,QCheckBox{{color:#dde0f0;font-size:{fs}px;}}
QTabBar::tab{{background:#141430;color:#888;padding:5px 12px;
              border:1px solid #2e3060;border-bottom:none;font-size:{tfs}px;}}
QTabBar::tab:selected{{background:#1c1c3a;color:#fff;font-weight:bold;}}
QTabWidget::pane{{border:1px solid #2e3060;}}
QSplitter::handle{{background:#1e1e3a;}}
QSlider::groove:horizontal{{height:4px;background:#1e1e3a;border-radius:2px;}}
QSlider::handle:horizontal{{width:14px;height:14px;background:#5dade2;
                             border-radius:7px;margin:-5px 0;}}
"""

def make_style(fs: int = DEFAULT_FONT_SIZE) -> str:
    return BASE_STYLE.format(fs=fs, logfs=max(10, fs-4), tfs=max(11, fs-2))


# ══════════════════════════════════════════════════════════════
# 3. 시그널 브릿지 (스레드 → Qt UI 안전 통신)
# ══════════════════════════════════════════════════════════════
class SignalBridge(QObject):
    tick_price     = pyqtSignal(int, int, float)
    tick_option    = pyqtSignal(int, int, float, float, float, float, float, float)
    connected      = pyqtSignal()
    error_sig      = pyqtSignal(int, int, str)
    # 계좌
    acct_value     = pyqtSignal(str, str, str, str)   # tag,val,cur,acct
    acct_end       = pyqtSignal()
    # 포지션
    position_sig   = pyqtSignal(str, str, str, float, float)
    position_end   = pyqtSignal()
    # 미체결
    open_order_sig = pyqtSignal(int, str, str, str, float, float, str)
    # 체결 (execDetails)
    exec_sig       = pyqtSignal(int, str, str, float, float)  # oid,sym,side,qty,price
    # 주문 상태
    order_status_sig = pyqtSignal(int, str, float, float)     # oid,status,filled,remaining
    # 히스토리
    hist_bar       = pyqtSignal(int, object)
    hist_end       = pyqtSignal(int)

# 전역 브릿지 싱글턴
bridge = SignalBridge()

# ══════════════════════════════════════════════════════════════
# 비동기 tick 라우터
# ── 탭별 reqId 범위를 등록해두고 tick이 오면 해당 탭의
#    전용 슬롯으로만 emit → 탭 간 상호 간섭·처리 지연 최소화
# ══════════════════════════════════════════════════════════════
class TickRouter(QObject):
    """
    tick_price / tick_option 시그널을 reqId 범위로 분기한다.
    각 탭은 register(rid_start, rid_end, slot) 으로 구독,
    전역 bridge.tick_price 를 직접 연결하는 대신 이 라우터를
    경유하면 불필요한 탭까지 wake-up 되는 현상을 방지한다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._price_routes  = []   # [(start,end,slot), ...]
        self._option_routes = []
        bridge.tick_price.connect(self._route_price,  Qt.QueuedConnection)
        bridge.tick_option.connect(self._route_option, Qt.QueuedConnection)

    def register_price(self, rid_start: int, rid_end: int, slot):
        self._price_routes.append((rid_start, rid_end, slot))

    def register_option(self, rid_start: int, rid_end: int, slot):
        self._option_routes.append((rid_start, rid_end, slot))

    def unregister_price(self, slot):
        self._price_routes = [(s,e,fn) for s,e,fn in self._price_routes if fn!=slot]

    def unregister_option(self, slot):
        self._option_routes = [(s,e,fn) for s,e,fn in self._option_routes if fn!=slot]

    def _route_price(self, rid: int, tt: int, price: float):
        for start, end, slot in self._price_routes:
            if start <= rid <= end:
                try: slot(rid, tt, price)
                except Exception as ex: print(f"[Router] price slot err: {ex}")

    def _route_option(self, rid: int, tt: int, iv, delta, op, gamma, vega, theta):
        for start, end, slot in self._option_routes:
            if start <= rid <= end:
                try: slot(rid, tt, iv, delta, op, gamma, vega, theta)
                except Exception as ex: print(f"[Router] option slot err: {ex}")

# 전역 라우터 싱글턴 (main.py 에서 초기화 후 각 탭이 사용)
router = TickRouter()


# ══════════════════════════════════════════════════════════════
# 4. IBKR 래퍼
# ══════════════════════════════════════════════════════════════
if IBAPI_AVAILABLE:
    class IBapi(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._next_id = None

        def nextValidId(self, orderId):
            self._next_id = orderId
            bridge.connected.emit()

        def tickPrice(self, reqId, tickType, price, attrib):
            bridge.tick_price.emit(reqId, int(tickType), float(price))

        def tickOptionComputation(self, reqId, tickType, tickAttrib,
                                  impliedVol, delta, optPrice, pvDividend,
                                  gamma, vega, theta, undPrice):
            def f(v): return float(v) if v is not None else 0.0
            bridge.tick_option.emit(reqId, int(tickType),
                f(impliedVol), f(delta), f(optPrice), f(gamma), f(vega), f(theta))

        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
            bridge.error_sig.emit(reqId, int(errorCode), str(errorString))

        def accountSummary(self, reqId, account, tag, value, currency):
            bridge.acct_value.emit(str(tag), str(value), str(currency), str(account))

        def accountSummaryEnd(self, reqId):
            bridge.acct_end.emit()

        def position(self, account, contract, position, avgCost):
            bridge.position_sig.emit(
                str(account), str(contract.symbol),
                str(getattr(contract, 'right', '')),
                float(position), float(avgCost))

        def positionEnd(self):
            bridge.position_end.emit()

        def openOrder(self, orderId, contract, order, orderState):
            bridge.open_order_sig.emit(
                int(orderId), str(contract.symbol),
                str(getattr(contract, 'right', '')),
                str(order.action), float(order.totalQuantity),
                float(order.lmtPrice if order.lmtPrice else 0),
                str(orderState.status))

        def orderStatus(self, orderId, status, filled, remaining,
                        avgFillPrice, permId, parentId, lastFillPrice,
                        clientId, whyHeld, mktCapPrice):
            bridge.order_status_sig.emit(
                int(orderId), str(status), float(filled), float(remaining))

        def execDetails(self, reqId, contract, execution):
            bridge.exec_sig.emit(
                int(execution.orderId),
                str(contract.symbol),
                str(execution.side),
                float(execution.shares),
                float(execution.price))

        def historicalData(self, reqId, bar):
            bridge.hist_bar.emit(reqId, bar)

        def historicalDataEnd(self, reqId, start, end):
            bridge.hist_end.emit(reqId)

        def get_next_id(self):
            oid = self._next_id
            if oid is not None:
                self._next_id += 1
            return oid

else:
    class IBapi:
        def __init__(self): self._next_id = 10000
        def connect(self,*a): pass
        def run(self): pass
        def disconnect(self): pass
        def isConnected(self): return False
        def reqMktData(self,*a): pass
        def cancelMktData(self,*a): pass
        def reqMarketDataType(self,*a): pass
        def reqAccountSummary(self,*a): pass
        def cancelAccountSummary(self,*a): pass
        def reqPositions(self): pass
        def cancelPositions(self): pass
        def reqAllOpenOrders(self): pass
        def reqHistoricalData(self,*a): pass
        def placeOrder(self,*a): pass
        def cancelOrder(self,*a): pass
        def get_next_id(self): return None


# ══════════════════════════════════════════════════════════════
# 5. 계약 팩토리 헬퍼
# ══════════════════════════════════════════════════════════════
# IBKR SPX 옵션 규칙:
#   c.symbol    = "SPX"  (SPXW여도 symbol은 항상 SPX)
#   tradingClass = "SPX"  → AM 정산 (월물·수요일 0DTE)
#   tradingClass = "SPXW" → PM 정산 (위클리·금요일·화/목 0DTE)
#   NDX 위클리  = tradingClass "NDXP"
_TRADING_CLASS = {
    "NDX":  "NDX",
    "NDXP": "NDXP",
    "RUT":  "RUT",
    "VIX":  "VIX",
    "XSP":  "XSP",
}

def _resolve_spx_trading_class(symbol: str, expiry: str, tag: str = "") -> str:
    """
    SPX/SPXW 옵션의 tradingClass 자동 판별.
    symbol : "SPX" 또는 "SPXW"
    expiry : "YYYYMMDD"
    tag    : build_expiry_list의 세 번째 요소 ("0DTE","W","M","")
    반환   : "SPX" 또는 "SPXW"
    """
    sym_up = symbol.upper()
    # 명시적으로 SPXW가 지정된 경우
    if sym_up == "SPXW":
        return "SPXW"
    # tag 기반 판별
    if tag == "0DTE":
        try:
            wd = datetime.strptime(expiry, "%Y%m%d").weekday()
            # 수요일(2) = SPX(AM 정산), 금요일(4) = SPXW(PM 정산)
            return "SPX" if wd == 2 else "SPXW"
        except: pass
    if tag == "W":
        return "SPXW"   # 위클리는 항상 SPXW
    if tag == "M":
        return "SPX"    # 월물(세 번째 금요일)은 SPX AM 정산
    # tag 없이 날짜로 판별
    try:
        wd = datetime.strptime(expiry, "%Y%m%d").weekday()
        # 금요일이 아닌 만기 = SPXW(화/목 0DTE 등)
        return "SPXW" if wd != 2 else "SPX"
    except:
        return "SPX"    # 판별 불가 → SPX 기본

def make_opt_contract(symbol: str, strike: float, right: str,
                      expiry: str, tag: str = "") -> "Contract":
    """
    symbol  : "SPX", "SPXW", "NDX", "AAPL" 등
    strike  : 행사가
    right   : "C" / "CALL" / "P" / "PUT"
    expiry  : "YYYYMMDD"
    tag     : build_expiry_list의 tag ("0DTE","W","M","") — SPX 판별에 사용
    """
    sym_up = symbol.upper()

    # ── SPX / SPXW 특별 처리 ─────────────────────────────────
    if sym_up in ("SPX", "SPXW"):
        sec, exch, mult, _ = SYMBOL_CFG.get("SPX", DEFAULT_CFG)
        tc = _resolve_spx_trading_class(sym_up, expiry, tag)
        c = Contract()
        c.symbol       = "SPX"       # 항상 SPX (SPXW여도)
        c.tradingClass = tc          # "SPX" or "SPXW"
        c.secType      = sec
        c.exchange     = "CBOE"      # ✅ SPX/SPXW 옵션은 반드시 CBOE (SMART → ambiguous ERR 200)
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = mult
        c.lastTradeDateOrContractMonth = expiry
        return c

    # ── NDX 위클리 (NDXP) 처리 ───────────────────────────────
    if sym_up == "NDX":
        sec, exch, mult, _ = SYMBOL_CFG.get("NDX", DEFAULT_CFG)
        # 위클리(W) 또는 금요일 아닌 만기 → NDXP
        try:
            wd = datetime.strptime(expiry, "%Y%m%d").weekday()
            tc = "NDXP" if (tag == "W" or wd != 2) else "NDX"
        except:
            tc = "NDX"
        c = Contract()
        c.symbol       = "NDX"
        c.tradingClass = tc
        c.secType      = sec
        c.exchange     = exch
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = mult
        c.lastTradeDateOrContractMonth = expiry
        return c

    # ── 일반 주식/기타 옵션 ───────────────────────────────────
    sec, exch, mult, _ = SYMBOL_CFG.get(sym_up, DEFAULT_CFG)
    c = Contract()
    c.symbol     = sym_up
    c.secType    = sec
    c.exchange   = exch
    c.currency   = "USD"
    c.strike     = float(strike)
    c.right      = "C" if right.upper() in ("C", "CALL") else "P"
    c.multiplier = mult
    c.lastTradeDateOrContractMonth = expiry
    # tradingClass 지정 → IBKR가 해당 만기만 조회해서 속도 향상
    # 미지정 시 모든 만기 탐색 → 느림/ambiguous 원인
    tc = _TRADING_CLASS.get(sym_up, sym_up)   # 없으면 심볼 그대로 사용
    c.tradingClass = tc
    return c

def make_und_contract(symbol: str) -> "Contract":
    c = Contract()
    c.symbol   = symbol.upper()
    c.currency = "USD"
    if symbol.upper() in INDEX_SYM:
        c.secType  = "IND"
        # IND는 거래소 직접 지정 필요 (SMART 미지원)
        c.exchange = "NASDAQ" if symbol.upper() in ("NDX",) else "CBOE"
    else:
        c.secType  = "STK"
        c.exchange = "SMART"
    return c


# ══════════════════════════════════════════════════════════════
# 6. 만기일 유틸
# ══════════════════════════════════════════════════════════════
def _easter(year: int) -> datetime:
    """서양 부활절 날짜 계산 (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100; c = year % 100
    d = b // 4;      e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i = c // 4;      k = c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day   = ((h + l - 7*m + 114) % 31) + 1
    return datetime(year, month, day)

def _us_market_holidays(year: int) -> set:
    """미국 주식시장 연간 휴장일 집합 (date 객체)."""
    hols = set()
    # 성금요일 (부활절 -2일)
    hols.add((_easter(year) - timedelta(days=2)).date())
    # 신정
    ny = dt_date(year, 1, 1)
    if ny.weekday() == 5: ny = dt_date(year, 12, 31)
    elif ny.weekday() == 6: ny = dt_date(year, 1, 2)
    hols.add(ny)
    # MLK Day: 1월 세 번째 월요일
    d = dt_date(year, 1, 1); cnt = 0
    while True:
        if d.weekday() == 0: cnt += 1
        if cnt == 3: hols.add(d); break
        d += timedelta(days=1)
    # Presidents Day: 2월 세 번째 월요일
    d = dt_date(year, 2, 1); cnt = 0
    while True:
        if d.weekday() == 0: cnt += 1
        if cnt == 3: hols.add(d); break
        d += timedelta(days=1)
    # Memorial Day: 5월 마지막 월요일
    d = dt_date(year, 5, 31)
    while d.weekday() != 0: d -= timedelta(days=1)
    hols.add(d)
    # Juneteenth: 6월 19일
    jt = dt_date(year, 6, 19)
    if jt.weekday() == 5: jt = dt_date(year, 6, 18)
    elif jt.weekday() == 6: jt = dt_date(year, 6, 20)
    hols.add(jt)
    # Independence Day: 7월 4일
    id_ = dt_date(year, 7, 4)
    if id_.weekday() == 5: id_ = dt_date(year, 7, 3)
    elif id_.weekday() == 6: id_ = dt_date(year, 7, 5)
    hols.add(id_)
    # Labor Day: 9월 첫 번째 월요일
    d = dt_date(year, 9, 1)
    while d.weekday() != 0: d += timedelta(days=1)
    hols.add(d)
    # Thanksgiving: 11월 네 번째 목요일
    d = dt_date(year, 11, 1); cnt = 0
    while True:
        if d.weekday() == 3: cnt += 1
        if cnt == 4: hols.add(d); break
        d += timedelta(days=1)
    # Christmas: 12월 25일
    xm = dt_date(year, 12, 25)
    if xm.weekday() == 5: xm = dt_date(year, 12, 24)
    elif xm.weekday() == 6: xm = dt_date(year, 12, 26)
    hols.add(xm)
    return hols

_HOLIDAY_CACHE: dict = {}

def is_trading_day(d) -> bool:
    """d (datetime 또는 date)가 미국 주식시장 거래일인지 반환."""
    if isinstance(d, datetime): d = d.date()
    if d.weekday() >= 5: return False
    year = d.year
    if year not in _HOLIDAY_CACHE:
        _HOLIDAY_CACHE[year] = _us_market_holidays(year)
    return d not in _HOLIDAY_CACHE[year]

def next_wd(base: datetime, wd: int) -> datetime:
    """base 이후 첫 번째 wd 요일 (당일 제외, 0=월~4=금)."""
    days = (wd - base.weekday()) % 7 or 7
    return base + timedelta(days=days)

def next_trading_friday(base: datetime, skip: int = 0) -> datetime:
    """base 이후 skip번째 거래 금요일 (성금요일 등 휴장일 자동 스킵)."""
    fri = next_wd(base, 4)
    found = 0
    while True:
        if is_trading_day(fri):
            if found == skip:
                return fri
            found += 1
        fri += timedelta(weeks=1)

def build_expiry_list(sym: str = "SPX"):
    """콤보박스용 만기일 목록 -> [(label, YYYYMMDD, tag), ...]
    SPX/SPXW : 0DTE(수금) + 위클리 금요일 + 월물
    주식/ETF  : 이번주 + 다음주 월~금 전체 + 월물
    성금요일 등 미국 휴장일은 자동 제외합니다.
    """
    sym_up = sym.upper().replace("SPXW", "SPX")
    today  = datetime.today()
    entries = []

    is_spx = sym_up in ("SPX", "NDX", "RUT", "VIX", "XSP")

    if is_spx:
        # ── SPX 계열: 기존 로직 유지 ─────────────────────────
        # [0DTE] 오늘이 거래일인 수.금만
        if today.weekday() in (2, 4) and is_trading_day(today):
            entries.append((
                "[0DTE] 오늘 %s" % today.strftime("%m/%d(%a)"),
                today.strftime("%Y%m%d"), "0DTE"))

        # [W] 위클리 거래 금요일 3개 (휴장 스킵)
        for n in range(3):
            fri = next_trading_friday(today, skip=n)
            if not any(e[1] == fri.strftime("%Y%m%d") for e in entries):
                entries.append((
                    "[W] %s" % fri.strftime("%m/%d(%a)"),
                    fri.strftime("%Y%m%d"), "W"))

    else:
        # ── 주식/ETF: 이번주 + 다음주 거래일 전체 ────────────
        # 이번주 월요일 기준으로 2주치 거래일 생성
        monday = today - timedelta(days=today.weekday())
        for week_offset in range(2):
            for wd in range(5):   # 월~금
                d = monday + timedelta(weeks=week_offset, days=wd)
                if d.date() >= today.date() and is_trading_day(d):
                    label_prefix = "오늘 " if d.date() == today.date() else \
                                   "내일 " if d.date() == (today + timedelta(days=1)).date() else ""
                    week_label   = "" if week_offset == 0 else "다음주 "
                    entries.append((
                        f"[W] {week_label}{label_prefix}{d.strftime('%m/%d(%a)')}",
                        d.strftime("%Y%m%d"), "W"))

    # ── 공통: 이번달/다음달 월물 ─────────────────────────────
    # 이번 달 세 번째 금요일
    d = today.replace(day=1); fris = []
    while d.month == today.month:
        if d.weekday() == 4: fris.append(d)
        d += timedelta(days=1)
    if len(fris) >= 3:
        mf = fris[2]
        if not is_trading_day(mf):
            mf += timedelta(days=1)
            while not is_trading_day(mf): mf += timedelta(days=1)
        ms = mf.strftime("%Y%m%d")
        if not any(e[1] == ms for e in entries):
            entries.append(("[M] 월물 %s" % mf.strftime("%m/%d"), ms, "M"))

    # 다음 달 세 번째 금요일
    if today.month == 12:
        nm = today.replace(year=today.year+1, month=1, day=1)
    else:
        nm = today.replace(month=today.month+1, day=1)
    d2 = nm; fris2 = []
    while d2.month == nm.month:
        if d2.weekday() == 4: fris2.append(d2)
        d2 += timedelta(days=1)
    if len(fris2) >= 3:
        mf2 = fris2[2]
        if not is_trading_day(mf2):
            mf2 += timedelta(days=1)
            while not is_trading_day(mf2): mf2 += timedelta(days=1)
        ms2 = mf2.strftime("%Y%m%d")
        if not any(e[1] == ms2 for e in entries):
            entries.append(("[M] 다음달 %s" % mf2.strftime("%m/%d"), ms2, "M"))

    entries.append(("직접 입력 YYYYMMDD", "CUSTOM", ""))
    return entries



# ══════════════════════════════════════════════════════════════
# 7. 공통 UI 헬퍼
# ══════════════════════════════════════════════════════════════

# 전역 테이블 목록 (다크모드 전환 시 일괄 테마 적용)
_all_tables: list = []

def _apply_table_theme(tbl: QTableWidget, dark: bool = True):
    """테이블에 다크/라이트 테마 QSS 직접 적용 — 부모 stylesheet 오염 차단."""
    if dark:
        tbl.setStyleSheet(
            "QTableWidget{"
            "background:#08080f;color:#dde0f0;"
            "gridline-color:#1e1e3a;border:1px solid #2e3060;"
            "alternate-background-color:#0c0c20;}"
            "QTableWidget::item{padding:2px;color:#dde0f0;}"
            "QTableWidget::item:selected{background:#1c3a6a;color:#ffffff;}"
            "QHeaderView::section{"
            "background:#141430;color:#5dade2;"
            "border:1px solid #1e1e3a;padding:3px;}"
        )
    else:
        tbl.setStyleSheet(
            "QTableWidget{"
            "background:#ffffff;color:#111111;"
            "gridline-color:#cccccc;border:1px solid #bbbbbb;"
            "alternate-background-color:#f5f7fa;}"
            "QTableWidget::item{padding:2px;color:#111111;}"
            "QTableWidget::item:selected{background:#bbdefb;color:#000000;}"
            "QHeaderView::section{"
            "background:#e3f2fd;color:#1565c0;"
            "border:1px solid #bbbbbb;padding:3px;}"
        )

def make_table(headers: list, rows: int = 0) -> QTableWidget:
    """기본 스타일 테이블 생성 (다크모드 자동 대응, 전역 목록에 등록)"""
    t = QTableWidget(rows, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    _apply_table_theme(t, dark=True)
    _all_tables.append(t)
    return t

def tbl_set(tbl: QTableWidget, row: int, col: int,
            text: str, color: str = None):
    """테이블 셀 값 설정"""
    item = tbl.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter)
        tbl.setItem(row, col, item)
    item.setText(str(text))
    if color:
        item.setForeground(QBrush(QColor(color)))

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════════════════
# 8. 그리드 탭 베이스 (12×4 엑셀 좌표) + 위젯 리사이즈
# ══════════════════════════════════════════════════════════════

_BTN_SS = (
    "QPushButton{background:#1a1a3a;color:#5dade2;border:1px solid #2e3060;"
    "border-radius:2px;font-size:8px;padding:0px;}"
    "QPushButton:hover{background:#2a2a5a;}"
)

class _FloatWin(QWidget):
    """위젯을 독립 플로팅 창으로 띄우는 래퍼."""
    def __init__(self, inner: QWidget, title: str, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(title)
        self.resize(600, 400)
        self.setStyleSheet("background:#0e0e1a;color:#dde0f0;")
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 4)
        self._inner = inner
        inner.setParent(self)
        vl.addWidget(inner)

    def closeEvent(self, ev):
        """창 닫으면 inner 위젯을 원래 frame으로 돌려보냄."""
        if hasattr(self, '_on_close_cb') and self._on_close_cb:
            self._on_close_cb(self._inner)
        ev.accept()


class _ResizableFrame(QFrame):
    """
    각 위젯 블록 래퍼.
    상단 미니바 버튼:
      ←  → : 열(가로) stretch 감소/증가  (0.2 단위, 범위 0.2~20)
      ↑  ↓ : 행(세로) stretch 감소/증가  (0.2 단위, 범위 0.2~20)
      ⤢    : 플로팅 팝업 창으로 분리
      ▲    : 접기  /  ▼ : 펼치기(복구)
    """
    _COLLAPSED_H  = 18
    _STRETCH_MIN  = 2     # ×10 스케일 → 실제 0.2
    _STRETCH_MAX  = 200   # ×10 스케일 → 실제 20.0
    _STRETCH_STEP = 2     # ×10 스케일 → 실제 0.2 단위
    _SCALE        = 10    # QGridLayout은 int만 받으므로 10배 스케일

    def __init__(self, inner: QWidget, coord_txt: str,
                 grid_ref, row: int, col: int, rspan: int, cspan: int,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "border:1px solid #1e2050;border-radius:3px;background:transparent;")
        self._collapsed    = False
        self._normal_min_h = 0
        self._grid_ref     = grid_ref
        self._row          = row
        self._col          = col
        self._rspan        = rspan
        self._cspan        = cspan
        self._float_win    = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(0)

        # ── 상단 미니바 ──────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(18)
        bar.setStyleSheet("background:transparent;border:none;")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(2, 0, 2, 0)
        bh.setSpacing(1)

        coord_lbl = QLabel(coord_txt)
        coord_lbl.setStyleSheet(
            "color:#3a4060;font-size:8px;font-weight:bold;"
            "border:none;background:transparent;")
        bh.addWidget(coord_lbl)
        bh.addStretch()

        def _btn(text, tip, cb):
            b = QPushButton(text)
            b.setFixedSize(16, 14)
            b.setStyleSheet(_BTN_SS)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            return b

        bh.addWidget(_btn("←", "가로 축소 (0.2단위)",
                          lambda: self._adj_col(-self._STRETCH_STEP)))
        bh.addWidget(_btn("→", "가로 확장 (0.2단위)",
                          lambda: self._adj_col(+self._STRETCH_STEP)))
        bh.addWidget(_btn("↑", "세로 축소 (0.2단위)",
                          lambda: self._adj_row(-self._STRETCH_STEP)))
        bh.addWidget(_btn("↓", "세로 확장 (0.2단위)",
                          lambda: self._adj_row(+self._STRETCH_STEP)))

        self._btn_float = _btn("⤢", "팝업 창으로 분리", self._on_float)
        bh.addWidget(self._btn_float)

        self._btn_toggle = _btn("▲", "접기", self._on_toggle)
        bh.addWidget(self._btn_toggle)

        outer.addWidget(bar)

        # ── 내용 위젯 ────────────────────────────────────────
        self._inner = inner
        outer.addWidget(inner, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ── stretch 조절 헬퍼 ────────────────────────────────────
    def _cur_col(self, c: int) -> int:
        v = self._grid_ref.columnStretch(c)
        return v if v > 0 else self._SCALE  # 기본값 1.0 (=10)

    def _cur_row(self, r: int) -> int:
        v = self._grid_ref.rowStretch(r)
        return v if v > 0 else self._SCALE

    def _adj_col(self, delta: int):
        g = self._grid_ref
        for c in range(self._col, self._col + self._cspan):
            nxt = max(self._STRETCH_MIN,
                      min(self._STRETCH_MAX, self._cur_col(c) + delta))
            g.setColumnStretch(c, nxt)

    def _adj_row(self, delta: int):
        g = self._grid_ref
        for r in range(self._row, self._row + self._rspan):
            nxt = max(self._STRETCH_MIN,
                      min(self._STRETCH_MAX, self._cur_row(r) + delta))
            g.setRowStretch(r, nxt)

    # ── 플로팅 팝업 ──────────────────────────────────────────
    def _on_float(self):
        if self._float_win and self._float_win.isVisible():
            self._float_win.raise_()
            return
        win = _FloatWin(self._inner,
                        f"위젯 [{self._row},{self._col}]", self.window())
        win._on_close_cb = self._return_inner
        self._float_win = win
        self._btn_float.setText("◩")
        self._btn_float.setToolTip("팝업 창 올리기")
        win.show()

    def _return_inner(self, inner: QWidget):
        inner.setParent(self)
        self.layout().insertWidget(1, inner, 1)
        self._btn_float.setText("⤢")
        self._btn_float.setToolTip("팝업 창으로 분리")
        self._float_win = None

    # ── 접기(▲) / 펼치기 복구(▼) ────────────────────────────
    def _on_toggle(self):
        if self._collapsed:
            # ▼ 클릭 → 펼치기 (복구)
            self._collapsed = False
            self._btn_toggle.setText("▲")
            self._btn_toggle.setToolTip("접기")
            self._inner.setVisible(True)
            self.setMaximumHeight(16777215)
            if self._normal_min_h > 0:
                self.setMinimumHeight(0)   # 제약 해제 후 레이아웃이 자연 크기로
        else:
            # ▲ 클릭 → 접기
            self._normal_min_h = self.height()
            self._collapsed = True
            self._btn_toggle.setText("▼")
            self._btn_toggle.setToolTip("펼치기 (복구)")
            self._inner.setVisible(False)
            self.setFixedHeight(self._COLLAPSED_H)


class GridTab(QWidget):
    """
    12열 × N행 그리드 베이스.
    add(widget, row, col, rspan, cspan) → _ResizableFrame 으로 배치.
    상단 미니바:  ← →(가로stretch)  ↑ ↓(세로stretch)  ⤢(팝업)  ▲(접기)
    """
    ROWS = 4
    COLS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(3)
        self._grid.setContentsMargins(4, 4, 4, 4)
        for c in range(self.COLS): self._grid.setColumnStretch(c, 1)
        for r in range(self.ROWS): self._grid.setRowStretch(r, 1)

    def add(self, widget: QWidget, row: int, col: int,
            rspan: int = 1, cspan: int = 1) -> QWidget:
        frame = _ResizableFrame(
            widget, f"[{row},{col}]",
            self._grid, row, col, rspan, cspan)
        self._grid.addWidget(frame, row, col, rspan, cspan)
        return frame


# ══════════════════════════════════════════════════════════════
# 9. 폰트 조절 바 + 탭 래퍼
# ══════════════════════════════════════════════════════════════


class TabWrapper(QWidget):
    """FontBar + 다크모드 토글 + GridTab을 수직으로 묶는 래퍼.
    각 탭의 설정(다크모드, 폰트크기 등)을 data/tab_settings.json에 저장/복원."""

    # 앱 전체 다크모드 상태 (공유)
    _global_dark: bool = False
    _instances: list = []

    def __init__(self, grid_tab, tab_name: str = "", parent=None):
        super().__init__(parent)
        self.grid_tab = grid_tab
        self.tab_name = tab_name or type(grid_tab).__name__
        TabWrapper._instances.append(self)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── 상단 바 (폰트 + 다크모드) ──────────────────────────
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet("background:#07070f;border-bottom:1px solid #1e2050;")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(6, 2, 6, 2); bh.setSpacing(6)

        # 폰트 슬라이더
        lbl_f = QLabel("폰트:")
        lbl_f.setStyleSheet("color:#5dade2;font-size:11px;border:none;")
        lbl_f.setFixedWidth(36)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 28)
        self.slider.setValue(DEFAULT_FONT_SIZE)
        self.slider.setFixedWidth(120); self.slider.setFixedHeight(16)
        self.lbl_v = QLabel(f"{DEFAULT_FONT_SIZE}px")
        self.lbl_v.setStyleSheet("color:#ffd700;font-size:11px;border:none;min-width:32px;")
        self.slider.valueChanged.connect(self._on_font)

        # 다크모드 버튼
        self.btn_dark = QPushButton("🌙 다크")
        self.btn_dark.setCheckable(True)
        self.btn_dark.setFixedHeight(22)
        self.btn_dark.setFixedWidth(72)
        self.btn_dark.setStyleSheet(
            "QPushButton{background:#1c1c3a;color:#aaa;border:1px solid #3a3a7a;"
            "border-radius:3px;font-size:11px;padding:1px 4px;}"
            "QPushButton:checked{background:#23395d;color:#90caf9;border-color:#5599cc;}")
        self.btn_dark.clicked.connect(self._on_dark_btn)

        bh.addWidget(lbl_f); bh.addWidget(self.slider); bh.addWidget(self.lbl_v)
        bh.addStretch()
        bh.addWidget(self.btn_dark)

        vl.addWidget(bar)
        vl.addWidget(grid_tab, 1)

        self.font_bar = bar   # 하위 호환성

        # ── 저장된 설정 복원 ────────────────────────────────────
        self._restore_settings()

    # ── 폰트 ─────────────────────────────────────────────────
    def _on_font(self, fs: int):
        self.lbl_v.setText(f"{fs}px")
        self._apply_font(fs)
        self._save_settings()

    def _apply_font(self, fs: int):
        self.grid_tab.setStyleSheet(
            f"QWidget{{font-size:{fs}px;}}"
            f"QLabel{{font-size:{fs}px;}}"
            f"QTableWidget{{font-size:{fs}px;}}"
            f"QPushButton{{font-size:{fs}px;}}"
            f"QLineEdit,QComboBox,QSpinBox{{font-size:{fs}px;}}"
            f"QHeaderView::section{{font-size:{fs}px;}}"
            f"QListWidget{{font-size:{fs}px;}}"
            f"QTextEdit{{font-size:{max(10,fs-4)}px;}}")

    # ── 다크모드 ──────────────────────────────────────────────
    def _on_dark_btn(self, checked: bool):
        TabWrapper._global_dark = checked
        # 모든 탭에 동기 적용
        for inst in TabWrapper._instances:
            inst._apply_dark(checked)
            inst.btn_dark.blockSignals(True)
            inst.btn_dark.setChecked(checked)
            inst.btn_dark.blockSignals(False)
        self._save_settings()

    def _apply_dark(self, dark: bool):
        """탭 위젯 자체 + grid_tab에 다크/라이트 테마 적용 + 모든 테이블 테마 동기화."""
        if dark:
            style = (
                "QWidget{background:#1e1e2e;color:#e0e0f0;}"
                "QGroupBox{border:1px solid #3a3a6a;border-radius:4px;"
                "margin-top:8px;padding-top:6px;font-weight:bold;}"
                "QGroupBox::title{subcontrol-origin:margin;left:6px;color:#90caf9;}"
                "QLineEdit,QSpinBox,QListWidget,QCalendarWidget"
                "{background:#12122a;color:#e0e0f0;border:1px solid #3a3a6a;border-radius:3px;}"
                "QPushButton{background:#1c1c3a;color:#e0e0f0;"
                "border:1px solid #3a3a7a;border-radius:3px;padding:2px 6px;}"
                "QPushButton:hover{background:#2a2a5a;}"
                "QComboBox{background:#12122a;color:#e0e0f0;border:1px solid #3a3a6a;"
                "border-radius:3px;}"
                "QComboBox QAbstractItemView{background:#12122a;color:#e0e0f0;"
                "selection-background-color:#1c3a6a;}"
                "QTextEdit{background:#050510;color:#00e676;border:1px solid #2a2a4a;}"
                "QCheckBox,QRadioButton{color:#e0e0f0;background:transparent;}"
                "QLabel{color:#e0e0f0;background:transparent;}"
                "QScrollArea{border:none;}"
            )
        else:
            style = (
                "QWidget{background:#f0f2f5;color:#111;}"
                "QGroupBox{border:1px solid #bbb;border-radius:4px;"
                "margin-top:8px;padding-top:6px;font-weight:bold;}"
                "QGroupBox::title{subcontrol-origin:margin;left:6px;color:#1565c0;}"
                "QLineEdit,QSpinBox,QListWidget,QCalendarWidget"
                "{background:#fff;color:#111;border:1px solid #bbb;border-radius:3px;}"
                "QPushButton{background:#e8eaf0;color:#111;"
                "border:1px solid #bbb;border-radius:3px;padding:2px 6px;}"
                "QPushButton:hover{background:#c5cae9;}"
                "QComboBox{background:#fff;color:#111;border:1px solid #bbb;border-radius:3px;}"
                "QComboBox QAbstractItemView{background:#fff;color:#111;"
                "selection-background-color:#bbdefb;}"
                "QTextEdit{background:#fff;color:#222;border:1px solid #ccc;}"
                "QCheckBox,QRadioButton{color:#111;background:transparent;}"
                "QLabel{color:#111;background:transparent;}"
                "QScrollArea{border:none;}"
            )
        self.grid_tab.setStyleSheet(style)

        # ── 테이블은 별도 QSS로 강제 적용 (부모 스타일 오염 방지) ──
        from core import _all_tables, _apply_table_theme
        for tbl in _all_tables:
            try:
                _apply_table_theme(tbl, dark=dark)
            except Exception:
                pass

        # tab_chart.py처럼 _apply_theme()을 가진 탭은 별도 처리
        if hasattr(self.grid_tab, '_apply_theme'):
            self.grid_tab.dark_mode = dark
            self.grid_tab._apply_theme()

    # ── 설정 저장/복원 ────────────────────────────────────────
    def _settings_key(self) -> str:
        return f"tab_settings_{self.tab_name}"

    def _save_settings(self):
        all_s = load_json("tab_settings.json", {})
        data = {
            "dark": self.btn_dark.isChecked(),
            "font": self.slider.value(),
        }
        # grid_tab이 _get_extra_settings() 를 구현하면 추가 저장
        if hasattr(self.grid_tab, '_get_extra_settings'):
            try:
                data.update(self.grid_tab._get_extra_settings())
            except Exception as e:
                print(f"[settings save] {e}")
        all_s[self.tab_name] = data
        save_json("tab_settings.json", all_s)

    def _restore_settings(self):
        all_s = load_json("tab_settings.json", {})
        s = all_s.get(self.tab_name, {})
        dark = s.get("dark", False)
        fs   = s.get("font", DEFAULT_FONT_SIZE)
        self.slider.blockSignals(True)
        self.slider.setValue(fs)
        self.slider.blockSignals(False)
        self.lbl_v.setText(f"{fs}px")
        self._apply_font(fs)
        if dark:
            self.btn_dark.blockSignals(True)
            self.btn_dark.setChecked(True)
            self.btn_dark.blockSignals(False)
            TabWrapper._global_dark = True
        self._apply_dark(dark)
        # grid_tab이 _apply_extra_settings() 를 구현하면 복원 위임
        # (grid_tab이 아직 완전히 초기화된 후 호출되도록 QTimer 사용)
        if hasattr(self.grid_tab, '_apply_extra_settings') and s:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(300, lambda: self._restore_extra(s))

    def _restore_extra(self, s: dict):
        try:
            self.grid_tab._apply_extra_settings(s)
        except Exception as e:
            print(f"[settings restore] {e}")


# ══════════════════════════════════════════════════════════════
# 10. 저장/불러오기 유틸
# ══════════════════════════════════════════════════════════════
def save_json(filename: str, data: dict):
    path = SAVE_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # router 는 module-level 에서 이미 export 됨

def load_json(filename: str, default=None):
    path = SAVE_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

def append_csv(filename: str, row: dict):
    """CSV에 행 추가 (헤더 없으면 자동 생성)"""
    path = SAVE_DIR / filename
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if write_header: w.writeheader()
        w.writerow(row)

def load_csv(filename: str) -> list:
    path = SAVE_DIR / filename
    if not path.exists(): return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ══════════════════════════════════════════════════════════════
# 11. 장 마감 감지 + MarketDataType 자동 전환
# ══════════════════════════════════════════════════════════════
_ET = ZoneInfo("America/New_York")

# 미국 주식 시장 정규장: 월~금 09:30~16:00 ET
_MARKET_OPEN  = dt_time(9, 30)
_MARKET_CLOSE = dt_time(16, 0)

def is_market_open() -> bool:
    """현재 시각이 미국 정규장(ET 09:30~16:00, 월~금) 안인지 반환."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:          # 토(5) · 일(6)
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE

def auto_mdt(ib) -> int:
    """
    장중        → MarketDataType 1 (LIVE)
    장외/평일   → MarketDataType 3 (DELAYED)
    주말        → MarketDataType 4 (DELAYED-FROZEN) : 마지막 종가 고정 표시
    반환값: 실제 설정된 MarketDataType 번호
    """
    now = datetime.now(_ET)
    if is_market_open():
        mdt = 1   # LIVE
    elif now.weekday() >= 5:
        mdt = 4   # 주말 → Delayed-Frozen (마지막 종가)
    else:
        mdt = 3   # 평일 장외 → Delayed
    try:
        ib.reqMarketDataType(mdt)
    except Exception as e:
        print(f"[auto_mdt] reqMarketDataType({mdt}) 실패: {e}")
    return mdt