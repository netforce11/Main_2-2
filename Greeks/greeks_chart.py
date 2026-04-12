"""
greeks_chart.py — Greeks 차트 패널
════════════════════════════════════════════════════════════════
• GEX 막대 차트 (Call+/Put-)
• IV Skew 라인
• Normal Band 차트 — Gamma/IV 시계열 + 과거 평균±σ 밴드
  → "평소와 다른가" 시각적 판단용
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter
from PyQt5.QtCore    import Qt
from typing          import List, Optional

try:
    import pyqtgraph as pg
    import numpy as np
    PG = True
except ImportError:
    PG = False

POS_ESTIMATE = 500   # OI 없을 때 GEX 포지션 추정치


# ══════════════════════════════════════════════════════════════
# GEX + Skew 차트
# ══════════════════════════════════════════════════════════════
class GexSkewPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        if not PG:
            lay.addWidget(QLabel("pip install pyqtgraph  →  차트 활성화"))
            return

        pg.setConfigOption('background', '#08080f')
        pg.setConfigOption('foreground', '#cccccc')

        split = QSplitter(Qt.Vertical)

        self._gex  = pg.PlotWidget(title="GEX  (Gamma Exposure Estimate)")
        self._gex.showGrid(x=False, y=True, alpha=0.25)
        self._gex.setLabel('left', 'GEX', color='#aaa')
        self._gex.addLine(y=0, pen=pg.mkPen('#ff4444', width=1.5,
                                             style=Qt.DashLine))

        self._skew = pg.PlotWidget(title="IV Skew  (Call IV − Put IV)")
        self._skew.showGrid(x=True, y=True, alpha=0.25)
        self._skew.setLabel('left', 'Skew', color='#aaa')
        self._skew.addLine(y=0, pen=pg.mkPen('#555', width=1))

        split.addWidget(self._gex)
        split.addWidget(self._skew)
        split.setSizes([300, 200])
        lay.addWidget(split)

    def update(self, strikes: List[float], cell_data: dict):
        if not PG:
            return
        xs, gex_vals, skew_vals = [], [], []
        for r, st in enumerate(strikes):
            c = cell_data.get((r, "C"))
            p = cell_data.get((r, "P"))
            if not c and not p:
                continue
            cg = c["gamma"] if c else 0.0
            pg_ = p["gamma"] if p else 0.0
            ci  = c["iv"]    if c else 0.0
            pi  = p["iv"]    if p else 0.0
            xs.append(st)
            gex_vals.append((cg - pg_) * POS_ESTIMATE * 100)
            skew_vals.append(ci - pi)

        if not xs:
            return

        idx = list(range(len(xs)))
        tick_labels = [(i, str(int(s))) for i, s in enumerate(xs)]

        # GEX 막대
        self._gex.clear()
        self._gex.addLine(y=0, pen=pg.mkPen('#ff4444', width=1.5,
                                              style=Qt.DashLine))
        brushes = ['#3388ff' if v >= 0 else '#ff5555' for v in gex_vals]
        self._gex.addItem(pg.BarGraphItem(
            x=idx, height=gex_vals, width=0.7,
            brushes=brushes, pen=pg.mkPen('#111', width=0.5)))

        zero_x = _find_zero_gamma(idx, gex_vals)
        if zero_x is not None:
            zi = int(round(zero_x))
            label = f"Zero Γ {xs[zi]:.0f}" if 0 <= zi < len(xs) else "Zero Γ"
            self._gex.addItem(pg.InfiniteLine(
                pos=zero_x, angle=90,
                pen=pg.mkPen('#ffff00', width=2, style=Qt.DotLine),
                label=label, labelOpts={'color': '#ffff00', 'position': 0.95}
            ))
        self._gex.getAxis('bottom').setTicks([tick_labels])

        # Skew 라인
        self._skew.clear()
        self._skew.addLine(y=0, pen=pg.mkPen('#555', width=1))
        self._skew.plot(idx, skew_vals,
                        pen=pg.mkPen('#ffd700', width=2),
                        symbol='o', symbolSize=4, symbolBrush='#ffd700')
        self._skew.getAxis('bottom').setTicks([tick_labels])


# ══════════════════════════════════════════════════════════════
# Normal Band 차트 — "평소와 다른가" 판단
# ══════════════════════════════════════════════════════════════
class NormalBandPanel(QWidget):
    """
    ATM Gamma / ATM IV 시계열을 과거 평균±1σ 밴드와 함께 표시.
    밴드 이탈 = 급변동 시각 확인.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        if not PG:
            lay.addWidget(QLabel("pip install pyqtgraph  →  차트 활성화"))
            return

        split = QSplitter(Qt.Vertical)

        self._gamma_plot = pg.PlotWidget(title="ATM Gamma — 오늘 vs 평균±1σ")
        self._gamma_plot.showGrid(x=True, y=True, alpha=0.2)
        self._gamma_plot.setLabel('left', 'Gamma', color='#aaa')
        self._gamma_plot.setLabel('bottom', '시각', color='#aaa')
        self._gamma_today  = self._gamma_plot.plot(pen=pg.mkPen('#ff4444', width=2.5),
                                                    name="오늘")
        self._gamma_avg    = self._gamma_plot.plot(pen=pg.mkPen('#888', width=1,
                                                               style=Qt.DashLine),
                                                   name="과거평균")
        self._gamma_band_h = None
        self._gamma_band_l = None

        self._iv_plot = pg.PlotWidget(title="ATM IV — 오늘 vs 평균±1σ")
        self._iv_plot.showGrid(x=True, y=True, alpha=0.2)
        self._iv_plot.setLabel('left', 'IV', color='#aaa')
        self._iv_plot.setLabel('bottom', '시각', color='#aaa')
        self._iv_today = self._iv_plot.plot(pen=pg.mkPen('#00e5ff', width=2.5),
                                            name="오늘")
        self._iv_avg   = self._iv_plot.plot(pen=pg.mkPen('#888', width=1,
                                                          style=Qt.DashLine),
                                            name="과거평균")
        self._iv_band_h = None
        self._iv_band_l = None

        split.addWidget(self._gamma_plot)
        split.addWidget(self._iv_plot)
        split.setSizes([250, 250])
        lay.addWidget(split)

    def update_band(self,
                    today_ts: List[float],
                    today_gamma: List[float],
                    today_iv:    List[float],
                    hist_gamma:  List[float],   # 과거 같은 시간대 값들
                    hist_iv:     List[float]):
        """
        today_ts: 시각 x값 (epoch 또는 분 인덱스)
        """
        if not PG or not today_ts:
            return

        xs = today_ts

        # Gamma
        self._gamma_today.setData(xs, today_gamma)
        if hist_gamma:
            avg  = float(np.mean(hist_gamma))
            sig  = float(np.std(hist_gamma))
            self._gamma_avg.setData([xs[0], xs[-1]], [avg, avg])
            _fill_band(self._gamma_plot, xs, avg + sig, avg - sig,
                       QColor_str='#44334488')

        # IV
        self._iv_today.setData(xs, today_iv)
        if hist_iv:
            avg  = float(np.mean(hist_iv))
            sig  = float(np.std(hist_iv))
            self._iv_avg.setData([xs[0], xs[-1]], [avg, avg])
            _fill_band(self._iv_plot, xs, avg + sig, avg - sig,
                       QColor_str='#22334488')

    def clear(self):
        if not PG:
            return
        for p in (self._gamma_today, self._gamma_avg,
                  self._iv_today, self._iv_avg):
            p.setData([], [])


# ══════════════════════════════════════════════════════════════
# 내부 유틸
# ══════════════════════════════════════════════════════════════
def _find_zero_gamma(xs, vals):
    for i in range(len(vals) - 1):
        if vals[i] * vals[i + 1] < 0:
            x0, x1 = xs[i], xs[i + 1]
            g0, g1 = vals[i], vals[i + 1]
            return x0 + abs(g0) / (abs(g0) + abs(g1)) * (x1 - x0)
    return None


def _fill_band(plot_widget, xs, upper, lower, QColor_str='#33334488'):
    """±σ 음영 밴드 (FillBetweenItem)."""
    if not PG:
        return
    try:
        c1 = plot_widget.plot(xs, [upper] * len(xs),
                              pen=pg.mkPen(None))
        c2 = plot_widget.plot(xs, [lower] * len(xs),
                              pen=pg.mkPen(None))
        fill = pg.FillBetweenItem(c1, c2, brush=pg.mkBrush(QColor_str))
        plot_widget.addItem(fill)
    except Exception:
        pass