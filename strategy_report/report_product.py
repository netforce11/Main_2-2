"""
report_product.py — 상품·전략 메모 폼 UI   v1.0
════════════════════════════════════════════════
위치: IBKR/MAIN2/strategy_report/report_product.py

ProductFormPanel: QScrollArea 서브클래스
  Header    : 제목 / 심볼 / 카테고리 / 중요도
  Section ①  : 상품 기본 스펙 (계약단위 / 호가단위 / 연관·반대 상품)
  Section ②  : 만기 특징
  Section ③  : 상품 특징 / 주요 동작 패턴
  Section ④  : 전략 메모 (이 상품에 적합한 전략)
  Section ⑤  : 진입 / 청산 조건
  Section ⑥  : 리스크 메모
  Section ⑦  : 기타 메모
  Footer     : 저장 / 저장 후 새 상품 버튼
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit,
    QPushButton, QSizePolicy,
)
from PyQt5.QtCore import Qt

from .report_const import (
    FS_BODY, FS_SMALL, FS_SECTION, FS_HINT,
    PRODUCT_CATEGORIES, EXPIRY_TYPES, TICK_SIZES,
    StarWidget, hline, section_label, field_label,
    STYLE_INPUT, STYLE_TEXTEDIT, STYLE_COMBO,
)


class ProductFormPanel(QScrollArea):
    """상품·전략 메모 상세 편집 패널."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{border:none;background:#0f1a0f;}")

        container = QWidget()
        container.setStyleSheet("background:#0f1a0f;")
        self._lay = QVBoxLayout(container)
        self._lay.setContentsMargins(14, 10, 14, 14)
        self._lay.setSpacing(8)

        self._build_header()
        self._build_section1()
        self._build_section2()
        self._build_section3()
        self._build_section4()
        self._build_section5()
        self._build_section6()
        self._build_section7()
        self._build_footer()
        self._lay.addStretch()
        self.setWidget(container)

    # ── 공통 스타일 오버라이드 (초록 계열) ───────────────────
    _S_INPUT = (
        "background:#0d1f0d;color:#dfd;border:1px solid #3a6a3a;"
        f"border-radius:4px;padding:4px 8px;font-size:{FS_BODY};"
    )
    _S_TEXT = (
        "background:#0a180a;color:#cec;border:1px solid #2a5a2a;"
        f"border-radius:4px;padding:6px;font-size:{FS_BODY};"
    )
    _S_COMBO = (
        "background:#0d1f0d;color:#afa;border:1px solid #3a6a3a;"
        f"border-radius:4px;padding:3px 6px;font-size:{FS_BODY};"
    )

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:#8c8;font-size:{FS_BODY};")
        return lbl

    def _sec(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font-weight:bold;font-size:{FS_SECTION};"
            f"color:#afa;padding:4px 0 2px 0;"
        )
        return lbl

    def _hline(self):
        from PyQt5.QtWidgets import QFrame
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setFrameShadow(QFrame.Sunken)
        f.setStyleSheet("color:#2a4a2a;")
        return f

    # ── Header ───────────────────────────────────────────────
    def _build_header(self):
        self._lay.addWidget(self._sec("▶ 상품 기본 정보"))

        row1 = QHBoxLayout()
        row1.addWidget(self._lbl("카테고리:"))
        self.cmb_category = QComboBox()
        self.cmb_category.addItems(PRODUCT_CATEGORIES)
        self.cmb_category.setFixedWidth(160)
        self.cmb_category.setStyleSheet(self._S_COMBO)
        row1.addWidget(self.cmb_category)

        row1.addSpacing(12)
        row1.addWidget(self._lbl("중요도:"))
        self.wgt_stars = StarWidget()
        row1.addWidget(self.wgt_stars)
        row1.addStretch()
        self._lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(self._lbl("상품명 / 제목:"))
        self.edt_title = QLineEdit()
        self.edt_title.setPlaceholderText("예) SPXW 0DTE 콜 옵션")
        self.edt_title.setStyleSheet(
            f"background:#0d1f0d;color:#dfd;border:1px solid #3a6a3a;"
            f"border-radius:4px;padding:5px 8px;font-size:17px;"
        )
        row2.addWidget(self.edt_title, 1)
        self._lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(self._lbl("심볼:"))
        self.edt_symbol = QLineEdit()
        self.edt_symbol.setPlaceholderText("예) SPXW, SPY, QQQ")
        self.edt_symbol.setFixedWidth(160)
        self.edt_symbol.setStyleSheet(self._S_INPUT)
        row3.addWidget(self.edt_symbol)
        row3.addStretch()
        self._lay.addLayout(row3)
        self._lay.addWidget(self._hline())

    # ── ① 상품 스펙 ─────────────────────────────────────────
    def _build_section1(self):
        self._lay.addWidget(self._sec("① 상품 스펙"))

        # 계약단위 / 호가단위 / 틱 가치
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        v1 = QVBoxLayout()
        v1.addWidget(self._lbl("계약 단위:"))
        self.edt_contract_unit = QLineEdit()
        self.edt_contract_unit.setPlaceholderText("예) $100 × 지수")
        self.edt_contract_unit.setStyleSheet(self._S_INPUT)
        v1.addWidget(self.edt_contract_unit)
        row1.addLayout(v1)

        v2 = QVBoxLayout()
        v2.addWidget(self._lbl("호가 단위 (틱):"))
        h2 = QHBoxLayout()
        self.cmb_tick_size = QComboBox()
        self.cmb_tick_size.addItems(TICK_SIZES)
        self.cmb_tick_size.setFixedWidth(110)
        self.cmb_tick_size.setStyleSheet(self._S_COMBO)
        self.cmb_tick_size.currentTextChanged.connect(self._on_tick_changed)
        h2.addWidget(self.cmb_tick_size)
        self.edt_tick_custom = QLineEdit()
        self.edt_tick_custom.setPlaceholderText("직접 입력")
        self.edt_tick_custom.setFixedWidth(100)
        self.edt_tick_custom.setStyleSheet(self._S_INPUT)
        self.edt_tick_custom.setVisible(False)
        h2.addWidget(self.edt_tick_custom)
        v2.addLayout(h2)
        row1.addLayout(v2)

        v3 = QVBoxLayout()
        v3.addWidget(self._lbl("틱 가치 (금액):"))
        self.edt_tick_value = QLineEdit()
        self.edt_tick_value.setPlaceholderText("예) $5.00")
        self.edt_tick_value.setStyleSheet(self._S_INPUT)
        v3.addWidget(self.edt_tick_value)
        row1.addLayout(v3)

        self._lay.addLayout(row1)

        # 연관·반대 상품
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        v4 = QVBoxLayout()
        v4.addWidget(self._lbl("연관 상품:"))
        self.edt_related = QLineEdit()
        self.edt_related.setPlaceholderText("예) SPX, ES, SPY, VIX")
        self.edt_related.setStyleSheet(self._S_INPUT)
        v4.addWidget(self.edt_related)
        row2.addLayout(v4)

        v5 = QVBoxLayout()
        v5.addWidget(self._lbl("반대 상품 / 헤지:"))
        self.edt_opposite = QLineEdit()
        self.edt_opposite.setPlaceholderText("예) 풋 옵션, VIX 콜, SQQQ")
        self.edt_opposite.setStyleSheet(self._S_INPUT)
        v5.addWidget(self.edt_opposite)
        row2.addLayout(v5)

        self._lay.addLayout(row2)
        self._lay.addWidget(self._hline())

    def _on_tick_changed(self, text: str):
        self.edt_tick_custom.setVisible(text == "직접입력")

    # ── ② 만기 특징 ──────────────────────────────────────────
    def _build_section2(self):
        self._lay.addWidget(self._sec("② 만기 특징"))

        row = QHBoxLayout()
        row.addWidget(self._lbl("만기 유형:"))
        self.cmb_expiry_type = QComboBox()
        self.cmb_expiry_type.addItems(EXPIRY_TYPES)
        self.cmb_expiry_type.setFixedWidth(180)
        self.cmb_expiry_type.setStyleSheet(self._S_COMBO)
        row.addWidget(self.cmb_expiry_type)
        row.addStretch()
        self._lay.addLayout(row)

        self.txt_expiry_features = QTextEdit()
        self.txt_expiry_features.setPlaceholderText(
            "예) 매주 월~금 만기 존재 (0DTE)\n"
            "    3번째 금요일 = 월간 만기 (SPX Monthly)\n"
            "    만기 당일 오전 9:30 ~ 오후 4:00 ET\n"
            "    Pin Risk: 만기 직전 행사가 근처 급변동 주의\n"
            "    AM 만기 vs PM 만기 구분 확인 필수"
        )
        self.txt_expiry_features.setMinimumHeight(110)
        self.txt_expiry_features.setMaximumHeight(160)
        self.txt_expiry_features.setStyleSheet(self._S_TEXT)
        self._lay.addWidget(self.txt_expiry_features)
        self._lay.addWidget(self._hline())

    # ── ③ 상품 특징 ──────────────────────────────────────────
    def _build_section3(self):
        self._lay.addWidget(self._sec("③ 상품 특징 / 행동 패턴"))
        self.txt_characteristics = QTextEdit()
        self.txt_characteristics.setPlaceholderText(
            "예) SPX 옵션 특징:\n"
            "  - 현금 결제 (Cash-settled), 실물 인도 없음\n"
            "  - 유럽형 옵션 (만기일에만 행사 가능)\n"
            "  - 장 마감 후 CBOE SPX 지수 기준 정산\n"
            "  - 대형 기관 참여 많아 유동성 높음\n"
            "  - VIX 상승 시 풋 프리미엄 급등 패턴\n"
            "  - 장 시작 30분 / 장 마감 1시간 변동성 확대"
        )
        self.txt_characteristics.setMinimumHeight(130)
        self.txt_characteristics.setMaximumHeight(200)
        self.txt_characteristics.setStyleSheet(self._S_TEXT)
        self._lay.addWidget(self.txt_characteristics)
        self._lay.addWidget(self._hline())

    # ── ④ 전략 메모 ──────────────────────────────────────────
    def _build_section4(self):
        self._lay.addWidget(self._sec("④ 전략 메모 (이 상품에 적합한 전략)"))
        self.txt_strategy_memo = QTextEdit()
        self.txt_strategy_memo.setPlaceholderText(
            "예) SPXW 0DTE 활용 전략:\n"
            "  ✓ 콜/풋 스프레드: 방향성 있을 때 프리미엄 수취\n"
            "  ✓ 아이언 콘도르: 낮은 변동성 예상 시 양방향 수취\n"
            "  ✗ 네이키드 숏: 급등락 리스크 — 가급적 지양\n"
            "  📌 진입 타이밍: 장 시작 후 30분 이후 (초반 변동성 소화 후)\n"
            "  📌 청산 원칙: 수익 50% 달성 시 선청산 고려"
        )
        self.txt_strategy_memo.setMinimumHeight(130)
        self.txt_strategy_memo.setMaximumHeight(200)
        self.txt_strategy_memo.setStyleSheet(self._S_TEXT)
        self._lay.addWidget(self.txt_strategy_memo)
        self._lay.addWidget(self._hline())

    # ── ⑤ 진입 / 청산 조건 ───────────────────────────────────
    def _build_section5(self):
        self._lay.addWidget(self._sec("⑤ 진입 / 청산 조건"))
        s5 = QHBoxLayout()
        s5.setSpacing(12)

        s5l = QVBoxLayout()
        s5l.addWidget(self._lbl("진입 조건:"))
        self.txt_entry = QTextEdit()
        self.txt_entry.setPlaceholderText(
            "예)\n"
            "  - VIX < 20 (저변동성 구간)\n"
            "  - SPX 일봉 추세 확인 후\n"
            "  - 장 시작 30분 후 진입\n"
            "  - 수취 프리미엄 최소 $3 이상"
        )
        self.txt_entry.setMinimumHeight(110)
        self.txt_entry.setMaximumHeight(160)
        self.txt_entry.setStyleSheet(self._S_TEXT)
        s5l.addWidget(self.txt_entry)
        s5.addLayout(s5l)

        s5r = QVBoxLayout()
        s5r.addWidget(self._lbl("청산 조건:"))
        self.txt_exit = QTextEdit()
        self.txt_exit.setPlaceholderText(
            "예)\n"
            "  - 수익 50% 달성 시 선청산\n"
            "  - 손실 2배 달성 시 손절\n"
            "  - 만기 1시간 전 전량 청산\n"
            "  - VIX 급등 (20+) 시 즉시 청산"
        )
        self.txt_exit.setMinimumHeight(110)
        self.txt_exit.setMaximumHeight(160)
        self.txt_exit.setStyleSheet(self._S_TEXT)
        s5r.addWidget(self.txt_exit)
        s5.addLayout(s5r)

        self._lay.addLayout(s5)
        self._lay.addWidget(self._hline())

    # ── ⑥ 리스크 메모 ────────────────────────────────────────
    def _build_section6(self):
        self._lay.addWidget(self._sec("⑥ 리스크 메모"))
        self.txt_risk_memo = QTextEdit()
        self.txt_risk_memo.setPlaceholderText(
            "예)\n"
            "  ⚠ Pin Risk — 만기 행사가 근처에서 감마 폭발\n"
            "  ⚠ Gap Risk — 장 외 뉴스로 인한 갭 오픈\n"
            "  ⚠ IV Crush — 이벤트 직후 변동성 급락 (양방향 포지션 주의)\n"
            "  ⚠ 유동성 — 외가격 깊숙할수록 스프레드 확대"
        )
        self.txt_risk_memo.setMinimumHeight(100)
        self.txt_risk_memo.setMaximumHeight(150)
        self.txt_risk_memo.setStyleSheet(
            f"background:#1a0a0a;color:#fca;border:1px solid #5a3a1a;"
            f"border-radius:4px;padding:6px;font-size:{FS_BODY};"
        )
        self._lay.addWidget(self.txt_risk_memo)
        self._lay.addWidget(self._hline())

    # ── ⑦ 기타 메모 ─────────────────────────────────────────
    def _build_section7(self):
        self._lay.addWidget(self._sec("⑦ 기타 메모"))
        self.txt_memo = QTextEdit()
        self.txt_memo.setPlaceholderText("참고 링크, 추가 학습 내용, 기타 메모...")
        self.txt_memo.setMinimumHeight(80)
        self.txt_memo.setMaximumHeight(130)
        self.txt_memo.setStyleSheet(self._S_TEXT)
        self._lay.addWidget(self.txt_memo)

    # ── Footer ───────────────────────────────────────────────
    def _build_footer(self):
        self._lay.addSpacing(8)
        row = QHBoxLayout()
        row.addStretch()

        self.btn_save = QPushButton("💾  저장  (Ctrl+S)")
        self.btn_save.setFixedWidth(190)
        self.btn_save.setFixedHeight(42)
        self.btn_save.setStyleSheet(
            "background:#1a4a1a;color:#afa;border-radius:6px;"
            "font-size:16px;font-weight:bold;border:1px solid #3a9a3a;"
        )
        row.addWidget(self.btn_save)

        self.btn_save_new = QPushButton("＋  저장 후 새 상품")
        self.btn_save_new.setFixedWidth(200)
        self.btn_save_new.setFixedHeight(42)
        self.btn_save_new.setStyleSheet(
            "background:#1a3a2a;color:#7fa;border-radius:6px;"
            "font-size:15px;font-weight:bold;border:1px solid #2a7a4a;"
        )
        row.addWidget(self.btn_save_new)
        row.addStretch()
        self._lay.addLayout(row)

    # ── tick 값 반환 헬퍼 ─────────────────────────────────────
    def tick_size_value(self) -> str:
        v = self.cmb_tick_size.currentText()
        if v == "직접입력":
            return self.edt_tick_custom.text().strip()
        return v
