"""
chart_condition_monitor.py — 조건 모니터 (_Monitor 클래스)
────────────────────────────────────────────────────────
· IBKR 옵션 구독 / 틱 수신
· 시간·틱속도·현재가 조건 검사
· 조건 충족 시 자동 주문 실행
"""
import time
from datetime import date, datetime, timezone, timedelta

try:
    from ibapi.contract import Contract
    from ibapi.order    import Order as IBOrder
    IBAPI_OK = True
except ImportError:
    IBAPI_OK = False

from core import router

REQ_COND_OPT_BASE = 8100
COOLDOWN_S        = 30
TICK_STEP         = 0.05


# ── ET 시각 헬퍼 ─────────────────────────────────────────────

def _et_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except ImportError:
        offset = -4 if time.daylight and time.localtime().tm_isdst else -5
        return datetime.now(timezone(timedelta(hours=offset)))


def _et_now_str() -> str:
    return _et_now().strftime("%H:%M")


def _kst_str_to_et_str(kst_str: str) -> str:
    """
    'HH:MM' KST → 'HH:MM' ET 변환.
    [수정] zoneinfo 기반으로 DST 자동 처리 (기존: 한국 서버 DST 기준 오류)
    """
    try:
        h, m = map(int, kst_str.strip().split(":"))
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime as _dt
            ny_offset = int(
                _dt.now(ZoneInfo("America/New_York"))
                .utcoffset().total_seconds() / 3600
            )
        except ImportError:
            ny_offset = -4 if time.daylight and time.localtime().tm_isdst else -5
        kst_offset = 9
        total_min  = h * 60 + m - (kst_offset - ny_offset) * 60
        total_min  = total_min % (24 * 60)
        eh = total_min // 60; em = total_min % 60
        return f"{eh:02d}:{em:02d}"
    except Exception:
        return kst_str


# ══════════════════════════════════════════════════════════════
# 조건 모니터
# ══════════════════════════════════════════════════════════════

class Monitor:
    def __init__(self, mw):
        self.mw          = mw
        self.running     = False
        self._req_id     = REQ_COND_OPT_BASE
        self._price      = {"bid": 0.0, "ask": 0.0, "last": 0.0}
        self._trigger_ts = 0.0
        self._order_sent = False

        try:
            from chart_tick_speed import _tick_times
            self._tick_q = _tick_times
        except Exception:
            self._tick_q = None

        router.register_price(
            REQ_COND_OPT_BASE, REQ_COND_OPT_BASE + 9,
            self._on_tick)

    # ── 구독 ─────────────────────────────────────────────────
    def subscribe(self, strike_str: str):
        if not IBAPI_OK: return
        ibkr = self._ibkr()
        if ibkr is None: return
        try:
            c = self._make_contract(strike_str)
            if c:
                ibkr.reqMktData(self._req_id, c, "", False, False, [])
        except Exception as e:
            print(f"[CondOrder] subscribe err: {e}")

    def unsubscribe(self):
        if not IBAPI_OK: return
        ibkr = self._ibkr()
        if ibkr is None: return
        try:
            ibkr.cancelMktData(self._req_id)
        except Exception:
            pass

    def _make_contract(self, strike_str: str):
        if not strike_str or len(strike_str) < 2:
            return None
        try:
            right  = "C" if strike_str[-1].upper() == "C" else "P"
            strike = float(strike_str[:-1])
            c = Contract()
            c.symbol       = "SPXW"
            c.secType      = "OPT"
            c.exchange     = "SMART"
            c.currency     = "USD"
            c.right        = right
            c.strike       = strike
            c.multiplier   = "100"
            c.tradingClass = "SPXW"
            c.lastTradeDateOrContractMonth = date.today().strftime("%Y%m%d")
            return c
        except Exception as e:
            print(f"[CondOrder] contract err: {e}")
            return None

    def _on_tick(self, rid, tick_type, price):
        if rid != self._req_id: return
        if   tick_type == 1: self._price["bid"]  = price
        elif tick_type == 2: self._price["ask"]  = price
        elif tick_type == 4: self._price["last"] = price

    # ── 조건 검사 ─────────────────────────────────────────────
    def check(self, cfg: dict) -> tuple:
        """반환: (triggered: bool, tick_10s: int, reason: str)"""
        if not self.running:
            return False, 0, ""

        et_now = _et_now_str()
        et_s   = _kst_str_to_et_str(cfg["time_start"])
        et_e   = _kst_str_to_et_str(cfg["time_end"])
        if not (et_s <= et_now <= et_e):
            return False, 0, f"시간 외 ({et_now} ET)"

        tick_10s = self.tick_10s()
        if tick_10s <= cfg["tick_thresh"]:
            return False, tick_10s, f"틱 {tick_10s} ≤ {cfg['tick_thresh']}"

        if cfg["price_enabled"]:
            last = self._price["last"]
            op   = cfg["price_op"]
            pv1  = cfg["price_val1"]
            pv2  = cfg["price_val2"]
            if op == "이상" and not (last >= pv1):
                return False, tick_10s, f"현재가 {last:.2f} < {pv1:.2f}"
            elif op == "이하" and not (last <= pv1):
                return False, tick_10s, f"현재가 {last:.2f} > {pv1:.2f}"
            elif op == "범위" and not (pv1 <= last <= pv2):
                return False, tick_10s, f"현재가 {last:.2f} 범위외"

        elapsed = time.time() - self._trigger_ts
        if elapsed < COOLDOWN_S:
            return False, tick_10s, f"쿨다운 {int(COOLDOWN_S - elapsed)}s"

        self._trigger_ts = time.time()
        return True, tick_10s, "OK"

    # ── 주문 ─────────────────────────────────────────────────
    def place_order(self, cfg: dict) -> str:
        ibkr = self._ibkr()
        if ibkr is None or not IBAPI_OK:
            return "IBKR 미연결"
        try:
            c = self._make_contract(cfg["strike"])
            if c is None: return "컨트랙트 오류"

            o = IBOrder()
            o.action        = cfg["order_side"]
            o.totalQuantity = cfg["order_qty"]

            if cfg["limit_enabled"]:
                o.orderType = "LMT"
                o.lmtPrice  = cfg["limit_price"]
            else:
                last = self._price["last"]
                lmt  = last + TICK_STEP if cfg["order_side"] == "BUY" else last - TICK_STEP
                o.orderType = "LMT"
                o.lmtPrice  = round(lmt * 20) / 20

            # [수정] ms 단위 타임스탬프로 주문ID 충돌 방지
            oid = int(time.time() * 1000) % 2_000_000_000
            ibkr.placeOrder(oid, c, o)
            self._order_sent = True
            return (f"주문 #{oid}  {o.action} {o.totalQuantity}계약"
                    f" @ LMT {o.lmtPrice:.2f}")
        except Exception as e:
            return f"주문 오류: {e}"

    def get_price(self) -> dict:
        return dict(self._price)

    def tick_10s(self) -> int:
        if self._tick_q is None: return 0
        cutoff = time.time() - 10
        return sum(1 for t in self._tick_q if t >= cutoff)

    def _ibkr(self):
        try: return self.mw.api
        except AttributeError: return None

    # ── ET 범위 문자열 반환 (UI 표시용) ─────────────────────
    def et_range_str(self, cfg: dict) -> str:
        et_s = _kst_str_to_et_str(cfg["time_start"])
        et_e = _kst_str_to_et_str(cfg["time_end"])
        return f"ET: {et_s} ~ {et_e}"
