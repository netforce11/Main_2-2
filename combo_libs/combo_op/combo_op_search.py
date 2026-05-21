"""
combo_op_search.py — Optimizer 탐색 실행 + 콜백
────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_search.py
포함:
  _opt_params()
  _atm_dist_pct() / _atm_ok()
  _run_optimizer()
  _on_search_done() / _on_search_error()
────────────────────────────────────────────────────
"""

from .combo_op_constants import (
    _strat_key,
    _CALL_SPREAD_TYPES, _PUT_SPREAD_TYPES,
    _BEAR_CALL_TYPES, _BULL_PUT_TYPES,
    ALL_CALL_TYPES, ALL_PUT_TYPES,  # [FIX-B12] 통합 집합 임포트
)
from .combo_op_worker import _SearchWorker


# ── 파라미터 수집 ─────────────────────────────────────────────

def _opt_params(self) -> dict:
    return {
        "budget":   self.opt_max_loss.value(),
        "min_ror":  self.opt_min_ror.value(),
        "qty":      self.opt_qty.value(),
        "atm_dist": self.opt_atm_dist.value(),   # 0 = 미적용
        "iv":       self.opt_iv.value(),
        "dte":      self.opt_dte.value(),
        "min_pop":  self.opt_min_pop.value(),     # 0 = 미적용
    }


# ── ATM 거리 헬퍼 ─────────────────────────────────────────────

def _atm_dist_pct(self, strike: float) -> float:
    """현재가 대비 행사가 거리 (%)."""
    if not self._und_price:
        return 0.0
    return abs(strike - self._und_price) / self._und_price * 100.0


def _atm_ok(self, strike: float, limit: float) -> bool:
    """ATM 거리 필터 통과 여부."""
    if limit == 0:
        return True
    return _atm_dist_pct(self, strike) <= limit


# ── 탐색 실행 ─────────────────────────────────────────────────

def _run_optimizer(self):
    strat_text = self.combo_strat.currentText()
    skey       = _strat_key(strat_text)

    if not skey:
        self.lbl_opt_status.setText(
            "⚠️  커버드콜·프로텍티브풋은 탐색 대상 아닙니다.")
        return
    if not self._call_strikes and not self._put_strikes:
        self.lbl_opt_status.setText("⚠️  먼저 체인 데이터를 동기화하세요.")
        return

    p = _opt_params(self)

    if skey in _CALL_SPREAD_TYPES:
        fn   = self._search_vertical
        args = (self._call_strikes, self._chain_call, "C",
                "콜 데빗 스프레드", p["qty"], p["budget"], p["min_ror"], True, p)
    elif skey in _PUT_SPREAD_TYPES:
        fn   = self._search_vertical
        args = (self._put_strikes, self._chain_put, "P",
                "풋 데빗 스프레드", p["qty"], p["budget"], p["min_ror"], False, p)
    elif skey == "스트래들":
        fn   = self._search_straddle
        args = (p["qty"], p["budget"], p["min_ror"], p)
    elif skey == "스트랭글":
        fn   = self._search_strangle
        args = (p["qty"], p["budget"], p["min_ror"], p)
    elif skey == "아이언 콘도르":
        fn   = self._search_iron_condor
        args = (p["qty"], p["budget"], p["min_ror"], p)
    elif skey in _BEAR_CALL_TYPES:
        fn   = self._search_credit_vertical
        args = (self._call_strikes, self._chain_call, "C",
                "숏 콜 스프레드 / 베어 콜 스프레드",
                p["qty"], p["budget"], p["min_ror"], p)
    elif skey in _BULL_PUT_TYPES:
        fn   = self._search_credit_vertical
        args = (self._put_strikes, self._chain_put, "P",
                "불 풋 스프레드", p["qty"], p["budget"], p["min_ror"], p)
    else:
        return

    self.btn_opt_run.setEnabled(False)
    self.lbl_opt_status.setText("🔄 탐색 중...")

    self._search_worker = _SearchWorker(fn, *args)
    self._search_worker.done.connect(self._on_search_done)
    self._search_worker.error.connect(self._on_search_error)
    self._search_worker.start()


# ── 탐색 완료 / 에러 콜백 ────────────────────────────────────

def _on_search_done(self, results: list):
    self.btn_opt_run.setEnabled(True)
    p       = _opt_params(self)
    min_pop = p["min_pop"]

    if min_pop > 0:
        results = [r for r in results if r.get("pop", 0) >= min_pop]

    results.sort(key=lambda x: (-x["max_profit"], -x["ror"]))
    results = results[:self.opt_top_n.value()]

    self._populate_opt_table(results)
    count = len(results)
    self.lbl_opt_status.setText(
        f"✅ {count}개 조합 발견  |  예산 ${p['budget']:,.0f}"
        + (f"  |  ATM±{p['atm_dist']}%" if p['atm_dist'] else "")
        + (f"  |  POP≥{p['min_pop']:.0f}%" if min_pop else ""))
    self.btn_opt_apply.setEnabled(count > 0)
    self._log(
        f"[Optimizer] {self.combo_strat.currentText()} — "
        f"{count}개 결과 (예산 ${p['budget']:,.0f}"
        + (f", ATM±{p['atm_dist']}%" if p['atm_dist'] else "")
        + (f", POP≥{p['min_pop']:.0f}%" if min_pop else "") + ")")


def _on_search_error(self, msg: str):
    self.btn_opt_run.setEnabled(True)
    self.lbl_opt_status.setText(f"❌ 오류: {msg}")
    self._log(f"[Optimizer] 오류: {msg}")
