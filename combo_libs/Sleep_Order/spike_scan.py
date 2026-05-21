"""
spike_scan.py — 체인 스캔 + 주문 발사 로직  v1.7
════════════════════════════════════════════════════════
v1.7 변경:
  · [BUG-FIX] _scan_and_fire_call_only: symbol NameError 수정
      net_r = _round_to_tick(net, symbol) → _get_symbol(ref) 사용
  · [XSP] _scan_and_fire_call / _scan_and_fire_call_b /
           _fire_call_from_peek 동일 버그 동일 패턴 일괄 수정
  · [ANOMALY] 콜 체인 이상 프리미엄 감지 — _check_call_anomaly() 추가
      buy_prem <= sell_prem / net 이론최대 초과 시 skip + tg 알림
  · v1.6 이하 모든 변경(재진입락·조건B·fire_lock 등) 유지
════════════════════════════════════════════════════════
"""
from __future__ import annotations
import threading
import time as _time
from Sleep_Order.spike_utils import tg as _tg_raw


def tg(msg: str) -> None:
    """텔레그램 전송 실패 시 주문 흐름 중단 방지 — 별도 스레드."""
    def _run():
        try: _tg_raw(msg)
        except Exception as e: print(f"[SpikeScan] TG 실패: {e}")
    threading.Thread(target=_run, daemon=True).start()


def _ensure_fire_lock(watcher) -> threading.Lock:
    if not hasattr(watcher, '_fire_lock'):
        watcher._fire_lock = threading.Lock()
    return watcher._fire_lock


from Sleep_Order.spike_scan_call_helper import find_call_item as _find_call_item


# ── 심볼·틱 유틸 ────────────────────────────────────────────────
_XSP_SYMBOLS = {"XSP", "XSPC", "XSPP"}


def _get_symbol(ref) -> str:
    sym_w = getattr(ref, 'edit_sym_combo', None)
    if sym_w: return sym_w.text().strip().upper()
    return "SPX"


def _opt_tick(net: float, symbol: str = "") -> float:
    """XSP: $0.01 고정 / SPX·SPXW: net 기준 0.05 or 0.10"""
    if symbol.upper() in _XSP_SYMBOLS: return 0.01
    return 0.10 if net >= 3.00 else 0.05


def _round_to_tick(net: float, symbol: str = "") -> float:
    """net 가격을 심볼 틱 단위로 반올림 (부동소수점 오차 방지)."""
    from decimal import Decimal, ROUND_HALF_UP
    tick = _opt_tick(net, symbol)
    d    = Decimal(str(net))
    step = Decimal(str(tick))
    return float((d / step).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * step)


def calc_entry_price(net: float, sleep_cfg, symbol: str = "") -> float:
    if not sleep_cfg.aggressive_entry: return net
    tick = _opt_tick(net, symbol)
    return round(net + tick * max(1, int(sleep_cfg.aggressive_ticks)), 2)


def _now_str() -> str:
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S")
    except Exception:
        return datetime.utcnow().strftime("%H:%M:%S")


# ── [v1.7] 콜 이상 프리미엄 감지 ───────────────────────────────

def _check_call_anomaly(buy_prem: float, sell_prem: float,
                        net: float, spread_width: float,
                        symbol: str, watcher=None) -> bool:
    """콜 스프레드 이상 프리미엄 감지. 이상 있으면 True.
    조건 ①: buy_prem <= sell_prem (스프레드 역전)
    조건 ②: net > spread_width * 0.9 (이론 최대 초과)
    """
    tag = f"[{symbol}]" if symbol else ""
    if buy_prem <= 0 or sell_prem <= 0:
        return True
    if buy_prem <= sell_prem:
        tg(f"⚠ 콜 이상{tag} buy≤sell: buy={buy_prem:.2f} sell={sell_prem:.2f}")
        return True
    if net > spread_width * 0.9:
        tg(f"⚠ 콜 이상{tag} net 이론최대 초과: {net:.2f} > {spread_width*0.9:.2f}")
        return True
    return False


# ── 메인 스캔 진입점 ─────────────────────────────────────────────

def scan_and_check(watcher) -> None:
    """재진입 방어 래퍼."""
    if getattr(watcher, '_scanning', False): return
    watcher._scanning = True
    try:
        _scan_and_check_inner(watcher)
    finally:
        watcher._scanning = False


def _scan_and_check_inner(watcher) -> None:
    from Sleep_Order.sleep_order_config   import sleep_cfg
    from Sleep_Order.spike_watcher_debit  import DebitSpikeWatcher
    from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher, resolve_single_strikes
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start,
                               sleep_cfg.schedule_end): return

    chain_put = getattr(ref, '_chain_put', {})
    if len([v for v in chain_put.values() if v and v > 0]) < 3: return

    direction = sleep_cfg.combo_direction
    if not watcher._fired:
        try:
            if DebitSpikeWatcher.get().any_fired():
                watcher.status_changed.emit("⚠ Debit캐치 발사됨 — 예약 중복 차단")
                return
        except Exception: pass

    if direction != "both":
        _pend = getattr(ref, '_pending_position', {})
        if (getattr(ref, '_chaser_current_oid', None)
                and _pend.get('status') == '미체결'
                and _pend.get('tag', '') == 'SLEEP_ORDER'):
            return

    try: und = ref._sleep_get_underlying_price()
    except Exception: return
    if not und or und <= 0: return

    _sym   = _get_symbol(ref)
    now_ts = _time.monotonic()
    if now_ts - watcher._last_range_reset >= 60:
        watcher._last_range_reset = now_ts
        DebitSpikeWatcher.get().evict_out_of_range(und)

    try: put_chain = ref._sleep_get_chain(sleep_cfg.expiry_offset)
    except Exception: return
    if not put_chain: return

    # ── both 모드 ───────────────────────────────────────────────
    if direction == "both":
        put_done  = getattr(watcher, '_put_fired',  False)
        call_done = getattr(watcher, '_call_fired', False)
        primary   = getattr(sleep_cfg, 'primary_direction', 'put')
        sec_tp    = getattr(sleep_cfg, 'secondary_target_price', 0.65)

        if not put_done:
            dmin = sleep_cfg.strike_dist_min / 100.0
            dmax = sleep_cfg.strike_dist_max / 100.0
            for item in put_chain:
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
                    if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max):
                        continue
                key   = f"{strike}_{sleep_cfg.expiry_offset}"
                strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
                DebitSpikeWatcher.get().register(key, ref, legs, strat)
                DebitSpikeWatcher.get().on_price_update(key, net_price, ask_price)
                net_r = _round_to_tick(net_price, _sym)
                if primary != "put": continue
                if net_r <= sleep_cfg.target_price_1:
                    call_net = _peek_call_net(ref, und, sleep_cfg)
                    if call_net is not None and call_net <= sec_tp:
                        _fire_put(watcher, ref, legs, net_r, strat, sleep_cfg)
                        if not watcher._call_fired:
                            _fire_call_from_peek(watcher, ref, und, sleep_cfg)
                    else:
                        _tg_wait_secondary("콜", call_net, sec_tp, watcher)
                    break

        if not call_done:
            if primary == "call":
                _scan_and_fire_call_b(watcher, ref, und, sleep_cfg,
                                      put_chain=put_chain, sec_tp=sec_tp)

    # ── 단방향 모드 ─────────────────────────────────────────────
    else:
        if watcher._fired: return
        if direction == "put_only":
            dmin = sleep_cfg.strike_dist_min / 100.0
            dmax = sleep_cfg.strike_dist_max / 100.0
            for item in put_chain:
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
                    if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max):
                        continue
                key   = f"{strike}_{sleep_cfg.expiry_offset}"
                strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
                DebitSpikeWatcher.get().register(key, ref, legs, strat)
                DebitSpikeWatcher.get().on_price_update(key, net_price, ask_price)
                net_r = _round_to_tick(net_price, _sym)
                if net_r <= sleep_cfg.target_price_1:
                    fire_order(watcher, legs, net_r, strat, side="put")
                    break
        elif direction == "call_only":
            _scan_and_fire_call_only(watcher, ref, und, sleep_cfg)

    # ── 단일 옵션 급락캐치 ──────────────────────────────────────
    if sleep_cfg.single_spike_enabled:
        cp_side = sleep_cfg.single_cp
        if cp_side == "P":
            live = getattr(ref, '_sleep_live_prices', {})
            chain_fb = getattr(ref, '_chain_put', {})
            src_map = {k: (live.get(k) or v) for k, v in chain_fb.items()}
        else:
            src_map = getattr(ref, '_chain_call', {})
        for s in resolve_single_strikes(ref):
            price = float(src_map.get(s) or 0.0)
            if price <= 0: continue
            SingleOptSpikeWatcher.get().register(s, ref, f"SINGLE_{cp_side} {s}")
            SingleOptSpikeWatcher.get().on_price_update(s, price)


# ── call_only 전용 스캔 ─────────────────────────────────────────

def _scan_and_fire_call_only(watcher, ref, und: float, sleep_cfg) -> None:
    """[v1.7 BUG-FIX] symbol NameError 수정 — _get_symbol(ref) 사용."""
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call: return

    symbol  = _get_symbol(ref).replace("SPXW", "SPX")   # [FIX]
    width   = sleep_cfg.spread_width
    dmin    = getattr(sleep_cfg, 'call_dist_min', sleep_cfg.strike_dist_min) / 100.0
    dmax    = getattr(sleep_cfg, 'call_dist_max', sleep_cfg.strike_dist_max) / 100.0
    roi_min = getattr(sleep_cfg, 'call_roi_min', sleep_cfg.roi_min)
    roi_max = getattr(sleep_cfg, 'call_roi_max', sleep_cfg.roi_max)
    target  = getattr(sleep_cfg, 'call_target_price', sleep_cfg.target_price_1)

    for buy_strike in sorted(call_strikes, key=lambda s: abs(und - s)):
        if und > 0 and not (dmin <= abs(und - buy_strike) / und <= dmax):
            continue
        sell_strike = min(call_strikes,
                          key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike: continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        net = round(buy_prem - sell_prem, 2)
        if _check_call_anomaly(buy_prem, sell_prem, net,
                                width, symbol): continue
        mp = (width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (roi_min <= roi <= roi_max): continue
        net_r = _round_to_tick(net, symbol)
        if net_r > target: continue

        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            def _cid(s):
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0
        tick = _opt_tick(net, symbol)
        call_item = {
            "net": net, "ask": round(net + tick, 2),
            "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {buy_strike}",
            "legs": [
                {"cp": "C", "strike": buy_strike, "expiry": expiry,
                 "dir": "BUY",  "qty": 1, "prem": buy_prem,
                 "con_id": _cid(buy_strike)},
                {"cp": "C", "strike": sell_strike, "expiry": expiry,
                 "dir": "SELL", "qty": 1, "prem": sell_prem,
                 "con_id": _cid(sell_strike)},
            ],
        }
        fire_order(watcher, call_item["legs"],
                   call_item["net"], call_item["strat"], side="call")
        break


def _scan_and_fire_call(watcher, ref, und: float, sleep_cfg) -> None:
    """both 모드 콜 루프 — 풋과 완전 독립. [v1.7] symbol 버그 수정."""
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call: return

    symbol = _get_symbol(ref).replace("SPXW", "SPX")   # [FIX]
    width  = sleep_cfg.spread_width
    dmin   = sleep_cfg.call_dist_min / 100.0
    dmax   = sleep_cfg.call_dist_max / 100.0

    for buy_strike in sorted(call_strikes, key=lambda s: abs(und - s)):
        if und > 0 and not (dmin <= abs(und - buy_strike) / und <= dmax):
            continue
        sell_strike = min(call_strikes,
                          key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike: continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        net = round(buy_prem - sell_prem, 2)
        if _check_call_anomaly(buy_prem, sell_prem, net,
                                width, symbol): continue
        mp = (width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        net_r = _round_to_tick(net, symbol)
        if net_r > sleep_cfg.call_target_price: continue

        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            def _cid(s):
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0
        tick = _opt_tick(net, symbol)
        call_item = {
            "net": net, "ask": round(net + tick, 2),
            "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {buy_strike}",
            "legs": [
                {"cp": "C", "strike": buy_strike, "expiry": expiry,
                 "dir": "BUY",  "qty": 1, "prem": buy_prem,
                 "con_id": _cid(buy_strike)},
                {"cp": "C", "strike": sell_strike, "expiry": expiry,
                 "dir": "SELL", "qty": 1, "prem": sell_prem,
                 "con_id": _cid(sell_strike)},
            ],
        }
        _fire_call(watcher, ref, call_item, sleep_cfg)
        break


# ── both 모드 풋/콜 발사 ─────────────────────────────────────────

def _fire_put(watcher, ref, legs: list, net: float,
              strat: str, sleep_cfg) -> None:
    _lock = _ensure_fire_lock(watcher)
    with _lock:
        if getattr(watcher, '_put_fired', False): return
        _sym = _get_symbol(ref)
        agg  = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
        put_lmt = calc_entry_price(net, sleep_cfg, symbol=_sym)
        put_qty = max(1, int(sleep_cfg.combo_put_budget // (put_lmt * 100)))
        if sleep_cfg.dry_run:
            watcher._put_fired = True
            watcher._fired = watcher._put_fired and watcher._call_fired
            tg(f"🧪 [드라이런] PUT\n{strat}\n${net:.2f}→${put_lmt:.2f}{agg} qty={put_qty}")
            watcher.status_changed.emit(f"🧪 드라이런 PUT  ${put_lmt:.2f}×{put_qty}")
            return
        watcher._put_fired = True
        watcher._fired = watcher._put_fired and watcher._call_fired
        try:
            put_oid = ref._sleep_place_order(
                legs=legs, lmt_price=put_lmt, qty=put_qty,
                strat=strat, tag="SLEEP_ORDER_PUT")
        except Exception as e:
            watcher._put_fired = False; watcher._fired = False
            tg(f"❌ [BOTH] 풋 주문 실패: {e}"); return
        if put_oid is None:
            watcher._put_fired = False; watcher._fired = False; return
        if not isinstance(getattr(ref, '_pending_both', None), dict):
            ref._pending_both = {}
        ref._pending_both.update(put_oid=put_oid, put_strat=strat,
                                  put_lmt=put_lmt, put_qty=put_qty,
                                  put_status='미체결')
        ref._pending_position = {
            "strategy": strat, "qty": put_qty, "entry": put_lmt,
            "current": put_lmt, "side": "BUY", "oid": put_oid,
            "legs": legs, "status": "미체결", "tag": "SLEEP_ORDER_PUT",
        }
        used = round(put_lmt * put_qty * 100, 2)
        tg(f"✅ 풋 스프레드 매수\n{strat}\n"
           f"${put_lmt:.2f}{agg} ×{put_qty} = ${used:,.0f}\n"
           f"🕐 {_now_str()} ET"
           f"{'  ⏳ CALL 대기중…' if not watcher._call_fired else ''}")
        if watcher._fired: _tg_both_summary(ref, sleep_cfg)
        watcher.status_changed.emit(
            f"✅ PUT×{put_qty}"
            f"{'  CALL대기…' if not watcher._call_fired else '  BOTH완료'}")


def _fire_call(watcher, ref, call_item: dict, sleep_cfg) -> None:
    _lock = _ensure_fire_lock(watcher)
    with _lock:
        if getattr(watcher, '_call_fired', False): return
        net   = call_item["net"]; strat = call_item["strat"]
        legs  = call_item["legs"]
        _sym  = _get_symbol(ref)
        agg   = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
        call_lmt = calc_entry_price(net, sleep_cfg, symbol=_sym)
        call_qty = max(1, int(sleep_cfg.combo_call_budget // (call_lmt * 100)))
        if sleep_cfg.dry_run:
            watcher._call_fired = True
            watcher._fired = watcher._put_fired and watcher._call_fired
            tg(f"🧪 [드라이런] CALL\n{strat}\n${net:.2f}→${call_lmt:.2f}{agg} qty={call_qty}")
            watcher.status_changed.emit(f"🧪 드라이런 CALL  ${call_lmt:.2f}×{call_qty}")
            return
        watcher._call_fired = True
        watcher._fired = watcher._put_fired and watcher._call_fired
        try:
            call_oid = ref._sleep_place_order(
                legs=legs, lmt_price=call_lmt, qty=call_qty,
                strat=strat, tag="SLEEP_ORDER_CALL")
        except Exception as e:
            watcher._call_fired = False; watcher._fired = False
            tg(f"❌ [BOTH] 콜 주문 실패: {e}"); return
        if call_oid is None:
            watcher._call_fired = False; watcher._fired = False; return
        if not isinstance(getattr(ref, '_pending_both', None), dict):
            ref._pending_both = {}
        ref._pending_both.update(call_oid=call_oid, call_strat=strat,
                                  call_lmt=call_lmt, call_qty=call_qty,
                                  call_status='미체결')
        used = round(call_lmt * call_qty * 100, 2)
        tg(f"✅ 콜 스프레드 매수\n{strat}\n"
           f"${call_lmt:.2f}{agg} ×{call_qty} = ${used:,.0f}\n"
           f"🕐 {_now_str()} ET"
           f"{'  ⏳ PUT 대기중…' if not watcher._put_fired else ''}")
        if watcher._fired: _tg_both_summary(ref, sleep_cfg)
        watcher.status_changed.emit(
            f"✅ CALL×{call_qty}"
            f"{'  PUT대기…' if not watcher._put_fired else '  BOTH완료'}")


# ── 조건 B 보조 함수들 ───────────────────────────────────────────

def _peek_call_net(ref, und: float, sleep_cfg) -> float | None:
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    if not call_strikes or not chain_call: return None
    symbol = _get_symbol(ref)
    width  = sleep_cfg.spread_width
    dmin   = sleep_cfg.call_dist_min / 100.0
    dmax   = sleep_cfg.call_dist_max / 100.0
    for buy_strike in sorted(call_strikes, key=lambda s: abs(und - s)):
        if und > 0 and not (dmin <= abs(und - buy_strike) / und <= dmax):
            continue
        sell_strike = min(call_strikes,
                          key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike: continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        net = round(buy_prem - sell_prem, 2)
        if _check_call_anomaly(buy_prem, sell_prem, net, width, symbol):
            continue
        mp = (width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        return _round_to_tick(net, symbol)
    return None


def _scan_and_fire_call_b(watcher, ref, und: float, sleep_cfg,
                           put_chain: list, sec_tp: float) -> None:
    """콜이 primary 일 때 — 콜 엄격·풋 보조 동시 체크."""
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call: return
    symbol = _get_symbol(ref).replace("SPXW", "SPX")   # [FIX]
    width  = sleep_cfg.spread_width
    dmin   = sleep_cfg.call_dist_min / 100.0
    dmax   = sleep_cfg.call_dist_max / 100.0

    for buy_strike in sorted(call_strikes, key=lambda s: abs(und - s)):
        if und > 0 and not (dmin <= abs(und - buy_strike) / und <= dmax):
            continue
        sell_strike = min(call_strikes,
                          key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike: continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        net = round(buy_prem - sell_prem, 2)
        if _check_call_anomaly(buy_prem, sell_prem, net, width, symbol):
            continue
        mp = (width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        net_r = _round_to_tick(net, symbol)
        if net_r > sleep_cfg.call_target_price: continue

        put_net = _peek_put_net(put_chain, und, sleep_cfg, ref)
        if put_net is None or put_net > sec_tp:
            _tg_wait_secondary("풋", put_net, sec_tp, watcher); break

        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            def _cid(s):
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0
        tick = _opt_tick(net, symbol)
        call_item = {
            "net": net, "ask": round(net + tick, 2),
            "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {buy_strike}",
            "legs": [
                {"cp": "C", "strike": buy_strike, "expiry": expiry,
                 "dir": "BUY",  "qty": 1, "prem": buy_prem,
                 "con_id": _cid(buy_strike)},
                {"cp": "C", "strike": sell_strike, "expiry": expiry,
                 "dir": "SELL", "qty": 1, "prem": sell_prem,
                 "con_id": _cid(sell_strike)},
            ],
        }
        _fire_call(watcher, ref, call_item, sleep_cfg)
        if watcher._call_fired and not watcher._put_fired:
            _fire_put_from_chain(watcher, ref, put_chain,
                                  put_net, und, sleep_cfg)
        break


def _peek_put_net(put_chain: list, und: float, sleep_cfg,
                   ref=None) -> float | None:
    dmin = sleep_cfg.strike_dist_min / 100.0
    dmax = sleep_cfg.strike_dist_max / 100.0
    sym  = _get_symbol(ref) if ref is not None else ""
    for item in put_chain:
        strike    = float(item.get("strike", 0))
        net_price = float(item.get("put_net", 0))
        legs      = item.get("legs", [])
        if not strike or not legs: continue
        if not (dmin <= abs(und - strike) / und <= dmax): continue
        if net_price > 0:
            mp = (sleep_cfg.spread_width - net_price) * 100
            if mp <= 0: continue
            roi = mp / (net_price * 100) * 100
            if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max): continue
            return _round_to_tick(net_price, sym)
    return None


def _fire_put_from_chain(watcher, ref, put_chain: list,
                          target_net: float, und: float,
                          sleep_cfg) -> None:
    dmin = sleep_cfg.strike_dist_min / 100.0
    dmax = sleep_cfg.strike_dist_max / 100.0
    for item in put_chain:
        strike    = float(item.get("strike", 0))
        net_price = float(item.get("put_net", 0))
        legs      = item.get("legs", [])
        if not strike or not legs: continue
        if not (dmin <= abs(und - strike) / und <= dmax): continue
        net_r = _round_to_tick(net_price, _get_symbol(ref))
        if abs(net_r - target_net) < 0.01:
            strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
            _fire_put(watcher, ref, legs, net_r, strat, sleep_cfg)
            return
    tg(f"⚠️ [조건B] 콜 체결 후 풋 항목 매칭 실패 target_net=${target_net:.2f}")


def _fire_call_from_peek(watcher, ref, und: float, sleep_cfg) -> None:
    """peek 에서 이미 확인된 콜 가격으로 직접 발사. [v1.7] symbol 버그 수정."""
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call:
        tg("⚠️ [조건B] 콜 발사 실패 — _chain_call 없음"); return
    symbol = _get_symbol(ref).replace("SPXW", "SPX")   # [FIX]
    width  = sleep_cfg.spread_width
    dmin   = sleep_cfg.call_dist_min / 100.0
    dmax   = sleep_cfg.call_dist_max / 100.0

    for buy_strike in sorted(call_strikes, key=lambda s: abs(und - s)):
        if und > 0 and not (dmin <= abs(und - buy_strike) / und <= dmax):
            continue
        sell_strike = min(call_strikes,
                          key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike: continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        net = round(buy_prem - sell_prem, 2)
        if _check_call_anomaly(buy_prem, sell_prem, net, width, symbol):
            continue
        mp = (width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            def _cid(s):
                return int(_CONID_CACHE.get(
                    _conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0
        tick = _opt_tick(net, symbol)
        call_item = {
            "net": net, "ask": round(net + tick, 2),
            "strat": f"CALL_SPREAD D+{sleep_cfg.expiry_offset} {buy_strike}",
            "legs": [
                {"cp": "C", "strike": buy_strike, "expiry": expiry,
                 "dir": "BUY",  "qty": 1, "prem": buy_prem,
                 "con_id": _cid(buy_strike)},
                {"cp": "C", "strike": sell_strike, "expiry": expiry,
                 "dir": "SELL", "qty": 1, "prem": sell_prem,
                 "con_id": _cid(sell_strike)},
            ],
        }
        _fire_call(watcher, ref, call_item, sleep_cfg)
        return
    tg("⚠️ [조건B] 콜 발사 실패 — 보조 조건 통과 행사가 재탐색 실패")


def _tg_wait_secondary(side: str, current_net, threshold: float,
                        watcher) -> None:
    """보조 조건 미달 텔레그램 알림 — 30초 쿨다운."""
    import time as _t
    attr = f"_sec_wait_sent_{side}"
    last = getattr(watcher, attr, 0)
    now  = _t.monotonic()
    if now - last < 30: return
    setattr(watcher, attr, now)
    net_str = f"${current_net:.2f}" if current_net is not None else "데이터 없음"
    tg(f"⏳ [조건B 대기] {side} 보조조건 미달\n"
       f"현재가: {net_str}  목표: ≤${threshold:.2f}")


def _tg_both_summary(ref, sleep_cfg) -> None:
    pb = getattr(ref, '_pending_both', {})
    call_lmt = pb.get('call_lmt', 0); call_qty = pb.get('call_qty', 0)
    put_lmt  = pb.get('put_lmt',  0); put_qty  = pb.get('put_qty',  0)
    call_used = round(call_lmt * call_qty * 100, 2)
    put_used  = round(put_lmt  * put_qty  * 100, 2)
    tg(f"🎯 [양방향 체결 완료]\n"
       f"📈 콜: {pb.get('call_strat','')} {call_qty}계약 ×${call_lmt:.2f}=${call_used:,.0f}\n"
       f"📉 풋: {pb.get('put_strat','')}  {put_qty}계약 ×${put_lmt:.2f}=${put_used:,.0f}\n"
       f"💵 합계: ${call_used+put_used:,.0f}  🕐 {_now_str()} ET")


def fire_order(watcher, legs: list, net: float,
               strat: str, side: str = "put") -> None:
    """put_only / call_only 단방향 발주."""
    from Sleep_Order.sleep_order_config import sleep_cfg
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start,
                               sleep_cfg.schedule_end): return
    _sym   = _get_symbol(ref)
    lmt    = calc_entry_price(net, sleep_cfg, symbol=_sym)
    budget = (sleep_cfg.combo_call_budget if side == "call"
              else sleep_cfg.combo_put_budget)
    qty    = max(1, int(budget // (lmt * 100)))
    agg    = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    total  = round(lmt * qty * 100, 2)
    side_tag = "CALL_ONLY" if side == "call" else "PUT_ONLY"
    if sleep_cfg.dry_run:
        watcher._fired = True
        tg(f"🧪 [드라이런] {side_tag}\n{strat}\n"
           f"${net:.2f}→${lmt:.2f}{agg} qty={qty}")
        watcher.status_changed.emit(f"🧪 드라이런 {side_tag}  ${lmt:.2f}×{qty}")
        return
    watcher._fired = True
    try:
        oid = ref._sleep_place_order(legs=legs, lmt_price=lmt, qty=qty,
                                     strat=strat, tag="SLEEP_ORDER")
    except Exception as e:
        watcher._fired = False; tg(f"❌ 예약주문 실패: {e}"); return
    if oid is None:
        watcher._fired = False; return
    remain = round(budget - total, 2)
    side_label = "📈 콜" if side == "call" else "📉 풋"
    tg(f"✅ {side_label} 스프레드 매수\n{strat}\n"
       f"${lmt:.2f}{agg} ×{qty} = ${total:,.0f}  잔액 ${remain:,.0f}\n"
       f"🔖 OID:{oid}  🕐 {_now_str()} ET")
    watcher.status_changed.emit(f"✅ 주문완료 {side_tag}  ${lmt:.2f}×{qty}")
