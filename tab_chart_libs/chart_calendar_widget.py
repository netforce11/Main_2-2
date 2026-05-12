"""
chart_calendar_widget.py — 다크 테마 커스텀 달력 위젯
[분리] chart_build_side.py 에서 분리 (_CustomCalendar)

외부에서: from chart_calendar_widget import _CustomCalendar
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel,
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal

class _CustomCalendar(QWidget):
    """다크 테마 커스텀 달력 위젯."""

    clicked = pyqtSignal(object)   # QDate emit → _on_calendar(qdate) 호환

    # ── 미국 공휴일 (간략, 주요 날짜만) ─────────────────────
    _HOLIDAYS = {
        (1, 1), (7, 4), (12, 25), (12, 26),
        (11, 11),   # Veterans Day
    }

    _DOW = ["월", "화", "수", "목", "금", "토", "일"]

    _SS = """
        QWidget { background:#0e0e1a; color:#dde0f0; }
        QPushButton {
            background:#1c1c3a; color:#5dade2;
            border:1px solid #3a3a7a; border-radius:3px;
            font-size:11px; padding:2px 6px;
        }
        QPushButton:hover { background:#2a2a5a; }
        QPushButton#today_btn {
            color:#00e676; border-color:#1a5c3a;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(self._SS)
        today = QDate.currentDate()
        self._year  = today.year()
        self._month = today.month()
        self._selected = today
        self._build()
        self._render()

    # ── 외부 호환 메서드 ──────────────────────────────────────
    def selectedDate(self) -> QDate:
        """chart_data.py: self.calendar.selectedDate() 호환."""
        return self._selected

    def setSelectedDate(self, qdate: QDate):
        self._selected = qdate
        self._year  = qdate.year()
        self._month = qdate.month()
        self._render()

    # ── UI 빌드 (최초 1회) ────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(3)

        # 헤더 (이전/다음 + 년월)
        hdr = QHBoxLayout(); hdr.setSpacing(3)
        self._btn_pm = QPushButton("◀◀"); self._btn_pm.setFixedSize(26, 20)
        self._btn_pm.clicked.connect(self._prev_month)
        self._btn_nm = QPushButton("▶▶"); self._btn_nm.setFixedSize(26, 20)
        self._btn_nm.clicked.connect(self._next_month)
        self._lbl_ym = QLabel("", alignment=Qt.AlignCenter)
        self._lbl_ym.setStyleSheet(
            "color:#5dade2; font-size:12px; font-weight:bold; letter-spacing:1px;")
        hdr.addWidget(self._btn_pm)
        hdr.addWidget(self._lbl_ym, 1)
        hdr.addWidget(self._btn_nm)
        root.addLayout(hdr)

        # 요일 헤더 + 날짜 그리드
        self._grid = QGridLayout()
        self._grid.setSpacing(2)
        self._grid.setContentsMargins(0, 0, 0, 0)
        for col, dow in enumerate(self._DOW):
            lbl = QLabel(dow, alignment=Qt.AlignCenter)
            color = "#3a7abd" if dow == "토" else \
                    "#9a3a3a" if dow == "일" else "#556"
            lbl.setStyleSheet(f"color:{color}; font-size:10px;")
            lbl.setFixedHeight(16)
            self._grid.addWidget(lbl, 0, col)
        self._day_btns: list = []
        for r in range(6):
            for c in range(7):
                btn = QPushButton("")
                btn.setFixedSize(28, 22)
                btn.setStyleSheet("border:none; font-size:11px;")
                btn.clicked.connect(self._on_day_click)
                self._grid.addWidget(btn, r + 1, c)
                self._day_btns.append(btn)
        root.addLayout(self._grid)

        # 하단 빠른 이동 버튼
        ftr = QHBoxLayout(); ftr.setSpacing(2)
        for label, slot in [
            ("오늘", self._go_today),
            ("◀1주", self._prev_week),
            ("1주▶", self._next_week),
            ("◀1달", self._prev_month),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(18)
            b.setStyleSheet(
                "background:#141430; color:#888;"
                "border:1px solid #2a2a5a; border-radius:2px; font-size:10px;")
            if label == "오늘":
                b.setObjectName("today_btn")
                b.setStyleSheet(
                    "background:#141430; color:#00e676;"
                    "border:1px solid #1a5c3a; border-radius:2px; font-size:10px;")
            b.clicked.connect(slot)
            ftr.addWidget(b)
        root.addLayout(ftr)

        # 범례
        leg = QHBoxLayout(); leg.setSpacing(6)
        for dot_color, text in [("#00e676", "데이터있음"), ("#5dade2", "오늘")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{dot_color}; font-size:9px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("color:#444; font-size:9px;")
            leg.addWidget(dot); leg.addWidget(lbl)
        leg.addStretch()
        root.addLayout(leg)

    # ── 렌더링 (월 변경마다 호출) ─────────────────────────────
    def _render(self):
        self._lbl_ym.setText(f"{self._year} / {self._month:02d}")
        first = QDate(self._year, self._month, 1)
        start_col = first.dayOfWeek() - 1   # 0=월 ... 6=일
        days_in_month = first.daysInMonth()
        today = QDate.currentDate()

        for idx, btn in enumerate(self._day_btns):
            day_num = idx - start_col + 1
            if day_num < 1 or day_num > days_in_month:
                btn.setText("")
                btn.setEnabled(False)
                btn.setStyleSheet("border:none; background:transparent;")
                btn.setProperty("qdate", None)
                continue

            qd   = QDate(self._year, self._month, day_num)
            dow  = qd.dayOfWeek()
            is_today    = (qd == today)
            is_selected = (qd == self._selected)
            is_weekend  = (dow >= 6)
            is_holiday  = (self._month, day_num) in self._HOLIDAYS
            is_trading  = not is_weekend and not is_holiday

            btn.setText(str(day_num))
            btn.setEnabled(True)
            btn.setProperty("qdate", qd)

            if is_selected:
                btn.setStyleSheet(
                    "background:#5dade2; color:#0e0e1a;"
                    "font-weight:bold; border-radius:3px; font-size:11px;")
            elif is_today:
                btn.setStyleSheet(
                    "background:#1a3a5a; color:#5dade2;"
                    "border:1px solid #3a6a9a; border-radius:3px; font-size:11px;")
            elif dow == 7:
                btn.setStyleSheet(
                    "background:transparent; color:#7a3a3a;"
                    "border:none; font-size:11px;")
            elif dow == 6:
                btn.setStyleSheet(
                    "background:transparent; color:#3a6a9a;"
                    "border:none; font-size:11px;")
            elif is_trading:
                btn.setStyleSheet(
                    "background:transparent; color:#dde0f0;"
                    "border:none; font-size:11px;"
                    "padding-bottom:6px;")
            else:
                btn.setStyleSheet(
                    "background:transparent; color:#444;"
                    "border:none; font-size:11px;")

            if is_trading and qd < today and not is_selected:
                btn.setToolTip(qd.toString("yyyy-MM-dd"))

    # ── 클릭 핸들러 ──────────────────────────────────────────
    def _on_day_click(self):
        btn = self.sender()
        qd  = btn.property("qdate")
        if qd is None:
            return
        self._selected = qd
        self._render()
        self.clicked.emit(qd)

    # ── 빠른 이동 ─────────────────────────────────────────────
    def _go_today(self):
        today = QDate.currentDate()
        self._year  = today.year()
        self._month = today.month()
        self._selected = today
        self._render()
        self.clicked.emit(today)

    def _prev_month(self):
        d = QDate(self._year, self._month, 1).addMonths(-1)
        self._year = d.year(); self._month = d.month()
        self._render()

    def _next_month(self):
        d = QDate(self._year, self._month, 1).addMonths(1)
        self._year = d.year(); self._month = d.month()
        self._render()

    def _prev_week(self):
        nd = self._selected.addDays(-7)
        self._selected = nd
        self._year = nd.year(); self._month = nd.month()
        self._render()
        self.clicked.emit(nd)

    def _next_week(self):
        nd = self._selected.addDays(7)
        self._selected = nd
        self._year = nd.year(); self._month = nd.month()
        self._render()
