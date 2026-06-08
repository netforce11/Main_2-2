"""
chart_ibkr_bar_timer.py — IBKR keepUpToDate 실시간 바 타이머
[분리] chart_workers.py 에서 분리
"""
import time
from datetime import datetime

from PyQt5.QtCore import QTimer, pyqtSignal
from core import bridge, make_und_contract, REQ_HIST


class IBKRBarTimer(QTimer):
    """
    keepUpToDate=True 방식.
    - start() 에서 bridge 시그널 연결 (중복 방지)
    - 10초 watchdog: 30초 침묵 시 자동 재구독
    """
    bar_updated = pyqtSignal(dict)
    _WATCHDOG_MS = 10_000

    def __init__(self, ib, symbol, parent=None):
        super().__init__(parent)
        self.ib                = ib
        self.symbol            = symbol
        self._rid              = REQ_HIST
        self._subscribed       = False
        self._last_bar_t       = 0
        self._bridge_connected = False
        self.timeout.connect(self._watchdog)

    def start(self, msec=None):
        if not self._bridge_connected:
            bridge.hist_bar.connect(self._on_bar)
            bridge.hist_bar_update.connect(self._on_bar_update)
            self._bridge_connected = True
        self._subscribe()
        super().start(self._WATCHDOG_MS)

    def _subscribe(self):
        if not self.ib or not hasattr(self.ib, 'reqHistoricalData'):
            return
        c = make_und_contract(self.symbol)
        self.ib.reqHistoricalData(
            self._rid, c, "", "3600 S", "1 min", "TRADES", 1, 1, True, [])
        self._subscribed = True
        print(f"[IBKRBarTimer] {self.symbol} 구독 시작 rid={self._rid}")

    def _watchdog(self):
        if not self._subscribed:
            return
        if self._last_bar_t and (time.time() - self._last_bar_t) > 30:
            print("[IBKRBarTimer] 30초 침묵 → 재구독")
            try: self.ib.cancelHistoricalData(self._rid)
            except Exception: pass
            self._subscribe()

    def _parse_bar(self, rid, bar):
        if rid != self._rid:
            return None
        try:
            dt = datetime.strptime(bar["date"], "%Y%m%d  %H:%M:%S")
            return {"t": int(dt.timestamp() * 1000),
                    "o": bar["open"], "h": bar["high"],
                    "l": bar["low"],  "c": bar["close"], "v": bar["volume"]}
        except Exception as e:
            print(f"[IBKRBarTimer] _parse_bar 실패: {e}")
            return None

    def _on_bar(self, rid, bar):
        d = self._parse_bar(rid, bar)
        if d:
            self._last_bar_t = time.time()
            self.bar_updated.emit(d)

    def _on_bar_update(self, rid, bar):
        d = self._parse_bar(rid, bar)
        if d:
            self._last_bar_t = time.time()
            self.bar_updated.emit(d)

    def stop(self):
        try: bridge.hist_bar.disconnect(self._on_bar)
        except Exception: pass
        try: bridge.hist_bar_update.disconnect(self._on_bar_update)
        except Exception: pass
        try:
            if self._subscribed and self.ib:
                self.ib.cancelHistoricalData(self._rid)
                self._subscribed = False
        except Exception: pass
        super().stop()
        print(f"[IBKRBarTimer] {self.symbol} 구독 해제")
