"""tab_options_price.py — PricePanelMixin: price + position panels [S6]"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QFrame,
    QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush


def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it

_S_SYM        = "color:#5dade2;font-size:14px;font-weight:bold;border:none;"
_S_PRICE      = ("color:#ffd700;font-size:20px;font-weight:bold;"
                 "border:1px solid #2a2a5a;border-radius:3px;"
                 "background:#08080f;padding:2px 4px;")
_S_CHG        = "color:#aaa;font-size:13px;border:none;"
_S_SEP        = "border:none;background:#2a2a5a;max-height:1px;"
_S_HINT       = "color:#444;font-size:9px;border:none;"
_S_TIME       = "color:#2a2a6a;font-size:9px;border:none;"
_S_SP_LBL     = "color:#888;font-size:10px;border:none;"
_S_SP_VAL     = "color:#ffd700;font-size:11px;font-weight:bold;border:none;"
_S_OPT        = "color:#90caf9;font-size:10px;border:none;"
_S_ASK_VAL    = ("color:#ff6666;font-size:14px;font-weight:bold;border:none;"
                 "background:#0a0510;border-radius:2px;padding:1px 4px;")
_S_BID_VAL    = ("color:#33aaff;font-size:14px;font-weight:bold;border:none;"
                 "background:#050a10;border-radius:2px;padding:1px 4px;")


class PricePanelMixin:
    """Builds and updates the price panel (⑤) and position panel (⑥)."""

    # ── ⑤ Price panel ─────────────────────────────────────────
    def _build_price_panel(self) -> QGroupBox:
        gb = QGroupBox("📌 현재가")
        gb.setMinimumWidth(120)
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffd700;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:6px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(3)

        # ① 종목명 + 갱신시각
        row1 = QHBoxLayout(); row1.setSpacing(4)
        self._pp_lbl_sym = QLabel("―")
        self._pp_lbl_sym.setStyleSheet(_S_SYM)
        self._pp_lbl_time = QLabel("―")
        self._pp_lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pp_lbl_time.setStyleSheet(_S_TIME)
        row1.addWidget(self._pp_lbl_sym)
        row1.addStretch()
        row1.addWidget(self._pp_lbl_time)
        v.addLayout(row1)

        # ② 현재가 + 등락
        row2 = QHBoxLayout(); row2.setSpacing(6)
        self._pp_lbl_price = QLabel("―")
        self._pp_lbl_price.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._pp_lbl_price.setStyleSheet(_S_PRICE)
        self._pp_lbl_chg = QLabel("― (―%)")
        self._pp_lbl_chg.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pp_lbl_chg.setStyleSheet(_S_CHG)
        row2.addWidget(self._pp_lbl_price)
        row2.addStretch()
        row2.addWidget(self._pp_lbl_chg)
        v.addLayout(row2)

        # ③ 구분선
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(_S_SEP)
        v.addWidget(sep1)

        # ④ Ask / Bid — QGridLayout (스크롤바 없음)
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)

        for col, txt in enumerate(["", "호가", "값"]):
            lh = QLabel(txt); lh.setAlignment(Qt.AlignCenter)
            lh.setStyleSheet("color:#555;font-size:9px;border:none;"); grid.addWidget(lh, 0, col)

        # Ask / Bid label pairs
        for row_i, (tag_s, val_s, attr, cb) in enumerate([
            ("color:#ff6666;font-size:10px;font-weight:bold;border:none;",
             _S_ASK_VAL, '_pp_lbl_ask_val', lambda e: self._on_pp_quote_click(0, 1)),
            ("color:#33aaff;font-size:10px;font-weight:bold;border:none;",
             _S_BID_VAL, '_pp_lbl_bid_val', lambda e: self._on_pp_quote_click(1, 1)),
        ], start=1):
            side = "Ask" if row_i == 1 else "Bid"
            tag = QLabel(side); tag.setAlignment(Qt.AlignCenter); tag.setStyleSheet(tag_s)
            lbl = QLabel(side); lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(tag_s.replace("font-weight:bold;", ""))
            val = QLabel("―"); val.setAlignment(Qt.AlignCenter); val.setStyleSheet(val_s)
            val.setCursor(Qt.PointingHandCursor); val.mousePressEvent = cb
            setattr(self, attr, val)
            grid.addWidget(tag, row_i, 0); grid.addWidget(lbl, row_i, 1); grid.addWidget(val, row_i, 2)

        grid.setColumnStretch(2, 1)
        v.addLayout(grid)

        # ⑤ 클릭 힌트
        hint = QLabel("↑ 클릭 → 주문창 가격 입력")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(_S_HINT)
        v.addWidget(hint)

        # ⑥ 구분선
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(_S_SEP)
        v.addWidget(sep2)

        # ⑦ 스프레드 + Delta 정보 (한 줄)
        row3 = QHBoxLayout(); row3.setSpacing(6)
        row3.addWidget(QLabel("Spread:", styleSheet=_S_SP_LBL))
        self._pp_lbl_spread = QLabel("―")
        self._pp_lbl_spread.setStyleSheet(_S_SP_VAL)
        row3.addWidget(self._pp_lbl_spread)
        row3.addStretch()
        self._pp_lbl_opt_info = QLabel("")
        self._pp_lbl_opt_info.setStyleSheet(_S_OPT)
        row3.addWidget(self._pp_lbl_opt_info)
        v.addLayout(row3)

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
            "margin-top:6px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(2)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 조회")
        btn_refresh.setFixedHeight(20)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffa500;font-size:10px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_refresh.clicked.connect(self._refresh_positions)
        btn_row.addWidget(btn_refresh); btn_row.addStretch()
        v.addLayout(btn_row)

        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#2a1a0a;"
            "font-size:11px;border:1px solid #3a2a1a;}"
            "QHeaderView::section{background:#0a0805;color:#ffa500;"
            "border:1px solid #2a1a0a;font-size:10px;padding:1px;}"
            "QTableWidget::item{padding:1px;}"
            "QTableWidget::item:selected{background:#3a2a0a;color:#ffd700;}"
            "QTableWidget::item:hover{background:#1a1005;cursor:pointer;}")
        self.tbl_positions = QTableWidget(0, 4)
        self.tbl_positions.setHorizontalHeaderLabels(["C/P", "행사가", "수량", "평균가"])
        self.tbl_positions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_positions.verticalHeader().setVisible(False)
        self.tbl_positions.verticalHeader().setDefaultSectionSize(22)
        self.tbl_positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_positions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_positions.setMinimumHeight(0)
        self.tbl_positions.setStyleSheet(_tbl_s)
        self.tbl_positions.cellClicked.connect(self._on_position_row_click)
        v.addWidget(self.tbl_positions, 1)

        hint = QLabel("↑ 클릭 → 매도 주문창")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(_S_HINT)
        v.addWidget(hint)
        return gb

    # ── Update helpers ─────────────────────────────────────────
    def _pp_set_quote(self, ask, bid):
        self._pp_lbl_ask_val.setText(f"{ask:.2f}" if ask else "―")
        self._pp_lbl_bid_val.setText(f"{bid:.2f}" if bid else "―")
        self._pp_lbl_spread.setText(
            f"{ask - bid:.2f}" if ask and bid else "―")

    def _update_price_panel(self):
        if not hasattr(self, '_pp_lbl_price'): return
        if getattr(self, '_pp_mode', 'und') != 'und': return

        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "―"
        price = getattr(self, 'und_price', None)
        prev  = getattr(self, 'und_prev',  None)

        self._pp_lbl_sym.setText(sym)
        self._pp_lbl_sym.setStyleSheet(_S_SYM)
        if price:
            self._pp_lbl_price.setText(f"{price:,.2f}")
            if prev and prev > 0:
                chg = price - prev; pct = chg / prev * 100
                sign = "+" if chg >= 0 else ""
                col  = "#00e676" if chg >= 0 else "#ff5252"
                self._pp_lbl_chg.setText(f"{sign}{chg:.2f} ({sign}{pct:.2f}%)")
                self._pp_lbl_chg.setStyleSheet(
                    f"color:{col};font-size:11px;border:none;")
            else:
                self._pp_lbl_chg.setText("― (―%)")
                self._pp_lbl_chg.setStyleSheet(_S_CHG)
        else:
            self._pp_lbl_price.setText("―")

        self._pp_set_quote(self._pp_ask, self._pp_bid)
        self._pp_lbl_opt_info.setText("")
        self._pp_lbl_time.setText(datetime.now().strftime("%H:%M:%S"))

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
        self._pp_lbl_price.setText(
            f"{(bid+ask)/2:.2f}" if bid and ask else (f"{ask:.2f}" if ask else "―"))
        self._pp_lbl_chg.setText(f"행사가  {strike}")
        self._pp_lbl_chg.setStyleSheet(
            f"color:{col};font-size:11px;border:none;font-weight:bold;")
        self._pp_set_quote(ask, bid)
        self._pp_lbl_opt_info.setText(f"Δ {delta:+.4f}" if delta is not None else "")
        self._pp_lbl_time.setText(datetime.now().strftime("%H:%M:%S"))

    def _pp_switch_to_und(self):
        self._pp_mode = "und"
        self._pp_lbl_sym.setStyleSheet(_S_SYM)
        self._pp_lbl_chg.setStyleSheet(_S_CHG)
        self._pp_lbl_opt_info.setText("")
        self._update_price_panel()

    # ── Click handlers ─────────────────────────────────────────
    def _on_position_row_click(self, row: int, col: int):
        tbl = self.tbl_positions
        cp_item = tbl.item(row, 0); strike_item = tbl.item(row, 1)
        qty_item = tbl.item(row, 2); price_item  = tbl.item(row, 3)
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
        """Ask(row=0) or Bid(row=1) → fill quick-order price."""
        if not hasattr(self, 'qord_price'): return
        mode = getattr(self, '_pp_mode', 'und')
        val = (self._pp_opt_ask if row == 0 else self._pp_opt_bid) if mode == 'opt' \
              else (self._pp_ask  if row == 0 else self._pp_bid)
        if val:
            self.qord_price.setText(f"{val:.2f}")
            src = "Ask" if row == 0 else "Bid"
            if hasattr(self, 'lbl_qord_src'):
                self.lbl_qord_src.setText(f"← {src} 클릭")
            if hasattr(self, '_log'):
                self._log(f"주문가격 자동입력: {src} {val:.2f}")
