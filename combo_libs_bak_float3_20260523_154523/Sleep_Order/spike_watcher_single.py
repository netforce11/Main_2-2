"""
spike_watcher_single.py — SingleOptSpikeWatcher + resolve_single_strikes  v1.0
════════════════════════════════════════
행사가 결정 헬퍼 + 싱글톤 Watcher.
"""
from __future__ import annotations
import threading
from typing import Dict, List, Optional

from Sleep_Order.spike_catcher_single import SingleOptSpikeCatcher
from Sleep_Order.spike_utils          import tg
def resolve_single_strikes(ref: object) -> List[float]:
    """
    설정값에 따라 감시할 행사가 목록을 반환.
    ref 객체에서 _und_price, _put_strikes/_call_strikes 를 읽음.
    """
    from Sleep_Order.sleep_order_config import sleep_cfg
    mode      = sleep_cfg.single_strike_mode
    cp        = sleep_cfg.single_cp
    und_price = float(getattr(ref, '_und_price', 0) or 0)
    raw_strikes: list = (getattr(ref, '_put_strikes', [])
                         if cp == "P" else getattr(ref, '_call_strikes', []))
    if not raw_strikes or und_price <= 0:
        return []

    if mode == "direct":
        target = sleep_cfg.single_strike_value
        return [target] if target > 0 else []

    if mode == "atm_offset":
        atm    = min(raw_strikes, key=lambda s: abs(s - und_price))
        target = atm + sleep_cfg.single_strike_value  # 음수=아래, 양수=위
        nearest = min(raw_strikes, key=lambda s: abs(s - target))
        return [nearest]

    if mode == "dist_pct":
        target = und_price * (1 - sleep_cfg.single_dist_pct / 100.0)
        nearest = min(raw_strikes, key=lambda s: abs(s - target))
        return [nearest]

    if mode == "range":
        dmin = sleep_cfg.single_dist_min / 100.0
        dmax = sleep_cfg.single_dist_max / 100.0
        return [s for s in raw_strikes
                if dmin <= abs(und_price - s) / und_price <= dmax]

    return []


class SingleOptSpikeWatcher:
    """싱글톤. SingleOptSpikeCatcher 관리."""
    _inst: Optional["SingleOptSpikeWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                o._catchers: Dict[float, SingleOptSpikeCatcher] = {}
                cls._inst = o
        return cls._inst

    @classmethod
    def get(cls) -> "SingleOptSpikeWatcher":
        return cls()

    def register(self, strike: float, ref: object, strat: str = "") -> SingleOptSpikeCatcher:
        from Sleep_Order.sleep_order_config import sleep_cfg
        with self._mu:
            if strike not in self._catchers:
                self._catchers[strike] = SingleOptSpikeCatcher(
                    strike, sleep_cfg.single_cp, ref, strat)
            return self._catchers[strike]

    def on_price_update(self, strike: float, price: float, ask: float = 0.0) -> None:
        with self._mu:
            c = self._catchers.get(strike)
        if c:
            c.on_price_update(price, ask)

    def unwatch_by_oid(self, oid: int, fill_price: float = 0.0) -> bool:
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_filled(fill_price); return True
            if c._sell_oid == oid:
                tg(f"✅ 단일옵션 자동매도 체결 OID={oid} ${fill_price:.2f}")
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

    def reset_all(self) -> None:
        with self._mu:
            for c in self._catchers.values(): c.reset()
            self._catchers.clear()

    def reconfigure_all(self) -> None:
        with self._mu:
            for c in self._catchers.values(): c.reconfigure()