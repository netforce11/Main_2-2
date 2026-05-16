"""
sleep_order_mixin.py — SleepOrder 연동 메서드  v2.0
════════════════════════════════════════════════════════
LeftPanelMixin 에 상속 추가.
v2.0 변경:
  · 단일 옵션 급락 캐치용 콜백 3개 추가
    - _sleep_place_single_order()
    - _sleep_modify_single_order()
    - _sleep_place_single_sell_order()
  · 기존 구조 버그 수정
    - _sleep_place_sell_order docstring 오염 제거
    - _sleep_modify_order 클래스 내부로 복귀
    - 하단 독립 함수 3개 → 클래스 메서드로 이동
════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Optional

_REQ_SLEEP_BASE = 8600
_REQ_SLEEP_MAX  = 100


class SleepOrderMixin:

    # ── 0. 실시간 구독 관리 ─────────────────────────────────────

    def _sleep_subscribe_chain(self) -> None:
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None or not getattr(getattr(self, 'mw', None), 'connected', False):
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
                    lambda rid, tt, px, _s=strike: self._sleep_on_tick(rid, tt, px, _s))
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
        self._sleep_req_map     = {}
        self._sleep_live_prices = {}
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
        from Sleep_Order.sleep_order_config import sleep_cfg
        put_strikes = getattr(self, '_put_strikes', [])
        chain_put   = getattr(self, '_chain_put', {})
        live_prices = getattr(self, '_sleep_live_prices', {})
        expiry      = getattr(self, '_current_expiry', '') or ''
        if not put_strikes or not expiry: return []
        target_expiry = _offset_expiry(expiry, expiry_offset) or expiry
        step  = _detect_strike_step(put_strikes)
        width = sleep_cfg.spread_width
        n_step       = max(1, round(width / step)) if step > 0 else 1
        actual_width = n_step * step
        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            sym_w  = getattr(self, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
            def _cid(s): return int(_CONID_CACHE.get(_conid_key(symbol,"P",s,target_expiry), 0))
        except ImportError:
            symbol = "SPX"; _cid = lambda s: 0

        def _price(s):
            p = live_prices.get(s)
            return p if p and p > 0 else chain_put.get(s)

        strike_set = set(put_strikes)
        results = []
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
            if net <= 0: continue
            tick = 0.10 if net >= 3.0 else 0.05
            results.append({
                "strike":  upper, "put_net": net, "put_ask": round(net + tick, 2),
                "legs": [
                    {"cp":"P","strike":upper,"expiry":target_expiry,
                     "dir":"BUY", "qty":1,"prem":up_p,"con_id":_cid(upper)},
                    {"cp":"P","strike":lower,"expiry":target_expiry,
                     "dir":"SELL","qty":1,"prem":lo_p,"con_id":_cid(lower)},
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
        if ib is None: self._log("[SleepOrder] ❌ IB 미연결"); return None
        connect_order_callbacks(self)
        oid = ib.get_next_id()
        if oid is None: self._log("[SleepOrder] ❌ OID 발급 실패"); return None
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW","SPX")
        bag = Contract()
        bag.symbol = symbol; bag.secType = "BAG"
        bag.currency = "USD"; bag.exchange = "SMART"
        combo_legs = []
        for leg in legs:
            con_id = int(leg.get("con_id") or 0)
            if con_id == 0:
                try:
                    from combo_order_bag import _CONID_CACHE, _conid_key
                    con_id = int(_CONID_CACHE.get(
                        _conid_key(bag.symbol, str(leg.get("cp","P")),
                                   float(leg.get("strike",0)), str(leg.get("expiry",""))), 0))
                except Exception: pass
            if con_id == 0:
                self._log(f"[SleepOrder] ❌ conId 없음: {leg.get('cp')} {leg.get('strike')}")
                return None
            cl = ComboLeg()
            cl.conId = con_id; cl.ratio = int(leg.get("qty",1))
            cl.action = leg["dir"]; cl.exchange = "SMART"
            combo_legs.append(cl)
        bag.comboLegs = combo_legs
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception as _e:
            tif = "DAY"; outside_rth = True
            self._log(f"[SleepOrder] ⚠ session_info 실패→폴백 DAY/outsideRth: {_e}")
        ibord = IbOrder()
        ibord.action = "BUY"; ibord.orderType = "LMT"
        ibord.totalQuantity = qty; ibord.lmtPrice = lmt_price
        ibord.tif = tif; ibord.outsideRth = outside_rth
        ibord.eTradeOnly = False; ibord.firmQuoteOnly = False; ibord.transmit = True
        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(f"[SleepOrder] ✅ BAG 주문 OID={oid} ${lmt_price:.2f}×{qty} [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ placeOrder 실패: {e}"); return None
        if not hasattr(self, '_exec_known_oids'): self._exec_known_oids = set()
        self._exec_known_oids.add(oid)
        self._chaser_bag_contract = bag
        self._chaser_current_oid  = oid
        self._chaser_oid          = oid
        self._pending_position = {
            "strategy": strat, "qty": qty, "entry": lmt_price,
            "current": lmt_price, "side": "BUY",
            "oid": oid, "legs": legs, "status": "미체결",
        }
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().watch(
                self, oid, lmt_price, "BUY", legs, strat, bag_contract=bag, qty=qty)
        except Exception as e:
            self._log(f"[SleepOrder] ⚠ SpecialFillWatcher 등록 실패: {e}")
        return oid

    # ── 4. Debit Spread BAG 정정 ────────────────────────────────

    def _sleep_modify_order(self, oid: int, new_lmt: float,
                            legs: list, qty: int, strat: str = "") -> None:
        try:
            from ibapi.order import Order as IbOrder
            ib  = getattr(getattr(self, 'mw', None), 'ib', None)
            bag = getattr(self, '_chaser_bag_contract', None)
            if ib is None or bag is None:
                self._log(f"[SleepOrder] ❌ 정정 실패: "
                          f"{'IB 미연결' if ib is None else 'bag_contract 없음'} OID={oid}")
                return
            ibord = IbOrder()
            ibord.action = "BUY"; ibord.orderType = "LMT"
            ibord.totalQuantity = qty; ibord.lmtPrice = new_lmt
            ibord.tif = "DAY"; ibord.eTradeOnly = False
            ibord.firmQuoteOnly = False; ibord.transmit = True
            ib.placeOrder(oid, bag, ibord)
            self._log(f"[SleepOrder] ✅ BAG 정정 OID={oid} → ${new_lmt:.2f} qty={qty}")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ BAG 정정 실패 OID={oid}: {e}")

    # ── 5. Debit Spread 자동 매도 ───────────────────────────────

    def _sleep_place_sell_order(self, legs: list, lmt_price: float,
                                qty: int = 1, strat: str = "",
                                tag: str = "SPIKE_AUTO_SELL") -> Optional[int]:
        try:
            from combo_order_bag import _sleep_place_sell_order as _fn
            return _fn(self, legs=legs, lmt_price=lmt_price,
                       qty=qty, strat=strat, tag=tag)
        except Exception as e:
            self._log(f"[SleepOrder] ❌ Debit 자동매도 실패: {e}"); return None

    # ── 6. 단일 옵션 주문  [신규] ───────────────────────────────

    def _sleep_place_single_order(self, strike: float, cp: str,
                                  lmt_price: float, qty: int,
                                  strat: str = "",
                                  tag: str = "SPIKE_SINGLE") -> Optional[int]:
        """단일 PUT/CALL 매수 주문 → OID 반환."""
        try:
            from ibapi.contract import Contract
            from ibapi.order    import Order as IbOrder
            from combo_order_callbacks import connect_order_callbacks
        except ImportError as e:
            self._log(f"[SleepOrder] ❌ import 실패: {e}"); return None
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None: self._log("[SleepOrder] ❌ IB 미연결"); return None
        connect_order_callbacks(self)
        oid = ib.get_next_id()
        if oid is None: self._log("[SleepOrder] ❌ OID 발급 실패"); return None
        expiry = getattr(self, '_current_expiry', '') or ''
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
        # 단일 옵션 컨트랙트
        try:
            from core_contract import make_opt_contract
            contract = make_opt_contract(symbol, strike, cp, expiry)
        except Exception:
            contract = Contract()
            contract.symbol   = symbol
            contract.secType  = "OPT"
            contract.currency = "USD"
            contract.exchange = "SMART"
            contract.right    = cp
            contract.strike   = strike
            contract.lastTradeDateOrContractMonth = expiry
            contract.multiplier = "100"
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception as _e:
            tif = "DAY"; outside_rth = True
            self._log(f"[SleepOrder] ⚠ session_info 실패→폴백 DAY/outsideRth: {_e}")
        ibord = IbOrder()
        ibord.action = "BUY"; ibord.orderType = "LMT"
        ibord.totalQuantity = qty; ibord.lmtPrice = lmt_price
        ibord.tif = tif; ibord.outsideRth = outside_rth
        ibord.eTradeOnly = False; ibord.firmQuoteOnly = False; ibord.transmit = True
        try:
            ib.placeOrder(oid, contract, ibord)
            self._log(f"[SleepOrder] ✅ 단일옵션 주문 {cp}{strike} "
                      f"OID={oid} ${lmt_price:.2f}×{qty} [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ 단일옵션 placeOrder 실패: {e}"); return None
        if not hasattr(self, '_exec_known_oids'): self._exec_known_oids = set()
        self._exec_known_oids.add(oid)
        self._chaser_current_oid = oid
        return oid

    # ── 7. 단일 옵션 정정  [신규] ───────────────────────────────

    def _sleep_modify_single_order(self, oid: int, new_lmt: float,
                                   strike: float, cp: str,
                                   qty: int, strat: str = "") -> None:
        """단일 옵션 주문 정정."""
        try:
            from ibapi.contract import Contract
            from ibapi.order    import Order as IbOrder
            ib = getattr(getattr(self, 'mw', None), 'ib', None)
            if ib is None: self._log("[SleepOrder] ❌ 단일옵션 정정: IB 미연결"); return
            expiry = getattr(self, '_current_expiry', '') or ''
            sym_w  = getattr(self, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW","SPX")
            try:
                from core_contract import make_opt_contract
                contract = make_opt_contract(symbol, strike, cp, expiry)
            except Exception:
                contract = Contract()
                contract.symbol   = symbol; contract.secType  = "OPT"
                contract.currency = "USD";  contract.exchange = "SMART"
                contract.right    = cp;     contract.strike   = strike
                contract.lastTradeDateOrContractMonth = expiry
                contract.multiplier = "100"
            ibord = IbOrder()
            ibord.action = "BUY"; ibord.orderType = "LMT"
            ibord.totalQuantity = qty; ibord.lmtPrice = new_lmt
            ibord.tif = "DAY"; ibord.eTradeOnly = False
            ibord.firmQuoteOnly = False; ibord.transmit = True
            ib.placeOrder(oid, contract, ibord)
            self._log(f"[SleepOrder] ✅ 단일옵션 정정 {cp}{strike} "
                      f"OID={oid} → ${new_lmt:.2f}")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ 단일옵션 정정 실패 OID={oid}: {e}")

    # ── 8. 단일 옵션 자동 매도  [신규] ─────────────────────────

    def _sleep_place_single_sell_order(self, strike: float, cp: str,
                                       lmt_price: float, qty: int,
                                       strat: str = "",
                                       tag: str = "SPIKE_SINGLE_SELL") -> Optional[int]:
        """단일 옵션 자동 익절 매도 주문."""
        try:
            from ibapi.contract import Contract
            from ibapi.order    import Order as IbOrder
            from combo_order_callbacks import connect_order_callbacks
        except ImportError as e:
            self._log(f"[SleepOrder] ❌ import 실패: {e}"); return None
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None: self._log("[SleepOrder] ❌ IB 미연결"); return None
        connect_order_callbacks(self)
        oid = ib.get_next_id()
        if oid is None: self._log("[SleepOrder] ❌ OID 발급 실패"); return None
        expiry = getattr(self, '_current_expiry', '') or ''
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW","SPX")
        try:
            from core_contract import make_opt_contract
            contract = make_opt_contract(symbol, strike, cp, expiry)
        except Exception:
            contract = Contract()
            contract.symbol   = symbol; contract.secType  = "OPT"
            contract.currency = "USD";  contract.exchange = "SMART"
            contract.right    = cp;     contract.strike   = strike
            contract.lastTradeDateOrContractMonth = expiry
            contract.multiplier = "100"
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception as _e:
            tif = "DAY"; outside_rth = True
            self._log(f"[SleepOrder] ⚠ session_info 실패→폴백 DAY/outsideRth: {_e}")
        ibord = IbOrder()
        ibord.action = "SELL"; ibord.orderType = "LMT"
        ibord.totalQuantity = qty; ibord.lmtPrice = lmt_price
        ibord.tif = tif; ibord.outsideRth = outside_rth
        ibord.eTradeOnly = False; ibord.firmQuoteOnly = False; ibord.transmit = True
        try:
            ib.placeOrder(oid, contract, ibord)
            self._log(f"[SleepOrder] 💰 단일옵션 자동매도 {cp}{strike} "
                      f"OID={oid} ${lmt_price:.2f}×{qty} [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ 단일옵션 자동매도 실패: {e}"); return None
        if not hasattr(self, '_exec_known_oids'): self._exec_known_oids = set()
        self._exec_known_oids.add(oid)
        return oid


# ── 유틸 (클래스 바깥) ───────────────────────────────────────────

def _detect_strike_step(strikes: list) -> float:
    if len(strikes) < 2: return 5.0
    diffs = [abs(strikes[i] - strikes[i-1]) for i in range(1, min(5, len(strikes)))
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
