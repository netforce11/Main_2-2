"""
chain_saver/snapshot.py — OTM/ITM + 내일 만기 스냅샷 요청
════════════════════════════════════════════════════════
scheduler.py 에서 분리. reqMktData 요청 로직만 담당.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

from core import SYMBOL_CFG, DEFAULT_CFG, make_opt_contract

log = logging.getLogger(__name__)

# ── reqId 블록 정의 ──────────────────────────────────────────
from core import REQ_CALL, REQ_PUT
SNAP_C_START = REQ_CALL + 20   # 1020  오늘 OTM/ITM 콜
SNAP_P_START = REQ_PUT  + 20   # 2020  오늘 OTM/ITM 풋
SNAP_SLOTS   = 30

NEXT_C_START = 4400            # 내일 만기 콜
NEXT_P_START = 4600            # 내일 만기 풋
NEXT_SLOTS   = 50


def request_otm(ib, sym: str, expiry: str, tag: str,
                und: float, n_atm: int,
                snap_map: Dict[int, Tuple]) -> None:
    """
    ATM 바깥 OTM/ITM 스냅샷 요청.
    snap_map 에 reqId → (expiry, strike, side) 기록.
    """
    _, _, _, step = SYMBOL_CFG.get(
        sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
    atm = round(und / step) * step

    calls = [atm + (n_atm + i) * step for i in range(1, SNAP_SLOTS // 2 + 1)]
    puts  = [atm - (n_atm + i) * step for i in range(1, SNAP_SLOTS // 2 + 1)]

    snap_map.clear()
    rid_c, rid_p = SNAP_C_START, SNAP_P_START

    for st in calls:
        if rid_c >= SNAP_C_START + SNAP_SLOTS: break
        snap_map[rid_c] = (expiry, st, "C")
        _req(ib, rid_c, make_opt_contract(sym, st, "C", expiry, tag))
        rid_c += 1

    for st in puts:
        if rid_p >= SNAP_P_START + SNAP_SLOTS: break
        snap_map[rid_p] = (expiry, st, "P")
        _req(ib, rid_p, make_opt_contract(sym, st, "P", expiry, tag))
        rid_p += 1


def request_next(ib, sym: str, und: float,
                 next_map: Dict[int, Tuple]) -> Optional[str]:
    """
    내일 만기 스냅샷 요청. next_map 에 reqId → (expiry, strike, side) 기록.
    반환값: 요청한 만기일 (없으면 None)
    """
    nxt = _next_trading_day()
    if not nxt:
        return None

    _, _, _, step = SYMBOL_CFG.get(
        sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
    atm     = round(und / step) * step
    strikes = [atm + i * step for i in range(-10, 11)]

    next_map.clear()
    rid_c, rid_p = NEXT_C_START, NEXT_P_START

    for st in strikes:
        if rid_c < NEXT_C_START + NEXT_SLOTS:
            next_map[rid_c] = (nxt, st, "C")
            _req(ib, rid_c, make_opt_contract(sym, st, "C", nxt, ""))
            rid_c += 1
        if rid_p < NEXT_P_START + NEXT_SLOTS:
            next_map[rid_p] = (nxt, st, "P")
            _req(ib, rid_p, make_opt_contract(sym, st, "P", nxt, ""))
            rid_p += 1

    return nxt


def cancel_map(ib, req_map: Dict[int, Tuple]) -> None:
    for rid in req_map:
        try: ib.cancelMktData(rid)
        except: pass
    req_map.clear()


# ── 내부 헬퍼 ────────────────────────────────────────────────
def _req(ib, rid: int, contract) -> None:
    try:
        # snapshot=True 모드에서는 genericTickList 비워야 함 (bM 에러 방지)
        ib.reqMktData(rid, contract, "", True, False, [])
    except Exception as e:
        log.warning("[Snapshot] reqMktData rid=%d: %s", rid, e)


def _today_et() -> date:
    """pytz 없이 미국 동부시간(ET) 기준 오늘 날짜 반환."""
    from datetime import datetime, timezone, timedelta as _td
    from datetime import date as _date
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    # 3월 둘째 일요일 (DST 시작, 07:00 UTC = 02:00 ET)
    mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = mar1 + _td(days=(6 - mar1.weekday()) % 7 + 7)
    dst_start = dst_start.replace(hour=7)
    # 11월 첫째 일요일 (DST 종료, 06:00 UTC = 02:00 ET)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = nov1 + _td(days=(6 - nov1.weekday()) % 7)
    dst_end = dst_end.replace(hour=6)
    offset = _td(hours=-4 if dst_start <= now_utc < dst_end else -5)
    return (now_utc + offset).date()


def _next_trading_day() -> Optional[str]:
    nxt = _today_et() + timedelta(days=1)   # ★ ET 기준 오늘 날짜
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt.strftime("%Y%m%d")