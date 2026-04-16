"""
tab_greeks.py — Greeks Matrix 탭  v2.0  (tab_account.py 에서 분리)
════════════════════════════════════════════════════════════════
  Tab 6  GreeksGrid  (전면 재설계)

  ┌─ 레이아웃 (QSplitter 기반) ──────────────────────────────┐
  │  _v_splitter (수직)                                       │
  │  ├─ ctrl_w          컨트롤바                              │
  │  └─ _h_splitter (수평)                                    │
  │      ├─ Greeks Matrix 테이블 (중앙 행사가)                │
  │      └─ _chart_vsplit (수직)                              │
  │          ├─ GEX 막대 차트  (Call +위 / Put –아래)         │
  │          └─ IV Skew 라인 차트                             │
  └───────────────────────────────────────────────────────────┘
# ※ 이 파일은 사용되지 않습니다.
# 실제 파일: Main2/Greeks/tab_greeks.py
# main.py 에서 sys.path.insert(0, "Greeks/") 로 로드됨


  신규 기능
  ─────────
  • 중앙 행사가: [Call Δ][Call Γ][Call IV][Call Vanna] | STRIKE | [Put Δ][Put Γ][Put IV][Put Vanna]
  • ATM 행 황금색 배경 하이라이트
  • Gamma Heatmap: gamma 절대값 비례 → 보라 계열 셀 배경
  • 증감 화살표: 이전 틱 대비 ▲(빨강) / ▼(파랑) 인라인 표시
  • Delta 필터: |delta| < 임계값 행 숨김 (슬라이더 조절)
  • GEX 차트: gamma × position_est (포지션 추정치) 막대
  • IV Skew 차트: Call IV − Put IV 라인
  • Zero Gamma 수평선 자동 표시
  • SQLite 1분 단위 자동저장 (장중만)
  • 탭 비활성화 시 구독 유지, 과부하 방지: throttle 300ms
════════════════════════════════════════════════════════════════
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QSlider, QCheckBox, QMessageBox, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, GridTab, make_table, tbl_set, ts, ts_full,
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_UND, REQ_CHAIN, REQ_CHAIN_P,
    GREEKS_MATRIX_N,
    build_expiry_list, make_opt_contract,
    SAVE_DIR, is_market_open,
)

# ── 상수 ──────────────────────────────────────────────────────
DB_FILE        = SAVE_DIR / "greeks_history.db"
AUTOSAVE_MS    = 60_000        # 1분 자동저장
THROTTLE_MS    = 300           # tick 반영 최소 간격
POS_ESTIMATE   = 500           # OI 없을 때 GEX 계산용 포지션 추정치
ATM_BG         = QColor(60, 55, 0)       # ATM 행 배경 (진황)
ATM_BG_TEXT    = QColor(255, 220, 50)    # ATM 행 글자
CALL_HDR_COL   = "#1a4a8a"              # 콜 헤더 배경
PUT_HDR_COL    = "#5a1a1a"              # 풋 헤더 배경
STRIKE_HDR_COL = "#1a2a1a"             # 행사가 헤더 배경

# 테이블 열 인덱스
C_DELTA, C_GAMMA, C_IV, C_VANNA = 0, 1, 2, 3
COL_STRIKE = 4
P_DELTA, P_GAMMA, P_IV, P_VANNA = 5, 6, 7, 8
NCOLS = 9

COL_LABELS = [
    "C Δ Delta", "C Γ Gamma", "C IV", "C Vanna",
    "⚡ STRIKE",
    "P Δ Delta", "P Γ Gamma", "P IV", "P Vanna",
]


# ══════════════════════════════════════════════════════════════
# SQLite 헬퍼
# ══════════════════════════════════════════════════════════════
def _init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greeks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            sym       TEXT,
            expiry    TEXT,
            strike    REAL,
            side      TEXT,
            delta     REAL,
            gamma     REAL,
            iv        REAL,
            vanna     REAL,
            und_price REAL
        )
    """)
    conn.commit()
    return conn


def _save_to_db(conn, sym, expiry, und_price, rows):
    """rows: list of (strike, side, delta, gamma, iv, vanna)"""
    now = ts_full()
    conn.executemany(
        "INSERT INTO greeks(ts,sym,expiry,strike,side,delta,gamma,iv,vanna,und_price) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(now, sym, expiry, st, side, d, g, iv, va, und_price)
         for st, side, d, g, iv, va in rows]
    )
    conn.commit()


# ══════════════════════════════════════════════════════════════
# 색상 유틸
# ══════════════════════════════════════════════════════════════
def _gamma_bg(gamma: float, max_gamma: float):
    """gamma 절대값 비율 → 보라 계열 배경 (heatmap)."""
    if max_gamma <= 0:
        return None
    ratio = min(abs(gamma) / max_gamma, 1.0)
    if ratio < 0.05:
        return None
    alpha = int(30 + ratio * 160)   # 30~190
    return QColor(90, 40, 180, alpha)


def _delta_color(delta: float, side: str) -> QColor:
    """delta 수치 → 글자색. Call 파랑계, Put 빨강계. ATM 근처 밝게."""
    abs_d = abs(delta)
    if side == "C":
        g = int(120 + abs_d * 135)
        return QColor(80, g, 255)
    else:
        r = int(120 + abs_d * 135)
        return QColor(r, 80, 80)


def _arrow_str(curr: float, prev: float, threshold: float = 1e-6):
    """값 변화 → '▲' / '▼' / ''."""
    diff = curr - prev
    if abs(diff) < threshold:
        return ""
    return "▲" if diff > 0 else "▼"


def _arrow_color(curr: float, prev: float):
    diff = curr - prev
    if abs(diff) < 1e-6:
        return None
    return QColor(255, 80, 80) if diff > 0 else QColor(80, 140, 255)


# ══════════════════════════════════════════════════════════════
# GreeksGrid
# ══════════════════════════════════════════════════════════════
class GreeksGrid(GridTab):
    """
    Greeks Matrix 탭 (전면 재설계)
    GridTab 상속 → TabWrapper(폰트슬라이더·다크모드·설정저장) 자동 적용
    """

    def __init__(self, mw):
        super().__init__()
        self.mw           = mw
        self.sym          = "SPX"
        self.expiry       = ""
        self.exp_tag      = ""
        self.und_price    = 0.0
        self.strikes      = []           # 현재 조회 행사가 리스트 (정렬됨)
        self.atm_strike   = 0.0

        # tick 수신 버퍼: rid → {row, strike, side}
        self.call_info    = {}
        self.put_info     = {}

        # 마지막 저장 데이터 (증감 화살표용)
        # key: (strike, side, col) → float
        self._prev: dict  = {}

        # 현재 화면에 렌더링된 값 캐시 (heatmap 재계산용)
        # key: (row, side) → {delta, gamma, iv, vanna}
        self._cell_data: dict = {}

        # throttle: tick 수신 후 300ms 뒤 일괄 렌더
        self._dirty       = False
        self._throttle    = QTimer(self)
        self._throttle.setSingleShot(True)
        self._throttle.setInterval(THROTTLE_MS)
        self._throttle.timeout.connect(self._flush)

        # SQLite
        self._db          = _init_db()
        self._autosave_t  = QTimer(self)
        self._autosave_t.setInterval(AUTOSAVE_MS)
        self._autosave_t.timeout.connect(self._autosave)
        self._autosave_t.start()

        self._exp_list    = build_expiry_list()
        self._build()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────
    # UI 빌드
    # ─────────────────────────────────────────────────────────
    def _build(self):
        # ── [0] 컨트롤바 ──────────────────────────────────────
        ctrl = QWidget()
        cl   = QHBoxLayout(ctrl)
        cl.setContentsMargins(4, 2, 4, 2)
        cl.setSpacing(6)

        cl.addWidget(QLabel("심볼:"))
        self.edit_sym = QLineEdit("SPX")
        self.edit_sym.setFixedWidth(56)
        cl.addWidget(self.edit_sym)

        cl.addWidget(QLabel("만기:"))
        self.combo_exp = QComboBox()
        self.combo_exp.setMinimumWidth(120)
        for lbl, _, _ in self._exp_list:
            self.combo_exp.addItem(lbl)
        cl.addWidget(self.combo_exp)

        btn_fetch = QPushButton("▶ 조회")
        btn_fetch.setStyleSheet(
            "background:#1a3a6b;font-weight:bold;padding:4px 10px;")
        btn_fetch.clicked.connect(self._fetch)
        cl.addWidget(btn_fetch)

        # 현재가 표시
        self.lbl_und = QLabel("SPX: ―")
        self.lbl_und.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_und.setStyleSheet(
            "color:#ffd700;padding:0 10px;border:none;")
        cl.addWidget(self.lbl_und)

        cl.addWidget(_vline())

        # Delta 필터
        cl.addWidget(QLabel("Delta 필터 ≥"))
        self.sld_delta = QSlider(Qt.Horizontal)
        self.sld_delta.setRange(0, 50)   # 0.00 ~ 0.50
        self.sld_delta.setValue(5)       # 기본 0.05
        self.sld_delta.setFixedWidth(90)
        self.sld_delta.valueChanged.connect(self._apply_delta_filter)
        self.lbl_delta_val = QLabel("0.05")
        self.lbl_delta_val.setStyleSheet("color:#aaa;border:none;min-width:28px;")
        cl.addWidget(self.sld_delta)
        cl.addWidget(self.lbl_delta_val)

        cl.addWidget(_vline())

        # SQLite 저장 상태
        self.chk_autosave = QCheckBox("1분 자동저장")
        self.chk_autosave.setChecked(True)
        cl.addWidget(self.chk_autosave)

        self.lbl_save = QLabel("저장: ―")
        self.lbl_save.setStyleSheet("color:#555;font-size:11px;border:none;")
        cl.addWidget(self.lbl_save)

        btn_sv = QPushButton("💾 즉시 저장")
        btn_sv.clicked.connect(self._manual_save)
        cl.addWidget(btn_sv)

        cl.addStretch()
        self.add(ctrl, 0, 0, 1, 12)

        # ── [1-3] 수평 스플리터: 테이블 | 차트 ──────────────
        self._h_split = QSplitter(Qt.Horizontal)
        self._h_split.setHandleWidth(6)
        self._h_split.setStyleSheet(
            "QSplitter::handle{background:#2a2a5a;}"
            "QSplitter::handle:hover{background:#5dade2;}"
        )

        # ── 테이블 ─────────────────────────────────────────
        self.tbl = QTableWidget(0, NCOLS)
        self.tbl.setHorizontalHeaderLabels(COL_LABELS)
        self.tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setAlternatingRowColors(False)
        self.tbl.setStyleSheet("""
            QTableWidget{background:#08080f;gridline-color:#1a1a3a;
                         border:1px solid #2e3060;}
            QTableWidget::item{padding:3px 6px;}
            QTableWidget::item:selected{background:#1c3a6a;}
            QHeaderView::section{padding:5px 4px;font-weight:bold;
                                  border:1px solid #1e1e3a;}
        """)
        self._style_header()
        self._h_split.addWidget(self.tbl)

        # ── 우측 차트 영역 ──────────────────────────────────
        self._chart_vsplit = QSplitter(Qt.Vertical)
        self._chart_vsplit.setHandleWidth(5)

        if PG:
            pg.setConfigOption('background', '#08080f')
            pg.setConfigOption('foreground', '#cccccc')

            # GEX 차트
            self._gex_plot = pg.PlotWidget(title="GEX (Gamma Exposure Estimate)")
            self._gex_plot.showGrid(x=False, y=True, alpha=0.25)
            self._gex_plot.setLabel('left',   'GEX',    color='#aaa')
            self._gex_plot.setLabel('bottom', 'Strike', color='#aaa')
            self._gex_plot.addLine(y=0, pen=pg.mkPen('#ff4444', width=1.5,
                                                      style=Qt.DashLine))
            self._gex_bar_call = None
            self._gex_bar_put  = None
            self._zero_line    = None

            # Skew 차트
            self._skew_plot = pg.PlotWidget(title="IV Skew  (Call IV − Put IV)")
            self._skew_plot.showGrid(x=True, y=True, alpha=0.25)
            self._skew_plot.setLabel('left',   'Skew', color='#aaa')
            self._skew_plot.setLabel('bottom', 'Strike', color='#aaa')
            self._skew_plot.addLine(y=0, pen=pg.mkPen('#555', width=1))
            self._skew_curve = self._skew_plot.plot(
                pen=pg.mkPen('#ffd700', width=2))

            self._chart_vsplit.addWidget(self._gex_plot)
            self._chart_vsplit.addWidget(self._skew_plot)
            self._chart_vsplit.setSizes([300, 200])
        else:
            self._chart_vsplit.addWidget(
                QLabel("pip install pyqtgraph  →  차트 활성화"))

        self._h_split.addWidget(self._chart_vsplit)
        self._h_split.setSizes([700, 450])

        self.add(self._h_split, 1, 0, 3, 12)

    def _style_header(self):
        """콜/풋/행사가 헤더 색상 분리."""
        hdr = self.tbl.horizontalHeader()
        for col in range(NCOLS):
            item = QTableWidgetItem(COL_LABELS[col])
            item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            if col < COL_STRIKE:
                item.setBackground(QBrush(QColor(CALL_HDR_COL)))
                item.setForeground(QBrush(QColor("#88ccff")))
            elif col == COL_STRIKE:
                item.setBackground(QBrush(QColor(STRIKE_HDR_COL)))
                item.setForeground(QBrush(QColor("#aaffaa")))
            else:
                item.setBackground(QBrush(QColor(PUT_HDR_COL)))
                item.setForeground(QBrush(QColor("#ffaaaa")))
            self.tbl.setHorizontalHeaderItem(col, item)

    # ─────────────────────────────────────────────────────────
    # 시그널 연결
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        router.register_price(REQ_UND,      REQ_UND,           self._on_tick_price)
        router.register_price(REQ_CHAIN,    REQ_CHAIN   + 199, self._on_tick_price)
        router.register_price(REQ_CHAIN_P,  REQ_CHAIN_P + 199, self._on_tick_price)
        router.register_option(REQ_CHAIN,   REQ_CHAIN   + 199, self._on_tick_opt)
        router.register_option(REQ_CHAIN_P, REQ_CHAIN_P + 199, self._on_tick_opt)

    # ─────────────────────────────────────────────────────────
    # 데이터 조회
    # ─────────────────────────────────────────────────────────
    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요.")
            return

        self.sym = self.edit_sym.text().strip().upper()
        cp        = getattr(self.mw, 'tab_callput', None)
        und_price = getattr(cp, 'und_price', None) or self.und_price
        if not und_price:
            QMessageBox.information(
                self, "대기", "콜-풋 탭에서 먼저 현재가를 수신하세요.")
            return

        idx = self.combo_exp.currentIndex()
        _, code, tag = self._exp_list[idx]
        if code == "CUSTOM":
            return
        self.expiry  = code
        self.exp_tag = tag

        base_sym = "SPX" if self.sym == "SPXW" else self.sym
        _, _, _, step = SYMBOL_CFG.get(base_sym, DEFAULT_CFG)
        self.atm_strike = round(und_price / step) * step

        self.strikes = sorted({
            self.atm_strike + i * step
            for i in range(-GREEKS_MATRIX_N, GREEKS_MATRIX_N + 1)
        })

        self.call_info.clear()
        self.put_info.clear()
        self._cell_data.clear()
        self.tbl.setRowCount(len(self.strikes))

        for r, st in enumerate(self.strikes):
            self._init_row(r, st)

        ticks = "100,101,106"
        for i, st in enumerate(self.strikes):
            rid_c = REQ_CHAIN   + i
            rid_p = REQ_CHAIN_P + i
            self.call_info[rid_c] = {"row": i, "strike": st}
            self.put_info[rid_p]  = {"row": i, "strike": st}
            self.mw.ib.reqMktData(
                rid_c, make_opt_contract(self.sym, st, "C", self.expiry, self.exp_tag),
                ticks, False, False, [])
            self.mw.ib.reqMktData(
                rid_p, make_opt_contract(self.sym, st, "P", self.expiry, self.exp_tag),
                ticks, False, False, [])

    def _init_row(self, row: int, strike: float):
        """행 초기화 + ATM 하이라이트."""
        is_atm = (strike == self.atm_strike)
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
                item.setForeground(QBrush(ATM_BG_TEXT))
            self.tbl.setItem(row, col, item)
        self.tbl.setRowHidden(row, False)

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid: int, tt: int, price: float):
        if price <= 0:
            return
        if rid == REQ_UND and tt in (4, 14, 75):
            self.und_price = price
            self.lbl_und.setText(f"{self.sym}: {price:,.2f}")

    def _on_tick_opt(self, rid: int, tt: int,
                     iv: float, delta: float, op: float,
                     gamma: float, vega: float, theta: float):
        if tt not in (12, 13):
            return
        if rid in self.call_info:
            info = self.call_info[rid]
            r, st = info["row"], info["strike"]
            # Vanna 추정: vega × (delta 변화/IV 변화) → 근사치로 vega * delta 사용
            vanna = round(vega * delta, 6) if vega and delta else 0.0
            self._cell_data[(r, "C")] = {
                "delta": delta, "gamma": gamma,
                "iv": iv or 0.0, "vanna": vanna,
                "strike": st,
            }
        elif rid in self.put_info:
            info = self.put_info[rid]
            r, st = info["row"], info["strike"]
            vanna = round(vega * delta, 6) if vega and delta else 0.0
            self._cell_data[(r, "P")] = {
                "delta": delta, "gamma": gamma,
                "iv": iv or 0.0, "vanna": vanna,
                "strike": st,
            }
        # throttle: 300ms 후 일괄 렌더
        self._dirty = True
        if not self._throttle.isActive():
            self._throttle.start()

    # ─────────────────────────────────────────────────────────
    # 렌더링 (throttle flush)
    # ─────────────────────────────────────────────────────────
    def _flush(self):
        if not self._dirty:
            return
        self._dirty = False
        self._render_table()
        self._update_charts()

    def _render_table(self):
        # 최대 gamma 계산 (heatmap 정규화용)
        all_gammas = [
            d["gamma"]
            for d in self._cell_data.values()
            if d.get("gamma")
        ]
        max_gamma = max(all_gammas) if all_gammas else 1.0

        for r, st in enumerate(self.strikes):
            c_data = self._cell_data.get((r, "C"))
            p_data = self._cell_data.get((r, "P"))
            is_atm = (st == self.atm_strike)

            # ── Call 측 ──────────────────────────────────────
            if c_data:
                self._set_greek_cell(r, C_DELTA, c_data["delta"], "C",
                                     "delta", max_gamma, is_atm, fmt="+.4f")
                self._set_greek_cell(r, C_GAMMA, c_data["gamma"], "C",
                                     "gamma", max_gamma, is_atm, fmt=".6f",
                                     use_heatmap=True)
                self._set_greek_cell(r, C_IV,    c_data["iv"],    "C",
                                     "iv",    max_gamma, is_atm, fmt=".4f")
                self._set_greek_cell(r, C_VANNA,  c_data["vanna"], "C",
                                     "vanna", max_gamma, is_atm, fmt="+.5f")

            # ── Put 측 ───────────────────────────────────────
            if p_data:
                self._set_greek_cell(r, P_DELTA, p_data["delta"], "P",
                                     "delta", max_gamma, is_atm, fmt="+.4f")
                self._set_greek_cell(r, P_GAMMA, p_data["gamma"], "P",
                                     "gamma", max_gamma, is_atm, fmt=".6f",
                                     use_heatmap=True)
                self._set_greek_cell(r, P_IV,    p_data["iv"],    "P",
                                     "iv",    max_gamma, is_atm, fmt=".4f")
                self._set_greek_cell(r, P_VANNA,  p_data["vanna"], "P",
                                     "vanna", max_gamma, is_atm, fmt="+.5f")

        self._apply_delta_filter()

    def _set_greek_cell(self, row: int, col: int, value: float, side: str,
                        key: str, max_gamma: float, is_atm: bool,
                        fmt: str = ".4f", use_heatmap: bool = False):
        """셀 값·색상·화살표·heatmap 일괄 적용."""
        item = self.tbl.item(row, col)
        if item is None:
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.tbl.setItem(row, col, item)

        st    = self.strikes[row]
        prev  = self._prev.get((st, side, key), value)
        arrow = _arrow_str(value, prev)
        a_col = _arrow_color(value, prev)
        self._prev[(st, side, key)] = value

        # 텍스트
        try:
            text = f"{value:{fmt}}"
        except (ValueError, TypeError):
            text = "―"
        if arrow:
            text = f"{text} {arrow}"
        item.setText(text)

        # 폰트
        f = QFont("Consolas", 0)
        if key == "gamma":
            f.setBold(True)
        item.setFont(f)

        # ATM 행 배경 우선
        if is_atm:
            item.setBackground(QBrush(ATM_BG))
        elif use_heatmap:
            bg = _gamma_bg(value, max_gamma)
            item.setBackground(QBrush(bg) if bg else QBrush(QColor(8, 8, 15)))
        else:
            item.setBackground(QBrush(QColor(8, 8, 15)))

        # 글자색
        if a_col and not is_atm:
            item.setForeground(QBrush(a_col))
        elif key == "delta":
            item.setForeground(QBrush(_delta_color(value, side)))
        elif key == "gamma":
            item.setForeground(QBrush(QColor(160, 255, 120)))
        elif key == "iv":
            item.setForeground(QBrush(QColor(200, 180, 255)))
        elif key == "vanna":
            item.setForeground(QBrush(QColor(255, 200, 100)))
        elif is_atm:
            item.setForeground(QBrush(ATM_BG_TEXT))

    # ─────────────────────────────────────────────────────────
    # Delta 필터
    # ─────────────────────────────────────────────────────────
    def _apply_delta_filter(self):
        threshold = self.sld_delta.value() / 100.0
        self.lbl_delta_val.setText(f"{threshold:.2f}")
        for r, st in enumerate(self.strikes):
            c_data = self._cell_data.get((r, "C"))
            p_data = self._cell_data.get((r, "P"))
            c_abs  = abs(c_data["delta"]) if c_data else 0.0
            p_abs  = abs(p_data["delta"]) if p_data else 0.0
            # ATM는 항상 표시
            is_atm = (st == self.atm_strike)
            hide   = (not is_atm) and (c_abs < threshold) and (p_abs < threshold)
            self.tbl.setRowHidden(r, hide)

    # ─────────────────────────────────────────────────────────
    # 차트 갱신
    # ─────────────────────────────────────────────────────────
    def _update_charts(self):
        if not PG:
            return
        strikes_vis = []
        gex_vals    = []
        skew_vals   = []

        for r, st in enumerate(self.strikes):
            if self.tbl.isRowHidden(r):
                continue
            c_data = self._cell_data.get((r, "C"))
            p_data = self._cell_data.get((r, "P"))

            c_gamma = c_data["gamma"] if c_data else 0.0
            p_gamma = p_data["gamma"] if p_data else 0.0
            c_iv    = c_data["iv"]    if c_data else 0.0
            p_iv    = p_data["iv"]    if p_data else 0.0

            # GEX = gamma × position_estimate × 100 (multiplier)
            gex = (c_gamma - p_gamma) * POS_ESTIMATE * 100
            strikes_vis.append(st)
            gex_vals.append(gex)
            skew_vals.append(c_iv - p_iv)

        if not strikes_vis:
            return

        xs = list(range(len(strikes_vis)))

        # ── GEX 막대 (BarGraphItem) ──────────────────────────
        self._gex_plot.clear()
        self._gex_plot.addLine(
            y=0, pen=pg.mkPen('#ff4444', width=1.5, style=Qt.DashLine))

        brushes = [
            '#3388ff' if v >= 0 else '#ff5555'
            for v in gex_vals
        ]
        bar = pg.BarGraphItem(
            x=xs, height=gex_vals,
            width=0.7, brushes=brushes,
            pen=pg.mkPen('#111', width=0.5)
        )
        self._gex_plot.addItem(bar)

        # Zero Gamma 선 (GEX 가장 가까운 0 교차 지점)
        zero_x = self._find_zero_gamma(xs, gex_vals)
        if zero_x is not None:
            vl = pg.InfiniteLine(
                pos=zero_x, angle=90,
                pen=pg.mkPen('#ffff00', width=2, style=Qt.DotLine),
                label=f'Zero Γ  {strikes_vis[int(zero_x)]:.0f}',
                labelOpts={'color': '#ffff00', 'position': 0.95}
            )
            self._gex_plot.addItem(vl)

        # x축 레이블 (행사가)
        ax = self._gex_plot.getAxis('bottom')
        ax.setTicks([[(i, str(int(s))) for i, s in enumerate(strikes_vis)]])

        # ── Skew 라인 ────────────────────────────────────────
        self._skew_plot.clear()
        self._skew_plot.addLine(
            y=0, pen=pg.mkPen('#555', width=1))
        curve = self._skew_plot.plot(
            xs, skew_vals,
            pen=pg.mkPen('#ffd700', width=2),
            symbol='o', symbolSize=4,
            symbolBrush='#ffd700'
        )
        ax2 = self._skew_plot.getAxis('bottom')
        ax2.setTicks([[(i, str(int(s))) for i, s in enumerate(strikes_vis)]])

    @staticmethod
    def _find_zero_gamma(xs, gex_vals):
        """GEX 부호 교차점 찾기 → 보간 x 반환."""
        for i in range(len(gex_vals) - 1):
            if gex_vals[i] * gex_vals[i + 1] < 0:
                # 선형 보간
                x0, x1 = xs[i], xs[i + 1]
                g0, g1  = gex_vals[i], gex_vals[i + 1]
                return x0 + abs(g0) / (abs(g0) + abs(g1)) * (x1 - x0)
        return None

    # ─────────────────────────────────────────────────────────
    # SQLite 저장
    # ─────────────────────────────────────────────────────────
    def _autosave(self):
        if not self.chk_autosave.isChecked():
            return
        if not self.strikes or not self._cell_data:
            return
        if not is_market_open():
            return
        self._do_save()

    def _manual_save(self):
        self._do_save()
        QMessageBox.information(self, "저장", "Greeks 스냅샷 저장 완료")

    def _do_save(self):
        rows = []
        for r, st in enumerate(self.strikes):
            for side, key in (("C", r), ("P", r)):
                d = self._cell_data.get((r, side))
                if not d:
                    continue
                rows.append((
                    st, side,
                    d.get("delta", 0.0),
                    d.get("gamma", 0.0),
                    d.get("iv",    0.0),
                    d.get("vanna", 0.0),
                ))
        if not rows:
            return
        try:
            _save_to_db(self._db, self.sym, self.expiry,
                        self.und_price, rows)
            self.lbl_save.setText(f"저장: {ts()}")
        except Exception as e:
            print(f"[GreeksGrid] DB 저장 오류: {e}")

    # ─────────────────────────────────────────────────────────
    # 설정 저장/복원 (TabWrapper 연동)
    # ─────────────────────────────────────────────────────────
    def _get_extra_settings(self) -> dict:
        d = {}
        try:
            d["h_split"]       = list(self._h_split.sizes())
            d["chart_vsplit"]  = list(self._chart_vsplit.sizes())
            d["delta_filter"]  = self.sld_delta.value()
            d["sym"]           = self.edit_sym.text()
            d["exp_idx"]       = self.combo_exp.currentIndex()
            d["autosave"]      = self.chk_autosave.isChecked()
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        def _restore():
            try:
                if s.get("h_split"):
                    self._h_split.setSizes(s["h_split"])
                if s.get("chart_vsplit"):
                    self._chart_vsplit.setSizes(s["chart_vsplit"])
                if "delta_filter" in s:
                    self.sld_delta.setValue(s["delta_filter"])
                if "sym" in s:
                    self.edit_sym.setText(s["sym"])
                if "exp_idx" in s:
                    self.combo_exp.setCurrentIndex(s["exp_idx"])
                if "autosave" in s:
                    self.chk_autosave.setChecked(s["autosave"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)

    # ─────────────────────────────────────────────────────────
    # 탭 활성화/비활성화 (main.py 호출)
    # ─────────────────────────────────────────────────────────
    def on_tab_activate(self):
        """
        탭 포커스 진입 시 호출.
        구독은 _connect_signals()에서 이미 항상 유지됨 → 별도 조치 불필요.
        (탭이 숨겨져도 QTimer·router 구독 모두 활성 상태)
        """
        pass

    def on_tab_deactivate(self):
        """
        탭 포커스 이탈 시 호출.
        과부하 방지: throttle 타이머는 유지하되 렌더는 탭 활성 여부 무관하게
        처리 (데이터 누락 방지). 화면 갱신은 Qt가 백그라운드 탭에서
        자동 최소화하므로 추가 중단 불필요.
        """
        pass

    # ─────────────────────────────────────────────────────────
    # 테마 전환 (TabWrapper 호환)
    # ─────────────────────────────────────────────────────────
    def _apply_theme(self):
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        _apply_table_theme(self.tbl, dark)


# ── 유틸 ──────────────────────────────────────────────────────
def _vline() -> QFrame:
    """컨트롤바 구분선."""
    from PyQt5.QtWidgets import QFrame
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#2e3060;")
    return f