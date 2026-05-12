"""
multi_price_grid.py — MultiPriceGrid (복수 현재가 탭) 메인 클래스
════════════════════════════════════════════════════════
포함 내용:
  - MultiPriceGrid(GridTab)
      __init__()   초기화 (슬롯 데이터, RID, 알람 경로)
      → _build()           UI 빌드  (MultiPriceBuildMixin)
      → _connect_signals() 시그널   (MultiPriceLogicMixin)

의존:
  account.multi_price_build  UI 빌드
  account.multi_price_logic  슬롯·틱·트리거·사운드·파일 로직
════════════════════════════════════════════════════════
"""

from core import GridTab, REQ_MULTI

from tab_account.multi_price_build import MultiPriceBuildMixin
from tab_account.multi_price_logic import MultiPriceLogicMixin


class MultiPriceGrid(MultiPriceBuildMixin, MultiPriceLogicMixin, GridTab):
    """
    복수 현재가 탭 (Tab 5).

    MRO:
      MultiPriceGrid
        → MultiPriceBuildMixin  (UI 빌드)
        → MultiPriceLogicMixin  (슬롯·틱·트리거·사운드·파일)
        → GridTab
    """
    SLOTS = 3

    def __init__(self, mw):
        GridTab.__init__(self)
        self.mw               = mw
        self.slot_data        = [{} for _ in range(self.SLOTS)]
        self.slot_rids        = [REQ_MULTI + i * 100 for i in range(self.SLOTS)]
        self.trigger_logs     = []
        self._alert_sound_path = ""
        self._build()
        self._connect_signals()
        self._restore_sound_setting()
