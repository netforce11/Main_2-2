"""
combo_ui_net_price_input.py  (파트 2/2 — 직접입력 모드 UI + 로직)
──────────────────────────────────────────────────────────────────
NetPriceDisplay 의 직접입력 서브 위젯.

UI:
    [-0.01]  [  2.35  ]  [+0.01]    ○ DEBIT  ○ CREDIT

특징:
  - +0.01 / -0.01 버튼으로 가격 미세 조정
  - 가격 최솟값 0.01 (0 이하 진입 차단)
  - DEBIT / CREDIT 라디오 버튼으로 주문 방향 전환
  - 직접 타이핑 가능 (QLineEdit)
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QButtonGroup, QRadioButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QDoubleValidator


class ManualPriceRow(QWidget):
    """
    직접입력 가격 행 위젯.

    부모(NetPriceDisplay)가 setVisible(True/False)로 표시 제어.
    get_price()  → float (절댓값)
    is_debit()   → bool  (True=DEBIT/BUY, False=CREDIT/SELL)
    set_price()  → 외부에서 초기값 주입
    """

    _STEP = 0.01
    _MIN  = 0.01

    def __init__(self, parent=None):
        super().__init__(parent)
        self._price: float = 0.0
        self._is_debit: bool = True
        self._build_ui()

    # ──────────────────────────────────────────────
    # UI 구성
    # ──────────────────────────────────────────────
    def _build_ui(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(4)

        # ── 가격 조절 섹션 ────────────────────────
        lbl = QLabel("스프레드 가격:")
        lbl.setStyleSheet("color:#aaa; font-size:11px;")
        lbl.setFont(QFont("Consolas", 10))
        row.addWidget(lbl)

        # [-0.01] 버튼
        self._btn_minus = QPushButton("−0.01")
        self._btn_minus.setFixedSize(52, 24)
        self._btn_minus.setFont(QFont("Consolas", 9, QFont.Bold))
        self._btn_minus.setStyleSheet(self._step_btn_style("#5a1a1a", "#ff6666"))
        self._btn_minus.clicked.connect(self._on_minus)
        row.addWidget(self._btn_minus)

        # 가격 입력창
        self._edit = QLineEdit("0.00")
        self._edit.setFixedSize(68, 24)
        self._edit.setAlignment(Qt.AlignCenter)
        self._edit.setFont(QFont("Consolas", 12, QFont.Bold))
        self._edit.setStyleSheet(
            "background:#0d1a2a; color:#ffd700; "
            "border:1px solid #4ca8ff; border-radius:3px; "
            "padding:1px 4px;")
        # 소수점 2자리 양수만 허용
        self._edit.setValidator(QDoubleValidator(0.00, 9999.99, 2, self._edit))
        self._edit.editingFinished.connect(self._on_edit_finished)
        row.addWidget(self._edit)

        # [+0.01] 버튼
        self._btn_plus = QPushButton("+0.01")
        self._btn_plus.setFixedSize(52, 24)
        self._btn_plus.setFont(QFont("Consolas", 9, QFont.Bold))
        self._btn_plus.setStyleSheet(self._step_btn_style("#1a3a1a", "#4cff4c"))
        self._btn_plus.clicked.connect(self._on_plus)
        row.addWidget(self._btn_plus)

        # ── 구분선 ───────────────────────────────
        sep = QLabel("│")
        sep.setStyleSheet("color:#334; font-size:14px; border:none;")
        sep.setFixedWidth(10)
        sep.setAlignment(Qt.AlignCenter)
        row.addWidget(sep)

        # ── DEBIT / CREDIT 라디오 ─────────────────
        self._rb_debit  = QRadioButton("DEBIT")
        self._rb_credit = QRadioButton("CREDIT")
        self._rb_debit.setChecked(True)

        self._rb_debit.setStyleSheet(
            "color:#4cff4c; font-size:10px; font-family:Consolas;")
        self._rb_credit.setStyleSheet(
            "color:#4c9fff; font-size:10px; font-family:Consolas;")

        self._bg = QButtonGroup(self)
        self._bg.addButton(self._rb_debit,  0)
        self._bg.addButton(self._rb_credit, 1)
        self._bg.buttonClicked.connect(self._on_direction_changed)

        row.addWidget(self._rb_debit)
        row.addWidget(self._rb_credit)
        row.addStretch()

        # 배경 스타일
        self.setStyleSheet(
            "ManualPriceRow { background:#0d1520; border-top:1px solid #233; "
            "border-radius:0px; }")

    @staticmethod
    def _step_btn_style(bg: str, fg: str) -> str:
        return (
            f"QPushButton{{background:{bg}; color:{fg}; "
            f"border:1px solid {fg}; border-radius:3px; "
            f"font-size:9px; font-weight:bold; padding:1px 4px;}}"
            f"QPushButton:hover{{background:{fg}; color:#000;}}"
            f"QPushButton:pressed{{background:{fg}; color:#000; "
            f"border:1px solid #fff;}}"
        )

    # ──────────────────────────────────────────────
    # 이벤트 핸들러
    # ──────────────────────────────────────────────
    def _on_plus(self):
        self._set_price_clamp(self._price + self._STEP)

    def _on_minus(self):
        self._set_price_clamp(self._price - self._STEP)

    def _on_edit_finished(self):
        try:
            val = float(self._edit.text().replace(",", ""))
        except ValueError:
            val = self._price
        self._set_price_clamp(val)

    def _on_direction_changed(self):
        self._is_debit = self._rb_debit.isChecked()

    def _set_price_clamp(self, val: float):
        """최솟값 0.01 보장 후 QLineEdit 갱신."""
        self._price = max(round(val, 2), self._MIN)
        self._edit.setText(f"{self._price:.2f}")

    # ──────────────────────────────────────────────
    # 외부 API
    # ──────────────────────────────────────────────
    def get_price(self) -> float:
        """절댓값 가격 반환 (최소 0.01)."""
        return max(self._price, self._MIN)

    def is_debit(self) -> bool:
        """True → DEBIT(BUY), False → CREDIT(SELL)."""
        return self._rb_debit.isChecked()

    def set_price(self, val: float):
        """외부에서 초기값 주입 (자동모드 → 직접입력 전환 시)."""
        self._set_price_clamp(val)

    def set_direction(self, is_debit: bool):
        """방향 초기화 (자동모드 → 직접입력 전환 시)."""
        self._is_debit = is_debit
        self._rb_debit.setChecked(is_debit)
        self._rb_credit.setChecked(not is_debit)
