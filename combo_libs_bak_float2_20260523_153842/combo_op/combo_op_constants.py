"""
combo_op_constants.py — Optimizer 전략 상수 + POP 계산
────────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_constants.py
포함:
  _STRAT_LEGS, _CALL_SPREAD_TYPES, _PUT_SPREAD_TYPES,
  _BEAR_CALL_TYPES, _BULL_PUT_TYPES
  _strat_key()
  _norm_cdf() / _calc_pop()
────────────────────────────────────────────────────────
"""

import math

# ── 전략별 레그 방향 정의 ──────────────────────────────────────
# 주의: _strat_key()가 콤보박스 텍스트에 key가 포함되는지 in으로 검색하므로
# 짧은 키가 긴 키의 부분 문자열이 되는 경우 긴 키(신규)를 반드시 먼저 배치해야 함.
# 예: "콜 스프레드" ⊂ "숏 콜 스프레드 / 베어 콜 스프레드" → 신규 전략 먼저!
_STRAT_LEGS = {
    # ── 신규 (v2.3) — 반드시 "콜 스프레드"/"풋 스프레드" 보다 앞에 위치 ──
    "숏 콜 스프레드":    [("C", "SELL"), ("C", "BUY")],   # 베어 콜 스프레드
    "베어 콜 스프레드":  [("C", "SELL"), ("C", "BUY")],
    "불 풋 스프레드":    [("P", "SELL"), ("P", "BUY")],
    # ── 기존 전략 ─────────────────────────────────────────────
    "콜 데빗 스프레드":   [("C", "BUY"),  ("C", "SELL")],
    "풋 데빗 스프레드":   [("P", "BUY"),  ("P", "SELL")],
    "콜 스프레드":        [("C", "BUY"),  ("C", "SELL")],
    "풋 스프레드":        [("P", "BUY"),  ("P", "SELL")],
    # [FIX-B11] 스트래들 vs 스트랭글 레그 방향은 동일(둘 다 BUY+BUY).
    # 차이점: 스트래들 = 동일 행사가, 스트랭글 = 다른 행사가.
    # 행사가 선택 로직은 _search_straddle / _search_strangle 에서 분기 처리.
    "스트래들":           [("C", "BUY"),  ("P", "BUY")],  # 동일 행사가 C+P 매수
    "스트랭글":           [("C", "BUY"),  ("P", "BUY")],  # 다른 행사가 C+P 매수
    "아이언 콘도르":      [("P", "BUY"),  ("P", "SELL"),
                           ("C", "SELL"), ("C", "BUY")],
}

_CALL_SPREAD_TYPES = {"콜 스프레드", "콜 데빗 스프레드"}
_PUT_SPREAD_TYPES  = {"풋 스프레드", "풋 데빗 스프레드"}
_BEAR_CALL_TYPES   = {"숏 콜 스프레드", "베어 콜 스프레드"}
_BULL_PUT_TYPES    = {"불 풋 스프레드"}

# [FIX-B12] 콜 계열 전략을 하나의 집합으로 통합 제공
# combo_op_search.py 에서 CALL 기반 로직 분기 시 이 집합을 사용하면
# "숏 콜 스프레드" 계열이 _CALL_SPREAD_TYPES 에 없어 누락되는 문제 방지
ALL_CALL_TYPES = _CALL_SPREAD_TYPES | _BEAR_CALL_TYPES
ALL_PUT_TYPES  = _PUT_SPREAD_TYPES  | _BULL_PUT_TYPES


def _strat_key(strat_text: str) -> str:
    """
    전략 콤보박스 텍스트 → _STRAT_LEGS 키 반환.
    긴 키가 짧은 키의 부분 문자열이 될 수 있으므로
    키 길이 내림차순 정렬 후 매칭 (더 구체적인 키 우선).
    _STRAT_LEGS 딕셔너리 삽입 순서로도 보장되지만 안전망으로 추가.
    """
    for key in sorted(_STRAT_LEGS.keys(), key=len, reverse=True):
        if key in strat_text:
            return key
    return ""


# ── POP 계산 (Black-Scholes N(d2), scipy 불필요) ──────────────

def _norm_cdf(x: float) -> float:
    """표준 정규 누적분포 — math.erf 이용."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _calc_pop(S: float, K: float, T_days: float,
              iv_pct: float, cp: str = "C") -> float:
    """
    만기 시 해당 레그가 OTM(수익)으로 끝날 확률 (%).
    콜 매도 POP = 1 - N(d2)
    풋 매도 POP = N(-d2) = 1 - N(d2) 로 근사
    """
    T     = T_days / 365.0
    sigma = iv_pct  / 100.0
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d2 = (math.log(S / K) + (-0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    except (ValueError, ZeroDivisionError):
        return 0.0
    if cp.upper() == "C":
        return (1.0 - _norm_cdf(d2)) * 100.0   # 콜이 OTM으로 끝날 확률
    else:
        return _norm_cdf(d2) * 100.0            # 풋이 OTM으로 끝날 확률