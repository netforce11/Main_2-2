"""
combo_order_chaser.py — Smart Chaser (체결 추격 주문) 로직
──────────────────────────────────────────────────────────
수동 모드 : Chase 버튼 클릭 시 1틱 개선 후 정정 주문
자동 모드 : 미체결 N초 후 자동으로 1틱 개선 (최대 횟수 제한)
──────────────────────────────────────────────────────────
"""

import time
from typing import Optional
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

# ── 상수 ───────────────────────────────────────────────────────
CHASE_INTERVAL_MS  = 5_000   # 자동 모드: 미체결 감지 후 재시도 간격 (5초)
CHASE_MAX_ATTEMPTS = 3       # 자동 모드: 최대 추격 횟수
CHASE_MIN_TICK     = 0.05    # 기본 1틱 크기 (Penny Pilot 아닌 종목)
CHASE_TICK_HIGH    = 0.10    # 프리미엄 $3 이상 종목 틱


def _get_tick_size(price: float) -> float:
    """프리미엄 가격에 따른 틱 크기 반환."""
    return CHASE_TICK_HIGH if price >= 3.0 else CHASE_MIN_TICK


# ── Chaser 상태 초기화 ──────────────────────────────────────────

def init_chaser_state(self):
    """Chaser 관련 인스턴스 변수 초기화. __init__ 또는 _build_right_panel 끝에서 호출."""
    self._chaser_oid       = None    # 추적 중인 주문 ID
    self._chaser_price     = 0.0     # 현재 주문 가격
    self._chaser_action    = "BUY"   # BUY / SELL
    self._chaser_attempts  = 0       # 자동 시도 횟수
    self._chaser_timer     = None    # 자동 모드 QTimer
    self._chaser_active    = False   # Chaser 활성 여부
    self._chaser_max_price = 0.0     # 최대 허용 가격 (캡)


# ── 외부 진입점: BAG 주문 전송 후 Chaser 등록 ─────────────────

def register_chaser(self, oid: int, price: float, action: str, max_slippage: float = 0.30):
    """
    BAG 주문 전송 직후 호출.
    price       : lmtPrice 최초값
    max_slippage: 허용 최대 가격 이탈 (기본 $0.30)
    """
    init_chaser_state(self)
    self._chaser_oid      = oid
    self._chaser_price    = price
    self._chaser_action   = action
    self._chaser_attempts = 0
    self._chaser_active   = True
    self._chaser_max_price = round(price + max_slippage, 2)

    _update_chaser_ui(self, active=True)
    self._log(f"🎯 Chaser 등록: OID={oid}  가격=${price:.2f}  캡=${self._chaser_max_price:.2f}")

    # 자동 모드이면 타이머 즉시 시작
    if _is_auto_mode(self):
        _start_auto_timer(self)


def deactivate_chaser(self, reason: str = "체결 완료"):
    """Chaser 비활성화 (체결 완료 / 취소 시 호출)."""
    if not self._chaser_active:
        return
    _stop_auto_timer(self)
    self._chaser_active = False
    self._chaser_oid    = None
    _update_chaser_ui(self, active=False)
    self._log(f"🎯 Chaser 종료: {reason}")


# ── 수동 모드: Chase 버튼 클릭 ────────────────────────────────

def on_chase_click(self):
    """수동 Chase 버튼 클릭 핸들러."""
    if not self._chaser_active or self._chaser_oid is None:
        return QMessageBox.information(self, "Chaser", "활성화된 미체결 주문이 없습니다.")
    _do_chase(self, reason="수동")


# ── 자동 모드 타이머 ─────────────────────────────────────────

def _start_auto_timer(self):
    _stop_auto_timer(self)
    t = QTimer()
    t.setSingleShot(False)
    t.setInterval(CHASE_INTERVAL_MS)
    t.timeout.connect(lambda: _auto_chase_tick(self))
    t.start()
    self._chaser_timer = t


def _stop_auto_timer(self):
    t = getattr(self, '_chaser_timer', None)
    if t and t.isActive():
        t.stop()
    self._chaser_timer = None


def _auto_chase_tick(self):
    """자동 모드 타이머 콜백."""
    if not self._chaser_active:
        return _stop_auto_timer(self)
    if self._chaser_attempts >= CHASE_MAX_ATTEMPTS:
        _stop_auto_timer(self)
        self._log(f"⚠ Chaser 최대 시도 횟수 도달 ({CHASE_MAX_ATTEMPTS}회) → 자동 중지")
        _notify_user(self, f"Chaser: {CHASE_MAX_ATTEMPTS}회 추격 후에도 미체결\n주문을 확인하세요.")
        deactivate_chaser(self, reason=f"최대 횟수({CHASE_MAX_ATTEMPTS}회) 초과")
        return
    _do_chase(self, reason="자동")


# ── 실제 1틱 개선 로직 ─────────────────────────────────────────

def _do_chase(self, reason: str = ""):
    """
    정정 가격 = 현재 시장 Mid price + 1호가(틱).
    Mid price 조회 가능 시 사용, 실패 시 마지막 주문가 + 1틱으로 폴백.
    """
    tick = _get_tick_size(self._chaser_price)

    # ── Mid price 실시간 조회 시도 ─────────────────────────────
    mid = _fetch_mid_price_sync(self)
    if mid is not None and mid > 0:
        # Mid + 1틱: 더 공격적으로 체결 우선순위 확보
        new_price = round(mid + tick, 2)
        self._log(f"   ↳ Mid=${mid:.2f} + 1틱(${tick}) = ${new_price:.2f}")
    else:
        # 폴백: 마지막 주문가 + 1틱
        new_price = round(self._chaser_price + tick, 2)
        self._log(f"   ↳ Mid 조회 실패 → 폴백: ${self._chaser_price:.2f} + 1틱 = ${new_price:.2f}")

    if new_price > self._chaser_max_price:
        self._log(f"⚠ Chaser 가격 캡 도달 ${self._chaser_max_price:.2f} → 추격 중지")
        deactivate_chaser(self, reason="가격 캡 도달")
        return

    self._chaser_price    = new_price
    self._chaser_attempts += 1
    self._log(f"🎯 Chaser [{reason}] #{self._chaser_attempts}: "
              f"OID={self._chaser_oid}  가격 → ${new_price:.2f}  (틱+{tick})")

    _modify_order(self, self._chaser_oid, new_price)
    _update_chaser_ui(self, active=True)


def _fetch_mid_price_sync(self) -> Optional[float]:
    """
    현재 BAG 계약의 Mid price를 동기적으로 조회.
    (이미 reqMktData 스트림이 열려 있으면 캐시된 값 사용)

    반환: Mid price float, 조회 불가 시 None.
    """
    # combo_ui_leg_panel 에 캐시된 최신 Bid/Ask 사용
    mid_ticks: dict = getattr(self, '_mid_ticks', {})

    # 가장 최근 ticker 항목에서 bid/ask 읽기 (레그 0~15)
    for tid in range(_TICKER_BASE + 15, _TICKER_BASE - 1, -1):
        entry = mid_ticks.get(tid)
        if entry:
            bid = entry.get(1); ask = entry.get(2)
            if bid and ask and bid > 0 and ask > 0:
                return round((bid + ask) / 2, 2)

    # BAG 계약 자체의 시장가 조회 시도
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    bag = getattr(self, '_chaser_bag_contract', None)
    if ib is None or bag is None:
        return None

    _CHASE_TICKER_ID = 8799
    result: list = []

    _orig = getattr(ib, 'tickPrice', lambda *a: None)

    def _on_tick(req_id, tick_type, price, attrib=None):
        if req_id == _CHASE_TICKER_ID and tick_type in (1, 2) and price > 0:
            result.append((tick_type, price))
            if len({t for t, _ in result}) >= 2:
                try:
                    ib.cancelMktData(_CHASE_TICKER_ID)
                except Exception:
                    pass
                ib.tickPrice = _orig
        else:
            _orig(req_id, tick_type, price)

    ib.tickPrice = _on_tick
    try:
        ib.reqMktData(_CHASE_TICKER_ID, bag, "", True, False, [])
    except Exception:
        ib.tickPrice = _orig
        return None

    # 최대 300ms 대기 (이벤트 루프 블로킹 없이)
    import time
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        ticks = {t: p for t, p in result}
        if 1 in ticks and 2 in ticks:
            return round((ticks[1] + ticks[2]) / 2, 2)
        QTimer.singleShot(0, lambda: None)   # 이벤트 루프 양보

    ib.tickPrice = _orig
    return None


_TICKER_BASE = 8800   # combo_ui_leg_panel과 동일


def _modify_order(self, oid: int, new_price: float):
    """IBKR API 정정 주문 전송 (동일 OID로 placeOrder 재호출)."""
    try:
        from ibapi.order import Order as IbOrder
        ib    = self.mw.ib
        ibord = IbOrder()
        ibord.action        = self._chaser_action
        ibord.orderType     = "LMT"
        ibord.totalQuantity = 1
        ibord.lmtPrice      = new_price
        ibord.tif           = "DAY"
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True
        ib.placeOrder(oid, getattr(self, '_chaser_bag_contract', None) or oid, ibord)
        self._log(f"   ↳ 정정 주문 전송: OID={oid}  lmtPrice=${new_price:.2f}")
    except Exception as e:
        self._log(f"❌ 정정 주문 오류: {e}")


# ── UI 헬퍼 ─────────────────────────────────────────────────

def _is_auto_mode(self) -> bool:
    rb = getattr(self, '_rb_chaser_auto', None)
    return rb is not None and rb.isChecked()


def _update_chaser_ui(self, active: bool):
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


def _notify_user(self, msg: str):
    try:
        QMessageBox.warning(self, "Chaser 알림", msg)
    except Exception:
        self._log(f"[Chaser 알림] {msg}")