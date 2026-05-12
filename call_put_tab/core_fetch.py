"""
core_fetch.py — 조회·기초자산·테이블클릭·관심종목 로직 v6.5
════════════════════════════════════════════════════════
[리팩토링] 기능별 파일 분리 후 하위 호환 통합 진입점으로 변경.

분리된 파일 구조:
  core_fetch_contracts.py   계약 생성·만기 계산
  core_fetch_subscribe.py   기초자산 구독·옵션 체인 조회
  core_fetch_table.py       테이블 클릭·옵션 차트 스냅샷
  core_fetch_watchlist.py   관심종목 관리

외부 코드에서 기존처럼 CoreFetchMixin 을 임포트하면 그대로 동작한다.
════════════════════════════════════════════════════════
"""

from call_put_tab.core_fetch_contracts import (
    make_opt_contract_safe,
    _mdt_for_sym,
    _alive,
    _DELAYED_SYMS,
    CoreFetchContractsMixin,
)
from call_put_tab.core_fetch_subscribe import CoreFetchSubscribeMixin
from call_put_tab.core_fetch_table import CoreFetchTableMixin, _DummyLabel
from call_put_tab.core_fetch_watchlist import CoreFetchWatchlistMixin
from call_put_tab.core_fetch_pos import CoreFetchPosMixin   # 기존 포지션 mixin


class CoreFetchMixin(CoreFetchWatchlistMixin, CoreFetchPosMixin):
    """
    조회·기초자산·테이블클릭·관심종목 로직.
    CallPutGrid에 mixin된다.

    MRO(상속 순서):
      CoreFetchMixin
        → CoreFetchWatchlistMixin  (관심종목)
          → CoreFetchTableMixin    (테이블 클릭·스냅샷)
            → CoreFetchSubscribeMixin  (구독·체인 조회)
              → CoreFetchContractsMixin  (계약·만기)
        → CoreFetchPosMixin        (포지션)
    """
