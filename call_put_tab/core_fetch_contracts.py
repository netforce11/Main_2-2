"""
core_fetch_contracts.py — 계약 생성 및 만기 계산 로직
════════════════════════════════════════════════════════
포함 내용:
  - make_opt_contract_safe()       FOP/옵션 계약 래퍼
  - _mdt_for_sym()                 종목별 MarketDataType 결정
  - _alive()                       위젯 파괴 확인 헬퍼
  - CoreFetchContractsMixin        FUT 계약·만기 계산 메서드 모음
      _cl_front_month()            CL(WTI) front-month 계산
      _es_front_month()            /ES E-mini front-month 계산
      _make_fut_contract()         선물 FUT 계약 생성
      _next_trading_day()          다음 거래일 계산
      _auto_select_next_expiry()   장외 만기 자동 선택
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer

from core import (
    SYMBOL_CFG, DEFAULT_CFG,
    make_opt_contract, make_und_contract, auto_mdt,
)

# ── 종목별 강제 지연 세트 ─────────────────────────────────────────
_DELAYED_SYMS = {"VIX", "CL"}


def make_opt_contract_safe(sym: str, strike: float, right: str, expiry: str, tag: str):
    """
    make_opt_contract 래퍼. FOP 종목(CL 등)은
    SYMBOL_CFG의 secType/exchange를 강제 적용한다.
    """
    c = make_opt_contract(sym, strike, right, expiry, tag)
    sec_type, exchange, multiplier, _step = SYMBOL_CFG.get(sym, DEFAULT_CFG)
    if sec_type == "FOP":
        c.secType    = "FOP"
        c.exchange   = exchange
        c.multiplier = multiplier
        if not getattr(c, 'tradingClass', ''):
            c.tradingClass = sym
    return c


def _mdt_for_sym(sym: str, ib) -> int:
    """
    종목별 MarketDataType 결정.

    _DELAYED_SYMS(VIX, CL 등):
      - 장중(auto_mdt=1): MDT=3 (20분 지연) 강제
      - 평일 장외(auto_mdt=3): MDT=3 유지
      - 주말(auto_mdt=4): MDT=4 (frozen 종가) 사용

    나머지: auto_mdt() 그대로 (장중=1, 평일장외=3, 주말=4).
    """
    if sym.upper() in _DELAYED_SYMS:
        base   = auto_mdt(ib)
        actual = max(base, 3)
        try:
            ib.reqMarketDataType(actual)
        except Exception as e:
            print(f"[mdt_for_sym] MDT={actual} 설정 실패({sym}): {e}")
        return actual
    return auto_mdt(ib)


def _alive(widget) -> bool:
    """위젯이 파괴되지 않았는지 확인."""
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False


class CoreFetchContractsMixin:
    """FUT 계약 생성 및 만기 계산 메서드 모음."""

    # ── 선물 종목별 설정 테이블 ──────────────────────────────────
    _FUT_UND_CFG = {
        "CL": ("NYMEX", "USD", "1000"),
        "GC": ("COMEX", "USD", "100"),
        "SI": ("COMEX", "USD", "5000"),
        "ES": ("CME",   "USD", "50"),
        "NQ": ("CME",   "USD", "20"),
    }

    # /ES 장외 대체 구독 대상 종목
    _SPX_SYMS = {"SPX", "SPXW"}

    @staticmethod
    def _cl_front_month() -> str:
        """CL(WTI 원유) front-month 만기 계산 → 'YYYYMM' 반환."""
        from datetime import date, timedelta

        def _expiry_for_month(y: int, m: int) -> date:
            cnt = 0
            cur = date(y, m, 25) - timedelta(days=1)
            while cnt < 3:
                if cur.weekday() < 5:
                    cnt += 1
                cur -= timedelta(days=1)
            return cur + timedelta(days=1)

        today = date.today()
        y, m  = today.year, today.month
        exp   = _expiry_for_month(y, m)

        biz_remaining = 0
        d = today
        while d < exp:
            if d.weekday() < 5:
                biz_remaining += 1
            d += timedelta(days=1)

        if biz_remaining <= 5:
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1

        return f"{y}{m:02d}"

    @staticmethod
    def _es_front_month() -> str:
        """
        /ES E-mini S&P500 최근월물 만기 계산 → 'YYYYMM' 반환.

        /ES 만기 규칙:
          - 분기물: 3월/6월/9월/12월의 세 번째 금요일
          - 만기 5영업일 이전이면 다음 분기월로 롤오버
        """
        from datetime import date, timedelta

        QUARTERLY = [3, 6, 9, 12]

        def _third_friday(y: int, m: int) -> date:
            d = date(y, m, 1)
            days_to_fri = (4 - d.weekday()) % 7
            first_fri   = d + timedelta(days=days_to_fri)
            return first_fri + timedelta(weeks=2)

        today = date.today()
        y, m  = today.year, today.month

        candidate_months = [(y, qm) for qm in QUARTERLY if qm >= m]
        if not candidate_months:
            candidate_months.append((y + 1, 3))

        cy, cm = candidate_months[0]
        exp    = _third_friday(cy, cm)

        biz_remaining = 0
        d = today
        while d < exp:
            if d.weekday() < 5:
                biz_remaining += 1
            d += timedelta(days=1)

        if biz_remaining <= 5:
            if len(candidate_months) > 1:
                cy, cm = candidate_months[1]
            else:
                cy, cm = y + 1, 3

        return f"{cy}{cm:02d}"

    def _make_fut_contract(self, sym: str):
        """선물 종목용 FUT 계약 생성. front-month 만기 직접 지정."""
        from ibapi.contract import Contract as _C
        exch, cur, mult = self._FUT_UND_CFG.get(sym, ("SMART", "USD", ""))
        c = _C()
        c.symbol     = sym
        c.secType    = "FUT"
        c.exchange   = exch
        c.currency   = cur
        c.multiplier = mult

        if sym == "CL":
            c.lastTradeDateOrContractMonth = self._cl_front_month()
        elif sym == "ES":
            c.lastTradeDateOrContractMonth = self._es_front_month()
        else:
            from datetime import date
            today = date.today()
            c.lastTradeDateOrContractMonth = f"{today.year}{today.month:02d}"

        return c

    @staticmethod
    def _next_trading_day() -> str:
        """
        오늘 기준 다음 거래일을 'YYYYMMDD' 문자열로 반환.

        규칙:
          - 오늘이 평일이고 장이 열려 있으면 → 오늘
          - 오늘이 평일이고 장이 끝났으면 → 다음 평일
          - 오늘이 주말이면 → 다음 월요일
        """
        from datetime import date, timedelta
        from core import is_market_open

        today = date.today()
        wd    = today.weekday()

        if wd == 5:
            return (today + timedelta(days=2)).strftime("%Y%m%d")
        if wd == 6:
            return (today + timedelta(days=1)).strftime("%Y%m%d")

        if is_market_open():
            return today.strftime("%Y%m%d")

        next_d = today + timedelta(days=1)
        while next_d.weekday() >= 5:
            next_d += timedelta(days=1)
        return next_d.strftime("%Y%m%d")

    def _auto_select_next_expiry(self):
        """
        장외 /ES 구독 시 combo_exp(만기 콤보)를 다음 거래일 SPXW로 자동 선택한다.
        """
        if not getattr(self, '_und_is_futures', False):
            return

        if getattr(self, '_spxw_today_selected', False):
            return

        target      = self._next_trading_day()
        expiry_list = getattr(self, '_expiry_list', [])
        found_idx   = -1
        for i, (label, code, tag) in enumerate(expiry_list):
            if code == target:
                found_idx = i
                break

        if found_idx < 0:
            self._log(
                f"🌙 장외 만기 자동 선택: {target} 항목 없음 "
                f"— 만기 콤보에서 직접 선택하세요.")
            return

        if hasattr(self, 'combo_exp'):
            self.combo_exp.blockSignals(True)
            self.combo_exp.setCurrentIndex(found_idx)
            self.combo_exp.blockSignals(False)

        self._log(f"🌙 장외 만기 자동 선택: {target} (다음 거래일 SPXW)")
