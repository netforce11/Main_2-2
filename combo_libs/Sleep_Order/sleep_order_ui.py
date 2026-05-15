"""
sleep_order_ui.py — 수면 예약 주문 UI  v1.2
════════════════════════════════════════════════════════════════
변경 이력 v1.2:
  - 감시 시간 입력을 KST 기준으로 변경 (내부에서 ET 자동 변환, 서머타임 감지)
  - 체인 확인 출력 창 추가 (버튼 아래 별도 텍스트 영역 + 범위내 스프레드 상세)
  - 목표가 옆 현재 체인 가격 비교 표시 (현재가 ≤ 목표가 조건 강조)
  - 예약주문 버튼 ON 시 체인 확인 자동 실행
  - findChildren(type(w)) 버그 → findChildren(QWidget) 수정

제공 클래스:
  SleepOrderRightPanel  : Main_config.py 우측에 삽입되는 설정 패널
  SleepOrderButton      : combo_ui_synthetic_panel.py 우측 상단 버튼 위젯
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox,
    QGroupBox, QScrollArea, QButtonGroup, QRadioButton,
    QSizePolicy, QTimeEdit, QTextEdit, QFrame,
)
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtGui import QFont


# ══════════════════════════════════════════════════════════════
# KST ↔ ET 변환 유틸
# ══════════════════════════════════════════════════════════════

def _is_edt() -> bool:
    """
    현재 미국 동부 서머타임(EDT, UTC-4) 여부 반환.
    서머타임: 3월 둘째 일요일 02:00 ~ 11월 첫째 일요일 02:00
    ZoneInfo 로 정확히 판별.
    """
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
    except Exception:
        try:
            from backports.zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            return False
    now = datetime.now(tz)
    # UTC 오프셋이 -4시간이면 EDT, -5시간이면 EST
    return now.utcoffset().total_seconds() == -4 * 3600


def _kst_to_et(hhmm: str) -> str:
    """
    KST HH:MM → ET HH:MM 변환.
    KST = UTC+9
    EDT = UTC-4  →  KST 에서 -13시간
    EST = UTC-5  →  KST 에서 -14시간
    자정 넘김 자동 처리.
    """
    try:
        h, m = map(int, hhmm.split(":"))
        offset = 13 if _is_edt() else 14
        total = h * 60 + m - offset * 60
        total = total % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return hhmm


def _et_to_kst(hhmm: str) -> str:
    """ET HH:MM → KST HH:MM 변환."""
    try:
        h, m = map(int, hhmm.split(":"))
        offset = 13 if _is_edt() else 14
        total = h * 60 + m + offset * 60
        total = total % (24 * 60)
        return f"{total // 60:02d}:{total % 60:02d}"
    except Exception:
        return hhmm


# ── 스타일 헬퍼 ─────────────────────────────────────────────────

def _gb(title: str, color: str = "#5dade2") -> QGroupBox:
    gb = QGroupBox(title)
    gb.setStyleSheet(
        f"QGroupBox{{font-size:16px;color:{color};font-weight:bold;"
        f"border:1px solid #2a2a5a;border-radius:6px;"
        f"margin-top:10px;padding-top:8px;}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;}}"
    )
    return gb


def _lbl(text: str, color: str = "#dde0f0", size: int = 16) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{color};font-size:{size}px;border:none;")
    return lbl


def _btn(text: str, color: str = "#1c1c3a", fg: str = "#dde0f0") -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:{fg};font-size:16px;"
        f"border:1px solid #3a3a7a;border-radius:4px;padding:4px 14px;}}"
        f"QPushButton:hover{{background:#2a2a5a;color:#fff;}}"
        f"QPushButton:pressed{{background:#0e0e2a;}}"
    )
    return b


def _spinbox(min_val: int, max_val: int, val: int,
             suffix: str = "") -> QSpinBox:
    sb = QSpinBox()
    sb.setMinimum(min_val); sb.setMaximum(max_val); sb.setValue(val)
    if suffix:
        sb.setSuffix(f" {suffix}")
    sb.setFixedWidth(110)
    sb.setStyleSheet(
        "QSpinBox{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}"
    )
    return sb


def _dspinbox(min_val: float, max_val: float, val: float,
              step: float = 0.05, decimals: int = 2,
              prefix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setMinimum(min_val); sb.setMaximum(max_val)
    sb.setValue(val); sb.setSingleStep(step)
    sb.setDecimals(decimals)
    if prefix:
        sb.setPrefix(prefix)
    sb.setFixedWidth(110)
    sb.setStyleSheet(
        "QDoubleSpinBox{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}"
    )
    return sb


def _time_edit(hhmm: str) -> QTimeEdit:
    te = QTimeEdit()
    try:
        h, m = map(int, hhmm.split(":"))
        te.setTime(QTime(h, m))
    except Exception:
        te.setTime(QTime(4, 40))
    te.setDisplayFormat("HH:mm")
    te.setFixedWidth(80)
    te.setStyleSheet(
        "QTimeEdit{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}"
    )
    return te


# ══════════════════════════════════════════════════════════════
# SleepOrderRightPanel — Main_config 우측 패널
# ══════════════════════════════════════════════════════════════

class SleepOrderRightPanel(QWidget):
    """
    Main_config.py 의 우측 절반에 삽입.
    설정값 표시/편집 + JSON 저장.
    감시 시간은 KST 로 입력받아 내부에서 ET 변환 후 저장.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#0a0a18;")
        self._build()
        self._load_values()

    # ── 빌드 ────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#0a0a18;}"
            "QScrollBar:vertical{width:8px;background:#06060e;}"
            "QScrollBar::handle:vertical{background:#3a3a7a;border-radius:4px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )

        inner = QWidget(); inner.setStyleSheet("background:#0a0a18;")
        vlay  = QVBoxLayout(inner)
        vlay.setContentsMargins(12, 12, 12, 16)
        vlay.setSpacing(10)

        hdr = QLabel("🌙  수면 예약 주문 설정")
        hdr.setStyleSheet(
            "color:#ffd700;font-size:20px;font-weight:bold;border:none;"
            "padding:6px 0 2px 0;"
        )
        vlay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;margin:4px 0;")
        vlay.addWidget(sep)

        vlay.addWidget(self._build_section_a())
        vlay.addWidget(self._build_section_b())
        vlay.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll)

    # ── 섹션 A: 예약 주문 ────────────────────────────────────────

    def _build_section_a(self) -> QGroupBox:
        gb  = _gb("📅  예약 주문 설정", "#ffd700")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        r = 0

        # ── KST 입력 안내 ─────────────────────────────────────
        tz_tag = "EDT(서머타임)" if _is_edt() else "EST(표준시)"
        kst_note = _lbl(f"⏰ 한국시간(KST) 기준 입력  →  {tz_tag} 자동 변환", "#ffd700", 12)
        lay.addWidget(kst_note, r, 0, 1, 4); r += 1

        # 감시 시작
        lay.addWidget(_lbl("감시 시작 (KST):"), r, 0, Qt.AlignRight)
        self._te_start = _time_edit("05:40")
        lay.addWidget(self._te_start, r, 1)
        self._lbl_start_et = _lbl("→ ET --:--", "#888", 12)
        lay.addWidget(self._lbl_start_et, r, 2, 1, 2)
        self._te_start.timeChanged.connect(self._update_et_preview)
        r += 1

        # 감시 종료
        lay.addWidget(_lbl("감시 종료 (KST):"), r, 0, Qt.AlignRight)
        self._te_end = _time_edit("18:14")
        lay.addWidget(self._te_end, r, 1)
        self._lbl_end_et = _lbl("→ ET --:--", "#888", 12)
        lay.addWidget(self._lbl_end_et, r, 2, 1, 2)
        self._te_end.timeChanged.connect(self._update_et_preview)
        r += 1

        # 구분선
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        lay.addWidget(sep, r, 0, 1, 4); r += 1

        # 만기
        lay.addWidget(_lbl("만기 오프셋:"), r, 0, Qt.AlignRight)
        self._sb_expiry = _spinbox(0, 2, 1, "일")
        lay.addWidget(self._sb_expiry, r, 1)
        lay.addWidget(_lbl("(D+0/+1/+2)", "#888", 11), r, 2, 1, 2); r += 1

        # 행사가 거리
        lay.addWidget(_lbl("행사가 거리 하한:"), r, 0, Qt.AlignRight)
        self._dsb_dist_min = _dspinbox(0.10, 2.00, 0.60, 0.05, prefix="")
        lay.addWidget(self._dsb_dist_min, r, 1)
        lay.addWidget(_lbl("%", "#aaa", 13), r, 2); r += 1

        lay.addWidget(_lbl("행사가 거리 상한:"), r, 0, Qt.AlignRight)
        self._dsb_dist_max = _dspinbox(0.10, 2.00, 0.95, 0.05, prefix="")
        lay.addWidget(self._dsb_dist_max, r, 1)
        lay.addWidget(_lbl("%", "#aaa", 13), r, 2); r += 1

        # 스프레드 폭
        lay.addWidget(_lbl("스프레드 폭:"), r, 0, Qt.AlignRight)
        self._sb_width = _spinbox(5, 100, 20, "$")
        lay.addWidget(self._sb_width, r, 1); r += 1

        # ── 목표가 + 현재가 비교 라벨 ─────────────────────────
        lay.addWidget(_lbl("목표가 1:"), r, 0, Qt.AlignRight)
        self._dsb_tp1 = _dspinbox(0.01, 9.99, 0.50, 0.05, prefix="$")
        lay.addWidget(self._dsb_tp1, r, 1)
        self._lbl_tp1_cmp = _lbl("", "#555577", 13)
        lay.addWidget(self._lbl_tp1_cmp, r, 2, 1, 2); r += 1

        lay.addWidget(_lbl("목표가 2:"), r, 0, Qt.AlignRight)
        self._dsb_tp2 = _dspinbox(0.01, 9.99, 0.40, 0.05, prefix="$")
        lay.addWidget(self._dsb_tp2, r, 1)
        self._lbl_tp2_cmp = _lbl("", "#555577", 13)
        lay.addWidget(self._lbl_tp2_cmp, r, 2, 1, 2); r += 1

        # 최대 금액
        lay.addWidget(_lbl("최대 투자 금액:"), r, 0, Qt.AlignRight)
        self._sb_budget = _spinbox(10, 9999, 100, "$")
        lay.addWidget(self._sb_budget, r, 1); r += 1

        # ── 수익률 필터 (신규) ────────────────────────────────
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
        lay.addWidget(sep2, r, 0, 1, 4); r += 1

        lay.addWidget(_lbl("최대 수익률 하한:"), r, 0, Qt.AlignRight)
        self._sb_roi_min = _spinbox(100, 9900, 500, "%")
        lay.addWidget(self._sb_roi_min, r, 1)
        lay.addWidget(_lbl("이상 (만기 전액ITM 기준)", "#888", 11), r, 2, 1, 2); r += 1

        lay.addWidget(_lbl("최대 수익률 상한:"), r, 0, Qt.AlignRight)
        self._sb_roi_max = _spinbox(100, 9900, 1200, "%")
        lay.addWidget(self._sb_roi_max, r, 1)
        lay.addWidget(_lbl("이하", "#888", 11), r, 2, 1, 2); r += 1

        roi_note = _lbl("※ ROI = (폭×100 − 진입가×100) ÷ 진입가×100 × 100", "#556677", 11)
        lay.addWidget(roi_note, r, 0, 1, 4); r += 1

        # 드라이런 체크박스
        from PyQt5.QtWidgets import QCheckBox
        self._chk_dry_run = QCheckBox("🧪 드라이런 (테스트 — 실제 주문 안 함)")
        self._chk_dry_run.setStyleSheet(
            "QCheckBox{color:#ffaa44;font-size:14px;border:none;font-weight:bold;}"
            "QCheckBox::indicator{width:16px;height:16px;}"
            "QCheckBox::indicator:checked{background:#3a2a00;border:2px solid #ffaa44;border-radius:3px;}"
            "QCheckBox::indicator:unchecked{background:#0a0a18;border:1px solid #3a3a7a;border-radius:3px;}"
        )
        lay.addWidget(self._chk_dry_run, r, 0, 1, 4); r += 1

        # 저장 상태 라벨
        self._lbl_a_status = _lbl("", "#aaa", 12)
        lay.addWidget(self._lbl_a_status, r, 0, 1, 4); r += 1

        # ── 버튼 행 ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_a_apply = _btn("✔  저장", "#1a2a1a", "#00e676")
        self._btn_a_apply.clicked.connect(self._on_a_apply)
        btn_row.addWidget(self._btn_a_apply)

        self._btn_check_chain = _btn("🔍 체인 확인", "#1a1a2a", "#5dade2")
        self._btn_check_chain.clicked.connect(self._on_check_chain)
        btn_row.addWidget(self._btn_check_chain)
        btn_row.addStretch()
        lay.addLayout(btn_row, r, 0, 1, 4); r += 1

        # ── 체인 확인 출력 창 ─────────────────────────────────
        self._txt_chain_output = QTextEdit()
        self._txt_chain_output.setReadOnly(True)
        self._txt_chain_output.setFixedHeight(160)
        self._txt_chain_output.setStyleSheet(
            "QTextEdit{"
            "background:#06060e;color:#dde0f0;font-size:13px;"
            "font-family:Consolas,monospace;"
            "border:1px solid #2a2a5a;border-radius:4px;padding:6px;"
            "}"
        )
        self._txt_chain_output.setPlaceholderText(
            "🔍 체인 확인 버튼을 누르면 여기에 결과가 표시됩니다.\n"
            "예약주문 버튼 ON 시 자동으로 실행됩니다.")
        lay.addWidget(self._txt_chain_output, r, 0, 1, 4); r += 1

        return gb

    def _update_et_preview(self) -> None:
        """KST 시간 입력 시 ET 변환 미리보기 실시간 갱신."""
        kst_s = self._te_start.time().toString("HH:mm")
        kst_e = self._te_end.time().toString("HH:mm")
        et_s  = _kst_to_et(kst_s)
        et_e  = _kst_to_et(kst_e)
        tz    = "EDT" if _is_edt() else "EST"
        self._lbl_start_et.setText(f"→ {et_s} {tz}")
        self._lbl_end_et.setText(f"→ {et_e} {tz}")

    # ── 섹션 B: 급락 캐치 ────────────────────────────────────────

    def _build_section_b(self) -> QGroupBox:
        gb  = _gb("⚡  급락 캐치 설정", "#ff6b6b")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        r = 0

        lay.addWidget(_lbl("틱 평균 개수 N:"), r, 0, Qt.AlignRight)
        self._sb_tick_n = _spinbox(5, 10, 7, "개")
        lay.addWidget(self._sb_tick_n, r, 1)
        lay.addWidget(_lbl("(5~10개 평균 기준가)", "#888", 11), r, 2, 1, 2); r += 1

        lay.addWidget(_lbl("급락 판단 비율:"), r, 0, Qt.AlignRight)
        self._sb_drop = _spinbox(10, 90, 40, "%")
        lay.addWidget(self._sb_drop, r, 1)
        lay.addWidget(_lbl("이상 급락 시 발동", "#888", 11), r, 2, 1, 2); r += 1

        lay.addWidget(_lbl("절대가 상한:"), r, 0, Qt.AlignRight)
        self._dsb_floor = _dspinbox(0.05, 1.00, 0.20, 0.05, prefix="$")
        lay.addWidget(self._dsb_floor, r, 1); r += 1

        lay.addWidget(_lbl("주문 방식:"), r, 0, Qt.AlignRight)
        mode_w = QWidget(); mode_w.setStyleSheet("background:transparent;")
        mode_row = QHBoxLayout(mode_w)
        mode_row.setContentsMargins(0, 0, 0, 0); mode_row.setSpacing(10)
        self._rb_ask1  = QRadioButton("1호가 위")
        self._rb_fixed = QRadioButton("고정값")
        self._rb_ask1.setChecked(True)
        for rb in (self._rb_ask1, self._rb_fixed):
            rb.setStyleSheet("color:#dde0f0;font-size:15px;border:none;")
        self._mode_grp = QButtonGroup(self)
        self._mode_grp.addButton(self._rb_ask1,  0)
        self._mode_grp.addButton(self._rb_fixed, 1)
        mode_row.addWidget(self._rb_ask1)
        mode_row.addWidget(self._rb_fixed)
        lay.addWidget(mode_w, r, 1, 1, 3); r += 1

        lay.addWidget(_lbl("고정 주문가:"), r, 0, Qt.AlignRight)
        self._dsb_fixed = _dspinbox(0.01, 9.99, 0.15, 0.05, prefix="$")
        lay.addWidget(self._dsb_fixed, r, 1)
        self._rb_ask1.toggled.connect(
            lambda on: self._dsb_fixed.setEnabled(not on))
        self._dsb_fixed.setEnabled(False)
        r += 1

        lay.addWidget(_lbl("정정 대기:"), r, 0, Qt.AlignRight)
        self._sb_wait = _spinbox(1, 60, 2, "초")
        lay.addWidget(self._sb_wait, r, 1)
        lay.addWidget(_lbl("정정 단위:"), r, 2, Qt.AlignRight)
        self._dsb_step = _dspinbox(0.01, 1.00, 0.05, 0.01, prefix="$")
        lay.addWidget(self._dsb_step, r, 3); r += 1

        lay.addWidget(_lbl("최대 정정:"), r, 0, Qt.AlignRight)
        self._sb_max_mod = _spinbox(1, 10, 3, "회")
        lay.addWidget(self._sb_max_mod, r, 1)
        lay.addWidget(_lbl("정정 상한가:"), r, 2, Qt.AlignRight)
        self._dsb_cap = _dspinbox(0.05, 9.99, 0.30, 0.05, prefix="$")
        lay.addWidget(self._dsb_cap, r, 3); r += 1

        lay.addWidget(_lbl("최대 투자 금액:"), r, 0, Qt.AlignRight)
        self._sb_spike_budget = _spinbox(10, 9999, 100, "$")
        lay.addWidget(self._sb_spike_budget, r, 1); r += 1

        self._lbl_b_status = _lbl("", "#aaa", 12)
        lay.addWidget(self._lbl_b_status, r, 0, 1, 4); r += 1

        btn_row = QHBoxLayout()
        self._btn_b_apply = _btn("✔  저장", "#1a2a1a", "#00e676")
        self._btn_b_apply.clicked.connect(self._on_b_apply)
        btn_row.addWidget(self._btn_b_apply)
        btn_row.addStretch()
        lay.addLayout(btn_row, r, 0, 1, 4)

        return gb

    # ── 값 로드 ─────────────────────────────────────────────────

    def _load_values(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        # ET 저장값 → KST 변환해서 표시
        try:
            kst_start = _et_to_kst(sleep_cfg.schedule_start)
            h, m = map(int, kst_start.split(":"))
            self._te_start.setTime(QTime(h, m))
        except Exception:
            pass
        try:
            kst_end = _et_to_kst(sleep_cfg.schedule_end)
            h, m = map(int, kst_end.split(":"))
            self._te_end.setTime(QTime(h, m))
        except Exception:
            pass

        self._update_et_preview()   # ET 미리보기 초기 갱신

        self._sb_expiry.setValue(sleep_cfg.expiry_offset)
        self._dsb_dist_min.setValue(sleep_cfg.strike_dist_min)
        self._dsb_dist_max.setValue(sleep_cfg.strike_dist_max)
        self._sb_width.setValue(sleep_cfg.spread_width)
        self._dsb_tp1.setValue(sleep_cfg.target_price_1)
        self._dsb_tp2.setValue(sleep_cfg.target_price_2)
        self._sb_budget.setValue(sleep_cfg.max_budget)
        self._sb_roi_min.setValue(sleep_cfg.roi_min)
        self._sb_roi_max.setValue(sleep_cfg.roi_max)
        self._chk_dry_run.setChecked(sleep_cfg.dry_run)

        self._sb_tick_n.setValue(sleep_cfg.tick_window)
        self._sb_drop.setValue(sleep_cfg.drop_ratio)
        self._dsb_floor.setValue(sleep_cfg.abs_floor)
        is_fixed = (sleep_cfg.order_mode == "fixed")
        self._rb_fixed.setChecked(is_fixed)
        self._rb_ask1.setChecked(not is_fixed)
        self._dsb_fixed.setValue(sleep_cfg.fixed_price)
        self._dsb_fixed.setEnabled(is_fixed)
        self._sb_wait.setValue(sleep_cfg.modify_wait_sec)
        self._dsb_step.setValue(sleep_cfg.modify_step)
        self._sb_max_mod.setValue(sleep_cfg.modify_max_count)
        self._dsb_cap.setValue(sleep_cfg.modify_price_cap)
        self._sb_spike_budget.setValue(sleep_cfg.spike_budget)

    # ── 저장 ────────────────────────────────────────────────────

    def _on_a_apply(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        # KST 입력 → ET 변환 후 저장
        kst_start = self._te_start.time().toString("HH:mm")
        kst_end   = self._te_end.time().toString("HH:mm")
        et_start  = _kst_to_et(kst_start)
        et_end    = _kst_to_et(kst_end)

        sleep_cfg.set("schedule_start",  et_start)
        sleep_cfg.set("schedule_end",    et_end)
        sleep_cfg.set("expiry_offset",   self._sb_expiry.value())
        sleep_cfg.set("strike_dist_min", self._dsb_dist_min.value())
        sleep_cfg.set("strike_dist_max", self._dsb_dist_max.value())
        sleep_cfg.set("spread_width",    self._sb_width.value())
        sleep_cfg.set("target_price_1",  self._dsb_tp1.value())
        sleep_cfg.set("target_price_2",  self._dsb_tp2.value())
        sleep_cfg.set("max_budget",      self._sb_budget.value())
        sleep_cfg.set("roi_min",         self._sb_roi_min.value())
        sleep_cfg.set("roi_max",         self._sb_roi_max.value())
        sleep_cfg.set("dry_run",         self._chk_dry_run.isChecked())
        sleep_cfg.save()

        tz = "EDT" if _is_edt() else "EST"
        dry_tag = "  🧪 드라이런ON" if sleep_cfg.dry_run else ""
        self._lbl_a_status.setText(
            f"✅ 저장됨  KST {kst_start}~{kst_end}"
            f"  ({tz} {et_start}~{et_end})"
            f"  D+{sleep_cfg.expiry_offset}{dry_tag}")
        print(f"[SleepUI] 섹션 A 저장  KST {kst_start}~{kst_end} → {tz} {et_start}~{et_end}")

    def _on_b_apply(self) -> None:
        from Sleep_Order.sleep_order_config  import sleep_cfg
        from Sleep_Order.sleep_order_spike   import SleepSpikeWatcher

        sleep_cfg.set("tick_window",      self._sb_tick_n.value())
        sleep_cfg.set("drop_ratio",       self._sb_drop.value())
        sleep_cfg.set("abs_floor",        self._dsb_floor.value())
        sleep_cfg.set("order_mode",
                      "fixed" if self._rb_fixed.isChecked() else "ask+1")
        sleep_cfg.set("fixed_price",      self._dsb_fixed.value())
        sleep_cfg.set("modify_wait_sec",  self._sb_wait.value())
        sleep_cfg.set("modify_step",      self._dsb_step.value())
        sleep_cfg.set("modify_max_count", self._sb_max_mod.value())
        sleep_cfg.set("modify_price_cap", self._dsb_cap.value())
        sleep_cfg.set("spike_budget",     self._sb_spike_budget.value())
        sleep_cfg.save()

        SleepSpikeWatcher.get().reconfigure_all()

        self._lbl_b_status.setText(
            f"✅ 저장됨  N={sleep_cfg.tick_window}  "
            f"급락{sleep_cfg.drop_ratio}%  상한${sleep_cfg.abs_floor}")
        print("[SleepUI] 섹션 B 저장 완료")

    # ── ref 탐색 (버그 수정: findChildren(QWidget)) ──────────────

    def _get_ref(self):
        """
        ComboTab ref 탐색.
        1) SleepOrderWatcher._ref
        2) QApplication 전체 위젯에서 _sleep_get_chain 속성 탐색
           → findChildren(QWidget) 으로 모든 자식 탐색 (type(w) 버그 수정)
        """
        ref = None
        try:
            from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
            ref = SleepOrderWatcher.get()._ref
        except Exception:
            pass

        if ref is None:
            try:
                from PyQt5.QtWidgets import QApplication, QWidget as _QW
                for w in QApplication.topLevelWidgets():
                    if hasattr(w, '_sleep_get_chain'):
                        ref = w
                        break
                    for child in w.findChildren(_QW):
                        if hasattr(child, '_sleep_get_chain'):
                            ref = child
                            break
                    if ref:
                        break
            except Exception:
                pass
        return ref

    def _on_check_chain(self) -> None:
        """🔍 체인 확인 — 출력 창에 상세 결과 표시."""
        from Sleep_Order.sleep_order_config import sleep_cfg

        ref = self._get_ref()

        if ref is None:
            self._set_chain_output(
                "⚠ 복합 전략 탭 미연결\n"
                "예약주문 버튼을 ON 하면 자동으로 연결됩니다.",
                color="#ffaa44", border="#5a3a00")
            self._lbl_tp1_cmp.setText("─")
            self._lbl_tp1_cmp.setStyleSheet("color:#555577;font-size:13px;border:none;")
            self._lbl_tp2_cmp.setText("─")
            self._lbl_tp2_cmp.setStyleSheet("color:#555577;font-size:13px;border:none;")
            return

        put_strikes  = getattr(ref, '_put_strikes', [])
        chain_put    = getattr(ref, '_chain_put', {})
        und_price    = getattr(ref, '_und_price', 0.0) or 0.0
        cur_expiry   = getattr(ref, '_current_expiry', '') or ''
        valid_prices = [v for v in chain_put.values() if v and v > 0]

        if not put_strikes:
            self._set_chain_output(
                "❌ 풋 체인 없음 — 콜-풋탭 동기화 필요",
                color="#ff4444", border="#5a1a1a")
            return

        if len(valid_prices) < 3:
            self._set_chain_output(
                f"⚠ 유효 가격 {len(valid_prices)}개 — 동기화 대기",
                color="#ffaa44", border="#5a3a00")
            return

        if und_price <= 0:
            self._set_chain_output(
                f"⚠ 행사가 {len(put_strikes)}개 수신 / 지수 가격 없음",
                color="#ffaa44", border="#5a3a00")
            return

        # ── 정상: 범위내 스프레드 상세 출력 ────────────────────
        dmin    = sleep_cfg.strike_dist_min / 100.0
        dmax    = sleep_cfg.strike_dist_max / 100.0
        tp1     = sleep_cfg.target_price_1
        tp2     = sleep_cfg.target_price_2
        roi_min = sleep_cfg.roi_min
        roi_max = sleep_cfg.roi_max
        sw      = sleep_cfg.spread_width

        in_range_items = [
            (s, chain_put.get(s, 0))
            for s in sorted(put_strikes, reverse=True)
            if dmin <= abs(und_price - s) / und_price <= dmax
        ]

        lines = []
        lines.append(f"✅ 체인 정상  |  만기 {cur_expiry}  |  지수 {und_price:,.0f}")
        lines.append(
            f"행사가 {len(put_strikes)}개  /  유효가격 {len(valid_prices)}개  "
            f"/  범위내 {len(in_range_items)}개"
        )
        lines.append(f"거리 범위: {sleep_cfg.strike_dist_min}% ~ {sleep_cfg.strike_dist_max}%"
                     f"  |  ROI 허용: {roi_min}% ~ {roi_max}%")
        lines.append("─" * 64)
        lines.append(f"{'행사가':>8}  {'현재가':>7}  {'ROI':>7}  {'목표1':>6}  {'목표2':>6}  상태")
        lines.append("─" * 64)

        best_net = None
        for strike, net in in_range_items:
            if net is None or net <= 0:
                roi_str = "   ─   "
                status  = "가격없음"
            else:
                # ROI 계산
                max_profit = (sw - net) * 100
                if max_profit > 0:
                    roi_pct = (max_profit / (net * 100)) * 100
                    roi_str = f"{roi_pct:>6.0f}%"
                    roi_ok  = roi_min <= roi_pct <= roi_max
                else:
                    roi_pct = 0
                    roi_str = " N/A  "
                    roi_ok  = False

                net_r = round(net * 20) / 20
                if not roi_ok:
                    status = f"🚫 ROI범위외"
                elif net_r <= tp2:
                    status = f"✅ ≤목표2"
                elif net_r <= tp1:
                    status = f"🟡 ≤목표1"
                else:
                    status = f"⏳ 대기"

                if best_net is None and roi_ok:
                    best_net = net

            net_str = f"${net:.2f}" if (net and net > 0) else "  ─   "
            lines.append(
                f"{strike:>8.0f}  {net_str:>7}  {roi_str:>7}  "
                f"${tp1:>5.2f}  ${tp2:>5.2f}  {status}"
            )

        lines.append("─" * 64)

        self._set_chain_output("\n".join(lines), color="#00ff88", border="#1a5a2a")
        self._update_tp_compare(best_net, tp1, tp2)

    def _set_chain_output(self, text: str, color: str = "#dde0f0",
                          border: str = "#2a2a5a") -> None:
        """체인 출력 창 텍스트 + 스타일 한번에 설정."""
        self._txt_chain_output.setPlainText(text)
        self._txt_chain_output.setStyleSheet(
            f"QTextEdit{{background:#06060e;color:{color};font-size:13px;"
            f"font-family:Consolas,monospace;"
            f"border:1px solid {border};border-radius:4px;padding:6px;}}"
        )

    def _update_tp_compare(self, best_net, tp1: float, tp2: float) -> None:
        """목표가 옆 현재가 비교 라벨 업데이트."""
        if best_net is None or best_net <= 0:
            for lbl in (self._lbl_tp1_cmp, self._lbl_tp2_cmp):
                lbl.setText("─ 가격 없음")
                lbl.setStyleSheet("color:#555577;font-size:13px;border:none;")
            return

        net_r = round(best_net * 20) / 20

        if net_r <= tp1:
            self._lbl_tp1_cmp.setText(f"✅ 현재 ${best_net:.2f} ≤ ${tp1:.2f}")
            self._lbl_tp1_cmp.setStyleSheet(
                "color:#00ff88;font-size:13px;font-weight:bold;border:none;")
        else:
            diff = best_net - tp1
            self._lbl_tp1_cmp.setText(f"⏳ 현재 ${best_net:.2f}  (차이 ${diff:+.2f})")
            self._lbl_tp1_cmp.setStyleSheet(
                "color:#ffaa44;font-size:13px;border:none;")

        if net_r <= tp2:
            self._lbl_tp2_cmp.setText(f"✅ 현재 ${best_net:.2f} ≤ ${tp2:.2f}")
            self._lbl_tp2_cmp.setStyleSheet(
                "color:#00ff88;font-size:13px;font-weight:bold;border:none;")
        else:
            diff = best_net - tp2
            self._lbl_tp2_cmp.setText(f"⏳ 현재 ${best_net:.2f}  (차이 ${diff:+.2f})")
            self._lbl_tp2_cmp.setStyleSheet(
                "color:#ffaa44;font-size:13px;border:none;")


# ══════════════════════════════════════════════════════════════
# SleepOrderButton — 복합 전략 탭 우측 상단 버튼
# ══════════════════════════════════════════════════════════════

class SleepOrderButton(QWidget):
    """
    SyntheticStatusPanel._build_ui() 의 mode_row 우측에 추가.
    예약주문 ON 시 설정 탭 체인 확인 자동 실행.
    """

    def __init__(self, ref: object, parent=None):
        super().__init__(parent)
        self._ref = ref
        self.setStyleSheet("background:transparent;")
        self._build()
        self._connect_watcher()

    def set_ref(self, ref: object) -> None:
        self._ref = ref
        print(f"[SleepOrderButton] ref 주입 완료: {type(ref).__name__}")

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(6)

        self._lbl_onoff = QLabel("OFF")
        self._lbl_onoff.setFixedWidth(36)
        self._lbl_onoff.setAlignment(Qt.AlignCenter)
        self._lbl_onoff.setStyleSheet(
            "color:#ff4444;font-size:11px;font-weight:bold;"
            "background:#2a0a0a;border:1px solid #6a1a1a;"
            "border-radius:3px;padding:1px 4px;")
        lay.addWidget(self._lbl_onoff)

        self._lbl_status = QLabel("⏸ 대기")
        self._lbl_status.setStyleSheet("color:#555577;font-size:12px;border:none;")
        lay.addWidget(self._lbl_status)

        self._btn = QPushButton("🌙 예약 주문")
        self._btn.setFixedHeight(26)
        self._btn.setStyleSheet(
            "QPushButton{background:#1a1a0a;color:#ffd700;font-size:13px;"
            "font-weight:bold;border:1px solid #5a5a1a;"
            "border-radius:4px;padding:2px 12px;}"
            "QPushButton:hover{background:#2a2a0a;color:#ffee44;}"
            "QPushButton:checked{background:#0a2a0a;color:#00ff88;"
            "border:2px solid #00ff44;}"
            "QPushButton:pressed{background:#080808;}"
        )
        self._btn.setCheckable(True)
        self._btn.clicked.connect(self._on_click)
        lay.addWidget(self._btn)

    def _set_on(self) -> None:
        self._lbl_onoff.setText("ON")
        self._lbl_onoff.setStyleSheet(
            "color:#00ff88;font-size:11px;font-weight:bold;"
            "background:#0a2a0a;border:1px solid #00ff44;"
            "border-radius:3px;padding:1px 4px;")
        self._btn.setChecked(True)

    def _set_off(self) -> None:
        self._lbl_onoff.setText("OFF")
        self._lbl_onoff.setStyleSheet(
            "color:#ff4444;font-size:11px;font-weight:bold;"
            "background:#2a0a0a;border:1px solid #6a1a1a;"
            "border-radius:3px;padding:1px 4px;")
        self._btn.setChecked(False)

    def _connect_watcher(self) -> None:
        try:
            from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
            SleepOrderWatcher.get().status_changed.connect(self._on_status_changed)
        except Exception as e:
            print(f"[SleepOrderButton] watcher 연결 실패: {e}")

    def _on_click(self) -> None:
        try:
            if self._ref is None:
                from PyQt5.QtWidgets import QWidget as _QW
                w = self
                for _ in range(8):
                    w = w.parent()
                    if w is None:
                        break
                    if hasattr(w, '_sleep_get_chain'):
                        self._ref = w
                        print(f"[SleepBtn] ref 자동 탐색 성공: {type(w).__name__}")
                        break

            from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
            started = SleepOrderWatcher.get().toggle(self._ref)

            if started:
                self._set_on()
                self._btn.setText("🟢 ON  예약감시중")
                self._lbl_status.setText("")
                self._lbl_status.setStyleSheet("color:#00ff88;font-size:12px;border:none;")
                # ── 예약주문 ON → 설정 탭 체인 확인 자동 실행 ──
                self._auto_check_chain()
            else:
                self._set_off()
                self._btn.setText("🌙 예약 주문")
                self._lbl_status.setText("⏸ 대기")
                self._lbl_status.setStyleSheet("color:#555577;font-size:12px;border:none;")
        except Exception as e:
            print(f"[SleepOrderButton] toggle 실패: {e}")

    def _auto_check_chain(self) -> None:
        """
        예약주문 ON 시 설정 탭 SleepOrderRightPanel._on_check_chain() 자동 호출.
        QApplication 전체에서 SleepOrderRightPanel 인스턴스 탐색.
        """
        try:
            from PyQt5.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                panels = w.findChildren(SleepOrderRightPanel)
                if panels:
                    panels[0]._on_check_chain()
                    print("[SleepBtn] 설정 탭 체인 확인 자동 실행")
                    return
        except Exception as e:
            print(f"[SleepBtn] 체인 확인 자동 실행 실패: {e}")

    def _on_status_changed(self, text: str) -> None:
        self._lbl_status.setText(text)
        if "주문완료" in text:
            self._set_on()
            self._btn.setText("✅ ON  주문완료")
            self._lbl_status.setStyleSheet("color:#00e676;font-size:12px;border:none;")
        elif "감시중" in text:
            self._set_on()
            self._btn.setText("🟢 ON  예약감시중")
            self._lbl_status.setStyleSheet("color:#00ff88;font-size:12px;border:none;")
        else:
            self._set_off()
            self._btn.setText("🌙 예약 주문")
            self._lbl_status.setStyleSheet("color:#555577;font-size:12px;border:none;")


# ══════════════════════════════════════════════════════════════
# Main_config.py 패치 헬퍼 (레거시 — 사용 안 함)
# ══════════════════════════════════════════════════════════════

def patch_main_config_layout(config_tab_instance) -> None:
    """현재는 ConfigTab._build() 자체를 QHBoxLayout 2단으로 직접 구현. 레거시 유지."""
    from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy

    cfg = config_tab_instance
    root_layout = cfg.layout()

    if root_layout is None or root_layout.count() == 0:
        print("[SleepUI] patch: root layout 없음")
        return

    item = root_layout.takeAt(0)
    if item is None:
        print("[SleepUI] patch: item 없음")
        return
    old_scroll = item.widget()
    if old_scroll is None:
        print("[SleepUI] patch: scroll 위젯 없음")
        return

    container = QWidget()
    container.setStyleSheet("background:#0a0a18;")
    hlay = QHBoxLayout(container)
    hlay.setContentsMargins(0, 0, 0, 0)
    hlay.setSpacing(0)

    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setFixedWidth(1)
    sep.setStyleSheet("background:#2a2a5a;border:none;")

    right_panel = SleepOrderRightPanel()
    right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    hlay.addWidget(old_scroll,  stretch=1)
    hlay.addWidget(sep)
    hlay.addWidget(right_panel, stretch=1)

    root_layout.addWidget(container)
    cfg._sleep_right_panel = right_panel
    print("[SleepUI] Main_config 2단 레이아웃 패치 완료")