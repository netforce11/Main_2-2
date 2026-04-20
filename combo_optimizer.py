"""
combo_optimizer.py — Cost Optimizer 조립 Entry Point
════════════════════════════════════════════════════════════════
위치: main2/combo_libs/combo_optimizer.py   ← combo_op/ 폴더 밖!

역할: combo_op/ 서브패키지의 모듈들을 OptimizerPanelMixin으로 조립.
      ComboStrategyGrid가 이 Mixin을 상속하면 모든 Optimizer 기능을 얻는다.

v2.3 변경사항:
  - 파일 분리: combo_op/ 서브패키지로 기능별 분리 (150~200줄 단위)
  - 신규 전략: 숏 콜 스프레드(베어 콜) / 불 풋 스프레드 추가
  - Optimizer 팝업 방식 전환: 슬라이드 패널 → 독립 QDialog
════════════════════════════════════════════════════════════════
"""

# ── 서브패키지 공개 심벌 re-export ───────────────────────────
from combo_op.combo_op_constants import (          # noqa: F401
    _STRAT_LEGS, _CALL_SPREAD_TYPES, _PUT_SPREAD_TYPES,
    _BEAR_CALL_TYPES, _BULL_PUT_TYPES,
    _strat_key, _norm_cdf, _calc_pop,
)
from combo_op.combo_op_worker  import _SearchWorker          # noqa: F401
from combo_op.combo_op_dialog  import (                      # noqa: F401
    OptimizerDialog, _toggle_optimizer_panel,
)


# ══════════════════════════════════════════════════════════════
class OptimizerPanelMixin:
    """
    Cost Optimizer 기능 Mixin.
    각 메서드는 combo_op/ 서브패키지 함수를 위임(delegate)한다.
    """

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_optimizer_panel(self):
        from combo_op.combo_op_ui import _build_optimizer_panel as _f
        return _f(self)

    @staticmethod
    def _opt_label(text):
        from combo_op.combo_op_ui import _opt_label
        return _opt_label(text)

    @staticmethod
    def _opt_spin_style():
        from combo_op.combo_op_ui import _opt_spin_style
        return _opt_spin_style()

    # ── 파라미터 + ATM 헬퍼 ──────────────────────────────────
    def _opt_params(self):
        from combo_op.combo_op_search import _opt_params as _f
        return _f(self)

    def _atm_dist_pct(self, strike):
        from combo_op.combo_op_search import _atm_dist_pct as _f
        return _f(self, strike)

    def _atm_ok(self, strike, limit):
        from combo_op.combo_op_search import _atm_ok as _f
        return _f(self, strike, limit)

    # ── 탐색 실행 / 콜백 ─────────────────────────────────────
    def _run_optimizer(self):
        from combo_op.combo_op_search import _run_optimizer as _f
        _f(self)

    def _on_search_done(self, results):
        from combo_op.combo_op_search import _on_search_done as _f
        _f(self, results)

    def _on_search_error(self, msg):
        from combo_op.combo_op_search import _on_search_error as _f
        _f(self, msg)

    # ── 전략별 탐색 ──────────────────────────────────────────
    def _search_vertical(self, strikes, chain, cp, label,
                         qty, budget, min_ror, buy_lower, p):
        from combo_op.combo_op_strategies import _search_vertical as _f
        return _f(self, strikes, chain, cp, label,
                  qty, budget, min_ror, buy_lower, p)

    def _search_credit_vertical(self, strikes, chain, cp, label,
                                qty, budget, min_ror, p):
        from combo_op.combo_op_strategies import _search_credit_vertical as _f
        return _f(self, strikes, chain, cp, label, qty, budget, min_ror, p)

    def _search_straddle(self, qty, budget, min_ror, p):
        from combo_op.combo_op_strategies import _search_straddle as _f
        return _f(self, qty, budget, min_ror, p)

    def _search_strangle(self, qty, budget, min_ror, p):
        from combo_op.combo_op_strategies import _search_strangle as _f
        return _f(self, qty, budget, min_ror, p)

    def _search_iron_condor(self, qty, budget, min_ror, p):
        from combo_op.combo_op_strategies import _search_iron_condor as _f
        return _f(self, qty, budget, min_ror, p)

    # ── 결과 테이블 + 레그 적용 ──────────────────────────────
    def _populate_opt_table(self, results):
        from combo_op.combo_op_table import _populate_opt_table as _f
        _f(self, results)

    def _on_opt_result_click(self, row, col):
        from combo_op.combo_op_table import _on_opt_result_click as _f
        _f(self, row, col)

    def _fill_legs_from_result(self):
        from combo_op.combo_op_table import _fill_legs_from_result as _f
        _f(self)

    def _set_leg_row(self, row, strike, prem, qty, expiry):
        from combo_op.combo_op_table import _set_leg_row as _f
        _f(self, row, strike, prem, qty, expiry)

    def _get_chain_price(self, cp, strike):
        from combo_op.combo_op_table import _get_chain_price as _f
        return _f(self, cp, strike)

    # ── 팝업 토글 ────────────────────────────────────────────
    def _toggle_optimizer_panel(self):
        from combo_op.combo_op_dialog import _toggle_optimizer_panel as _f
        _f(self)
