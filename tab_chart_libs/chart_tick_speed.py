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
        self._ts_timer.timeout.connect(lambda: _update(self))
        self._ts_timer.start(TIMER_MS)

    def stop_tick_speed(self):
        t = getattr(self, '_ts_timer', None)
        if t:
            t.stop()

else:
    def init_tick_speed(self): pass
    def stop_tick_speed(self): pass


def _update(self):
    """2초마다 호출 — 집계 + 라벨 갱신 + DB 저장."""
    if not PG:
        return

    now = time.time()
    _purge(now - max(WINDOWS) - 5)

    counts = {}
    for w in WINDOWS:
        qc = _count(_quote_times, w)   # 호가
        ec = _count(_tick_times,  w)   # 체결 (Last)
        counts[w] = {"quote": qc, "exec": ec}

        hist = self._ts_hist[w]
        hist["quote"].append(qc)
        hist["exec"].append(ec)
        if len(hist["quote"]) > HISTORY_LEN: hist["quote"].pop(0)
        if len(hist["exec"])  > HISTORY_LEN: hist["exec"].pop(0)

    x = self._ts_x
    self._ts_x += 1

    # ── 윈도우별 라벨 갱신 ──────────────────────────────────
    # y 위치: 호가=상단(0.68), 체결=하단(0.35)
    # x 위치: 10s=좌, 30s=중, 60s=우
    vr    = self.p3.getViewBox().viewRange()
    x_min = vr[0][0]
    x_span = max(vr[0][1] - vr[0][0], 1)
    col_w  = x_span / len(WINDOWS)

    for i, w in enumerate(WINDOWS):
        qc = counts[w]["quote"]
        ec = counts[w]["exec"]
        hist = self._ts_hist[w]

        q_color = _get_color(qc, hist["quote"])
        e_color = _get_color(ec, hist["exec"])
        q_ratio = _ratio_str(qc, hist["quote"])
        e_ratio = _ratio_str(ec, hist["exec"])

        lx = x_min + col_w * i + col_w * 0.02
        lbl = self._ts_labels[w]

        # 호가: 상단, 체결: 하단
        lbl["quote"].setText(f"{w}s 호가 {qc:>3} {q_ratio}", color=q_color)
        lbl["exec"].setText( f"{w}s 체결 {ec:>3} {e_ratio}", color=e_color)
        lbl["quote"].setPos(lx, 1.0)
        lbl["exec"].setPos( lx, 0.5)

        # 히스토리 바: 10s 윈도우만 (호가=상단 절반, 체결=하단 절반)
        if w == 10:
            if qc > 0:
                b = pg.BarGraphItem(x=[x], height=[0.44], width=0.8,
                                     y0=0.55, brush=q_color, pen=pg.mkPen(None))
                self.p3.addItem(b)
                self._ts_bars[w]["quote"].append(b)
            if ec > 0:
                b2 = pg.BarGraphItem(x=[x], height=[0.44], width=0.8,
                                      y0=0.05, brush=e_color, pen=pg.mkPen(None))
                self.p3.addItem(b2)
                self._ts_bars[w]["exec"].append(b2)
            _trim_bars(self.p3, self._ts_bars[w]["quote"], HISTORY_LEN)
            _trim_bars(self.p3, self._ts_bars[w]["exec"],  HISTORY_LEN)

    # ── DB 저장 ───────────────────────────────────────────────
    _save_to_db(counts)


def _save_to_db(counts: dict):
    """tick_speed 테이블에 현재 집계값 저장."""
    try:
        from db_manager import DBManager
        db = DBManager.get()
        db.insert_tick_speed(
            symbol    = _current_sym or "UNKNOWN",
            w10_tick  = counts[10]["exec"],
            w10_quote = counts[10]["quote"],
            w30_tick  = counts[30]["exec"],
            w30_quote = counts[30]["quote"],
            w60_tick  = counts[60]["exec"],
            w60_quote = counts[60]["quote"],
        )
    except Exception:
        pass   # DB 미연결 시 조용히 패스


def _trim_bars(plot, bar_list: list, max_len: int):
    while len(bar_list) > max_len:
        try:
            plot.removeItem(bar_list.pop(0))
        except Exception:
            bar_list.pop(0) if bar_list else None