# watchlist_font_patch.py — 관심종목 폰트 +3 런타임 패치
#
# _build_watchlist_panel() 은 core_fetch.py 에 있어 직접 수정 불가.
# 런타임 패치: tab_options.py CallPutGrid.__init__ 말미에 한 줄 추가:
#     patch_watchlist_font(self, delta=3)

from PyQt5.QtWidgets import QListWidget, QLabel
from PyQt5.QtGui import QFont


def patch_watchlist_font(widget, delta: int = 3):
    """
    CallPutGrid 인스턴스의 관심종목 QListWidget 폰트를 delta 만큼 증가.
    widget 내 모든 QListWidget 과 관련 QLabel 에 적용.
    """
    for lw in widget.findChildren(QListWidget):
        f: QFont = lw.font()
        f.setPointSize(max(8, f.pointSize() + delta))
        lw.setFont(f)
        # 기존 아이템에도 즉시 적용
        for i in range(lw.count()):
            item = lw.item(i)
            if item:
                item.setFont(f)
