"""
chart_build_main.py — 차트탭 테이블/차트 영역 UI 빌드
────────────────────────────────────────────────────────
build_tables(self)     → QSplitter (좌테이블 | 우테이블)
build_chart_area(self) → QWidget   (컨트롤바 + gfx)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QSplitter, QAbstractItemView,
)
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from core import make_table

def build_tables(self) -> QSplitter:
    self._tbl_splitter = QSplitter(Qt.Horizontal)
    self._tbl_splitter.setHandleWidth(4)
    self._tbl_splitter.setStyleSheet(
        "QSplitter::handle{background:#2a2a4a;}"
        "QSplitter::handle:hover{background:#5dade2;}")

    lw = QWidget(); lbox = QVBoxLayout(lw)
    lbox.setContentsMargins(0,0,0,0); lbox.setSpacing(2)
    lbox.addWidget(QLabel("▶ 데이터 테이블 (좌)"))
    self.table_l = make_table(["시간(ET)","시가","고가","저가","종가","거래대금(억)"])
    self.table_l.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_l.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_l.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_l))
    lbox.addWidget(self.table_l)
    self._tbl_splitter.addWidget(lw)

    rw = QWidget(); rbox = QVBoxLayout(rw)
    rbox.setContentsMargins(0,0,0,0); rbox.setSpacing(2)
    rtitle_row = QHBoxLayout()
    rtitle_row.addWidget(QLabel("▶ 대량체결 / FTD / 공매도 테이블 (우)"))
    rtitle_row.addStretch()
    btn_clr = QPushButton("초기화"); btn_clr.setFixedWidth(60); btn_clr.setFixedHeight(22)
    btn_clr.clicked.connect(self._clr_right)
    rtitle_row.addWidget(btn_clr)
    rbox.addLayout(rtitle_row)
    load_row = QHBoxLayout(); load_row.setSpacing(4)
    self.file_type_combo = QComboBox()
    self.file_type_combo.addItems(["FTD (미결제)", "공매도 (Short Volume)"])
    self.file_type_combo.setFixedWidth(155); self.file_type_combo.setFixedHeight(22)
    load_row.addWidget(self.file_type_combo)
    self.file_sym_in = QLineEdit()
    self.file_sym_in.setPlaceholderText("종목 (예: spy)")
    self.file_sym_in.setFixedWidth(80); self.file_sym_in.setFixedHeight(22)
    load_row.addWidget(self.file_sym_in)
    btn_load = QPushButton("📂 불러오기"); btn_load.setFixedWidth(85); btn_load.setFixedHeight(22)
    btn_load.clicked.connect(self._load_aux_file); load_row.addWidget(btn_load)
    self.file_status_lbl = QLabel("")
    self.file_status_lbl.setStyleSheet("font-size:11px;color:gray;")
    load_row.addWidget(self.file_status_lbl); load_row.addStretch()
    rbox.addLayout(load_row)
    self.table_r = make_table(["시간(ET)","시가","고가","저가","종가","거래대금(억)","구분"])
    self.table_r.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_r.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_r.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_r))
    rbox.addWidget(self.table_r)
    self._tbl_splitter.addWidget(rw)
    self._tbl_splitter.setSizes([500, 500])
    return self._tbl_splitter

def build_chart_area(self) -> QWidget:
    chart_w = QWidget(); chart_v = QVBoxLayout(chart_w)
    chart_v.setContentsMargins(0,0,0,0); chart_v.setSpacing(2)

    if PG:
        # ── 컨트롤 바 ─────────────────────────────────────
        line_bar = QHBoxLayout(); line_bar.setSpacing(6)
        self.btn_hline = QPushButton("✏ 가로 라인")
        self.btn_hline.setCheckable(True); self.btn_hline.setFixedHeight(24)
        self.btn_hline.setStyleSheet(
            "QPushButton{background:#1c1c3a;color:#aaa;"
            "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
            "QPushButton:checked{background:#2a4a2a;color:#00e676;"
            "border-color:#00e676;}")
        line_bar.addWidget(self.btn_hline)

        # 시간 마커 입력 — 숫자만도 입력 가능 (예: 1030)
        self.time_marker_in = QLineEdit()
        self.time_marker_in.setPlaceholderText("1030 또는 10:30")
        self.time_marker_in.setFixedWidth(110); self.time_marker_in.setFixedHeight(24)
        btn_marker = QPushButton("▼ 마커")
        btn_marker.setFixedHeight(24); btn_marker.setFixedWidth(58)
        btn_marker.clicked.connect(self._add_time_marker)
        line_bar.addWidget(self.time_marker_in); line_bar.addWidget(btn_marker)

        # 📷 캡쳐 버튼 (마커 우측) — 신규
        self.btn_capture = QPushButton("📷 캡쳐")
        self.btn_capture.setFixedHeight(24); self.btn_capture.setFixedWidth(64)
        self.btn_capture.setStyleSheet(
            "QPushButton{background:#1a2a1a;color:#88ff88;"
            "border:1px solid #2a6a2a;border-radius:3px;padding:2px 6px;}"
            "QPushButton:hover{background:#2a4a2a;color:#aaffaa;}")
        self.btn_capture.setToolTip(
            r"차트 캡쳐 → C:\data\chart_save\날짜_시각_심볼.png")
        self.btn_capture.clicked.connect(self.capture_chart)
        line_bar.addWidget(self.btn_capture)

        self.kst_chk = QCheckBox("KST"); self.kst_chk.setFixedHeight(24)
        self.kst_chk.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;")
        self.kst_chk.stateChanged.connect(lambda _: self._update_display())
        line_bar.addWidget(self.kst_chk)

        self.lbl_hline_info = QLabel("라인/마커: 체크 해제로 삭제")
        self.lbl_hline_info.setStyleSheet("color:#666;font-size:11px;")
        line_bar.addWidget(self.lbl_hline_info)
        line_bar.addStretch()
        chart_v.addLayout(line_bar)

        # ── 체크박스 바 ───────────────────────────────────
        chk_bar = QHBoxLayout(); chk_bar.setSpacing(3)
        chk_bar.addWidget(QLabel("라인:"))
        self._hline_slots = 10; self._hline_chks = []
        for i in range(self._hline_slots):
            chk = QCheckBox(str(i+1))
            chk.setEnabled(False); chk.setFixedWidth(34)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.stateChanged.connect(
                lambda state, idx=i: self._on_hline_chk(idx, state))
            chk_bar.addWidget(chk); self._hline_chks.append(chk)
        chk_bar.addWidget(QLabel("  마커:"))
        self._marker_slots = 5; self._marker_chks = []
        for i in range(self._marker_slots):
            chk = QCheckBox(str(i+1))
            chk.setEnabled(False); chk.setFixedWidth(34)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.stateChanged.connect(
                lambda state, idx=i: self._on_marker_chk(idx, state))
            chk_bar.addWidget(chk); self._marker_chks.append(chk)
        chk_bar.addStretch()
        self.lbl_zoom_time = QLabel("")
        self.lbl_zoom_time.setStyleSheet(
            "color:#ffd700;font-size:11px;font-weight:bold;border:none;")
        chk_bar.addWidget(self.lbl_zoom_time)
        chart_v.addLayout(chk_bar)

        self._hlines: dict       = {}
        self._time_markers: dict = {}

        self.gfx = pg.GraphicsLayoutWidget()
        self.p1  = self.gfx.addPlot(row=0, col=0)
        self.p2  = self.gfx.addPlot(row=1, col=0)
        self.p2.setFixedHeight(110); self.p2.setXLink(self.p1)
        self.p1.scene().sigMouseClicked.connect(self._on_chart_click)
        self.p1.getViewBox().sigRangeChanged.connect(self._on_range_changed)
        chart_v.addWidget(self.gfx, 1)
    else:
        chart_v.addWidget(QLabel("pip install pyqtgraph"))

    return chart_w
