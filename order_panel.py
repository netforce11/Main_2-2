"""
order_panel.py — 빠른 주문 패널 UI  v6.7  [S6]
════════════════════════════════════════════════════════
[S6 변경]
  - 탭 구성: 신규 / 정정 / 취소 / 빠른매도  (4탭)
  - 정정·취소 탭 진입 시 미체결 주문 자동 조회
  - 신규 탭 하단 잔고 패널 내장
  - 빠른 매도 버튼 (+0.05/-0.05/+0.10/-0.10 매도)
  - 정정/취소/빠른매도 로직 → order_panel_amend.py
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QRadioButton, QButtonGroup,
    QSpinBox, QTabWidget, QCheckBox,
    QTableWidget, QHeaderView, QAbstractItemView,
    QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from order_panel_amend import AmendPanelMixin
from order_panel_tabs import OrderTabsMixin


# ── 공통 스타일 상수 ──────────────────────────────────────────
_LS   = "color:#aaa;font-size:13px;border:none;"
_ES   = "background:#0a0a1e;color:#ffd700;border:1px solid #444;font-size:15px;"
_FETCH_S = ("background:#1a3a1a;color:#00ff88;font-size:13px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")
_TBL_S = (
    "QTableWidget{background:#05050f;color:#ccc;"
    "gridline-color:#1a1a3a;font-size:13px;}"
    "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
    "border:1px solid #1a1a3a;font-size:12px;}"
    "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}")
_TAB_S = (
    "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
    "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
    "border:1px solid #2a2a4a;border-bottom:none;font-size:13px;}"
    "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
    "border-bottom:1px solid #12122a;}"
    "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
_BUMP_UP   = ("QPushButton{background:#1a3a5a;color:#90caf9;font-size:12px;"
              "font-weight:bold;border-radius:3px;padding:3px 2px;"
              "border:1px solid #3a3a6a;}QPushButton:hover{background:#2a4a6a;}")
_BUMP_DN   = ("QPushButton{background:#3a1a3a;color:#ff90f0;font-size:12px;"
              "font-weight:bold;border-radius:3px;padding:3px 2px;"
              "border:1px solid #3a3a6a;}QPushButton:hover{background:#4a2a4a;}")
_SELL_UP   = ("QPushButton{background:#3a1a1a;color:#ff6666;font-size:12px;"
              "font-weight:bold;border-radius:3px;padding:3px 2px;"
              "border:1px solid #6a2a2a;}QPushButton:hover{background:#5a2a2a;}")
_SELL_DN   = ("QPushButton{background:#1a3a1a;color:#00e676;font-size:12px;"
              "font-weight:bold;border-radius:3px;padding:3px 2px;"
              "border:1px solid #2a6a2a;}QPushButton:hover{background:#2a5a2a;}")


def _make_order_tbl(sel_color="#1a3a6b"):
    tbl = QTableWidget(0, 4)
    tbl.setHorizontalHeaderLabels(["OID", "종목", "방향", "가격"])
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setMaximumHeight(110)
    tbl.setStyleSheet(_TBL_S.replace("#1a3a6b", sel_color))
    return tbl


class OrderPanelMixin(OrderTabsMixin, AmendPanelMixin):
    """빠른 주문 패널 UI. CallPutGrid에 mixin된다."""

    def _build_quick_order_panel(self) -> QWidget:
        gb = QGroupBox("⚡ 빠른 주문")
        gb_v = QVBoxLayout(gb)
        gb_v.setSpacing(3); gb_v.setContentsMargins(4, 6, 4, 4)

        tab_w = QTabWidget(); tab_w.setStyleSheet(_TAB_S)

        tab_w.addTab(self._build_new_tab(),    "⚡ 신규")
        tab_w.addTab(self._build_amend_tab(),  "✏ 정정")
        tab_w.addTab(self._build_cancel_tab(), "✕ 취소")
        tab_w.addTab(self._build_sell_tab(),   "▼ 빠른매도")

        # [S6] 정정·취소 탭 진입 시 미체결 자동 조회
        def _on_tab_changed(idx):
            if idx in (1, 2):   # 정정=1, 취소=2
                QTimer.singleShot(100, self._fetch_open_orders)
        tab_w.currentChanged.connect(_on_tab_changed)

        gb_v.addWidget(tab_w, 1)

        # 잔고 청산 슬라이드업 패널 (기존 유지)
        gb_v.addWidget(self._build_pos_sell_panel())
        return gb