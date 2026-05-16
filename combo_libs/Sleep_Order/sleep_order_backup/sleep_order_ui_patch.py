"""
sleep_order_ui_patch.py — 신규 설정 UI 위젯  v1.0
════════════════════════════════════════════════════════════════
기존 sleep_order_ui.py 의 설정 탭에 아래 두 섹션을 추가.

[섹션 B2] 급락 캐치 — 시간 / 기준가 설정  (spike_tab 또는 기존 탭 하단)
[섹션 C ] 자동 매도 설정

사용법:
  기존 SleepOrderSettingsTab.__init__() 의 레이아웃 끝부분에서
  아래 두 위젯을 생성 후 addWidget() 으로 추가:

    from Sleep_Order.sleep_order_ui_patch import (
        SpikeScheduleWidget, AutoSellWidget)

    self._spike_schedule_w = SpikeScheduleWidget()
    self._auto_sell_w      = AutoSellWidget()
    layout.addWidget(self._spike_schedule_w)
    layout.addWidget(self._auto_sell_w)

  저장 버튼 핸들러에서:
    self._spike_schedule_w.save()
    self._auto_sell_w.save()

  로드 시:
    self._spike_schedule_w.load()
    self._auto_sell_w.load()
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui  import QFont
from PyQt5.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QDoubleSpinBox,
    QSpinBox, QPushButton, QSizePolicy
)


def _bold(text: str) -> QLabel:
    lbl = QLabel(text)
    f   = lbl.font()
    f.setBold(True)
    lbl.setFont(f)
    return lbl


def _section_box(title: str) -> QGroupBox:
    box = QGroupBox(title)
    box.setStyleSheet(
        "QGroupBox { font-weight: bold; border: 1px solid #555;"
        " border-radius: 4px; margin-top: 6px; padding-top: 4px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
    )
    return box


# ══════════════════════════════════════════════════════════════
# SpikeScheduleWidget — 섹션 B2: 급락 캐치 시간 / 기준가
# ══════════════════════════════════════════════════════════════

class SpikeScheduleWidget(QWidget):
    """
    급락 캐치 전용 시간 설정 + 기준가 산출 방식 선택 위젯.

    필드:
      spike_use_own_schedule  체크박스
      spike_start / spike_end  HH:MM 입력
      spike_ref_mode           콤보 (시간 기준 / 틱 평균)
      spike_ref_minutes        스핀박스 (mode=time)
      tick_window              스핀박스 (mode=tick)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.load()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── 그룹박스 ─────────────────────────────────────────
        box  = _section_box("📡 급락 캐치 — 시간 / 기준가 설정")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        box.setLayout(form)

        # 전용 시간대 사용 여부
        self._chk_own = QCheckBox("예약주문과 별도 시간대 사용")
        self._chk_own.stateChanged.connect(self._on_own_toggled)
        form.addRow("", self._chk_own)

        # spike_start / spike_end
        self._ed_start = QLineEdit()
        self._ed_start.setPlaceholderText("HH:MM  (ET)")
        self._ed_start.setFixedWidth(80)
        self._ed_end   = QLineEdit()
        self._ed_end.setPlaceholderText("HH:MM  (ET)")
        self._ed_end.setFixedWidth(80)

        time_row = QHBoxLayout()
        time_row.addWidget(self._ed_start)
        time_row.addWidget(QLabel("~"))
        time_row.addWidget(self._ed_end)
        time_row.addWidget(QLabel("(ET, 자정 넘김 지원)"))
        time_row.addStretch()
        self._time_container = QWidget()
        self._time_container.setLayout(time_row)
        form.addRow("감시 시간", self._time_container)

        # 구분선
        sep = QLabel("─" * 40)
        sep.setStyleSheet("color: #666;")
        form.addRow("", sep)

        # 기준가 산출 방식
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItem("시간 기준  (N분 전 고가)", "time")
        self._cmb_mode.addItem("틱 평균    (최근 N개 mid 평균)", "tick")
        self._cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self._cmb_mode.setFixedWidth(240)
        form.addRow("기준가 방식", self._cmb_mode)

        # spike_ref_minutes (mode=time)
        self._spn_minutes = QSpinBox()
        self._spn_minutes.setRange(1, 60)
        self._spn_minutes.setSuffix(" 분")
        self._spn_minutes.setFixedWidth(80)
        self._lbl_minutes = QLabel("기준가 lookback")
        form.addRow(self._lbl_minutes, self._spn_minutes)

        note_time = QLabel(
            "  예) 3분 설정 시: 감시 시작 후 3분간 수신 가격 중\n"
            "  최고가를 기준가로 확정. 그 이후 현재가가 N% 이하로\n"
            "  떨어지면 급락 캐치 발동."
        )
        note_time.setStyleSheet("color: #aaa; font-size: 11px;")
        self._note_time = note_time
        form.addRow("", note_time)

        # tick_window (mode=tick)
        self._spn_window = QSpinBox()
        self._spn_window.setRange(1, 50)
        self._spn_window.setSuffix(" 개")
        self._spn_window.setFixedWidth(80)
        self._lbl_window = QLabel("틱 평균 개수")
        form.addRow(self._lbl_window, self._spn_window)

        note_tick = QLabel(
            "  최근 N개 틱 mid 평균을 기준가로 사용.\n"
            "  (기존 방식)"
        )
        note_tick.setStyleSheet("color: #aaa; font-size: 11px;")
        self._note_tick = note_tick
        form.addRow("", note_tick)

        root.addWidget(box)
        self._on_mode_changed()   # 초기 표시 상태 적용

    def _on_own_toggled(self, state: int) -> None:
        enabled = bool(state)
        self._time_container.setEnabled(enabled)

    def _on_mode_changed(self, *_) -> None:
        is_time = (self._cmb_mode.currentData() == "time")
        self._spn_minutes.setVisible(is_time)
        self._lbl_minutes.setVisible(is_time)
        self._note_time.setVisible(is_time)
        self._spn_window.setVisible(not is_time)
        self._lbl_window.setVisible(not is_time)
        self._note_tick.setVisible(not is_time)

    # ── 저장 / 로드 ─────────────────────────────────────────────
    def save(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        sleep_cfg.set("spike_use_own_schedule", self._chk_own.isChecked())
        sleep_cfg.set("spike_start",   self._ed_start.text().strip() or "16:53")
        sleep_cfg.set("spike_end",     self._ed_end.text().strip()   or "05:14")
        sleep_cfg.set("spike_ref_mode",    self._cmb_mode.currentData())
        sleep_cfg.set("spike_ref_minutes", self._spn_minutes.value())
        sleep_cfg.set("tick_window",       self._spn_window.value())
        sleep_cfg.save()

        # 실행 중인 catcher 에 즉시 반영
        try:
            from Sleep_Order.sleep_order_spike import SleepSpikeWatcher
            SleepSpikeWatcher.get().reconfigure_all()
        except Exception:
            pass

    def load(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        own = sleep_cfg.spike_use_own_schedule
        self._chk_own.setChecked(own)
        self._time_container.setEnabled(own)
        self._ed_start.setText(sleep_cfg.get("spike_start", "16:53"))
        self._ed_end.setText(sleep_cfg.get("spike_end",   "05:14"))

        mode = sleep_cfg.spike_ref_mode
        idx  = self._cmb_mode.findData(mode)
        if idx >= 0:
            self._cmb_mode.setCurrentIndex(idx)

        self._spn_minutes.setValue(sleep_cfg.spike_ref_minutes)
        self._spn_window.setValue(sleep_cfg.tick_window)
        self._on_mode_changed()


# ══════════════════════════════════════════════════════════════
# AutoSellWidget — 섹션 C: 자동 매도 (체결 즉시 익절)
# ══════════════════════════════════════════════════════════════

class AutoSellWidget(QWidget):
    """
    급락 캐치 매수 체결 직후 자동 매도 설정 위젯.

    필드:
      auto_sell_enabled     ON/OFF 체크박스
      auto_sell_mode        콤보 (고정가 / 배수)
      auto_sell_fixed_price 고정 매도가 (mode=fixed)
      auto_sell_multiplier  매수 체결가 × 배수 (mode=multiplier)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.load()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        box  = _section_box("💰 자동 매도 설정  (급락 캐치 체결 즉시)")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        box.setLayout(form)

        # ON/OFF
        self._chk_enabled = QCheckBox("체결 즉시 익절 주문 자동 전송")
        self._chk_enabled.stateChanged.connect(self._on_enabled_toggled)
        form.addRow("", self._chk_enabled)

        # 주문가 방식
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItem("고정가  (항상 같은 가격으로 매도)", "fixed")
        self._cmb_mode.addItem("배수    (매수 체결가 × N배로 매도)", "multiplier")
        self._cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self._cmb_mode.setFixedWidth(280)
        form.addRow("매도 주문가", self._cmb_mode)

        # 고정가
        self._spn_fixed = QDoubleSpinBox()
        self._spn_fixed.setRange(0.05, 50.0)
        self._spn_fixed.setSingleStep(0.05)
        self._spn_fixed.setDecimals(2)
        self._spn_fixed.setPrefix("$ ")
        self._spn_fixed.setFixedWidth(100)
        self._lbl_fixed = QLabel("고정 매도가")
        form.addRow(self._lbl_fixed, self._spn_fixed)

        note_fixed = QLabel("  항상 이 가격으로 매도 지정가 주문.")
        note_fixed.setStyleSheet("color: #aaa; font-size: 11px;")
        self._note_fixed = note_fixed
        form.addRow("", note_fixed)

        # 배수
        self._spn_mult = QDoubleSpinBox()
        self._spn_mult.setRange(1.1, 20.0)
        self._spn_mult.setSingleStep(0.5)
        self._spn_mult.setDecimals(1)
        self._spn_mult.setSuffix(" 배")
        self._spn_mult.setFixedWidth(100)
        self._lbl_mult = QLabel("매수가 대비 배수")
        form.addRow(self._lbl_mult, self._spn_mult)

        self._lbl_preview = QLabel("")
        self._lbl_preview.setStyleSheet("color: #8cf; font-size: 11px;")
        self._spn_mult.valueChanged.connect(self._update_preview)
        self._note_mult = QLabel(
            "  예) 매수 체결가 $0.10, 배수 3.0 → 매도 주문가 $0.30\n"
            "  체결가 기준으로 확정되므로 정정 없이 단 1회 주문."
        )
        self._note_mult.setStyleSheet("color: #aaa; font-size: 11px;")
        form.addRow("", self._note_mult)
        form.addRow("예상 매도가", self._lbl_preview)

        # 주의 문구
        warn = QLabel(
            "⚠  자동 매도 주문은 급락 캐치 매수 체결 직후 즉시 전송됩니다.\n"
            "    ref._sleep_place_sell_order() 콜백이 구현되어 있어야 합니다."
        )
        warn.setStyleSheet("color: #f90; font-size: 11px;")
        form.addRow("", warn)

        root.addWidget(box)
        self._on_mode_changed()

    def _on_enabled_toggled(self, state: int) -> None:
        enabled = bool(state)
        for w in (self._cmb_mode, self._spn_fixed, self._lbl_fixed,
                  self._note_fixed, self._spn_mult, self._lbl_mult,
                  self._note_mult, self._lbl_preview):
            w.setEnabled(enabled)

    def _on_mode_changed(self, *_) -> None:
        is_fixed = (self._cmb_mode.currentData() == "fixed")
        self._spn_fixed.setVisible(is_fixed)
        self._lbl_fixed.setVisible(is_fixed)
        self._note_fixed.setVisible(is_fixed)
        self._spn_mult.setVisible(not is_fixed)
        self._lbl_mult.setVisible(not is_fixed)
        self._note_mult.setVisible(not is_fixed)
        self._lbl_preview.setVisible(not is_fixed)
        if not is_fixed:
            self._update_preview()

    def _update_preview(self, *_) -> None:
        """배수 모드: 예시 체결가 기준 미리보기."""
        mult = self._spn_mult.value()
        examples = [0.10, 0.15, 0.20, 0.30]
        parts = [f"${p:.2f}→${p*mult:.2f}" for p in examples]
        self._lbl_preview.setText("  예) " + "  /  ".join(parts))

    # ── 저장 / 로드 ─────────────────────────────────────────────
    def save(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        sleep_cfg.set("auto_sell_enabled",     self._chk_enabled.isChecked())
        sleep_cfg.set("auto_sell_mode",        self._cmb_mode.currentData())
        sleep_cfg.set("auto_sell_fixed_price", self._spn_fixed.value())
        sleep_cfg.set("auto_sell_multiplier",  self._spn_mult.value())
        sleep_cfg.save()

    def load(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        self._chk_enabled.setChecked(sleep_cfg.auto_sell_enabled)

        mode = sleep_cfg.auto_sell_mode
        idx  = self._cmb_mode.findData(mode)
        if idx >= 0:
            self._cmb_mode.setCurrentIndex(idx)

        self._spn_fixed.setValue(sleep_cfg.auto_sell_fixed_price)
        self._spn_mult.setValue(sleep_cfg.auto_sell_multiplier)
        self._on_enabled_toggled(int(sleep_cfg.auto_sell_enabled))
        self._on_mode_changed()
        self._update_preview()


# ══════════════════════════════════════════════════════════════
# combo_order_callbacks.py 수정 가이드
# ══════════════════════════════════════════════════════════════
"""
기존 Filled 핸들러에서:

  # 기존 (fill_price 전달 안 함)
  SleepSpikeWatcher.get().unwatch_by_oid(oid)

  # 변경 후 (avgFillPrice 전달)
  SleepSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avgFillPrice)

기존 Cancelled 핸들러에서:

  # 기존
  SleepSpikeWatcher.get().unwatch_by_oid(oid)

  # 변경 후
  SleepSpikeWatcher.get().unwatch_cancelled_by_oid(oid)

ref 객체에 추가 필요한 콜백:

  def _sleep_place_sell_order(self, legs, lmt_price, qty, strat, tag) -> int:
      \"\"\"급락 캐치 매수 체결 후 자동 익절 매도 주문.\"\"\"
      # 기존 _sleep_place_order 와 동일하되 action='SELL' 로 전달
      return self._place_bag_order(legs, lmt_price, qty,
                                   action='SELL', tag=tag)
"""
