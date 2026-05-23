"""
ui_panel_debit.py — Debit Spread 급락 캐치 설정 패널  v1.0
════════════════════════════════════════
DebitSpikePanel : QGroupBox 서브클래스
  - ON/OFF 토글 버튼
  - 전용 시간 (KST 입력 → ET 저장)
  - 기준가 방식 (time/tick)
  - 급락 조건, 주문/정정, 자동매도
  - 저장 버튼
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QGridLayout, QHBoxLayout, QVBoxLayout,
    QWidget, QPushButton, QButtonGroup, QRadioButton,
)
from PyQt5.QtCore import Qt

from Sleep_Order.ui_helpers import (
    gb, lbl, btn, spinbox, dspinbox, time_edit, combo, checkbox,
    sep, spike_btn_style, load_kst_time, update_et_preview,
    kst_to_et, _is_edt,
)


class DebitSpikePanel(QGroupBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("⚡  Debit Spread 급락 캐치")
        self.setStyleSheet(
            "QGroupBox{font-size:15px;color:#ff6b6b;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:6px;"
            "margin-top:10px;padding-top:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}")
        self._build()
        self.load()

    def _build(self) -> None:
        lay = QGridLayout(self)
        lay.setContentsMargins(12, 14, 12, 10); lay.setSpacing(8)
        r = 0

        # ON/OFF 토글
        self._btn_toggle = QPushButton("⚡  급락 캐치  OFF")
        self._btn_toggle.setCheckable(True); self._btn_toggle.setFixedHeight(34)
        self._btn_toggle.setStyleSheet(spike_btn_style(False))
        self._btn_toggle.clicked.connect(self._on_toggle)
        self._lbl_status = lbl("● 비활성", "#888", 12)
        row0 = QHBoxLayout()
        row0.addWidget(self._btn_toggle); row0.addWidget(self._lbl_status)
        row0.addStretch()
        lay.addLayout(row0, r, 0, 1, 4); r += 1
        lay.addWidget(sep(), r, 0, 1, 4); r += 1

        # 전용 시간
        self._chk_own = checkbox("예약주문과 별도 시간대", "#ff9988", "#ff6b6b")
        self._chk_own.stateChanged.connect(
            lambda s: [w.setEnabled(bool(s)) for w in self._time_widgets])
        lay.addWidget(self._chk_own, r, 0, 1, 4); r += 1

        tz = "EDT" if _is_edt() else "EST"
        lay.addWidget(lbl(f"KST 입력 → {tz} 자동변환", "#ff9988", 11), r, 0, 1, 4); r += 1

        self._te_start = time_edit("01:53"); self._lbl_start_et = lbl("→ ET --:--", "#888", 12)
        self._te_end   = time_edit("18:14"); self._lbl_end_et   = lbl("→ ET --:--", "#888", 12)
        self._te_start.timeChanged.connect(
            lambda: update_et_preview(self._te_start, self._lbl_start_et))
        self._te_end.timeChanged.connect(
            lambda: update_et_preview(self._te_end, self._lbl_end_et))
        lay.addWidget(lbl("시작 (KST):"), r, 0, Qt.AlignRight)
        lay.addWidget(self._te_start, r, 1); lay.addWidget(self._lbl_start_et, r, 2, 1, 2); r += 1
        lay.addWidget(lbl("종료 (KST):"), r, 0, Qt.AlignRight)
        lay.addWidget(self._te_end, r, 1); lay.addWidget(self._lbl_end_et, r, 2, 1, 2); r += 1
        self._time_widgets = [self._te_start, self._lbl_start_et,
                              self._te_end, self._lbl_end_et]
        lay.addWidget(sep(), r, 0, 1, 4); r += 1

        # 기준가 방식
        lay.addWidget(lbl("기준가 방식:"), r, 0, Qt.AlignRight)
        self._cmb_mode = combo([("시간 기준  (N분 고가)", "time"),
                                ("틱 평균    (N개 mid)", "tick")], 200)
        self._cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self._cmb_mode, r, 1, 1, 3); r += 1

        lay.addWidget(lbl("기준 시간:"), r, 0, Qt.AlignRight)
        self._sb_ref_min = spinbox(1, 60, 3, "분")
        self._lbl_ref_min = lbl("N분간 최고가 → 기준가 확정", "#888", 11)
        lay.addWidget(self._sb_ref_min, r, 1); lay.addWidget(self._lbl_ref_min, r, 2, 1, 2); r += 1

        lay.addWidget(lbl("틱 평균 N:"), r, 0, Qt.AlignRight)
        self._sb_tick_n = spinbox(5, 10, 7, "개")
        self._lbl_tick  = lbl("최근 N개 mid 평균", "#888", 11)
        lay.addWidget(self._sb_tick_n, r, 1); lay.addWidget(self._lbl_tick, r, 2, 1, 2); r += 1
        lay.addWidget(sep(), r, 0, 1, 4); r += 1

        # 급락 조건
        lay.addWidget(lbl("급락 비율:"), r, 0, Qt.AlignRight)
        self._sb_drop = spinbox(10, 90, 40, "%")
        lay.addWidget(self._sb_drop, r, 1)
        lay.addWidget(lbl("이상 급락 시 발동", "#888", 11), r, 2, 1, 2); r += 1

        lay.addWidget(lbl("절대가 상한:"), r, 0, Qt.AlignRight)
        self._dsb_floor = dspinbox(0.05, 1.00, 0.20, 0.05, prefix="$")
        lay.addWidget(self._dsb_floor, r, 1); r += 1

        # 주문 방식
        lay.addWidget(lbl("주문 방식:"), r, 0, Qt.AlignRight)
        mw = QWidget(); mw.setStyleSheet("background:transparent;")
        mr = QHBoxLayout(mw); mr.setContentsMargins(0,0,0,0); mr.setSpacing(10)
        self._rb_ask1  = QRadioButton("1호가 위"); self._rb_fixed = QRadioButton("고정값")
        self._rb_ask1.setChecked(True)
        for rb in (self._rb_ask1, self._rb_fixed):
            rb.setStyleSheet("color:#dde0f0;font-size:15px;border:none;")
        grp = QButtonGroup(self)
        grp.addButton(self._rb_ask1, 0); grp.addButton(self._rb_fixed, 1)
        mr.addWidget(self._rb_ask1); mr.addWidget(self._rb_fixed)
        lay.addWidget(mw, r, 1, 1, 3); r += 1

        lay.addWidget(lbl("고정 주문가:"), r, 0, Qt.AlignRight)
        self._dsb_fixed = dspinbox(0.01, 9.99, 0.15, 0.05, prefix="$")
        self._rb_ask1.toggled.connect(lambda on: self._dsb_fixed.setEnabled(not on))
        self._dsb_fixed.setEnabled(False)
        lay.addWidget(self._dsb_fixed, r, 1); r += 1

        # 정정
        lay.addWidget(lbl("정정 대기:"), r, 0, Qt.AlignRight)
        self._sb_wait = spinbox(1, 60, 2, "초")
        lay.addWidget(self._sb_wait, r, 1)
        lay.addWidget(lbl("정정 단위:"), r, 2, Qt.AlignRight)
        self._dsb_step = dspinbox(0.01, 1.00, 0.05, 0.01, prefix="$")
        lay.addWidget(self._dsb_step, r, 3); r += 1

        lay.addWidget(lbl("최대 정정:"), r, 0, Qt.AlignRight)
        self._sb_max_mod = spinbox(1, 10, 3, "회")
        lay.addWidget(self._sb_max_mod, r, 1)
        lay.addWidget(lbl("정정 상한가:"), r, 2, Qt.AlignRight)
        self._dsb_cap = dspinbox(0.05, 9.99, 0.30, 0.05, prefix="$")
        lay.addWidget(self._dsb_cap, r, 3); r += 1

        lay.addWidget(lbl("투자 예산:"), r, 0, Qt.AlignRight)
        self._sb_budget = spinbox(10, 9999, 100, "$")
        lay.addWidget(self._sb_budget, r, 1); r += 1
        lay.addWidget(sep(), r, 0, 1, 4); r += 1

        # 자동 매도
        self._chk_sell = checkbox("💰 체결 즉시 자동 매도", "#2ecc71", "#2ecc71")
        self._chk_sell.stateChanged.connect(
            lambda s: [w.setEnabled(bool(s)) for w in self._sell_widgets])
        lay.addWidget(self._chk_sell, r, 0, 1, 4); r += 1

        lay.addWidget(lbl("매도 방식:"), r, 0, Qt.AlignRight)
        self._cmb_sell = combo([("체결가 × 배수", "multiplier"), ("고정가", "fixed")], 180)
        self._cmb_sell.currentIndexChanged.connect(self._on_sell_mode_changed)
        lay.addWidget(self._cmb_sell, r, 1, 1, 3); r += 1

        lay.addWidget(lbl("배수:"), r, 0, Qt.AlignRight)
        self._dsb_mult = dspinbox(1.1, 20.0, 3.0, 0.5, 1)
        self._dsb_mult.valueChanged.connect(self._update_sell_preview)
        self._lbl_preview = lbl("", "#8cf", 11)
        lay.addWidget(self._dsb_mult, r, 1); lay.addWidget(self._lbl_preview, r, 2, 1, 2); r += 1

        lay.addWidget(lbl("고정 매도가:"), r, 0, Qt.AlignRight)
        self._dsb_sell_fixed = dspinbox(0.05, 50.0, 2.50, 0.05, prefix="$")
        lay.addWidget(self._dsb_sell_fixed, r, 1); r += 1
        self._sell_widgets = [self._cmb_sell, self._dsb_mult,
                              self._lbl_preview, self._dsb_sell_fixed]

        # 저장
        self._lbl_st = lbl("", "#aaa", 12)
        lay.addWidget(self._lbl_st, r, 0, 1, 4); r += 1
        b = btn("✔  저장", "#1a2a1a", "#00e676")
        b.clicked.connect(self.save)
        lay.addWidget(b, r, 0)

    # ── 핸들러 ──────────────────────────────────────────────
    def _on_toggle(self, checked: bool) -> None:
        self._btn_toggle.setText("⚡  급락캐치  ON (OFF하려면 클릭)" if checked else "⚡  급락 캐치  OFF")
        self._btn_toggle.setStyleSheet(spike_btn_style(checked))
        self._lbl_status.setText("● 활성" if checked else "● 비활성")
        self._lbl_status.setStyleSheet(f"color:{'#ff4444' if checked else '#888'};font-size:12px;border:none;")
        try:
            from Sleep_Order.sleep_order_config  import sleep_cfg
            from Sleep_Order.spike_catcher_debit import DebitSpikeWatcher
            sleep_cfg.set("spike_enabled", checked); sleep_cfg.save()
            DebitSpikeWatcher.get().reconfigure_all()
        except Exception as e:
            print(f"[DebitPanel] 즉시저장 실패: {e}")

    def _on_mode_changed(self, *_) -> None:
        is_time = self._cmb_mode.currentData() == "time"
        self._sb_ref_min.setVisible(is_time); self._lbl_ref_min.setVisible(is_time)
        self._sb_tick_n.setVisible(not is_time); self._lbl_tick.setVisible(not is_time)

    def _on_sell_mode_changed(self, *_) -> None:
        is_mult = self._cmb_sell.currentData() == "multiplier"
        self._dsb_mult.setVisible(is_mult); self._lbl_preview.setVisible(is_mult)
        self._dsb_sell_fixed.setVisible(not is_mult)
        if is_mult: self._update_sell_preview()

    def _update_sell_preview(self, *_) -> None:
        m = self._dsb_mult.value()
        self._lbl_preview.setText("  예) " + "  /  ".join(
            f"${p:.2f}→${p*m:.2f}" for p in (0.10, 0.15, 0.20, 0.30)))

    # ── 저장 / 로드 ────────────────────────────────────────
    def save(self) -> None:
        from Sleep_Order.ui_panel_debit_io import save_debit
        save_debit(self)

    def load(self) -> None:
        from Sleep_Order.ui_panel_debit_io import load_debit
        load_debit(self)
