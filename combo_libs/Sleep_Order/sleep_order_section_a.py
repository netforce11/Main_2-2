"""
sleep_order_section_a.py — 예약주문 섹션 A UI 빌더  v1.0
════════════════════════════════════════
기존 sleep_order_ui.py 의 예약주문 관련 QGroupBox 위젯 빌더.
SleepOrderRightPanel._make_left_col() 에서 호출.

함수:
    build_schedule_section_a(parent) -> QGroupBox
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QGridLayout, QHBoxLayout, QWidget,
)
from PyQt5.QtCore import Qt
from Sleep_Order.ui_helpers import (
    gb, lbl, btn, spinbox, dspinbox, time_edit, combo, checkbox,
    sep, load_kst_time, update_et_preview, kst_to_et, _is_edt,
)


def build_schedule_section_a(parent) -> QGroupBox:
    """
    섹션 A : 예약 주문 기본 설정.
    parent 는 SleepOrderRightPanel 인스턴스.
    parent 에 위젯 참조(_te_sched_start 등)를 직접 주입.
    """
    g   = gb("🌙  예약 주문 설정", "#ffd700")
    lay = QGridLayout(g)
    lay.setContentsMargins(10, 14, 10, 10); lay.setSpacing(8)
    r   = 0
    tz  = "EDT" if _is_edt() else "EST"

    # 스케줄 시간
    lay.addWidget(lbl(f"KST 입력 → {tz} 자동변환", "#ffd066", 11), r, 0, 1, 4); r += 1
    parent._te_sched_start = time_edit("18:40")
    parent._lbl_sched_s_et  = lbl("→ ET --:--", "#888", 12)
    parent._te_sched_start.timeChanged.connect(
        lambda: update_et_preview(parent._te_sched_start, parent._lbl_sched_s_et))
    lay.addWidget(lbl("시작 (KST):"), r, 0, Qt.AlignRight)
    lay.addWidget(parent._te_sched_start, r, 1)
    lay.addWidget(parent._lbl_sched_s_et, r, 2, 1, 2); r += 1

    parent._te_sched_end   = time_edit("18:14")
    parent._lbl_sched_e_et  = lbl("→ ET --:--", "#888", 12)
    parent._te_sched_end.timeChanged.connect(
        lambda: update_et_preview(parent._te_sched_end, parent._lbl_sched_e_et))
    lay.addWidget(lbl("종료 (KST):"), r, 0, Qt.AlignRight)
    lay.addWidget(parent._te_sched_end, r, 1)
    lay.addWidget(parent._lbl_sched_e_et, r, 2, 1, 2); r += 1
    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # 파라미터
    lay.addWidget(lbl("익일물 오프셋:"), r, 0, Qt.AlignRight)
    parent._sb_expiry = spinbox(0, 5, 1, "일")
    lay.addWidget(parent._sb_expiry, r, 1)
    lay.addWidget(lbl("스프레드 폭:"), r, 2, Qt.AlignRight)
    parent._sb_sw = spinbox(5, 100, 20, "pt")
    lay.addWidget(parent._sb_sw, r, 3); r += 1

    lay.addWidget(lbl("거리 하한:"), r, 0, Qt.AlignRight)
    parent._dsb_dmin = dspinbox(0.01, 5.0, 0.60, 0.05)
    lay.addWidget(parent._dsb_dmin, r, 1)
    lay.addWidget(lbl("거리 상한:"), r, 2, Qt.AlignRight)
    parent._dsb_dmax = dspinbox(0.01, 5.0, 0.95, 0.05)
    lay.addWidget(parent._dsb_dmax, r, 3); r += 1

    lay.addWidget(lbl("목표가 1차:"), r, 0, Qt.AlignRight)
    parent._dsb_tp1 = dspinbox(0.01, 5.0, 0.50, 0.05, prefix="$")
    lay.addWidget(parent._dsb_tp1, r, 1)
    lay.addWidget(lbl("목표가 2차:"), r, 2, Qt.AlignRight)
    parent._dsb_tp2 = dspinbox(0.01, 5.0, 0.40, 0.05, prefix="$")
    lay.addWidget(parent._dsb_tp2, r, 3); r += 1

    lay.addWidget(lbl("최대 예산:"), r, 0, Qt.AlignRight)
    parent._sb_budget = spinbox(10, 9999, 100, "$")
    lay.addWidget(parent._sb_budget, r, 1)
    lay.addWidget(lbl("ROI 하한:"), r, 2, Qt.AlignRight)
    parent._sb_roi_min = spinbox(0, 9999, 0, "%")
    lay.addWidget(parent._sb_roi_min, r, 3); r += 1

    lay.addWidget(lbl("ROI 상한:"), r, 0, Qt.AlignRight)
    parent._sb_roi_max = spinbox(0, 9999, 1200, "%")
    lay.addWidget(parent._sb_roi_max, r, 1); r += 1
    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # 공격적 진입
    parent._chk_agg = checkbox("공격적 진입 (호가 위 주문)")
    parent._chk_agg.setChecked(True)
    lay.addWidget(parent._chk_agg, r, 0, 1, 2)
    parent._sb_agg_ticks = spinbox(1, 5, 1, "틱")
    lay.addWidget(parent._sb_agg_ticks, r, 2); r += 1

    parent._chk_dry = checkbox("🧪 드라이런 (실제 주문 안함)", "#ffaa44", "#ffaa44")
    lay.addWidget(parent._chk_dry, r, 0, 1, 4); r += 1

    # 저장
    parent._lbl_sched_st = lbl("", "#aaa", 12)
    lay.addWidget(parent._lbl_sched_st, r, 0, 1, 4); r += 1
    b = btn("✔  저장", "#1a1a0a", "#ffd700")
    b.clicked.connect(lambda: _save_schedule(parent))
    lay.addWidget(b, r, 0)

    _load_schedule(parent)
    return g


def _save_schedule(parent) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    sleep_cfg.set("schedule_start", kst_to_et(parent._te_sched_start.time().toString("HH:mm")))
    sleep_cfg.set("schedule_end",   kst_to_et(parent._te_sched_end.time().toString("HH:mm")))
    sleep_cfg.set("expiry_offset",   parent._sb_expiry.value())
    sleep_cfg.set("spread_width",    parent._sb_sw.value())
    sleep_cfg.set("strike_dist_min", parent._dsb_dmin.value())
    sleep_cfg.set("strike_dist_max", parent._dsb_dmax.value())
    sleep_cfg.set("target_price_1",  parent._dsb_tp1.value())
    sleep_cfg.set("target_price_2",  parent._dsb_tp2.value())
    sleep_cfg.set("max_budget",      parent._sb_budget.value())
    sleep_cfg.set("roi_min",         parent._sb_roi_min.value())
    sleep_cfg.set("roi_max",         parent._sb_roi_max.value())
    sleep_cfg.set("aggressive_entry",parent._chk_agg.isChecked())
    sleep_cfg.set("aggressive_ticks",parent._sb_agg_ticks.value())
    sleep_cfg.set("dry_run",         parent._chk_dry.isChecked())
    sleep_cfg.save()
    parent._lbl_sched_st.setText("✅ 저장됨")


def _load_schedule(parent) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    load_kst_time(parent._te_sched_start, sleep_cfg.schedule_start)
    load_kst_time(parent._te_sched_end,   sleep_cfg.schedule_end)
    update_et_preview(parent._te_sched_start, parent._lbl_sched_s_et)
    update_et_preview(parent._te_sched_end,   parent._lbl_sched_e_et)
    parent._sb_expiry.setValue(sleep_cfg.expiry_offset)
    parent._sb_sw.setValue(sleep_cfg.spread_width)
    parent._dsb_dmin.setValue(sleep_cfg.strike_dist_min)
    parent._dsb_dmax.setValue(sleep_cfg.strike_dist_max)
    parent._dsb_tp1.setValue(sleep_cfg.target_price_1)
    parent._dsb_tp2.setValue(sleep_cfg.target_price_2)
    parent._sb_budget.setValue(sleep_cfg.max_budget)
    parent._sb_roi_min.setValue(sleep_cfg.roi_min)
    parent._sb_roi_max.setValue(sleep_cfg.roi_max)
    parent._chk_agg.setChecked(sleep_cfg.aggressive_entry)
    parent._sb_agg_ticks.setValue(sleep_cfg.aggressive_ticks)
    parent._chk_dry.setChecked(sleep_cfg.dry_run)
