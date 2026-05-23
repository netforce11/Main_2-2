"""
ui_panel_single.py — 단일 옵션 급락 캐치 설정 패널  v1.0
════════════════════════════════════════
SingleOptSpikePanel : QGroupBox 서브클래스
  - ON/OFF 토글
  - 전용 시간 (KST → ET)
  - 기준가 방식 (time/tick)
  - 행사가 지정 방식 4종 (direct/atm_offset/dist_pct/range)
  - PUT / CALL 선택
  - 급락 조건, 주문/정정, 자동매도
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QGridLayout, QHBoxLayout, QVBoxLayout,
    QWidget, QPushButton, QButtonGroup, QRadioButton, QStackedWidget,
)
from PyQt5.QtCore import Qt

from Sleep_Order.ui_helpers import (
    gb, lbl, btn, spinbox, dspinbox, time_edit, combo, checkbox,
    sep, spike_btn_style, load_kst_time, update_et_preview,
    kst_to_et, _is_edt,
)


class SingleOptSpikePanel(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("🎯  단일 옵션 급락 캐치  [신규]")
        self.setStyleSheet(
            "QGroupBox{font-size:15px;color:#2ecc71;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:6px;"
            "margin-top:10px;padding-top:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}")
        self._build()
        self.load()

    def _build(self) -> None:
        lay = QGridLayout(self)
        lay.setContentsMargins(12, 14, 12, 10); lay.setSpacing(8)
        r = 0

        self._build_header(lay, r); r += 9

        # 행사가 지정 방식
        lay.addWidget(lbl("행사가 방식:"), r, 0, Qt.AlignRight)
        self._cmb_strike_mode = combo([
            ("직접 입력",           "direct"),
            ("ATM ± N 포인트",      "atm_offset"),
            ("지수 대비 N% (단일)", "dist_pct"),
            ("지수 대비 범위 %",    "range"),
        ], 200)
        self._cmb_strike_mode.currentIndexChanged.connect(self._on_strike_mode_changed)
        lay.addWidget(self._cmb_strike_mode, r, 1, 1, 3); r += 1

        self._build_strike_stack(lay, r); r += 1
        lay.addWidget(sep(), r, 0, 1, 4); r += 1

        self._build_ref_drop(lay, r); r += 7

        self._build_order_section(lay, r); r += 6

        self._build_sell_section(lay, r); r += 4

        self._lbl_st = lbl("", "#aaa", 12)
        lay.addWidget(self._lbl_st, r, 0, 1, 4); r += 1
        b = btn("✔  저장", "#1a2a1a", "#00e676")
        b.clicked.connect(self.save)
        lay.addWidget(b, r, 0)

    # ── 핸들러 ──────────────────────────────────────────────
    def _on_toggle(self, checked: bool) -> None:
        self._btn_toggle.setText("🎯  단일 캐치  ON (OFF)" if checked else "🎯  단일 캐치  OFF")
        self._btn_toggle.setStyleSheet(spike_btn_style(checked))
        self._lbl_status.setText("● 활성" if checked else "● 비활성")
        self._lbl_status.setStyleSheet(f"color:{'#2ecc71' if checked else '#888'};font-size:12px;border:none;")
        try:
            from Sleep_Order.sleep_order_config      import sleep_cfg
            from Sleep_Order.spike_catcher_single    import SingleOptSpikeWatcher
            sleep_cfg.set("single_spike_enabled", checked); sleep_cfg.save()
            SingleOptSpikeWatcher.get().reconfigure_all()
        except Exception as e:
            print(f"[SinglePanel] 즉시저장 실패: {e}")

    def _on_strike_mode_changed(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)

    def _on_ref_mode_changed(self, *_) -> None:
        is_t = self._cmb_ref.currentData() == "time"
        self._sb_ref_min.setVisible(is_t); self._lbl_ref_min.setVisible(is_t)
        self._sb_tick_n.setVisible(not is_t); self._lbl_tick.setVisible(not is_t)

    def _on_sell_mode(self, *_) -> None:
        is_m = self._cmb_sell.currentData() == "multiplier"
        self._dsb_mult.setVisible(is_m); self._lbl_prev.setVisible(is_m)
        self._dsb_sfixed.setVisible(not is_m)
        if is_m: self._update_preview()

    def _update_preview(self, *_) -> None:
        m = self._dsb_mult.value()
        self._lbl_prev.setText("  예) " + "  /  ".join(
            f"${p:.2f}→${p*m:.2f}" for p in (0.10, 0.15, 0.20, 0.30)))

    # ── 저장 / 로드 ────────────────────────────────────────
    def _build_header(self, lay, r: int) -> None:
        self._btn_toggle = QPushButton("🎯  단일 캐치  OFF")
        self._btn_toggle.setCheckable(True); self._btn_toggle.setFixedHeight(34)
        self._btn_toggle.setStyleSheet(spike_btn_style(False))
        self._btn_toggle.clicked.connect(self._on_toggle)
        self._lbl_status = lbl("● 비활성", "#888", 12)
        row0 = QHBoxLayout()
        row0.addWidget(self._btn_toggle); row0.addWidget(self._lbl_status); row0.addStretch()
        lay.addLayout(row0, r, 0, 1, 4); lay.addWidget(sep(), r+1, 0, 1, 4)
        self._cmb_cp = combo([("PUT  (풋)", "P"), ("CALL (콜)", "C")], 140)
        lay.addWidget(lbl("옵션 종류:"), r+2, 0, Qt.AlignRight); lay.addWidget(self._cmb_cp, r+2, 1, 1, 3)
        self._chk_own = checkbox("예약주문과 별도 시간대", "#90ee90", "#2ecc71")
        self._chk_own.stateChanged.connect(lambda s: [w.setEnabled(bool(s)) for w in self._time_ws])
        lay.addWidget(self._chk_own, r+3, 0, 1, 4)
        tz = "EDT" if _is_edt() else "EST"
        lay.addWidget(lbl(f"KST 입력 → {tz} 자동변환", "#90ee90", 11), r+4, 0, 1, 4)
        self._te_start = time_edit("01:53"); self._lbl_se = lbl("→ ET --:--", "#888", 12)
        self._te_end   = time_edit("18:14"); self._lbl_ee = lbl("→ ET --:--", "#888", 12)
        self._te_start.timeChanged.connect(lambda: update_et_preview(self._te_start, self._lbl_se))
        self._te_end.timeChanged.connect(  lambda: update_et_preview(self._te_end,   self._lbl_ee))
        lay.addWidget(lbl("시작 (KST):"), r+5, 0, Qt.AlignRight)
        lay.addWidget(self._te_start, r+5, 1); lay.addWidget(self._lbl_se, r+5, 2, 1, 2)
        lay.addWidget(lbl("종료 (KST):"), r+6, 0, Qt.AlignRight)
        lay.addWidget(self._te_end, r+6, 1); lay.addWidget(self._lbl_ee, r+6, 2, 1, 2)
        self._time_ws = [self._te_start, self._lbl_se, self._te_end, self._lbl_ee]
        lay.addWidget(sep(), r+7, 0, 1, 4)

    def _build_strike_stack(self, lay, r: int) -> None:
        """행사가 입력 스택 위젯 (4가지 모드)."""
        from PyQt5.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()
        p0 = QWidget(); p0l = QHBoxLayout(p0); p0l.setContentsMargins(0,0,0,0)
        self._dsb_direct = dspinbox(100, 99999, 5000.0, 5.0, 0)
        p0l.addWidget(lbl("행사가:", size=14)); p0l.addWidget(self._dsb_direct); p0l.addStretch()
        p1 = QWidget(); p1l = QHBoxLayout(p1); p1l.setContentsMargins(0,0,0,0)
        self._dsb_atm = dspinbox(-500, 500, 0.0, 5.0, 0)
        p1l.addWidget(lbl("ATM ±:", size=14)); p1l.addWidget(self._dsb_atm)
        p1l.addWidget(lbl("포인트 (음수=아래)", "#888", 11)); p1l.addStretch()
        p2 = QWidget(); p2l = QHBoxLayout(p2); p2l.setContentsMargins(0,0,0,0)
        self._dsb_dist = dspinbox(0.01, 10.0, 0.50, 0.05)
        p2l.addWidget(lbl("거리 %:", size=14)); p2l.addWidget(self._dsb_dist)
        p2l.addWidget(lbl("% (지수 대비)", "#888", 11)); p2l.addStretch()
        p3 = QWidget(); p3l = QHBoxLayout(p3); p3l.setContentsMargins(0,0,0,0)
        self._dsb_rmin = dspinbox(0.01, 10.0, 0.30, 0.05)
        self._dsb_rmax = dspinbox(0.01, 10.0, 0.80, 0.05)
        p3l.addWidget(lbl("범위:", size=14)); p3l.addWidget(self._dsb_rmin)
        p3l.addWidget(lbl("~")); p3l.addWidget(self._dsb_rmax)
        p3l.addWidget(lbl("%", "#888", 11)); p3l.addStretch()
        for p in (p0, p1, p2, p3): self._stack.addWidget(p)
        lay.addWidget(self._stack, r, 0, 1, 4)

    def _build_ref_drop(self, lay, r: int) -> None:
        """기준가 방식 + 급락 조건 섹션."""
        self._cmb_ref = combo([("시간 기준  (N분 고가)", "time"),
                               ("틱 평균    (N개 mid)", "tick")], 200)
        self._cmb_ref.currentIndexChanged.connect(self._on_ref_mode_changed)
        lay.addWidget(lbl("기준가 방식:"), r, 0, Qt.AlignRight); lay.addWidget(self._cmb_ref, r, 1, 1, 3)
        self._sb_ref_min = spinbox(1, 60, 3, "분"); self._lbl_ref_min = lbl("N분간 최고가 확정", "#888", 11)
        lay.addWidget(lbl("기준 시간:"), r+1, 0, Qt.AlignRight)
        lay.addWidget(self._sb_ref_min, r+1, 1); lay.addWidget(self._lbl_ref_min, r+1, 2, 1, 2)
        self._sb_tick_n = spinbox(5, 10, 7, "개"); self._lbl_tick = lbl("최근 N개 평균", "#888", 11)
        lay.addWidget(lbl("틱 평균 N:"), r+2, 0, Qt.AlignRight)
        lay.addWidget(self._sb_tick_n, r+2, 1); lay.addWidget(self._lbl_tick, r+2, 2, 1, 2)
        lay.addWidget(sep(), r+3, 0, 1, 4)
        self._sb_drop = spinbox(10, 90, 40, "%")
        lay.addWidget(lbl("급락 비율:"), r+4, 0, Qt.AlignRight); lay.addWidget(self._sb_drop, r+4, 1)
        lay.addWidget(lbl("이상 급락 시 발동", "#888", 11), r+4, 2, 1, 2)
        self._dsb_floor = dspinbox(0.05, 5.00, 0.20, 0.05, prefix="$")
        lay.addWidget(lbl("절대가 상한:"), r+5, 0, Qt.AlignRight); lay.addWidget(self._dsb_floor, r+5, 1)

    def _build_order_section(self, lay, r: int) -> None:
        mw = QWidget(); mw.setStyleSheet("background:transparent;")
        mr = QHBoxLayout(mw); mr.setContentsMargins(0,0,0,0); mr.setSpacing(10)
        self._rb_ask = QRadioButton("1호가 위"); self._rb_fix = QRadioButton("고정값")
        self._rb_ask.setChecked(True)
        for rb in (self._rb_ask, self._rb_fix):
            rb.setStyleSheet("color:#dde0f0;font-size:15px;border:none;")
        grp = QButtonGroup(self); grp.addButton(self._rb_ask, 0); grp.addButton(self._rb_fix, 1)
        mr.addWidget(self._rb_ask); mr.addWidget(self._rb_fix)
        lay.addWidget(lbl("주문 방식:"), r, 0, Qt.AlignRight); lay.addWidget(mw, r, 1, 1, 3)
        self._dsb_fixed = dspinbox(0.01, 9.99, 0.15, 0.05, prefix="$")
        self._rb_ask.toggled.connect(lambda on: self._dsb_fixed.setEnabled(not on))
        self._dsb_fixed.setEnabled(False)
        lay.addWidget(lbl("고정 주문가:"), r+1, 0, Qt.AlignRight); lay.addWidget(self._dsb_fixed, r+1, 1)
        self._sb_wait = spinbox(1, 60, 2, "초"); self._dsb_step = dspinbox(0.01, 1.00, 0.05, 0.01, prefix="$")
        lay.addWidget(lbl("정정 대기:"), r+2, 0, Qt.AlignRight); lay.addWidget(self._sb_wait, r+2, 1)
        lay.addWidget(lbl("정정 단위:"), r+2, 2, Qt.AlignRight); lay.addWidget(self._dsb_step, r+2, 3)
        self._sb_max = spinbox(1, 10, 3, "회"); self._dsb_cap = dspinbox(0.05, 9.99, 0.30, 0.05, prefix="$")
        lay.addWidget(lbl("최대 정정:"), r+3, 0, Qt.AlignRight); lay.addWidget(self._sb_max, r+3, 1)
        lay.addWidget(lbl("정정 상한가:"), r+3, 2, Qt.AlignRight); lay.addWidget(self._dsb_cap, r+3, 3)
        self._sb_budget = spinbox(10, 9999, 100, "$")
        lay.addWidget(lbl("투자 예산:"), r+4, 0, Qt.AlignRight); lay.addWidget(self._sb_budget, r+4, 1)
        lay.addWidget(sep(), r+5, 0, 1, 4)

    def _build_sell_section(self, lay, r: int) -> None:
        self._chk_sell = checkbox("💰 체결 즉시 자동 매도", "#2ecc71", "#2ecc71")
        self._chk_sell.stateChanged.connect(
            lambda s: [w.setEnabled(bool(s)) for w in self._sell_ws])
        lay.addWidget(self._chk_sell, r, 0, 1, 4)
        self._cmb_sell = combo([("체결가 × 배수", "multiplier"), ("고정가", "fixed")], 180)
        self._cmb_sell.currentIndexChanged.connect(self._on_sell_mode)
        lay.addWidget(lbl("매도 방식:"), r+1, 0, Qt.AlignRight)
        lay.addWidget(self._cmb_sell, r+1, 1, 1, 3)
        self._dsb_mult = dspinbox(1.1, 20.0, 3.0, 0.5, 1)
        self._dsb_mult.valueChanged.connect(self._update_preview)
        self._lbl_prev = lbl("", "#8cf", 11)
        lay.addWidget(lbl("배수:"), r+2, 0, Qt.AlignRight)
        lay.addWidget(self._dsb_mult, r+2, 1); lay.addWidget(self._lbl_prev, r+2, 2, 1, 2)
        self._dsb_sfixed = dspinbox(0.05, 50.0, 2.50, 0.05, prefix="$")
        lay.addWidget(lbl("고정 매도가:"), r+3, 0, Qt.AlignRight)
        lay.addWidget(self._dsb_sfixed, r+3, 1)
        self._sell_ws = [self._cmb_sell, self._dsb_mult, self._lbl_prev, self._dsb_sfixed]

    def save(self) -> None:
        from Sleep_Order.ui_panel_single_io import save_single
        save_single(self)

    def load(self) -> None:
        from Sleep_Order.ui_panel_single_io import load_single
        load_single(self)
