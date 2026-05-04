"""
combo_order_chaser.py — Smart Chaser (체결 추격 주문) + 취소 주문 로직  v2.3
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
    self._chaser_max_price = round(price + max_slippage, 2)
    self._last_bag_oid     = oid

    _update_chaser_ui(self, active=True)
    _update_cancel_ui(self, active=True)
    self._log(
        f"🎯 Chaser 등록: OID={oid}  가격=${price:.2f}"
        f"  qty={self._chaser_qty}  캡=${self._chaser_max_price:.2f}"
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
    t = QTimer()
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
    [BUG #5 수정] QEventLoop 제거 → 비동기 방식으로 교체.

    기존: _fetch_mid_price_sync() 안에서 QEventLoop.exec_()를 실행해
    QTimer 콜백(자동 추격) 내부에서 중첩 이벤트 루프가 돌아 UI 프리즈 위험.

    수정: Mid price 조회를 비동기로 수행.
      1) 캐시(_mid_ticks)에 이미 유효한 bid/ask가 있으면 즉시 사용.
      2) 캐시 없으면 reqMktData 요청 후 500ms QTimer로 결과 확인.
         결과 수신 시 → _do_chase_with_price() 호출.
         타임아웃 시  → fallback(현재 chaser_price + tick) 사용.
    """
    # Step 1: 캐시 우선 확인
    mid = _read_mid_from_cache(self)
    if mid is not None:
        _do_chase_with_price(self, mid, reason)
        return

    # Step 2: 비동기 reqMktData
    ib  = getattr(getattr(self, 'mw', None), 'ib', None)
    bag = getattr(self, '_chaser_bag_contract', None)
    if ib is None or bag is None:
        _do_chase_with_price(self, None, reason)
        return

    result: dict = {}
    _orig = getattr(ib, 'tickPrice', lambda *a: None)
    _done = [False]

    def _restore():
        try:
            ib.tickPrice = _orig
        except Exception:
            pass

    def _on_tick(req_id, tick_type, price, attrib=None):
        try:
            if attrib is not None:
                _orig(req_id, tick_type, price, attrib)
            else:
                _orig(req_id, tick_type, price)
        except Exception:
            pass
        if req_id == _CHASE_TICKER_ID and tick_type in (1, 2) and price > 0:
            result[tick_type] = price
            if 1 in result and 2 in result and not _done[0]:
                _done[0] = True
                try:
                    ib.cancelMktData(_CHASE_TICKER_ID)
                except Exception:
                    pass
                _restore()
                mid_val = round((result[1] + result[2]) / 2, 2)
                QTimer.singleShot(0, lambda: _do_chase_with_price(self, mid_val, reason))

    def _on_timeout():
        if _done[0]:
            return
        _done[0] = True
        _restore()
        try:
            ib.cancelMktData(_CHASE_TICKER_ID)
        except Exception:
            pass
        _do_chase_with_price(self, None, reason)

    ib.tickPrice = _on_tick
    try:
        ib.reqMktData(_CHASE_TICKER_ID, bag, "", True, False, [])
        QTimer.singleShot(500, _on_timeout)
    except Exception:
        _restore()
        _do_chase_with_price(self, None, reason)


def _do_chase_with_price(self, mid: Optional[float], reason: str) -> None:
    """Mid price(또는 None)를 받아 실제 정정 주문 수행."""
    # ★ FIX: _chaser_bag_contract.symbol에서 종목 읽기 (XSP=$0.01 / SPX=$0.05 분기)
    _bag = getattr(self, '_chaser_bag_contract', None)
    _sym = _bag.symbol if _bag is not None else ""
    tick = _get_tick_size(self._chaser_price, _sym)
    if mid is not None and mid > 0:
        new_price = round(mid + tick, 2)
        self._log(f"   ↳ Mid=${mid:.2f} + 1틱(${tick}) = ${new_price:.2f}")
    else:
        new_price = round(self._chaser_price + tick, 2)
        self._log(
            f"   ↳ Mid unavailable → fallback: ${self._chaser_price:.2f}"
            f" + tick ${tick} = ${new_price:.2f}")

    if new_price > self._chaser_max_price:
        self._log(
            f"⚠ Chaser 가격 캡 도달 ${self._chaser_max_price:.2f} → 추격 중지")
        deactivate_chaser(self, reason="가격 캡 도달")
        return

    self._chaser_price    = new_price
    self._chaser_attempts += 1
    self._log(
        f"🎯 Chaser [{reason}] #{self._chaser_attempts}: "
        f"OID={self._chaser_oid}  가격 → ${new_price:.2f}  (틱+{tick})")
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
    """
    mid_ticks: dict = getattr(self, '_mid_ticks', {})
    for tid in range(_TICKER_BASE + 15, _TICKER_BASE - 1, -1):
        entry = mid_ticks.get(tid)
        if entry:
            bid = entry.get(1)
            ask = entry.get(2)
            if bid and ask and bid > 0 and ask > 0:
                return round((bid + ask) / 2, 2)
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
    rb = getattr(self, '_rb_chaser_auto', None)
    if rb is not None:
        return rb.isChecked()
    # synthetic_panel 에서 조회 (fallback)
    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'is_auto_chaser'):
        return panel.is_auto_chaser()
    return False


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