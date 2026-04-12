"""
combo_logic.py — 복합 전략 탭: 손익 계산 로직
════════════════════════════════════════════════════════════════
v2.2 변경사항:
  - T+0 이론가 손익 곡선 추가 (오렌지 파선)
  - IV 슬라이더 + DTE 슬라이더 → T+0 실시간 갱신
  - 현재가 수직선 (흰 점선)
  - _build_spread_chart_panel() 에서 슬라이더 위젯 빌드
    (combo_ui_right.py 의 _build_spread_chart_panel 을 오버라이드)
════════════════════════════════════════════════════════════════
"""

import math

from PyQt5.QtWidgets import (
    QMessageBox, QGroupBox, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QSpinBox,
)
from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from combo_constants import mk_item


# ══════════════════════════════════════════════════════════════
# Black-Scholes 이론가 (T+0 곡선용)
# ══════════════════════════════════════════════════════════════
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_price(S: float, K: float, T_days: float,
              iv_pct: float, cp: str) -> float:
    """
    Black-Scholes 이론가 (r=0 단순화).
    S  : 현재 기초자산 가격
    K  : 행사가
    T_days : 잔존일
    iv_pct : 연환산 IV (%)
    cp : 'C' 콜 / 'P' 풋
    """
    T     = max(T_days, 0.0) / 365.0
    sigma = iv_pct / 100.0
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        # 만기 도달 — 내재가치만
        if cp.upper() == "C":
            return max(0.0, S - K)
        return max(0.0, K - S)
    try:
        d1 = (math.log(S / K) + 0.5 * sigma ** 2 * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
    except (ValueError, ZeroDivisionError):
        return 0.0

    if cp.upper() == "C":
        return S * _norm_cdf(d1) - K * _norm_cdf(d2)
    else:
        return K * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# ══════════════════════════════════════════════════════════════
class PnlLogicMixin:
    """손익 계산 전용 Mixin."""

    # ──────────────────────────────────────────────────────────
    # 차트 패널 빌드 (combo_ui_right.py 의 기본 구현을 오버라이드)
    # ──────────────────────────────────────────────────────────
    def _build_spread_chart_panel(self) -> QGroupBox:
        """
        ★ v2.3: 손익 곡선 전용 패널 (우측).
        스프레드 계산 수치는 _build_result_panel 내부로 이동.
        슬라이더(IV / DTE) + pyqtgraph 차트만 포함.
        """
        gb = QGroupBox("📉 손익 곡선")
        v  = QVBoxLayout(gb)
        v.setContentsMargins(4, 6, 4, 4)
        v.setSpacing(4)

        # ── pyqtgraph 차트 ──────────────────────────────────
        if PG:
            pw = pg.PlotWidget(background="#07070f")
            pw.showGrid(x=True, y=True, alpha=0.25)
            pw.setLabel("left",   "손익 ($)",   color="#aaa")
            pw.setLabel("bottom", "기초자산 가격", color="#aaa")
            pw.addLegend(offset=(10, 10))

            # 만기 손익 (초록 실선)
            self._curve_pnl = pw.plot(
                pen=pg.mkPen("#00e676", width=2),
                name="만기 손익")

            # T+0 이론가 손익 (오렌지 파선)
            self._curve_t0 = pw.plot(
                pen=pg.mkPen("#ff9800", width=2, style=Qt.DashLine),
                name="T+0 (현재)")

            # 손익분기 수직선 (빨간 점선)
            self._curve_be = pw.plot(
                pen=pg.mkPen("#ff5252", width=1, style=Qt.DotLine))

            # 현재가 수직선 (흰 점선)
            self._curve_und = pw.plot(
                pen=pg.mkPen("#ffffff", width=1, style=Qt.DotLine),
                name="현재가")

            # 제로 기준선
            self._curve_zero = pw.plot(
                pen=pg.mkPen("#555555", width=1))

            v.addWidget(pw, 1)
        else:
            lbl = QLabel("pyqtgraph 미설치 — pip install pyqtgraph")
            lbl.setStyleSheet("color:#ff5252;font-size:11px;")
            v.addWidget(lbl)

        # ── T+0 슬라이더 영역 ────────────────────────────
        slider_row = QHBoxLayout()
        slider_row.setSpacing(12)

        # IV 슬라이더
        iv_lbl = QLabel("IV:")
        iv_lbl.setStyleSheet("color:#ff9800;font-size:11px;border:none;min-width:16px;")
        self.sld_t0_iv = QSlider(Qt.Horizontal)
        self.sld_t0_iv.setRange(5, 200)
        self.sld_t0_iv.setValue(20)
        self.sld_t0_iv.setFixedHeight(18)
        self.sld_t0_iv.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#ff9800;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#ff9800;border-radius:2px;}")
        self.lbl_t0_iv = QLabel("IV: 20%")
        self.lbl_t0_iv.setStyleSheet(
            "color:#ff9800;font-size:11px;border:none;min-width:60px;")
        self.sld_t0_iv.valueChanged.connect(self._on_t0_iv_changed)

        # DTE 슬라이더
        dte_lbl = QLabel("DTE:")
        dte_lbl.setStyleSheet("color:#64b5f6;font-size:11px;border:none;min-width:28px;")
        self.sld_t0_dte = QSlider(Qt.Horizontal)
        self.sld_t0_dte.setRange(0, 60)
        self.sld_t0_dte.setValue(1)
        self.sld_t0_dte.setFixedHeight(18)
        self.sld_t0_dte.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#64b5f6;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#64b5f6;border-radius:2px;}")
        self.lbl_t0_dte = QLabel("DTE: 1일")
        self.lbl_t0_dte.setStyleSheet(
            "color:#64b5f6;font-size:11px;border:none;min-width:60px;")
        self.sld_t0_dte.valueChanged.connect(self._on_t0_dte_changed)

        slider_row.addWidget(iv_lbl)
        slider_row.addWidget(self.sld_t0_iv, 2)
        slider_row.addWidget(self.lbl_t0_iv)
        slider_row.addSpacing(16)
        slider_row.addWidget(dte_lbl)
        slider_row.addWidget(self.sld_t0_dte, 2)
        slider_row.addWidget(self.lbl_t0_dte)
        slider_row.addStretch()
        v.addLayout(slider_row)

        gb.setMinimumHeight(180)
        return gb

    # ── 슬라이더 이벤트 ───────────────────────────────────
    def _on_t0_iv_changed(self, val: int):
        self.lbl_t0_iv.setText(f"IV: {val}%")
        self._refresh_t0()

    def _on_t0_dte_changed(self, val: int):
        self.lbl_t0_dte.setText(f"DTE: {val}일")
        self._refresh_t0()

    def _refresh_t0(self):
        """슬라이더 변경 시 T+0 곡선만 재계산."""
        if not PG:
            return
        legs = self._read_legs()
        if not legs:
            return

        try:
            stock_price = (float(self.edit_stock_price.text())
                           if self.edit_stock_price.isEnabled() else None)
            stock_qty   = (self.spin_stock_qty.value()
                           if self.edit_stock_price.isEnabled() else 0)
        except (ValueError, AttributeError):
            stock_price = None
            stock_qty   = 0

        ref_price = self._und_price or stock_price
        if ref_price is None:
            valid_strikes = [l["strike"] for l in legs if l["strike"]]
            ref_price = (sum(valid_strikes) / len(valid_strikes)
                         if valid_strikes else 100.0)

        iv_pct = self.sld_t0_iv.value()
        dte    = self.sld_t0_dte.value()

        xs, ys_t0 = self._build_t0_curve(legs, ref_price, stock_price,
                                          stock_qty, iv_pct, dte)
        if xs and hasattr(self, "_curve_t0"):
            self._curve_t0.setData(xs, ys_t0)

    # ──────────────────────────────────────────────────────────
    # 레그 읽기
    # ──────────────────────────────────────────────────────────
    def _read_legs(self) -> list:
        legs = []
        for r in range(self.tbl_legs.rowCount()):
            def cell(c, _r=r):
                it = self.tbl_legs.item(_r, c)
                return it.text().strip() if it else ""
            try:
                leg = {
                    "leg":    cell(0),
                    "dir":    cell(1),
                    "cp":     cell(2),
                    "strike": float(cell(3)) if cell(3) else None,
                    "prem":   float(cell(4)) if cell(4) else None,
                    "qty":    int(cell(5))   if cell(5) else 1,
                }
                legs.append(leg)
            except (ValueError, TypeError):
                pass
        return legs

    # ──────────────────────────────────────────────────────────
    # 메인 계산
    # ──────────────────────────────────────────────────────────
    def _calc_pnl(self):
        strat = self.combo_strat.currentText()
        legs  = self._read_legs()

        if not legs:
            QMessageBox.warning(self, "입력 오류", "레그 정보를 입력하세요.")
            return

        try:
            stock_price = (float(self.edit_stock_price.text())
                           if self.edit_stock_price.isEnabled() else None)
            stock_qty   = (self.spin_stock_qty.value()
                           if self.edit_stock_price.isEnabled() else 0)
        except ValueError:
            stock_price = None
            stock_qty   = 0

        ref_price = self._und_price or stock_price
        if ref_price is None:
            valid_strikes = [l["strike"] for l in legs if l["strike"]]
            ref_price = (sum(valid_strikes) / len(valid_strikes)
                         if valid_strikes else 100.0)

        scenarios = self._build_scenarios(legs, ref_price, stock_price, stock_qty)

        self._update_scenario_table(scenarios)
        self._update_kpi(scenarios, legs)
        self._update_spread(scenarios, legs)
        self._update_chart(scenarios)

        # T+0 곡선 초기 그리기
        iv_pct = self.sld_t0_iv.value()  if hasattr(self, "sld_t0_iv")  else 20
        dte    = self.sld_t0_dte.value() if hasattr(self, "sld_t0_dte") else 1
        xs, ys_t0 = self._build_t0_curve(
            legs, ref_price, stock_price, stock_qty, iv_pct, dte)
        if PG and xs and hasattr(self, "_curve_t0"):
            self._curve_t0.setData(xs, ys_t0)

        pnls       = [s[1] for s in scenarios]
        breakevens = self._find_breakevens(scenarios)
        self._log(
            f"손익 계산 완료 — {strat}  "
            f"최대이익=${max(pnls):,.2f}  최대손실=${min(pnls):,.2f}  "
            f"손익분기={[f'{b:.2f}' for b in breakevens]}")

    # ──────────────────────────────────────────────────────────
    # 만기 시나리오 생성 (기존 유지)
    # ──────────────────────────────────────────────────────────
    def _build_scenarios(self, legs, ref_price, stock_price, stock_qty) -> list:
        # ★ 가격 범위: ref_price 기준 ±30%
        lo = ref_price * 0.70
        hi = ref_price * 1.30

        # ★ 스텝: 레그 행사가 간격의 1/5 (최소 0.01)
        # 예) 681·682 → 간격 1 → 스텝 0.2 → 10배 촘촘해짐
        # 행사가 없으면 40등분 폴백
        valid_strikes = sorted(set(
            l["strike"] for l in legs
            if l.get("strike") is not None
        ))
        if len(valid_strikes) >= 2:
            min_gap = min(b - a for a, b in zip(valid_strikes, valid_strikes[1:]))
            step = max(0.01, min_gap / 5)
        elif len(valid_strikes) == 1:
            step = max(0.01, ref_price * 0.001)
        else:
            step = (hi - lo) / 40   # 폴백

        # 포인트 수 상한 801개 → 너무 촘촘해 느려지는 것 방지
        n = min(801, int((hi - lo) / step) + 1)
        step = (hi - lo) / (n - 1)
        prices = [lo + i * step for i in range(n)]

        cost_basis = self._cost_basis(legs)
        scenarios  = []

        for p in prices:
            pnl_call = pnl_put = 0.0
            for leg in legs:
                if leg["strike"] is None or leg["prem"] is None:
                    continue
                k   = leg["strike"]
                pm  = leg["prem"]
                qty = leg["qty"]
                mul = 1 if leg["dir"] == "BUY" else -1

                if leg["cp"].upper() == "C":
                    pnl_call += mul * (max(0.0, p - k) - pm) * qty * 100
                else:
                    pnl_put  += mul * (max(0.0, k - p) - pm) * qty * 100

            stock_pnl = (p - stock_price) * stock_qty if stock_price and stock_qty else 0.0
            total = pnl_call + pnl_put + stock_pnl
            pct   = (total / abs(cost_basis) * 100) if cost_basis else 0.0
            scenarios.append((p, total, total / 100, pct, pnl_call, pnl_put))

        return scenarios

    # ──────────────────────────────────────────────────────────
    # ★ T+0 이론가 손익 곡선 생성
    # ──────────────────────────────────────────────────────────
    def _build_t0_curve(self, legs, ref_price, stock_price,
                         stock_qty, iv_pct: float, dte: float):
        """
        각 가격 포인트에서 BS 이론가로 현재 평가가치를 계산.
        반환: (xs, ys) 리스트
        """
        lo    = ref_price * 0.70
        hi    = ref_price * 1.30
        step  = (hi - lo) / 80   # 만기 곡선보다 2배 촘촘하게
        prices = [lo + i * step for i in range(81)]

        xs, ys = [], []
        for S in prices:
            total = 0.0
            for leg in legs:
                if leg["strike"] is None or leg["prem"] is None:
                    continue
                K   = leg["strike"]
                pm  = leg["prem"]
                qty = leg["qty"]
                mul = 1 if leg["dir"] == "BUY" else -1
                cp  = leg["cp"].upper()

                theory = _bs_price(S, K, dte, iv_pct, cp)
                # 현재 평가손익 = (이론가 - 매입가) × 수량 × 100 × 방향
                total += mul * (theory - pm) * qty * 100

            if stock_price and stock_qty:
                total += (S - stock_price) * stock_qty

            xs.append(S)
            ys.append(total)
        return xs, ys

    # ──────────────────────────────────────────────────────────
    # 보조 계산
    # ──────────────────────────────────────────────────────────
    @staticmethod
    def _cost_basis(legs) -> float:
        return sum(
            l["prem"] * l["qty"] * 100 * (1 if l["dir"] == "BUY" else -1)
            for l in legs if l["prem"]
        )

    @staticmethod
    def _find_breakevens(scenarios) -> list:
        bes = []
        for i in range(len(scenarios) - 1):
            p1, t1 = scenarios[i][0],   scenarios[i][1]
            p2, t2 = scenarios[i+1][0], scenarios[i+1][1]
            if t1 * t2 <= 0 and t1 != t2:
                bes.append(p1 + (p2 - p1) * (-t1 / (t2 - t1)))
        return bes

    # ──────────────────────────────────────────────────────────
    # 테이블 갱신 — BEP 근처만 표시 (★ v2.3)
    # ──────────────────────────────────────────────────────────
    def _update_scenario_table(self, scenarios):
        """
        손익분기점(BEP) 기준 ± bep_margin % 범위의 행만 출력.
        BEP 없는 전략(커버드콜 등)은 현재가 기준으로 폴백.
        """
        BEP_MARGIN_PCT = 7.0   # BEP 양쪽 몇 % 까지 보여줄지

        breakevens = self._find_breakevens(scenarios)

        if breakevens:
            lo_be = min(breakevens)
            hi_be = max(breakevens)
        else:
            # BEP 없으면 현재가 또는 시나리오 중간값 사용
            prices   = [s[0] for s in scenarios]
            mid_price = (prices[0] + prices[-1]) / 2
            lo_be = hi_be = (self._und_price or mid_price)

        span   = max(hi_be - lo_be, lo_be * 0.01)   # 최소 스팬 보장
        margin = max(span, lo_be * (BEP_MARGIN_PCT / 100))
        lo_cut = lo_be - margin
        hi_cut = hi_be + margin

        self.tbl_scenario.setRowCount(0)
        for p, tot, tot100, pct, c_leg, p_leg in scenarios:
            if not (lo_cut <= p <= hi_cut):
                continue
            col = "#00ff88" if tot >= 0 else "#ff4444"
            r   = self.tbl_scenario.rowCount()
            self.tbl_scenario.insertRow(r)
            self.tbl_scenario.setItem(r, 0, mk_item(f"{p:,.2f}", "#ffd700"))
            self.tbl_scenario.setItem(r, 1, mk_item(f"${tot:,.2f}", col))
            self.tbl_scenario.setItem(r, 2, mk_item(f"${tot100:,.2f}", col))
            self.tbl_scenario.setItem(r, 3, mk_item(f"{pct:.1f}%", col))
            self.tbl_scenario.setItem(r, 4, mk_item(
                f"${c_leg:,.2f}", "#00ff88" if c_leg >= 0 else "#ff4444"))
            self.tbl_scenario.setItem(r, 5, mk_item(
                f"${p_leg:,.2f}", "#00ff88" if p_leg >= 0 else "#ff4444"))

    # ──────────────────────────────────────────────────────────
    # KPI 갱신 (기존 유지)
    # ──────────────────────────────────────────────────────────
    def _update_kpi(self, scenarios, legs):
        pnls       = [s[1] for s in scenarios]
        max_profit = max(pnls)
        max_loss   = min(pnls)
        breakevens = self._find_breakevens(scenarios)
        cost_basis = self._cost_basis(legs)
        rr = abs(max_profit / max_loss) if max_loss != 0 else float("inf")

        self._kpi_widgets["max_profit"].setText(
            f"${max_profit:,.2f}" if max_profit < 999999 else "무제한")
        self._kpi_widgets["max_loss"].setText(
            f"${max_loss:,.2f}" if max_loss > -999999 else "무제한")
        self._kpi_widgets["breakeven1"].setText(
            f"{breakevens[0]:,.2f}" if len(breakevens) > 0 else "―")
        self._kpi_widgets["breakeven2"].setText(
            f"{breakevens[1]:,.2f}" if len(breakevens) > 1 else "―")
        self._kpi_widgets["cost"].setText(
            f"${abs(cost_basis):,.2f} {'수취' if cost_basis < 0 else '지불'}")
        self._kpi_widgets["rr"].setText(
            f"{rr:.2f}:1" if rr < 999 else "∞")

    # ──────────────────────────────────────────────────────────
    # 스프레드 계산 갱신 (기존 유지)
    # ──────────────────────────────────────────────────────────
    def _update_spread(self, scenarios, legs):
        pnls       = [s[1] for s in scenarios]
        max_profit = max(pnls)
        cost_basis = self._cost_basis(legs)
        credit     = -cost_basis if cost_basis < 0 else 0

        call_legs    = [l for l in legs if l.get("cp", "").upper() == "C" and l["strike"]]
        put_legs     = [l for l in legs if l.get("cp", "").upper() == "P" and l["strike"]]
        call_strikes = sorted(l["strike"] for l in call_legs)
        put_strikes  = sorted(l["strike"] for l in put_legs)

        c_spread = (call_strikes[-1] - call_strikes[0]
                    if len(call_strikes) > 1 else 0)
        p_spread = (put_strikes[-1] - put_strikes[0]
                    if len(put_strikes) > 1 else 0)

        self._spread_labels["call_spread"].setText(
            f"${c_spread:.2f}" if c_spread else "단일 레그")
        self._spread_labels["put_spread"].setText(
            f"${p_spread:.2f}" if p_spread else "단일 레그")
        self._spread_labels["buy_cost"].setText(f"${abs(cost_basis):,.2f}")
        self._spread_labels["max_gain"].setText(
            f"${max_profit:,.2f}" if max_profit < 999999 else "무제한")
        self._spread_labels["credit"].setText(
            f"${credit:,.2f}" if credit > 0 else "―")

        if call_legs and len(call_strikes) > 1:
            margin = c_spread * max(l["qty"] for l in call_legs) * 100 - credit
        elif put_legs and len(put_strikes) > 1:
            margin = p_spread * max(l["qty"] for l in put_legs) * 100 - credit
        else:
            margin = abs(cost_basis)
        self._spread_labels["margin"].setText(f"~${margin:,.2f}")

    # ──────────────────────────────────────────────────────────
    # 차트 갱신
    # ──────────────────────────────────────────────────────────
    def _update_chart(self, scenarios):
        if not PG:
            return
        xs = [s[0] for s in scenarios]
        ys = [s[1] for s in scenarios]

        # _curve_pnl 은 combo_ui_right.py 또는 이 파일 어느 쪽에서
        # 차트 패널이 빌드되어도 반드시 존재한다.
        self._curve_pnl.setData(xs, ys)

        # 손익분기 수직선 (_curve_be 는 항상 존재)
        breakevens = self._find_breakevens(scenarios)
        if breakevens:
            y_lo = min(ys) * 1.1
            y_hi = max(ys) * 1.1
            self._curve_be.setData(
                [breakevens[0], breakevens[0]], [y_lo, y_hi])
        else:
            self._curve_be.setData([], [])

        # ★ 제로 기준선 — _build_spread_chart_panel 오버라이드가
        #   적용된 경우에만 존재. 없으면 조용히 건너뜀.
        if xs and hasattr(self, "_curve_zero"):
            self._curve_zero.setData([xs[0], xs[-1]], [0, 0])

        # ★ 현재가 수직선 — 동일하게 방어
        und = self._und_price
        if hasattr(self, "_curve_und"):
            if und and ys:
                y_lo = min(ys) * 1.1
                y_hi = max(ys) * 1.1
                self._curve_und.setData([und, und], [y_lo, y_hi])
            else:
                self._curve_und.setData([], [])