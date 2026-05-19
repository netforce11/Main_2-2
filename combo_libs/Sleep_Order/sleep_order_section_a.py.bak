"""
sleep_order_section_a.py — 예약주문 섹션 A UI 빌더  v2.0
════════════════════════════════════════
v2.0 변경:
  · 주문 방향 (풋만/콜만/콜+풋 동시) 섹션 A 내부 통합
  · 방향에 따라 예산/슬라이더 위젯 자동 활성/비활성
  · 저장 버튼 하단에 현재 설정 요약 뱃지 표시
  · 콤보 비중 패널 별도 불필요 (섹션 A에서 일괄 저장)
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QGridLayout, QHBoxLayout, QWidget, QSlider,
)
from PyQt5.QtCore import Qt
from Sleep_Order.ui_helpers import (
    gb, lbl, btn, spinbox, dspinbox, time_edit, combo, checkbox,
    sep, load_kst_time, update_et_preview, kst_to_et, _is_edt,
)


def build_schedule_section_a(parent) -> QGroupBox:
    g   = gb("🌙  예약 주문 설정", "#ffd700")
    lay = QGridLayout(g)
    lay.setContentsMargins(10, 14, 10, 10); lay.setSpacing(8)
    r = 0; tz = "EDT" if _is_edt() else "EST"

    # ── 스케줄 시간 ───────────────────────────────────────────
    lay.addWidget(lbl(f"KST 입력 → {tz} 자동변환", "#ffd066", 11), r, 0, 1, 4); r += 1
    parent._te_sched_start = time_edit("18:40")
    parent._lbl_sched_s_et = lbl("→ ET --:--", "#888", 12)
    parent._te_sched_start.timeChanged.connect(
        lambda: update_et_preview(parent._te_sched_start, parent._lbl_sched_s_et))
    lay.addWidget(lbl("시작 (KST):"), r, 0, Qt.AlignRight)
    lay.addWidget(parent._te_sched_start, r, 1)
    lay.addWidget(parent._lbl_sched_s_et, r, 2, 1, 2); r += 1

    parent._te_sched_end   = time_edit("18:14")
    parent._lbl_sched_e_et = lbl("→ ET --:--", "#888", 12)
    parent._te_sched_end.timeChanged.connect(
        lambda: update_et_preview(parent._te_sched_end, parent._lbl_sched_e_et))
    lay.addWidget(lbl("종료 (KST):"), r, 0, Qt.AlignRight)
    lay.addWidget(parent._te_sched_end, r, 1)
    lay.addWidget(parent._lbl_sched_e_et, r, 2, 1, 2); r += 1
    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # ── 파라미터 ──────────────────────────────────────────────
    lay.addWidget(lbl("익일물 오프셋:"), r, 0, Qt.AlignRight)
    parent._sb_expiry = spinbox(0, 5, 1, "일")
    lay.addWidget(parent._sb_expiry, r, 1)
    lay.addWidget(lbl("스프레드 폭:"), r, 2, Qt.AlignRight)
    parent._sb_sw = spinbox(1, 100, 5, "pt")   # [XSP] 최솟값 1pt (XSP=1, SPX=5)
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

    lay.addWidget(lbl("ROI 하한:"), r, 0, Qt.AlignRight)
    parent._sb_roi_min = spinbox(0, 9999, 0, "%")
    lay.addWidget(parent._sb_roi_min, r, 1)
    lay.addWidget(lbl("ROI 상한:"), r, 2, Qt.AlignRight)
    parent._sb_roi_max = spinbox(0, 9999, 1200, "%")
    lay.addWidget(parent._sb_roi_max, r, 3); r += 1
    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # ── 주문 방향 ─────────────────────────────────────────────
    lay.addWidget(lbl("주문 방향:", "#ffd700", 14), r, 0, Qt.AlignRight)
    parent._cmb_direction = combo([
        ("🔵 풋 스프레드만",      "put_only"),
        ("🟠 콜 스프레드만",      "call_only"),
        ("🟢 콜 + 풋  동시 주문", "both"),
    ], 190)
    parent._cmb_direction.currentIndexChanged.connect(
        lambda: _on_direction_changed(parent))
    lay.addWidget(parent._cmb_direction, r, 1, 1, 3); r += 1

    # ── 예산 ──────────────────────────────────────────────────
    lay.addWidget(lbl("풋 예산:"), r, 0, Qt.AlignRight)
    parent._sb_put_budget = spinbox(1, 9999, 100, "$")   # [FIX-0] 최솟값 1
    parent._sb_put_budget.valueChanged.connect(lambda: _update_direction_badge(parent))
    lay.addWidget(parent._sb_put_budget, r, 1)
    lay.addWidget(lbl("콜 예산:"), r, 2, Qt.AlignRight)
    parent._sb_call_budget = spinbox(1, 9999, 100, "$")   # [FIX-0] 최솟값 1
    parent._sb_call_budget.valueChanged.connect(lambda: _update_direction_badge(parent))
    lay.addWidget(parent._sb_call_budget, r, 3); r += 1

    # ── 콜 비중 슬라이더 (both 전용) ─────────────────────────
    parent._lbl_ratio_hdr = lbl("콜 비중:", "#aaa", 13)
    lay.addWidget(parent._lbl_ratio_hdr, r, 0, Qt.AlignRight)
    parent._slider_ratio = QSlider(Qt.Horizontal)
    parent._slider_ratio.setMinimum(10); parent._slider_ratio.setMaximum(90)
    parent._slider_ratio.setValue(50); parent._slider_ratio.setSingleStep(5)
    parent._slider_ratio.setStyleSheet(
        "QSlider::groove:horizontal{height:6px;background:#2a2a5a;border-radius:3px;}"
        "QSlider::handle:horizontal{width:16px;height:16px;margin:-5px 0;"
        "background:#5dade2;border-radius:8px;}"
        "QSlider::sub-page:horizontal{background:#5dade2;border-radius:3px;}")
    parent._slider_ratio.valueChanged.connect(
        lambda v: _on_slider_changed(parent, v))
    lay.addWidget(parent._slider_ratio, r, 1, 1, 2)
    parent._lbl_ratio_pct = lbl("50%", "#5dade2", 13)
    lay.addWidget(parent._lbl_ratio_pct, r, 3); r += 1

    # ── 콜 조건 그룹박스 (both 전용, 방향 변경 시 show/hide) ──
    parent._gb_call_cond = _build_call_cond_group(parent)
    lay.addWidget(parent._gb_call_cond, r, 0, 1, 4); r += 1

    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # ── 공격적 진입 + 드라이런 ────────────────────────────────
    parent._chk_agg = checkbox("공격적 진입 (호가 위 주문)")
    parent._chk_agg.setChecked(True)
    lay.addWidget(parent._chk_agg, r, 0, 1, 2)
    parent._sb_agg_ticks = spinbox(1, 5, 1, "틱")
    lay.addWidget(parent._sb_agg_ticks, r, 2); r += 1

    # ── 정정 주문 설정 ─────────────────────────────────────
    parent._chk_correction = checkbox("미체결 시 자동 정정", "#00e5cc", "#00e5cc")
    lay.addWidget(parent._chk_correction, r, 0, 1, 2)
    parent._sb_correction_sec = spinbox(1, 60, 3, "초")
    parent._sb_correction_sec.setToolTip("N초 후 미체결 시 -1틱 정정")
    lay.addWidget(lbl("후 정정:"), r, 2, Qt.AlignRight)
    lay.addWidget(parent._sb_correction_sec, r, 3); r += 1
    parent._chk_correction.stateChanged.connect(
        lambda: parent._sb_correction_sec.setEnabled(
            parent._chk_correction.isChecked()))
    parent._sb_correction_sec.setEnabled(False)   # 초기 비활성

    parent._chk_dry = checkbox("🧪 드라이런 (실제 주문 안함)", "#ffaa44", "#ffaa44")
    parent._chk_dry.stateChanged.connect(lambda: _update_direction_badge(parent))
    lay.addWidget(parent._chk_dry, r, 0, 1, 4); r += 1

    # ── 저장 ──────────────────────────────────────────────────
    parent._lbl_sched_st = lbl("", "#aaa", 12)
    lay.addWidget(parent._lbl_sched_st, r, 0, 1, 4); r += 1
    b = btn("✔  저장", "#1a1a0a", "#ffd700")
    b.clicked.connect(lambda: _save_schedule(parent))
    lay.addWidget(b, r, 0); r += 1
    lay.addWidget(sep(), r, 0, 1, 4); r += 1

    # ── 현재 설정 요약 뱃지 ───────────────────────────────────
    parent._lbl_direction_badge = lbl("", "#fff", 13)
    parent._lbl_direction_badge.setWordWrap(True)
    lay.addWidget(parent._lbl_direction_badge, r, 0, 1, 4)

    _load_schedule(parent)
    return g


# ── 핸들러 ────────────────────────────────────────────────────

def _build_call_cond_group(parent) -> "QGroupBox":
    """콜 조건 그룹박스 — both 모드일 때만 visible."""
    from PyQt5.QtWidgets import QGroupBox, QGridLayout
    gb = QGroupBox("📞  콜 조건")
    gb.setStyleSheet(
        "QGroupBox{font-size:13px;color:#00e5cc;font-weight:bold;"
        "border:1px solid #00665a;border-radius:6px;"
        "margin-top:8px;padding-top:6px;background:#060f0e;}"
        "QGroupBox::title{subcontrol-origin:margin;left:10px;}")
    g = QGridLayout(gb)
    g.setContentsMargins(10, 12, 10, 8); g.setSpacing(7)
    r = 0

    # 콜 목표가
    g.addWidget(lbl("목표가 상한:", "#aaffd0", 13), r, 0, Qt.AlignRight)
    parent._dsb_call_tp = dspinbox(0.01, 5.0, 0.50, 0.05, prefix="$")
    g.addWidget(parent._dsb_call_tp, r, 1)
    g.addWidget(lbl("(이하일 때 진입)", "#666", 11), r, 2, 1, 2); r += 1

    # 콜 ROI
    g.addWidget(lbl("ROI 하한:", "#aaffd0", 13), r, 0, Qt.AlignRight)
    parent._sb_call_roi_min = spinbox(0, 9999, 0, "%")
    g.addWidget(parent._sb_call_roi_min, r, 1)
    g.addWidget(lbl("ROI 상한:", "#aaffd0", 13), r, 2, Qt.AlignRight)
    parent._sb_call_roi_max = spinbox(0, 9999, 1200, "%")
    g.addWidget(parent._sb_call_roi_max, r, 3); r += 1

    # 콜 거리
    g.addWidget(lbl("거리 하한:", "#aaffd0", 13), r, 0, Qt.AlignRight)
    parent._dsb_call_dmin = dspinbox(0.01, 5.0, 0.60, 0.05)
    g.addWidget(parent._dsb_call_dmin, r, 1)
    g.addWidget(lbl("거리 상한:", "#aaffd0", 13), r, 2, Qt.AlignRight)
    parent._dsb_call_dmax = dspinbox(0.01, 5.0, 0.95, 0.05)
    g.addWidget(parent._dsb_call_dmax, r, 3); r += 1

    # ── 조건 B 구분선 ─────────────────────────────────────────
    g.addWidget(sep(), r, 0, 1, 4); r += 1
    g.addWidget(lbl("🔀  조건 B — AND 동시 체결", "#ffd700", 12), r, 0, 1, 4); r += 1

    # 주력 방향
    g.addWidget(lbl("주력 방향:", "#ffd066", 13), r, 0, Qt.AlignRight)
    parent._cmb_primary = combo([
        ("📉 풋 기준", "put"),
        ("📈 콜 기준", "call"),
    ], 120)
    g.addWidget(parent._cmb_primary, r, 1)
    g.addWidget(lbl("(주력이 엄격한 조건 적용)", "#666", 11), r, 2, 1, 2); r += 1

    # 보조 목표가 (느슨한 조건)
    g.addWidget(lbl("보조 목표가:", "#ffd066", 13), r, 0, Qt.AlignRight)
    parent._dsb_sec_tp = dspinbox(0.01, 5.0, 0.65, 0.05, prefix="$")
    g.addWidget(parent._dsb_sec_tp, r, 1)
    g.addWidget(lbl("(반대쪽 느슨한 조건)", "#666", 11), r, 2, 1, 2); r += 1

    gb.setVisible(False)   # 초기 숨김 — both 선택 시 show
    return gb


def _on_direction_changed(parent) -> None:
    d = parent._cmb_direction.currentData()
    is_both = (d == "both")
    parent._sb_put_budget.setEnabled(d in ("put_only", "both"))
    parent._sb_call_budget.setEnabled(d in ("call_only", "both"))
    parent._slider_ratio.setEnabled(is_both)
    parent._lbl_ratio_hdr.setEnabled(is_both)
    parent._lbl_ratio_pct.setEnabled(is_both)
    # 콜 조건 그룹박스: both 일 때만 표시
    gb = getattr(parent, '_gb_call_cond', None)
    if gb is not None:
        gb.setVisible(is_both)
    _update_direction_badge(parent)


def _on_call_indep_changed(parent) -> None:
    """v1.4 이후 미사용 — 콜은 항상 독립 루프로 동작."""
    pass


def _on_slider_changed(parent, val: int) -> None:
    parent._lbl_ratio_pct.setText(f"{val}%")
    total = parent._sb_put_budget.value() + parent._sb_call_budget.value()
    call_b = max(1, round(total * val / 100 / 10) * 10)   # [FIX-0]
    put_b  = max(1, total - call_b)                        # [FIX-0]
    parent._sb_call_budget.blockSignals(True)
    parent._sb_put_budget.blockSignals(True)
    parent._sb_call_budget.setValue(call_b)
    parent._sb_put_budget.setValue(put_b)
    parent._sb_call_budget.blockSignals(False)
    parent._sb_put_budget.blockSignals(False)
    _update_direction_badge(parent)


# ── 저장 / 로드 ───────────────────────────────────────────────

def _save_schedule(parent) -> None:
    from Sleep_Order.sleep_order_config import sleep_cfg
    sleep_cfg.set("schedule_start",   kst_to_et(parent._te_sched_start.time().toString("HH:mm")))
    sleep_cfg.set("schedule_end",     kst_to_et(parent._te_sched_end.time().toString("HH:mm")))
    sleep_cfg.set("expiry_offset",    parent._sb_expiry.value())
    sleep_cfg.set("spread_width",     parent._sb_sw.value())
    sleep_cfg.set("strike_dist_min",  parent._dsb_dmin.value())
    sleep_cfg.set("strike_dist_max",  parent._dsb_dmax.value())
    sleep_cfg.set("target_price_1",   parent._dsb_tp1.value())
    sleep_cfg.set("target_price_2",   parent._dsb_tp2.value())
    sleep_cfg.set("roi_min",          parent._sb_roi_min.value())
    sleep_cfg.set("roi_max",          parent._sb_roi_max.value())
    sleep_cfg.set("aggressive_entry", parent._chk_agg.isChecked())
    sleep_cfg.set("aggressive_ticks", parent._sb_agg_ticks.value())
    sleep_cfg.set("dry_run",          parent._chk_dry.isChecked())
    sleep_cfg.set("correction_enabled",  parent._chk_correction.isChecked())
    sleep_cfg.set("correction_wait_sec", parent._sb_correction_sec.value())
    d = parent._cmb_direction.currentData()
    sleep_cfg.set("combo_direction",   d)
    sleep_cfg.set("combo_call_budget", parent._sb_call_budget.value())
    sleep_cfg.set("combo_put_budget",  parent._sb_put_budget.value())
    sleep_cfg.set("combo_call_ratio",  parent._slider_ratio.value() / 100.0)
    # 콜 조건
    sleep_cfg.set("call_target_price", parent._dsb_call_tp.value())
    sleep_cfg.set("call_roi_min",      parent._sb_call_roi_min.value())
    sleep_cfg.set("call_roi_max",      parent._sb_call_roi_max.value())
    sleep_cfg.set("call_dist_min",     parent._dsb_call_dmin.value())
    sleep_cfg.set("call_dist_max",     parent._dsb_call_dmax.value())
    # 조건 B
    sleep_cfg.set("primary_direction",      parent._cmb_primary.currentData())
    sleep_cfg.set("secondary_target_price", parent._dsb_sec_tp.value())
    # max_budget 호환 유지
    if d == "put_only":
        sleep_cfg.set("max_budget", parent._sb_put_budget.value())
    elif d == "call_only":
        sleep_cfg.set("max_budget", parent._sb_call_budget.value())
    else:
        sleep_cfg.set("max_budget",
                      parent._sb_put_budget.value() + parent._sb_call_budget.value())
    sleep_cfg.save()
    parent._lbl_sched_st.setText("✅ 저장됨")
    _update_direction_badge(parent)


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
    parent._sb_roi_min.setValue(sleep_cfg.roi_min)
    parent._sb_roi_max.setValue(sleep_cfg.roi_max)
    parent._chk_agg.setChecked(sleep_cfg.aggressive_entry)
    parent._sb_agg_ticks.setValue(sleep_cfg.aggressive_ticks)
    parent._chk_dry.setChecked(sleep_cfg.dry_run)
    parent._chk_correction.setChecked(sleep_cfg.correction_enabled)
    parent._sb_correction_sec.setValue(sleep_cfg.correction_wait_sec)
    parent._sb_correction_sec.setEnabled(sleep_cfg.correction_enabled)
    idx = parent._cmb_direction.findData(sleep_cfg.combo_direction)
    parent._cmb_direction.setCurrentIndex(max(0, idx))
    parent._sb_call_budget.setValue(sleep_cfg.combo_call_budget)
    parent._sb_put_budget.setValue(sleep_cfg.combo_put_budget)
    v = int(round(sleep_cfg.combo_call_ratio * 100))
    parent._slider_ratio.setValue(v)
    parent._lbl_ratio_pct.setText(f"{v}%")
    # 콜 조건 로드
    parent._dsb_call_tp.setValue(sleep_cfg.call_target_price)
    parent._sb_call_roi_min.setValue(sleep_cfg.call_roi_min)
    parent._sb_call_roi_max.setValue(sleep_cfg.call_roi_max)
    parent._dsb_call_dmin.setValue(sleep_cfg.call_dist_min)
    parent._dsb_call_dmax.setValue(sleep_cfg.call_dist_max)
    # 조건 B
    idx = parent._cmb_primary.findData(getattr(sleep_cfg, 'primary_direction', 'put'))
    parent._cmb_primary.setCurrentIndex(max(0, idx))
    parent._dsb_sec_tp.setValue(getattr(sleep_cfg, 'secondary_target_price', 0.65))
    _on_direction_changed(parent)


# ── 요약 뱃지 ─────────────────────────────────────────────────

def _update_direction_badge(parent) -> None:
    w = getattr(parent, '_lbl_direction_badge', None)
    if w is None:
        return
    try:
        d   = parent._cmb_direction.currentData()
        dry = parent._chk_dry.isChecked()
        cb  = parent._sb_call_budget.value()
        pb  = parent._sb_put_budget.value()
        pct = parent._slider_ratio.value()
        _DIR = {
            "put_only":  ("🔵 풋 스프레드만", "#3399ff"),
            "call_only": ("🟠 콜 스프레드만", "#ff9933"),
            "both":      ("🟢 콜 + 풋  동시", "#00cc66"),
        }
        dir_text, color = _DIR.get(d, ("❓ 미설정", "#888"))
        if d == "put_only":
            budget = f"  예산 ${pb}"
        elif d == "call_only":
            budget = f"  예산 ${cb}"
        else:
            budget = f"  콜 ${cb} ({pct}%) / 풋 ${pb} ({100-pct}%)"
            tp = getattr(parent, '_dsb_call_tp', None)
            sec_tp  = getattr(parent, '_dsb_sec_tp', None)
            primary = getattr(parent, '_cmb_primary', None)
            if tp is not None:
                budget += f"\n  콜 조건: 목표가 ≤${tp.value():.2f}"
            if primary is not None and sec_tp is not None:
                pri_txt = "풋 기준" if primary.currentData() == "put" else "콜 기준"
                budget += f"\n  조건B: 주력={pri_txt}  보조 ≤${sec_tp.value():.2f}"
        dry_mark = "  🧪 드라이런" if dry else "  ✅ 실제주문"
        w.setText(f"{dir_text}{budget}{dry_mark}")
        w.setStyleSheet(
            f"color:{color};font-size:13px;font-weight:bold;border:none;"
            f"background:#0d0d20;border-radius:4px;padding:5px 8px;"
            f"border-left:3px solid {color};")
    except Exception as e:
        print(f"[SectionA] badge 갱신 실패: {e}")