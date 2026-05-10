"""
core_conn_fill.py — 체결 콜백 패치 (execDetails + orderStatus)  v6.7
════════════════════════════════════════════════════════════════════
core_conn_signals.py에서 체결 콜백 로직을 분리.

포함:
  ConnFillMixin
    · _hook_fill_callbacks()  execDetails + orderStatus 패치
    · _on_fill_event()        체결 공통 처리 (로그 + 잔고 팝업 + 포지션 갱신)
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from collections import deque
from PyQt5.QtCore import QTimer

try:
    from call_put_tab.core_conn_watchdog import _tg_send
except ImportError:
    def _tg_send(msg: str) -> None:
        pass


class ConnFillMixin:
    """체결 콜백 패치 Mixin. ConnSignalsMixin에 통합된다."""

    def _hook_fill_callbacks(self):
        """
        execDetails + orderStatus 콜백 패치.

        수정 사항:
          1) _fill_hooks_applied 플래그로 재패치 방지
             (재연결 시 _on_connected에서 False로 초기화됨)
          2) _exec_id_cache (deque maxlen=20) — execId 중복 체결 방지
          3) _order_fill_cache (set) — orderStatus 중복 처리 방지
          4) execDetails 처리한 OID → _order_fill_cache 마킹
             → orderStatus Filled 중복 억제
          5) orderStatus Inactive → 주문 거부 텔레그램 알림
        """
        if not self.mw.connected or not self.mw.ib:
            return
        if getattr(self, '_fill_hooks_applied', False):
            return
        self._fill_hooks_applied = True

        ib = self.mw.ib

        # 캐시 초기화 (없으면 생성)
        if not hasattr(self, '_exec_id_cache'):
            self._exec_id_cache = deque(maxlen=20)
        if not hasattr(self, '_order_fill_cache'):
            self._order_fill_cache = set()

        # ── execDetails 패치 ─────────────────────────────────
        _orig_exec = getattr(ib, 'execDetails', lambda *a: None)

        def _on_exec(reqId, contract, execution):
            # 원래 핸들러 호출 (다른 모듈 연동 유지)
            try:
                _orig_exec(reqId, contract, execution)
            except Exception:
                pass

            # execId 중복 체크
            exec_id = getattr(execution, 'execId', None)
            if exec_id and exec_id in self._exec_id_cache:
                return
            if exec_id:
                self._exec_id_cache.append(exec_id)

            sym  = (getattr(contract, 'localSymbol', '')
                    or getattr(contract, 'symbol', ''))
            qty  = getattr(execution, 'shares', 0)
            side = getattr(execution, 'side', '')
            px   = getattr(execution, 'price', 0)
            oid  = getattr(execution, 'orderId', None)

            # 이 OID는 처리됨 → orderStatus Filled 중복 억제
            if oid is not None:
                self._order_fill_cache.add(oid)

            QTimer.singleShot(0, lambda: self._on_fill_event(sym, qty, side, px))

        ib.execDetails = _on_exec

        # ── orderStatus 패치 ─────────────────────────────────
        _orig_status = getattr(ib, 'orderStatus', lambda *a: None)

        def _on_status(orderId, status, filled, remaining, avgFillPrice,
                       permId, parentId, lastFillPrice, clientId,
                       whyHeld, mktCapPrice):
            try:
                _orig_status(orderId, status, filled, remaining, avgFillPrice,
                             permId, parentId, lastFillPrice, clientId,
                             whyHeld, mktCapPrice)
            except Exception:
                pass

            # 주문 거부 / 비활성 → 텔레그램 알림
            if status == 'Inactive':
                reason = whyHeld or "사유 미수신"
                self._log(f"❌ OID={orderId} 주문 거부/비활성: {reason}")
                _tg_send(
                    f"❌ <b>주문 거부 (Inactive)</b>\n"
                    f"OID: {orderId}\n사유: {reason}")

            if status != 'Filled' or filled <= 0:
                return

            # execDetails가 이미 처리한 OID → 중복 건너뜀
            if orderId in self._order_fill_cache:
                self._order_fill_cache.discard(orderId)
                return

            # execDetails 미수신 → orderStatus 단독 체결 통보
            fill_px = (lastFillPrice if lastFillPrice and lastFillPrice > 0
                       else avgFillPrice)
            QTimer.singleShot(0, lambda: self._on_fill_event(
                f"OID={orderId}", filled, "", fill_px))

        ib.orderStatus = _on_status
        self._log("✅ 체결 콜백 패치 완료 (execDetails + orderStatus)")

    def _on_fill_event(self, sym: str, qty: float, side: str, price: float):
        """
        체결 이벤트 공통 처리.
          · 로그 출력
          · 잔고창 자동 팝업 (btn_pos_toggle)
          · 포지션 자동 갱신 (_refresh_positions, 500ms 후)
        """
        side_str = f" {side}" if side else ""
        self._log(f"✅ 체결 완료: {sym}{side_str} {qty}계약  @{price:.2f}")

        # 잔고창이 닫혀있으면 자동 팝업
        if hasattr(self, 'btn_pos_toggle'):
            win = getattr(self, '_pos_float_win', None)
            if not win or not win.isVisible():
                self.btn_pos_toggle.setChecked(True)
                if hasattr(self, '_on_pos_toggle'):
                    self._on_pos_toggle()

        # 500ms 후 잔고 갱신 (체결 반영 대기)
        if hasattr(self, '_refresh_positions'):
            QTimer.singleShot(500, self._refresh_positions)
