"""
spike_scan_call_helper.py — 콜 스프레드 체인 조회 헬퍼  v1.0
════════════════════════════════════════
spike_scan.py 에서 분리.
_find_call_item : put_strike 기준으로 콜 스프레드 legs/net 반환.
"""
from __future__ import annotations


def find_call_item(ref: object, put_strike: float, sleep_cfg) -> dict | None:
    """
    put_strike 와 동일 행사가 기준의 콜 스프레드 legs/net 반환.
    _chain_call 에서 직접 조회. 없으면 None.
    콜 스프레드 구조: 낮은 콜 BUY + 높은 콜 SELL (debit spread)
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes:
        return None

    width  = sleep_cfg.spread_width
    upper  = min(call_strikes, key=lambda s: abs(s - put_strike))
    lower  = min(call_strikes, key=lambda s: abs(s - (upper + width)))
    if lower == upper:
        return None

    up_p = float(chain_call.get(upper) or 0)
    lo_p = float(chain_call.get(lower) or 0)
    if up_p <= 0 or lo_p <= 0 or up_p <= lo_p:
        return None
    net = round(up_p - lo_p, 2)
    if net <= 0:
        return None

    tick = 0.10 if net >= 3.0 else 0.05

    try:
        from combo_order_bag import _CONID_CACHE, _conid_key
        sym_w  = getattr(ref, 'edit_sym_combo', None)
        symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
        def _cid(s): return int(_CONID_CACHE.get(_conid_key(symbol, "C", s, expiry), 0))
    except ImportError:
        _cid = lambda s: 0

    return {
        "net":   net,
        "ask":   round(net + tick, 2),
        "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {upper}",
        "legs": [
            {"cp": "C", "strike": upper, "expiry": expiry,
             "dir": "BUY",  "qty": 1, "prem": up_p, "con_id": _cid(upper)},
            {"cp": "C", "strike": lower, "expiry": expiry,
             "dir": "SELL", "qty": 1, "prem": lo_p, "con_id": _cid(lower)},
        ],
    }
