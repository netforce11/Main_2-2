"""
combo_order_open.py — 미체결 조회 / 정정 / 취소 로직
────────────────────────────────────────────────────
on_open_orders  : 미체결 조회 → SyntheticStatusPanel 미체결 탭 직접 갱신 (팝업 없음)
on_modify_order : 미체결 조회 후 탭에서 +1/-1호가 버튼으로 정정
on_cancel_order : 미체결 조회 후 탭에서 전체취소 버튼으로 취소
_modify_tick    : +1/-1호가 정정 전송
_cancel_selected: 선택 or 전체 취소
────────────────────────────────────────────────────
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QTableWidgetItem


# ── 미체결 주문 조회 ─────────────────────────────────────────────
def on_open_orders(self):
    """
    IB reqOpenOrders() → SyntheticStatusPanel 미체결 탭에 직접 출력.
    팝업 없음 — 하단 탭 테이블에 바로 표시.
    """
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return

    panel = getattr(self, 'synthetic_panel', None)

    collected = []
    _done = [False]
    _orig_open = getattr(ib, 'openOrder',    lambda *a: None)
    _orig_end  = getattr(ib, 'openOrderEnd', lambda *a: None)

    def _restore():
        ib.openOrder    = _orig_open
        ib.openOrderEnd = _orig_end

    def _on_open_order(oid, contract, order, state):
        try: _orig_open(oid, contract, order, state)
        except: pass
        collected.append({
            "oid":      oid,
            "sym":      getattr(contract, 'symbol', ''),
            "sec":      getattr(contract, 'secType', ''),
            "action":   getattr(order,    'action', ''),
            "qty":      getattr(order,    'totalQuantity', 0),
            "lmt":      getattr(order,    'lmtPrice', 0.0),
            "status":   getattr(state,    'status', ''),
            "order":    order,
            "contract": contract,
        })

    def _on_end(*a):
        if _done[0]: return
        _done[0] = True
        try: _orig_end(*a)
        except: pass
        _restore()
        QTimer.singleShot(0, lambda: _update_panel(collected))

    def _update_panel(orders):
        """팝업 없이 미체결 탭에 직접 갱신."""
        self._cached_open_orders = orders
        if panel and hasattr(panel, 'update_open_orders'):
            panel.update_open_orders(orders)
            panel._tabs.setCurrentIndex(2)
        if orders:
            self._log(f"📋 미체결 {len(orders)}건 — 하단 미체결 탭 확인")
        else:
            self._log("📋 미체결 주문 없음")

    ib.openOrder    = _on_open_order
    ib.openOrderEnd = _on_end

    # 4초 타임아웃 안전망
    def _timeout():
        if not _done[0]:
            _done[0] = True
            _restore()
            QTimer.singleShot(0, lambda: _update_panel(collected))
    QTimer.singleShot(4000, _timeout)

    try:
        ib.reqOpenOrders()
        self._log("📋 미체결 주문 조회 중…")
    except Exception as e:
        _restore()
        self._log(f"❌ reqOpenOrders: {e}")


# ── 정정 / 취소 버튼 핸들러 ─────────────────────────────────────
def on_modify_order(self):
    """정정 버튼 → 미체결 조회 후 탭에서 행 선택 → +1/-1호가 버튼으로 정정."""
    on_open_orders(self)
    self._log("ℹ 미체결 탭에서 행 선택 후 [+1호가 정정] / [-1호가 정정] 버튼을 누르세요.")


def on_cancel_order(self):
    """취소 버튼 → 미체결 조회 후 탭에서 행 선택 → 전체취소 버튼으로 취소."""
    on_open_orders(self)
    self._log("ℹ 미체결 탭에서 행 선택 후 [✖ 전체 취소] 버튼을 누르세요.")


def _do_cancel_order(self, oid: int):
    """실제 cancelOrder 전송."""
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결"); return
    try:
        ib.cancelOrder(oid)
        self._log(f"✖ 취소 전송: OID {oid}")
        # Chaser도 비활성화
        try:
            from combo_order_chaser import deactivate_chaser
            deactivate_chaser(self, reason="수동 취소")
        except Exception:
            pass
    except Exception as e:
        self._log(f"❌ cancelOrder: {e}")


# ── +1/-1호가 정정 ────────────────────────────────────────────
def _modify_tick(self, direction: int):
    """
    미체결 탭에서 선택된 주문을 +1 또는 -1 호가로 정정.
    direction: +1 또는 -1
    """
    panel = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])
    if not orders:
        self._log("⚠ 미체결 주문 없음 — 먼저 조회하세요.")
        return

    row = panel.get_selected_order() if panel else -1
    if row < 0 or row >= len(orders):
        self._log("⚠ 정정할 주문을 선택하세요.")
        return

    o = orders[row]
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결"); return

    cur_price = o.get("lmt", 0.0) or 0.0
    # 틱 크기: $3 이상 = 0.10, 미만 = 0.05
    tick = 0.10 if cur_price >= 3.0 else 0.05
    new_price = round(cur_price + direction * tick, 2)
    if new_price <= 0:
        self._log("⚠ 가격이 0 이하로 내려갈 수 없음"); return

    try:
        order = o["order"]
        order.lmtPrice = new_price
        ib.placeOrder(o["oid"], o["contract"], order)
        sign = "+" if direction > 0 else ""
        self._log(f"✏ {sign}{direction}호가 정정: OID {o['oid']}  "
                  f"{cur_price:.2f} → {new_price:.2f}")
        # 캐시 업데이트
        orders[row]["lmt"] = new_price
        if panel:
            panel.update_open_orders(orders)
    except Exception as e:
        self._log(f"❌ 정정 오류: {e}")


# ── 자동 취소 ─────────────────────────────────────────────────
def _cancel_selected(self):
    """미체결 탭 선택 항목 취소 (없으면 전체 취소)."""
    panel  = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])

    if not orders:
        # 캐시 없으면 먼저 조회 후 취소
        def _after_fetch():
            orders2 = getattr(self, '_cached_open_orders', [])
            for o in orders2:
                _do_cancel_order(self, o["oid"])
            if orders2:
                self._log(f"✖ 전체 취소 완료: {len(orders2)}건")
            if panel:
                panel.update_open_orders([])
        on_open_orders(self)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(3500, _after_fetch)
        return

    row = panel.get_selected_order() if panel else -1
    if row >= 0 and row < len(orders):
        o = orders[row]
        _do_cancel_order(self, o["oid"])
        orders.pop(row)
        self._log(f"✖ 취소: OID {o['oid']}")
    else:
        # 선택 없으면 전체
        for o in orders:
            _do_cancel_order(self, o["oid"])
        self._log(f"✖ 전체 취소: {len(orders)}건")
        orders.clear()

    if panel:
        panel.update_open_orders(orders)