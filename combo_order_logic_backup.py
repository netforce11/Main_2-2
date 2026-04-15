"""
combo_order_logic.py — 합성 주문 버튼 핸들러
──────────────────────────────────────────────
포함:
  _on_synthetic_order    — ⚡ 합성 주문 버튼
  _on_check_margin       — 💰 증거금 조회 버튼 (로컬/서버 모드)
  _on_cancel_bag_order   — ✕ 주문 취소 버튼
  _on_close_position_order — 잔고 탭 청산
  _init_synthetic_panel_callbacks — 패널 콜백 연결
  _load_ib_positions     — 재연결 후 IB 포지션 로드
  _calc_margin_local     — 로컬 증거금 계산 (장외 할증 포함)

v2.7 변경:
  - 증거금 모드: 로컬(즉시) / 서버(whatIf) 라디오 선택
  - 로컬 모드: 확인창 즉시 팝업 (서버 대기 없음)
  - 장외 시간 자동 감지 → 25% 할증 + 경고 표시
──────────────────────────────────────────────
"""

from datetime import datetime, time as dt_time
from PyQt5.QtWidgets import QMessageBox

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

# ── 장외 시간 판별 (ET 기준 09:30~16:00) ──────────────────────
try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

_MARKET_OPEN  = dt_time(9, 30)
_MARKET_CLOSE = dt_time(16, 0)
_AFTER_HOURS_SURCHARGE = 0.25   # 25% 할증

def _is_after_hours() -> bool:
    """현재 ET 기준 장외 시간 여부."""
    try:
        now_et = datetime.now(ZoneInfo("America/New_York")).time()
        return not (_MARKET_OPEN <= now_et <= _MARKET_CLOSE)
    except Exception:
        return False


def _calc_margin_local(self, legs: list) -> tuple:
    """
    로컬 증거금 계산.
    반환: (available, required, margin_ok, after_hours)
    """
    available = getattr(self, '_cached_available_funds', 1_000_000.0)
    required  = _calc_required_margin(legs)
    after_hours = _is_after_hours()
    if after_hours:
        required = round(required * (1 + _AFTER_HOURS_SURCHARGE), 2)
    margin_ok = available >= required
    return available, required, margin_ok, after_hours


# ── 공개 핸들러 ────────────────────────────────────────────────

def _on_synthetic_order(self):
    """⚡ 합성 주문 버튼 핸들러."""
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

    # ── 증거금 모드 판별 ───────────────────────────────────────
    use_server = getattr(self, '_margin_mode_server', False)

    if use_server:
        # 서버 모드: whatIf → 콜백 후 주문
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
        # 로컬 모드: 즉시 계산 → 바로 확인창
        available, required, margin_ok, after_hours = _calc_margin_local(self, legs)
        self._cached_available_funds = available   # 이후 패널 갱신용 저장

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
                f"계속 주문하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return

        # 패널 증거금 탭 갱신
        if panel:
            panel.update_margin(available, required, strat)

        _place_combo_legs(self, legs, strat)


def _on_check_margin(self):
    """💰 증거금 조회 버튼 핸들러 — 로컬/서버 모드."""
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
        self._cached_available_funds = available
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
    """✕ 주문 취소 버튼 핸들러."""
    cancel_bag_order(self)


def _on_close_position_order(self, pos: dict):
    """잔고 탭 청산 버튼 핸들러."""
    legs = pos.get("legs", [])
    if not legs:
        _close_ib_position(self, pos)
        return
    close_legs = [dict(lg, dir="SELL" if lg["dir"] == "BUY" else "BUY") for lg in legs]
    _place_combo_legs(self, close_legs, f"청산: {pos.get('strategy','')}")


def _close_ib_position(self, pos: dict):
    """IB reqPositions로 불러온 포지션 청산 — MKT 주문."""
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
    ord_ = IbOrder()
    ord_.action = close_action; ord_.orderType = "MKT"
    ord_.totalQuantity = qty;   ord_.tif = "DAY"
    ord_.eTradeOnly = False;    ord_.firmQuoteOnly = False
    ord_.transmit = True
    try:
        ib.placeOrder(oid, ct, ord_)
        self._log(f"🔴 청산 주문: OID={oid}  {close_action} {qty}계약  {strategy}")
    except Exception as e:
        self._log(f"❌ 청산 오류: {e}")


def _init_synthetic_panel_callbacks(self):
    """synthetic_panel 콜백 연결 + 증거금 모드 초기화."""
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
    # 기본값: 로컬 모드
    self._margin_mode_server     = False
    self._cached_available_funds = 1_000_000.0


def _on_manual_modify(self, oid: int, new_price: float):
    """수동 정정."""
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
    """Chaser 자동/수동 모드 전환."""
    self._log(f"🎯 Chaser 모드: {mode}")
    try:
        if mode == "manual":
            deactivate_chaser(self, reason="수동 모드 전환")
    except Exception:
        pass


def _on_pos_reconnect_hook(self):
    """재연결 후 IB 포지션 재조회."""
    panel = getattr(self, 'synthetic_panel', None)
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    if not panel or not ib:
        return
    self._log("🔄 재연결: IB 포지션 재조회 중…")
    panel.clear_positions()
    _load_ib_positions(self)


def _load_ib_positions(self):
    """IB reqPositions → 합성 잔고 탭."""
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


# ── 공개 핸들러 ────────────────────────────────────────────────

def _on_synthetic_order(self):
    """⚡ 합성 주문 버튼 핸들러.
    확인창은 combo_order_bag._send_bag() 안에서 1회만 표시됨.
    여기서는 증거금 체크 후 바로 _place_combo_legs 위임.
    """
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return self._log("⚠ synthetic_panel 없음")
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")

    strat    = self.combo_strat.currentText()
    cost_str = (self._kpi_widgets.get('cost',
                type('', (), {'text': lambda s: '―'})()).text()
                if hasattr(self, '_kpi_widgets') else "―")
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가/만기가 입력되지 않았습니다.\n"
            "체인 클릭 또는 수동 입력 후 다시 시도하세요.")

    def _on_margin_checked(available, required, margin_ok):
        if not margin_ok:
            return QMessageBox.warning(self, "증거금 부족",
                f"가용: ${available:,.2f}  /  필요: ${required:,.2f}\n"
                "증거금 부족으로 주문 취소.")
        # 확인창은 _place_combo_legs → _send_bag 안에서 1회 표시
        _place_combo_legs(self, legs, strat)

    _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)


def _on_close_position_order(self, pos: dict):
    """잔고 탭 청산 버튼 핸들러."""
    legs = pos.get("legs", [])

    # ── IB 서버에서 불러온 포지션 (legs 없음) → BAG 청산 직접 구성 ──
    if not legs:
        _close_ib_position(self, pos)
        return

    # ── 앱 내에서 주문한 포지션 → 레그 반전 후 재주문 ──────────────
    close_legs = []
    for lg in legs:
        cl = dict(lg)
        cl["dir"] = "SELL" if lg["dir"] == "BUY" else "BUY"
        close_legs.append(cl)
    strat = f"청산: {pos.get('strategy', '')}"
    _place_combo_legs(self, close_legs, strat)


def _close_ib_position(self, pos: dict):
    """IB reqPositions로 불러온 포지션 청산 — 단일 옵션 MKT 주문."""
    from PyQt5.QtWidgets import QMessageBox as _MB
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib:
        return

    strategy = pos.get("strategy", "")
    qty      = pos.get("qty", 1)
    side     = pos.get("side", "BUY")   # 보유 방향
    close_action = "SELL" if side == "BUY" else "BUY"
    current  = pos.get("current", pos.get("entry", 0))

    msg = (
        f"포지션 청산\n"
        f"─────────────────────────\n"
        f"종목:  {strategy}\n"
        f"수량:  {qty}계약\n"
        f"현재가:  ${current:.2f}\n"
        f"청산 방향:  {close_action}\n"
        f"─────────────────────────\n"
        f"시장가(MKT) 청산 주문을 전송하시겠습니까?"
    )
    dlg = _MB(self)
    dlg.setWindowTitle("🔴 포지션 청산")
    dlg.setText(msg)
    dlg.setStandardButtons(_MB.Ok | _MB.Cancel)
    dlg.button(_MB.Ok).setText("청산 전송")
    dlg.button(_MB.Cancel).setText("취소")
    if dlg.exec_() != _MB.Ok:
        return

    # ── IB 포지션에서 conId 추출 (저장해뒀다면) ─────────────────
    con_id = pos.get("con_id", 0)
    sym    = strategy.split()[0] if strategy else "SPX"

    from ibapi.contract import Contract
    from ibapi.order import Order as IbOrder

    if con_id:
        ct = Contract(); ct.conId = con_id; ct.exchange = "SMART"
    else:
        # conId 없으면 symbol만으로 시도 (TWS가 resolve)
        ct = Contract()
        ct.symbol   = sym; ct.secType  = "OPT"
        ct.exchange = "SMART"; ct.currency = "USD"

    oid = ib.get_next_id()
    if oid is None:
        return self._log("❌ nextOrderId 없음")

    ord_ = IbOrder()
    ord_.action        = close_action
    ord_.orderType     = "MKT"
    ord_.totalQuantity = qty
    ord_.tif           = "DAY"
    ord_.eTradeOnly    = False
    ord_.firmQuoteOnly = False
    ord_.transmit      = True

    try:
        ib.placeOrder(oid, ct, ord_)
        self._log(f"🔴 청산 주문 전송: OID={oid}  {close_action} {qty}계약  {strategy}")
    except Exception as e:
        self._log(f"❌ 청산 주문 오류: {e}")


def _init_synthetic_panel_callbacks(self):
    """synthetic_panel 콜백 연결 — 탭 초기화 시 1회 호출."""
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return
    panel.set_close_position_callback(
        lambda pos: _on_close_position_order(self, pos))
    panel.set_manual_modify_callback(
        lambda oid, price: _on_manual_modify(self, oid, price))
    panel.set_chaser_mode_callback(
        lambda mode: _on_chaser_mode_changed(self, mode))


def _on_manual_modify(self, oid: int, new_price: float):
    """수동 정정: 지정가 변경 후 placeOrder."""
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib:
        return
    bag = getattr(self, '_chaser_bag_contract', None)
    ibord = getattr(self, '_chaser_bag_order', None)
    if not bag or not ibord:
        return self._log("⚠ 수동 정정: 주문 객체 없음")
    from ibapi.order import Order as IbOrder
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
    """Chaser 자동/수동 모드 전환."""
    self._log(f"🎯 Chaser 모드 전환: {mode}")
    # combo_order_chaser의 자동 타이머 제어
    try:
        from combo_order_chaser import deactivate_chaser
        if mode == "manual":
            deactivate_chaser(self, reason="수동 모드 전환")
    except Exception:
        pass


def _on_pos_reconnect_hook(self):
    """재연결 후 IB 서버 포지션 조회 → 잔고 탭 갱신."""
    panel = getattr(self, 'synthetic_panel', None)
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    if not panel or not ib:
        return
    self._log("🔄 재연결: IB 포지션 재조회 중…")
    panel.clear_positions()
    _load_ib_positions(self)


def _load_ib_positions(self):
    """IB reqPositions → 합성 잔고 탭 재구성."""
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    panel = getattr(self, 'synthetic_panel', None)
    if not ib or not panel:
        return

    _buf = []

    def _on_pos(account, contract, pos, avg_cost):
        if abs(pos) < 0.001:
            return
        sec  = getattr(contract, 'secType', '')
        sym  = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
        right = getattr(contract, 'right', '')
        strike = getattr(contract, 'strike', 0)
        expiry = getattr(contract, 'lastTradeDateOrContractMonth', '')
        mult   = float(getattr(contract, 'multiplier', 100) or 100)
        if sec not in ('OPT', 'BAG', 'FOP'):
            return
        side = 'BUY' if pos > 0 else 'SELL'
        cp   = 'C' if right == 'C' else 'P'
        label = f"{cp}{int(strike)} ×{int(abs(pos))}"
        entry = avg_cost / mult if mult else avg_cost
        _buf.append({
            "strategy": f"{sym} {label}",
            "qty":      int(abs(pos)),
            "entry":    round(entry, 2),
            "current":  round(entry, 2),
            "side":     side,
            "legs":     [],          # IB 포지션은 레그 분해 불가 → TWS 청산 안내
        })

    def _on_pos_end():
        from PyQt5.QtCore import QTimer as _QT
        def _apply():
            for p in _buf:
                panel.add_position(p)
            if _buf:
                self._log(f"✅ IB 포지션 {len(_buf)}건 잔고 탭 반영")
            else:
                self._log("ℹ IB 옵션 포지션 없음")
        _QT.singleShot(0, _apply)
        # 콜백 복구
        try:
            ib.position    = ib._orig_pos
            ib.positionEnd = ib._orig_pos_end
        except Exception:
            pass

    ib._orig_pos     = getattr(ib, 'position',    lambda *a: None)
    ib._orig_pos_end = getattr(ib, 'positionEnd', lambda:    None)
    ib.position    = _on_pos
    ib.positionEnd = _on_pos_end

    try:
        ib.reqPositions()
    except Exception as e:
        self._log(f"❌ reqPositions 오류: {e}")


def _on_check_margin(self):
    """💰 증거금 조회 버튼 핸들러."""
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
    # 중복 요청 방지 — _whatif_in_progress 는 _send_whatif_order 내부에서 관리
    if getattr(self, '_whatif_in_progress', False):
        return
    strat    = self.combo_strat.currentText()
    cost_str = (self._kpi_widgets.get('cost',
                type('', (), {'text': lambda s: '―'})()).text()
                if hasattr(self, '_kpi_widgets') else "―")
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가·프리미엄·만기를 입력한 후 다시 시도하세요.")
    self._log("💰 whatIf 증거금 조회 요청 중...")
    _send_whatif_order(self, legs, strat, cost_str, on_done=None)


def _on_cancel_bag_order(self):
    """✕ 주문 취소 버튼 핸들러 — cancel_bag_order 위임."""
    cancel_bag_order(self)