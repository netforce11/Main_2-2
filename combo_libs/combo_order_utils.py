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

v2.9 버그픽스:
  _parse_expiry_display:
    - ★ [BUG-2] MM/DD 일반 분기 이월 로직 제거
      · 이전: candidate < today → +1년 (어제 만기 "04/21" → "20270421")
      · 수정: 이월 없이 현재 연도 그대로 반환
      · 0DTE/오늘 키워드 포함 분기에서만 이월 유지
    - ★ [BUG-5] digits 8자리 유효성 검증 추가
      · "04/21/2026" → digits="04212026" → month=42 오류 방지
      · date() 생성 실패 시 하위 분기로 낙하
    - ★ [BUG-6] 3-part 파싱 형식 판별 로직 수정
      · 이전: y>1000이면 Y/M/D, 아니면 D/Y/M (MM/DD/YYYY 미지원)
      · 수정: parts[2]>1000이면 MM/DD/YYYY, parts[0]>1000이면 YYYY/MM/DD
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
      YYYYMMDD (8자리 숫자)
      YYYY-MM-DD, YYYY/MM/DD  (연도 우선 3-part)
      MM/DD/YYYY              (미국식 3-part)
      MM/DD                   (연도 생략, 현재 연도 사용 — 이월 없음)
      '[0DTE] 오늘 MM/DD(...)' 또는 '오늘 MM/DD(...)' 형식
        → 지나간 날짜면 내년으로 자동 이월 (0DTE/오늘 전용)
    """
    if not display or display in ("―", ""):
        return ""

    # ── '[0DTE] 오늘 MM/DD(...)' 또는 '오늘 MM/DD(...)' 형식 ──────────
    # 이 분기만 이월 로직 적용 (당일 만기 자동 롤 전용)
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

    # ── ★ [BUG-5] YYYYMMDD 8자리: date() 유효성 검증 후 반환 ──────────
    digits = "".join(c for c in display if c.isdigit())
    if len(digits) == 8:
        try:
            y, m, d = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
            return date(y, m, d).strftime("%Y%m%d")  # 유효하지 않으면 ValueError → 낙하
        except (ValueError, TypeError):
            pass  # 잘못된 날짜(예: month=42)면 하위 분기로 진행

    # ── 3-part / 2-part 파싱 ─────────────────────────────────────────
    parts = re.split(r"[/\-\.]", display.strip())
    today = date.today()
    try:
        if len(parts) == 3:
            a, b, c = int(parts[0]), int(parts[1]), int(parts[2])
            # ★ [BUG-6] 연도(>1000) 위치로 형식 판별
            if a > 1000:
                # YYYY/MM/DD 또는 YYYY-MM-DD
                return date(a, b, c).strftime("%Y%m%d")
            elif c > 1000:
                # MM/DD/YYYY (미국식)
                return date(c, a, b).strftime("%Y%m%d")
            # 연도 없는 3-part는 파싱 포기
            return ""

        if len(parts) == 2:
            mm, dd = int(parts[0]), int(parts[1])
            # ★ [BUG-2] 이월 로직 제거 — 현재 연도 그대로 사용
            # 이월이 필요한 케이스는 위의 0DTE/오늘 분기에서만 처리
            return date(today.year, mm, dd).strftime("%Y%m%d")

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
            # ── 백 스프레드 판별: BUY qty > SELL qty ──────────────
            is_back_spread = (buy_qty > sell_qty)

            if is_back_spread:
                # ★ 백 스프레드 증거금 (v2.9 수정)
                #   실제 최대손실 = (행사가 차이) × SELL qty × 100 - 수취 크레딧
                #   초과 BUY는 헤지 역할 → 증거금에 더하지 않음 (기존 과대계산 수정)
                if buy_legs and sell_legs:
                    sell_strike  = sell_legs[0]["strike"]
                    buy_strike   = buy_legs[0]["strike"]
                    strike_diff  = abs(sell_strike - buy_strike) * sell_qty * 100
                    # 크레딧 수취분만큼 최대손실 감소
                    credit_received = sell_prem_total * 100
                    max_loss_est = max(strike_diff - credit_received, 0.0)
                    total += max_loss_est
                else:
                    total += abs(net_prem) * 100

            elif net_prem > 0:
                # ★ 일반 데빗 스프레드 (BUY qty == SELL qty, 데빗)
                #   최대손실 = 낸 프리미엄 (행사가 차이 상한)
                covered_qty = sell_qty
                if buy_legs and sell_legs:
                    sell_strike = sell_legs[0]["strike"]
                    buy_strike  = buy_legs[0]["strike"]
                    strike_diff = abs(sell_strike - buy_strike) * covered_qty * 100
                    prem_based  = net_prem * 100
                    total += min(prem_based, strike_diff) if strike_diff > 0 else prem_based
                else:
                    total += net_prem * 100

            else:
                # 크레딧 수취 동수 스프레드 (BUY qty == SELL qty, 크레딧)
                sell_strike = sell_legs[0]["strike"]
                buy_strike  = buy_legs[0]["strike"] if buy_legs else sell_strike
                spread      = abs(sell_strike - buy_strike)
                total      += spread * sell_qty * 100

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