"""
core_conn_spxw.py — SPXW 0DTE 콤보·Zone 관리  v6.5
"""

from datetime import timedelta
from PyQt5.QtCore import QDate, QTimer
from core import is_trading_day

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



class ConnSpxwMixin:
    """SPXW 0DTE 콤보·Zone 로직. CoreConnMixin에 통합된다."""

    def _build_spxw_combo(self):
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.clear()
        self.combo_spxw.addItem("── 0DTE 선택 ──", "")
        today = _today_et()   # ★ ET 기준
        d = today - timedelta(days=3)
        days = []
        while d <= today + timedelta(days=14):
            if is_trading_day(d): days.append(d)
            d += timedelta(days=1)
        for d in days:
            label = ("오늘 " if d == today else
                     "어제 " if d == today - timedelta(days=1) else
                     "내일 " if d == today + timedelta(days=1) else "")
            label += d.strftime("%m/%d(%a)")
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
