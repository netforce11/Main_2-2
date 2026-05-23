"""
combo_ui_synthetic_panel_patch.py
──────────────────────────────────────────────────────────────
버그 수정 패치 (combo_ui_synthetic_panel.py 에 적용)

[BUG-2] '청산중' 상태에서 수익률이 "―"로 잠기는 문제
  _refresh_pos_table: is_closing일 때도 pnl/pnl_rate 계산 유지

[BUG-3] 잔고 현재가 갱신 속도 불일치
  update_position_prices: 전체 테이블 rebuild → 해당 행만 갱신

[BUG-4] 테마 미적용 — 잔고 테이블 글씨색 하드코딩
  _it() 헬퍼의 기본 색상을 _pal()['widget_fg'] 참조로 변경
──────────────────────────────────────────────────────────────
"""

# ── 이 파일은 단독 실행용이 아닙니다.
# combo_ui_synthetic_panel.py 에서 아래 두 메서드를 교체하세요.
# (str_replace 또는 직접 붙여넣기)


# ─────────────────────────────────────────────────────────────
# [BUG-2 + BUG-4] _refresh_pos_table  (전체 교체)
# ─────────────────────────────────────────────────────────────
def _refresh_pos_table(self):
    from combo_ui_panel_constants import _pal
    from combo_ui_panel_utils import _calc_delta_pnl_pct, _format_expiry
    from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QWidget
    from PyQt5.QtGui import QColor, QFont
    from PyQt5.QtCore import Qt

    tbl = self._tbl_pos
    tbl.setRowCount(0)
    if not self._positions:
        self._lbl_no_pos.setVisible(True)
        tbl.setVisible(False)
        self._lbl_total_pnl.setText("$0.00")
        self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
        return

    self._lbl_no_pos.setVisible(False)
    tbl.setVisible(True)
    tbl.setRowCount(len(self._positions))

    # [BUG-4] 테마 팔레트에서 기본 전경색 가져오기
    t         = _pal()
    fg_normal = t.get("widget_fg", "#cccccc")   # 테마 적용 기본색
    fg_dim    = t.get("tbl_grid",  "#888899")    # 비활성/보조 색

    total_pnl = 0.0

    for r, pos in enumerate(self._positions):
        qty       = pos.get("qty", 1)
        entry     = pos.get("entry", 0.0)
        current   = pos.get("current", entry)
        status    = pos.get("status", "미체결")
        is_filled = status in ("체결완료", "보유")
        is_closing = status == "청산중"

        # [BUG-2] 청산중에도 수익률 계산 — pnl은 0이 아닌 실제 값 사용
        if is_filled or is_closing:
            pnl = (current - entry) * qty * 100
        else:
            pnl = 0.0
        total_pnl += pnl
        pnl_col = ("#00ff88" if pnl > 0
                   else "#ff4444" if pnl < 0 else "#888899")

        # [BUG-2] 청산중에도 수익률 표시 (is_closing 제외 조건 제거)
        show_rate = (is_filled or is_closing) and entry > 0
        if show_rate:
            pnl_rate     = (current - entry) / entry * 100
            pnl_rate_txt = f"{pnl_rate:+.1f}%"
            pnl_rate_col = ("#00ff88" if pnl_rate > 0
                            else "#ff4444" if pnl_rate < 0 else "#888899")
        else:
            pnl_rate_txt = "―"
            pnl_rate_col = fg_dim

        if is_closing:
            st_col, st_text = "#888888", "🔄 청산중"
        elif is_filled:
            st_col, st_text = "#00ff88", "📌 보유"
        else:
            st_col, st_text = "#ffaa44", "⏳ 미체결"

        # [BUG-4] 기본 색상을 테마 팔레트에서 가져오는 _it 헬퍼
        def _it(text, color=None, align=Qt.AlignCenter,
                _fg=fg_normal):
            from PyQt5.QtWidgets import QTableWidgetItem
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(align)
            it.setForeground(QColor(color if color else _fg))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            return it

        expiry_txt, expiry_col = _format_expiry(pos.get("legs", []))
        tbl.setItem(r, 0, _it(expiry_txt, expiry_col))
        tbl.setItem(r, 1, _it(
            pos.get("strategy", "―"), fg_normal,
            Qt.AlignLeft | Qt.AlignVCenter))
        tbl.setItem(r, 2, _it(str(qty),          fg_dim))
        tbl.setItem(r, 3, _it(f"${entry:.2f}",   fg_dim))
        tbl.setItem(r, 4, _it(f"${current:.2f}", fg_normal))
        tbl.setItem(r, 5, _it(
            f"${pnl:+,.2f}" if (is_filled or is_closing) else "―",
            pnl_col))
        tbl.setItem(r, 6, _it(pnl_rate_txt, pnl_rate_col))

        # [FIX-DELTA] 칼럼 7: 지수 5P당 예상 손익률
        delta_pct_txt, delta_pct_col = _calc_delta_pnl_pct(pos)
        from PyQt5.QtWidgets import QTableWidgetItem
        delta_it = QTableWidgetItem(delta_pct_txt)
        delta_it.setTextAlignment(Qt.AlignCenter)
        delta_it.setForeground(QColor(delta_pct_col))
        delta_it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        delta_font = QFont()
        delta_font.setPointSize(14)
        delta_it.setFont(delta_font)
        tbl.setItem(r, 7, delta_it)

        tbl.setItem(r, 8, _it(st_text, st_col))

        # 칼럼 9: 청산 예약 + 수동 삭제 버튼
        _cell_w   = QWidget(tbl)  # [FIX] parent 지정 — 재연결 시 floating 방지
        _cell_lay = QHBoxLayout(_cell_w)
        _cell_lay.setContentsMargins(1, 0, 1, 0)
        _cell_lay.setSpacing(2)
        _cell_w.setStyleSheet("background:transparent;")

        if is_filled and not is_closing:
            _btn_close_rsv = QPushButton("📌 예약")
            _btn_close_rsv.setFixedHeight(22)
            _btn_close_rsv.setStyleSheet(
                "QPushButton{background:#1a0a1a;color:#ff6b6b;"
                "font-size:11px;font-weight:bold;"
                "border:1px solid #5a1a3a;border-radius:3px;padding:1px 4px;}"
                "QPushButton:hover{background:#2a0a2a;color:#ff8888;}")
            _p = dict(pos)
            _btn_close_rsv.clicked.connect(
                lambda _, p=_p: self._open_close_reserve_dialog(p))
            _cell_lay.addWidget(_btn_close_rsv)

        _btn_del = QPushButton("🗑")
        _btn_del.setFixedSize(24, 22)
        _btn_del.setToolTip("잔고에서 수동 삭제 (주문 없이 즉시 제거)")
        _btn_del.setStyleSheet(
            "QPushButton{background:#1a0808;color:#ff4444;"
            "font-size:12px;border:1px solid #3a1010;"
            "border-radius:3px;padding:0px;}"
            "QPushButton:hover{background:#2a0808;color:#ff6666;}")
        _pos_oid = pos.get("oid")
        _btn_del.clicked.connect(
            lambda _, o=_pos_oid: self._manual_delete_position(o))
        _cell_lay.addWidget(_btn_del)

        tbl.setCellWidget(r, 9, _cell_w)

    tc = ("#00ff88" if total_pnl > 0
          else "#ff4444" if total_pnl < 0 else "#888899")
    self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
    self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")

    # [FIX-BANNER] 수익률 배너 갱신
    if self.profit_alert_banner and self._positions:
        try:
            best_pct = 0.0
            for pos in self._positions:
                if pos.get("status") not in ("체결완료", "보유"):
                    continue
                entry   = float(pos.get("entry", 0) or 0)
                current = float(pos.get("current", entry) or entry)
                side    = pos.get("side", "SELL")
                if entry <= 0:
                    continue
                pct = ((entry - current) / entry * 100
                       if side == "SELL"
                       else (current - entry) / entry * 100)
                if pct > best_pct:
                    best_pct = pct
            self.profit_alert_banner.update_pct(best_pct)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# [BUG-3] update_position_prices  (전체 교체)
# 기존: 전체 테이블 rebuild → 느림
# 수정: 해당 oid 행만 현재가/pnl/수익률 셀 직접 갱신
# ─────────────────────────────────────────────────────────────
def update_position_prices(self, oid: int, current_price: float):
    """[BUG-3] oid 행만 직접 갱신 — 테이블 전체 rebuild 제거."""
    from combo_ui_panel_constants import _pal
    from PyQt5.QtGui import QColor
    from PyQt5.QtCore import Qt

    row_idx = None
    for i, pos in enumerate(self._positions):
        if pos.get("oid") == oid:
            pos["current"] = current_price
            row_idx = i
            break

    if row_idx is None:
        return  # oid 없으면 무시

    pos       = self._positions[row_idx]
    entry     = pos.get("entry", 0.0)
    qty       = pos.get("qty", 1)
    status    = pos.get("status", "미체결")
    is_filled = status in ("체결완료", "보유")
    is_closing = status == "청산중"

    t       = _pal()
    fg_dim  = t.get("tbl_grid", "#888899")

    tbl = self._tbl_pos
    if row_idx >= tbl.rowCount():
        # 행이 아직 생성 안 됐으면 전체 refresh
        self._refresh_pos_table()
        return

    def _set(col, text, color):
        item = tbl.item(row_idx, col)
        if item is None:
            from PyQt5.QtWidgets import QTableWidgetItem
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tbl.setItem(row_idx, col, item)
        item.setText(str(text))
        item.setForeground(QColor(color))

    # 현재가 (col 4)
    _set(4, f"${current_price:.2f}", t.get("widget_fg", "#cccccc"))

    # pnl (col 5)
    if is_filled or is_closing:
        pnl     = (current_price - entry) * qty * 100
        pnl_col = ("#00ff88" if pnl > 0
                   else "#ff4444" if pnl < 0 else "#888899")
        _set(5, f"${pnl:+,.2f}", pnl_col)
    else:
        _set(5, "―", fg_dim)

    # 수익률 (col 6) — [BUG-2] 청산중에도 표시
    show_rate = (is_filled or is_closing) and entry > 0
    if show_rate:
        pnl_rate = (current_price - entry) / entry * 100
        rate_col = ("#00ff88" if pnl_rate > 0
                    else "#ff4444" if pnl_rate < 0 else "#888899")
        _set(6, f"{pnl_rate:+.1f}%", rate_col)
    else:
        _set(6, "―", fg_dim)

    # total_pnl 라벨 갱신
    total_pnl = 0.0
    for p in self._positions:
        s = p.get("status", "")
        if s in ("체결완료", "보유", "청산중"):
            e = p.get("entry", 0.0)
            c = p.get("current", e)
            q = p.get("qty", 1)
            total_pnl += (c - e) * q * 100
    tc = ("#00ff88" if total_pnl > 0
          else "#ff4444" if total_pnl < 0 else "#888899")
    self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
    self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")
