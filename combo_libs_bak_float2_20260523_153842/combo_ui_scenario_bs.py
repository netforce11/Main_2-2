"""combo_ui_scenario_bs.py — Black-Scholes 계산 엔진 믹스인

ScenarioTab 에서 사용하는 순수 BS 계산 로직.
직접 인스턴스화하지 않고 ScenarioTab 이 상속해 사용.

[FIX-BS]
  · _bs_price()        — 순수 Python BS 공식 (math 표준 라이브러리)
  · _bs_spread_price() — 스프레드 포지션 BS 재계산
  · _calc()            — 단일 시나리오 계산 (BS 우선, 폴백 Δ+½Γ)
"""
import math


class _ScenarioBSMixin:
    """Black-Scholes 계산 전용 믹스인. ScenarioTab 이 단독 상속."""

    # ── [FIX-BS] 기본 BS 공식 ────────────────────────────────

    @staticmethod
    def _bs_price(S: float, K: float, T: float,
                  sigma: float, cp: str = 'C') -> float:
        """
        순수 Python Black-Scholes 옵션 가격 계산.
        외부 라이브러리 불필요 (math 표준 라이브러리만 사용).

        Args:
            S     : 현재 지수 가격
            K     : 행사가
            T     : 만기까지 남은 시간 (연 단위)
                    예) 2시간 = 2 / (252 * 6.5)  ← 거래일 기준
            sigma : IV (소수. 예: 0.15 = 15%)
            cp    : 'C' (콜) / 'P' (풋)

        Returns:
            float: 옵션 가격 (달러)
        """
        if S <= 0 or K <= 0 or sigma <= 0:
            return 0.0
        if T <= 1e-6:
            return max(S - K, 0.0) if cp == 'C' else max(K - S, 0.0)
        try:
            sqrtT = math.sqrt(T)
            d1    = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
            d2    = d1 - sigma * sqrtT

            def _N(x: float) -> float:
                return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

            return (S * _N(d1) - K * _N(d2) if cp == 'C'
                    else K * _N(-d2) - S * _N(-d1))
        except Exception:
            return 0.0

    # ── [FIX-BS] 스프레드 포지션 BS 재계산 ──────────────────

    def _bs_spread_price(self, S_new: float, T_new: float,
                         div: float) -> tuple:
        """
        스프레드 포지션 전체 BS 재계산.

        지수가 S_new 로 이동하고 남은 시간이 T_new 일 때
        각 레그를 BS로 재계산해 포지션 가격 반환.

        Args:
            S_new  : 이동 후 지수 가격
            T_new  : 남은 시간 (연 단위)
            div    : IV 변화 (%. 예: +2 = IV 2%p 상승)

        Returns:
            (포지션 가격, 계산 모드 str)  |  (None, '근사') — BS 불가 시
            계산 모드: 'BS' | '근사' | 'BS+근사'
        """
        if not self._legs_raw or self._und_price <= 0:
            return (None, '근사')

        total_price  = 0.0
        bs_count     = 0
        approx_count = 0

        for leg in self._legs_raw:
            try:
                strike    = float(leg.get('strike', 0) or 0)
                iv_raw    = leg.get('iv')
                qty       = float(leg.get('qty', 1) or 1)
                cp        = str(leg.get('cp', 'C')).upper()
                direction = str(leg.get('dir', 'BUY')).upper()
                coeff     = 1.0 if direction == 'BUY' else -1.0

                if strike <= 0:
                    continue

                if iv_raw is not None and float(iv_raw) > 0:
                    sigma     = max(float(iv_raw) + div / 100.0, 0.001)
                    leg_price = self._bs_price(S_new, strike, T_new, sigma, cp)
                    total_price += leg_price * qty * coeff * 100.0
                    bs_count += 1
                else:
                    d  = float(leg.get('delta', 0) or 0)
                    g  = float(leg.get('gamma', 0) or 0)
                    ds = S_new - self._und_price
                    total_price += (
                        (d * ds + 0.5 * g * ds * ds) * qty * coeff * 100.0)
                    approx_count += 1

            except Exception:
                continue

        if bs_count == 0:
            return (None, '근사')

        mode = 'BS' if approx_count == 0 else 'BS+근사'
        return (total_price / 100.0, mode)

    # ── 단일 시나리오 계산 ───────────────────────────────────

    def _calc(self, move: float, hours_left: float, div: float) -> dict:
        """
        단일 시나리오 계산 — BS 우선, 폴백 Δ+½Γ.

        Args:
            move       : 지수 이동 (포인트)
            hours_left : 만기까지 남은 시간 (시간, 슬라이더 값)
            div        : IV 변화 (%)

        Returns:
            dict: dg, th, vg, price, pct, capped, elapsed, mode
        """
        entry   = self._entry if self._entry > 0 else 0.01
        elapsed = max(self._hours_left - hours_left, 0.0)

        S_new     = self._und_price + move
        T_new     = max(hours_left / (252.0 * 6.5), 1e-6)
        bs_result, mode = self._bs_spread_price(S_new, T_new, div)

        dg_dollars = (self._pos_delta * move +
                      0.5 * self._pos_gamma * move * move) * 100.0
        th_dollars = self._pos_theta * (elapsed / 24.0) * 100.0
        vg_dollars = self._pos_vega * div * 100.0

        if bs_result is not None:
            expected_price = bs_result
        else:
            mode           = '근사'
            expected_price = entry + (dg_dollars + th_dollars + vg_dollars) / 100.0

        max_price      = self._max_val
        capped         = expected_price > max_price
        expected_price = min(max(expected_price, 0.0), max_price)
        pnl_pct        = ((expected_price - entry) / entry * 100.0) if entry > 0 else 0.0

        return {
            "dg":      dg_dollars,
            "th":      th_dollars,
            "vg":      vg_dollars,
            "price":   expected_price,
            "pct":     pnl_pct,
            "capped":  capped,
            "elapsed": elapsed,
            "mode":    mode,
        }
