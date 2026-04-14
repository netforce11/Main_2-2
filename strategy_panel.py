"""strategy_panel.py — StrategyPanelMixin  [S11]
지원 전략 : 콜 백 스프레드 / 풋 백 스프레드 / 콜 스프레드 / 풋 스프레드
신규 기능 :
  [S11-1] 1세트 / 2세트 / 3세트 프리셋 버튼 (전략별 레그 설정 즉시 적용)
  [S11-2] 만기 자동 수신 (옵션 체인 combo_exp → _strat_exp_lbl 동기화)
  [S11-3] 종목 필드 우측 날짜 자동 입력 필드 (_strat_date_edit)
  [S11-4] 단축키 Shift+1~4 → 전략 유형 즉시 선택
  [S11-5] 손익 분석 패널 공간 축소 + 정보 폰트 +3
  [S11-6] 손익 곡선 패널 1/2 크기 축소
  [S11-7] 모의투자 / 실제 모드 토글 (남은 여유 공간)
분할 구조 (200줄 단위):
  Part 1  — 스타일 상수 + 세트 프리셋 정의          (이 파일)
  Part 2  — _build_strategy_panel() 메인 레이아웃
  Part 3  — 레그 카드 / 세트 버튼 빌더
  Part 4  — 이벤트 핸들러 / 계산 로직
  Part 5  — 모의/실제 모드 패널 + 단축키
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QFrame, QGroupBox,
    QDoubleSpinBox, QSpinBox, QLineEdit, QDateEdit,
    QButtonGroup, QRadioButton, QSizePolicy,
)
from PyQt5.QtCore import Qt, QDate, QTimer
from PyQt5.QtGui import QKeySequence, QFont

# ═══════════════════════════════════════════════════════════════
# Part 1 — 스타일 상수
# ═══════════════════════════════════════════════════════════════

_BG       = "background:#07070f;"
_S_TITLE  = "color:#c084fc;font-size:14px;font-weight:bold;border:none;"
_S_GB     = (
    "QGroupBox{font-size:12px;color:#c084fc;font-weight:bold;"
    "border:1px solid #3a1a5a;border-radius:5px;"
    "margin-top:8px;padding-top:6px;background:#09091a;}"
    "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
)
_S_GB_R   = (
    "QGroupBox{font-size:12px;color:#ffd700;font-weight:bold;"
    "border:1px solid #4a3a0a;border-radius:5px;"
    "margin-top:8px;padding-top:6px;background:#09091a;}"
    "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
)
_S_GB_MODE = ""  # 미사용 — 모드 패널 제거됨 (호환성 유지용 빈 상수)

_S_LBL    = "color:#999;font-size:15px;border:none;"           # +3 기본
_S_LEG_A  = "color:#33aaff;font-size:15px;font-weight:bold;border:none;"
_S_LEG_B  = "color:#ff6666;font-size:15px;font-weight:bold;border:none;"
_S_VAL_G  = "color:#00e676;font-size:18px;font-weight:bold;border:none;"  # +3
_S_VAL_R  = "color:#ff5252;font-size:18px;font-weight:bold;border:none;"  # +3
_S_VAL_B  = "color:#90caf9;font-size:16px;font-weight:bold;border:none;"  # +3
_S_VAL_Y  = "color:#ffd700;font-size:16px;font-weight:bold;border:none;"  # +3
_S_SEP    = "border:none;background:#2a1a4a;max-height:1px;"
_S_COMBO  = (
    "QComboBox{background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
    "font-size:13px;font-weight:bold;padding:3px 6px;border-radius:3px;}"
    "QComboBox QAbstractItemView{background:#0c0c22;color:#ffd700;font-size:13px;}"
    "QComboBox::drop-down{border:none;width:16px;}"
)
_S_SPIN   = (
    "background:#0c0c22;color:#ffd700;border:1px solid #4a4a8a;"
    "font-size:13px;font-weight:bold;border-radius:3px;padding:2px;"
)
_S_STRIKE = (
    "color:#ffd700;font-size:17px;font-weight:bold;"
    "background:#0c0c22;padding:4px 10px;border-radius:3px;"
    "border:1px solid #3a3a6a;min-width:64px;"
)
_S_BTN    = (
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
_S_BTN_SET = (
    "QPushButton{{background:{bg};color:{fg};font-size:11px;"
    "font-weight:bold;border:1px solid {bd};border-radius:4px;padding:4px 8px;}}"
    "QPushButton:hover{{background:{hv};}}"
    "QPushButton:pressed{{background:#0a0a1a;}}"
)
_S_HINT   = "color:#666;font-size:11px;border:none;font-style:italic;"
_S_NEXT   = "color:#c084fc;font-size:12px;font-weight:bold;border:none;"
_S_DATE   = (
    "QDateEdit{background:#0c0c22;color:#90caf9;border:1px solid #4a4a8a;"
    "font-size:12px;font-weight:bold;border-radius:3px;padding:2px;}"
)
_S_EXP_LBL = "color:#90caf9;font-size:13px;font-weight:bold;border:none;"

STRATEGIES = ["콜 백 스프레드", "풋 백 스프레드", "콜 스프레드", "풋 스프레드"]

# ── 세트 프리셋 정의 ─────────────────────────────────────────────
# 각 세트: (전략명, leg_a_행사가_오프셋, leg_b_행사가_오프셋, 수량)
# 오프셋은 ATM 기준 상대값(포인트). None이면 마지막 선택값 유지
SET_PRESETS = {
    "콜 백 스프레드": [
        {"label": "1세트", "a_offset":  0, "b_offset":  5, "qty": 1,
         "desc": "ATM 매도 + OTM5 매수×2"},
        {"label": "2세트", "a_offset":  0, "b_offset": 10, "qty": 1,
         "desc": "ATM 매도 + OTM10 매수×2"},
        {"label": "3세트", "a_offset":  5, "b_offset": 15, "qty": 2,
         "desc": "OTM5 매도 + OTM15 매수×2, 2계약"},
    ],
    "풋 백 스프레드": [
        {"label": "1세트", "a_offset":  0, "b_offset": -5, "qty": 1,
         "desc": "ATM 매도 + OTM5 Put 매수×2"},
        {"label": "2세트", "a_offset":  0, "b_offset":-10, "qty": 1,
         "desc": "ATM 매도 + OTM10 Put 매수×2"},
        {"label": "3세트", "a_offset": -5, "b_offset":-15, "qty": 2,
         "desc": "OTM5 Put 매도 + OTM15 Put 매수×2, 2계약"},
    ],
    "콜 스프레드": [
        {"label": "1세트", "a_offset":  0, "b_offset":  5, "qty": 1,
         "desc": "ATM 매수 + OTM5 매도"},
        {"label": "2세트", "a_offset":  0, "b_offset": 10, "qty": 1,
         "desc": "ATM 매수 + OTM10 매도"},
        {"label": "3세트", "a_offset": -5, "b_offset":  5, "qty": 2,
         "desc": "ITM5 매수 + OTM5 매도, 2계약"},
    ],
    "풋 스프레드": [
        {"label": "1세트", "a_offset":  0, "b_offset": -5, "qty": 1,
         "desc": "ATM Put 매수 + OTM5 Put 매도"},
        {"label": "2세트", "a_offset":  0, "b_offset":-10, "qty": 1,
         "desc": "ATM Put 매수 + OTM10 Put 매도"},
        {"label": "3세트", "a_offset":  5, "b_offset": -5, "qty": 2,
         "desc": "OTM5 Put 매수 + ITM5 Put 매도, 2계약"},
    ],
}

# ═══════════════════════════════════════════════════════════════
# Part 2 — _build_strategy_panel() 메인 레이아웃
# ═══════════════════════════════════════════════════════════════

class StrategyPanelMixin:

    def _build_strategy_panel(self) -> QWidget:
        """전략 설정 패널 루트 위젯 반환.

        레이아웃 (수직 QSplitter):
        ┌─────────────────────────────────────┐
        │  헤더 (전략 콤보 / 만기 / 리셋)      │
        │  다음 클릭 안내                       │
        │  ── 상단 스플리터 영역 ──             │
        │  [레그 입력]  │  [손익 요약]          │
        │──────────────── 드래그 가능 ─────────│
        │  [증거금확인] [합성잔고] [미체결내역] │  ← 하단 탭
        │──────────────────────────────────────│
        │  [모의/실제 모드]                     │
        └─────────────────────────────────────┘
        """
        root = QWidget()
        root.setStyleSheet(_BG)
        rv = QVBoxLayout(root)
        rv.setContentsMargins(6, 4, 6, 4)
        rv.setSpacing(4)

        # 헤더 + 힌트 (스플리터 밖 — 항상 표시)
        rv.addLayout(self._build_strat_header())
        rv.addWidget(self._build_next_hint_row())
        rv.addWidget(self._sep())

        # ── 수직 스플리터: 상단(레그+손익) / 하단(미체결 탭) ──
        from PyQt5.QtWidgets import QSplitter as _Spl
        v_spl = _Spl(Qt.Vertical)
        v_spl.setHandleWidth(5)
        v_spl.setStyleSheet(
            "QSplitter::handle:vertical{"
            "background:#2a1a5a;border-top:1px solid #4a2a8a;"
            "border-bottom:1px solid #4a2a8a;height:5px;margin:0 2px;}"
            "QSplitter::handle:vertical:hover{"
            "background:#5a2aaa;border-top:1px solid #c084fc;"
            "border-bottom:1px solid #c084fc;}")
        v_spl.setChildrenCollapsible(False)

        # 상단: 레그 입력 + 손익 요약 (가로 배치)
        top_w = QWidget(); top_w.setStyleSheet(_BG)
        top_h = QHBoxLayout(top_w)
        top_h.setContentsMargins(0, 0, 0, 0); top_h.setSpacing(6)
        top_h.addWidget(self._build_leg_panel(), 5)
        top_h.addWidget(self._build_result_panel(), 4)
        v_spl.addWidget(top_w)

        # 하단: 미체결 탭 패널
        v_spl.addWidget(self._build_open_orders_panel())

        v_spl.setSizes([320, 200])   # 상단 ~62% / 하단 ~38%
        rv.addWidget(v_spl, 1)

        # 단축키 설치
        self._install_strategy_shortcuts()

        # 초기화
        self._strat_leg       = {"A": {}, "B": {}}
        self._strat_click_seq = 0
        self._on_strat_change(0)
        return root

    # ── 헤더 ──────────────────────────────────────────────────
    def _build_strat_header(self) -> QHBoxLayout:
        hdr = QHBoxLayout(); hdr.setSpacing(6)
        hdr.addWidget(QLabel("📐 스프레드 전략", styleSheet=_S_TITLE))

        self._strat_combo = QComboBox()
        self._strat_combo.addItems(STRATEGIES)
        self._strat_combo.setFixedHeight(28)
        self._strat_combo.setMinimumWidth(140)
        self._strat_combo.setStyleSheet(_S_COMBO)
        self._strat_combo.setToolTip(
            "Shift+1: 콜 백  Shift+2: 풋 백  Shift+3: 콜 스프레드  Shift+4: 풋 스프레드")
        self._strat_combo.currentIndexChanged.connect(self._on_strat_change)
        hdr.addWidget(self._strat_combo, 1)

        # [S11-3] 날짜 자동 입력 필드 (옵션 체인 만기 수신)
        self._strat_date_edit = QDateEdit()
        self._strat_date_edit.setCalendarPopup(True)
        self._strat_date_edit.setDate(QDate.currentDate())
        self._strat_date_edit.setFixedHeight(26)
        self._strat_date_edit.setFixedWidth(100)
        self._strat_date_edit.setStyleSheet(_S_DATE)
        self._strat_date_edit.setToolTip("만기일 (옵션 체인에서 자동 수신)")
        hdr.addWidget(QLabel("만기:", styleSheet=_S_LBL))
        hdr.addWidget(self._strat_date_edit)

        btn_reset = QPushButton("↺ 초기화")
        btn_reset.setFixedHeight(28)
        btn_reset.setStyleSheet(_S_BTN_RESET)
        btn_reset.clicked.connect(self._reset_strategy)
        hdr.addWidget(btn_reset)
        return hdr

    def _build_next_hint_row(self) -> QLabel:
        self._strat_next_lbl = QLabel("① 체인에서 첫 번째 행사가를 클릭하세요")
        self._strat_next_lbl.setStyleSheet(_S_NEXT)
        return self._strat_next_lbl

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(_S_SEP)
        return f

# ═══════════════════════════════════════════════════════════════
# Part 3 — 레그 패널 / 세트 버튼 / 손익 결과 패널 / 모드 패널
# ═══════════════════════════════════════════════════════════════

    def _build_leg_panel(self) -> QGroupBox:
        """레그 입력 그룹박스 (세트 버튼 포함)."""
        gb = QGroupBox("레그 입력")
        gb.setStyleSheet(_S_GB)
        lg = QVBoxLayout(gb)
        lg.setContentsMargins(8, 12, 8, 6); lg.setSpacing(6)

        # [S11-1] 세트 프리셋 버튼 행
        set_row = QHBoxLayout(); set_row.setSpacing(4)
        set_row.addWidget(QLabel("프리셋:", styleSheet=_S_LBL))
        self._set_btns = []
        set_colors = [
            ("#1a2a1a", "#00ff88", "#2a5a2a", "#2a3a2a"),
            ("#1a1a2a", "#90caf9", "#2a2a6a", "#2a2a4a"),
            ("#2a1a0a", "#ffd700", "#5a3a0a", "#3a2a1a"),
        ]
        for i, (bg, fg, bd, hv) in enumerate(set_colors):
            btn = QPushButton(f"{i+1}세트")
            btn.setFixedHeight(26)
            btn.setFixedWidth(56)
            btn.setStyleSheet(_S_BTN_SET.format(bg=bg, fg=fg, bd=bd, hv=hv))
            btn.clicked.connect(lambda _, idx=i: self._apply_set_preset(idx))
            btn.setToolTip(f"세트 {i+1} 프리셋 적용 (클릭 → 레그에 자동 입력)")
            set_row.addWidget(btn)
            self._set_btns.append(btn)
        set_row.addStretch()
        lg.addLayout(set_row)

        lg.addWidget(self._sep())

        self._leg_a_label = QLabel("● 매도 레그 A  (ATM)")
        self._leg_a_label.setStyleSheet(_S_LEG_B)
        lg.addWidget(self._leg_a_label)
        lg.addWidget(self._build_leg_card("A"))

        lg.addWidget(self._sep())

        self._leg_b_label = QLabel("● 매수 레그 B  (OTM ×2)")
        self._leg_b_label.setStyleSheet(_S_LEG_A)
        lg.addWidget(self._leg_b_label)
        lg.addWidget(self._build_leg_card("B"))

        lg.addWidget(self._sep())

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
        return gb

    def _build_leg_card(self, leg: str) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:#0c0c1e;border-radius:4px;border:1px solid #2a2a4a;}")
        gl = QGridLayout(card)
        gl.setContentsMargins(8, 5, 8, 5); gl.setSpacing(4)

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

    def _build_result_panel(self) -> QGroupBox:
        """손익 요약 패널 (폰트 +3, 공간 최소화)."""
        gb = QGroupBox("손익 요약")
        gb.setStyleSheet(_S_GB_R)
        rg = QVBoxLayout(gb)
        rg.setContentsMargins(8, 10, 8, 6); rg.setSpacing(4)

        def _res_row(label, attr, style):
            row = QHBoxLayout(); row.setSpacing(4)
            lw = QLabel(label); lw.setStyleSheet(_S_LBL); lw.setFixedWidth(80)
            vw = QLabel("―"); vw.setStyleSheet(style)
            vw.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            setattr(self, attr, vw)
            row.addWidget(lw); row.addWidget(vw, 1)
            return row

        rg.addLayout(_res_row("순 비용",    '_sr_cost',     _S_VAL_Y))
        rg.addWidget(self._sep())
        rg.addLayout(_res_row("최대 이익",  '_sr_max_prof', _S_VAL_G))
        rg.addLayout(_res_row("최대 손실",  '_sr_max_loss', _S_VAL_R))
        rg.addWidget(self._sep())
        rg.addLayout(_res_row("BEP",        '_sr_bep',      _S_VAL_B))
        rg.addLayout(_res_row("손익비 R:R", '_sr_rr',       _S_VAL_Y))
        rg.addWidget(self._sep())

        self._strat_desc = QLabel("")
        self._strat_desc.setWordWrap(True)
        self._strat_desc.setStyleSheet(_S_HINT)
        rg.addWidget(self._strat_desc)
        rg.addStretch()
        return gb


# ═══════════════════════════════════════════════════════════════
# Part 4 — 이벤트 핸들러 / 세트 프리셋 적용 / 계산 로직
# ═══════════════════════════════════════════════════════════════

    # ── [S11-2] 만기 자동 동기화 ──────────────────────────────
    def _sync_strat_expiry(self):
        """옵션 체인 combo_exp 변경 시 호출 — 날짜 필드 자동 갱신."""
        if not hasattr(self, '_strat_date_edit'): return
        if not hasattr(self, 'combo_exp'): return
        if not hasattr(self, '_expiry_list'): return
        idx = self.combo_exp.currentIndex()
        if idx < 0 or idx >= len(self._expiry_list): return
        _, code, _ = self._expiry_list[idx]
        if code and code != "CUSTOM" and len(code) == 8:
            try:
                y, m, d = int(code[:4]), int(code[4:6]), int(code[6:8])
                self._strat_date_edit.blockSignals(True)
                self._strat_date_edit.setDate(QDate(y, m, d))
                self._strat_date_edit.blockSignals(False)
            except Exception:
                pass

    # ── 전략 변경 ─────────────────────────────────────────────
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
        self._update_set_tooltips()
        self._calc_strategy()

    # ── [S11-1] 세트 프리셋 적용 ──────────────────────────────
    def _apply_set_preset(self, set_idx: int):
        """
        세트 버튼 클릭 → ATM 기준 오프셋으로 레그 행사가 자동 입력.
        und_price 미수신 시 마지막 알려진 체인 클릭 행사가로 대체.
        """
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        presets = SET_PRESETS.get(strat, [])
        if set_idx >= len(presets): return
        p = presets[set_idx]

        # ATM 기준 행사가 계산
        atm = None
        if hasattr(self, 'und_price') and self.und_price:
            atm = self.und_price
        elif self._strat_leg["A"].get("strike"):
            atm = self._strat_leg["A"]["strike"]
        elif self._strat_leg["B"].get("strike"):
            atm = self._strat_leg["B"]["strike"]

        if atm is None:
            if hasattr(self, '_log'):
                self._log("⚠ 기초자산 가격 미수신 — 체인에서 먼저 조회하세요.")
            return

        # 종목별 행사가 스텝 적용
        from core import SYMBOL_CFG, DEFAULT_CFG
        sym = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "SPX"
        cfg = SYMBOL_CFG.get(sym, DEFAULT_CFG)
        step = cfg[3] if len(cfg) > 3 else 5

        sa = round(round(atm / step) * step + p["a_offset"])
        sb = round(round(atm / step) * step + p["b_offset"])

        self._leg_a_strike.setText(str(sa))
        self._leg_b_strike.setText(str(sb))
        self._strat_qty.setValue(p["qty"])

        # 기존 레그 데이터 보존 (price 는 0 유지 — 사용자가 수동 입력)
        self._strat_leg["A"] = {"strike": float(sa), "side": "", "mid": 0.0}
        self._strat_leg["B"] = {"strike": float(sb), "side": "", "mid": 0.0}

        self._strat_click_seq = 2  # 세트 완성 → 안내 숨김
        self._update_next_hint()
        self._calc_strategy()
        if hasattr(self, '_log'):
            self._log(f"[{strat}] {p['label']} 적용: A={sa} / B={sb} ({p['desc']})")

    def _update_set_tooltips(self):
        """전략 변경 시 세트 버튼 툴팁 갱신."""
        if not hasattr(self, '_set_btns'): return
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        presets = SET_PRESETS.get(strat, [])
        for i, btn in enumerate(self._set_btns):
            desc = presets[i]["desc"] if i < len(presets) else ""
            btn.setToolTip(f"{strat} {i+1}세트\n{desc}")

    def _update_next_hint(self):
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        is_back = "백" in strat
        seq = self._strat_click_seq
        if seq >= 2:
            hint = "✅ 양쪽 레그 입력 완료 — 계산 버튼을 누르거나 수량을 조정하세요"
        elif seq == 0:
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
        """체인 테이블 클릭 시 호출 (tab_options_price.py에서 연동)."""
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        if "콜" in strat and side != "C": return
        if "풋" in strat and side != "P": return

        mid = round((bid + ask) / 2, 2) if bid and ask else (ask or bid or 0.0)
        leg = "A" if self._strat_click_seq == 0 else "B"
        strike_str = str(int(strike)) if strike == int(strike) else str(strike)
        getattr(self, f'_leg_{leg.lower()}_strike').setText(strike_str)
        getattr(self, f'_leg_{leg.lower()}_price').setValue(mid)
        self._strat_leg[leg] = {
            "strike": strike, "side": side, "bid": bid, "ask": ask, "mid": mid}
        self._strat_click_seq = min(self._strat_click_seq + 1, 2)
        self._update_next_hint()
        self._calc_strategy()
        # 만기 자동 동기화
        self._sync_strat_expiry()

    # ── 손익 계산 ─────────────────────────────────────────────
    def _calc_strategy(self):
        strat = STRATEGIES[self._strat_combo.currentIndex()]
        qty   = self._strat_qty.value()
        mult  = 100
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
                f"{'비용' if net >= 0 else '크레딧'}  ${abs(net):,.0f}",
                f"${max_p:,.0f}",
                f"-${abs(max_l):,.0f}",
                f"{bep:.2f}",
                f"1 : {rr:.1f}" if rr > 0 else "―",
            )
        else:  # 백 스프레드
            credit = pa * mult * qty
            debit  = pb * mult * qty * 2
            net    = debit - credit
            max_l  = abs(sa - sb) * mult * qty + net
            if strat == "콜 백 스프레드":
                bep_lo = sa - net / (mult * qty) if net >= 0 else sa + abs(net) / (mult * qty)
                bep_hi = sb + net / (mult * qty) if net >= 0 else sb - abs(net) / (mult * qty)
                mp_str = "무제한 ↑"
            else:
                bep_hi = sa + net / (mult * qty) if net >= 0 else sa - abs(net) / (mult * qty)
                bep_lo = sb - net / (mult * qty) if net >= 0 else sb + abs(net) / (mult * qty)
                mp_str = "무제한 ↓"
            self._set_results(
                f"{'비용' if net >= 0 else '크레딧'}  ${abs(net):,.0f}",
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

# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# Part 5 — 단축키
# ═══════════════════════════════════════════════════════════════

    # ── [S11-4] 단축키 Shift+1~4 ─────────────────────────────
    def _install_strategy_shortcuts(self):
        """Shift+1~4 → 전략 유형 즉시 선택."""
        from PyQt5.QtWidgets import QShortcut
        mapping = {
            "Shift+1": 0,   # 콜 백 스프레드
            "Shift+2": 1,   # 풋 백 스프레드
            "Shift+3": 2,   # 콜 스프레드
            "Shift+4": 3,   # 풋 스프레드
        }
        for key_str, idx in mapping.items():
            sc = QShortcut(QKeySequence(key_str), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(lambda i=idx: self._select_strategy(i))

    def _select_strategy(self, idx: int):
        """단축키로 전략 선택 + 로그."""
        self._strat_combo.setCurrentIndex(idx)
        strat = STRATEGIES[idx]
        if hasattr(self, '_log'):
            self._log(f"⌨ 단축키 전략 선택: {strat}")

# ═══════════════════════════════════════════════════════════════
# Part 6 — 미체결 패널 (전략 설정 패널 하단 탭)
#   탭 구성: [증거금 확인] [합성 잔고] [미체결 내역]
#   + 정정주문 +1/-1 호가  + 선택/전체 취소
# ═══════════════════════════════════════════════════════════════

    def _build_open_orders_panel(self) -> QWidget:
        """미체결 탭 패널 — 전략 패널 하단에 인라인 배치."""
        from PyQt5.QtWidgets import (
            QTabWidget, QTableWidget, QHeaderView, QAbstractItemView,
            QTableWidgetItem, QGridLayout,
        )

        _tbl_ss = (
            "QTableWidget{background:#05050f;color:#ccc;gridline-color:#2a1a0a;"
            "font-size:11px;border:1px solid #3a2a1a;}"
            "QHeaderView::section{background:#0a0805;color:#ffd700;"
            "border:1px solid #2a1a0a;font-size:10px;padding:1px;}"
            "QTableWidget::item{padding:1px;}"
            "QTableWidget::item:selected{background:#3a2a0a;color:#ffd700;}"
            "QTableWidget::item:hover{background:#1a1005;}")
        _btn_ss = (
            "QPushButton{background:#1c1c3a;color:#dde0f0;font-size:11px;"
            "border:1px solid #3a3a7a;border-radius:3px;padding:2px 6px;}"
            "QPushButton:hover{background:#2a2a5a;}"
            "QPushButton:pressed{background:#0e0e2a;}")

        container = QWidget(); container.setStyleSheet("background:#08080f;")
        cv = QVBoxLayout(container)
        cv.setContentsMargins(2, 2, 2, 2); cv.setSpacing(2)

        # ── 탭 위젯 ────────────────────────────────────────────
        self._oo_tab = QTabWidget()
        self._oo_tab.setStyleSheet(
            "QTabBar::tab{background:#141430;color:#888;padding:4px 10px;"
            "border:1px solid #2e3060;border-bottom:none;font-size:11px;}"
            "QTabBar::tab:selected{background:#1c1c3a;color:#fff;font-weight:bold;}"
            "QTabWidget::pane{border:1px solid #2e3060;}")

        # ── Tab 0: 증거금 확인 ──────────────────────────────────
        tab_margin = QWidget()
        tv0 = QVBoxLayout(tab_margin)
        tv0.setContentsMargins(6, 6, 6, 4); tv0.setSpacing(3)

        margin_grid = QGridLayout(); margin_grid.setSpacing(3)
        margin_items = [
            ("초기 증거금 (Before)", '_mg_init_before'),
            ("초기 증거금 (After)",  '_mg_init_after'),
            ("유지 증거금 (Before)", '_mg_maint_before'),
            ("유지 증거금 (After)",  '_mg_maint_after'),
            ("예상 수수료",          '_mg_commission'),
        ]
        for i, (lbl_txt, attr) in enumerate(margin_items):
            margin_grid.addWidget(
                QLabel(lbl_txt,
                       styleSheet="color:#888;font-size:11px;border:none;"), i, 0)
            vl = QLabel("―")
            vl.setStyleSheet(
                "color:#ffd700;font-size:13px;font-weight:bold;border:none;")
            vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            setattr(self, attr, vl)
            margin_grid.addWidget(vl, i, 1)
        tv0.addLayout(margin_grid)

        btn_whatif = QPushButton("🔍 증거금 조회 (whatIf)")
        btn_whatif.setFixedHeight(24)
        btn_whatif.setStyleSheet(
            "QPushButton{background:#1a2a1a;color:#00ff88;font-size:11px;"
            "font-weight:bold;border:1px solid #2a5a2a;border-radius:3px;}"
            "QPushButton:hover{background:#2a3a2a;}")
        btn_whatif.clicked.connect(
            lambda: self._req_whatif() if hasattr(self, '_req_whatif') else
            self._log("⚠ _req_whatif 미구현 — order_logic.py 확인"))
        tv0.addWidget(btn_whatif)
        tv0.addStretch()
        self._oo_tab.addTab(tab_margin, "＋ 증거금 확인")

        # ── Tab 1: 합성 잔고 ────────────────────────────────────
        tab_synth = QWidget()
        tv1 = QVBoxLayout(tab_synth)
        tv1.setContentsMargins(4, 4, 4, 4); tv1.setSpacing(2)

        self.tbl_synth = QTableWidget(0, 6)
        self.tbl_synth.setHorizontalHeaderLabels(
            ["C/P", "행사가", "만기", "수량", "평균단가", "평가손익"])
        self.tbl_synth.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_synth.verticalHeader().setVisible(False)
        self.tbl_synth.verticalHeader().setDefaultSectionSize(20)
        self.tbl_synth.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_synth.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_synth.setMinimumHeight(0)
        self.tbl_synth.setStyleSheet(_tbl_ss)
        tv1.addWidget(self.tbl_synth, 1)

        btn_ref_synth = QPushButton("🔄 합성 잔고 조회")
        btn_ref_synth.setFixedHeight(24)
        btn_ref_synth.setStyleSheet(_btn_ss)
        btn_ref_synth.clicked.connect(
            lambda: self._refresh_positions()
            if hasattr(self, '_refresh_positions') else None)
        tv1.addWidget(btn_ref_synth)
        self._oo_tab.addTab(tab_synth, "합성 잔고")

        # ── Tab 2: 미체결 내역 ──────────────────────────────────
        tab_oo = QWidget()
        tv2 = QVBoxLayout(tab_oo)
        tv2.setContentsMargins(4, 4, 4, 4); tv2.setSpacing(3)

        oo_btn_row = QHBoxLayout(); oo_btn_row.setSpacing(4)
        btn_fetch_oo = QPushButton("🔄 미체결 조회")
        btn_fetch_oo.setFixedHeight(24)
        btn_fetch_oo.setStyleSheet(_btn_ss)
        btn_fetch_oo.clicked.connect(self._fetch_open_orders)

        btn_cancel_all = QPushButton("✕ 전체 취소")
        btn_cancel_all.setFixedHeight(24)
        btn_cancel_all.setStyleSheet(
            "QPushButton{background:#2a0a0a;color:#ff6666;font-size:11px;"
            "font-weight:bold;border:1px solid #5a1a1a;border-radius:3px;padding:2px 6px;}"
            "QPushButton:hover{background:#3a1a1a;}")
        btn_cancel_all.clicked.connect(self._cancel_all_open_orders)

        for w in (btn_fetch_oo, btn_cancel_all):
            oo_btn_row.addWidget(w)
        oo_btn_row.addStretch()
        tv2.addLayout(oo_btn_row)

        self.tbl_open_orders = QTableWidget(0, 7)
        self.tbl_open_orders.setHorizontalHeaderLabels(
            ["주문ID", "C/P", "행사가", "방향", "수량", "지정가", "상태"])
        self.tbl_open_orders.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.tbl_open_orders.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.tbl_open_orders.verticalHeader().setVisible(False)
        self.tbl_open_orders.verticalHeader().setDefaultSectionSize(20)
        self.tbl_open_orders.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_open_orders.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_open_orders.setMinimumHeight(0)
        self.tbl_open_orders.setStyleSheet(_tbl_ss)
        self.tbl_open_orders.cellClicked.connect(self._on_open_order_click)
        tv2.addWidget(self.tbl_open_orders, 1)

        # 정정/취소 버튼 행
        amend_row = QHBoxLayout(); amend_row.setSpacing(4)
        amend_row.addWidget(
            QLabel("정정:", styleSheet="color:#888;font-size:11px;border:none;"))

        for lbl, tip, delta, bg, fg, bd in [
            ("+1 호가", "선택 주문 +1 호가 정정", +1,
             "#1a3a1a", "#00ff88", "#2a5a2a"),
            ("-1 호가", "선택 주문 -1 호가 정정", -1,
             "#3a1a1a", "#ff6666", "#5a2a2a"),
        ]:
            b = QPushButton(lbl); b.setFixedHeight(22)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:{fg};font-size:11px;"
                f"font-weight:bold;border:1px solid {bd};border-radius:3px;padding:1px 6px;}}"
                f"QPushButton:hover{{background:{bd};}}")
            b.setToolTip(tip)
            b.clicked.connect(lambda _, d=delta: self._amend_order(d))
            amend_row.addWidget(b)

        btn_cancel_sel = QPushButton("✕ 선택 취소")
        btn_cancel_sel.setFixedHeight(22)
        btn_cancel_sel.setStyleSheet(
            "QPushButton{background:#2a1a0a;color:#ffaa44;font-size:11px;"
            "font-weight:bold;border:1px solid #5a3a1a;border-radius:3px;padding:1px 6px;}"
            "QPushButton:hover{background:#3a2a1a;}")
        btn_cancel_sel.setToolTip("선택한 미체결 주문 취소")
        btn_cancel_sel.clicked.connect(self._cancel_selected_order)
        amend_row.addWidget(btn_cancel_sel)
        amend_row.addStretch()
        tv2.addLayout(amend_row)
        self._oo_tab.addTab(tab_oo, "미체결 내역")

        cv.addWidget(self._oo_tab, 1)
        return container

    # ── 미체결 조회 ────────────────────────────────────────────
    def _fetch_open_orders(self):
        if not getattr(self, 'mw', None) or not self.mw.connected:
            self._log("⚠ TWS 미연결 — 미체결 조회 불가"); return
        self._log("🔍 미체결 주문 조회 중…")
        self.tbl_open_orders.setRowCount(0)
        try:
            self.mw.ib.reqOpenOrders()
        except Exception as e:
            self._log(f"미체결 조회 오류: {e}")

    def _on_open_orders_received(self, orders: list):
        """bridge.open_order_sig 집계 결과 → 테이블 갱신."""
        from PyQt5.QtWidgets import QTableWidgetItem as _Item
        from PyQt5.QtGui import QColor as _Clr, QBrush as _Br
        if not hasattr(self, 'tbl_open_orders'): return
        tbl = self.tbl_open_orders
        tbl.setRowCount(0)
        cp_colors = {"C": "#ff6666", "P": "#5599ff"}
        for row_data in orders:
            r = tbl.rowCount(); tbl.insertRow(r)
            for col, val in enumerate(row_data):
                it = _Item(str(val))
                it.setTextAlignment(Qt.AlignCenter)
                if col == 1:
                    it.setForeground(_Br(_Clr(cp_colors.get(str(val), "#dde0f0"))))
                tbl.setItem(r, col, it)
        self._log(f"미체결 주문 {len(orders)}건 수신")
        # 탭 자동 전환 → 미체결 내역
        if hasattr(self, '_oo_tab'):
            self._oo_tab.setCurrentIndex(2)

    def _on_open_order_click(self, row: int, col: int):
        try:
            self._selected_oo_id    = int(
                self.tbl_open_orders.item(row, 0).text())
            self._selected_oo_price = float(
                self.tbl_open_orders.item(row, 5).text())
            self._log(
                f"미체결 선택: OID={self._selected_oo_id}"
                f"  가격={self._selected_oo_price:.2f}")
        except Exception:
            pass

    # ── 정정주문 ───────────────────────────────────────────────
    def _amend_order(self, tick_dir: int):
        oid   = getattr(self, '_selected_oo_id',    None)
        price = getattr(self, '_selected_oo_price', None)
        if oid is None:
            self._log("⚠ 정정할 주문을 먼저 선택하세요."); return
        if not self.mw.connected:
            self._log("⚠ TWS 미연결"); return

        tick_size = 0.01 if price < 3.0 else 0.05
        new_price = round(price + tick_dir * tick_size, 2)
        if new_price <= 0:
            self._log("⚠ 가격이 0 이하 — 취소합니다."); return
        try:
            from ibapi.order import Order as _Ord
            o = _Ord()
            o.orderId = oid; o.orderType = "LMT"
            o.lmtPrice = new_price; o.totalQuantity = 1
            self.mw.ib.placeOrder(oid, None, o)
            self._selected_oo_price = new_price
            self._log(
                f"정정: OID={oid}  "
                f"{'▲' if tick_dir>0 else '▼'}{abs(tick_dir)} 호가"
                f"  {price:.2f} → {new_price:.2f}")
            QTimer.singleShot(800, self._fetch_open_orders)
        except Exception as e:
            self._log(f"정정 오류: {e}")

    # ── 취소 ───────────────────────────────────────────────────
    def _cancel_selected_order(self):
        oid = getattr(self, '_selected_oo_id', None)
        if oid is None:
            self._log("⚠ 취소할 주문을 먼저 선택하세요."); return
        self._cancel_order_by_id(oid)

    def _cancel_all_open_orders(self):
        tbl = self.tbl_open_orders
        if tbl.rowCount() == 0:
            self._fetch_open_orders()
            QTimer.singleShot(1200, self._cancel_all_open_orders)
            return
        ids = []
        for r in range(tbl.rowCount()):
            try: ids.append(int(tbl.item(r, 0).text()))
            except Exception: pass
        self._log(f"⚠ 전체 취소 시작: {len(ids)}건")
        for oid in ids:
            self._cancel_order_by_id(oid)

    def _cancel_order_by_id(self, oid: int):
        if not getattr(self, 'mw', None) or not self.mw.connected:
            self._log("⚠ TWS 미연결 — 취소 불가"); return
        try:
            self.mw.ib.cancelOrder(oid)
            self._log(f"취소 요청: OID={oid}")
            QTimer.singleShot(600, self._fetch_open_orders)
        except Exception as e:
            self._log(f"취소 오류 OID={oid}: {e}")