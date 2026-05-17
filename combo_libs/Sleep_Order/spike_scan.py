"""
spike_scan.py — 체인 스캔 + 주문 발사 로직  v1.1
════════════════════════════════════════
v1.1 변경:
  · fire_order → combo_direction 에 따라
    put_only / call_only / both(콜+풋 동시) 분기 추가
"""
from __future__ import annotations
import time as _time
from Sleep_Order.spike_utils import tg
from Sleep_Order.spike_scan_call_helper import find_call_item as _find_call_item


def calc_entry_price(net: float, sleep_cfg) -> float:
    if not sleep_cfg.aggressive_entry:
        return net
    tick = 0.10 if net >= 3.00 else 0.05
    return round(net + tick * max(1, int(sleep_cfg.aggressive_ticks)), 2)


def scan_and_check(watcher) -> None:
    """watcher = SleepOrderWatcher 인스턴스."""
    from Sleep_Order.sleep_order_config   import sleep_cfg
    from Sleep_Order.spike_watcher_debit  import DebitSpikeWatcher
    from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher, resolve_single_strikes
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end): return

    chain_put = getattr(ref, '_chain_put', {})
    if len([v for v in chain_put.values() if v and v > 0]) < 3: return
    _pend = getattr(ref, '_pending_position', {})
    if (getattr(ref, '_chaser_current_oid', None)
            and _pend.get('status') == '미체결'
            and _pend.get('tag', '') == 'SLEEP_ORDER'):
        return

    try: und = ref._sleep_get_underlying_price()
    except Exception: return
    if not und or und <= 0: return

    now_ts = _time.monotonic()
    if now_ts - watcher._last_range_reset >= 60:
        watcher._last_range_reset = now_ts
        DebitSpikeWatcher.get().evict_out_of_range(und)

    try: chain = ref._sleep_get_chain(sleep_cfg.expiry_offset)
    except Exception: return
    if not chain: return

    dmin = sleep_cfg.strike_dist_min / 100.0
    dmax = sleep_cfg.strike_dist_max / 100.0
    direction = sleep_cfg.combo_direction  # "put_only" | "call_only" | "both"

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
                if direction == "put_only":
                    # 기존 방식 — 풋 스프레드 단독 발주
                    fire_order(watcher, legs, net_r, strat, side="put")
                elif direction == "call_only":
                    # 콜 스프레드 단독 발주 (call legs 별도 조회)
                    call_item = _find_call_item(ref, strike, sleep_cfg)
                    if call_item:
                        fire_order(watcher, call_item["legs"],
                                   call_item["net"], call_item["strat"], side="call")
                elif direction == "both":
                    # 콜+풋 동시 발주
                    fire_order_both(watcher, legs, net_r, strat, ref, sleep_cfg)
                break

    if sleep_cfg.single_spike_enabled:
        cp = sleep_cfg.single_cp
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


# ── 단방향 발주 ──────────────────────────────────────────────────

def fire_order(watcher, legs: list, net: float,
               strat: str, side: str = "put") -> None:
    """put_only / call_only 단방향 발주."""
    from Sleep_Order.sleep_order_config import sleep_cfg
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end): return
    lmt   = calc_entry_price(net, sleep_cfg)
    budget = (sleep_cfg.combo_call_budget if side == "call"
              else sleep_cfg.combo_put_budget)
    qty   = max(1, int(budget // (lmt * 100)))
    total = round(lmt * qty * 100, 2)
    agg   = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    side_tag = "CALL_ONLY" if side == "call" else "PUT_ONLY"
    if sleep_cfg.dry_run:
        watcher._fired = True
        tg(f"🧪 [드라이런] 예약주문 {side_tag}\n{strat}\n"
           f"${net:.2f}→${lmt:.2f}{agg} qty={qty} 총=${total}\n⚠ 미전송")
        watcher.status_changed.emit(f"🧪 드라이런 {side_tag}  ${lmt:.2f}×{qty}")
        return
    try:
        oid = ref._sleep_place_order(legs=legs, lmt_price=lmt, qty=qty,
                                     strat=strat, tag="SLEEP_ORDER")
    except Exception as e:
        tg(f"❌ 예약주문 실패: {e}"); return
    if oid is None: return
    watcher._fired = True
    if hasattr(ref, '_pending_position') and isinstance(ref._pending_position, dict):
        ref._pending_position['tag'] = 'SLEEP_ORDER'
    tg(f"🌙 예약주문 [{side_tag}]\n{strat}\n"
       f"${net:.2f}→${lmt:.2f}{agg} qty={qty} OID={oid}")
    watcher.status_changed.emit(f"✅ 주문완료 {side_tag}  ${lmt:.2f}×{qty}")


# ── 양방향 동시 발주 ─────────────────────────────────────────────

def fire_order_both(watcher, put_legs: list, put_net: float,
                    put_strat: str, ref: object, sleep_cfg) -> None:
    """콜+풋 동시 발주. 각각 combo_call_budget / combo_put_budget 사용."""
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end):
        return
    agg = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    put_lmt = calc_entry_price(put_net, sleep_cfg)
    put_qty = max(1, int(sleep_cfg.combo_put_budget // (put_lmt * 100)))

    call_item = _find_call_item(ref, float(put_strat.split()[-1]), sleep_cfg)
    call_lmt = call_qty = call_oid = None
    if call_item:
        call_lmt = calc_entry_price(call_item["net"], sleep_cfg)
        call_qty = max(1, int(sleep_cfg.combo_call_budget // (call_lmt * 100)))

    if sleep_cfg.dry_run:
        watcher._fired = True
        msg = (f"🧪 [드라이런] 콜+풋 동시\n"
               f"PUT: ${put_lmt:.2f}×{put_qty}\n")
        if call_lmt:
            msg += f"CALL: ${call_lmt:.2f}×{call_qty}\n"
        msg += "⚠ 미전송"
        tg(msg)
        watcher.status_changed.emit("🧪 드라이런 BOTH")
        return

    # 풋 발주
    put_oid = None
    try:
        put_oid = ref._sleep_place_order(
            legs=put_legs, lmt_price=put_lmt, qty=put_qty,
            strat=put_strat, tag="SLEEP_ORDER_PUT")
    except Exception as e:
        tg(f"❌ [BOTH] 풋 주문 실패: {e}")

    # 콜 발주
    if call_item and call_lmt and call_qty:
        try:
            call_oid = ref._sleep_place_order(
                legs=call_item["legs"], lmt_price=call_lmt, qty=call_qty,
                strat=call_item["strat"], tag="SLEEP_ORDER_CALL")
        except Exception as e:
            tg(f"❌ [BOTH] 콜 주문 실패: {e}")

    watcher._fired = True
    if hasattr(ref, '_pending_position') and isinstance(ref._pending_position, dict):
        ref._pending_position['tag'] = 'SLEEP_ORDER'

    msg = f"🌙 콜+풋 동시 주문\n"
    if put_oid:
        msg += f"PUT ${put_lmt:.2f}×{put_qty} OID={put_oid}\n"
    if call_oid:
        msg += f"CALL ${call_lmt:.2f}×{call_qty} OID={call_oid}\n"
    tg(msg.strip())
    watcher.status_changed.emit(
        f"✅ BOTH  PUT×{put_qty} / CALL×{call_qty or 0}")

