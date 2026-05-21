"""
auto_spx_fetch.py — AutoSpxFetchMixin
══════════════════════════════════════════════════════════
앱 시작 후 10초간 아무 동작이 없으면 SPX를 자동 조회한다.

조건:
  1. 10초 내 사용자가 관심종목을 클릭하거나 _fetch()를 호출하면 취소
  2. 관심종목에 SPX가 없으면 맨 위에 자동 추가
  3. IBKR 연결 완료 후 날짜 수신 시점 기준으로 거래일 판단
  4. 주말 / 미국 공휴일이면 직전 거래일 기준으로 조회
  5. 자정(00:00) 넘어가도 KST 날짜 기준이 아닌 ET 날짜 기준으로 처리

통합 방법
─────────
1. CallPutGrid 상속 목록에 AutoSpxFetchMixin 추가 (CoreFetchMixin 앞)
2. __init__ 말미에  self._init_auto_spx_fetch()  추가
3. _on_watch_single_click / _on_watch_dbl / _fetch 등 사용자 액션 함수에서
       self._cancel_auto_spx_fetch()  호출 (이미 있는 함수이면 내부에 추가)
   → 아래 _patch_user_actions() 를 __init__ 에서 호출하면 자동 패치됨

의존 항목
─────────
- PyQt5 QTimer
- self.watchlist        : QListWidget (관심종목)
- self._on_watch_dbl()  : 더블클릭 조회 (이미 구현됨)
- self._w_save()        : 관심종목 저장
- self._apply_watchlist_font() : 폰트 적용
- self._log()           : 하단 로그

미국 공휴일 목록 (NYSE 기준, 고정일 + 부동일 포함)
"""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt5.QtCore import QTimer


# ── 미국 NYSE 공휴일 계산 ────────────────────────────────────

def _us_holidays(year: int) -> set:
    """
    NYSE 공휴일 날짜 집합 반환 (ET 기준).
    고정일이 주말이면 월요일(금요일) 대체 포함.
    """
    from datetime import date, timedelta

    def _nearest_weekday(d: date) -> date:
        """주말이면 가장 가까운 평일로 이동."""
        if d.weekday() == 5:   # 토 → 금
            return d - timedelta(days=1)
        if d.weekday() == 6:   # 일 → 월
            return d + timedelta(days=1)
        return d

    def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
        """해당 월 n번째 weekday(0=월…6=일) 날짜 반환."""
        first = date(year, month, 1)
        delta = (weekday - first.weekday()) % 7
        return first + timedelta(days=delta + 7 * (n - 1))

    holidays = set()

    # 고정 공휴일
    fixed = [
        (1,  1),   # New Year's Day
        (7,  4),   # Independence Day
        (12, 25),  # Christmas
    ]
    for m, d in fixed:
        holidays.add(_nearest_weekday(date(year, m, d)))

    # MLK Day: 1월 세 번째 월요일
    holidays.add(_nth_weekday(year, 1, 0, 3))
    # Presidents' Day: 2월 세 번째 월요일
    holidays.add(_nth_weekday(year, 2, 0, 3))
    # Memorial Day: 5월 마지막 월요일
    last_monday_may = date(year, 5, 31)
    while last_monday_may.weekday() != 0:
        last_monday_may -= datetime.timedelta(days=1)
    holidays.add(last_monday_may)
    # Juneteenth: 6월 19일
    holidays.add(_nearest_weekday(date(year, 6, 19)))
    # Labor Day: 9월 첫 번째 월요일
    holidays.add(_nth_weekday(year, 9, 0, 1))
    # Thanksgiving: 11월 네 번째 목요일
    holidays.add(_nth_weekday(year, 11, 3, 4))
    # Good Friday: 부활절 전 금요일
    easter = _calc_easter(year)
    holidays.add(easter - datetime.timedelta(days=2))

    return holidays


def _calc_easter(year: int) -> datetime.date:
    """Anonymous Gregorian algorithm으로 부활절 날짜 계산."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


def _today_et() -> datetime.date:
    """pytz 없이 ET(UTC-4/UTC-5) 기준 오늘 날짜 반환."""
    from datetime import timezone, timedelta
    now_utc = datetime.datetime.now(timezone.utc)
    y = now_utc.year
    # DST 시작: 3월 두 번째 일요일 02:00 ET = 07:00 UTC
    mar1 = datetime.datetime(y, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - mar1.weekday()) % 7
    dst_start = mar1 + timedelta(days=days_to_sun + 7)
    dst_start = dst_start.replace(hour=7)
    # DST 종료: 11월 첫 번째 일요일 02:00 ET = 06:00 UTC
    nov1 = datetime.datetime(y, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - nov1.weekday()) % 7
    dst_end = nov1 + timedelta(days=days_to_sun)
    dst_end = dst_end.replace(hour=6)
    offset = timedelta(hours=-4 if dst_start <= now_utc < dst_end else -5)
    return (now_utc + offset).date()


def _prev_trading_day(ref: Optional[datetime.date] = None) -> datetime.date:
    """
    ref(기본: ET 오늘) 기준으로 가장 최근 거래일 반환.
    ref 자체가 거래일이면 그대로, 주말/공휴일이면 직전 거래일 반환.
    """
    if ref is None:
        ref = _today_et()
    holidays = _us_holidays(ref.year)
    # 전년도 공휴일도 포함 (연초에 12월 25일 대체일 등 가능성)
    holidays |= _us_holidays(ref.year - 1)
    d = ref
    while d.weekday() >= 5 or d in holidays:
        d -= datetime.timedelta(days=1)
    return d


# ── Mixin ────────────────────────────────────────────────────

class AutoSpxFetchMixin:
    """
    앱 시작 후 10초 내 아무 동작 없으면 SPX 자동 조회.

    사용하는 self 속성 (CallPutGrid가 제공)
    ────────────────────────────────────────
    watchlist           : QListWidget
    _on_watch_dbl()     : 더블클릭 조회
    _w_save()           : 관심종목 저장
    _apply_watchlist_font() : 폰트 적용
    _log()              : 로그 출력
    mw.connected        : IBKR 연결 상태

    추가되는 self 속성
    ──────────────────
    _asf_timer          : QTimer  — 10초 카운트다운
    _asf_cancelled      : bool    — 사용자 액션으로 취소됐는지
    _asf_fired          : bool    — 이미 실행됐는지
    """

    # ── 초기화 ───────────────────────────────────────────────

    def _init_auto_spx_fetch(self) -> None:
        """__init__ 말미에 호출."""
        self._asf_cancelled: bool = False
        self._asf_fired:     bool = False

        self._asf_timer = QTimer(self)
        self._asf_timer.setSingleShot(True)
        self._asf_timer.setInterval(10_000)   # 10초
        self._asf_timer.timeout.connect(self._asf_do)
        self._asf_timer.start()

        # 기존 사용자 액션 함수에 취소 훅 자동 주입
        self._asf_patch_user_actions()

    # ── 사용자 액션 감지 → 취소 ──────────────────────────────

    def _asf_patch_user_actions(self) -> None:
        """
        _on_watch_single_click / _on_watch_dbl / _fetch 를
        런타임에 래핑하여 호출 시 자동으로 _cancel_auto_spx_fetch() 실행.
        """
        for attr in ('_on_watch_single_click', '_on_watch_dbl', '_fetch'):
            orig = getattr(self, attr, None)
            if orig is None:
                continue

            def _make_wrapper(fn):
                def _wrapper(*args, **kwargs):
                    self._cancel_auto_spx_fetch()
                    return fn(*args, **kwargs)
                _wrapper.__name__ = fn.__name__ if hasattr(fn, '__name__') else attr
                return _wrapper

            setattr(self, attr, _make_wrapper(orig))

    def _cancel_auto_spx_fetch(self) -> None:
        """사용자 액션 발생 시 자동 조회 타이머 취소."""
        if not self._asf_cancelled and not self._asf_fired:
            self._asf_timer.stop()
            self._asf_cancelled = True
            self._log("[AutoSPX] 사용자 액션 감지 → 자동 조회 취소")

    # ── 실행 ─────────────────────────────────────────────────

    def _asf_do(self) -> None:
        """10초 타임아웃 → SPX 자동 조회."""
        if self._asf_cancelled or self._asf_fired:
            return
        self._asf_fired = True

        # IBKR 연결 확인
        if not getattr(self.mw, 'connected', False):
            self._log("[AutoSPX] IBKR 미연결 — 연결 후 재시도 (최대 30초 대기)")
            # 연결 대기: 3초마다 체크, 최대 30초
            self._asf_retry_count = 0
            self._asf_retry_timer = QTimer(self)
            self._asf_retry_timer.setInterval(3_000)
            self._asf_retry_timer.timeout.connect(self._asf_retry_connected)
            self._asf_retry_timer.start()
            return

        self._asf_run()

    def _asf_retry_connected(self) -> None:
        """연결 대기 중 3초마다 체크."""
        self._asf_retry_count += 1
        if self._asf_cancelled:
            self._asf_retry_timer.stop()
            return
        if getattr(self.mw, 'connected', False):
            self._asf_retry_timer.stop()
            self._asf_run()
            return
        if self._asf_retry_count >= 10:   # 30초 초과
            self._asf_retry_timer.stop()
            self._log("[AutoSPX] 연결 타임아웃 — 자동 조회 포기")

    def _asf_run(self) -> None:
        """
        실제 SPX 조회 실행.
        1. ET 기준 오늘이 거래일인지 확인
        2. 관심종목에 SPX 없으면 추가
        3. _on_watch_dbl 트리거
        """
        today_et = _today_et()
        trading_day = _prev_trading_day(today_et)

        if trading_day != today_et:
            self._log(
                f"[AutoSPX] 오늘({today_et}) 비거래일 "
                f"→ 직전 거래일 {trading_day} 기준 조회")
        else:
            self._log(f"[AutoSPX] 거래일 확인: {today_et}")

        # 관심종목에 SPX 없으면 맨 위에 추가
        spx_in_list = False
        for i in range(self.watchlist.count()):
            if self.watchlist.item(i).text().upper() in ("SPX", "SPXW"):
                spx_in_list = True
                break

        if not spx_in_list:
            self.watchlist.insertItem(0, "SPX")
            self._apply_watchlist_font()
            self._w_save()
            self._log("[AutoSPX] 관심종목에 SPX 추가됨")

        # SPX 항목 선택 후 더블클릭 트리거
        for i in range(self.watchlist.count()):
            item = self.watchlist.item(i)
            if item.text().upper() in ("SPX", "SPXW"):
                self.watchlist.setCurrentRow(i)
                # _asf_patch로 래핑된 _on_watch_dbl 호출 방지:
                # 이미 _asf_fired=True 이므로 중복 취소 없이 정상 동작
                from call_put_tab.core_fetch_watchlist import (
                    CoreFetchWatchlistMixin)
                CoreFetchWatchlistMixin._on_watch_dbl(self, item)
                self._log(
                    f"[AutoSPX] {item.text()} 자동 조회 시작 "
                    f"(ET {today_et})")
                break
