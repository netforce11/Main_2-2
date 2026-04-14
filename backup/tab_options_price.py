"""tab_options_price.py — PricePanelMixin: price + position panels [S9]
변경: _on_position_row_click → order_panel_util.py(OrderUtilMixin)로 일원화
      (중복 정의 제거 — MRO 충돌 및 _ps_expiry 미세팅 문제 해소)
      _build_tbl_panel 에서 price/position을 QSplitter로 분리 (panels.py에서 호출)
      _update_price_panel_opt → 전략 패널 _strat_on_chain_click 연동 [S9]
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QFrame, QSplitter,
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
    """Builds and updates the price panel and position panel."""

    # ── Price panel ────────────────────────────────────────────
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

        row1 = QHBoxLayout(); row1.setSpacing(4)
        self._pp_lbl_sym = QLabel("―")
        self._pp_lbl_sym.setStyleSheet(_S_SYM)
        self._pp_lbl_time = QLabel("―")
        self._pp_lbl_time.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pp_lbl_time.setStyleSheet(_S_TIME)
        row1.addWidget(self._pp_lbl_sym); row1.addStretch()
        row1.addWidget(self._pp_lbl_time)
        v.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        self._pp_lbl_price = QLabel("―")
        self._pp_lbl_price.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._pp_lbl_price.setStyleSheet(_S_PRICE)
        self._pp_lbl_chg = QLabel("― (―%)")
        self._pp_lbl_chg.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pp_lbl_chg.setStyleSheet(_S_CHG)
        row2.addWidget(self._pp_lbl_price); row2.addStretch()
        row2.addWidget(self._pp_lbl_chg)
        v.addLayout(row2)

        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet(_S_SEP)
        v.addWidget(sep1)

        grid = QGridLayout(); grid.setSpacing(2); grid.setContentsMargins(0, 0, 0, 0)
        for col, txt in enumerate(["", "호가", "값"]):
            lh = QLabel(txt); lh.setAlignment(Qt.AlignCenter)
            lh.setStyleSheet("color:#555;font-size:9px;border:none;"); grid.addWidget(lh, 0, col)

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

        hint = QLabel("↑ 클릭 → 주문창 가격 입력")
        hint.setAlignment(Qt.AlignCenter); hint.setStyleSheet(_S_HINT)
        v.addWidget(hint)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(_S_SEP); v.addWidget(sep2)

        row3 = QHBoxLayout(); row3.setSpacing(6)
        row3.addWidget(QLabel("Spread:", styleSheet=_S_SP_LBL))
        self._pp_lbl_spread = QLabel("―"); self._pp_lbl_spread.setStyleSheet(_S_SP_VAL)
        row3.addWidget(self._pp_lbl_spread); row3.addStretch()
        self._pp_lbl_opt_info = QLabel(""); self._pp_lbl_opt_info.setStyleSheet(_S_OPT)
        row3.addWidget(self._pp_lbl_opt_info)
        v.addLayout(row3)

        self._pp_bid = None; self._pp_ask = None
        self._pp_mode = "und"
        self._pp_opt_side = ""; self._pp_opt_strike = ""
        self._pp_opt_bid = None; self._pp_opt_ask = None
        self._pp_is_nanos = False   # ✅ NANOS 호가 ×10 보정 플래그
        return gb

    # ── Position panel ─────────────────────────────────────────
    def _build_position_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 잔고")
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffa500;font-weight:bold;"
            "border:1px solid #3a2a1a;border-radius:4px;"
            "margin-top:6px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb)
        v.setContentsMargins(4, 6, 4, 4); v.setSpacing(2)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("🔄 조회")
        btn_refresh.setFixedHeight(20)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffa500;font-size:10px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_refresh.clicked.connect(
            lambda: self._refresh_positions()
            if hasattr(self, '_refresh_positions')
            else self._log("⚠ _refresh_positions 미연결 — CoreFetchPosMixin MRO 확인")
        )
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
        self.tbl_positions = QTableWidget(0, 5)
        self.tbl_positions.setHorizontalHeaderLabels(["C/P", "행사가", "수량", "평균가", "평가손익"])
        self.tbl_positions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_positions.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tbl_positions.verticalHeader().setVisible(False)
        self.tbl_positions.verticalHeader().setDefaultSectionSize(22)
        self.tbl_positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_positions.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_positions.setMinimumHeight(0)
        self.tbl_positions.setStyleSheet(_tbl_s)
        # _on_position_row_click은 OrderUtilMixin에 정의 — 런타임에 바인딩
        self.tbl_positions.cellClicked.connect(
            lambda r, c: self._on_position_row_click(r, c))
        v.addWidget(self.tbl_positions, 1)

        hint = QLabel("↑ 클릭 → 빠른매도 탭으로 이동")
        hint.setAlignment(Qt.AlignCenter); hint.setStyleSheet(_S_HINT)
        v.addWidget(hint)
        return gb

    # ── Price+Position 수직 분할 위젯 (panels.py에서 호출) ────
    def _build_price_pos_widget(self) -> QSplitter:
        """현재가(상단) + 잔고(하단) 수직 QSplitter."""
        spl = QSplitter(Qt.Vertical)
        spl.setHandleWidth(4)
        spl.setStyleSheet(
            "QSplitter::handle{background:#2a2a5a;}"
            "QSplitter::handle:hover{background:#4a4a9a;}")
        spl.addWidget(self._build_price_panel())
        spl.addWidget(self._build_position_panel())
        spl.setSizes([220, 160])
        return spl

    # ── Update helpers ─────────────────────────────────────────
    def _pp_set_quote(self, ask, bid):
        self._pp_lbl_ask_val.setText(f"{ask:.2f}" if ask else "―")
        self._pp_lbl_bid_val.setText(f"{bid:.2f}" if bid else "―")
        self._pp_lbl_spread.setText(f"{ask - bid:.2f}" if ask and bid else "―")

    def _update_price_panel(self):
        if not hasattr(self, '_pp_lbl_price'): return
        if getattr(self, '_pp_mode', 'und') != 'und': return
        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "―"
        price = getattr(self, 'und_price', None)
        prev  = getattr(self, 'und_prev',  None)
        self._pp_lbl_sym.setText(sym); self._pp_lbl_sym.setStyleSheet(_S_SYM)
        if price:
            self._pp_lbl_price.setText(f"{price:,.2f}")
            if prev and prev > 0:
                chg = price - prev; pct = chg / prev * 100
                sign = "+" if chg >= 0 else ""
                col  = "#00e676" if chg >= 0 else "#ff5252"
                self._pp_lbl_chg.setText(f"{sign}{chg:.2f} ({sign}{pct:.2f}%)")
                self._pp_lbl_chg.setStyleSheet(f"color:{col};font-size:11px;border:none;")
            else:
                self._pp_lbl_chg.setText("― (―%)"); self._pp_lbl_chg.setStyleSheet(_S_CHG)
        else:
            self._pp_lbl_price.setText("―")
        self._pp_set_quote(self._pp_ask, self._pp_bid)
        self._pp_lbl_opt_info.setText("")
        self._pp_lbl_time.setText(datetime.now().strftime("%H:%M:%S"))

        # ── 사이드바 기초자산 패널 동기화 ────────────────────────
        if hasattr(self, '_side_und_price'):
            self._side_und_sym.setText(sym)
            if price:
                self._side_und_price.setText(f"{price:,.2f}")
                if prev and prev > 0:
                    chg = price - prev; pct = chg / prev * 100
                    sign = "+" if chg >= 0 else ""
                    col  = "#00e676" if chg >= 0 else "#ff5252"
                    self._side_und_chg.setText(f"{sign}{chg:.2f} ({sign}{pct:.2f}%)")
                    self._side_und_chg.setStyleSheet(
                        f"color:{col};font-size:10px;border:none;")
                else:
                    self._side_und_chg.setText("― (―%)")
                    self._side_und_chg.setStyleSheet("color:#aaa;font-size:10px;border:none;")
            else:
                self._side_und_price.setText("―")
            # 만기 동기화
            if hasattr(self, 'combo_exp'):
                self._side_und_exp.setText(f"만기: {self.combo_exp.currentText()}")
            # Zone 동기화
            zone = getattr(self, '_zone', 'ATM')
            zone_colors = {
                "OTM2": "#00b894", "OTM1": "#00e676",
                "ATM":  "#ffd700",
                "ITM1": "#ff8800", "ITM2": "#ff4444",
            }
            zcol = zone_colors.get(zone, "#ffd700")
            self._side_und_zone.setText(f"Zone: {zone}")
            self._side_und_zone.setStyleSheet(
                f"color:{zcol};font-size:10px;border:none;")

    def _update_price_panel_opt(self, side, strike, bid, ask, delta=None):
        if not hasattr(self, '_pp_lbl_price'): return
        self._pp_mode = "opt"; self._pp_opt_side = side
        self._pp_opt_strike = strike; self._pp_opt_bid = bid; self._pp_opt_ask = ask
        label = "CALL" if side == "C" else "PUT"
        # ✅ CALL=빨강, PUT=파랑 — 한국형 HTS 표준
        col   = "#ff6666" if side == "C" else "#33aaff"
        sym   = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""
        self._pp_lbl_sym.setText(f"{sym}  {label}")
        self._pp_lbl_sym.setStyleSheet(f"color:{col};font-size:14px;font-weight:bold;border:none;")
        mid_price = (bid+ask)/2 if bid and ask else (ask if ask else None)
        self._pp_lbl_price.setText(f"{mid_price:.2f}" if mid_price else "―")
        # ✅ 기초자산 급등락 ≥5% 시 Bold 강조
        und_price = getattr(self, 'und_price', None)
        und_prev  = getattr(self, 'und_prev',  None)
        if und_price and und_prev and und_prev > 0:
            pct = abs((und_price - und_prev) / und_prev * 100)
            bold = "font-weight:bold;" if pct >= 5.0 else ""
        else:
            bold = ""
        self._pp_lbl_price.setStyleSheet(
            f"color:#ffd700;font-size:20px;{bold}border:1px solid #2a2a5a;"
            "border-radius:3px;background:#08080f;padding:2px 4px;")
        self._pp_lbl_chg.setText(f"행사가  {self._safe_strike_int(strike)}")
        self._pp_lbl_chg.setStyleSheet(f"color:{col};font-size:11px;border:none;font-weight:bold;")
        self._pp_set_quote(ask, bid)
        self._pp_lbl_opt_info.setText(f"Δ {delta:+.4f}" if delta is not None else "")
        self._pp_lbl_time.setText(datetime.now().strftime("%H:%M:%S"))

        # [S9] 전략 패널 연동 — 세트 완성(seq>=2) 시에는 덮어쓰지 않음
        if hasattr(self, '_strat_on_chain_click'):
            seq = getattr(self, '_strat_click_seq', 0)
            if seq < 2:
                self._strat_on_chain_click(
                    side, float(strike) if strike else 0.0, bid or 0.0, ask or 0.0)
            # [S11-2] 만기 자동 동기화
            if hasattr(self, '_sync_strat_expiry'):
                self._sync_strat_expiry()

    def _pp_switch_to_und(self):
        self._pp_mode = "und"
        self._pp_lbl_sym.setStyleSheet(_S_SYM)
        self._pp_lbl_chg.setStyleSheet(_S_CHG)
        self._pp_lbl_opt_info.setText("")
        self._update_price_panel()

    # ── Click handlers ─────────────────────────────────────────
    def _safe_strike_int(self, strike) -> str:
        """빈 문자열/None strike 안전 변환."""
        try:
            if strike is None or str(strike).strip() == "": return ""
            return str(int(float(strike)))
        except Exception:
            return str(strike)

    def _on_pp_quote_click(self, row: int, col: int):
        """Ask(row=0) or Bid(row=1) → fill quick-order price."""
        if not hasattr(self, 'qord_price'): return
        mode = getattr(self, '_pp_mode', 'und')
        if mode == 'opt':
            # ✅ getattr 방어코드 — AttributeError 완전 차단
            raw = getattr(self, '_pp_opt_ask', None) if row == 0 else getattr(self, '_pp_opt_bid', None)
            # ✅ NANOS 호가 ×10 보정
            val = raw * 10 if raw and getattr(self, '_pp_is_nanos', False) else raw
        else:
            val = getattr(self, '_pp_ask', None) if row == 0 else getattr(self, '_pp_bid', None)
        if val:
            self.qord_price.setText(f"{val:.2f}")
            src = "Ask" if row == 0 else "Bid"
            if hasattr(self, 'lbl_qord_src'):
                self.lbl_qord_src.setText(f"← {src} 클릭")
            if hasattr(self, '_log'):
                self._log(f"주문가격 자동입력: {src} {val:.2f}")