"""
core_expiry_utils.py — 만기일 판별 유틸  v1.0
════════════════════════════════════════════════════════
다른 call_put_tab 모듈에 의존하지 않는 순수 함수만 포함.
core_conn_spxw / core_conn_expiry 양쪽에서 import 해도
순환 의존성이 발생하지 않는다.

제공 함수:
  _is_monthly_expiry(dt) → bool
      매월 세 번째 금요일(SPX 월물 만기일) 여부 판별.
════════════════════════════════════════════════════════
"""

from datetime import datetime, date


def _is_monthly_expiry(dt) -> bool:
    """
    해당 날짜가 SPX 월물 만기일(매월 세 번째 금요일)인지 확인.

    IBKR은 세 번째 금요일에 SPXW(주간물) 계약을 발행하지 않으며,
    해당 날짜는 SPX(월물) 티커로만 체인이 존재한다.

    Args:
        dt: datetime.date, datetime.datetime, 또는 "YYYYMMDD" 문자열
    Returns:
        True  = Monthly 만기 → edit_sym = "SPX" 로 조회해야 함
        False = 일반 Weekly  → edit_sym = "SPXW" 로 조회
    """
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, "%Y%m%d").date()
        except Exception:
            return False
    if hasattr(dt, 'date'):          # datetime → date
        dt = dt.date()
    if dt.weekday() != 4:            # 금요일(4)이 아니면 무조건 False
        return False
    # 해당 월 첫 번째 금요일 계산
    first_day = dt.replace(day=1)
    first_fri_offset = (4 - first_day.weekday()) % 7
    third_friday_day = 1 + first_fri_offset + 14   # 세 번째 금요일의 day
    return dt.day == third_friday_day
