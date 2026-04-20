"""
combo_ui_right_panels_ext.py — 손익 결과 패널 · 차트 · 팝업 · Optimizer 토글
────────────────────────────────────────────────────────────────────────────
v2.6 변경:
  _calc_pnl: N-레그(최대 8개) 손익 계산 지원
  순수 함수 분리 → combo_pnl_calc.py
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont as _QFont

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import STRATEGY_DESC
from combo_pnl_calc import (
    _make_price_range, _leg_pnl_at_expiry,
    _find_breakevens, _fill_scenario_table,
)


# ── 손익 분석 결과 패널 ─────────────────────────────────────────

def _build_result_panel(self) -> QGroupBox:
    gb = QGroupBox("📈 손익 분석 결과")
    v  = QVBoxLayout(gb); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

    kpi_row = QHBoxLayout(); kpi_row.setSpacing(8); self._kpi_widgets = {}
    for key, label, col in [
        ("max_profit","최대 이익","#00ff88"), ("max_loss","최대 손실","#ff4444"),
        ("breakeven1","손익분기①","#ffd700"), ("breakeven2","손익분기②","#ffd700"),
        ("cost","순 비용","#90caf9"),         ("rr","R:R","#ff8844"),
    ]:
        box = QWidget(); bv = QVBoxLayout(box); bv.setContentsMargins(6,4,6,4)
        box.setStyleSheet("border:1px solid #2a2a4a;border-radius:5px;background:#0a0a1e;")
        lk = QLabel(label)
        lk.setStyleSheet(f"color:{col};font-size:13px;font-weight:bold;border:none;")
        lv = QLabel("―"); lv.setFont(_QFont("Arial", 16, _QFont.Bold))
        lv.setStyleSheet(f"color:{col};border:none;"); lv.setAlignment(Qt.AlignCenter)
        bv.addWidget(lk); bv.addWidget(lv)
        self._kpi_widgets[key] = lv; kpi_row.addWidget(box)
    v.addLayout(kpi_row)

    sg = QGridLayout(); sg.setSpacing(6); self._spread_labels = {}
    for i, (key, label) in enumerate([
        ("call_spread","콜 스프레드"), ("put_spread","풋 스프레드"),
        ("buy_cost","매수 비용"),      ("max_gain","최대 이익"),
        ("credit","수취 크레딧"),      ("margin","예상 증거금"),
    ]):
        lk = QLabel(label + ":")
        lk.setStyleSheet("color:#aaa;font-size:13px;border:none;")
        lv = QLabel("―")
        lv.setStyleSheet("color:#ffd700;font-size:14px;font-weight:bold;border:none;")
        sg.addWidget(lk, i//2, (i%2)*2); sg.addWidget(lv, i//2, (i%2)*2+1)
        self._spread_labels[key] = lv
    v.addLayout(sg)

    v.addWidget(QLabel("행사가별 손익  (BEP 근처)"))
    self.tbl_scenario = QTableWidget(0, 6)
    self.tbl_scenario.setHorizontalHeaderLabels(
        ["기초자산 가격","총 PnL ($)","PnL (×100)","수익률 (%)","콜 레그","풋 레그"])
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
        self._pw_pnl.setLabel('left', 'PnL ($)')
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


# ── N-레그 손익 계산 ────────────────────────────────────────────

def _calc_pnl(self):
    """📊 손익 계산 버튼 핸들러. 최대 8레그 모두 반영."""
    from combo_order_utils import _parse_legs_from_table, _calc_required_margin

    legs = _parse_legs_from_table(self)
    if not legs:
        QMessageBox.warning(self, "입력 오류",
            "행사가와 프리미엄을 먼저 입력하세요.")
        return

    strikes    = [l["strike"] for l in legs]
    min_s, max_s = min(strikes), max(strikes)
    spread_width = max_s - min_s if max_s > min_s else 50.0

    # 스트라이크 범위 바깥으로 충분히 확장 (양쪽 spread_width * 1.5 또는 최소 50pt)
    padding    = max(spread_width * 1.5, 50.0)
    range_low  = min_s - padding
    range_high = max_s + padding

    # 전체 범위를 40행 기준으로 스텝 결정 (최소 2.5, 최대 25)
    total_width = range_high - range_low
    price_step  = max(2.5, min(25.0, round(total_width / 40, 1)))
    price_range = _make_price_range(range_low, range_high, price_step)

    pnl_series  = [_leg_pnl_at_expiry(leg, price_range) for leg in legs]
    total_pnl   = [sum(s[i] for s in pnl_series) for i in range(len(price_range))]

    net_cost = sum(
        float(l.get("prem", 0) or 0) * int(l.get("qty", 1)) *
        (1 if l["dir"] == "BUY" else -1)
        for l in legs)
    net_cost_100 = round(net_cost * 100, 2)
    max_profit   = max(total_pnl)
    max_loss     = min(total_pnl)
    breakevens   = _find_breakevens(price_range, total_pnl)
    margin       = _calc_required_margin(legs)
    # 장외 시간이면 25% 할증 표시 (combo_order_logic 과 동일 로직)
    try:
        from combo_order_logic import _is_after_hours, _AFTER_HOURS_SURCHARGE
        if _is_after_hours():
            margin = round(margin * (1 + _AFTER_HOURS_SURCHARGE), 2)
    except Exception:
        pass
    rr = abs(max_profit / max_loss) if max_loss < 0 else float('inf')

    kw = self._kpi_widgets
    kw['max_profit'].setText(f"${max_profit*100:,.0f}")
    kw['max_loss'  ].setText(f"${max_loss*100:,.0f}")
    kw['breakeven1'].setText(f"{breakevens[0]:.1f}" if len(breakevens) > 0 else "―")
    kw['breakeven2'].setText(f"{breakevens[1]:.1f}" if len(breakevens) > 1 else "―")
    kw['cost'      ].setText(
        f"{'데빗' if net_cost >= 0 else '크레딧'} ${abs(net_cost_100):,.0f}")
    kw['rr'        ].setText(f"1 : {rr:.1f}" if rr != float('inf') else "∞")

    call_legs    = [l for l in legs if l["cp"].upper() == "C"]
    put_legs     = [l for l in legs if l["cp"].upper() == "P"]
    call_strikes = sorted(set(l["strike"] for l in call_legs))
    put_strikes  = sorted(set(l["strike"] for l in put_legs), reverse=True)
    sl = self._spread_labels
    sl['call_spread'].setText(
        f"{call_strikes[0]:.0f}~{call_strikes[-1]:.0f}" if len(call_strikes) >= 2
        else (f"{call_strikes[0]:.0f}" if call_strikes else "―"))
    sl['put_spread'].setText(
        f"{put_strikes[0]:.0f}~{put_strikes[-1]:.0f}" if len(put_strikes) >= 2
        else (f"{put_strikes[0]:.0f}" if put_strikes else "―"))
    sl['buy_cost' ].setText(f"${abs(net_cost_100):,.0f}")
    sl['max_gain' ].setText(f"${max_profit*100:,.0f}")
    sl['credit'   ].setText(f"${abs(net_cost_100):,.0f}" if net_cost < 0 else "―")
    sl['margin'   ].setText(f"${margin:,.0f}")

    _fill_scenario_table(self, price_range, total_pnl, pnl_series, legs, net_cost)

    if PG and hasattr(self, '_curve_pnl'):
        pnl_100 = [p * 100 for p in total_pnl]
        self._curve_pnl.setData(price_range, pnl_100)
        if hasattr(self, '_curve_be') and breakevens:
            be_x = [v for bep in breakevens for v in (bep, bep)]
            be_y = [min(pnl_100), max(pnl_100)] * len(breakevens)
            self._curve_be.setData(be_x, be_y)

    self._log(f"📊 손익 계산 완료: {len(legs)}레그  "
              f"최대이익=${max_profit*100:,.0f}  최대손실=${max_loss*100:,.0f}")


# ── 전략 설명 팝업 ──────────────────────────────────────────────

def _show_strat_desc(self):
    strat = self.combo_strat.currentText()
    desc  = STRATEGY_DESC.get(strat, "설명 정보가 없습니다.")
    dlg   = QMessageBox(self)
    dlg.setWindowTitle("전략 설명"); dlg.setText(desc)
    dlg.setStyleSheet(
        "QMessageBox{background:#0d0d22;color:#ccc;}"
        "QLabel{color:#ffd700;font-size:13px;min-width:480px;}"
        "QPushButton{background:#1a2a4a;color:#90caf9;"
        "border:1px solid #3a3a6a;border-radius:4px;"
        "padding:6px 18px;font-size:12px;}"
        "QPushButton:hover{background:#2a3a6a;}")
    dlg.exec_()


# ── Optimizer 팝업 토글 (v2.3 — 슬라이드 방식 → 독립 창 방식으로 교체) ──

def _toggle_optimizer_panel(self):
    """
    🔍 Optimiser 버튼 핸들러.
    메인 화면 안에서 펼쳐지는 슬라이드 방식 대신
    완전히 별도의 독립 창(QDialog)을 띄운다.
    이미 열려 있으면 앞으로 가져오고, 없으면 새로 생성.
    """
    from combo_op.combo_op_dialog import OptimizerDialog

    dlg = getattr(self, '_optimizer_dialog', None)
    if dlg is not None and dlg.isVisible():
        dlg.raise_()
        dlg.activateWindow()
        return

    dlg = OptimizerDialog(self)
    self._optimizer_dialog = dlg
    dlg.show()