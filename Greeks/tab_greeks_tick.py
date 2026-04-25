"""
tab_greeks_tick.py — IBKR tick 수신 처리  S12-patch1
══════════════════════════════════════════════════════
S12  BUG-3: _on_snap_data dead code 신호등 카운터 제거
S12-patch1 수정 사항:
  [핵심] snap_mgr 관할 reqId tick 수신 시 _cell_data 갱신 및 DB 즉시 저장 누락 수정.
         기존: record_received() 만 호출 → 카운터만 증가, Greeks 데이터 유실
         수정: tick 파라미터를 직접 파싱 → _cell_data 갱신 + slot>0 이면 DB 즉시 저장
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

    # ── 경로 1: 당일 0DTE 직접 구독 (_req_map / fetch 관할) ──────────────
    if req_id in self._req_map:
        strike, side, exp = self._req_map[req_id]
        k = (exp, strike, side)
        is_new = k not in self._cell_data
        if is_new and len(self._cell_data) == 0:
            print(f"[Greeks] ✅ 첫 tick reqId={req_id} {side}{int(strike)} "
                  f"iv={iv:.4f} delta={delta:.4f} tt={tick_type}")
        self._prev_data[k] = self._cell_data.get(k, {}).copy()
        self._cell_data[k] = dict(expiry=exp, strike=strike, side=side,
                                  delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                                  und_price=self._und_price, ts=ts)
        if is_new:
            n = len(self._cell_data); total = len(self._req_map)
            if n % 10 == 0 or n == total:
                pct = int(n / total * 100) if total else 0
                self._banner.setText(
                    f"📡 수신 중 {n}/{total} ({pct}%) | {side}{int(strike)} iv={iv:.3f}")

    # ── 경로 2: 레거시 +1DTE 스냅샷 (_next_map / fetch_next_expiry 관할) ──
    elif req_id in self._next_map:
        s, side, exp = self._next_map[req_id]
        gdb.save_snapshot(self._conn, [dict(
            ts=ts, sym=self._sym, expiry=exp, strike=s, side=side,
            delta=delta, gamma=gamma, iv=iv, vanna=vanna,
            und_price=self._und_price)])
        self._snap_count_1dte += 1
        if self._snap_count_1dte % 10 == 0:
            self._status_saving(1, self._snap_count_1dte, "+1DTE 저장 중…")

    # ── 경로 3: SnapshotManager 관할 (+1DTE / +2DTE) ──────────────────────
    # S12-patch1: tick 데이터를 _cell_data 에 저장하고 slot>0 이면 DB 즉시 저장.
    # 기존 코드는 record_received(rid) 만 호출해서 카운터만 올리고 데이터를 버렸음.
    elif self._snap_mgr and self._snap_mgr.is_managed_req(req_id):
        info = self._snap_mgr.get_req_info(req_id)   # → (expiry, strike, side)
        if info:
            exp, strike, side = info
            k = (exp, strike, side)

            # ① _cell_data 갱신 (화면 렌더링용)
            self._prev_data[k] = self._cell_data.get(k, {}).copy()
            self._cell_data[k] = dict(expiry=exp, strike=strike, side=side,
                                      delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                                      und_price=self._und_price, ts=ts)

            # ② DB 즉시 저장
            #    slot 1=+1DTE, slot 2=D+2 → tick 수신 즉시 저장
            #    slot 0=0DTE  → autosave(1분 주기)가 담당하므로 생략 (중복 방지)
            slot = self._snap_mgr._slot_for_expiry(exp)
            if slot > 0:
                try:
                    gdb.save_snapshot(self._conn, [dict(
                        ts=ts, sym=self._sym, expiry=exp,
                        strike=strike, side=side,
                        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                        und_price=self._und_price)])
                except Exception as e:
                    log.error("[Greeks] snap_mgr DB 저장 실패 rid=%d: %s", req_id, e)

        # ③ 신호등 카운터 갱신 (기존 역할 유지)
        self._snap_mgr.record_received(req_id)

    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_snap_data(self, expiry: str, strike: float, side: str, data: dict):
    """
    SnapshotManager.on_data_fn 콜백.
    BUG-3(S12): 신호등 데드코드 제거. record_received 경로가 신호등을 처리.
    NOTE: 현재 SnapshotManager 는 on_data_fn 을 직접 호출하지 않음.
          tick 은 on_tick_opt → snap_mgr 경로로만 수신됨.
    """
    iv = data.get("iv")
    if not iv or not (0 < iv < 10): return
    delta = data.get("delta", 0.0); gamma = data.get("gamma", 0.0)
    vega  = data.get("vega",  0.0)
    vanna = vega * delta if (vega and delta) else 0.0
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    k     = (expiry, strike, side)
    self._prev_data[k] = self._cell_data.get(k, {}).copy()
    self._cell_data[k] = dict(expiry=expiry, strike=strike, side=side,
                               delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                               und_price=self._und_price, ts=ts)
    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_ibkr_error(self, req_id: int, error_code: int, msg: str):
    if req_id in self._req_map:
        print(f"[Greeks] ❌ IBKR 에러 reqId={req_id} code={error_code}: {msg}")
        self._banner.setText(f"❌ IBKR 에러 {error_code}: {msg}")


def on_raw_tick_option(self, req_id: int, tick_type: int,
                       iv: float, delta: float, op: float,
                       gamma: float, vega: float, theta: float):
    """bridge.tick_option 원시 수신 — Greeks reqId 범위 첫 10개 디버그 출력."""
    if REQ_CHAIN <= req_id <= REQ_CHAIN_P + 199:
        if not hasattr(self, "_raw_tick_count"): self._raw_tick_count = 0
        if self._raw_tick_count < 10:
            print(f"[Greeks] raw tick reqId={req_id} tt={tick_type} "
                  f"iv={iv:.4f} delta={delta:.4f}")
            self._raw_tick_count += 1