"""
chain_spike_monitor.py — 옵션 체인 급변 감시 엔진  v1.0
════════════════════════════════════════════════════════
목적:
  지정 시간(예: 1112~1118) 동안, 지정 행사가 3~4개의
  옵션 프리미엄을 N초 간격으로 스냅샷 → 직전 대비
  ① N틱 이상 변동  or  ② X% 이상 변동 시 감지·로그 저장.

흐름:
  start() → QTimer(N초) → _tick_snapshot()
    → 각 행사가별 현재가 조회 (_chain_put / _chain_call)
    → 직전 스냅샷과 비교
    → 조건 충족 → 이벤트 레코드 생성
    → on_event 콜백 (UI) + 로그 파일 append

로그 파일:
  {log_dir}/chain_spike_{YYYYMMDD}.csv
  컬럼: time_et, strike, cp, prev, curr, tick_delta,
         pct_change, ref_pct, trigger
"""
from __future__ import annotations
import os
import csv
import threading
import time as _time
from datetime import datetime
from typing import Optional, Callable

try:
    from zoneinfo import ZoneInfo
    _TZ_ET = ZoneInfo("America/New_York")
except Exception:
    _TZ_ET = None


def _now_et() -> datetime:
    if _TZ_ET:
        return datetime.now(_TZ_ET)
    return datetime.utcnow()


def _hhmm_to_minutes(hhmm) -> int:
    """'1112' or 1112 or '11:12' → 분(int) 671."""
    s = str(hhmm).replace(":", "").strip()
    if len(s) == 3: s = "0" + s
    if len(s) != 4: return 0
    return int(s[:2]) * 60 + int(s[2:])


# 틱 사이즈 (SPX 기준)
def _tick_size(price: float) -> float:
    return 0.01 if price < 3.0 else 0.05


class SpikeEvent:
    """급변 감지 1건."""
    __slots__ = ("time_str", "strike", "cp", "prev", "curr",
                 "tick_delta", "pct_change", "ref_pct", "trigger")

    def __init__(self, time_str, strike, cp, prev, curr,
                 tick_delta, pct_change, ref_pct, trigger):
        self.time_str   = time_str
        self.strike     = strike
        self.cp         = cp
        self.prev       = prev
        self.curr       = curr
        self.tick_delta = tick_delta
        self.pct_change = pct_change
        self.ref_pct    = ref_pct
        self.trigger    = trigger   # "TICK" | "PCT" | "BOTH"


class ChainSpikeMonitor:
    """싱글톤 급변 감시 엔진."""

    _inst: Optional["ChainSpikeMonitor"] = None
    _mu   = threading.Lock()

    def __new__(cls):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                o._initialized = False
                cls._inst = o
        return cls._inst

    @classmethod
    def get(cls) -> "ChainSpikeMonitor":
        return cls()

    def __init__(self):
        if getattr(self, '_initialized', False): return
        self._initialized = True
        self._active      = False
        self._ref         = None
        self._lock        = threading.Lock()

        # 설정값 (UI에서 주입)
        self.start_hhmm   = "1112"     # 시작 시각
        self.end_hhmm     = "1118"     # 종료 시각
        self.tick_interval = 3         # 스냅샷 간격(초)
        self.strikes_put: list[float]  = []   # 감시 풋 행사가
        self.strikes_call: list[float] = []   # 감시 콜 행사가
        self.min_tick_delta = 3        # N틱 이상 변동 조건
        self.min_pct_change = 15.0     # X% 이상 변동 조건
        self.ref_pct_window = 5        # 기준가 비교 스냅샷 수 (N스냅샷 전 대비)
        self.log_dir        = os.path.expanduser("~/chain_spike_logs")
        self.dry_log        = False    # True 면 파일 저장 안 함

        # 내부 상태
        self._snapshots: dict[tuple, list[float]] = {}  # (strike,cp) → 가격 히스토리
        self._timer: Optional[threading.Timer] = None
        self._end_timer: Optional[threading.Timer] = None

        # 콜백
        self.on_event:  Optional[Callable[[SpikeEvent], None]] = None
        self.on_status: Optional[Callable[[str], None]]        = None

    # ── 공개 API ─────────────────────────────────────────────────

    def start(self, ref: object) -> bool:
        with self._lock:
            if self._active: return False
            self._active = True
            self._ref    = ref
            self._snapshots.clear()

        os.makedirs(self.log_dir, exist_ok=True)
        sym = self._sym()
        msg = (f"⚡ 급변 감시 시작  {sym}\n"
               f"시간: {self.start_hhmm}~{self.end_hhmm}  "
               f"간격: {self.tick_interval}초\n"
               f"풋 행사가: {self.strikes_put}  "
               f"콜 행사가: {self.strikes_call}\n"
               f"조건: {self.min_tick_delta}틱 or {self.min_pct_change}%")
        self._set_status(f"⚡ 감시중  {self.start_hhmm}~{self.end_hhmm}")
        self._log_info(msg)
        self._schedule_next()
        # [FIX] 시작 직후 즉시 상태 갱신 (시간 윈도우 전이면 대기 메시지)
        now_et  = _now_et()
        now_min = now_et.hour * 60 + now_et.minute
        start_m = _hhmm_to_minutes(self.start_hhmm)
        end_m   = _hhmm_to_minutes(self.end_hhmm)
        if now_min < start_m:
            remain_m = start_m - now_min
            self._set_status(
                f"⏳ 감시 등록됨 — {self.start_hhmm} 까지 {remain_m}분 대기"
                f"  (현재 ET {now_et.strftime('%H:%M')})")
        elif now_min > end_m:
            self._set_status(f"⚠ 감시 시간({self.start_hhmm}~{self.end_hhmm}) 이미 종료 — 내일 적용")
        # 종료 타이머 설정
        end_min = _hhmm_to_minutes(self.end_hhmm)
        now_min = _now_et().hour * 60 + _now_et().minute
        remain  = max(0, (end_min - now_min) * 60)
        self._end_timer = threading.Timer(remain + 60, self._on_timeout)
        self._end_timer.daemon = True
        self._end_timer.start()
        return True

    def stop(self, reason: str = "수동 중지") -> None:
        with self._lock:
            if not self._active: return
            self._active = False
        self._cancel_timers()
        self._set_status(f"⏹ 종료 ({reason})")
        self._log_info(f"⏹ 급변 감시 종료: {reason}")

    def is_active(self) -> bool:
        return self._active

    def reconfigure(self, **kwargs) -> None:
        """UI에서 설정값 일괄 주입."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    # ── 스냅샷 루프 ──────────────────────────────────────────────

    def _schedule_next(self) -> None:
        t = threading.Timer(self.tick_interval, self._tick_snapshot)
        t.daemon = True; t.start()
        with self._lock:
            self._timer = t

    def _tick_snapshot(self) -> None:
        if not self._active: return

        now    = _now_et()
        now_m  = now.hour * 60 + now.minute
        start_m = _hhmm_to_minutes(self.start_hhmm)
        end_m   = _hhmm_to_minutes(self.end_hhmm)

        # 시간 윈도우 체크
        if not (start_m <= now_m <= end_m):
            if now_m > end_m:
                self._on_timeout()
            else:
                # [FIX] 시작 전 — 남은 시간 표시 후 계속 대기
                remain = (start_m - now_m)
                self._set_status(
                    f"⏳ 감시 대기중  {self.start_hhmm} 까지 {remain}분 남음"
                    f"  (현재 ET {now.strftime('%H:%M')})")
                if self._active: self._schedule_next()
            return

        ref = self._ref
        if ref is None:
            if self._active: self._schedule_next()
            return

        chain_put  = getattr(ref, '_chain_put',  {})
        chain_call = getattr(ref, '_chain_call', {})
        time_str   = now.strftime("%H:%M:%S")

        # [BUG-C FIX] 체인 비어있으면 구독 재요청
        if not chain_put and not chain_call:
            try:
                if hasattr(ref, '_sleep_get_chain'):
                    ref._sleep_get_chain()
                self._set_status("🔄 체인 구독 재요청...")
            except Exception:
                pass

        # 풋 행사가 스캔
        hit = 0
        for st in self.strikes_put:
            price = float(chain_put.get(st) or 0)
            if price > 0:
                self._evaluate(time_str, st, "P", price); hit += 1

        # 콜 행사가 스캔
        for st in self.strikes_call:
            price = float(chain_call.get(st) or 0)
            if price > 0:
                self._evaluate(time_str, st, "C", price); hit += 1

        if hit == 0 and self._active:
            self._set_status(
                f"⚡ 감시중 — 가격 대기 "
                f"(P:{len(chain_put)}행사가 C:{len(chain_call)}행사가 수신)")

        if self._active:
            self._schedule_next()

    def _evaluate(self, time_str: str, strike: float,
                  cp: str, curr: float) -> None:
        key = (strike, cp)
        hist = self._snapshots.setdefault(key, [])
        hist.append(curr)

        if len(hist) < 2: return   # 최초 수신 — 비교 불가

        prev = hist[-2]
        if prev <= 0: return

        # 틱 델타
        tick      = _tick_size(prev)
        tick_delta = round(abs(curr - prev) / tick)
        pct_change = (curr - prev) / prev * 100.0

        # 기준가 대비 변동 (N스냅샷 전)
        ref_price = hist[-(self.ref_pct_window + 1)] if len(hist) > self.ref_pct_window else hist[0]
        ref_pct   = (curr - ref_price) / ref_price * 100.0 if ref_price > 0 else 0.0

        # 조건 평가
        hit_tick = tick_delta >= self.min_tick_delta
        hit_pct  = abs(pct_change) >= self.min_pct_change

        if not hit_tick and not hit_pct: return

        trigger = ("BOTH" if hit_tick and hit_pct
                   else "TICK" if hit_tick else "PCT")

        ev = SpikeEvent(
            time_str=time_str,
            strike=strike, cp=cp,
            prev=prev, curr=curr,
            tick_delta=int(tick_delta),
            pct_change=round(pct_change, 2),
            ref_pct=round(ref_pct, 2),
            trigger=trigger,
        )
        self._emit_event(ev)

    def _emit_event(self, ev: SpikeEvent) -> None:
        # UI 콜백
        if self.on_event:
            try: self.on_event(ev)
            except Exception: pass
        # 로그 파일
        self._write_log(ev)

    # ── 로그 파일 ────────────────────────────────────────────────

    def _write_log(self, ev: SpikeEvent) -> None:
        if self.dry_log: return
        try:
            date_str  = _now_et().strftime("%Y%m%d")
            path      = os.path.join(self.log_dir,
                                     f"chain_spike_{date_str}.csv")
            is_new    = not os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if is_new:
                    w.writerow(["time_et", "strike", "cp",
                                "prev", "curr", "tick_delta",
                                "pct_change", "ref_pct", "trigger"])
                w.writerow([
                    ev.time_str, ev.strike, ev.cp,
                    f"{ev.prev:.2f}", f"{ev.curr:.2f}",
                    ev.tick_delta,
                    f"{ev.pct_change:+.2f}",
                    f"{ev.ref_pct:+.2f}",
                    ev.trigger,
                ])
        except Exception as e:
            print(f"[ChainSpikeMonitor] 로그 저장 실패: {e}")

    def _log_info(self, msg: str) -> None:
        """감시 시작/종료 정보를 로그 파일 상단에 기록."""
        if self.dry_log: return
        try:
            date_str = _now_et().strftime("%Y%m%d")
            path     = os.path.join(self.log_dir,
                                    f"chain_spike_{date_str}.csv")
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([f"# {_now_et().strftime('%H:%M:%S')} {msg}"])
        except Exception:
            pass

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _on_timeout(self) -> None:
        if not self._active: return
        self.stop(reason="시간 종료")

    def _cancel_timers(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel(); self._timer = None
            if self._end_timer:
                self._end_timer.cancel(); self._end_timer = None

    def _set_status(self, msg: str) -> None:
        if self.on_status:
            try: self.on_status(msg)
            except Exception: pass

    def _sym(self) -> str:
        try:
            from Sleep_Order.spike_scan import _get_symbol
            return _get_symbol(self._ref) if self._ref else "SPX"
        except Exception:
            return "SPX"