"""
combo_order_utils.py — 주문 관련 파싱 유틸 · 증거금 추정
────────────────────────────────────────────────────────
포함:
  _parse_legs_from_table — tbl_legs → legs dict 리스트 (N-레그 지원)
  _parse_expiry_display  — MM/DD → YYYYMMDD 복원
  _calc_required_margin  — 전략 구조 기반 증거금 추정 (N-레그 확장)

v2.6 변경:
  _calc_required_margin:
    - 레그가 4개를 초과해도 BUY/SELL 쌍 매칭으로 정확히 계산
    - 수량(qty) 가중 페어링 방식: 각 레그의 qty를 반영
    - 추가 레그(레그5~8)도 콜/풋 분류 후 자동 포함
────────────────────────────────────────────────────────
"""

import re
from datetime import date


def _parse_legs_from_table(self) -> list:
    """tbl_legs → 레그 dict 리스트. 행사가 미입력 행 제외."""
    legs = []
    for r in range(self.tbl_legs.rowCount()):
        def cell(c, _r=r):
            it = self.tbl_legs.item(_r, c)
            return it.text().strip() if it else ""
        direction = cell(1); cp = cell(2); strike = cell(3)
        prem = cell(4); qty = cell(5); expiry = cell(6)
        if not strike or strike in ("―", ""):
            continue
        raw_expiry = _parse_expiry_display(expiry)
        if not raw_expiry:
            self._log(f"⚠ 레그{r+1} 만기 파싱 실패: '{expiry}'"); continue
        try:
            strike_f = float(strike)
        except ValueError:
            self._log(f"⚠ 레그{r+1} 행사가 파싱 실패: '{strike}'"); continue
        legs.append({
            "dir":    direction.upper() or "BUY",
            "cp":     cp.upper() or "C",
            "strike": strike_f,
            "prem":   prem or "0",
            "qty":    int(qty) if qty else 1,
            "expiry": raw_expiry,
        })
    return legs


def _parse_expiry_display(display: str) -> str:
    """
    다양한 만기 형식 → YYYYMMDD.
    지원: MM/DD, YYYYMMDD, YYYY-MM-DD, YYYY/MM/DD
    지나간 날짜면 내년으로 자동 이월.
    """
    if not display or display in ("―", ""):
        return ""
    digits = "".join(c for c in display if c.isdigit())
    if len(digits) == 8:
        return digits
    parts = re.split(r"[/\-\.]", display.strip())
    today = date.today()
    try:
        if len(parts) == 3:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return (date(y, m, d) if y > 1000 else date(d, y, m)).strftime("%Y%m%d")
        if len(parts) == 2:
            mm, dd = int(parts[0]), int(parts[1])
            candidate = date(today.year, mm, dd)
            if candidate < today:
                candidate = date(today.year + 1, mm, dd)
            return candidate.strftime("%Y%m%d")
    except (ValueError, TypeError):
        pass
    return ""


def _calc_required_margin(legs: list) -> float:
    """
    N-레그 전략 증거금 추정 (v2.6 확장).

    알고리즘:
      1. 레그를 콜/풋으로 분류 후 각각 qty-가중 페어링
      2. BUY qty ≥ SELL qty → 스프레드 증거금
         (행사가 차이 × min(buy, sell) × 100)
      3. 초과 BUY → 프리미엄 기반 추가 증거금
      4. BUY qty < SELL qty → 커버 분 스프레드 + 네이키드 분 20%
      5. 추가 레그(5~8번)는 자동으로 동일 계산에 포함됨
    """
    def _sort_by_strike(lst, reverse=False):
        return sorted(lst, key=lambda x: x["strike"], reverse=reverse)

    calls_sell = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "C" and l["dir"] == "SELL"])
    calls_buy  = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "C" and l["dir"] == "BUY"])
    puts_sell  = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "P" and l["dir"] == "SELL"],
        reverse=True)
    puts_buy   = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "P" and l["dir"] == "BUY"],
        reverse=True)

    total = 0.0
    for sell_legs, buy_legs in [(calls_sell, calls_buy),
                                (puts_sell,  puts_buy)]:
        sell_qty = sum(int(l.get("qty", 1)) for l in sell_legs)
        buy_qty  = sum(int(l.get("qty", 1)) for l in buy_legs)
        if sell_qty == 0:
            continue

        if buy_qty >= sell_qty:
            # 스프레드 / 백 스프레드 계열
            if sell_legs and buy_legs:
                spread = abs(sell_legs[0]["strike"] - buy_legs[0]["strike"])
                total += spread * min(sell_qty, buy_qty) * 100
            excess = buy_qty - sell_qty
            if excess > 0 and buy_legs:
                avg_prem = (
                    sum(float(l.get("prem", 0) or 0) * int(l.get("qty", 1))
                        for l in buy_legs) / buy_qty)
                total += avg_prem * excess * 100
        else:
            # 레이쇼 / 네이키드 포함
            if buy_legs and sell_legs:
                spread = abs(sell_legs[0]["strike"] - buy_legs[0]["strike"])
                total += spread * buy_qty * 100
            if sell_legs:
                naked_qty = sell_qty - buy_qty
                # 네이키드 레그 중 행사가 가장 높은 것 기준
                naked_strike = max(l["strike"] for l in sell_legs)
                total += naked_strike * 0.20 * naked_qty * 100

    return total
