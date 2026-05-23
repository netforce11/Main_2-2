"""
sleep_order_config_single.py — 단일 옵션 급락 캐치 설정 기본값
════════════════════════════════════════
sleep_order_config.py 의 _DEFAULTS 딕셔너리에 업데이트로 병합됨.
SleepOrderConfigStore 가 import 시 자동으로 읽음.
직접 사용하지 말 것 — sleep_cfg 를 통해 접근.
"""

SINGLE_DEFAULTS: dict = {
    "single_spike_enabled":          False,
    "single_spike_use_own_schedule": True,
    "single_spike_start":            "16:53",
    "single_spike_end":              "05:14",
    "single_spike_ref_mode":         "time",
    "single_spike_ref_minutes":      3,
    "single_tick_window":            7,
    "single_drop_ratio":             40,
    "single_abs_floor":              0.20,
    "single_strike_mode":            "atm_offset",
    "single_strike_value":           0.0,
    "single_dist_pct":               0.50,
    "single_dist_min":               0.30,
    "single_dist_max":               0.80,
    "single_cp":                     "P",
    "single_order_mode":             "ask+1",
    "single_fixed_price":            0.15,
    "single_budget":                 100,
    "single_modify_wait_sec":        2,
    "single_modify_step":            0.05,
    "single_modify_max_count":       3,
    "single_modify_price_cap":       0.30,
    "single_auto_sell_enabled":      False,
    "single_auto_sell_mode":         "multiplier",
    "single_auto_sell_fixed_price":  2.50,
    "single_auto_sell_multiplier":   3.0,
}
