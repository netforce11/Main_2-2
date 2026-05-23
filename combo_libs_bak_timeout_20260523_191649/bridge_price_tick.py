"""
bridge_price_tick.py — 시세 틱 중앙 라우터  v1.0
════════════════════════════════════════════════════
[L-A] tickPrice 직접 덮어쓰기 → 중앙 Signal 구독 구조로 전환

핵심 아이디어:
  ib.tickPrice 는 딱 한 곳(core_conn_ibkr._setup_tick_router)에서만
  연결하고, 수신한 틱을 price_tick_sig.emit() 으로 방송한다.

  모든 모듈(Chaser, 긴급매도, 스나이퍼 등)은
  ib.tickPrice 를 건드리는 대신 price_tick_sig.connect(cb) 로 구독.
  서로 독립적으로 동작 → 한 모듈이 예외나도 다른 모듈 수신 영향 없음.

공개 API:
  price_tick_sig          : PriceTickSignal 인스턴스 (모듈 레벨 싱글턴)
  subscribe(cb, req_ids)  : 특정 reqId 범위만 필터링해서 수신
  unsubscribe(cb)         : 구독 해제
  emit_tick(...)          : ib.tickPrice 콜백에서 호출

사용 예 (Chaser):
  from call_put_tab.bridge_price_tick import price_tick_sig, subscribe, unsubscribe

  def _my_handler(req_id, tick_type, price):
      if req_id == MY_REQ_ID and tick_type in (1, 2):
          ...

  subscribe(_my_handler, req_ids={MY_REQ_ID})   # 구독
  ...
  unsubscribe(_my_handler)                       # 완료 후 해제
════════════════════════════════════════════════════
"""

from __future__ import annotations
import threading
from typing import Callable, Optional, Set


# ── 내부 구독자 레지스트리 ────────────────────────────────────
# {callback: req_ids | None}
# req_ids=None 이면 모든 reqId 수신
_subscribers: dict[Callable, Optional[Set[int]]] = {}
_lock = threading.Lock()


class PriceTickSignal:
    """
    Qt Signal 없이도 동작하는 경량 브로드캐스터.
    Qt가 임포트 가능한 환경에서는 하위 PyQtSignal 래퍼와 함께 사용 가능.

    설계 원칙:
      · 모든 콜백은 호출 스레드(IBKR 콜백 스레드)에서 직접 실행
      · 예외가 발생해도 다른 구독자에 영향 없음 (try/except per callback)
      · 구독/해제는 락으로 보호 (멀티스레드 안전)
    """

    def emit(self, req_id: int, tick_type: int, price: float) -> None:
        """
        IBKR ib.tickPrice 콜백에서 호출.
        등록된 모든 구독자에게 브로드캐스트.
        """
        with _lock:
            snapshot = list(_subscribers.items())

        for cb, req_ids in snapshot:
            if req_ids is not None and req_id not in req_ids:
                continue
            try:
                cb(req_id, tick_type, price)
            except Exception as e:
                print(f"[price_tick_sig] 구독자 예외 ({cb.__name__}): {e}")

    def connect(self, cb: Callable, req_ids: Optional[Set[int]] = None) -> None:
        """
        구독 등록.
        req_ids: 수신할 reqId 집합. None이면 전체 수신.
        """
        with _lock:
            _subscribers[cb] = req_ids

    def disconnect(self, cb: Callable) -> None:
        """구독 해제. 미등록 콜백은 조용히 무시."""
        with _lock:
            _subscribers.pop(cb, None)

    def disconnect_all(self) -> None:
        """전체 구독 해제 (앱 종료 또는 재연결 시)."""
        with _lock:
            _subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        with _lock:
            return len(_subscribers)


# ── 모듈 레벨 싱글턴 ─────────────────────────────────────────
price_tick_sig = PriceTickSignal()


# ── 편의 함수 ─────────────────────────────────────────────────

def subscribe(cb: Callable, req_ids: Optional[Set[int]] = None) -> None:
    """
    price_tick_sig.connect의 함수형 alias.

    Args:
        cb      : (req_id, tick_type, price) → None
        req_ids : 수신할 reqId 집합. None이면 전체.

    예:
        subscribe(_my_tick_handler, req_ids={8799})
        subscribe(_global_handler)   # 전체 틱 수신
    """
    price_tick_sig.connect(cb, req_ids)


def unsubscribe(cb: Callable) -> None:
    """price_tick_sig.disconnect의 함수형 alias."""
    price_tick_sig.disconnect(cb)


def emit_tick(req_id: int, tick_type: int, price: float,
              attrib=None) -> None:
    """
    ib.tickPrice 콜백에서 호출할 진입점.
    attrib는 IBKR API 인자이지만 라우팅엔 불필요 → 무시.
    """
    if price > 0:
        price_tick_sig.emit(req_id, tick_type, price)
