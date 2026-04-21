"""
kr_chart_data.py — 데이터 표시·캘린더·연속보기·KST 포맷
────────────────────────────────────────────────────────
포함:
  on_calendar()      — 캘린더 클릭 핸들러
  do_fetch_date()    — 날짜 기준 데이터 로드 + 표시
  on_multi_chk()     — 연속보기 체크박스
  update_display()   — 캔들/테이블 렌더링
  push_trend_df()    — Tab4 추세판 DF push
  fmt_kst()          — KST 시간 포맷 (타임스탬프 → HH:MM)
  on_range_changed() — 줌 시 시간대 라벨 갱신
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime, timedelta, time, date

from PyQt5.QtWidgets import QTableWidgetItem, QMessageBox
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from kr_chart_theme import _THEME

try:
    from kr_chart_workers import CandlestickItem
except ImportError:
    CandlestickItem = None


# ── KST 시간 포맷 ─────────────────────────────────────────────

def fmt_kst(self, ts_ms: int) -> str:
    """밀리초 UTC 타임스탬프 → KST HH:MM 문자열."""
    try:
        if PANDAS:
            kst = (pd.Timestamp(ts_ms, unit="ms", tz="UTC")
                   .tz_convert("Asia/Seoul"))
            return kst.strftime("%m/%d %H:%M")
        dt = datetime.utcfromtimestamp(ts_ms / 1000)
        kst = dt + timedelta(hours=9)
        return kst.strftime("%m/%d %H:%M")
    except Exception:
        return "??:??"


def on_range_changed(self, vb, ranges):
    if not hasattr(self, "lbl_zoom_time"): return
    if not hasattr(self, "_x_time_map") or not self._x_time_map: return
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


# ── 캘린더 핸들러 ─────────────────────────────────────────────

def on_calendar(self, qdate=None):
    """캘린더 클릭 또는 날짜 직접 입력 후 호출."""
    if self.is_rt:
        self._stop_rt()
    qd  = self.calendar.selectedDate()
    tgt = date(qd.year(), qd.month(), qd.day())
    self.selected_date = tgt
    sym = self.sym_in.text().strip().zfill(6)

    if getattr(self, "_daily_view_active", False):
        from kr_chart_daily import load_daily_data
        load_daily_data(self)
        return

    if self._multi_day_active:
        _do_multi_day(self, self._multi_day_count)
        return

    do_fetch_date(self, sym, tgt)


def on_multi_chk(self, days: int, chk, state: int):
    if state == Qt.Checked:
        for d, c in self.multi_chks.items():
            if d != days:
                c.blockSignals(True); c.setChecked(False); c.blockSignals(False)
        self._multi_day_active = True
        self._multi_day_count  = days
        _do_multi_day(self, days)
    else:
        self._multi_day_active = False
        self._multi_day_count  = 1
        on_calendar(self)


def _do_multi_day(self, num_days: int):
    sym    = self.sym_in.text().strip().zfill(6)
    qd     = self.calendar.selectedDate()
    end_d  = date(qd.year(), qd.month(), qd.day())
    frames, collected, d, attempts = [], 0, end_d, 0

    from kr_chart_kiwoom import load_day_df
    while collected < num_days and attempts < num_days + 14:
        attempts += 1
        if d.weekday() < 5:
            f = load_day_df(self, sym, d)
            if f is not None and not f.empty:
                frames.insert(0, f); collected += 1
        d -= timedelta(days=1)

    if not frames:
        QMessageBox.warning(self, "데이터 없음", "연속 데이터를 불러올 수 없습니다.")
        return
    self.df_raw = []
    for f in frames:
        self.df_raw.extend(f.to_dict("records"))
    self.selected_date = end_d
    self.status_lbl.setText(f"📅 {num_days}일 연속")
    update_display(self, force_regular=True)
    if PG: self.p1.autoRange()
    push_trend_df(self)


def do_fetch_date(self, sym: str, tgt: date):
    """CSV 캐시 확인 → 없으면 API 조회."""
    from kr_chart_kiwoom import load_day_df, fetch_history, _has_marker

    if _has_marker(sym, tgt):
        df = load_day_df(self, sym, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict("records")
            self.selected_date = tgt
            self.status_lbl.setText(f"📅 {tgt} 캐시 로드 ({len(df)}봉)")
            update_display(self)
            if PG: self.p1.autoRange()
            push_trend_df(self)
            return

    fetch_history(self, sym, tgt)


# ── 차트/테이블 렌더링 ────────────────────────────────────────

def update_display(self, force_regular=False):
    raw = self.df_raw
    if not raw or not PG or CandlestickItem is None:
        return
    from kr_chart_hlines import redraw_hlines
    from kr_chart_markers import redraw_time_markers

    limit = float(self.high_in.text() or 100)

    def get_kst(r):
        try:
            if PANDAS:
                return (pd.Timestamp(r["t"], unit="ms", tz="UTC")
                        .tz_convert("Asia/Seoul"))
            dt = datetime.utcfromtimestamp(r["t"] / 1000)
            return dt + timedelta(hours=9)
        except Exception:
            return None

    holding = (self.holding_chk.isChecked()
               and not self.is_rt and not force_regular)
    filtered = []
    for r in sorted(raw, key=lambda x: x.get("t", 0)):
        kst = get_kst(r)
        if kst is None: continue
        kst_t = kst.time()
        if holding:
            if not ((time(15, 0) <= kst_t < time(15, 30))
                    or (time(9, 0) <= kst_t <= time(10, 30))):
                continue
        else:
            if not (time(9, 0) <= kst_t < time(15, 30)): continue
        filtered.append((r, kst))

    if not filtered: return
    if self.is_rt:
        filtered = filtered[-self.candle_spin.value():]

    self.p1.clear(); self.p2.clear()
    p_data = []; v_h = []; v_b = []; x_t = []
    hi_rows = []; prev_d = None; date_bounds = []
    self._x_time_map = {}
    C = _THEME[self.dark_mode]

    for i, (r, kst) in enumerate(filtered):
        o  = r.get("o", 0); c_ = r.get("c", 0)
        lo = r.get("l", 0); hi = r.get("h", 0); v = r.get("v", 0)
        eok = (c_ * v) / 100_000_000   # 거래대금(억): 종가×거래량/1억
        cur_d = kst.date()
        if prev_d and cur_d != prev_d:
            date_bounds.append(i - 0.5)
        prev_d = cur_d
        p_data.append((i, o, c_, lo, hi))
        v_h.append(v)
        v_b.append(self._c_up() if c_ >= o else self._c_dn())
        t_str = fmt_kst(self, r["t"])
        self._x_time_map[i] = t_str
        if i % 30 == 0: x_t.append((i, t_str))
        if eok >= limit: hi_rows.append((i, r, kst, eok))

    self.p1.addItem(CandlestickItem(p_data, self._c_up(), self._c_dn()))
    self.p2.addItem(pg.BarGraphItem(
        x=range(len(v_h)), height=v_h, width=0.6, brushes=v_b))

    from PyQt5.QtCore import Qt as _Qt
    for bx in date_bounds:
        for pl in (self.p1, self.p2):
            pl.addItem(pg.InfiniteLine(
                pos=bx, angle=90,
                pen=pg.mkPen("#ff6600", width=2, style=_Qt.DashLine)))

    for pl in (self.p1, self.p2):
        pl.getAxis("bottom").setTicks([x_t])

    redraw_time_markers(self)
    redraw_hlines(self)
    self.current_processed = [(r, kst, eok) for _, r, kst, eok in hi_rows]

    # 좌측 테이블 렌더링 (거래대금 내림차순)
    hi_sorted = sorted(hi_rows, key=lambda x: -x[3])
    self.table_l.setRowCount(len(hi_sorted))
    for ri, (i, r, kst, eok) in enumerate(hi_sorted):
        t_s = kst.strftime("%H:%M:%S")
        vals = [t_s,
                f"{r.get('o', 0):,.0f}", f"{r.get('h', 0):,.0f}",
                f"{r.get('l', 0):,.0f}", f"{r.get('c', 0):,.0f}",
                f"{eok:,.2f}"]
        for ci, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignCenter)
            it.setForeground(QColor(C["fg"]))
            self.table_l.setItem(ri, ci, it)
            if ci == 5:
                bg = (C["row_hi"] if eok >= 500
                      else (C["row_mid"] if eok >= 200 else C["row_lo"]))
                self.table_l.item(ri, ci).setBackground(QColor(bg))


def push_trend_df(self):
    if not PANDAS or self.df is None or self.df.empty: return
    try:
        combo = getattr(self.mw, "tab_combo", None)
        if combo and hasattr(combo, "set_trend_df"):
            col_map = {"o": "open", "h": "high", "l": "low",
                       "c": "close", "v": "volume"}
            combo.set_trend_df(self.df.rename(columns=col_map))
    except Exception as e:
        print(f"[KrChart] push_trend_df 오류: {e}")
