"""
spike_catcher_debit.py — DebitSpikeCatcher  v2.0
════════════════════════════════════════
Debit Spread 1개 급락 감시 → BAG 주문 → 정정 → 자동 매도.
싱글톤 Watcher: spike_watcher_debit.py
"""
from __future__ import annotations
import threading
from typing import Optional
from Sleep_Order.spike_tracker import build_tracker
from Sleep_Order.spike_utils   import tg, tick_size, in_time_window, calc_lmt, calc_qty


class DebitSpikeCatcher:

    def __init__(self, key: str, ref: object, legs: list, strat: str = ""):
        self._key = key; self._ref = ref; self._legs = legs; self._strat = strat
        self._fired = False; self._oid: Optional[int] = None
        self._sell_oid: Optional[int] = None
        self._current_lmt = 0.0; self._qty = 0; self._modify_count = 0
        self._modify_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._t_tick = self._t_time = None
        self.reconfigure()

    def reconfigure(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        self._t_tick = build_tracker("tick", sleep_cfg.spike_ref_minutes, sleep_cfg.tick_window)
        self._t_time = build_tracker("time", sleep_cfg.spike_ref_minutes, sleep_cfg.tick_window)

    def _tracker(self):
        from Sleep_Order.sleep_order_config import sleep_cfg
        return self._t_time if sleep_cfg.spike_ref_mode == "time" else self._t_tick

    def on_price_update(self, net: float, ask: float = 0.0) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        self._t_tick.update(net); self._t_time.update(net)
        if self._fired or not sleep_cfg.spike_enabled: return
        if not in_time_window(sleep_cfg.spike_start, sleep_cfg.spike_end): return
        ref = self._tracker().ref_price
        if ref is None: return
        drop = 1.0 - (net / ref if ref > 0 else 1.0)
        if drop >= sleep_cfg.drop_ratio / 100.0 and net <= sleep_cfg.abs_floor:
            self._fire(net, ask, ref)

    def _fire(self, net: float, ask: float, ref: float) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        with self._lock:
            if self._fired: return
            self._fired = True
        mode = (f"시간기준 {sleep_cfg.spike_ref_minutes}분"
                if sleep_cfg.spike_ref_mode == "time" else f"틱평균 {sleep_cfg.tick_window}개")
        lmt = calc_lmt(net, ask, sleep_cfg.order_mode, sleep_cfg.fixed_price)
        qty = calc_qty(lmt, sleep_cfg.spike_budget)
        print(f"[DebitSpike] ⚡ {self._key} [{mode}] ref=${ref:.2f}→${net:.2f} lmt=${lmt:.2f} qty={qty}")
        if sleep_cfg.dry_run:
            tg(f"🧪 [드라이런] Debit 급락캐치\n{self._strat}\n"
               f"기준${ref:.2f}→현재${net:.2f} ({(1-net/ref)*100:.1f}%)\n"
               f"매수${lmt:.2f} qty={qty}\n⚠ 미전송"); return
        oid = self._place_order(lmt, qty)
        with self._lock:
            if oid is None:
                self._fired = False; return
            self._oid = oid; self._current_lmt = lmt; self._qty = qty; self._modify_count = 0
        tg(f"⚡ Debit 급락캐치\n{self._strat}\n"
           f"기준${ref:.2f}→현재${net:.2f} ({(1-net/ref)*100:.1f}%)\n"
           f"매수${lmt:.2f} qty={qty} OID={oid}")
        self._arm_modify()

    def _arm_modify(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        t = threading.Timer(sleep_cfg.modify_wait_sec, self._try_modify)
        t.daemon = True; t.start()
        with self._lock: self._modify_timer = t

    def _try_modify(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        with self._lock:
            if self._oid is None: return
            if self._modify_count >= sleep_cfg.modify_max_count:
                tg(f"🚨 Debit 수동대응 필요\n{self._strat}\n최대정정초과 OID={self._oid}"); return
            new_lmt = round(self._current_lmt + sleep_cfg.modify_step, 2)
            if new_lmt > sleep_cfg.modify_price_cap:
                tg(f"⛔ Debit 정정상한 ${sleep_cfg.modify_price_cap:.2f} OID={self._oid}"); return
            self._modify_count += 1; prev = self._current_lmt
            self._current_lmt = new_lmt; oid = self._oid; cnt = self._modify_count
        self._modify_order(oid, new_lmt)
        tg(f"⚠ Debit 정정 {cnt}차\n${prev:.2f}→${new_lmt:.2f} OID={oid}")
        self._arm_modify()

    def _place_order(self, lmt: float, qty: int) -> Optional[int]:
        try:
            fn = getattr(self._ref, '_sleep_place_order', None)
            if fn is None: print("[DebitSpike] ❌ _sleep_place_order 없음"); return None
            return fn(legs=self._legs, lmt_price=lmt, qty=qty, strat=self._strat, tag="SPIKE_DEBIT")
        except Exception as e:
            print(f"[DebitSpike] ❌ 주문 실패: {e}"); return None

    def _modify_order(self, oid: int, new_lmt: float) -> None:
        try:
            fn = getattr(self._ref, '_sleep_modify_order', None)
            if fn: fn(oid=oid, new_lmt=new_lmt, legs=self._legs, qty=self._qty, strat=self._strat)
        except Exception as e: print(f"[DebitSpike] ❌ 정정 실패 OID={oid}: {e}")

    def on_filled(self, fill_price: float = 0.0) -> None:
        with self._lock:
            oid = self._oid; self._oid = None
            if self._modify_timer: self._modify_timer.cancel(); self._modify_timer = None
        if oid is not None: self._place_sell(fill_price)

    def _place_sell(self, fill_price: float) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        if not sleep_cfg.auto_sell_enabled: return
        buy = fill_price if fill_price > 0 else self._current_lmt
        if sleep_cfg.auto_sell_mode == "fixed":
            sell = sleep_cfg.auto_sell_fixed_price
        else:
            sell = round(buy * sleep_cfg.auto_sell_multiplier, 2)
            t = tick_size(sell); sell = round(round(sell/t)*t, 2)
        if sleep_cfg.dry_run:
            tg(f"🧪 [드라이런] Debit 자동매도\n${sell:.2f} qty={self._qty}"); return
        try:
            fn = getattr(self._ref, '_sleep_place_sell_order', None)
            if fn is None: tg(f"❌ _sleep_place_sell_order 없음\n수동매도 qty={self._qty}"); return
            oid = fn(legs=self._legs, lmt_price=sell, qty=self._qty, strat=self._strat, tag="SPIKE_DEBIT_SELL")
            with self._lock: self._sell_oid = oid
            tg(f"💰 Debit 자동매도\n${sell:.2f} qty={self._qty} OID={oid}")
        except Exception as e: tg(f"❌ Debit 자동매도 실패: {e}")

    def on_cancelled(self) -> None:
        with self._lock:
            self._oid = None; self._fired = False
            if self._modify_timer: self._modify_timer.cancel(); self._modify_timer = None

    def reset(self) -> None:
        with self._lock:
            self._fired = False; self._oid = None; self._sell_oid = None; self._modify_count = 0
            if self._modify_timer: self._modify_timer.cancel(); self._modify_timer = None
        self._t_tick.reset(); self._t_time.reset()
