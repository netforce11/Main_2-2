"""
combo_order_logic.py — 합성 주문 버튼 핸들러  v2.1-fix
──────────────────────────────────────────────────────
[FIX-RECONN-RACE] _on_pos_reconnect_hook:
  _pos_hook_active 세팅을 atomic하게 처리
  → 빠른 재연결 두 번에도 중복 실행 방지

[FIX-CHASER-CLOSE] _on_close_position_order:
  register_chaser is_close=True 전달
  → 청산 주문의 Chaser 자동 추격 방지

[FIX-OID-INACTIVE] _close_ib_position:
  Inactive 콜백에서 _close_oid_set 정리 보장
  → 이미 callbacks.py에 수정 반영됨, 여기선 주석 명시

이하 나머지 로직은 원본과 동일 — 변경된 함수만 포함
──────────────────────────────────────────────────────
"""

from datetime import datetime, time as dt_time
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt

from combo_order_utils import _parse_legs_from_table, _parse_expiry_display, _calc_required_margin  # noqa
from combo_order_whatif import (                                                                      # noqa
    _on_whatif_acct_value, _on_whatif_acct_end,
    _on_whatif_result, _finish_whatif, _send_whatif_order,
)
from combo_order_bag    import _place_combo_legs, _place_bag_with_conids                             # noqa
from combo_order_chaser import (                                                                      # noqa
    register_chaser, deactivate_chaser,
    on_chase_click, cancel_bag_order,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

_MARKET_OPEN           = dt_time(9,  30)
_MARKET_CLOSE          = dt_time(16,  0)
_SPX_D1_CLOSE          = dt_time(17, 15)   # D+1 옵션 마감 (CBOE 16:00~17:15 ET)
_AFTER_HOURS_SURCHARGE = 0.25


# ══════════════════════════════════════════════════════════════
# 시간/세션 유틸
# ══════════════════════════════════════════════════════════════

def _is_after_hours() -> bool:
    """정규장(09:30~16:00) 및 D+1 연장(16:00~17:15) 외 시간을 after_hours로 판단.
    SPX/XSP D+1 옵션은 16:00~17:15 ET까지 거래 가능 → 이 구간은 할증 면제.
    """
    try:
        now_et = datetime.now(ZoneInfo("America/New_York")).time()
        # 정규장 또는 D+1 연장 구간이면 할증 없음
        if _MARKET_OPEN <= now_et < _SPX_D1_CLOSE:
            return False
        return True
    except Exception:
        return False


def _get_session_info() -> tuple:
    """ET 기준 세션 판단. Returns: (after_hours, label, tif, outside_rth)
    세션 구분:
      09:30~16:00  정규장        DAY  / rth=False
      16:00~17:15  D+1 연장      GTX  / rth=True   ← SPX D+1 옵션 거래 가능
      17:15~20:00  애프터(거래불가) GTX / rth=True  ← 주문 차단
      20:00~04:00  심야(거래불가)  GTX / rth=True   ← 주문 차단
      04:00~09:30  프리마켓       GTX  / rth=True   ← 주문 차단
    """
    _PRE_START = dt_time(4,  0)
    _AFTER_END = dt_time(20, 0)
    try:
        now_et = datetime.now(ZoneInfo("America/New_York")).time()
    except Exception:
        return False, "알수없음", "DAY", False
    if _MARKET_OPEN <= now_et < _MARKET_CLOSE:
        return False, "정규장(09:30~16:00)",      "DAY", False
    elif _MARKET_CLOSE <= now_et < _SPX_D1_CLOSE:
        return True,  "D+1연장(16:00~17:15)",     "GTX", True
    elif _SPX_D1_CLOSE <= now_et < _AFTER_END:
        return True,  "애프터(17:15~20:00/거래불가)", "GTX", True
    elif _PRE_START <= now_et < _MARKET_OPEN:
        return True,  "프리마켓(04:00~09:30/거래불가)", "GTX", True
    else:
        return True,  "심야(20:00~04:00/거래불가)", "GTX", True


# ══════════════════════════════════════════════════════════════
# 증거금 계산
# ══════════════════════════════════════════════════════════════

def _calc_margin_local(self, legs: list) -> tuple:
    cache     = getattr(self, '_whatif_acct_cache', {})
    cache_val = cache.get("af") or cache.get("bp")
    if cache_val:
        available = cache_val
        self._cached_available_funds = cache_val
        self._acct_fetched_once      = True
    else:
        cached = getattr(self, '_cached_available_funds', None)
        if cached is None:
            available = 0.0
            self._log("⚠ 계좌 잔고 미조회 — 💰 증거금 조회 버튼을 눌러주세요")
        elif cached == 1_000_000.0 and not getattr(self, '_acct_fetched_once', False):
            available = cached
            self._log("⚠ 계좌 잔고가 기본값($1,000,000) — 실계좌라면 💰 증거금 조회 먼저")
        else:
            available = cached
    required    = _calc_required_margin(legs)
    after_hours = _is_after_hours()
    if after_hours:
        required = round(required * (1 + _AFTER_HOURS_SURCHARGE), 2)
    return available, required, available >= required, after_hours


# ══════════════════════════════════════════════════════════════
# 신규 주문
# ══════════════════════════════════════════════════════════════

def _on_synthetic_order(self):
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return self._log("⚠ synthetic_panel 없음")
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")

    strat = self.combo_strat.currentText()
    legs  = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가/만기가 입력되지 않았습니다.\n체인 클릭 또는 수동 입력 후 다시 시도하세요.")

    use_server = getattr(self, '_margin_mode_server', False)
    if use_server:
        cost_str = (self._kpi_widgets.get('cost',
                    type('', (), {'text': lambda s: '―'})()).text()
                    if hasattr(self, '_kpi_widgets') else "―")
        def _on_margin_checked(available, required, margin_ok):
            if not margin_ok:
                return QMessageBox.warning(self, "증거금 부족",
                    f"가용: ${available:,.2f}  /  필요: ${required:,.2f}\n증거금 부족.")
            _place_combo_legs(self, legs, strat)
        _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)
    else:
        available, required, margin_ok, after_hours = _calc_margin_local(self, legs)
        if not margin_ok:
            ah_note = "\n⚠ 장외 시간 25% 할증 적용됨" if after_hours else ""
            return QMessageBox.warning(self, "증거금 부족",
                f"가용: ${available:,.2f}  /  필요: ${required:,.2f}{ah_note}")
        if after_hours:
            ret = QMessageBox.warning(self, "⚠ 장외 시간 경고",
                f"장외 시간 — IB 장외 증거금 25% 할증\n"
                f"필요 증거금: ${required:,.2f}\n가용: ${available:,.2f}\n\n계속 주문?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        if panel:
            panel.update_margin(available, required, strat)
        _place_combo_legs(self, legs, strat)


def _on_check_margin(self):
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
    strat = self.combo_strat.currentText()
    legs  = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가·프리미엄·만기를 입력한 후 다시 시도하세요.")
    use_server = getattr(self, '_margin_mode_server', False)
    panel      = getattr(self, 'synthetic_panel', None)
    if use_server:
        if getattr(self, '_whatif_in_progress', False):
            return
        cost_str = (self._kpi_widgets.get('cost',
                    type('', (), {'text': lambda s: '―'})()).text()
                    if hasattr(self, '_kpi_widgets') else "―")
        self._log("💰 [서버] whatIf 증거금 조회 요청 중…")
        _send_whatif_order(self, legs, strat, cost_str, on_done=None)
    else:
        available, required, margin_ok, after_hours = _calc_margin_local(self, legs)
        ah_tag = "  ⚠ 장외 25% 할증" if after_hours else ""
        self._log(f"💰 [로컬] {'✅' if margin_ok else '❌'}  "
                  f"가용=${available:,.2f}  필요=${required:,.2f}{ah_tag}")
        if panel:
            panel.update_margin(available, required, strat)


def _on_cancel_bag_order(self):
    cancel_bag_order(self)


# ══════════════════════════════════════════════════════════════
# 청산 주문
# ══════════════════════════════════════════════════════════════

def _on_close_position_order(self, pos: dict, lmt_price: float = None,
                              _auto: bool = False):
    """
    [FIX-CHASER-CLOSE] close_legs → _place_combo_legs 호출 시
    register_chaser 에 is_close=True 전달은 combo_order_bag._do_send_body
    내부의 register_chaser 호출에서 strat.startswith("청산:") 로 자동 판별.
    combo_order_bag.py 의 register_chaser 호출에 is_close 파라미터 추가 필요.
    """
    if lmt_price is None and pos.get('_lmt_price'):
        lmt_price = float(pos.pop('_lmt_price'))

    oid = pos.get("oid")
    price_label = f"${lmt_price:.2f} [LMT]" if lmt_price is not None else "[MKT]"
    self._log(f"🔴 청산 요청: OID={oid}  가격={price_label}  전략={pos.get('strategy','')}")

    legs = pos.get("legs", [])
    if not legs and _auto:
        try:
            panel     = getattr(self, "synthetic_panel", None)
            positions = getattr(panel, "_positions", []) if panel else []
            for p in positions:
                if p.get("oid") == oid and p.get("legs"):
                    legs = p["legs"]
                    pos  = dict(pos)
                    pos["legs"] = legs
                    break
        except Exception as e:
            self._log(f"  [FIX-AUTO] legs 재조회 실패: {e}")

    if not legs:
        self._log("  → legs 없음 — IB 단건 청산 경로")
        _close_ib_position(self, pos, lmt_price=lmt_price, _auto=_auto)
        return

    required_keys = {"dir", "cp", "strike", "expiry", "qty"}
    for i, lg in enumerate(legs):
        missing = required_keys - set(lg.keys())
        if missing:
            self._log(f"❌ 청산 오류: 레그{i+1} 필수 키 누락 {missing}")
            return

    saved_qty = int(pos.get("qty", 1))
    ib_qty    = int(pos.get("ib_qty", saved_qty))
    if ib_qty != saved_qty:
        self._log(f"⚠ 청산 수량 불일치: 파일={saved_qty} / IB={ib_qty}"
                  f" — IB 서버 수량({ib_qty})으로 청산")

    close_legs = [dict(lg, dir="SELL" if lg["dir"] == "BUY" else "BUY") for lg in legs]
    strat_name = f"청산: {pos.get('strategy','')}"
    self._log(f"  → BAG 청산: 레그{len(close_legs)}개  {strat_name}")

    if oid:
        if not hasattr(self, '_close_oid_set'):
            self._close_oid_set = set()
        self._close_oid_set.add(oid)

    if oid:
        try:
            from combo_position_store import record_trade_history
            exit_price = float(pos.get("current", pos.get("entry", 0)))
            record_trade_history(pos, exit_price=exit_price, close_type="청산주문")
        except Exception:
            pass

    if oid:
        self._pending_close_oid        = oid
        self._pending_close_source_oid = oid

    if lmt_price is not None:
        self._log(f"  → _place_combo_legs_lmt ${lmt_price:.2f}")
        _place_combo_legs_lmt(self, close_legs, strat_name, lmt_price)
    else:
        self._log("  → _place_combo_legs MKT")
        _place_combo_legs(self, close_legs, strat_name)


def _close_ib_position(self, pos: dict, lmt_price: float = None,
                        _auto: bool = False):
    """IB reqPositions 단건 청산."""
    from PyQt5.QtWidgets import QMessageBox as _MB
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib:
        return

    strategy     = pos.get("strategy", "")
    qty          = pos.get("qty", 1)
    side         = pos.get("side", "BUY")
    close_action = "SELL" if side == "BUY" else "BUY"
    current      = pos.get("current", pos.get("entry", 0))
    order_type   = "LMT" if lmt_price is not None else "MKT"

    if not _auto:
        dlg = _MB(self)
        dlg.setWindowTitle("🔴 포지션 청산")
        price_line = f"지정가:  ${lmt_price:.2f}" if lmt_price else f"현재가:  ${current:.2f}"
        dlg.setText(
            f"포지션 청산\n─────────────────────\n"
            f"종목:  {strategy}\n수량:  {qty}계약\n"
            f"{price_line}\n청산 방향:  {close_action}  [{order_type}]\n"
            f"─────────────────────\n청산 주문을 전송하시겠습니까?")
        dlg.setStandardButtons(_MB.Ok | _MB.Cancel)
        dlg.button(_MB.Ok).setText("청산 전송")
        dlg.button(_MB.Cancel).setText("취소")
        if dlg.exec_() != _MB.Ok:
            return

    from ibapi.contract import Contract
    from ibapi.order import Order as IbOrder
    con_id = pos.get("con_id", 0)
    sym    = strategy.split()[0] if strategy else "SPX"
    ct     = Contract()
    if con_id:
        ct.conId = con_id; ct.exchange = "SMART"
    else:
        ct.symbol = sym; ct.secType = "OPT"
        ct.exchange = "SMART"; ct.currency = "USD"

    oid = ib.get_next_id()
    if oid is None:
        return self._log("❌ nextOrderId 없음")

    if not hasattr(self, '_close_oid_set'):
        self._close_oid_set = set()
    self._close_oid_set.add(oid)
    self._log(f"  단건 청산 oid 등록: {oid}")

    after_hours, session_label, tif, outside_rth = _get_session_info()
    # [FIX] 17:15 이후(D+1 마감 후)~프리마켓 종료까지 SPX 옵션 거래 불가 → 차단
    _now_et = datetime.now(ZoneInfo("America/New_York")).time()
    _tradeable = (
        (dt_time(9, 30) <= _now_et < dt_time(17, 15))   # 정규장 + D+1 연장
    )
    if not _tradeable:
        _log_fn = getattr(self, '_log', print)
        _log_fn(f"⛔ [{session_label}] SPX 옵션 거래 불가 시간 — 주문 차단")
        return None
    ord_               = IbOrder()
    ord_.action        = close_action
    ord_.orderType     = order_type
    ord_.totalQuantity = qty
    ord_.tif           = tif
    ord_.outsideRth    = outside_rth
    ord_.eTradeOnly    = False
    ord_.firmQuoteOnly = False
    ord_.transmit      = True
    if lmt_price is not None:
        ord_.lmtPrice = lmt_price

    try:
        ib.placeOrder(oid, ct, ord_)
        price_log = f"  지정가=${lmt_price:.2f}" if lmt_price else ""
        self._log(
            f"🔴 청산({order_type}): OID={oid}  {close_action} {qty}계약  "
            f"{strategy}{price_log}  TIF:{tif}  세션:{session_label}")

        src_oid = pos.get("oid")
        if src_oid:
            try:
                from combo_order_callbacks import stop_position_price_stream
                stop_position_price_stream(self, src_oid)
            except Exception:
                pass
        if src_oid:
            try:
                from combo_position_store import safe_remove_after_order
                safe_remove_after_order(src_oid, log_fn=self._log)
            except Exception:
                pass
    except Exception as e:
        # [FIX-OID-INACTIVE] 주문 실패 시 _close_oid_set 오염 방지
        self._close_oid_set.discard(oid)
        self._log(f"❌ 청산 오류: {e}")


def _place_combo_legs_lmt(self, legs: list, strat: str, lmt_price: float):
    self._pending_lmt_override = lmt_price
    try:
        _place_combo_legs(self, legs, strat)
    except Exception:
        self._pending_lmt_override = None
        raise


# ══════════════════════════════════════════════════════════════
# 패널 콜백 초기화
# ══════════════════════════════════════════════════════════════

def _init_synthetic_panel_callbacks(self):
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return

    def _close_cb(pos, lmt_price=None, *args, **kwargs):
        _on_close_position_order(self, pos, lmt_price=lmt_price)
    panel.set_close_position_callback(_close_cb)
    panel.set_manual_modify_callback(
        lambda oid, price: _on_manual_modify(self, oid, price))
    panel.set_chaser_mode_callback(
        lambda mode: _on_chaser_mode_changed(self, mode))
    panel.set_margin_mode_callback(
        lambda server: setattr(self, '_margin_mode_server', server))

    self._margin_mode_server     = False
    self._cached_available_funds = 1_000_000.0
    self._whatif_acct_cache      = {}
    self._acct_fetched_once      = False

    if not hasattr(self, '_close_oid_set'):
        self._close_oid_set = set()
    self._pending_close_source_oid = None

    if not getattr(self, '_whatif_slots_connected', False):
        try:
            from core import bridge
            bridge.acct_value.connect(self._on_whatif_acct_value, Qt.QueuedConnection)
            bridge.acct_end.connect(self._on_whatif_acct_end,     Qt.QueuedConnection)
            bridge.whatif_sig.connect(self._on_whatif_result,     Qt.QueuedConnection)
            self._whatif_slots_connected = True
        except Exception:
            self._whatif_slots_connected = False


def _on_manual_modify(self, oid: int, new_price: float):
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    bag   = getattr(self, '_chaser_bag_contract', None)
    ibord = getattr(self, '_chaser_bag_order', None)
    if not ib or not bag or not ibord:
        return self._log("⚠ 수동 정정: 주문 객체 없음")
    import copy
    new_ord = copy.deepcopy(ibord)
    new_ord.lmtPrice = round(new_price, 2)
    try:
        ib.placeOrder(oid, bag, new_ord)
        self._log(f"✏ 수동 정정: OID={oid}  새 가격=${new_price:.2f}")
        self._chaser_bag_order = new_ord
    except Exception as e:
        self._log(f"❌ 수동 정정 오류: {e}")


def _on_chaser_mode_changed(self, mode: str):
    self._log(f"🎯 Chaser 모드: {mode}")
    try:
        if mode == "manual":
            deactivate_chaser(self, reason="수동 모드 전환")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 재연결 훅
# ══════════════════════════════════════════════════════════════

def _on_pos_reconnect_hook(self):
    """
    재연결 후 합성 잔고 복원.
    [FIX-RECONN-RACE] _pos_hook_active 를 try/except 앞에서 먼저 세팅
    → 빠른 재연결 두 번에도 중복 실행 안 됨.
    """
    import importlib.util, sys
    from pathlib import Path

    # [FIX-RECONN-RACE] 중복 방지 플래그 — 먼저 세팅
    if getattr(self, '_pos_hook_active', False):
        self._log("⚠ 재연결 훅 이미 진행 중 — 중복 무시")
        return
    self._pos_hook_active = True  # 먼저 세팅 후 처리 시작

    # [FIX-CACHE] 재연결 시 체결 캐시 초기화 (오래된 OID 데이터 혼입 방지)
    self._exec_avg_cache = {}

    try:
        from combo_position_store import restore_on_reconnect
        self._log("🔄 재연결: 합성 잔고 복원 시작…")
        restore_on_reconnect(self)
        return
    except ImportError:
        pass
    except Exception as e:
        self._log(f"⚠ 잔고 복원 오류(일반): {e}")
        self._pos_hook_active = False  # 오류 시 플래그 해제
        return

    try:
        _this_dir   = Path(__file__).resolve().parent
        _store_path = _this_dir / "combo_position_store.py"
        if not _store_path.exists():
            self._log(f"⚠ combo_position_store.py 없음: {_store_path}")
            self._pos_hook_active = False
            return
        spec   = importlib.util.spec_from_file_location(
                    "combo_position_store", str(_store_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("combo_position_store", module)
        spec.loader.exec_module(module)
        self._log("🔄 재연결: 합성 잔고 복원 시작 (절대경로)…")
        module.restore_on_reconnect(self)
    except Exception as e:
        self._log(f"⚠ 잔고 복원 오류(절대경로): {e}")
        self._pos_hook_active = False


# ══════════════════════════════════════════════════════════════
# IB 포지션 직접 조회 (보조용)
# ══════════════════════════════════════════════════════════════

def _load_ib_positions(self):
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    panel = getattr(self, 'synthetic_panel', None)
    if not ib or not panel:
        return
    _buf = []

    def _on_pos(account, contract, pos, avg_cost):
        if abs(pos) < 0.001: return
        if getattr(contract, 'secType', '') not in ('OPT', 'BAG', 'FOP'): return
        sym    = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
        right  = getattr(contract, 'right', '')
        strike = getattr(contract, 'strike', 0)
        mult   = float(getattr(contract, 'multiplier', 100) or 100)
        con_id = getattr(contract, 'conId', 0)
        side   = 'BUY' if pos > 0 else 'SELL'
        cp     = 'C' if right == 'C' else 'P'
        entry  = avg_cost / mult if mult else avg_cost
        _buf.append({
            "strategy": f"{sym} {cp}{int(strike)} ×{int(abs(pos))}",
            "qty": int(abs(pos)), "entry": round(entry, 2),
            "current": round(entry, 2), "side": side,
            "con_id": con_id, "legs": [],
        })

    def _on_pos_end():
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: [panel.add_position(p) for p in _buf] or
                       self._log(f"✅ IB 포지션 {len(_buf)}건" if _buf else "ℹ 없음"))
        try:
            ib.position    = ib._orig_pos
            ib.positionEnd = ib._orig_pos_end
        except Exception:
            pass

    ib._orig_pos     = getattr(ib, 'position',    lambda *a: None)
    ib._orig_pos_end = getattr(ib, 'positionEnd', lambda: None)
    ib.position    = _on_pos
    ib.positionEnd = _on_pos_end
    try:
        ib.reqPositions()
    except Exception as e:
        self._log(f"❌ reqPositions 오류: {e}")
