"""
combo_order_utils.py — 주문 관련 파싱 유틸 · 증거금 추정
────────────────────────────────────────────────────────
포함:
  _parse_legs_from_table — tbl_legs → legs dict 리스트 (N-레그 지원)
  _parse_expiry_display  — MM/DD → YYYYMMDD 복원
  _calc_required_margin  — 전략 구조 기반 증거금 추정 (N-레그 확장)

v2.8 변경:
  _calc_required_margin:
    - ★ 데빗 스프레드 오계산 버그 수정
      · BUY qty >= SELL qty 이어도, 순수 데빗 스프레드(BUY 주도)는
        최대손실 = 낸 프리미엄 → 프리미엄 합계로 계산
      · 크레딧 스프레드(SELL 주도)만 행사가 차이 방식 유지
    - 전략 판별 로직 명확화:
        debit  → max_loss = buy_prem - sell_prem  (프리미엄 기준)
        credit → max_loss = strike_diff           (행사가 차이 기준)
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
            "qty":    int(float(qty)) if qty else 1,
            "expiry": raw_expiry,
        })
    return legs


def _parse_expiry_display(display: str) -> str:
    """
    다양한 만기 형식 → YYYYMMDD.
    지원:
      '[0DTE] 오늘 MM/DD(Wed)' 형식
      '오늘 MM/DD(...)' 형식
      MM/DD, YYYYMMDD, YYYY-MM-DD, YYYY/MM/DD
    지나간 날짜면 내년으로 자동 이월.
    """
    if not display or display in ("―", ""):
        return ""

    # ── '[0DTE] 오늘 MM/DD(...)' 또는 '오늘 MM/DD(...)' 형식 처리 ──
    _dte_match = re.search(r"(\d{1,2})/(\d{1,2})", display)
    if _dte_match and ("오늘" in display or "0DTE" in display or "DTE" in display):
        today = date.today()
        try:
            mm = int(_dte_match.group(1))
            dd = int(_dte_match.group(2))
            candidate = date(today.year, mm, dd)
            if candidate < today:
                candidate = date(today.year + 1, mm, dd)
            return candidate.strftime("%Y%m%d")
        except (ValueError, TypeError):
            pass

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
    N-레그 전략 증거금 추정 (v2.8 데빗 스프레드 버그픽스).

    ★ 핵심 수정:
      데빗 스프레드 = BUY 프리미엄 합계 - SELL 프리미엄 합계
        → 최대손실 = 낸 프리미엄 (증거금 기준)
      크레딧 스프레드 = SELL qty > BUY qty
        → 최대손실 = 행사가 차이 × 계약 수 × 100

    알고리즘:
      1. 레그를 콜/풋으로 분류
      2. [데빗] BUY 순매수(BUY prem > SELL prem 또는 BUY qty > SELL qty)
           → max_loss = (buy_prem_total - sell_prem_total) × 100
      3. [크레딧] SELL qty > BUY qty
           → 커버 분: 행사가 차이 × covered_qty × 100
             네이키드 분: strike × 0.20 × naked_qty × 100
      4. [백 스프레드] BUY qty > SELL qty
           → 크레딧 수취 분 스프레드 + 초과 BUY 프리미엄
    """
    def _safe_qty(leg):
        try:
            return max(1, int(str(leg.get("qty", 1)).strip() or "1"))
        except (ValueError, TypeError):
            return 1

    def _safe_prem(leg):
        try:
            return max(0.0, float(str(leg.get("prem", 0) or "0").strip() or "0"))
        except (ValueError, TypeError):
            return 0.0

    def _sort_by_strike(lst, reverse=False):
        return sorted(lst, key=lambda x: float(x["strike"]), reverse=reverse)

    calls_sell = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "C" and l["dir"].upper() == "SELL"])
    calls_buy  = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "C" and l["dir"].upper() == "BUY"])
    puts_sell  = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "P" and l["dir"].upper() == "SELL"],
        reverse=True)
    puts_buy   = _sort_by_strike(
        [l for l in legs if l["cp"].upper() == "P" and l["dir"].upper() == "BUY"],
        reverse=True)

    total = 0.0

    for sell_legs, buy_legs in [(calls_sell, calls_buy),
                                (puts_sell,  puts_buy)]:
        sell_qty  = sum(_safe_qty(l) for l in sell_legs)
        buy_qty   = sum(_safe_qty(l) for l in buy_legs)

        buy_prem_total  = sum(_safe_prem(l) * _safe_qty(l) for l in buy_legs)
        sell_prem_total = sum(_safe_prem(l) * _safe_qty(l) for l in sell_legs)

        if sell_qty == 0 and buy_qty == 0:
            continue

        if sell_qty == 0:
            # ── 순수 매수 포지션 → 프리미엄 비용만 ──────────────
            total += buy_prem_total * 100
            continue

        if buy_qty == 0:
            # ── 순수 매도 포지션 → 네이키드 증거금 ───────────────
            naked_strike = max(float(l["strike"]) for l in sell_legs)
            total += naked_strike * 0.20 * sell_qty * 100
            continue

        # ── 스프레드 판별: 데빗 vs 크레딧 ────────────────────────
        # 데빗: 낸 프리미엄(BUY) > 받은 프리미엄(SELL)
        # 크레딧: 받은 프리미엄(SELL) >= 낸 프리미엄(BUY)
        net_prem = buy_prem_total - sell_prem_total   # 양수 = 데빗, 음수 = 크레딧

        if buy_qty >= sell_qty:
            if net_prem > 0:
                # ★ 데빗 스프레드 / 데빗 백 스프레드
                #   최대손실 = 낸 프리미엄 합계 (크레딧 수취분 차감)
                covered_qty = min(buy_qty, sell_qty)
                # 행사가 차이 상한과 프리미엄 중 작은 값 (보수적 계산)
                if buy_legs and sell_legs:
                    sell_strike = sell_legs[0]["strike"]
                    buy_strike  = buy_legs[0]["strike"]
                    strike_diff = abs(sell_strike - buy_strike) * covered_qty * 100
                    prem_based  = net_prem * 100
                    # 데빗 스프레드: 최대손실은 낸 프리미엄 (행사가 차이보다 클 수 없음)
                    total += min(prem_based, strike_diff) if strike_diff > 0 else prem_based
                else:
                    total += net_prem * 100

                # 초과 BUY (백 스프레드 추가분)
                excess = buy_qty - sell_qty
                if excess > 0:
                    avg_buy_prem = buy_prem_total / buy_qty if buy_qty else 0.0
                    total += avg_buy_prem * excess * 100
            else:
                # 크레딧 수취 후 BUY qty >= SELL qty (크레딧 백 스프레드)
                sell_strike = sell_legs[0]["strike"]
                buy_strike  = buy_legs[0]["strike"] if buy_legs else sell_strike
                spread      = abs(sell_strike - buy_strike)
                covered_qty = min(sell_qty, buy_qty)
                total      += spread * covered_qty * 100

                excess = buy_qty - sell_qty
                if excess > 0:
                    avg_buy_prem = buy_prem_total / buy_qty if buy_qty else 0.0
                    total += avg_buy_prem * excess * 100

        else:
            # ── 크레딧 스프레드 / 레이쇼 / 네이키드 포함 ──────────
            sell_strike  = sell_legs[0]["strike"]
            buy_strike   = buy_legs[0]["strike"] if buy_legs else sell_strike
            spread       = abs(sell_strike - buy_strike)
            total       += spread * buy_qty * 100

            naked_qty    = sell_qty - buy_qty
            naked_strike = max(float(l["strike"]) for l in sell_legs)
            total       += naked_strike * 0.20 * naked_qty * 100

    return total
