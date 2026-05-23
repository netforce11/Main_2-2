"""
ui_panel_combo_ratio_io.py — ComboRatioPanel 저장/로드  v1.0
════════════════════════════════════════
ComboRatioPanel.save() / load() 로직 분리.
패널에서: from Sleep_Order.ui_panel_combo_ratio_io import save_combo_ratio, load_combo_ratio
"""
from __future__ import annotations


def save_combo_ratio(panel) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    d = panel._cmb_dir.currentData()
    sleep_cfg.set("combo_direction",   d)
    sleep_cfg.set("combo_ratio_mode",  "equal" if panel._rb_equal.isChecked() else "custom")
    sleep_cfg.set("combo_call_ratio",  panel._slider.value() / 100.0)
    sleep_cfg.set("combo_call_budget", panel._sb_call_budget.value())
    sleep_cfg.set("combo_put_budget",  panel._sb_put_budget.value())
    sleep_cfg.save()
    panel._lbl_st.setText(f"✅ 저장됨  [{_dir_label(d)}]")
    # 섹션 A 방향 뱃지 갱신 (SleepOrderRightPanel 에 _lbl_direction_badge 있으면)
    try:
        from Sleep_Order.sleep_order_section_a import _update_direction_badge
        top = panel.parent()
        while top is not None:
            if hasattr(top, '_lbl_direction_badge'):
                _update_direction_badge(top)
                break
            top = top.parent()
    except Exception:
        pass


def load_combo_ratio(panel) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    # 방향
    idx = panel._cmb_dir.findData(sleep_cfg.combo_direction)
    panel._cmb_dir.setCurrentIndex(max(0, idx))
    # 비율 모드
    is_custom = sleep_cfg.combo_ratio_mode == "custom"
    panel._rb_custom.setChecked(is_custom)
    panel._rb_equal.setChecked(not is_custom)
    # 슬라이더
    panel._slider.setValue(int(round(sleep_cfg.combo_call_ratio * 100)))
    panel._lbl_call_pct.setText(f"{int(round(sleep_cfg.combo_call_ratio * 100))}%")
    # 예산
    panel._sb_call_budget.setValue(sleep_cfg.combo_call_budget)
    panel._sb_put_budget.setValue(sleep_cfg.combo_put_budget)
    # 위젯 활성화 상태 동기화
    panel._on_dir_changed()
    panel._update_preview()


def _dir_label(d: str) -> str:
    return {"put_only": "풋만", "call_only": "콜만", "both": "콜+풋 동시"}.get(d, d)