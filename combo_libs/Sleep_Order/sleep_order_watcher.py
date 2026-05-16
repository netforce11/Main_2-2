"""
sleep_order_watcher.py — 예약주문 감시 루프  v3.0
════════════════════════════════════════
QTimer(1초) → 시간 체크 → spike_scan.scan_and_check() 위임.
체인 스캔/주문 로직: Sleep_Order.spike_scan
"""
from __future__ import annotations
import threading
from typing import Optional
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from Sleep_Order.spike_utils import tg


class SleepOrderWatcher(QObject):
    status_changed = pyqtSignal(str)
    _inst: Optional["SleepOrderWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls, parent=None):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls); cls._inst = o
        return cls._inst

    def __init__(self, parent=None):
        if getattr(self, '_initialized', False): return
        super().__init__(parent)
        self._initialized = True
        self._ref = None; self._active = False; self._fired = False
        self._last_range_reset = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    @classmethod
    def get(cls) -> "SleepOrderWatcher":
        with cls._mu:
            if cls._inst is None:
                inst = super(SleepOrderWatcher, cls).__new__(cls)
                inst._initialized = False; cls._inst = inst; inst.__init__()
        return cls._inst

    def toggle(self, ref: object) -> bool:
        if self._active: self.stop(); return False
        self.start(ref); return True

    def start(self, ref: object) -> None:
        from Sleep_Order.sleep_order_config   import sleep_cfg
        from Sleep_Order.spike_watcher_debit  import DebitSpikeWatcher
        from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher
        self._ref = ref; self._active = True; self._fired = False; self._last_range_reset = 0.0
        DebitSpikeWatcher.get().reset_all()
        SingleOptSpikeWatcher.get().reset_all()
        if hasattr(ref, '_sleep_subscribe_chain'): ref._sleep_subscribe_chain()
        self.status_changed.emit(f"🟢 감시중  {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}")
        tg(f"🌙 감시 시작\n예약: {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}"
           f"  D+{sleep_cfg.expiry_offset}\n"
           f"Debit캐치: {'ON' if sleep_cfg.spike_enabled else 'OFF'}"
           f"  단일캐치: {'ON' if sleep_cfg.single_spike_enabled else 'OFF'}")
        self._timer.start()

    def stop(self, reason: str = "수동 중지") -> None:
        self._active = False; self._timer.stop()
        ref = getattr(self, '_ref', None)
        if ref and hasattr(ref, '_sleep_unsubscribe_chain'): ref._sleep_unsubscribe_chain()
        try:
            from Sleep_Order.spike_watcher_debit  import DebitSpikeWatcher
            from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher
            DebitSpikeWatcher.get().reset_all()
            SingleOptSpikeWatcher.get().reset_all()
        except Exception: pass
        self.status_changed.emit("🌙 예약 주문")
        print(f"[SleepWatcher] 종료: {reason}")

    @property
    def is_active(self) -> bool:
        return self._active

    def _tick(self) -> None:
        if not self._active: return
        from Sleep_Order.sleep_order_config import sleep_cfg
        in_win = self._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end)
        if not in_win:
            if self._fired: self.stop(reason="주문 완료 후 시간 종료")
            elif self._past_end(sleep_cfg.schedule_end):
                tg("⏰ 예약 시간 종료  미주문"); self.stop(reason="시간 초과 미주문")
            return
        if not self._fired:
            from Sleep_Order.spike_scan import scan_and_check
            scan_and_check(self)

    # ── 시간 유틸 ─────────────────────────────────────────
    @staticmethod
    def _now_et() -> tuple:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo; tz = ZoneInfo("America/New_York")
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.utcnow()
        return now.hour, now.minute

    def _in_window(self, start: str, end: str) -> bool:
        try:
            sh, sm = map(int, start.split(":")); eh, em = map(int, end.split(":"))
            h, m = self._now_et(); n = h*60+m; s = sh*60+sm; e = eh*60+em
            return (s <= n <= e) if s <= e else (n >= s or n <= e)
        except Exception: return False

    def _past_end(self, end: str) -> bool:
        try:
            from Sleep_Order.sleep_order_config import sleep_cfg
            sh, sm = map(int, sleep_cfg.schedule_start.split(":"))
            eh, em = map(int, end.split(":"))
            h, m = self._now_et(); n = h*60+m; s = sh*60+sm; e = eh*60+em
            if s <= e: return n > e
            return (n > e) if n < s else False
        except Exception: return False
