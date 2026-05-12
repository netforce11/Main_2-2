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
# [분리] 시간 유틸 → chart_time_utils.py
from chart_time_utils import et_to_kst_str, fmt_time, on_range_changed

# ── 순환참조 방지: lazy import 사용 (chart_tab_ibkr → chart_data 방향 없음)
from chart_tab_ibkr import (
    fetch_ibkr_history, fetch_polygon_history,
    load_day_df, download_day,
)


# ── 캘린더 / 연속보기 ─────────────────────────────────────


# [분리] 캘린더/연속보기 → chart_data_nav.py
from chart_data_nav import on_calendar, on_multi_chk, do_multi_day  # noqa: F401

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

    # ── 기능3: 거래량 급증 하이라이트 ───────────────────────
    try:
        from chart_vol_surge import draw_vol_surge
        # vol_data: [(x_index, volume), ...]
        _vol_data = list(enumerate(v_h))
        draw_vol_surge(self, p_data, _vol_data)
    except Exception as _e:
        # vol_surge 미설치 시 기본 바 그리기로 fallback
        self.p2.addItem(pg.BarGraphItem(
            x=range(len(v_h)), height=v_h, width=0.6, brushes=v_b))
    else:
        # draw_vol_surge 내부에서 p2 바를 그리므로 중복 방지
        # 급증 없는 봉은 draw_vol_surge 가 이미 기본색으로 그림
        pass
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

    # current_processed: (r_dict, et_datetime, eok_float) 튜플 리스트
    # peak1/peak2/update_peak3 및 chart_exec_marker 모두 이 형식 사용
    self.current_processed = []
    for r, et in filtered:
        eok_val = (r.get('c', r.get('close', 0)) *
                   r.get('v', r.get('volume', 0)) * fx) / 100_000_000
        # exec_marker 가 참조하는 키 정규화
        r_norm = {**r,
                  'h': r.get('h', r.get('high', 0)),
                  'l': r.get('l', r.get('low',  0)),
                  't': r.get('t', 0)}
        self.current_processed.append((r_norm, et, eok_val))

    # [수정] self.df 갱신 — push_trend_df 가 오래된 데이터를 보내는 버그 수정
    if PANDAS and filtered:
        try:
            self.df = pd.DataFrame([r for r, _ in filtered])
        except Exception:
            pass

    # ── 기능5: 체결 마커 오버레이 ────────────────────────────
    try:
        from chart_exec_marker import redraw_exec_markers
        redraw_exec_markers(self)
    except Exception as _e:
        pass


    # [분리] 테이블 렌더링
    from chart_data_render import _render_left_table
    _render_left_table(self, hi_rows, fx, C)


# ── re-export: tab_chart.py 가 chart_data 에서 직접 임포트하는 함수들 ──
from chart_data_table import append_right, clr_right, push_trend_df  # noqa: F401
