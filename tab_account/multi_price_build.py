"""
multi_price_build.py — MultiPriceGrid 전체 UI 빌드 통합 Mixin
════════════════════════════════════════════════════════
분리된 파일:
  multi_price_slots.py   슬롯 3개 + 스플리터 비율
  multi_price_panels.py  트리거·파일·사운드 하단 패널

MultiPriceBuildMixin 을 임포트하면 두 Mixin을 모두 포함한다.
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSplitter

from tab_account.multi_price_slots  import MultiPriceSlotsMixin, _SPLITTER_STYLE
from tab_account.multi_price_panels import MultiPricePanelsMixin


class MultiPriceBuildMixin(MultiPriceSlotsMixin, MultiPricePanelsMixin):
    """전체 UI 빌드 Mixin = Slots + Panels."""

    def _build(self):
        """관심종목 + 슬롯 3개 + 하단 패널(트리거·파일·사운드) 구성."""
        self._build_watchlist()
        self._build_slots()

        bot = QSplitter(Qt.Horizontal)
        bot.setHandleWidth(5)
        bot.setStyleSheet(_SPLITTER_STYLE)
        bot.setChildrenCollapsible(False)
        bot.addWidget(self._build_trigger_panel())
        bot.addWidget(self._build_file_sound_panel())
        bot.setSizes([800, 220])
        self._bot_hsplit = bot
        self.add(bot, 1, 1, 3, 11)
