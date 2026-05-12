"""
chart_daily.py — 일봉 추가 보기 위임 함수 (진입점)
────────────────────────────────────────────────────────
[분리] v2:
  chart_daily_helpers.py — CSV/마커 경로 헬퍼
  chart_daily_worker.py  — _DailyFillWorker (QThread)
  이 파일 — toggle/load/render/center 위임 함수
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime
import pyqtgraph as pg
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPicture
from PyQt5.QtWidgets import QSizePolicy

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from chart_daily_helpers import (
    _daily_csv_path, _has_daily_marker, _set_daily_marker
)
from chart_daily_worker import _DailyFillWorker  # noqa: F401


# ── 캔들스틱 아이템 (일봉 전용) ───────────────────────────
class _DailyCandle(pg.GraphicsObject):
    def __init__(self, data, body_w=0.55):
        super().__init__()
        self._data = data; self._body_w = body_w
        self._pic  = None; self._gen()

    def _gen(self):
        self._pic = QPicture()
        p = QPainter(self._pic)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self._body_w / 2
        for idx, o, h, l, c in self._data:
            col = QColor("#26a69a") if c >= o else QColor("#ef5350")
            p.setPen(pg.mkPen(col, width=1))
            p.setBrush(pg.mkBrush(col))
            p.drawLine(pg.QtCore.QPointF(idx, l), pg.QtCore.QPointF(idx, h))
            top = max(o, c); bot = min(o, c)
            p.drawRect(pg.QtCore.QRectF(idx - w, bot, 2 * w, max(top - bot, 0.0001)))
        p.end()

    def paint(self, p, *args): p.drawPicture(0, 0, self._pic)
    def boundingRect(self):    return pg.QtCore.QRectF(self._pic.boundingRect())

def toggle_daily_view(self):
    """btn_daily 클릭 → 분차트 테이블 ↔ 일봉 차트 전환"""
    on = self.btn_daily.isChecked()
    if on:
        self.btn_daily.setText("📈 일봉 보기 ✔")
        self._tbl_splitter.hide()
        self.daily_container.show()
        self._load_daily_data()
    else:
        self.btn_daily.setText("📈 일봉 추가 보기")
        self.daily_container.hide()
        self._tbl_splitter.show()
        if getattr(self, "_daily_worker", None):
            self._daily_worker.quit()
            self._daily_worker = None


def load_daily_data(self):
    """심볼 + 캘린더 날짜 기준으로 일봉 데이터 로드 (캐시 우선)"""
    sym = self.sym_in.text().strip().upper()
    if not sym:
        self.status_lbl.setText("일봉 조회 실패: 종목을 먼저 입력하세요.")
        return

    cal_date = self.calendar.selectedDate().toString("yyyy-MM-dd")
    self.status_lbl.setText(f"📈 일봉 확인 중…  {sym}  ({cal_date} 기준)")

    if getattr(self, "_daily_worker", None):
        self._daily_worker.quit()

    self._daily_worker = _DailyFillWorker(sym, cal_date, self.api_key)
    self._daily_worker.status.connect(
        lambda msg: self.status_lbl.setText(msg))
    self._daily_worker.done.connect(
        lambda df: render_daily(self, df))
    self._daily_worker.error.connect(
        lambda msg: self.status_lbl.setText(f"일봉 오류: {msg}"))
    self._daily_worker.start()



# [분리] 렌더 함수 → chart_daily_render.py
from chart_daily_render import (  # noqa: F401
    render_daily, center_on_calendar
)
