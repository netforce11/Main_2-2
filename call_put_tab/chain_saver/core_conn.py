"""
core_conn.py — 연결·MDT·SPXW·Zone·만기 로직  v6.5  [분할 버전]
════════════════════════════════════════════════════════
분할 구조 (call_put_tab/ 패키지 내):
  ConnSignalsMixin  ← core_conn_signals.py  (~150줄) 연결 시그널·Watchdog·체결
  ConnIbkrMixin     ← core_conn_ibkr.py     (~100줄) 연결 이벤트·MDT
  ConnSpxwMixin     ← core_conn_spxw.py     (~50줄)  SPXW 0DTE·Zone
  ConnExpiryMixin   ← core_conn_expiry.py   (~150줄) 만기 조회·행사가 계산
  ConnAccountMixin  ← core_conn_account.py  (~170줄) 포트·계좌·미체결

외부 인터페이스 변경 없음. CallPutGrid는 CoreConnMixin만 import.
════════════════════════════════════════════════════════
"""

from call_put_tab.core_conn_signals import ConnSignalsMixin
from call_put_tab.core_conn_ibkr    import ConnIbkrMixin
from call_put_tab.core_conn_spxw    import ConnSpxwMixin
from call_put_tab.core_conn_expiry  import ConnExpiryMixin
from call_put_tab.core_conn_account import ConnAccountMixin


class CoreConnMixin(
    ConnSignalsMixin,
    ConnIbkrMixin,
    ConnSpxwMixin,
    ConnExpiryMixin,
    ConnAccountMixin,
):
    """
    연결·MDT·SPXW·Zone·만기 로직 통합 Mixin.
    CallPutGrid가 다중상속으로 사용한다.
    """
    pass
