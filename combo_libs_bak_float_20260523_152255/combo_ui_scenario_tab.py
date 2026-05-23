"""combo_ui_scenario_tab.py — 📈 시나리오 탭 위젯  (ScenarioTab)

[FIX-SCENARIO] Mode B + C안
  · 슬라이더 3개 (지수 이동 / 남은 시간 / IV 변화)
  · Δ+Γ 보정, Θ 세타 손실, ν 베가 효과 종합 계산
  · 스프레드 상한 처리 (max_spread = 행사가 차이)
  · 시나리오 매트릭스 (지수 이동 × 만기까지 남은 시간)
  · update_scenario_greeks(legs, entry) 외부 API

[FIX-BS] BS 계산 엔진은 combo_ui_scenario_bs.py (_ScenarioBSMixin) 에 분리.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem,
    QSizePolicy, QGridLayout, QSlider,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from combo_ui_panel_constants import _f, _TBL_STYLE
from combo_ui_scenario_bs import _ScenarioBSMixin
from combo_ui_scenario_logic import _ScenarioLogicMixin


class ScenarioTab(_ScenarioLogicMixin, _ScenarioBSMixin, QWidget):
    """
    📈 시나리오 탭 — Mode B + C안.

    슬라이더 3개 (지수 이동 / 경과 시간 / IV 변화) 로 조건을 설정하면
    Δ+Γ 보정, Θ 세타 손실, ν 베가 효과를 종합한 예상 수익률과
    시나리오 매트릭스(지수 이동 × 경과 시간)를 실시간 갱신.

    외부 연동:
        set_greeks(legs, entry, und_price) — 레그 Greeks 주입
    """

    # 시나리오 매트릭스 행/열 고정
    _MOVES = [-50, -40, -30, -20, -15, -10, -5, 0, 5, 10, 15, 20, 30, 40, 50]
    _TIMES = [4.0, 3.0, 2.0, 1.0, 0.5]   # 만기까지 남은 시간 (많은→적은)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#07070f;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Greeks 초기값 (데이터 수신 전)
        self._entry      = 0.0
        self._pos_delta  = 0.0
        self._pos_gamma  = 0.0
        self._pos_theta  = 0.0   # 일 기준
        self._pos_vega   = 0.0
        self._max_val    = 5.0   # 스프레드 상한 (행사가 차이)
        self._expiry_str = ""    # 만기일 (YYYYMMDD)
        self._hours_left = 4.0   # 만기까지 남은 시간 기본값 (h)

        # [FIX-BS] Black-Scholes 계산용 원본 데이터
        self._legs_raw  = []    # 레그 원본 리스트
        self._und_price = 0.0   # 현재 지수 가격 (BS 기준가)

        self._build_ui()

    # ══════════════════════════════════════════════════════════
    # UI 구성
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── 포지션 요약 행 ────────────────────────────────────
        info_row = QHBoxLayout()
        self._lbl_entry  = self._mk_info("DEBIT: ―")
        self._lbl_greeks = self._mk_info("δ ―  γ ―  θ ―  ν ―")
        self._lbl_cap    = self._mk_info("상한: ―")
        self._lbl_und    = self._mk_info("지수: ―")
        info_row.addWidget(self._lbl_entry)
        info_row.addStretch()
        info_row.addWidget(self._lbl_und)
        info_row.addStretch()
        info_row.addWidget(self._lbl_greeks)
        info_row.addStretch()
        info_row.addWidget(self._lbl_cap)
        root.addLayout(info_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep)

        # ── 슬라이더 3개 ──────────────────────────────────────
        root.addLayout(self._mk_slider_row(
            "지수 이동(P)", -30, 30, 5, 1, "sl_move", "v_move",
            lambda v: (f"+{v}P" if v >= 0 else f"{v}P")))
        root.addLayout(self._mk_slider_row(
            "남은 시간(h)", 0, 16, 8, 1, "sl_time", "v_time",
            lambda v: f"{v/2:.1f}h"))
        root.addLayout(self._mk_slider_row(
            "IV 변화(%)", -10, 20, 4, 1, "sl_iv", "v_iv",
            lambda v: (f"+{v}%" if v >= 0 else f"{v}%")))

        # 만기까지 남은 시간 자동 계산 표시
        self._lbl_time_auto = QLabel("⏱ ET 기준 자동 계산 중...")
        self._lbl_time_auto.setStyleSheet(
            "color:#445566;font-size:10px;border:none;")
        root.addWidget(self._lbl_time_auto)

        # 자동 갱신 타이머 (1분마다)
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(60_000)
        self._time_timer.timeout.connect(self._auto_update_time)
        self._time_timer.start()
        self._auto_update_time()   # 즉시 1회 실행

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep2)

        # ── 결과 카드 4개 ──────────────────────────────────────
        card_row = QHBoxLayout(); card_row.setSpacing(4)
        self._card_dg  = self._mk_card("Δ+Γ 수익")
        self._card_th  = self._mk_card("Θ 손실")
        self._card_vg  = self._mk_card("ν 효과")
        self._card_pct = self._mk_card("예상 수익률", big=True)
        for c in (self._card_dg, self._card_th, self._card_vg, self._card_pct):
            card_row.addWidget(c[0])
        root.addLayout(card_row)

        # ── 상세 분해 ─────────────────────────────────────────
        detail = QGridLayout(); detail.setSpacing(2)

        def _kv(row, col_k, col_v, k):
            lk = QLabel(k); lk.setStyleSheet("color:#555;font-size:10px;border:none;")
            lv = QLabel("―"); lv.setStyleSheet("color:#aaa;font-size:10px;border:none;")
            lv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            detail.addWidget(lk, row, col_k)
            detail.addWidget(lv, row, col_v)
            return lv

        self._lv_delta  = _kv(0, 0, 1, "Δ×ΔS")
        self._lv_gamma  = _kv(0, 2, 3, "½Γ×ΔS²")
        self._lv_theta  = _kv(1, 0, 1, "Θ×Δt")
        self._lv_vega   = _kv(1, 2, 3, "ν×ΔIV")
        self._lv_price  = _kv(2, 0, 1, "예상가")
        self._lv_return = _kv(2, 2, 3, "수익률")

        self._lbl_cap_warn = QLabel("")
        self._lbl_cap_warn.setStyleSheet(
            "color:#ffaa44;font-size:10px;border:none;")
        detail.addWidget(self._lbl_cap_warn, 3, 0, 1, 4)
        root.addLayout(detail)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
        sep3.setFixedHeight(1)
        sep3.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep3)

        # ── 시나리오 매트릭스 ─────────────────────────────────
        lbl_mat = QLabel("시나리오 매트릭스 (지수 이동 × 만기까지 남은 시간)")
        lbl_mat.setStyleSheet("color:#4466aa;font-size:10px;border:none;")
        root.addWidget(lbl_mat)

        self._matrix_tbl = QTableWidget(len(self._MOVES), len(self._TIMES))
        self._matrix_tbl.setHorizontalHeaderLabels(
            [f"{t:.1f}h 남음" for t in self._TIMES])
        self._matrix_tbl.setVerticalHeaderLabels(
            [f"{m:+d}P" for m in self._MOVES])
        self._matrix_tbl.setFont(_f(10))
        self._matrix_tbl.horizontalHeader().setFont(_f(9, bold=True))
        self._matrix_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._matrix_tbl.verticalHeader().setFont(_f(9))
        self._matrix_tbl.verticalHeader().setDefaultSectionSize(20)
        self._matrix_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._matrix_tbl.setFixedHeight(136)
        self._matrix_tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._matrix_tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._matrix_tbl.setStyleSheet(_TBL_STYLE)
        root.addWidget(self._matrix_tbl)

        lbl_note = QLabel(
            "* IV 변화는 슬라이더 값 고정 적용  "
            "· 스프레드 상한 초과 시 MAX 표시  "
            "· 남은 시간 0h = 만기 직전")
        lbl_note.setStyleSheet("color:#333355;font-size:9px;border:none;")
        root.addWidget(lbl_note)

        self._refresh()

    # ══════════════════════════════════════════════════════════
    # 슬라이더 / 카드 헬퍼
    # ══════════════════════════════════════════════════════════

    def _mk_info(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#556677;font-size:10px;border:none;")
        return lbl

    def _mk_slider_row(self, label, mn, mx, default, step,
                       sl_attr, val_attr, fmt_fn) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)
        lk = QLabel(label)
        lk.setFixedWidth(80)
        lk.setStyleSheet("color:#888;font-size:10px;border:none;")
        sl = QSlider(Qt.Horizontal)
        sl.setRange(mn, mx); sl.setValue(default); sl.setSingleStep(step)
        sl.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#1a1a3a;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#4488ff;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#2255aa;border-radius:2px;}")
        lv = QLabel(fmt_fn(default))
        lv.setFixedWidth(46)
        lv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lv.setStyleSheet("color:#ffff44;font-size:11px;font-weight:bold;border:none;")
        setattr(self, sl_attr, sl)
        setattr(self, val_attr, lv)
        sl.valueChanged.connect(lambda v, f=fmt_fn, l=lv: (
            l.setText(f(v)), self._refresh()))
        row.addWidget(lk); row.addWidget(sl); row.addWidget(lv)
        return row

    def _mk_card(self, title: str, big: bool = False):
        w = QWidget()
        w.setStyleSheet(
            "background:#0a0a1e;border:1px solid #1a1a3a;border-radius:4px;")
        v = QVBoxLayout(w); v.setContentsMargins(6, 4, 6, 4); v.setSpacing(1)
        lt = QLabel(title)
        lt.setAlignment(Qt.AlignCenter)
        lt.setStyleSheet("color:#446688;font-size:9px;border:none;")
        lv = QLabel("―")
        lv.setAlignment(Qt.AlignCenter)
        sz = 16 if big else 13
        lv.setFont(_f(sz, bold=True))
        lv.setStyleSheet("color:#888899;border:none;")
        v.addWidget(lt); v.addWidget(lv)
        return w, lv

    # ══════════════════════════════════════════════════════════
    # 외부 API

    # (데이터·갱신 로직은 _ScenarioLogicMixin 에 위임)
