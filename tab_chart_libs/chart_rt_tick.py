"""
chart_rt_tick.py — IBKR 틱 구독 헬퍼 (차트용)
[분리] chart_rt.py 에서 분리
  _on_chart_tick, _set_p3_visible,
  _start_tick_subscription, _stop_tick_subscription
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from core import router

REQ_CHART_TICK = 6600

def _on_chart_tick(rid: int, tt: int, price: float):
    """TickRouter → chart_tick_speed 전달 슬롯."""
    try:
        from chart_tick_speed import on_ibkr_tick
        on_ibkr_tick(tt, price)
    except Exception:
        pass


def _set_p3_visible(self, visible: bool):
    """p3 틱속도 패널 표시/숨김."""
    try:
        self.p3.setVisible(visible)
    except Exception:
        pass


def _start_tick_subscription(self, symbol: str):
    """
    IBKR reqMktData(REQ_CHART_TICK) 구독 시작.
    make_und_contract 로 SPX/주식 모두 대응.
    """
    if not getattr(self.mw, 'connected', False):
        return
    try:
        from core_contract import make_und_contract
        from chart_tick_speed import set_current_sym
        set_current_sym(symbol)          # DB 저장용 종목명 갱신
        c = make_und_contract(symbol)
        self.mw.ib.reqMktData(REQ_CHART_TICK, c, "", False, False, [])
        router.register_price(REQ_CHART_TICK, REQ_CHART_TICK, _on_chart_tick)
        self._chart_tick_subscribed = True
        print(f"[ChartTick] {symbol} 구독 시작 reqId={REQ_CHART_TICK}")
    except Exception as e:
        print(f"[ChartTick] 구독 실패: {e}")
        self._chart_tick_subscribed = False


def _stop_tick_subscription(self):
    """cancelMktData + router unregister."""
    if not getattr(self, '_chart_tick_subscribed', False):
        return
    try:
        if getattr(self.mw, 'connected', False):
            self.mw.ib.cancelMktData(REQ_CHART_TICK)
        router.unregister_price(_on_chart_tick)
        self._chart_tick_subscribed = False
        print(f"[ChartTick] 구독 해제 reqId={REQ_CHART_TICK}")
    except Exception as e:
        print(f"[ChartTick] 해제 실패: {e}")