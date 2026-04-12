"""
greeks_replay.py — Greeks 리플레이 패널
════════════════════════════════════════════════════════════════
저장된 SQLite 데이터를 날짜·시간 범위 지정 후 슬라이더로 재생.
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider,
    QLineEdit, QTableWidget, QGroupBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer

from greeks_db     import load_snapshots, available_days, load_timestamps
from greeks_render import (
    init_table, init_row, render_rows,
    NCOLS, COL_STRIKE,
)

REPLAY_SPEEDS = {"x1": 1000, "x5": 200, "x10": 100}


class ReplayPanel(QWidget):
    """
    날짜 선택 → 시간범위 입력 → ▶/⏸ + 슬라이더로 Greeks 재생.
    재생 중에는 테이블이 저장된 스냅샷 기준으로 업데이트됨.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshots: list  = []   # 전체 타임스탬프 목록
        self._frames:    dict  = {}   # ts → {(row,side): cell_data}
        self._ts_list:   list  = []   # 필터된 타임스탬프 순서
        self._cur_idx:   int   = 0
        self._strikes:   list  = []
        self._atm:       float = 0.0
        self._prev:      dict  = {}
        self._playing    = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

        self._build()

    # ─────────────────────────────────────────────────────────
    def _build(self):
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(4)

        # ── 컨트롤 바 ─────────────────────────────────────────
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("날짜:"))
        self.cmb_day = QComboBox()
        self.cmb_day.setMinimumWidth(100)
        self.cmb_day.currentTextChanged.connect(self._on_day_changed)
        ctrl.addWidget(self.cmb_day)

        ctrl.addWidget(QLabel("From:"))
        self.edit_from = QLineEdit("14:00")
        self.edit_from.setFixedWidth(52)
        ctrl.addWidget(self.edit_from)

        ctrl.addWidget(QLabel("To:"))
        self.edit_to = QLineEdit("15:05")
        self.edit_to.setFixedWidth(52)
        ctrl.addWidget(self.edit_to)

        self.btn_load = QPushButton("📂 불러오기")
        self.btn_load.clicked.connect(self._load)
        ctrl.addWidget(self.btn_load)

        ctrl.addWidget(QLabel("  속도:"))
        self.cmb_speed = QComboBox()
        for k in REPLAY_SPEEDS:
            self.cmb_speed.addItem(k)
        self.cmb_speed.currentTextChanged.connect(self._on_speed)
        ctrl.addWidget(self.cmb_speed)

        self.btn_play = QPushButton("▶ 재생")
        self.btn_play.setStyleSheet(
            "background:#1a5a1a;font-weight:bold;padding:4px 12px;")
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹ 정지")
        self.btn_stop.clicked.connect(self._stop)
        ctrl.addWidget(self.btn_stop)

        self.lbl_ts = QLabel("―")
        self.lbl_ts.setStyleSheet(
            "color:#ffd700;font-weight:bold;padding:0 8px;border:none;")
        ctrl.addWidget(self.lbl_ts)

        ctrl.addStretch()
        vlay.addLayout(ctrl)

        # ── 슬라이더 ─────────────────────────────────────────
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        vlay.addWidget(self.slider)

        # ── 테이블 ────────────────────────────────────────────
        self.tbl = QTableWidget(0, NCOLS)
        init_table(self.tbl)
        self.tbl.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        vlay.addWidget(self.tbl)

        # 날짜 목록 채우기
        self._refresh_days()

    # ─────────────────────────────────────────────────────────
    def _refresh_days(self):
        self.cmb_day.clear()
        for d in reversed(available_days()):   # 최신 날짜 먼저
            self.cmb_day.addItem(d)

    def _on_day_changed(self, day: str):
        self.edit_from.setText("14:00")
        self.edit_to.setText("15:05")

    def _on_speed(self, key: str):
        if self._playing:
            self._timer.setInterval(REPLAY_SPEEDS.get(key, 1000))

    # ─────────────────────────────────────────────────────────
    # 데이터 로드
    # ─────────────────────────────────────────────────────────
    def _load(self):
        self._stop()
        day  = self.cmb_day.currentText()
        t_fr = self.edit_from.text().strip()
        t_to = self.edit_to.text().strip()
        rows = load_snapshots(day, t_fr, t_to)
        if not rows:
            self.lbl_ts.setText("데이터 없음")
            return

        # 타임스탬프 순서 구성
        ts_set = dict.fromkeys(r["ts"] for r in rows)   # 순서 유지
        self._ts_list = list(ts_set.keys())

        # 프레임별 cell_data 구성
        strikes_set = sorted({r["strike"] for r in rows})
        self._strikes = strikes_set

        # ATM 추정: 첫 und_price 기준
        und = next((r["und_price"] for r in rows if r["und_price"]), 0)
        if und and strikes_set:
            self._atm = min(strikes_set, key=lambda s: abs(s - und))

        self._frames = {}
        for r in rows:
            ts   = r["ts"]
            st   = r["strike"]
            side = r["side"]
            row  = strikes_set.index(st)
            self._frames.setdefault(ts, {})[(row, side)] = {
                "delta": r["delta"] or 0.0,
                "gamma": r["gamma"] or 0.0,
                "iv":    r["iv"]    or 0.0,
                "vanna": r["vanna"] or 0.0,
            }

        # 테이블 초기화
        self.tbl.setRowCount(len(strikes_set))
        for i, st in enumerate(strikes_set):
            init_row(self.tbl, i, st, self._atm)

        self.slider.setMaximum(max(0, len(self._ts_list) - 1))
        self.slider.setValue(0)
        self._cur_idx = 0
        self._prev    = {}
        self._render(0)

    # ─────────────────────────────────────────────────────────
    # 재생 제어
    # ─────────────────────────────────────────────────────────
    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._timer.stop()
            self.btn_play.setText("▶ 재생")
        else:
            if not self._ts_list:
                return
            speed = REPLAY_SPEEDS.get(self.cmb_speed.currentText(), 1000)
            self._playing = True
            self._timer.start(speed)
            self.btn_play.setText("⏸ 일시정지")

    def _stop(self):
        self._playing = False
        self._timer.stop()
        self.btn_play.setText("▶ 재생")
        self._cur_idx = 0
        if self._ts_list:
            self.slider.setValue(0)

    def _step(self):
        if self._cur_idx >= len(self._ts_list) - 1:
            self._stop()
            return
        self._cur_idx += 1
        self.slider.blockSignals(True)
        self.slider.setValue(self._cur_idx)
        self.slider.blockSignals(False)
        self._render(self._cur_idx)

    def _on_slider(self, val: int):
        self._cur_idx = val
        self._render(val)

    # ─────────────────────────────────────────────────────────
    # 렌더
    # ─────────────────────────────────────────────────────────
    def _render(self, idx: int):
        if not self._ts_list or idx >= len(self._ts_list):
            return
        ts       = self._ts_list[idx]
        cell_d   = self._frames.get(ts, {})
        self.lbl_ts.setText(ts)
        render_rows(self.tbl, self._strikes, self._atm, cell_d, self._prev)

    # ─────────────────────────────────────────────────────────
    # 외부에서 호출 (탭 전환 시 날짜 목록 갱신)
    # ─────────────────────────────────────────────────────────
    def refresh(self):
        self._refresh_days()
