"""
combo_order_whatif.py — whatIf 증거금 조회 콜백 & 전송 로직
────────────────────────────────────────────────────────────
포함:
  _on_whatif_acct_value  — 계좌 요약 수신 (캐시 갱신)
  _on_whatif_acct_end    — 계좌 요약 완료 (fallback용)
  _on_whatif_result      — whatIf 콜백 (BAG 단일 응답)
  _finish_whatif         — 결과 집계 → 패널 갱신
  _send_whatif_order     — whatIf=True 주문 전송 진입점

v3.1 개선:
  - ★ _on_whatif_acct_value: _cached_available_funds / _acct_fetched_once
    동시 갱신 → 로컬 모드에서도 실계좌 잔고 즉시 반영
  - BAG whatIf 단일 전송 (레그 개별 전송 방식 폐기)
    · conId 캐시 있음 → BAG whatIf 1회 전송 (정확, 빠름)
    · conId 캐시 없음 → 로컬 추정값 즉시 사용 (대기 없음)
  - 타임아웃 5초 → 로컬 추정값 폴백
  - reqAccountSummary: core_contract.py 연결 시 영구 구독
────────────────────────────────────────────────────────────
"""

import time
from PyQt5.QtCore import Qt, QTimer
from combo_order_utils import _calc_required_margin


# ── 계좌 요약 콜백 (core_contract.py 영구 구독 → 자동 갱신) ───

def _on_whatif_acct_value(self, tag: str, value: str, currency: str, account: str):
    """
    bridge.acct_value 수신 → 두 캐시 모두 갱신.

    ★ v3.1: _whatif_acct_cache 뿐 아니라 _cached_available_funds /
             _acct_fetched_once 도 동기화 → 로컬 모드에서도 실잔고 사용.
    """
    try:
        v = float(value)
        cache = getattr(self, '_whatif_acct_cache', {})
        if tag == "AvailableFunds":
            cache["af"] = v
            # ★ 로컬 모드 캐시도 동기화
            self._cached_available_funds = v
            self._acct_fetched_once      = True
        elif tag == "BuyingPower":
            cache["bp"] = v
            # AvailableFunds 없을 때 폴백
            if not cache.get("af"):
                self._cached_available_funds = v
                self._acct_fetched_once      = True
        self._whatif_acct_cache = cache

        # fallback 세션 진행 중이면 버퍼에도 저장
        if getattr(self, '_whatif_session', -1) == -1:
            return
        buf = getattr(self, '_whatif_acct_buf', {})
        if tag == "AvailableFunds":
            buf["af"] = v
        elif tag == "BuyingPower":
            buf["bp"] = v
        self._whatif_acct_buf = buf
    except (ValueError, TypeError):
        pass


def _on_whatif_acct_end(self):
    """fallback: reqAccountSummary(9902) 응답 완료 → send_legs 호출."""
    if getattr(self, '_whatif_session', -1) == -1:
        return
    buf = getattr(self, '_whatif_acct_buf', {})
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
    IB whatIf 콜백.
    BAG 단일 전송: oid 1개, 응답 1~2회 (미확정 → 확정 순서)
    init_after > 0 수신 즉시 _finish_whatif 호출.
    """
    if getattr(self, '_whatif_session', -1) == -1:
        return
    oids = getattr(self, '_whatif_oids', [])
    if oid not in oids:
        return

    buf = getattr(self, '_whatif_buf', {})
    existing = buf.get(oid)

    # 이미 확정값 있는데 미확정 응답이 늦게 오면 무시
    if existing and init_after <= 0 and existing.get("init_after", -1) > 0:
        self._log(f"  oid={oid} 중복 미확정 무시")
        return

    buf[oid] = {
        "init_before":  init_before,
        "init_after":   init_after,
        "maint_before": maint_before,
        "maint_after":  maint_after,
        "commission":   commission,
    }
    self._whatif_buf = buf
    self._log(f"🔍 BAG whatIf oid={oid}: "
              f"initBefore=${init_before:,.2f}  initAfter=${init_after:,.2f}")

    # init_after 확정값 즉시 완료 처리
    if init_after > 0:
        _finish_whatif(self, self._whatif_session)


def _finish_whatif(self, session_id: int):
    if session_id != getattr(self, '_whatif_session', -1):
        return
    # Prevent duplicate on_done if timeout already fired
    if getattr(self, '_whatif_done_called', False):
        return
    self._whatif_done_called  = True
    self._whatif_session      = -1
    self._whatif_in_progress  = False

    buf  = dict(getattr(self, '_whatif_buf',  {}))
    oids = list(getattr(self, '_whatif_oids', []))
    self._whatif_oids = []

    btn = getattr(self, '_btn_check_margin', None)
    if btn:
        btn.setEnabled(True)
        btn.setText("💰 증거금")

    panel     = getattr(self, 'synthetic_panel', None)
    strat     = getattr(self, '_whatif_strat',    "―")
    cost_str  = getattr(self, '_whatif_cost_str', "―")
    available = getattr(self, '_whatif_available', 0.0)
    on_done   = getattr(self, '_whatif_on_done',  None)
    legs_info = getattr(self, '_whatif_legs',     [])

    local_margin = _calc_required_margin(legs_info)

    if not buf:
        required = local_margin
        self._log(f"⚠ whatIf 응답 없음 → 로컬 추정값 사용: ${required:,.2f}")
    else:
        d = next(iter(buf.values()))
        ib_margin = d.get("init_after", 0.0)
        if ib_margin > 0:
            self._log(f"💰 IB BAG whatIf=${ib_margin:,.2f}  로컬추정=${local_margin:,.2f}")
            required = ib_margin
        else:
            required = local_margin
            self._log(f"⚠ IB whatIf 값 미확정 → 로컬 추정값 사용: ${required:,.2f}")

    self._log(f"💰 최종: 필요=${required:,.2f}  가용=${available:,.2f}")
    if panel:
        panel.update_margin(available=available, required=required,
                            strategy=strat, cost=cost_str)
    if on_done:
        on_done(available, required, available >= required if required > 0 else True)


# ── whatIf 주문 전송 ───────────────────────────────────────────

def _send_whatif_order(self, legs: list, strat: str, cost_str: str, on_done=None):
    """
    IB 서버 증거금 조회.

    [conId 캐시 있음]
      BAG whatIf=True 1회 전송 → 응답 1개 대기 (타임아웃 5초)
      타임아웃 시 로컬 추정값으로 자동 폴백

    [conId 캐시 없음]
      로컬 추정값 즉시 사용 (서버 조회 생략)
    """
    from core_contract import make_opt_contract
    from ibapi.contract import Contract, ComboLeg
    from ibapi.order import Order as IbOrder
    from core import bridge
    from combo_order_bag import _CONID_CACHE, _conid_key

    # ── 중복 요청 방지 ────────────────────────────────────────
    if getattr(self, '_whatif_in_progress', False):
        self._log("⚠ 증거금 조회 진행 중 — 중복 요청 무시")
        return
    self._whatif_in_progress = True

    btn = getattr(self, '_btn_check_margin', None)
    if btn:
        btn.setEnabled(False)
        btn.setText("💰 조회 중...")

    ib     = self.mw.ib
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"

    session_id = int(time.time() * 1000)
    self._whatif_session      = session_id
    self._whatif_buf          = {}
    self._whatif_oids         = []
    self._whatif_on_done      = on_done
    self._whatif_strat        = strat
    self._whatif_cost_str     = cost_str
    self._whatif_legs         = legs
    # Guard: ensures on_done is called exactly once per session
    self._whatif_done_called  = False

    # 브릿지 슬롯 연결 (최초 1회)
    if not getattr(self, '_whatif_slots_connected', False):
        bridge.acct_value.connect(self._on_whatif_acct_value, Qt.QueuedConnection)
        bridge.acct_end.connect(self._on_whatif_acct_end,     Qt.QueuedConnection)
        bridge.whatif_sig.connect(self._on_whatif_result,     Qt.QueuedConnection)
        self._whatif_slots_connected = True

    # ── 가용 증거금: 영구 구독 캐시에서 즉시 사용 ────────────
    cache = getattr(self, '_whatif_acct_cache', {})
    available = cache.get("af") or cache.get("bp") or 0.0
    self._whatif_available = available
    if available > 0:
        self._log(f"💰 가용 증거금: ${available:,.2f}")
    else:
        self._log("⚠ 가용 증거금 미조회 — 연결 후 잠시 후 다시 시도하세요")

    # ── conId 캐시 확인 ───────────────────────────────────────
    bag_sym = symbol.replace("SPXW", "SPX")
    conids  = {}
    for i, leg in enumerate(legs):
        key = _conid_key(bag_sym, leg["cp"], leg["strike"], leg["expiry"])
        if key in _CONID_CACHE:
            conids[i] = _CONID_CACHE[key]

    all_cached = (len(conids) == len(legs))

    # ── [conId 캐시 없음] 로컬 추정값 즉시 사용 ──────────────
    if not all_cached:
        local_margin = _calc_required_margin(legs)
        self._whatif_session     = -1
        self._whatif_in_progress = False
        if btn:
            btn.setEnabled(True)
            btn.setText("💰 증거금")
        missing = [i+1 for i in range(len(legs)) if i not in conids]
        self._log(
            f"ℹ conId 캐시 없음 (레그 {missing}) → 로컬 추정값 사용: ${local_margin:,.2f}"
        )
        self._log(
            f"  ※ 합성 주문 실행 후 conId가 캐시에 저장됩니다."
            f"  다음 증거금 조회부터 IB 서버(BAG whatIf) 방식이 자동 적용됩니다."
        )
        panel = getattr(self, 'synthetic_panel', None)
        if panel:
            panel.update_margin(available=available, required=local_margin,
                                strategy=strat, cost=cost_str)
        if on_done:
            margin_ok = available >= local_margin if local_margin > 0 else True
            on_done(available, local_margin, margin_ok)
        return

    # ── [conId 캐시 있음] BAG whatIf 1회 전송 ────────────────
    self._log(f"💰 BAG whatIf 조회 중... (레그 {len(legs)}개, conId 캐시 사용)")

    bag          = Contract()
    bag.symbol   = bag_sym
    bag.secType  = "BAG"
    bag.currency = "USD"
    bag.exchange = "SMART"

    combo_legs = []
    for i, leg in enumerate(legs):
        cl          = ComboLeg()
        cl.conId    = conids[i]
        cl.ratio    = int(float(leg["qty"]))
        cl.action   = leg["dir"]
        cl.exchange = "SMART"
        combo_legs.append(cl)
        self._log(f"  레그{i+1}: {leg['dir']} {leg['cp']} "
                  f"{int(leg['strike'])}  conId={conids[i]}")
    bag.comboLegs = combo_legs

    # lmtPrice 계산
    buy_total  = sum(float(lg.get("prem") or 0) * int(float(lg.get("qty", 1)))
                     for lg in legs if lg["dir"] == "BUY")
    sell_total = sum(float(lg.get("prem") or 0) * int(float(lg.get("qty", 1)))
                     for lg in legs if lg["dir"] == "SELL")
    net        = round(buy_total - sell_total, 2)
    lmt_price  = round(abs(net), 2) or 0.01
    bag_action = "BUY" if net >= 0 else "SELL"

    oid = ib.get_next_id()
    if oid is None:
        self._whatif_session     = -1
        self._whatif_in_progress = False
        if btn:
            btn.setEnabled(True); btn.setText("💰 증거금")
        return self._log("❌ nextOrderId 없음")

    self._whatif_oids = [oid]

    ibord               = IbOrder()
    ibord.action        = bag_action
    ibord.orderType     = "LMT"
    ibord.totalQuantity = 1
    ibord.lmtPrice      = lmt_price
    ibord.tif           = "DAY"
    ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False
    ibord.whatIf        = True

    try:
        ib.placeOrder(oid, bag, ibord)
        self._log(f"🔍 BAG whatIf 전송: OID={oid}  {bag_action} ${lmt_price:.2f}")
    except Exception as e:
        self._whatif_session     = -1
        self._whatif_in_progress = False
        if btn:
            btn.setEnabled(True); btn.setText("💰 증거금")
        return self._log(f"❌ BAG whatIf 전송 오류: {e}")

    # ── Timeout: 5s → fallback to local estimate ──────────────
    def _check_timeout(sid):
        if sid != getattr(self, '_whatif_session', -1):
            return   # already completed normally
        # Prevent duplicate if _finish_whatif already ran
        if getattr(self, '_whatif_done_called', False):
            return
        self._whatif_done_called  = True
        local_margin = _calc_required_margin(legs)
        self._whatif_session      = -1
        self._whatif_in_progress  = False
        self._whatif_oids         = []
        if btn:
            btn.setEnabled(True); btn.setText("💰 증거금")
        self._log(
            f"⚠ BAG whatIf 타임아웃 (5초) → 로컬 추정값 사용: ${local_margin:,.2f}"
        )
        panel = getattr(self, 'synthetic_panel', None)
        if panel:
            panel.update_margin(available=self._whatif_available,
                                required=local_margin,
                                strategy=strat, cost=cost_str)
        if on_done:
            avail = self._whatif_available
            margin_ok = avail >= local_margin if local_margin > 0 else True
            on_done(avail, local_margin, margin_ok)

    QTimer.singleShot(5_000, lambda: _check_timeout(session_id))