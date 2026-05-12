"""
order_panel/shortcuts.py — 단축키 등록 + Enter 포커스 체인
════════════════════════════════════════════════════════
포함 메서드 (OrderPanelMixin에 mixin):
  _setup_quick_order_shortcuts()  Alt+[/]/Enter 단축키 등록
  _sc_focus_price()               가격 필드 포커스
  _sc_focus_qty()                 수량 필드 포커스
  _install_enter_next()           src Enter → dst 포커스 이동
"""

from PyQt5.QtCore import Qt, QObject, QEvent
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtGui import QKeySequence


class ShortcutsMixin:
    """단축키·Enter 포커스 체인 로직. OrderPanelMixin에 mixin된다."""

    def _setup_quick_order_shortcuts(self):
        """
        단축키 등록 + Enter 포커스 흐름 설정.
          Alt+[     → 가격 필드 포커스
          Alt+]     → 수량 필드 포커스
          Alt+Enter → 매수 버튼 클릭
          가격 Enter → 수량 이동 → 매수 버튼 포커스 → Enter = 주문
        """
        sc_price = QShortcut(QKeySequence("Alt+["), self)
        sc_price.setContext(Qt.WidgetWithChildrenShortcut)
        sc_price.activated.connect(self._sc_focus_price)

        sc_qty = QShortcut(QKeySequence("Alt+]"), self)
        sc_qty.setContext(Qt.WidgetWithChildrenShortcut)
        sc_qty.activated.connect(self._sc_focus_qty)

        sc_buy = QShortcut(QKeySequence("Alt+Return"), self)
        sc_buy.setContext(Qt.WidgetWithChildrenShortcut)
        sc_buy.activated.connect(self.btn_qord_buy.click)

        self._install_enter_next(self.qord_price, self.qord_qty)
        self._install_enter_next(self.qord_qty,   self.btn_qord_buy)

    def _sc_focus_price(self):
        self.qord_price.setFocus()
        self.qord_price.selectAll()

    def _sc_focus_qty(self):
        self.qord_qty.setFocus()
        self.qord_qty.selectAll()

    @staticmethod
    def _install_enter_next(src, dst):
        """src 위젯에서 Enter/Return 키 → dst 위젯으로 포커스 이동."""
        class _Filter(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.KeyPress and ev.key() in (
                        Qt.Key_Return, Qt.Key_Enter):
                    dst.setFocus()
                    if hasattr(dst, 'selectAll'):
                        dst.selectAll()
                    return True
                return False

        f = _Filter(src)
        src.installEventFilter(f)
        src._ef_enter = f   # GC 방지
