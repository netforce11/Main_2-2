# spread_calc.py  (Python 3.8 호환)
"""
v1.9 변경 (버그 수정):
  ★ [BUG-FIX-1] get_call/put_spreads: on_done 있을 때 동기경로에서
    on_done([]) 직접 호출 후 None 반환하도록 통일.
    (기존: on_done 있어도 [] 반환 → spread_tele_bot 에서
     result is not None 조건에 걸려 _send_result 이중호출 또는 누락)

  ★ [BUG-FIX-2] _fetch_ticks_for_expiry IB 미연결 경로:
    threading.Thread(on_done({})) → threading.Thread(on_done(row_map={}))
    동일하지만 로그 추가로 디버그 가시성 확보.

  ★ [BUG-FIX-3] _calc_spreads: CALL_RANGE_PCT / PUT_RANGE_PCT 범위
    in_range 조건 수정 — pair(lk)가 strikes 목록에 없어도 계산 진행.
    (기존: in_range 체크만 하고 short_row가 None이면 skip → 결과 0개)

  v1.8 대비 구조 변경 없음. 스레드/QTimer 방식 동일.
"""
from __future__ import annotations
import threading
from typing import TYPE_CHECKING, Optional, List, Tuple, Callable
from datetime import datetime, timezone, timedelta, date as _date

from .spread_config import (
    ES_BASIS_OFFSET, SPREAD_STEP,
    CALL_RANGE_PCT, PUT_RANGE_PCT,
)

if TYPE_CHECKING:
    from call_put_tab.tab_options import CallPutGrid

REQ_SPREAD_BASE = 9800
REQ_SPREAD_MAX  = 50


# ── ET 기준 오늘 날짜 ────────────────────────────────────

def _et_today() -> _date:
    """IB 서버 기준 오늘 날짜 (EDT = UTC-4). 한국 00~13시는 ET로 전날."""
    return datetime.now(tz=timezone(timedelta(hours=-4))).date()


# ── 기준가 ───────────────────────────────────────────────

def get_base_price(tab: "CallPutGrid") -> Optional[float]:
    price = getattr(tab, "und_price", None)
    if price is None:
        return None
    if getattr(tab, "_und_is_futures", False):
        return price - ES_BASIS_OFFSET
    return price


def get_price_label(tab: "CallPutGrid") -> str:
    is_fut = getattr(tab, "_und_is_futures", False)
    price  = get_base_price(tab)
    sym    = "/ES→SPX" if is_fut else "SPX"
    if price is None:
        return f"{sym} (미수신)"
    return f"{sym} {price:,.2f}"


# ── 만기 선택 ────────────────────────────────────────────

def resolve_expiry(tab: "CallPutGrid", which: str) -> Tuple[Optional[str], str]:
    """
    which: "today" | "next"
    """
    today_str   = _et_today().strftime("%Y%m%d")
    expiry_list = getattr(tab, "_expiry_list", [])

    valid = []
    for item in expiry_list:
        if len(item) >= 2:
            code = str(item[1])
            if code.isdigit() and len(code) == 8 and code >= today_str:
                valid.append((code, str(item[0])))
    valid.sort(key=lambda x: x[0])

    if not valid:
        return None, "유효한 만기 없음"

    if which == "today":
        for code, _ in valid:
            if code == today_str:
                return code, f"{code[4:6]}/{code[6:8]} (오늘)"
        code, _ = valid[0]
        return code, f"{code[4:6]}/{code[6:8]} (최근)"
    else:  # "next"
        code, _ = valid[1] if len(valid) >= 2 else valid[0]
        return code, f"{code[4:6]}/{code[6:8]} (다음)"


# ── 틱 헬퍼 ─────────────────────────────────────────────

def _build_row_map(data_dict: dict) -> dict:
    """
    {reqId: {row, bid, ask, ...}} → {row: {bid, ask}}
    동일 row 에 여러 reqId → 유효 틱 우선.
    """
    row_map: dict = {}
    for rid, info in data_dict.items():
        r = info.get("row")
        if r is None:
            continue
        if r not in row_map:
            row_map[r] = info
        else:
            existing = row_map[r]
            e_ok = (existing.get("bid") or 0) > 0 and (existing.get("ask") or 0) > 0
            n_ok = (info.get("bid") or 0) > 0 and (info.get("ask") or 0) > 0
            if n_ok and not e_ok:
                row_map[r] = info
    return row_map


def _mid(info: Optional[dict]) -> Optional[float]:
    """bid > ask 역전 방어."""
    if info is None:
        return None
    bid = info.get("bid")
    ask = info.get("ask")
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid > ask:
        return None
    m = (bid + ask) / 2.0
    return m if m > 0 else None


# ── 손익 계산 ────────────────────────────────────────────

def calc_spread_pnl(long_k: float, short_k: float,
                    mid: Optional[float], is_call: bool) -> dict:
    """mid=None 이면 전 필드 None."""
    width = abs(long_k - short_k)
    if mid is None:
        return {"max_profit": None, "max_loss": None, "breakeven": None, "rr": "―"}
    if mid <= 0 or mid >= width:
        return {"max_profit": None, "max_loss": None, "breakeven": None, "rr": "틱이상"}
    mp = round(width - mid, 2)
    ml = round(mid, 2)
    be = round(long_k + mid, 2) if is_call else round(long_k - mid, 2)
    return {"max_profit": mp, "max_loss": ml, "breakeven": be,
            "rr": f"1 : {round(mp / ml, 1)}"}


# ── 행사가 → row 인덱스 ──────────────────────────────────

def _get_spread_row(strikes: list, k: float) -> Optional[int]:
    """float 비교 오차 0.01pt 허용."""
    if not isinstance(strikes, (list, tuple)):
        return None
    for i, s in enumerate(strikes):
        if abs(s - k) < 0.01:
            return i
    return None


# ── 탭 현재 만기 읽기 (★ 메인 스레드 전용) ──────────────

def _tab_current_expiry_main(tab: "CallPutGrid") -> Optional[str]:
    """
    반드시 메인 스레드에서만 호출.
    combo_exp / date_edit 은 Qt 위젯 → 다른 스레드 접근 시 crash/hang.
    """
    try:
        expiry_list = getattr(tab, "_expiry_list", [])
        combo = getattr(tab, "combo_exp", None)
        if combo is not None:
            ci = combo.currentIndex()
            if 0 <= ci < len(expiry_list):
                code = str(expiry_list[ci][1])
                if code.isdigit() and len(code) == 8:
                    return code
        de = getattr(tab, "date_edit", None)
        if de:
            return de.date().toString("yyyyMMdd")
    except Exception:
        pass
    return None


# ── 스프레드 계산 (공통 내부) ────────────────────────────

def _calc_spreads(strikes: List[float], row_map: dict,
                  base: float, is_call: bool) -> List[dict]:
    if is_call:
        limit    = base * (1 + CALL_RANGE_PCT)
        sorted_s = sorted(s for s in strikes if base <= s <= limit + SPREAD_STEP)
        def pair(lk): return lk + SPREAD_STEP
        # [BUG-FIX-3] pair(lk)가 strikes 안에 없어도 계산 진행
        # in_range 는 단순 범위 체크만 (short_row None은 pnl에서 처리)
        def in_range(lk): return pair(lk) <= limit + SPREAD_STEP
    else:
        limit    = base * (1 - PUT_RANGE_PCT)
        sorted_s = sorted(
            (s for s in strikes if limit - SPREAD_STEP <= s <= base),
            reverse=True)
        def pair(lk): return lk - SPREAD_STEP
        def in_range(lk): return pair(lk) >= limit - SPREAD_STEP

    results = []
    for long_k in sorted_s:
        short_k = pair(long_k)
        if not in_range(long_k):
            continue
        long_row  = _get_spread_row(strikes, long_k)
        short_row = _get_spread_row(strikes, short_k)
        # [BUG-FIX-3] short_row None → mid=None 으로 처리, skip 하지 않음
        # long_row 만 없으면 skip (long 없으면 거리 계산 불가)
        if long_row is None:
            continue

        long_mid  = _mid(row_map.get(long_row))
        short_mid = _mid(row_map.get(short_row)) if short_row is not None else None
        spread_mid = (round(long_mid - short_mid, 2)
                      if long_mid is not None and short_mid is not None else None)
        dist_pct = round((long_k - base) / base * 100, 2)
        pnl      = calc_spread_pnl(long_k, short_k, spread_mid, is_call=is_call)

        results.append({
            "long": long_k, "short": short_k,
            "mid": spread_mid, "dist_pct": dist_pct,
            **pnl,
        })
    return results


# ── 별도 만기 틱 구독 ────────────────────────────────────

def _fetch_ticks_for_expiry(
    tab:         "CallPutGrid",
    expiry_code: str,
    strikes:     List[float],
    cached_data: dict,
    is_call:     bool,
    on_done:     Callable[[dict], None],
    timeout_ms:  int = 4000,
) -> None:
    """
    호출 스레드: TgPolling (메인 아님) → 즉시 return.
    on_done   : daemon 스레드에서 실행 (HTTP blocking 이므로 메인 스레드 금지).
    """
    from PyQt5.QtCore import QTimer
    from core import bridge as _bridge
    from core_contract import make_opt_contract

    mw = getattr(tab, "mw", None)
    ib = getattr(mw, "ib", None)

    # ── IB 미연결: 빈 row_map 으로 on_done (틱 미수신 표시)
    if ib is None or not getattr(mw, "connected", False):
        print("[spread_calc] IB 미연결 — 캐시 없이 계산 진행")
        threading.Thread(
            target=lambda: on_done({}), daemon=True, name="SpreadOnDone"
        ).start()
        return

    sym_raw = tab.edit_sym.text().strip().upper() if hasattr(tab, "edit_sym") else "SPX"
    sym     = sym_raw.replace("SPXW", "SPX")
    right   = "C" if is_call else "P"
    n       = min(len(strikes), REQ_SPREAD_MAX)

    def _run_on_main():
        """메인 스레드에서 실행 — Qt 위젯 / QTimer / 시그널 안전."""

        cur_exp = _tab_current_expiry_main(tab)
        if cur_exp == expiry_code:
            # 캐시 재활용
            row_map = _build_row_map(cached_data)
            print(f"[spread_calc] 만기 일치({expiry_code}) — 캐시 사용, row_map 크기={len(row_map)}")
            threading.Thread(
                target=lambda: on_done(row_map), daemon=True, name="SpreadOnDone"
            ).start()
            return

        # ── 별도 만기 TWS 구독 ──
        print(f"[spread_calc] 만기 불일치(cur={cur_exp}, req={expiry_code}) — TWS 구독 시작")
        tick_buf: dict = {}
        _done = [False]

        def _on_tick(rid, tt, price):
            if rid < REQ_SPREAD_BASE or rid >= REQ_SPREAD_BASE + n:
                return
            if price <= 0:
                return
            row = rid - REQ_SPREAD_BASE
            if row not in tick_buf:
                tick_buf[row] = {"row": row, "bid": None, "ask": None}
            if tt == 1:
                tick_buf[row]["bid"] = price
            elif tt == 2:
                tick_buf[row]["ask"] = price

        def _cleanup_and_done(row_map: dict):
            if _done[0]:
                return
            _done[0] = True
            try:
                _bridge.tick_price.disconnect(_on_tick)
            except Exception:
                pass
            for i in range(n):
                try:
                    ib.cancelMktData(REQ_SPREAD_BASE + i)
                except Exception:
                    pass
            print(f"[spread_calc] 틱 수집 완료, row_map 크기={len(row_map)}")
            threading.Thread(
                target=lambda: on_done(row_map), daemon=True, name="SpreadOnDone"
            ).start()

        def _on_timeout():
            _cleanup_and_done(dict(tick_buf))

        _bridge.tick_price.connect(_on_tick)
        QTimer.singleShot(timeout_ms, _on_timeout)

        for i, strike in enumerate(strikes[:n]):
            rid = REQ_SPREAD_BASE + i
            try:
                contract = make_opt_contract(
                    symbol=sym, strike=strike, right=right, expiry=expiry_code)
                ib.reqMktData(rid, contract, "", False, False, [])
            except Exception as e:
                print(f"[spread_calc] reqMktData 오류 rid={rid}: {e}")

    QTimer.singleShot(0, _run_on_main)


# ── 공개 API ─────────────────────────────────────────────

def get_call_spreads(tab: "CallPutGrid", expiry_code: str,
                     on_done: Optional[Callable[[List[dict]], None]] = None
                     ) -> Optional[List[dict]]:
    """
    on_done 없음 → 동기 반환.
    on_done 있음 → 반드시 비동기, 항상 None 반환.
                   결과는 on_done(results) 로만 전달.

    [BUG-FIX-1] 기존: base=None 이거나 strikes=[] 일 때 on_done([]) 호출 후에도
    [] 를 반환 → spread_tele_bot 에서 result is not None 에 걸려 _send_result
    이중호출 또는 on_done 무시 발생.
    수정: on_done 있으면 항상 None 반환, on_done() 내부에서만 결과 전달.
    """
    base = get_base_price(tab)
    if base is None:
        if on_done:
            threading.Thread(
                target=lambda: on_done([]), daemon=True, name="SpreadOnDone"
            ).start()
            return None  # [BUG-FIX-1] on_done 있으면 None 반환
        return []

    strikes     = list(getattr(tab, "call_strikes", []) or [])
    cached_data = dict(getattr(tab, "call_data", {}) or {})

    if not strikes:
        if on_done:
            threading.Thread(
                target=lambda: on_done([]), daemon=True, name="SpreadOnDone"
            ).start()
            return None  # [BUG-FIX-1]
        return []

    if on_done is None:
        row_map = _build_row_map(cached_data)
        return _calc_spreads(strikes, row_map, base, is_call=True)

    def _cb(row_map: dict):
        results = _calc_spreads(strikes, row_map, base, is_call=True)
        print(f"[spread_calc] get_call_spreads 결과: {len(results)}개")
        on_done(results)

    _fetch_ticks_for_expiry(
        tab, expiry_code, strikes,
        cached_data=cached_data, is_call=True, on_done=_cb)
    return None  # [BUG-FIX-1] 항상 None


def get_put_spreads(tab: "CallPutGrid", expiry_code: str,
                    on_done: Optional[Callable[[List[dict]], None]] = None
                    ) -> Optional[List[dict]]:
    """
    [BUG-FIX-1] 동일 적용.
    """
    base = get_base_price(tab)
    if base is None:
        if on_done:
            threading.Thread(
                target=lambda: on_done([]), daemon=True, name="SpreadOnDone"
            ).start()
            return None
        return []

    strikes     = list(getattr(tab, "put_strikes", []) or [])
    cached_data = dict(getattr(tab, "put_data", {}) or {})

    if not strikes:
        if on_done:
            threading.Thread(
                target=lambda: on_done([]), daemon=True, name="SpreadOnDone"
            ).start()
            return None
        return []

    if on_done is None:
        row_map = _build_row_map(cached_data)
        return _calc_spreads(strikes, row_map, base, is_call=False)

    def _cb(row_map: dict):
        results = _calc_spreads(strikes, row_map, base, is_call=False)
        print(f"[spread_calc] get_put_spreads 결과: {len(results)}개")
        on_done(results)

    _fetch_ticks_for_expiry(
        tab, expiry_code, strikes,
        cached_data=cached_data, is_call=False, on_done=_cb)
    return None  # [BUG-FIX-1] 항상 None