"""
core_ui.py — 공통 UI 헬퍼 / _ResizableFrame / GridTab
core.py 300줄 초과로 분리.
"""
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QPushButton, QSlider, QSizeGrip, QFrame,
)
from PyQt5.QtCore import Qt, QObject
from PyQt5.QtGui import QFont, QColor, QBrush

from core import DEFAULT_FONT_SIZE

# ══════════════════════════════════════════════════════════════
# 7. 공통 UI 헬퍼
# ══════════════════════════════════════════════════════════════

# 전역 테이블 목록 (다크모드 전환 시 일괄 테마 적용)
_all_tables: list = []

def _apply_table_theme(tbl: QTableWidget, dark: bool = True):
    """테이블에 다크/라이트 테마 QSS 직접 적용 — 부모 stylesheet 오염 차단."""
    if dark:
        tbl.setStyleSheet(
            "QTableWidget{"
            "background:#08080f;color:#dde0f0;"
            "gridline-color:#1e1e3a;border:1px solid #2e3060;"
            "alternate-background-color:#0c0c20;}"
            "QTableWidget::item{padding:2px;color:#dde0f0;}"
            "QTableWidget::item:selected{background:#1c3a6a;color:#ffffff;}"
            "QHeaderView::section{"
            "background:#141430;color:#5dade2;"
            "border:1px solid #1e1e3a;padding:3px;}"
        )
    else:
        tbl.setStyleSheet(
            "QTableWidget{"
            "background:#ffffff;color:#111111;"
            "gridline-color:#cccccc;border:1px solid #bbbbbb;"
            "alternate-background-color:#f5f7fa;}"
            "QTableWidget::item{padding:2px;color:#111111;}"
            "QTableWidget::item:selected{background:#bbdefb;color:#000000;}"
            "QHeaderView::section{"
            "background:#e3f2fd;color:#1565c0;"
            "border:1px solid #bbbbbb;padding:3px;}"
        )

def make_table(headers: list, rows: int = 0) -> QTableWidget:
    """기본 스타일 테이블 생성 (다크모드 자동 대응, 전역 목록에 등록)"""
    t = QTableWidget(rows, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setAlternatingRowColors(True)
    _apply_table_theme(t, dark=True)
    _all_tables.append(t)
    return t

def tbl_set(tbl: QTableWidget, row: int, col: int,
            text: str, color: str = None):
    """테이블 셀 값 설정"""
    item = tbl.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter)
        tbl.setItem(row, col, item)
    item.setText(str(text))
    if color:
        item.setForeground(QBrush(QColor(color)))

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════════════════════
# 8. 그리드 탭 베이스 (12×4 엑셀 좌표) + 위젯 리사이즈
# ══════════════════════════════════════════════════════════════

_BTN_SS = (
    "QPushButton{background:#1a1a3a;color:#5dade2;border:1px solid #2e3060;"
    "border-radius:2px;font-size:8px;padding:0px;}"
    "QPushButton:hover{background:#2a2a5a;}"
)

class _FloatWin(QWidget):
    """위젯을 독립 플로팅 창으로 띄우는 래퍼."""
    def __init__(self, inner: QWidget, title: str, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(title)
        self.resize(600, 400)
        self.setStyleSheet("background:#0e0e1a;color:#dde0f0;")
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 4)
        self._inner = inner
        inner.setParent(self)
        vl.addWidget(inner)

    def closeEvent(self, ev):
        """창 닫으면 inner 위젯을 원래 frame으로 돌려보냄."""
        if hasattr(self, '_on_close_cb') and self._on_close_cb:
            self._on_close_cb(self._inner)
        ev.accept()


class _ResizableFrame(QFrame):
    """
    각 위젯 블록 래퍼.
    상단 미니바 버튼:
      ←  → : 열(가로) stretch 감소/증가  (0.2 단위, 범위 0.2~20)
      ↑  ↓ : 행(세로) stretch 감소/증가  (0.2 단위, 범위 0.2~20)
      ⤢    : 플로팅 팝업 창으로 분리
      ▲    : 접기  /  ▼ : 펼치기(복구)
    """
    _COLLAPSED_H  = 18
    _STRETCH_MIN  = 2     # ×10 스케일 → 실제 0.2
    _STRETCH_MAX  = 200   # ×10 스케일 → 실제 20.0
    _STRETCH_STEP = 2     # ×10 스케일 → 실제 0.2 단위
    _SCALE        = 10    # QGridLayout은 int만 받으므로 10배 스케일

    def __init__(self, inner: QWidget, coord_txt: str,
                 grid_ref, row: int, col: int, rspan: int, cspan: int,
                 parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "border:1px solid #1e2050;border-radius:3px;background:transparent;")
        self._collapsed    = False
        self._normal_min_h = 0
        self._grid_ref     = grid_ref
        self._row          = row
        self._col          = col
        self._rspan        = rspan
        self._cspan        = cspan
        self._float_win    = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 1, 2, 1)
        outer.setSpacing(0)

        # ── 상단 미니바 ──────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(18)
        bar.setStyleSheet("background:transparent;border:none;")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(2, 0, 2, 0)
        bh.setSpacing(1)

        coord_lbl = QLabel(coord_txt)
        coord_lbl.setStyleSheet(
            "color:#3a4060;font-size:8px;font-weight:bold;"
            "border:none;background:transparent;")
        bh.addWidget(coord_lbl)
        bh.addStretch()

        def _btn(text, tip, cb):
            b = QPushButton(text)
            b.setFixedSize(16, 14)
            b.setStyleSheet(_BTN_SS)
            b.setToolTip(tip)
            b.clicked.connect(cb)
            return b

        bh.addWidget(_btn("←", "가로 축소 (0.2단위)",
                          lambda: self._adj_col(-self._STRETCH_STEP)))
        bh.addWidget(_btn("→", "가로 확장 (0.2단위)",
                          lambda: self._adj_col(+self._STRETCH_STEP)))
        bh.addWidget(_btn("↑", "세로 축소 (0.2단위)",
                          lambda: self._adj_row(-self._STRETCH_STEP)))
        bh.addWidget(_btn("↓", "세로 확장 (0.2단위)",
                          lambda: self._adj_row(+self._STRETCH_STEP)))

        self._btn_float = _btn("⤢", "팝업 창으로 분리", self._on_float)
        bh.addWidget(self._btn_float)

        self._btn_toggle = _btn("▲", "접기", self._on_toggle)
        bh.addWidget(self._btn_toggle)

        outer.addWidget(bar)

        # ── 내용 위젯 ────────────────────────────────────────
        self._inner = inner
        outer.addWidget(inner, 1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ── stretch 조절 헬퍼 ────────────────────────────────────
    def _cur_col(self, c: int) -> int:
        v = self._grid_ref.columnStretch(c)
        return v if v > 0 else self._SCALE  # 기본값 1.0 (=10)

    def _cur_row(self, r: int) -> int:
        v = self._grid_ref.rowStretch(r)
        return v if v > 0 else self._SCALE

    def _adj_col(self, delta: int):
        g = self._grid_ref
        for c in range(self._col, self._col + self._cspan):
            nxt = max(self._STRETCH_MIN,
                      min(self._STRETCH_MAX, self._cur_col(c) + delta))
            g.setColumnStretch(c, nxt)

    def _adj_row(self, delta: int):
        g = self._grid_ref
        for r in range(self._row, self._row + self._rspan):
            nxt = max(self._STRETCH_MIN,
                      min(self._STRETCH_MAX, self._cur_row(r) + delta))
            g.setRowStretch(r, nxt)

    # ── 플로팅 팝업 ──────────────────────────────────────────
    def _on_float(self):
        if self._float_win and self._float_win.isVisible():
            self._float_win.raise_()
            return
        win = _FloatWin(self._inner,
                        f"위젯 [{self._row},{self._col}]", self.window())
        win._on_close_cb = self._return_inner
        self._float_win = win
        self._btn_float.setText("◩")
        self._btn_float.setToolTip("팝업 창 올리기")
        win.show()

    def _return_inner(self, inner: QWidget):
        inner.setParent(self)
        self.layout().insertWidget(1, inner, 1)
        self._btn_float.setText("⤢")
        self._btn_float.setToolTip("팝업 창으로 분리")
        self._float_win = None

    # ── 접기(▲) / 펼치기 복구(▼) ────────────────────────────
    def _on_toggle(self):
        if self._collapsed:
            # ▼ 클릭 → 펼치기 (복구)
            self._collapsed = False
            self._btn_toggle.setText("▲")
            self._btn_toggle.setToolTip("접기")
            self._inner.setVisible(True)
            self.setMaximumHeight(16777215)
            if self._normal_min_h > 0:
                self.setMinimumHeight(0)   # 제약 해제 후 레이아웃이 자연 크기로
        else:
            # ▲ 클릭 → 접기
            self._normal_min_h = self.height()
            self._collapsed = True
            self._btn_toggle.setText("▼")
            self._btn_toggle.setToolTip("펼치기 (복구)")
            self._inner.setVisible(False)
            self.setFixedHeight(self._COLLAPSED_H)


class GridTab(QWidget):
    """
    12열 × N행 그리드 베이스.
    add(widget, row, col, rspan, cspan) → _ResizableFrame 으로 배치.
    상단 미니바:  ← →(가로stretch)  ↑ ↓(세로stretch)  ⤢(팝업)  ▲(접기)
    """
    ROWS = 4
    COLS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setSpacing(3)
        self._grid.setContentsMargins(4, 4, 4, 4)
        for c in range(self.COLS): self._grid.setColumnStretch(c, 1)
        for r in range(self.ROWS): self._grid.setRowStretch(r, 1)

    def add(self, widget: QWidget, row: int, col: int,
            rspan: int = 1, cspan: int = 1) -> QWidget:
        frame = _ResizableFrame(
            widget, f"[{row},{col}]",
            self._grid, row, col, rspan, cspan)
        self._grid.addWidget(frame, row, col, rspan, cspan)
        return frame


# ══════════════════════════════════════════════════════════════
# 9. 폰트 조절 바 + 탭 래퍼
# ══════════════════════════════════════════════════════════════


