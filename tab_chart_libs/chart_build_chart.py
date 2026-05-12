"""
chart_build_chart.py — 차트 영역 빌드 (build_chart_area)
[분리] chart_build_main.py 에서 분리
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox,
)
from PyQt5.QtCore import Qt
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False
from chart_labels import LABEL_ITEMS

def build_chart_area(self) -> QWidget:
    chart_w = QWidget(); chart_v = QVBoxLayout(chart_w)
    chart_v.setContentsMargins(0, 0, 0, 0); chart_v.setSpacing(2)

    if PG:
        # ── 컨트롤 바 ─────────────────────────────────────
        line_bar = QHBoxLayout(); line_bar.setSpacing(6)

        # ✏ 가로 라인 버튼
        self.btn_hline = QPushButton("✏ 가로 라인")
        self.btn_hline.setCheckable(True); self.btn_hline.setFixedHeight(24)
        self.btn_hline.setStyleSheet(
            "QPushButton{background:#1c1c3a;color:#aaa;"
            "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
            "QPushButton:checked{background:#2a4a2a;color:#00e676;"
            "border-color:#00e676;}")
        line_bar.addWidget(self.btn_hline)

        # 시간 마커 입력
        self.time_marker_in = QLineEdit()
        self.time_marker_in.setPlaceholderText("1030 또는 10:30")
        self.time_marker_in.setFixedWidth(110); self.time_marker_in.setFixedHeight(24)
        btn_marker = QPushButton("▼ 마커")
        btn_marker.setFixedHeight(24); btn_marker.setFixedWidth(58)
        btn_marker.clicked.connect(self._add_time_marker)
        line_bar.addWidget(self.time_marker_in); line_bar.addWidget(btn_marker)

        # 📷 캡쳐 버튼
        self.btn_capture = QPushButton("📷 캡쳐")
        self.btn_capture.setFixedHeight(24); self.btn_capture.setFixedWidth(64)
        self.btn_capture.setStyleSheet(
            "QPushButton{background:#1a2a1a;color:#88ff88;"
            "border:1px solid #2a6a2a;border-radius:3px;padding:2px 6px;}"
            "QPushButton:hover{background:#2a4a2a;color:#aaffaa;}")
        self.btn_capture.setToolTip(
            r"차트 캡쳐 → /home/netforce/US_Data/chart_save/날짜_시각_심볼.png")
        self.btn_capture.clicked.connect(self.capture_chart)
        line_bar.addWidget(self.btn_capture)

        # ── 🔤 레이블 버튼 + 콤보 + 전체삭제 ─────────────
        self.btn_label = QPushButton("🔤 레이블")
        self.btn_label.setCheckable(True); self.btn_label.setFixedHeight(24)
        self.btn_label.setStyleSheet(
            "QPushButton{background:#1c1c3a;color:#aaa;"
            "border:1px solid #3a3a7a;border-radius:3px;padding:2px 8px;}"
            "QPushButton:checked{background:#2a2a4a;color:#00e5ff;"
            "border-color:#00e5ff;}"
            "QPushButton:checked:hover{background:#2a3a4a;}")
        self.btn_label.setToolTip(
            "ON 상태에서 차트 클릭 → 선택한 레이블(숫자/문자)을 해당 위치에 추가")
        line_bar.addWidget(self.btn_label)

        self.label_combo = QComboBox()
        self.label_combo.addItems(["1", "2", "3", "4", "5", "A", "B", "C", "D", "E"])
        self.label_combo.setFixedWidth(52); self.label_combo.setFixedHeight(24)
        self.label_combo.setToolTip("차트에 추가할 레이블 선택")
        line_bar.addWidget(self.label_combo)

        btn_del_labels = QPushButton("🗑")
        btn_del_labels.setFixedHeight(24); btn_del_labels.setFixedWidth(28)
        btn_del_labels.setToolTip("레이블 전체 삭제")
        btn_del_labels.setStyleSheet(
            "QPushButton{background:#2a1a1a;color:#ff6666;"
            "border:1px solid #6a2a2a;border-radius:3px;}"
            "QPushButton:hover{background:#3a2a2a;color:#ff9999;}")
        btn_del_labels.clicked.connect(self._del_labels)
        line_bar.addWidget(btn_del_labels)

        self.kst_chk = QCheckBox("KST"); self.kst_chk.setFixedHeight(24)
        self.kst_chk.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;")
        self.kst_chk.stateChanged.connect(lambda _: self._update_display())
        line_bar.addWidget(self.kst_chk)

        self.lbl_hline_info = QLabel("라인/마커/레이블: 체크 해제로 삭제")
        self.lbl_hline_info.setStyleSheet("color:#666;font-size:11px;")
        line_bar.addWidget(self.lbl_hline_info)
        line_bar.addStretch()
        chart_v.addLayout(line_bar)

        # ── 체크박스 바 ───────────────────────────────────
        chk_bar = QHBoxLayout(); chk_bar.setSpacing(3)

        chk_bar.addWidget(QLabel("라인:"))
        self._hline_slots = 10; self._hline_chks = []
        for i in range(self._hline_slots):
            chk = QCheckBox(str(i + 1))
            chk.setEnabled(False); chk.setFixedWidth(34)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.stateChanged.connect(
                lambda state, idx=i: self._on_hline_chk(idx, state))
            chk_bar.addWidget(chk); self._hline_chks.append(chk)

        chk_bar.addWidget(QLabel("  마커:"))
        self._marker_slots = 5; self._marker_chks = []
        for i in range(self._marker_slots):
            chk = QCheckBox(str(i + 1))
            chk.setEnabled(False); chk.setFixedWidth(34)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.stateChanged.connect(
                lambda state, idx=i: self._on_marker_chk(idx, state))
            chk_bar.addWidget(chk); self._marker_chks.append(chk)

        chk_bar.addWidget(QLabel("  레이블:"))
        self._label_chks = []
        from chart_labels import LABEL_ITEMS
        for i, lbl in enumerate(LABEL_ITEMS):
            chk = QCheckBox(lbl)
            chk.setEnabled(False); chk.setFixedWidth(30)
            chk.setStyleSheet("color:#444;font-size:10px;")
            chk.stateChanged.connect(
                lambda state, idx=i: self._on_label_chk(idx, state))
            chk_bar.addWidget(chk)
            self._label_chks.append(chk)

        chk_bar.addStretch()
        self.lbl_zoom_time = QLabel("")
        self.lbl_zoom_time.setStyleSheet(
            "color:#ffd700;font-size:11px;font-weight:bold;border:none;")
        chk_bar.addWidget(self.lbl_zoom_time)
        chart_v.addLayout(chk_bar)

        # 상태 초기화
        self._hlines:       dict = {}
        self._time_markers: dict = {}
        self._chart_labels: dict = {}

        self.gfx = pg.GraphicsLayoutWidget()
        self.p1  = self.gfx.addPlot(row=0, col=0)
        self.p2  = self.gfx.addPlot(row=1, col=0)
        self.p2.setFixedHeight(80); self.p2.setXLink(self.p1)
        self.p1.scene().sigMouseClicked.connect(self._on_chart_click)
        self.p1.getViewBox().sigRangeChanged.connect(self._on_range_changed)

        # ── 틱/호가 속도 인디케이터 패널 (p3) ────────────
        try:
            from chart_tick_speed import init_tick_speed
            init_tick_speed(self)
        except Exception as _e:
            print(f"[TickSpeed] init 실패: {_e}")

        chart_v.addWidget(self.gfx, 1)
    else:
        chart_v.addWidget(QLabel("pip install pyqtgraph"))

    return chart_w