"""combo_ui_synthetic_panel.py — SyntheticStatusPanel 위젯
탭1: 📊 증거금 확인 (update_margin)  탭2: 📋 합성 잔고 (add_position)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QTableWidget, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QSizePolicy,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

# ── 폰트 상수 (setFont로 적용 — QSS font-size 캐스케이딩 우회) ───
def _f(pt, bold=False):
    f = QFont(); f.setPointSize(pt)
    if bold: f.setBold(True)
    return f

_TAB_STYLE = """
QTabWidget::pane { border:1px solid #1a1a3a; background:#07070f; }
QTabBar::tab { background:#0d0d22; color:#666688;
    padding:5px 12px; border:1px solid #1a1a3a; border-bottom:none; }
QTabBar::tab:selected { background:#07070f; color:#e0e0ff; border-top:2px solid #00ff88; }
QTabBar::tab:hover { color:#aaaacc; }
"""
_TBL_STYLE = """
QTableWidget { background:#07070f; alternate-background-color:#0c0c20;
    color:#cccccc; gridline-color:#1a1a3a; border:none; }
QTableWidget::item:selected { background:#1a1a3a; color:#ffffff; }
QHeaderView::section { background:#0a0a1e; color:#90caf9;
    border:1px solid #1a1a3a; font-weight:bold; padding:3px 6px; }
"""


class SyntheticStatusPanel(QWidget):
    """합성 주문 상태 패널 (v2.5)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#07070f;")
        self._positions = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.tabBar().setFont(_f(12, bold=True))
        self._tabs.addTab(self._build_margin_tab(),   "📊 증거금 확인")
        self._tabs.addTab(self._build_position_tab(), "📋 합성 잔고")
        root.addWidget(self._tabs)

    def _build_margin_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(5)

        def kv(label):
            row = QHBoxLayout()
            lk = QLabel(label); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
            lv = QLabel("―");   lv.setStyleSheet("color:#e0e0e0;border:none;"); lv.setFont(_f(13, True))
            row.addWidget(lk); row.addStretch(); row.addWidget(lv)
            return row, lv

        row_s, self._lbl_m_strategy  = kv("전략명")
        row_c, self._lbl_m_cost      = kv("순 비용")
        row_a, self._lbl_m_available = kv("주문가능")
        row_r, self._lbl_m_required  = kv("필요증거금")

        for row in (row_s, row_c): lay.addLayout(row)
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color:#1a1a3a; max-height:1px;"); lay.addWidget(sep1)
        for row in (row_a, row_r): lay.addLayout(row)
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#1a1a3a; max-height:1px;"); lay.addWidget(sep2)

        self._lbl_margin_status = QLabel("―")
        self._lbl_margin_status.setAlignment(Qt.AlignCenter)
        self._lbl_margin_status.setFont(_f(13, bold=True))
        self._lbl_margin_status.setStyleSheet(
            "color:#555577;padding:7px;border:1px solid #2a2a4a;"
            "border-radius:4px;background:#0a0a1e;")
        lay.addWidget(self._lbl_margin_status)
        lay.addStretch()
        return w

    def _build_position_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        summary = QHBoxLayout()
        lk = QLabel("총 손익"); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
        self._lbl_total_pnl = QLabel("$0.00")
        self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
        self._lbl_total_pnl.setFont(_f(14, bold=True))
        summary.addWidget(lk); summary.addStretch(); summary.addWidget(self._lbl_total_pnl)
        lay.addLayout(summary)

        self._lbl_no_pos = QLabel("체결된 합성 포지션이 없습니다.")
        self._lbl_no_pos.setAlignment(Qt.AlignCenter)
        self._lbl_no_pos.setFont(_f(12))
        self._lbl_no_pos.setStyleSheet("color:#333355;padding:14px;")
        lay.addWidget(self._lbl_no_pos)

        self._tbl_pos = QTableWidget(0, 5)
        self._tbl_pos.setHorizontalHeaderLabels(["전략명","수량","진입가","현재가","손익"])
        self._tbl_pos.setFont(_f(12))
        self._tbl_pos.horizontalHeader().setFont(_f(11, bold=True))
        self._tbl_pos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            self._tbl_pos.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_pos.verticalHeader().setVisible(False)
        self._tbl_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_pos.setAlternatingRowColors(True)
        self._tbl_pos.setStyleSheet(_TBL_STYLE)
        self._tbl_pos.setVisible(False)
        lay.addWidget(self._tbl_pos, 1)
        return w

    # ── Public API ────────────────────────────────────────────
    def update_margin(self, available: float, required: float,
                      strategy: str = "―", cost: str = "―"):
        self._lbl_m_strategy.setText(strategy or "―")
        self._lbl_m_cost.setText(cost or "―")
        self._lbl_m_available.setText(f"${available:,.2f}")
        self._lbl_m_required.setText(f"${required:,.2f}")
        if required <= 0:
            st, col, bg, bc = "— 데이터 없음 —", "#555577", "#0a0a1e", "#2a2a4a"
        elif available >= required:
            surplus = available - required
            st, col, bg, bc = f"✅  주문 가능  (여유 ${surplus:,.2f})", "#00ff88", "#071a0e", "#00ff88"
        else:
            shortage = required - available
            st, col, bg, bc = f"❌  증거금 부족  (${shortage:,.2f} 부족)", "#ff4444", "#1a0707", "#ff4444"
        self._lbl_margin_status.setText(st)
        self._lbl_margin_status.setStyleSheet(
            f"color:{col};padding:7px;border:1px solid {bc};"
            f"border-radius:4px;background:{bg};")
        self._tabs.setCurrentIndex(0)

    def add_position(self, fill_info: dict):
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def update_position_prices(self, strategy: str, current_price: float):
        for pos in self._positions:
            if pos.get("strategy") == strategy:
                pos["current"] = current_price
        self._refresh_pos_table()

    def clear_positions(self):
        self._positions.clear()
        self._refresh_pos_table()

    def _refresh_pos_table(self):
        tbl = self._tbl_pos
        tbl.setRowCount(0)
        if not self._positions:
            self._lbl_no_pos.setVisible(True); tbl.setVisible(False)
            self._lbl_total_pnl.setText("$0.00")
            self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
            return
        self._lbl_no_pos.setVisible(False); tbl.setVisible(True)
        tbl.setRowCount(len(self._positions))
        total_pnl = 0.0
        for r, pos in enumerate(self._positions):
            qty     = pos.get("qty", 1)
            entry   = pos.get("entry", 0.0)
            current = pos.get("current", entry)
            pnl     = (current - entry) * qty * 100
            total_pnl += pnl
            pnl_col = "#00ff88" if pnl > 0 else "#ff4444" if pnl < 0 else "#888899"

            def _it(text, color="#cccccc", align=Qt.AlignCenter):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            tbl.setItem(r, 0, _it(pos.get("strategy","―"), "#e0e0ff", Qt.AlignLeft|Qt.AlignVCenter))
            tbl.setItem(r, 1, _it(str(qty),          "#aaaaaa"))
            tbl.setItem(r, 2, _it(f"${entry:.2f}",   "#aaaaaa"))
            tbl.setItem(r, 3, _it(f"${current:.2f}", "#e0e0e0"))
            tbl.setItem(r, 4, _it(f"${pnl:+,.2f}",  pnl_col))

        tc = "#00ff88" if total_pnl > 0 else "#ff4444" if total_pnl < 0 else "#888899"
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")