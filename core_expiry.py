"""
core_expiry.py — 미국 주식시장 휴장일 / 만기일 유틸
core.py 300줄 초과로 분리.

【수정 2026-05】
- _third_friday()        : 헬퍼 — 해당 년월의 세 번째 금요일 반환
- _monthly_expiry_dates(): 헬퍼 — 이번달/다음달 월물 날짜 집합
- build_expiry_list()    : 버그 3건 수정
    ① W 목록에 월간만기가 포함되면 M 항목이 스킵되던 문제
       → 중복 날짜는 skip 대신 기존 항목 태그/레이블을 M으로 교체
    ② 위클리 금요일이 월간만기임에도 [W] 배지로 표시되던 문제
       → monthly_dates 집합으로 판별 후 [월간] / [W] 배지 분리
    ③ (SPX) 0DTE 날짜가 월간만기일 때도 [0DTE]로만 표시되던 문제
       → [0DTE 월간] 배지 추가
"""
import os, json, csv
from datetime import datetime, timedelta, time as dt_time, date as dt_date
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

def _easter(year: int) -> datetime:
    """서양 부활절 날짜 계산 (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100; c = year % 100
    d = b // 4;      e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i = c // 4;      k = c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day   = ((h + l - 7*m + 114) % 31) + 1
    return datetime(year, month, day)

def _us_market_holidays(year: int) -> set:
    """미국 주식시장 연간 휴장일 집합 (date 객체)."""
    hols = set()
    # 성금요일 (부활절 -2일)
    hols.add((_easter(year) - timedelta(days=2)).date())
    # 신정
    ny = dt_date(year, 1, 1)
    if ny.weekday() == 5: ny = dt_date(year, 12, 31)
    elif ny.weekday() == 6: ny = dt_date(year, 1, 2)
    hols.add(ny)
    # MLK Day: 1월 세 번째 월요일
    d = dt_date(year, 1, 1); cnt = 0
    while True:
        if d.weekday() == 0: cnt += 1
        if cnt == 3: hols.add(d); break
        d += timedelta(days=1)
    # Presidents Day: 2월 세 번째 월요일
    d = dt_date(year, 2, 1); cnt = 0
    while True:
        if d.weekday() == 0: cnt += 1
        if cnt == 3: hols.add(d); break
        d += timedelta(days=1)
    # Memorial Day: 5월 마지막 월요일
    d = dt_date(year, 5, 31)
    while d.weekday() != 0: d -= timedelta(days=1)
    hols.add(d)
    # Juneteenth: 6월 19일
    jt = dt_date(year, 6, 19)
    if jt.weekday() == 5: jt = dt_date(year, 6, 18)
    elif jt.weekday() == 6: jt = dt_date(year, 6, 20)
    hols.add(jt)
    # Independence Day: 7월 4일
    id_ = dt_date(year, 7, 4)
    if id_.weekday() == 5: id_ = dt_date(year, 7, 3)
    elif id_.weekday() == 6: id_ = dt_date(year, 7, 5)
    hols.add(id_)
    # Labor Day: 9월 첫 번째 월요일
    d = dt_date(year, 9, 1)
    while d.weekday() != 0: d += timedelta(days=1)
    hols.add(d)
    # Thanksgiving: 11월 네 번째 목요일
    d = dt_date(year, 11, 1); cnt = 0
    while True:
        if d.weekday() == 3: cnt += 1
        if cnt == 4: hols.add(d); break
        d += timedelta(days=1)
    # Christmas: 12월 25일
    xm = dt_date(year, 12, 25)
    if xm.weekday() == 5: xm = dt_date(year, 12, 24)
    elif xm.weekday() == 6: xm = dt_date(year, 12, 26)
    hols.add(xm)
    return hols

_HOLIDAY_CACHE: dict = {}

def is_trading_day(d) -> bool:
    """d (datetime 또는 date)가 미국 주식시장 거래일인지 반환."""
    if isinstance(d, datetime): d = d.date()
    if d.weekday() >= 5: return False
    year = d.year
    if year not in _HOLIDAY_CACHE:
        _HOLIDAY_CACHE[year] = _us_market_holidays(year)
    return d not in _HOLIDAY_CACHE[year]

def next_wd(base: datetime, wd: int) -> datetime:
    """base 이후 첫 번째 wd 요일 (당일 제외, 0=월~4=금)."""
    days = (wd - base.weekday()) % 7 or 7
    return base + timedelta(days=days)

def next_trading_friday(base: datetime, skip: int = 0) -> datetime:
    """base 이후 skip번째 거래 금요일 (성금요일 등 휴장일 자동 스킵)."""
    fri = next_wd(base, 4)
    found = 0
    while True:
        if is_trading_day(fri):
            if found == skip:
                return fri
            found += 1
        fri += timedelta(weeks=1)


# ──────────────────────────────────────────────────────────────
# 【신규 헬퍼】월간만기 판별용
# ──────────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> dt_date:
    """
    해당 년월의 세 번째 금요일(월간 옵션 만기 기준일) 반환.
    성금요일 등 휴장일이면 다음 거래일로 밀기.
    """
    d = dt_date(year, month, 1)
    fris = []
    while d.month == month:
        if d.weekday() == 4:
            fris.append(d)
        d += timedelta(days=1)
    mf = fris[2]
    # 휴장일이면 다음 거래일로 밀기
    while not is_trading_day(mf):
        mf += timedelta(days=1)
    return mf


def _monthly_expiry_dates(today: datetime) -> set:
    """
    이번달/다음달 월물 날짜 집합 (dt_date 객체).
    build_expiry_list() 내부에서 W 금요일이 월간만기인지 판별할 때 사용.
    """
    result = set()
    for month_offset in range(2):
        if month_offset == 0:
            ref = today
        else:
            if today.month == 12:
                ref = today.replace(year=today.year + 1, month=1, day=1)
            else:
                ref = today.replace(month=today.month + 1, day=1)
        result.add(_third_friday(ref.year, ref.month))
    return result


# ──────────────────────────────────────────────────────────────

def build_expiry_list(sym: str = "SPX"):
    """
    콤보박스용 만기일 목록 → [(label, YYYYMMDD, tag), ...]

    tag 값:
        "0DTE"   — SPX 당일 만기 (수/금)
        "0DTE-M" — SPX 당일 만기이면서 월간만기
        "W"      — 위클리 금요일
        "M"      — 월간만기 (세 번째 금요일)
        ""       — 직접 입력(CUSTOM)

    SPX/SPXW/NDX/RUT/VIX/XSP :
        0DTE(오늘이 수·금) + 위클리 금요일 3개 + 이번달/다음달 월물

        ★ SPX는 월/수/금 만기이지만 0DTE 표시는 수·금만.
          목요일(SPXW 0DTE)은 combo_spxw 에서 자동 선택.

    주식/ETF (NVDA·AAPL 등) :
        ① 이번주 금요일  (오늘이 토·일이면 다음주 금요일부터)
        ② 다음주 금요일
        ③ 이번달 월물 (세 번째 금요일)
        ④ 다음달 월물
        ⑤ 직접 입력

    ★ 금요일 전용 이유: 주식 주간 옵션은 매주 금요일만 만기 존재.
       월~목 만기를 넣으면 IBKR ERR 200 (No security definition).

    【수정】 W 목록에 포함된 날짜가 월간만기이면:
        - skip 하지 않고 해당 항목의 태그/레이블을 M으로 교체
        - 배지: [W] → [월간]
    """
    sym_up = sym.upper().replace("SPXW", "SPX")
    today  = datetime.today()
    entries = []

    is_spx = sym_up in ("SPX", "NDX", "RUT", "VIX", "XSP")

    # 【수정】월간만기 날짜 집합 — W 항목 생성 시 태그 결정에 사용
    monthly_dates = _monthly_expiry_dates(today)

    if is_spx:
        # ── SPX 계열 ───────────────────────────────────────────
        if today.weekday() in (2, 4) and is_trading_day(today):
            date_str   = today.strftime("%Y%m%d")
            # 【수정】0DTE 날짜가 월간만기이면 배지/태그 구분
            is_monthly = today.date() in monthly_dates
            tag        = "0DTE-M" if is_monthly else "0DTE"
            badge      = "[0DTE 월간]" if is_monthly else "[0DTE]"
            entries.append((
                f"{badge} 오늘 {today.strftime('%m/%d(%a)')}",
                date_str, tag))

        for n in range(3):
            fri      = next_trading_friday(today, skip=n)
            date_str = fri.strftime("%Y%m%d")
            if any(e[1] == date_str for e in entries):
                continue
            # 【수정】월간만기 여부에 따라 배지/태그 분리
            is_monthly = fri.date() in monthly_dates
            tag        = "M" if is_monthly else "W"
            badge      = "[월간]" if is_monthly else "[W]"
            entries.append((
                f"{badge} {fri.strftime('%m/%d(%a)')}",
                date_str, tag))

    else:
        # ── 주식/ETF: 금요일만 생성 ───────────────────────────
        if today.weekday() == 5:       # 토요일
            base = today + timedelta(days=2)
        elif today.weekday() == 6:     # 일요일
            base = today + timedelta(days=1)
        else:
            base = today

        days_to_fri = (4 - base.weekday()) % 7
        this_fri    = base + timedelta(days=days_to_fri)

        candidates = []
        for week_offset in range(4):
            fri = this_fri + timedelta(weeks=week_offset)
            if fri.date() >= base.date() and is_trading_day(fri):
                # 【수정】월간만기 여부에 따라 배지/태그 분리
                is_monthly = fri.date() in monthly_dates
                tag        = "M" if is_monthly else "W"
                badge      = "[월간]" if is_monthly else "[W]"
                label_prefix = ("오늘 " if fri.date() == today.date() else
                                "내일 " if fri.date() == (today + timedelta(days=1)).date() else
                                "다음주 " if week_offset == 1 else "")
                candidates.append((
                    f"{badge} {label_prefix}{fri.strftime('%m/%d(%a)')}",
                    fri.strftime("%Y%m%d"), tag))
            if len(candidates) >= 2:
                break

        entries.extend(candidates)

    # ── 공통: 이번달/다음달 월물 (세 번째 금요일) ────────────
    # 【수정】중복 날짜는 skip 대신 기존 항목의 태그/레이블을 M으로 교체
    for month_offset in range(2):
        if month_offset == 0:
            ref = today
        else:
            if today.month == 12:
                ref = today.replace(year=today.year + 1, month=1, day=1)
            else:
                ref = today.replace(month=today.month + 1, day=1)

        mf = _third_friday(ref.year, ref.month)
        ms = mf.strftime("%Y%m%d")

        label_tmpl = "[M] 월물 %s" if month_offset == 0 else "[M] 다음달 %s"
        new_label  = label_tmpl % mf.strftime("%m/%d(%a)")

        # 이미 같은 날짜가 entries에 있으면 태그/레이블 교체 (W → M)
        # 단, 0DTE-M(당일 월간만기)은 레이블 유지하고 태그만 M으로 통일
        existing = [(i, e) for i, e in enumerate(entries) if e[1] == ms]
        if existing:
            idx, old_entry = existing[0]
            if old_entry[2] == "0DTE-M":
                # 0DTE 배지는 유지, 태그만 M으로 통일
                entries[idx] = (old_entry[0], ms, "M")
            else:
                entries[idx] = (new_label, ms, "M")
        else:
            entries.append((new_label, ms, "M"))

    entries.append(("직접 입력 YYYYMMDD", "CUSTOM", ""))
    return entries