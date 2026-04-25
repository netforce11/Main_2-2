"""
combo_order_open.py — 미체결 조회 / 정정 / 취소 로직
────────────────────────────────────────────────────
on_open_orders  : 미체결 조회 → SyntheticStatusPanel 미체결 탭 직접 갱신 (팝업 없음)
                  reqAllOpenOrders 사용 — 세션 무관 전체 미체결 조회
on_modify_order : 미체결 조회 후 탭에서 +1/-1호가 버튼으로 정정
on_cancel_order : 미체결 조회 후 탭에서 전체취소 버튼으로 취소
_modify_tick    : +1/-1호가 정정 전송
_cancel_selected: 선택 or 전체 취소
────────────────────────────────────────────────────
v2.1 변경:
  - on_open_orders: 재진입 방지 락 (_oo_in_progress)
  - on_open_orders: 원본 콜백 클래스 속성 보관으로 중복 패치 방지
  - reqAllOpenOrders 사용 (세션 무관 전체 조회)
  - openOrdersEnd 콜백 사용

v2.2 버그 수정:
  Fix #1 : _modify_tick — 정정 전송 후 TWS 재동기화(on_open_orders) 추가.
           이전: 로컬 캐시만 갱신해 정정 실패 시 UI가 성공한 것처럼 보임.
  Fix #2 : _cancel_selected — 전체 취소 시 타임아웃을 4.5초로 여유 확보.
           이전: on_open_orders 2초 타임아웃 + 3.5초 후 취소 = 0.5초 여유뿐,
           TWS 응답 지연 시 빈 캐시로 취소 루프가 돌아 아무것도 취소 안 됨.
  Fix #7 : _cancel_selected — cancelOrder 전송 성공 확인 후 캐시에서 제거.
           이전: orders.pop(row) 즉시 → 취소 실패 시 재시도 불가.
  Fix #10: _modify_tick — get_selected_order() 반환값을 row 인덱스로 명시.
           panel.get_selected_order() → int row index, not oid
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QTableWidgetItem


# ── 미체결 주문 조회 ─────────────────────────────────────────────
def on_open_orders(self):
    """
    IB reqAllOpenOrders() → SyntheticStatusPanel 미체결 탭에 직접 출력.
    팝업 없음 — 하단 탭 테이블에 바로 표시.

    재진입 방지: 조회 진행 중 추가 호출은 무시.
    원본 콜백을 인스턴스 속성(_oo_orig_*)에 보관해 중복 패치 방지.
    """
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return

    # ── 재진입 방지 ──────────────────────────────────────────
    if getattr(self, '_oo_in_progress', False):
        self._log("📋 미체결 조회 진행 중 — 중복 요청 무시")
        return
    self._oo_in_progress = True

    panel = getattr(self, 'synthetic_panel', None)
    collected = []
    _done = [False]

    # ── 원본 콜백 보관 ────────────────────────────────────────
    if not getattr(self, '_oo_orig_saved', False):
        self._oo_orig_open = getattr(ib, 'openOrder',     lambda *a: None)
        self._oo_orig_end  = getattr(ib, 'openOrdersEnd', lambda *a: None)
        self._oo_orig_saved = True

    orig_open = self._oo_orig_open
    orig_end  = self._oo_orig_end

    def _restore():
        ib.openOrder     = orig_open
        ib.openOrdersEnd = orig_end
        self._oo_orig_saved  = False
        self._oo_in_progress = False

    def _on_open_order(oid, contract, order, state):
        try: orig_open(oid, contract, order, state)
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
        try: orig_end(*a)
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

    ib.openOrder     = _on_open_order
    ib.openOrdersEnd = _on_end

    # ── 타임아웃 안전망 ─────────────────────────────────────
    def _timeout():
        if not _done[0]:
            _done[0] = True
            _restore()
            self._log("⚠ 미체결 조회 타임아웃 (2초) — TWS 응답 없음")
            QTimer.singleShot(0, lambda: _update_panel(collected))
    QTimer.singleShot(2000, _timeout)

    try:
        ib.reqAllOpenOrders()
        self._log("📋 미체결 주문 조회 중…")
    except Exception as e:
        _restore()
        self._log(f"❌ reqAllOpenOrders: {e}")


# ── 정정 / 취소 버튼 핸들러 ─────────────────────────────────────
def on_modify_order(self):
    """정정 버튼 → 미체결 조회 후 탭에서 행 선택 → +1/-1호가 버튼으로 정정."""
    on_open_orders(self)
    self._log("ℹ 미체결 탭에서 행 선택 후 [+1호가 정정] / [-1호가 정정] 버튼을 누르세요.")


def on_cancel_order(self):
    """취소 버튼 → 미체결 조회 후 탭에서 행 선택 → 전체취소 버튼으로 취소."""
    on_open_orders(self)
    self._log("ℹ 미체결 탭에서 행 선택 후 [✖ 전체 취소] 버튼을 누르세요.")


def _do_cancel_order(self, oid: int) -> bool:
    """
    실제 cancelOrder 전송. 성공 시 True, 실패 시 False 반환.

    Fix #7: 반환값(bool)을 추가해 _cancel_selected에서 성공 여부를
    확인한 뒤에만 캐시에서 제거하도록 변경.
    """
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return False
    try:
        ib.cancelOrder(oid)
        self._log(f"✖ 취소 전송: OID {oid}")
        try:
            from combo_order_chaser import deactivate_chaser
            deactivate_chaser(self, reason="수동 취소")
        except Exception:
            pass
        return True
    except Exception as e:
        self._log(f"❌ cancelOrder: {e}")
        return False


# ── +1/-1호가 정정 ────────────────────────────────────────────
def _modify_tick(self, direction: int):
    """
    미체결 탭에서 선택된 주문을 +1 또는 -1 호가로 정정.
    direction: +1 또는 -1

    Fix #1 : 정정 전송 성공 후 on_open_orders()를 재호출해 TWS 실제 상태로
             미체결 탭을 동기화. 이전 코드는 로컬 캐시만 갱신해 정정 실패
             시에도 UI에 성공한 것처럼 표시되는 버그가 있었음.
    Fix #10: get_selected_order()가 row 인덱스(int)를 반환함을 명시.
             panel.get_selected_order() → int row index (0-based), not oid.
    """
    panel = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])
    if not orders:
        self._log("⚠ 미체결 주문 없음 — 먼저 [미체결 조회] 버튼을 누르세요.")
        return

    # Fix #10: get_selected_order()는 row 인덱스(int 0-based)를 반환.
    # panel 구현에서 선택된 행의 테이블 인덱스를 반환해야 함 (oid가 아님).
    row: int = panel.get_selected_order() if panel else -1
    if row < 0 or row >= len(orders):
        self._log("⚠ 정정할 주문을 선택하세요.")
        return

    o = orders[row]
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return

    cur_price = o.get("lmt", 0.0) or 0.0
    tick = 0.10 if cur_price >= 3.0 else 0.05
    new_price = round(cur_price + direction * tick, 2)
    if new_price <= 0:
        self._log("⚠ 가격이 0 이하로 내려갈 수 없음")
        return

    try:
        order = o["order"]
        order.lmtPrice = new_price
        ib.placeOrder(o["oid"], o["contract"], order)
        sign = "+" if direction > 0 else ""
        self._log(
            f"✏ {sign}{direction}호가 정정: OID {o['oid']}  "
            f"{cur_price:.2f} → {new_price:.2f}"
        )

        # Fix #1: 정정 전송 직후 로컬 캐시만 갱신하지 않고,
        # 1.5초 후 TWS에서 실제 접수된 상태로 미체결 탭을 재동기화한다.
        # (TWS가 정정을 처리하는 데 통상 0.5~1초 소요)
        def _resync():
            self._log("📋 정정 접수 확인을 위해 미체결 재조회…")
            on_open_orders(self)

        QTimer.singleShot(1500, _resync)

    except Exception as e:
        self._log(f"❌ 정정 오류: {e}")


# ── 선택 / 전체 취소 ─────────────────────────────────────────────
def _cancel_selected(self):
    """
    미체결 탭 선택 항목 취소 (없으면 전체 취소).

    Fix #2 : 캐시가 비어있을 때 전체 취소 시 타임아웃을 4.5초로 늘려
             TWS 응답 지연(2초 타임아웃) + 처리 여유를 안전하게 확보.
             이전 코드: 3.5초 → 여유 0.5초뿐, 응답 지연 시 아무것도 취소 안 됨.
    Fix #7 : cancelOrder 전송 성공 확인(_do_cancel_order 반환값 bool) 후
             캐시에서 해당 항목 제거. 이전 코드: 즉시 pop() → 실패 시 재시도 불가.
    """
    panel  = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])

    if not orders:
        # Fix #2: 타임아웃을 4.5초로 여유 있게 설정
        def _after_fetch():
            orders2 = getattr(self, '_cached_open_orders', [])
            cancelled = []
            for o in orders2:
                if _do_cancel_order(self, o["oid"]):
                    cancelled.append(o)
            if cancelled:
                self._log(f"✖ 전체 취소 완료: {len(cancelled)}건")
            else:
                self._log("⚠ 취소할 미체결 주문 없음 (TWS 응답 없거나 이미 체결됨)")
            # Fix #7: 취소 전송 성공한 항목만 캐시에서 제거
            remaining = [o for o in orders2 if o not in cancelled]
            self._cached_open_orders = remaining
            if panel:
                panel.update_open_orders(remaining)

        on_open_orders(self)
        QTimer.singleShot(4500, _after_fetch)   # Fix #2: 3500 → 4500
        return

    row = panel.get_selected_order() if panel else -1
    if 0 <= row < len(orders):
        o = orders[row]
        # Fix #7: 전송 성공 확인 후에만 캐시에서 제거
        if _do_cancel_order(self, o["oid"]):
            orders.pop(row)
            self._log(f"✖ 취소: OID {o['oid']}")
        else:
            self._log(f"⚠ 취소 전송 실패: OID {o['oid']} — 캐시 유지 (재시도 가능)")
    else:
        # Fix #7: 전체 취소 시 성공한 항목만 제거, 실패한 OID는 로그 출력
        failed_oids = []
        removed = []
        for o in list(orders):
            if _do_cancel_order(self, o["oid"]):
                removed.append(o)
            else:
                failed_oids.append(o["oid"])
        for o in removed:
            orders.remove(o)
        self._log(f"✖ 전체 취소: {len(removed)}건 전송 성공"
                  + (f"  ⚠ 실패 OID: {failed_oids}" if failed_oids else ""))

    if panel:
        panel.update_open_orders(orders)