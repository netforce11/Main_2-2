"""
combo_order_logic.py — 합성 주문 · whatIf 증거금 · BAG 주문 로직
──────────────────────────────────────────────────────────────────
포함:
  _on_synthetic_order   — ⚡ 합성 주문 버튼 핸들러
  _on_check_margin      — 💰 증거금 조회 버튼 핸들러
  _on_whatif_*          — whatIf 콜백 슬롯 (bridge 시그널 수신)
  _finish_whatif        — whatIf 결과 처리
  _send_whatif_order    — whatIf=True 주문 전송
  _place_combo_legs     — BAG 주문 진입점
  _place_bag_with_conids— conId 조회 → BAG placeOrder
  _parse_legs_from_table— tbl_legs 파싱
  _parse_expiry_display — MM/DD → YYYYMMDD 복원
  _calc_required_margin — 전략 구조 기반 증거금 추정
──────────────────────────────────────────────────────────────────
"""

import time
import re
from datetime import date

from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt, QTimer
from combo_order_utils import _parse_legs_from_table, _parse_expiry_display, _calc_required_margin


# ── 공개 핸들러 ────────────────────────────────────────────────

def _on_synthetic_order(self):
    """⚡ 합성 주문 버튼 핸들러."""
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return self._log("⚠ synthetic_panel 없음")
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")

    strat    = self.combo_strat.currentText()
    cost_str = self._kpi_widgets.get('cost', type('', (), {'text': lambda self: '―'})()).text() \
               if hasattr(self, '_kpi_widgets') else "―"
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가/만기가 입력되지 않았습니다.\n체인 클릭 또는 수동 입력 후 다시 시도하세요.")

    def _on_margin_checked(available, required, margin_ok):
        if not margin_ok:
            return QMessageBox.warning(self, "증거금 부족",
                f"가용: ${available:,.2f}  /  필요: ${required:,.2f}\n증거금 부족으로 주문 취소.")
        leg_summary = "\n".join(
            f"  레그{i+1}: {lg['dir']} {lg['qty']}계약  {lg['cp']} {lg['strike']}"
            f"  @${lg['prem']}  만기:{lg['expiry']}"
            for i, lg in enumerate(legs))
        reply = QMessageBox.question(self, "⚡ 합성 주문 확인",
            f"전략: {strat}\n순비용: {cost_str}\n\n{leg_summary}\n\n"
            f"가용 증거금: ${available:,.2f}\n필요 증거금: ${required:,.2f}\n\n"
            f"총 {len(legs)}개 레그를 주문하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            _place_combo_legs(self, legs, strat)

    _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)


def _on_check_margin(self):
    """💰 증거금 조회 버튼 핸들러."""
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
    strat    = self.combo_strat.currentText()
    cost_str = self._kpi_widgets.get('cost', type('', (), {'text': lambda self: '―'})()).text() \
               if hasattr(self, '_kpi_widgets') else "―"
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가·프리미엄·만기를 입력한 후 다시 시도하세요.")
    self._log("💰 whatIf 증거금 조회 요청 중...")
    _send_whatif_order(self, legs, strat, cost_str, on_done=None)


# ── whatIf 콜백 슬롯 (RightPanelMixin에 주입) ─────────────────

def _on_whatif_acct_value(self, tag: str, value: str, currency: str, account: str):
    if self._whatif_session == -1:
        return
    try:
        v = float(value)
        buf = getattr(self, '_whatif_acct_buf', {})
        if tag == "AvailableFunds": buf["af"] = v
        elif tag == "BuyingPower":  buf["bp"] = v
        self._whatif_acct_buf = buf
    except (ValueError, TypeError):
        pass


def _on_whatif_acct_end(self):
    if self._whatif_session == -1:
        return
    buf = getattr(self, '_whatif_acct_buf', {})
    available = buf.get("af") or buf.get("bp") or 0.0
    self._whatif_available = available
    self._log(f"💰 가용 증거금: ${available:,.2f}")
    send_fn = getattr(self, '_whatif_send_legs', None)
    if send_fn:
        send_fn()


def _on_whatif_result(self, oid, init_before, init_after,
                      maint_before, maint_after, commission):
    """
    IB whatIf 콜백. 레그당 2회 이상 발생:
      1번째: initBefore=0, initAfter=0  → 미확정, 무시
      2번째: initBefore=X, initAfter=실제값 → 유효 (저장)
    이미 유효값이 저장된 oid 에 0이 다시 오면 덮어쓰지 않음.
    """
    oids = getattr(self, '_whatif_oids', [])
    if oid not in oids:
        return

    legs_info = getattr(self, '_whatif_legs', [])
    leg_idx   = oids.index(oid)
    leg_dir   = legs_info[leg_idx]["dir"] if 0 <= leg_idx < len(legs_info) else "BUY"

    buf      = getattr(self, '_whatif_buf', {})
    existing = buf.get(oid)

    if leg_dir == "SELL":
        # SELL: initAfter=0 & initBefore=0 → 미확정 콜백 → 무시
        if init_after <= 0 and init_before <= 0:
            self._log(f"  oid={oid} SELL 미확정 무시")
            return
    else:
        # BUY: 이미 유효값(>0) 저장 후 0 덮어쓰기 시도 → 무시
        if existing and init_after <= 0 and existing.get("init_after", -1) > 0:
            self._log(f"  oid={oid} BUY 중복 0 무시")
            return

    buf[oid] = {"init_before": init_before, "init_after": init_after,
                "maint_before": maint_before, "maint_after": maint_after,
                "commission": commission}
    self._whatif_buf = buf
    self._log(f"🔍 whatIf oid={oid} [{leg_dir}]: "
              f"initBefore=${init_before:,.2f}  initAfter=${init_after:,.2f}")

    if len(buf) >= len(oids):
        self._finish_whatif(self._whatif_session)


def _finish_whatif(self, session_id: int):
    if session_id != getattr(self, '_whatif_session', -1):
        return
    self._whatif_session = -1

    buf      = getattr(self, '_whatif_buf', {})
    oids     = getattr(self, '_whatif_oids', [])
    panel    = getattr(self, 'synthetic_panel', None)
    strat    = getattr(self, '_whatif_strat',    "―")
    cost_str = getattr(self, '_whatif_cost_str', "―")
    available= getattr(self, '_whatif_available', 0.0)
    on_done  = getattr(self, '_whatif_on_done',  None)
    legs_info= getattr(self, '_whatif_legs',     [])

    if not buf:
        return self._log("⚠ whatIf 결과 없음")

    # ── 증거금 계산: 전략 유형에 따라 다르게 처리 ─────────────
    # 방법1 (IB 직접값): 마지막 SELL 레그의 initAfter 가 포지션 전체 증거금
    # IB BAG 주문 whatIf 는 레그 순서 누적으로 반환하므로
    # → SELL 레그 중 가장 큰 initAfter 를 실제 필요 증거금으로 사용
    sell_afters = []
    for oid, d in buf.items():
        idx = oids.index(oid) if oid in oids else -1
        leg_dir = legs_info[idx]["dir"] if 0 <= idx < len(legs_info) else "BUY"
        after = d.get("init_after", 0.0)
        if leg_dir == "SELL" and after > 0:
            sell_afters.append(after)

    if sell_afters:
        required = max(sell_afters)
        self._log(f"💰 IB whatIf 기반 필요증거금=${required:,.2f} (SELL 레그 max initAfter)")
    else:
        # SELL 레그 유효값 없음 → 전략 구조 기반 추정값 사용
        required = _calc_required_margin(legs_info)
        self._log(f"💰 구조 기반 추정 증거금=${required:,.2f}")

    self._log(f"💰 최종: 필요증거금=${required:,.2f}  가용=${available:,.2f}")

    if panel:
        panel.update_margin(available=available, required=required,
                            strategy=strat, cost=cost_str)
    if on_done:
        on_done(available, required, available >= required if required > 0 else True)


# ── whatIf 주문 전송 ──────────────────────────────────────────

def _send_whatif_order(self, legs: list, strat: str, cost_str: str, on_done=None):
    """whatIf=True 주문으로 IB 서버 증거금 계산."""
    from core_contract import make_opt_contract
    from ibapi.order import Order as IbOrder
    from core import bridge

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"

    session_id = int(time.time() * 1000)
    self._whatif_session   = session_id
    self._whatif_buf       = {}
    self._whatif_oids      = []
    self._whatif_available = 0.0
    self._whatif_on_done   = on_done
    self._whatif_strat     = strat
    self._whatif_cost_str  = cost_str
    self._whatif_legs      = legs

    if not getattr(self, '_whatif_slots_connected', False):
        bridge.acct_value.connect(self._on_whatif_acct_value, Qt.QueuedConnection)
        bridge.acct_end.connect(self._on_whatif_acct_end,     Qt.QueuedConnection)
        bridge.whatif_sig.connect(self._on_whatif_result,     Qt.QueuedConnection)
        self._whatif_slots_connected = True

    self._whatif_acct_buf = {}
    try:
        ib.reqAccountSummary(9902, "All", "AvailableFunds,BuyingPower")
        self._log("🔍 가용 증거금 조회 중...")
    except Exception as e:
        return self._log(f"❌ reqAccountSummary 오류: {e}")

    def _send_legs():
        self._whatif_buf = {}; self._whatif_oids = []
        for i, leg in enumerate(legs):
            oid = ib.get_next_id()
            if oid is None: return self._log("❌ nextOrderId 없음")
            self._whatif_oids.append(oid)
            try:
                contract = make_opt_contract(symbol=symbol, strike=leg["strike"],
                                             right=leg["cp"], expiry=leg["expiry"])
                ibord = IbOrder()
                ibord.action = leg["dir"]; ibord.orderType = "LMT"
                ibord.totalQuantity = leg["qty"]
                ibord.lmtPrice = float(leg["prem"]) if leg["prem"] else 0.0
                ibord.tif = "DAY"; ibord.eTradeOnly = False
                ibord.firmQuoteOnly = False; ibord.whatIf = True
                ib.placeOrder(oid, contract, ibord)
                self._log(f"🔍 whatIf 레그{i+1}: {leg['dir']} {leg['qty']}  "
                          f"{leg['cp']} {int(leg['strike'])}  만기:{leg['expiry']}")
            except Exception as e:
                self._log(f"❌ whatIf 레그{i+1} 오류: {e}")

    self._whatif_send_legs = _send_legs

    def _check_timeout(sid):
        if sid != self._whatif_session: return
        if not self._whatif_buf:
            self._log("⚠ whatIf 타임아웃")
            self._whatif_session = -1
        elif len(self._whatif_buf) < len(self._whatif_oids):
            self._log("⚠ whatIf 일부 타임아웃 — 수신분으로 계산")
            self._finish_whatif(sid)
    QTimer.singleShot(10000, lambda: _check_timeout(session_id))


# ── BAG 주문 ────────────────────────────────────────────────────

def _place_combo_legs(self, legs: list, strat: str):
    """BAG(Combo) 계약 주문 진입점."""
    try:
        from core_contract import make_opt_contract
        from ibapi.contract import Contract, ComboLeg
    except ImportError as e:
        return QMessageBox.critical(self, "오류", f"모듈 import 실패: {e}")

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = (sym_w.text().strip().upper() if sym_w else "SPX")

    bag = Contract()
    bag.symbol = symbol.replace("SPXW", "SPX")
    bag.secType = "BAG"; bag.currency = "USD"; bag.exchange = "SMART"

    combo_legs = []
    for leg in legs:
        opt_contract = make_opt_contract(symbol=symbol, strike=leg["strike"],
                                         right=leg["cp"], expiry=leg["expiry"])
        cl = ComboLeg()
        cl.conId = 0; cl.ratio = int(leg["qty"])
        cl.action = leg["dir"]; cl.exchange = "SMART"
        combo_legs.append((cl, opt_contract))

    _place_bag_with_conids(self, bag, combo_legs, legs, strat)


def _place_bag_with_conids(self, bag, combo_legs, legs, strat):
    """conId 조회 → BAG placeOrder."""
    from ibapi.order import Order as IbOrder

    ib    = self.mw.ib
    total = len(combo_legs)
    resolved = {}
    base_rid  = 9910

    def _on_cd(reqId, contractDetails):
        idx = reqId - base_rid
        if 0 <= idx < total:
            resolved[idx] = contractDetails.contract.conId

    def _on_cd_end(reqId):
        idx = reqId - base_rid
        if idx not in resolved: resolved[idx] = 0
        if len(resolved) >= total:
            QTimer.singleShot(0, _send_bag)

    ib._orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
    ib._orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)
    ib.contractDetails    = _on_cd
    ib.contractDetailsEnd = _on_cd_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        try:
            ib.reqContractDetails(base_rid + i, opt_contract)
            self._log(f"🔍 conId 조회: 레그{i+1} "
                      f"{opt_contract.right} {int(opt_contract.strike)}")
        except Exception as e:
            self._log(f"❌ reqContractDetails 레그{i+1}: {e}")
            resolved[i] = 0

    def _on_timeout():
        for i in range(total):
            if i not in resolved: resolved[i] = 0
        _send_bag()
    QTimer.singleShot(10000, _on_timeout)

    def _send_bag():
        try:
            ib.contractDetails    = ib._orig_cd
            ib.contractDetailsEnd = ib._orig_cd_end
        except Exception:
            pass

        for i, (cl, _) in enumerate(combo_legs):
            cl.conId = resolved.get(i, 0)
            self._log(f"  레그{i+1} conId={cl.conId}  {legs[i]['dir']} {legs[i]['cp']} {int(legs[i]['strike'])}")
        bag.comboLegs = [cl for cl, _ in combo_legs]

        # ── BAG lmtPrice 계산 ────────────────────────────────────
        # net = Σ(BUY 레그 프리미엄 × 수량) - Σ(SELL 레그 프리미엄 × 수량)
        # IB BAG 규칙:
        #   데빗 전략 (net > 0): action=BUY,  lmtPrice=net (지불할 최대 금액)
        #   크레딧 전략(net < 0): action=SELL, lmtPrice=|net| (수취할 최소 금액)
        #   스프레드 차액이 주문가격 — 개별 레그 프리미엄 합계가 아님
        buy_total  = sum(float(lg.get("prem",0) or 0) * int(lg.get("qty",1))
                         for lg in legs if lg["dir"] == "BUY")
        sell_total = sum(float(lg.get("prem",0) or 0) * int(lg.get("qty",1))
                         for lg in legs if lg["dir"] == "SELL")
        net        = round(buy_total - sell_total, 2)   # 양수=데빗, 음수=크레딧
        lmt_price  = round(abs(net), 2)
        bag_action = "BUY" if net >= 0 else "SELL"
        order_type_str = f"{'데빗' if net >= 0 else '크레딧'} ${lmt_price:.2f}"

        oid = ib.get_next_id()
        if oid is None: return self._log("❌ nextOrderId 없음")

        ibord = IbOrder()
        ibord.action = bag_action; ibord.orderType = "LMT"
        ibord.totalQuantity = 1; ibord.lmtPrice = lmt_price
        ibord.tif = "DAY"; ibord.eTradeOnly = False
        ibord.firmQuoteOnly = False; ibord.transmit = True

        try:
            ib.placeOrder(oid, bag, ibord)
            self._log(f"⚡ BAG 주문 전송: OID={oid}  {order_type_str}  레그{total}개")
            self._log(f"   BUY 합계=${buy_total:.2f}  SELL 합계=${sell_total:.2f}  net=${net:+.2f}")
            panel = getattr(self, 'synthetic_panel', None)
            if panel:
                panel.add_position({
                    "strategy": strat, "qty": 1,
                    "entry": lmt_price, "current": lmt_price,
                    "side": bag_action,
                })
        except Exception as e:
            self._log(f"❌ BAG 주문 오류: {e}")