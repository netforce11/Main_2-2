"""
combo_order_whatif.py — whatIf 증거금 조회 콜백 & 전송 로직
────────────────────────────────────────────────────────────
포함:
  _on_whatif_acct_value  — 계좌 요약 수신
  _on_whatif_acct_end    — 계좌 요약 완료 → 레그 전송
  _on_whatif_result      — whatIf 콜백 (레그당 2회 필터링)
  _finish_whatif         — 결과 집계 → 패널 갱신
  _send_whatif_order     — whatIf=True 주문 전송 진입점
────────────────────────────────────────────────────────────
"""

import time
from PyQt5.QtCore import Qt, QTimer
from combo_order_utils import _calc_required_margin


# ── 계좌 요약 콜백 ─────────────────────────────────────────────

def _on_whatif_acct_value(self, tag: str, value: str, currency: str, account: str):
    if self._whatif_session == -1:
        return
    try:
        v   = float(value)
        buf = getattr(self, '_whatif_acct_buf', {})
        if tag == "AvailableFunds":
            buf["af"] = v
        elif tag == "BuyingPower":
            buf["bp"] = v
        self._whatif_acct_buf = buf
    except (ValueError, TypeError):
        pass


def _on_whatif_acct_end(self):
    if self._whatif_session == -1:
        return
    buf       = getattr(self, '_whatif_acct_buf', {})
    available = buf.get("af") or buf.get("bp") or 0.0
    self._whatif_available = available
    self._log(f"💰 가용 증거금: ${available:,.2f}")
    send_fn = getattr(self, '_whatif_send_legs', None)
    if send_fn:
        send_fn()


# ── whatIf 결과 콜백 ────────────────────────────────────────────

def _on_whatif_result(self, oid, init_before, init_after,
                      maint_before, maint_after, commission):
    """
    IB whatIf 콜백. 레그당 2회 발생:
      1번째: initBefore=0, initAfter=0  → 미확정, 무시
      2번째: initAfter=실제값          → 저장
    """
    oids = getattr(self, '_whatif_oids', [])
    if oid not in oids:
        return

    legs_info = getattr(self, '_whatif_legs', [])
    leg_idx   = oids.index(oid)
    leg_dir   = legs_info[leg_idx]["dir"] if 0 <= leg_idx < len(legs_info) else "BUY"
    buf       = getattr(self, '_whatif_buf', {})
    existing  = buf.get(oid)

    if leg_dir == "SELL":
        if init_after <= 0 and init_before <= 0:
            self._log(f"  oid={oid} SELL 미확정 무시")
            return
    else:
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
        _finish_whatif(self, self._whatif_session)


def _finish_whatif(self, session_id: int):
    if session_id != getattr(self, '_whatif_session', -1):
        return
    self._whatif_session = -1

    buf       = getattr(self, '_whatif_buf', {})
    oids      = getattr(self, '_whatif_oids', [])
    panel     = getattr(self, 'synthetic_panel', None)
    strat     = getattr(self, '_whatif_strat',    "―")
    cost_str  = getattr(self, '_whatif_cost_str', "―")
    available = getattr(self, '_whatif_available', 0.0)
    on_done   = getattr(self, '_whatif_on_done',  None)
    legs_info = getattr(self, '_whatif_legs',     [])

    if not buf:
        return self._log("⚠ whatIf 결과 없음")

    # SELL 레그 max(initAfter) → 필요 증거금
    sell_afters = []
    for oid, d in buf.items():
        idx     = oids.index(oid) if oid in oids else -1
        leg_dir = legs_info[idx]["dir"] if 0 <= idx < len(legs_info) else "BUY"
        after   = d.get("init_after", 0.0)
        if leg_dir == "SELL" and after > 0:
            sell_afters.append(after)

    if sell_afters:
        required = max(sell_afters)
        self._log(f"💰 IB whatIf 기반 증거금=${required:,.2f}")
    else:
        required = _calc_required_margin(legs_info)
        self._log(f"💰 구조 기반 추정 증거금=${required:,.2f}")

    self._log(f"💰 최종: 필요=${required:,.2f}  가용=${available:,.2f}")
    if panel:
        panel.update_margin(available=available, required=required,
                            strategy=strat, cost=cost_str)
    if on_done:
        on_done(available, required, available >= required if required > 0 else True)


# ── whatIf 주문 전송 ───────────────────────────────────────────

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
            if oid is None:
                return self._log("❌ nextOrderId 없음")
            self._whatif_oids.append(oid)
            try:
                contract = make_opt_contract(
                    symbol=symbol, strike=leg["strike"],
                    right=leg["cp"], expiry=leg["expiry"])
                ibord = IbOrder()
                ibord.action        = leg["dir"]; ibord.orderType = "LMT"
                ibord.totalQuantity = leg["qty"]
                ibord.lmtPrice      = float(leg["prem"]) if leg["prem"] else 0.0
                ibord.tif           = "DAY"; ibord.eTradeOnly    = False
                ibord.firmQuoteOnly = False;  ibord.whatIf       = True
                ib.placeOrder(oid, contract, ibord)
                self._log(f"🔍 whatIf 레그{i+1}: {leg['dir']} {leg['qty']}  "
                          f"{leg['cp']} {int(leg['strike'])}  만기:{leg['expiry']}")
            except Exception as e:
                self._log(f"❌ whatIf 레그{i+1} 오류: {e}")

    self._whatif_send_legs = _send_legs

    def _check_timeout(sid):
        if sid != self._whatif_session:
            return
        if not self._whatif_buf:
            self._log("⚠ whatIf 타임아웃")
            self._whatif_session = -1
        elif len(self._whatif_buf) < len(self._whatif_oids):
            self._log("⚠ whatIf 일부 타임아웃 — 수신분으로 계산")
            _finish_whatif(self, sid)
    QTimer.singleShot(10000, lambda: _check_timeout(session_id))
