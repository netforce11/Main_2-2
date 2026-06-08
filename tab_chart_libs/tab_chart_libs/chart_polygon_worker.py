"""
chart_polygon_worker.py — Polygon WebSocket QThread
[분리] chart_workers.py 에서 분리
"""
import asyncio, json
from PyQt5.QtCore import QThread, pyqtSignal


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
                await ws.send(json.dumps({"action": "auth", "params": self.api_key}))
                await ws.send(json.dumps({"action": "subscribe", "params": f"AM.{self.symbol}"}))
                while self._run:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        for d in json.loads(raw):
                            if d.get('ev') == 'AM' and d.get('sym') == self.symbol:
                                self.data_received.emit(d)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
        except ImportError:
            print("[ChartTab] websockets 미설치 → pip install websockets")

    def stop(self):
        self._run = False
