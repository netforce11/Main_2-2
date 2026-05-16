"""
spike_watcher_debit.py — DebitSpikeWatcher 싱글톤  v2.0
════════════════════════════════════════
스프레드별 DebitSpikeCatcher 관리.
"""
from __future__ import annotations
import threading
from typing import Dict, Optional

from Sleep_Order.spike_catcher_debit import DebitSpikeCatcher
from Sleep_Order.spike_utils          import tg
class DebitSpikeWatcher:
    """싱글톤. DebitSpikeCatcher 딕셔너리 관리."""
    _inst: Optional["DebitSpikeWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                o._catchers: Dict[str, DebitSpikeCatcher] = {}
                cls._inst = o
        return cls._inst

    @classmethod
    def get(cls) -> "DebitSpikeWatcher":
        return cls()

    def register(self, key: str, ref: object,
                 legs: list, strat: str = "") -> DebitSpikeCatcher:
        with self._mu:
            if key not in self._catchers:
                self._catchers[key] = DebitSpikeCatcher(key, ref, legs, strat)
            return self._catchers[key]

    def on_price_update(self, key: str, net: float, ask: float = 0.0) -> None:
        with self._mu:
            c = self._catchers.get(key)
        if c:
            c.on_price_update(net, ask)

    def unwatch_by_oid(self, oid: int, fill_price: float = 0.0) -> bool:
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_filled(fill_price); return True
            if c._sell_oid == oid:
                tg(f"✅ Debit 자동매도 체결 OID={oid} ${fill_price:.2f}")
                with c._lock: c._sell_oid = None
                return True
        return False

    def unwatch_cancelled_by_oid(self, oid: int) -> bool:
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_cancelled(); return True
        return False

    def evict_out_of_range(self, und_price: float) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        dmin = sleep_cfg.strike_dist_min / 100.0
        dmax = sleep_cfg.strike_dist_max / 100.0
        def _strike_from_key(k: str) -> float:
            try: return float(k.rsplit('_', 1)[0])
            except Exception: return 0.0
        with self._mu:
            to_del = [k for k, c in self._catchers.items()
                      if not c._fired and _strike_from_key(k) > 0 and not (
                          dmin <= abs(und_price - _strike_from_key(k)) / und_price <= dmax)]
            for k in to_del:
                del self._catchers[k]
        if to_del:
            print(f"[DebitSpikeWatcher] 범위 이탈 제거: {to_del}")

    def reset_all(self) -> None:
        with self._mu:
            for c in self._catchers.values(): c.reset()
            self._catchers.clear()

    def reconfigure_all(self) -> None:
        with self._mu:
            for c in self._catchers.values(): c.reconfigure()