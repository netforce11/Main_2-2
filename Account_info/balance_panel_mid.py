"""
balance_panel_mid.py — 중단 3패널  v2.0
[2,0-3] 일자별 차트  /  [2,4-7] Session Stats  /  [2,8-11] 미체결 주문

설정하는 self 속성:
    pw_nlv, curve_nlv, pw_pnl, curve_pnl   (pyqtgraph)
    lbl_winrate, lbl_avghold, lbl_tot_pnl, lbl_tot_cnt
    tbl_trades, tbl_ord
"""

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QGridLayout, QWidget,
    QLabel, QPushButton,
)
from PyQt5.QtGui   import QFont
from PyQt5.QtCore  import Qt
from core          import make_table
from Account_info.balance_style import CS


def build_chart_panel(self) -> QGroupBox:
    """[2,0-3] 일자별 잔고·손익 차트."""
    gb = QGroupBox("일자별 잔고·손익 추이")
    gb.setStyleSheet(CS["card"])
    vc = QVBoxLayout(gb); vc.setSpacing(6)

    if PG:
        pg.setConfigOption('background', '#f8fafc')
        pg.setConfigOption('foreground', '#64748b')

        lbl_nlv = QLabel("총자산")
        lbl_nlv.setStyleSheet(
            "color:#475569;font-size:10px;font-weight:700;"
            "letter-spacing:0.5px;border:none;")

        self.pw_nlv = pg.PlotWidget()
        self.pw_nlv.showGrid(x=False, y=True, alpha=0.25)
        self.pw_nlv.setMaximumHeight(90)
        self.pw_nlv.getPlotItem().hideAxis('bottom')
        self.pw_nlv.setStyleSheet("border:none;border-radius:6px;")
        self.curve_nlv = self.pw_nlv.plot(
            pen=pg.mkPen('#1d4ed8', width=2), symbol=None)

        lbl_pnl = QLabel("일별 손익")
        lbl_pnl.setStyleSheet(
            "color:#475569;font-size:10px;font-weight:700;"
            "letter-spacing:0.5px;border:none;margin-top:4px;")

        self.pw_pnl = pg.PlotWidget()
        self.pw_pnl.showGrid(x=False, y=True, alpha=0.25)
        self.pw_pnl.setMaximumHeight(70)
        self.pw_pnl.getPlotItem().hideAxis('bottom')
        self.pw_pnl.setStyleSheet("border:none;border-radius:6px;")
        self.pw_pnl.addLine(y=0, pen=pg.mkPen('#cbd5e1', width=1))
        self.curve_pnl = self.pw_pnl.plot(
            pen=pg.mkPen('#15803d', width=2), symbol=None)

        vc.addWidget(lbl_nlv)
        vc.addWidget(self.pw_nlv)
        vc.addWidget(lbl_pnl)
        vc.addWidget(self.pw_pnl)
    else:
        vc.addWidget(QLabel("pip install pyqtgraph"))
    return gb


def build_session_panel(self) -> QGroupBox:
    """[2,4-7] Session Stats — KPI 4개 + 거래 테이블."""
    gb = QGroupBox("Session Stats")
    gb.setStyleSheet(CS["card"])
    g = QGridLayout(gb); g.setSpacing(7)

    KPI = [
        ("승률",      "lbl_winrate"),
        ("평균 보유", "lbl_avghold"),
        ("누적 손익", "lbl_tot_pnl"),
        ("총 거래",   "lbl_tot_cnt"),
    ]
    for i, (title, attr) in enumerate(KPI):
        kpi = QWidget()
        kpi.setMinimumHeight(56)     # KPI 카드 높이 확보
        kpi.setStyleSheet("background:#f1f5f9;border-radius:8px;border:none;")
        kv = QVBoxLayout(kpi)
        kv.setContentsMargins(12, 8, 12, 8); kv.setSpacing(2)

        lb_t = QLabel(title)
        lb_t.setStyleSheet(
            "color:#475569;font-size:10px;font-weight:700;"
            "letter-spacing:0.5px;border:none;")

        lb_v = QLabel("―")
        lb_v.setFont(QFont("Arial", 13, QFont.Bold))
        lb_v.setMinimumWidth(60)     # 값 잘림 방지
        lb_v.setStyleSheet("color:#94a3b8;border:none;")

        kv.addWidget(lb_t); kv.addWidget(lb_v)
        setattr(self, attr, lb_v)   # 기존 코드가 직접 setText 호출
        g.addWidget(kpi, i // 2, i % 2)

    self.tbl_trades = make_table(
        ["시간","심볼","방향","수량","진입가","청산가","PnL","보유(분)"], 0)
    self.tbl_trades.setStyleSheet(CS["tbl"])
    self.tbl_trades.setAlternatingRowColors(True)
    g.addWidget(self.tbl_trades, 2, 0, 1, 2)

    btn_clr = QPushButton("Session 초기화")
    btn_clr.setStyleSheet(CS["btn_gray"])
    btn_clr.clicked.connect(self._clear_session)
    g.addWidget(btn_clr, 3, 0, 1, 2)
    return gb


def build_order_panel(self) -> QGroupBox:
    """[2,8-11] 미체결 주문 테이블."""
    gb = QGroupBox("미체결 주문")
    gb.setStyleSheet(CS["card"])
    v = QVBoxLayout(gb)
    self.tbl_ord = make_table(
        ["ID","심볼","종류","매수/도","수량","지정가","상태"], 0)
    self.tbl_ord.setStyleSheet(CS["tbl"])
    self.tbl_ord.setAlternatingRowColors(True)
    self.tbl_ord.setRowCount(0)
    v.addWidget(self.tbl_ord)
    return gb