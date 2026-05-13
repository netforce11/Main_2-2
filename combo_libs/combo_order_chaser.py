"""
combo_order_chaser.py — Smart Chaser (체결 추격 주문) + 취소 주문 로직  v2.6
──────────────────────────────────────────────────────────────────────────────
변경 (v2.6):
  [FIX-C1] 자동 모드 기본값 OFF
    · init_chaser_state(): _chaser_auto_mode = False 추가
    · _is_auto_mode(): _rb_chaser_auto / panel 모두 없을 때 False 반환 (기존과 동일하나 명시)
    · _rb_chaser_auto 가 있으면 최초 1회 setChecked(False) 보장
      → ensure_chaser_auto_off(self) 함수 추가
      → 이 함수를 UI 빌드 완료 시점(combo_ui_chaser_row 등)에서 호출하면 됨
    · register_chaser() 로그에 현재 모드(수동/자동) 표시 추가

  [FIX-C2] 매도 Chaser cap 방향 수정
    · 기존: action 무관 price + max_slippage (위쪽 cap) → 매도 정정 시 절대 안 걸림
    · 수정: SELL → price - max_slippage (아래쪽 cap)
            BUY  → price + max_slippage (위쪽 cap, 기존 동일)

  [FIX-C3] _do_chase_with_price() cap 체크 방향 수정
    · 기존: new_price > cap (매수/매도 구분 없이 동일 비교 → 매도 cap 무의미)
    · 수정: SELL → new_price < cap 이면 중지
            BUY  → new_price > cap 이면 중지

  [FIX-C4] _do_chase_with_price() 매도 정정 방향 수정
    · 기존: mid + tick (매수/매도 동일 → 매도인데 가격이 올라감)
    · 수정: SELL → mid - tick (체결 유리하게 낮춤)
            BUY  → mid + tick (체결 유리하게 높임, 기존 동일)

──────────────────────────────────────────────────────────────────────────────
변경 (v2.5):
  [L-A] tickPrice 직접 덮어쓰기 제거 — 중앙 라우터 구독 방식으로 전환
    · _do_chase(): ib.tickPrice = _on_tick 제거
    · price_tick_sig.connect(_on_tick, {_CHASE_TICKER_ID}) 로 대체
    · Bid/Ask 수신 완료 또는 타임아웃 시 price_tick_sig.disconnect(_on_tick)
    · _restore() 함수 불필요 — 삭제
    · 동시 실행 / 예외 발생 시에도 다른 모듈 시세 수신에 영향 없음

변경 (v2.4):
  [BUG #TICK] 소수점 정밀도 수정 — _snap_to_tick() 함수 추가
──────────────────────────────────────────────────────────────────────────────
변경 (v2.3):
  [BUG #5] _fetch_mid_price_sync(): QTimer 콜백(자동 추격) 안에서
    QEventLoop.exec_()를 호출하면 중첩 이벤트 루프가 생겨 UI 프리즈/
    Qt 내부 이벤트 처리 불일치 위험이 있었음.
    → QEventLoop 제거. 비동기 방식으로 교체:
      reqMktData 요청 후 별도 QTimer(500ms)로 결과 확인.
      Mid price가 있으면 _do_chase_with_price() 호출,
      없으면 현재 chaser_price 기반 fallback 사용.
    → _do_chase()를 _do_chase_async()로 분리해 비동기 흐름 지원.
──────────────────────────────────────────────────────────────────────────────
변경 (v2.2):
  - CHASE_INTERVAL_MS: 5초 → 4초
  - Mid 조회 타임아웃: 0.3초 → 0.5초
  - _fetch_mid_price_sync(): reqId 필터링 방식으로 교체
──────────────────────────────────────────────────────────────────────────────
변경 (v2.1):
  - register_chaser()에 qty 파라미터 추가 → _chaser_qty 저장
  - _modify_order() totalQuantity 하드코딩(1) → _chaser_qty 사용
  - _modify_order() _chaser_bag_contract None 시 조기 리턴 + 에러 로그
  - cancel_bag_order() deactivate_chaser 즉시 호출 제거
    → orderStatus "Cancelled" 콜백(combo_order_callbacks)에서 처리
──────────────────────────────────────────────────────────────────────────────
수동 모드 : Chase 버튼 클릭 시 1틱 개선 후 정정 주문
자동 모드 : 미체결 N초 후 자동으로 1틱 개선 (최대 횟수 제한)
취소      : cancel_bag_order(oid) → cancelOrder 전송
            실제 비활성화는 orderStatus "Cancelled" 콜백에서 수행
──────────────────────────────────────────────────────────────────────────────
Python 3.8 호환
"""

from __future__ import annotations
import math
import time
from typing import Optional
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox


# ── 상수 ────────────────────────────────────────────────────────
CHASE_INTERVAL_MS  = 4_000   # ★ v2.2: 5초 → 4초 (문서 기준 통일, bag.py 접수확인 4초와 일치)
CHASE_MAX_ATTEMPTS = 3
CHASE_MIN_TICK     = 0.05
CHASE_TICK_HIGH    = 0.10

# ★ XSP 등 $0.01 틱 종목 목록
_PENNY_TICK_SYMBOLS = {"XSP"}


def _get_tick_size(price: float, symbol: str = "") -> float:
    """
    종목 우선으로 틱 사이즈 결정.
      XSP 등 페니 틱 종목 → 무조건 $0.01
      그 외 → 가격대 기준: $3.00 미만=$0.05 / $3.00 이상=$0.10
    """
    if symbol.upper() in _PENNY_TICK_SYMBOLS:
        return 0.01
    return CHASE_TICK_HIGH if price >= 3.0 else CHASE_MIN_TICK


def _snap_to_tick(price: float, tick: float, direction: str = "buy") -> float:
    """
    [v2.4] 계산된 가격을 틱 사이즈 배수로 스냅.

    IBKR은 SPX 등 인덱스 옵션에서 $0.01 단위 가격을 Invalid Order Price로
    거절합니다. 이 함수는 price를 tick 배수의 가장 가까운 값으로 올림(매수)
    또는 내림(매도) 처리하여 IBKR 규정에 맞는 가격을 반환합니다.

    Args:
        price     : 원본 계산 가격
        tick      : 틱 사이즈 (0.01 / 0.05 / 0.10)
        direction : "buy"  → 올림 (ceil) — 추격 매수가 높아지는 방향
                    "sell" → 내림 (floor) — 추격 매도가 낮아지는 방향

    Returns:
        tick 배수로 정렬된 가격 (소수점 오차 제거)

    Examples:
        _snap_to_tick(5.123, 0.10, "buy")  → 5.20
        _snap_to_tick(5.123, 0.10, "sell") → 5.10
        _snap_to_tick(2.031, 0.05, "buy")  → 2.05
        _snap_to_tick(0.047, 0.01, "buy")  → 0.05
    """
    if tick <= 0:
        return round(price, 2)
    # 부동소수점 오차 방지: 1/tick 배율로 정수 연산 후 복원
    inv = 1.0 / tick
    if direction == "sell":
        snapped = math.floor(price * inv) / inv
    else:
        snapped = math.ceil(price * inv) / inv
    # 최종 소수점 정리 (tick 소수점 자리수 기준)
    decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    return round(snapped, decimals)


# ══════════════════════════════════════════════════════════════
# 상태 초기화
# ══════════════════════════════════════════════════════════════

def init_chaser_state(self) -> None:
    self._chaser_oid       = None
    self._chaser_price     = 0.0
    self._chaser_action    = "BUY"
    self._chaser_qty       = 1          # ★ v2.1: 수량 저장
    self._chaser_attempts  = 0
    self._chaser_timer     = None
    self._chaser_active    = False
    self._chaser_max_price = 0.0
    # [FIX-C1] 자동 모드 기본값 OFF — 사용자가 명시적으로 켤 때만 동작
    self._chaser_auto_mode = False


# ══════════════════════════════════════════════════════════════
# 등록 / 비활성화
# ══════════════════════════════════════════════════════════════

def register_chaser(self, oid: int, price: float, action: str,
                    qty: int = 1,               # ★ v2.1: qty 파라미터 추가
                    max_slippage: float = 0.30) -> None:
    """
    BAG 주문 전송 직후 호출.
    qty : 원래 주문 수량 (정정 시 동일 수량 유지에 사용)
    """
    init_chaser_state(self)
    self._chaser_oid       = oid
    self._chaser_price     = price
    self._chaser_action    = action
    self._chaser_qty       = max(1, int(qty))   # ★ v2.1
    self._chaser_attempts  = 0
    self._chaser_active    = True

    # [FIX-C2] cap 방향을 action 에 맞게 설정
    # SELL: 가격이 낮아지는 방향 → price - max_slippage (아래쪽 캡)
    # BUY : 가격이 높아지는 방향 → price + max_slippage (위쪽 캡, 기존 동일)
    _direction = "sell" if action.upper() == "SELL" else "buy"
    if action.upper() == "SELL":
        _cap_raw           = price - max_slippage
        _tick_for_cap      = _get_tick_size(_cap_raw)
        self._chaser_max_price = _snap_to_tick(_cap_raw, _tick_for_cap, "sell")
    else:
        _cap_raw           = price + max_slippage
        _tick_for_cap      = _get_tick_size(_cap_raw)
        self._chaser_max_price = _snap_to_tick(_cap_raw, _tick_for_cap, "buy")

    self._last_bag_oid     = oid

    _update_chaser_ui(self, active=True)
    _update_cancel_ui(self, active=True)

    _mode_label = "자동" if _is_auto_mode(self) else "수동(OFF)"
    self._log(
        f"🎯 Chaser 등록: OID={oid}  가격=${price:.2f}"
        f"  action={action}  qty={self._chaser_qty}"
        f"  캡=${self._chaser_max_price:.2f}  모드={_mode_label}"
    )

    if _is_auto_mode(self):
        _start_auto_timer(self)


def deactivate_chaser(self, reason: str = "체결 완료") -> None:
    """
    Chaser 비활성화.
    취소의 경우 orderStatus "Cancelled" 콜백에서 호출되므로
    cancel_bag_order()는 더 이상 직접 호출하지 않는다.
    """
    if not getattr(self, '_chaser_active', False):
        return
    _stop_auto_timer(self)
    self._chaser_active = False
    self._chaser_oid    = None
    _update_chaser_ui(self, active=False)
    _update_cancel_ui(self, active=False)
    self._log(f"🎯 Chaser 종료: {reason}")


# ══════════════════════════════════════════════════════════════
# 취소 주문
# ══════════════════════════════════════════════════════════════

def cancel_bag_order(self) -> None:
    """
    ✕ BAG 주문 취소 버튼 핸들러.
    cancelOrder 전송만 수행.
    실제 deactivate_chaser 는 orderStatus "Cancelled"
    콜백(combo_order_callbacks._on_order_status)에서 처리.
    """
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
        self._log(f"✕ BAG 취소 전송: OID={oid}  (확인은 orderStatus 콜백 대기 중)")
        # ★ v2.1: deactivate_chaser 여기서 호출하지 않음
        #   → combo_order_callbacks._on_order_status("Cancelled") 에서 처리
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
    _do_chase(self, reason="수동")


# ══════════════════════════════════════════════════════════════
# 자동 모드 타이머
# ══════════════════════════════════════════════════════════════

def _start_auto_timer(self) -> None:
    _stop_auto_timer(self)
    # [FIX-C5] QTimer 부모(self) 지정 — 부모 없으면 GC가 수집해 타이머 즉시 중단됨
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
    if self._chaser_attempts >= CHASE_MAX_ATTEMPTS:
        _stop_auto_timer(self)
        self._log(
            f"⚠ Chaser 최대 시도 횟수 도달 ({CHASE_MAX_ATTEMPTS}회) → 자동 중지")
        _notify_user(
            self, f"Chaser: {CHASE_MAX_ATTEMPTS}회 추격 후에도 미체결\n주문을 확인하세요.")
        deactivate_chaser(self, reason=f"최대 횟수({CHASE_MAX_ATTEMPTS}회) 초과")
        return
    _do_chase(self, reason="자동")


# ══════════════════════════════════════════════════════════════
# 1틱 정정 핵심 로직
# ══════════════════════════════════════════════════════════════

def _do_chase(self, reason: str = "") -> None:
    """
    [v2.5 L-A] ib.tickPrice 덮어쓰기 제거 → price_tick_sig 구독 방식.

    기존: ib.tickPrice = _on_tick  (전역 슬롯 독점 → 예외 시 전체 시세 마비)
    수정: price_tick_sig.connect(_on_tick, {_CHASE_TICKER_ID})
          → Bid/Ask 수신 완료 또는 타임아웃 시 disconnect

    흐름:
      1) 캐시(_mid_ticks)에 유효한 bid/ask 있으면 즉시 사용
      2) 없으면 reqMktData(_CHASE_TICKER_ID) 전송
         price_tick_sig 에서 해당 reqId 틱만 수신
         → Bid + Ask 둘 다 오면 Mid 계산 → _do_chase_with_price()
         → 500ms 타임아웃 시 fallback (현재 chaser_price + tick)
    """
    mid = _read_mid_from_cache(self)
    if mid is not None:
        _do_chase_with_price(self, mid, reason)
        return

    ib  = getattr(getattr(self, 'mw', None), 'ib', None)
    bag = getattr(self, '_chaser_bag_contract', None)
    if ib is None or bag is None:
        _do_chase_with_price(self, None, reason)
        return

    # [L-A] price_tick_sig 구독 방식
    try:
        from call_put_tab.bridge_price_tick import subscribe as _sub
        from call_put_tab.bridge_price_tick import unsubscribe as _unsub
        _use_router = True
    except ImportError:
        _use_router = False

    result: dict = {}
    _done = [False]

    def _cleanup():
        """구독 해제 + 시세 취소 — 항상 안전하게 수행."""
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
        """price_tick_sig 콜백 — _CHASE_TICKER_ID 의 Bid/Ask만 처리."""
        if req_id != _CHASE_TICKER_ID:
            return
        if tick_type not in (1, 2) or price <= 0:
            return
        result[tick_type] = price
        if 1 in result and 2 in result and not _done[0]:
            _done[0] = True
            _cleanup()
            _raw_mid   = (result[1] + result[2]) / 2
            _tick_s    = _get_tick_size(_raw_mid)
            _direction = "sell" if getattr(self, '_chaser_action', 'BUY').upper() == "SELL" else "buy"
            mid_val    = _snap_to_tick(_raw_mid, _tick_s, _direction)
            QTimer.singleShot(0, lambda: _do_chase_with_price(self, mid_val, reason))

    def _on_timeout() -> None:
        if _done[0]:
            return
        _done[0] = True
        _cleanup()
        _do_chase_with_price(self, None, reason)

    # 구독 등록 (router 없으면 직접 덮어쓰기 폴백)
    if _use_router:
        _sub(_on_tick, req_ids={_CHASE_TICKER_ID})
    else:
        # bridge_price_tick 임포트 불가 시 기존 방식으로 폴백 (호환성)
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
    """Mid price(또는 None)를 받아 실제 정정 주문 수행."""
    _bag       = getattr(self, '_chaser_bag_contract', None)
    _sym       = _bag.symbol if _bag is not None else ""
    _action    = self._chaser_action.upper()
    _direction = "sell" if _action == "SELL" else "buy"
    tick       = _get_tick_size(self._chaser_price, _sym)

    if mid is not None and mid > 0:
        # [FIX-C4] 방향에 따라 가격 조정
        # SELL: mid - tick (낮춰서 체결 유리하게)
        # BUY : mid + tick (높여서 체결 유리하게)
        if _action == "SELL":
            new_price = _snap_to_tick(mid - tick, tick, "sell")
        else:
            new_price = _snap_to_tick(mid + tick, tick, "buy")
        self._log(
            f"   ↳ Mid=${mid:.2f} {'−' if _action == 'SELL' else '+'} "
            f"1틱(${tick}) = ${new_price:.2f}  [틱스냅 적용]")
    else:
        # fallback: 현재 chaser_price 에서 1틱 개선
        if _action == "SELL":
            new_price = _snap_to_tick(self._chaser_price - tick, tick, "sell")
        else:
            new_price = _snap_to_tick(self._chaser_price + tick, tick, "buy")
        self._log(
            f"   ↳ Mid unavailable → fallback: ${self._chaser_price:.2f}"
            f" {'−' if _action == 'SELL' else '+'} tick ${tick}"
            f" = ${new_price:.2f}  [틱스냅 적용]")

    # [FIX-C3] cap 체크 방향 수정
    # SELL: new_price 가 cap(아래쪽) 보다 낮아지면 중지
    # BUY : new_price 가 cap(위쪽) 보다 높아지면 중지
    cap = self._chaser_max_price
    cap_hit = (new_price < cap) if _action == "SELL" else (new_price > cap)
    if cap_hit:
        self._log(
            f"⚠ Chaser 가격 캡 도달 ${cap:.2f} → 추격 중지"
            f"  (요청가=${new_price:.2f}  방향={_action})")
        deactivate_chaser(self, reason="가격 캡 도달")
        return

    self._chaser_price    = new_price
    self._chaser_attempts += 1
    self._log(
        f"🎯 Chaser [{reason}] #{self._chaser_attempts}: "
        f"OID={self._chaser_oid}  가격 → ${new_price:.2f}  ({_action} 1틱{tick})")
    _modify_order(self, self._chaser_oid, new_price)
    _update_chaser_ui(self, active=True)


# ══════════════════════════════════════════════════════════════
# Mid Price 캐시 조회
# ══════════════════════════════════════════════════════════════

_TICKER_BASE     = 8800
_CHASE_TICKER_ID = 8799


def _read_mid_from_cache(self) -> Optional[float]:
    """
    캐시(_mid_ticks 8800-8815)에서 유효한 bid/ask를 찾아 mid 반환.
    없으면 None.
    [v2.4] 반환 mid도 틱 단위로 스냅하여 후속 계산 정확도 보장.
    """
    mid_ticks: dict = getattr(self, '_mid_ticks', {})
    for tid in range(_TICKER_BASE + 15, _TICKER_BASE - 1, -1):
        entry = mid_ticks.get(tid)
        if entry:
            bid = entry.get(1)
            ask = entry.get(2)
            if bid and ask and bid > 0 and ask > 0:
                raw_mid    = (bid + ask) / 2
                tick       = _get_tick_size(raw_mid)
                _direction = "sell" if getattr(self, '_chaser_action', 'BUY').upper() == "SELL" else "buy"
                return _snap_to_tick(raw_mid, tick, _direction)
    return None

def _modify_order(self, oid: int, new_price: float) -> None:
    """
    동일 OID placeOrder 재호출 = IBKR 정정.

    ★ v2.1 변경사항:
      - _chaser_bag_contract None 시 조기 리턴 (oid 정수 전달 버그 방지)
      - totalQuantity = self._chaser_qty (하드코딩 1 제거)
    """
    bag = getattr(self, '_chaser_bag_contract', None)
    if bag is None:
        self._log(
            f"❌ 정정 취소: _chaser_bag_contract 없음 (OID={oid})")
        return

    try:
        from ibapi.order import Order as IbOrder
        ib = self.mw.ib

        ibord = IbOrder()
        ibord.action        = self._chaser_action
        ibord.orderType     = "LMT"
        ibord.totalQuantity = getattr(self, '_chaser_qty', 1)  # ★ v2.1
        ibord.lmtPrice      = new_price
        ibord.tif           = "DAY"
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True

        ib.placeOrder(oid, bag, ibord)
        self._log(
            f"   ↳ 정정 주문 전송: OID={oid}"
            f"  lmtPrice=${new_price:.2f}"
            f"  qty={ibord.totalQuantity}")
    except Exception as e:
        self._log(f"❌ 정정 주문 오류: {e}")


# ══════════════════════════════════════════════════════════════
# UI 헬퍼
# ══════════════════════════════════════════════════════════════

def _is_auto_mode(self) -> bool:
    # [FIX-C1] 우선순위: UI 라디오버튼 → panel → _chaser_auto_mode(기본 False)
    rb = getattr(self, '_rb_chaser_auto', None)
    if rb is not None:
        return rb.isChecked()
    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'is_auto_chaser'):
        return panel.is_auto_chaser()
    # UI가 없을 때 내부 상태값 사용 (기본 False)
    return getattr(self, '_chaser_auto_mode', False)


def ensure_chaser_auto_off(self) -> None:
    """
    [FIX-C1] 프로그램 시작 / UI 빌드 완료 후 호출.
    자동 모드 라디오버튼을 강제로 OFF 상태로 초기화.
    combo_ui_chaser_row.py 또는 SyntheticStatusPanel.__init__ 에서
    UI 위젯 생성 직후 호출하면 됨:
        from combo_order_chaser import ensure_chaser_auto_off
        ensure_chaser_auto_off(self)
    """
    rb = getattr(self, '_rb_chaser_auto', None)
    if rb is not None:
        rb.setChecked(False)
    rb_manual = getattr(self, '_rb_chaser_manual', None)
    if rb_manual is not None:
        rb_manual.setChecked(True)
    # panel 경로
    panel = getattr(self, 'synthetic_panel', None)
    if panel:
        rb2 = getattr(panel, '_rb_chaser_auto', None)
        if rb2 is not None:
            rb2.setChecked(False)
        rb2_m = getattr(panel, '_rb_chaser_manual', None)
        if rb2_m is not None:
            rb2_m.setChecked(True)
    # 내부 상태도 초기화
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