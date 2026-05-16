"""
sleep_order_config.py — 수면 예약 주문 전체 설정  v3.0
════════════════════════════════════════
섹션 A : 예약 주문
섹션 B1: Debit Spread 급락 캐치
섹션 B2: 단일 옵션 급락 캐치  [신규]
섹션 C : 자동 매도
"""
from __future__ import annotations
import json, copy
from pathlib import Path
from Sleep_Order.sleep_order_config_props import _SingleSellProps
from Sleep_Order.sleep_order_config_single import SINGLE_DEFAULTS

try:
    from core import SAVE_DIR
except ImportError:
    SAVE_DIR = Path(".")

_CONFIG_FILE = SAVE_DIR / "sleep_order_settings.json"

_DEFAULTS: dict = {
    # ── A: 예약 주문 ─────────────────────────────────────
    "schedule_start":       "04:40",
    "schedule_end":         "05:14",
    "expiry_offset":        1,
    "strike_dist_min":      0.60,
    "strike_dist_max":      0.95,
    "spread_width":         20,
    "target_price_1":       0.50,
    "target_price_2":       0.40,
    "max_budget":           100,
    "schedule_enabled":     False,
    "roi_min":              0,
    "roi_max":              1200,
    "aggressive_entry":     True,
    "aggressive_ticks":     1,
    "cancel_cooldown_sec":  120,
    "dry_run":              False,


    # ── B1: Debit Spread 급락 캐치 ───────────────────────
    "spike_enabled":            False,
    "spike_use_own_schedule":   True,
    "spike_start":              "16:53",
    "spike_end":                "05:14",
    "spike_ref_mode":           "time",   # "time" | "tick"
    "spike_ref_minutes":        3,
    "tick_window":              7,
    "drop_ratio":               40,
    "abs_floor":                0.20,
    "order_mode":               "ask+1",
    "fixed_price":              0.15,
    "spike_budget":             100,
    "modify_wait_sec":          2,
    "modify_step":              0.05,
    "modify_max_count":         3,
    "modify_price_cap":         0.30,

    # ── B2: 단일 옵션 급락 캐치 [신규] ───────────────────
    "single_spike_enabled":         False,
    "single_spike_use_own_schedule":True,
    "single_spike_start":           "16:53",
    "single_spike_end":             "05:14",
    "single_spike_ref_mode":        "time",
    "single_spike_ref_minutes":     3,
    "single_tick_window":           7,
    "single_drop_ratio":            40,
    "single_abs_floor":             0.20,
    # 행사가 지정 방식: "direct"|"atm_offset"|"dist_pct"|"range"
    "single_strike_mode":           "atm_offset",
    "single_strike_value":          0.0,   # direct=행사가, atm_offset=±N포인트
    "single_dist_pct":              0.50,  # dist_pct 전용: 지수 대비 %
    "single_dist_min":              0.30,  # range 전용: 하한 %
    "single_dist_max":              0.80,  # range 전용: 상한 %
    "single_cp":                    "P",   # "P" | "C"
    "single_order_mode":            "ask+1",
    "single_fixed_price":           0.15,
    "single_budget":                100,
    "single_modify_wait_sec":       2,
    "single_modify_step":           0.05,
    "single_modify_max_count":      3,
    "single_modify_price_cap":      0.30,

    # ── C: 자동 매도 ─────────────────────────────────────
    "auto_sell_enabled":        False,
    "auto_sell_mode":           "multiplier",
    "auto_sell_fixed_price":    2.50,
    "auto_sell_multiplier":     3.0,
    # 단일 옵션 전용 자동매도 (Debit 과 별도 설정 가능)
    "single_auto_sell_enabled":     False,
    "single_auto_sell_mode":        "multiplier",
    "single_auto_sell_fixed_price": 2.50,
    "single_auto_sell_multiplier":  3.0,
}

_DEFAULTS.update(SINGLE_DEFAULTS)


class SleepOrderConfigStore(_SingleSellProps):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: dict = {}
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        self._data = copy.deepcopy(_DEFAULTS)
        if _CONFIG_FILE.exists():
            try:
                saved = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                self._data.update(saved)
            except Exception as e:
                print(f"[SleepCfg] 로드 실패: {e}")

    def save(self) -> None:
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            print(f"[SleepCfg] 저장 실패: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def all(self) -> dict:
        return copy.deepcopy(self._data)

    # ── A 프로퍼티 ───────────────────────────────────────
    @property
    def schedule_start(self) -> str:      return str(self._data.get("schedule_start", "04:40"))
    @property
    def schedule_end(self) -> str:        return str(self._data.get("schedule_end",   "05:14"))
    @property
    def expiry_offset(self) -> int:       return int(self._data.get("expiry_offset", 1))
    @property
    def strike_dist_min(self) -> float:   return float(self._data.get("strike_dist_min", 0.60))
    @property
    def strike_dist_max(self) -> float:   return float(self._data.get("strike_dist_max", 0.95))
    @property
    def spread_width(self) -> int:        return int(self._data.get("spread_width", 20))
    @property
    def target_price_1(self) -> float:    return float(self._data.get("target_price_1", 0.50))
    @property
    def target_price_2(self) -> float:    return float(self._data.get("target_price_2", 0.40))
    @property
    def max_budget(self) -> int:          return int(self._data.get("max_budget", 100))
    @property
    def schedule_enabled(self) -> bool:   return bool(self._data.get("schedule_enabled", False))
    @property
    def roi_min(self) -> int:             return int(self._data.get("roi_min", 0))
    @property
    def roi_max(self) -> int:             return int(self._data.get("roi_max", 1200))
    @property
    def aggressive_entry(self) -> bool:   return bool(self._data.get("aggressive_entry", True))
    @property
    def aggressive_ticks(self) -> int:    return int(self._data.get("aggressive_ticks", 1))
    @property
    def cancel_cooldown_sec(self) -> int: return int(self._data.get("cancel_cooldown_sec", 120))
    @property
    def dry_run(self) -> bool:            return bool(self._data.get("dry_run", False))

    # ── B1 프로퍼티 ──────────────────────────────────────
    @property
    def spike_enabled(self) -> bool:          return bool(self._data.get("spike_enabled", False))
    @property
    def spike_use_own_schedule(self) -> bool: return bool(self._data.get("spike_use_own_schedule", True))
    @property
    def spike_start(self) -> str:
        return str(self._data.get("spike_start", "16:53")) if self.spike_use_own_schedule else self.schedule_start
    @property
    def spike_end(self) -> str:
        return str(self._data.get("spike_end", "05:14")) if self.spike_use_own_schedule else self.schedule_end
    @property
    def spike_ref_mode(self) -> str:      return str(self._data.get("spike_ref_mode", "time"))
    @property
    def spike_ref_minutes(self) -> int:   return int(self._data.get("spike_ref_minutes", 3))
    @property
    def tick_window(self) -> int:         return int(self._data.get("tick_window", 7))
    @property
    def drop_ratio(self) -> int:          return int(self._data.get("drop_ratio", 40))
    @property
    def abs_floor(self) -> float:         return float(self._data.get("abs_floor", 0.20))
    @property
    def order_mode(self) -> str:          return str(self._data.get("order_mode", "ask+1"))
    @property
    def fixed_price(self) -> float:       return float(self._data.get("fixed_price", 0.15))
    @property
    def spike_budget(self) -> int:        return int(self._data.get("spike_budget", 100))
    @property
    def modify_wait_sec(self) -> int:     return int(self._data.get("modify_wait_sec", 2))
    @property
    def modify_step(self) -> float:       return float(self._data.get("modify_step", 0.05))
    @property
    def modify_max_count(self) -> int:    return int(self._data.get("modify_max_count", 3))
    @property
    def modify_price_cap(self) -> float:  return float(self._data.get("modify_price_cap", 0.30))


sleep_cfg = SleepOrderConfigStore()
