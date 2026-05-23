"""combo_ui_panel_utils.py — 모듈 레벨 유틸리티 함수

포지션 테이블에서 사용하는 순수 계산·포매팅 함수 모음.
UI 의존성 없음 (PyQt5 임포트 불필요).

공개 함수:
    _calc_delta_pnl_pct(pos)  → (str, color_str)
    _enrich_strategy_name(pos) → str
    _format_expiry(legs)       → (str, color_str)
"""


def _calc_delta_pnl_pct(pos: dict) -> tuple:
    """
    [FIX-DELTA] 지수 5P 당 포지션 예상 손익률 계산.

    공식:
      포지션 델타 = Σ( leg_delta × leg_qty × 방향계수 )
                    (BUY: 부호 유지, SELL: 부호 반전)
      5P 손익($) = 포지션 델타 × 5 × 100          (SPX 승수 100)
      손익률(%)  = 5P 손익 / (entry × 100) × 100

    Args:
        pos: 포지션 딕셔너리. legs[i]['delta'] 필드 필요.
             delta 필드가 없거나 모두 0 이면 "―" 반환.

    Returns:
        (표시 문자열, 색상 hex)
        예: ("+95%", "#ffff44")  /  ("-45%", "#ff6666")  /  ("―", "#888899")
    """
    entry = float(pos.get("entry", 0) or 0)
    legs  = pos.get("legs", [])

    if not legs or entry <= 0:
        return ("―", "#888899")

    try:
        pos_delta = 0.0
        has_delta = False
        for leg in legs:
            raw = leg.get("delta")
            if raw is None:
                continue
            leg_delta = float(raw)
            leg_qty   = float(leg.get("qty", 1) or 1)
            leg_dir   = str(leg.get("dir", "BUY")).upper()
            if leg_dir == "SELL":
                leg_delta = -leg_delta
            pos_delta += leg_delta * leg_qty
            has_delta = True

        if not has_delta:
            return ("―", "#888899")

        five_p_pnl    = pos_delta * 5.0 * 100.0        # 달러
        debit_dollars = entry * 100.0                   # $1.05 → $105
        pnl_pct       = (five_p_pnl / debit_dollars) * 100.0

        if pnl_pct >= 0:
            txt = f"+{pnl_pct:.0f}%"
            col = "#ffff44"     # 형광 노랑
        else:
            txt = f"{pnl_pct:.0f}%"
            col = "#ff6666"     # 연한 빨강

        return (txt, col)

    except Exception:
        return ("―", "#888899")


def _enrich_strategy_name(pos: dict) -> str:
    """
    [FIX-M] legs 에서 행사가 추출해 전략명에 추가.
    예) "풋 스프레드 (풋매수+풋매도)" + legs[6700, 6705]
        → "풋 스프레드 6700/6705 (풋매수+풋매도)"
    이미 행사가가 포함된 경우 중복 추가 방지.
    """
    legs = pos.get("legs", [])
    if not legs:
        return pos.get("strategy", "")
    try:
        strikes = "/".join(
            str(int(float(l["strike"])))
            for l in sorted(legs, key=lambda l: l.get("dir", ""), reverse=True)
            if l.get("strike")
        )
        base = pos.get("strategy", "")
        if strikes and strikes not in base:
            if "(" in base:
                idx = base.index("(")
                return f"{base[:idx].rstrip()} {strikes} {base[idx:]}"
            return f"{base} {strikes}"
    except Exception:
        pass
    return pos.get("strategy", "")


def _format_expiry(legs: list) -> tuple:
    """
    [FIX-N] legs 에서 만기일 추출 후 포맷.
    ET 기준으로 남은 일수 계산 후 색상과 함께 반환.

    반환: (표시 텍스트, 색상) 튜플

    예시:
      - expiry = "20260509" (내일)    → ("1일",  "#ffaa44")
      - expiry = "20260510" (3일 후)  → ("3일",  "#aabbff")
      - expiry = "20260601" (1개월 후)→ ("52일", "#88dd55")
      - 만기 지난 경우                → ("만료", "#888888")
    """
    if not legs:
        return ("―", "#888899")

    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        expiry_str = str(legs[0].get("expiry", "")).strip()
        if not expiry_str or len(expiry_str) != 8:
            return ("―", "#888899")

        try:
            exp_year  = int(expiry_str[:4])
            exp_month = int(expiry_str[4:6])
            exp_day   = int(expiry_str[6:8])
            exp_date  = datetime(
                exp_year, exp_month, exp_day, 16, 0, 0,
                tzinfo=ZoneInfo("America/New_York"),
            ).date()
        except (ValueError, TypeError):
            return ("―", "#888899")

        now_et = datetime.now(ZoneInfo("America/New_York")).date()

        if exp_date < now_et:
            return ("만료", "#888888")
        elif exp_date == now_et:
            return ("0일", "#ff6666")
        else:
            delta = (exp_date - now_et).days
            if delta == 1:
                color = "#ffaa44"
            elif delta <= 7:
                color = "#ff9999"
            elif delta <= 14:
                color = "#ffdd88"
            elif delta <= 30:
                color = "#aabbff"
            else:
                color = "#88dd55"
            return (f"{delta}일", color)

    except Exception:
        return ("―", "#888899")
