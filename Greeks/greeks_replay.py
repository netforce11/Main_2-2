"""
greeks_replay.py — Greeks 리플레이 패널 (메인)
════════════════════════════════════════════════════════════════
저장된 SQLite 데이터를 날짜·시간 범위 지정 후 슬라이더로 재생.

v6.7 변경:
  - ★ 뷰 모드 라디오버튼 추가 (Greeks / 프리미엄 / 이론가)
  - ★ 파일 분리: greeks_replay_ctrl.py + greeks_replay_data.py
  - ★ 등락률(chg_pct) 컬럼 추가

파일 구성:
  greeks_replay.py       ← 이 파일. ReplayPanel 클래스만 정의.
  greeks_replay_ctrl.py  ← 컨트롤바 + 라디오버튼 UI 빌드.
  greeks_replay_data.py  ← DB 로드 + 프레임 구성 + 렌더 로직.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QSlider, QTableWidget, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer

from greeks_db import available_days_merged, available_expiries_for_day
from greeks_render_replay import init_table_replay, REPLAY_NCOLS

from greeks_replay_ctrl import build_ctrl_bar, REPLAY_SPEEDS
from greeks_replay_data import load_replay_data, render_frame


class ReplayPanel(QWidget):
    """
    날짜 선택 → 시간범위 입력 → 재생/정지 + 슬라이더로
    Greeks + 프리미엄 + 이론가 재생.

    뷰 모드 (라디오버튼):
      greeks   → Delta / Gamma / IV / Vanna
      premium  → Bid / Ask / Mid / Last
      theory   → Theo / Mispct / 등락률
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── 상태 ──────────────────────────────────────────────
        self._snapshots: list  = []
        self._frames:    dict  = {}
        self._ts_list:   list  = []
        self._cur_idx:   int   = 0
        self._strikes:   list  = []
        self._atm:       float = 0.0
        self._prev:      dict  = {}
        self._playing          = False
        self._cur_view         = "greeks"    # 기본 뷰 모드

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

        self._build()

    # ── UI 조립 ───────────────────────────────────────────────

    def _build(self):
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(4, 4, 4, 4)
        vlay.setSpacing(4)

        # 컨트롤바 (ctrl.py 에서 빌드, panel 속성으로 위젯 등록)
        vlay.addLayout(build_ctrl_bar(self))

        # 슬라이더
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        vlay.addWidget(self.slider)

        # 테이블
        self.tbl = QTableWidget(0, REPLAY_NCOLS)
        init_table_replay(self.tbl)
        self.tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vlay.addWidget(self.tbl)

        self._refresh_days()

    # ── 날짜 / 만기 갱신 ──────────────────────────────────────

    def _refresh_days(self):
        self.cmb_day.clear()
        for d in reversed(available_days_merged()):
            self.cmb_day.addItem(d)
        self._refresh_expiries(self.cmb_day.currentText())

    def _on_day_changed(self, day: str):
        self.edit_from.clear()
        self.edit_to.clear()
        self._refresh_expiries(day)

    def _refresh_expiries(self, day: str):
        self.cmb_expiry.clear()
        if not day:
            return
        self.cmb_expiry.addItem("전체 만기", "")
        for exp in available_expiries_for_day(day):
            label = _fmt_expiry(exp, day)
            self.cmb_expiry.addItem(label, exp)

    # ── 데이터 로드 ───────────────────────────────────────────

    def _load(self):
        self._stop()
        day          = self.cmb_day.currentText()
        expiry_raw   = self.cmb_expiry.currentData() or ""
        expiry_label = self.cmb_expiry.currentText()

        if not day:
            self.lbl_ts.setText("날짜를 선택하세요")
            return

        ok = load_replay_data(
            self,
            day       = day,
            t_fr      = self.edit_from.text().strip(),
            t_to      = self.edit_to.text().strip(),
            expiry_raw   = expiry_raw,
            expiry_label = expiry_label,
        )
        if ok:
            self._render(0)

    # ── 재생 제어 ─────────────────────────────────────────────

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

    def _on_speed(self, key: str):
        if self._playing:
            self._timer.setInterval(REPLAY_SPEEDS.get(key, 1000))

    # ── 렌더 ──────────────────────────────────────────────────

    def _render(self, idx: int):
        render_frame(self, idx)

    # ── 외부 호출 ─────────────────────────────────────────────

    def refresh(self):
        self._refresh_days()


# ── 헬퍼 ──────────────────────────────────────────────────────

def _fmt_expiry(exp: str, day: str) -> str:
    """YYYYMMDD 만기일 → 'MM/DD (+N일)' 레이블."""
    try:
        from datetime import datetime
        exp_dt  = datetime.strptime(exp, "%Y%m%d")
        base_dt = datetime.strptime(day, "%Y%m%d")
        diff    = (exp_dt - base_dt).days
        base    = f"{exp[4:6]}/{exp[6:8]}"
        if diff == 0:   return f"{base} (당일)"
        if diff == 1:   return f"{base} (내일)"
        if diff > 0:    return f"{base} (+{diff}일)"
        return f"{base} (만료)"
    except Exception:
        return exp