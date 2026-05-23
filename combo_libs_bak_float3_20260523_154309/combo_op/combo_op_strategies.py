"""
combo_op_strategies.py — 전략별 행사가 탐색 로직
────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_strategies.py
포함:
  _search_vertical()         — 콜/풋 데빗 스프레드
  _search_credit_vertical()  — 숏 콜 스프레드 / 불 풋 스프레드 (신규 v2.3)
  _search_straddle()
  _search_strangle()
  _search_iron_condor()
────────────────────────────────────────────────────
"""

from itertools import combinations
from .combo_op_constants import _calc_pop
from .combo_op_search    import _atm_dist_pct


# ── 데빗 수직 스프레드 ────────────────────────────────────────

def _search_vertical(self, strikes, chain, cp, label,
                     qty, budget, min_ror, buy_lower, p) -> list:
    """콜/풋 데빗 스프레드 탐색. buy_lower=True → 콜 스프레드, False → 풋 스프레드."""
    results   = []
    atm_limit = p["atm_dist"]
    iv        = p["iv"]
    dte       = p["dte"]
    und       = self._und_price or 0

    valid = [(k, v) for k, v in chain.items() if v and k in strikes]
    valid.sort(key=lambda x: x[0])

    for (k1, p1), (k2, p2) in combinations(valid, 2):
        if buy_lower:
            buy_k, buy_p   = k1, p1
            sell_k, sell_p = k2, p2
        else:
            buy_k, buy_p   = k2, p2
            sell_k, sell_p = k1, p1

        if atm_limit and und and _atm_dist_pct(self, buy_k) > atm_limit:
            continue

        width    = abs(buy_k - sell_k)
        net_prem = buy_p - sell_p
        if net_prem <= 0:
            continue
        max_loss   = net_prem * qty * 100
        max_profit = (width - net_prem) * qty * 100
        if max_profit <= 0 or max_loss > budget:
            continue
        ror = (max_profit / max_loss * 100) if max_loss else 0
        if min_ror and ror < min_ror:
            continue

        atm_d = _atm_dist_pct(self, buy_k) if und else 0.0
        pop   = _calc_pop(und or buy_k, sell_k, dte, iv, cp) if und else 0.0

        results.append({
            "label":      label,
            "buy_k":      buy_k,
            "sell_k":     sell_k,
            "net_prem":   net_prem,
            "max_profit": max_profit,
            "max_loss":   max_loss,
            "ror":        ror,
            "rr":         max_profit / max_loss if max_loss else 0,
            "cp":         cp,
            "qty":        qty,
            "atm_dist":   atm_d,
            "pop":        pop,
        })
    return results


# ── 크레딧 수직 스프레드 (신규 v2.3) ─────────────────────────

def _search_credit_vertical(self, strikes, chain, cp, label,
                             qty, budget, min_ror, p) -> list:
    """
    숏 콜 스프레드(베어 콜) / 불 풋 스프레드 탐색.
    크레딧 수취 구조:
      콜: sell_k=낮은K, buy_k=높은K  → credit = sell_p - buy_p
      풋: sell_k=높은K, buy_k=낮은K  → credit = sell_p - buy_p
    budget = 최대 허용 손실 (= 스프레드 너비 - 크레딧)
    """
    results   = []
    atm_limit = p["atm_dist"]
    iv        = p["iv"]
    dte       = p["dte"]
    und       = self._und_price or 0

    valid = [(k, v) for k, v in chain.items() if v and k in strikes]
    valid.sort(key=lambda x: x[0])

    for (k1, p1), (k2, p2) in combinations(valid, 2):
        if cp == "C":
            sell_k, sell_p = k1, p1   # 낮은 K 매도
            buy_k,  buy_p  = k2, p2   # 높은 K 매수
        else:  # P
            sell_k, sell_p = k2, p2   # 높은 K 매도
            buy_k,  buy_p  = k1, p1   # 낮은 K 매수

        if atm_limit and und and _atm_dist_pct(self, sell_k) > atm_limit:
            continue

        credit = sell_p - buy_p   # 수취 크레딧 (양수여야 유효)
        if credit <= 0:
            continue

        width      = abs(sell_k - buy_k)
        max_profit = credit * qty * 100        # 최대 이익 = 수취 크레딧
        max_loss   = (width - credit) * qty * 100
        if max_loss <= 0 or max_loss > budget:
            continue

        ror = (max_profit / max_loss * 100) if max_loss else 0
        if min_ror and ror < min_ror:
            continue

        atm_d = _atm_dist_pct(self, sell_k) if und else 0.0
        pop   = _calc_pop(und or sell_k, sell_k, dte, iv, cp) if und else 0.0

        results.append({
            "label":      label,
            "buy_k":      buy_k,
            "sell_k":     sell_k,
            "net_prem":   -credit,        # 크레딧이므로 음수 표시
            "max_profit": max_profit,
            "max_loss":   max_loss,
            "ror":        ror,
            "rr":         max_profit / max_loss if max_loss else 0,
            "cp":         cp,
            "qty":        qty,
            "atm_dist":   atm_d,
            "pop":        pop,
        })
    return results


# ── 스트래들 ──────────────────────────────────────────────────

def _search_straddle(self, qty, budget, min_ror, p) -> list:
    results   = []
    atm_limit = p["atm_dist"]
    iv        = p["iv"]
    dte       = p["dte"]
    und       = self._und_price or 0

    call_map = {k: v for k, v in self._chain_call.items() if v}
    put_map  = {k: v for k, v in self._chain_put.items()  if v}

    for strike in set(call_map) & set(put_map):
        if atm_limit and und and _atm_dist_pct(self, strike) > atm_limit:
            continue

        cp_ = call_map[strike]
        pp_ = put_map[strike]
        total_prem = (cp_ + pp_) * qty * 100
        if total_prem > budget:
            continue

        max_loss   = total_prem
        max_profit = (cp_ + pp_) * qty * 100 * 2   # 근사
        ror = max_profit / max_loss * 100 if max_loss else 0
        if min_ror and ror < min_ror:
            continue

        atm_d = _atm_dist_pct(self, strike) if und else 0.0
        pop_c = _calc_pop(und or strike, strike, dte, iv, "C") if und else 0.0
        pop_p = _calc_pop(und or strike, strike, dte, iv, "P") if und else 0.0
        pop   = (pop_c + pop_p) / 2

        results.append({
            "label":      "스트래들",
            "buy_k":      strike,
            "sell_k":     strike,
            "net_prem":   cp_ + pp_,
            "max_profit": max_profit,
            "max_loss":   max_loss,
            "ror":        ror,
            "rr":         max_profit / max_loss if max_loss else 0,
            "cp":         "C+P",
            "qty":        qty,
            "atm_dist":   atm_d,
            "pop":        pop,
        })
    return results


# ── 스트랭글 ──────────────────────────────────────────────────

def _search_strangle(self, qty, budget, min_ror, p) -> list:
    results   = []
    atm_limit = p["atm_dist"]
    iv        = p["iv"]
    dte       = p["dte"]
    und       = self._und_price or 0

    call_valid = [(k, v) for k, v in self._chain_call.items() if v]
    put_valid  = [(k, v) for k, v in self._chain_put.items()  if v]

    for (ck, cp_) in call_valid:
        for (pk, pp_) in put_valid:
            if ck <= pk:
                continue
            if und and (ck < und or pk > und):
                continue   # OTM 필터

            if atm_limit and und:
                if (_atm_dist_pct(self, ck) > atm_limit or
                        _atm_dist_pct(self, pk) > atm_limit):
                    continue

            total_prem = (cp_ + pp_) * qty * 100
            if total_prem > budget:
                continue
            max_loss   = total_prem
            max_profit = (ck - pk - cp_ - pp_) * qty * 100
            if max_profit <= 0:
                continue
            ror = max_profit / max_loss * 100 if max_loss else 0
            if min_ror and ror < min_ror:
                continue

            atm_d = (_atm_dist_pct(self, ck) + _atm_dist_pct(self, pk)) / 2 if und else 0.0
            pop_c = _calc_pop(und, ck, dte, iv, "C") if und else 0.0
            pop_p = _calc_pop(und, pk, dte, iv, "P") if und else 0.0
            pop   = (pop_c + pop_p) / 2

            results.append({
                "label":      "스트랭글",
                "buy_k":      pk,
                "sell_k":     ck,
                "net_prem":   cp_ + pp_,
                "max_profit": max_profit,
                "max_loss":   max_loss,
                "ror":        ror,
                "rr":         max_profit / max_loss if max_loss else 0,
                "cp":         "C+P",
                "qty":        qty,
                "atm_dist":   atm_d,
                "pop":        pop,
            })
    return results


# ── 아이언 콘도르 (O(n⁴) — Worker 필수) ─────────────────────

def _search_iron_condor(self, qty, budget, min_ror, p) -> list:
    results   = []
    atm_limit = p["atm_dist"]
    iv        = p["iv"]
    dte       = p["dte"]
    und       = self._und_price or 0

    call_valid = sorted(
        [(k, v) for k, v in self._chain_call.items() if v],
        key=lambda x: x[0])
    put_valid  = sorted(
        [(k, v) for k, v in self._chain_put.items() if v],
        key=lambda x: x[0])

    for (bp_k, bp_p), (sp_k, sp_p) in combinations(put_valid, 2):
        if bp_k >= sp_k:
            continue
        if atm_limit and und and _atm_dist_pct(self, sp_k) > atm_limit:
            continue

        for (sc_k, sc_p), (bc_k, bc_p) in combinations(call_valid, 2):
            if sc_k >= bc_k:
                continue
            if sp_k >= sc_k:
                continue
            if atm_limit and und and _atm_dist_pct(self, sc_k) > atm_limit:
                continue

            credit     = (sp_p - bp_p + sc_p - bc_p) * qty * 100
            if credit <= 0:
                continue
            put_width  = (sp_k - bp_k) * qty * 100
            call_width = (bc_k - sc_k) * qty * 100
            max_loss   = max(put_width, call_width) - credit
            if max_loss <= 0 or max_loss > budget:
                continue
            max_profit = credit
            ror = max_profit / max_loss * 100 if max_loss else 0
            if min_ror and ror < min_ror:
                continue

            atm_d = (_atm_dist_pct(self, sp_k) + _atm_dist_pct(self, sc_k)) / 2 if und else 0.0
            pop_p = _calc_pop(und, sp_k, dte, iv, "P") if und else 0.0
            pop_c = _calc_pop(und, sc_k, dte, iv, "C") if und else 0.0
            pop   = (pop_p + pop_c) / 2

            results.append({
                "label":      "아이언 콘도르",
                "buy_k":      f"{bp_k}/{sp_k}",
                "sell_k":     f"{sc_k}/{bc_k}",
                "net_prem":   -(sp_p - bp_p + sc_p - bc_p),
                "max_profit": max_profit,
                "max_loss":   max_loss,
                "ror":        ror,
                "rr":         max_profit / max_loss if max_loss else 0,
                "cp":         "IC",
                "qty":        qty,
                "atm_dist":   atm_d,
                "pop":        pop,
            })
    return results
