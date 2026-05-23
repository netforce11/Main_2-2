"""
ui_panel_single_io.py — SingleOptSpikePanel 저장/로드  v1.0
════════════════════════════════════════
"""
from __future__ import annotations
from Sleep_Order.ui_helpers import load_kst_time, update_et_preview, kst_to_et, spike_btn_style, lbl, btn


def save_single(panel) -> None:
    from Sleep_Order.sleep_order_config   import sleep_cfg
    from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher
    from Sleep_Order.sleep_order_config   import sleep_cfg
    from Sleep_Order.spike_catcher_single import SingleOptSpikeWatcher
    sleep_cfg.set("single_spike_enabled",          panel._btn_toggle.isChecked())
    sleep_cfg.set("single_cp",                     panel._cmb_cp.currentData())
    sleep_cfg.set("single_spike_use_own_schedule", panel._chk_own.isChecked())
    sleep_cfg.set("single_spike_start", kst_to_et(panel._te_start.time().toString("HH:mm")))
    sleep_cfg.set("single_spike_end",   kst_to_et(panel._te_end.time().toString("HH:mm")))
    sleep_cfg.set("single_strike_mode",       panel._cmb_strike_mode.currentData())
    sleep_cfg.set("single_strike_value",      panel._dsb_direct.value()
                                              if panel._cmb_strike_mode.currentData() == "direct"
                                              else panel._dsb_atm.value())
    sleep_cfg.set("single_dist_pct",          panel._dsb_dist.value())
    sleep_cfg.set("single_dist_min",          panel._dsb_rmin.value())
    sleep_cfg.set("single_dist_max",          panel._dsb_rmax.value())
    sleep_cfg.set("single_spike_ref_mode",    panel._cmb_ref.currentData())
    sleep_cfg.set("single_spike_ref_minutes", panel._sb_ref_min.value())
    sleep_cfg.set("single_tick_window",       panel._sb_tick_n.value())
    sleep_cfg.set("single_drop_ratio",        panel._sb_drop.value())
    sleep_cfg.set("single_abs_floor",         panel._dsb_floor.value())
    sleep_cfg.set("single_order_mode",        "fixed" if panel._rb_fix.isChecked() else "ask+1")
    sleep_cfg.set("single_fixed_price",       panel._dsb_fixed.value())
    sleep_cfg.set("single_modify_wait_sec",   panel._sb_wait.value())
    sleep_cfg.set("single_modify_step",       panel._dsb_step.value())
    sleep_cfg.set("single_modify_max_count",  panel._sb_max.value())
    sleep_cfg.set("single_modify_price_cap",  panel._dsb_cap.value())
    sleep_cfg.set("single_budget",            panel._sb_budget.value())
    sleep_cfg.set("single_auto_sell_enabled",     panel._chk_sell.isChecked())
    sleep_cfg.set("single_auto_sell_mode",        panel._cmb_sell.currentData())
    sleep_cfg.set("single_auto_sell_multiplier",  panel._dsb_mult.value())
    sleep_cfg.set("single_auto_sell_fixed_price", panel._dsb_sfixed.value())
    sleep_cfg.save()
    SingleOptSpikeWatcher.get().reconfigure_all()
    panel._lbl_st.setText(f"✅ 저장됨  {'ON' if sleep_cfg.single_spike_enabled else 'OFF'}")



def load_single(panel) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    on = sleep_cfg.single_spike_enabled
    panel._btn_toggle.setChecked(on)
    panel._btn_toggle.setText("🎯  단일 캐치  ON (OFF)" if on else "🎯  단일 캐치  OFF")
    panel._btn_toggle.setStyleSheet(spike_btn_style(on))
    panel._lbl_status.setText("● 활성" if on else "● 비활성")
    panel._lbl_status.setStyleSheet(f"color:{'#2ecc71' if on else '#888'};font-size:12px;border:none;")
    idx_cp = panel._cmb_cp.findData(sleep_cfg.single_cp)
    panel._cmb_cp.setCurrentIndex(max(0, idx_cp))
    own = sleep_cfg.single_spike_use_own_schedule
    panel._chk_own.setChecked(own)
    for w in panel._time_ws: w.setEnabled(own)
    load_kst_time(panel._te_start, sleep_cfg.get("single_spike_start", "16:53"))
    load_kst_time(panel._te_end,   sleep_cfg.get("single_spike_end",   "05:14"))
    update_et_preview(panel._te_start, panel._lbl_se)
    update_et_preview(panel._te_end,   panel._lbl_ee)
    idx_sm = panel._cmb_strike_mode.findData(sleep_cfg.single_strike_mode)
    panel._cmb_strike_mode.setCurrentIndex(max(0, idx_sm))
    panel._dsb_direct.setValue(sleep_cfg.single_strike_value)
    panel._dsb_atm.setValue(sleep_cfg.single_strike_value)
    panel._dsb_dist.setValue(sleep_cfg.single_dist_pct)
    panel._dsb_rmin.setValue(sleep_cfg.single_dist_min)
    panel._dsb_rmax.setValue(sleep_cfg.single_dist_max)
    idx_r = panel._cmb_ref.findData(sleep_cfg.single_spike_ref_mode)
    panel._cmb_ref.setCurrentIndex(max(0, idx_r))
    panel._sb_ref_min.setValue(sleep_cfg.single_spike_ref_minutes)
    panel._sb_tick_n.setValue(sleep_cfg.single_tick_window)
    panel._on_ref_mode_changed()
    panel._sb_drop.setValue(sleep_cfg.single_drop_ratio)
    panel._dsb_floor.setValue(sleep_cfg.single_abs_floor)
    is_fix = sleep_cfg.single_order_mode == "fixed"
    panel._rb_fix.setChecked(is_fix); panel._rb_ask.setChecked(not is_fix)
    panel._dsb_fixed.setValue(sleep_cfg.single_fixed_price)
    panel._dsb_fixed.setEnabled(is_fix)
    panel._sb_wait.setValue(sleep_cfg.single_modify_wait_sec)
    panel._dsb_step.setValue(sleep_cfg.single_modify_step)
    panel._sb_max.setValue(sleep_cfg.single_modify_max_count)
    panel._dsb_cap.setValue(sleep_cfg.single_modify_price_cap)
    panel._sb_budget.setValue(sleep_cfg.single_budget)
    sell_on = sleep_cfg.single_auto_sell_enabled
    panel._chk_sell.setChecked(sell_on)
    for w in panel._sell_ws: w.setEnabled(sell_on)
    idx_s = panel._cmb_sell.findData(sleep_cfg.single_auto_sell_mode)
    panel._cmb_sell.setCurrentIndex(max(0, idx_s))
    panel._dsb_mult.setValue(sleep_cfg.single_auto_sell_multiplier)
    panel._dsb_sfixed.setValue(sleep_cfg.single_auto_sell_fixed_price)
    panel._on_sell_mode()