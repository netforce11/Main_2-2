"""
combo_order_chaser.py — Smart Chaser v2.7
──────────────────────────────────────────
[FIX-C4-TIF] _modify_order(): TIF 하드코딩 "DAY" 제거
  기존: ibord.tif = "DAY" → 장외 시간 정정 주문 거절
  수정: _get_session_info() 로 현재 세션 TIF/outsideRth 동적 결정
       원래 주문과 동일한 tif/outsideRth 사용

[FIX-C5-SLEEP] register_chaser() — Sleep 자동매도 등록 시
  기존 활성 Chaser 있으면 먼저 deactivate 후 재등록
  → 두 주문 동시 추격 방지

[FIX-C6-CLOSE] 청산 주문은 Chaser 자동모드 적용 안 함
  register_chaser() 에 is_close=False 파라미터 추가
  is_close=True 이면 자동 타이머 시작 안 함

[FIX-C7-LOCK] _do_chase_with_price() 동시 호출 lock
  자동 타이머 + 수동 클릭 동시 실행 방지
──────────────────────────────────────────
"""

from __future__ import annotations
import math
import time
import threading
from typing import Optional
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

CHASE_INTERVAL_MS  = 4_000
CHASE_MAX_ATTEMPTS = 3
CHASE_MIN_TICK     = 0.05
CHASE_TICK_HIGH    = 0.10

# ── 옵션 호가 단위 (CBOE 기준) ────────────────────────────────
# Penny Pilot ($0.01/$0.05): XSP, AAPL, NVDA, AMZN, GOOGL, MSFT,
#   META, TSLA, AMD, INTC, BAC, GS, JPM, QQQ, SPY, IWM 등 주요 500종목
# 비Penny ($0.05/$0.10): SPX, VIX, NDX, RUT 등 지수 옵션
_PENNY_PILOT = {
    # 지수 ETF
    "XSP","SPY","QQQ","IWM","GLD","SLV","EEM","TLT","HYG","LQD",
    # 빅테크/반도체
    "AAPL","MSFT","NVDA","AMZN","GOOGL","GOOG","META","TSLA",
    "AMD","INTC","QCOM","AVGO","MU","AMAT","LRCX","KLAC",
    # 금융
    "BAC","JPM","GS","MS","WFC","C","BRK","BLK",
    # 기타 주요 종목
    "NFLX","DIS","UBER","LYFT","COIN","RBLX","SNAP","PLTR",
    "XOM","CVX","OXY","SLB","HAL",
}
_NON_PENNY = {
    # 지수 옵션 (비Penny — 틱 0.05/$0.10)
    "SPX","SPXW","NDX","VIX","RUT","RUTW","DJX",
}

# [FIX-C7-LOCK] 동시 chase 방지 락
_chase_lock = threading.Lock()


def _get_tick_size(price: float, symbol: str = "") -> float:
    """
    CBOE 공식 호가 단위 반환.
    Penny Pilot 종목: $3 미만=$0.01, $3 이상=$0.05
    비Penny(지수):   $3 미만=$0.05, $3 이상=$0.10
    미등록 심볼:      보수적으로 비Penny 적용
    """
    s = symbol.upper()
    if s in _PENNY_PILOT:
        return 0.01 if price < 3.0 else 0.05
    # 비Penny 또는 미등록 (SPX, VIX, NDX 포함)
    return CHASE_TICK_HIGH if price >= 3.0 else CHASE_MIN_TICK


def _snap_to_tick(price: float, tick: float, direction: str = "buy") -> float:
    if tick <= 0:
        return round(price, 2)
    inv = 1.0 / tick
    if direction == "sell":
        snapped = math.floor(price * inv) / inv
    else:
        snapped = math.ceil(price * inv) / inv
    decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    return round(snapped, decimals)


# ══════════════════════════════════════════════════════════════
# 상태 초기화
# ══════════════════════════════════════════════════════════════

def init_chaser_state(self) -> None:
    self._chaser_oid        = None
    self._chaser_price      = 0.0
    self._chaser_action     = "BUY"
    self._chaser_qty        = 1
    self._chaser_attempts   = 0
    self._chaser_timer      = None
    self._chaser_active     = False
    self._chaser_max_price  = 0.0
    self._chaser_auto_mode  = False
    self._chaser_is_close   = False   # [FIX-C6-CLOSE]
    self._chase_in_progress = False   # [FIX-C7-LOCK]


# ══════════════════════════════════════════════════════════════
# 등록 / 비활성화
# ══════════════════════════════════════════════════════════════

def register_chaser(self, oid: int, price: float, action: str,
                    qty: int = 1, max_slippage: float = 0.30,
                    is_close: bool = False) -> None:
    """
    BAG 주문 전송 직후 호출.
    [FIX-C5-SLEEP] 기존 활성 Chaser가 있으면 먼저 비활성화 (덮어쓰기 방지).
    [FIX-C6-CLOSE] is_close=True면 자동 타이머 시작 안 함.
    """
    # [FIX-C5-SLEEP] 기존 활성 Chaser 먼저 종료
    if getattr(self, '_chaser_active', False):
        _stop_auto_timer(self)
        self._log(
            f"⚠ [FIX-C5] 기존 Chaser(OID={self._chaser_oid}) 자동 종료 "
            f"→ 새 OID={oid} 등록")

    init_chaser_state(self)
    self._chaser_oid        = oid
    self._chaser_price      = price
    self._chaser_action     = action
    self._chaser_qty        = max(1, int(qty))
    self._chaser_attempts   = 0
    self._chaser_active     = True
    self._chaser_is_close   = is_close  # [FIX-C6-CLOSE]
    self._chase_in_progress = False

    _direction = "sell" if action.upper() == "SELL" else "buy"
    if action.upper() == "SELL":
        _cap_raw           = price - max_slippage
        _tick_for_cap      = _get_tick_size(_cap_raw)
        self._chaser_max_price = _snap_to_tick(_cap_raw, _tick_for_cap, "sell")
    else:
        _cap_raw           = price + max_slippage
        _tick_for_cap      = _get_tick_size(_cap_raw)
        self._chaser_max_price = _snap_to_tick(_cap_raw, _tick_for_cap, "buy")

    self._last_bag_oid = oid
    _update_chaser_ui(self, active=True)
    _update_cancel_ui(self, active=True)

    _mode_label = "자동" if _is_auto_mode(self) else "수동(OFF)"
    _close_label = " [청산]" if is_close else ""
    self._log(
        f"🎯 Chaser 등록: OID={oid}  ${price:.2f}"
        f"  action={action}  qty={self._chaser_qty}"
        f"  캡=${self._chaser_max_price:.2f}"
        f"  모드={_mode_label}{_close_label}"
    )

    # [FIX-C6-CLOSE] 청산 주문은 자동 모드 적용 안 함
    if _is_auto_mode(self) and not is_close:
        _start_auto_timer(self)


def deactivate_chaser(self, reason: str = "체결 완료") -> None:
    if not getattr(self, '_chaser_active', False):
        return
    _stop_auto_timer(self)
    self._chaser_active     = False
    self._chaser_oid        = None
    self._chaser_is_close   = False
    self._chase_in_progress = False
    _update_chaser_ui(self, active=False)
    _update_cancel_ui(self, active=False)
    self._log(f"🎯 Chaser 종료: {reason}")


# ══════════════════════════════════════════════════════════════
# 취소 주문
# ══════════════════════════════════════════════════════════════

def cancel_bag_order(self) -> None:
    oid = (getattr(self, '_chaser_oid', None)
           or getattr(self, '_last_bag_oid', None))
    if not oid:
        QMessageBox.information(self, "취소", "취소할 미체결 BAG 주문이 없습니다.")
        return
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
        return
    reply = QMessageBox.question(
        self, "✕ BAG 주문 취소",
        f"OID {oid} 합성 주문을 취소하시겠습니까?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply != QMessageBox.Yes:
        return
    try:
        self.mw.ib.cancelOrder(oid)
        self._log(f"✕ BAG 취소 전송: OID={oid}")
        panel = getattr(self, 'synthetic_panel', None)
        if panel and hasattr(panel, 'lbl_status'):
            panel.lbl_status.setText(f"✕ 취소 요청됨 (OID={oid})")
    except Exception as e:
        self._log(f"❌ BAG 취소 오류: {e}")
        QMessageBox.critical(self, "오류", f"취소 전송 실패: {e}")


def _update_cancel_ui(self, active: bool) -> None:
    btn = getattr(self, 'btn_cancel_bag', None)
    if not btn:
        return
    if active:
        oid = getattr(self, '_chaser_oid', None)
        btn.setText(f"✕ 취소 (OID={oid})" if oid else "✕ 주문 취소")
        btn.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff6666;font-size:12px;"
            "font-weight:bold;padding:4px 8px;border-radius:3px;"
            "border:1px solid #aa2222;}"
            "QPushButton:hover{background:#8b2a2a;}")
    else:
        btn.setText("✕ 주문 취소")
        btn.setStyleSheet(
            "QPushButton{background:#1a1a2a;color:#555;font-size:12px;"
            "font-weight:bold;padding:4px 8px;border-radius:3px;"
            "border:1px solid #333;}")


# ══════════════════════════════════════════════════════════════
# 수동 Chase 버튼
# ══════════════════════════════════════════════════════════════

def on_chase_click(self) -> None:
    if not self._chaser_active or self._chaser_oid is None:
        QMessageBox.information(self, "Chaser", "활성화된 미체결 주문이 없습니다.")
        return
    # [FIX-C7-LOCK] 이미 chase 진행 중이면 무시
    if getattr(self, '_chase_in_progress', False):
        self._log("⚠ Chaser: 이미 진행 중 — 수동 클릭 무시")
        return
    _do_chase(self, reason="수동")


# ══════════════════════════════════════════════════════════════
# 자동 모드 타이머
# ══════════════════════════════════════════════════════════════

def _start_auto_timer(self) -> None:
    _stop_auto_timer(self)
    t = QTimer(self)
    t.setSingleShot(False)
    t.setInterval(CHASE_INTERVAL_MS)
    t.timeout.connect(lambda: _auto_chase_tick(self))
    t.start()
    self._chaser_timer = t


def _stop_auto_timer(self) -> None:
    t = getattr(self, '_chaser_timer', None)
    if t and t.isActive():
        t.stop()
    self._chaser_timer = None


def _auto_chase_tick(self) -> None:
    if not self._chaser_active:
        _stop_auto_timer(self)
        return
    # [FIX-C7-LOCK] 이미 진행 중이면 스킵
    if getattr(self, '_chase_in_progress', False):
        self._log("⚠ Chaser 자동: 이전 chase 처리 중 — 이번 틱 스킵")
        return
    if self._chaser_attempts >= CHASE_MAX_ATTEMPTS:
        _stop_auto_timer(self)
        self._log(f"⚠ Chaser 최대 시도 횟수 도달 ({CHASE_MAX_ATTEMPTS}회)")
        _notify_user(self, f"Chaser: {CHASE_MAX_ATTEMPTS}회 후에도 미체결")
        deactivate_chaser(self, reason=f"최대 횟수({CHASE_MAX_ATTEMPTS}회) 초과")
        return
    _do_chase(self, reason="자동")


# ══════════════════════════════════════════════════════════════
# 1틱 정정 핵심 로직
# ══════════════════════════════════════════════════════════════

def _do_chase(self, reason: str = "") -> None:
    """
    [FIX-C7-LOCK] _chase_in_progress 플래그로 동시 실행 방지.
    [FIX-B8] _chaser_bag_contract None 체크를 진입부에서 통합 처리.
    [v2.5 L-A] price_tick_sig 구독 방식.
    """
    # [FIX-C7-LOCK]
    if getattr(self, '_chase_in_progress', False):
        return
    self._chase_in_progress = True

    # [FIX-B8] bag 유효성 단일 검증 — 이전 코드는 두 곳에서 중복 체크
    ib  = getattr(getattr(self, 'mw', None), 'ib', None)
    bag = getattr(self, '_chaser_bag_contract', None)

    mid = _read_mid_from_cache(self)
    if mid is not None:
        _do_chase_with_price(self, mid, reason)
        return

    if ib is None or bag is None:
        _do_chase_with_price(self, None, reason)
        return

    try:
        from call_put_tab.bridge_price_tick import subscribe as _sub
        from call_put_tab.bridge_price_tick import unsubscribe as _unsub
        _use_router = True
    except ImportError:
        _use_router = False

    result: dict = {}
    _done = [False]

    def _cleanup():
        if _use_router:
            try:
                _unsub(_on_tick)
            except Exception:
                pass
        try:
            ib.cancelMktData(_CHASE_TICKER_ID)
        except Exception:
            pass

    def _on_tick(req_id: int, tick_type: int, price: float) -> None:
        if req_id != _CHASE_TICKER_ID:
            return
        if tick_type not in (1, 2) or price <= 0:
            return
        result[tick_type] = price
        if 1 in result and 2 in result and not _done[0]:
            _done[0] = True
            _cleanup()
            _raw_mid   = (result[1] + result[2]) / 2
            # [XSP-FIX] bag 심볼 전달로 XSP $0.01 틱 올바르게 적용
            _bag_sym_a = getattr(getattr(self, '_chaser_bag_contract', None), 'symbol', '')
            _tick_s    = _get_tick_size(_raw_mid, _bag_sym_a)
            _direction = "sell" if getattr(self, '_chaser_action', 'BUY').upper() == "SELL" else "buy"
            mid_val    = _snap_to_tick(_raw_mid, _tick_s, _direction)
            QTimer.singleShot(0, lambda: _do_chase_with_price(self, mid_val, reason))

    def _on_timeout() -> None:
        if _done[0]:
            return
        _done[0] = True
        _cleanup()
        _do_chase_with_price(self, None, reason)

    if _use_router:
        _sub(_on_tick, req_ids={_CHASE_TICKER_ID})
    else:
        _orig = getattr(ib, 'tickPrice', lambda *a: None)

        def _on_tick_legacy(req_id, tick_type, price, attrib=None):
            try:
                _orig(req_id, tick_type, price) if attrib is None \
                    else _orig(req_id, tick_type, price, attrib)
            except Exception:
                pass
            _on_tick(req_id, tick_type, price)

        ib.tickPrice = _on_tick_legacy
        original_cleanup = _cleanup

        def _cleanup():  # noqa: F811
            try:
                ib.tickPrice = _orig
            except Exception:
                pass
            original_cleanup()

    try:
        ib.reqMktData(_CHASE_TICKER_ID, bag, "", True, False, [])
        QTimer.singleShot(500, _on_timeout)
    except Exception:
        _cleanup()
        _do_chase_with_price(self, None, reason)


def _do_chase_with_price(self, mid: Optional[float], reason: str) -> None:
    """Mid price로 실제 정정 주문. 완료 후 _chase_in_progress 해제."""
    try:
        _bag       = getattr(self, '_chaser_bag_contract', None)
        _sym       = _bag.symbol if _bag is not None else ""
        _action    = self._chaser_action.upper()
        _direction = "sell" if _action == "SELL" else "buy"
        tick       = _get_tick_size(self._chaser_price, _sym)

        if mid is not None and mid > 0:
            if _action == "SELL":
                new_price = _snap_to_tick(mid - tick, tick, "sell")
            else:
                new_price = _snap_to_tick(mid + tick, tick, "buy")
            self._log(
                f"   ↳ Mid=${mid:.2f} {'−' if _action == 'SELL' else '+'} "
                f"1틱(${tick}) = ${new_price:.2f}")
        else:
            if _action == "SELL":
                new_price = _snap_to_tick(self._chaser_price - tick, tick, "sell")
            else:
                new_price = _snap_to_tick(self._chaser_price + tick, tick, "buy")
            self._log(
                f"   ↳ Mid unavailable → fallback: ${self._chaser_price:.2f}"
                f" {'−' if _action == 'SELL' else '+'} tick=${tick}"
                f" = ${new_price:.2f}")

        cap     = self._chaser_max_price
        cap_hit = (new_price < cap) if _action == "SELL" else (new_price > cap)
        if cap_hit:
            self._log(
                f"⚠ Chaser 캡 도달 ${cap:.2f} → 추격 중지"
                f"  (요청가=${new_price:.2f}  방향={_action})")
            deactivate_chaser(self, reason="가격 캡 도달")
            return

        self._chaser_price    = new_price
        self._chaser_attempts += 1
        self._log(
            f"🎯 Chaser [{reason}] #{self._chaser_attempts}: "
            f"OID={self._chaser_oid}  → ${new_price:.2f}  ({_action})")
        _modify_order(self, self._chaser_oid, new_price)
        _update_chaser_ui(self, active=True)
    finally:
        # [FIX-C7-LOCK] 항상 해제
        self._chase_in_progress = False


# ══════════════════════════════════════════════════════════════
# Mid Price 캐시
# ══════════════════════════════════════════════════════════════

_TICKER_BASE     = 8800
_CHASE_TICKER_ID = 8799


def _read_mid_from_cache(self) -> Optional[float]:
    mid_ticks: dict = getattr(self, '_mid_ticks', {})
    for tid in range(_TICKER_BASE + 15, _TICKER_BASE - 1, -1):
        entry = mid_ticks.get(tid)
        if entry:
            bid = entry.get(1)
            ask = entry.get(2)
            if bid and ask and bid > 0 and ask > 0:
                raw_mid    = (bid + ask) / 2
                # [XSP-FIX] bag 심볼 전달
                _bag_sym_b = getattr(getattr(self, '_chaser_bag_contract', None), 'symbol', '')
                tick       = _get_tick_size(raw_mid, _bag_sym_b)
                _direction = "sell" if getattr(self, '_chaser_action', 'BUY').upper() == "SELL" else "buy"
                return _snap_to_tick(raw_mid, tick, _direction)
    return None


def _modify_order(self, oid: int, new_price: float) -> None:
    """
    동일 OID placeOrder 재호출 = IBKR 정정.
    [FIX-C4-TIF] tif/outsideRth 을 현재 세션에 맞게 동적 결정
    """
    bag = getattr(self, '_chaser_bag_contract', None)
    if bag is None:
        self._log(f"❌ 정정 취소: _chaser_bag_contract 없음 (OID={oid})")
        return

    try:
        from ibapi.order import Order as IbOrder
        # [FIX-C4-TIF] 하드코딩 "DAY" → 현재 세션 TIF 사용
        from combo_order_logic import _get_session_info
        _, _, tif, outside_rth = _get_session_info()

        ib = self.mw.ib
        ibord               = IbOrder()
        ibord.action        = self._chaser_action
        ibord.orderType     = "LMT"
        ibord.totalQuantity = getattr(self, '_chaser_qty', 1)
        ibord.lmtPrice      = new_price
        ibord.tif           = tif            # [FIX-C4-TIF]
        ibord.outsideRth    = outside_rth    # [FIX-C4-TIF]
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True

        ib.placeOrder(oid, bag, ibord)
        self._log(
            f"   ↳ 정정 전송: OID={oid}"
            f"  lmtPrice=${new_price:.2f}"
            f"  qty={ibord.totalQuantity}"
            f"  tif={tif}  outsideRth={outside_rth}")
    except Exception as e:
        self._log(f"❌ 정정 주문 오류: {e}")


# ══════════════════════════════════════════════════════════════
# UI 헬퍼
# ══════════════════════════════════════════════════════════════

def _is_auto_mode(self) -> bool:
    rb = getattr(self, '_rb_chaser_auto', None)
    if rb is not None:
        return rb.isChecked()
    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'is_auto_chaser'):
        return panel.is_auto_chaser()
    return getattr(self, '_chaser_auto_mode', False)


def ensure_chaser_auto_off(self) -> None:
    rb = getattr(self, '_rb_chaser_auto', None)
    if rb is not None:
        rb.setChecked(False)
    rb_manual = getattr(self, '_rb_chaser_manual', None)
    if rb_manual is not None:
        rb_manual.setChecked(True)
    panel = getattr(self, 'synthetic_panel', None)
    if panel:
        rb2 = getattr(panel, '_rb_chaser_auto', None)
        if rb2 is not None:
            rb2.setChecked(False)
        rb2_m = getattr(panel, '_rb_chaser_manual', None)
        if rb2_m is not None:
            rb2_m.setChecked(True)
    self._chaser_auto_mode = False


def _update_chaser_ui(self, active: bool) -> None:
    btn = getattr(self, 'btn_chase', None)
    if not btn:
        return
    if active:
        attempts = getattr(self, '_chaser_attempts', 0)
        price    = getattr(self, '_chaser_price', 0.0)
        btn.setText(f"🎯 Chase ({attempts}회  ${price:.2f})")
        btn.setEnabled(not _is_auto_mode(self))
    else:
        btn.setText("🎯 Chase")
        btn.setEnabled(True)


def _notify_user(self, msg: str) -> None:
    try:
        QMessageBox.warning(self, "Chaser 알림", msg)
    except Exception:
        self._log(f"[Chaser 알림] {msg}")
