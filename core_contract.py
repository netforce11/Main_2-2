"""
core_contract.py — IBapi 래퍼 / 계약 팩토리 (make_opt_contract, make_und_contract)
core.py 300줄 초과로 분리.

[S9] 변경사항:
  - IBapi.historicalDataUpdate() 추가 → keepUpToDate=True 실시간 바 수신
  - bridge.hist_bar_update 시그널로 emit (hist_bar 와 동일 직렬화 방식)
  - IBapi (더미 클래스) 에 cancelHistoricalData 추가
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

            # whatIf=True 주문 결과 — 증거금 수치 emit
            if getattr(order, 'whatIf', False):
                def _f(v):
                    try:
                        f = float(v)
                        return f if f < 1e300 else 0.0  # IB 미정의값(1.79e308) 제거
                    except (ValueError, TypeError):
                        return 0.0
                bridge.whatif_sig.emit(
                    int(orderId),
                    _f(getattr(orderState, 'initMarginBefore',  0)),
                    _f(getattr(orderState, 'initMarginAfter',   0)),
                    _f(getattr(orderState, 'maintMarginBefore', 0)),
                    _f(getattr(orderState, 'maintMarginAfter',  0)),
                    str(getattr(orderState, 'commissionAndFees', '―')),
                )

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
            """과거 바 배치 수신 — dict 직렬화 후 emit (cross-thread 안전)."""
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

        def historicalDataUpdate(self, reqId, bar):
            """
            [S9] 실시간 분봉 업데이트 콜백 — keepUpToDate=True 일 때 호출.
            현재 진행 중인 분봉이 매초/매틱 갱신될 때마다 수신.
            hist_bar_update 시그널로 emit → chart_ibkr._on_bar_update() 처리.
            """
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
                print(f"[historicalDataUpdate] bar 변환 실패: {e}")
                return
            bridge.hist_bar_update.emit(reqId, bar_dict)

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
        def connect(self, *a): pass
        def run(self): pass
        def disconnect(self): pass
        def isConnected(self): return False
        def reqMktData(self, *a): pass
        def cancelMktData(self, *a): pass
        def reqMarketDataType(self, *a): pass
        def reqAccountSummary(self, *a): pass
        def cancelAccountSummary(self, *a): pass
        def reqPositions(self): pass
        def cancelPositions(self): pass
        def reqAllOpenOrders(self): pass
        def reqHistoricalData(self, *a): pass
        def cancelHistoricalData(self, *a): pass   # [S9] 추가
        def placeOrder(self, *a): pass
        def cancelOrder(self, *a): pass
        def get_next_id(self): return None


# ══════════════════════════════════════════════════════════════
# 5. 계약 팩토리 헬퍼
# ══════════════════════════════════════════════════════════════
_TRADING_CLASS = {
    "NDX":  "NDX",
    "NDXP": "NDXP",
    "RUT":  "RUT",
    "VIX":  "VIX",
    "XSP":  "XSP",
}

def _resolve_spx_trading_class(symbol: str, expiry: str, tag: str = "") -> str:
    sym_up = symbol.upper()
    if sym_up == "SPXW":
        return "SPXW"
    if tag == "0DTE":
        try:
            wd = datetime.strptime(expiry, "%Y%m%d").weekday()
            return "SPX" if wd == 2 else "SPXW"
        except Exception:
            pass
    if tag == "W":
        return "SPXW"
    if tag == "M":
        return "SPX"
    try:
        wd = datetime.strptime(expiry, "%Y%m%d").weekday()
        return "SPXW" if wd != 2 else "SPX"
    except Exception:
        return "SPX"


def make_opt_contract(symbol: str, strike: float, right: str,
                      expiry: str, tag: str = "") -> "Contract":
    sym_up = symbol.upper()

    # ── NANOS 전용 분기 (최우선) ─────────────────────────────
    # IBKR NANOS 옵션: symbol="SPX", tradingClass="NANOS", exchange="CBOE", multiplier="1"
    if sym_up == "NANOS":
        _, _, mult, _ = SYMBOL_CFG.get("NANOS", ("OPT", "CBOE", "1", ""))
        c = Contract()
        c.symbol       = "SPX"
        c.tradingClass = "NANOS"
        c.secType      = "OPT"
        c.exchange     = "CBOE"
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = mult if mult else "1"
        c.lastTradeDateOrContractMonth = expiry
        return c

    if sym_up in ("SPX", "SPXW"):
        sec, exch, mult, _ = SYMBOL_CFG.get("SPX", DEFAULT_CFG)
        tc = _resolve_spx_trading_class(sym_up, expiry, tag)
        c = Contract()
        c.symbol       = "SPX"
        c.tradingClass = tc
        c.secType      = sec
        c.exchange     = "CBOE"
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = mult
        c.lastTradeDateOrContractMonth = expiry
        return c

    if sym_up == "NDX":
        sec, exch, mult, _ = SYMBOL_CFG.get("NDX", DEFAULT_CFG)
        try:
            wd = datetime.strptime(expiry, "%Y%m%d").weekday()
            tc = "NDXP" if (tag == "W" or wd != 2) else "NDX"
        except Exception:
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
    tc = _TRADING_CLASS.get(sym_up, sym_up)
    c.tradingClass = tc
    return c


def make_und_contract(symbol: str) -> "Contract":
    sym = symbol.upper().replace("SPXW", "SPX")
    c = Contract()
    c.currency = "USD"

    if sym in INDEX_SYM:
        c.symbol  = sym
        c.secType = "IND"
        _IND_EXCH = {
            "NDX": "NASDAQ",
            "RUT": "RUSSELL",
            "DJX": "CBOE",
            "XSP": "CBOE",
            "VIX": "CBOE",
            "SPX": "CBOE",
        }
        c.exchange = _IND_EXCH.get(sym, "CBOE")
        return c

    c.symbol   = sym
    c.secType  = "STK"
    c.exchange = "SMART"
    return c