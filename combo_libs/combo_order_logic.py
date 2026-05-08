"""
combo_order_logic.py — 합성 주문 버튼 핸들러
──────────────────────────────────────────────
[FIX-A] 청산 순서 교정: remove_position → placeOrder 이후로 이동
         주문 전송 실패 시 파일 데이터 보존.
[FIX-B] 청산 oid 추적: _close_oid_set 에 등록 →
         combo_order_callbacks._on_order_status("Filled") 에서
         청산 완료 후 save_one_position 호출 차단.
[FIX-C] 청산 수량 검증: IB 서버 qty 와 파일 qty 불일치 시 경고.
[FIX-D] _on_pos_reconnect_hook 중복 등록 방지.
──────────────────────────────────────────────
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

_MARKET_OPEN           = dt_time(9, 30)
_MARKET_CLOSE          = dt_time(16, 0)
_AFTER_HOURS_SURCHARGE = 0.25


# ══════════════════════════════════════════════════════════════
# 시간/세션 유틸
# ══════════════════════════════════════════════════════════════

def _is_after_hours() -> bool:
    try:
        now_et = datetime.now(ZoneInfo("America/New_York")).time()
        return not (_MARKET_OPEN <= now_et <= _MARKET_CLOSE)
    except Exception:
        return False


def _get_session_info() -> tuple:
    """
    현재 ET 시각 기준으로 장 세션 판단.
    Returns: (after_hours, session_label, tif, outside_rth)
    """
    _PRE_START = dt_time(4,  0)
    _AFTER_END = dt_time(20, 0)

    try:
        now_et = datetime.now(ZoneInfo("America/New_York")).time()
    except Exception:
        return False, "알수없음", "DAY", False

    if _MARKET_OPEN <= now_et < _MARKET_CLOSE:
        return False, "정규장(09:30~16:00)", "DAY", False
    elif _PRE_START <= now_et < _MARKET_OPEN:
        return True,  "프리마켓(04:00~09:30)", "GTX", True
    elif _MARKET_CLOSE <= now_et < _AFTER_END:
        return True,  "애프터(16:00~20:00)",   "GTX", True
    else:
        return True,  "심야(20:00~04:00)",     "GTX", True


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
            self._log("⚠ 계좌 잔고 미조회 — TWS 연결 후 💰 증거금 조회 버튼을 눌러주세요")
        elif cached == 1_000_000.0 and not getattr(self, '_acct_fetched_once', False):
            available = cached
            self._log("⚠ 계좌 잔고가 기본값($1,000,000) — 실계좌라면 💰 증거금 조회 먼저")
        else:
            available = cached

    required    = _calc_required_margin(legs)
    after_hours = _is_after_hours()
    if after_hours:
        required = round(required * (1 + _AFTER_HOURS_SURCHARGE), 2)
    margin_ok = available >= required
    return available, required, margin_ok, after_hours


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
            "행사가/만기가 입력되지 않았습니다.\n"
            "체인 클릭 또는 수동 입력 후 다시 시도하세요.")

    use_server = getattr(self, '_margin_mode_server', False)

    if use_server:
        cost_str = (self._kpi_widgets.get('cost',
                    type('', (), {'text': lambda s: '―'})()).text()
                    if hasattr(self, '_kpi_widgets') else "―")

        def _on_margin_checked(available, required, margin_ok):
            if not margin_ok:
                return QMessageBox.warning(self, "증거금 부족",
                    f"가용: ${available:,.2f}  /  필요: ${required:,.2f}\n"
                    "증거금 부족으로 주문 취소.")
            _place_combo_legs(self, legs, strat)

        _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)

    else:
        available, required, margin_ok, after_hours = _calc_margin_local(self, legs)

        if not margin_ok:
            ah_note = "\n⚠ 장외 시간 25% 할증 적용됨" if after_hours else ""
            return QMessageBox.warning(self, "증거금 부족",
                f"가용: ${available:,.2f}  /  필요: ${required:,.2f}{ah_note}\n"
                "증거금 부족으로 주문 취소.")

        if after_hours:
            ret = QMessageBox.warning(self, "⚠ 장외 시간 경고",
                f"현재 장외 시간입니다.\n"
                f"IB는 장외 증거금을 25% 할증 적용합니다.\n\n"
                f"필요 증거금 (할증 포함): ${required:,.2f}\n"
                f"가용 증거금: ${available:,.2f}\n\n"
                "계속 주문하시겠습니까?",
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
        status = "✅ 주문 가능" if margin_ok else "❌ 증거금 부족"
        self._log(f"💰 [로컬] {status}  가용=${available:,.2f}  "
                  f"필요=${required:,.2f}{ah_tag}")
        if panel:
            panel.update_margin(available, required, strat)
        if after_hours:
            QMessageBox.information(self, "⚠ 장외 시간",
                f"장외 시간 — IB 증거금 25% 할증 적용\n"
                f"필요 증거금 (할증 포함): ${required:,.2f}")


def _on_cancel_bag_order(self):
    cancel_bag_order(self)


# ══════════════════════════════════════════════════════════════
# 청산 주문
# ══════════════════════════════════════════════════════════════

def _on_close_position_order(self, pos: dict):
    """
    잔고 탭 청산 버튼 핸들러.

    [FIX-A] remove_position 을 placeOrder 성공 후로 이동.
            주문 실패 시 파일 데이터 보존됨.
    [FIX-B] _close_oid_set 에 청산 oid 등록 →
            _on_order_status("Filled") 에서 신규 save 차단.
    [FIX-C] 수량 불일치 경고.
    """
    oid = pos.get("oid")

    # 실시간 손익 구독 해제 (청산 직전)
    if oid:
        try:
            from combo_order_callbacks import stop_position_price_stream
            stop_position_price_stream(self, oid)
        except Exception:
            pass

    legs = pos.get("legs", [])
    if not legs:
        # IB 단건 MKT 청산 — 성공 후 파일 제거는 _close_ib_position 내부에서
        _close_ib_position(self, pos)
        return

    # [FIX-C] 수량 불일치 검증
    saved_qty = int(pos.get("qty", 1))
    ib_qty    = int(pos.get("ib_qty", saved_qty))   # IB 서버가 보정한 qty
    if ib_qty != saved_qty:
        self._log(
            f"⚠ 청산 수량 불일치: 파일={saved_qty} / IB서버={ib_qty} "
            f"— IB 서버 수량({ib_qty})으로 청산 진행")

    close_legs = [dict(lg, dir="SELL" if lg["dir"] == "BUY" else "BUY") for lg in legs]
    strat_name = f"청산: {pos.get('strategy','')}"

    # [FIX-B] 청산 oid 미리 추적 등록 (placeOrder 전)
    if oid:
        if not hasattr(self, '_close_oid_set'):
            self._close_oid_set = set()
        self._close_oid_set.add(oid)

    # 청산 이력 기록 (주문 전송 전에 기록 — 전송 실패해도 이력은 남김)
    if oid:
        try:
            from combo_position_store import record_trade_history
            exit_price = float(pos.get("current", pos.get("entry", 0)))
            record_trade_history(pos, exit_price=exit_price, close_type="청산주문")
        except Exception:
            pass

    # [FIX-A] 주문 전송 후 성공 시 파일 제거
    # _place_combo_legs 는 동기가 아니므로 콜백(Filled/Submitted)에서 remove.
    # 단, 여기서 _pending_close_oid 를 등록해두면
    # _on_order_status("Submitted") 수신 시 즉시 파일에서 제거 가능.
    if oid:
        self._pending_close_oid = oid   # callbacks 에서 Submitted 확인 후 제거

    _place_combo_legs(self, close_legs, strat_name)


def _close_ib_position(self, pos: dict):
    """IB reqPositions 로 불러온 포지션 MKT 청산."""
    from PyQt5.QtWidgets import QMessageBox as _MB
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib:
        return

    strategy     = pos.get("strategy", "")
    qty          = pos.get("qty", 1)
    side         = pos.get("side", "BUY")
    close_action = "SELL" if side == "BUY" else "BUY"
    current      = pos.get("current", pos.get("entry", 0))

    dlg = _MB(self)
    dlg.setWindowTitle("🔴 포지션 청산")
    dlg.setText(
        f"포지션 청산\n─────────────────────────\n"
        f"종목:  {strategy}\n수량:  {qty}계약\n"
        f"현재가:  ${current:.2f}\n청산 방향:  {close_action}\n"
        f"─────────────────────────\n시장가(MKT) 청산 주문을 전송하시겠습니까?")
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

    after_hours, session_label, tif, outside_rth = _get_session_info()

    ord_ = IbOrder()
    ord_.action        = close_action
    ord_.orderType     = "MKT"
    ord_.totalQuantity = qty
    ord_.tif           = tif
    ord_.outsideRth    = outside_rth
    ord_.eTradeOnly    = False
    ord_.firmQuoteOnly = False
    ord_.transmit      = True

    try:
        ib.placeOrder(oid, ct, ord_)
        self._log(
            f"🔴 청산 주문(MKT): OID={oid}  {close_action} {qty}계약  {strategy}"
            f"  TIF:{tif}  장외:{outside_rth}  세션:{session_label}")

        # [FIX-A] 주문 전송 성공 후 파일 제거
        src_oid = pos.get("oid")
        if src_oid:
            try:
                from combo_position_store import safe_remove_after_order
                safe_remove_after_order(src_oid, log_fn=self._log)
            except Exception:
                pass

    except Exception as e:
        self._log(f"❌ 청산 오류: {e}")


# ══════════════════════════════════════════════════════════════
# 패널 콜백 초기화
# ══════════════════════════════════════════════════════════════

def _init_synthetic_panel_callbacks(self):
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return
    panel.set_close_position_callback(
        lambda pos: _on_close_position_order(self, pos))
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

    # [FIX-B] 청산 oid 추적 집합 초기화
    if not hasattr(self, '_close_oid_set'):
        self._close_oid_set = set()

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
    [FIX-D] combo_position_store._pos_hook_active 플래그로 중복 등록 방지.
            (tab_combo_strategy._connect_signals 중복 호출 시 안전)
    """
    import importlib.util, sys
    from pathlib import Path

    try:
        from combo_position_store import restore_on_reconnect
        self._log("🔄 재연결: 합성 잔고 복원 시작…")
        restore_on_reconnect(self)
        return
    except ImportError:
        pass
    except Exception as e:
        self._log(f"⚠ 잔고 복원 오류(일반): {e}")
        return

    try:
        _this_dir   = Path(__file__).resolve().parent
        _store_path = _this_dir / "combo_position_store.py"
        if not _store_path.exists():
            self._log(f"⚠ combo_position_store.py 없음: {_store_path}")
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


# ══════════════════════════════════════════════════════════════
# IB 포지션 직접 조회 (비긴급 보조용)
# ══════════════════════════════════════════════════════════════

def _load_ib_positions(self):
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    panel = getattr(self, 'synthetic_panel', None)
    if not ib or not panel:
        return
    _buf = []

    def _on_pos(account, contract, pos, avg_cost):
        if abs(pos) < 0.001:
            return
        if getattr(contract, 'secType', '') not in ('OPT', 'BAG', 'FOP'):
            return
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
            "qty":      int(abs(pos)),
            "entry":    round(entry, 2),
            "current":  round(entry, 2),
            "side":     side,
            "con_id":   con_id,
            "legs":     [],
        })

    def _on_pos_end():
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: [panel.add_position(p) for p in _buf] or
                       self._log(f"✅ IB 포지션 {len(_buf)}건 반영" if _buf else "ℹ IB 옵션 포지션 없음"))
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
