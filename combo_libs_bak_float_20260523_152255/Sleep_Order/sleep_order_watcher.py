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
        self._scanning = False   # [FIX-REENTRANT] 재진입 방어 플래그
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
        self._ref = ref; self._active = True
        self._fired = False          # 단방향(put_only/call_only) 및 호환용
        self._put_fired  = False     # both 모드 — 풋 발사 완료
        self._call_fired = False     # both 모드 — 콜 발사 완료
        self._last_range_reset = 0.0
        self._scanning = False       # [FIX-REENTRANT]
        DebitSpikeWatcher.get().reset_all()
        SingleOptSpikeWatcher.get().reset_all()
        if hasattr(ref, '_sleep_subscribe_chain'): ref._sleep_subscribe_chain()
        self.status_changed.emit(f"🟢 감시중  {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}")
        _d   = sleep_cfg.combo_direction
        _sym = ""
        try:
            from Sleep_Order.spike_scan import _get_symbol
            _sym = _get_symbol(self._ref) if self._ref else ""
        except Exception:
            pass
        _sym_label = f"[{_sym}] " if _sym else ""
        if _d == "both":
            _pri = getattr(sleep_cfg, 'primary_direction', 'put')
            _sec_tp = getattr(sleep_cfg, 'secondary_target_price', 0.65)
            _pri_label = "풋 기준" if _pri == "put" else "콜 기준"
            tg(f"🌙 감시 시작  {_sym_label}\n"
               f"예약: {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}  D+{sleep_cfg.expiry_offset}\n"
               f"────────────────────\n"
               f"📈 콜 예산: ${sleep_cfg.combo_call_budget:,}  목표 ≤${sleep_cfg.call_target_price:.2f}\n"
               f"📉 풋 예산: ${sleep_cfg.combo_put_budget:,}  목표 ≤${sleep_cfg.target_price_1:.2f}\n"
               f"🔀 조건B: 선호={_pri_label}  반대쪽 허용 ≤${_sec_tp:.2f}\n"
               f"Debit캐치: {'ON' if sleep_cfg.spike_enabled else 'OFF'}"
               f"  단일캐치: {'ON' if sleep_cfg.single_spike_enabled else 'OFF'}")
        elif _d == "call_only":
            tg(f"🌙 감시 시작  {_sym_label}\n"
               f"예약: {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}  D+{sleep_cfg.expiry_offset}\n"
               f"────────────────────\n"
               f"📈 콜 방향만  예산: ${sleep_cfg.combo_call_budget:,}  목표 ≤${sleep_cfg.call_target_price:.2f}\n"
               f"Debit캐치: {'ON' if sleep_cfg.spike_enabled else 'OFF'}"
               f"  단일캐치: {'ON' if sleep_cfg.single_spike_enabled else 'OFF'}")
        else:  # put_only
            tg(f"🌙 감시 시작  {_sym_label}\n"
               f"예약: {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}  D+{sleep_cfg.expiry_offset}\n"
               f"────────────────────\n"
               f"📉 풋 방향만  예산: ${sleep_cfg.combo_put_budget:,}  목표 ≤${sleep_cfg.target_price_1:.2f}\n"
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

    def on_price_update(self, ref, net_price: float) -> None:
        """[EVENT-DRIVEN] 체인 가격 업데이트 시 즉시 scan_and_check 호출.
        1초 폴링 대기 없이 틱 수신 즉시 조건 체크.
        ref가 현재 감시 중인 ref와 다르면 무시.
        """
        if not self._active:
            return
        if ref is not self._ref:
            return
        from Sleep_Order.sleep_order_config import sleep_cfg
        if not self._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end):
            return
        if sleep_cfg.combo_direction == "both":
            if self._put_fired and self._call_fired:
                return
        else:
            if self._fired:
                return
        from Sleep_Order.spike_scan import scan_and_check
        scan_and_check(self)

    def _tick(self) -> None:
        if not self._active: return
        from Sleep_Order.sleep_order_config import sleep_cfg
        in_win = self._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end)
        if not in_win:
            if sleep_cfg.combo_direction == "both":
                any_fired = self._put_fired or self._call_fired
                if any_fired:
                    # 어느 쪽이 체결됐는지 구분해서 메시지
                    if self._put_fired and self._call_fired:
                        tg("✅ [조건B] 양방향 체결 완료 후 시간 종료")
                    elif self._put_fired:
                        tg("⚠️ [조건B] 시간 종료\n"
                           "풋 ✅ 체결  |  콜 ❌ 보조조건 미달로 미체결\n"
                           "🚨 풋 포지션 단독 보유 중 — 수동 확인 필요")
                    else:
                        tg("⚠️ [조건B] 시간 종료\n"
                           "콜 ✅ 체결  |  풋 ❌ 보조조건 미달로 미체결\n"
                           "🚨 콜 포지션 단독 보유 중 — 수동 확인 필요")
                    self.stop(reason="주문 완료 후 시간 종료")
                elif self._past_end(sleep_cfg.schedule_end):
                    tg("⏰ [조건B] 예약 시간 종료  양방향 조건 미충족 — 미주문")
                    self.stop(reason="시간 초과 미주문")
            else:
                if self._fired: self.stop(reason="주문 완료 후 시간 종료")
                elif self._past_end(sleep_cfg.schedule_end):
                    tg("⏰ 예약 시간 종료  미주문"); self.stop(reason="시간 초과 미주문")
            return
        # both 모드: 풋/콜 각각 독립 — 둘 다 완료됐을 때만 스캔 중단
        if sleep_cfg.combo_direction == "both":
            if self._put_fired and self._call_fired:
                return
        else:
            if self._fired:
                return
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