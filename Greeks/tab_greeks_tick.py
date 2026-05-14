"""
tab_greeks_tick.py — IBKR tick 수신 처리  S12-fix2 (최종)
══════════════════════════════════════════════════════════════
수정 이력:
  S12       BUG-3: _on_snap_data dead code 신호등 카운터 제거
  S12-patch1 [핵심] snap_mgr 관할 reqId tick → _cell_data 갱신 + DB 즉시 저장
  S12-patch2 [BUG]  경로 2 (_next_map) 제거
             [BUG]  on_snap_data() _cell_data에 sym 필드 누락 수정
  S12-fix2   [FIX-3] on_tick_price() und_price 이상값(SPX 범위 밖) 필터링
             [FIX-6] _cell_data 저장 시 sym 필드 누락 추가 방어
             [FIX-8] +1DTE/+2DTE 즉시 저장 시 conn 날짜 자동 갱신 호출

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
from greeks_db import UND_PRICE_MIN, UND_PRICE_MAX
from core import REQ_CHAIN, REQ_CHAIN_P
# [🟠 FIX] tick 루프 내 반복 import 제거 → 파일 상단으로 이동
from tab_greeks_save import _refresh_conn_if_needed

log = logging.getLogger(__name__)


def on_tick_price(self, req_id: int, tick_type: int, price: float):
    """
    기초자산 현재가 수신.
    [FIX-3] SPX 정상 범위(3000~12000) 외 값은 무시.
            /ES(~5000대), SPY(~500대), 기타 종목 혼입 방지.
    """
    if not price or price <= 0:
        return

    # [FIX-3] 이상값 필터
    if price < UND_PRICE_MIN or price > UND_PRICE_MAX:
        log.warning("[Greeks] und_price 이상값 무시: %.2f (reqId=%d) — "
                    "SPX 범위(%s~%s) 아님",
                    price, req_id, UND_PRICE_MIN, UND_PRICE_MAX)
        return

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
        # [FIX-6] sym 항상 명시
        self._cell_data[k] = dict(
            sym=self._sym, expiry=exp, strike=strike, side=side,
            delta=delta, gamma=gamma, iv=iv, vanna=vanna,
            und_price=self._und_price if self._und_price > 0 else None,
            ts=ts
        )
        if is_new:
            n = len(self._cell_data); total = len(self._req_map)
            if n % 10 == 0 or n == total:
                pct = int(n / total * 100) if total else 0
                self._banner.setText(
                    f"📡 수신 중 {n}/{total} ({pct}%) | {side}{int(strike)} iv={iv:.3f}")

    # ── 경로 2: 레거시 _next_map — S12-patch1에서 완전 삭제됨 ────────────────
    # tab_greeks.py에서 _next_map 상태변수 자체가 제거되어 있으므로 제거.

    # ── 경로 3: SnapshotManager 관할 (0DTE snap_mgr + +1DTE + +2DTE) ─────────
    elif self._snap_mgr and self._snap_mgr.is_managed_req(req_id):
        info = self._snap_mgr.get_req_info(req_id)
        if info:
            exp, strike, side = info
            k = (exp, strike, side)

            # ① _cell_data 갱신
            self._prev_data[k] = self._cell_data.get(k, {}).copy()
            # [FIX-6] sym 항상 명시
            self._cell_data[k] = dict(
                sym=self._sym, expiry=exp, strike=strike, side=side,
                delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                und_price=self._und_price if self._und_price > 0 else None,
                ts=ts
            )

            # ② DB 저장 분기
            slot = self._snap_mgr._slot_for_expiry(exp)
            if slot > 0:   # +1DTE / +2DTE 만 즉시 저장
                # [FIX-8] 즉시 저장 전 날짜 변경 체크 (파일 상단 import 사용)
                _refresh_conn_if_needed(self)

                und = self._und_price if self._und_price > 0 else None
                try:
                    gdb.save_snapshot(self._conn, [dict(
                        ts=ts, sym=self._sym, expiry=exp,
                        strike=strike, side=side,
                        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                        und_price=und
                    )])
                except Exception as e:
                    log.error("[Greeks] snap_mgr DB 저장 실패 rid=%d: %s", req_id, e)

            # [🟠 FIX] record_received는 info 성공 여부와 무관하게 호출해야
            # 신호등 카운터가 올바르게 작동하므로 if info 블록 밖으로 이동
        # ③ 신호등 카운터 갱신 (info=None이어도 수신 자체는 기록)
        self._snap_mgr.record_received(req_id)

    # [🟢 FIX] reqId가 어디에도 해당 안 되는 경우 flush 트리거 하지 않음
    else:
        return

    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_snap_data(self, expiry: str, strike: float, side: str, data: dict):
    """
    SnapshotManager.on_data_fn 콜백 (예비 경로).
    S12-patch2: sym 필드 추가.
    S12-fix2 [FIX-6]: sym 필드 추가 방어.
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
    # [FIX-6] sym 항상 명시
    self._cell_data[k] = dict(
        sym=self._sym, expiry=expiry, strike=strike, side=side,
        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
        und_price=self._und_price if self._und_price > 0 else None,
        ts=ts
    )
    if not self._flush_t.isActive():
        self._flush_t.start(300)


def on_ibkr_error(self, req_id: int, error_code: int, msg: str):
    """
    IBKR 에러 처리.
    504 (Not connected): dead reqId 정리 후 조용히 return.
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
