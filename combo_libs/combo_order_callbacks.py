"""
combo_order_callbacks.py — BAG 주문 상태 콜백 연결 / UI 갱신
──────────────────────────────────────────────────────────────
bridge.order_status_sig  → _on_order_status()
bridge.exec_sig          → _on_exec_details()

사용법 (ComboUI.__init__ 등에서 1회 호출):
    from combo_order_callbacks import connect_order_callbacks
    connect_order_callbacks(self)

해제 (탭 닫힐 때):
    from combo_order_callbacks import disconnect_order_callbacks
    disconnect_order_callbacks(self)
──────────────────────────────────────────────────────────────
Python 3.8 호환
"""

from __future__ import annotations
from typing import Optional
from functools import partial
from PyQt5.QtCore import Qt


# ── 내부 상수 ───────────────────────────────────────────────────
_STATUS_SUBMITTED  = ("Submitted", "PreSubmitted")
_STATUS_FILLED     = ("Filled",)
_STATUS_CANCELLED  = ("Cancelled",)
_STATUS_INACTIVE   = ("Inactive",)


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def connect_order_callbacks(self) -> None:
    """
    bridge 시그널을 self 의 핸들러에 연결한다.
    중복 연결 방지: _cb_connected 플래그로 1회만 연결.

    Fix #8: lambda 대신 functools.partial 사용.
      - lambda는 self를 클로저로 캡처해 순환참조 발생.
      - partial은 Qt가 슬롯 식별자로 안전하게 disconnect 가능.
    """
    if getattr(self, '_cb_connected', False):
        return

    from core import bridge
    _slot_status = partial(_on_order_status, self)
    _slot_exec   = partial(_on_exec_details, self)

    bridge.order_status_sig.connect(_slot_status, Qt.QueuedConnection)
    bridge.exec_sig.connect(_slot_exec,           Qt.QueuedConnection)

    # 슬롯 레퍼런스 보관 (disconnect 시 필요)
    self._cb_slot_status = _slot_status
    self._cb_slot_exec   = _slot_exec
    self._cb_connected   = True


def disconnect_order_callbacks(self) -> None:
    """bridge 시그널 연결 해제."""
    if not getattr(self, '_cb_connected', False):
        return
    try:
        from core import bridge
        bridge.order_status_sig.disconnect(self._cb_slot_status)
        bridge.exec_sig.disconnect(self._cb_slot_exec)
    except Exception:
        pass
    self._cb_connected = False


# ══════════════════════════════════════════════════════════════
# 내부 핸들러
# ══════════════════════════════════════════════════════════════

def _on_order_status(self, oid: int, status: str,
                     filled: float, remaining: float) -> None:
    """
    TWS → orderStatus 콜백.
    내 BAG 주문 OID 인지 확인 후 panel 갱신.
    DB 저장은 tab_account.py bridge 시그널에서 일괄 처리.
    """
    my_oid = getattr(self, '_chaser_current_oid', None)
    if my_oid is None or oid != my_oid:
        return

    panel = getattr(self, 'synthetic_panel', None)

    # ── 접수 ─────────────────────────────────────────────────
    if status in _STATUS_SUBMITTED:
        self._log(f"📨 OID={oid} 주문 접수됨 ({status})")
        _set_panel_status(panel, oid, "⏳ 접수됨")

    # ── 체결 ─────────────────────────────────────────────────
    elif status in _STATUS_FILLED:
        avg = _get_avg_price(self, oid)

        # Fix #4: 부분 체결은 status="Filled" + remaining>0 으로 수신됨.
        # 이전 코드에서는 elif filled>0 and remaining>0 분기가 Filled 분기보다
        # 아래에 있어 절대 실행되지 않았음 → Filled 분기 안에서 먼저 판별.
        if remaining > 0:
            self._log(f"⚡ OID={oid} 부분체결: {filled:.0f}체결 / {remaining:.0f}잔여")
            _set_panel_status(panel, oid, f"⚡ 부분체결({filled:.0f})")
            return  # 아직 완전 체결 아님 — Chaser 유지

        msg = f"✅ OID={oid} 체결완료"
        msg += f"  avg=${avg:.2f}" if avg else ""
        self._log(msg)

        # 체결 시점에 합성 잔고에 추가 (주문 시점엔 추가 안 함)
        pending = getattr(self, '_pending_position', None)
        if pending and pending.get('oid') == oid:
            if avg:
                pending['entry']   = avg
                pending['current'] = avg
            pending['status'] = '체결완료'
            if panel and hasattr(panel, 'add_position'):
                panel.add_position(pending)
            # ── 영속화: 파일 저장 (재연결 후 복원용) ────────────
            try:
                from combo_position_store import save_one_position
                save_one_position(pending)
            except Exception:
                pass
            self._pending_position = None

        _set_panel_filled(panel, oid, avg)
        _deactivate_chaser_safe(self, reason="체결 완료")
        # Fix #5: 완전 체결 후 current_oid 해제 → 뒤늦은 콜백 차단
        self._chaser_current_oid = None

    # ── 취소 확인 ────────────────────────────────────────────
    elif status in _STATUS_CANCELLED:
        self._log(f"✕ OID={oid} 취소 확인됨")
        _set_panel_cancelled(panel, oid)
        _deactivate_chaser_safe(self, reason="취소 확인")
        # pending 포지션 정리 (합성 잔고에 추가되지 않았으므로 그냥 버림)
        if getattr(self, '_pending_position', None) and \
                getattr(self, '_pending_position', {}).get('oid') == oid:
            self._pending_position = None
        # 완전 취소 후 재주문 허용
        self._bag_session = None
        # Fix #5: 취소 확인 후 current_oid 해제 → 뒤늦은 콜백 차단
        self._chaser_current_oid = None
        # [BUG-A 연동] _do_cancel_order의 중복 전송 방지 플래그 해제
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None
        # ── 영속화: 취소된 OID 파일에서 제거 ────────────────────
        try:
            from combo_position_store import remove_position
            remove_position(oid)
        except Exception:
            pass

    # ── IBKR 거절 ────────────────────────────────────────────
    elif status in _STATUS_INACTIVE:
        self._log(f"❌ OID={oid} 주문 거절/비활성")
        _set_panel_status(panel, oid, "❌ 거절됨")
        _deactivate_chaser_safe(self, reason="주문 거절")
        self._bag_session = None
        # Fix #5: 거절 후 current_oid 해제
        self._chaser_current_oid = None
        # [BUG-A 연동] 거절된 OID도 취소 플래그 해제
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None


def _on_exec_details(self, oid: int, sym: str,
                     side: str, qty: float, price: float) -> None:
    """
    TWS → execDetails 콜백.
    실제 체결가를 self._exec_avg_price 에 캐시.
    """
    my_oid = getattr(self, '_chaser_current_oid', None)
    if my_oid is None or oid != my_oid:
        return

    self._log(f"💰 체결내역: OID={oid}  {side}  qty={qty:.0f}  price=${price:.2f}")

    # avg price 캐시 (orderStatus Filled 콜백보다 먼저 올 수도 있음)
    cache = getattr(self, '_exec_avg_cache', {})
    cache[oid] = price
    self._exec_avg_cache = cache

    # panel 진입가 즉시 갱신
    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'mark_position_filled'):
        panel.mark_position_filled(oid)
    _update_panel_entry_price(panel, oid, price)


# ══════════════════════════════════════════════════════════════
# panel 헬퍼 (None-safe)
# ══════════════════════════════════════════════════════════════

def _set_panel_status(panel, oid: int, text: str) -> None:
    """합성 잔고 탭: OID 행의 상태 컬럼만 갱신."""
    if panel is None:
        return
    positions = getattr(panel, '_positions', [])
    for pos in positions:
        if pos.get('oid') == oid:
            pos['status'] = text
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()


def _set_panel_filled(panel, oid: int, avg_price: Optional[float]) -> None:
    """체결완료 상태 + 진입가(avg) 갱신."""
    if panel is None:
        return
    positions = getattr(panel, '_positions', [])
    for pos in positions:
        if pos.get('oid') == oid:
            pos['status'] = '체결완료'
            if avg_price:
                pos['entry']   = avg_price
                pos['current'] = avg_price
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()
    # 탭 전환: 합성 잔고 탭(index=1)
    tabs = getattr(panel, '_tabs', None)
    if tabs:
        tabs.setCurrentIndex(1)


def _set_panel_cancelled(panel, oid: int) -> None:
    """취소 완료 → 잔고 탭에서 해당 항목 제거."""
    if panel is None:
        return
    if hasattr(panel, 'mark_position_cancelled'):
        panel.mark_position_cancelled(oid)


def _update_panel_entry_price(panel, oid: int, price: float) -> None:
    """execDetails 에서 받은 실체결가로 진입가 덮어쓰기."""
    if panel is None:
        return
    positions = getattr(panel, '_positions', [])
    for pos in positions:
        if pos.get('oid') == oid:
            pos['entry']   = price
            pos['current'] = price
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()


# ══════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════

def _get_avg_price(self, oid: int) -> Optional[float]:
    """execDetails 캐시에서 체결 평균가 반환."""
    return getattr(self, '_exec_avg_cache', {}).get(oid)


def _deactivate_chaser_safe(self, reason: str = "") -> None:
    """Chaser 모듈이 없어도 안전하게 비활성화."""
    try:
        from combo_order_chaser import deactivate_chaser
        deactivate_chaser(self, reason=reason)
    except Exception:
        pass