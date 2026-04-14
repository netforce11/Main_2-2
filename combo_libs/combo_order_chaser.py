"""
combo_order_chaser.py — Smart Chaser (체결 추격 주문) + 취소 주문 로직
──────────────────────────────────────────────────────────────────────
수동 모드 : Chase 버튼 클릭 시 1틱 개선 후 정정 주문
자동 모드 : 미체결 N초 후 자동으로 1틱 개선 (최대 횟수 제한)
취소      : cancel_bag_order(oid) → cancelOrder 전송 + Chaser 비활성화
──────────────────────────────────────────────────────────────────────
"""

import time
from typing import Optional
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

# ── 상수 ───────────────────────────────────────────────────────
CHASE_INTERVAL_MS  = 5_000
CHASE_MAX_ATTEMPTS = 3
CHASE_MIN_TICK     = 0.05
CHASE_TICK_HIGH    = 0.10


def _get_tick_size(price: float) -> float:
    return CHASE_TICK_HIGH if price >= 3.0 else CHASE_MIN_TICK


# ── Chaser 상태 초기화 ──────────────────────────────────────────

def init_chaser_state(self):
    self._chaser_oid       = None
    self._chaser_price     = 0.0
    self._chaser_action    = "BUY"
    self._chaser_attempts  = 0
    self._chaser_timer     = None
    self._chaser_active    = False
    self._chaser_max_price = 0.0


# ── 등록 / 비활성화 ────────────────────────────────────────────

def register_chaser(self, oid: int, price: float, action: str,
                    max_slippage: float = 0.30):
    init_chaser_state(self)
    self._chaser_oid       = oid
    self._chaser_price     = price
    self._chaser_action    = action
    self._chaser_attempts  = 0
    self._chaser_active    = True
    self._chaser_max_price = round(price + max_slippage, 2)
    self._last_bag_oid     = oid   # 취소용 fallback 저장

    _update_chaser_ui(self, active=True)
    _update_cancel_ui(self, active=True)
    self._log(f"🎯 Chaser 등록: OID={oid}  가격=${price:.2f}  캡=${self._chaser_max_price:.2f}")

    if _is_auto_mode(self):
        _start_auto_timer(self)


def deactivate_chaser(self, reason: str = "체결 완료"):
    if not self._chaser_active:
        return
    _stop_auto_timer(self)
    self._chaser_active = False
    self._chaser_oid    = None
    _update_chaser_ui(self, active=False)
    _update_cancel_ui(self, active=False)
    self._log(f"🎯 Chaser 종료: {reason}")


# ── 취소 주문 ──────────────────────────────────────────────────

def cancel_bag_order(self):
    """
    ✕ BAG 주문 취소 버튼 핸들러.
    콜-풋 탭 cancelOrder(oid) 와 동일한 IBKR API 패턴.
    BAG 전용: Chaser 비활성화 후 cancelOrder 전송.
    """
    oid = getattr(self, '_chaser_oid', None) or getattr(self, '_last_bag_oid', None)
    if not oid:
        return QMessageBox.information(self, "취소", "취소할 미체결 BAG 주문이 없습니다.")

    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")

    reply = QMessageBox.question(
        self, "✕ BAG 주문 취소",
        f"OID {oid} 합성 주문을 취소하시겠습니까?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply != QMessageBox.Yes:
        return

    try:
        self.mw.ib.cancelOrder(oid)
        self._log(f"✕ BAG 취소 전송: OID={oid}")
        deactivate_chaser(self, reason=f"사용자 취소 (OID={oid})")
        panel = getattr(self, 'synthetic_panel', None)
        if panel and hasattr(panel, 'lbl_status'):
            panel.lbl_status.setText(f"✕ 취소 요청됨 (OID={oid})")
    except Exception as e:
        self._log(f"❌ BAG 취소 오류: {e}")
        QMessageBox.critical(self, "오류", f"취소 전송 실패: {e}")


def _update_cancel_ui(self, active: bool):
    """✕ 취소 버튼 활성/비활성 갱신."""
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


# ── 수동 Chase 버튼 ────────────────────────────────────────────

def on_chase_click(self):
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
    if not self._chaser_active:
        return _stop_auto_timer(self)
    if self._chaser_attempts >= CHASE_MAX_ATTEMPTS:
        _stop_auto_timer(self)
        self._log(f"⚠ Chaser 최대 시도 횟수 도달 ({CHASE_MAX_ATTEMPTS}회) → 자동 중지")
        _notify_user(self, f"Chaser: {CHASE_MAX_ATTEMPTS}회 추격 후에도 미체결\n주문을 확인하세요.")
        deactivate_chaser(self, reason=f"최대 횟수({CHASE_MAX_ATTEMPTS}회) 초과")
        return
    _do_chase(self, reason="자동")


# ── 실제 1틱 정정 로직 ─────────────────────────────────────────

def _do_chase(self, reason: str = ""):
    tick = _get_tick_size(self._chaser_price)
    mid  = _fetch_mid_price_sync(self)
    if mid is not None and mid > 0:
        new_price = round(mid + tick, 2)
        self._log(f"   ↳ Mid=${mid:.2f} + 1틱(${tick}) = ${new_price:.2f}")
    else:
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
    mid_ticks: dict = getattr(self, '_mid_ticks', {})
    for tid in range(_TICKER_BASE + 15, _TICKER_BASE - 1, -1):
        entry = mid_ticks.get(tid)
        if entry:
            bid = entry.get(1); ask = entry.get(2)
            if bid and ask and bid > 0 and ask > 0:
                return round((bid + ask) / 2, 2)

    ib  = getattr(self, 'mw', None)
    ib  = getattr(ib, 'ib', None) if ib else None
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

    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        ticks = {t: p for t, p in result}
        if 1 in ticks and 2 in ticks:
            return round((ticks[1] + ticks[2]) / 2, 2)
        QTimer.singleShot(0, lambda: None)

    ib.tickPrice = _orig
    return None


_TICKER_BASE = 8800


def _modify_order(self, oid: int, new_price: float):
    """동일 OID placeOrder 재호출 = 정정 (콜-풋 탭과 동일 IBKR API 패턴)."""
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
