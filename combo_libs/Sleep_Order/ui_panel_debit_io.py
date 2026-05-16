"""
ui_panel_debit_io.py — DebitSpikePanel 저장/로드  v1.0
════════════════════════════════════════
DebitSpikePanel.save() / load() 로직 분리.
패널에서: from Sleep_Order.ui_panel_debit_io import save_debit, load_debit
"""
from __future__ import annotations
from Sleep_Order.ui_helpers import load_kst_time, update_et_preview, kst_to_et, spike_btn_style, lbl, btn


def save_debit(panel) -> None:
    from Sleep_Order.sleep_order_config   import sleep_cfg
    from Sleep_Order.spike_watcher_debit  import DebitSpikeWatcher
    sleep_cfg.set("spike_enabled",          panel._btn_toggle.isChecked())
    sleep_cfg.set("spike_use_own_schedule", panel._chk_own.isChecked())
    sleep_cfg.set("spike_start", kst_to_et(panel._te_start.time().toString("HH:mm")))
    sleep_cfg.set("spike_end",   kst_to_et(panel._te_end.time().toString("HH:mm")))
    sleep_cfg.set("spike_ref_mode",    panel._cmb_mode.currentData())
    sleep_cfg.set("spike_ref_minutes", panel._sb_ref_min.value())
    sleep_cfg.set("tick_window",       panel._sb_tick_n.value())
    sleep_cfg.set("drop_ratio",        panel._sb_drop.value())
    sleep_cfg.set("abs_floor",         panel._dsb_floor.value())
    sleep_cfg.set("order_mode",  "fixed" if panel._rb_fixed.isChecked() else "ask+1")
    sleep_cfg.set("fixed_price",       panel._dsb_fixed.value())
    sleep_cfg.set("modify_wait_sec",   panel._sb_wait.value())
    sleep_cfg.set("modify_step",       panel._dsb_step.value())
    sleep_cfg.set("modify_max_count",  panel._sb_max_mod.value())
    sleep_cfg.set("modify_price_cap",  panel._dsb_cap.value())
    sleep_cfg.set("spike_budget",      panel._sb_budget.value())
    sleep_cfg.set("auto_sell_enabled",     panel._chk_sell.isChecked())
    sleep_cfg.set("auto_sell_mode",        panel._cmb_sell.currentData())
    sleep_cfg.set("auto_sell_multiplier",  panel._dsb_mult.value())
    sleep_cfg.set("auto_sell_fixed_price", panel._dsb_sell_fixed.value())
    sleep_cfg.save()
    DebitSpikeWatcher.get().reconfigure_all()
    panel._lbl_st.setText(f"✅ 저장됨  {'ON' if sleep_cfg.spike_enabled else 'OFF'}")


def load_debit(panel) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    from Sleep_Order.ui_helpers import spike_btn_style
    on = sleep_cfg.spike_enabled
    panel._btn_toggle.setChecked(on)
    panel._btn_toggle.setText("⚡  급락캐치  ON (OFF)" if on else "⚡  급락 캐치  OFF")
    panel._btn_toggle.setStyleSheet(spike_btn_style(on))
    panel._lbl_status.setText("● 활성" if on else "● 비활성")
    panel._lbl_status.setStyleSheet(f"color:{'#ff4444' if on else '#888'};font-size:12px;border:none;")
    own = sleep_cfg.spike_use_own_schedule
    panel._chk_own.setChecked(own)
    for w in panel._time_widgets: w.setEnabled(own)
    load_kst_time(panel._te_start, sleep_cfg.get("spike_start", "16:53"))
    load_kst_time(panel._te_end,   sleep_cfg.get("spike_end",   "05:14"))
    update_et_preview(panel._te_start, panel._lbl_start_et)
    update_et_preview(panel._te_end,   panel._lbl_end_et)
    idx = panel._cmb_mode.findData(sleep_cfg.spike_ref_mode)
    panel._cmb_mode.setCurrentIndex(max(0, idx))
    panel._sb_ref_min.setValue(sleep_cfg.spike_ref_minutes)
    panel._sb_tick_n.setValue(sleep_cfg.tick_window)
    panel._on_mode_changed()
    panel._sb_drop.setValue(sleep_cfg.drop_ratio)
    panel._dsb_floor.setValue(sleep_cfg.abs_floor)
    is_f = sleep_cfg.order_mode == "fixed"
    panel._rb_fixed.setChecked(is_f); panel._rb_ask1.setChecked(not is_f)
    panel._dsb_fixed.setValue(sleep_cfg.fixed_price); panel._dsb_fixed.setEnabled(is_f)
    panel._sb_wait.setValue(sleep_cfg.modify_wait_sec)
    panel._dsb_step.setValue(sleep_cfg.modify_step)
    panel._sb_max_mod.setValue(sleep_cfg.modify_max_count)
    panel._dsb_cap.setValue(sleep_cfg.modify_price_cap)
    panel._sb_budget.setValue(sleep_cfg.spike_budget)
    sell_on = sleep_cfg.auto_sell_enabled
    panel._chk_sell.setChecked(sell_on)
    for w in panel._sell_widgets: w.setEnabled(sell_on)
    idx2 = panel._cmb_sell.findData(sleep_cfg.auto_sell_mode)
    panel._cmb_sell.setCurrentIndex(max(0, idx2))
    panel._dsb_mult.setValue(sleep_cfg.auto_sell_multiplier)
    panel._dsb_sell_fixed.setValue(sleep_cfg.auto_sell_fixed_price)
    panel._on_sell_mode_changed()