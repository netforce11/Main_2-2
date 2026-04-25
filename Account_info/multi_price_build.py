"""
multi_price_build.py — MultiPriceGrid._build() UI 구성 로직
tab_multi_price.py 에서 import 하여 위임 호출.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui  import QFont, QColor, QBrush
from core import make_table, tbl_set, SAVE_DIR


def build_multi_price(self) -> None:
    """MultiPriceGrid 전체 UI 구성. self 에 위젯 속성 주입."""
    # ── [0-1, 0-1] 관심종목 (좁게, 2열 × 2행) ──────────────
    gb_w = QGroupBox("관심종목")
    vw   = QVBoxLayout(gb_w)
    self.watch = QListWidget()
    self.watch.addItems([
        "SPX","SPXW","NDX","QQQ","SPY",
        "AAPL","TSLA","NVDA","AMZN","MSFT"])
    self.watch.itemClicked.connect(self._on_watch_click)
    vw.addWidget(self.watch)
    wa = QHBoxLayout()
    ba = QPushButton("추가"); bd = QPushButton("삭제")
    ba.setFixedHeight(22); bd.setFixedHeight(22)
    ba.clicked.connect(self._w_add); bd.clicked.connect(self._w_del)
    wa.addWidget(ba); wa.addWidget(bd)
    vw.addLayout(wa)
    # 관심종목은 슬롯 수평 스플리터 앞에 별도 배치 불가 → 슬롯1 상단에 통합
    # (슬롯 수평 스플리터가 행0 전체를 차지하므로 watchlist는 별도 탭으로 이동)
    # 관심종목을 별도 좁은 위젯으로 왼쪽에 배치 (행 0-1, 별도 GridTab 셀)
    self.add(gb_w, 1, 0, 1, 1)   # 행1 좁게

    # ── 슬롯 스플리터 스타일 ─────────────────────────────────
    _sh = ("QSplitter::handle:horizontal{background:#5a5a9a;border-left:1px solid #00aaff;border-right:1px solid #00aaff;margin:4px 0;}QSplitter::handle:horizontal:hover{background:#5dade2;border-left:1px solid #00e676;border-right:1px solid #00e676;}QSplitter::handle:vertical{background:#5a5a9a;border-top:1px solid #00aaff;border-bottom:1px solid #00aaff;margin:0 4px;}QSplitter::handle:vertical:hover{background:#5dade2;border-top:1px solid #00e676;border-bottom:1px solid #00e676;}")

    # ── 슬롯 3개 + 스플리터 (가로로 나란히, row0 전체) ──────
    # 슬롯 너비: 3열, 3열, 4열 → 단일 수평 스플리터로 묶어 행0 전체 차지
    self.slot_w = []
    self._slot_splitters = []   # 각 슬롯 내부 수직 스플리터

    # 전체 3슬롯을 하나의 수평 스플리터로 묶기
    self._slots_hsplit = QSplitter(Qt.Horizontal)
    self._slots_hsplit.setHandleWidth(5)
    self._slots_hsplit.setStyleSheet(_sh)
    self._slots_hsplit.setChildrenCollapsible(False)

    for i in range(self.SLOTS):
        gb = QGroupBox(f"슬롯 {i+1}")
        # 슬롯 내부: 수직 스플리터 (현재가 패널 | 상세 테이블)
        v_spl = QSplitter(Qt.Vertical)
        v_spl.setHandleWidth(5)
        v_spl.setStyleSheet(_sh)
        v_spl.setChildrenCollapsible(False)

        # ── 상단 패널: 심볼 + 현재가 + 입력 ──────────────────
        top_w = QWidget(); top_v = QVBoxLayout(top_w)
        top_v.setSpacing(3); top_v.setContentsMargins(4,4,4,4)

        lsym = QLabel("―")
        lsym.setFont(QFont("Arial", 12, QFont.Bold))
        lsym.setStyleSheet("color:#ffd700;border:none;")
        lsym.setAlignment(Qt.AlignCenter)

        lprice = QLabel("현재가: ―")
        lprice.setFont(QFont("Arial", 22, QFont.Bold))
        lprice.setAlignment(Qt.AlignCenter)
        lprice.setStyleSheet(
            "color:#00ff88;background:#07070f;"
            "border-radius:6px;padding:6px;border:1px solid #1e2050;")
        lprice.setMinimumHeight(54)

        sym_in = QLineEdit()
        sym_in.setPlaceholderText(f"종목 입력 (슬롯{i+1})")
        sym_in.setFixedHeight(24)
        btn_load = QPushButton("조회")
        btn_load.setFixedHeight(24); btn_load.setFixedWidth(48)
        btn_load.clicked.connect(lambda _, idx=i: self._load_from_input(idx))
        sym_in.returnPressed.connect(lambda idx=i: self._load_from_input(idx))
        inp_row = QHBoxLayout(); inp_row.setContentsMargins(0,0,0,0)
        inp_row.addWidget(sym_in); inp_row.addWidget(btn_load)

        top_v.addWidget(lsym)
        top_v.addWidget(lprice)
        top_v.addLayout(inp_row)
        v_spl.addWidget(top_w)

        # ── 하단 패널: 상세 테이블 ────────────────────────────
        tbl = make_table(["항목","값"], 0)
        for kk in ["체결가","거래량","Delta","Gamma","Theta","전일종가"]:
            r2 = tbl.rowCount(); tbl.insertRow(r2)
            tbl_set(tbl, r2, 0, kk); tbl_set(tbl, r2, 1, "―")
        v_spl.addWidget(tbl)
        v_spl.setSizes([120, 200])

        # gb 레이아웃에 수직 스플리터 넣기
        gb_v = QVBoxLayout(gb); gb_v.setContentsMargins(2,2,2,2)
        gb_v.addWidget(v_spl)

        self._slot_splitters.append(v_spl)
        self.slot_w.append({
            "sym": lsym, "price": lprice, "tbl": tbl, "input": sym_in})
        self._slots_hsplit.addWidget(gb)

    self._slots_hsplit.setSizes([400, 400, 400])
    self.add(self._slots_hsplit, 0, 0, 1, 12)  # 행0 전체 12열

    # ══════════════════════════════════════════════════════
    # 하단 수평 스플리터: 트리거 영역 | 파일·사운드 패널
    # ══════════════════════════════════════════════════════
    self._bot_hsplit = QSplitter(Qt.Horizontal)
    self._bot_hsplit.setHandleWidth(5)
    self._bot_hsplit.setStyleSheet(_sh)
    self._bot_hsplit.setChildrenCollapsible(False)

    # ── 좌측: 트리거 등록 + 목록 + 로그 (수직 스플리터) ─────
    self._bot_left_vsplit = QSplitter(Qt.Vertical)
    self._bot_left_vsplit.setHandleWidth(5)
    self._bot_left_vsplit.setStyleSheet(_sh)
    self._bot_left_vsplit.setChildrenCollapsible(False)

    # 트리거 등록 패널
    gb_trg = QGroupBox("조건 트리거 등록")
    gl = QGridLayout(gb_trg); gl.setSpacing(4)
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
    self._bot_left_vsplit.addWidget(gb_trg)

    # 등록된 트리거 목록
    gb3 = QGroupBox("등록된 트리거  (더블클릭→수정 / Del→삭제)")
    v3  = QVBoxLayout(gb3)
    self.tbl_trg = QTableWidget(0, 4)
    self.tbl_trg.setHorizontalHeaderLabels(["가격조건","시간조건","설명","상태"])
    self.tbl_trg.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.tbl_trg.verticalHeader().setVisible(False)
    self.tbl_trg.setAlternatingRowColors(True)
    self.tbl_trg.setStyleSheet("QTableWidget{alternate-background-color:#0c0c20;}")
    self.tbl_trg.cellDoubleClicked.connect(self._on_trg_dbl)
    self.tbl_trg.keyPressEvent = self._trg_keypress
    v3.addWidget(self.tbl_trg)
    tr = QHBoxLayout()
    btn_del = QPushButton("선택 삭제"); btn_del.clicked.connect(self._del_trigger)
    btn_clr = QPushButton("전체 초기화"); btn_clr.clicked.connect(self._clr_triggers)
    tr.addWidget(btn_del); tr.addWidget(btn_clr); tr.addStretch()
    v3.addLayout(tr)
    gb3.setMinimumHeight(80)
    self._bot_left_vsplit.addWidget(gb3)

    # 트리거 이벤트 로그
    gb4 = QGroupBox("트리거 이벤트 로그")
    v4  = QVBoxLayout(gb4)
    self.trg_log = QTextEdit(); self.trg_log.setReadOnly(True)
    v4.addWidget(self.trg_log)
    gb4.setMinimumHeight(60)
    self._bot_left_vsplit.addWidget(gb4)
    self._bot_left_vsplit.setSizes([90, 150, 120])

    self._bot_hsplit.addWidget(self._bot_left_vsplit)

    # ── 우측: 파일 저장 + 사운드 설정 (수직 스플리터) ───────
    self._bot_right_vsplit = QSplitter(Qt.Vertical)
    self._bot_right_vsplit.setHandleWidth(5)
    self._bot_right_vsplit.setStyleSheet(_sh)
    self._bot_right_vsplit.setChildrenCollapsible(False)

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
    self._bot_right_vsplit.addWidget(gb5)

    # 🔊 사운드 설정 (트리거 발동 알람)
    gb_snd = QGroupBox("🔊 알람 사운드 설정")
    v_snd  = QVBoxLayout(gb_snd); v_snd.setSpacing(6)

    snd_row1 = QHBoxLayout()
    lbl_snd = QLabel("선택 파일:")
    lbl_snd.setStyleSheet("color:#aaa;font-size:11px;border:none;")
    self.lbl_snd_file = QLabel("기본 비프음")
    self.lbl_snd_file.setStyleSheet(
        "color:#ffd700;font-size:11px;border:1px solid #333;"
        "border-radius:3px;padding:1px 4px;background:#0a0a1e;")
    self.lbl_snd_file.setWordWrap(False)
    self.lbl_snd_file.setMaximumWidth(160)
    snd_row1.addWidget(lbl_snd)
    snd_row1.addWidget(self.lbl_snd_file, 1)
    v_snd.addLayout(snd_row1)

    snd_row2 = QHBoxLayout(); snd_row2.setSpacing(4)
    btn_snd_pick = QPushButton("📂 파일 선택")
    btn_snd_pick.setStyleSheet(
        "background:#1a3a6b;color:#90caf9;font-size:10px;padding:3px 6px;")
    btn_snd_pick.clicked.connect(self._pick_alert_sound)
    btn_snd_test = QPushButton("▶ 테스트")
    btn_snd_test.setStyleSheet(
        "background:#2d2d2d;color:#ffd700;font-size:10px;padding:3px 6px;")
    btn_snd_test.clicked.connect(self._play_alert_sound)
    btn_snd_clr = QPushButton("✕ 초기화")
    btn_snd_clr.setStyleSheet(
        "background:#4a1a1a;color:#ff8888;font-size:10px;padding:3px 6px;")
    btn_snd_clr.clicked.connect(self._clear_alert_sound)
    snd_row2.addWidget(btn_snd_pick)
    snd_row2.addWidget(btn_snd_test)
    snd_row2.addWidget(btn_snd_clr)
    v_snd.addLayout(snd_row2)

    # 기본값으로 저장 체크박스
    self.chk_snd_default = QCheckBox("이 파일을 기본값으로 저장")
    self.chk_snd_default.setStyleSheet("color:#90caf9;font-size:10px;")
    self.chk_snd_default.setChecked(True)
    v_snd.addWidget(self.chk_snd_default)
    v_snd.addStretch()

    gb_snd.setMinimumHeight(80)
    self._bot_right_vsplit.addWidget(gb_snd)
    self._bot_right_vsplit.setSizes([120, 140])
    self._bot_right_vsplit.setMaximumWidth(280)

    self._bot_hsplit.addWidget(self._bot_right_vsplit)
    self._bot_hsplit.setSizes([800, 220])

    self.add(self._bot_hsplit, 1, 1, 3, 11)

