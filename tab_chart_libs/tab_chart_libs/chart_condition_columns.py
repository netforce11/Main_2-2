"""
chart_condition_columns.py — ConditionPanel 3컬럼 빌더
[분리] chart_condition_ui.py 에서 분리
  _build_col_cond, _build_col_live, _build_col_order
이 함수들은 ConditionPanel 메서드로 동작하므로
  ConditionPanel 클래스 내부에서 직접 호출됩니다.
  분리 후 chart_condition_ui.py 에서 mixin 방식으로 주입.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QCheckBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt
from chart_condition_widgets import (
    _lbl, _inp, _sep, _mini_title, _spin_widget,
    C_GRAY, C_DIM, C_TEXT, C_YELLOW, C_TEAL,
    C_GREEN, C_BLUE, C_PANEL, C_BORDER, SS_INPUT,
)

def _build_col_cond(self):
    w = QWidget(); v = QVBoxLayout(w)
    v.setContentsMargins(4, 4, 8, 4); v.setSpacing(4)
    v.addWidget(_mini_title("조건 설정"))
    v.addWidget(_lbl("시간 범위 (KST)"))
    tr = QHBoxLayout(); tr.setSpacing(3)
    self.inp_ts = _inp("10:11", 52); tr.addWidget(self.inp_ts)
    tr.addWidget(_lbl("~"))
    self.inp_te = _inp("10:15", 52); tr.addWidget(self.inp_te)
    tr.addStretch(); v.addLayout(tr)
    v.addWidget(_lbl("틱 임계값"))
    tr2 = QHBoxLayout(); tr2.setSpacing(3)
    self.inp_tick = _spin_widget(1, 999, 20, w=52)
    tr2.addWidget(self.inp_tick); tr2.addWidget(_lbl("/ 10s 초과"))
    tr2.addStretch(); v.addLayout(tr2)
    v.addWidget(_lbl("행사가"))
    sr = QHBoxLayout(); sr.setSpacing(3)
    self.inp_strike = _inp("5200C", 72)
    self.inp_strike.setPlaceholderText("5200C")
    sr.addWidget(self.inp_strike); sr.addStretch(); v.addLayout(sr)
    v.addWidget(_sep())
    self.chk_price = QCheckBox("현재가 조건 사용")
    self.chk_price.setStyleSheet(
        f"QCheckBox{{color:{C_YELLOW};font-size:11px;font-weight:bold;}}"
        f"QCheckBox::indicator{{width:13px;height:13px;}}"
        f"QCheckBox::indicator:unchecked{{border:1px solid #5a5a1a;border-radius:2px;background:#1a1a0a;}}"
        f"QCheckBox::indicator:checked{{border:1px solid {C_YELLOW};border-radius:2px;background:#3a3a0a;}}")
    self.chk_price.stateChanged.connect(self._on_price_chk)
    v.addWidget(self.chk_price)
    self._price_detail = QWidget()
    pd = QVBoxLayout(self._price_detail)
    pd.setContentsMargins(0, 2, 0, 0); pd.setSpacing(3)
    pr = QHBoxLayout(); pr.setSpacing(3)
    self.sel_price_op = QComboBox()
    self.sel_price_op.addItems(["이상", "이하", "범위"])
    self.sel_price_op.setFixedWidth(52); self.sel_price_op.setFixedHeight(22)
    self.sel_price_op.setStyleSheet(SS_INPUT)
    self.sel_price_op.currentTextChanged.connect(self._on_price_op)
    pr.addWidget(self.sel_price_op)
    self.inp_pv1 = _spin_widget(0.01, 9999, 1.00, w=60, decimals=2, step=0.05)
    pr.addWidget(self.inp_pv1)
    self._lbl_tilde = _lbl("~")
    self.inp_pv2 = _spin_widget(0.01, 9999, 2.00, w=60, decimals=2, step=0.05)
    pr.addWidget(self._lbl_tilde); pr.addWidget(self.inp_pv2)
    pr.addStretch(); pd.addLayout(pr)
    self._lbl_tilde.hide(); self.inp_pv2.hide()
    self._price_detail.hide()
    v.addWidget(self._price_detail)
    v.addStretch(1)
    return w

def _build_col_live(self):
    w = QWidget(); v = QVBoxLayout(w)
    v.setContentsMargins(8, 4, 8, 4); v.setSpacing(4)
    v.addWidget(_mini_title("실시간 현황"))
    card_row = QHBoxLayout(); card_row.setSpacing(4)
    for key, label in [("bid", "BID"), ("last", "LAST"), ("ask", "ASK")]:
        card = QWidget()
        card.setStyleSheet(f"background:{C_PANEL}; border:1px solid {C_BORDER}; border-radius:4px;")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(4, 3, 4, 3); cv.setSpacing(1)
        l1 = QLabel(label); l1.setStyleSheet(f"color:{C_DIM}; font-size:9px;")
        l1.setAlignment(Qt.AlignCenter)
        l2 = QLabel("—"); l2.setStyleSheet(f"color:{C_GREEN}; font-size:14px; font-weight:bold;")
        l2.setAlignment(Qt.AlignCenter)
        cv.addWidget(l1); cv.addWidget(l2)
        setattr(self, f"lv_{key}", l2)
        card_row.addWidget(card)
    v.addLayout(card_row)
    v.addWidget(_lbl("틱 속도 (10s)"))
    gr = QHBoxLayout(); gr.setSpacing(5)
    self.lv_tick = QLabel("0")
    self.lv_tick.setFixedWidth(28)
    self.lv_tick.setStyleSheet(f"color:{C_TEAL}; font-size:13px; font-weight:bold;")
    gr.addWidget(self.lv_tick)
    self._gauge_bg = QFrame()
    self._gauge_bg.setFixedHeight(8)
    self._gauge_bg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    self._gauge_bg.setStyleSheet(f"background:{C_PANEL}; border-radius:4px; border:1px solid {C_BORDER};")
    self._gauge_fill = QFrame(self._gauge_bg)
    self._gauge_fill.setFixedHeight(8)
    self._gauge_fill.setStyleSheet(f"background:{C_TEAL}; border-radius:4px; border:none;")
    self._gauge_fill.setFixedWidth(0)
    gr.addWidget(self._gauge_bg, 1); v.addLayout(gr)
    self.lbl_et_range = QLabel("")
    self.lbl_et_range.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
    v.addWidget(self.lbl_et_range)
    v.addStretch(1)
    return w

def _build_col_order(self):
    w = QWidget(); v = QVBoxLayout(w)
    v.setContentsMargins(8, 4, 4, 4); v.setSpacing(4)
    v.addWidget(_mini_title("자동 주문"))
    self.chk_auto = QCheckBox("조건 충족 시 자동 주문")
    self.chk_auto.setStyleSheet(
        f"QCheckBox{{color:{C_TEXT};font-size:11px;}}"
        f"QCheckBox::indicator{{width:13px;height:13px;}}"
        f"QCheckBox::indicator:unchecked{{border:1px solid {C_DIM};border-radius:2px;background:{C_PANEL};}}"
        f"QCheckBox::indicator:checked{{border:1px solid {C_BLUE};border-radius:2px;background:#0a1a3a;}}")
    v.addWidget(self.chk_auto)
    qr = QHBoxLayout(); qr.setSpacing(4)
    qr.addWidget(_lbl("수량"))
    self.inp_qty = _spin_widget(1, 99, 1, w=50)
    qr.addWidget(self.inp_qty); qr.addWidget(_lbl("계약")); qr.addStretch()
    v.addLayout(qr)
    dr = QHBoxLayout(); dr.setSpacing(4)
    self.sel_side = QComboBox()
    self.sel_side.addItems(["BUY", "SELL"])
    self.sel_side.setFixedWidth(58); self.sel_side.setFixedHeight(22)
    self.sel_side.setStyleSheet(SS_INPUT)
    dr.addWidget(self.sel_side); dr.addStretch(); v.addLayout(dr)
    v.addWidget(_sep())
    self.chk_limit = QCheckBox("지정가 사용")
    self.chk_limit.setStyleSheet(
        f"QCheckBox{{color:{C_YELLOW};font-size:11px;font-weight:bold;}}"
        f"QCheckBox::indicator{{width:13px;height:13px;}}"
        f"QCheckBox::indicator:unchecked{{border:1px solid #5a5a1a;border-radius:2px;background:#1a1a0a;}}"
        f"QCheckBox::indicator:checked{{border:1px solid {C_YELLOW};border-radius:2px;background:#3a3a0a;}}")
    self.chk_limit.stateChanged.connect(self._on_limit_chk)
    v.addWidget(self.chk_limit)
    self._limit_detail = QWidget()
    ld = QHBoxLayout(self._limit_detail)
    ld.setContentsMargins(0, 2, 0, 0); ld.setSpacing(4)
    self.inp_limit = _spin_widget(0.01, 9999, 1.00, w=72, decimals=2, step=0.05)
    ld.addWidget(self.inp_limit); ld.addWidget(_lbl("USD")); ld.addStretch()
    self._limit_detail.hide(); v.addWidget(self._limit_detail)
    self.lbl_limit_hint = QLabel("미체크: Last + 0.05 자동")
    self.lbl_limit_hint.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
    v.addWidget(self.lbl_limit_hint)
    v.addStretch(1)
    return w

# ── 체크박스 핸들러 ──────────────────────────────────────
