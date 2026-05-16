"""
spike_scan.py — 체인 스캔 + 주문 발사 로직  v1.0
════════════════════════════════════════
SleepOrderWatcher._scan_and_check / _fire_order 를 분리.
watcher 파일 줄 수 감축 목적.
"""
from __future__ import annotations
import time as _time
from Sleep_Order.spike_utils import tg


def calc_entry_price(net: float, sleep_cfg) -> float:
    if not sleep_cfg.aggressive_entry:
        return net
    tick = 0.10 if net >= 3.00 else 0.05
    return round(net + tick * max(1, int(sleep_cfg.aggressive_ticks)), 2)


def scan_and_check(watcher) -> None:
    """watcher = SleepOrderWatcher 인스턴스."""
    from Sleep_Order.sleep_order_config     import sleep_cfg
    from Sleep_Order.spike_watcher_debit    import DebitSpikeWatcher
    from Sleep_Order.spike_watcher_single   import SingleOptSpikeWatcher, resolve_single_strikes
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end): return

    chain_put = getattr(ref, '_chain_put', {})
    if len([v for v in chain_put.values() if v and v > 0]) < 3: return
    # 예약주문(SLEEP_ORDER) 태그 OID만 차단, 급락캐치 OID는 통과
    _pend = getattr(ref, '_pending_position', {})
    if getattr(ref, '_chaser_current_oid', None) and             _pend.get('status') == '미체결' and             _pend.get('tag', '') == 'SLEEP_ORDER': return

    try: und = ref._sleep_get_underlying_price()
    except Exception: return
    if not und or und <= 0: return

    # 1분 보정
    now_ts = _time.monotonic()
    if now_ts - watcher._last_range_reset >= 60:
        watcher._last_range_reset = now_ts
        DebitSpikeWatcher.get().evict_out_of_range(und)

    try: chain = ref._sleep_get_chain(sleep_cfg.expiry_offset)
    except Exception: return
    if not chain: return

    dmin = sleep_cfg.strike_dist_min / 100.0; dmax = sleep_cfg.strike_dist_max / 100.0
    for item in chain:
        strike    = float(item.get("strike", 0))
        net_price = float(item.get("put_net", 0))
        ask_price = float(item.get("put_ask", 0))
        legs      = item.get("legs", [])
        if not strike or not legs: continue
        if not (dmin <= abs(und - strike) / und <= dmax): continue
        if net_price > 0:
            mp = (sleep_cfg.spread_width - net_price) * 100
            if mp <= 0: continue
            roi = mp / (net_price * 100) * 100
            if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max): continue

        key   = f"{strike}_{sleep_cfg.expiry_offset}"
        strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
        DebitSpikeWatcher.get().register(key, ref, legs, strat)
        DebitSpikeWatcher.get().on_price_update(key, net_price, ask_price)

        if not watcher._fired:
            net_r = round(net_price * 20) / 20
            if net_r <= sleep_cfg.target_price_1:
                lmt = calc_entry_price(net_r, sleep_cfg)
                qty = max(1, int(sleep_cfg.max_budget // (lmt * 100)))
                fire_order(watcher, legs, net_r, qty, strat)
                break

    if sleep_cfg.single_spike_enabled:
        cp = sleep_cfg.single_cp
        # PUT: live_prices(구독) 우선, 없으면 chain_put 폴백
        # CALL: chain_call 직접 참조 (live_prices는 PUT만 구독)
        if cp == "P":
            live = getattr(ref, '_sleep_live_prices', {})
            chain_fallback = getattr(ref, '_chain_put', {})
            src_map = {k: (live.get(k) or v) for k, v in chain_fallback.items()}
        else:
            src_map = getattr(ref, '_chain_call', {})
        for s in resolve_single_strikes(ref):
            price = float(src_map.get(s) or 0.0)
            if price <= 0: continue
            SingleOptSpikeWatcher.get().register(s, ref, f"SINGLE_{cp} {s}")
            SingleOptSpikeWatcher.get().on_price_update(s, price)


def fire_order(watcher, legs: list, net: float, qty: int, strat: str) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end): return
    lmt   = calc_entry_price(net, sleep_cfg)
    qty   = max(1, int(sleep_cfg.max_budget // (lmt * 100)))
    total = round(lmt * qty * 100, 2)
    agg   = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    if sleep_cfg.dry_run:
        watcher._fired = True
        tg(f"🧪 [드라이런] 예약주문 시뮬\n{strat}\n${net:.2f}→${lmt:.2f}{agg}\n"
           f"qty={qty} 총=${total}\n⚠ 미전송")
        watcher.status_changed.emit(f"🧪 드라이런  ${lmt:.2f}×{qty}"); return
    try:
        oid = ref._sleep_place_order(legs=legs, lmt_price=lmt, qty=qty,
                                     strat=strat, tag="SLEEP_ORDER")
    except Exception as e:
        tg(f"❌ 예약주문 실패: {e}"); return
    if oid is None: return
    watcher._fired = True
    # _pending_position 에 tag 저장 (예약주문 차단 조건 구별용)
    if hasattr(ref, '_pending_position') and isinstance(ref._pending_position, dict):
        ref._pending_position['tag'] = 'SLEEP_ORDER'
    tg(f"🌙 예약주문 실행\n{strat}\n${net:.2f}→${lmt:.2f}{agg}\nqty={qty} OID={oid}")
    watcher.status_changed.emit(f"✅ 주문완료  ${lmt:.2f}×{qty}")
