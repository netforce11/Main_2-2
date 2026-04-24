"""
chart_data.py — 데이터 로드 · 표시 · 캘린더 · 연속보기
────────────────────────────────────────────────────────
포함:
  on_calendar()          — 캘린더 클릭 핸들러
  on_multi_chk()         — 연속보기 체크박스
  do_multi_day()         — N일 연속 데이터 로드
  fetch_ibkr_history()   — IBKR 과거 바 요청
  fetch_polygon_history()— Polygon 과거 조회
  load_day_df()          — pickle → CSV → API 삼단 fallback
  download_day()         — Polygon API → CSV 저장
  update_display()       — 캔들/테이블 렌더링
  append_right()         — 대량체결 우측 테이블 추가
  clr_right()            — 우측 테이블 초기화
  push_trend_df()        — Tab4 추세판 DF push
  et_to_kst_str()        — ET → KST 변환
  fmt_time()             — 표시 시간 포맷
  on_range_changed()     — 줌 시 시간대 라벨 갱신
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


import requests
from datetime import datetime, timedelta, time, date

from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False
    pd = None

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import bridge, make_und_contract, REQ_HIST, auto_mdt

try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")

from chart_theme import _THEME
from chart_workers import CandlestickItem

# ── 순환참조 방지: chart_tab_ibkr 은 내부에서 lazy import 하므로
#    여기서는 파일 상단에 한 번만 import (chart_tab_ibkr → chart_data 방향 없음)
from chart_tab_ibkr import (
    fetch_ibkr_history, fetch_polygon_history,
    load_day_df, download_day,
)


# ── KST 변환 ────────────────────────────────────────────────

def et_to_kst_str(self, et_dt) -> str:
    try:
        d = et_dt.date() if hasattr(et_dt, 'date') else et_dt
        year = d.year
        mar1 = date(year, 3, 1); sun_count = 0
        for day_offset in range(31):
            dd = mar1 + timedelta(days=day_offset)
            if dd.weekday() == 6:
                sun_count += 1
                if sun_count == 2: dst_start = dd; break
        nov1 = date(year, 11, 1)
        for day_offset in range(7):
            dd = nov1 + timedelta(days=day_offset)
            if dd.weekday() == 6: dst_end = dd; break
        is_dst  = dst_start <= d < dst_end
        offset_h = 13 if is_dst else 14
        kst = et_dt + timedelta(hours=offset_h)
        return kst.strftime('%m/%d %H:%M')
    except Exception:
        return "??:??"


def fmt_time(self, et_dt) -> str:
    use_kst = hasattr(self, 'kst_chk') and self.kst_chk.isChecked()
    return et_to_kst_str(self, et_dt) if use_kst else et_dt.strftime('%m/%d %H:%M')


def on_range_changed(self, vb, ranges):
    if not hasattr(self, 'lbl_zoom_time'): return
    if not hasattr(self, '_x_time_map') or not self._x_time_map: return
    try:
        xmin, xmax = ranges[0]
        keys = sorted(self._x_time_map.keys())
        vis  = [k for k in keys if xmin <= k <= xmax]
        if vis:
            t_start = self._x_time_map.get(vis[0], "")
            t_end   = self._x_time_map.get(vis[-1], "")
            self.lbl_zoom_time.setText(
                f"📊 {t_start} ~ {t_end}  ({len(vis)}봉)")
    except Exception:
        pass


# ── 캘린더 / 연속보기 ─────────────────────────────────────

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
    update_display(self, force_regular=True)
    if PG: self.p1.autoRange()
    push_trend_df(self)


def update_display(self, force_regular=False):
    raw = self.df_raw
    if not raw or not PG: return
    from chart_hlines import redraw_hlines
    from chart_markers import redraw_time_markers
    fx    = float(self.fx_in.text() or 1480)
    limit = float(self.high_in.text() or 3000)

    def get_et(r):
        try:
            if PANDAS:
                return (pd.Timestamp(r['t'], unit='ms', tz='UTC')
                        .tz_convert('America/New_York'))
            return datetime.utcfromtimestamp(r['t'] / 1000)
        except Exception: return None

    holding = (self.holding_chk.isChecked()
               and not self.is_rt and not force_regular)
    filtered = []
    for r in sorted(raw, key=lambda x: x.get('t', 0)):
        et = get_et(r)
        if et is None: continue
        et_t = et.time()
        if holding:
            if not ((time(15, 0) <= et_t < time(16, 0))
                    or (time(9, 30) <= et_t <= time(10, 30))):
                continue
        else:
            if not (time(9, 30) <= et_t < time(16, 0)): continue
        filtered.append((r, et))
    if not filtered: return
    if self.is_rt:
        filtered = filtered[-self.candle_spin.value():]

    self.p1.clear(); self.p2.clear()
    p_data = []; v_h = []; v_b = []; x_t = []
    hi_rows = []; prev_d = None; date_bounds = []
    self._x_time_map = {}
    C = _THEME[self.dark_mode]
    for i, (r, et) in enumerate(filtered):
        o  = r.get('o', r.get('open', 0))
        c_ = r.get('c', r.get('close', 0))
        lo = r.get('l', r.get('low', 0))
        hi = r.get('h', r.get('high', 0))
        v  = r.get('v', r.get('volume', 0))
        eok = (c_ * v * fx) / 100_000_000
        cur_d = et.date()
        if prev_d and cur_d != prev_d: date_bounds.append(i - 0.5)
        prev_d = cur_d
        p_data.append((i, o, c_, lo, hi))
        v_h.append(v)
        v_b.append(self._c_up() if c_ >= o else self._c_dn())
        t_str = fmt_time(self, et)
        self._x_time_map[i] = t_str
        if i % 30 == 0: x_t.append((i, t_str))
        if eok >= limit: hi_rows.append((i, r, et, eok))

    self.p1.addItem(CandlestickItem(p_data, self._c_up(), self._c_dn()))
    self.p2.addItem(pg.BarGraphItem(
        x=range(len(v_h)), height=v_h, width=0.6, brushes=v_b))
    from PyQt5.QtCore import Qt as _Qt
    for bx in date_bounds:
        for pl in (self.p1, self.p2):
            pl.addItem(pg.InfiniteLine(
                pos=bx, angle=90,
                pen=pg.mkPen('#ff6600', width=2, style=_Qt.DashLine)))
    for pl in (self.p1, self.p2):
        pl.getAxis('bottom').setTicks([x_t])
    redraw_time_markers(self)
    redraw_hlines(self)
    self.current_processed = [(r, et, eok) for _, r, et, eok in hi_rows]

    hi_sorted = sorted(hi_rows, key=lambda x: -x[3])
    self.table_l.setRowCount(len(hi_sorted))
    for ri, (i, r, et, eok) in enumerate(hi_sorted):
        et_s = et.strftime('%H:%M:%S')
        vals = [et_s,
                f"{r.get('o', 0):,.2f}", f"{r.get('h', 0):,.2f}",
                f"{r.get('l', 0):,.2f}", f"{r.get('c', 0):,.2f}",
                f"{eok:,.2f}"]
        for ci, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignCenter)
            it.setForeground(QColor(C['fg']))
            self.table_l.setItem(ri, ci, it)
            if ci == 5:
                bg = (C['row_hi'] if eok >= 5000
                      else (C['row_mid'] if eok >= 3000 else C['row_lo']))
                self.table_l.item(ri, ci).setBackground(QColor(bg))


def append_right(self, data, eok):
    C = _THEME[self.dark_mode]
    from core import ts
    try:
        et_s = (pd.Timestamp(data['s'], unit='ms', tz='UTC')
                .tz_convert('America/New_York').strftime('%H:%M:%S')
                if PANDAS else ts())
    except Exception:
        et_s = ts()
    r = self.table_r.rowCount(); self.table_r.insertRow(r)
    vals = [et_s,
            f"{data.get('o', 0):,.2f}", f"{data.get('h', 0):,.2f}",
            f"{data.get('l', 0):,.2f}", f"{data.get('c', 0):,.2f}",
            f"{eok:,.2f}", "실시간"]
    for ci, v in enumerate(vals):
        it = QTableWidgetItem(str(v))
        it.setTextAlignment(Qt.AlignCenter)
        it.setForeground(QColor(C['fg']))
        self.table_r.setItem(r, ci, it)
        if ci == 5:
            bg = (C['row_hi'] if eok >= 5000
                  else (C['row_mid'] if eok >= 3000 else C['row_lo']))
            self.table_r.item(r, ci).setBackground(QColor(bg))
    self.table_r.scrollToBottom()


def clr_right(self):
    self.table_r.setRowCount(0)


def push_trend_df(self):
    if not PANDAS or self.df is None or self.df.empty: return
    try:
        combo = getattr(self.mw, 'tab_combo', None)
        if combo and hasattr(combo, 'set_trend_df'):
            col_map = {'o': 'open', 'h': 'high', 'l': 'low',
                       'c': 'close', 'v': 'volume'}
            combo.set_trend_df(self.df.rename(columns=col_map))
    except Exception as e:
        print(f"[ChartGrid] _push_trend_df 오류: {e}")