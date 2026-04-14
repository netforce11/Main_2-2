"""
combo_ui_right_panels_ext.py — 손익 결과 패널 · 차트 · 팝업 · Optimizer 토글
────────────────────────────────────────────────────────────────────────────
RightPanelMixin 에 mixin 되는 메서드 모음 (UI 전담).
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont as _QFont

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import STRATEGY_DESC


# ── 손익 분석 결과 패널 ─────────────────────────────────────────

def _build_result_panel(self) -> QGroupBox:
    gb = QGroupBox("📈 손익 분석 결과")
    v  = QVBoxLayout(gb); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

    # KPI 카드 행
    kpi_row = QHBoxLayout(); kpi_row.setSpacing(8); self._kpi_widgets = {}
    _KPI = [
        ("max_profit", "최대 이익",  "#00ff88"),
        ("max_loss",   "최대 손실",  "#ff4444"),
        ("breakeven1", "손익분기①", "#ffd700"),
        ("breakeven2", "손익분기②", "#ffd700"),
        ("cost",       "순 비용",    "#90caf9"),
        ("rr",         "R:R",        "#ff8844"),
    ]
    for key, label, col in _KPI:
        box = QWidget(); bv = QVBoxLayout(box); bv.setContentsMargins(6, 4, 6, 4)
        box.setStyleSheet(
            "border:1px solid #2a2a4a;border-radius:5px;background:#0a0a1e;")
        lk = QLabel(label)
        lk.setStyleSheet(f"color:{col};font-size:13px;font-weight:bold;border:none;")
        lv = QLabel("―")
        lv.setFont(_QFont("Arial", 16, _QFont.Bold))
        lv.setStyleSheet(f"color:{col};border:none;")
        lv.setAlignment(Qt.AlignCenter)
        bv.addWidget(lk); bv.addWidget(lv)
        self._kpi_widgets[key] = lv
        kpi_row.addWidget(box)
    v.addLayout(kpi_row)

    # 스프레드 세부 그리드
    sg = QGridLayout(); sg.setSpacing(6); self._spread_labels = {}
    _SG = [
        ("call_spread", "콜 스프레드"), ("put_spread",  "풋 스프레드"),
        ("buy_cost",    "매수 비용"),   ("max_gain",    "최대 이익"),
        ("credit",      "수취 크레딧"), ("margin",      "예상 증거금"),
    ]
    for i, (key, label) in enumerate(_SG):
        lk = QLabel(label + ":")
        lk.setStyleSheet("color:#aaa;font-size:13px;border:none;")
        lv = QLabel("―")
        lv.setStyleSheet("color:#ffd700;font-size:14px;font-weight:bold;border:none;")
        sg.addWidget(lk, i // 2, (i % 2) * 2)
        sg.addWidget(lv, i // 2, (i % 2) * 2 + 1)
        self._spread_labels[key] = lv
    v.addLayout(sg)

    v.addWidget(QLabel("행사가별 손익  (BEP 근처)"))
    self.tbl_scenario = QTableWidget(0, 6)
    self.tbl_scenario.setHorizontalHeaderLabels(
        ["기초자산 가격", "총 PnL ($)", "PnL (×100)", "수익률 (%)", "콜 레그", "풋 레그"])
    self.tbl_scenario.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.tbl_scenario.verticalHeader().setVisible(False)
    self.tbl_scenario.setEditTriggers(QAbstractItemView.NoEditTriggers)
    self.tbl_scenario.setAlternatingRowColors(True)
    self.tbl_scenario.setStyleSheet(
        "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
        "color:#ccc;gridline-color:#1a1a3a;}"
        "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
        "border:1px solid #1a1a3a;font-weight:bold;}")
    v.addWidget(self.tbl_scenario, 1)
    gb.setMinimumHeight(80)
    return gb


# ── 손익 곡선 패널 ──────────────────────────────────────────────

def _build_spread_chart_panel(self) -> QGroupBox:
    gb = QGroupBox("📉 손익 곡선")
    v  = QVBoxLayout(gb); v.setContentsMargins(4, 6, 4, 4)
    self._spread_labels = getattr(self, "_spread_labels", {})
    if PG:
        self._pw_pnl = pg.PlotWidget()
        self._pw_pnl.showGrid(x=True, y=True, alpha=0.2)
        self._pw_pnl.setLabel('left',   'PnL ($)')
        self._pw_pnl.setLabel('bottom', '기초자산 가격')
        self._pw_pnl.addLine(y=0, pen=pg.mkPen('#444', width=1))
        self._curve_pnl = self._pw_pnl.plot(
            pen=pg.mkPen('#00ff88', width=2), name="PnL")
        self._curve_be  = self._pw_pnl.plot(
            pen=pg.mkPen('#ffd700', width=1, style=Qt.DashLine))
        v.addWidget(self._pw_pnl, 1)
    else:
        v.addWidget(QLabel("pip install pyqtgraph"))
    gb.setMinimumHeight(80)
    return gb


# ── 전략 설명 팝업 ──────────────────────────────────────────────

def _show_strat_desc(self):
    strat = self.combo_strat.currentText()
    desc  = STRATEGY_DESC.get(strat, "설명 정보가 없습니다.")
    dlg   = QMessageBox(self)
    dlg.setWindowTitle("전략 설명")
    dlg.setText(desc)
    dlg.setStyleSheet(
        "QMessageBox{background:#0d0d22;color:#ccc;}"
        "QLabel{color:#ffd700;font-size:13px;min-width:480px;}"
        "QPushButton{background:#1a2a4a;color:#90caf9;"
        "border:1px solid #3a3a6a;border-radius:4px;"
        "padding:6px 18px;font-size:12px;}"
        "QPushButton:hover{background:#2a3a6a;}")
    dlg.exec_()


# ── Optimizer 슬라이드 토글 ─────────────────────────────────────

def _toggle_optimizer_panel(self):
    collapsed = (self._opt_wrapper.maximumHeight() == 0)
    anim = QPropertyAnimation(self._opt_wrapper, b"maximumHeight")
    anim.setDuration(220)
    anim.setStartValue(self._opt_wrapper.maximumHeight())
    anim.setEndValue(420 if collapsed else 0)
    anim.setEasingCurve(
        QEasingCurve.OutCubic if collapsed else QEasingCurve.InCubic)
    self._opt_anim = anim
    anim.start()
    if hasattr(self, "_btn_opt_toggle"):
        self._btn_opt_toggle.setText(
            "🔍 Cost Optimiser  ▲" if collapsed else "🔍 Cost Optimiser  ▼")
