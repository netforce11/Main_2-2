"""greeks_snapshot_mgr.py — IBKR 스냅샷 요청 관리  S12-patch2
BUG-2: 0DTE 콜/풋 rid 카운터 분리  BUG-7: queue_done 마지막 슬롯만 발송

S12-patch2 수정:
  [CRITICAL-1] REQ_0DTE 블록을 core.py REQ_CHAIN(4000~4399)과 충돌하지 않도록
               10000번대로 이동. router 등록 범위도 동일하게 변경.
               (기존 4000~4399는 tab_greeks_fetch.fetch()가 사용하는 REQ_CHAIN 범위와 동일해
                두 경로가 같은 reqId를 요청 → 충돌 및 저장 누락 발생)
  [CRITICAL-2] _request_snapshot()에서 tag=""로 하드코딩된 부분 수정.
               SPX/SPXW는 만기 요일 기반으로 tradingClass 자동 계산.
  [BUG]        _next_bday()가 주말만 건너뛰고 공휴일 미처리 → is_trading_day() 사용.
  [THREAD]     record_received()가 EClient 스레드에서 직접 _notify() 호출 →
               QMetaObject.invokeMethod로 메인 스레드 마샬링.
  [LEAK]       stop()에서 router option 슬롯 unregister 추가.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QTimer, QMetaObject, Qt, Q_ARG, pyqtSlot, QObject

log = logging.getLogger(__name__)

# ── reqId 블록 (core.py REQ_CHAIN 4000~4399와 완전히 분리) ──────────────────
# 기존: 0DTE=4000~4399 → core.REQ_CHAIN과 충돌
# 수정: 0DTE=10000~10399, 1DTE=11000~11799, 2DTE=12000~12799
REQ_0DTE_C_BASE = 10000; REQ_0DTE_P_BASE = 10200; REQ_0DTE_RANGE = 200
REQ_1DTE_C_BASE = 11000; REQ_1DTE_P_BASE = 11400; REQ_1DTE_RANGE = 400
REQ_2DTE_C_BASE = 12000; REQ_2DTE_P_BASE = 12400; REQ_2DTE_RANGE = 400

PACING_DELAY_MS = 22        # 초당 45개 (22ms 간격)
SNAP_1DTE_MS    = 60_000    # +1DTE 갱신 주기: 1분
SNAP_2DTE_MS    = 120_000   # +2DTE 갱신 주기: 2분

StatusFn = Optional[Callable[[int, str, int, str], None]]


class SnapshotManager(QObject):
    """만기별 IBKR 스냅샷/스트리밍 요청 관리."""

    def __init__(self, ib, make_contract_fn, on_data_fn, on_status_fn: StatusFn = None):
        super().__init__()   # QObject 초기화 (invokeMethod 사용을 위해 필요)
        self._ib        = ib
        self._make_con  = make_contract_fn
        self._on_data   = on_data_fn
        self._on_status = on_status_fn
        self._req_map: Dict[int, Tuple[str, float, str]] = {}
        self._streaming_rids: Set[int] = set()
        self._t1 = QTimer(); self._t1.setInterval(SNAP_1DTE_MS)
        self._t2 = QTimer(); self._t2.setInterval(SNAP_2DTE_MS)
        self._t1.timeout.connect(self._snap_1dte)
        self._t2.timeout.connect(self._snap_2dte)
        self._queue: List[Tuple] = []
        self._pace_t = QTimer(); self._pace_t.setInterval(PACING_DELAY_MS)
        self._pace_t.timeout.connect(self._send_one)
        self._sym = ""; self._und = 0.0
        self._exp_0 = ""; self._exp_1 = ""; self._exp_2 = ""
        self._last_queued_slot: int = -1
        self._recv_count  = [0, 0, 0]
        self._total_count = [0, 0, 0]

        # router 등록 (snap_mgr 전용 reqId 범위)
        try:
            from core import router
            router.register_option(REQ_0DTE_C_BASE, REQ_0DTE_P_BASE + REQ_0DTE_RANGE - 1,
                                   self._dummy_tick)
            router.register_option(REQ_1DTE_C_BASE, REQ_1DTE_P_BASE + REQ_1DTE_RANGE - 1,
                                   self._dummy_tick)
            router.register_option(REQ_2DTE_C_BASE, REQ_2DTE_P_BASE + REQ_2DTE_RANGE - 1,
                                   self._dummy_tick)
            self._router_registered = True
            log.info("[SnapMgr] router 등록 완료 (10000~12799)")
        except Exception as e:
            self._router_registered = False
            log.warning("[SnapMgr] router 등록 실패: %s", e)

    def start(self, sym: str, und_price: float, expiry_0dte: str,
              expiry_1dte: str = "", expiry_2dte: str = ""):
        self._sym   = sym;  self._und   = und_price
        self._exp_0 = expiry_0dte
        self._exp_1 = expiry_1dte or self._next_bday(1)
        self._exp_2 = expiry_2dte or self._next_bday(2)
        log.info("[SnapMgr] start %s und=%.1f 0=%s +1=%s +2=%s",
                 sym, und_price, self._exp_0, self._exp_1, self._exp_2)
        self._start_0dte_streaming()
        self._snap_1dte(); self._snap_2dte()
        self._t1.start(); self._t2.start()

    def stop(self):
        self._t1.stop(); self._t2.stop()
        self._pace_t.stop(); self._queue.clear()
        self._cancel_streaming(); self._req_map.clear()
        # router unregister (재시작 시 중복 등록 방지)
        if getattr(self, '_router_registered', False):
            try:
                from core import router
                router.unregister_option(self._dummy_tick)
                self._router_registered = False
            except Exception as e:
                log.warning("[SnapMgr] router unregister 실패: %s", e)
        log.info("[SnapMgr] 전체 정지")

    def update_und_price(self, price: float): self._und = price

    def get_req_info(self, rid: int) -> Optional[Tuple[str, float, str]]:
        return self._req_map.get(rid)

    def is_managed_req(self, rid: int) -> bool:
        return rid in self._req_map

    def record_received(self, rid: int):
        """tick 수신 시 tab_greeks에서 호출 → 메인 스레드에서 카운터/신호등 갱신.
        EClient 스레드에서 직접 호출되므로 QMetaObject.invokeMethod로 마샬링."""
        QMetaObject.invokeMethod(self, "_do_record_received",
                                 Qt.QueuedConnection, Q_ARG(int, rid))

    @pyqtSlot(int)
    def _do_record_received(self, rid: int):
        """메인 스레드에서 실행되는 카운터 증가 + 신호등 갱신."""
        info = self._req_map.get(rid)
        if not info: return
        slot = self._slot_for_expiry(info[0])
        if slot < 0: return
        self._recv_count[slot] += 1
        n     = self._recv_count[slot]
        total = self._total_count[slot]
        _saving = ("당일 만기 저장 중…", "+1DTE 저장 중…", "D+2 저장 중…")
        _done   = ("당일 만기 수신 완료", "+1DTE 저장 완료", "D+2 저장 완료")
        if total > 0 and n >= total:
            self._notify(slot, "done", _done[slot])
        elif n == 1 or n % 10 == 0:
            self._notify(slot, "saving", _saving[slot])

    def _dummy_tick(self, rid: int, *args):
        """router 등록용 더미 슬롯. 실제 tick 처리는 tab_greeks_tick.on_tick_opt에서 담당."""
        pass

    def _notify(self, slot: int, event: str, label: str = ""):
        if self._on_status:
            try: self._on_status(slot, event, self._recv_count[slot], label)
            except Exception as e: log.warning("[SnapMgr] on_status_fn 오류: %s", e)

    def _slot_for_expiry(self, expiry: str) -> int:
        if expiry == self._exp_0: return 0
        if expiry == self._exp_1: return 1
        if expiry == self._exp_2: return 2
        return -1

    def _start_0dte_streaming(self):
        self._cancel_streaming()
        cfg   = self._symbol_cfg()
        step  = cfg["step"]; wing = cfg["wing_0dte"]
        # S12-patch2: 0DTE tag 자동계산
        try:
            from core import _resolve_spx_trading_class
            tag = (_resolve_spx_trading_class(self._sym, self._exp_0, "")
                   if self._sym in ("SPX", "SPXW") else "")
        except ImportError:
            tag = ""
        # BUG-2 수정: 콜/풋 rid 카운터 분리
        rid_c = REQ_0DTE_C_BASE
        rid_p = REQ_0DTE_P_BASE
        count = 0
        for strike in self._strikes(self._und, wing, step):
            for side in ("C", "P"):
                rid  = rid_c if side == "C" else rid_p
                base = REQ_0DTE_C_BASE if side == "C" else REQ_0DTE_P_BASE
                if rid >= base + REQ_0DTE_RANGE:
                    log.warning("[SnapMgr] 0DTE reqId 초과 side=%s", side); continue
                con = self._make_con(self._sym, strike, side, self._exp_0, tag)
                self._enqueue(rid, con, snapshot=False, slot=0)
                self._req_map[rid] = (self._exp_0, strike, side)
                self._streaming_rids.add(rid)
                if side == "C": rid_c += 1
                else:           rid_p += 1
                count += 1
        self._recv_count[0] = 0; self._total_count[0] = count
        self._pace_t.start()
        log.info("[SnapMgr] 0DTE 스트리밍 큐: %d건", count)
        self._notify(0, "saving", f"당일 만기 조회 중… ({count}건)")

    def _cancel_streaming(self):
        for rid in list(self._streaming_rids):
            try: self._ib.cancelMktData(rid)
            except Exception: pass
        self._streaming_rids.clear()

    def _snap_1dte(self):
        if not self._exp_1: return
        self._recv_count[1] = 0
        cnt = self._request_snapshot(self._exp_1, REQ_1DTE_C_BASE, REQ_1DTE_P_BASE,
                                     REQ_1DTE_RANGE, "wing_1dte", "+1DTE", slot=1)
        self._total_count[1] = cnt
        self._notify(1, "saving", f"+1DTE 조회 중… ({cnt}건)")

    def _snap_2dte(self):
        if not self._exp_2: return
        self._recv_count[2] = 0
        cnt = self._request_snapshot(self._exp_2, REQ_2DTE_C_BASE, REQ_2DTE_P_BASE,
                                     REQ_2DTE_RANGE, "wing_2dte", "+2DTE", slot=2)
        self._total_count[2] = cnt
        self._notify(2, "saving", f"D+2 조회 중… ({cnt}건)")

    def _request_snapshot(self, expiry, c_base, p_base, max_range,
                          wing_key, label, slot: int) -> int:
        cfg = self._symbol_cfg()
        count = 0
        # S12-patch2: SPX/SPXW tradingClass 자동 계산 (tag="" 하드코딩 제거)
        try:
            from core import _resolve_spx_trading_class
            _get_tag = lambda sym, exp: (_resolve_spx_trading_class(sym, exp, "")
                                         if sym in ("SPX", "SPXW") else "")
        except ImportError:
            _get_tag = lambda sym, exp: ""
        tag = _get_tag(self._sym, expiry)

        for i, strike in enumerate(self._strikes(self._und, cfg[wing_key], cfg["step"])):
            for side in ("C", "P"):
                base = c_base if side == "C" else p_base
                rid  = base + i
                if rid >= base + max_range:
                    log.warning("[SnapMgr] %s reqId 초과", label); break
                con = self._make_con(self._sym, strike, side, expiry, tag)
                self._enqueue(rid, con, snapshot=True, slot=slot)
                self._req_map[rid] = (expiry, strike, side)
                count += 1
        if not self._pace_t.isActive(): self._pace_t.start()
        log.info("[SnapMgr] %s 스냅샷 큐 %d건 (만기=%s, tag=%s)", label, count, expiry, tag)
        return count

    def _enqueue(self, rid: int, contract, snapshot: bool, slot: int):
        self._queue.append((rid, contract, snapshot, slot))

    def _send_one(self):
        if not self._queue:
            self._pace_t.stop()
            # BUG-7 수정: 마지막으로 전송한 슬롯만 queue_done 발송
            if self._last_queued_slot >= 0:
                s = self._last_queued_slot
                self._notify(s, "queue_done",
                             f"전송 완료 ({self._total_count[s]}건 요청)")
                self._last_queued_slot = -1
            return
        rid, contract, snapshot, slot = self._queue.pop(0)
        self._last_queued_slot = slot
        try: self._ib.reqMktData(rid, contract, "", snapshot, False, [])
        except Exception as e: log.error("[SnapMgr] reqMktData 실패 rid=%d: %s", rid, e)

    def _symbol_cfg(self) -> dict:
        _CFG = {
            "SPX": {"step": 5,  "wing_0dte": 8,  "wing_1dte": 30, "wing_2dte": 20},
            "NDX": {"step": 25, "wing_0dte": 6,  "wing_1dte": 20, "wing_2dte": 15},
            "SPY": {"step": 1,  "wing_0dte": 10, "wing_1dte": 40, "wing_2dte": 30},
            "QQQ": {"step": 1,  "wing_0dte": 10, "wing_1dte": 40, "wing_2dte": 30},
        }
        return _CFG.get(self._sym, {"step": 5, "wing_0dte": 8, "wing_1dte": 30, "wing_2dte": 20})

    @staticmethod
    def _strikes(und: float, wing: int, step: int) -> List[float]:
        atm = round(und / step) * step
        return [atm + i * step for i in range(-wing, wing + 1)]

    @staticmethod
    def _next_bday(n: int) -> str:
        """n번째 다음 거래일 반환. 주말 + 미국 공휴일 모두 건너뜀."""
        try:
            from core import is_trading_day
            d = date.today(); count = 0
            while count < n:
                d += timedelta(days=1)
                if is_trading_day(d): count += 1
        except ImportError:
            # fallback: 주말만 건너뜀
            d = date.today(); count = 0
            while count < n:
                d += timedelta(days=1)
                if d.weekday() < 5: count += 1
        return d.strftime("%Y%m%d")
