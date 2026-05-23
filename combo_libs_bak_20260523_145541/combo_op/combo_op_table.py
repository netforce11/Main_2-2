"""
combo_op_table.py — 결과 테이블 렌더링 + 레그 적용
────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_table.py
포함:
  _populate_opt_table()
  _on_opt_result_click()
  _fill_legs_from_result()
  _set_leg_row() / _get_chain_price()
────────────────────────────────────────────────────
"""

from PyQt5.QtCore import QTimer

# combo_constants는 main2/combo_libs/ 에 위치
from combo_constants import mk_item


# ── 결과 테이블 채우기 ────────────────────────────────────────

def _populate_opt_table(self, results: list):
    """탐색 결과 리스트 → tbl_opt_result 렌더링."""
    self.tbl_opt_result.setRowCount(0)
    for res in results:
        r = self.tbl_opt_result.rowCount()
        self.tbl_opt_result.insertRow(r)

        profit_col = "#00ff88" if res["max_profit"] > 0 else "#ff4444"
        ror_col    = "#00ff88" if res["ror"] >= 50  else "#ffd700"

        pop   = res.get("pop", 0)
        pop_col = ("#00ff88" if pop >= 70
                   else "#ffd700" if pop >= 50
                   else "#ff6666")

        atm_d   = res.get("atm_dist", 0)
        atm_col = ("#00e676" if atm_d <= 2
                   else "#ffd700" if atm_d <= 5
                   else "#aaaaaa")

        self.tbl_opt_result.setItem(r, 0, mk_item(res["label"],              "#90caf9"))
        self.tbl_opt_result.setItem(r, 1, mk_item(str(res["buy_k"]),         "#ffd700"))
        self.tbl_opt_result.setItem(r, 2, mk_item(str(res["sell_k"]),        "#ff9999"))
        self.tbl_opt_result.setItem(r, 3, mk_item(f"${res['net_prem']:.2f}", "#aaa"))
        self.tbl_opt_result.setItem(r, 4, mk_item(
            f"${res['max_profit']:,.2f}", profit_col))
        self.tbl_opt_result.setItem(r, 5, mk_item(
            f"${res['max_loss']:,.2f}", "#ff4444"))
        self.tbl_opt_result.setItem(r, 6, mk_item(
            f"{res['ror']:.1f}%", ror_col))
        self.tbl_opt_result.setItem(r, 7, mk_item(
            f"{res['rr']:.2f}:1", "#ff8844"))
        self.tbl_opt_result.setItem(r, 8, mk_item(
            f"{atm_d:.1f}%", atm_col))
        self.tbl_opt_result.setItem(r, 9, mk_item(
            f"{pop:.1f}%" if pop > 0 else "—", pop_col))

    self._opt_results = results


# ── 행 클릭 ──────────────────────────────────────────────────

def _on_opt_result_click(self, row, col):
    self._opt_selected_row = row
    self.btn_opt_apply.setEnabled(True)


# ── 선택 결과 → 레그 테이블 자동 입력 ────────────────────────

def _fill_legs_from_result(self):
    if not hasattr(self, "_opt_results") or not self._opt_results:
        return
    row = getattr(self, "_opt_selected_row",
                  self.tbl_opt_result.currentRow())
    if row < 0 or row >= len(self._opt_results):
        row = 0

    res        = self._opt_results[row]
    qty        = str(res["qty"])
    cp         = res["cp"]
    expiry     = (self._expiry_list[0][0] if self._expiry_list else "")

    # _fmt_expiry: combo_ui_leg_logic.py 에 위치
    from combo_ui_leg_logic import _fmt_expiry
    exp_display = _fmt_expiry(expiry)

    # 전략 콤보박스 동기화
    for i in range(self.combo_strat.count()):
        if res["label"] in self.combo_strat.itemText(i):
            self.combo_strat.blockSignals(True)
            self.combo_strat.setCurrentIndex(i)
            self.combo_strat.blockSignals(False)
            self._on_strat_change(i)
            break

    def _apply():
        n      = self.tbl_legs.rowCount()
        buy_k  = res["buy_k"]
        sell_k = res["sell_k"]

        if cp in ("C", "P"):
            if n >= 1:
                _set_leg_row(self, 0, str(int(buy_k)),
                             f"{_get_chain_price(self, cp, buy_k):.2f}",
                             qty, exp_display)
            if n >= 2:
                _set_leg_row(self, 1, str(int(sell_k)),
                             f"{_get_chain_price(self, cp, sell_k):.2f}",
                             qty, exp_display)

        elif cp == "C+P":
            if n >= 1:
                _set_leg_row(self, 0, str(int(sell_k)),
                             f"{_get_chain_price(self, 'C', sell_k):.2f}",
                             qty, exp_display)
            if n >= 2:
                _set_leg_row(self, 1, str(int(buy_k)),
                             f"{_get_chain_price(self, 'P', buy_k):.2f}",
                             qty, exp_display)

        elif cp == "IC":
            try:
                bp, sp = [float(x) for x in str(buy_k).split("/")]
                sc, bc = [float(x) for x in str(sell_k).split("/")]
                for idx, (k, c) in enumerate([(bp, "P"), (sp, "P"),
                                               (sc, "C"), (bc, "C")]):
                    if idx < n:
                        _set_leg_row(self, idx, str(int(k)),
                                     f"{_get_chain_price(self, c, k):.2f}",
                                     qty, exp_display)
            except Exception:
                pass

        pop_str = (f"  POP {res['pop']:.1f}%"
                   if res.get("pop", 0) > 0 else "")
        atm_str = (f"  ATM±{res['atm_dist']:.1f}%"
                   if res.get("atm_dist", 0) > 0 else "")
        self._log(
            f"[Optimizer] 레그 적용: {res['label']}  "
            f"매수{buy_k} / 매도{sell_k}  "
            f"최대이익 ${res['max_profit']:,.2f}  "
            f"최대손실 ${res['max_loss']:,.2f}"
            + pop_str + atm_str)

    QTimer.singleShot(50, _apply)


# ── 행 내용 설정 헬퍼 ────────────────────────────────────────

def _set_leg_row(self, row: int, strike: str,
                 prem: str, qty: str, expiry: str):
    def _s(col, val):
        it = self.tbl_legs.item(row, col)
        if it:
            it.setText(val)
    _s(3, strike); _s(4, prem); _s(5, qty); _s(6, expiry)


def _get_chain_price(self, cp: str, strike: float) -> float:
    chain = self._chain_call if cp == "C" else self._chain_put
    return chain.get(strike) or 0.0
