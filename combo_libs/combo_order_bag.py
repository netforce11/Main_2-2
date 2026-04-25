"""
combo_order_bag.py — BAG(Combo) 주문 전송 로직  v2.9
──────────────────────────────────────────────────────
변경 (v2.9):
  - _do_send(): _orig_cd / _orig_cd_end 복구 코드 제거 (잔류 코드)
  - register_chaser() 호출 시 qty=ibord.totalQuantity 전달
  - connect_order_callbacks() 호출 → orderStatus/execDetails 콜백 자동 연결
  - 기존 주문 로직 변경 없음
──────────────────────────────────────────────────────
Python 3.8 호환
"""

from __future__ import annotations
import json
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer
from combo_order_chaser import register_chaser
from combo_order_callbacks import connect_order_callbacks


# ── conId 캐시 ─────────────────────────────────────────────────
_CONID_CACHE: dict = {}
_CACHE_FILE = Path("data/conid_cache.json")


def _load_conid_cache() -> None:
    """Load cache from disk, then purge keys with past expiry dates."""
    global _CONID_CACHE
    try:
        if _CACHE_FILE.exists():
            _CONID_CACHE = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CONID_CACHE = {}
    _purge_stale_conid_keys()


def _purge_stale_conid_keys() -> None:
    """
    Remove keys whose expiry date (YYYYMMDD, 4th field) is before today.
    Key format: 'SYMBOL|RIGHT|STRIKE|YYYYMMDD'
    Runs once at startup — keeps cache lean without touching live entries.
    """
    from datetime import date
    today_str = date.today().strftime("%Y%m%d")
    stale = [k for k in list(_CONID_CACHE)
             if len(k.split("|")) == 4 and k.split("|")[3] < today_str]
    for k in stale:
        del _CONID_CACHE[k]
    if stale:
        _save_conid_cache()
        print(f"[conid_cache] purged {len(stale)} stale key(s)")


def _save_conid_cache() -> None:
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(_CONID_CACHE, indent=2), encoding="utf-8")
    except Exception:
        pass


def _conid_key(symbol: str, right: str, strike: float, expiry: str) -> str:
    return f"{symbol}|{right}|{int(strike)}|{expiry}"


_load_conid_cache()


# ══════════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════════

def _place_combo_legs(self, legs: list, strat: str) -> None:
    """BAG 주문 진입점. 호출마다 세션 무효화 → 이전 타이머 완전 차단."""
    self._bag_session = None

    # ★ v2.9: orderStatus / execDetails 콜백 연결 (1회만)
    connect_order_callbacks(self)

    try:
        from core_contract import make_opt_contract
        from ibapi.contract import Contract, ComboLeg
    except ImportError as e:
        QMessageBox.critical(self, "오류", f"모듈 import 실패: {e}")
        return

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = (sym_w.text().strip().upper() if sym_w else "SPX")

    bag = Contract()
    bag.symbol  = symbol.replace("SPXW", "SPX")
    bag.secType = "BAG"
    bag.currency = "USD"
    bag.exchange = "SMART"

    combo_legs = []
    for leg in legs:
        opt_contract = make_opt_contract(
            symbol=symbol, strike=leg["strike"],
            right=leg["cp"], expiry=leg["expiry"])
        cl = ComboLeg()
        cl.conId    = 0
        cl.ratio    = int(float(leg["qty"]))
        cl.action   = leg["dir"]
        cl.exchange = "SMART"
        combo_legs.append((cl, opt_contract))

    _place_bag_with_conids(self, bag, combo_legs, legs, strat)


# ══════════════════════════════════════════════════════════════
# conId 조회
# ══════════════════════════════════════════════════════════════

def _place_bag_with_conids(self, bag, combo_legs: list,
                           legs: list, strat: str) -> None:
    """conId 조회(캐시 우선) 후 _do_send 호출."""
    import time as _t
    session = int(_t.time() * 1000)
    self._bag_session = session

    ib       = self.mw.ib
    total    = len(combo_legs)
    resolved: dict = {}
    symbol   = bag.symbol
    base_rid = 9910

    # ── 캐시 우선 채우기 ────────────────────────────────────
    for i, (cl, opt_c) in enumerate(combo_legs):
        key = _conid_key(symbol, opt_c.right, opt_c.strike,
                         opt_c.lastTradeDateOrContractMonth)
        if key in _CONID_CACHE:
            resolved[i] = _CONID_CACHE[key]
            self._log(f"  캐시 히트: 레그{i+1} conId={resolved[i]}")

    if len(resolved) == total:
        self._log("⚡ conId 전부 캐시 — 즉시 주문 진행")
        QTimer.singleShot(0, lambda: _do_send(
            self, bag, combo_legs, legs, strat, ib, total, resolved, session))
        return

    # ── 미캐시 → bridge 시그널 수신 ─────────────────────────
    from core import bridge as _bridge
    _cd_conn = [None, None]

    def _on_cd(reqId, contractDetails):
        if getattr(self, '_bag_session', None) != session:
            return
        idx = reqId - base_rid
        if 0 <= idx < total:
            cid = contractDetails.contract.conId
            resolved[idx] = cid
            opt_c = combo_legs[idx][1]
            key = _conid_key(symbol, opt_c.right, opt_c.strike,
                             opt_c.lastTradeDateOrContractMonth)
            _CONID_CACHE[key] = cid
            _save_conid_cache()
            self._log(f"  conId 수신: 레그{idx+1} conId={cid}")

    def _on_cd_end(reqId):
        if getattr(self, '_bag_session', None) != session:
            return
        idx = reqId - base_rid
        if 0 <= idx < total and idx not in resolved:
            resolved[idx] = 0
        if all(i in resolved for i in range(total)):
            _disconnect_cd()
            QTimer.singleShot(0, lambda: _do_send(
                self, bag, combo_legs, legs, strat, ib, total, resolved, session))

    def _disconnect_cd():
        try:
            if _cd_conn[0]:
                _bridge.contract_details_sig.disconnect(_on_cd)
        except Exception:
            pass
        try:
            if _cd_conn[1]:
                _bridge.contract_details_end_sig.disconnect(_on_cd_end)
        except Exception:
            pass
        _cd_conn[0] = _cd_conn[1] = None

    _bridge.contract_details_sig.connect(_on_cd)
    _bridge.contract_details_end_sig.connect(_on_cd_end)
    _cd_conn[0] = _on_cd
    _cd_conn[1] = _on_cd_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        if i in resolved:
            continue
        try:
            ib.reqContractDetails(base_rid + i, opt_contract)
            self._log(
                f"🔍 conId 조회: 레그{i+1} "
                f"{opt_contract.right} {int(opt_contract.strike)} "
                f"만기={opt_contract.lastTradeDateOrContractMonth!r}")
        except Exception as e:
            self._log(f"❌ reqContractDetails 레그{i+1}: {e}")
            resolved[i] = 0

    def _on_timeout():
        if getattr(self, '_bag_session', None) != session:
            return
        _disconnect_cd()
        for i in range(total):
            if i not in resolved:
                resolved[i] = 0
                opt_c = combo_legs[i][1]
                self._log(
                    f"  ⚠ 레그{i+1} conId 타임아웃 10초 — "
                    f"{opt_c.right} {int(opt_c.strike)} "
                    f"{opt_c.lastTradeDateOrContractMonth}")
        _do_send(self, bag, combo_legs, legs, strat, ib, total, resolved, session)

    QTimer.singleShot(10000, _on_timeout)


# ══════════════════════════════════════════════════════════════
# 주문 전송
# ══════════════════════════════════════════════════════════════

def _do_send(self, bag, combo_legs: list, legs: list, strat: str,
             ib, total: int, resolved: dict, session: int) -> None:
    """확인창 표시 후 BAG placeOrder. 세션 불일치/중복 호출 시 즉시 리턴."""
    if getattr(self, '_bag_session', None) != session:
        return

    # 중복 호출 방지
    # Fix #9: lock_key를 finally에서 반드시 삭제해 self에 키가 누적되는 버그 수정.
    # 이전 코드는 setattr(self, lock_key, True)만 하고 delattr 없이 방치됨.
    lock_key = f'_do_send_lock_{session}'
    if getattr(self, lock_key, False):
        return
    setattr(self, lock_key, True)

    try:
        _do_send_inner(self, bag, combo_legs, legs, strat, ib, total, resolved, session)
    finally:
        # Fix #9: 호출 완료(성공/실패/예외 무관) 후 lock 키 제거
        try:
            delattr(self, lock_key)
        except AttributeError:
            pass


    # ★ v2.9: _orig_cd 복구 코드 제거 (bridge 방식으로 교체됨, 잔류 코드였음)

    # conId 세팅
    for i, (cl, _) in enumerate(combo_legs):
        cl.conId = resolved.get(i, 0)
        self._log(
            f"  레그{i+1} conId={cl.conId}  "
            f"{legs[i]['dir']} {legs[i]['cp']} {int(legs[i]['strike'])}")
    bag.comboLegs = [cl for cl, _ in combo_legs]

    # conId=0 레그 존재 시 주문 차단
    zero_legs = [i + 1 for i, (cl, _) in enumerate(combo_legs) if cl.conId == 0]
    if zero_legs:
        self._bag_session = None
        self._log(
            f"❌ 주문 취소: 레그 {zero_legs} conId 조회 실패 (타임아웃) — "
            f"체인 동기화 후 다시 시도하세요")
        QMessageBox.warning(
            self, "주문 오류",
            f"레그 {zero_legs}의 conId 조회가 타임아웃됐습니다.\n\n"
            f"복합전략 탭 좌측 '↺ 즉시 동기화' 버튼을 누른 후\n"
            f"잠시 기다렸다가 다시 시도하세요.")
        return

    # lmtPrice 계산 — 전광판 위젯 실시간 가격 우선, 없으면 legs 데이터 폴백
    buy_total  = sum(
        float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
        for lg in legs if lg["dir"] == "BUY")
    sell_total = sum(
        float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
        for lg in legs if lg["dir"] == "SELL")
    net = round(buy_total - sell_total, 2)

    # ★ 전광판 위젯에서 실시간 Mid-price 기반 순가격 수신
    display = getattr(self, 'net_price_display', None)
    if display is not None and display.get_net_price() != 0.0:
        params     = display.get_bag_params()
        lmt_price  = params["lmt_price"]
        bag_action = params["action"]
        # net 부호는 위젯 값으로 재동기화
        net = lmt_price if bag_action == "BUY" else -lmt_price
    else:
        # 폴백: legs 데이터 or _recalc_net_price
        try:
            from combo_ui_leg_panel import _recalc_net_price
            ui_price  = _recalc_net_price(self)
            lmt_price = round(abs(float(ui_price)), 2) if ui_price else round(abs(net), 2)
        except Exception:
            lmt_price = round(abs(net), 2)
        bag_action = "BUY" if net >= 0 else "SELL"

    if lmt_price <= 0.0:
        lmt_price = 0.01

    type_label = "데빗 (지불)" if bag_action == "BUY" else "크레딧 (수취)"

    # 확인 다이얼로그
    leg_lines = "\n".join(
        f"  {'매도(SELL)' if lg['dir'] == 'SELL' else '매수(BUY) '}  "
        f"{lg['cp']} {int(lg['strike'])}  ×{lg['qty']}  "
        f"@${float(lg.get('prem', 0)):.2f}"
        for lg in legs)
    expiry_str = legs[0].get("expiry", "") if legs else ""
    if len(expiry_str) == 8:
        expiry_str = (f"{expiry_str[:4]}/{expiry_str[4:6]}/{expiry_str[6:]}")

    from PyQt5.QtWidgets import QMessageBox as _MB
    dlg = _MB(self)
    dlg.setWindowTitle("⚡ 합성 주문 확인")
    dlg.setText(
        f"전략:  {strat}\n만기:  {expiry_str}\n"
        f"─────────────────────────\n{leg_lines}\n"
        f"─────────────────────────\n순비용({type_label}):  ${lmt_price:.2f}")
    dlg.setStandardButtons(_MB.Ok | _MB.Cancel)
    dlg.button(_MB.Ok).setText("주문 전송")
    dlg.button(_MB.Cancel).setText("취소")
    if dlg.exec_() != _MB.Ok:
        self._bag_session = None
        return

    oid = ib.get_next_id()
    if oid is None:
        self._bag_session = None
        self._log("❌ nextOrderId 없음")
        return

    from ibapi.order import Order as IbOrder
    ibord = IbOrder()
    ibord.action        = bag_action
    ibord.orderType     = "LMT"
    ibord.totalQuantity = 1
    ibord.lmtPrice      = lmt_price
    ibord.tif           = "DAY"
    ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False
    ibord.transmit      = True

    try:
        ib.placeOrder(oid, bag, ibord)
        self._log(
            f"⚡ BAG 주문: OID={oid}  {type_label} ${lmt_price:.2f}"
            f"  레그{total}개  qty={ibord.totalQuantity}")
        self._log(
            f"   BUY=${buy_total:.2f}  SELL=${sell_total:.2f}  net=${net:+.2f}")

        self._chaser_bag_contract = bag
        self._chaser_current_oid  = oid
        self._chaser_bag_order    = ibord

        # 체결 후 합성 잔고에 추가하기 위해 주문 정보 캐시 (add_position은 Filled 콜백에서)
        self._pending_position = {
            "strategy": strat,
            "qty":      int(ibord.totalQuantity),
            "entry":    lmt_price,
            "current":  lmt_price,
            "side":     bag_action,
            "oid":      oid,
            "legs":     legs,
            "status":   "미체결",
        }

        # ★ v2.9: qty 파라미터 추가 전달
        register_chaser(
            self, oid=oid, price=lmt_price,
            action=bag_action, qty=int(ibord.totalQuantity))

        # ── 주문 접수 확인: 5초 후 on_open_orders 재사용하여 OID 직접 확인 ──
        # Fix #3: Chaser 첫 정정(4초) + on_open_orders 락(2초) 충돌 방지를 위해
        # 5초로 변경. Chaser 정정이 4초에 실행되고 조회는 5초에 시작하므로
        # _oo_in_progress 락과 겹치지 않음.
        def _verify_order(check_oid=oid):
            from combo_order_open import on_open_orders

            # 조회 완료 후 캐시에서 OID 확인 (조회 2초 + 0.5초 여유 = 2.5초 후)
            def _check_cache():
                orders = getattr(self, '_cached_open_orders', [])
                oids = [o.get('oid') for o in orders]
                if check_oid in oids:
                    self._log(f"✅ OID={check_oid} 주문 접수 확인 (TWS 미체결 목록)")
                else:
                    self._log(f"⚠ OID={check_oid} 주문 미확인 — TWS에서 직접 확인 필요")

            on_open_orders(self)
            QTimer.singleShot(2500, _check_cache)

        QTimer.singleShot(5000, _verify_order)

    except Exception as e:
        self._bag_session = None
        self._log(f"❌ BAG 주문 오류: {e}")