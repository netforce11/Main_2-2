"""
combo_order_bag.py — BAG(Combo) 주문 전송 로직  v3.5
──────────────────────────────────────────────────────
v3.5 변경:
  [FIX-R] totalQuantity 하드코딩 1 → legs 실제 수량 반영
    · 기존: ibord.totalQuantity = 1 (수량 무관 항상 1계약 주문)
    · 수정: max(leg["qty"] for leg in legs) 로 실제 수량 반영
    · 영향: 체결 직후 잔고 qty 정확히 표시, 파일 저장값도 정확

v3.4 변경:
  [BUG #TICK] 틱 단위 가격 선택 다이얼로그
    · lmtPrice가 정확히 틱 배수(0.05 / 0.10)이면 → 그냥 주문 (기존 동일)
    · 틱 배수가 아니면 → 큰 버튼 2개로 사용자에게 선택 요청
        [ $2.20 내림(floor) ]   [ $2.25 올림(ceil) ]
    · 사용자가 직접 선택 → 선택된 가격으로 기존 확인창 진행
    · 취소 버튼 → 주문 취소
    · 함수: _ask_tick_snap_dialog()

v3.3 변경:
  [BUG #TICK] lmtPrice 틱 스냅 자동 적용 (v3.4에서 선택 방식으로 전환)

v3.2 변경:
  [FIX-J] _pending_lmt_override 지원
    - _do_send_body 최상단에서 self._pending_lmt_override 체크
    - 값이 있으면 NetPriceDisplay / legs 폴백보다 최우선 사용
    - 소비 후 즉시 None 으로 초기화 (다음 신규 주문에 영향 없음)
    - bag_action 은 close_legs[0].dir 로 결정

v3.1 변경 (이전):
  직접입력 가격 우선 반영 (manual mode)
v3.0 변경 (이전):
  BUG #1~#4 수정
──────────────────────────────────────────────────────
Python 3.8 호환
"""

from __future__ import annotations
import math
import json
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from combo_order_chaser import register_chaser
from combo_order_callbacks import connect_order_callbacks


# ══════════════════════════════════════════════════════════════
# [v3.4] 틱 단위 가격 선택 다이얼로그
# ══════════════════════════════════════════════════════════════

def _is_tick_aligned(price: float, tick: float) -> bool:
    """price가 tick의 정확한 배수인지 확인 (부동소수점 오차 허용)."""
    if tick <= 0:
        return True
    remainder = abs(price - round(price / tick) * tick)
    return remainder < tick * 0.001   # 0.1% 오차 허용


def _ask_tick_snap_dialog(parent, price: float, tick: float,
                          bag_action: str) -> float | None:
    """
    [v3.4] 입력 가격이 틱 배수가 아닐 때 사용자에게 선택을 요청하는 다이얼로그.

    Args:
        parent     : QWidget 부모
        price      : 원본 입력 가격 (틱 배수 아님)
        tick       : 틱 사이즈 (0.05 / 0.10 / 0.01)
        bag_action : "BUY" 또는 "SELL"

    Returns:
        선택된 가격 (float) — 사용자가 하나 선택
        None               — 취소
    """
    import math as _m

    inv  = 1.0 / tick
    dec  = max(0, -int(_m.floor(_m.log10(tick)))) if tick < 1 else 0

    price_floor = round(_m.floor(price * inv) / inv, dec)
    price_ceil  = round(_m.ceil(price  * inv) / inv, dec)

    # 최솟값 보정
    price_floor = max(price_floor, tick)
    price_ceil  = max(price_ceil,  tick)

    dlg = QDialog(parent)
    dlg.setWindowTitle("⚠ 주문 가격 조정 필요")
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dlg.setStyleSheet(
        "QDialog { background:#0d1520; color:#ccc; }"
        "QLabel  { border:none; }")
    dlg.setMinimumWidth(400)

    v = QVBoxLayout(dlg)
    v.setContentsMargins(20, 18, 20, 18)
    v.setSpacing(14)

    # ── 안내 문구 ──────────────────────────────────────────
    lbl_warn = QLabel(
        f"입력 가격  <b style='color:#ffd700'>${price:.2f}</b>  은 "
        f"틱 단위(<b style='color:#aaa'>${tick}</b>)가 아닙니다.<br>"
        f"아래 두 가격 중 하나를 선택하세요.")
    lbl_warn.setStyleSheet("color:#ccc; font-size:12px;")
    lbl_warn.setWordWrap(True)
    lbl_warn.setAlignment(Qt.AlignCenter)
    v.addWidget(lbl_warn)

    # ── 버튼 행 ────────────────────────────────────────────
    h = QHBoxLayout()
    h.setSpacing(16)

    def _make_btn(snap_price: float, label_top: str,
                  label_bot: str, color: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(160, 72)
        btn.setFont(QFont("Consolas", 11, QFont.Bold))
        btn.setText(f"${snap_price:.2f}\n{label_top}\n{label_bot}")
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background:#0a1a0a; color:{color};"
            f"  border:2px solid {color}; border-radius:8px;"
            f"  font-size:13px; font-weight:bold;"
            f"  padding:6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background:{color}; color:#000;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background:{color}; color:#000;"
            f"  border:2px solid #fff;"
            f"}}")
        return btn

    # floor 버튼
    btn_floor = _make_btn(
        price_floor,
        "▼ 내림 (floor)",
        "매도 유리" if bag_action == "SELL" else "매수 불리",
        "#4c9fff")

    # ceil 버튼
    btn_ceil = _make_btn(
        price_ceil,
        "▲ 올림 (ceil)",
        "매수 유리" if bag_action == "BUY" else "매도 불리",
        "#4cff4c")

    # 선택된 가격 저장
    _result = [None]

    def _pick(p):
        _result[0] = p
        dlg.accept()

    btn_floor.clicked.connect(lambda: _pick(price_floor))
    btn_ceil.clicked.connect(lambda:  _pick(price_ceil))

    h.addStretch()
    h.addWidget(btn_floor)
    h.addWidget(btn_ceil)
    h.addStretch()
    v.addLayout(h)

    # ── 취소 버튼 ──────────────────────────────────────────
    btn_cancel = QPushButton("취소")
    btn_cancel.setFixedHeight(28)
    btn_cancel.setStyleSheet(
        "QPushButton { background:#1a1a1a; color:#888; "
        "border:1px solid #444; border-radius:4px; font-size:11px; }"
        "QPushButton:hover { background:#333; color:#ccc; }")
    btn_cancel.clicked.connect(dlg.reject)
    v.addWidget(btn_cancel, alignment=Qt.AlignCenter)

    if dlg.exec_() == QDialog.Accepted:
        return _result[0]
    return None


from PyQt5.QtCore import QTimer


# ── conId 캐시 ─────────────────────────────────────────────────
_CONID_CACHE: dict = {}
_CACHE_FILE = Path(__file__).resolve().parent / "data" / "conid_cache.json"


def _load_conid_cache() -> None:
    global _CONID_CACHE
    try:
        if _CACHE_FILE.exists():
            _CONID_CACHE = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CONID_CACHE = {}
    _purge_stale_conid_keys()


def _purge_stale_conid_keys() -> None:
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
        _CACHE_FILE.write_text(json.dumps(_CONID_CACHE, indent=2), encoding="utf-8")
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
    bag.symbol   = symbol.replace("SPXW", "SPX")
    bag.secType  = "BAG"
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

    from core import bridge as _bridge
    _cd_conn = [None, None]

    def _on_cd(reqId, contractDetails):
        if getattr(self, '_bag_session', None) != session: return
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
        if getattr(self, '_bag_session', None) != session: return
        idx = reqId - base_rid
        if 0 <= idx < total and idx not in resolved:
            resolved[idx] = 0
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

    _bridge.contract_details_sig.connect(_on_cd)
    _bridge.contract_details_end_sig.connect(_on_cd_end)
    _cd_conn[0] = _on_cd; _cd_conn[1] = _on_cd_end

    for i, (cl, opt_contract) in enumerate(combo_legs):
        if i in resolved: continue
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
        if getattr(self, '_bag_session', None) != session: return
        _disconnect_cd()
        for i in range(total):
            if i not in resolved:
                resolved[i] = 0
                opt_c = combo_legs[i][1]
                self._log(f"  ⚠ 레그{i+1} conId 타임아웃 10초 — "
                          f"{opt_c.right} {int(opt_c.strike)} "
                          f"{opt_c.lastTradeDateOrContractMonth}")
        _do_send(self, bag, combo_legs, legs, strat, ib, total, resolved, session)

    QTimer.singleShot(10000, _on_timeout)


# ══════════════════════════════════════════════════════════════
# 주문 전송
# ══════════════════════════════════════════════════════════════

def _do_send(self, bag, combo_legs: list, legs: list, strat: str,
             ib, total: int, resolved: dict, session: int) -> None:
    """중복 호출 방지 lock → _do_send_body() 호출."""
    if getattr(self, '_bag_session', None) != session:
        return
    lock_key = f'_do_send_lock_{session}'
    if getattr(self, lock_key, False):
        return
    setattr(self, lock_key, True)
    try:
        _do_send_body(self, bag, combo_legs, legs, strat, ib, total, resolved, session)
    finally:
        try:
            delattr(self, lock_key)
        except AttributeError:
            pass


def _do_send_body(self, bag, combo_legs: list, legs: list, strat: str,
                  ib, total: int, resolved: dict, session: int) -> None:
    """
    실제 주문 전송 본체.
    conId 세팅 → zero_legs 체크 → lmtPrice 계산 → 확인창 → placeOrder.

    [FIX-J] _pending_lmt_override 최우선 처리
      청산 지정가 주문 시 NetPriceDisplay 를 우회하고
      _place_combo_legs_lmt 에서 세팅한 가격을 직접 사용.
    """
    # ── conId 세팅 ──────────────────────────────────────────
    for i, (cl, _) in enumerate(combo_legs):
        cl.conId = resolved.get(i, 0)
        self._log(
            f"  레그{i+1} conId={cl.conId}  "
            f"{legs[i]['dir']} {legs[i]['cp']} {int(legs[i]['strike'])}")
    bag.comboLegs = [cl for cl, _ in combo_legs]

    # ── conId=0 레그 차단 ────────────────────────────────────
    zero_legs = [i + 1 for i, (cl, _) in enumerate(combo_legs) if cl.conId == 0]
    if zero_legs:
        self._bag_session = None
        self._pending_lmt_override = None   # [FIX-J] override 정리
        self._log(f"❌ 주문 취소: 레그 {zero_legs} conId 조회 실패 (타임아웃) — "
                  f"체인 동기화 후 다시 시도하세요")
        QMessageBox.warning(
            self, "주문 오류",
            f"레그 {zero_legs}의 conId 조회가 타임아웃됐습니다.\n\n"
            f"복합전략 탭 좌측 '↺ 즉시 동기화' 버튼을 누른 후\n"
            f"잠시 기다렸다가 다시 시도하세요.")
        return

    # ── [FIX-J] 청산 지정가 override 최우선 처리 ────────────
    override_lmt = getattr(self, '_pending_lmt_override', None)
    if override_lmt is not None:
        lmt_price               = round(float(override_lmt), 2)
        bag_action              = legs[0]["dir"] if legs else "SELL"
        is_manual_price         = True
        self._pending_lmt_override = None
        self._log(f"📌 지정가 청산 override: ${lmt_price:.2f}  방향:{bag_action}")
        buy_total = sell_total = 0.0
        net       = -lmt_price if bag_action == "SELL" else lmt_price

    else:
        # ── lmtPrice 계산 (v3.1 기존 로직) ────────────────────
        buy_total  = sum(
            float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
            for lg in legs if lg["dir"] == "BUY")
        sell_total = sum(
            float(lg.get("prem", 0) or 0) * int(float(lg.get("qty", 1)))
            for lg in legs if lg["dir"] == "SELL")
        net = round(buy_total - sell_total, 2)

        is_manual_price = False
        display = getattr(self, 'net_price_display', None)

        if display is not None:
            params = display.get_bag_params()
            if params.get("invalid", False):
                self._bag_session = None
                self._log("❌ 주문 취소: 직접입력 모드에서 가격이 입력되지 않았습니다.")
                QMessageBox.warning(
                    self, "가격 미입력",
                    "직접입력 모드에서 스프레드 가격을 입력해주세요.\n\n"
                    "가격 입력 후 합성주문 버튼을 다시 누르세요.")
                return
            lmt_price       = params["lmt_price"]
            bag_action      = params["action"]
            is_manual_price = params.get("manual", False)
            net = lmt_price if bag_action == "BUY" else -lmt_price
            if not is_manual_price and lmt_price == 0.0:
                try:
                    from combo_ui_leg_panel import _recalc_net_price
                    ui_price  = _recalc_net_price(self)
                    lmt_price = round(abs(float(ui_price)), 2) if ui_price else round(abs(net), 2)
                except Exception:
                    lmt_price = round(abs(net), 2)
                bag_action = "BUY" if net >= 0 else "SELL"
        else:
            try:
                from combo_ui_leg_panel import _recalc_net_price
                ui_price  = _recalc_net_price(self)
                lmt_price = round(abs(float(ui_price)), 2) if ui_price else round(abs(net), 2)
            except Exception:
                lmt_price = round(abs(net), 2)
            bag_action = "BUY" if net >= 0 else "SELL"

        if lmt_price <= 0.0:
            lmt_price = 0.01

    # ── [v3.4] 틱 단위 확인 → 비배수면 선택 다이얼로그 ──────────
    try:
        from combo_order_chaser import _get_tick_size
        _tick_size = _get_tick_size(lmt_price)

        if not _is_tick_aligned(lmt_price, _tick_size):
            # 틱 배수가 아님 → 사용자에게 floor / ceil 선택 요청
            self._log(
                f"   ⚠ 입력가격 ${lmt_price:.2f}이 틱 단위(${_tick_size}) 아님 "
                f"→ 선택 다이얼로그 표시")
            chosen = _ask_tick_snap_dialog(self, lmt_price, _tick_size, bag_action)
            if chosen is None:
                # 취소
                self._bag_session = None
                self._log("   주문 취소 (틱 가격 선택 취소)")
                return
            self._log(f"   틱 가격 선택: ${lmt_price:.2f} → ${chosen:.2f}")
            lmt_price = chosen
        else:
            self._log(f"   틱 단위 확인: ${lmt_price:.2f} ✅ (틱={_tick_size})")

    except Exception as _e:
        self._log(f"   ⚠ 틱 단위 확인 실패 ({_e}) — 원본 가격 사용: ${lmt_price:.2f}")

    type_label   = "데빗 (지불)" if bag_action == "BUY" else "크레딧 (수취)"
    price_source = " [직접입력]" if is_manual_price else " [자동/Mid]"

    from combo_order_logic import _get_session_info
    after_hours, session_label, tif, outside_rth = _get_session_info()

    # ── [v3.4] 확인 다이얼로그 제거 ─────────────────────────────
    # 틱 선택 다이얼로그에서 이미 사용자가 가격을 직접 선택했으므로
    # 추가 확인창 없이 바로 주문 전송.
    # (정확한 틱 배수로 입력된 경우도 동일하게 바로 전송)
    self._log(
        f"📤 합성주문 전송 준비: {strat}  "
        f"${lmt_price:.2f}{price_source}  "
        f"TIF:{tif}  세션:{session_label}"
    )

    # ── OID 발급 ────────────────────────────────────────────
    oid = ib.get_next_id()
    if oid is None:
        self._bag_session = None
        self._log("❌ nextOrderId 없음")
        return

    # ── 주문 객체 ────────────────────────────────────────────
    from ibapi.order import Order as IbOrder
    # [FIX-R] totalQuantity: 기존 하드코딩 1 → legs 에서 실제 수량 읽어서 반영
    # BAG 주문의 totalQuantity = 레그들 중 가장 큰 qty
    # (스프레드는 모든 레그 qty 동일, 레이쇼 스프레드는 max가 기준)
    _bag_qty = max((int(float(lg.get("qty", 1))) for lg in legs), default=1)
    ibord = IbOrder()
    ibord.action        = bag_action
    ibord.orderType     = "LMT"
    ibord.totalQuantity = _bag_qty
    ibord.lmtPrice      = lmt_price
    ibord.tif           = tif
    ibord.outsideRth    = outside_rth
    ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False
    ibord.transmit      = True

    # ── placeOrder ──────────────────────────────────────────
    try:
        ib.placeOrder(oid, bag, ibord)
        self._log(
            f"⚡ BAG 주문: OID={oid}  {type_label} ${lmt_price:.2f}{price_source}"
            f"  TIF:{tif}  outsideRth:{outside_rth}  레그{total}개  qty={ibord.totalQuantity}")
        self._log(
            f"   BUY=${buy_total:.2f}  SELL=${sell_total:.2f}  net=${net:+.2f}  세션:{session_label}")

        self._chaser_bag_contract = bag
        self._chaser_bag_order    = ibord
        self._chaser_current_oid  = oid
        self._chaser_oid          = oid

        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)

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

        register_chaser(
            self, oid=oid, price=lmt_price,
            action=bag_action, qty=int(ibord.totalQuantity))

        # [FIX-W3] _is_close_order 정의 — 미정의로 NameError 발생하던 버그 수정
        # _close_oid_set 에 등록된 OID 면 청산 주문, 아니면 신규 주문
        _is_close_order = (oid in getattr(self, '_close_oid_set', set()))

        # [TG-3] 선주문 감시 등록 — 청산 주문이 아닐 때만
        # [FIX-W1] bag_contract / qty 직접 전달
        #   Chaser OFF 기본값 상태에서도 정정주문이 정상 전송되도록
        #   bag 컨트랙트와 수량을 SpecialFillWatcher 에 직접 저장
        if not _is_close_order:
            try:
                from combo_order_special_condition import SpecialFillWatcher
                SpecialFillWatcher.get().watch(
                    self, oid, lmt_price, bag_action, legs, strat,
                    bag_contract=bag,                  # [FIX-W1]
                    qty=int(ibord.totalQuantity))      # [FIX-W1]
            except Exception as _e:
                self._log(f"⚠ SpecialFillWatcher 등록 실패: {_e}")

        def _verify_order(check_oid=oid):
            from combo_order_open import on_open_orders
            def _check_cache():
                orders = getattr(self, '_cached_open_orders', [])
                oids   = [o.get('oid') for o in orders]
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