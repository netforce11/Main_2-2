"""
spike_scan.py — 체인 스캔 + 주문 발사 로직  v1.5
════════════════════════════════════════
v1.5 변경 (조건 B — AND 동시 체결):
  · both 모드에 조건 B 적용
    - primary_direction(선호 방향) 기준으로 엄격 조건 평가
    - 선호 방향 통과 시 반대쪽 secondary_target_price(느슨) 즉시 체크
    - 양쪽 모두 통과해야만 동시 발사 — 한쪽 미달 시 이번 틱 대기
  · _fire_call_from_peek() 신규 — 보조 조건 통과 콜을 엄격 조건 재평가 없이 직접 발사
  · _peek_call_net() ROI 조건 추가 — 실제 발사 조건과 일치
  · _fire_put_from_chain() 매칭 실패 시 tg 알림 추가
  · 콜 발사 실패 시 풋 후속 발사 차단
  · _fire_call() tg 메시지 정리
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


def _now_str() -> str:
    """현재 시각 문자열 (ET 기준)."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = datetime.utcnow()
    return now.strftime("%H:%M:%S")


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

    direction = sleep_cfg.combo_direction

    # ── 단방향 중복 발주 가드 ─────────────────────────────────
    if direction != "both":
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

    try: put_chain = ref._sleep_get_chain(sleep_cfg.expiry_offset)
    except Exception: return
    if not put_chain: return

    # ════════════════════════════════════════════════════════
    # both 모드: 풋 루프 / 콜 루프 완전 분리  [조건 B]
    # ────────────────────────────────────────────────────────
    # 조건 B 규칙:
    #   · 주력(primary) 목표가: target_price_1  (엄격)
    #   · 보조(secondary) 목표가: secondary_target_price  (느슨, 고정값)
    #   · primary_direction == "put" 이면:
    #       풋이 target_price_1 충족 → 콜이 secondary_target_price 충족 → 동시 발사
    #   · primary_direction == "call" 이면:
    #       콜이 call_target_price 충족 → 풋이 secondary_target_price 충족 → 동시 발사
    #   · 어느 한쪽이 느슨한 조건도 못 맞추면 → 이번 틱은 발사 안 함 (계속 감시)
    # ════════════════════════════════════════════════════════
    if direction == "both":
        put_done  = getattr(watcher, '_put_fired',  False)
        call_done = getattr(watcher, '_call_fired', False)

        primary   = getattr(sleep_cfg, 'primary_direction', 'put')   # "put" | "call"
        sec_tp    = getattr(sleep_cfg, 'secondary_target_price', 0.65)

        # ── 풋 루프 ──────────────────────────────────────────
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
                    if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max): continue

                # DebitSpikeWatcher 등록 (급락캐치용)
                key   = f"{strike}_{sleep_cfg.expiry_offset}"
                strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
                DebitSpikeWatcher.get().register(key, ref, legs, strat)
                DebitSpikeWatcher.get().on_price_update(key, net_price, ask_price)

                net_r = round(net_price * 20) / 20

                # ── [조건 B] 풋이 주력인 경우만 풋 루프에서 발사 판단 ─
                # primary == "call" 이면 풋 루프는 DebitSpikeWatcher 등록만 하고 스킵
                if primary != "put":
                    continue

                if net_r <= sleep_cfg.target_price_1:
                    # 풋 주력 조건 통과 → 콜 보조 조건 즉시 체크
                    call_net = _peek_call_net(ref, und, sleep_cfg)
                    if call_net is not None and call_net <= sec_tp:
                        # 둘 다 통과 → 풋 먼저 발사, 콜은 이미 확인된 가격으로 직접 발사
                        _fire_put(watcher, ref, legs, net_r, strat, sleep_cfg)
                        if not watcher._call_fired:
                            _fire_call_from_peek(watcher, ref, und, sleep_cfg)
                    else:
                        # 콜이 보조 조건 미달 → 이번 틱 대기
                        _tg_wait_secondary("콜", call_net, sec_tp, watcher)
                    break

        # ── 콜 루프 ──────────────────────────────────────────
        if not call_done:
            if primary == "call":
                # 콜이 주력: call_target_price(엄격) 통과 시 풋 보조 조건 체크
                _scan_and_fire_call_b(watcher, ref, und, sleep_cfg,
                                      put_chain=put_chain, sec_tp=sec_tp)
            else:
                # 풋이 주력: 콜은 풋 루프에서 동시 발사되므로 여기선 skip
                pass

    # ════════════════════════════════════════════════════════
    # 단방향 모드 (put_only / call_only)
    # ════════════════════════════════════════════════════════
    else:
        if watcher._fired:
            return

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
                if not (sleep_cfg.roi_min <= roi <= sleep_cfg.roi_max): continue

            key   = f"{strike}_{sleep_cfg.expiry_offset}"
            strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
            DebitSpikeWatcher.get().register(key, ref, legs, strat)
            DebitSpikeWatcher.get().on_price_update(key, net_price, ask_price)

            net_r = round(net_price * 20) / 20
            if net_r <= sleep_cfg.target_price_1:
                if direction == "put_only":
                    fire_order(watcher, legs, net_r, strat, side="put")
                elif direction == "call_only":
                    call_item = _find_call_item(ref, strike, sleep_cfg)
                    if call_item:
                        fire_order(watcher, call_item["legs"],
                                   call_item["net"], call_item["strat"], side="call")
                break

    # ── 단일 옵션 급락캐치 ────────────────────────────────────
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


# ── 콜 루프 스캔 + 발사 ──────────────────────────────────────────

def _scan_and_fire_call(watcher, ref, und: float, sleep_cfg) -> None:
    """
    _chain_call 을 직접 순회해서 콜 조건을 독립 평가하고 발사.
    풋 루프와 완전히 분리 — 풋 조건과 무관하게 동작.
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call:
        return

    width = sleep_cfg.spread_width
    dmin  = sleep_cfg.call_dist_min / 100.0
    dmax  = sleep_cfg.call_dist_max / 100.0

    # 행사가 거리 순으로 정렬 (ATM 가까운 것부터)
    sorted_strikes = sorted(call_strikes, key=lambda s: abs(und - s))

    for buy_strike in sorted_strikes:
        # 거리 조건
        if und > 0:
            dist_pct = abs(und - buy_strike) / und
            if not (dmin <= dist_pct <= dmax):
                continue

        # 매도 행사가 (buy + width)
        sell_strike = min(call_strikes, key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike:
            continue

        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        if buy_prem <= 0 or sell_prem <= 0 or buy_prem <= sell_prem:
            continue
        net = round(buy_prem - sell_prem, 2)
        if net <= 0:
            continue

        # ROI 조건
        mp = (sleep_cfg.spread_width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue

        # 가격 상한 조건
        net_r = round(net * 20) / 20
        if net_r > sleep_cfg.call_target_price:
            continue

        # 조건 모두 통과 → 발사
        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            sym_w  = getattr(ref, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
            def _cid(s): return int(_CONID_CACHE.get(_conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0

        tick = 0.10 if net >= 3.0 else 0.05
        call_item = {
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
        _fire_call(watcher, ref, call_item, sleep_cfg)
        break   # 콜도 첫 번째 조건 충족 행사가에서 발사


# ── both 모드 풋 발사 ────────────────────────────────────────────

def _fire_put(watcher, ref, legs: list, net: float,
              strat: str, sleep_cfg) -> None:
    """both 모드 전용 풋 발사."""
    agg     = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    put_lmt = calc_entry_price(net, sleep_cfg)
    put_qty = max(1, int(sleep_cfg.combo_put_budget // (put_lmt * 100)))

    if sleep_cfg.dry_run:
        watcher._put_fired = True
        watcher._fired = watcher._put_fired and watcher._call_fired
        tg(f"🧪 [드라이런] PUT 발사\n{strat}\n"
           f"${net:.2f}→${put_lmt:.2f}{agg} qty={put_qty}\n⚠ 미전송")
        watcher.status_changed.emit(
            f"🧪 드라이런 PUT  ${put_lmt:.2f}×{put_qty}"
            f"{'  CALL대기…' if not watcher._call_fired else ''}")
        return

    try:
        put_oid = ref._sleep_place_order(
            legs=legs, lmt_price=put_lmt, qty=put_qty,
            strat=strat, tag="SLEEP_ORDER_PUT")
    except Exception as e:
        tg(f"❌ [BOTH] 풋 주문 실패: {e}"); return
    if put_oid is None: return

    watcher._put_fired = True
    watcher._fired = watcher._put_fired and watcher._call_fired

    if not hasattr(ref, '_pending_both') or not isinstance(ref._pending_both, dict):
        ref._pending_both = {}
    ref._pending_both.update({
        'put_oid': put_oid, 'put_strat': strat,
        'put_lmt': put_lmt, 'put_qty':   put_qty, 'put_status': '미체결',
    })
    # _pending_position 초기 설정 (chaser 호환)
    ref._pending_position = {
        "strategy": strat, "qty": put_qty, "entry": put_lmt,
        "current": put_lmt, "side": "BUY",
        "oid": put_oid, "legs": legs, "status": "미체결", "tag": "SLEEP_ORDER_PUT",
    }
    used    = round(put_lmt * put_qty * 100, 2)
    remain  = round(sleep_cfg.combo_put_budget - used, 2)
    tg(f"✅ [체결] 풋 스프레드 매수\n"
       f"────────────────────\n"
       f"📋 {strat}\n"
       f"🔢 수량: {put_qty}계약\n"
       f"💰 체결가: ${put_lmt:.2f}{agg}  (net ${net:.2f})\n"
       f"💵 총 매수금액: ${used:,.0f}\n"
       f"🪙 잔액: ${remain:,.0f}\n"
       f"🔖 OID: {put_oid}\n"
       f"🕐 {_now_str()} ET"
       f"{'  ⏳ CALL 대기중…' if not watcher._call_fired else ''}")
    # 양방향 모두 완료 시 합산 요약
    if watcher._fired:
        _tg_both_summary(ref, sleep_cfg)
    watcher.status_changed.emit(
        f"✅ PUT×{put_qty}"
        f"{'  CALL대기…' if not watcher._call_fired else '  BOTH완료'}") 


# ── both 모드 콜 발사 ────────────────────────────────────────────

def _fire_call(watcher, ref, call_item: dict, sleep_cfg) -> None:
    """both 모드 전용 콜 발사."""
    net      = call_item["net"]
    strat    = call_item["strat"]
    legs     = call_item["legs"]
    agg      = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
    call_lmt = calc_entry_price(net, sleep_cfg)
    call_qty = max(1, int(sleep_cfg.combo_call_budget // (call_lmt * 100)))

    if sleep_cfg.dry_run:
        watcher._call_fired = True
        watcher._fired = watcher._put_fired and watcher._call_fired
        tg(f"🧪 [드라이런] CALL 발사\n{strat}\n"
           f"${net:.2f}→${call_lmt:.2f}{agg} qty={call_qty}\n⚠ 미전송")
        watcher.status_changed.emit(
            f"🧪 드라이런 CALL  ${call_lmt:.2f}×{call_qty}"
            f"{'  PUT대기…' if not watcher._put_fired else ''}")
        return

    try:
        call_oid = ref._sleep_place_order(
            legs=legs, lmt_price=call_lmt, qty=call_qty,
            strat=strat, tag="SLEEP_ORDER_CALL")
    except Exception as e:
        tg(f"❌ [BOTH] 콜 주문 실패: {e}"); return
    if call_oid is None: return

    watcher._call_fired = True
    watcher._fired = watcher._put_fired and watcher._call_fired

    if not hasattr(ref, '_pending_both') or not isinstance(ref._pending_both, dict):
        ref._pending_both = {}
    ref._pending_both.update({
        'call_oid': call_oid, 'call_strat': strat,
        'call_lmt': call_lmt, 'call_qty':   call_qty, 'call_status': '미체결',
    })
    used   = round(call_lmt * call_qty * 100, 2)
    remain = round(sleep_cfg.combo_call_budget - used, 2)
    tg(f"✅ [체결] 콜 스프레드 매수\n"
       f"────────────────────\n"
       f"📋 {strat}\n"
       f"🔢 수량: {call_qty}계약\n"
       f"💰 체결가: ${call_lmt:.2f}{agg}  (net ${net:.2f})\n"
       f"💵 총 매수금액: ${used:,.0f}\n"
       f"🪙 잔액: ${remain:,.0f}\n"
       f"🔖 OID: {call_oid}\n"
       f"🕐 {_now_str()} ET"
       f"{'  ⏳ PUT 대기중…' if not watcher._put_fired else ''}")
    # 양방향 모두 완료 시 합산 요약
    if watcher._fired:
        _tg_both_summary(ref, sleep_cfg)
    watcher.status_changed.emit(
        f"✅ CALL×{call_qty}"
        f"{'  PUT대기…' if not watcher._put_fired else '  BOTH완료'}")


# ── [조건 B] 콜 현재 net 조회 (발사 없이 가격만 확인) ───────────

def _peek_call_net(ref, und: float, sleep_cfg) -> float | None:
    """
    _chain_call 을 순회해 첫 번째 거리 조건 통과 행사가의 net 을 반환.
    발사하지 않고 가격만 체크 — 조건 B 의 보조 조건 확인용.
    조건 통과 행사가가 없으면 None 반환.
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    if not call_strikes or not chain_call:
        return None

    width = sleep_cfg.spread_width
    dmin  = sleep_cfg.call_dist_min / 100.0
    dmax  = sleep_cfg.call_dist_max / 100.0
    sorted_strikes = sorted(call_strikes, key=lambda s: abs(und - s))

    for buy_strike in sorted_strikes:
        if und > 0:
            dist_pct = abs(und - buy_strike) / und
            if not (dmin <= dist_pct <= dmax):
                continue
        sell_strike = min(call_strikes, key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike:
            continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        if buy_prem <= 0 or sell_prem <= 0 or buy_prem <= sell_prem:
            continue
        net = round(buy_prem - sell_prem, 2)
        if net <= 0:
            continue
        # ROI 조건 (실제 발사 조건과 일치시킴)
        mp = (sleep_cfg.spread_width - net) * 100
        if mp <= 0:
            continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        return round(net * 20) / 20   # 틱 반올림 후 반환
    return None


# ── [조건 B] 콜이 주력일 때 콜 스캔 + 풋 보조 조건 동시 체크 ────

def _scan_and_fire_call_b(watcher, ref, und: float, sleep_cfg,
                           put_chain: list, sec_tp: float) -> None:
    """
    콜이 primary 일 때 사용.
    콜이 call_target_price(엄격) 통과 → 풋이 secondary_target_price(느슨) 통과
    → 둘 다 통과 시에만 동시 발사.
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call:
        return

    width = sleep_cfg.spread_width
    dmin  = sleep_cfg.call_dist_min / 100.0
    dmax  = sleep_cfg.call_dist_max / 100.0
    sorted_strikes = sorted(call_strikes, key=lambda s: abs(und - s))

    for buy_strike in sorted_strikes:
        if und > 0:
            dist_pct = abs(und - buy_strike) / und
            if not (dmin <= dist_pct <= dmax):
                continue
        sell_strike = min(call_strikes, key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike:
            continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        if buy_prem <= 0 or sell_prem <= 0 or buy_prem <= sell_prem:
            continue
        net = round(buy_prem - sell_prem, 2)
        if net <= 0:
            continue
        mp = (sleep_cfg.spread_width - net) * 100
        if mp <= 0:
            continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue
        net_r = round(net * 20) / 20
        if net_r > sleep_cfg.call_target_price:
            continue

        # 콜 주력 조건 통과 → 풋 보조 조건 즉시 체크
        put_net = _peek_put_net(put_chain, und, sleep_cfg)
        if put_net is None or put_net > sec_tp:
            _tg_wait_secondary("풋", put_net, sec_tp, watcher)
            break   # 이번 틱 발사 안 함 — 다음 틱에 재시도

        # 둘 다 통과 → 콜 먼저 발사, 풋 후속 발사
        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            sym_w  = getattr(ref, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
            def _cid(s): return int(_CONID_CACHE.get(_conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0

        tick = 0.10 if net >= 3.0 else 0.05
        call_item = {
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
        _fire_call(watcher, ref, call_item, sleep_cfg)

        # 풋 후속 발사 — 콜이 실제로 성공했을 때만
        if watcher._call_fired and not watcher._put_fired:
            _fire_put_from_chain(watcher, ref, put_chain, put_net, und, sleep_cfg)
        break


def _peek_put_net(put_chain: list, und: float, sleep_cfg) -> float | None:
    """put_chain 에서 첫 번째 거리 조건 통과 행사가의 net 반환 (발사 없이)."""
    dmin = sleep_cfg.strike_dist_min / 100.0
    dmax = sleep_cfg.strike_dist_max / 100.0
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
            return round(net_price * 20) / 20
    return None


def _fire_put_from_chain(watcher, ref, put_chain: list,
                          target_net: float, und: float, sleep_cfg) -> None:
    """put_chain 에서 target_net 과 일치하는 항목을 찾아 _fire_put() 호출."""
    dmin = sleep_cfg.strike_dist_min / 100.0
    dmax = sleep_cfg.strike_dist_max / 100.0
    for item in put_chain:
        strike    = float(item.get("strike", 0))
        net_price = float(item.get("put_net", 0))
        legs      = item.get("legs", [])
        if not strike or not legs: continue
        if not (dmin <= abs(und - strike) / und <= dmax): continue
        net_r = round(net_price * 20) / 20
        if abs(net_r - target_net) < 0.01:
            strat = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
            _fire_put(watcher, ref, legs, net_r, strat, sleep_cfg)
            return
    # 매칭 실패 — 콜만 체결된 상태이므로 텔레그램 알림
    tg(f"⚠️ [조건B] 콜 체결 후 풋 항목 매칭 실패\n"
       f"target_net=${target_net:.2f} — put_chain 재조회 필요")


def _fire_call_from_peek(watcher, ref, und: float, sleep_cfg) -> None:
    """
    _peek_call_net() 으로 이미 보조 조건 통과 확인된 콜을
    call_item 구성 후 _fire_call() 로 직접 발사.
    _scan_and_fire_call() 의 엄격 조건(call_target_price) 재평가 없이
    sec_tp 기준으로 이미 통과된 가격을 그대로 사용.
    """
    chain_call   = getattr(ref, '_chain_call', {})
    call_strikes = getattr(ref, '_call_strikes', [])
    expiry       = getattr(ref, '_current_expiry', '') or ''
    if not call_strikes or not chain_call:
        tg("⚠️ [조건B] 콜 발사 실패 — _chain_call 데이터 없음"); return

    width = sleep_cfg.spread_width
    dmin  = sleep_cfg.call_dist_min / 100.0
    dmax  = sleep_cfg.call_dist_max / 100.0
    sorted_strikes = sorted(call_strikes, key=lambda s: abs(und - s))

    for buy_strike in sorted_strikes:
        if und > 0:
            dist_pct = abs(und - buy_strike) / und
            if not (dmin <= dist_pct <= dmax):
                continue
        sell_strike = min(call_strikes, key=lambda s: abs(s - (buy_strike + width)))
        if sell_strike == buy_strike:
            continue
        buy_prem  = float(chain_call.get(buy_strike)  or 0)
        sell_prem = float(chain_call.get(sell_strike) or 0)
        if buy_prem <= 0 or sell_prem <= 0 or buy_prem <= sell_prem:
            continue
        net = round(buy_prem - sell_prem, 2)
        if net <= 0:
            continue
        mp = (sleep_cfg.spread_width - net) * 100
        if mp <= 0: continue
        roi = mp / (net * 100) * 100
        if not (sleep_cfg.call_roi_min <= roi <= sleep_cfg.call_roi_max):
            continue

        try:
            from combo_order_bag import _CONID_CACHE, _conid_key
            sym_w  = getattr(ref, 'edit_sym_combo', None)
            symbol = (sym_w.text().strip().upper() if sym_w else "SPX").replace("SPXW", "SPX")
            def _cid(s): return int(_CONID_CACHE.get(_conid_key(symbol, "C", s, expiry), 0))
        except ImportError:
            _cid = lambda s: 0

        tick = 0.10 if net >= 3.0 else 0.05
        call_item = {
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
        _fire_call(watcher, ref, call_item, sleep_cfg)
        return
    tg("⚠️ [조건B] 콜 발사 실패 — 보조 조건 통과 행사가 재탐색 실패")
    """보조 조건 미달 시 텔레그램 대기 메시지 (과도한 전송 방지: 30초에 1번)."""
    import time as _t
    attr = f"_sec_wait_sent_{side}"
    last = getattr(watcher, attr, 0)
    now  = _t.monotonic()
    if now - last < 30:
        return
    setattr(watcher, attr, now)
    net_str = f"${current_net:.2f}" if current_net is not None else "데이터 없음"
    tg(f"⏳ [조건B 대기] {side} 보조조건 미달\n"
       f"현재가: {net_str}  목표: ≤${threshold:.2f}\n"
       f"주력 조건 통과 — {side} 대기 중…")


# ── 양방향 체결 합산 요약 ────────────────────────────────────────

def _tg_both_summary(ref, sleep_cfg) -> None:
    """풋+콜 양방향 모두 체결 완료 시 합산 요약 메시지."""
    pb = getattr(ref, '_pending_both', {})
    call_lmt  = pb.get('call_lmt', 0)
    call_qty  = pb.get('call_qty', 0)
    put_lmt   = pb.get('put_lmt',  0)
    put_qty   = pb.get('put_qty',  0)
    call_used = round(call_lmt * call_qty * 100, 2)
    put_used  = round(put_lmt  * put_qty  * 100, 2)
    total     = round(call_used + put_used, 2)
    call_rem  = round(sleep_cfg.combo_call_budget - call_used, 2)
    put_rem   = round(sleep_cfg.combo_put_budget  - put_used,  2)
    tg(f"🎯 [양방향 체결 완료]\n"
       f"════════════════════\n"
       f"📈 콜: {pb.get('call_strat', '')}\n"
       f"   {call_qty}계약 × ${call_lmt:.2f} = ${call_used:,.0f}  (잔액 ${call_rem:,.0f})\n"
       f"📉 풋: {pb.get('put_strat', '')}\n"
       f"   {put_qty}계약 × ${put_lmt:.2f} = ${put_used:,.0f}  (잔액 ${put_rem:,.0f})\n"
       f"────────────────────\n"
       f"💵 합계 투입: ${total:,.0f}\n"
       f"🕐 {_now_str()} ET")


# ── 단방향 발주 ──────────────────────────────────────────────────

def fire_order(watcher, legs: list, net: float,
               strat: str, side: str = "put") -> None:
    """put_only / call_only 단방향 발주."""
    from Sleep_Order.sleep_order_config import sleep_cfg
    ref = watcher._ref
    if ref is None: return
    if not watcher._in_window(sleep_cfg.schedule_start, sleep_cfg.schedule_end): return
    lmt    = calc_entry_price(net, sleep_cfg)
    budget = (sleep_cfg.combo_call_budget if side == "call"
              else sleep_cfg.combo_put_budget)
    qty    = max(1, int(budget // (lmt * 100)))
    total  = round(lmt * qty * 100, 2)
    agg    = f" (+{sleep_cfg.aggressive_ticks}틱)" if sleep_cfg.aggressive_entry else ""
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
    remain = round(budget - total, 2)
    side_label = "📈 콜" if side == "call" else "📉 풋"
    tg(f"✅ [체결] {side_label} 스프레드 매수\n"
       f"────────────────────\n"
       f"📋 {strat}\n"
       f"🔢 수량: {qty}계약\n"
       f"💰 체결가: ${lmt:.2f}{agg}  (net ${net:.2f})\n"
       f"💵 총 매수금액: ${total:,.0f}\n"
       f"🪙 잔액: ${remain:,.0f}\n"
       f"🔖 OID: {oid}\n"
       f"🕐 {_now_str()} ET")
    watcher.status_changed.emit(f"✅ 주문완료 {side_tag}  ${lmt:.2f}×{qty}")