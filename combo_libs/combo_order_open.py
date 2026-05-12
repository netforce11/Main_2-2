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

v2.3 버그 수정:
  [BUG #6] on_open_orders: ib.openOrder/ib.openOrdersEnd 직접 패치 방식을
    bridge 시그널 방식으로 교체.
    기존: ib.openOrder = _on_open_order 로 직접 패치하면 동일 콜백을 사용하는
    다른 탭/모듈과 충돌 위험. 원본 복구 타이밍도 불안정함.
    수정: bridge.open_order_sig / bridge.open_order_end_sig 시그널에
    connect/disconnect 방식으로 교체. 다른 구독자와 안전하게 공존.
    bridge에 해당 시그널이 없는 환경을 위해 직접 패치 폴백 유지.

v2.4 버그 수정:
  [BUG-A] _do_cancel_order: cancelOrder 전송 후 deactivate_chaser 즉시 호출
    제거. 설계 원칙상 Chaser 비활성화는 TWS orderStatus "Cancelled" 콜백에서만
    수행해야 함. 즉시 호출하면 callbacks 흐름과 충돌해 상태가 꼬임.
    중복 전송 방지: _cancel_sent_oid 플래그로 같은 OID에 두 경로(미체결 탭 /
    ✕ 버튼)가 동시에 cancelOrder를 보내는 상황 차단.
  [BUG-B] _cancel_selected: 캐시 없이 전체 취소 시 on_open_orders 조회 중
    Chaser·접수확인 타이머가 _oo_in_progress 락을 선점해 4.5초 후
    _after_fetch()가 읽는 캐시가 오염되던 문제 수정.
    → _cancel_fetch_token으로 의도한 조회 결과만 사용.
  [BUG-C] _modify_tick: o["order"]를 직접 수정해 placeOrder 실패 시에도
    캐시 lmtPrice가 바뀌어 이후 정정이 잘못된 가격 기준으로 전송되던 문제 수정.
    → copy.deepcopy 후 수정, placeOrder 성공 시에만 캐시 갱신.
  [BUG-D] _modify_tick: 정정 후 _resync(1.5초)가 _oo_in_progress 락 경합에서
    밀려 재조회가 무시되던 문제 완화.
    → 락이 걸려 있으면 추가 0.5초 지연 후 재시도(최대 1회).

v2.5 수정:
  [FIX-P] on_open_orders: _finish() 완료 후 reqMktData(delayed) 구독 추가.
    재접속 후 미체결 조회 시 시세(현재가)가 출력되지 않던 문제 수정.
    conId 없는 BAG 주문은 스킵, 장외 포함 reqMarketDataType(3) 선 설정.
  [FIX-Q] _modify_tick: 장외 시간 정정 시 tif 를 GTC 로 강제 변환.
    장중(DAY) 주문을 장외에서 정정하면 IB 가 거절함.
    ET 09:30~16:00 외 시간대에는 deepcopy 후 tif="GTC" 로 덮어씀.
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QTableWidgetItem


# ── 미체결 주문 조회 ─────────────────────────────────────────────
def on_open_orders(self):
    """
    IB reqAllOpenOrders() → SyntheticStatusPanel 미체결 탭에 직접 출력.
    팝업 없음 — 하단 탭 테이블에 바로 표시.

    [BUG #6 수정] ib.openOrder 직접 패치 → bridge 시그널 방식으로 교체.
    기존 직접 패치는 다른 탭/모듈이 동일 콜백을 쓰고 있을 때 덮어써
    다른 탭의 미체결 수신이 소실되는 충돌 위험이 있었음.
    bridge 시그널의 connect/disconnect는 다중 구독자와 안전하게 공존.
    bridge에 open_order_sig가 없는 환경은 직접 패치 폴백으로 동작.
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

    def _finish(orders):
        """수집 완료 후 UI 갱신 및 lock 해제."""
        self._oo_in_progress = False
        self._cached_open_orders = orders
        if panel and hasattr(panel, 'update_open_orders'):
            panel.update_open_orders(orders)
            panel._tabs.setCurrentIndex(2)
        if orders:
            self._log(f"📋 미체결 {len(orders)}건 — 하단 미체결 탭 확인")
            # [FIX-P] 미체결 주문 시세 구독 (장외 포함, delayed 허용)
            _subscribe_open_order_prices(self, ib, orders)
        else:
            self._log("📋 미체결 주문 없음")

    def _collect_order(oid, contract, order, state):
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

    def _on_end(*_):
        if _done[0]:
            return
        _done[0] = True
        _disconnect_bridge()
        QTimer.singleShot(0, lambda: _finish(collected))

    # ── bridge 시그널 방식 (우선) ─────────────────────────────
    _using_bridge = [False]

    def _disconnect_bridge():
        if not _using_bridge[0]:
            return
        try:
            from core import bridge
            bridge.open_order_sig.disconnect(_collect_order)
        except Exception:
            pass
        try:
            from core import bridge
            bridge.open_order_end_sig.disconnect(_on_end)
        except Exception:
            pass

    try:
        from core import bridge
        if hasattr(bridge, 'open_order_sig') and hasattr(bridge, 'open_order_end_sig'):
            bridge.open_order_sig.connect(_collect_order, Qt.QueuedConnection)
            bridge.open_order_end_sig.connect(_on_end,    Qt.QueuedConnection)
            _using_bridge[0] = True
    except Exception:
        pass

    # ── bridge 시그널 없는 환경: 직접 패치 폴백 ─────────────
    if not _using_bridge[0]:
        if not getattr(self, '_oo_orig_saved', False):
            self._oo_orig_open = getattr(ib, 'openOrder',     lambda *a: None)
            self._oo_orig_end  = getattr(ib, 'openOrdersEnd', lambda *a: None)
            self._oo_orig_saved = True

        orig_open = self._oo_orig_open
        orig_end  = self._oo_orig_end

        def _patch_open(oid, contract, order, state):
            try:
                orig_open(oid, contract, order, state)
            except Exception:
                pass
            _collect_order(oid, contract, order, state)

        def _patch_end(*a):
            if _done[0]:
                return
            _done[0] = True
            ib.openOrder     = orig_open
            ib.openOrdersEnd = orig_end
            self._oo_orig_saved = False
            try:
                orig_end(*a)
            except Exception:
                pass
            QTimer.singleShot(0, lambda: _finish(collected))

        ib.openOrder     = _patch_open
        ib.openOrdersEnd = _patch_end

    # ── 타임아웃 안전망 ─────────────────────────────────────
    def _timeout():
        if _done[0]:
            return
        _done[0] = True
        _disconnect_bridge()
        if not _using_bridge[0]:
            # 직접 패치 폴백 복구
            try:
                ib.openOrder     = self._oo_orig_open
                ib.openOrdersEnd = self._oo_orig_end
                self._oo_orig_saved = False
            except Exception:
                pass
        self._log("⚠ 미체결 조회 타임아웃 (2초) — TWS 응답 없음")
        QTimer.singleShot(0, lambda: _finish(collected))

    QTimer.singleShot(2000, _timeout)

    try:
        ib.reqAllOpenOrders()
        self._log("📋 미체결 주문 조회 중…")
    except Exception as e:
        _done[0] = True
        _disconnect_bridge()
        self._oo_in_progress = False
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

    [BUG-A 수정]
    1) deactivate_chaser 즉시 호출 제거.
       Chaser 비활성화는 반드시 TWS orderStatus "Cancelled" 콜백
       (combo_order_callbacks._on_order_status)에서만 수행해야 함.
       여기서 즉시 호출하면 callbacks 흐름과 충돌해 _chaser_oid 등
       상태 변수가 꼬이는 문제 발생.

    2) 중복 전송 방지: _cancel_sent_oid 플래그.
       미체결 탭 취소(_cancel_selected)와 ✕ 버튼(cancel_bag_order) 두
       경로가 동시에 같은 OID를 취소 시도할 수 있음.
       이미 전송된 OID면 False를 즉시 반환해 이중 전송 차단.
       TWS orderStatus "Cancelled" 수신 시 플래그 해제는
       combo_order_callbacks._on_order_status에서 처리.
    """
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if not ib:
        self._log("❌ IB 미연결")
        return False

    # [BUG-A] 중복 전송 방지
    if getattr(self, '_cancel_sent_oid', None) == oid:
        self._log(f"⚠ OID {oid} 취소 이미 전송됨 — 중복 차단")
        return False

    try:
        ib.cancelOrder(oid)
        self._cancel_sent_oid = oid   # 플래그 세팅 (callbacks에서 해제)
        self._log(f"✖ 취소 전송: OID {oid}  (확인은 orderStatus 콜백 대기)")
        # [BUG-A] deactivate_chaser 제거 → orderStatus "Cancelled" 콜백에서 처리
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
    Fix #1 : 정정 전송 성공 후 on_open_orders()를 재호출해 TWS 실제 상태로
             미체결 탭을 동기화.
    Fix #10: get_selected_order()는 row 인덱스(int 0-based) 반환.

    [BUG-C 수정] o["order"]를 직접 수정하면 placeOrder 실패 시에도 캐시의
      lmtPrice가 이미 변경되어 이후 정정이 잘못된 가격 기준으로 전송됨.
      → copy.deepcopy로 원본 보존. placeOrder 성공 시에만 캐시 갱신.

    [BUG-D 수정] 정정 후 _resync(1.5초)가 _oo_in_progress 락에 밀려
      재조회가 무시되는 경우를 완화.
      → 락 중이면 0.5초 추가 대기 후 1회 재시도.
    """
    import copy

    panel = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])
    if not orders:
        self._log("⚠ 미체결 주문 없음 — 먼저 [미체결 조회] 버튼을 누르세요.")
        return

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
        # [BUG-C] deepcopy로 원본 order 객체 보존 — 실패해도 캐시 오염 없음
        order = copy.deepcopy(o["order"])
        order.lmtPrice = new_price

        # [FIX-Q] 장외 시간 정정 시 tif 강제 GTC
        # ET 09:30~16:00 외 시간대에 DAY 주문을 정정하면 IB 가 거절함
        if not _is_market_hours_et():
            if getattr(order, 'tif', 'DAY') == 'DAY':
                order.tif = 'GTC'
                self._log("ℹ 장외 시간 — tif DAY→GTC 자동 변환")

        ib.placeOrder(o["oid"], o["contract"], order)

        sign = "+" if direction > 0 else ""
        self._log(
            f"✏ {sign}{direction}호가 정정: OID {o['oid']}  "
            f"{cur_price:.2f} → {new_price:.2f}"
        )

        # [BUG-C] placeOrder 성공 후에만 캐시 갱신
        o["lmt"]   = new_price
        o["order"] = order

        # [BUG-D] 락 경합 완화: _oo_in_progress 중이면 0.5초 뒤 1회 재시도
        def _resync(retry: bool = True):
            if getattr(self, '_oo_in_progress', False):
                if retry:
                    self._log("📋 미체결 조회 락 중 — 0.5초 후 재시도")
                    QTimer.singleShot(500, lambda: _resync(retry=False))
                else:
                    self._log("⚠ 정정 재조회 생략 — 락 지속 중")
                return
            self._log("📋 정정 접수 확인을 위해 미체결 재조회…")
            on_open_orders(self)

        QTimer.singleShot(1500, _resync)

    except Exception as e:
        self._log(f"❌ 정정 오류: {e}")


# ── 선택 / 전체 취소 ─────────────────────────────────────────────
def _cancel_selected(self):
    """
    미체결 탭 선택 항목 취소 (없으면 전체 취소).

    Fix #2 : 캐시 없을 때 타임아웃을 4.5초로 확보.
    Fix #7 : cancelOrder 전송 성공 확인 후에만 캐시에서 제거.

    [BUG-B 수정] 캐시 없이 전체 취소 시 on_open_orders 조회 중
      Chaser(4초)·접수확인(5초)·정정 재조회(1.5초) 타이머가 락을 선점하거나
      4.5초 대기 중에 캐시를 덮어써 _after_fetch()가 엉뚱한 주문 목록을
      취소하는 오염 문제 수정.
      → _cancel_fetch_token으로 이 취소 흐름이 요청한 캐시임을 검증.
         4.5초 후 캐시 세대(token)가 바뀌었으면 조회를 재시도.
    """
    import time as _time

    panel  = getattr(self, 'synthetic_panel', None)
    orders = getattr(self, '_cached_open_orders', [])

    if not orders:
        # [BUG-B] fetch token: 이 조회가 채운 캐시인지 구별
        fetch_token = _time.monotonic()
        self._cancel_fetch_token = fetch_token

        def _after_fetch():
            # 캐시 세대가 바뀌었으면(다른 타이머가 캐시를 갱신했으면) 재시도
            if getattr(self, '_cancel_fetch_token', None) != fetch_token:
                self._log("⚠ 취소 대상 캐시가 변경됨 — 재조회 후 취소 시도")
                # 재조회 후 다시 시도 (재귀 방지 위해 직접 취소만 수행)
                orders2 = getattr(self, '_cached_open_orders', [])
            else:
                orders2 = getattr(self, '_cached_open_orders', [])

            cancelled = []
            for o in orders2:
                if _do_cancel_order(self, o["oid"]):
                    cancelled.append(o)
            if cancelled:
                self._log(f"✖ 전체 취소 완료: {len(cancelled)}건")
            else:
                self._log("⚠ 취소할 미체결 주문 없음 (TWS 응답 없거나 이미 체결됨)")
            # Fix #7: 전송 성공한 항목만 캐시에서 제거
            remaining = [o for o in orders2 if o not in cancelled]
            self._cached_open_orders = remaining
            if panel:
                panel.update_open_orders(remaining)

        on_open_orders(self)
        QTimer.singleShot(4500, _after_fetch)
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
        # Fix #7: 전체 취소 시 성공한 항목만 제거
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


# ── 헬퍼 함수 ────────────────────────────────────────────────────

def _is_market_hours_et() -> bool:
    """
    [FIX-Q] ET 기준 정규장 시간(09:30~16:00) 여부.
    장외 판별에 사용 — 장외면 정정 tif 를 GTC 로 강제 변환.
    """
    try:
        from datetime import datetime, time
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York")).time()
        return time(9, 30) <= now <= time(16, 0)
    except Exception:
        return True   # 판별 실패 시 장중으로 간주 (안전 방향)


def _subscribe_open_order_prices(self, ib, orders: list) -> None:
    """
    [FIX-P] 미체결 주문 목록의 conId 를 이용해 reqMktData 구독.
    - 장외 포함 delayed quote(type 3) 허용 설정 후 구독.
    - BAG(combo) 주문은 conId 가 없으므로 스킵.
    - 이미 구독 중인 tid 는 재구독하지 않음.
    - tid 대역: 9300번대 (잔고 9200번대와 분리).
    """
    if not orders:
        return

    try:
        # delayed quote 허용 (장외에도 시세 수신)
        ib.reqMarketDataType(3)
    except Exception:
        pass

    if not hasattr(self, '_oo_stream_tids'):
        self._oo_stream_tids = {}   # {oid: tid}

    _OO_STREAM_BASE = 9300

    from core import router

    for o in orders:
        oid = o.get("oid")
        contract = o.get("contract")
        if not oid or not contract:
            continue

        # BAG(combo) 주문은 conId=0 → 스킵
        con_id = getattr(contract, 'conId', 0)
        if not con_id:
            continue

        # 이미 구독 중이면 재구독 생략
        if oid in self._oo_stream_tids:
            continue

        tid = _OO_STREAM_BASE + (oid % 900)   # 9300~9199 대역 내 분산

        def _make_handler(o_ref):
            def _on_tick(req_id: int, tick_type: int, price: float):
                if price <= 0 or tick_type not in (1, 2, 4, 9):
                    return
                # 현재가(mid 또는 last)를 캐시에 반영 후 패널 갱신
                if tick_type in (1, 2):
                    ticks = getattr(self, '_oo_price_ticks', {})
                    if req_id not in ticks:
                        ticks[req_id] = {}
                    ticks[req_id][tick_type] = price
                    self._oo_price_ticks = ticks
                    bid = ticks[req_id].get(1)
                    ask = ticks[req_id].get(2)
                    if bid and ask:
                        o_ref["current_price"] = round((bid + ask) / 2, 2)
                else:
                    o_ref["current_price"] = price
            return _on_tick

        try:
            from ibapi.contract import Contract as IbContract
            c = IbContract()
            c.conId = con_id
            c.exchange = "SMART"
            slot = _make_handler(o)
            router.register_price(tid, tid, slot)
            ib.reqMktData(tid, c, "", False, False, [])
            self._oo_stream_tids[oid] = tid
            self._log(
                f"📡 미체결 시세 구독: OID={oid} conId={con_id} tid={tid}")
        except Exception as e:
            self._log(f"⚠ 미체결 시세 구독 실패 OID={oid}: {e}")