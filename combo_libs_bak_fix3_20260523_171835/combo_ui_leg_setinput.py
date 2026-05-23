"""
combo_ui_leg_setinput.py — 세트 입력 적용 / 단축키 전략 변경
────────────────────────────────────────────────────────────
combo_ui_leg_panel.py 에서 분리.
"""

from combo_ui_leg_panel import _recalc_net_price


def _apply_set_input(self, sell_edit, buy_edit):
    """세트 입력 적용 — 현재 전략에 맞게 레그 테이블에 행사가 삽입."""
    sell_s = sell_edit.text().strip()
    buy_s  = buy_edit.text().strip()
    if not sell_s and not buy_s:
        return
    strat      = getattr(self, 'combo_strat', None)
    strat_name = strat.currentText() if strat else ""
    rows       = self.tbl_legs.rowCount()
    if rows == 0:
        return

    if "백 스프레드" in strat_name:
        sell_indices = [0]; buy_indices = [1]
    elif "스프레드" in strat_name:
        sell_indices = [1]; buy_indices = [0]
    else:
        sell_indices = [0] if rows > 0 else []
        buy_indices  = [1] if rows > 1 else []

    self._leg_item_changing = True
    try:
        for idx in sell_indices:
            if idx < rows and sell_s:
                it = self.tbl_legs.item(idx, 3)
                if it: it.setText(sell_s)
        for idx in buy_indices:
            if idx < rows and buy_s:
                it = self.tbl_legs.item(idx, 3)
                if it: it.setText(buy_s)
        expiry = getattr(self, '_current_expiry', '')
        if expiry and len(expiry) == 8:
            fmt = f"{expiry[4:6]}/{expiry[6:8]}"
            for r in range(rows):
                it = self.tbl_legs.item(r, 6)
                if it: it.setText(fmt)
    finally:
        self._leg_item_changing = False
    _recalc_net_price(self)
    self._log(f"세트 적용: 매도={sell_s}  매수={buy_s}")


def _set_strategy_by_name(self, strat_name: str):
    """단축키로 전략 변경."""
    combo = getattr(self, 'combo_strat', None)
    if combo is None:
        return
    for i in range(combo.count()):
        if strat_name in combo.itemText(i):
            combo.setCurrentIndex(i)
            self._log(f"⌨ 단축키 전략 변경: {combo.itemText(i)}")
            return


def build_set_input_panel(self):
    """세트 입력 패널 위젯 빌드 (combo_ui_leg_panel에서 위임)."""
    from PyQt5.QtWidgets import (
        QFrame, QVBoxLayout, QHBoxLayout, QWidget,
        QLabel, QLineEdit, QPushButton,
    )
    set_frame = QFrame()
    set_frame.setStyleSheet(
        "QFrame{background:#0a0a1e;border:1px solid #2a2a4a;border-radius:4px;}")
    set_v = QVBoxLayout(set_frame)
    set_v.setContentsMargins(4, 3, 4, 3); set_v.setSpacing(3)

    set_lbl = QLabel("세트 입력  (행사가 직접 입력 후 클릭 → 레그 자동 적용)")
    set_lbl.setStyleSheet("color:#90caf9;font-size:10px;font-weight:bold;border:none;")
    set_v.addWidget(set_lbl)

    self._set_inputs = []; self._set_rows = []
    for i in range(3):
        row_w = QWidget(); row_h = QHBoxLayout(row_w)
        row_h.setContentsMargins(0, 0, 0, 0); row_h.setSpacing(4)

        lbl_n = QLabel(f"{i+1}세트")
        lbl_n.setStyleSheet("color:#ffd700;font-size:10px;font-weight:bold;border:none;")
        lbl_n.setFixedWidth(32); row_h.addWidget(lbl_n)

        lbl_s = QLabel("매도:")
        lbl_s.setStyleSheet("color:#ff6666;font-size:10px;border:none;")
        lbl_s.setFixedWidth(28); row_h.addWidget(lbl_s)
        sell_e = QLineEdit(); sell_e.setFixedHeight(20); sell_e.setFixedWidth(55)
        sell_e.setPlaceholderText("행사가")
        sell_e.setStyleSheet(
            "background:#1a0a0a;color:#ff9999;border:1px solid #4a2a2a;"
            "border-radius:2px;font-size:11px;")
        row_h.addWidget(sell_e)

        lbl_b = QLabel("매수:")
        lbl_b.setStyleSheet("color:#00ff88;font-size:10px;border:none;")
        lbl_b.setFixedWidth(28); row_h.addWidget(lbl_b)
        buy_e = QLineEdit(); buy_e.setFixedHeight(20); buy_e.setFixedWidth(55)
        buy_e.setPlaceholderText("행사가")
        buy_e.setStyleSheet(
            "background:#0a1a0a;color:#aaffaa;border:1px solid #2a4a2a;"
            "border-radius:2px;font-size:11px;")
        row_h.addWidget(buy_e)

        btn_apply = QPushButton("적용"); btn_apply.setFixedHeight(20); btn_apply.setFixedWidth(36)
        btn_apply.setStyleSheet(
            "background:#1a2a4a;color:#90caf9;font-size:10px;"
            "border:1px solid #3a5a9a;border-radius:2px;")
        btn_apply.clicked.connect(
            lambda _, se=sell_e, be=buy_e: _apply_set_input(self, se, be))
        row_h.addWidget(btn_apply); row_h.addStretch()

        self._set_inputs.append((sell_e, buy_e))
        self._set_rows.append(row_w)
        set_v.addWidget(row_w)
    return set_frame
