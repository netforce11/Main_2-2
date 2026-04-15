"""
combo_ui_leg_logic.py — 레그 빌드 · 전략 변경 로직
────────────────────────────────────────────────────
포함:
  - _on_strat_change / _get_leg_template / _rebuild_legs
  - _reset_legs
  - _set_leg_mode / _manual_add_leg / _manual_del_leg
  - _fmt_expiry  (YYYYMMDD → MM/DD)
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import LEG_COLORS


# ── 만기 포맷 유틸 ────────────────────────────────────────────
def _fmt_expiry(raw: str) -> str:
    """YYYYMMDD / YYYY-MM-DD → MM/DD, 파싱 불가 시 원본 반환."""
    if not raw:
        return "―"
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) == 8:
        return f"{digits[4:6]}/{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[2:4]}/{digits[4:6]}"
    return raw


# ── RightPanelMixin 에 주입될 메서드들 ───────────────────────

def _on_strat_change(self, idx: int):
    strat = self.combo_strat.currentText()
    # 전략 변경 시 기존 실시간 스트림 모두 해제
    try:
        from combo_ui_leg_panel import cancel_all_streams
        cancel_all_streams(self)
    except Exception:
        pass
    self._rebuild_legs(self._get_leg_template(strat))
    needs_stock = "커버드" in strat or "프로텍티브" in strat
    self.edit_stock_price.setEnabled(needs_stock)
    self.spin_stock_qty.setEnabled(needs_stock)
    self.edit_stock_price.setStyleSheet(
        "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;border-radius:3px;font-size:12px;"
        if needs_stock else
        "background:#070710;color:#555;border:1px solid #222;")


def _get_leg_template(self, strat: str) -> list:
    """전략명 → 레그 기본 정의 반환."""
    expiry = self._expiry_list[0][0] if self._expiry_list else ""
    base   = {"qty": "1", "expiry": expiry}

    templates = {
        "커버드 콜": [
            {**base, "leg":"레그1","dir":"SELL","cp":"C","strike":"","prem":""}],
        "프로텍티브 풋": [
            {**base, "leg":"레그1","dir":"BUY","cp":"P","strike":"","prem":""}],
        "콜 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"C","strike":"","prem":""}],
        "풋 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"P","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"P","strike":"","prem":""}],
        "콜 데빗 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"C","strike":"","prem":""}],
        "풋 데빗 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"P","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"P","strike":"","prem":""}],
        "스트래들": [
            {**base, "leg":"레그1","dir":"BUY","cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY","cp":"P","strike":"","prem":""}],
        "스트랭글": [
            {**base, "leg":"레그1","dir":"BUY","cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY","cp":"P","strike":"","prem":""}],
        "아이언 콘도르": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"P","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"P","strike":"","prem":""},
            {**base, "leg":"레그3","dir":"SELL","cp":"C","strike":"","prem":""},
            {**base, "leg":"레그4","dir":"BUY", "cp":"C","strike":"","prem":""}],
        "콜 백 스프레드": [
            {**base, "leg":"레그1","dir":"SELL","cp":"C","qty":"1","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY", "cp":"C","qty":"2","strike":"","prem":""}],
        "풋 백 스프레드": [
            {**base, "leg":"레그1","dir":"SELL","cp":"P","qty":"1","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY", "cp":"P","qty":"2","strike":"","prem":""}],
    }
    for key, tmpl in templates.items():
        if key in strat:
            return tmpl
    return []


def _rebuild_legs(self, legs: list):
    """레그 테이블 재구성."""
    # 행사가(3) 변경 → Mid-price 자동 조회 훅 연결 (최초 1회)
    if not getattr(self, '_strike_hook_connected', False):
        self.tbl_legs.itemChanged.connect(lambda item: _on_strike_changed(self, item))
        self._strike_hook_connected = True

    self.tbl_legs.setRowCount(0)
    for i, leg in enumerate(legs):
        r = self.tbl_legs.rowCount()
        self.tbl_legs.insertRow(r)
        col = LEG_COLORS[i % len(LEG_COLORS)]

        it0 = QTableWidgetItem(leg["leg"])
        it0.setTextAlignment(Qt.AlignCenter)
        it0.setForeground(QBrush(QColor(col)))
        it0.setFlags(it0.flags() & ~Qt.ItemIsEditable)
        self.tbl_legs.setItem(r, 0, it0)

        dir_col = "#00ff88" if leg["dir"] == "BUY" else "#ff6666"
        it1 = QTableWidgetItem(leg["dir"])
        it1.setTextAlignment(Qt.AlignCenter)
        it1.setForeground(QBrush(QColor(dir_col)))
        it1.setFlags(it1.flags() & ~Qt.ItemIsEditable)
        self.tbl_legs.setItem(r, 1, it1)

        for c, key in enumerate(["cp","strike","prem","qty"], 2):
            it = QTableWidgetItem(str(leg.get(key, "")))
            it.setTextAlignment(Qt.AlignCenter)
            self.tbl_legs.setItem(r, c, it)

        raw_expiry = str(leg.get("expiry", ""))
        it_exp = QTableWidgetItem(_fmt_expiry(raw_expiry))
        it_exp.setTextAlignment(Qt.AlignCenter)
        it_exp.setForeground(QBrush(QColor("#aaffaa")))
        self.tbl_legs.setItem(r, 6, it_exp)


def _reset_legs(self):
    """레그 + 결과 초기화."""
    # 초기화 시 실시간 스트림 먼저 해제 (_on_strat_change 내부에서도 해제되지만 명시적으로)
    try:
        from combo_ui_leg_panel import cancel_all_streams
        cancel_all_streams(self)
    except Exception:
        pass
    self._on_strat_change(self.combo_strat.currentIndex())
    self.tbl_scenario.setRowCount(0)
    for v in self._kpi_widgets.values():
        v.setText("―")
    for v in self._spread_labels.values():
        v.setText("―")
    if PG and hasattr(self, '_curve_pnl'):
        self._curve_pnl.setData([], [])
    self._log("초기화 완료")


def _set_leg_mode(self, mode: str):
    is_manual = (mode == "manual")
    self._leg_mode = mode
    self._btn_leg_auto.setChecked(not is_manual)
    self._btn_leg_manual.setChecked(is_manual)
    self._manual_btn_row.setVisible(is_manual)
    for r in range(self.tbl_legs.rowCount()):
        for c in range(self.tbl_legs.columnCount()):
            it = self.tbl_legs.item(r, c)
            if it:
                if is_manual:
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
                elif c in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    self._log("✏ 수동 모드" if is_manual else "🔗 자동 모드")


def _manual_add_leg(self):
    r = self.tbl_legs.rowCount()
    self.tbl_legs.insertRow(r)
    col = LEG_COLORS[r % len(LEG_COLORS)]
    for c, val in enumerate([f"레그{r+1}", "BUY", "C", "", "0.00", "1", "―"]):
        it = QTableWidgetItem(val)
        it.setTextAlignment(Qt.AlignCenter)
        if c == 0:
            it.setForeground(QBrush(QColor(col)))
        elif c == 1:
            it.setForeground(QBrush(QColor("#00ff88")))
        self.tbl_legs.setItem(r, c, it)
    self._log(f"➕ 레그{r+1} 추가 (수동)")


def _manual_del_leg(self):
    row = self.tbl_legs.currentRow()
    if row < 0:
        row = self.tbl_legs.rowCount() - 1
    if row >= 0:
        self.tbl_legs.removeRow(row)
        self._log(f"➖ 레그{row+1} 제거 (수동)")


# ── 행사가 입력 시 Mid-price 자동 조회 ───────────────────────────

def _on_strike_changed(self, item):
    """
    tbl_legs 행사가(컬럼 3) 변경 시 자동 호출.

    흐름:
      1. 행사가 값 파싱
      2. reqContractDetails → conId 획득
      3. fill_premium_from_market(row, conId) 호출
         → Mid-price → 프리미엄 셀 자동 입력
         → _recalc_net_price() → Net Price 라벨 갱신
    """
    if item.column() != 3:          # 행사가 컬럼만 처리
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

    # 해당 레그의 C/P, 만기 읽기
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

    # conId 조회 후 fill_premium_from_market 호출
    _fetch_conid_then_premium(self, row, symbol, strike_f, cp, raw_expiry)


def _fetch_conid_then_premium(self, row, symbol, strike, cp, expiry):
    """
    reqContractDetails → conId → fill_premium_from_market(row, conId).
    타임아웃 3초 / 실패 시 conId=0으로 폴백(fill 스킵).
    """
    try:
        from core_contract import make_opt_contract
        from combo_ui_leg_panel import fill_premium_from_market
    except ImportError:
        return

    from PyQt5.QtCore import QTimer

    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ib is None:
        return

    rid = 8850 + row   # reqContractDetails용 ID (leg_panel 8800~8815와 분리)
    opt = make_opt_contract(symbol=symbol, strike=strike, right=cp, expiry=expiry)

    _orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
    _orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)
    resolved = {}

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

    # 3초 타임아웃
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