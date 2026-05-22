"""
combo_ui_right_panels_ext.py — 손익 결과 패널 · 차트 · 팝업 · Optimizer 토글
────────────────────────────────────────────────────────────────────────────
v2.6 변경:
  _calc_pnl: N-레그(최대 8개) 손익 계산 지원
v3.0 변경:
  _calc_pnl: 아이언 콘도르 / 버터플라이 전략 KPI 특화 계산 추가
    - 전략 자동 감지 → KPI 라벨 및 spread_labels 내용 전환
    - 아이언 콘도르: 수취 크레딧, 풋/콜 스프레드 너비, 손익분기 2개
    - 버터플라이: 날개 너비, 최대 이익 지점(바디), 손익분기 2개
    - 공통: 시나리오 테이블 5행 이상 강조 색상 적용
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QGroupBox, QTableWidget, QHeaderView, QAbstractItemView,
    QMessageBox, QTableWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont as _QFont, QColor, QBrush

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from combo_constants import STRATEGY_DESC
from combo_ui_panel_constants import _pal as _ext_pal
from combo_pnl_calc import (
    _make_price_range, _leg_pnl_at_expiry,
    _find_breakevens, _fill_scenario_table,
)


# ── 전략 감지 유틸 ──────────────────────────────────────────────

def _detect_strategy_type(legs: list, strat_name: str = "") -> str:
    """레그 구조 + 전략명으로 전략 유형을 분류."""
    name = strat_name.lower()
    if "아이언 버터플라이" in strat_name or "iron butterfly" in name:
        return "iron_butterfly"
    if "아이언 콘도르" in strat_name or "iron condor" in name:
        return "iron_condor"
    if "버터플라이" in strat_name or "butterfly" in name:
        cp_set = set(l["cp"].upper() for l in legs)
        if cp_set == {"C"}:
            return "call_butterfly"
        if cp_set == {"P"}:
            return "put_butterfly"
        return "butterfly"
    # ★ 백 스프레드 분류 추가
    if "콜 백 스프레드" in strat_name or "call back" in name:
        return "call_back_spread"
    if "풋 백 스프레드" in strat_name or "put back" in name:
        return "put_back_spread"
    return "generic"


# ── 손익 분석 결과 패널 ─────────────────────────────────────────

def _build_result_panel(self) -> QGroupBox:
    gb = QGroupBox("📈 손익 분석 결과")
    v  = QVBoxLayout(gb); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

    kpi_row = QHBoxLayout(); kpi_row.setSpacing(8); self._kpi_widgets = {}
    _t = _ext_pal()
    _is_dark = _t.get("win_bg", "#fff")[1:3].lower() < "88"
    # 의미색: 다크/라이트 분기
    _C_GAIN  = "#00cc66" if _is_dark else "#15803d"
    _C_LOSS  = "#ff4444" if _is_dark else "#dc2626"
    _C_GOLD  = "#e6b800" if _is_dark else "#92610a"
    _C_BLUE  = "#7eb8ff" if _is_dark else "#1d4ed8"
    _C_WARN  = "#ff7733" if _is_dark else "#c2410c"
    _C_SUB   = _t.get("hdr_fg",  "#888888")
    _C_VAL   = _t.get("group_title", "#ffd700")
    _KPI_BOX_BG  = _t.get("group_bg",     "#0a0a1e")
    _KPI_BOX_BDR = _t.get("group_border", "#2a2a4a")

    for key, label, col in [
        ("max_profit","최대 이익", _C_GAIN),
        ("max_loss",  "최대 손실", _C_LOSS),
        ("breakeven1","손익분기①", _C_GOLD),
        ("breakeven2","손익분기②", _C_GOLD),
        ("cost",      "순 비용",   _C_BLUE),
        ("rr",        "R:R",       _C_WARN),
    ]:
        box = QWidget(); bv = QVBoxLayout(box); bv.setContentsMargins(6,4,6,4)
        box.setStyleSheet(
            f"QWidget{{border:1px solid {_KPI_BOX_BDR};border-radius:5px;"
            f"background:{_KPI_BOX_BG};}}"
            "QLabel{border:none;background:transparent;}"
        )
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
        lk.setStyleSheet(f"color:{_C_SUB};font-size:13px;border:none;")
        lv = QLabel("―")
        lv.setStyleSheet(f"color:{_C_VAL};font-size:14px;font-weight:bold;border:none;")
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
        f"QTableWidget{{background:{_t.get('tbl_bg','#07070f')};"
        f"alternate-background-color:{_t.get('group_bg','#0c0c20')};"
        f"color:{_t.get('widget_fg','#cccccc')};"
        f"gridline-color:{_t.get('tbl_grid','#1a1a3a')};}}"
        f"QHeaderView::section{{background:{_t.get('hdr_bg','#0a0a1e')};"
        f"color:{_t.get('hdr_fg','#90caf9')};"
        f"border:1px solid {_t.get('hdr_border','#1a1a3a')};font-weight:bold;}}")
    v.addWidget(self.tbl_scenario, 1)
    gb.setMinimumHeight(80)
    return gb


# ── 손익 곡선 패널 ──────────────────────────────────────────────

def _build_spread_chart_panel(self) -> QGroupBox:
    gb = QGroupBox("📉 손익 곡선")
    v  = QVBoxLayout(gb); v.setContentsMargins(4, 6, 4, 4)
    # _spread_labels 는 _build_result_panel() 에서 이미 생성됨 — 덮어쓰지 않음

    if PG:
        # ── 차트 옵션 행: 색상 + 굵기 ──────────────────────────
        from PyQt5.QtWidgets import QComboBox, QHBoxLayout as _HBox, QLabel as _Lbl
        opt_row = _HBox(); opt_row.setSpacing(8)

        _ct = _ext_pal()
        _combo_ss = (
            f"QComboBox{{background:{_ct.get('input_bg','#1a1a2e')};"
            f"color:{_ct.get('group_title','#ffd700')};"
            f"border:1px solid {_ct.get('input_border','#3a3a6a')};"
            "border-radius:3px;font-size:11px;padding:1px 4px;}"
            "QComboBox::drop-down{border:none;}"
            f"QComboBox QAbstractItemView{{background:{_ct.get('combo_popup_bg','#0a0a1e')};"
            f"color:{_ct.get('combo_popup_fg','#cccccc')};}}"
        )
        _lbl_ss = f"color:{_ct.get('hdr_fg','#aaaaaa')};font-size:11px;border:none;"
        lbl_color = _Lbl("선 색상:")
        lbl_color.setStyleSheet(_lbl_ss)
        self._chart_color_combo = QComboBox()
        self._chart_color_combo.setFixedHeight(22)
        self._chart_color_combo.setFixedWidth(100)
        # 색상 항목: (표시명, hex코드)
        _CHART_COLORS = [
            ("빨간색",  "#ff4444"),
            ("검은색",  "#888888"),
            ("연두색",  "#00ff88"),
        ]
        for name, _ in _CHART_COLORS:
            self._chart_color_combo.addItem(name)
        self._chart_color_combo.setCurrentIndex(0)   # 기본값: 빨간색
        self._chart_color_combo.setStyleSheet(_combo_ss)

        lbl_width = _Lbl("굵기:")
        lbl_width.setStyleSheet(_lbl_ss)
        self._chart_width_combo = QComboBox()
        self._chart_width_combo.setFixedHeight(22)
        self._chart_width_combo.setFixedWidth(70)
        for w in ["얇게(1)", "보통(2)", "굵게(3)", "매우굵게(4)"]:
            self._chart_width_combo.addItem(w)
        self._chart_width_combo.setCurrentIndex(2)   # 기본값: 굵게(3)
        self._chart_width_combo.setStyleSheet(_combo_ss)

        # 변경 시 즉시 반영
        self._chart_color_combo.currentIndexChanged.connect(
            lambda _: _apply_chart_style(self, _CHART_COLORS))
        self._chart_width_combo.currentIndexChanged.connect(
            lambda _: _apply_chart_style(self, _CHART_COLORS))

        # 색상 목록을 위젯에 저장 (apply 함수에서 참조)
        self._chart_color_list = _CHART_COLORS

        opt_row.addWidget(lbl_color)
        opt_row.addWidget(self._chart_color_combo)
        opt_row.addWidget(lbl_width)
        opt_row.addWidget(self._chart_width_combo)
        opt_row.addStretch()
        v.addLayout(opt_row)

        # ── 차트 위젯 ──────────────────────────────────────────
        self._pw_pnl = pg.PlotWidget()
        self._pw_pnl.showGrid(x=True, y=True, alpha=0.2)
        self._pw_pnl.setLabel('left', 'PnL ($)')
        self._pw_pnl.setLabel('bottom', '기초자산 가격')
        _pg_t = _ext_pal()
        _zero_col = _pg_t.get('tbl_grid', '#444444')
        self._pw_pnl.addLine(y=0, pen=pg.mkPen(_zero_col, width=1))
        # 기본값: 빨간색 굵게(3)
        self._curve_pnl = self._pw_pnl.plot(
            pen=pg.mkPen('#ff4444', width=3), name="PnL")
        self._curve_be  = self._pw_pnl.plot(
            pen=pg.mkPen('#ffd700', width=1, style=Qt.DashLine))
        # BEP 텍스트 라벨 리스트 (동적 추가/제거)
        self._bep_labels = []
        # v3.0: 버터플라이 최대이익 지점 표시용 수직선
        self._line_body = self._pw_pnl.addLine(
            x=0, pen=pg.mkPen('#ff88ff', width=1, style=Qt.DotLine))
        self._line_body.setVisible(False)
        v.addWidget(self._pw_pnl, 1)
    else:
        v.addWidget(QLabel("pip install pyqtgraph"))
    gb.setMinimumHeight(80)
    return gb


def _apply_chart_style(self, color_list=None):
    """차트 색상/굵기 콤보 변경 시 curve_pnl 스타일 즉시 갱신."""
    if not PG or not hasattr(self, '_curve_pnl'):
        return
    cl = color_list or getattr(self, '_chart_color_list',
                                [("빨간색","#ff4444"),("검은색","#888888"),("연두색","#00ff88")])
    ci = self._chart_color_combo.currentIndex()
    _, hex_color = cl[ci] if ci < len(cl) else ("빨간색", "#ff4444")
    wi = self._chart_width_combo.currentIndex()
    width = wi + 1   # 0→1, 1→2, 2→3, 3→4
    self._curve_pnl.setPen(pg.mkPen(hex_color, width=width))


# ── N-레그 손익 계산 (v3.0 강화) ────────────────────────────────

def _calc_pnl(self):
    """📊 손익 계산 버튼 핸들러. 최대 8레그 + 전략별 KPI 특화."""
    from combo_order_utils import _parse_legs_from_table, _calc_required_margin

    legs = _parse_legs_from_table(self)
    if not legs:
        QMessageBox.warning(self, "입력 오류",
            "행사가와 프리미엄을 먼저 입력하세요.")
        return

    strat_name  = getattr(self, 'combo_strat', None)
    strat_name  = strat_name.currentText() if strat_name else ""
    strat_type  = _detect_strategy_type(legs, strat_name)

    strikes     = [l["strike"] for l in legs]
    min_s, max_s = min(strikes), max(strikes)
    spread_width = max_s - min_s if max_s > min_s else 50.0
    padding      = max(spread_width * 1.5, 50.0)
    price_step   = max(2.5, min(25.0, round((spread_width + 2*padding) / 40, 1)))
    price_range  = _make_price_range(min_s - padding, max_s + padding, price_step)

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
    try:
        from combo_order_logic import _is_after_hours, _AFTER_HOURS_SURCHARGE
        if _is_after_hours():
            margin = round(margin * (1 + _AFTER_HOURS_SURCHARGE), 2)
    except Exception:
        pass
    rr = abs(max_profit / max_loss) if max_loss < 0 else float('inf')

    # ── KPI 공통 갱신 ────────────────────────────────────────
    kw = self._kpi_widgets
    kw['max_profit'].setText(f"${max_profit*100:,.0f}")
    kw['max_loss'  ].setText(f"${max_loss*100:,.0f}")
    kw['breakeven1'].setText(f"{breakevens[0]:.1f}" if len(breakevens) > 0 else "―")
    kw['breakeven2'].setText(f"{breakevens[1]:.1f}" if len(breakevens) > 1 else "―")
    kw['rr'        ].setText(f"1 : {rr:.1f}" if rr != float('inf') else "∞")

    # ── 전략별 KPI 특화 ──────────────────────────────────────
    sl = self._spread_labels
    call_legs    = [l for l in legs if l["cp"].upper() == "C"]
    put_legs     = [l for l in legs if l["cp"].upper() == "P"]
    call_strikes = sorted(set(l["strike"] for l in call_legs))
    put_strikes  = sorted(set(l["strike"] for l in put_legs), reverse=True)

    if strat_type in ("iron_condor", "iron_butterfly"):
        # 크레딧 전략 — 수취 크레딧 강조
        net_credit   = abs(net_cost_100)
        put_width    = (put_strikes[0] - put_strikes[-1]) if len(put_strikes) >= 2 else 0
        call_width   = (call_strikes[-1] - call_strikes[0]) if len(call_strikes) >= 2 else 0
        kw['cost'].setText(f"크레딧 ${net_credit:,.0f}")
        sl['put_spread' ].setText(f"{put_strikes[-1]:.0f}~{put_strikes[0]:.0f} (너비 {put_width:.0f})"
                                   if len(put_strikes) >= 2 else "―")
        sl['call_spread'].setText(f"{call_strikes[0]:.0f}~{call_strikes[-1]:.0f} (너비 {call_width:.0f})"
                                   if len(call_strikes) >= 2 else "―")
        sl['buy_cost'   ].setText("―")
        sl['max_gain'   ].setText(f"${net_credit:,.0f}  (크레딧 전액)")
        sl['credit'     ].setText(f"${net_credit:,.0f}")
        sl['margin'     ].setText(f"${margin:,.0f}")

    elif strat_type in ("call_butterfly", "put_butterfly", "butterfly"):
        # 버터플라이 — 날개 너비, 바디(최대이익 지점) 강조
        all_strikes_sorted = sorted(set(l["strike"] for l in legs))
        body_k = None
        if len(all_strikes_sorted) >= 3:
            body_k = all_strikes_sorted[len(all_strikes_sorted) // 2]
        wing_width = (all_strikes_sorted[-1] - all_strikes_sorted[0]
                      ) if len(all_strikes_sorted) >= 2 else 0
        kw['cost'].setText(f"데빗 ${abs(net_cost_100):,.0f}")
        sl['call_spread'].setText(
            f"{call_strikes[0]:.0f}~{call_strikes[-1]:.0f}" if len(call_strikes) >= 2
            else (f"{call_strikes[0]:.0f}" if call_strikes else "―"))
        sl['put_spread' ].setText(
            f"{put_strikes[-1]:.0f}~{put_strikes[0]:.0f}" if len(put_strikes) >= 2
            else (f"{put_strikes[0]:.0f}" if put_strikes else "―"))
        sl['buy_cost'   ].setText(f"${abs(net_cost_100):,.0f}")
        sl['max_gain'   ].setText(
            f"${max_profit*100:,.0f}  @ K={body_k:.0f}" if body_k else f"${max_profit*100:,.0f}")
        sl['credit'     ].setText(f"날개 너비 {wing_width:.0f}pt")
        sl['margin'     ].setText(f"${margin:,.0f}")

        # 차트에 바디 수직선 표시
        if PG and body_k and hasattr(self, '_line_body'):
            self._line_body.setValue(body_k)
            self._line_body.setVisible(True)

    elif strat_type in ("call_back_spread", "put_back_spread"):
        # ★ 백 스프레드 — 방향 강조 (크레딧 수취지만 방향성 전략)
        direction_txt = "강한 상승 ▲" if strat_type == "call_back_spread" else "강한 하락 ▼"
        _bs_t = _ext_pal()
        _bs_dark = _bs_t.get("win_bg","#fff")[1:3].lower() < "88"
        direction_col = ("#00cc66" if _bs_dark else "#15803d") if strat_type == "call_back_spread"                    else ("#ff4444" if _bs_dark else "#dc2626")
        credit_amt    = abs(net_cost_100)
        kw['cost'].setText(f"크레딧 ${credit_amt:,.0f}")
        sl['max_gain'   ].setText(f"${max_profit*100:,.0f}  {direction_txt}")
        sl['max_gain'   ].setStyleSheet(
            f"color:{direction_col};font-size:14px;font-weight:bold;border:none;")
        sl['call_spread'].setText(
            f"{call_strikes[0]:.0f}~{call_strikes[-1]:.0f}" if len(call_strikes) >= 2
            else (f"{call_strikes[0]:.0f}" if call_strikes else "―"))
        sl['put_spread' ].setText(
            f"{put_strikes[-1]:.0f}~{put_strikes[0]:.0f}" if len(put_strikes) >= 2
            else (f"{put_strikes[0]:.0f}" if put_strikes else "―"))
        sl['buy_cost'   ].setText("―")
        sl['credit'     ].setText(f"${credit_amt:,.0f}")
        sl['margin'     ].setText(f"${margin:,.0f}")
        if PG and hasattr(self, '_line_body'):
            self._line_body.setVisible(False)

    else:
        # 기본(generic) 전략
        kw['cost'].setText(
            f"{'데빗' if net_cost >= 0 else '크레딧'} ${abs(net_cost_100):,.0f}")
        sl['call_spread'].setText(
            f"{call_strikes[0]:.0f}~{call_strikes[-1]:.0f}" if len(call_strikes) >= 2
            else (f"{call_strikes[0]:.0f}" if call_strikes else "―"))
        sl['put_spread' ].setText(
            f"{put_strikes[0]:.0f}~{put_strikes[-1]:.0f}" if len(put_strikes) >= 2
            else (f"{put_strikes[0]:.0f}" if put_strikes else "―"))
        sl['buy_cost'   ].setText(f"${abs(net_cost_100):,.0f}")
        sl['max_gain'   ].setText(f"${max_profit*100:,.0f}")
        sl['credit'     ].setText(f"${abs(net_cost_100):,.0f}" if net_cost < 0 else "―")
        sl['margin'     ].setText(f"${margin:,.0f}")
        # 버터플라이 바디선 숨기기
        if PG and hasattr(self, '_line_body'):
            self._line_body.setVisible(False)

    # ── 시나리오 테이블 ──────────────────────────────────────
    _fill_scenario_table(self, price_range, total_pnl, pnl_series, legs, net_cost)
    _colorize_scenario_table(self, net_cost)

    # ── 손익 곡선 차트 ───────────────────────────────────────
    if PG and hasattr(self, '_curve_pnl'):
        pnl_100 = [p * 100 for p in total_pnl]
        self._curve_pnl.setData(price_range, pnl_100)

        # BEP 수직선
        if hasattr(self, '_curve_be') and breakevens:
            be_x = [v for bep in breakevens for v in (bep, bep)]
            be_y = [min(pnl_100), max(pnl_100)] * len(breakevens)
            self._curve_be.setData(be_x, be_y)

        # ★ BEP 텍스트 라벨 (기존 제거 후 재생성)
        for lbl in getattr(self, '_bep_labels', []):
            try:
                self._pw_pnl.removeItem(lbl)
            except Exception:
                pass
        self._bep_labels = []
        for bep in breakevens:
            txt = pg.TextItem(
                text=f"BEP\n{bep:.1f}",
                color="#ffd700",
                anchor=(0.5, 1.0),   # 텍스트 중앙 하단 정렬
            )
            txt.setFont(_QFont("Consolas", 9, _QFont.Bold))
            self._pw_pnl.addItem(txt)
            txt.setPos(bep, 0)       # y=0 선(손익분기) 위에 표시
            self._bep_labels.append(txt)

    self._log(
        f"📊 [{strat_type}] 손익 계산 완료: {len(legs)}레그  "
        f"최대이익=${max_profit*100:,.0f}  최대손실=${max_loss*100:,.0f}  "
        f"BEP={[f'{b:.1f}' for b in breakevens]}")


# ── 시나리오 테이블 색상 강조 ────────────────────────────────────

def _colorize_scenario_table(self, net_cost: float):
    """총 PnL이 양수/음수에 따라 시나리오 테이블 행 색상 적용."""
    tbl = self.tbl_scenario
    for r in range(tbl.rowCount()):
        it_pnl = tbl.item(r, 1)
        if it_pnl is None:
            continue
        try:
            val = float(it_pnl.text().replace("$", "").replace(",", ""))
        except ValueError:
            continue
        _sc_t    = _ext_pal()
        _is_dark_sc = _sc_t.get("win_bg", "#fff")[1:3].lower() < "88"
        color = (QColor("#003300") if _is_dark_sc else QColor("#dcfce7")) if val > 0 else (
                (QColor("#330000") if _is_dark_sc else QColor("#fee2e2")) if val < 0
                else (QColor("#1a1a0a") if _is_dark_sc else QColor("#f5f5f5")))
        for c in range(tbl.columnCount()):
            it = tbl.item(r, c)
            if it:
                it.setBackground(QBrush(color))


# ── 전략 설명 팝업 ──────────────────────────────────────────────

def _show_strat_desc(self):
    strat = self.combo_strat.currentText()
    desc  = STRATEGY_DESC.get(strat, "설명 정보가 없습니다.")
    dlg   = QMessageBox(self)
    dlg.setWindowTitle("전략 설명"); dlg.setText(desc)
    _dt = _ext_pal()
    dlg.setStyleSheet(
        f"QMessageBox{{background:{_dt.get('win_bg','#0d0d22')};"
        f"color:{_dt.get('widget_fg','#cccccc')};}}"
        f"QLabel{{color:{_dt.get('group_title','#ffd700')};"
        "font-size:13px;min-width:480px;}"
        f"QPushButton{{background:{_dt.get('btn_bg','#1a2a4a')};"
        f"color:{_dt.get('btn_fg','#90caf9')};"
        f"border:1px solid {_dt.get('btn_border','#3a3a6a')};"
        "border-radius:4px;padding:6px 18px;font-size:12px;}"
        f"QPushButton:hover{{background:{_dt.get('btn_hover','#2a3a6a')};}}")
    dlg.exec_()


# ── Optimizer 팝업 토글 ──────────────────────────────────────────

def _toggle_optimizer_panel(self):
    from combo_op.combo_op_dialog import OptimizerDialog
    dlg = getattr(self, '_optimizer_dialog', None)
    if dlg is not None and dlg.isVisible():
        dlg.raise_(); dlg.activateWindow(); return
    dlg = OptimizerDialog(self)
    self._optimizer_dialog = dlg
    dlg.show()