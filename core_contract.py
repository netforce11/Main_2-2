"""
core_contract.py — IBapi 래퍼 / 계약 팩토리 (make_opt_contract, make_und_contract)
core.py 300줄 초과로 분리.

[S9] 변경사항:
  - IBapi.historicalDataUpdate() 추가 → keepUpToDate=True 실시간 바 수신
  - bridge.hist_bar_update 시그널로 emit (hist_bar 와 동일 직렬화 방식)
  - IBapi (더미 클래스) 에 cancelHistoricalData 추가

[S10] 변경사항:
  - 순환 import 제거: "from core import ..." 대신 필요한 것만 직접 정의/참조
    core.py → core_contract.py → core.py 순환 구조 해소

[BUG-FIX] avgFillPrice 수정:
  - orderStatus 콜백에서 avgFillPrice 를 bridge 시그널에 포함하도록 수정
  - 기존: emit(oid, status, filled, remaining)         ← avgFillPrice 버림
  - 수정: emit(oid, status, filled, remaining, avgFillPrice)  ← 전달
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

# ── 순환 import 방지: core의 상수/bridge를 직접 참조하지 않고
#    런타임에 core 모듈에서 가져온다 (core가 완전히 로드된 후 접근)
def _get_core():
    import core as _core
    return _core

def _bridge():
    return _get_core().bridge

# SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM, FUT_SYM 은 함수 내부에서
# _get_core() 를 통해 접근 → 모듈 로드 시점 순환 참조 없음


# ══════════════════════════════════════════════════════════════
# 4. IBKR 래퍼
# ══════════════════════════════════════════════════════════════
if IBAPI_AVAILABLE:
    class IBapi(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self._next_id       = None
            self._next_id_ready = False   # [BUG-FIX] 재연결 OID 동기화 완료 플래그

        def nextValidId(self, orderId):
            self._next_id       = orderId
            self._next_id_ready = True    # [BUG-FIX] OID 동기화 완료
            _bridge().connected.emit()
            try:
                self.reqAccountSummary(9901, "All", "AvailableFunds,BuyingPower")
            except Exception as e:
                print(f"[core] reqAccountSummary 구독 실패: {e}")

        def connectionClosed(self):
            """[BUG-FIX] 연결 끊김 시 OID 플래그 리셋 — 재연결 전 주문 차단."""
            self._next_id_ready = False
            print("[core] TWS 연결 끊김 — nextValidId 대기 중")

        def tickPrice(self, reqId, tickType, price, attrib):
            _bridge().tick_price.emit(reqId, int(tickType), float(price))

        def tickOptionComputation(self, reqId, tickType, tickAttrib,
                                  impliedVol, delta, optPrice, pvDividend,
                                  gamma, vega, theta, undPrice):
            def f(v): return float(v) if v is not None else 0.0
            _bridge().tick_option.emit(reqId, int(tickType),
                f(impliedVol), f(delta), f(optPrice), f(gamma), f(vega), f(theta))

        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
            _bridge().error_sig.emit(reqId, int(errorCode), str(errorString))

        def accountSummary(self, reqId, account, tag, value, currency):
            _bridge().acct_value.emit(str(tag), str(value), str(currency), str(account))

        def accountSummaryEnd(self, reqId):
            _bridge().acct_end.emit()

        def position(self, account, contract, position, avgCost):
            _bridge().position_sig.emit(
                str(account), str(contract.symbol),
                str(getattr(contract, 'right', '')),
                float(position), float(avgCost))

        def positionEnd(self):
            _bridge().position_end.emit()

        def openOrder(self, orderId, contract, order, orderState):
            _bridge().open_order_sig.emit(
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
                        return f if f < 1e300 else 0.0
                    except (ValueError, TypeError):
                        return 0.0
                _bridge().whatif_sig.emit(
                    int(orderId),
                    _f(getattr(orderState, 'initMarginBefore',  0)),
                    _f(getattr(orderState, 'initMarginAfter',   0)),
                    _f(getattr(orderState, 'maintMarginBefore', 0)),
                    _f(getattr(orderState, 'maintMarginAfter',  0)),
                    str(getattr(orderState, 'commissionAndFees', '―')),
                )

        # ── [BUG-FIX] avgFillPrice 추가 ────────────────────────────
        # 기존: emit(oid, status, filled, remaining)  → avgFillPrice 버림
        # 수정: emit(oid, status, filled, remaining, avgFillPrice) → 전달
        # core.py의 order_status_sig 시그니처도 float 1개 추가 필요:
        #   order_status_sig = pyqtSignal(int, str, float, float, float)
        def orderStatus(self, orderId, status, filled, remaining,
                        avgFillPrice, permId, parentId, lastFillPrice,
                        clientId, whyHeld, mktCapPrice):
            # avgFillPrice: IB가 주는 BAG 전체 net 체결가 (0.39 등)
            # 미체결/접수 상태에서는 0.0 으로 옴 → 그대로 전달
            _bridge().order_status_sig.emit(
                int(orderId), str(status),
                float(filled), float(remaining),
                float(avgFillPrice))   # ★ 추가

        def execDetails(self, reqId, contract, execution):
            _bridge().exec_sig.emit(
                int(execution.orderId),
                str(contract.symbol),
                str(execution.side),
                float(execution.shares),
                float(execution.price))
            # ── 체결 마커용 시그널 (chart_exec_marker.py 수신) ──
            import time as _time
            _action = "BUY" if str(execution.side).upper() == "BOT" else "SELL"
            _bridge().exec_filled.emit(
                int(_time.time() * 1000),
                _action,
                float(execution.price))

        def contractDetails(self, reqId, contractDetails):
            from types import SimpleNamespace
            try:
                c = contractDetails.contract
                cd = SimpleNamespace(
                    conId   = int(getattr(c, 'conId',   0)),
                    symbol  = str(getattr(c, 'symbol',  '')),
                    right   = str(getattr(c, 'right',   '')),
                    strike  = float(getattr(c, 'strike', 0.0)),
                    expiry  = str(getattr(c, 'lastTradeDateOrContractMonth', '')),
                    secType = str(getattr(c, 'secType', '')),
                )
                cd.contract = cd
            except Exception as e:
                print(f"[contractDetails] serialization error: {e}")
                return
            _bridge().contract_details_sig.emit(reqId, cd)

        def contractDetailsEnd(self, reqId):
            _bridge().contract_details_end_sig.emit(reqId)

        def historicalData(self, reqId, bar):
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
            _bridge().hist_bar.emit(reqId, bar_dict)

        def historicalDataUpdate(self, reqId, bar):
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
            _bridge().hist_bar_update.emit(reqId, bar_dict)

        def historicalDataEnd(self, reqId, start, end):
            _bridge().hist_end.emit(reqId)

        def historicalTicks(self, reqId, ticks, done):
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
            _bridge().hist_ticks.emit(reqId, tick_list, bool(done))

        def historicalTicksBidAsk(self, reqId, ticks, done):
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
            _bridge().hist_ticks.emit(reqId, tick_list, bool(done))

        def get_next_id(self):
            # [BUG-FIX] 재연결 후 nextValidId 수신 전 주문 차단
            # 두 번 끊김 등 불안정한 재연결 시 이전/중복 OID로 placeOrder 되면
            # TWS가 조용히 드랍 (에러 콜백 없음) — 플래그로 방어
            if not getattr(self, '_next_id_ready', False):
                print("[core] ⚠ get_next_id: nextValidId 미수신 — 주문 차단")
                return None
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
        def cancelHistoricalData(self, *a): pass
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
    """
    SPX/SPXW 옵션 계약의 tradingClass 결정.

    IBKR 규칙:
      ┌─────────────────────────────────────────────────────────────┐
      │ SPX Monthly (AM-settled, tradingClass="SPX")                │
      │   - 매월 세 번째 금요일이 공식 만기일                          │
      │   - 마지막 거래일 = 만기 전날(목요일)                          │
      │   - 만기 당일(금요일)은 거래 없음 → IBKR 시세 미제공           │
      │                                                             │
      │ SPXW Weekly (PM-settled, tradingClass="SPXW")               │
      │   - 매일 만기 존재 (세 번째 금요일 포함)                       │
      │   - 만기 당일 장마감(4PM ET)까지 거래 가능                     │
      │   - 세 번째 금요일 당일에도 SPXW로 시세 조회 가능              │
      └─────────────────────────────────────────────────────────────┘

    따라서:
      - expiry가 세 번째 금요일이고 오늘이 그 날이면 → "SPXW"
        (AM-settled SPX Monthly는 이미 마감, SPXW만 살아있음)
      - expiry가 세 번째 금요일이고 오늘이 그 전날(목요일)이면 → "SPX"
        (SPX Monthly 마지막 거래일 → SPX로 조회)
      - 그 외 날짜 → "SPXW"
    """
    sym_up = symbol.upper()

    # tag 명시 우선 (하위 호환)
    if tag == "W":
        return "SPXW"
    if tag in ("M", "MONTHLY"):
        # MONTHLY 태그라도 만기 당일이면 SPXW로 전환
        pass   # 아래 날짜 로직에서 처리

    try:
        dt = datetime.strptime(expiry, "%Y%m%d")
        if dt.weekday() != 4:
            # 금요일이 아닌 날짜 → 무조건 SPXW (평일 만기 주간물)
            return "SPXW"

        from datetime import date as _date
        first_day    = _date(dt.year, dt.month, 1)
        days_to_fri  = (4 - first_day.weekday()) % 7
        third_friday = first_day.day + days_to_fri + 14

        if dt.day != third_friday:
            # 세 번째 금요일이 아닌 일반 금요일 → SPXW
            return "SPXW"

        # ── 세 번째 금요일 ────────────────────────────────────────
        # 오늘 날짜와 비교해서 tradingClass 결정
        from call_put_tab.core_conn_spxw import _today_et
        today = _today_et()
        expiry_date = _date(dt.year, dt.month, dt.day)

        if today >= expiry_date:
            # 만기 당일 또는 이후 → SPX Monthly 이미 마감
            # SPXW PM-settled로 조회 (당일 4PM까지 거래 가능)
            return "SPXW"
        else:
            # 만기 전날(목요일) 포함 그 이전 → SPX Monthly 조회 가능
            return "SPX"

    except Exception:
        return "SPXW"


def make_opt_contract(symbol: str, strike: float, right: str,
                      expiry: str, tag: str = "") -> "Contract":
    sym_up = symbol.upper()
    _core = _get_core()
    SYMBOL_CFG  = _core.SYMBOL_CFG
    DEFAULT_CFG = _core.DEFAULT_CFG

    if sym_up == "CL":
        c = Contract()
        c.symbol       = "CL"
        c.secType      = "FOP"
        c.exchange     = "NYMEX"
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = "1000"
        c.lastTradeDateOrContractMonth = expiry
        c.tradingClass = "LO"
        return c

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

    if sym_up == "VIX":
        sec, _, mult, _ = SYMBOL_CFG.get("VIX", DEFAULT_CFG)
        c = Contract()
        c.symbol       = "VIX"
        c.secType      = sec
        c.exchange     = "CBOE"
        c.currency     = "USD"
        c.strike       = float(strike)
        c.right        = "C" if right.upper() in ("C", "CALL") else "P"
        c.multiplier   = mult
        c.tradingClass = "VIX"
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
    _core = _get_core()

    FUT_SYM   = _core.FUT_SYM
    INDEX_SYM = _core.INDEX_SYM
    if sym in FUT_SYM:
        c.symbol   = sym
        c.secType  = "FUT"
        c.exchange = "NYMEX"
        return c

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