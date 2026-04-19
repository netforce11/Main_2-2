"""
report_right.py — 우측 매매 복기 폼 UI   v2.0
════════════════════════════════════════════════
위치: IBKR/MAIN2/strategy_report/report_right.py

변경:
  v2.0 — 기존 복기 폼 그대로 유지
         tab_report.py 에서 QTabWidget 으로 감싸
         (이 파일은 복기 탭 내용만 담당)
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QDateEdit, QComboBox, QTextEdit,
    QCheckBox, QGroupBox, QGridLayout,
    QPushButton, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QDate

from .report_const import (
    FS_BODY, FS_SMALL, FS_SECTION, FS_TITLE, FS_HINT,
    STRATEGY_LIST, EVENT_TAGS,
    StarWidget, hline, section_label, field_label,
    STYLE_INPUT, STYLE_TEXTEDIT, STYLE_COMBO,
)


class TradeFormPanel(QScrollArea):
    """매매 복기 상세 편집 패널."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{border:none;background:#111;}")

        container = QWidget()
        container.setStyleSheet("background:#111;")
        self._lay = QVBoxLayout(container)
        self._lay.setContentsMargins(14, 10, 14, 14)
        self._lay.setSpacing(8)

        self._build_header()
        self._build_section1()
        self._build_section2()
        self._build_section3()
        self._build_section4()
        self._build_section5()
        self._build_footer()
        self._lay.addStretch()
        self.setWidget(container)

    # ── Header ───────────────────────────────────────────────
    def _build_header(self):
        self._lay.addWidget(section_label("▶ 기본 정보"))

        row1 = QHBoxLayout()
        row1.addWidget(field_label("날짜:"))
        self.edt_date = QDateEdit()
        self.edt_date.setCalendarPopup(True)
        self.edt_date.setDate(QDate.currentDate())
        self.edt_date.setDisplayFormat("yyyy-MM-dd")
        self.edt_date.setFixedWidth(140)
        self.edt_date.setStyleSheet(STYLE_INPUT)
        row1.addWidget(self.edt_date)

        row1.addSpacing(12)
        row1.addWidget(field_label("중요도:"))
        self.wgt_stars = StarWidget()
        row1.addWidget(self.wgt_stars)

        row1.addSpacing(12)
        row1.addWidget(field_label("이벤트:"))
        self.cmb_event_tag = QComboBox()
        self.cmb_event_tag.addItems(EVENT_TAGS)
        self.cmb_event_tag.setFixedWidth(120)
        self.cmb_event_tag.setStyleSheet(STYLE_COMBO)
        row1.addWidget(self.cmb_event_tag)
        row1.addStretch()
        self._lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(field_label("제목:"))
        self.edt_title = QLineEdit()
        self.edt_title.setPlaceholderText("리포트 제목")
        self.edt_title.setStyleSheet(
            f"background:#1e1e2e;color:#fff;border:1px solid #555;"
            f"border-radius:4px;padding:5px 8px;font-size:17px;"
        )
        row2.addWidget(self.edt_title, 1)
        self._lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(field_label("SPX:"))
        self.edt_spx = QLineEdit("0.00")
        self.edt_spx.setFixedWidth(100)
        self.edt_spx.setStyleSheet(
            f"background:#1e1e2e;color:#7df;border:1px solid #444;"
            f"border-radius:4px;padding:3px 6px;font-size:{FS_BODY};"
        )
        row3.addWidget(self.edt_spx)

        row3.addSpacing(12)
        row3.addWidget(field_label("VIX:"))
        self.edt_vix = QLineEdit("0.00")
        self.edt_vix.setFixedWidth(80)
        self.edt_vix.setStyleSheet(
            f"background:#1e1e2e;color:#fd7;border:1px solid #444;"
            f"border-radius:4px;padding:3px 6px;font-size:{FS_BODY};"
        )
        row3.addWidget(self.edt_vix)
        note = QLabel("(저장 시 자동 기록)")
        note.setStyleSheet(f"color:#666;font-size:{FS_SMALL};")
        row3.addWidget(note)
        row3.addStretch()
        self._lay.addLayout(row3)
        self._lay.addWidget(hline())

    # ── ① 이벤트 고찰 ────────────────────────────────────────
    def _build_section1(self):
        self._lay.addWidget(section_label("① 이벤트 고찰"))
        self.txt_event = QTextEdit()
        self.txt_event.setPlaceholderText(
            "예) FOMC 금리 동결 → 시장 초기 상승 후 반락. VIX 18→14 급락.\n"
            "    → 단기 콜 프리미엄 급감 예상, 풋 스프레드 유리할 듯..."
        )
        self.txt_event.setMinimumHeight(110)
        self.txt_event.setMaximumHeight(170)
        self.txt_event.setStyleSheet(STYLE_TEXTEDIT)
        self._lay.addWidget(self.txt_event)
        self._lay.addWidget(hline())

    # ── ② 전략 + 상품 선정 ───────────────────────────────────
    def _build_section2(self):
        self._lay.addWidget(section_label("② 전략 선택 및 상품 선정"))

        s2 = QHBoxLayout()
        s2.setSpacing(12)

        grp = QGroupBox("전략 선택")
        grp.setStyleSheet(
            f"QGroupBox{{color:#aef;border:1px solid #444;border-radius:4px;"
            f"margin-top:8px;padding:8px;font-size:{FS_BODY};}}"
            f"QGroupBox::title{{subcontrol-origin:margin;left:8px;top:-2px;}}"
        )
        g_lay = QGridLayout(grp)
        g_lay.setSpacing(6)
        self._chk_strategies: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(STRATEGY_LIST):
            chk = QCheckBox(label)
            chk.setStyleSheet(f"color:#ccc;font-size:{FS_BODY};")
            g_lay.addWidget(chk, i // 2, i % 2)
            self._chk_strategies[key] = chk
        s2.addWidget(grp)

        s2r = QVBoxLayout()
        s2r.setSpacing(6)
        s2r.addWidget(field_label("상품 선정 및 선정 사유:"))
        self.txt_product = QTextEdit()
        self.txt_product.setPlaceholderText(
            "예) SPXW 5200C / 5190-5200 콜 스프레드\n"
            "    프리미엄 수취 $8.50, 최대이익 $8.50, 최대손실 $1.50"
        )
        self.txt_product.setMinimumHeight(88)
        self.txt_product.setMaximumHeight(140)
        self.txt_product.setStyleSheet(STYLE_TEXTEDIT)
        s2r.addWidget(self.txt_product)

        hint_lbl = QLabel("📌 전략 힌트:")
        hint_lbl.setStyleSheet(f"color:#f5a623;font-size:{FS_BODY};margin-top:4px;")
        s2r.addWidget(hint_lbl)

        self.lbl_hint = QLabel("전략을 선택하면 리스크 힌트가 표시됩니다.")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(
            f"background:#1e1a0e;color:#f5c842;"
            f"border:1px solid #6a4a00;border-radius:4px;"
            f"padding:8px;font-size:{FS_HINT};min-height:46px;"
        )
        s2r.addWidget(self.lbl_hint)
        s2.addLayout(s2r)
        self._lay.addLayout(s2)
        self._lay.addWidget(hline())

    # ── ③ 리스크 관리 ────────────────────────────────────────
    def _build_section3(self):
        self._lay.addWidget(section_label("③ 리스크 관리"))
        s3 = QHBoxLayout()
        s3.setSpacing(12)

        s3l = QVBoxLayout()
        s3l.addWidget(field_label("어려운 구간 / 심리적 저항선:"))
        self.txt_difficult = QTextEdit()
        self.txt_difficult.setPlaceholderText(
            "예) SPX 5210 돌파 시 → 콜 스프레드 숏 레그 위험\n"
            "    심리적 손실 한도: -$500"
        )
        self.txt_difficult.setMinimumHeight(100)
        self.txt_difficult.setMaximumHeight(150)
        self.txt_difficult.setStyleSheet(
            f"background:#2a1a1a;color:#faa;border:1px solid #554;"
            f"border-radius:4px;padding:6px;font-size:{FS_BODY};"
        )
        s3l.addWidget(self.txt_difficult)
        s3.addLayout(s3l)

        s3r = QVBoxLayout()
        s3r.addWidget(field_label("대응 방안:"))
        self.txt_response = QTextEdit()
        self.txt_response.setPlaceholderText(
            "예) 5210 돌파 확인 시 → 즉시 롤업 또는 청산\n"
            "    VIX 18+ 시 → 포지션 50% 축소"
        )
        self.txt_response.setMinimumHeight(100)
        self.txt_response.setMaximumHeight(150)
        self.txt_response.setStyleSheet(
            f"background:#1a2a1a;color:#afa;border:1px solid #455;"
            f"border-radius:4px;padding:6px;font-size:{FS_BODY};"
        )
        s3r.addWidget(self.txt_response)
        s3.addLayout(s3r)
        self._lay.addLayout(s3)
        self._lay.addWidget(hline())

    # ── ④ 차트 이미지 ────────────────────────────────────────
    def _build_section4(self):
        self._lay.addWidget(section_label("④ 차트 이미지"))
        btn_row = QHBoxLayout()

        self.btn_chart_pick = QPushButton("📂  이미지 선택")
        self.btn_chart_pick.setStyleSheet(
            f"background:#1a3a5a;color:#7df;border-radius:4px;"
            f"padding:7px 14px;font-size:{FS_BODY};"
        )
        btn_row.addWidget(self.btn_chart_pick)

        self.btn_chart_clear = QPushButton("✕  제거")
        self.btn_chart_clear.setStyleSheet(
            f"background:#3a1a1a;color:#faa;border-radius:4px;"
            f"padding:7px 14px;font-size:{FS_BODY};"
        )
        btn_row.addWidget(self.btn_chart_clear)

        self.lbl_chart_path = QLabel("(선택된 이미지 없음)")
        self.lbl_chart_path.setStyleSheet(f"color:#666;font-size:{FS_SMALL};")
        btn_row.addWidget(self.lbl_chart_path, 1)
        self._lay.addLayout(btn_row)

        self.lbl_chart_img = QLabel()
        self.lbl_chart_img.setAlignment(Qt.AlignCenter)
        self.lbl_chart_img.setStyleSheet(
            f"background:#0d0d1a;border:1px solid #333;border-radius:4px;"
            f"min-height:210px;max-height:420px;color:#555;font-size:{FS_BODY};"
        )
        self.lbl_chart_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lbl_chart_img.setText("차트 이미지를 선택하세요")
        self._lay.addWidget(self.lbl_chart_img)
        self._lay.addWidget(hline())

    # ── ⑤ 기타 메모 ─────────────────────────────────────────
    def _build_section5(self):
        self._lay.addWidget(section_label("⑤ 기타 메모"))
        self.txt_memo = QTextEdit()
        self.txt_memo.setPlaceholderText("기타 메모, 사후 복기, 교훈 등...")
        self.txt_memo.setMinimumHeight(88)
        self.txt_memo.setMaximumHeight(150)
        self.txt_memo.setStyleSheet(STYLE_TEXTEDIT)
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
            f"background:#1a5276;color:#fff;border-radius:6px;"
            f"font-size:16px;font-weight:bold;border:1px solid #3a82b6;"
        )
        row.addWidget(self.btn_save)

        self.btn_save_new = QPushButton("＋  저장 후 새 복기")
        self.btn_save_new.setFixedWidth(200)
        self.btn_save_new.setFixedHeight(42)
        self.btn_save_new.setStyleSheet(
            f"background:#1a4030;color:#afa;border-radius:6px;"
            f"font-size:15px;font-weight:bold;border:1px solid #3a9060;"
        )
        row.addWidget(self.btn_save_new)
        row.addStretch()
        self._lay.addLayout(row)