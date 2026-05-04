"""
combo_ui_left.py — 복합 전략 탭: 좌측 패널 (LeftPanelMixin)
────────────────────────────────────────────────────────────
빌드·동기화만 담당. 세부 로직은 분리된 파일에 위임:
  combo_ui_left_price.py  — 현재가 조회·tick 수신·거리% 갱신
  combo_ui_left_chain.py  — 체인 클릭·conId 일괄 조회·거리% 셀
  tab_combo_shortcut.py   — Alt+↑↓ 단축키 (eventFilter)

v2.9  — BUG-1/3/7 수정
v3.1  — 파일 분리 (200줄 이내)
────────────────────────────────────────────────────────────
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
    """좌측 패널(옵션 체인) 빌드·동기화 Mixin."""

    # ── 빌드 ──────────────────────────────────────────────────
    def _build_left_panel(self) -> QGroupBox:
        return self._build_chain_panel()

    def _build_chain_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 옵션 체인  (콜-풋 탭 3초 동기화)")
        v  = QVBoxLayout(gb)
        v.setSpacing(3); v.setContentsMargins(4, 6, 4, 4)

        # 헤더 행 1: 종목 + 현재가 조회
        sym_row = QHBoxLayout(); sym_row.setSpacing(6)
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

        # 헤더 행 2: 심볼 표시 + 즉시 동기화
        hdr = QHBoxLayout()
        self.lbl_chain_sym = QLabel("종목: ―  |  현재가: ―")
        self.lbl_chain_sym.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        btn_sync = QPushButton("↺ 즉시 동기화")
        btn_sync.setFixedHeight(22)
        btn_sync.clicked.connect(self._sync_chain)
        hdr.addWidget(self.lbl_chain_sym); hdr.addStretch(); hdr.addWidget(btn_sync)
        v.addLayout(hdr)

        # 콜/풋 체인 테이블
        inner = QSplitter(Qt.Horizontal)
        inner.setHandleWidth(4); inner.setStyleSheet(SPLITTER_STYLE)
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
        self.tbl_chain_call = QTableWidget(0, 4)
        self.tbl_chain_call.setHorizontalHeaderLabels(["행사가", "현재가", "IV", "거리%"])
        self._apply_chain_style(self.tbl_chain_call, "#90caf9")
        self.tbl_chain_call.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "C"))
        lv.addWidget(lbl); lv.addWidget(self.tbl_chain_call)
        return w

    def _build_put_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)
        lbl = QLabel("▼ PUT")
        lbl.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)
        self.tbl_chain_put = QTableWidget(0, 4)
        self.tbl_chain_put.setHorizontalHeaderLabels(["행사가", "현재가", "IV", "거리%"])
        self._apply_chain_style(self.tbl_chain_put, "#ff9999")
        self.tbl_chain_put.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "P"))
        lv.addWidget(lbl); lv.addWidget(self.tbl_chain_put)
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

    # ── 위임 메서드: combo_ui_left_price.py ───────────────────
    def _req_sym_price(self):
        from combo_ui_left_price import _req_sym_price as _f; _f(self)

    def _on_combo_und_tick(self, rid, tt, price):
        from combo_ui_left_price import _on_combo_und_tick as _f; _f(self, rid, tt, price)

    def _apply_und_price_ui(self, price: float):
        from combo_ui_left_price import _apply_und_price_ui as _f; _f(self, price)

    def _refresh_dist_col(self, und_price: float):
        from combo_ui_left_price import _refresh_dist_col as _f; _f(self, und_price)

    # ── 체인 동기화 ───────────────────────────────────────────
    def _auto_sync_chain(self):
        cp = self.mw.tab_callput
        if not cp or (not cp.call_strikes and not cp.put_strikes):
            return
        self._sync_chain_from_cp(cp, silent=True)

    def _sync_chain(self):
        cp = self.mw.tab_callput
        if not cp:
            return
        if not cp.call_strikes and not cp.put_strikes:
            QMessageBox.information(self, "안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_chain_from_cp(cp, silent=False)

    def _sync_chain_from_cp(self, cp, silent=False):
        from combo_ui_left_chain import _make_dist_item, _bulk_fetch_conids
        sym       = cp.edit_sym.text().strip().upper()
        und_price = cp.und_price

        # ★ FIX: 왼쪽 패널 종목 입력 필드를 콜-풋 탭 종목과 동기화
        #        (XSP 등 종목 변경 시 edit_sym_combo가 갱신되지 않던 버그 수정)
        if hasattr(self, 'edit_sym_combo'):
            current_sym = self.edit_sym_combo.text().strip().upper()
            if current_sym != sym:
                self.edit_sym_combo.setText(sym)
                if not silent:
                    self._log(f"🔄 왼쪽 패널 종목 동기화: {current_sym} → {sym}")

        self.lbl_chain_sym.setText(
            f"종목: {sym}  |  현재가: {und_price:,.2f}" if und_price else f"종목: {sym}")
        if und_price:
            self._und_price = und_price
            self.lbl_sym_price.setText(f"현재가: {und_price:,.2f}")
            if hasattr(self, 'edit_stock_price') and not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{und_price:.2f}")

        # CALL 갱신
        self._call_strikes = list(cp.call_strikes)
        self._chain_call   = {}
        self.tbl_chain_call.setRowCount(0)
        for i, st in enumerate(cp.call_strikes):
            lp = cp.call_data.get(REQ_CALL + i, {}).get("last")
            self._chain_call[st] = lp
            r = self.tbl_chain_call.rowCount()
            self.tbl_chain_call.insertRow(r)
            self.tbl_chain_call.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_call.setItem(r, 1, mk_item(f"{lp:.2f}" if lp else "―", "#33aaff"))
            self.tbl_chain_call.setItem(r, 2, mk_item("―"))
            self.tbl_chain_call.setItem(r, 3, _make_dist_item(st, und_price, "C"))

        # PUT 갱신
        self._put_strikes = list(cp.put_strikes)
        self._chain_put   = {}
        self.tbl_chain_put.setRowCount(0)
        for i, st in enumerate(cp.put_strikes):
            lp = cp.put_data.get(REQ_PUT + i, {}).get("last")
            self._chain_put[st] = lp
            r = self.tbl_chain_put.rowCount()
            self.tbl_chain_put.insertRow(r)
            self.tbl_chain_put.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_put.setItem(r, 1, mk_item(f"{lp:.2f}" if lp else "―", "#ff6666"))
            self.tbl_chain_put.setItem(r, 2, mk_item("―"))
            self.tbl_chain_put.setItem(r, 3, _make_dist_item(st, und_price, "P"))

        # 만기 파싱
        try:
            expiry_code = ""
            if hasattr(cp, '_expiry_list') and cp._expiry_list:
                idx = getattr(cp, 'combo_exp', None)
                if idx is not None:
                    ci = idx.currentIndex()
                    if 0 <= ci < len(cp._expiry_list):
                        _, expiry_code, _ = cp._expiry_list[ci]
                        if expiry_code == "CUSTOM":
                            ew = getattr(cp, 'edit_custom', None)
                            expiry_code = ew.text().strip() if ew else ""
            elif hasattr(cp, 'date_edit'):
                expiry_code = cp.date_edit.date().toString("yyyyMMdd")
            if expiry_code and len(expiry_code) == 8:
                ed = getattr(self, 'edit_expiry_combo', None)
                if ed:
                    ed.setText(expiry_code)
                    ed.setToolTip(
                        f"만기: {expiry_code[:4]}-{expiry_code[4:6]}-{expiry_code[6:8]}")
                self._current_expiry = expiry_code
        except Exception:
            pass

        if not silent:
            self._log(f"체인 동기화: {sym}  C{len(cp.call_strikes)} / P{len(cp.put_strikes)}")

        raw_expiry = getattr(self, '_current_expiry', '')
        first_run  = not getattr(self, '_conid_bulk_done', False)
        if (not silent or first_run) and raw_expiry and (self._call_strikes or self._put_strikes):
            self._conid_bulk_done = True
            _bulk_fetch_conids(self, sym, raw_expiry, self._call_strikes, self._put_strikes)

    # ── 위임 메서드: combo_ui_left_chain.py ───────────────────
    def _on_chain_click(self, row: int, col: int, side: str):
        from combo_ui_left_chain import _on_chain_click as _f; _f(self, row, col, side)