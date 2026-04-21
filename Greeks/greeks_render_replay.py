"""
greeks_render_replay.py — 리플레이 전용 테이블 렌더링
════════════════════════════════════════════════════════════════
greeks_render.py 에서 분리된 리플레이 전용 모듈.

v6.7 변경:
  - ★ chg_pct(등락률) 컬럼 추가 → REPLAY_NCOLS = 21
  - ★ apply_view_mode(tbl, mode): 뷰 모드별 컬럼 show/hide
  - ★ render_rows_replay()에 view_cols 파라미터 추가

컬럼 레이아웃 (총 21개):
  0~3   : C Delta/Gamma/IV/Vanna       (greeks)
  4~7   : C Bid/Ask/Mid/Last           (premium)
  8~9   : C Theo/Mispct                (theory)
  10    : C Chg%                       (theory)
  11    : STRIKE
  12~15 : P Delta/Gamma/IV/Vanna       (greeks)
  16~19 : P Bid/Ask/Mid/Last           (premium)
  20~21 : P Theo/Mispct                (theory)  ← 실제 idx 20,21
  ※ 실제 인덱스는 아래 상수 참조
"""

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore    import Qt
from PyQt5.QtGui     import QFont, QColor, QBrush
from typing          import List, Optional, Set

from greeks_render import (
    ATM_BG, ATM_FG, CALL_HDR, PUT_HDR, STRIKE_HDR, PRICE_HDR, SPIKE_BG,
    gamma_bg, delta_color, arrow_str,
)

# ── 리플레이 열 인덱스 ────────────────────────────────────────
RC_DELTA, RC_GAMMA, RC_IV, RC_VANNA         = 0,  1,  2,  3
RC_BID,   RC_ASK,  RC_MID, RC_LAST          = 4,  5,  6,  7
RC_THEO,  RC_MISPCT, RC_CHGPCT              = 8,  9,  10
RCOL_STRIKE                                 = 11
RP_DELTA, RP_GAMMA, RP_IV, RP_VANNA         = 12, 13, 14, 15
RP_BID,   RP_ASK,  RP_MID, RP_LAST          = 16, 17, 18, 19
RP_THEO,  RP_MISPCT, RP_CHGPCT              = 20, 21, 22
REPLAY_NCOLS                                = 23

REPLAY_COL_LABELS = [
    "C Delta", "C Gamma", "C IV",   "C Vanna",          # 0~3
    "C Bid",   "C Ask",   "C Mid",  "C Last",            # 4~7
    "C Theo",  "C Mis%",  "C Chg%",                      # 8~10
    "STRIKE",                                             # 11
    "P Delta", "P Gamma", "P IV",   "P Vanna",           # 12~15
    "P Bid",   "P Ask",   "P Mid",  "P Last",            # 16~19
    "P Theo",  "P Mis%",  "P Chg%",                      # 20~22
]

# ── 뷰 모드 → 보여줄 열 집합 ──────────────────────────────────
_VIEW_COLS: dict = {
    "greeks":  {RC_DELTA, RC_GAMMA, RC_IV, RC_VANNA,
                RCOL_STRIKE,
                RP_DELTA, RP_GAMMA, RP_IV, RP_VANNA},
    "premium": {RC_BID, RC_ASK, RC_MID, RC_LAST,
                RCOL_STRIKE,
                RP_BID, RP_ASK, RP_MID, RP_LAST},
    "theory":  {RC_THEO, RC_MISPCT, RC_CHGPCT,
                RCOL_STRIKE,
                RP_THEO, RP_MISPCT, RP_CHGPCT},
}

# 뷰 모드 → 렌더할 (열인덱스, 데이터키) 매핑
_RENDER_MAP: dict = {
    "greeks": [
        ("C", RC_DELTA,  "delta"),  ("C", RC_GAMMA,  "gamma"),
        ("C", RC_IV,     "iv"),     ("C", RC_VANNA,  "vanna"),
        ("P", RP_DELTA,  "delta"),  ("P", RP_GAMMA,  "gamma"),
        ("P", RP_IV,     "iv"),     ("P", RP_VANNA,  "vanna"),
    ],
    "premium": [
        ("C", RC_BID,  "bid"),   ("C", RC_ASK,  "ask"),
        ("C", RC_MID,  "mid"),   ("C", RC_LAST, "last"),
        ("P", RP_BID,  "bid"),   ("P", RP_ASK,  "ask"),
        ("P", RP_MID,  "mid"),   ("P", RP_LAST, "last"),
    ],
    "theory": [
        ("C", RC_THEO,   "theo"),   ("C", RC_MISPCT, "mispct"),
        ("C", RC_CHGPCT, "chg_pct"),
        ("P", RP_THEO,   "theo"),   ("P", RP_MISPCT, "mispct"),
        ("P", RP_CHGPCT, "chg_pct"),
    ],
}

# 데이터키 → (포맷, 기본 색상함수)
def _fmt_fg(key: str, val: float, side: str):
    if key in ("bid", "ask", "mid", "last", "theo"):
        fg = QColor("#aaffcc") if side == "C" else QColor("#ffccaa")
        return ".2f", fg
    if key == "mispct":
        fg = QColor("#ff8888") if val > 0 else QColor("#88ff88")
        return "+.1f", fg
    if key == "chg_pct":
        fg = QColor("#ff9966") if val > 0 else QColor("#66ccff")
        return "+.1f", fg
    if key == "gamma":
        return ".6f", QColor(160, 255, 120)
    if key == "vanna":
        return "+.5f", QColor(255, 200, 100)
    if key == "iv":
        return "+.4f", QColor(200, 180, 255)
    return "+.4f", delta_color(val, side)   # delta


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def init_table_replay(tbl: QTableWidget):
    """리플레이 테이블 전체 초기화 (23컬럼)."""
    tbl.setColumnCount(REPLAY_NCOLS)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QTableWidget.NoEditTriggers)
    tbl.setSelectionBehavior(QTableWidget.SelectRows)
    tbl.setAlternatingRowColors(False)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    tbl.setStyleSheet("""
        QTableWidget{background:#08080f;gridline-color:#1a1a3a;
                     border:1px solid #2e3060;}
        QTableWidget::item{padding:2px 3px;font-size:10px;}
        QTableWidget::item:selected{background:#1c3a6a;}
        QHeaderView::section{padding:3px 2px;font-weight:bold;
                              font-size:10px;border:1px solid #1e1e3a;}
    """)
    for col, label in enumerate(REPLAY_COL_LABELS):
        item = QTableWidgetItem(label)
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        item.setBackground(QBrush(QColor(_hdr_color(col))))
        item.setForeground(QBrush(QColor(_hdr_fg(col))))
        tbl.setHorizontalHeaderItem(col, item)

    apply_view_mode(tbl, "greeks")   # 기본 뷰


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


def apply_view_mode(tbl: QTableWidget, mode: str):
    """뷰 모드에 맞게 컬럼 show/hide 전환."""
    visible = _VIEW_COLS.get(mode, _VIEW_COLS["greeks"])
    for col in range(REPLAY_NCOLS):
        tbl.setColumnHidden(col, col not in visible)


def render_rows_replay(tbl: QTableWidget,
                       strikes: List[float], atm_strike: float,
                       cell_data: dict, prev: dict,
                       view_cols: Optional[List[str]] = None,
                       spike_strikes: Optional[Set] = None):
    """현재 뷰 모드 컬럼만 렌더. view_cols 는 VIEW_MODES[mode]['cols']."""
    spike_strikes = spike_strikes or set()
    mode = _cols_to_mode(view_cols)
    render_map = _RENDER_MAP[mode]

    all_gammas = [d["gamma"] for d in cell_data.values() if d.get("gamma")]
    max_g = max(all_gammas) if all_gammas else 1.0

    for r, st in enumerate(strikes):
        is_atm = (st == atm_strike)
        spike  = st in spike_strikes
        for side, col, key in render_map:
            d = cell_data.get((r, side))
            if not d:
                continue
            val = d.get(key)
            if val is None:
                continue
            pv = prev.get((st, side, key), val)
            prev[(st, side, key)] = val
            _set_replay_cell(tbl, r, col, val, pv, key, side,
                             max_g, is_atm, spike)


# ── 내부 헬퍼 ─────────────────────────────────────────────────

def _set_replay_cell(tbl, row, col, val, pv, key, side,
                     max_g, is_atm, spike):
    item = tbl.item(row, col)
    if item is None:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        tbl.setItem(row, col, item)

    fmt, fg = _fmt_fg(key, val, side)
    try:
        text = f"{val:{fmt}}"
    except (ValueError, TypeError):
        text = "-"
    a = arrow_str(val, pv)
    if a:
        text = f"{text}{a}"
    item.setText(text)

    if spike:
        item.setBackground(QBrush(SPIKE_BG))
        item.setForeground(QBrush(QColor(255, 200, 200)))
    elif is_atm:
        item.setBackground(QBrush(ATM_BG))
        item.setForeground(QBrush(ATM_FG))
    elif key == "gamma":
        bg = gamma_bg(val, max_g)
        item.setBackground(QBrush(bg) if bg else QBrush(QColor(8, 8, 15)))
        item.setForeground(QBrush(fg))
    else:
        item.setBackground(QBrush(QColor(8, 8, 15)))
        item.setForeground(QBrush(fg))


def _cols_to_mode(view_cols: Optional[List[str]]) -> str:
    if not view_cols:
        return "greeks"
    first = view_cols[0] if view_cols else ""
    if first in ("bid", "ask", "mid", "last"):
        return "premium"
    if first in ("theo", "mispct", "chg_pct"):
        return "theory"
    return "greeks"


def _hdr_color(col: int) -> str:
    if col == RCOL_STRIKE:           return STRIKE_HDR
    if col in range(RC_BID, RC_THEO+1) or col in range(RP_BID, RP_THEO+1):
        return PRICE_HDR
    if col in (RC_MISPCT, RC_CHGPCT, RP_MISPCT, RP_CHGPCT):
        return "#2a1a3a"
    if col < RCOL_STRIKE:            return CALL_HDR
    return PUT_HDR


def _hdr_fg(col: int) -> str:
    if col == RCOL_STRIKE:           return "#aaffaa"
    if col in range(RC_BID, RC_CHGPCT+1) or col in range(RP_BID, RP_CHGPCT+1):
        return "#88ffcc"
    if col < RCOL_STRIKE:            return "#88ccff"
    return "#ffaaaa"