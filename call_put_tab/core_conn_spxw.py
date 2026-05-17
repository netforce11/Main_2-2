"""
core_conn_spxw.py — SPXW 0DTE 콤보·Zone 관리  v6.6

【수정 2026-05】
- _build_spxw_combo()
    ① 범위 확장: ±14 거래일 → 당일 포함 다음달 월간만기 다음날까지
       (다음달 세 번째 금요일이 14 거래일 밖에 있어도 항상 목록에 포함)
    ② 배지 추가: 월간만기 날짜에 [월간] 표시, 일반 금요일에 [W] 표시

【수정 v6.6】
- _on_spxw_select()
    ③ Monthly 만기(세 번째 금요일) 선택 시 edit_sym="SPX" 자동 전환
       (IBKR은 해당 날짜에 SPXW 계약을 발행하지 않으므로
        기존 "SPXW" 고정 시 ERR 200 / 빈 체인 반환되던 버그 수정)
    ④ _log()에 Monthly 여부 표기 추가
"""

from datetime import datetime, timedelta, timezone, date
from PyQt5.QtCore import QDate, QTimer
from core import is_trading_day
from core_expiry import _third_friday                          # 월간만기 판별용
from call_put_tab.core_expiry_utils import _is_monthly_expiry  # v6.6 Monthly 분기용 (순환 의존 없음)


def _today_et() -> date:
    """pytz 없이 미국 동부시간(ET) 기준 오늘 날짜 반환."""
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    from datetime import timedelta as _td
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar1 + _td(days=(6 - mar1.weekday()) % 7 + 7)
    dst_start = dst_start.replace(hour=7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov1 + _td(days=(6 - nov1.weekday()) % 7)
    dst_end = dst_end.replace(hour=6)
    offset = _td(hours=-4 if dst_start <= now_utc < dst_end else -5)
    return (now_utc + offset).date()


def _monthly_expiry_set_et() -> set:
    """
    ET 기준 이번달·다음달 월간만기 날짜 집합 (date 객체).
    combo_spxw 배지 표시에 사용.
    """
    today = _today_et()
    result = set()
    for month_offset in range(2):
        if month_offset == 0:
            y, m = today.year, today.month
        else:
            if today.month == 12:
                y, m = today.year + 1, 1
            else:
                y, m = today.year, today.month + 1
        result.add(_third_friday(y, m))
    return result


class ConnSpxwMixin:
    """SPXW 0DTE 콤보·Zone 로직. CoreConnMixin에 통합된다."""

    def _build_spxw_combo(self):
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.clear()
        self.combo_spxw.addItem("── 0DTE 선택 ──", "")

        today = _today_et()   # ★ ET 기준

        # 【수정①】월간만기 날짜 집합 — 배지 표시 및 범위 결정에 사용
        monthly_dates = _monthly_expiry_set_et()

        # 【수정①】범위: 3일 전 ~ max(오늘+14 거래일, 다음달 월간만기 다음날)
        # 다음달 세 번째 금요일이 14 거래일 밖이어도 반드시 포함되도록
        next_monthly = max(monthly_dates)           # 두 날짜 중 더 먼 쪽(다음달)
        range_end = max(today + timedelta(days=21), # 달력 기준 3주 여유
                        next_monthly + timedelta(days=1))

        days = []
        d = today - timedelta(days=3)
        while d <= range_end:
            if is_trading_day(d):
                days.append(d)
            d += timedelta(days=1)

        for d in days:
            # 【수정②】배지: 월간만기 / 일반 금요일(W) / 월~목 구분
            if d in monthly_dates:
                badge = "[월간] "
            elif d.weekday() == 4:          # 금요일이지만 월간만기 아님
                badge = "[W] "
            else:
                badge = ""

            # 상대일 접두사
            if d == today:
                prefix = "오늘 "
            elif d == today - timedelta(days=1):
                prefix = "어제 "
            elif d == today + timedelta(days=1):
                prefix = "내일 "
            else:
                prefix = ""

            label = badge + prefix + d.strftime("%m/%d(%a)")
            self.combo_spxw.addItem(label, d.strftime("%Y%m%d"))

        self.combo_spxw.blockSignals(False)

    def _on_spxw_select(self, idx):
        expiry = self.combo_spxw.itemData(idx)
        if not expiry:
            return

        # ── v6.6: Monthly 만기(세 번째 금요일) sym 분기 ─────────────
        # SPX Monthly(AM-settled)는 마지막 거래일이 만기 전날(목요일).
        # 만기 당일(금요일)에는 SPX Monthly 시세가 없고
        # SPXW PM-settled만 당일 4PM까지 조회 가능.
        is_monthly = _is_monthly_expiry(expiry)
        if is_monthly:
            from call_put_tab.core_conn_spxw import _today_et
            from datetime import date as _date
            today       = _today_et()
            expiry_date = _date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))
            if today >= expiry_date:
                # 만기 당일 또는 이후 → SPXW PM-settled로 조회
                sym        = "SPXW"
                is_monthly = False   # SPXW 처리 경로로
            else:
                # 만기 전 → SPX Monthly 조회 가능
                sym = "SPX"
        else:
            sym = "SPXW"
        self.edit_sym.setText(sym)

        # ── Monthly 컨텍스트 플래그 ─────────────────────────────────
        # _refresh_expiry_list() 내부에서 edit_sym을 읽어 raw_sym을 결정하는데,
        # Monthly의 경우 edit_sym="SPX"로 바뀌어 있어 _tag_monthly_expiries()를
        # 건너뛰게 된다. 플래그를 먼저 설정해 _refresh_expiry_list()가
        # Monthly 태깅을 강제 적용하도록 한다.
        self._spxw_monthly_pending = is_monthly

        if hasattr(self, '_refresh_expiry_list'):
            self._refresh_expiry_list()

        self._spxw_monthly_pending = False   # 소비 후 초기화

        custom_idx = next(
            (i for i, (_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list) - 1)
        self.combo_exp.blockSignals(True)
        self.combo_exp.setCurrentIndex(custom_idx)
        self.combo_exp.blockSignals(False)
        self.edit_custom.setVisible(False)
        self.edit_custom.setText(expiry)
        y, m, d = int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8])
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(QDate(y, m, d))
        self.date_edit.blockSignals(False)
        self.date_edit.setVisible(True)

        monthly_tag = "  [Monthly/SPX]" if is_monthly else ""
        self._log(f"SPXW 0DTE 선택: {expiry}  sym={sym}{monthly_tag}")

    # ── Zone / 만기 ─────────────────────────────────────────────
    def _on_zone_change(self, btn):
        for z, rb in self._zone_btns.items():
            if rb is btn: self._zone = z
        if self.und_price is not None: self._fetch()

    # ── 만기 조회용 reqId (기존 범위와 충돌 없음) ─────────────────