"""order_panel_util.py — OrderUtilMixin: position panel, pos_sell, util methods [NEW S6]"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView, QMessageBox,
)
from PyQt5.QtCore import Qt

from order_panel_common import _LS, _TBL_S


class OrderUtilMixin:
    """Position panel, pos-sell panel, and utility methods."""
    # ── [S6] 잔고 인라인 패널 (신규 탭 하단) ─────────────────
    def _build_inline_position_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 잔고")
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#ffa500;font-weight:bold;"
            "border:1px solid #3a2a1a;border-radius:4px;"
            "margin-top:6px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        v = QVBoxLayout(gb); v.setContentsMargins(4,6,4,4); v.setSpacing(2)

        btn_row = QHBoxLayout()
        btn_ref = QPushButton("🔄 조회"); btn_ref.setFixedHeight(20)
        btn_ref.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffa500;font-size:10px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_ref.clicked.connect(self._refresh_positions)
        btn_row.addWidget(btn_ref); btn_row.addStretch()
        v.addLayout(btn_row)

        # ── tbl_positions: 이미 PricePanelMixin에서 생성된 경우 재사용 ──
        # tab_options_price.py _build_position_panel()이 먼저 실행되면
        # self.tbl_positions가 이미 존재함 → 새로 생성하면 참조 불일치 발생
        if not hasattr(self, 'tbl_positions'):
            _ts = (
                "QTableWidget{background:#05050f;color:#ccc;gridline-color:#2a1a0a;"
                "font-size:11px;border:1px solid #3a2a1a;}"
                "QHeaderView::section{background:#0a0805;color:#ffa500;"
                "border:1px solid #2a1a0a;font-size:10px;padding:1px;}"
                "QTableWidget::item{padding:1px;}"
                "QTableWidget::item:selected{background:#3a2a0a;color:#ffd700;}"
                "QTableWidget::item:hover{background:#1a1005;}")
            self.tbl_positions = QTableWidget(0, 5)
            self.tbl_positions.setHorizontalHeaderLabels(["C/P","행사가","수량","평균가","손익"])
            self.tbl_positions.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.tbl_positions.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
            self.tbl_positions.verticalHeader().setVisible(False)
            self.tbl_positions.verticalHeader().setDefaultSectionSize(22)
            self.tbl_positions.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.tbl_positions.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.tbl_positions.setMinimumHeight(0)
            self.tbl_positions.setMaximumHeight(120)
            self.tbl_positions.setStyleSheet(_ts)
            self.tbl_positions.cellClicked.connect(self._on_position_row_click)
        else:
            # 기존 테이블 높이 제한만 인라인 패널용으로 재적용
            self.tbl_positions.setMaximumHeight(120)
        v.addWidget(self.tbl_positions)

        hint = QLabel("↑ 클릭 → 매도 주문창")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#444;font-size:9px;border:none;")
        v.addWidget(hint)
        return gb

    # ── 잔고 청산 슬라이드업 패널 ─────────────────────────────
    def _build_pos_sell_panel(self) -> QWidget:
        self._pos_sell_panel = QWidget()
        self._pos_sell_panel.setVisible(False)
        self._pos_sell_panel.setStyleSheet(
            "background:#1a0a0a;border:1px solid #6b1a1a;border-radius:4px;")
        ps_v = QVBoxLayout(self._pos_sell_panel)
        ps_v.setContentsMargins(6,5,6,5); ps_v.setSpacing(4)

        ps_hdr = QHBoxLayout()
        self._ps_lbl_title = QLabel("▼ 잔고 청산 매도")
        self._ps_lbl_title.setStyleSheet(
            "color:#ff6666;font-weight:bold;font-size:13px;border:none;")
        ps_btn_close = QPushButton("✕"); ps_btn_close.setFixedSize(18, 18)
        ps_btn_close.setStyleSheet(
            "background:#3a1a1a;color:#ff6666;border:none;font-size:11px;border-radius:2px;")
        ps_btn_close.clicked.connect(lambda: self._pos_sell_panel.setVisible(False))
        ps_hdr.addWidget(self._ps_lbl_title); ps_hdr.addStretch()
        ps_hdr.addWidget(ps_btn_close)
        ps_v.addLayout(ps_hdr)

        ps_info = QHBoxLayout()
        self._ps_lbl_sym = QLabel("―")
        self._ps_lbl_sym.setStyleSheet(
            "color:#ffd700;font-size:13px;font-weight:bold;border:none;")
        ps_info.addWidget(QLabel("종목:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_info.addWidget(self._ps_lbl_sym); ps_info.addStretch()
        ps_v.addLayout(ps_info)

        ps_qty_row = QHBoxLayout()
        self._ps_qty = QSpinBox()
        self._ps_qty.setRange(1, 9999); self._ps_qty.setValue(1)
        self._ps_qty.setFixedHeight(24)
        self._ps_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #6b1a1a;font-size:13px;")
        ps_qty_row.addWidget(QLabel("수량:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_qty_row.addWidget(self._ps_qty); ps_qty_row.addStretch()
        ps_v.addLayout(ps_qty_row)

        ps_price_row = QHBoxLayout()
        self._ps_price = QLineEdit()
        self._ps_price.setPlaceholderText("지정가 (비워두면 시장가)")
        self._ps_price.setFixedHeight(24)
        self._ps_price.setStyleSheet(
            "color:#ffd700;font-size:13px;background:#0a0a1e;border:1px solid #6b1a1a;")
        ps_price_row.addWidget(QLabel("가격:", styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_price_row.addWidget(self._ps_price)
        ps_v.addLayout(ps_price_row)

        ps_btn_sell = QPushButton("▼ 매도 주문 전송")
        ps_btn_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:14px;"
            "font-weight:bold;padding:8px;border-radius:4px;")
        ps_btn_sell.clicked.connect(self._pos_sell_execute)
        ps_v.addWidget(ps_btn_sell)
        return self._pos_sell_panel

    # ── 유틸 ──────────────────────────────────────────────────
    def _on_qord_type_toggle(self):
        is_lmt = self.qord_lmt.isChecked()
        self.qord_price.setEnabled(is_lmt)
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;"
            if is_lmt else
            "color:#555;font-weight:bold;font-size:15px;"
            "background:#070710;border:1px solid #222;")

    def _update_commission_label(self, qty: int = 1):
        fee = max(qty * 0.65, 1.00)
        self.lbl_commission.setText(
            f"예상 수수료: ${fee:.2f}  ({qty}계약 × $0.65)")

    def _validate_quick_order(self, action: str) -> tuple:
        errors = []
        side_val   = getattr(self, 'qord_side',   None)
        strike_val = getattr(self, 'qord_strike', None)
        side_txt   = side_val.text().strip()   if side_val   else ""
        strike_txt = strike_val.text().strip() if strike_val else ""
        if side_txt or strike_txt:
            if not side_txt:   errors.append("• C/P 대상 없음 (체인 행 클릭)")
            if not strike_txt: errors.append("• 행사가 없음 (체인 행 클릭)")
        qty_spin = getattr(self, 'qord_qty', None)
        if not qty_spin or qty_spin.value() <= 0:
            errors.append("• 수량을 1 이상 입력하세요")
        if getattr(self, 'qord_lmt', None) and self.qord_lmt.isChecked():
            price_edit = getattr(self, 'qord_price', None)
            try:
                if float(price_edit.text().strip()) <= 0: raise ValueError
            except (ValueError, TypeError):
                errors.append("• 지정가를 올바르게 입력하세요")
        return (False, "\n\n".join(errors)) if errors else (True, "")

    def _qord_place_validated(self, action: str):
        valid, err_msg = self._validate_quick_order(action)
        if not valid:
            QMessageBox.warning(self, "⚠ 주문 불가", f"확인하세요:\n\n{err_msg}")
            return
        chk = getattr(self, 'chk_order_confirm', None)
        self._skip_order_confirm = (chk is not None and not chk.isChecked())
        self._qord_place(action)
        self._skip_order_confirm = False

    def _on_position_row_click(self, row: int, col: int = 0):
        """
        현재가 패널 tbl_positions 행 클릭 →
          - _ps_side / _ps_strike 저장
          - 빠른매도 탭 sell_price / sell_qty 자동입력
          - 빠른매도 탭으로 자동 전환
        """
        tbl = getattr(self, 'tbl_positions', None)
        if tbl is None:
            return

        def _cell(c):
            item = tbl.item(row, c)
            return item.text().strip() if item else ""

        side   = _cell(0)   # "C" or "P"
        strike = _cell(1)   # 행사가
        qty    = _cell(2)   # 수량
        avg    = _cell(3)   # 평균단가

        if not side or not strike:
            return

        # _pos_snapshot에서 만기(expiry) + 실제 심볼(sym_raw) 찾기
        # key = (normalized_sym, right, strike_int, expiry)
        # value = {"qty":..., "avg":..., "con_id":..., "sym_raw": "NANOS"}
        expiry = None
        ps_sym = None
        snapshot = getattr(self, '_pos_snapshot', {})
        try:
            strike_int = int(float(strike))
            right = "C" if side == "C" else "P"
            for key, info in snapshot.items():
                if isinstance(key, tuple) and len(key) == 4:
                    _, k_right, k_strike, k_expiry = key
                    if k_right == right and int(k_strike) == strike_int:
                        expiry = k_expiry
                        # sym_raw: IB 원본 심볼 ("NANOS", "SPXW" 등)
                        # _normalize_sym으로 변환된 key[0]("SPX") 대신 사용
                        ps_sym = (info.get("sym_raw") or "").strip() or None
                        break
        except Exception:
            expiry = None
            ps_sym = None

        # _ps_side / _ps_strike / _ps_expiry / _ps_sym 저장 (매도 주문에 사용)
        self._ps_side   = side
        self._ps_strike = strike
        self._ps_expiry = expiry   # ex) "20260410"
        self._ps_sym    = ps_sym   # ex) "NANOS" → make_opt_contract에 전달

        # ── 디버그 로그 (원인 확인용) ──
        self._log(f"🔎 잔고클릭 디버그: side={side} strike={strike} expiry={expiry} ps_sym={ps_sym} snapshot_size={len(snapshot)}")
        if snapshot:
            first_key = next(iter(snapshot))
            first_val = snapshot[first_key]
            self._log(f"🔎 snapshot 첫번째: key={first_key}  val={first_val}")

        # 빠른매도 탭 필드 자동입력
        sell_price_w = getattr(self, 'sell_price', None)
        sell_qty_w   = getattr(self, 'sell_qty',   None)
        if sell_price_w:
            sell_price_w.setText(avg if avg else "")
        if sell_qty_w:
            try:    sell_qty_w.setValue(abs(int(float(qty))))
            except: sell_qty_w.setValue(1)

        # 상태 레이블 업데이트
        lbl = getattr(self, 'lbl_sell_status', None)
        label = "CALL" if side == "C" else "PUT"
        if lbl:
            lbl.setStyleSheet(
                "color:#ffa500;font-size:12px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            lbl.setText(f"선택: {label} {strike}  {qty}계약  avg@{avg}")

        # 빠른매도 탭으로 자동 전환
        tab_w = getattr(self, '_qord_tab_widget', None)
        if tab_w:
            for i in range(tab_w.count()):
                if "매도" in tab_w.tabText(i):
                    tab_w.setCurrentIndex(i)
                    break

    def _show_pos_sell_panel(self, side, strike, qty=1, price=None):
        label = "CALL" if side == "C" else "PUT"
        self._ps_lbl_title.setText(f"▼ 잔고 청산 매도  [{label}]")
        self._ps_lbl_sym.setText(f"{label}  {strike}")
        self._ps_qty.setValue(max(1, qty))
        self._ps_price.setText(f"{price:.2f}" if price else "")
        self._ps_side   = side
        self._ps_strike = strike
        self._pos_sell_panel.setVisible(True)

    def _pos_sell_execute(self):
        side   = getattr(self, '_ps_side',   None)
        strike = getattr(self, '_ps_strike', None)
        if not side or not strike:
            self._log("⚠ 매도 대상 없음. 잔고 테이블을 다시 클릭하세요."); return
        price_txt = self._ps_price.text().strip()
        self._qord_fill(side, strike,
                        float(price_txt) if price_txt else None,
                        source="← 잔고 청산")
        self.qord_qty.setValue(self._ps_qty.value())
        self._pos_sell_panel.setVisible(False)
        self._qord_place("SELL")