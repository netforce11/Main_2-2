"""greeks_snapshot_mgr.py — IBKR 스냅샷 요청 관리  S12-fix1
════════════════════════════════════════════════════════════════════════
수정 이력:
  S12       BUG-2: 0DTE 콜/풋 rid 카운터 분리
  S12       BUG-7: queue_done 마지막 슬롯만 발송
  S12-patch1: [논리결함1] 재호출 시 cancelMktData 누락 → _cancel_snapshot() 추가
  S12-patch2: [CRITICAL-1] REQ_0DTE 블록을 10000번대로 이동
              [CRITICAL-2] _request_snapshot() tag="" 하드코딩 제거
              [BUG]        _next_bday() 공휴일 처리 누락 → is_trading_day() 사용
              [THREAD]     record_received() EClient 스레드 → invokeMethod 마샬링
              [LEAK]       stop()에서 router option 슬롯 unregister 추가
  S12-fix1: [DESIGN] 0DTE 스트리밍 → 10초 주기 스냅샷으로 전환
              - _start_0dte_streaming() → _snap_0dte() 로 변경
              - snapshot=False(스트리밍) → snapshot=True(1회성 스냅샷)
              - IBKR 구독 한도 0DTE 42개 절감
              - _streaming_rids(Set) 제거 → _cancel_snapshot() 통일
              - _cancel_streaming() 제거
              - _t0 타이머 추가 (10초 주기, SNAP_0DTE_MS=10_000)
              - start() 에서 _t0.start() 추가
              - stop() 단순화: _cancel_snapshot() 3블록으로 통일
              - 클래스 docstring 업데이트
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QTimer, QMetaObject, Qt, Q_ARG, pyqtSlot, QObject

log = logging.getLogger(__name__)

# ── reqId 블록 ────────────────────────────────────────────────────────────────
# core.py REQ_CHAIN(4000~4399), REQ_OI(5000~5499), REQ_HIST(6000~6099) 등
# 기존 1~9999 범위와 완전히 분리된 10000번대 사용
#
#  10000~10399 : 0DTE  콜(10000~10199) + 풋(10200~10399)
#  11000~11799 : +1DTE 콜(11000~11399) + 풋(11400~11799)
#  12000~12799 : +2DTE 콜(12000~12399) + 풋(12400~12799)
REQ_0DTE_C_BASE = 10000; REQ_0DTE_P_BASE = 10200; REQ_0DTE_RANGE = 200
REQ_1DTE_C_BASE = 11000; REQ_1DTE_P_BASE = 11400; REQ_1DTE_RANGE = 400
REQ_2DTE_C_BASE = 12000; REQ_2DTE_P_BASE = 12400; REQ_2DTE_RANGE = 400

PACING_DELAY_MS = 22        # 초당 45개 (22ms 간격)
SNAP_0DTE_MS    = 10_000    # 0DTE  갱신 주기: 10초
SNAP_1DTE_MS    = 60_000    # +1DTE 갱신 주기: 1분
SNAP_2DTE_MS    = 120_000   # +2DTE 갱신 주기: 2분

StatusFn = Optional[Callable[[int, str, int, str], None]]


class SnapshotManager(QObject):
    """
    만기별 IBKR 스냅샷 요청 관리.  S12-fix1: 전 슬롯 snapshot=True 통일.

    역할 분담:
      - 0DTE 스냅샷  : _snap_0dte() / _t0 타이머 10초 (10000번대 reqId)
      - +1DTE 스냅샷 : _snap_1dte() / _t1 타이머 1분  (11000번대)
      - +2DTE 스냅샷 : _snap_2dte() / _t2 타이머 2분  (12000번대)

    모두 snapshot=True (1회성) → IBKR 구독 한도 미포함.

    tick 처리 흐름:
      IBKR → bridge.tick_option → TickRouter → (10000~12799 등록된 슬롯)
      → tab_greeks_tick.on_tick_opt() → _cell_data 갱신 + DB 저장
      → record_received() → 카운터/신호등 갱신 (메인 스레드 마샬링)
    """

    def __init__(self, ib, make_contract_fn, on_data_fn, on_status_fn: StatusFn = None):
        super().__init__()   # QObject 초기화 필수 (invokeMethod 사용)
        self._ib        = ib
        self._make_con  = make_contract_fn
        self._on_data   = on_data_fn       # 현재 미사용 — tick은 on_tick_opt 경로로만 처리됨
        self._on_status = on_status_fn

        self._req_map: Dict[int, Tuple[str, float, str]] = {}
        # S12-fix1: _streaming_rids 제거 (0DTE 스냅샷 전환으로 불필요)

        # 0DTE / +1DTE / +2DTE 고정 주기 타이머
        self._t0 = QTimer(self); self._t0.setInterval(SNAP_0DTE_MS)
        self._t1 = QTimer(self); self._t1.setInterval(SNAP_1DTE_MS)
        self._t2 = QTimer(self); self._t2.setInterval(SNAP_2DTE_MS)
        self._t0.timeout.connect(self._snap_0dte)
        self._t1.timeout.connect(self._snap_1dte)
        self._t2.timeout.connect(self._snap_2dte)

        # pacing 타이머 (22ms 간격 reqMktData 발송)
        self._queue: List[Tuple] = []
        self._pace_t = QTimer(self); self._pace_t.setInterval(PACING_DELAY_MS)
        self._pace_t.timeout.connect(self._send_one)

        self._sym   = ""; self._und = 0.0
        self._exp_0 = ""; self._exp_1 = ""; self._exp_2 = ""
        self._last_queued_slot: int = -1
        self._recv_count  = [0, 0, 0]
        self._total_count = [0, 0, 0]

        # router 등록 (snap_mgr 전용 reqId 범위 3블록)
        # 실제 Greeks 처리(cell_data 갱신·DB 저장)는 tab_greeks_tick.on_tick_opt 가 담당.
        # 여기서는 TickRouter가 해당 범위를 인식하도록 _dummy_tick 으로 등록.
        # tab_greeks._connect_signals() 에서도 동일 범위를 on_tick_opt 로 추가 등록함.
        self._router_registered = False
        try:
            from core import router
            router.register_option(REQ_0DTE_C_BASE,
                                   REQ_0DTE_P_BASE + REQ_0DTE_RANGE - 1,
                                   self._dummy_tick)
            router.register_option(REQ_1DTE_C_BASE,
                                   REQ_1DTE_P_BASE + REQ_1DTE_RANGE - 1,
                                   self._dummy_tick)
            router.register_option(REQ_2DTE_C_BASE,
                                   REQ_2DTE_P_BASE + REQ_2DTE_RANGE - 1,
                                   self._dummy_tick)
            self._router_registered = True
            log.info("[SnapMgr] router 등록 완료 (10000~12799)")
        except Exception as e:
            log.warning("[SnapMgr] router 등록 실패: %s", e)

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def start(self, sym: str, und_price: float, expiry_0dte: str,
              expiry_1dte: str = "", expiry_2dte: str = ""):
        """
        전 슬롯 스냅샷 시작. S12-fix1: 0DTE도 스냅샷(_snap_0dte)으로 통일.
        expiry_0dte: 0DTE 만기 (슬롯 매핑 + 스냅샷 요청에 사용)
        expiry_1dte/2dte: 생략 시 _next_bday() 자동 계산
        """
        self._sym   = sym
        self._und   = und_price
        self._exp_0 = expiry_0dte
        self._exp_1 = expiry_1dte or self._next_bday(1)
        self._exp_2 = expiry_2dte or self._next_bday(2)
        log.info("[SnapMgr] start %s und=%.1f 0=%s +1=%s +2=%s",
                 sym, und_price, self._exp_0, self._exp_1, self._exp_2)
        self._snap_0dte()
        self._snap_1dte()
        self._snap_2dte()
        self._t0.start()
        self._t1.start()
        self._t2.start()

    def stop(self):
        """전체 정지 — 타이머·큐·스냅샷·router 등록 모두 해제.
        S12-fix1: _cancel_streaming() 제거 → _cancel_snapshot() 3블록으로 통일.
        """
        self._t0.stop(); self._t1.stop(); self._t2.stop()
        self._pace_t.stop()
        self._queue.clear()
        # 전 슬롯 스냅샷 cancel (snapshot=True는 IBKR이 자동 해제하나 명시 cancel)
        self._cancel_snapshot(REQ_0DTE_C_BASE, REQ_0DTE_P_BASE, REQ_0DTE_RANGE)
        self._cancel_snapshot(REQ_1DTE_C_BASE, REQ_1DTE_P_BASE, REQ_1DTE_RANGE)
        self._cancel_snapshot(REQ_2DTE_C_BASE, REQ_2DTE_P_BASE, REQ_2DTE_RANGE)
        self._req_map.clear()
        # router unregister — 재시작 시 중복 등록 방지
        if self._router_registered:
            try:
                from core import router
                router.unregister_option(self._dummy_tick)
                self._router_registered = False
            except Exception as e:
                log.warning("[SnapMgr] router unregister 실패: %s", e)
        log.info("[SnapMgr] 전체 정지")

    def update_und_price(self, price: float):
        self._und = price

    def get_req_info(self, rid: int) -> Optional[Tuple[str, float, str]]:
        """rid → (expiry, strike, side) 반환. 없으면 None."""
        return self._req_map.get(rid)

    def is_managed_req(self, rid: int) -> bool:
        return rid in self._req_map

    def record_received(self, rid: int):
        """
        tick 수신 시 tab_greeks_tick 에서 호출.
        EClient 스레드 → 메인 스레드로 마샬링 후 카운터/신호등 갱신.
        """
        QMetaObject.invokeMethod(
            self, "_do_record_received",
            Qt.QueuedConnection,
            Q_ARG(int, rid)
        )

    @pyqtSlot(int)
    def _do_record_received(self, rid: int):
        """메인 스레드에서 실행 — 카운터 증가 + 신호등 갱신."""
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
        """router 등록용 더미 슬롯. 실제 처리는 tab_greeks_tick.on_tick_opt 담당."""
        pass

    # ── 내부 ─────────────────────────────────────────────────────────────────

    def _notify(self, slot: int, event: str, label: str = ""):
        if self._on_status:
            try:
                self._on_status(slot, event, self._recv_count[slot], label)
            except Exception as e:
                log.warning("[SnapMgr] on_status_fn 오류: %s", e)

    def _slot_for_expiry(self, expiry: str) -> int:
        """만기 문자열 → 슬롯 번호 (0=0DTE, 1=+1DTE, 2=+2DTE, -1=미관리)."""
        if expiry == self._exp_0: return 0
        if expiry == self._exp_1: return 1
        if expiry == self._exp_2: return 2
        return -1

    def _snap_0dte(self):
        """
        0DTE 스냅샷 요청. S12-fix1: 스트리밍 → snapshot=True 전환.
        10초 타이머(_t0)로 주기적 재요청.
        기존 0DTE rid cancel 후 재요청 → _cancel_snapshot() 재사용.
        """
        if not self._exp_0: return
        self._cancel_snapshot(REQ_0DTE_C_BASE, REQ_0DTE_P_BASE, REQ_0DTE_RANGE)
        self._recv_count[0] = 0
        cnt = self._request_snapshot(
            self._exp_0,
            REQ_0DTE_C_BASE, REQ_0DTE_P_BASE, REQ_0DTE_RANGE,
            "wing_0dte", "0DTE", slot=0
        )
        self._total_count[0] = cnt
        self._notify(0, "saving", f"당일 만기 조회 중… ({cnt}건)")

    def _cancel_snapshot(self, c_base: int, p_base: int, max_range: int):
        """
        해당 슬롯 rid 블록 cancel + req_map 제거.
        _snap_1dte/_snap_2dte 재호출 전 잔존 rid 정리용.
        """
        for base in (c_base, p_base):
            for i in range(max_range):
                rid = base + i
                if rid in self._req_map:
                    try: self._ib.cancelMktData(rid)
                    except Exception: pass
                    del self._req_map[rid]

    def _snap_1dte(self):
        if not self._exp_1: return
        self._cancel_snapshot(REQ_1DTE_C_BASE, REQ_1DTE_P_BASE, REQ_1DTE_RANGE)
        self._recv_count[1] = 0
        cnt = self._request_snapshot(
            self._exp_1,
            REQ_1DTE_C_BASE, REQ_1DTE_P_BASE, REQ_1DTE_RANGE,
            "wing_1dte", "+1DTE", slot=1
        )
        self._total_count[1] = cnt
        self._notify(1, "saving", f"+1DTE 조회 중… ({cnt}건)")

    def _snap_2dte(self):
        if not self._exp_2: return
        self._cancel_snapshot(REQ_2DTE_C_BASE, REQ_2DTE_P_BASE, REQ_2DTE_RANGE)
        self._recv_count[2] = 0
        cnt = self._request_snapshot(
            self._exp_2,
            REQ_2DTE_C_BASE, REQ_2DTE_P_BASE, REQ_2DTE_RANGE,
            "wing_2dte", "+2DTE", slot=2
        )
        self._total_count[2] = cnt
        self._notify(2, "saving", f"D+2 조회 중… ({cnt}건)")

    def _request_snapshot(self, expiry: str, c_base: int, p_base: int,
                          max_range: int, wing_key: str,
                          label: str, slot: int) -> int:
        """
        스냅샷 요청 공통 로직.
        S12-patch2: tag="" 하드코딩 제거 → _resolve_tag() 자동 계산.
        콜/풋이 같은 strike 인덱스 i 를 공유하므로 c_base+i, p_base+i 로 분리됨.
        """
        cfg   = self._symbol_cfg()
        tag   = self._resolve_tag(self._sym, expiry)
        count = 0

        for i, strike in enumerate(
                self._strikes(self._und, cfg[wing_key], cfg["step"])):
            for side in ("C", "P"):
                base = c_base if side == "C" else p_base
                rid  = base + i
                if rid >= base + max_range:
                    log.warning("[SnapMgr] %s reqId 초과 (side=%s)", label, side)
                    break
                con = self._make_con(self._sym, strike, side, expiry, tag)
                self._enqueue(rid, con, snapshot=True, slot=slot)
                self._req_map[rid] = (expiry, strike, side)
                count += 1

        if not self._pace_t.isActive():
            self._pace_t.start()
        log.info("[SnapMgr] %s 스냅샷 큐 %d건 (만기=%s, tag=%s)",
                 label, count, expiry, tag)
        return count

    def _enqueue(self, rid: int, contract, snapshot: bool, slot: int):
        self._queue.append((rid, contract, snapshot, slot))

    def _send_one(self):
        """pacing 타이머 콜백 — 22ms마다 큐에서 하나씩 reqMktData 발송."""
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
        try:
            self._ib.reqMktData(rid, contract, "", snapshot, False, [])
        except Exception as e:
            log.error("[SnapMgr] reqMktData 실패 rid=%d: %s", rid, e)

    @staticmethod
    def _resolve_tag(sym: str, expiry: str) -> str:
        """
        SPX/SPXW tradingClass 자동 계산.
        S12-patch2: tag="" 하드코딩 제거.
        core._resolve_spx_trading_class import 실패 시 "" 폴백.
        """
        if sym not in ("SPX", "SPXW"):
            return ""
        try:
            from core import _resolve_spx_trading_class
            return _resolve_spx_trading_class(sym, expiry, "")
        except Exception:
            return ""

    def _symbol_cfg(self) -> dict:
        _CFG = {
            "SPX": {"step": 5,  "wing_0dte": 8,  "wing_1dte": 30, "wing_2dte": 20},
            "NDX": {"step": 25, "wing_0dte": 6,  "wing_1dte": 20, "wing_2dte": 15},
            "SPY": {"step": 1,  "wing_0dte": 10, "wing_1dte": 40, "wing_2dte": 30},
            "QQQ": {"step": 1,  "wing_0dte": 10, "wing_1dte": 40, "wing_2dte": 30},
        }
        return _CFG.get(
            self._sym,
            {"step": 5, "wing_0dte": 8, "wing_1dte": 30, "wing_2dte": 20}
        )

    @staticmethod
    def _strikes(und: float, wing: int, step: int) -> List[float]:
        atm = round(und / step) * step
        return [atm + i * step for i in range(-wing, wing + 1)]

    @staticmethod
    def _next_bday(n: int) -> str:
        """
        n번째 다음 거래일 반환.
        S12-patch2: 주말 + 미국 공휴일 통합 처리 (is_trading_day 사용).
        core import 실패 시 주말만 건너뛰는 폴백.
        """
        try:
            from core import is_trading_day
            d = date.today(); count = 0
            while count < n:
                d += timedelta(days=1)
                if is_trading_day(d): count += 1
        except ImportError:
            d = date.today(); count = 0
            while count < n:
                d += timedelta(days=1)
                if d.weekday() < 5: count += 1
        return d.strftime("%Y%m%d")