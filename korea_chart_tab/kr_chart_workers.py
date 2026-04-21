"""
kr_chart_workers.py — 캔들스틱 아이템 + 실시간 폴링 타이머
────────────────────────────────────────────────────────
포함:
  CandlestickItem — pyqtgraph 캔들 렌더링
  KrBarTimer      — opt10080 주기적 갱신 타이머

KrBarTimer 동작:
  - QTimer 기반 (interval_ms 마다 opt10080 요청)
  - 최신 봉 데이터(records) 수신 시 bar_updated(list) 시그널 emit
  - stop() 시 타이머 정지 및 시그널 disconnect
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import date, datetime, timedelta

from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPicture, QPainter, QColor

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None


# ── CandlestickItem ──────────────────────────────────────────

if PG:
    class CandlestickItem(pg.GraphicsObject):
        """pyqtgraph 캔들스틱 아이템."""

        def __init__(self, data, up="#3c78ff", dn="#ff3c3c"):
            pg.GraphicsObject.__init__(self)
            self.data = data; self.up = up; self.dn = dn
            self._gen()

        def _gen(self):
            self.picture = QPicture()
            p = QPainter(self.picture)
            for t, o, c, lo, hi in self.data:
                col = QColor(self.up if c >= o else self.dn)
                p.setPen(pg.mkPen(col, width=1))
                p.setBrush(pg.mkBrush(col))
                p.drawLine(
                    pg.QtCore.QPointF(t, lo),
                    pg.QtCore.QPointF(t, hi))
                p.drawRect(
                    pg.QtCore.QRectF(t - 0.3, o, 0.6, c - o))
            p.end()

        def paint(self, p, *a):
            p.drawPicture(0, 0, self.picture)

        def boundingRect(self):
            return pg.QtCore.QRectF(self.picture.boundingRect())

else:
    class CandlestickItem:   # fallback stub
        def __init__(self, *a, **kw): pass


# ── KrBarTimer ───────────────────────────────────────────────

class KrBarTimer(QObject):
    """
    opt10080 TR을 주기적으로 호출해 최신 분봉 데이터를 갱신.

    Parameters
    ----------
    parent_grid : KoreaChartGrid
        ChartGrid 인스턴스 (kiwoom, sym_in 등 보유)
    symbol : str
        종목코드 6자리
    interval_ms : int
        갱신 주기 (밀리초), 기본 10000 (10초)
    """

    bar_updated = pyqtSignal(list)   # 갱신된 records 리스트 전달

    def __init__(self, parent_grid, symbol: str, interval_ms: int = 10000):
        super().__init__()
        self._grid       = parent_grid
        self.symbol      = symbol.zfill(6)
        self.interval_ms = max(interval_ms, 5000)   # 최소 5초
        self._timer      = QTimer()
        self._timer.timeout.connect(self._fetch)

    def start(self):
        self._fetch()                       # 즉시 1회 실행
        self._timer.start(self.interval_ms)

    def stop(self):
        self._timer.stop()

    def _fetch(self):
        """opt10080 1회 요청 → 오늘 날짜 데이터 수신 → emit."""
        try:
            from kr_chart_kiwoom import download_opt10080
            tgt = date.today()
            records, _, _ = download_opt10080(self._grid, self.symbol, tgt)
            if records:
                self.bar_updated.emit(records)
        except Exception as ex:
            print(f"[KrBarTimer] 조회 오류: {ex}")
