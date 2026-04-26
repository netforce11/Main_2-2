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
    """
    v2: keepUpToDate=True 방식으로 전환.
    ─ 최초 start() 시 reqHistoricalData 1회만 호출
    ─ historicalData      → hist_bar        → 과거 봉 초기 로드
    ─ historicalDataUpdate → hist_bar_update → 실시간 봉 push
    ─ 5초 타이머는 watchdog 용도로만 유지
      (TWS 끊김 감지 → 자동 재구독)
    """
    bar_updated = pyqtSignal(dict)

    _WATCHDOG_MS = 10_000   # 10초마다 연결 상태 확인

    def __init__(self, ib, symbol, parent=None):
        super().__init__(parent)
        self.ib          = ib
        self.symbol      = symbol
        self._rid        = REQ_HIST
        self._subscribed = False
        self._last_bar_t = 0    # 마지막 바 수신 시각 (epoch)

        # hist_bar       → 과거 봉 (historicalData 콜백)
        # hist_bar_update → 실시간 봉 (historicalDataUpdate 콜백)
        bridge.hist_bar.connect(self._on_bar)
        bridge.hist_bar_update.connect(self._on_bar_update)

        # watchdog 타이머
        self.timeout.connect(self._watchdog)

    def start(self, msec=None):
        """최초 구독 시작."""
        self._subscribe()
        super().start(self._WATCHDOG_MS)

    def _subscribe(self):
        if not self.ib or not hasattr(self.ib, 'reqHistoricalData'):
            return
        c = make_und_contract(self.symbol)
        # keepUpToDate=True → 과거 봉 수신 후 실시간 업데이트 자동 push
        self.ib.reqHistoricalData(
            self._rid, c, "", "3600 S", "1 min", "TRADES",
            1,    # useRTH
            1,    # formatDate
            True, # keepUpToDate ← 핵심
            [])
        self._subscribed = True
        print(f"[IBKRBarTimer] {self.symbol} 구독 시작 rid={self._rid}")

    def _watchdog(self):
        """10초마다 마지막 바 수신 시각 확인 → 30초 침묵 시 재구독."""
        import time
        if not self._subscribed:
            return
        if self._last_bar_t and (time.time() - self._last_bar_t) > 30:
            print(f"[IBKRBarTimer] 30초 침묵 → 재구독")
            try:
                self.ib.cancelHistoricalData(self._rid)
            except Exception:
                pass
            self._subscribe()

    def _parse_bar(self, rid, bar) -> dict | None:
        """
        bridge emit 포맷 (dict):
          {"date": "20260424  09:31:00",
           "open": 5200.0, "high": ..., "low": ..., "close": ..., "volume": ...}
        → chart_data.py 가 쓰는 포맷:
          {"t": epoch_ms, "o":, "h":, "l":, "c":, "v":}
        """
        if rid != self._rid:
            return None
        try:
            dt = datetime.strptime(bar["date"], "%Y%m%d  %H:%M:%S")
            return {
                "t": int(dt.timestamp() * 1000),
                "o": bar["open"],
                "h": bar["high"],
                "l": bar["low"],
                "c": bar["close"],
                "v": bar["volume"],
            }
        except Exception as e:
            print(f"[IBKRBarTimer] _parse_bar 실패: {e}")
            return None

    def _on_bar(self, rid, bar):
        """historicalData → 과거 봉 (초기 로드)."""
        import time
        d = self._parse_bar(rid, bar)
        if d:
            self._last_bar_t = time.time()
            self.bar_updated.emit(d)

    def _on_bar_update(self, rid, bar):
        """historicalDataUpdate → 실시간 봉 push."""
        import time
        d = self._parse_bar(rid, bar)
        if d:
            self._last_bar_t = time.time()
            self.bar_updated.emit(d)

    def stop(self):
        try:
            bridge.hist_bar.disconnect(self._on_bar)
        except Exception:
            pass
        try:
            bridge.hist_bar_update.disconnect(self._on_bar_update)
        except Exception:
            pass
        try:
            if self._subscribed and self.ib:
                self.ib.cancelHistoricalData(self._rid)
                self._subscribed = False
        except Exception:
            pass
        super().stop()
        print(f"[IBKRBarTimer] {self.symbol} 구독 해제")