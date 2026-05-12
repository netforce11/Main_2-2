"""
order_sniper.py — 스나이퍼 주문 통합 진입점 v6.6
════════════════════════════════════════════════════════
분리된 파일 구조:
  order_sniper_persist.py  JSON 저장·복원
  order_sniper_manage.py   조건 등록/해제 (persist 포함)
  order_sniper_exec.py     틱 수신·조건 평가·발주

외부 코드에서 OrderSniperMixin 을 임포트하면 그대로 동작한다.
════════════════════════════════════════════════════════
"""

from call_put_tab.order_sniper_manage import OrderSniperManageMixin
from call_put_tab.order_sniper_exec   import OrderSniperExecMixin


class OrderSniperMixin(OrderSniperManageMixin, OrderSniperExecMixin):
    """
    스나이퍼 주문 로직. CallPutGrid에 mixin된다.

    MRO:
      OrderSniperMixin
        → OrderSniperManageMixin   (조건 등록/해제)
          → OrderSniperPersistMixin  (저장·복원)
        → OrderSniperExecMixin     (틱 수신·평가·발주)
    """
