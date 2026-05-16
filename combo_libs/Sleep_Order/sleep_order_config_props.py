"""
sleep_order_config_props.py — B2/C 섹션 프로퍼티 (SleepOrderConfigStore 믹스인)
════════════════════════════════════════
B2: 단일 옵션 급락 캐치 / C: 자동 매도
SleepOrderConfigStore 가 이 파일에서 import 해서 클래스 본체에 붙여씀.
직접 사용 금지.
"""
from __future__ import annotations
from typing import Optional


class _SingleSellProps:
    """SleepOrderConfigStore 에 믹스인되는 B2/C 프로퍼티."""
    _data: dict

    # ── B2 프로퍼티 ──────────────────────────────────────
    @property
    def single_spike_enabled(self) -> bool:          return bool(self._data.get("single_spike_enabled", False))
    @property
    def single_spike_use_own_schedule(self) -> bool: return bool(self._data.get("single_spike_use_own_schedule", True))
    @property
    def single_spike_start(self) -> str:
        return str(self._data.get("single_spike_start", "16:53")) if self.single_spike_use_own_schedule else self.schedule_start
    @property
    def single_spike_end(self) -> str:
        return str(self._data.get("single_spike_end", "05:14")) if self.single_spike_use_own_schedule else self.schedule_end
    @property
    def single_spike_ref_mode(self) -> str:     return str(self._data.get("single_spike_ref_mode", "time"))
    @property
    def single_spike_ref_minutes(self) -> int:  return int(self._data.get("single_spike_ref_minutes", 3))
    @property
    def single_tick_window(self) -> int:        return int(self._data.get("single_tick_window", 7))
    @property
    def single_drop_ratio(self) -> int:         return int(self._data.get("single_drop_ratio", 40))
    @property
    def single_abs_floor(self) -> float:        return float(self._data.get("single_abs_floor", 0.20))
    @property
    def single_strike_mode(self) -> str:        return str(self._data.get("single_strike_mode", "atm_offset"))
    @property
    def single_strike_value(self) -> float:     return float(self._data.get("single_strike_value", 0.0))
    @property
    def single_dist_pct(self) -> float:         return float(self._data.get("single_dist_pct", 0.50))
    @property
    def single_dist_min(self) -> float:         return float(self._data.get("single_dist_min", 0.30))
    @property
    def single_dist_max(self) -> float:         return float(self._data.get("single_dist_max", 0.80))
    @property
    def single_cp(self) -> str:                 return str(self._data.get("single_cp", "P"))
    @property
    def single_order_mode(self) -> str:         return str(self._data.get("single_order_mode", "ask+1"))
    @property
    def single_fixed_price(self) -> float:      return float(self._data.get("single_fixed_price", 0.15))
    @property
    def single_budget(self) -> int:             return int(self._data.get("single_budget", 100))
    @property
    def single_modify_wait_sec(self) -> int:    return int(self._data.get("single_modify_wait_sec", 2))
    @property
    def single_modify_step(self) -> float:      return float(self._data.get("single_modify_step", 0.05))
    @property
    def single_modify_max_count(self) -> int:   return int(self._data.get("single_modify_max_count", 3))
    @property
    def single_modify_price_cap(self) -> float: return float(self._data.get("single_modify_price_cap", 0.30))

    # ── C 프로퍼티 ───────────────────────────────────────
    @property
    def auto_sell_enabled(self) -> bool:        return bool(self._data.get("auto_sell_enabled", False))
    @property
    def auto_sell_mode(self) -> str:            return str(self._data.get("auto_sell_mode", "multiplier"))
    @property
    def auto_sell_fixed_price(self) -> float:   return float(self._data.get("auto_sell_fixed_price", 2.50))
    @property
    def auto_sell_multiplier(self) -> float:    return float(self._data.get("auto_sell_multiplier", 3.0))
    @property
    def single_auto_sell_enabled(self) -> bool:       return bool(self._data.get("single_auto_sell_enabled", False))
    @property
    def single_auto_sell_mode(self) -> str:           return str(self._data.get("single_auto_sell_mode", "multiplier"))
    @property
    def single_auto_sell_fixed_price(self) -> float:  return float(self._data.get("single_auto_sell_fixed_price", 2.50))
    @property
    def single_auto_sell_multiplier(self) -> float:   return float(self._data.get("single_auto_sell_multiplier", 3.0))