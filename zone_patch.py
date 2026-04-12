"""
zone_patch.py — _strikes_for_zone 패치 (S10)
=============================================
기존 ITM / ATM / OTM (3구간) → OTM2 / OTM1 / ATM / ITM1 / ITM2 (5구간)

[구간 정의]
  ATM  : ATM 중심 ±n/2 행  (n = spin_n 값)
  OTM1 : ATM 바로 위 n/2 행  (Call 기준 높은 행사가)
  OTM2 : OTM1 위  n/2 행  (더 깊은 외가)
  ITM1 : ATM 바로 아래 n/2 행
  ITM2 : ITM1 아래 n/2 행  (더 깊은 내가)

[적용 방법]
  core_fetch.py의 CoreFetchMixin 안에 있는 _strikes_for_zone() 메서드를
  아래 코드로 교체하세요.
  기존 ITM/OTM 키도 하위 호환으로 유지됩니다.
"""


def _strikes_for_zone(self, atm: float, step: float, n: int):
    """
    zone별 콜/풋 행사가 리스트를 반환.
    반환: (call_strikes, put_strikes) — 각각 list[float]

    Zone 키:
      "ATM"  — ATM 중심 ±(n//2) 행 (기존 동작 유지)
      "OTM1" — Call: ATM+step ~ ATM+n*step  (외가 1단계, n행)
               Put:  ATM-step ~ ATM-n*step
      "OTM2" — Call: ATM+(n+1)*step ~ ATM+2n*step (외가 심층, n행)
               Put:  ATM-(n+1)*step ~ ATM-2n*step
      "ITM1" — Call: ATM-step ~ ATM-n*step  (내가 1단계, n행)
               Put:  ATM+step ~ ATM+n*step
      "ITM2" — Call: ATM-(n+1)*step ~ ATM-2n*step (내가 심층, n행)
               Put:  ATM+(n+1)*step ~ ATM+2n*step

      "ITM"  — 하위 호환: ITM1 동작
      "OTM"  — 하위 호환: OTM1 동작
    """
    zone = getattr(self, '_zone', 'ATM')

    half = max(n // 2, 1)

    if zone == "ATM":
        # ATM 중심 ±half 행 (CALL/PUT 동일)
        call_st = [atm + i * step for i in range(-half, half + 1)]
        put_st  = call_st[:]

    elif zone in ("OTM1", "OTM"):
        # CALL 외가: ATM+step ~ ATM+n*step
        # PUT  외가: ATM-step ~ ATM-n*step (내림차순)
        call_st = [atm + (i + 1) * step for i in range(n)]
        put_st  = [atm - (i + 1) * step for i in range(n)]

    elif zone == "OTM2":
        # 더 깊은 외가: OTM1 끝 다음부터 n행
        call_st = [atm + (n + i + 1) * step for i in range(n)]
        put_st  = [atm - (n + i + 1) * step for i in range(n)]

    elif zone in ("ITM1", "ITM"):
        # CALL 내가: ATM-step ~ ATM-n*step
        # PUT  내가: ATM+step ~ ATM+n*step
        call_st = [atm - (i + 1) * step for i in range(n)]
        put_st  = [atm + (i + 1) * step for i in range(n)]

    elif zone == "ITM2":
        # 더 깊은 내가: ITM1 끝 다음부터 n행
        call_st = [atm - (n + i + 1) * step for i in range(n)]
        put_st  = [atm + (n + i + 1) * step for i in range(n)]

    else:
        # 알 수 없는 zone → ATM 폴백
        call_st = [atm + i * step for i in range(-half, half + 1)]
        put_st  = call_st[:]

    # 음수 행사가 제거 + 정수 반올림
    call_st = [round(s) for s in call_st if s > 0]
    put_st  = [round(s) for s in put_st  if s > 0]

    return call_st[:n], put_st[:n]
