"""
combo_order_bag.py — BAG(Combo) 주문 전송 로직  v3.8
──────────────────────────────────────────────────────
v3.8 변경 (bug fix):
  [BUG-BAG-1 FIX] XSP 종목 $0.01 틱 예외 누락 수정
    · _do_send_body(): _get_tick_size(lmt_price) → _get_tick_size(lmt_price, bag.symbol)
    · _sleep_place_sell_order(): 동일하게 bag.symbol 전달
    · XSP 합성 매수/매도 주문 시 0.01 단위가 아닌 가격에도
      불필요한 "가격 조정 팝업"이 뜨던 문제 해결

이하는 v3.7 기준 변경 없음
──────────────────────────────────────────────────────
v3.7 변경 (bug fix):
  [FIX-CHASER-CLOSE] register_chaser() 호출 시 is_close 파라미터 전달
    · strat.startswith("청산:") 이면 is_close=True
    · 청산 주문의 자동 Chaser 추격 방지

  [FIX-OID1] _chaser_current_oid 동기화
    · placeOrder 성공 시 _chaser_current_oid = oid 로 명시 세팅

  [FIX-SLEEP-CHASER] _sleep_place_sell_order 에서도 is_close=True

이하는 v3.6 기준 변경 없음 (틱 다이얼로그, conId 캐시 등 동일)
──────────────────────────────────────────────────────
"""

from __future__ import annotations
import math
import json
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from combo_order_chaser import register_chaser
from combo_order_callbacks import connect_order_callbacks


# ══════════════════════════════════════════════════════════════
# 틱 단위 가격 선택 다이얼로그 (v3.4 그대로)
# ══════════════════════════════════════════════════════════════

def _is_tick_aligned(price: float, tick: float) -> bool:
    if tick <= 0:
        return True
    remainder = abs(price - round(price / tick) * tick)
    return remainder < tick * 0.001


def _ask_tick_snap_dialog(parent, price: float, tick: float,
                          bag_action: str) -> float | None:
    import math as _m
    inv  = 1.0 / tick
    dec  = max(0, -int(_m.floor(_m.log10(tick)))) if tick < 1 else 0
    price_floor = round(_m.floor(price * inv) / inv, dec)
    price_ceil  = round(_m.ceil(price  * inv) / inv, dec)
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

    lbl_warn = QLabel(
        f"입력 가격  <b style='color:#ffd700'>${price:.2f}</b>  은 "
        f"틱 단위(<b style='color:#aaa'>${tick}</b>)가 아닙니다.<br>"
        f"아래 두 가격 중 하나를 선택하세요.")
    lbl_warn.setStyleSheet("color:#ccc; font-size:12px;")
    lbl_warn.setWordWrap(True)
    lbl_warn.setAlignment(Qt.AlignCenter)
    v.addWidget(lbl_warn)

    h = QHBoxLayout()
    h.setSpacing(16)

    def _make_btn(snap_price, label_top, label_bot, color):
        btn = QPushButton()
        btn.setFixedSize(160, 72)
        btn.setFont(QFont("Consolas", 11, QFont.Bold))
        btn.setText(f"${snap_price:.2f}\n{label_top}\n{label_bot}")
        btn.setStyleSheet(
            f"QPushButton {{background:#0a1a0a;color:{color};"
            f"border:2px solid {color};border-radius:8px;"
            f"font-size:13px;font-weight:bold;padding:6px;}}"
            f"QPushButton:hover {{background:{color};color:#000;}}"
            f"QPushButton:pressed {{background:{color};color:#000;"
            f"border:2px solid #fff;}}")
        return btn

    btn_floor = _make_btn(price_floor, "▼ 내림 (floor)",
        "매도 유리" if bag_action == "SELL" else "매수 불리", "#4c9fff")
    btn_ceil = _make_btn(price_ceil, "▲ 올림 (ceil)",
        "매수 유리" if bag_action == "BUY" else "매도 불리", "#4cff4c")

    _result = [None]

    def _pick(p):
        _result[0] = p
        dlg.accept()

    btn_floor.clicked.connect(lambda: _pick(price_floor))
    btn_ceil.clicked.connect(lambda:  _pick(price_ceil))
    h.addStretch(); h.addWidget(btn_floor); h.addWidget(btn_ceil); h.addStretch()
    v.addLayout(h)

    btn_cancel = QPushButton("취소")
    btn_cancel.setFixedHeight(28)
    btn_cancel.setStyleSheet(
        "QPushButton{background:#1a1a1a;color:#888;border:1px solid #444;"
        "border-radius:4px;font-size:11px;}"
        "QPushButton:hover{background:#333;color:#ccc;}")
    btn_cancel.clicked.connect(dlg.reject)
    v.addWidget(btn_cancel, alignment=Qt.AlignCenter)

    if dlg.exec_() == QDialog.Accepted:
        return _result[0]
    return None


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
# [SLEEP v2.0] 급락 캐치 자동 익절 매도 콜백
# ══════════════════════════════════════════════════════════════

def _sleep_place_sell_order(self, legs: list, lmt_price: float,
                            qty: int = 1, strat: str = "",
                            tag: str = "SPIKE_AUTO_SELL") -> "Optional[int]":
    """
    [FIX-SLEEP-CHASER] is_close=True 전달 → 자동 Chaser 추격 방지
    """
    from typing import Optional as _Opt
    try:
        from core_contract import make_opt_contract
        from ibapi.contract import Contract, ComboLeg
        from ibapi.order   import Order as IbOrder
        from combo_order_callbacks import connect_order_callbacks
        from combo_order_chaser    import register_chaser
    except ImportError as e:
        print(f"[SleepSell] ❌ import 실패: {e}")
        return None

    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if ib is None:
        print("[SleepSell] ❌ IB 연결 없음")
        return None

    connect_order_callbacks(self)
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"

    bag = Contract()
    bag.symbol   = symbol.replace("SPXW", "SPX")
    bag.secType  = "BAG"
    bag.currency = "USD"
    bag.exchange = "SMART"

    combo_legs_out = []
    for leg in legs:
        opt_c = make_opt_contract(
            symbol=symbol, strike=leg["strike"],
            right=leg["cp"], expiry=leg["expiry"])
        cl          = ComboLeg()
        cl.exchange = "SMART"
        cl.ratio    = int(float(leg.get("qty", 1)))
        orig_dir    = str(leg.get("dir", "BUY")).upper()
        cl.action   = "SELL" if orig_dir == "BUY" else "BUY"
        cl.conId    = int(leg.get("con_id", 0))
        if cl.conId == 0:
            try:
                key = _conid_key(bag.symbol, str(leg.get("cp", "")),
                                 float(leg.get("strike", 0)), str(leg.get("expiry", "")))
                cl.conId = int(_CONID_CACHE.get(key, 0))
            except Exception:
                pass
        combo_legs_out.append(cl)

    bag.comboLegs = combo_legs_out
    zero_legs = [i + 1 for i, cl in enumerate(combo_legs_out) if cl.conId == 0]
    if zero_legs:
        print(f"[SleepSell] ❌ 레그 {zero_legs} conId 없음")
        return None

    try:
        from combo_order_chaser import _get_tick_size, _snap_to_tick
        _sleep_symbol = getattr(bag, 'symbol', '').upper()
        tick      = _get_tick_size(lmt_price, _sleep_symbol)
        lmt_price = _snap_to_tick(lmt_price, tick, "sell")
    except Exception:
        pass

    try:
        from combo_order_logic import _get_session_info
        _, _, tif, outside_rth = _get_session_info()
    except Exception:
        tif         = "DAY"
        outside_rth = True

    oid = ib.get_next_id()
    if oid is None:
        print("[SleepSell] ❌ nextOrderId 없음")
        return None

    ibord               = IbOrder()
    ibord.action        = "SELL"
    ibord.orderType     = "LMT"
    ibord.totalQuantity = qty
    ibord.lmtPrice      = lmt_price
    ibord.tif           = tif
    ibord.outsideRth    = outside_rth
    ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False
    ibord.transmit      = True

    try:
        ib.placeOrder(oid, bag, ibord)
        print(f"[SleepSell] ✅ 자동 매도: OID={oid}  lmt=${lmt_price:.2f}  qty={qty}")

        if not hasattr(self, '_close_oid_set'):
            self._close_oid_set = set()
        self._close_oid_set.add(oid)

        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)

        # [FIX-SLEEP-CHASER] is_close=True — 자동 추격 방지
        register_chaser(self, oid=oid, price=lmt_price,
                        action="SELL", qty=qty, is_close=True)
        return oid
    except Exception as e:
        print(f"[SleepSell] ❌ placeOrder 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════════

def _place_combo_legs(self, legs: list, strat: str) -> None:
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

    if len(resolved) == total:
        self._log("⚡ conId 전부 캐시 — 즉시 주문")
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
        except Exception as e:
            self._log(f"❌ reqContractDetails 레그{i+1}: {e}")
            resolved[i] = 0

    def _on_timeout():
        if getattr(self, '_bag_session', None) != session: return
        _disconnect_cd()
        for i in range(total):
            if i not in resolved:
                resolved[i] = 0
        _do_send(self, bag, combo_legs, legs, strat, ib, total, resolved, session)

    QTimer.singleShot(10000, _on_timeout)


# ══════════════════════════════════════════════════════════════
# 주문 전송
# ══════════════════════════════════════════════════════════════

def _do_send(self, bag, combo_legs: list, legs: list, strat: str,
             ib, total: int, resolved: dict, session: int) -> None:
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
    """실제 주문 전송 본체."""
    for i, (cl, _) in enumerate(combo_legs):
        cl.conId = resolved.get(i, 0)
    bag.comboLegs = [cl for cl, _ in combo_legs]

    zero_legs = [i + 1 for i, (cl, _) in enumerate(combo_legs) if cl.conId == 0]
    if zero_legs:
        self._bag_session = None
        self._pending_lmt_override = None
        self._log(f"❌ 주문 취소: 레그 {zero_legs} conId 조회 실패")
        QMessageBox.warning(self, "주문 오류",
            f"레그 {zero_legs}의 conId 조회가 타임아웃됐습니다.\n"
            "즉시 동기화 후 다시 시도하세요.")
        return

    override_lmt = getattr(self, '_pending_lmt_override', None)
    if override_lmt is not None:
        lmt_price               = round(float(override_lmt), 2)
        bag_action              = legs[0]["dir"] if legs else "SELL"
        is_manual_price         = True
        self._pending_lmt_override = None
        buy_total = sell_total = 0.0
        net       = -lmt_price if bag_action == "SELL" else lmt_price
    else:
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
                QMessageBox.warning(self, "가격 미입력", "직접입력 모드에서 스프레드 가격을 입력해주세요.")
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

    # 틱 단위 확인
    # [BUG-BAG-1 FIX] bag.symbol 을 함께 전달하여 XSP($0.01 틱) 예외 적용
    try:
        from combo_order_chaser import _get_tick_size
        _bag_symbol = getattr(bag, 'symbol', '').upper()
        _tick_size = _get_tick_size(lmt_price, _bag_symbol)
        if not _is_tick_aligned(lmt_price, _tick_size):
            chosen = _ask_tick_snap_dialog(self, lmt_price, _tick_size, bag_action)
            if chosen is None:
                self._bag_session = None
                return
            lmt_price = chosen
    except Exception as _e:
        self._log(f"⚠ 틱 확인 실패: {_e}")

    from combo_order_logic import _get_session_info
    after_hours, session_label, tif, outside_rth = _get_session_info()

    oid = ib.get_next_id()
    if oid is None:
        self._bag_session = None
        return

    # [FIX-CHASER-CLOSE] 청산 주문 여부 확정
    _is_close_order = strat.startswith("청산:")
    if _is_close_order:
        if not hasattr(self, '_close_oid_set'):
            self._close_oid_set = set()
        self._close_oid_set.add(oid)
        def _discard_close_oid(target_oid=oid):
            if hasattr(self, '_close_oid_set'):
                self._close_oid_set.discard(target_oid)
        QTimer.singleShot(30000, _discard_close_oid)

    from ibapi.order import Order as IbOrder
    # [SET-QTY] edit_set_qty 위젯에서 세트 수량 읽기
    _set_qty_w = getattr(getattr(self,'synthetic_panel',None),'spin_set_qty',None)
    _set_qty   = int(_set_qty_w.value() if _set_qty_w else 1)
    _bag_qty   = max((int(float(lg.get("qty", 1))) for lg in legs), default=1) * _set_qty
    ibord               = IbOrder()
    ibord.action        = bag_action
    ibord.orderType     = "LMT"
    ibord.totalQuantity = _bag_qty
    ibord.lmtPrice      = lmt_price
    ibord.tif           = tif
    ibord.outsideRth    = outside_rth
    ibord.eTradeOnly    = False
    ibord.firmQuoteOnly = False
    ibord.transmit      = True

    try:
        ib.placeOrder(oid, bag, ibord)
        self._log(
            f"⚡ BAG 주문: OID={oid}  ${lmt_price:.2f}"
            f"  TIF:{tif}  outsideRth:{outside_rth}  레그{total}개  qty={ibord.totalQuantity}")

        self._chaser_bag_contract = bag
        self._chaser_bag_order    = ibord
        # [FIX-OID1] 두 변수 동기화
        self._chaser_current_oid  = oid
        self._chaser_oid          = oid

        try:
            from Sleep_Order.position_close_watcher import PositionCloseWatcher
            _src_oid = getattr(self, '_pending_close_source_oid', None)
            PositionCloseWatcher.get().on_order_placed(
                oid, pos_oid=_src_oid, bag_contract=bag, bag_order=ibord)
        except Exception:
            pass

        if not hasattr(self, '_exec_known_oids'):
            self._exec_known_oids = set()
        self._exec_known_oids.add(oid)

        self._pending_position = {
            "strategy": strat, "qty": int(ibord.totalQuantity),
            "entry": lmt_price, "current": lmt_price,
            "side": bag_action, "oid": oid, "legs": legs, "status": "미체결",
        }

        _leg_data = getattr(self, '_leg_data', {})
        for _i, _leg in enumerate(legs):
            if 'delta' not in _leg:
                _leg['delta'] = float(
                    (_leg_data.get(_i) or {}).get('delta') or 0.0)

        # [FIX-CHASER-CLOSE] 청산 주문이면 is_close=True 전달
        register_chaser(
            self, oid=oid, price=lmt_price,
            action=bag_action, qty=int(ibord.totalQuantity),
            is_close=_is_close_order)

        if not _is_close_order:
            try:
                from combo_order_special_condition import SpecialFillWatcher
                SpecialFillWatcher.get().watch(
                    self, oid, lmt_price, bag_action, legs, strat,
                    bag_contract=bag, qty=int(ibord.totalQuantity))
            except Exception as _e:
                self._log(f"⚠ SpecialFillWatcher 등록 실패: {_e}")

        def _verify_order(check_oid=oid):
            from combo_order_open import on_open_orders
            def _check_cache():
                orders = getattr(self, '_cached_open_orders', [])
                oids   = [o.get('oid') for o in orders]
                if check_oid in oids:
                    self._log(f"✅ OID={check_oid} 주문 접수 확인")
                else:
                    self._log(f"⚠ OID={check_oid} 미확인 — TWS에서 직접 확인")
            on_open_orders(self)
            QTimer.singleShot(2500, _check_cache)

        QTimer.singleShot(5000, _verify_order)

    except Exception as e:
        self._bag_session = None
        # 실패 시 등록된 close_oid_set 정리
        if _is_close_order:
            getattr(self, '_close_oid_set', set()).discard(oid)
        self._log(f"❌ BAG 주문 오류: {e}")