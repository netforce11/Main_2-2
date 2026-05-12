"""
order_logic.py — 주문 실행 로직 v6.6
════════════════════════════════════════════════════════
[리팩토링] 기능별 파일 분리 후 하위 호환 통합 진입점으로 변경.

분리된 파일 구조:
  order_amend_cancel.py     정정·취소 주문
  order_quick.py            빠른주문(qord)·수량 계산
  order_sniper.py           스나이퍼 통합
    order_sniper_manage.py  ↳ 조건 등록/해제/저장/복원
    order_sniper_exec.py    ↳ 틱 수신·조건 평가·발주

외부 코드에서 기존처럼 OrderLogicMixin 을 임포트하면 그대로 동작한다.
════════════════════════════════════════════════════════
"""

import math as _math

from call_put_tab.order_amend_cancel import OrderAmendCancelMixin
from call_put_tab.order_quick        import OrderQuickMixin
from call_put_tab.order_sniper       import OrderSniperMixin


class OrderLogicMixin(OrderAmendCancelMixin, OrderQuickMixin, OrderSniperMixin):
    """
    주문 실행 로직. CallPutGrid에 mixin된다.

    MRO:
      OrderLogicMixin
        → OrderAmendCancelMixin  (정정·취소)
        → OrderQuickMixin        (빠른주문·수량계산)
        → OrderSniperMixin       (스나이퍼)
    """


# ═══════════════════════════════════════════════════════
# [v6.6] ERR 201 대응 헬퍼 — 긴급 옵션 매도 LMT 가격 계산
# ═══════════════════════════════════════════════════════

def get_emergency_sell_lmt_price(
    bid: float,
    sym: str = "",
    ticks_below: int = 2,
) -> float:
    """
    긴급 매도 시 MKT 대신 사용할 LMT 가격.
    Bid에서 ticks_below 틱 아래, 틱 단위로 정렬하여 반환.

    틱 사이즈: XSP=$0.01 / $3 미만=$0.05 / $3 이상=$0.10
    """
    if not bid or bid <= 0:
        return 0.05
    tick = 0.01 if sym.upper() == "XSP" else (0.10 if bid >= 3.0 else 0.05)
    raw  = max(bid - tick * ticks_below, tick)
    inv  = 1.0 / tick
    dec  = max(0, -int(_math.floor(_math.log10(tick)))) if tick < 1 else 0
    return round(_math.floor(raw * inv) / inv, dec)
