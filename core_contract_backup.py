"""
core_contract.py — IBapi 래퍼 / 계약 팩토리 (make_opt_contract, make_und_contract)
core.py 300줄 초과로 분리.
"""
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IBAPI_AVAILABLE = True
except ModuleNotFoundError:
    IBAPI_AVAILABLE = False

from PyQt5.QtCore import pyqtSignal, QObject
from datetime import datetime

from core import (
    SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM,
    bridge, SignalBridge,
)

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
            # bar 객체를 백그라운드에서 dict로 변환 후 emit.
            # pyqtSignal(int, object)로 IBKR bar를 직접 전달하면
            # Qt cross-thread 복사 시 메모리 접근 위반(0xC0000005) 발생.
            try:
                bar_dict = {
                    "date":   bar.date,
                    "open":   float(bar.open),
                    "high":   float(bar.high),
                    "low":    float(bar.low),
                    "close":  float(bar.close),
                    "volume": float(bar.volume),
                }
            except Exception as e:
                print(f"[historicalData] bar 변환 실패: {e}")
                return
            bridge.hist_bar.emit(reqId, bar_dict)

        def historicalDataEnd(self, reqId, start, end):
            bridge.hist_end.emit(reqId)

        def historicalTicks(self, reqId, ticks, done):
            """TRADES 틱 콜백 — STK/ETF용."""
            tick_list = []
            for t in ticks:
                try:
                    tick_list.append({
                        "t": float(t.time),
                        "p": float(t.price),
                        "s": int(t.size),
                    })
                except Exception:
                    pass
            bridge.hist_ticks.emit(reqId, tick_list, bool(done))

        def historicalTicksBidAsk(self, reqId, ticks, done):
            """BID_ASK 틱 콜백 — IND(지수)용. mid price로 변환."""
            tick_list = []
            for t in ticks:
                try:
                    mid = (float(t.priceBid) + float(t.priceAsk)) / 2.0
                    tick_list.append({
                        "t": float(t.time),
                        "p": mid,
                        "s": int(t.sizeBid) + int(t.sizeAsk),
                    })
                except Exception:
                    pass
            bridge.hist_ticks.emit(reqId, tick_list, bool(done))

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
    """
    기초자산 Contract 생성.
    - 지수 (IND) : SPX/SPXW→SPX@CBOE, NDX@NASDAQ, RUT@RUSSELL,
                   VIX/DJX/XSP→CBOE
    - 주식/ETF (STK) : SMART
    SPXW는 내부적으로 항상 SPX로 정규화.
    """
    sym = symbol.upper().replace("SPXW", "SPX")
    c = Contract()
    c.currency = "USD"

    # ── 지수 ──────────────────────────────────────────────────
    if sym in INDEX_SYM:
        c.symbol  = sym
        c.secType = "IND"
        _IND_EXCH = {
            "NDX": "NASDAQ",   # Nasdaq-100
            "RUT": "RUSSELL",  # Russell 2000
            "DJX": "CBOE",
            "XSP": "CBOE",
            "VIX": "CBOE",
            "SPX": "CBOE",
        }
        c.exchange = _IND_EXCH.get(sym, "CBOE")
        return c

    # ── 주식/ETF ──────────────────────────────────────────────
    c.symbol   = sym
    c.secType  = "STK"
    c.exchange = "SMART"
    return c



