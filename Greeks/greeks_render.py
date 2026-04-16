"""
greeks_render.py — Greeks Matrix 테이블 렌더링 유틸
════════════════════════════════════════════════════════════════
색상 계산, 셀 스타일, 헤더 초기화 함수 모음.
GreeksGrid 와 ReplayPanel 양쪽에서 공용으로 사용.

v6.6 변경:
  - ★ 리플레이 전용 확장 컬럼 추가 (REPLAY_NCOLS=19)
    C: Delta/Gamma/IV/Vanna/Bid/Ask/Mid/Theo/Mis%
    STRIKE
    P: Delta/Gamma/IV/Vanna/Bid/Ask/Mid/Theo/Mis%
  - init_table_replay / init_row_replay / render_rows_replay 추가
  - 기존 GreeksGrid용 함수는 그대로 유지
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QFont, QColor, QBrush
from typing          import Dict, List, Optional, Set

# ── 기존 열 인덱스 (GreeksGrid 실시간용) ─────────────────────
C_DELTA, C_GAMMA, C_IV, C_VANNA = 0, 1, 2, 3
COL_STRIKE = 4
P_DELTA, P_GAMMA, P_IV, P_VANNA = 5, 6, 7, 8
NCOLS = 9

COL_LABELS = [
    "C Delta", "C Gamma", "C IV", "C Vanna",
    "STRIKE",
    "P Delta", "P Gamma", "P IV", "P Vanna",
]

# ── 리플레이 확장 열 인덱스 ──────────────────────────────────
RC_DELTA, RC_GAMMA, RC_IV, RC_VANNA = 0, 1, 2, 3
RC_BID, RC_ASK, RC_MID, RC_THEO, RC_MISPCT = 4, 5, 6, 7, 8
RCOL_STRIKE = 9
RP_DELTA, RP_GAMMA, RP_IV, RP_VANNA = 10, 11, 12, 13
RP_BID, RP_ASK, RP_MID, RP_THEO, RP_MISPCT = 14, 15, 16, 17, 18
REPLAY_NCOLS = 19

REPLAY_COL_LABELS = [
    "C Delta", "C Gamma", "C IV", "C Vanna",
    "C Bid", "C Ask", "C Mid", "C Theo", "C Mis%",
    "STRIKE",
    "P Delta", "P Gamma", "P IV", "P Vanna",
    "P Bid", "P Ask", "P Mid", "P Theo", "P Mis%",
]

# ── 색상 상수 ─────────────────────────────────────────────────
ATM_BG    = QColor(60, 55, 0)
ATM_FG    = QColor(255, 220, 50)
CALL_HDR  = "#1a4a8a"
PUT_HDR   = "#5a1a1a"
STRIKE_HDR= "#1a2a1a"
PRICE_HDR = "#1a3a2a"
SPIKE_BG  = QColor(180, 20, 20, 160)


# ══════════════════════════════════════════════════════════════
# 색상 계산
# ══════════════════════════════════════════════════════════════
def gamma_bg(gamma: float, max_gamma: float) -> Optional[QColor]:
    if max_gamma <= 0:
        return None
    ratio = min(abs(gamma) / max_gamma, 1.0)
    if ratio < 0.05:
        return None
    alpha = int(30 + ratio * 160)
    return QColor(90, 40, 180, alpha)


def delta_color(delta: float, side: str) -> QColor:
    abs_d = abs(delta)
    if side == "C":
        return QColor(80, int(120 + abs_d * 135), 255)
    return QColor(int(120 + abs_d * 135), 80, 80)


def arrow_str(curr: float, prev: float, thr: float = 1e-6) -> str:
    diff = curr - prev
    if abs(diff) < thr:
        return ""
    return "a" if diff > 0 else "v"


def arrow_color(curr: float, prev: float) -> Optional[QColor]:
    diff = curr - prev
    if abs(diff) < 1e-6:
        return None
    return QColor(255, 80, 80) if diff > 0 else QColor(80, 140, 255)


# ══════════════════════════════════════════════════════════════
# 기존 테이블 초기화 (GreeksGrid 실시간용 — 변경 없음)
# ══════════════════════════════════════════════════════════════
def init_table(tbl: QTableWidget):
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
    is_atm = (strike == atm_strike)
    for col in range(NCOLS):
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if col == COL_STRIKE:
            item.setText(str(int(strike)))
            item.setFont(QFont("Arial", 0, QFont.Bold))
        else:
            item.setText("-")
        if is_atm:
            item.setBackground(QBrush(ATM_BG))
            item.setForeground(QBrush(ATM_FG))
        tbl.setItem(row, col, item)
    tbl.setRowHidden(row, False)


# ══════════════════════════════════════════════════════════════
# ★ 리플레이 전용 테이블 초기화 (Greeks + 가격 확장)
# ══════════════════════════════════════════════════════════════
def init_table_replay(tbl: QTableWidget):
    tbl.setColumnCount(REPLAY_NCOLS)
    tbl.setHorizontalHeaderLabels(REPLAY_COL_LABELS)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setAlternatingRowColors(False)
    tbl.setStyleSheet("""
        QTableWidget{background:#08080f;gridline-color:#1a1a3a;
                     border:1px solid #2e3060;}
        QTableWidget::item{padding:2px 3px;font-size:10px;}
        QTableWidget::item:selected{background:#1c3a6a;}
        QHeaderView::section{padding:3px 2px;font-weight:bold;
                              font-size:10px;border:1px solid #1e1e3a;}
    """)
    for col in range(REPLAY_NCOLS):
        item = QTableWidgetItem(REPLAY_COL_LABELS[col])
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if col < RCOL_STRIKE:
            if col < 4:
                item.setBackground(QBrush(QColor(CALL_HDR)))
                item.setForeground(QBrush(QColor("#88ccff")))
            else:
                item.setBackground(QBrush(QColor(PRICE_HDR)))
                item.setForeground(QBrush(QColor("#88ffcc")))
        elif col == RCOL_STRIKE:
            item.setBackground(QBrush(QColor(STRIKE_HDR)))
            item.setForeground(QBrush(QColor("#aaffaa")))
        else:
            if col < 14:
                item.setBackground(QBrush(QColor(PUT_HDR)))
                item.setForeground(QBrush(QColor("#ffaaaa")))
            else:
                item.setBackground(QBrush(QColor("#3a1a2a")))
                item.setForeground(QBrush(QColor("#ffccaa")))
        tbl.setHorizontalHeaderItem(col, item)


def init_row_replay(tbl: QTableWidget, row: int,
                    strike: float, atm_strike: float):
    is_atm = (strike == atm_strike)
    for col in range(REPLAY_NCOLS):
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if col == RCOL_STRIKE:
            item.setText(str(int(strike)))
            item.setFont(QFont("Arial", 0, QFont.Bold))
        else:
            item.setText("-")
        if is_atm:
            item.setBackground(QBrush(ATM_BG))
            item.setForeground(QBrush(ATM_FG))
        tbl.setItem(row, col, item)
    tbl.setRowHidden(row, False)


def render_rows_replay(tbl: QTableWidget,
                       strikes: List[float], atm_strike: float,
                       cell_data: dict, prev: dict,
                       spike_strikes: Optional[Set] = None):
    spike_strikes = spike_strikes or set()
    all_gammas = [d["gamma"] for d in cell_data.values() if d.get("gamma")]
    max_g = max(all_gammas) if all_gammas else 1.0

    for r, st in enumerate(strikes):
        is_atm = (st == atm_strike)
        spike  = st in spike_strikes
        for side, col_map in (
            ("C", {
                RC_DELTA: "delta", RC_GAMMA: "gamma",
                RC_IV: "iv",       RC_VANNA: "vanna",
                RC_BID: "bid",     RC_ASK: "ask",
                RC_MID: "mid",     RC_THEO: "theo",
                RC_MISPCT: "mispct",
            }),
            ("P", {
                RP_DELTA: "delta", RP_GAMMA: "gamma",
                RP_IV: "iv",       RP_VANNA: "vanna",
                RP_BID: "bid",     RP_ASK: "ask",
                RP_MID: "mid",     RP_THEO: "theo",
                RP_MISPCT: "mispct",
            }),
        ):
            d = cell_data.get((r, side))
            if not d:
                continue
            for col, key in col_map.items():
                val = d.get(key)
                if val is None:
                    continue
                pv  = prev.get((st, side, key), val)
                prev[(st, side, key)] = val

                if key in ("bid", "ask", "mid", "theo"):
                    fmt = ".2f"
                    fg  = QColor("#aaffcc") if side == "C" else QColor("#ffccaa")
                elif key == "mispct":
                    fmt = "+.1f"
                    fg  = QColor("#ff8888") if val > 0 else QColor("#88ff88")
                elif key == "gamma":
                    fmt = ".6f"
                    fg  = QColor(160, 255, 120)
                elif key == "vanna":
                    fmt = "+.5f"
                    fg  = QColor(255, 200, 100)
                elif key == "iv":
                    fmt = "+.4f"
                    fg  = QColor(200, 180, 255)
                else:
                    fmt = "+.4f"
                    fg  = delta_color(val, side)

                item = tbl.item(r, col)
                if item is None:
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    tbl.setItem(r, col, item)

                try:
                    text = f"{val:{fmt}}"
                except (ValueError, TypeError):
                    text = "-"

                a_str = arrow_str(val, pv)
                if a_str:
                    text = f"{text}{a_str}"
                item.setText(text)

                if spike:
                    item.setBackground(QBrush(SPIKE_BG))
                    item.setForeground(QBrush(QColor(255, 200, 200)))
                elif is_atm:
                    item.setBackground(QBrush(ATM_BG))
                    item.setForeground(QBrush(ATM_FG))
                elif key == "gamma":
                    bg = gamma_bg(val, max_g)
                    item.setBackground(
                        QBrush(bg) if bg else QBrush(QColor(8, 8, 15)))
                    item.setForeground(QBrush(fg))
                else:
                    item.setBackground(QBrush(QColor(8, 8, 15)))
                    item.setForeground(QBrush(fg))


# ══════════════════════════════════════════════════════════════
# 기존 셀 렌더링 (GreeksGrid 실시간용 — 변경 없음)
# ══════════════════════════════════════════════════════════════
def set_cell(tbl, row, col, value, side, key, max_gamma, is_atm,
             prev=None, fmt=".4f", use_heatmap=False, spike=False):
    item = tbl.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        tbl.setItem(row, col, item)

    try:
        text = f"{value:{fmt}}"
    except (ValueError, TypeError):
        text = "-"

    a_str = arrow_str(value, prev) if prev is not None else ""
    a_col = arrow_color(value, prev) if prev is not None else None
    if a_str:
        text = f"{text}{a_str}"
    item.setText(text)

    f = QFont("Consolas", 0)
    if key == "gamma":
        f.setBold(True)
    item.setFont(f)

    if spike:
        item.setBackground(QBrush(SPIKE_BG))
    elif is_atm:
        item.setBackground(QBrush(ATM_BG))
    elif use_heatmap:
        bg = gamma_bg(value, max_gamma)
        item.setBackground(QBrush(bg) if bg else QBrush(QColor(8, 8, 15)))
    else:
        item.setBackground(QBrush(QColor(8, 8, 15)))

    if a_col and not is_atm and not spike:
        item.setForeground(QBrush(a_col))
    elif is_atm or spike:
        item.setForeground(
            QBrush(ATM_FG if is_atm else QColor(255, 200, 200)))
    elif key == "delta":
        item.setForeground(QBrush(delta_color(value, side)))
    elif key == "gamma":
        item.setForeground(QBrush(QColor(160, 255, 120)))
    elif key == "iv":
        item.setForeground(QBrush(QColor(200, 180, 255)))
    elif key == "vanna":
        item.setForeground(QBrush(QColor(255, 200, 100)))


def render_rows(tbl, strikes, atm_strike, cell_data, prev,
                spike_strikes=None):
    spike_strikes = spike_strikes or set()
    all_gammas = [d["gamma"] for d in cell_data.values() if d.get("gamma")]
    max_g = max(all_gammas) if all_gammas else 1.0

    for r, st in enumerate(strikes):
        is_atm = (st == atm_strike)
        spike  = st in spike_strikes
        for side, col_map in (
            ("C", {C_DELTA: "delta", C_GAMMA: "gamma",
                   C_IV: "iv",       C_VANNA: "vanna"}),
            ("P", {P_DELTA: "delta", P_GAMMA: "gamma",
                   P_IV: "iv",       P_VANNA: "vanna"}),
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