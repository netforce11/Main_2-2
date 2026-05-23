"""
sleep_order_mixin.py — SleepOrder 연동 메서드  v2.1
════════════════════════════════════════════════════════
v2.1 변경:
  · _sleep_get_chain(): XSP 틱 사이즈 적용 (_opt_tick 사용)
  · _sleep_get_chain(): 이상 프리미엄 감지 로직 추가
      - net 부호 역전 / 레그 가격 0 / 이론 최대 초과 시 skip + 로그
  · 기존 v2.0 구조 유지 (단일 옵션 메서드 등)
════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Optional

_REQ_SLEEP_BASE = 8600
_REQ_SLEEP_MAX  = 100


def _opt_tick(net: float, symbol: str = "") -> float:
    """심볼·가격 기반 옵션 틱 크기. XSP: 0.01 / SPX: 0.05 or 0.10"""
    if symbol.upper() in {"XSP", "XSPC", "XSPP"}:
        return 0.01
    return 0.10 if net >= 3.00 else 0.05


def _check_premium_anomaly(net: float, up_p: float, lo_p: float,
                            spread_width: float, symbol: str,
                            log_fn=None) -> bool:
    """이상 프리미엄 감지. 이상 있으면 True 반환.
    감지 조건:
      ① net <= 0 (부호 역전 — 크레딧 구조)
      ② 레그 가격 0 이하
      ③ net > spread_width * 100 * 0.9 (이론 최대 90% 초과)
    """
    tag = f"[{symbol}]" if symbol else ""
    if up_p <= 0 or lo_p <= 0:
        if log_fn:
            log_fn(f"⚠ 이상프리미엄{tag} 레그가격 0: up={up_p} lo={lo_p}")
        return True
    if net <= 0:
        if log_fn:
            log_fn(f"⚠ 이상프리미엄{tag} net 역전: {net:.2f}")
        return True
    max_theoretical = spread_width * 0.9
    if net > max_theoretical:
        if log_fn:
            log_fn(f"⚠ 이상프리미엄{tag} 이론최대 초과: "
                   f"net={net:.2f} > 한도={max_theoretical:.2f}")
        return True
    return False


from Sleep_Order.sleep_order_mixin_orders import SleepOrderOrdersMixin


class SleepOrderMixin(SleepOrderOrdersMixin):

    # ── 0. 실시간 구독 관리 ─────────────────────────────────────

    def _sleep_subscribe_chain(self) -> None:
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None or not getattr(getattr(self, 'mw', None),
                                     'connected', False):
            self._log("[SleepOrder] ⚠ 구독 실패: TWS 미연결"); return
        put_strikes: list = getattr(self, '_put_strikes', [])
        expiry: str       = getattr(self, '_current_expiry', '') or ''
        sym_w             = getattr(self, 'edit_sym_combo', None)
        symbol            = sym_w.text().strip().upper() if sym_w else "SPX"
        symbol            = symbol.replace("SPXW", "SPX")
        if not put_strikes or not expiry:
            self._log("[SleepOrder] ⚠ 구독 실패: 행사가/만기 없음"); return
        self._sleep_unsubscribe_chain()
        self._sleep_live_prices: dict = {}
        self._sleep_req_map: dict     = {}
        try:
            from core_contract import make_opt_contract
            from core import router
        except ImportError as e:
            self._log(f"[SleepOrder] ⚠ import 실패 — 캐시 폴백: {e}"); return
        subscribed = 0
        for i, strike in enumerate(put_strikes[:_REQ_SLEEP_MAX]):
            req_id = _REQ_SLEEP_BASE + i
            try:
                contract = make_opt_contract(symbol, strike, "P", expiry)
                ib.reqMktData(req_id, contract, "", False, False, [])
                self._sleep_req_map[req_id] = strike
                router.register_price(
                    req_id, req_id,
                    lambda rid, tt, px, _s=strike:
                        self._sleep_on_tick(rid, tt, px, _s))
                subscribed += 1
            except Exception as e:
                self._log(f"[SleepOrder] ⚠ reqMktData 실패 strike={strike}: {e}")
        self._log(f"[SleepOrder] 📡 실시간 구독: {subscribed}개  "
                  f"reqId {_REQ_SLEEP_BASE}~{_REQ_SLEEP_BASE+subscribed-1}")

    def _sleep_unsubscribe_chain(self) -> None:
        ib      = getattr(getattr(self, 'mw', None), 'ib', None)
        req_map = getattr(self, '_sleep_req_map', {})
        if not req_map: return
        try:
            from core import router
        except ImportError:
            router = None
        for req_id in list(req_map.keys()):
            try:
                if ib: ib.cancelMktData(req_id)
            except Exception: pass
            try:
                if router: router.unregister_price(req_id)
            except Exception: pass
        count = len(req_map)
        self._sleep_req_map = {}; self._sleep_live_prices = {}
        self._log(f"[SleepOrder] 🔌 구독 해제: {count}개")

    def _sleep_on_tick(self, req_id: int, tick_type: int,
                       price: float, strike: float) -> None:
        if price <= 0: return
        if not hasattr(self, '_sleep_tick_buf'):
            self._sleep_tick_buf: dict = {}
        buf = self._sleep_tick_buf.setdefault(strike, {})
        if tick_type == 1:   buf["bid"]  = price
        elif tick_type == 2: buf["ask"]  = price
        elif tick_type == 4: buf.setdefault("last", price)
        bid = buf.get("bid"); ask = buf.get("ask")
        if not hasattr(self, '_sleep_live_prices'):
            self._sleep_live_prices = {}
        if bid and ask and bid > 0 and ask > 0:
            self._sleep_live_prices[strike] = round((bid + ask) / 2, 2)
        elif "last" in buf and strike not in self._sleep_live_prices:
            self._sleep_live_prices[strike] = buf["last"]

    # ── 1. 지수 현재가 ──────────────────────────────────────────

    def _sleep_get_underlying_price(self) -> float:
        price = float(getattr(self, '_und_price', 0.0) or 0.0)
        if price > 0: return price
        try:
            cp = getattr(getattr(self, 'mw', None), 'tab_callput', None)
            if cp: price = float(getattr(cp, 'und_price', 0) or 0)
        except Exception: pass
        return float(price)

    # ── 2. 체인 스캔 ────────────────────────────────────────────

    def _sleep_get_chain(self, expiry_offset: int) -> list:
        """풋 스프레드 체인 조립.
        [v2.1] XSP 틱 사이즈 적용 / 이상 프리미엄 감지 추가.
        """
        from Sleep_Order.sleep_order_config import sleep_cfg
        put_strikes = getattr(self, '_put_strikes', [])
        chain_put   = getattr(self, '_chain_put', {})
        live_prices = getattr(self, '_sleep_live_prices', {})
        expiry      = getattr(self, '_current_expiry', '') or ''
        if not put_strikes or not expiry: return []

        target_expiry = _offset_expiry(expiry, expiry_offset) or expiry
        step  = _detect_strike_step(put_strikes)
        # [XSP-FIX] XSP는 1pt 간격, SPX는 sleep_cfg.spread_width 사용
        width = 1 if symbol.upper() in {"XSP","XSPC","XSPP"}                   else sleep_cfg.spread_width
        n_step       = max(1, round(width / step)) if step > 0 else 1
        actual_width = n_step * step

        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX"
                  ).replace("SPXW", "SPX")
        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            def _cid(s):
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "P", s, target_expiry), 0))
        except ImportError:
            _cid = lambda s: 0

        def _price(s):
            p = live_prices.get(s)
            return p if p and p > 0 else chain_put.get(s)

        strike_set = set(put_strikes)
        results = []
        log_fn  = getattr(self, '_log', None)

        for upper in put_strikes:
            lower = upper - actual_width
            if lower not in strike_set:
                cands = [s for s in put_strikes if s < upper]
                if not cands: continue
                lower  = max(cands)
                real_w = upper - lower
                if real_w < step or real_w > actual_width * 1.5: continue

            up_p = _price(upper); lo_p = _price(lower)
            if up_p is None or lo_p is None: continue

            net = round(up_p - lo_p, 2)

            # [v2.1] 이상 프리미엄 감지 → skip
            if _check_premium_anomaly(net, up_p, lo_p,
                                      actual_width, symbol, log_fn):
                continue

            # [v2.1] XSP 틱 사이즈 적용
            tick = _opt_tick(net, symbol)
            results.append({
                "strike":  upper,
                "put_net": net,
                "put_ask": round(net + tick, 2),
                "legs": [
                    {"cp": "P", "strike": upper, "expiry": target_expiry,
                     "dir": "BUY",  "qty": 1, "prem": up_p,
                     "con_id": _cid(upper)},
                    {"cp": "P", "strike": lower, "expiry": target_expiry,
                     "dir": "SELL", "qty": 1, "prem": lo_p,
                     "con_id": _cid(lower)},
                ],
            })
        return results

    # ── 3. Debit Spread BAG 주문 ────────────────────────────────

    def _sleep_place_order(self, legs: list, lmt_price: float,
                           qty: int, strat: str,
                           tag: str = "") -> Optional[int]:
        try:
            from ibapi.contract import Contract, ComboLeg
            from ibapi.order   import Order as IbOrder
            from combo_order_callbacks import connect_order_callbacks
        except ImportError as e:
            self._log(f"[SleepOrder] ❌ import 실패: {e}"); return None
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None:
            self._log("[SleepOrder] ❌ IB 미연결"); return None
        connect_order_callbacks(self)
        oid = ib.get_next_id()
        if oid is None:
            self._log("[SleepOrder] ❌ OID 발급 실패"); return None
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX"
                  ).replace("SPXW", "SPX")
        from combo_order_bag import _get_selected_exchange as _gse
        _exch = _gse(self)
        bag = Contract()
        bag.symbol = symbol; bag.secType = "BAG"
        bag.currency = "USD"; bag.exchange = _exch
        combo_legs = []
        for leg in legs:
            con_id = int(leg.get("con_id") or 0)
            if con_id == 0:
                try:
                    from combo_order_bag import _CONID_CACHE, _conid_key
                    con_id = int(_CONID_CACHE.get(
                        _conid_key(bag.symbol,
                                   str(leg.get("cp", "P")),
                                   float(leg.get("strike", 0)),
                                   str(leg.get("expiry", ""))), 0))
                except Exception: pass
            if con_id == 0:
                self._log(f"[SleepOrder] ❌ conId 없음: "
                          f"{leg.get('cp')} {leg.get('strike')}")
                return None
            cl = ComboLeg()
            cl.conId = con_id; cl.ratio = int(leg.get("qty", 1))
            cl.action = leg["dir"]; cl.exchange = _exch
            combo_legs.append(cl)
        bag.comboLegs = combo_legs
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception as _e:
            tif = "DAY"; outside_rth = True
        ibord = IbOrder()
        ibord.action = "BUY"; ibord.orderType = "LMT"
        ibord.totalQuantity = qty; ibord.lmtPrice = lmt_price
        ibord.tif = tif; ibord.outsideRth = outside_rth
        ibord.eTradeOnly = False; ibord.firmQuoteOnly = False
        ibord.transmit = True
        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(f"[SleepOrder] ✅ BAG 주문 OID={oid} "
                      f"${lmt_price:.2f}×{qty} [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ placeOrder 실패: {e}"); return None
        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)
        self._chaser_bag_contract = bag
        self._chaser_current_oid  = oid
        self._chaser_oid          = oid
        if tag in ("SLEEP_ORDER_PUT", "SLEEP_ORDER_CALL"):
            if tag == "SLEEP_ORDER_PUT":
                self._pending_position = {
                    "strategy": strat, "qty": qty, "entry": lmt_price,
                    "current": lmt_price, "side": "BUY",
                    "oid": oid, "legs": legs,
                    "status": "미체결", "tag": tag,
                }
        else:
            self._pending_position = {
                "strategy": strat, "qty": qty, "entry": lmt_price,
                "current": lmt_price, "side": "BUY",
                "oid": oid, "legs": legs, "status": "미체결",
            }
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().watch(
                self, oid, lmt_price, "BUY", legs, strat,
                bag_contract=bag, qty=qty)
        except Exception as e:
            self._log(f"[SleepOrder] ⚠ SpecialFillWatcher 등록 실패: {e}")
        return oid


# ── 정정·매도·단일옵션 메서드는 SleepOrderOrdersMixin 에서 상속 ──


# ── 유틸 (클래스 바깥) ───────────────────────────────────────────

_XSP_SYMBOLS = {"XSP", "XSPC", "XSPP"}

# 심볼별 기본 스프레드 간격 (사용자 spread_width 미설정 시 자동 적용)
_DEFAULT_WIDTH = {
    "SPX":5,"SPXW":5,"NDX":25,"RUT":5,"RUTW":5,
    "VIX":1,"VIXW":1,
    "XSP":1,"XSPC":1,"XSPP":1,
    "AAPL":2,"MSFT":5,"NVDA":5,"AMZN":5,
    "GOOGL":5,"META":5,"TSLA":5,"AMD":5,
    "SPY":1,"QQQ":1,"IWM":1,
}


def _effective_spread_width(sleep_cfg, symbol: str) -> float:
    """심볼별 스프레드 간격 자동 결정. 사용자 기본값(5)이면 테이블 자동 적용."""
    user_w = int(getattr(sleep_cfg, 'spread_width', 5))
    sym    = symbol.upper()
    auto_w = _DEFAULT_WIDTH.get(sym)
    if auto_w is not None and user_w == 5 and sym not in {"SPX","SPXW"}:
        return float(auto_w)
    return float(user_w)


def _detect_strike_step(strikes: list) -> float:
    if len(strikes) < 2: return 5.0
    diffs = [abs(strikes[i] - strikes[i-1])
             for i in range(1, min(5, len(strikes)))
             if abs(strikes[i] - strikes[i-1]) > 0]
    return min(diffs) if diffs else 5.0


def _offset_expiry(expiry8: str, offset: int) -> str:
    if not expiry8 or len(expiry8) != 8: return expiry8
    if offset == 0: return expiry8
    try:
        from datetime import datetime, timedelta
        dt = datetime.strptime(expiry8, "%Y%m%d")
        added = 0
        while added < offset:
            dt += timedelta(days=1)
            if dt.weekday() < 5: added += 1
        return dt.strftime("%Y%m%d")
    except Exception:
        return expiry8
