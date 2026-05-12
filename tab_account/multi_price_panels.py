"""
multi_price_panels.py — MultiPriceGrid 하단 패널 UI 빌드
════════════════════════════════════════════════════════
포함 내용:
  - MultiPricePanelsMixin
      _build_trigger_panel()   트리거 등록 + 목록 + 로그 패널
      _build_file_sound_panel() 파일 저장 + 사운드 설정 패널
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox, QTextEdit,
    QTableWidget, QHeaderView, QSplitter, QCheckBox,
)
from PyQt5.QtCore import Qt

from tab_account.multi_price_slots import _SPLITTER_STYLE


class MultiPricePanelsMixin:
    """하단 트리거·파일·사운드 패널 UI 빌드 Mixin."""

    def _build_trigger_panel(self) -> QSplitter:
        """트리거 등록 + 목록 + 로그를 묶은 수직 스플리터 반환."""
        vsplit = QSplitter(Qt.Vertical)
        vsplit.setHandleWidth(5)
        vsplit.setStyleSheet(_SPLITTER_STYLE)
        vsplit.setChildrenCollapsible(False)

        # 트리거 등록 패널
        gb_trg = QGroupBox("조건 트리거 등록")
        gl     = QGridLayout(gb_trg); gl.setSpacing(4)
        gl.addWidget(QLabel("가격 조건 (≤):"), 0, 0)
        self.trg_price = QLineEdit(); self.trg_price.setPlaceholderText("예: 5.00")
        gl.addWidget(self.trg_price, 0, 1)
        gl.addWidget(QLabel("시간 조건 (≥):"), 0, 2)
        self.trg_time = QLineEdit(); self.trg_time.setPlaceholderText("HH:MM:SS")
        gl.addWidget(self.trg_time, 0, 3)
        gl.addWidget(QLabel("설명:"), 1, 0)
        self.trg_desc = QLineEdit(); self.trg_desc.setPlaceholderText("예: 09:45 급락 감지")
        gl.addWidget(self.trg_desc, 1, 1, 1, 2)
        btn_add = QPushButton("▶ 트리거 등록")
        btn_add.setStyleSheet("background:#1a3a6b;font-weight:bold;")
        btn_add.clicked.connect(self._add_trigger)
        gl.addWidget(btn_add, 1, 3)
        gb_trg.setMinimumHeight(80)
        vsplit.addWidget(gb_trg)

        # 등록된 트리거 목록
        gb3 = QGroupBox("등록된 트리거  (더블클릭→수정 / Del→삭제)")
        v3  = QVBoxLayout(gb3)
        self.tbl_trg = QTableWidget(0, 4)
        self.tbl_trg.setHorizontalHeaderLabels(["가격조건", "시간조건", "설명", "상태"])
        self.tbl_trg.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_trg.verticalHeader().setVisible(False)
        self.tbl_trg.setAlternatingRowColors(True)
        self.tbl_trg.setStyleSheet(
            "QTableWidget{alternate-background-color:#0c0c20;}")
        self.tbl_trg.cellDoubleClicked.connect(self._on_trg_dbl)
        self.tbl_trg.keyPressEvent = self._trg_keypress
        v3.addWidget(self.tbl_trg)
        tr = QHBoxLayout()
        btn_del = QPushButton("선택 삭제"); btn_del.clicked.connect(self._del_trigger)
        btn_clr = QPushButton("전체 초기화"); btn_clr.clicked.connect(self._clr_triggers)
        tr.addWidget(btn_del); tr.addWidget(btn_clr); tr.addStretch()
        v3.addLayout(tr)
        gb3.setMinimumHeight(80)
        vsplit.addWidget(gb3)

        # 트리거 이벤트 로그
        gb4 = QGroupBox("트리거 이벤트 로그")
        v4  = QVBoxLayout(gb4)
        self.trg_log = QTextEdit(); self.trg_log.setReadOnly(True)
        v4.addWidget(self.trg_log)
        gb4.setMinimumHeight(60)
        vsplit.addWidget(gb4)
        vsplit.setSizes([90, 150, 120])
        self._bot_left_vsplit = vsplit
        return vsplit

    def _build_file_sound_panel(self) -> QSplitter:
        """파일 저장 + 사운드 설정을 묶은 수직 스플리터 반환."""
        vsplit = QSplitter(Qt.Vertical)
        vsplit.setHandleWidth(5)
        vsplit.setStyleSheet(_SPLITTER_STYLE)
        vsplit.setChildrenCollapsible(False)

        # 파일 저장/불러오기
        gb5 = QGroupBox("파일")
        v5  = QVBoxLayout(gb5); v5.setSpacing(6)
        btn_sv = QPushButton("💾 로그 저장"); btn_sv.clicked.connect(self._save_log)
        btn_ld = QPushButton("📂 로그 불러오기"); btn_ld.clicked.connect(self._load_log)
        self.lbl_file = QLabel("파일: ―")
        self.lbl_file.setStyleSheet("color:#555;font-size:11px;border:none;")
        self.lbl_file.setWordWrap(True)
        for w in (btn_sv, btn_ld, self.lbl_file): v5.addWidget(w)
        v5.addStretch()
        gb5.setMinimumHeight(80)
        vsplit.addWidget(gb5)

        # 사운드 설정
        gb_snd  = QGroupBox("🔊 알람 사운드 설정")
        v_snd   = QVBoxLayout(gb_snd); v_snd.setSpacing(6)
        snd_row1 = QHBoxLayout()
        lbl_snd  = QLabel("선택 파일:")
        lbl_snd.setStyleSheet("color:#aaa;font-size:11px;border:none;")
        self.lbl_snd_file = QLabel("기본 비프음")
        self.lbl_snd_file.setStyleSheet(
            "color:#ffd700;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:1px 4px;background:#0a0a1e;")
        self.lbl_snd_file.setWordWrap(False)
        self.lbl_snd_file.setMaximumWidth(160)
        snd_row1.addWidget(lbl_snd); snd_row1.addWidget(self.lbl_snd_file, 1)
        v_snd.addLayout(snd_row1)

        snd_row2 = QHBoxLayout(); snd_row2.setSpacing(4)
        for lbl_txt, slot, style in [
            ("📂 파일 선택", self._pick_alert_sound,
             "background:#1a3a6b;color:#90caf9;font-size:10px;padding:3px 6px;"),
            ("▶ 테스트",     self._play_alert_sound,
             "background:#2d2d2d;color:#ffd700;font-size:10px;padding:3px 6px;"),
            ("✕ 초기화",    self._clear_alert_sound,
             "background:#4a1a1a;color:#ff8888;font-size:10px;padding:3px 6px;"),
        ]:
            btn = QPushButton(lbl_txt); btn.setStyleSheet(style)
            btn.clicked.connect(slot); snd_row2.addWidget(btn)
        v_snd.addLayout(snd_row2)

        self.chk_snd_default = QCheckBox("이 파일을 기본값으로 저장")
        self.chk_snd_default.setStyleSheet("color:#90caf9;font-size:10px;")
        self.chk_snd_default.setChecked(True)
        v_snd.addWidget(self.chk_snd_default)
        v_snd.addStretch()
        gb_snd.setMinimumHeight(80)
        vsplit.addWidget(gb_snd)
        vsplit.setSizes([120, 140])
        vsplit.setMaximumWidth(280)
        self._bot_right_vsplit = vsplit
        return vsplit
