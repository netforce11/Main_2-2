"""
chart_data_nav.py — 캘린더 / 연속보기 내비게이션 핸들러
[분리] chart_data.py 에서 분리
  on_calendar, on_multi_chk, do_multi_day
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import timedelta, date
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from chart_tab_ibkr import fetch_ibkr_history, fetch_polygon_history, load_day_df
# update_display, push_trend_df는 순환 임포트 방지를 위해 함수 내부에서 lazy import

def on_calendar(self, qdate=None):
    from chart_rt import stop_rt
    stop_rt(self)
    qd  = self.calendar.selectedDate()
    tgt = date(qd.year(), qd.month(), qd.day())
    self.selected_date = tgt
    sym = self.sym_in.text().upper()

    # ── 일봉 뷰 활성 중이면 일봉도 자동 갱신 ─────────────────
    if getattr(self, '_daily_view_active', False):
        from chart_daily import load_daily_data
        load_daily_data(self)
        return   # 일봉 모드일 때는 분봉 로드 생략

    if self._multi_day_active:
        do_multi_day(self, self._multi_day_count); return
    if self.mode == "ibkr" and self.mw.connected:
        fetch_ibkr_history(self, sym, tgt)
    else:
        fetch_polygon_history(self, sym, tgt)


def on_multi_chk(self, days: int, chk, state: int):
    if state == Qt.Checked:
        for d, c in self.multi_chks.items():
            if d != days:
                c.blockSignals(True); c.setChecked(False); c.blockSignals(False)
        self._multi_day_active = True
        self._multi_day_count  = days
        do_multi_day(self, days)
    else:
        self._multi_day_active = False
        self._multi_day_count  = 1
        on_calendar(self)


def do_multi_day(self, num_days: int):
    symbol   = self.sym_in.text().upper().strip()
    qd       = self.calendar.selectedDate()
    end_date = date(qd.year(), qd.month(), qd.day())
    frames, collected, d, attempts = [], 0, end_date, 0
    while collected < num_days and attempts < num_days + 14:
        attempts += 1
        f = load_day_df(self, symbol, d)
        if f is not None and not f.empty:
            frames.insert(0, f); collected += 1
        d -= timedelta(days=1)
    if not frames:
        QMessageBox.warning(self, "데이터 없음", "연속 데이터를 불러올 수 없습니다.")
        return
    self.df_raw = []
    for f in frames:
        self.df_raw.extend(f.to_dict('records'))
    self.selected_date = end_date
    self.status_lbl.setText(f"📅 {num_days}일 연속 (ET, 정규장)")
    from chart_data import update_display
    update_display(self, force_regular=True)
    if PG: self.p1.autoRange()
    from chart_data_table import push_trend_df
    push_trend_df(self)