"""
chart_exec_marker.py — 기능5: 체결 마커 오버레이
────────────────────────────────────────────────────────
· BUY  체결 → 캔들 저가 아래 ▲ 녹색 마커
· SELL 체결 → 캔들 고가 위  ▼ 적색 마커
· order_logic.py 체결 이벤트 → SignalBridge → 이 모듈로 흐름

외부 호출:
    from chart_exec_marker import (
        init_exec_markers, add_exec_marker,
        redraw_exec_markers, clear_exec_markers
    )

tab_chart.py __init__ 에서:
    self._exec_markers = []      # [(ts_epoch_ms, action, price), ...]
    init_exec_markers(self)

core.py SignalBridge 에 추가:
    exec_filled = pyqtSignal(int, str, float)
    # emit: (timestamp_ms, 'BUY'|'SELL', fill_price)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime

try:
    import pyqtgraph as pg
    import numpy as np
    PG = True
except ImportError:
    PG = False

# ── 설정 ─────────────────────────────────────────────────────
COLOR_BUY   = "#00e676"   # 녹색
COLOR_SELL  = "#ff1744"   # 적색
MARKER_SIZE = 12
OFFSET_PCT  = 0.003       # 캔들 고/저가 대비 오프셋 비율


def init_exec_markers(self):
    """ChartGrid.__init__ 에서 1회 호출."""
    self._exec_markers      = []   # [(ts_ms, action, price), ...]
    self._exec_marker_item  = None

    # SignalBridge 연결 (core.py 에 exec_filled 시그널 추가 필요)
    try:
        from core import bridge
        bridge.exec_filled.connect(
            lambda ts, act, px: add_exec_marker(self, ts, act, px))
    except AttributeError:
        # exec_filled 시그널이 아직 없으면 수동 add_exec_marker() 호출로 대체
        pass


def add_exec_marker(self, ts_ms: int, action: str, price: float):
    """
    체결 발생 시 호출.
    ts_ms  : 체결 시각 (epoch milliseconds)
    action : 'BUY' 또는 'SELL'
    price  : 체결가
    """
    self._exec_markers.append((ts_ms, action.upper(), float(price)))
    redraw_exec_markers(self)


def redraw_exec_markers(self):
    """차트 데이터(self.current_processed)와 매칭해 마커를 다시 그림."""
    if not PG:
        return

    clear_exec_markers(self)

    if not self._exec_markers or not getattr(self, 'current_processed', []):
        return

    # current_processed: [{'t':ms, 'o':, 'h':, 'l':, 'c':, 'v':}, ...]
    # t 기준으로 가장 가까운 봉에 마커 매핑
    proc = self.current_processed
    ts_list = [d.get('t', 0) for d in proc]

    buy_x,  buy_y  = [], []
    sell_x, sell_y = [], []

    # 차트 반전 상태 확인 (tab_chart._on_flip_chart 에서 설정)
    flipped = getattr(self, '_chart_flipped', False)

    for ts_ms, action, price in self._exec_markers:
        if not ts_list:
            break
        # 가장 가까운 봉 인덱스
        idx = int(np.argmin([abs(t - ts_ms) for t in ts_list]))
        bar = proc[idx]

        # x: 봉 인덱스 (캔들은 0,1,2,... 인덱스로 그려짐)
        x = idx
        lo = bar.get('l', bar.get('low',  price))
        hi = bar.get('h', bar.get('high', price))
        offset = (hi - lo) * 0.15 if (hi - lo) > 0 else price * OFFSET_PCT

        if action == 'BUY':
            buy_x.append(x)
            # 반전 시: 저가 아래 → 고가 위로 위치 변경
            buy_y.append(hi + offset if flipped else lo - offset)
        else:
            sell_x.append(x)
            # 반전 시: 고가 위 → 저가 아래로 위치 변경
            sell_y.append(lo - offset if flipped else hi + offset)

    items = []
    if buy_x:
        item_b = pg.ScatterPlotItem(
            x=buy_x, y=buy_y,
            symbol='t1',        # 위 방향 삼각형 ▲
            size=MARKER_SIZE,
            brush=pg.mkBrush(COLOR_BUY),
            pen=pg.mkPen(None))
        self.p1.addItem(item_b)
        items.append(item_b)

    if sell_x:
        item_s = pg.ScatterPlotItem(
            x=sell_x, y=sell_y,
            symbol='t',         # 아래 방향 삼각형 ▼
            size=MARKER_SIZE,
            brush=pg.mkBrush(COLOR_SELL),
            pen=pg.mkPen(None))
        self.p1.addItem(item_s)
        items.append(item_s)

    self._exec_marker_item = items


def clear_exec_markers(self):
    """마커 아이템만 제거 (데이터는 유지)."""
    for item in (self._exec_marker_item or []):
        try:
            self.p1.removeItem(item)
        except Exception:
            pass
    self._exec_marker_item = []


def load_exec_markers_from_db(self, date_str: str = None):
    """
    db_manager.py 연동: 과거 체결 이력 불러오기.
    date_str 없으면 오늘 날짜.
    """
    try:
        from db_manager import DBManager
        db  = DBManager.get()
        df  = db.fetch_pnl(date=date_str)
        if df is None or df.empty:
            return
        self._exec_markers = []
        for _, row in df.iterrows():
            try:
                dt = datetime.fromisoformat(row['ts'])
                ts_ms = int(dt.timestamp() * 1000)
                self._exec_markers.append(
                    (ts_ms, row['action'], float(row['price'])))
            except Exception:
                continue
        redraw_exec_markers(self)
    except Exception as e:
        print(f"[ExecMarker] DB 로드 실패: {e}")
