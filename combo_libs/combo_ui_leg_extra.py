"""
combo_ui_leg_extra.py — 수동 레그 추가/제거 + strike 변경 훅
──────────────────────────────────────────────────────────────
포함:
  _manual_add_leg   — ➕ 레그 추가 (수동 모드)
  _manual_del_leg   — ➖ 레그 제거 (수동 모드)
  _extra_add_leg    — ➕ 추가 레그 버튼 (자동/수동 공용, 최대 MAX_LEGS)
  _extra_del_leg    — ➖ 마지막 추가 레그 제거
  _on_strike_changed      — 행사가 변경 훅
  _fetch_conid_then_premium — conId → Mid-price 자동 조회
──────────────────────────────────────────────────────────────
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

from combo_constants import LEG_COLORS, MAX_LEGS


# ── 수동 모드 레그 추가/제거 ─────────────────────────────────

def _manual_add_leg(self):
    """수동 모드 전용 ➕ 레그 추가."""
    from combo_ui_leg_logic import _update_add_btn_state
    if self.tbl_legs.rowCount() >= MAX_LEGS:
        self._log(f"⚠ 최대 {MAX_LEGS}개 레그까지만 추가 가능합니다")
        return
    r   = self.tbl_legs.rowCount()
    col = LEG_COLORS[r % len(LEG_COLORS)]
    self.tbl_legs.insertRow(r)
    for c, val in enumerate([f"레그{r+1}", "BUY", "C", "", "0.00", "1", "―"]):
        it = QTableWidgetItem(val)
        it.setTextAlignment(Qt.AlignCenter)
        if c == 0:
            it.setForeground(QBrush(QColor(col)))
        elif c == 1:
            it.setForeground(QBrush(QColor("#00ff88")))
        self.tbl_legs.setItem(r, c, it)
    _update_add_btn_state(self)
    self._log(f"➕ 레그{r+1} 추가 (수동)")


def _manual_del_leg(self):
    """수동 모드 전용 ➖ 레그 제거."""
    from combo_ui_leg_logic import _update_add_btn_state
    row = self.tbl_legs.currentRow()
    if row < 0:
        row = self.tbl_legs.rowCount() - 1
    if row >= 0:
        self.tbl_legs.removeRow(row)
        _update_add_btn_state(self)
        self._log(f"➖ 레그{row+1} 제거 (수동)")


# ── 자동/수동 공용 추가 레그 버튼 ────────────────────────────

def _extra_add_leg(self):
    """
    ➕ 추가 레그 버튼 — 자동/수동 모드 모두 동작.
    기본 전략 레그에 행을 1개 추가.
    최대 MAX_LEGS(8) 제한.
    추가된 레그는 전략 손익·증거금 계산에 자동 포함됨.
    """
    from combo_ui_leg_logic import _update_add_btn_state
    if self.tbl_legs.rowCount() >= MAX_LEGS:
        self._log(f"⚠ 최대 {MAX_LEGS}개 레그까지만 추가 가능합니다")
        return
    r   = self.tbl_legs.rowCount()
    col = LEG_COLORS[r % len(LEG_COLORS)]
    self.tbl_legs.insertRow(r)

    # 기본값: BUY C, 수량 1, 프리미엄 0
    defaults = [f"레그{r+1}", "BUY", "C", "", "0.00", "1", "―"]
    for c, val in enumerate(defaults):
        it = QTableWidgetItem(val)
        it.setTextAlignment(Qt.AlignCenter)
        if c == 0:
            it.setForeground(QBrush(QColor(col)))
        elif c == 1:
            it.setForeground(QBrush(QColor("#00ff88")))
        # 자동 모드라도 추가된 레그는 모두 편집 가능
        self.tbl_legs.setItem(r, c, it)

    # 만기 기본값: 현재 전략 첫 번째 레그와 동일
    if r > 0:
        prev_exp = self.tbl_legs.item(r - 1, 6)
        if prev_exp:
            exp_it = QTableWidgetItem(prev_exp.text())
            exp_it.setTextAlignment(Qt.AlignCenter)
            exp_it.setForeground(QBrush(QColor("#aaffaa")))
            self.tbl_legs.setItem(r, 6, exp_it)

    _update_add_btn_state(self)
    self._log(f"➕ 레그{r+1} 추가 (추가 레그 버튼)")


def _extra_del_leg(self):
    """➖ 마지막 레그 제거 (추가 레그 전용)."""
    from combo_ui_leg_logic import _update_add_btn_state
    # 전략 기본 레그 수 파악: _base_leg_count 가 없으면 제거 차단
    base_count = getattr(self, '_base_leg_count', 0)
    row_count  = self.tbl_legs.rowCount()
    if row_count <= base_count:
        self._log("⚠ 기본 전략 레그는 제거할 수 없습니다 (수동 모드에서 제거하세요)")
        return
    self.tbl_legs.removeRow(row_count - 1)
    _update_add_btn_state(self)
    self._log(f"➖ 레그{row_count} 제거 (추가 레그 버튼)")


# ── 행사가 입력 시 Mid-price 자동 조회 ──────────────────────

def _on_strike_changed(self, item):
    """tbl_legs 행사가(컬럼 3) 변경 시 자동 호출."""
    if item.column() != 3:
        return
    if getattr(self, '_leg_item_changing', False):
        return

    row    = item.row()
    strike = item.text().strip()
    if not strike or strike in ("―", ""):
        return
    try:
        strike_f = float(strike)
    except ValueError:
        return

    def _cell(c):
        it = self.tbl_legs.item(row, c)
        return it.text().strip() if it else ""

    cp     = _cell(2).upper() or "C"
    expiry = _cell(6)

    from combo_order_utils import _parse_expiry_display
    raw_expiry = _parse_expiry_display(expiry)
    if not raw_expiry:
        return

    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"
    _fetch_conid_then_premium(self, row, symbol, strike_f, cp, raw_expiry)


def _fetch_conid_then_premium(self, row, symbol, strike, cp, expiry):
    """reqContractDetails → conId → fill_premium_from_market."""
    try:
        from core_contract import make_opt_contract
        from combo_ui_leg_panel import fill_premium_from_market
    except ImportError:
        return

    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ib is None:
        return

    rid = 8850 + row
    opt = make_opt_contract(symbol=symbol, strike=strike,
                            right=cp, expiry=expiry)

    _orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
    _orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)
    resolved     = {}

    def _on_cd(req_id, cd):
        if req_id == rid:
            resolved['conId'] = cd.contract.conId

    def _on_cd_end(req_id):
        if req_id != rid:
            return
        ib.contractDetails    = _orig_cd
        ib.contractDetailsEnd = _orig_cd_end
        con_id = resolved.get('conId', 0)
        if con_id > 0:
            fill_premium_from_market(self, row, con_id)
        else:
            self._log(f"⚠ 레그{row+1} conId 조회 실패 — 프리미엄 수동 입력 필요")

    ib.contractDetails    = _on_cd
    ib.contractDetailsEnd = _on_cd_end

    def _timeout():
        if ib.contractDetails is _on_cd:
            ib.contractDetails    = _orig_cd
            ib.contractDetailsEnd = _orig_cd_end
            self._log(f"⚠ 레그{row+1} conId 조회 타임아웃")
    QTimer.singleShot(3_000, _timeout)

    try:
        ib.reqContractDetails(rid, opt)
    except Exception as e:
        ib.contractDetails    = _orig_cd
        ib.contractDetailsEnd = _orig_cd_end
        self._log(f"❌ reqContractDetails 레그{row+1}: {e}")
