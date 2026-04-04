"""
core_expiry.py — 미국 주식시장 휴장일 / 만기일 유틸
core.py 300줄 초과로 분리.
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


def build_expiry_list(sym: str = "SPX"):
    """
    콤보박스용 만기일 목록 → [(label, YYYYMMDD, tag), ...]

    SPX/SPXW/NDX/RUT/VIX/XSP :
        0DTE(오늘이 수·금) + 위클리 금요일 3개 + 이번달/다음달 월물

    주식/ETF (NVDA·AAPL 등) :
        ① 이번주 금요일  (오늘이 토·일이면 다음주 금요일부터)
        ② 다음주 금요일
        ③ 이번달 월물 (세 번째 금요일)
        ④ 다음달 월물
        ⑤ 직접 입력

    ★ 금요일 전용 이유: 주식 주간 옵션은 매주 금요일만 만기 존재.
       월~목 만기를 넣으면 IBKR ERR 200 (No security definition).
    """
    sym_up = sym.upper().replace("SPXW", "SPX")
    today = datetime.today()
    entries = []

    is_spx = sym_up in ("SPX", "NDX", "RUT", "VIX", "XSP")

    if is_spx:
        # ── SPX 계열: 기존 로직 그대로 ───────────────────────
        if today.weekday() in (2, 4) and is_trading_day(today):
            entries.append((
                "[0DTE] 오늘 %s" % today.strftime("%m/%d(%a)"),
                today.strftime("%Y%m%d"), "0DTE"))

        for n in range(3):
            fri = next_trading_friday(today, skip=n)
            if not any(e[1] == fri.strftime("%Y%m%d") for e in entries):
                entries.append((
                    "[W] %s" % fri.strftime("%m/%d(%a)"),
                    fri.strftime("%Y%m%d"), "W"))

    else:
        # ── 주식/ETF: 금요일만 생성 ───────────────────────────
        # 주말이면 기준일을 다음 월요일로 보정 (이번주 금요일은 이미 지남)
        if today.weekday() == 5:  # 토요일
            base = today + timedelta(days=2)  # 다음 월요일
        elif today.weekday() == 6:  # 일요일
            base = today + timedelta(days=1)  # 다음 월요일
        else:
            base = today

        # 이번주 금요일 (base 기준, 당일 포함)
        days_to_fri = (4 - base.weekday()) % 7
        this_fri = base + timedelta(days=days_to_fri)

        # 오늘(base)이 금요일 당일이면 이번주 포함, 지났으면 다음주부터
        candidates = []
        for week_offset in range(4):  # 4주치 생성 후 유효한 2개 취득
            fri = this_fri + timedelta(weeks=week_offset)
            if fri.date() >= base.date() and is_trading_day(fri):
                label_prefix = ("오늘 " if fri.date() == today.date() else
                                "내일 " if fri.date() == (today + timedelta(days=1)).date() else
                                "다음주 " if week_offset == 1 else "")
                candidates.append((
                    f"[W] {label_prefix}{fri.strftime('%m/%d(%a)')}",
                    fri.strftime("%Y%m%d"), "W"))
            if len(candidates) >= 2:
                break

        entries.extend(candidates)

    # ── 공통: 이번달/다음달 월물 (세 번째 금요일) ────────────
    for month_offset in range(2):
        if month_offset == 0:
            ref = today
        else:
            if today.month == 12:
                ref = today.replace(year=today.year + 1, month=1, day=1)
            else:
                ref = today.replace(month=today.month + 1, day=1)

        d = ref.replace(day=1)
        fris = []
        while d.month == ref.month:
            if d.weekday() == 4:
                fris.append(d)
            d += timedelta(days=1)

        if len(fris) >= 3:
            mf = fris[2]
            if not is_trading_day(mf):
                mf += timedelta(days=1)
                while not is_trading_day(mf):
                    mf += timedelta(days=1)
            ms = mf.strftime("%Y%m%d")
            if not any(e[1] == ms for e in entries):
                label = ("[M] 월물 %s" if month_offset == 0 else "[M] 다음달 %s")
                entries.append((label % mf.strftime("%m/%d"), ms, "M"))

    entries.append(("직접 입력 YYYYMMDD", "CUSTOM", ""))
    return entries

