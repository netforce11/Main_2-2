"""
kr_build_main.py — 한국 차트탭 테이블/차트 영역 UI 빌드
────────────────────────────────────────────────────────
build_tables(self)     → QWidget (일봉 컨테이너 + 분봉 스플리터)
build_chart_area(self) → QWidget (컨트롤바 + gfx)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QSplitter, QAbstractItemView,
    QSizePolicy, QComboBox,
)
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

# make_table 은 core 가 아닌 직접 구현
def _make_table(headers):
    from PyQt5.QtWidgets import QTableWidget, QHeaderView
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setStyleSheet(
        "QTableWidget{font-size:11px;}"
        "QHeaderView::section{font-size:11px;font-weight:bold;}")
    return t


def build_tables(self) -> QWidget:
    outer = QWidget()
    outer_v = QVBoxLayout(outer)
    outer_v.setContentsMargins(0, 0, 0, 0)
    outer_v.setSpacing(0)

    # 일봉 컨테이너 (초기 hidden)
    self.daily_container = QWidget()
    self.daily_container.setSizePolicy(
        QSizePolicy.Expanding, QSizePolicy.Expanding)
    daily_v = QVBoxLayout(self.daily_container)
    daily_v.setContentsMargins(2, 2, 2, 2); daily_v.setSpacing(2)
    _ph = QLabel("캘린더 날짜를 선택 후\n📈 일봉 추가 보기를 눌러주세요.")
    _ph.setAlignment(Qt.AlignCenter)
    _ph.setStyleSheet(
        "color:#556655;font-size:13px;"
        "background:#151f15;border-radius:4px;")
    daily_v.addWidget(_ph)
    self.daily_container.hide()
    outer_v.addWidget(self.daily_container)

    # 분봉 테이블 스플리터
    self._tbl_splitter = QSplitter(Qt.Horizontal)
    self._tbl_splitter.setHandleWidth(4)
    self._tbl_splitter.setStyleSheet(
        "QSplitter::handle{background:#2a2a4a;}"
        "QSplitter::handle:hover{background:#5dade2;}")

    # 좌측: 데이터 테이블
    lw = QWidget(); lbox = QVBoxLayout(lw)
    lbox.setContentsMargins(0, 0, 0, 0); lbox.setSpacing(2)
    lbox.addWidget(QLabel("▶ 데이터 테이블 (좌)"))
    self.table_l = _make_table(["시간(KST)", "시가", "고가", "저가", "종가", "거래대금(억)"])
    self.table_l.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_l.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_l.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_l))
    lbox.addWidget(self.table_l)
    self._tbl_splitter.addWidget(lw)

    # 우측: 대량체결 테이블
    rw = QWidget(); rbox = QVBoxLayout(rw)
    rbox.setContentsMargins(0, 0, 0, 0); rbox.setSpacing(2)
    rtitle_row = QHBoxLayout()
    rtitle_row.addWidget(QLabel("▶ 대량체결 / 수급 테이블 (우)"))
    rtitle_row.addStretch()
    btn_clr = QPushButton("초기화"); btn_clr.setFixedWidth(60); btn_clr.setFixedHeight(22)
    btn_clr.clicked.connect(self._clr_right)
    rtitle_row.addWidget(btn_clr)
    rbox.addLayout(rtitle_row)
    self.table_r = _make_table(["시간(KST)", "시가", "고가", "저가", "종가", "거래대금(억)", "구분"])
    self.table_r.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_r.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_r.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_r))
    rbox.addWidget(self.table_r)
    self._tbl_splitter.addWidget(rw)
    self._tbl_splitter.setSizes([500, 500])

    outer_v.addWidget(self._tbl_splitter)
    return outer


def build_chart_area(self) -> QWidget:
    chart_w = QWidget(); chart_v = QVBoxLayout(chart_w)
    chart_v.setContentsMargins(0, 0, 0, 0); chart_v.setSpacing(2)

    if not PG:
        chart_v.addWidget(QLabel("pip install pyqtgraph"))
        return chart_w

    # ── 컨트롤 바 ─────────────────────────────────────────────
    line_bar = QHBoxLayout(); line_bar.setSpacing(6)

    self.btn_hline = QPushButton("✏ 가로 라인")
    self.btn_hline.setCheckable(True); self.btn_hline.setFixedHeight(24)
    self.btn_hline.setStyleSheet(
        "QPushButton{background:#1c1c3a;color:#aaa;"
        "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
        "QPushButton:checked{background:#2a4a2a;color:#00e676;border-color:#00e676;}")
    line_bar.addWidget(self.btn_hline)

    self.time_marker_in = QLineEdit()
    self.time_marker_in.setPlaceholderText("0930 또는 09:30")
    self.time_marker_in.setFixedWidth(110); self.time_marker_in.setFixedHeight(24)
    btn_marker = QPushButton("▼ 마커"); btn_marker.setFixedHeight(24); btn_marker.setFixedWidth(58)
    btn_marker.clicked.connect(self._add_time_marker)
    line_bar.addWidget(self.time_marker_in); line_bar.addWidget(btn_marker)

    self.btn_capture = QPushButton("📷 캡쳐")
    self.btn_capture.setFixedHeight(24); self.btn_capture.setFixedWidth(64)
    self.btn_capture.setStyleSheet(
        "QPushButton{background:#1a2a1a;color:#88ff88;"
        "border:1px solid #2a6a2a;border-radius:3px;padding:2px 6px;}"
        "QPushButton:hover{background:#2a4a2a;color:#aaffaa;}")
    self.btn_capture.clicked.connect(self.capture_chart)
    line_bar.addWidget(self.btn_capture)

    self.btn_label = QPushButton("🔤 레이블")
    self.btn_label.setCheckable(True); self.btn_label.setFixedHeight(24)
    self.btn_label.setStyleSheet(
        "QPushButton{background:#1c1c3a;color:#aaa;"
        "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
        "QPushButton:checked{background:#2a2a4a;color:#00e5ff;border-color:#00e5ff;}")
    line_bar.addWidget(self.btn_label)

    self.label_combo = QComboBox()
    self.label_combo.addItems(["1","2","3","4","5","A","B","C","D","E"])
    self.label_combo.setFixedWidth(52); self.label_combo.setFixedHeight(24)
    line_bar.addWidget(self.label_combo)

    btn_del_labels = QPushButton("🗑"); btn_del_labels.setFixedHeight(24); btn_del_labels.setFixedWidth(28)
    btn_del_labels.setStyleSheet(
        "QPushButton{background:#2a1a1a;color:#ff6666;"
        "border:1px solid #6a2a2a;border-radius:3px;}"
        "QPushButton:hover{background:#3a2a2a;color:#ff9999;}")
    btn_del_labels.clicked.connect(self._del_labels)
    line_bar.addWidget(btn_del_labels)

    self.lbl_hline_info = QLabel("라인/마커/레이블: 체크 해제로 삭제")
    self.lbl_hline_info.setStyleSheet("color:#666;font-size:11px;")
    line_bar.addWidget(self.lbl_hline_info)
    line_bar.addStretch()
    chart_v.addLayout(line_bar)

    # ── 체크박스 바 ───────────────────────────────────────────
    chk_bar = QHBoxLayout(); chk_bar.setSpacing(3)
    chk_bar.addWidget(QLabel("라인:"))
    self._hline_slots = 10; self._hline_chks = []
    for i in range(self._hline_slots):
        chk = QCheckBox(str(i+1)); chk.setEnabled(False); chk.setFixedWidth(34)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.stateChanged.connect(
            lambda state, idx=i: self._on_hline_chk(idx, state))
        chk_bar.addWidget(chk); self._hline_chks.append(chk)

    chk_bar.addWidget(QLabel("  마커:"))
    self._marker_slots = 5; self._marker_chks = []
    for i in range(self._marker_slots):
        chk = QCheckBox(str(i+1)); chk.setEnabled(False); chk.setFixedWidth(34)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.stateChanged.connect(
            lambda state, idx=i: self._on_marker_chk(idx, state))
        chk_bar.addWidget(chk); self._marker_chks.append(chk)

    chk_bar.addWidget(QLabel("  레이블:"))
    self._label_chks = []
    LABEL_ITEMS = ["1","2","3","4","5","A","B","C","D","E"]
    for i, lbl in enumerate(LABEL_ITEMS):
        chk = QCheckBox(lbl); chk.setEnabled(False); chk.setFixedWidth(30)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.stateChanged.connect(
            lambda state, idx=i: self._on_label_chk(idx, state))
        chk_bar.addWidget(chk); self._label_chks.append(chk)

    chk_bar.addStretch()
    self.lbl_zoom_time = QLabel("")
    self.lbl_zoom_time.setStyleSheet(
        "color:#ffd700;font-size:11px;font-weight:bold;border:none;")
    chk_bar.addWidget(self.lbl_zoom_time)
    chart_v.addLayout(chk_bar)

    # 상태 초기화
    self._hlines = {}; self._time_markers = {}; self._chart_labels = {}

    self.gfx = pg.GraphicsLayoutWidget()
    self.p1  = self.gfx.addPlot(row=0, col=0)
    self.p2  = self.gfx.addPlot(row=1, col=0)
    self.p2.setFixedHeight(110); self.p2.setXLink(self.p1)
    self.p1.scene().sigMouseClicked.connect(self._on_chart_click)
    self.p1.getViewBox().sigRangeChanged.connect(self._on_range_changed)
    chart_v.addWidget(self.gfx, 1)
    return chart_w


def _clr_right(self):
    self.table_r.setRowCount(0)
