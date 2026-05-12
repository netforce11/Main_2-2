"""
chart_build_tables.py — 테이블/스플리터 영역 빌드 (build_tables)
[분리] chart_build_main.py 에서 분리
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
from core import make_table
from chart_build_handlers import _on_order_panel_toggle, _toggle_table_panel  # noqa: F401

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


    # [분리] 우측 패널 → chart_build_right_panel.py
    from chart_build_right_panel import _build_right_panel
    rw   = QWidget(); rbox = QVBoxLayout(rw)
    rbox.setContentsMargins(0, 0, 0, 0); rbox.setSpacing(2)
    _build_right_panel(self, rw, rbox)
    self._tbl_splitter.addWidget(rw)
    self._tbl_splitter.setSizes([500, 500])

    tbl_inner_v.addWidget(self._tbl_splitter)
    outer_v.addWidget(self._tbl_inner)
    return outer
