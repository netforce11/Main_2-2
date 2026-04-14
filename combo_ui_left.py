"""
combo_ui_left.py — 복합 전략 탭: 좌측 패널
════════════════════════════════════════════════════════════════
포함:
  - LeftPanelMixin : 옵션 체인 (콜·풋) 패널 빌드
  - 체인 동기화 (_sync_chain, _auto_sync_chain, _sync_chain_from_cp)
  - 현재가 조회 (_req_sym_price)
  - 체인 클릭 → 레그 자동 입력 (_on_chain_click)

v2.3 변경:
  - 관심종목 패널 제거 (공간 확보 → 추세점수판으로 대체)
  - edit_sym_combo / lbl_sym_price / ▶현재가조회 버튼을
    _build_chain_panel() 헤더 행으로 이동
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QMessageBox,
    QTableWidget, QHeaderView, QAbstractItemView,
    QSplitter,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from combo_constants import SPLITTER_STYLE, mk_item
from core import REQ_CALL, REQ_PUT


class LeftPanelMixin:
    """좌측 패널(옵션 체인) 빌드·로직 Mixin."""

    # ──────────────────────────────────────────────────────────
    # 빌드
    # ──────────────────────────────────────────────────────────
    def _build_left_panel(self) -> QGroupBox:
        """좌측: 옵션 체인 패널만 반환 (관심종목 제거)."""
        return self._build_chain_panel()

    # ── 옵션 체인 패널 ─────────────────────────────────────────
    def _build_chain_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 옵션 체인  (콜-풋 탭 3초 동기화)")
        v  = QVBoxLayout(gb)
        v.setSpacing(3); v.setContentsMargins(4, 6, 4, 4)

        # ── 헤더 행 1: 종목 입력 + 현재가 조회 (관심종목에서 이동) ──
        sym_row = QHBoxLayout()
        sym_row.setSpacing(6)

        sym_row.addWidget(QLabel("종목:"))

        self.edit_sym_combo = QLineEdit("SPX")
        self.edit_sym_combo.setFixedHeight(24)
        self.edit_sym_combo.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-weight:bold;")
        sym_row.addWidget(self.edit_sym_combo)

        btn_req = QPushButton("▶ 현재가 조회")
        btn_req.setFixedHeight(24)
        btn_req.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-weight:bold;padding:3px 8px;")
        btn_req.clicked.connect(self._req_sym_price)
        sym_row.addWidget(btn_req)

        self.lbl_sym_price = QLabel("현재가: ―")
        self.lbl_sym_price.setFont(QFont("Arial", 12, QFont.Bold))
        self.lbl_sym_price.setStyleSheet("color:#ffd700;border:none;")
        sym_row.addWidget(self.lbl_sym_price)

        # 만기 날짜 자동 입력 필드
        sym_row.addWidget(QLabel("만기:"))
        self.edit_expiry_combo = QLineEdit()
        self.edit_expiry_combo.setFixedWidth(72)
        self.edit_expiry_combo.setFixedHeight(24)
        self.edit_expiry_combo.setPlaceholderText("YYYYMMDD")
        self.edit_expiry_combo.setReadOnly(True)
        self.edit_expiry_combo.setStyleSheet(
            "background:#0a0a1e;color:#aaffaa;border:1px solid #3a6a3a;"
            "border-radius:3px;font-size:11px;font-weight:bold;")
        self.edit_expiry_combo.setToolTip("콜-풋 탭 만기 자동 수신")
        sym_row.addWidget(self.edit_expiry_combo)
        sym_row.addStretch()

        v.addLayout(sym_row)

        # ── 헤더 행 2: 체인 심볼 표시 + 즉시 동기화 버튼 ──
        hdr = QHBoxLayout()
        self.lbl_chain_sym = QLabel("종목: ―  |  현재가: ―")
        self.lbl_chain_sym.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        btn_sync = QPushButton("↺ 즉시 동기화")
        btn_sync.setFixedHeight(22)
        btn_sync.clicked.connect(self._sync_chain)
        hdr.addWidget(self.lbl_chain_sym)
        hdr.addStretch()
        hdr.addWidget(btn_sync)
        v.addLayout(hdr)

        # ── 콜/풋 체인 테이블 ──
        inner = QSplitter(Qt.Horizontal)
        inner.setHandleWidth(4)
        inner.setStyleSheet(SPLITTER_STYLE)
        inner.setChildrenCollapsible(False)
        inner.addWidget(self._build_call_chain())
        inner.addWidget(self._build_put_chain())
        inner.setSizes([300, 300])

        v.addWidget(inner, 1)
        gb.setMinimumWidth(300)
        return gb

    def _build_call_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)

        lbl = QLabel("▲ CALL")
        lbl.setStyleSheet("color:#33aaff;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)

        self.tbl_chain_call = QTableWidget(0, 3)
        self.tbl_chain_call.setHorizontalHeaderLabels(["행사가", "현재가", "IV"])
        self._apply_chain_style(self.tbl_chain_call, "#90caf9")
        self.tbl_chain_call.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "C"))

        lv.addWidget(lbl)
        lv.addWidget(self.tbl_chain_call)
        return w

    def _build_put_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)

        lbl = QLabel("▼ PUT")
        lbl.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)

        self.tbl_chain_put = QTableWidget(0, 3)
        self.tbl_chain_put.setHorizontalHeaderLabels(["행사가", "현재가", "IV"])
        self._apply_chain_style(self.tbl_chain_put, "#ff9999")
        self.tbl_chain_put.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "P"))

        lv.addWidget(lbl)
        lv.addWidget(self.tbl_chain_put)
        return w

    @staticmethod
    def _apply_chain_style(tbl: QTableWidget, hdr_color: str):
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            f"QHeaderView::section{{background:#0a0a1e;color:{hdr_color};"
            "border:1px solid #1a1a3a;font-weight:bold;}")

    # ──────────────────────────────────────────────────────────
    # 현재가 조회
    # ──────────────────────────────────────────────────────────
    def _req_sym_price(self):
        """종목 입력 → 현재가 조회."""
        sym = self.edit_sym_combo.text().strip().upper()
        if not sym:
            return
        cp = self.mw.tab_callput
        if cp and cp.und_price and cp.edit_sym.text().strip().upper() == sym:
            price = cp.und_price
            self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
            self.edit_stock_price.setText(f"{price:.2f}")
            self._und_price = price
            self._log(f"현재가 수신 (콜-풋탭): {sym} = {price:,.2f}")
        else:
            self.lbl_sym_price.setText("현재가: 조회 중…")
            self._log(f"콜-풋 탭에서 {sym} 먼저 조회하세요.")

    # ──────────────────────────────────────────────────────────
    # 체인 동기화
    # ──────────────────────────────────────────────────────────
    def _auto_sync_chain(self):
        """3초마다 자동 동기화."""
        cp = self.mw.tab_callput
        if not cp or (not cp.call_strikes and not cp.put_strikes):
            return
        self._sync_chain_from_cp(cp, silent=True)

    def _sync_chain(self):
        """수동 동기화 버튼."""
        cp = self.mw.tab_callput
        if not cp:
            return
        if not cp.call_strikes and not cp.put_strikes:
            QMessageBox.information(self, "안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_chain_from_cp(cp, silent=False)

    def _sync_chain_from_cp(self, cp, silent=False):
        """콜-풋 탭 → 체인 테이블 동기화."""
        sym       = cp.edit_sym.text().strip().upper()
        und_price = cp.und_price

        header = (f"종목: {sym}  |  현재가: {und_price:,.2f}"
                  if und_price else f"종목: {sym}")
        self.lbl_chain_sym.setText(header)

        if und_price:
            self._und_price = und_price
            self.lbl_sym_price.setText(f"현재가: {und_price:,.2f}")
            if not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{und_price:.2f}")

        # CALL 체인 갱신
        self._call_strikes = list(cp.call_strikes)
        self._chain_call   = {}
        self.tbl_chain_call.setRowCount(0)
        for i, st in enumerate(cp.call_strikes):
            rid = REQ_CALL + i
            lp  = cp.call_data.get(rid, {}).get("last")
            self._chain_call[st] = lp
            r = self.tbl_chain_call.rowCount()
            self.tbl_chain_call.insertRow(r)
            self.tbl_chain_call.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_call.setItem(r, 1, mk_item(
                f"{lp:.2f}" if lp else "―", "#33aaff"))
            self.tbl_chain_call.setItem(r, 2, mk_item("―"))

        # PUT 체인 갱신
        self._put_strikes = list(cp.put_strikes)
        self._chain_put   = {}
        self.tbl_chain_put.setRowCount(0)
        for i, st in enumerate(cp.put_strikes):
            rid = REQ_PUT + i
            lp  = cp.put_data.get(rid, {}).get("last")
            self._chain_put[st] = lp
            r = self.tbl_chain_put.rowCount()
            self.tbl_chain_put.insertRow(r)
            self.tbl_chain_put.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_put.setItem(r, 1, mk_item(
                f"{lp:.2f}" if lp else "―", "#ff6666"))
            self.tbl_chain_put.setItem(r, 2, mk_item("―"))

        # 만기 날짜 자동 수신 — 탭1의 현재 만기 읽기
        try:
            expiry_code = ""
            if hasattr(cp, '_expiry_list') and cp._expiry_list:
                idx = getattr(cp, 'combo_exp', None)
                if idx is not None:
                    ci = idx.currentIndex()
                    if 0 <= ci < len(cp._expiry_list):
                        _, expiry_code, _ = cp._expiry_list[ci]
                        if expiry_code and expiry_code != "CUSTOM":
                            pass
                        else:
                            expiry_code = getattr(cp, 'edit_custom', None)
                            if expiry_code:
                                expiry_code = expiry_code.text().strip()
            elif hasattr(cp, 'date_edit'):
                expiry_code = cp.date_edit.date().toString("yyyyMMdd")
            if expiry_code and len(expiry_code) == 8:
                lbl = f"{expiry_code[4:6]}/{expiry_code[6:8]}"
                lbl_full = f"{expiry_code[:4]}-{expiry_code[4:6]}-{expiry_code[6:8]}"
                ed = getattr(self, 'edit_expiry_combo', None)
                if ed:
                    ed.setText(expiry_code)
                    ed.setToolTip(f"만기: {lbl_full}")
                self._current_expiry = expiry_code
        except Exception:
            pass

        if not silent:
            self._log(
                f"체인 동기화: {sym}  C{len(cp.call_strikes)} / P{len(cp.put_strikes)}")

    # ──────────────────────────────────────────────────────────
    # 체인 클릭 → 레그 자동 입력
    # ──────────────────────────────────────────────────────────
    def _on_chain_click(self, row: int, col: int, side: str):
        strikes = self._call_strikes if side == "C" else self._put_strikes
        prices  = self._chain_call   if side == "C" else self._chain_put

        if row >= len(strikes):
            return
        strike = strikes[row]
        price  = prices.get(strike)

        leg_row = self.tbl_legs.currentRow()
        if leg_row < 0:
            leg_row = 0
        if leg_row >= self.tbl_legs.rowCount():
            return

        self.tbl_legs.item(leg_row, 2).setText(side)
        self.tbl_legs.item(leg_row, 3).setText(str(int(strike)))
        if price:
            self.tbl_legs.item(leg_row, 4).setText(f"{price:.2f}")

        # 만기 자동 입력
        expiry = getattr(self, '_current_expiry', '')
        if expiry and self.tbl_legs.item(leg_row, 6):
            fmt = f"{expiry[4:6]}/{expiry[6:8]}" if len(expiry) == 8 else expiry
            self.tbl_legs.item(leg_row, 6).setText(fmt)

        price_str = f"{price:.2f}" if price else "0.00"
        self._log(f"레그{leg_row+1} 자동 입력: {side} {int(strike)}  ${price_str}")