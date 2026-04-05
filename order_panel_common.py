"""order_panel_common.py — 공통 스타일 상수 + _make_order_tbl  [NEW S6]
순환 임포트 방지를 위해 order_panel.py / order_panel_tabs.py 양쪽에서 여기서만 임포트.
"""

from PyQt5.QtWidgets import (
    QTableWidget, QHeaderView, QAbstractItemView,
)

# ── 공통 스타일 상수 ──────────────────────────────────────────
_LS      = "color:#aaa;font-size:13px;border:none;"
_ES      = "background:#0a0a1e;color:#ffd700;border:1px solid #444;font-size:15px;"
_FETCH_S = ("background:#1a3a1a;color:#00ff88;font-size:13px;font-weight:bold;"
            "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")
_TBL_S   = (
    "QTableWidget{background:#05050f;color:#ccc;"
    "gridline-color:#1a1a3a;font-size:13px;}"
    "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
    "border:1px solid #1a1a3a;font-size:12px;}"
    "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}")
_TAB_S   = (
    "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
    "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
    "border:1px solid #2a2a4a;border-bottom:none;font-size:13px;}"
    "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
    "border-bottom:1px solid #12122a;}"
    "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
_BUMP_UP = ("QPushButton{background:#1a3a5a;color:#90caf9;font-size:12px;"
            "font-weight:bold;border-radius:3px;padding:3px 2px;"
            "border:1px solid #3a3a6a;}QPushButton:hover{background:#2a4a6a;}")
_BUMP_DN = ("QPushButton{background:#3a1a3a;color:#ff90f0;font-size:12px;"
            "font-weight:bold;border-radius:3px;padding:3px 2px;"
            "border:1px solid #3a3a6a;}QPushButton:hover{background:#4a2a4a;}")
_SELL_UP = ("QPushButton{background:#3a1a1a;color:#ff6666;font-size:12px;"
            "font-weight:bold;border-radius:3px;padding:3px 2px;"
            "border:1px solid #6a2a2a;}QPushButton:hover{background:#5a2a2a;}")
_SELL_DN = ("QPushButton{background:#1a3a1a;color:#00e676;font-size:12px;"
            "font-weight:bold;border-radius:3px;padding:3px 2px;"
            "border:1px solid #2a6a2a;}QPushButton:hover{background:#2a5a2a;}")


def _make_order_tbl(sel_color: str = "#1a3a6b") -> QTableWidget:
    """미체결 주문 표시용 4열 테이블 팩토리."""
    tbl = QTableWidget(0, 4)
    tbl.setHorizontalHeaderLabels(["OID", "종목", "방향", "가격"])
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setMaximumHeight(110)
    tbl.setStyleSheet(_TBL_S.replace("#1a3a6b", sel_color))
    return tbl
