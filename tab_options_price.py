"""
tab_options_price.py — PricePanelMixin: price + position panels  [NEW — S6]
Extracted from tab_options.py to keep files ≤ 300 lines.
Includes _build_price_panel, _build_position_panel, update/click handlers.
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush


def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


class PricePanelMixin:
    """Builds and updates the price panel (⑤) and position panel (⑥)."""

    # ── ⑤ Price panel ─────────────────────────────────────────
    def _build_price_panel(self) -> QGroupBox:
        gb = QGroupBox("📌 현재가")
        gb.setMinimumWidth(120)
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffd700;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb); v.setContentsMargins(5, 8, 5, 5); v.setSpacing(4)

        self._pp_lbl_sym = QLabel("―")
        self._pp_lbl_sym.setAlignment(Qt.AlignCenter)
        self._pp_lbl_sym.setStyleSheet(
            "color:#5dade2;font-size:14px;font-weight:bold;border:none;")
        v.addWidget(self._pp_lbl_sym)

        self._pp_lbl_price = QLabel("―")
        self._pp_lbl_price.setAlignment(Qt.AlignCenter)
        self._pp_lbl_price.setStyleSheet(
            "color:#ffd700;font-size:22px;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "background:#08080f;padding:4px;")
        v.addWidget(self._pp_lbl_price)

        self._pp_lbl_chg = QLabel("― (―%)")
        self._pp_lbl_chg.setAlignment(Qt.AlignCenter)
        self._pp_lbl_chg.setStyleSheet("color:#aaa;font-size:14px;border:none;")
        v.addWidget(self._pp_lbl_chg)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        v.addWidget(sep1)

        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#1a1a3a;"
            "font-size:13px;border:1px solid #2a2a5a;}"
            "QHeaderView::section{background:#0a0a1e;color:#5dade2;"
            "border:1px solid #1a1a3a;font-size:11px;padding:2px;}"
            "QTableWidget::item{padding:3px;}"
            "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}"
            "QTableWidget::item:hover{background:#12122a;cursor:pointer;}")
        self._pp_tbl_quote = QTableWidget(2, 2)
        self._pp_tbl_quote.setHorizontalHeaderLabels(["호가", "값"])
        self._pp_tbl_quote.setVerticalHeaderLabels(["Ask", "Bid"])
        self._pp_tbl_quote.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._pp_tbl_quote.verticalHeader().setVisible(True)
        self._pp_tbl_quote.verticalHeader().setDefaultSectionSize(32)
        self._pp_tbl_quote.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._pp_tbl_quote.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._pp_tbl_quote.setFixedHeight(90)
        self._pp_tbl_quote.setStyleSheet(_tbl_s)
        self._pp_tbl_quote.setItem(0, 0, _mk("Ask", "#ff6666"))
        self._pp_tbl_quote.setItem(0, 1, _mk("―",   "#ff6666"))
        self._pp_tbl_quote.setItem(1, 0, _mk("Bid",  "#33aaff"))
        self._pp_tbl_quote.setItem(1, 1, _mk("―",   "#33aaff"))
        self._pp_tbl_quote.cellClicked.connect(self._on_pp_quote_click)
        v.addWidget(self._pp_tbl_quote)

        hint = QLabel("↑ 클릭 → 주문창 가격 입력")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#444;font-size:9px;border:none;")
        v.addWidget(hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        v.addWidget(sep2)

        spread_row = QHBoxLayout()
        spread_row.addWidget(QLabel("스프레드:",
            styleSheet="color:#aaa;font-size:10px;border:none;"))
        self._pp_lbl_spread = QLabel("―")
        self._pp_lbl_spread.setStyleSheet(
            "color:#ffd700;font-size:13px;border:none;font-weight:bold;")
        spread_row.addWidget(self._pp_lbl_spread); spread_row.addStretch()
        v.addLayout(spread_row)

        self._pp_lbl_opt_info = QLabel("")
        self._pp_lbl_opt_info.setAlignment(Qt.AlignCenter)
        self._pp_lbl_opt_info.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        v.addWidget(self._pp_lbl_opt_info)
        v.addStretch()

        self._pp_lbl_time = QLabel("―")
        self._pp_lbl_time.setAlignment(Qt.AlignCenter)
        self._pp_lbl_time.setStyleSheet("color:#333;font-size:9px;border:none;")
        v.addWidget(self._pp_lbl_time)

        # Internal state
        self._pp_bid = None; self._pp_ask = None
        self._pp_mode = "und"
        self._pp_opt_side = ""; self._pp_opt_strike = ""
        self._pp_opt_bid = None; self._pp_opt_ask = None
        return gb

    # ── ⑥ Position panel ──────────────────────────────────────
    def _build_position_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 잔고")
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffa500;font-weight:bold;"
            "border:1px solid #3a2a1a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb); v.setContentsMargins(4, 8, 4, 4); v.setSpacing(3)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 조회"); btn_refresh.setFixedHeight(22)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffa500;font-size:11px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_refresh.clicked.connect(self._refresh_positions)
        btn_row.addWidget(btn_refresh); btn_row.addStretch()
        v.addLayout(btn_row)

        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#2a1a0a;"
            "font-size:12px;border:1px solid #3a2a1a;}"
            "QHeaderView::section{background:#0a0805;color:#ffa500;"
            "border:1px solid #2a1a0a;font-size:11px;padding:2px;}"
            "QTableWidget::item{padding:2px;}"
            "QTableWidget::item:selected{background:#3a2a0a;color:#ffd700;}"
            "QTableWidget::item:hover{background:#1a1005;cursor:pointer;}")
        self.tbl_positions = QTableWidget(0, 4)
        self.tbl_positions.setHorizontalHeaderLabels(["C/P","행사가","수량","평균가"])
        self.tbl_positions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_positions.verticalHeader().setVisible(False)
        self.tbl_positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_positions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_positions.setStyleSheet(_tbl_s)
        self.tbl_positions.cellClicked.connect(self._on_position_row_click)
        v.addWidget(self.tbl_positions)

        hint = QLabel("↑ 클릭 → 매도 주문창")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#444;font-size:9px;border:none;")
        v.addWidget(hint)
        return gb

    # ── Update methods ─────────────────────────────────────────
    def _update_price_panel(self):
        if not hasattr(self, '_pp_lbl_price'): return
        if getattr(self, '_pp_mode', 'und') != 'und': return

        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "―"
        price = getattr(self, 'und_price', None)
        prev  = getattr(self, 'und_prev',  None)

        self._pp_lbl_sym.setText(sym)
        if price:
            self._pp_lbl_price.setText(f"{price:,.2f}")
            if prev and prev > 0:
                chg = price - prev; pct = chg / prev * 100
                sign = "+" if chg >= 0 else ""
                col  = "#00e676" if chg >= 0 else "#ff5252"
                self._pp_lbl_chg.setText(f"{sign}{chg:,.2f}  ({sign}{pct:.2f}%)")
                self._pp_lbl_chg.setStyleSheet(f"color:{col};font-size:14px;border:none;")
            else:
                self._pp_lbl_chg.setText("― (―%)")
        else:
            self._pp_lbl_price.setText("―")

        ask = self._pp_ask; bid = self._pp_bid
        self._pp_tbl_quote.setItem(0, 1, _mk(f"{ask:.2f}" if ask else "―", "#ff6666"))
        self._pp_tbl_quote.setItem(1, 1, _mk(f"{bid:.2f}" if bid else "―", "#33aaff"))
        self._pp_lbl_spread.setText(f"{ask - bid:.2f}" if ask and bid else "―")
        self._pp_lbl_opt_info.setText("")
        self._pp_lbl_time.setText(datetime.now().strftime("갱신 %H:%M:%S"))

    def _update_price_panel_opt(self, side, strike, bid, ask, delta=None):
        if not hasattr(self, '_pp_lbl_price'): return
        self._pp_mode = "opt"; self._pp_opt_side = side
        self._pp_opt_strike = strike; self._pp_opt_bid = bid; self._pp_opt_ask = ask

        label = "CALL" if side == "C" else "PUT"
        col   = "#33aaff" if side == "C" else "#ff6666"
        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""

        self._pp_lbl_sym.setText(f"{sym}  {label}")
        self._pp_lbl_sym.setStyleSheet(
            f"color:{col};font-size:14px;font-weight:bold;border:none;")

        if bid and ask:
            mid = (bid + ask) / 2
            self._pp_lbl_price.setText(f"{mid:.2f}")
            self._pp_lbl_spread.setText(f"{ask - bid:.2f}")
        elif ask:
            self._pp_lbl_price.setText(f"{ask:.2f}")
            self._pp_lbl_spread.setText("―")
        else:
            self._pp_lbl_price.setText("―"); self._pp_lbl_spread.setText("―")

        self._pp_lbl_chg.setText(f"행사가  {strike}")
        self._pp_lbl_chg.setStyleSheet(
            f"color:{col};font-size:14px;border:none;font-weight:bold;")
        self._pp_tbl_quote.setItem(0, 1, _mk(f"{ask:.2f}" if ask else "―", "#ff6666"))
        self._pp_tbl_quote.setItem(1, 1, _mk(f"{bid:.2f}" if bid else "―", "#33aaff"))
        self._pp_lbl_opt_info.setText(f"Δ {delta:+.4f}" if delta is not None else "")
        self._pp_lbl_time.setText(datetime.now().strftime("갱신 %H:%M:%S"))

    def _pp_switch_to_und(self):
        self._pp_mode = "und"
        self._pp_lbl_sym.setStyleSheet(
            "color:#5dade2;font-size:14px;font-weight:bold;border:none;")
        self._pp_lbl_chg.setStyleSheet("color:#aaa;font-size:14px;border:none;")
        self._pp_lbl_opt_info.setText("")
        self._update_price_panel()

    def _on_position_row_click(self, row: int, col: int):
        tbl = self.tbl_positions
        cp_item = tbl.item(row, 0); strike_item = tbl.item(row, 1)
        qty_item = tbl.item(row, 2); price_item = tbl.item(row, 3)
        if not cp_item or not strike_item: return

        side   = "C" if "C" in cp_item.text() else "P"
        strike = strike_item.text().strip()
        try:    qty = abs(int(qty_item.text())) if qty_item else 1
        except Exception: qty = 1
        try:    price = float(price_item.text()) if price_item else None
        except Exception: price = None

        if hasattr(self, '_show_pos_sell_panel'):
            self._show_pos_sell_panel(side, strike, qty=qty, price=price)

    def _on_pp_quote_click(self, row: int, col: int):
        if not hasattr(self, 'qord_price'): return
        mode = getattr(self, '_pp_mode', 'und')
        val = (self._pp_opt_ask if row == 0 else self._pp_opt_bid) if mode == 'opt' \
              else (self._pp_ask if row == 0 else self._pp_bid)
        if val:
            self.qord_price.setText(f"{val:.2f}")
            src = "Ask" if row == 0 else "Bid"
            if hasattr(self, 'lbl_qord_src'):
                self.lbl_qord_src.setText(f"← 현재가 {src} 클릭")
            if hasattr(self, '_log'):
                self._log(f"주문가격 자동입력: {src} {val:.2f}")
