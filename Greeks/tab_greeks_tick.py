"""
tab_greeks_tick.py — IBKR tick 수신 처리  S12-patch2 (최종)
══════════════════════════════════════════════════════════════
수정 이력:
  S12       BUG-3: _on_snap_data dead code 신호등 카운터 제거
  S12-patch1 [핵심] snap_mgr 관할 reqId tick → _cell_data 갱신 + DB 즉시 저장
  S12-patch2 [BUG]  경로 2 (_next_map) 제거
             → tab_greeks.py S12-patch1에서 _next_map 상태변수 삭제됨.
                AttributeError 방지 + 레거시 경로 완전 제거.
             [BUG]  on_snap_data() _cell_data에 sym 필드 누락 수정

저장 구조:
  경로 1  fetch() 0DTE  (4000번대) → _cell_data 갱신만 → autosave(1분) 저장
  경로 3a snap_mgr 0DTE (10000번대) → _cell_data 갱신만 → autosave(1분) 저장
  경로 3b snap_mgr +1DTE/+2DTE (11000~12799) → tick 수신 즉시 DB 저장
  autosave → self._expiry(0DTE) 만 필터 → 경로 3b 와 중복 없음
"""
from __future__ import annotations
import logging
from datetime import datetime

import greeks_db as gdb
from core import REQ_CHAIN, REQ_CHAIN_P

log = logging.getLogger(__name__)


def on_tick_price(self, req_id: int, tick_type: int, price: float):
    if price and price > 0:
        self._und_price = price


def on_tick_opt(self, req_id: int, tick_type: int,
                iv: float, delta: float, option_price: float,
                gamma: float, vega: float, theta: float):
    """core.TickRouter 에서 라우팅된 옵션 틱 처리."""
    if tick_type not in (10, 11, 12, 13): return
    if not iv or not (0 < iv < 10): return

    vanna = vega * delta if (vega and delta) else 0.0
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── 경로 1: 당일 0DTE 직접 구독 (fetch() / REQ_CHAIN 4000번대) ──────────
    if req_id in self._req_map:
        strike, side, exp = self._req_map[req_id]
        k = (exp, strike, side)
        is_new = k not in self._cell_data
        if is_new and len(self._cell_data) == 0:
            print(f"[Greeks] ✅ 첫 tick reqId={req_id} {side}{int(strike)} "
                  f"iv={iv:.4f} delta={delta:.4f} tt={tick_type}")
        self._prev_data[k] = self._cell_data.get(k, {}).copy()
        self._cell_data[k] = dict(
            sym=self._sym, expiry=exp, strike=strike, side=side,
            delta=delta, gamma=gamma, iv=iv, vanna=vanna,
            und_price=self._und_price, ts=ts
        )
        if is_new:
            n = len(self._cell_data); total = len(self._req_map)
            if n % 10 == 0 or n == total:
                pct = int(n / total * 100) if total else 0
                self._banner.setText(
                    f"📡 수신 중 {n}/{total} ({pct}%) | {side}{int(strike)} iv={iv:.3f}")

    # ── 경로 2: 레거시 _next_map 경로 — S12-patch1에서 완전 삭제됨 ────────────
    # tab_greeks.py에서 _next_map 상태변수 자체가 제거되어 있으므로
    # 이 elif 블록을 유지하면 AttributeError 발생.
    # → 완전 제거. +1DTE 는 경로 3 (snap_mgr) 이 전담.

    # ── 경로 3: SnapshotManager 관할 (0DTE snap_mgr + +1DTE + +2DTE) ─────────
    # reqId 범위: 10000~12799 (REQ_0DTE~REQ_2DTE)
    #
    # 저장 분기:
    #   slot 0 (0DTE): _cell_data 갱신만 → autosave(1분 주기)가 저장
    #                  즉시 저장 시 autosave와 이중 저장 발생하므로 저장 안 함
    #   slot 1/2 (+1DTE/+2DTE): tick 수신 즉시 DB 저장
    #                            autosave는 self._expiry(0DTE)만 필터하므로 중복 없음
    elif self._snap_mgr and self._snap_mgr.is_managed_req(req_id):
        info = self._snap_mgr.get_req_info(req_id)   # → (expiry, strike, side)
        if info:
            exp, strike, side = info
            k = (exp, strike, side)

            # ① _cell_data 갱신 (화면 렌더링 + autosave 소스)
            self._prev_data[k] = self._cell_data.get(k, {}).copy()
            self._cell_data[k] = dict(
                sym=self._sym, expiry=exp, strike=strike, side=side,
                delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                und_price=self._und_price, ts=ts
            )

            # ② DB 저장 분기
            slot = self._snap_mgr._slot_for_expiry(exp)
            if slot > 0:   # +1DTE / +2DTE 만 즉시 저장
                try:
                    gdb.save_snapshot(self._conn, [dict(
                        ts=ts, sym=self._sym, expiry=exp,
                        strike=strike, side=side,
                        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                        und_price=self._und_price
                    )])
                except Exception as e:
                    log.error("[Greeks] snap_mgr DB 저장 실패 rid=%d: %s", req_id, e)

        # ③ 신호등 카운터 갱신 (EClient 스레드 → invokeMethod 마샬링)
        self._snap_mgr.record_received(req_id)

    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_snap_data(self, expiry: str, strike: float, side: str, data: dict):
    """
    SnapshotManager.on_data_fn 콜백.
    BUG-3(S12): 신호등 데드코드 제거. 신호등은 record_received 경로가 처리.
    S12-patch2: sym 필드 추가 (detect_spike 등 _cell_data 직접 접근 시 KeyError 방지).
    NOTE: 현재 SnapshotManager 는 on_data_fn 을 직접 호출하지 않음.
          tick 은 on_tick_opt → snap_mgr 경로로만 수신됨. 이 함수는 예비 경로.
    """
    iv = data.get("iv")
    if not iv or not (0 < iv < 10): return
    delta = data.get("delta", 0.0)
    gamma = data.get("gamma", 0.0)
    vega  = data.get("vega",  0.0)
    vanna = vega * delta if (vega and delta) else 0.0
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    k     = (expiry, strike, side)
    self._prev_data[k] = self._cell_data.get(k, {}).copy()
    # S12-patch2: sym 필드 누락 수정
    self._cell_data[k] = dict(
        sym=self._sym, expiry=expiry, strike=strike, side=side,
        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
        und_price=self._und_price, ts=ts
    )
    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_ibkr_error(self, req_id: int, error_code: int, msg: str):
    """
    IBKR 에러 처리.
    504 (Not connected): 연결 해제 상태에서 reqMktData/cancelMktData 발생.
    → dead reqId 정리 후 조용히 return (배너 노출 불필요, 연결 복구 후 자동 재구독).
    """
    if error_code == 504:
        if req_id in self._req_map:
            del self._req_map[req_id]
        if self._snap_mgr and self._snap_mgr.is_managed_req(req_id):
            try:
                del self._snap_mgr._req_map[req_id]
            except Exception:
                pass
        return

    if req_id in self._req_map:
        print(f"[Greeks] ❌ IBKR 에러 reqId={req_id} code={error_code}: {msg}")
        self._banner.setText(f"❌ IBKR 에러 {error_code}: {msg}")


def on_raw_tick_option(self, req_id: int, tick_type: int,
                       iv: float, delta: float, op: float,
                       gamma: float, vega: float, theta: float):
    """bridge.tick_option 원시 수신 — Greeks reqId 범위 첫 10개 디버그 출력."""
    if REQ_CHAIN <= req_id <= REQ_CHAIN_P + 199:
        if not hasattr(self, "_raw_tick_count"):
            self._raw_tick_count = 0
        if self._raw_tick_count < 10:
            print(f"[Greeks] raw tick reqId={req_id} tt={tick_type} "
                  f"iv={iv:.4f} delta={delta:.4f}")
            self._raw_tick_count += 1
