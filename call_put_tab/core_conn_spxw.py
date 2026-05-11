"""
core_conn_spxw.py — SPXW 0DTE 콤보·Zone 관리  v6.5

【수정 2026-05】
- _build_spxw_combo()
    ① 범위 확장: ±14 거래일 → 당일 포함 다음달 월간만기 다음날까지
       (다음달 세 번째 금요일이 14 거래일 밖에 있어도 항상 목록에 포함)
    ② 배지 추가: 월간만기 날짜에 [월간] 표시, 일반 금요일에 [W] 표시
"""

from datetime import datetime, timedelta, timezone, date
from PyQt5.QtCore import QDate, QTimer
from core import is_trading_day
from core_expiry import _third_friday   # 월간만기 판별용


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
        if not expiry: return
        self.edit_sym.setText("SPXW")
        if hasattr(self, '_refresh_expiry_list'):
            self._refresh_expiry_list()
        custom_idx = next(
            (i for i,(_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list)-1)
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
        self._log(f"SPXW 0DTE 선택: {expiry}")

    # ── Zone / 만기 ─────────────────────────────────────────────
    def _on_zone_change(self, btn):
        for z, rb in self._zone_btns.items():
            if rb is btn: self._zone = z
        if self.und_price is not None: self._fetch()

    # ── 만기 조회용 reqId (기존 범위와 충돌 없음) ─────────────────