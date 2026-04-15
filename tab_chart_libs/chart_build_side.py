"""
chart_build_side.py — 차트탭 좌측 사이드바 빌드
────────────────────────────────────────────────────────
build_sidebar(self) → QScrollArea

v6.4 변경: 사이드바 하단에 '📈 일봉 추가 보기' 토글 버튼 추가
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
    QScrollArea,
)
from PyQt5.QtCore import Qt


def build_sidebar(self) -> QScrollArea:
    side = QVBoxLayout(); side.setSpacing(3)
    side.setContentsMargins(4, 4, 4, 4)

    # 데이터 소스
    src_grp = QGroupBox("데이터 소스"); src_v = QVBoxLayout(src_grp)
    src_v.setSpacing(2); src_v.setContentsMargins(6, 4, 6, 4)
    self.radio_polygon = QRadioButton("Polygon.io")
    self.radio_ibkr    = QRadioButton("IBKR API")
    self.radio_polygon.setChecked(True)
    mg = QButtonGroup(self)
    mg.addButton(self.radio_polygon); mg.addButton(self.radio_ibkr)
    self.radio_polygon.toggled.connect(self._on_mode_change)
    self.lbl_mode = QLabel("Polygon.io")
    self.lbl_mode.setStyleSheet("color:#aaa;font-size:11px;")
    src_v.addWidget(self.radio_polygon); src_v.addWidget(self.radio_ibkr)
    src_v.addWidget(self.lbl_mode); side.addWidget(src_grp)

    # 종목 / 관심종목
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

    # 환율 / 필터
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

    # 실시간
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
    self.btn_force_reload.setToolTip("현재 날짜 데이터를 캐시 무시하고 API에서 강제 재다운로드")
    self.btn_force_reload.clicked.connect(self._on_force_reload)
    rt_btn_row.addWidget(self.btn_force_reload)
    rt_v.addLayout(rt_btn_row)
    crow = QHBoxLayout(); crow.addWidget(QLabel("캔들:"))
    self.candle_spin = QSpinBox()
    self.candle_spin.setRange(10, 2000); self.candle_spin.setValue(180)
    crow.addWidget(self.candle_spin); crow.addStretch()
    rt_v.addLayout(crow)
    self.status_lbl = QLabel("상태: 대기")
    self.status_lbl.setStyleSheet("font-weight:bold;font-size:11px;")
    rt_v.addWidget(self.status_lbl); side.addWidget(rt_grp)

    # 보기 옵션
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

    # 캘린더
    cal_grp = QGroupBox("과거 복기"); cal_v = QVBoxLayout(cal_grp)
    cal_v.setSpacing(2); cal_v.setContentsMargins(4, 4, 4, 4)
    self.calendar = QCalendarWidget(); self.calendar.setMaximumHeight(185)
    self.calendar.clicked.connect(self._on_calendar)
    cal_v.addWidget(self.calendar); side.addWidget(cal_grp)

    # 수급 피크 검색
    pk_grp = QGroupBox("수급 피크 검색"); pk_v = QVBoxLayout(pk_grp)
    pk_v.setSpacing(3); pk_v.setContentsMargins(6, 4, 6, 4)
    pk_v.addWidget(QLabel("① ±30분 최대"))
    p1r = QHBoxLayout(); p1r.setSpacing(3)
    self.pk1_in = QLineEdit(); self.pk1_in.setPlaceholderText("10:30 (ET)")
    self.pk1_in.setFixedHeight(22)
    b1 = QPushButton("검색"); b1.setFixedHeight(22); b1.setFixedWidth(44)
    b1.clicked.connect(self._peak1)
    p1r.addWidget(self.pk1_in); p1r.addWidget(b1); pk_v.addLayout(p1r)
    self.pk1_lbl = QLabel("결과: ―"); self.pk1_lbl.setWordWrap(True)
    self.pk1_lbl.setStyleSheet("color:#c62828;font-weight:bold;font-size:11px;")
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
    p2r.addWidget(self.pk2_e); p2r.addWidget(b2); pk_v.addLayout(p2r)
    self.pk2_lbl = QLabel("합산: ―"); self.pk2_lbl.setWordWrap(True)
    self.pk2_lbl.setStyleSheet("color:#1b5e20;font-weight:bold;font-size:11px;")
    pk_v.addWidget(self.pk2_lbl)
    pk_v.addWidget(QLabel("③ 테이블 다중선택"))
    self.pk3_lbl = QLabel("선택 합산: 0.00억"); self.pk3_lbl.setWordWrap(True)
    self.pk3_lbl.setStyleSheet(
        "font-weight:bold;font-size:12px;"
        "border:1px solid #9c27b0;padding:3px;border-radius:4px;")
    pk_v.addWidget(self.pk3_lbl); side.addWidget(pk_grp)

    # ════════════════════════════════════════════════════
    # v6.4 신규: 일봉 추가 보기 버튼 (사이드바 하단)
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
        "  font-weight:bold;padding:4px 8px;"
        "}"
        "QPushButton:hover{"
        "  background:#243024;color:#cccccc;"
        "  border-color:#4a7a4a;"
        "}"
        "QPushButton:checked{"
        "  background:#1a3a2a;color:#26a69a;"
        "  border:1px solid #26a69a;"
        "}"
        "QPushButton:checked:hover{"
        "  background:#1e4a34;"
        "}"
    )
    self.btn_daily.clicked.connect(self._toggle_daily_view)
    side.addWidget(self.btn_daily)
    # ════════════════════════════════════════════════════

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