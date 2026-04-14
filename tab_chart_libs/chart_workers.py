"""
chart_workers.py — 캔들스틱 아이템 + 실시간 데이터 워커
────────────────────────────────────────────────────────
포함:
  CandlestickItem  — pyqtgraph 캔들 렌더링
  PolygonWorker    — Polygon WebSocket QThread
  IBKRBarTimer     — IBKR reqHistoricalData 타이머
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


import asyncio, json
from datetime import datetime

from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPicture, QPainter, QColor

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import bridge, make_und_contract, REQ_HIST


if PG:
    class CandlestickItem(pg.GraphicsObject):
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
                p.drawLine(pg.QtCore.QPointF(t, lo), pg.QtCore.QPointF(t, hi))
                p.drawRect(pg.QtCore.QRectF(t - 0.3, o, 0.6, c - o))
            p.end()

        def paint(self, p, *a):
            p.drawPicture(0, 0, self.picture)

        def boundingRect(self):
            return pg.QtCore.QRectF(self.picture.boundingRect())


class PolygonWorker(QThread):
    data_received = pyqtSignal(dict)

    def __init__(self, api_key, symbol):
        super().__init__()
        self.api_key = api_key
        self.symbol  = symbol.upper()
        self._run    = True

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception:
            pass

    async def _main(self):
        try:
            import websockets
            uri = "wss://socket.polygon.io/stocks"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"action": "auth",
                                          "params": self.api_key}))
                await ws.send(json.dumps({"action": "subscribe",
                                          "params": f"AM.{self.symbol}"}))
                while self._run:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        for d in json.loads(raw):
                            if (d.get('ev') == 'AM'
                                    and d.get('sym') == self.symbol):
                                self.data_received.emit(d)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
        except ImportError:
            print("[ChartTab] websockets 미설치 → pip install websockets")

    def stop(self):
        self._run = False


class IBKRBarTimer(QTimer):
    bar_updated = pyqtSignal(dict)

    def __init__(self, ib, symbol, parent=None):
        super().__init__(parent)
        self.ib     = ib
        self.symbol = symbol
        self._rid   = REQ_HIST
        self.timeout.connect(self._fetch)
        bridge.hist_bar.connect(self._on_bar)

    def _fetch(self):
        if not self.ib or not hasattr(self.ib, 'reqHistoricalData'):
            return
        c = make_und_contract(self.symbol)
        self.ib.reqHistoricalData(
            self._rid, c, "", "3600 S", "1 min", "TRADES", 1, 1, True, [])

    def _on_bar(self, rid, bar):
        if rid != self._rid:
            return
        try:
            dt = datetime.strptime(bar.date, "%Y%m%d  %H:%M:%S")
            self.bar_updated.emit({
                "t": int(dt.timestamp() * 1000),
                "o": bar.open, "h": bar.high,
                "l": bar.low,  "c": bar.close, "v": bar.volume})
        except Exception:
            pass

    def stop(self):
        try:
            bridge.hist_bar.disconnect(self._on_bar)
        except Exception:
            pass
        super().stop()
