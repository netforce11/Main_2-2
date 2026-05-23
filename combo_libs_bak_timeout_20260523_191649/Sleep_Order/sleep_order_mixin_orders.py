"""
sleep_order_mixin_orders.py — SleepOrder 정정·매도·단일옵션 메서드  v2.1
════════════════════════════════════════════════════════════════
sleep_order_mixin.py 에서 분리.
SleepOrderMixin 에 mixin 으로 포함시키거나
sleep_order_mixin.py 에서 import 해서 사용.

포함 메서드:
  _sleep_modify_order        — Debit Spread BAG 정정
  _sleep_place_sell_order    — Debit Spread 자동 매도
  _sleep_place_single_order  — 단일 옵션 매수
  _sleep_place_single_sell_order — 단일 옵션 매도
  _sleep_single_order_core   — 단일 옵션 BUY/SELL 공통 처리
  _sleep_modify_single_order — 단일 옵션 정정
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Optional


class SleepOrderOrdersMixin:
    """정정·매도·단일 옵션 주문 메서드 묶음."""

    def _sleep_modify_order(self, oid: int, new_lmt: float,
                            legs: list, qty: int, strat: str = "") -> None:
        try:
            from ibapi.order import Order as IbOrder
            ib  = getattr(getattr(self, 'mw', None), 'ib', None)
            bag = getattr(self, '_chaser_bag_contract', None)
            if ib is None or bag is None:
                self._log(f"[SleepOrder] ❌ 정정 실패 OID={oid}"); return
            ibord = IbOrder()
            ibord.action = "BUY"; ibord.orderType = "LMT"
            ibord.totalQuantity = qty; ibord.lmtPrice = new_lmt
            ibord.tif = "DAY"; ibord.eTradeOnly = False
            ibord.firmQuoteOnly = False; ibord.transmit = True
            ib.placeOrder(oid, bag, ibord)
            self._log(f"[SleepOrder] ✅ BAG 정정 OID={oid} → ${new_lmt:.2f}")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ BAG 정정 실패 OID={oid}: {e}")

    def _sleep_place_sell_order(self, legs: list, lmt_price: float,
                                qty: int = 1, strat: str = "",
                                tag: str = "SPIKE_AUTO_SELL") -> Optional[int]:
        try:
            from combo_order_bag import _sleep_place_sell_order as _fn
            return _fn(self, legs=legs, lmt_price=lmt_price,
                       qty=qty, strat=strat, tag=tag)
        except Exception as e:
            self._log(f"[SleepOrder] ❌ Debit 자동매도 실패: {e}"); return None

    def _sleep_place_single_order(self, strike: float, cp: str,
                                  lmt_price: float, qty: int,
                                  strat: str = "",
                                  tag: str = "SPIKE_SINGLE") -> Optional[int]:
        return self._sleep_single_order_core(
            strike, cp, lmt_price, qty, "BUY", tag)

    def _sleep_place_single_sell_order(self, strike: float, cp: str,
                                       lmt_price: float, qty: int,
                                       strat: str = "",
                                       tag: str = "SPIKE_SINGLE_SELL"
                                       ) -> Optional[int]:
        return self._sleep_single_order_core(
            strike, cp, lmt_price, qty, "SELL", tag)

    def _sleep_single_order_core(self, strike: float, cp: str,
                                  lmt_price: float, qty: int,
                                  action: str, tag: str) -> Optional[int]:
        """단일 옵션 BUY/SELL 공통 처리."""
        try:
            from ibapi.order import Order as IbOrder
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
        expiry = getattr(self, '_current_expiry', '') or ''
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX"
                  ).replace("SPXW", "SPX")
        try:
            from core_contract import make_opt_contract
            contract = make_opt_contract(symbol, strike, cp, expiry)
        except Exception:
            from ibapi.contract import Contract
            from combo_order_bag import _get_selected_exchange as _gse
            contract = Contract()
            contract.symbol = symbol; contract.secType = "OPT"
            contract.currency = "USD"; contract.exchange = _gse(self)
            contract.right = cp; contract.strike = strike
            contract.lastTradeDateOrContractMonth = expiry
            contract.multiplier = "100"
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception:
            tif = "DAY"; outside_rth = True
        ibord = IbOrder()
        ibord.action = action; ibord.orderType = "LMT"
        ibord.totalQuantity = qty; ibord.lmtPrice = lmt_price
        ibord.tif = tif; ibord.outsideRth = outside_rth
        ibord.eTradeOnly = False; ibord.firmQuoteOnly = False
        ibord.transmit = True
        try:
            ib.placeOrder(oid, contract, ibord)
            self._log(f"[SleepOrder] ✅ 단일옵션 {action} {cp}{strike} "
                      f"OID={oid} ${lmt_price:.2f}×{qty} [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ 단일옵션 실패: {e}"); return None
        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)
        return oid

    def _sleep_modify_single_order(self, oid: int, new_lmt: float,
                                   strike: float, cp: str,
                                   qty: int, strat: str = "") -> None:
        try:
            from ibapi.order import Order as IbOrder
            ib = getattr(getattr(self, 'mw', None), 'ib', None)
            if ib is None:
                self._log("[SleepOrder] ❌ 단일옵션 정정: IB 미연결"); return
            expiry = getattr(self, '_current_expiry', '') or ''
            sym_w  = getattr(self, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX"
                      ).replace("SPXW", "SPX")
            try:
                from core_contract import make_opt_contract
                contract = make_opt_contract(symbol, strike, cp, expiry)
            except Exception:
                from ibapi.contract import Contract
                from combo_order_bag import _get_selected_exchange as _gse
                contract = Contract()
                contract.symbol = symbol; contract.secType = "OPT"
                contract.currency = "USD"; contract.exchange = _gse(self)
                contract.right = cp; contract.strike = strike
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
