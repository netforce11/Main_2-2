"""
combo_ui_leg_logic.py — 레그 빌드 · 전략 변경 로직
────────────────────────────────────────────────────
포함:
  _on_strat_change / _get_leg_template / _rebuild_legs
  _reset_legs / _fmt_expiry
  _set_leg_mode

분리:
  _manual_add_leg / _manual_del_leg / _on_strike_changed
  → combo_ui_leg_extra.py
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import LEG_COLORS, MAX_LEGS


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


# ── 전략 변경 ────────────────────────────────────────────────

def _on_strat_change(self, idx: int):
    strat = self.combo_strat.currentText()
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
        "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
        "border-radius:3px;font-size:12px;"
        if needs_stock else
        "background:#070710;color:#555;border:1px solid #222;")
    # 추가 레그 버튼 최대치 갱신
    _update_add_btn_state(self)


def _get_leg_template(self, strat: str) -> list:
    """전략명 → 레그 기본 정의 반환."""
    expiry = self._expiry_list[0][0] if self._expiry_list else ""
    base   = {"qty": "1", "expiry": expiry}

    # 주의: 키 매칭이 'key in strat' 방식이므로
    # 짧은 키가 긴 키의 부분 문자열이 되면 먼저 매칭됨.
    # ex) "콜 스프레드" ⊂ "숏 콜 스프레드 / 베어 콜 스프레드"
    # → 신규 전략(더 긴 이름)을 반드시 앞에 배치해야 함.
    templates = {
        # ── 신규 전략 — 반드시 "콜 스프레드"/"풋 스프레드" 앞에 위치 ──
        "숏 콜 스프레드": [
            {**base, "leg":"레그1","dir":"SELL","cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY", "cp":"C","strike":"","prem":""}],
        "베어 콜 스프레드": [
            {**base, "leg":"레그1","dir":"SELL","cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY", "cp":"C","strike":"","prem":""}],
        "불 풋 스프레드": [
            {**base, "leg":"레그1","dir":"SELL","cp":"P","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"BUY", "cp":"P","strike":"","prem":""}],
        # ── 기존 전략 ──────────────────────────────────────────
        "커버드 콜": [
            {**base, "leg":"레그1","dir":"SELL","cp":"C","strike":"","prem":""}],
        "프로텍티브 풋": [
            {**base, "leg":"레그1","dir":"BUY","cp":"P","strike":"","prem":""}],
        "콜 데빗 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"C","strike":"","prem":""}],
        "풋 데빗 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"P","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"P","strike":"","prem":""}],
        "콜 스프레드": [
            {**base, "leg":"레그1","dir":"BUY", "cp":"C","strike":"","prem":""},
            {**base, "leg":"레그2","dir":"SELL","cp":"C","strike":"","prem":""}],
        "풋 스프레드": [
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
    # 길이 내림차순 정렬 후 매칭 — 긴 키(더 구체적)가 먼저 매칭되도록 보장
    for key in sorted(templates.keys(), key=len, reverse=True):
        if key in strat:
            return templates[key]
    return []


# ── 레그 테이블 재구성 ────────────────────────────────────────

def _rebuild_legs(self, legs: list):
    """레그 테이블 재구성."""
    if not getattr(self, '_strike_hook_connected', False):
        from combo_ui_leg_extra import _on_strike_changed
        self.tbl_legs.itemChanged.connect(
            lambda item: _on_strike_changed(self, item))
        self._strike_hook_connected = True

    self.tbl_legs.setRowCount(0)
    for i, leg in enumerate(legs):
        _insert_leg_row(self, leg, i)
    _update_add_btn_state(self)

    # ★ 전략 변경 시 전광판 초기화
    display = getattr(self, 'net_price_display', None)
    if display is not None:
        display.reset()


def _insert_leg_row(self, leg: dict, row_idx: int):
    """레그 1행을 tbl_legs에 삽입."""
    r   = self.tbl_legs.rowCount()
    col = LEG_COLORS[row_idx % len(LEG_COLORS)]
    self.tbl_legs.insertRow(r)

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


# ── 초기화 ───────────────────────────────────────────────────

def _reset_legs(self):
    """레그 + 결과 초기화."""
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


# ── 레그 모드 전환 ────────────────────────────────────────────

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
    _update_add_btn_state(self)
    self._log("✏ 수동 모드" if is_manual else "🔗 자동 모드")


# ── 추가 레그 버튼 상태 갱신 ─────────────────────────────────

def _update_add_btn_state(self):
    """레그 수가 MAX_LEGS 이상이면 추가 버튼 비활성화."""
    btn = getattr(self, '_btn_extra_add', None)
    if btn:
        count = self.tbl_legs.rowCount()
        btn.setEnabled(count < MAX_LEGS)
        btn.setToolTip(
            f"레그 추가 (현재 {count}/{MAX_LEGS})"
            if count < MAX_LEGS else
            f"최대 {MAX_LEGS}개 레그까지 추가 가능합니다")