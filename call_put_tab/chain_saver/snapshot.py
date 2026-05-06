"""
chain_saver/snapshot.py — OTM/ITM + D+1 + D+2 만기 스냅샷 요청
════════════════════════════════════════════════════════
scheduler.py 에서 분리. reqMktData 요청 로직만 담당.

★ v6.7: D+1/D+2 를 snapshot=True (1회성) 로 변경
  - snapshot=True 는 IBKR 100개 ticker 한도에 포함되지 않음
  - D+1: 1분 주기 재요청, D+2: 2분 주기 재요청
  - 당일 OTM/ITM(SNAP)만 스트리밍(snapshot=False) 유지
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

from core import SYMBOL_CFG, DEFAULT_CFG, make_opt_contract

log = logging.getLogger(__name__)

# ── reqId 블록 정의 ──────────────────────────────────────────
from core import REQ_CALL, REQ_PUT
SNAP_C_START  = REQ_CALL + 20   # 1020  당일 OTM/ITM 콜 (스트리밍)
SNAP_P_START  = REQ_PUT  + 20   # 2020  당일 OTM/ITM 풋 (스트리밍)
SNAP_SLOTS    = 14

NEXT_C_START  = 4400            # D+1 만기 콜 (snapshot=True, 1분 주기)
NEXT_P_START  = 4600            # D+1 만기 풋 (snapshot=True, 1분 주기)
NEXT_SLOTS    = 32              # 콜 32개 + 풋 32개 = 총 64개

NEXT2_C_START = 4800            # D+2 만기 콜 (snapshot=True, 2분 주기)
NEXT2_P_START = 4840            # D+2 만기 풋 (snapshot=True, 2분 주기)
                                # S12-fix1: 5000 → 4840
                                # 구 값 5000은 core.REQ_OI(5000~5498)와 충돌
NEXT2_SLOTS   = 32              # 콜 32개 + 풋 32개 = 총 64개

# ── reqId 범위 충돌 확인 ─────────────────────────────────────
# NEXT_C:  4400~4431 (32개)
# NEXT_P:  4600~4631 (32개)
# NEXT2_C: 4800~4831 (32개)
# NEXT2_P: 4840~4871 (32개)  ← S12-fix1: 5000~5031 → 4840~4871
# REQ_OI:  5000~5498          ← NEXT2_P 와 완전 분리됨
#
# snapshot=True → IBKR 100개 티커 한도 미포함 → 수량 제한 없음


def request_otm(ib, sym: str, expiry: str, tag: str,
                und: float, n_atm: int,
                snap_map: Dict[int, Tuple]) -> None:
    """
    당일 ATM 바깥 OTM/ITM 스트리밍 구독.
    snap_map 에 reqId -> (expiry, strike, side) 기록.
    snapshot=False 지속 수신 (ticker 한도 포함)
    """
    _, _, _, step = SYMBOL_CFG.get(
        sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
    atm = round(und / step) * step

    calls = [atm + (n_atm + i) * step for i in range(1, SNAP_SLOTS // 2 + 1)]
    puts  = [atm - (n_atm + i) * step for i in range(1, SNAP_SLOTS // 2 + 1)]

    cancel_map(ib, snap_map)

    rid_c, rid_p = SNAP_C_START, SNAP_P_START

    for st in calls:
        if rid_c >= SNAP_C_START + SNAP_SLOTS: break
        snap_map[rid_c] = (expiry, st, "C")
        _req_stream(ib, rid_c, make_opt_contract(sym, st, "C", expiry, tag))
        rid_c += 1

    for st in puts:
        if rid_p >= SNAP_P_START + SNAP_SLOTS: break
        snap_map[rid_p] = (expiry, st, "P")
        _req_stream(ib, rid_p, make_opt_contract(sym, st, "P", expiry, tag))
        rid_p += 1


def request_next(ib, sym: str, und: float,
                 next_map: Dict[int, Tuple]) -> Optional[str]:
    """
    D+1 만기 1회성 스냅샷 요청 (1분 주기 재호출).
    snapshot=True -> IBKR ticker 한도 미포함.
    콜 32개 + 풋 32개 = 총 64개.
    반환값: 요청한 만기일 (없으면 None)
    """
    nxt = _next_trading_day(days=1)
    if not nxt:
        return None

    _, _, _, step = SYMBOL_CFG.get(
        sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
    atm = round(und / step) * step

    # 콜: ATM ~ ATM+31*step (32개), 풋: ATM-1*step ~ ATM-32*step (32개)
    call_strikes = [atm + i * step for i in range(NEXT_SLOTS)]       # ATM 포함 위쪽
    put_strikes  = [atm - i * step for i in range(1, NEXT_SLOTS + 1)] # ATM 제외 아래쪽

    from core import _resolve_spx_trading_class
    tag = _resolve_spx_trading_class(sym, nxt, "") if sym in ("SPX", "SPXW") else ""

    # snapshot=True 는 수신 완료 후 자동 해제 -> cancel 불필요, map만 초기화
    next_map.clear()

    rid_c = NEXT_C_START
    for st in call_strikes:
        if rid_c >= NEXT_C_START + NEXT_SLOTS: break
        next_map[rid_c] = (nxt, st, "C")
        _req_snapshot(ib, rid_c, make_opt_contract(sym, st, "C", nxt, tag))
        rid_c += 1

    rid_p = NEXT_P_START
    for st in put_strikes:
        if rid_p >= NEXT_P_START + NEXT_SLOTS: break
        next_map[rid_p] = (nxt, st, "P")
        _req_snapshot(ib, rid_p, make_opt_contract(sym, st, "P", nxt, tag))
        rid_p += 1

    log.info("[Snapshot] D+1 요청: %s 만기=%s tag=%s 콜%d개 풋%d개",
             sym, nxt, tag,
             rid_c - NEXT_C_START, rid_p - NEXT_P_START)
    return nxt


def request_next2(ib, sym: str, und: float,
                  next2_map: Dict[int, Tuple]) -> Optional[str]:
    """
    D+2 만기 1회성 스냅샷 요청 (2분 주기 재호출).
    snapshot=True -> IBKR ticker 한도 미포함.
    콜 32개 + 풋 32개 = 총 64개.
    반환값: 요청한 만기일 (없으면 None)
    """
    nxt2 = _next_trading_day(days=2)
    if not nxt2:
        return None

    _, _, _, step = SYMBOL_CFG.get(
        sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
    atm = round(und / step) * step

    # 콜: ATM ~ ATM+31*step (32개), 풋: ATM-1*step ~ ATM-32*step (32개)
    call_strikes = [atm + i * step for i in range(NEXT2_SLOTS)]
    put_strikes  = [atm - i * step for i in range(1, NEXT2_SLOTS + 1)]

    from core import _resolve_spx_trading_class
    tag = _resolve_spx_trading_class(sym, nxt2, "") if sym in ("SPX", "SPXW") else ""

    next2_map.clear()

    rid_c = NEXT2_C_START
    for st in call_strikes:
        if rid_c >= NEXT2_C_START + NEXT2_SLOTS: break
        next2_map[rid_c] = (nxt2, st, "C")
        _req_snapshot(ib, rid_c, make_opt_contract(sym, st, "C", nxt2, tag))
        rid_c += 1

    rid_p = NEXT2_P_START
    for st in put_strikes:
        if rid_p >= NEXT2_P_START + NEXT2_SLOTS: break
        next2_map[rid_p] = (nxt2, st, "P")
        _req_snapshot(ib, rid_p, make_opt_contract(sym, st, "P", nxt2, tag))
        rid_p += 1

    log.info("[Snapshot] D+2 요청: %s 만기=%s tag=%s 콜%d개 풋%d개",
             sym, nxt2, tag,
             rid_c - NEXT2_C_START, rid_p - NEXT2_P_START)
    return nxt2


def cancel_map(ib, req_map: Dict[int, Tuple]) -> None:
    """스트리밍 구독 취소 + map 초기화. snapshot=True 요청엔 불필요."""
    for rid in req_map:
        try: ib.cancelMktData(rid)
        except: pass
    req_map.clear()


# ── 내부 헬퍼 ────────────────────────────────────────────────
def _req_stream(ib, rid: int, contract) -> None:
    """스트리밍 모드 (snapshot=False). 당일 OTM/ITM 전용. ticker 한도 포함."""
    try:
        ib.reqMktData(rid, contract, "106", False, False, [])
    except Exception as e:
        log.warning("[Snapshot] stream rid=%d: %s", rid, e)


def _req_snapshot(ib, rid: int, contract) -> None:
    """
    1회성 스냅샷 (snapshot=True). D+1/D+2 전용.
    ticker 한도 미포함. 수신 완료 후 IBKR이 자동 해제.
    genericTickList="" 필수 — snapshot=True 시 generic tick 미지원 (ERR 321)
    """
    try:
        ib.reqMktData(rid, contract, "", True, False, [])
    except Exception as e:
        log.warning("[Snapshot] snapshot rid=%d: %s", rid, e)


def _today_et() -> date:
    """pytz 없이 미국 동부시간(ET) 기준 오늘 날짜 반환."""
    from datetime import datetime, timezone, timedelta as _td
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar1 + _td(days=(6 - mar1.weekday()) % 7 + 7)
    dst_start = dst_start.replace(hour=7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov1 + _td(days=(6 - nov1.weekday()) % 7)
    dst_end = dst_end.replace(hour=6)
    offset = _td(hours=-4 if dst_start <= now_utc < dst_end else -5)
    return (now_utc + offset).date()


def _next_trading_day(days: int = 1) -> Optional[str]:
    """ET 기준 오늘로부터 days 번째 거래일 반환."""
    nxt = _today_et()
    count = 0
    while count < days:
        nxt += timedelta(days=1)
        if nxt.weekday() < 5:
            count += 1
    return nxt.strftime("%Y%m%d")