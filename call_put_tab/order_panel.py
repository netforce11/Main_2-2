"""
order_panel.py — 빠른 주문 패널 UI  v7.0  [통합 진입점]
════════════════════════════════════════════════════════
분리된 파일 구조 (order_panel/ 폴더):
  helpers.py          _kst_now / _animate_press / _spx_tag
  tab_new_order.py    탭1 「⚡ 신규」 UI 빌드
  tab_amend_cancel.py 탭2 「✏ 정정」/ 탭3 「✕ 취소」 UI 빌드
  tab_sell.py         탭4 「▼ 빠른매도」 UI 빌드
  tab_sniper.py       탭5 「🎯 스나이퍼」 UI 빌드 + 잔고매도패널
  order_actions.py    미체결 조회·테이블·KST·수수료·유형토글
  sell_actions.py     빠른매도·지정가매도·bump·잔고패널·+1호가
  emergency.py        긴급매도·전체취소
  shortcuts.py        단축키·Enter 포커스 체인

외부에서 기존처럼 임포트하면 그대로 동작:
  from order_panel import OrderPanelMixin
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QTabWidget
from PyQt5.QtCore    import QTimer

from order_panel.helpers           import _kst_now, _animate_press, _spx_tag  # noqa: F401
from order_panel.order_actions     import OrderActionsMixin
from order_panel.sell_actions      import SellActionsMixin
from order_panel.emergency         import EmergencyMixin
from order_panel.shortcuts         import ShortcutsMixin
from order_panel.tab_new_order     import build_new_order_tab
from order_panel.tab_amend_cancel  import build_amend_tab, build_cancel_tab
from order_panel.tab_sell          import build_sell_tab
from order_panel.tab_sniper        import build_sniper_tab, build_pos_sell_panel


class OrderPanelMixin(
    OrderActionsMixin,
    SellActionsMixin,
    EmergencyMixin,
    ShortcutsMixin,
):
    """
    빠른 주문 패널 UI. CallPutGrid에 mixin된다.

    MRO:
      OrderPanelMixin
        → OrderActionsMixin   (미체결 조회·KST·수수료)
        → SellActionsMixin    (빠른매도·bump·+1호가)
        → EmergencyMixin      (긴급매도·전체취소)
        → ShortcutsMixin      (단축키·Enter 체인)
    """

    def _build_quick_order_panel(self) -> QWidget:
        gb   = QGroupBox("⚡ 빠른 주문")
        gb_v = QVBoxLayout(gb)
        gb_v.setSpacing(3); gb_v.setContentsMargins(4, 6, 4, 4)

        _tab_s = (
            "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
            "border:1px solid #2a2a4a;border-bottom:none;font-size:13px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
        tab_w = QTabWidget(); tab_w.setStyleSheet(_tab_s)
        self._qord_tab_widget = tab_w

        # ── 탭 빌드 ─────────────────────────────────────────
        tab_w.addTab(build_new_order_tab(self), "⚡ 신규")
        self._setup_quick_order_shortcuts()     # 신규탭 위젯 생성 후
        build_amend_tab(self, tab_w)
        build_cancel_tab(self, tab_w)
        build_sell_tab(self, tab_w)
        build_sniper_tab(self, tab_w)

        gb_v.addWidget(tab_w)
        gb_v.setSpacing(0)

        # ── 잔고 매도 패널 (하단 슬라이드) ──────────────────
        self._pos_sell_panel = build_pos_sell_panel(self)
        gb_v.addWidget(self._pos_sell_panel)

        # ── KST 시각 타이머 (1초) ────────────────────────────
        self._kst_timer = QTimer(self)
        self._kst_timer.setInterval(1000)
        self._kst_timer.timeout.connect(self._update_kst_labels)
        self._kst_timer.start()

        # ── 체결 감지 → 잔고 자동 갱신 연결 ─────────────────
        QTimer.singleShot(500, self._try_connect_exec_refresh)

        return gb
