"""
greeks_render.py — Greeks Matrix 테이블 렌더링 유틸
════════════════════════════════════════════════════════════════
색상 계산, 셀 스타일, 헤더 초기화 함수 모음.
GreeksGrid 와 ReplayPanel 양쪽에서 공용으로 사용.
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QFont, QColor, QBrush
from typing          import Dict, List, Optional, Set

# ── 열 인덱스 ──────────────────────────────────────────────────
C_DELTA, C_GAMMA, C_IV, C_VANNA = 0, 1, 2, 3
COL_STRIKE = 4
P_DELTA, P_GAMMA, P_IV, P_VANNA = 5, 6, 7, 8
NCOLS = 9

COL_LABELS = [
    "C Δ Delta", "C Γ Gamma", "C IV", "C Vanna",
    "⚡ STRIKE",
    "P Δ Delta", "P Γ Gamma", "P IV", "P Vanna",
]

# ── 색상 상수 ─────────────────────────────────────────────────
ATM_BG         = QColor(60, 55, 0)
ATM_FG         = QColor(255, 220, 50)
CALL_HDR       = "#1a4a8a"
PUT_HDR        = "#5a1a1a"
STRIKE_HDR     = "#1a2a1a"
SPIKE_BG       = QColor(180, 20, 20, 160)   # 급변동 행 배경


# ══════════════════════════════════════════════════════════════
# 색상 계산
# ══════════════════════════════════════════════════════════════
def gamma_bg(gamma: float, max_gamma: float) -> Optional[QColor]:
    """gamma 절대값 비율 → 보라 계열 heatmap 배경."""
    if max_gamma <= 0:
        return None
    ratio = min(abs(gamma) / max_gamma, 1.0)
    if ratio < 0.05:
        return None
    alpha = int(30 + ratio * 160)
    return QColor(90, 40, 180, alpha)


def delta_color(delta: float, side: str) -> QColor:
    """delta 수치 → 글자색 (Call 파랑, Put 빨강)."""
    abs_d = abs(delta)
    if side == "C":
        return QColor(80, int(120 + abs_d * 135), 255)
    return QColor(int(120 + abs_d * 135), 80, 80)


def arrow_str(curr: float, prev: float, thr: float = 1e-6) -> str:
    diff = curr - prev
    if abs(diff) < thr:
        return ""
    return "▲" if diff > 0 else "▼"


def arrow_color(curr: float, prev: float) -> Optional[QColor]:
    diff = curr - prev
    if abs(diff) < 1e-6:
        return None
    return QColor(255, 80, 80) if diff > 0 else QColor(80, 140, 255)


# ══════════════════════════════════════════════════════════════
# 테이블 초기화
# ══════════════════════════════════════════════════════════════
def init_table(tbl: QTableWidget):
    """헤더 스타일 + 공통 옵션 적용."""
    tbl.setColumnCount(NCOLS)
    tbl.setHorizontalHeaderLabels(COL_LABELS)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setAlternatingRowColors(False)
    tbl.setStyleSheet("""
        QTableWidget{background:#08080f;gridline-color:#1a1a3a;
                     border:1px solid #2e3060;}
        QTableWidget::item{padding:3px 6px;}
        QTableWidget::item:selected{background:#1c3a6a;}
        QHeaderView::section{padding:5px 4px;font-weight:bold;
                              border:1px solid #1e1e3a;}
    """)
    _style_header(tbl)


def _style_header(tbl: QTableWidget):
    for col in range(NCOLS):
        item = QTableWidgetItem(COL_LABELS[col])
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if col < COL_STRIKE:
            item.setBackground(QBrush(QColor(CALL_HDR)))
            item.setForeground(QBrush(QColor("#88ccff")))
        elif col == COL_STRIKE:
            item.setBackground(QBrush(QColor(STRIKE_HDR)))
            item.setForeground(QBrush(QColor("#aaffaa")))
        else:
            item.setBackground(QBrush(QColor(PUT_HDR)))
            item.setForeground(QBrush(QColor("#ffaaaa")))
        tbl.setHorizontalHeaderItem(col, item)


def init_row(tbl: QTableWidget, row: int, strike: float, atm_strike: float):
    """행 초기화 (STRIKE 셀 + ATM 하이라이트)."""
    is_atm = (strike == atm_strike)
    for col in range(NCOLS):
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if col == COL_STRIKE:
            item.setText(str(int(strike)))
            item.setFont(QFont("Arial", 0, QFont.Bold))
        else:
            item.setText("―")
        if is_atm:
            item.setBackground(QBrush(ATM_BG))
            item.setForeground(QBrush(ATM_FG))
        tbl.setItem(row, col, item)
    tbl.setRowHidden(row, False)


# ══════════════════════════════════════════════════════════════
# 셀 1개 렌더링
# ══════════════════════════════════════════════════════════════
def set_cell(tbl: QTableWidget,
             row: int, col: int,
             value: float, side: str, key: str,
             max_gamma: float, is_atm: bool,
             prev: Optional[float] = None,
             fmt: str = ".4f",
             use_heatmap: bool = False,
             spike: bool = False):
    """
    셀 값·색상·화살표·heatmap 일괄 적용.
    spike=True 이면 빨간 배경 (급변동 경고).
    """
    item = tbl.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        tbl.setItem(row, col, item)

    # 텍스트 + 화살표
    try:
        text = f"{value:{fmt}}"
    except (ValueError, TypeError):
        text = "―"

    a_str = arrow_str(value, prev) if prev is not None else ""
    a_col = arrow_color(value, prev) if prev is not None else None
    if a_str:
        text = f"{text} {a_str}"
    item.setText(text)

    # 폰트
    f = QFont("Consolas", 0)
    if key == "gamma":
        f.setBold(True)
    item.setFont(f)

    # 배경
    if spike:
        item.setBackground(QBrush(SPIKE_BG))
    elif is_atm:
        item.setBackground(QBrush(ATM_BG))
    elif use_heatmap:
        bg = gamma_bg(value, max_gamma)
        item.setBackground(QBrush(bg) if bg else QBrush(QColor(8, 8, 15)))
    else:
        item.setBackground(QBrush(QColor(8, 8, 15)))

    # 글자색
    if a_col and not is_atm and not spike:
        item.setForeground(QBrush(a_col))
    elif is_atm or spike:
        item.setForeground(QBrush(ATM_FG if is_atm else QColor(255, 200, 200)))
    elif key == "delta":
        item.setForeground(QBrush(delta_color(value, side)))
    elif key == "gamma":
        item.setForeground(QBrush(QColor(160, 255, 120)))
    elif key == "iv":
        item.setForeground(QBrush(QColor(200, 180, 255)))
    elif key == "vanna":
        item.setForeground(QBrush(QColor(255, 200, 100)))


# ══════════════════════════════════════════════════════════════
# 전체 행 렌더링 (cell_data 딕셔너리 → 테이블)
# ══════════════════════════════════════════════════════════════
def render_rows(tbl: QTableWidget,
                strikes: List[float], atm_strike: float,
                cell_data: dict, prev: dict,
                spike_strikes: Optional[Set] = None):
    """
    cell_data: {(row, 'C'|'P'): {delta, gamma, iv, vanna}} 
    prev:      {(strike, side, key): float}
    spike_strikes: 급변동 감지된 strike 집합
    """
    spike_strikes = spike_strikes or set()
    all_gammas = [d["gamma"] for d in cell_data.values() if d.get("gamma")]
    max_g = max(all_gammas) if all_gammas else 1.0

    for r, st in enumerate(strikes):
        is_atm = (st == atm_strike)
        spike  = st in spike_strikes
        for side, col_map in (
            ("C", {C_DELTA: "delta", C_GAMMA: "gamma", C_IV: "iv", C_VANNA: "vanna"}),
            ("P", {P_DELTA: "delta", P_GAMMA: "gamma", P_IV: "iv", P_VANNA: "vanna"}),
        ):
            d = cell_data.get((r, side))
            if not d:
                continue
            for col, key in col_map.items():
                val  = d.get(key, 0.0)
                pv   = prev.get((st, side, key), val)
                prev[(st, side, key)] = val
                set_cell(tbl, r, col, val, side, key, max_g, is_atm,
                         prev=pv,
                         fmt=(".6f" if key == "gamma" else
                              "+.5f" if key == "vanna" else "+.4f"),
                         use_heatmap=(key == "gamma"),
                         spike=spike)
