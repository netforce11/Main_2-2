"""
kr_build_side.py — 한국 차트탭 좌측 사이드바 빌드
────────────────────────────────────────────────────────
build_sidebar(self) → QScrollArea
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QListWidget, QCheckBox, QSpinBox,
    QCalendarWidget, QFrame, QScrollArea,
)
from PyQt5.QtCore import Qt


def build_sidebar(self) -> QScrollArea:
    side = QVBoxLayout()
    side.setSpacing(3)
    side.setContentsMargins(4, 4, 4, 4)

    # ── 데이터 소스 + 키움 연결 ───────────────────────────────
    src_grp = QGroupBox("데이터 소스")
    src_v = QVBoxLayout(src_grp)
    src_v.setSpacing(4); src_v.setContentsMargins(6, 4, 6, 4)
    lbl_src = QLabel("키움증권 OpenAPI+  (opt10080)")
    lbl_src.setStyleSheet("color:#5dade2;font-size:11px;font-weight:bold;")
    src_v.addWidget(lbl_src)

    self.btn_kiwoom_connect = QPushButton("🔌 키움 연결")
    self.btn_kiwoom_connect.setFixedHeight(28)
    self.btn_kiwoom_connect.setStyleSheet(
        "background:#1a1a3a;color:#8888ff;"
        "border:1px solid #3a3a7a;border-radius:3px;"
        "font-weight:bold;padding:4px;")
    self.btn_kiwoom_connect.setToolTip(
        "클릭하면 키움증권 로그인 팝업이 뜹니다.")
    self.btn_kiwoom_connect.clicked.connect(self._connect_kiwoom)
    src_v.addWidget(self.btn_kiwoom_connect)

    # 이미 연결된 상태라면 버튼 스타일 즉시 반영
    if getattr(self, 'kiwoom', None) is not None:
        self._update_connect_ui(True)

    side.addWidget(src_grp)

    # ── 종목 / 관심종목 ───────────────────────────────────────
    sym_grp = QGroupBox("종목 / 관심종목")
    sym_v = QVBoxLayout(sym_grp)
    sym_v.setSpacing(2); sym_v.setContentsMargins(6, 4, 6, 4)

    sym_row = QHBoxLayout()
    sym_row.addWidget(QLabel("코드:"))
    self.sym_in = QLineEdit("005930")
    self.sym_in.setFixedWidth(75)
    self.sym_in.setPlaceholderText("종목코드")
    self.sym_in.textChanged.connect(self._on_sym_changed)
    sym_row.addWidget(self.sym_in)
    sym_v.addLayout(sym_row)

    self.watch_list = QListWidget()
    self.watch_list.setMaximumHeight(90)
    self.watch_list.itemClicked.connect(self._on_watch_click)
    sym_v.addWidget(self.watch_list)

    brow = QHBoxLayout(); brow.setSpacing(2)
    ba = QPushButton("추가"); ba.setFixedHeight(22)
    ba.clicked.connect(self._w_add)
    bd = QPushButton("삭제"); bd.setFixedHeight(22)
    bd.clicked.connect(self._w_del)
    brow.addWidget(ba); brow.addWidget(bd)
    sym_v.addLayout(brow)
    side.addWidget(sym_grp)

    # ── 필터 ─────────────────────────────────────────────────
    flt_grp = QGroupBox("거래대금 필터")
    flt_v = QVBoxLayout(flt_grp)
    flt_v.setSpacing(2); flt_v.setContentsMargins(6, 4, 6, 4)
    fr = QHBoxLayout()
    fr.addWidget(QLabel("필터(억)"))
    self.high_in = QLineEdit("100")
    self.high_in.setFixedWidth(60)
    fr.addWidget(self.high_in)
    flt_v.addLayout(fr)
    fg = QHBoxLayout(); fg.setSpacing(2)
    for val in ["50", "100", "200", "500"]:
        btn = QPushButton(f"{val}억"); btn.setFixedHeight(20)
        btn.clicked.connect(lambda _, v=val: self.high_in.setText(v))
        fg.addWidget(btn)
    flt_v.addLayout(fg)
    side.addWidget(flt_grp)

    # ── 실시간 / 조회 ─────────────────────────────────────────
    rt_grp = QGroupBox("조회 / 실시간")
    rt_v = QVBoxLayout(rt_grp)
    rt_v.setSpacing(3); rt_v.setContentsMargins(6, 4, 6, 4)

    # RT 시작 + 재조회
    rt_btn_row = QHBoxLayout(); rt_btn_row.setSpacing(4)
    self.btn_rt = QPushButton("▶ RT 시작")
    self.btn_rt.setCheckable(True)
    self.btn_rt.setStyleSheet(
        "background:#1a6b3c;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
    self.btn_rt.clicked.connect(self._on_rt_btn)
    rt_btn_row.addWidget(self.btn_rt)
    self.btn_force_reload = QPushButton("🔄 재조회")
    self.btn_force_reload.setFixedHeight(28)
    self.btn_force_reload.setStyleSheet(
        "QPushButton{background:#2a2a1a;color:#ffcc44;"
        "border:1px solid #7a6a1a;border-radius:3px;"
        "font-weight:bold;padding:2px 6px;}"
        "QPushButton:hover{background:#3a3a1a;color:#ffe066;}")
    self.btn_force_reload.setToolTip("캐시 무시하고 API에서 강제 재다운로드")
    self.btn_force_reload.clicked.connect(self._on_force_reload)
    rt_btn_row.addWidget(self.btn_force_reload)
    rt_v.addLayout(rt_btn_row)

    # RT 갱신 주기 (초)
    interval_row = QHBoxLayout()
    interval_row.addWidget(QLabel("RT 갱신(초):"))
    self.rt_interval_spin = QSpinBox()
    self.rt_interval_spin.setRange(5, 60)
    self.rt_interval_spin.setValue(10)
    interval_row.addWidget(self.rt_interval_spin)
    interval_row.addStretch()
    rt_v.addLayout(interval_row)

    # 캔들 수
    crow = QHBoxLayout()
    crow.addWidget(QLabel("캔들:"))
    self.candle_spin = QSpinBox()
    self.candle_spin.setRange(10, 2000)
    self.candle_spin.setValue(180)
    crow.addWidget(self.candle_spin); crow.addStretch()
    rt_v.addLayout(crow)

    # 최대조회 / 20일 조회 버튼
    fetch_row = QHBoxLayout(); fetch_row.setSpacing(4)
    self.btn_fetch_max = QPushButton("📥 최대 조회")
    self.btn_fetch_max.setFixedHeight(26)
    self.btn_fetch_max.setStyleSheet(
        "QPushButton{background:#1c2a3a;color:#5dade2;"
        "border:1px solid #2a4a6a;border-radius:3px;font-weight:bold;}"
        "QPushButton:hover{background:#243444;color:#7ec8e3;}")
    self.btn_fetch_max.setToolTip("연속 요청으로 수신 가능한 최대 분봉 수집")
    self.btn_fetch_max.clicked.connect(self._fetch_max)
    fetch_row.addWidget(self.btn_fetch_max)

    self.btn_fetch_20d = QPushButton("📅 20일 조회")
    self.btn_fetch_20d.setFixedHeight(26)
    self.btn_fetch_20d.setStyleSheet(
        "QPushButton{background:#2a1c3a;color:#c39bd3;"
        "border:1px solid #5a2a7a;border-radius:3px;font-weight:bold;}"
        "QPushButton:hover{background:#341e48;color:#d7bde2;}")
    self.btn_fetch_20d.setToolTip("최근 20거래일 분봉 일괄 수집")
    self.btn_fetch_20d.clicked.connect(self._fetch_20days)
    fetch_row.addWidget(self.btn_fetch_20d)
    rt_v.addLayout(fetch_row)

    # 마커 초기화 버튼 (잘못된 마커 삭제 후 재수집)
    btn_clear_markers = QPushButton("🗑 마커 초기화")
    btn_clear_markers.setFixedHeight(22)
    btn_clear_markers.setStyleSheet(
        "QPushButton{background:#2a1a1a;color:#ff8888;"
        "border:1px solid #6a2a2a;border-radius:3px;font-size:10px;}"
        "QPushButton:hover{background:#3a2020;color:#ffaaaa;}")
    btn_clear_markers.setToolTip(
        "현재 종목의 모든 완료 마커를 삭제합니다.\n"
        "이후 20일 조회 시 전체 재수집됩니다.")
    btn_clear_markers.clicked.connect(self._clear_all_markers)
    rt_v.addWidget(btn_clear_markers)

    self.status_lbl = QLabel("상태: 대기")
    self.status_lbl.setStyleSheet("font-weight:bold;font-size:11px;")
    rt_v.addWidget(self.status_lbl)
    side.addWidget(rt_grp)

    # ── 보기 옵션 ────────────────────────────────────────────
    opt_grp = QGroupBox("보기 옵션")
    opt_v = QVBoxLayout(opt_grp)
    opt_v.setSpacing(2); opt_v.setContentsMargins(6, 4, 6, 4)
    self.holding_chk = QCheckBox("종가홀딩 보기")
    self.holding_chk.stateChanged.connect(lambda _: self._update_display())
    opt_v.addWidget(self.holding_chk)
    opt_v.addWidget(QLabel("  15:00~장마감 + 다음날 시초~10:30",
                            styleSheet="color:gray;font-size:10px;"))
    multi_row = QHBoxLayout(); multi_row.setSpacing(4)
    multi_row.addWidget(QLabel("연속:"))
    self.multi_chks = {}
    for days in [2, 3, 4]:
        chk = QCheckBox(f"{days}일"); chk.setChecked(False)
        chk.stateChanged.connect(
            lambda state, d=days, c=chk: self._on_multi_chk(d, c, state))
        multi_row.addWidget(chk); self.multi_chks[days] = chk
    opt_v.addLayout(multi_row)
    side.addWidget(opt_grp)

    # ── 캘린더 ───────────────────────────────────────────────
    cal_grp = QGroupBox("과거 복기  (Alt+Enter: 날짜 직접 입력)")
    cal_v = QVBoxLayout(cal_grp)
    cal_v.setSpacing(2); cal_v.setContentsMargins(4, 4, 4, 4)
    self.calendar = QCalendarWidget()
    self.calendar.setMaximumHeight(185)
    self.calendar.clicked.connect(self._on_calendar)
    cal_v.addWidget(self.calendar)
    side.addWidget(cal_grp)

    # ── 수급 피크 ────────────────────────────────────────────
    pk_grp = QGroupBox("수급 피크 검색")
    pk_v = QVBoxLayout(pk_grp)
    pk_v.setSpacing(3); pk_v.setContentsMargins(6, 4, 6, 4)
    pk_v.addWidget(QLabel("① ±30분 최대"))
    p1r = QHBoxLayout(); p1r.setSpacing(3)
    self.pk1_in = QLineEdit(); self.pk1_in.setPlaceholderText("0930 또는 09:30")
    self.pk1_in.setFixedHeight(22)
    b1 = QPushButton("검색"); b1.setFixedHeight(22); b1.setFixedWidth(44)
    b1.clicked.connect(self._peak1)
    p1r.addWidget(self.pk1_in); p1r.addWidget(b1); pk_v.addLayout(p1r)
    self.pk1_lbl = QLabel("결과: ―")
    self.pk1_lbl.setWordWrap(True)
    self.pk1_lbl.setStyleSheet("color:#c62828;font-weight:bold;font-size:11px;")
    pk_v.addWidget(self.pk1_lbl)
    pk_v.addWidget(QLabel("② 구간 합산"))
    p2r = QHBoxLayout(); p2r.setSpacing(2)
    self.pk2_s = QLineEdit(); self.pk2_s.setPlaceholderText("0930")
    self.pk2_s.setFixedHeight(22)
    self.pk2_e = QLineEdit(); self.pk2_e.setPlaceholderText("1030")
    self.pk2_e.setFixedHeight(22)
    b2 = QPushButton("합산"); b2.setFixedHeight(22); b2.setFixedWidth(44)
    b2.clicked.connect(self._peak2)
    p2r.addWidget(self.pk2_s); p2r.addWidget(QLabel("~"))
    p2r.addWidget(self.pk2_e); p2r.addWidget(b2); pk_v.addLayout(p2r)
    self.pk2_lbl = QLabel("합산: ―")
    self.pk2_lbl.setWordWrap(True)
    self.pk2_lbl.setStyleSheet("color:#1b5e20;font-weight:bold;font-size:11px;")
    pk_v.addWidget(self.pk2_lbl)
    pk_v.addWidget(QLabel("③ 테이블 다중선택"))
    self.pk3_lbl = QLabel("선택 합산: 0.00억")
    self.pk3_lbl.setWordWrap(True)
    self.pk3_lbl.setStyleSheet(
        "font-weight:bold;font-size:12px;"
        "border:1px solid #9c27b0;padding:3px;border-radius:4px;")
    pk_v.addWidget(self.pk3_lbl)
    side.addWidget(pk_grp)

    # ── 일봉 추가 보기 ───────────────────────────────────────
    side.addWidget(_make_sep())
    self.btn_daily = QPushButton("📈 일봉 추가 보기")
    self.btn_daily.setCheckable(True); self.btn_daily.setChecked(False)
    self.btn_daily.setFixedHeight(30)
    self.btn_daily.setToolTip(
        "캘린더 날짜 기준 일봉 차트를 표시합니다.\n"
        "분차트 테이블이 일시적으로 숨겨집니다.")
    self.btn_daily.setStyleSheet(
        "QPushButton{background:#1c2a1c;color:#aaa;"
        "border:1px solid #3a5a3a;border-radius:3px;font-weight:bold;padding:4px 8px;}"
        "QPushButton:checked{background:#1a3a2a;color:#26a69a;"
        "border:1px solid #26a69a;}")
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
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    sep.setStyleSheet("color:#333344;margin:2px 0;")
    return sep