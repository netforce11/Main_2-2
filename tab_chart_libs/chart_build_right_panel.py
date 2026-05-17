"""
chart_build_right_panel.py — 우측 테이블/주문패널 스택 빌드
[분리] chart_build_tables.py 에서 분리
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QAbstractItemView, QStackedWidget,
)
from PyQt5.QtCore import Qt
from core import make_table

def _build_right_panel(self, rw, rbox):
    """우측 패널 내부를 빌드. rw=QWidget, rbox=QVBoxLayout."""
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

    # page 1 — 조건부 주문 패널
    # [피뢰침 포착 비활성화] build_condition_panel 이 None 반환 시
    # addWidget(None) → QLayout 경고 방지: 빈 플레이스홀더로 대체
    try:
        from chart_condition_order import build_condition_panel
        _panel = build_condition_panel(self.mw)
    except Exception as e:
        print(f"[build_main] 조건부 주문 패널 로드 실패: {e}")
        _panel = None

    if _panel is None:
        # 피뢰침 비활성화 상태 — 빈 위젯으로 슬롯 채움
        _panel = QLabel("⚙ 조건부 주문 패널 (비활성화)")
        _panel.setStyleSheet(
            "color:#444; font-size:12px; padding:16px;")
        _panel.setAlignment(Qt.AlignCenter)

    self._cond_panel = _panel
    self._right_stack.addWidget(self._cond_panel)   # index 1
    self._right_stack.setCurrentIndex(0)            # 기본: 테이블

    rbox.addWidget(self._right_stack, 1)            # stretch=1
    self._tbl_splitter.addWidget(rw)
    self._tbl_splitter.setSizes([500, 500])




# [분리] 토글 핸들러 → chart_build_handlers.py
from chart_build_handlers import (  # noqa: F401
    _on_order_panel_toggle, _toggle_table_panel
)