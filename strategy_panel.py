"""strategy_panel.py — StrategyPanelMixin: 스프레드 전략 패널 [S9]
지원 전략: 콜 스프레드 / 풋 스프레드 / 콜 백 스프레드 / 풋 백 스프레드
레이아웃: 좌(레그 입력) + 우(손익 결과) 2열 구성, 폰트 확대
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QFrame, QGroupBox,
    QDoubleSpinBox, QSpinBox,
)
from PyQt5.QtCore import Qt

# ── Style ──────────────────────────────────────────────────────
_BG      = "background:#07070f;"
_S_TITLE = "color:#c084fc;font-size:14px;font-weight:bold;border:none;"
_S_GB    = (
    "QGroupBox{font-size:12px;color:#c084fc;font-weight:bold;"
    "border:1px solid #3a1a5a;border-radius:5px;"
    "margin-top:8px;padding-top:6px;background:#09091a;}"
    "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
)
_S_GB_R  = (
    "QGroupBox{font-size:12px;color:#ffd700;font-weight:bold;"
    "border:1px solid #4a3a0a;border-radius:5px;"
    "margin-top:8px;padding-top:6px;background:#09091a;}"
    "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
)
_S_LBL   = "color:#999;font-size:12px;border:none;"
_S_LEG_A = "color:#33aaff;font-size:12px;font-weight:bold;border:none;"
_S_LEG_B = "color:#ff6666;font-size:12px;font-weight:bold;border:none;"
_S_VAL_G = "color:#00e676;font-size:15px;font-weight:bold;border:none;"
_S_VAL_R = "color:#ff5252;font-size:15px;font-weight:bold;border:none;"
_S_VAL_B = "color:#90caf9;font-size:13px;font-weight:bold;border:none;"
_S_VAL_Y = "color:#ffd700;font-size:13px;font-weight:bold;border:none;"
_S_SEP   = "border:none;background:#2a1a4a;max-height:1px;"
_S_COMBO = (
    "QComboBox{background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
    "font-size:13px;font-weight:bold;padding:3px 6px;border-radius:3px;}"
    "QComboBox QAbstractItemView{background:#0c0c22;color:#ffd700;font-size:13px;}"
    "QComboBox::drop-down{border:none;width:16px;}"
)
_S_SPIN  = (
    "background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
    "font-size:13px;font-weight:bold;border-radius:3px;padding:2px;"
)
_S_STRIKE = (
    "color:#ffd700;font-size:15px;font-weight:bold;"
    "background:#0c0c22;padding:4px 10px;border-radius:3px;"
    "border:1px solid #3a3a6a;min-width:64px;"
)
_S_BTN = (
    "QPushButton{background:#1a1a3a;color:#90caf9;font-size:12px;"
    "font-weight:bold;border:1px solid #3a3a7a;border-radius:4px;padding:5px 10px;}"
    "QPushButton:hover{background:#2a2a5a;}"
    "QPushButton:pressed{background:#0a0a2a;}"
)
_S_BTN_RESET = (
    "QPushButton{background:#1a0a0a;color:#ff8888;font-size:11px;"
    "font-weight:bold;border:1px solid #5a2a2a;border-radius:4px;padding:3px 8px;}"
    "QPushButton:hover{background:#2a1a1a;}"
)
_S_HINT  = "color:#666;font-size:11px;border:none;font-style:italic;"
_S_NEXT  = "color:#c084fc;font-size:12px;font-weight:bold;border:none;"

STRATEGIES = ["콜 스프레드", "풋 스프레드", "콜 백 스프레드", "풋 백 스프레드"]


class StrategyPanelMixin:

    def _build_strategy_panel(self) -> QWidget:
        root = QWidget()
        root.setStyleSheet(_BG)
        rv = QVBoxLayout(root)
        rv.setContentsMargins(6, 6, 6, 6)
        rv.setSpacing(6)

        # ── 헤더 ─────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        hdr.addWidget(QLabel("📐 스프레드 전략", styleSheet=_S_TITLE))

        self._strat_combo = QComboBox()
        self._strat_combo.addItems(STRATEGIES)
        self._strat_combo.setFixedHeight(28)
        self._strat_combo.setMinimumWidth(130)
        self._strat_combo.setStyleSheet(_S_COMBO)
        self._strat_combo.currentIndexChanged.connect(self._on_strat_change)
        hdr.addWidget(self._strat_combo, 1)

        btn_reset = QPushButton("↺ 초기화")
        btn_reset.setFixedHeight(28)
        btn_reset.setStyleSheet(_S_BTN_RESET)
        btn_reset.clicked.connect(self._reset_strategy)
        hdr.addWidget(btn_reset)
        rv.addLayout(hdr)

        # ── 다음 클릭 안내 ────────────────────────────────────────
        self._strat_next_lbl = QLabel("① 체인에서 첫 번째 행사가를 클릭하세요")
        self._strat_next_lbl.setStyleSheet(_S_NEXT)
        rv.addWidget(self._strat_next_lbl)

        sep_top = QFrame(); sep_top.setFrameShape(QFrame.HLine)
        sep_top.setStyleSheet(_S_SEP); rv.addWidget(sep_top)

        # ── 좌우 2열 본문 ─────────────────────────────────────────
        body = QHBoxLayout(); body.setSpacing(8)

        # 왼쪽: 레그 입력
        left_gb = QGroupBox("레그 입력")
        left_gb.setStyleSheet(_S_GB)
        lg = QVBoxLayout(left_gb)
        lg.setContentsMargins(8, 14, 8, 8); lg.setSpacing(8)

        self._leg_a_label = QLabel("● 매수 레그 A")
        self._leg_a_label.setStyleSheet(_S_LEG_A)
        lg.addWidget(self._leg_a_label)
        lg.addWidget(self._build_leg_card("A"))

        sep_mid = QFrame(); sep_mid.setFrameShape(QFrame.HLine)
        sep_mid.setStyleSheet(_S_SEP); lg.addWidget(sep_mid)

        self._leg_b_label = QLabel("● 매도 레그 B")
        self._leg_b_label.setStyleSheet(_S_LEG_B)
        lg.addWidget(self._leg_b_label)
        lg.addWidget(self._build_leg_card("B"))

        sep_qty = QFrame(); sep_qty.setFrameShape(QFrame.HLine)
        sep_qty.setStyleSheet(_S_SEP); lg.addWidget(sep_qty)

        qty_row = QHBoxLayout(); qty_row.setSpacing(6)
        qty_row.addWidget(QLabel("수량:", styleSheet=_S_LBL))
        self._strat_qty = QSpinBox()
        self._strat_qty.setRange(1, 999); self._strat_qty.setValue(1)
        self._strat_qty.setFixedHeight(28); self._strat_qty.setFixedWidth(60)
        self._strat_qty.setStyleSheet(_S_SPIN)
        self._strat_qty.valueChanged.connect(self._calc_strategy)
        qty_row.addWidget(self._strat_qty)
        qty_row.addStretch()
        btn_calc = QPushButton("🔢 계산")
        btn_calc.setFixedHeight(28)
        btn_calc.setStyleSheet(_S_BTN)
        btn_calc.clicked.connect(self._calc_strategy)
        qty_row.addWidget(btn_calc)
        lg.addLayout(qty_row)
        lg.addStretch()
        body.addWidget(left_gb, 5)

        # 오른쪽: 손익 결과
        right_gb = QGroupBox("손익 요약")
        right_gb.setStyleSheet(_S_GB_R)
        rg = QVBoxLayout(right_gb)
        rg.setContentsMargins(8, 14, 8, 8); rg.setSpacing(6)

        def _res_row(label, attr, style):
            row = QHBoxLayout(); row.setSpacing(4)
            lw = QLabel(label); lw.setStyleSheet(_S_LBL); lw.setFixedWidth(76)
            vw = QLabel("―"); vw.setStyleSheet(style)
            vw.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            setattr(self, attr, vw)
            row.addWidget(lw); row.addWidget(vw, 1)
            return row

        rg.addLayout(_res_row("순 비용",   '_sr_cost',     _S_VAL_Y))

        s1 = QFrame(); s1.setFrameShape(QFrame.HLine); s1.setStyleSheet(_S_SEP)
        rg.addWidget(s1)

        rg.addLayout(_res_row("최대 이익", '_sr_max_prof', _S_VAL_G))
        rg.addLayout(_res_row("최대 손실", '_sr_max_loss', _S_VAL_R))

        s2 = QFrame(); s2.setFrameShape(QFrame.HLine); s2.setStyleSheet(_S_SEP)
        rg.addWidget(s2)

        rg.addLayout(_res_row("BEP",       '_sr_bep',      _S_VAL_B))
        rg.addLayout(_res_row("손익비 R:R",'_sr_rr',       _S_VAL_Y))

        s3 = QFrame(); s3.setFrameShape(QFrame.HLine); s3.setStyleSheet(_S_SEP)
        rg.addWidget(s3)

        self._strat_desc = QLabel("")
        self._strat_desc.setWordWrap(True)
        self._strat_desc.setStyleSheet(_S_HINT)
        rg.addWidget(self._strat_desc)
        rg.addStretch()
        body.addWidget(right_gb, 4)

        rv.addLayout(body, 1)

        self._strat_leg = {"A": {}, "B": {}}
        self._strat_click_seq = 0
        self._on_strat_change(0)
        return root

    def _build_leg_card(self, leg: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:#0c0c1e;border-radius:4px;border:1px solid #2a2a4a;}")
        gl = QGridLayout(card)
        gl.setContentsMargins(8, 6, 8, 6); gl.setSpacing(5)

        gl.addWidget(QLabel("행사가", styleSheet=_S_LBL), 0, 0)
        strike_lbl = QLabel("―")
        strike_lbl.setStyleSheet(_S_STRIKE)
        strike_lbl.setAlignment(Qt.AlignCenter)
        setattr(self, f'_leg_{leg.lower()}_strike', strike_lbl)
        gl.addWidget(strike_lbl, 0, 1)

        gl.addWidget(QLabel("Mid 가격", styleSheet=_S_LBL), 1, 0)
        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.0, 9999.0); price_spin.setDecimals(2)
        price_spin.setSingleStep(0.05); price_spin.setValue(0.0)
        price_spin.setFixedHeight(26)
        price_spin.setStyleSheet(_S_SPIN)
        price_spin.valueChanged.connect(self._calc_strategy)
        setattr(self, f'_leg_{leg.lower()}_price', price_spin)
        gl.addWidget(price_spin, 1, 1)

        gl.setColumnStretch(1, 1)
        return card

    def _on_strat_change(self, idx: int):
        strat = STRATEGIES[idx]
        is_back = "백" in strat
        if is_back:
            self._leg_a_label.setText("● 매도 레그 A  (ATM)")
            self._leg_a_label.setStyleSheet(_S_LEG_B)
            self._leg_b_label.setText("● 매수 레그 B  (OTM ×2)")
            self._leg_b_label.setStyleSheet(_S_LEG_A)
            desc = ("ATM 1계약 매도 + OTM 2계약 매수.\n"
                    "방향 강하게 맞으면 무제한 수익, 중간 구간 최대 손실.")
        elif strat == "콜 스프레드":
            self._leg_a_label.setText("● 매수 레그 A  (낮은 행사가)")
            self._leg_a_label.setStyleSheet(_S_LEG_A)
            self._leg_b_label.setText("● 매도 레그 B  (높은 행사가)")
            self._leg_b_label.setStyleSheet(_S_LEG_B)
            desc = "낮은 콜 매수 + 높은 콜 매도.\n제한 비용, 제한 수익."
        else:
            self._leg_a_label.setText("● 매수 레그 A  (높은 행사가)")
            self._leg_a_label.setStyleSheet(_S_LEG_A)
            self._leg_b_label.setText("● 매도 레그 B  (낮은 행사가)")
            self._leg_b_label.setStyleSheet(_S_LEG_B)
            desc = "높은 풋 매수 + 낮은 풋 매도.\n하락 제한 수익 전략."
        self._strat_desc.setText(desc)
        self._strat_click_seq = 0
        self._update_next_hint()
        self._calc_strategy()

    def _update_next_hint(self):
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        is_back = "백" in strat
        seq = self._strat_click_seq
        if seq == 0:
            hint = "① 매도 행사가 클릭 → A레그" if is_back else "① 매수 행사가 클릭 → A레그"
        else:
            hint = "② 매수 행사가 클릭 → B레그 (×2)" if is_back else "② 매도 행사가 클릭 → B레그"
        self._strat_next_lbl.setText(hint)

    def _reset_strategy(self):
        self._strat_click_seq = 0
        for leg in ("a", "b"):
            getattr(self, f'_leg_{leg}_strike').setText("―")
            getattr(self, f'_leg_{leg}_price').setValue(0.0)
        self._strat_leg = {"A": {}, "B": {}}
        self._update_next_hint()
        self._set_results("―", "―", "―", "―", "―")

    def _strat_on_chain_click(self, side: str, strike: float, bid: float, ask: float):
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        if "콜" in strat and side != "C": return
        if "풋" in strat and side != "P": return

        mid = round((bid + ask) / 2, 2) if bid and ask else (ask or bid or 0.0)
        leg = "A" if self._strat_click_seq == 0 else "B"
        strike_str = str(int(strike)) if strike == int(strike) else str(strike)
        getattr(self, f'_leg_{leg.lower()}_strike').setText(strike_str)
        getattr(self, f'_leg_{leg.lower()}_price').setValue(mid)
        self._strat_leg[leg] = {"strike": strike, "side": side, "bid": bid, "ask": ask, "mid": mid}
        self._strat_click_seq = min(self._strat_click_seq + 1, 1)
        self._update_next_hint()
        self._calc_strategy()

    def _calc_strategy(self):
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        qty = self._strat_qty.value()
        mult = 100
        try:
            pa = self._leg_a_price.value()
            pb = self._leg_b_price.value()
            sa = float(self._leg_a_strike.text()) if self._leg_a_strike.text() != "―" else 0.0
            sb = float(self._leg_b_strike.text()) if self._leg_b_strike.text() != "―" else 0.0
        except (ValueError, AttributeError):
            self._set_results("―", "―", "―", "―", "―"); return

        if pa == 0.0 and pb == 0.0:
            self._set_results("―", "―", "―", "―", "―"); return

        if strat in ("콜 스프레드", "풋 스프레드"):
            net   = (pa - pb) * mult * qty
            width = abs(sa - sb) * mult * qty
            max_p = width - net
            max_l = net
            bep   = (sa + (pa - pb)) if strat == "콜 스프레드" else (sa - (pa - pb))
            rr    = abs(max_p / max_l) if max_l != 0 else 0
            self._set_results(
                f"{'비용' if net>=0 else '크레딧'}  ${abs(net):,.0f}",
                f"${max_p:,.0f}",
                f"-${abs(max_l):,.0f}",
                f"{bep:.2f}",
                f"1 : {rr:.1f}" if rr > 0 else "―",
            )
        else:
            credit = pa * mult * qty
            debit  = pb * mult * qty * 2
            net    = debit - credit
            max_l  = abs(sa - sb) * mult * qty + net
            if strat == "콜 백 스프레드":
                bep_lo = sa - net/(mult*qty) if net>=0 else sa + abs(net)/(mult*qty)
                bep_hi = sb + net/(mult*qty) if net>=0 else sb - abs(net)/(mult*qty)
                mp_str = "무제한 ↑"
            else:
                bep_hi = sa + net/(mult*qty) if net>=0 else sa - abs(net)/(mult*qty)
                bep_lo = sb - net/(mult*qty) if net>=0 else sb + abs(net)/(mult*qty)
                mp_str = "무제한 ↓"
            self._set_results(
                f"{'비용' if net>=0 else '크레딧'}  ${abs(net):,.0f}",
                mp_str,
                f"-${abs(max_l):,.0f}",
                f"{bep_lo:.1f}  /  {bep_hi:.1f}",
                "∞",
            )

    def _set_results(self, cost, max_prof, max_loss, bep, rr):
        self._sr_cost.setText(cost)
        self._sr_max_prof.setText(max_prof)
        self._sr_max_loss.setText(max_loss)
        self._sr_bep.setText(bep)
        self._sr_rr.setText(rr)
        if isinstance(cost, str) and cost != "―":
            self._sr_cost.setStyleSheet(_S_VAL_R if "비용" in cost else _S_VAL_G)
        else:
            self._sr_cost.setStyleSheet(_S_VAL_Y)