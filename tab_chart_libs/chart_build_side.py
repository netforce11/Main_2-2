"""
chart_build_side.py — 차트탭 좌측 사이드바 빌드
────────────────────────────────────────────────────────
build_sidebar(self) → QScrollArea

v6.4 변경: 사이드바 하단에 '📈 일봉 추가 보기' 토글 버튼 추가
v6.5 변경:
  - 데이터 소스: 가로 배치로 공간 확보
  - 수급 피크 검색: Foldable 패널 (▶/▼ 토글)
  - IBKR 자동전환 안내 라벨 추가 (RT 버튼 하단)
v6.6 변경:
  - 상단 우측 패널 토글 체크박스 추가
    (대량 체결 테이블 ↔ 조건부 주문 설정 창)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QCheckBox, QSpinBox,
    QCalendarWidget, QFrame, QRadioButton, QButtonGroup,
    QScrollArea, QGridLayout, QSizePolicy,
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal
from PyQt5.QtGui import QColor


# ══════════════════════════════════════════════════════════════
# Foldable GroupBox 헬퍼
# ══════════════════════════════════════════════════════════════
class _FoldableGroup(QWidget):
    """
    접기/펼치기 가능한 그룹 패널.
    header_text: 상단 토글 버튼에 표시될 제목
    content    : 펼쳤을 때 보여줄 QWidget
    """
    def __init__(self, header_text: str, content: QWidget, parent=None,
                 collapsed: bool = False):
        super().__init__(parent)
        self._collapsed = collapsed
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 헤더 토글 버튼
        self._btn = QPushButton()
        self._btn.setCheckable(True)
        self._btn.setChecked(not collapsed)
        self._btn.setFixedHeight(24)
        self._btn.setStyleSheet(
            "QPushButton{"
            "  background:#141430; color:#5dade2;"
            "  border:1px solid #2e3060; border-radius:3px;"
            "  text-align:left; padding:0 6px;"
            "  font-weight:bold; font-size:12px;"
            "}"
            "QPushButton:hover{ background:#1c1c3a; }"
        )
        self._btn.clicked.connect(self._toggle)
        root.addWidget(self._btn)

        # 컨텐츠 영역
        self._content = content
        root.addWidget(self._content)

        self._update_label(header_text)
        self._content.setVisible(not collapsed)

    def _update_label(self, text: str):
        self._header_text = text
        arrow = "▼" if self._btn.isChecked() else "▶"
        self._btn.setText(f"  {arrow}  {text}")

    def _toggle(self, checked: bool):
        self._content.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self._btn.setText(f"  {arrow}  {self._header_text}")


def build_sidebar(self) -> QScrollArea:
    side = QVBoxLayout(); side.setSpacing(3)
    side.setContentsMargins(4, 4, 4, 4)

    # ── 데이터 소스 (가로 배치) ──────────────────────────────
    src_grp = QGroupBox("데이터 소스")
    src_h   = QHBoxLayout(src_grp)
    src_h.setSpacing(4); src_h.setContentsMargins(6, 4, 6, 4)

    self.radio_polygon = QRadioButton("Polygon.io")
    self.radio_ibkr    = QRadioButton("IBKR")
    self.radio_polygon.setChecked(True)
    mg = QButtonGroup(self)
    mg.addButton(self.radio_polygon); mg.addButton(self.radio_ibkr)
    self.radio_polygon.toggled.connect(self._on_mode_change)

    self.lbl_mode = QLabel("Polygon.io")
    self.lbl_mode.setStyleSheet(
        "color:#5dade2; font-size:11px; font-weight:bold;")
    self.lbl_mode.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    src_h.addWidget(self.radio_polygon)
    src_h.addWidget(self.radio_ibkr)
    src_h.addStretch()
    src_h.addWidget(self.lbl_mode)
    side.addWidget(src_grp)

    # ── 종목 / 관심종목 ──────────────────────────────────────
    sym_grp = QGroupBox("종목 / 관심종목"); sym_v = QVBoxLayout(sym_grp)
    sym_v.setSpacing(2); sym_v.setContentsMargins(6, 4, 6, 4)
    self.sym_in = QLineEdit("SPY"); sym_v.addWidget(self.sym_in)
    self.watch_list = QListWidget(); self.watch_list.setMaximumHeight(80)
    self.watch_list.itemClicked.connect(
        lambda it: self.start_stream(it.text()))
    sym_v.addWidget(self.watch_list)
    brow = QHBoxLayout(); brow.setSpacing(2)
    ba = QPushButton("추가"); ba.setFixedHeight(22); ba.clicked.connect(self._w_add)
    bd = QPushButton("삭제"); bd.setFixedHeight(22); bd.clicked.connect(self._w_del)
    brow.addWidget(ba); brow.addWidget(bd)
    sym_v.addLayout(brow); side.addWidget(sym_grp)

    # ── 환율 / 필터 ──────────────────────────────────────────
    flt_grp = QGroupBox("환율 / 필터"); flt_v = QVBoxLayout(flt_grp)
    flt_v.setSpacing(2); flt_v.setContentsMargins(6, 4, 6, 4)
    fr = QHBoxLayout()
    fr.addWidget(QLabel("환율(원)")); self.fx_in = QLineEdit("1480")
    self.fx_in.setFixedWidth(60); fr.addWidget(self.fx_in)
    fr.addWidget(QLabel("필터(억)")); self.high_in = QLineEdit("3000")
    self.high_in.setFixedWidth(60); fr.addWidget(self.high_in)
    flt_v.addLayout(fr)
    fg = QHBoxLayout(); fg.setSpacing(2)
    for val in ["1000", "3000", "5000", "7500"]:
        btn = QPushButton(f"{val}억"); btn.setFixedHeight(20)
        btn.clicked.connect(lambda _, v=val: self.high_in.setText(v))
        fg.addWidget(btn)
    flt_v.addLayout(fg); side.addWidget(flt_grp)

    # ── 실시간 ───────────────────────────────────────────────
    rt_grp = QGroupBox("실시간"); rt_v = QVBoxLayout(rt_grp)
    rt_v.setSpacing(2); rt_v.setContentsMargins(6, 4, 6, 4)

    rt_btn_row = QHBoxLayout(); rt_btn_row.setSpacing(4)
    self.btn_rt = QPushButton("▶ RT 시작"); self.btn_rt.setCheckable(True)
    self.btn_rt.setStyleSheet(
        "background:#1a6b3c;color:#fff;font-weight:bold;"
        "padding:4px;border-radius:3px;")
    self.btn_rt.clicked.connect(self._on_rt_btn)
    rt_btn_row.addWidget(self.btn_rt)

    self.btn_force_reload = QPushButton("🔄 재조회")
    self.btn_force_reload.setFixedHeight(28)
    self.btn_force_reload.setStyleSheet(
        "QPushButton{background:#2a2a1a;color:#ffcc44;"
        "border:1px solid #7a6a1a;border-radius:3px;"
        "font-weight:bold;padding:2px 6px;}"
        "QPushButton:hover{background:#3a3a1a;color:#ffe066;}")
    self.btn_force_reload.setToolTip(
        "현재 날짜 데이터를 캐시 무시하고 API에서 강제 재다운로드")
    self.btn_force_reload.clicked.connect(self._on_force_reload)
    rt_btn_row.addWidget(self.btn_force_reload)
    rt_v.addLayout(rt_btn_row)

    # IBKR 자동전환 안내 라벨
    self.lbl_ibkr_auto = QLabel("IBKR 연결 시 자동 전환")
    self.lbl_ibkr_auto.setStyleSheet(
        "color:#5dade2; font-size:10px; padding-left:4px;")
    rt_v.addWidget(self.lbl_ibkr_auto)

    crow = QHBoxLayout(); crow.addWidget(QLabel("캔들:"))
    self.candle_spin = QSpinBox()
    self.candle_spin.setRange(10, 2000); self.candle_spin.setValue(180)
    crow.addWidget(self.candle_spin); crow.addStretch()
    rt_v.addLayout(crow)

    self.status_lbl = QLabel("상태: 대기")
    self.status_lbl.setStyleSheet("font-weight:bold;font-size:11px;")
    rt_v.addWidget(self.status_lbl)
    side.addWidget(rt_grp)

    # ── 보기 옵션 ─────────────────────────────────────────────
    opt_grp = QGroupBox("보기 옵션"); opt_v = QVBoxLayout(opt_grp)
    opt_v.setSpacing(2); opt_v.setContentsMargins(6, 4, 6, 4)
    self.holding_chk = QCheckBox("종가홀딩 보기")
    self.holding_chk.stateChanged.connect(lambda _: self._update_display())
    opt_v.addWidget(self.holding_chk)
    opt_v.addWidget(QLabel("  15:00~마감 + 다음날 시초~10:30",
                            styleSheet="color:gray;font-size:10px;"))
    multi_row = QHBoxLayout(); multi_row.setSpacing(4)
    multi_row.addWidget(QLabel("연속:"))
    self.multi_chks = {}
    for days in [2, 3, 4]:
        chk = QCheckBox(f"{days}일"); chk.setChecked(False)
        chk.stateChanged.connect(
            lambda state, d=days, c=chk: self._on_multi_chk(d, c, state))
        multi_row.addWidget(chk); self.multi_chks[days] = chk
    opt_v.addLayout(multi_row); side.addWidget(opt_grp)

    # ── 캘린더 ───────────────────────────────────────────────
    cal_grp = QGroupBox("과거 복기"); cal_v = QVBoxLayout(cal_grp)
    cal_v.setSpacing(2); cal_v.setContentsMargins(4, 4, 4, 4)
    self.calendar = _CustomCalendar()
    self.calendar.clicked.connect(self._on_calendar)
    cal_v.addWidget(self.calendar); side.addWidget(cal_grp)

    # ── 수급 피크 검색 (Foldable) ────────────────────────────
    pk_content = QWidget()
    pk_v = QVBoxLayout(pk_content)
    pk_v.setSpacing(3); pk_v.setContentsMargins(6, 4, 6, 4)

    pk_v.addWidget(QLabel("① ±30분 최대"))
    p1r = QHBoxLayout(); p1r.setSpacing(3)
    self.pk1_in = QLineEdit(); self.pk1_in.setPlaceholderText("10:30 (ET)")
    self.pk1_in.setFixedHeight(22)
    b1 = QPushButton("검색"); b1.setFixedHeight(22); b1.setFixedWidth(44)
    b1.clicked.connect(self._peak1)
    p1r.addWidget(self.pk1_in); p1r.addWidget(b1)
    pk_v.addLayout(p1r)

    self.pk1_lbl = QLabel("결과: ―"); self.pk1_lbl.setWordWrap(True)
    self.pk1_lbl.setStyleSheet(
        "color:#c62828;font-weight:bold;font-size:11px;")
    pk_v.addWidget(self.pk1_lbl)

    pk_v.addWidget(QLabel("② 구간 합산"))
    p2r = QHBoxLayout(); p2r.setSpacing(2)
    self.pk2_s = QLineEdit(); self.pk2_s.setPlaceholderText("09:30")
    self.pk2_s.setFixedHeight(22)
    self.pk2_e = QLineEdit(); self.pk2_e.setPlaceholderText("10:30")
    self.pk2_e.setFixedHeight(22)
    b2 = QPushButton("합산"); b2.setFixedHeight(22); b2.setFixedWidth(44)
    b2.clicked.connect(self._peak2)
    p2r.addWidget(self.pk2_s); p2r.addWidget(QLabel("~"))
    p2r.addWidget(self.pk2_e); p2r.addWidget(b2)
    pk_v.addLayout(p2r)

    self.pk2_lbl = QLabel("합산: ―"); self.pk2_lbl.setWordWrap(True)
    self.pk2_lbl.setStyleSheet(
        "color:#1b5e20;font-weight:bold;font-size:11px;")
    pk_v.addWidget(self.pk2_lbl)

    pk_v.addWidget(QLabel("③ 테이블 다중선택"))
    self.pk3_lbl = QLabel("선택 합산: 0.00억")
    self.pk3_lbl.setWordWrap(True)
    self.pk3_lbl.setStyleSheet(
        "font-weight:bold;font-size:12px;"
        "border:1px solid #9c27b0;padding:3px;border-radius:4px;")
    pk_v.addWidget(self.pk3_lbl)

    # Foldable 래퍼 (기본: 접힌 상태 collapsed=True 로 공간 절약)
    self._pk_fold = _FoldableGroup("수급 피크 검색", pk_content,
                                   collapsed=True)
    side.addWidget(self._pk_fold)

    # ════════════════════════════════════════════════════
    # v6.4: 일봉 추가 보기 버튼
    # ════════════════════════════════════════════════════
    side.addWidget(_make_sep())

    self.btn_daily = QPushButton("📈 일봉 추가 보기")
    self.btn_daily.setCheckable(True)
    self.btn_daily.setChecked(False)
    self.btn_daily.setFixedHeight(30)
    self.btn_daily.setToolTip(
        "캘린더 날짜 기준 일봉 차트를 표시합니다.\n"
        "분차트 테이블이 일시적으로 숨겨집니다.\n"
        "다시 클릭하면 분차트 테이블로 복귀합니다."
    )
    self.btn_daily.setStyleSheet(
        "QPushButton{"
        "  background:#1c2a1c;color:#aaaaaa;"
        "  border:1px solid #3a5a3a;border-radius:3px;"
        "  font-weight:bold;padding:4px 8px;}"
        "QPushButton:hover{"
        "  background:#243024;color:#cccccc;"
        "  border-color:#4a7a4a;}"
        "QPushButton:checked{"
        "  background:#1a3a2a;color:#26a69a;"
        "  border:1px solid #26a69a;}"
        "QPushButton:checked:hover{"
        "  background:#1e4a34;}"
    )
    self.btn_daily.clicked.connect(self._toggle_daily_view)
    side.addWidget(self.btn_daily)

    side.addStretch(1)

    side_w = QWidget(); side_w.setLayout(side)
    side_w.setMinimumWidth(220)
    scroll = QScrollArea()
    scroll.setWidget(side_w); scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setMinimumWidth(230); scroll.setMaximumWidth(320)
    scroll.setFrameShape(QFrame.NoFrame)
    return scroll


def _make_sep():
    """구분선 헬퍼"""
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    sep.setStyleSheet("color:#333344; margin:2px 0;")
    return sep


# ══════════════════════════════════════════════════════════════
# 커스텀 캘린더 위젯
# QCalendarWidget 을 완전히 대체.
# .clicked 시그널(QDate) + .selectedDate() 메서드를 동일하게 제공
# → tab_chart.py / chart_data.py 의 self.calendar.* 호출이 그대로 동작
# ══════════════════════════════════════════════════════════════
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
        self.clicked.emit(nd)