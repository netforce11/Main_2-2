"""
combo_pnl_calc.py — 손익 계산 순수 함수 모음
────────────────────────────────────────────
포함:
  _make_price_range     — 시나리오 가격 범위 생성
  _leg_pnl_at_expiry    — 단일 레그 만기 손익 시리즈
  _find_breakevens      — 손익분기 탐색
  _fill_scenario_table  — 시나리오 테이블 갱신

combo_ui_right_panels_ext._calc_pnl 에서 호출.
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush


def _make_price_range(min_s: float, max_s: float,
                      step: float, margin: float = 0.15) -> list:
    """시나리오 가격 범위 생성."""
    span  = max(max_s - min_s, 50.0)
    start = max(0, min_s - span * margin)
    end   = max_s + span * margin
    prices = []
    p = start
    while p <= end + step:
        prices.append(round(p, 2))
        p += step
    return prices


def _leg_pnl_at_expiry(leg: dict, price_range: list) -> list:
    """
    단일 레그 만기 손익 시리즈.
    BUY: 행사가 초과분 - 프리미엄
    SELL: 프리미엄 - 행사가 초과분
    qty 반영.
    """
    strike = leg["strike"]
    prem   = float(leg.get("prem", 0) or 0)
    qty    = int(leg.get("qty", 1))
    cp     = leg["cp"].upper()
    is_buy = (leg["dir"] == "BUY")
    result = []
    for price in price_range:
        intrinsic = max(price - strike, 0) if cp == "C" else max(strike - price, 0)
        pnl = (intrinsic - prem) * qty if is_buy else (prem - intrinsic) * qty
        result.append(round(pnl, 4))
    return result


def _find_breakevens(price_range: list, total_pnl: list,
                     threshold: float = 0.5) -> list:
    """부호 전환점 → 손익분기 가격 리스트 (최대 2개)."""
    beps = []
    for i in range(1, len(total_pnl)):
        prev, curr = total_pnl[i-1], total_pnl[i]
        if prev * curr < 0:
            ratio = abs(prev) / (abs(prev) + abs(curr))
            bep   = price_range[i-1] + ratio * (price_range[i] - price_range[i-1])
            beps.append(round(bep, 1))
        elif abs(curr) < threshold and abs(prev) >= threshold:
            beps.append(price_range[i])
    return beps[:2]


def _fill_scenario_table(self, price_range, total_pnl,
                          pnl_series, legs, net_cost):
    """행사가별 손익 시나리오 테이블 갱신."""
    tbl = self.tbl_scenario
    tbl.setRowCount(0)
    call_idxs    = [i for i, l in enumerate(legs) if l["cp"].upper() == "C"]
    put_idxs     = [i for i, l in enumerate(legs) if l["cp"].upper() == "P"]
    net_cost_abs = abs(net_cost) if net_cost != 0 else 1e-9

    for i, (price, pnl) in enumerate(zip(price_range, total_pnl)):
        r = tbl.rowCount(); tbl.insertRow(r)
        pnl_100  = round(pnl * 100, 0)
        pct      = round(pnl / net_cost_abs * 100, 1) if net_cost_abs else 0
        call_sum = sum(pnl_series[ci][i] for ci in call_idxs)
        put_sum  = sum(pnl_series[pi][i] for pi in put_idxs)
        color    = "#00ff88" if pnl > 0 else ("#ff4444" if pnl < 0 else "#888")

        def _mk(text, col=None):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(Qt.AlignCenter)
            if col:
                it.setForeground(QBrush(QColor(col)))
            return it

        tbl.setItem(r, 0, _mk(f"{price:.1f}", "#90caf9"))
        tbl.setItem(r, 1, _mk(f"${pnl:.4f}", color))
        tbl.setItem(r, 2, _mk(f"${pnl_100:,.0f}", color))
        tbl.setItem(r, 3, _mk(f"{pct:+.1f}%", color))
        tbl.setItem(r, 4, _mk(f"${call_sum*100:,.0f}", "#33aaff"))
        tbl.setItem(r, 5, _mk(f"${put_sum*100:,.0f}", "#ff9944"))
