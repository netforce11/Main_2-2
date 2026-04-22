# spread_config.py
# 0DTE 스프레드 텔레그램 조회 — 설정 상수
# -------------------------------------------------------

# /ES → SPX basis 보정 (장외 선물 사용 시 차감값, pt)
ES_BASIS_OFFSET: float = 5.0

# SPX 행사가 간격 (pt)
SPREAD_STEP: int = 5

# 콜 스프레드 범위 (기준가 대비 +%)
CALL_RANGE_PCT: float = 0.008   # +0.8%

# 풋 스프레드 범위 (기준가 대비 -%)
PUT_RANGE_PCT: float = 0.008    # -0.8%

# 텔레그램 ConversationHandler 상태값
STATE_TYPE   = 0    # 콜/풋 선택
STATE_EXPIRY = 1    # 만기 선택 (오늘/내일)

# 메뉴 콜백 데이터
CB_CALL      = "spread_call"
CB_PUT       = "spread_put"
CB_TODAY     = "expiry_today"
CB_TOMORROW  = "expiry_tomorrow"
CB_CANCEL    = "spread_cancel"