"""
combo_order_bag.py — BAG(Combo) 주문 전송 로직  v2.8
──────────────────────────────────────────────────────
변경:
  - 구버전 중복 코드 완전 제거
  - conId 캐시 (메모리 + data/conid_cache.json)
  - 세션 토큰으로 중복 확인창 완전 차단
  - 잔고 탭: 미체결 주문 상태 추적 (pending/filled)
──────────────────────────────────────────────────────
"""

import json
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer
from combo_order_chaser import register_chaser

# ── conId 캐시 ─────────────────────────────────────────────────
_CONID_CACHE: dict = {}
_CACHE_FILE = Path("data/conid_cache.json")

def _load_conid_cache():
    global _CONID_CACHE
    try:
        if _CACHE_FILE.exists():
            _CONID_CACHE = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CONID_CACHE = {}

def _save_conid_cache():
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_CONID_CACHE, indent=2), encoding="utf-8")
    except Exception:
        pass

def _conid_key(symbol, right, strike, expiry):
    return f"{symbol}|{right}|{int(strike)}|{expiry}"

_load_conid_cache()


# ── 진입점 ─────────────────────────────────────────────────────
def _place_combo_legs(self, legs: list, strat: str):
    """BAG 주문 진입점. 호출마다 세션 무효화 → 이전 타이머 완전 차단."""
    self._bag_session = None
    try:
        from core_contract import make_opt_contract
        from ibapi.contract import Contract, ComboLeg
    except ImportError as e:
        return QMessageBox.critical(self, "오류", f"모듈 import 실패: {e}")

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = (sym_w.text().strip().upper() if sym_w else "SPX")

    bag = Contract()
    bag.symbol  = symbol.replace("SPXW", "SPX")
    bag.secType = "BAG"; bag.currency = "USD"; bag.exchange = "SMART"

    combo_legs = []
    for leg in legs:
        opt_contract = make_opt_contract(
            symbol=symbol, strike=leg["strike"],
            right=leg["cp"], expiry=leg["expiry"])
        cl = ComboLeg()
        cl.conId = 0; cl.ratio = int(float(leg["qty"]))
        cl.action = leg["dir"]; cl.exchange = "SMART"
        combo_legs.append((cl, opt_contract))

    _place_bag_with_conids(self, bag, combo_legs, legs, strat)


def _place_bag_with_conids(self, bag, combo_legs, legs, strat):
    """conId 조회(캐시 우선) 후 _do_send 호출."""
    import time as _t
    session = int(_t.time() * 1000)
    self._bag_session = session

    ib       = self.mw.ib
    total    = len(combo_legs)
    resolved = {}
    symbol   = bag.symbol
    base_rid = 9910

    # ── 캐시 우선 채우기 ────────────────────────────────────────
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

    # ── 미캐시 → bridge 시그널로 수신 (인스턴스 패치 방식 제거) ─
    from core import bridge as _bridge
    _cd_conn = [None, None]  # 연결 해제용

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
        # 전체 레그 완료 시에만 전송
        if all(i in resolved for i in range(total)):
            _disconnect_cd()
            QTimer.singleShot(0, lambda: _do_send(
                self, bag, combo_legs, legs, strat, ib, total, resolved, session))

    def _disconnect_cd():
        try:
            if _cd_conn[0]: _bridge.contract_details_sig.disconnect(_on_cd)
        except Exception: pass
        try:
            if _cd_conn[1]: _bridge.contract_details_end_sig.disconnect(_on_cd_end)
        except Exception: pass
        _cd_conn[0] = _cd_conn[1] = None

    # bridge 시그널 연결 — Qt 스레드 안전
    _bridge.contract_details_sig.connect(_on_cd)
    _bridge.contract_details_end_sig.connect(_on_cd_end)
    _cd_conn[0] = _on_cd
    _cd_conn[1] = _on_cd_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        if i in resolved:
            continue
        try:
            ib.reqContractDetails(base_rid + i, opt_contract)
            self._log(f"🔍 conId 조회: 레그{i+1} "
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
                self._log(f"  ⚠ 레그{i+1} conId 타임아웃 10초 — "
                          f"{opt_c.right} {int(opt_c.strike)} {opt_c.lastTradeDateOrContractMonth}")
        _do_send(self, bag, combo_legs, legs, strat, ib, total, resolved, session)

    QTimer.singleShot(10000, _on_timeout)


def _do_send(self, bag, combo_legs, legs, strat, ib, total, resolved, session):
    """확인창 표시 후 BAG placeOrder. 세션 불일치/중복 호출 시 즉시 리턴."""
    if getattr(self, '_bag_session', None) != session:
        return
    # 중복 호출 방지 (타임아웃 + _on_cd_end 동시 도달 방어)
    lock_key = f'_do_send_lock_{session}'
    if getattr(self, lock_key, False):
        return
    setattr(self, lock_key, True)

    # 콜백 복구
    try:
        ib.contractDetails    = ib._orig_cd
        ib.contractDetailsEnd = ib._orig_cd_end
    except Exception:
        pass

    for i, (cl, _) in enumerate(combo_legs):
        cl.conId = resolved.get(i, 0)
        self._log(f"  레그{i+1} conId={cl.conId}  "
                  f"{legs[i]['dir']} {legs[i]['cp']} {int(legs[i]['strike'])}")
    bag.comboLegs = [cl for cl, _ in combo_legs]

    # ★ conId=0 레그 존재 시 주문 차단 (타임아웃 폴백 케이스)
    zero_legs = [i+1 for i, (cl, _) in enumerate(combo_legs) if cl.conId == 0]
    if zero_legs:
        self._bag_session = None
        self._log(f"❌ 주문 취소: 레그 {zero_legs} conId 조회 실패 (타임아웃) — "
                  f"체인 동기화 후 다시 시도하세요")
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(self, "주문 오류",
            f"레그 {zero_legs}의 conId 조회가 타임아웃됐습니다.\n\n"
            f"복합전략 탭 좌측 '↺ 즉시 동기화' 버튼을 누른 후\n"
            f"잠시 기다렸다가 다시 시도하세요.")
        return

    # lmtPrice 계산
    # BAG 주문: BUY 레그 합계 - SELL 레그 합계 = net
    # net > 0 (데빗): BUY BAG, lmtPrice = net (지불 금액)
    # net < 0 (크레딧): SELL BAG, lmtPrice = abs(net) (수취 금액)
    buy_total  = sum(float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
                     for lg in legs if lg["dir"] == "BUY")
    sell_total = sum(float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
                     for lg in legs if lg["dir"] == "SELL")
    net        = round(buy_total - sell_total, 2)

    # _recalc_net_price 는 보조 수단 — 실패해도 net 으로 대체
    try:
        from combo_ui_leg_panel import _recalc_net_price
        ui_price = _recalc_net_price(self)
        lmt_price = round(abs(float(ui_price)), 2) if ui_price else round(abs(net), 2)
    except Exception:
        lmt_price = round(abs(net), 2)

    # lmtPrice 최소값 보정 — 0.00 이면 주문 거절됨
    if lmt_price <= 0.0:
        lmt_price = 0.01

    bag_action = "BUY" if net >= 0 else "SELL"
    type_label = "데빗 (지불)" if net >= 0 else "크레딧 (수취)"

    # ── 확인 다이얼로그 (1회 보장) ─────────────────────────────
    leg_lines = "\n".join(
        f"  {'매도(SELL)' if lg['dir']=='SELL' else '매수(BUY) '}  "
        f"{lg['cp']} {int(lg['strike'])}  ×{lg['qty']}  "
        f"@${float(lg.get('prem', 0)):.2f}"
        for lg in legs)
    expiry_str = legs[0].get("expiry", "") if legs else ""
    if len(expiry_str) == 8:
        expiry_str = f"{expiry_str[:4]}/{expiry_str[4:6]}/{expiry_str[6:]}"

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
        self._bag_session = None   # 취소 → 재주문 허용
        return

    oid = ib.get_next_id()
    if oid is None:
        self._bag_session = None
        return self._log("❌ nextOrderId 없음")

    from ibapi.order import Order as IbOrder
    ibord = IbOrder()
    ibord.action = bag_action;   ibord.orderType     = "LMT"
    ibord.totalQuantity = 1;     ibord.lmtPrice      = lmt_price
    ibord.tif = "DAY";           ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False;  ibord.transmit      = True

    try:
        ib.placeOrder(oid, bag, ibord)
        self._log(f"⚡ BAG 주문: OID={oid}  {type_label} ${lmt_price:.2f}  레그{total}개")
        self._log(f"   BUY=${buy_total:.2f}  SELL=${sell_total:.2f}  net=${net:+.2f}")
        self._chaser_bag_contract = bag
        self._chaser_current_oid  = oid
        self._chaser_bag_order    = ibord
        register_chaser(self, oid=oid, price=lmt_price, action=bag_action)

        panel = getattr(self, 'synthetic_panel', None)
        if panel:
            # 잔고탭: 미체결 상태로 추가 (체결 시 _on_fill_event에서 갱신)
            panel.add_position({
                "strategy": strat,
                "qty":      1,
                "entry":    lmt_price,
                "current":  lmt_price,
                "side":     bag_action,
                "oid":      oid,
                "legs":     legs,
                "status":   "미체결",   # 체결 후 "체결완료"로 갱신
            })
    except Exception as e:
        self._bag_session = None
        self._log(f"❌ BAG 주문 오류: {e}")