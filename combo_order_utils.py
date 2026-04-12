"""
combo_order_utils.py — 주문 관련 파싱 유틸 · 증거금 추정
────────────────────────────────────────────────────────
포함:
  _parse_legs_from_table — tbl_legs → legs dict 리스트
  _parse_expiry_display  — MM/DD → YYYYMMDD 복원
  _calc_required_margin  — 전략 구조 기반 증거금 추정
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
    전략 구조 기반 증거금 추정.
    IB InitMarginReq 는 주문 전 0 반환 → 직접 계산.

    규칙:
      매수 ≥ 매도 (스프레드 / 백 스프레드)
        → 행사가 차이 × 커버 수 × 100
        → 초과 매수분: 프리미엄 × 초과 수 × 100
      매수 < 매도 (레이쇼 / 네이키드 포함)
        → 커버분: 스프레드 증거금
        → 네이키드분: 행사가 × 20% × 100
    """
    def _sort(lst, reverse=False):
        return sorted(lst, key=lambda x: x["strike"], reverse=reverse)

    calls_sell = _sort([l for l in legs if l["cp"].upper()=="C" and l["dir"]=="SELL"])
    calls_buy  = _sort([l for l in legs if l["cp"].upper()=="C" and l["dir"]=="BUY"])
    puts_sell  = _sort([l for l in legs if l["cp"].upper()=="P" and l["dir"]=="SELL"], reverse=True)
    puts_buy   = _sort([l for l in legs if l["cp"].upper()=="P" and l["dir"]=="BUY"],  reverse=True)

    total = 0.0
    for sell_legs, buy_legs in [(calls_sell, calls_buy), (puts_sell, puts_buy)]:
        sell_qty = sum(int(l.get("qty", 1)) for l in sell_legs)
        buy_qty  = sum(int(l.get("qty", 1)) for l in buy_legs)
        if sell_qty == 0:
            continue

        if buy_qty >= sell_qty:
            if sell_legs and buy_legs:
                spread = abs(sell_legs[0]["strike"] - buy_legs[0]["strike"])
                total += spread * min(sell_qty, buy_qty) * 100
            excess = buy_qty - sell_qty
            if excess > 0 and buy_legs:
                avg_prem = (sum(float(l.get("prem",0) or 0) * int(l.get("qty",1))
                                for l in buy_legs) / buy_qty)
                total += avg_prem * excess * 100
        else:
            if buy_legs and sell_legs:
                spread = abs(sell_legs[0]["strike"] - buy_legs[0]["strike"])
                total += spread * buy_qty * 100
            if sell_legs:
                total += sell_legs[0]["strike"] * 0.20 * (sell_qty - buy_qty) * 100

    return total
