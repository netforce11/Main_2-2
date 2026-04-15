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
    # 예: '[0DTE] 오늘 04/15(Wed)', '오늘 12/31(Fri)'
    _dte_match = re.search(r"(\d{1,2})/(\d{1,2})", display)
    if _dte_match and ("오늘" in display or "0DTE" in display or "DTE" in display):
        today = date.today()
        try:
            mm = int(_dte_match.group(1))
            dd = int(_dte_match.group(2))
            # 오늘 날짜와 비교해서 올해/내년 결정
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
    N-레그 전략 증거금 추정 (v2.7 버그픽스).

    수정:
      - qty 파싱을 _safe_qty()로 일원화 (문자열/None/빈값 안전 처리)
      - 백 스프레드에서 qty 오인식으로 네이키드 분기 잘못 진입하던 문제 수정
      - 스프레드 계산 시 SELL/BUY 행사가 차이를 절댓값으로 안전 계산

    알고리즘:
      1. 레그를 콜/풋으로 분류 후 각각 qty-가중 페어링
      2. BUY qty ≥ SELL qty → 스프레드 증거금
         (행사가 차이 × min(buy_qty, sell_qty) × 100)
      3. 초과 BUY (백 스프레드) → 프리미엄 기반 추가 증거금
      4. BUY qty < SELL qty → 커버 분 스프레드 + 네이키드 분 20%
    """
    def _safe_qty(leg):
        """qty 필드를 안전하게 int로 변환. 실패 시 1 반환."""
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
        sell_qty = sum(_safe_qty(l) for l in sell_legs)
        buy_qty  = sum(_safe_qty(l) for l in buy_legs)

        if sell_qty == 0:
            # 매도 없음 → 순수 매수 포지션, 프리미엄 비용만
            for l in buy_legs:
                total += _safe_prem(l) * _safe_qty(l) * 100
            continue

        if buy_qty >= sell_qty:
            # ── 스프레드 / 백 스프레드 ─────────────────────────
            # 매도 스트라이크 기준으로 가장 가까운 매수 스트라이크 찾기
            sell_strike = sell_legs[0]["strike"]
            buy_strike  = buy_legs[0]["strike"] if buy_legs else sell_strike
            spread      = abs(sell_strike - buy_strike)
            covered_qty = min(sell_qty, buy_qty)
            total      += spread * covered_qty * 100

            # 초과 매수분 (백 스프레드의 추가 BUY 계약)
            excess = buy_qty - sell_qty
            if excess > 0 and buy_legs:
                total_buy_prem = sum(
                    _safe_prem(l) * _safe_qty(l) for l in buy_legs)
                avg_prem = total_buy_prem / buy_qty if buy_qty else 0.0
                total   += avg_prem * excess * 100

        else:
            # ── 레이쇼 / 네이키드 포함 ──────────────────────────
            sell_strike  = sell_legs[0]["strike"]
            buy_strike   = buy_legs[0]["strike"] if buy_legs else sell_strike
            spread       = abs(sell_strike - buy_strike)
            total       += spread * buy_qty * 100

            naked_qty    = sell_qty - buy_qty
            naked_strike = max(float(l["strike"]) for l in sell_legs)
            total       += naked_strike * 0.20 * naked_qty * 100

    return total