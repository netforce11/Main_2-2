"""
greeks_replay.py — Greeks 리플레이 패널
════════════════════════════════════════════════════════════════
저장된 SQLite 데이터를 날짜·시간 범위 지정 후 슬라이더로 재생.

v6.6 변경:
  - ★ greeks_YYYYMMDD.db + chain_YYYYMMDD.db 동시 로드 (머지)
  - ★ 가격 컬럼 추가: Bid / Ask / Mid / Theo / Mis%
  - available_days_merged() 로 날짜 목록 통합
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider,
    QLineEdit, QTableWidget, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer

from greeks_db import (
    load_merged_snapshots, available_days_merged, load_timestamps,
)
from greeks_render import (
    init_table_replay, init_row_replay, render_rows_replay,
    REPLAY_NCOLS, RCOL_STRIKE,
)

REPLAY_SPEEDS = {"x1": 1000, "x5": 200, "x10": 100}


class ReplayPanel(QWidget):
    """
    날짜 선택 -> 시간범위 입력 -> 재생/정지 + 슬라이더로 Greeks+가격 재생.
    greeks_YYYYMMDD.db (Greeks/Vanna) +
    chain_YYYYMMDD.db  (Bid/Ask/Mid/Theo/Mispct) 머지 표시.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshots: list = []
        self._frames:    dict = {}
        self._ts_list:   list = []
        self._cur_idx:   int  = 0
        self._strikes:   list = []
        self._atm:       float = 0.0
        self._prev:      dict = {}
        self._playing         = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

        self._build()

    # ----------------------------------------------------------
    def _build(self):
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(4)

        # -- 컨트롤 바 -----------------------------------------
        ctrl = QHBoxLayout()

        ctrl.addWidget(QLabel("날짜:"))
        self.cmb_day = QComboBox()
        self.cmb_day.setMinimumWidth(100)
        self.cmb_day.currentTextChanged.connect(self._on_day_changed)
        ctrl.addWidget(self.cmb_day)

        for attr, placeholder, width in [
            ("edit_from", "HH:MM (선택)", 80),
            ("edit_to",   "HH:MM (선택)", 80),
        ]:
            lbl = QLabel("From:" if "from" in attr else "To:")
            lbl.setStyleSheet("color:#888;font-size:10px;border:none;")
            ctrl.addWidget(lbl)
            edit = QLineEdit("")
            edit.setPlaceholderText(placeholder)
            edit.setFixedWidth(width)
            edit.setToolTip("비워두면 해당 날짜 전체 로드")
            edit.setStyleSheet(
                "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;"
                "font-size:11px;padding:1px 3px;")
            ctrl.addWidget(edit)
            setattr(self, attr, edit)

        self.btn_load = QPushButton("불러오기")
        self.btn_load.clicked.connect(self._load)
        ctrl.addWidget(self.btn_load)

        ctrl.addWidget(QLabel("  속도:"))
        self.cmb_speed = QComboBox()
        for k in REPLAY_SPEEDS:
            self.cmb_speed.addItem(k)
        self.cmb_speed.currentTextChanged.connect(self._on_speed)
        ctrl.addWidget(self.cmb_speed)

        self.btn_play = QPushButton("재생")
        self.btn_play.setStyleSheet(
            "background:#1a5a1a;font-weight:bold;padding:4px 12px;")
        self.btn_play.clicked.connect(self._toggle_play)
        ctrl.addWidget(self.btn_play)

        self.btn_stop = QPushButton("정지")
        self.btn_stop.clicked.connect(self._stop)
        ctrl.addWidget(self.btn_stop)

        self.lbl_ts = QLabel("-")
        self.lbl_ts.setStyleSheet(
            "color:#ffd700;font-weight:bold;padding:0 8px;border:none;")
        ctrl.addWidget(self.lbl_ts)

        ctrl.addStretch()
        vlay.addLayout(ctrl)

        # -- 슬라이더 ------------------------------------------
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        vlay.addWidget(self.slider)

        # -- 테이블 (확장 컬럼) --------------------------------
        self.tbl = QTableWidget(0, REPLAY_NCOLS)
        init_table_replay(self.tbl)
        self.tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vlay.addWidget(self.tbl)

        self._refresh_days()

    # ----------------------------------------------------------
    def _refresh_days(self):
        self.cmb_day.clear()
        for d in reversed(available_days_merged()):
            self.cmb_day.addItem(d)

    def _on_day_changed(self, day: str):
        self.edit_from.clear()
        self.edit_to.clear()

    def _on_speed(self, key: str):
        if self._playing:
            self._timer.setInterval(REPLAY_SPEEDS.get(key, 1000))

    # ----------------------------------------------------------
    # 데이터 로드
    # ----------------------------------------------------------
    def _load(self):
        self._stop()
        day  = self.cmb_day.currentText()
        t_fr = self.edit_from.text().strip()
        t_to = self.edit_to.text().strip()

        if not day:
            self.lbl_ts.setText("날짜를 선택하세요")
            return

        try:
            date_str = f"{day[:4]}-{day[4:6]}-{day[6:8]}"

            def _to_full(t: str, end: bool = False) -> str:
                if not t:
                    return ""
                parts = t.split(":")
                hh = parts[0].zfill(2)
                mm = parts[1].zfill(2) if len(parts) > 1 else "00"
                ss = parts[2].zfill(2) if len(parts) > 2 else ("59" if end else "00")
                return f"{date_str} {hh}:{mm}:{ss}"

            from_ts = _to_full(t_fr, end=False)
            to_ts   = _to_full(t_to, end=True)
        except Exception as e:
            self.lbl_ts.setText(f"시간 형식 오류: {e}")
            return

        range_str = f"{t_fr}~{t_to}" if t_fr or t_to else "전체"
        self.lbl_ts.setText(f"로딩 중... [{day} {range_str}]")

        # ★ 두 DB 머지 로드
        rows = load_merged_snapshots(day, from_ts, to_ts)
        if not rows:
            self.lbl_ts.setText(f"데이터 없음  [{day} {range_str}]")
            return

        # 타임스탬프 순서 구성
        ts_set = dict.fromkeys(r["ts"] for r in rows)
        self._ts_list = list(ts_set.keys())

        strikes_set = sorted({r["strike"] for r in rows})
        self._strikes = strikes_set

        und = next((r["und_price"] for r in rows if r["und_price"]), 0)
        if und and strikes_set:
            self._atm = min(strikes_set, key=lambda s: abs(s - und))

        # 프레임 구성 (Greeks + 가격 모두 포함)
        self._frames = {}
        for r in rows:
            ts   = r["ts"]
            st   = r["strike"]
            side = r["side"]
            row  = strikes_set.index(st)
            self._frames.setdefault(ts, {})[(row, side)] = {
                "delta":  r.get("delta")  or 0.0,
                "gamma":  r.get("gamma")  or 0.0,
                "iv":     r.get("iv")     or 0.0,
                "vanna":  r.get("vanna")  or 0.0,
                "bid":    r.get("bid"),
                "ask":    r.get("ask"),
                "mid":    r.get("mid"),
                "theo":   r.get("theo"),
                "mispct": r.get("mispct"),
            }

        # 테이블 초기화
        self.tbl.setRowCount(len(strikes_set))
        for i, st in enumerate(strikes_set):
            init_row_replay(self.tbl, i, st, self._atm)

        self.slider.setMaximum(max(0, len(self._ts_list) - 1))
        self.slider.setValue(0)
        self._cur_idx = 0
        self._prev    = {}

        total = len(rows)
        self.lbl_ts.setText(
            f"로드 완료: {len(self._ts_list)}개 시점  "
            f"/ {len(strikes_set)}개 행사가  "
            f"/ 총 {total}행  [{day} {range_str}]")
        self._render(0)

    # ----------------------------------------------------------
    # 재생 제어
    # ----------------------------------------------------------
    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._timer.stop()
            self.btn_play.setText("재생")
        else:
            if not self._ts_list:
                return
            speed = REPLAY_SPEEDS.get(self.cmb_speed.currentText(), 1000)
            self._playing = True
            self._timer.start(speed)
            self.btn_play.setText("일시정지")

    def _stop(self):
        self._playing = False
        self._timer.stop()
        self.btn_play.setText("재생")
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

    # ----------------------------------------------------------
    # 렌더
    # ----------------------------------------------------------
    def _render(self, idx: int):
        if not self._ts_list or idx >= len(self._ts_list):
            return
        ts     = self._ts_list[idx]
        cell_d = self._frames.get(ts, {})
        self.lbl_ts.setText(ts)
        render_rows_replay(
            self.tbl, self._strikes, self._atm, cell_d, self._prev)

    # ----------------------------------------------------------
    def refresh(self):
        self._refresh_days()