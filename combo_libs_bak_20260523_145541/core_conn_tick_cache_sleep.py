"""
core_conn_tick_cache_sleep.py — sleep_order 즉시 트리거 모듈 함수  v1.2
════════════════════════════════════════════════════════════════
core_conn_tick_cache.py 에서 분리.
_on_tick_price / _flush_one_req 에서 이 모듈의 함수를 호출한다.

  _notify_sleep_watcher  — 틱 즉시 watcher.on_price_update() 트리거
  _flush_chain_price     — 200ms flush 시 combo_tab 체인 갱신
  _patch_chain_price     — reqId 1개 O(1) 갱신 (_price_cache 직접 참조)

설계 원칙:
  · 모든 함수는 예외를 삼킨다 (sleep_order 연동 실패가 틱 흐름을 막으면 안 됨)
  · watcher 비활성 시 _notify_sleep_watcher 는 속성 조회 3회 후 즉시 리턴
  · _patch_chain_price 는 call_data 가 아닌 _price_cache 직접 참조
    (200ms flush 전 최신값 보장)
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from core import REQ_CALL, REQ_PUT


def _notify_sleep_watcher(cp, reqId: int) -> None:
    """틱 수신 즉시 watcher.on_price_update() 트리거.
    REQ_CALL/REQ_PUT 범위 외 reqId (스나이퍼·긴급매도 등)는 즉시 리턴.
    """
    if not (REQ_CALL <= reqId <= REQ_CALL + 25 or
            REQ_PUT  <= reqId <= REQ_PUT  + 25):
        return
    try:
        mw = getattr(cp, 'mw', None)
        if mw is None: return
        combo_tab = getattr(mw, 'tab_combo', None)
        if combo_tab is None: return
        watcher = getattr(combo_tab, '_sleep_watcher', None)
        if watcher is None or not watcher._active: return
        # _price_cache 직접 읽어 _chain_call/put 즉시 갱신
        _patch_chain_price(combo_tab, cp, reqId)
        # 윈도우·fired 체크 + scan_and_check 는 watcher 내부에서 처리
        watcher.on_price_update(combo_tab, 0.0)
    except Exception:
        pass


def _flush_chain_price(cp, reqId: int) -> None:
    """200ms flush 시 combo_tab._chain_call/_chain_put 갱신.
    _auto_sync_chain 3초 폴백과 역할 분리:
      · 이 함수: 200ms 주기로 변경된 reqId 1개만 갱신
      · _auto_sync_chain: 3초 주기로 전체 체인 풀 동기화
    """
    try:
        mw = getattr(cp, 'mw', None)
        if mw is None: return
        combo_tab = getattr(mw, 'tab_combo', None)
        if combo_tab is None: return
        if not hasattr(combo_tab, '_chain_call') or \
           not hasattr(combo_tab, '_chain_put'):
            return
        _patch_chain_price(combo_tab, cp, reqId)
    except Exception:
        pass


def _patch_chain_price(combo_tab, cp, reqId: int) -> None:
    """reqId 1개에 해당하는 행사가 가격만 O(1) 갱신.

    가격 우선순위: bid/ask mid → last
    call_data 대신 _price_cache 참조 이유:
      call_data 는 200ms flush 후에야 갱신 → 틱 직후 호출 시 직전 값
    """
    try:
        d    = getattr(cp, '_price_cache', {}).get(reqId, {})
        bid  = d.get(1); ask = d.get(2); last = d.get(4)
        if bid and ask and bid > 0 and ask > 0:
            lp = round((bid + ask) / 2, 2)
        elif last and last > 0:
            lp = last
        else:
            return

        if REQ_CALL <= reqId <= REQ_CALL + 25:
            idx = reqId - REQ_CALL
            strikes = getattr(cp, 'call_strikes', [])
            if idx < len(strikes):
                combo_tab._chain_call[strikes[idx]] = lp
            return

        if REQ_PUT <= reqId <= REQ_PUT + 25:
            idx = reqId - REQ_PUT
            strikes = getattr(cp, 'put_strikes', [])
            if idx < len(strikes):
                combo_tab._chain_put[strikes[idx]] = lp
    except Exception:
        pass
