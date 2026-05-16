"""
sleep_order_mixin.py — SleepOrder 연동 메서드  v1.2
════════════════════════════════════════════════════════
combo_ui_left.py 의 LeftPanelMixin 에 상속 추가.

v1.1 수정:
  · _build_bag_contract() 없음 확인 → BAG 컨트랙트 직접 조립
  · OID 발급: ib.get_next_id() 사용 (combo_order_bag.py 와 동일)
  · _place_combo_legs 경로 재사용 대신 직접 placeOrder
    (수면 주문은 UI 다이얼로그/틱 선택창 없이 바로 전송)
  · connect_order_callbacks() 호출 포함
  · _sleep_modify_order: _chaser_bag_contract 재사용

v1.2 수정:
  · _sleep_subscribe_chain(): 예약주문 ON 시 감시 대상 풋 행사가
    전체를 전용 reqId(REQ_SLEEP_BASE=8600~)로 직접 구독.
    tick 수신 시 bid/ask mid → _sleep_live_prices[strike] 저장.
  · _sleep_unsubscribe_chain(): 예약주문 OFF 시 구독 해제.
  · _sleep_get_chain(): _sleep_live_prices 우선 참조,
    없으면 _chain_put(3초 캐시) 폴백.
════════════════════════════════════════════════════════
"""
from __future__ import annotations
from typing import Optional

# 수면 주문 전용 reqId 범위: 8600 ~ 8699 (최대 100개 행사가)
_REQ_SLEEP_BASE = 8600
_REQ_SLEEP_MAX  = 100


class SleepOrderMixin:
    """
    LeftPanelMixin 에 추가할 Sleep Order 연동 메서드 묶음.
    단독으로 사용하거나 Mixin 으로 상속.
    """

    # ── 0. 실시간 구독 관리 ─────────────────────────────────────

    def _sleep_subscribe_chain(self) -> None:
        """
        예약주문 ON 시 호출.
        현재 _put_strikes 전체를 전용 reqId(8600~)로 직접 구독.
        tick 수신마다 bid/ask mid → self._sleep_live_prices[strike] 갱신.
        """
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None or not getattr(getattr(self, 'mw', None), 'connected', False):
            self._log("[SleepOrder] ⚠ 구독 실패: TWS 미연결")
            return

        put_strikes: list = getattr(self, '_put_strikes', [])
        expiry: str       = getattr(self, '_current_expiry', '') or ''
        sym_w             = getattr(self, 'edit_sym_combo', None)
        symbol            = sym_w.text().strip().upper() if sym_w else "SPX"
        symbol            = symbol.replace("SPXW", "SPX")

        if not put_strikes or not expiry:
            self._log("[SleepOrder] ⚠ 구독 실패: 행사가/만기 없음")
            return

        # 이전 구독 정리 후 재구독
        self._sleep_unsubscribe_chain()

        self._sleep_live_prices: dict = {}   # {strike: mid_price}
        self._sleep_req_map: dict     = {}   # {req_id: strike}

        try:
            from core_contract import make_opt_contract
        except ImportError:
            self._log("[SleepOrder] ⚠ core_contract import 실패 — 캐시 폴백")
            return

        try:
            from core import router
        except ImportError:
            self._log("[SleepOrder] ⚠ core.router import 실패 — 캐시 폴백")
            return

        subscribed = 0
        for i, strike in enumerate(put_strikes[:_REQ_SLEEP_MAX]):
            req_id = _REQ_SLEEP_BASE + i
            try:
                contract = make_opt_contract(symbol, strike, "P", expiry)
                ib.reqMktData(req_id, contract, "", False, False, [])
                self._sleep_req_map[req_id] = strike

                # tick 콜백 등록
                router.register_price(
                    req_id, req_id,
                    lambda rid, tt, px, _s=strike: self._sleep_on_tick(rid, tt, px, _s)
                )
                subscribed += 1
            except Exception as e:
                self._log(f"[SleepOrder] ⚠ reqMktData 실패 strike={strike}: {e}")

        self._log(
            f"[SleepOrder] 📡 실시간 구독 시작: {subscribed}개 행사가"
            f"  reqId {_REQ_SLEEP_BASE}~{_REQ_SLEEP_BASE + subscribed - 1}")

    def _sleep_unsubscribe_chain(self) -> None:
        """예약주문 OFF 시 호출. 전용 구독 전체 해제."""
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        req_map: dict = getattr(self, '_sleep_req_map', {})

        if not req_map:
            return

        try:
            from core import router
        except ImportError:
            router = None

        for req_id in list(req_map.keys()):
            try:
                if ib:
                    ib.cancelMktData(req_id)
            except Exception:
                pass
            try:
                if router:
                    router.unregister_price(req_id)
            except Exception:
                pass

        count = len(req_map)
        self._sleep_req_map    = {}
        self._sleep_live_prices = {}
        self._log(f"[SleepOrder] 🔌 실시간 구독 해제: {count}개")

    def _sleep_on_tick(self, req_id: int, tick_type: int,
                       price: float, strike: float) -> None:
        """
        풋 옵션 tick 수신 콜백.
        tick_type 1=bid, 2=ask → 쌍이 모이면 mid 계산하여 저장.
        tick_type 4=last → bid/ask 없을 때 폴백으로만 사용.
        """
        if price <= 0:
            return

        if not hasattr(self, '_sleep_tick_buf'):
            self._sleep_tick_buf: dict = {}   # {strike: {"bid":?, "ask":?}}

        buf = self._sleep_tick_buf.setdefault(strike, {})

        if tick_type == 1:    # bid
            buf["bid"] = price
        elif tick_type == 2:  # ask
            buf["ask"] = price
        elif tick_type == 4:  # last — 폴백
            buf.setdefault("last", price)

        bid = buf.get("bid")
        ask = buf.get("ask")

        if bid and ask and bid > 0 and ask > 0:
            mid = round((bid + ask) / 2, 2)
            if not hasattr(self, '_sleep_live_prices'):
                self._sleep_live_prices = {}
            self._sleep_live_prices[strike] = mid
        elif "last" in buf and strike not in getattr(self, '_sleep_live_prices', {}):
            # bid/ask 미수신 시 last 임시 저장
            if not hasattr(self, '_sleep_live_prices'):
                self._sleep_live_prices = {}
            self._sleep_live_prices[strike] = buf["last"]

    # ── 1. 지수 현재가 ──────────────────────────────────────────

    def _sleep_get_underlying_price(self) -> float:
        """현재 지수 가격. _und_price 우선, 없으면 콜-풋탭 참조."""
        price = float(getattr(self, '_und_price', 0.0) or 0.0)
        if price > 0:
            return price
        try:
            cp = getattr(getattr(self, 'mw', None), 'tab_callput', None)
            if cp:
                price = float(getattr(cp, 'und_price', 0) or 0)
        except Exception:
            pass
        return float(price)

    # ── 2. 체인 스캔 ────────────────────────────────────────────

    def _sleep_get_chain(self, expiry_offset: int) -> list:
        """
        D+expiry_offset 만기 기준 풋 스프레드 체인 반환.

        반환 형식:
        [
          {
            "strike":  5800.0,
            "put_net": 0.50,
            "put_ask": 0.55,
            "legs": [
              {"cp":"P","strike":5800,"expiry":"20260520",
               "dir":"BUY","qty":1,"prem":0.80,"con_id":123456},
              {"cp":"P","strike":5780,"expiry":"20260520",
               "dir":"SELL","qty":1,"prem":0.30,"con_id":789012},
            ]
          },
          ...
        ]
        """
        from Sleep_Order.sleep_order_config import sleep_cfg

        put_strikes: list = getattr(self, '_put_strikes', [])
        chain_put: dict   = getattr(self, '_chain_put', {})
        live_prices: dict = getattr(self, '_sleep_live_prices', {})
        expiry: str       = getattr(self, '_current_expiry', '') or ''

        # 실시간 구독 가격 수신 현황 로그
        live_count = len([v for v in live_prices.values() if v and v > 0])
        if live_count > 0:
            price_src = f"실시간({live_count}개)"
        else:
            price_src = "캐시(_chain_put) 폴백"

        def _get_price(strike: float) -> Optional[float]:
            """실시간 mid 우선, 없으면 _chain_put(3초 캐시) 폴백."""
            p = live_prices.get(strike)
            if p and p > 0:
                return p
            return chain_put.get(strike)

        if not put_strikes or not expiry:
            return []

        target_expiry = _offset_expiry(expiry, expiry_offset)
        if not target_expiry:
            target_expiry = expiry

        step         = _detect_strike_step(put_strikes)
        width        = sleep_cfg.spread_width
        n_step       = max(1, round(width / step)) if step > 0 else 1
        actual_width = n_step * step

        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            sym_w  = getattr(self, 'edit_sym_combo', None)
            symbol = sym_w.text().strip().upper() if sym_w else "SPX"
            symbol = symbol.replace("SPXW", "SPX")
            _has_cache = True
        except ImportError:
            _has_cache = False
            symbol = "SPX"

        def _cid(strike: float) -> int:
            if not _has_cache:
                return 0
            try:
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "P", strike, target_expiry), 0))
            except Exception:
                return 0

        strike_set = set(put_strikes)
        results    = []

        for upper in put_strikes:
            lower = upper - actual_width
            if lower not in strike_set:
                candidates = [s for s in put_strikes if s < upper]
                if not candidates:
                    continue
                lower  = max(candidates)
                real_w = upper - lower
                if real_w < step or real_w > actual_width * 1.5:
                    continue

            upper_last = _get_price(upper)
            lower_last = _get_price(lower)
            if upper_last is None or lower_last is None:
                continue

            net = round(upper_last - lower_last, 2)
            if net <= 0:
                continue

            tick = 0.10 if net >= 3.0 else 0.05
            ask  = round(net + tick, 2)

            results.append({
                "strike":  upper,
                "put_net": net,
                "put_ask": ask,
                "legs": [
                    {
                        "cp": "P", "strike": upper, "expiry": target_expiry,
                        "dir": "BUY",  "qty": 1,
                        "prem": upper_last, "con_id": _cid(upper),
                    },
                    {
                        "cp": "P", "strike": lower, "expiry": target_expiry,
                        "dir": "SELL", "qty": 1,
                        "prem": lower_last, "con_id": _cid(lower),
                    },
                ],
            })

        return results

    # ── 3. BAG 주문 실행 ────────────────────────────────────────

    def _sleep_place_order(self, legs: list, lmt_price: float,
                           qty: int, strat: str,
                           tag: str = "") -> Optional[int]:
        """
        풋 스프레드 BAG 주문 전송 → OID 반환.

        · UI 다이얼로그/틱 선택창 없이 직접 placeOrder
          (새벽 자동 주문이므로 대화창 불필요)
        · conId 는 legs[i]['con_id'] 에서 읽음
        · OID 발급: ib.get_next_id() (combo_order_bag 과 동일)
        · connect_order_callbacks() 로 콜백 연결 보장
        """
        try:
            from ibapi.contract import Contract, ComboLeg
            from ibapi.order   import Order as IbOrder
            from combo_order_callbacks import connect_order_callbacks
        except ImportError as e:
            self._log(f"[SleepOrder] ❌ import 실패: {e}")
            return None

        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        if ib is None:
            self._log("[SleepOrder] ❌ IB 미연결")
            return None

        connect_order_callbacks(self)

        # OID 발급
        oid = ib.get_next_id()
        if oid is None:
            self._log("[SleepOrder] ❌ OID 발급 실패")
            return None

        # BAG 컨트랙트 조립
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = sym_w.text().strip().upper() if sym_w else "SPX"

        bag          = Contract()
        bag.symbol   = symbol.replace("SPXW", "SPX")
        bag.secType  = "BAG"
        bag.currency = "USD"
        bag.exchange = "SMART"

        combo_legs_list = []
        for leg in legs:
            con_id = int(leg.get("con_id") or 0)
            if con_id == 0:
                try:
                    from combo_order_bag import _CONID_CACHE, _conid_key
                    key    = _conid_key(
                        bag.symbol,
                        str(leg.get("cp", "P")),
                        float(leg.get("strike", 0)),
                        str(leg.get("expiry", "")),
                    )
                    con_id = int(_CONID_CACHE.get(key, 0))
                except Exception:
                    pass

            if con_id == 0:
                self._log(
                    f"[SleepOrder] ❌ conId 없음: "
                    f"{leg.get('cp')} {leg.get('strike')} {leg.get('expiry')}")
                return None

            cl          = ComboLeg()
            cl.conId    = con_id
            cl.ratio    = int(leg.get("qty", 1))
            cl.action   = leg["dir"]
            cl.exchange = "SMART"
            combo_legs_list.append(cl)

        bag.comboLegs = combo_legs_list

        # tif / outsideRth — 새벽 Pre-Market 시간대
        try:
            from combo_order_logic import _get_session_info
            _, _, tif, outside_rth = _get_session_info()
        except Exception:
            tif         = "DAY"
            outside_rth = True

        # 주문 객체
        ibord               = IbOrder()
        ibord.action        = "BUY"
        ibord.orderType     = "LMT"
        ibord.totalQuantity = qty
        ibord.lmtPrice      = lmt_price
        ibord.tif           = tif
        ibord.outsideRth    = outside_rth
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True

        # placeOrder
        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(
                f"[SleepOrder] ✅ BAG 주문 OID={oid}"
                f"  ${lmt_price:.2f} × {qty}"
                f"  TIF:{tif}  outsideRth:{outside_rth}  [{tag}]")
        except Exception as e:
            self._log(f"[SleepOrder] ❌ placeOrder 실패: {e}")
            return None

        # 내부 상태 세팅 (combo_order_bag._do_send_body 와 동일 구조)
        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)

        self._chaser_bag_contract = bag   # 정정 시 재사용
        self._chaser_current_oid  = oid
        self._chaser_oid          = oid

        self._pending_position = {
            "strategy": strat,
            "qty":      qty,
            "entry":    lmt_price,
            "current":  lmt_price,
            "side":     "BUY",
            "oid":      oid,
            "legs":     legs,
            "status":   "미체결",
        }

        # SpecialFillWatcher 등록 (기존 TG-3 재사용)
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().watch(
                self, oid, lmt_price, "BUY", legs, strat,
                bag_contract=bag, qty=qty)
        except Exception as _e:
            self._log(f"[SleepOrder] ⚠ SpecialFillWatcher 등록 실패: {_e}")

        return oid

    """
    sleep_order_mixin_patch.py — _sleep_place_sell_order 바인딩 패치
    ════════════════════════════════════════════════════════════════
    기존 sleep_order_mixin.py 의 SleepOrderMixin 클래스에
    아래 메서드 1개를 추가하세요.

    위치: _sleep_place_order() 메서드 바로 아래
    ════════════════════════════════════════════════════════════════
    """

    # ── sleep_order_mixin.py 에 추가할 메서드 ──────────────────────

    def _sleep_place_sell_order(self, legs: list, lmt_price: float,
                                qty: int = 1, strat: str = "",
                                tag: str = "SPIKE_AUTO_SELL"):
        """
        급락 캐치 자동 익절 매도 주문 콜백.
        SpikeCatcher._place_sell_order() 에서 호출됨.

        combo_order_bag._sleep_place_sell_order() 로 위임.
        별도 UI 확인 없이 즉시 전송.
        """
        from combo_order_bag import _sleep_place_sell_order as _fn
        return _fn(
            self,
            legs=legs,
            lmt_price=lmt_price,
            qty=qty,
            strat=strat,
            tag=tag,
        )
        # ── 4. 주문 정정 ────────────────────────────────────────────

    def _sleep_modify_order(self, oid: int, new_lmt: float,
                            legs: list, qty: int,
                            strat: str = "") -> None:
        """
        수면 주문 정정.
        _chaser_bag_contract 재사용 (_sleep_place_order 에서 저장).
        """
        try:
            from ibapi.order import Order as IbOrder

            ib  = getattr(getattr(self, 'mw', None), 'ib', None)
            bag = getattr(self, '_chaser_bag_contract', None)

            if ib is None or bag is None:
                self._log(
                    f"[SleepOrder] ❌ 정정 실패: "
                    f"{'IB 미연결' if ib is None else 'bag_contract 없음'}"
                    f"  OID={oid}")
                return

            ibord               = IbOrder()
            ibord.action        = "BUY"
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = new_lmt
            ibord.tif           = "DAY"
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            ibord.transmit      = True

            ib.placeOrder(oid, bag, ibord)
            self._log(
                f"[SleepOrder] ✅ 정정 OID={oid}"
                f"  → ${new_lmt:.2f}  qty={qty}")

        except Exception as e:
            self._log(f"[SleepOrder] ❌ 정정 실패 OID={oid}: {e}")


# ── 유틸 ─────────────────────────────────────────────────────────

def _detect_strike_step(strikes: list) -> float:
    """행사가 목록에서 기본 간격 자동 감지. 기본 $5."""
    if len(strikes) < 2:
        return 5.0
    diffs = []
    for i in range(1, min(5, len(strikes))):
        d = abs(strikes[i] - strikes[i - 1])
        if d > 0:
            diffs.append(d)
    return min(diffs) if diffs else 5.0


def _offset_expiry(expiry8: str, offset: int) -> str:
    """
    8자리 만기 코드에 영업일 offset 추가.
    offset=0 → 당일, 1 → 다음 거래일 (주말 건너뜀, 공휴일 미처리).
    """
    if not expiry8 or len(expiry8) != 8:
        return expiry8
    if offset == 0:
        return expiry8
    try:
        from datetime import datetime, timedelta
        dt    = datetime.strptime(expiry8, "%Y%m%d")
        added = 0
        while added < offset:
            dt += timedelta(days=1)
            if dt.weekday() < 5:
                added += 1
        return dt.strftime("%Y%m%d")
    except Exception:
        return expiry8