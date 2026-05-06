"""
chart_build_main.py — 차트탭 테이블/차트 영역 UI 빌드
────────────────────────────────────────────────────────
build_tables(self)     → QSplitter (좌테이블 | 우테이블)
build_chart_area(self) → QWidget   (컨트롤바 + gfx)

v6.4 변경:
  build_tables() 상단에 daily_container 추가
  (일봉 보기 ON 시 분차트 테이블 숨기고 이 영역에 일봉 캔들 렌더링)

v6.6 변경:
  우측 상단 패널에 체크박스 토글 추가
    ☐ 미체크 → 기존 대량체결 테이블 표시
    ☑ 체크   → 조건부 주문 설정 WebEngine 패널로 전환
  _on_order_panel_toggle(checked) 핸들러 내장

v6.7 변경:
  데이터 테이블 영역 펼치기/닫기 토글 버튼 추가
    _toggle_table_panel(self) → 테이블 영역 표시/숨김
    self._tbl_panel_visible 상태 관리
    self.btn_tbl_toggle 버튼 (상단 좌측)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QSplitter, QAbstractItemView,
    QSizePolicy, QStackedWidget,
)
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from core import make_table


def build_tables(self) -> QWidget:
    """
    반환 구조 (v6.6):
    QWidget (outer)
    ├── daily_container        ← v6.4 신규, 초기 hidden
    └── _tbl_splitter
         ├── 좌 테이블 (분봉 데이터)
         └── 우 QWidget
              ├── 헤더 행 (타이틀 + 초기화버튼 + [☐ 주문 설정] 체크박스)
              ├── 로드 행 (FTD/공매도 + 파일 불러오기)
              └── _right_stack (QStackedWidget)
                   ├── page 0: table_r  (대량체결 테이블)  ← 기본
                   └── page 1: _cond_panel (조건부 주문 WebEngine)
    """
    outer   = QWidget()
    outer_v = QVBoxLayout(outer)
    outer_v.setContentsMargins(0, 0, 0, 0)
    outer_v.setSpacing(0)

    # ════════════════════════════════════════════════════
    # v6.7: 데이터 테이블 토글 버튼 행
    # ════════════════════════════════════════════════════
    tgl_row = QHBoxLayout()
    tgl_row.setContentsMargins(4, 2, 4, 2)
    tgl_row.setSpacing(4)

    self.btn_tbl_toggle = QPushButton("▲ 데이터 테이블 닫기")
    self.btn_tbl_toggle.setFixedHeight(22)
    self.btn_tbl_toggle.setCheckable(True)
    self.btn_tbl_toggle.setChecked(True)   # 초기: 펼쳐진 상태
    self.btn_tbl_toggle.setStyleSheet(
        "QPushButton{"
        "  background:#141430; color:#5dade2;"
        "  border:1px solid #2e3060; border-radius:3px;"
        "  font-size:11px; font-weight:bold;"
        "  text-align:left; padding:0 8px;}"
        "QPushButton:hover{ background:#1c1c3a; }"
        "QPushButton:checked{"
        "  background:#141430; color:#888;"
        "  border-color:#333;}"
    )
    self.btn_tbl_toggle.setToolTip(
        "데이터 테이블 영역을 펼치거나 닫습니다.\n"
        "닫으면 차트가 더 넓게 표시됩니다.")
    self.btn_tbl_toggle.clicked.connect(
        lambda checked: _toggle_table_panel(self, checked))
    tgl_row.addWidget(self.btn_tbl_toggle)
    tgl_row.addStretch()
    outer_v.addLayout(tgl_row)

    # 테이블 전체를 감싸는 컨테이너 (토글 대상)
    self._tbl_inner = QWidget()
    self._tbl_inner.setMinimumHeight(0)
    tbl_inner_v = QVBoxLayout(self._tbl_inner)
    tbl_inner_v.setContentsMargins(0, 0, 0, 0)
    tbl_inner_v.setSpacing(0)
    self._tbl_panel_visible = True

    # ════════════════════════════════════════════════════
    # v6.4: 일봉 컨테이너 (초기 hidden)
    # ════════════════════════════════════════════════════
    self.daily_container = QWidget()
    self.daily_container.setSizePolicy(
        QSizePolicy.Expanding, QSizePolicy.Expanding)
    daily_v = QVBoxLayout(self.daily_container)
    daily_v.setContentsMargins(2, 2, 2, 2)
    daily_v.setSpacing(2)

    _ph = QLabel("캘린더 날짜를 선택 후\n📈 일봉 추가 보기를 눌러주세요.")
    _ph.setAlignment(Qt.AlignCenter)
    _ph.setStyleSheet(
        "color:#556655;font-size:13px;"
        "background:#151f15;border-radius:4px;")
    daily_v.addWidget(_ph)
    self.daily_container.hide()
    tbl_inner_v.addWidget(self.daily_container)   # ← outer_v → tbl_inner_v

    # ── 분차트 테이블 스플리터 ────────────────────────────
    self._tbl_splitter = QSplitter(Qt.Horizontal)
    self._tbl_splitter.setHandleWidth(4)
    self._tbl_splitter.setStyleSheet(
        "QSplitter::handle{background:#2a2a4a;}"
        "QSplitter::handle:hover{background:#5dade2;}")
    # 상하 스플리터가 위로 최대한 올라갈 수 있도록 최소 높이 제거
    self._tbl_splitter.setMinimumHeight(0)
    outer.setMinimumHeight(0)

    # ── 좌 테이블 ─────────────────────────────────────────
    lw   = QWidget(); lbox = QVBoxLayout(lw)
    lbox.setContentsMargins(0, 0, 0, 0); lbox.setSpacing(2)
    lbox.addWidget(QLabel("▶ 데이터 테이블 (좌)"))
    self.table_l = make_table(
        ["시간(ET)", "시가", "고가", "저가", "종가", "거래대금(억)"])
    self.table_l.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_l.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_l.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_l))
    # 스플리터가 위로 자유롭게 올라가도록 최소 높이 제거
    self.table_l.setMinimumHeight(0)
    lw.setMinimumHeight(0)
    lbox.addWidget(self.table_l)
    self._tbl_splitter.addWidget(lw)

    # ── 우 패널 전체 컨테이너 ─────────────────────────────
    rw   = QWidget(); rbox = QVBoxLayout(rw)
    rbox.setContentsMargins(0, 0, 0, 0); rbox.setSpacing(2)

    # ── 헤더 행 (타이틀 + 초기화 + 주문설정 체크박스) ─────
    rtitle_row = QHBoxLayout(); rtitle_row.setSpacing(6)
    rtitle_row.addWidget(
        QLabel("▶ 대량체결 / FTD / 공매도 테이블 (우)"))
    rtitle_row.addStretch()

    # ── v6.6: 주문 설정 토글 체크박스 ─────────────────────
    self.chk_order_panel = QCheckBox("⚙ 주문 설정")
    self.chk_order_panel.setToolTip(
        "체크: 조건부 주문 설정 패널 표시\n"
        "미체크: 대량 체결 테이블 표시")
    self.chk_order_panel.setStyleSheet(
        "QCheckBox{ color:#FF8C00; font-weight:bold; font-size:11px; }"
        "QCheckBox::indicator{ width:14px; height:14px; }"
        "QCheckBox::indicator:unchecked{"
        "  border:1px solid #7a5a1a; border-radius:3px;"
        "  background:#1a1a0a; }"
        "QCheckBox::indicator:checked{"
        "  border:1px solid #FF8C00; border-radius:3px;"
        "  background:#3a2a0a; }"
    )
    self.chk_order_panel.stateChanged.connect(
        lambda state: _on_order_panel_toggle(self, bool(state)))
    rtitle_row.addWidget(self.chk_order_panel)

    btn_clr = QPushButton("초기화")
    btn_clr.setFixedWidth(60); btn_clr.setFixedHeight(22)
    btn_clr.clicked.connect(self._clr_right)
    rtitle_row.addWidget(btn_clr)
    rbox.addLayout(rtitle_row)

    # ── 로드 행 (FTD / 공매도 파일) ──────────────────────
    load_row = QHBoxLayout(); load_row.setSpacing(4)
    self.file_type_combo = QComboBox()
    self.file_type_combo.addItems(["FTD (미결제)", "공매도 (Short Volume)"])
    self.file_type_combo.setFixedWidth(155)
    self.file_type_combo.setFixedHeight(22)
    load_row.addWidget(self.file_type_combo)
    self.file_sym_in = QLineEdit()
    self.file_sym_in.setPlaceholderText("종목 (예: spy)")
    self.file_sym_in.setFixedWidth(80)
    self.file_sym_in.setFixedHeight(22)
    load_row.addWidget(self.file_sym_in)
    btn_load = QPushButton("📂 불러오기")
    btn_load.setFixedWidth(85); btn_load.setFixedHeight(22)
    btn_load.clicked.connect(self._load_aux_file)
    load_row.addWidget(btn_load)
    self.file_status_lbl = QLabel("")
    self.file_status_lbl.setStyleSheet("font-size:11px;color:gray;")
    load_row.addWidget(self.file_status_lbl)
    load_row.addStretch()
    rbox.addLayout(load_row)

    # ── QStackedWidget (테이블 ↔ 주문 패널) ──────────────
    self._right_stack = QStackedWidget()

    # page 0 — 대량체결 테이블 (기존)
    self.table_r = make_table(
        ["시간(ET)", "시가", "고가", "저가", "종가", "거래대금(억)", "구분"])
    self.table_r.setSelectionMode(QAbstractItemView.MultiSelection)
    self.table_r.setSelectionBehavior(QAbstractItemView.SelectRows)
    self.table_r.itemSelectionChanged.connect(
        lambda: self._update_peak3(self.table_r))
    # 스플리터가 위로 자유롭게 올라가도록 최소 높이 제거
    self.table_r.setMinimumHeight(0)
    rw.setMinimumHeight(0)
    self._right_stack.addWidget(self.table_r)       # index 0

    # page 1 — 조건부 주문 WebEngine 패널
    try:
        from chart_condition_order import build_condition_panel
        self._cond_panel = build_condition_panel(self.mw)
    except Exception as e:
        print(f"[build_main] 조건부 주문 패널 로드 실패: {e}")
        _err = QLabel(f"⚠ chart_condition_order 로드 실패\n{e}")
        _err.setStyleSheet("color:#ff5252;font-size:11px;padding:8px;")
        _err.setAlignment(Qt.AlignCenter)
        self._cond_panel = _err

    self._right_stack.addWidget(self._cond_panel)   # index 1
    self._right_stack.setCurrentIndex(0)            # 기본: 테이블

    rbox.addWidget(self._right_stack, 1)            # stretch=1
    self._tbl_splitter.addWidget(rw)
    self._tbl_splitter.setSizes([500, 500])

    tbl_inner_v.addWidget(self._tbl_splitter)   # ← tbl_inner에 추가
    outer_v.addWidget(self._tbl_inner)           # ← outer에 inner 추가
    return outer


# ── 토글 핸들러 ──────────────────────────────────────────────
def _on_order_panel_toggle(self, checked: bool):
    """
    체크박스 상태 변경 시 호출.
    checked=True  → 조건부 주문 패널 (page 1)
    checked=False → 대량체결 테이블  (page 0)
    """
    self._right_stack.setCurrentIndex(1 if checked else 0)

    # 로드 행(FTD/파일) 은 테이블 모드일 때만 의미있으므로 시인성 처리
    _load_visible = not checked
    self.file_type_combo.setVisible(_load_visible)
    self.file_sym_in.setVisible(_load_visible)
    self.file_status_lbl.setVisible(_load_visible)

    # 체크박스 색상 업데이트
    if checked:
        self.chk_order_panel.setStyleSheet(
            "QCheckBox{ color:#FF8C00; font-weight:bold; font-size:11px; }"
            "QCheckBox::indicator{ width:14px; height:14px; }"
            "QCheckBox::indicator:checked{"
            "  border:1px solid #FF8C00; border-radius:3px;"
            "  background:#3a2a0a; }"
        )
    else:
        self.chk_order_panel.setStyleSheet(
            "QCheckBox{ color:#888; font-weight:bold; font-size:11px; }"
            "QCheckBox::indicator{ width:14px; height:14px; }"
            "QCheckBox::indicator:unchecked{"
            "  border:1px solid #3a3a3a; border-radius:3px;"
            "  background:#1a1a1a; }"
        )


# ── 데이터 테이블 토글 핸들러 (v6.7) ─────────────────────────
def _toggle_table_panel(self, checked: bool):
    """
    데이터 테이블 영역 펼치기 / 닫기.
    checked=True  → 펼쳐진 상태 (버튼이 눌린=체크됨)
    checked=False → 닫힌 상태
    """
    inner = getattr(self, "_tbl_inner", None)
    if inner is None:
        return

    btn = getattr(self, "btn_tbl_toggle", None)

    if checked:
        # 펼치기
        inner.show()
        self._tbl_panel_visible = True
        if btn:
            btn.setText("▲ 데이터 테이블 닫기")
        # 스플리터 비율 복원 (테이블 280 : 차트 520)
        try:
            self._v_splitter.setSizes([280, 520])
        except Exception:
            pass
    else:
        # 닫기 — 현재 스플리터 크기 저장 후 테이블 0으로
        inner.hide()
        self._tbl_panel_visible = False
        if btn:
            btn.setText("▼ 데이터 테이블 열기")
        # 스플리터에서 테이블 영역 높이를 0으로 → 차트가 전체 차지
        try:
            total = sum(self._v_splitter.sizes())
            self._v_splitter.setSizes([0, total])
        except Exception:
            pass


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