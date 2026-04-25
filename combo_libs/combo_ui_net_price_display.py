"""
combo_ui_net_price_display.py
─────────────────────────────────────────────────────────────
전광판형 Net Price 실시간 디스플레이 위젯

위치: 레그 패널 하단 (기존 Net Price 라벨 교체)
연동:
  - fill_premium_from_market() 이 호출될 때마다 refresh() 호출
  - _do_send() 에서 get_net_price() 로 lmtPrice 자동 수신
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette


class NetPriceDisplay(QWidget):
    """
    실시간 Net Price 전광판 위젯.

    ┌──────────────────────────────────────────────┐
    │  순 프리미엄 (실시간)            ● LIVE       │
    │                                              │
    │        DEBIT  $  2.35                        │
    │   (지불)  BUY 합계 $3.10 │ SELL 합계 $0.75  │
    └──────────────────────────────────────────────┘

    시그널:
        price_updated(float)  : net price 변경 시 방출 → 주문 모듈에서 구독
    """

    price_updated = pyqtSignal(float)   # 외부 주문 모듈 연동용

    def __init__(self, parent=None):
        super().__init__(parent)
        self._net_price: float = 0.0          # + = debit, - = credit
        self._buy_total: float = 0.0
        self._sell_total: float = 0.0
        self._is_live: bool = False

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

        # ── 헤더 행 ──
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

        # ── 메인 가격 행 ──
        price_row = QHBoxLayout()
        price_row.setSpacing(6)

        self._lbl_direction = QLabel("DEBIT")
        self._lbl_direction.setFont(QFont("Consolas", 11, QFont.Bold))
        self._lbl_direction.setFixedWidth(56)
        self._lbl_direction.setAlignment(Qt.AlignCenter)
        self._lbl_direction.setStyleSheet(
            "background:#1a3a1a; color:#4cff4c; border-radius:4px; padding:2px 4px;"
        )

        self._lbl_dollar = QLabel("$")
        self._lbl_dollar.setFont(QFont("Consolas", 18, QFont.Bold))
        self._lbl_dollar.setStyleSheet("color:#ddd;")

        self._lbl_price = QLabel("—")
        self._lbl_price.setFont(QFont("Consolas", 28, QFont.Bold))
        self._lbl_price.setMinimumWidth(120)
        self._lbl_price.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._lbl_price.setStyleSheet("color:#ffffff; letter-spacing:1px;")

        price_row.addWidget(self._lbl_direction)
        price_row.addWidget(self._lbl_dollar)
        price_row.addWidget(self._lbl_price)
        price_row.addStretch()
        root.addLayout(price_row)

        # ── 상세 행 ──
        detail_row = QHBoxLayout()
        self._lbl_buy = QLabel("BUY 합계  $—")
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

        # 전체 스타일
        self.setStyleSheet("""
            NetPriceDisplay {
                background: #141d2b;
                border: 1px solid #2a3a50;
                border-radius: 6px;
            }
        """)
        self.setMinimumHeight(80)

    # ──────────────────────────────────────────────
    # 외부 호출 API
    # ──────────────────────────────────────────────
    def refresh(self, buy_total: float, sell_total: float):
        """
        fill_premium_from_market() 완료 후 호출.
        buy_total  : BUY 레그 프리미엄 합계 (양수)
        sell_total : SELL 레그 프리미엄 합계 (양수)
        """
        self._buy_total = buy_total
        self._sell_total = sell_total
        net = buy_total - sell_total          # + = debit, - = credit
        self._net_price = net
        self._is_live = True

        # 가격 표시
        abs_net = abs(net)
        self._lbl_price.setText(f"{abs_net:.2f}")
        self._lbl_buy.setText(f"BUY 합계  ${buy_total:.2f}")
        self._lbl_sell.setText(f"SELL 합계  ${sell_total:.2f}")

        if net >= 0:          # Debit (지불)
            self._lbl_direction.setText("DEBIT")
            self._lbl_direction.setStyleSheet(
                "background:#1a3a1a; color:#4cff4c; border-radius:4px; padding:2px 4px;"
            )
            self._lbl_price.setStyleSheet("color:#4cff4c; letter-spacing:1px;")
            self._lbl_hint.setText("(지불)")
        else:                  # Credit (수취)
            self._lbl_direction.setText("CREDIT")
            self._lbl_direction.setStyleSheet(
                "background:#1a1a3a; color:#4c9fff; border-radius:4px; padding:2px 4px;"
            )
            self._lbl_price.setStyleSheet("color:#4c9fff; letter-spacing:1px;")
            self._lbl_hint.setText("(수취)")

        if not self._blink_timer.isActive():
            self._blink_timer.start()

        # 시그널 방출 → 주문 모듈
        self.price_updated.emit(net)

    def get_net_price(self) -> float:
        """주문 모듈에서 lmtPrice 로 사용"""
        return self._net_price

    def get_bag_params(self) -> dict:
        """
        _do_send() 에서 직접 사용.
        returns: {"lmt_price": float, "action": "BUY"|"SELL"}
        """
        if self._net_price >= 0:
            return {"lmt_price": round(self._net_price, 2), "action": "BUY"}
        else:
            return {"lmt_price": round(abs(self._net_price), 2), "action": "SELL"}

    def reset(self):
        """전략 변경 / 레그 리셋 시 초기화"""
        self._net_price = 0.0
        self._buy_total = 0.0
        self._sell_total = 0.0
        self._is_live = False
        self._lbl_price.setText("—")
        self._lbl_buy.setText("BUY 합계  $—")
        self._lbl_sell.setText("SELL 합계  $—")
        self._lbl_hint.setText("(지불)")
        self._lbl_live.setStyleSheet("color:#555; font-size:11px;")
        self._blink_timer.stop()

    # ──────────────────────────────────────────────
    # 내부
    # ──────────────────────────────────────────────
    def _blink_dot(self):
        self._blink_state = not self._blink_state
        color = "#00e676" if self._blink_state else "#555"
        self._lbl_live.setStyleSheet(f"color:{color}; font-size:11px;")