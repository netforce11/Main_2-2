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

    콜 debit 스프레드 구조:
      buy_strike  (ATM 근처, 낮은 행사가) → BUY
      sell_strike (buy_strike + width,  높은 행사가) → SELL
      net = buy_prem - sell_prem  (양수여야 함)
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes:
        return None

    width = sleep_cfg.spread_width

    # buy_strike: put_strike 와 가장 가까운 콜 행사가 (ATM 근처, 낮은 쪽)
    buy_strike  = min(call_strikes, key=lambda s: abs(s - put_strike))
    # sell_strike: buy_strike 에서 width 만큼 위 (높은 행사가)
    sell_strike = min(call_strikes, key=lambda s: abs(s - (buy_strike + width)))
    if sell_strike == buy_strike:
        return None

    buy_prem  = float(chain_call.get(buy_strike)  or 0)
    sell_prem = float(chain_call.get(sell_strike) or 0)
    # buy_prem > sell_prem 이어야 정상 (낮은 콜이 더 비쌈)
    if buy_prem <= 0 or sell_prem <= 0 or buy_prem <= sell_prem:
        return None
    net = round(buy_prem - sell_prem, 2)
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
        "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {buy_strike}",
        "legs": [
            {"cp": "C", "strike": buy_strike,  "expiry": expiry,
             "dir": "BUY",  "qty": 1, "prem": buy_prem,  "con_id": _cid(buy_strike)},
            {"cp": "C", "strike": sell_strike, "expiry": expiry,
             "dir": "SELL", "qty": 1, "prem": sell_prem, "con_id": _cid(sell_strike)},
        ],
    }
