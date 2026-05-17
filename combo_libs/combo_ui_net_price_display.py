"""
combo_ui_net_price_display.py  (파트 1/2 — UI 구조 + 자동모드)
─────────────────────────────────────────────────────────────────
전광판형 Net Price 실시간 디스플레이 위젯

변경사항 (v2.0):
  ★ 가격 입력 모드 추가
    - [자동] 버튼: Mid-price 기반 Debit/Credit 자동 계산 (기존 동작)
    - [직접입력] 버튼: 사용자가 스프레드 가격 직접 입력
      • [-0.01] [가격입력창] [+0.01] 조절 버튼
      • get_bag_params() 가 직접입력 가격 우선 반환
  파트 2: combo_ui_net_price_input.py (직접입력 모드 UI + 로직)

변경사항 (v2.1):
  [FIX-DELTA] 지수 5P 당 예상 손익률 라벨 추가
    - DEBIT 가격 우측 끝에 형광색(#ffff44) 14pt 로 표시
    - update_delta_pnl(legs, entry) 외부 호출로 갱신
    - refresh() 호출 시 entry 자동 반영
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from combo_ui_net_price_input import ManualPriceRow   # 파트2 임포트


class NetPriceDisplay(QWidget):
    """
    실시간 Net Price 전광판 위젯.

    ┌──────────────────────────────────────────────────────┐
    │  순 프리미엄 (실시간)              ● LIVE            │
    │                                                      │
    │       DEBIT  $  2.35                                 │
    │  (지불) BUY 합계 $3.10 │ SELL 합계 $0.75            │
    │                                                      │
    │  [자동(Mid)]  [직접입력]                              │
    │  ← 직접입력 모드일 때만 표시 →                        │
    │  [-0.01]  [ 2.35 ]  [+0.01]  ☑ DEBIT / ☐ CREDIT    │
    └──────────────────────────────────────────────────────┘

    시그널:
        price_updated(float): net price 변경 시 방출 → 주문 모듈 구독용
    """

    price_updated = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._net_price: float = 0.0      # + = debit, - = credit
        self._buy_total: float = 0.0
        self._sell_total: float = 0.0
        self._is_live: bool = False
        self._manual_mode: bool = False   # False=자동, True=직접입력
        self._delta_legs: list = []       # [FIX-DELTA] 레그 리스트 캐시

        self._build_ui()

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(800)
        self._blink_timer.timeout.connect(self._blink_dot)
        self._blink_state = True

    # ──────────────────────────────────────────────
    # UI 구성
    # ──────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        # ── 헤더 행 ──────────────────────────────
        hdr = QHBoxLayout()
        lbl_title = QLabel("순 프리미엄 (실시간)")
        lbl_title.setStyleSheet("color:#aaa; font-size:11px;")
        self._lbl_live = QLabel("●  LIVE")
        self._lbl_live.setStyleSheet("color:#555; font-size:11px;")
        self._lbl_live.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hdr.addWidget(lbl_title)
        hdr.addStretch()
        hdr.addWidget(self._lbl_live)
        root.addLayout(hdr)

        # ── 메인 가격 행 ─────────────────────────
        price_row = QHBoxLayout()
        price_row.setSpacing(6)

        self._lbl_direction = QLabel("DEBIT")
        self._lbl_direction.setFont(QFont("Consolas", 11, QFont.Bold))
        self._lbl_direction.setFixedWidth(56)
        self._lbl_direction.setAlignment(Qt.AlignCenter)
        self._lbl_direction.setStyleSheet(
            "background:#1a3a1a; color:#4cff4c; border-radius:4px; padding:2px 4px;")

        self._lbl_dollar = QLabel("$")
        self._lbl_dollar.setFont(QFont("Consolas", 18, QFont.Bold))
        self._lbl_dollar.setStyleSheet("color:#ddd;")

        self._lbl_price = QLabel("—")
        self._lbl_price.setFont(QFont("Consolas", 28, QFont.Bold))
        self._lbl_price.setMinimumWidth(120)
        self._lbl_price.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._lbl_price.setStyleSheet("color:#ffffff; letter-spacing:1px;")

        # [FIX-DELTA] 5P 손익률 라벨
        self._lbl_delta_pnl = QLabel("")
        self._lbl_delta_pnl.setFont(QFont("Consolas", 14, QFont.Bold))
        self._lbl_delta_pnl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._lbl_delta_pnl.setStyleSheet("color:#ffff44; border:none;")
        self._lbl_delta_pnl.setVisible(False)   # 데이터 있을 때만 표시

        price_row.addWidget(self._lbl_direction)
        price_row.addWidget(self._lbl_dollar)
        price_row.addWidget(self._lbl_price)
        price_row.addStretch()
        price_row.addWidget(self._lbl_delta_pnl)   # [FIX-DELTA] 우측 끝
        root.addLayout(price_row)

        # ── 상세 행 ──────────────────────────────
        detail_row = QHBoxLayout()
        self._lbl_buy  = QLabel("BUY 합계  $—")
        self._lbl_sell = QLabel("SELL 합계  $—")
        for lbl in (self._lbl_buy, self._lbl_sell):
            lbl.setFont(QFont("Consolas", 10))
            lbl.setStyleSheet("color:#888;")
        self._lbl_hint = QLabel("(지불)")
        self._lbl_hint.setStyleSheet("color:#555; font-size:10px;")
        detail_row.addWidget(self._lbl_hint)
        detail_row.addWidget(self._lbl_buy)
        detail_row.addWidget(QLabel(" │ "))
        detail_row.addWidget(self._lbl_sell)
        detail_row.addStretch()
        root.addLayout(detail_row)

        # ── 모드 토글 행 ─────────────────────────
        root.addLayout(self._build_mode_toggle_row())

        # ── 직접입력 행 (ManualPriceRow, 파트2) ──
        self._manual_row = ManualPriceRow()
        self._manual_row.setVisible(False)
        root.addWidget(self._manual_row)

        # 전체 위젯 스타일
        try:
            import core as _c
            _t = _c.THEME_PALETTES.get(_c.CURRENT_THEME, _c.THEME_PALETTES["light"])
            _bg = _t['group_bg']; _bd = _t['group_border']
        except Exception:
            _bg = "#141d2b"; _bd = "#2a3a50"
        self.setStyleSheet(
            f"NetPriceDisplay{{background:{_bg};"
            f"border:1px solid {_bd};border-radius:6px;}}")
        self.setMinimumHeight(80)

    def _build_mode_toggle_row(self) -> QHBoxLayout:
        """[자동(Mid)] / [직접입력] 토글 버튼 행."""
        row = QHBoxLayout()
        row.setSpacing(4)

        self._btn_auto = QPushButton("자동(Mid)")
        self._btn_manual = QPushButton("✏ 직접입력")

        for btn in (self._btn_auto, self._btn_manual):
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setFont(QFont("Consolas", 9))

        self._btn_auto.setChecked(True)
        self._btn_auto.setStyleSheet(self._toggle_style(active=True))
        self._btn_manual.setChecked(False)
        self._btn_manual.setStyleSheet(self._toggle_style(active=False))

        self._btn_auto.clicked.connect(lambda: self._set_mode(False))
        self._btn_manual.clicked.connect(lambda: self._set_mode(True))

        row.addWidget(QLabel("가격 모드:"))
        row.addWidget(self._btn_auto)
        row.addWidget(self._btn_manual)
        row.addStretch()
        return row

    @staticmethod
    def _toggle_style(active: bool) -> str:
        try:
            import core as _c
            t = _c.THEME_PALETTES.get(_c.CURRENT_THEME, _c.THEME_PALETTES["light"])
            if active:
                return (f"background:{t['group_bg']}; color:{t['group_title']}; "
                        f"border:1px solid {t['btn_hover_bdr']}; border-radius:6px; padding:1px 6px;")
            return (f"background:{t['group_bg']}; color:{t['input_border']}; "
                    f"border:1px solid {t['input_border']}; border-radius:6px; padding:1px 6px;")
        except Exception:
            if active:
                return ("background:#1a3a5a; color:#4ca8ff; "
                        "border:1px solid #4ca8ff; border-radius:6px; padding:1px 6px;")
            return ("background:#1a1a2a; color:#556; "
                    "border:1px solid #334; border-radius:6px; padding:1px 6px;")

    # ──────────────────────────────────────────────
    # 모드 전환
    # ──────────────────────────────────────────────
    def _set_mode(self, manual: bool):
        self._manual_mode = manual
        self._btn_auto.setChecked(not manual)
        self._btn_manual.setChecked(manual)
        self._btn_auto.setStyleSheet(self._toggle_style(not manual))
        self._btn_manual.setStyleSheet(self._toggle_style(manual))
        self._manual_row.setVisible(manual)

        # 직접입력 전환 시 현재 자동계산 가격을 초기값으로 설정
        if manual and self._net_price != 0.0:
            self._manual_row.set_price(abs(self._net_price))
            self._manual_row.set_direction(self._net_price >= 0)

    # ──────────────────────────────────────────────
    # 외부 호출 API
    # ──────────────────────────────────────────────
    def refresh(self, buy_total: float, sell_total: float):
        """
        fill_premium_from_market() 완료 후 호출.
        buy_total  : BUY 레그 프리미엄 합계 (양수)
        sell_total : SELL 레그 프리미엄 합계 (양수)
        자동모드 전광판만 갱신; 직접입력 모드에서는 전광판 표시만 업데이트.
        """
        self._buy_total  = buy_total
        self._sell_total = sell_total
        net = buy_total - sell_total
        self._net_price  = net
        self._is_live    = True

        abs_net = abs(net)
        self._lbl_price.setText(f"{abs_net:.2f}")
        self._lbl_buy.setText(f"BUY 합계  ${buy_total:.2f}")
        self._lbl_sell.setText(f"SELL 합계  ${sell_total:.2f}")

        if net >= 0:
            self._lbl_direction.setText("DEBIT")
            self._lbl_direction.setStyleSheet(
                "background:#1a3a1a; color:#4cff4c; border-radius:4px; padding:2px 4px;")
            self._lbl_price.setStyleSheet("color:#4cff4c; letter-spacing:1px;")
            self._lbl_hint.setText("(지불)")
        else:
            self._lbl_direction.setText("CREDIT")
            self._lbl_direction.setStyleSheet(
                "background:#1a1a3a; color:#4c9fff; border-radius:4px; padding:2px 4px;")
            self._lbl_price.setStyleSheet("color:#4c9fff; letter-spacing:1px;")
            self._lbl_hint.setText("(수취)")

        if not self._blink_timer.isActive():
            self._blink_timer.start()

        self.price_updated.emit(net)

        # [FIX-DELTA] 저장된 레그가 있으면 새 entry 기준으로 재계산
        if self._delta_legs:
            self._recalc_delta_pnl(abs_net)

    def get_net_price(self) -> float:
        """주문 모듈에서 lmtPrice 로 사용 (직접입력 우선)."""
        if self._manual_mode:
            p = self._manual_row.get_price()
            return p if self._manual_row.is_debit() else -p
        return self._net_price

    def get_bag_params(self) -> dict:
        """
        _do_send_body() 에서 직접 사용.
        직접입력 모드이면 입력 가격 우선 반환.
        returns: {"lmt_price": float, "action": "BUY"|"SELL", "manual": bool}
        """
        if self._manual_mode:
            if not self._manual_row.is_ready():
                # 직접입력 모드지만 가격 미입력 → None 반환으로 호출부에서 차단
                return {"lmt_price": 0.0, "action": "BUY", "manual": True, "invalid": True}
            price  = self._manual_row.get_price()
            is_deb = self._manual_row.is_debit()
            return {
                "lmt_price": round(max(price, 0.01), 2),
                "action":    "BUY" if is_deb else "SELL",
                "manual":    True,
                "invalid":   False,
            }
        # 자동모드 (기존 동작)
        net = self._net_price
        if net >= 0:
            return {"lmt_price": round(net, 2), "action": "BUY", "manual": False, "invalid": False}
        return {"lmt_price": round(abs(net), 2), "action": "SELL", "manual": False, "invalid": False}

    def reset(self):
        """전략 변경 / 레그 리셋 시 초기화."""
        self._net_price  = 0.0
        self._buy_total  = 0.0
        self._sell_total = 0.0
        self._is_live    = False
        self._delta_legs = []                          # [FIX-DELTA]
        self._lbl_price.setText("—")
        self._lbl_buy.setText("BUY 합계  $—")
        self._lbl_sell.setText("SELL 합계  $—")
        self._lbl_hint.setText("(지불)")
        self._lbl_live.setStyleSheet("color:#555; font-size:11px;")
        self._lbl_delta_pnl.setText("")                # [FIX-DELTA]
        self._lbl_delta_pnl.setVisible(False)          # [FIX-DELTA]
        self._blink_timer.stop()
        # 직접입력도 초기화
        self._manual_row.set_price(0.0)

    # ──────────────────────────────────────────────
    # [FIX-DELTA] 5P 손익률 외부 갱신 API
    # ──────────────────────────────────────────────
    def update_delta_pnl(self, legs: list, entry: float = 0.0) -> None:
        """
        [FIX-DELTA] 레그 설정 완료 시 호출 → DEBIT 우측에 5P 손익률 표시.

        Args:
            legs  : 레그 딕셔너리 리스트. 각 원소에 'delta', 'dir', 'qty' 필요.
                    예) [{'dir':'BUY','qty':1,'delta':0.38}, {'dir':'SELL','qty':1,'delta':0.33}]
            entry : DEBIT 가격 (달러). 0이면 self._net_price 의 절대값 사용.

        호출 시점 예시 (tab_combo_shortcut.py 또는 _trigger_premium 완료 후):
            display = getattr(self, 'net_price_display', None)
            if display:
                display.update_delta_pnl(legs)
        """
        self._delta_legs = legs or []
        use_entry = entry if entry > 0 else abs(self._net_price)
        self._recalc_delta_pnl(use_entry)

    def _recalc_delta_pnl(self, entry: float) -> None:
        """
        [FIX-DELTA] 내부 계산 함수.
        포지션 델타 = Σ(leg_delta × leg_qty × 방향계수)
        5P 손익률(%) = (포지션 델타 × 5 × 100) / (entry × 100) × 100
        """
        legs = self._delta_legs
        if not legs or entry <= 0:
            self._lbl_delta_pnl.setVisible(False)
            return

        try:
            pos_delta = 0.0
            has_delta = False
            for leg in legs:
                raw = leg.get("delta")
                if raw is None:
                    continue
                leg_delta = float(raw)
                leg_qty   = float(leg.get("qty", 1) or 1)
                leg_dir   = str(leg.get("dir", "BUY")).upper()
                if leg_dir == "SELL":
                    leg_delta = -leg_delta
                pos_delta += leg_delta * leg_qty
                has_delta = True

            if not has_delta:
                self._lbl_delta_pnl.setVisible(False)
                return

            # 5P 손익률
            five_p_pnl    = pos_delta * 5.0 * 100.0   # 달러
            debit_dollars = entry * 100.0              # $1.80 → $180
            pnl_pct       = (five_p_pnl / debit_dollars) * 100.0

            if pnl_pct >= 0:
                txt   = f"5P ▲ +{pnl_pct:.0f}%"
                color = "#ffff44"   # 형광 노랑
            else:
                txt   = f"5P ▼ {pnl_pct:.0f}%"
                color = "#ff6666"   # 연한 빨강

            self._lbl_delta_pnl.setText(txt)
            self._lbl_delta_pnl.setStyleSheet(
                f"color:{color}; border:none; font-weight:bold;")
            self._lbl_delta_pnl.setVisible(True)

        except Exception:
            self._lbl_delta_pnl.setVisible(False)

    # ──────────────────────────────────────────────
    # 내부
    # ──────────────────────────────────────────────
    def _blink_dot(self):
        self._blink_state = not self._blink_state
        color = "#00e676" if self._blink_state else "#555"
        self._lbl_live.setStyleSheet(f"color:{color}; font-size:11px;")