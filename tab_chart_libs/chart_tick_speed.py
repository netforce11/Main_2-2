"""
chart_tick_speed.py — 틱/호가 속도 인디케이터 (멀티 윈도우)
────────────────────────────────────────────────────────
· IBKR tickPrice 콜백(Bid/Ask/Last)을 슬라이딩 윈도우로 집계
· 10초 / 30초 / 60초 세 윈도우를 p3 패널에 나란히 표시
· 2초마다 갱신 + SQLite 저장 (db_manager.py 연동)

외부 호출:
    from chart_tick_speed import init_tick_speed, stop_tick_speed
    init_tick_speed(self)   # p3 패널 생성
    stop_tick_speed(self)   # 타이머 정지

core.py TickRouter._route_price() 에서:
    from chart_tick_speed import on_ibkr_tick
    on_ibkr_tick(tick_type, price)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import time
from collections import deque

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel, QHBoxLayout, QWidget, QVBoxLayout

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

# ── 설정 ─────────────────────────────────────────────────────
WINDOWS      = [10, 30, 60]      # 집계 윈도우 (초)
TIMER_MS     = 2000              # 갱신 주기
HISTORY_LEN  = 30                # 윈도우당 히스토리 봉 수
MULT_FAST    = 2.0               # 평균 대비 → 주황
MULT_SURGE   = 4.0               # 평균 대비 → 빨강

COLOR_NORMAL = "#1D9E75"
COLOR_FAST   = "#FF8C00"
COLOR_SURGE  = "#E24B4A"
COLOR_BG     = "#0d0d1a"
COLOR_DIM    = "#aaaaaa"

# ── 전역 큐 (최대 윈도우=60초치 보관) ───────────────────────
_tick_times  = deque()   # Last 틱
_quote_times = deque()   # Bid/Ask 변경
_current_sym = ""        # 현재 구독 종목 (DB 저장용)
_db_batch: list = []     # [수정] 배치 버퍼 (30초치 모아서 한 번에 INSERT)


def on_ibkr_tick(tick_type: int, price: float):
    """core.py TickRouter 에서 호출."""
    now = time.time()
    if tick_type in (1, 2):
        _quote_times.append(now)
    elif tick_type == 4:
        _tick_times.append(now)


def set_current_sym(sym: str):
    """start_stream() 에서 종목 변경 시 호출."""
    global _current_sym
    _current_sym = sym.upper()


def _purge(cutoff: float):
    while _tick_times  and _tick_times[0]  < cutoff: _tick_times.popleft()
    while _quote_times and _quote_times[0] < cutoff: _quote_times.popleft()


def _count(q: deque, window: int) -> int:
    cutoff = time.time() - window
    return sum(1 for t in q if t >= cutoff)


def _get_color(count: int, hist: list) -> str:
    if not hist or len(hist) < 3:
        return COLOR_NORMAL
    avg = sum(hist[-6:]) / len(hist[-6:]) if hist[-6:] else 0
    if avg == 0:
        return COLOR_NORMAL
    r = count / avg
    return COLOR_SURGE if r >= MULT_SURGE else (COLOR_FAST if r >= MULT_FAST else COLOR_NORMAL)


def _ratio_str(count: int, hist: list) -> str:
    if not hist or len(hist) < 3:
        return ""
    avg = sum(hist[-6:]) / len(hist[-6:]) if hist[-6:] else 0
    return f"×{count/avg:.1f}" if avg > 0 else ""


# ── p3 패널 초기화 ───────────────────────────────────────────
if PG:
    def init_tick_speed(self):
        """build_chart_area() 에서 1회 호출. p3 패널(row=2) 생성."""
        self.p3 = self.gfx.addPlot(row=2, col=0)
        self.p3.setFixedHeight(90)          # 3행 → 높이 확장
        self.p3.setXLink(self.p1)
        self.p3.hideAxis('bottom')
        self.p3.hideAxis('left')
        self.p3.setMouseEnabled(x=False, y=False)
        self.p3.setMenuEnabled(False)
        self.p3.getViewBox().setBackgroundColor(COLOR_BG)
        self.p3.setYRange(0, 1, padding=0)

        # ── 윈도우별 히스토리 + 라벨 ────────────────────────
        # 행: quote(호가) / exec(체결)
        self._ts_hist = {
            w: {"quote": [], "exec": []} for w in WINDOWS
        }
        self._ts_bars = {
            w: {"quote": [], "exec": []} for w in WINDOWS
        }
        self._ts_labels = {}   # {w: {"quote": TextItem, "exec": TextItem}}
        self._ts_x = 0

        for w in WINDOWS:
            lbl_q = pg.TextItem(f"{w}s 호가 —", color=COLOR_DIM, anchor=(0, 1))
            lbl_e = pg.TextItem(f"{w}s 체결 —", color=COLOR_DIM, anchor=(0, 1))
            self.p3.addItem(lbl_q)
            self.p3.addItem(lbl_e)
            self._ts_labels[w] = {"quote": lbl_q, "exec": lbl_e}

        # 2초 타이머
        self._ts_timer = QTimer(self)
        self._ts_timer.timeout.connect(lambda: __import__('chart_tick_updater')._update(self))
        self._ts_timer.start(TIMER_MS)

    def stop_tick_speed(self):
        t = getattr(self, '_ts_timer', None)
        if t:
            t.stop()

else:
    def init_tick_speed(self): pass
    def stop_tick_speed(self): pass


