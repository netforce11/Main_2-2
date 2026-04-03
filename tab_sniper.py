"""
tab_sniper.py — 스나이퍼 주문 탭  v6.2
════════════════════════════════════════════════════════════════
  Tab 3  SniperGrid     스나이퍼 주문
════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QTextEdit, QRadioButton,
    QButtonGroup, QMessageBox, QAbstractItemView, QTableWidgetItem,
    QSpinBox, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

from core import (
    bridge, router, GridTab, make_table, tbl_set, ts,
    SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM,
    REQ_UND, REQ_CALL, REQ_PUT, REQ_SNIPER, N_STRIKES, ALERT_COOLDOWN,
    build_expiry_list, make_opt_contract, make_und_contract,
    save_json, load_json, SAVE_DIR,
    auto_mdt,
)
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QBrush, QColor


def _mk(text, color=None):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    if color:
        it.setForeground(QBrush(QColor(color)))
    return it

class SniperGrid(QWidget):
    """
    레이아웃: QSplitter 기반 (모든 패널 개별 조절 가능)
    ┌──────────────────────────────────────────────────────┐
    │  _top_splitter (수평)                                │
    │  ├── 옵션 타겟         (좌)                          │
    │  ├── 스나이퍼 설정     (중앙)                        │
    │  ├── 활성 스나이퍼     (중앙우)                      │
    │  └── 원클릭 주문       (우)                          │
    ├──────────────────────────────────────────────────────┤
    │  _bot_splitter (수평)                                │
    │  ├── _bot_left_splitter (수평)                       │
    │  │   ├── 정정 스나이퍼                               │
    │  │   ├── 일반 주문창 (신규)                          │
    │  │   └── 지수 현재가                                 │
    │  └── 스나이퍼 로그                                   │
    ├──────────────────────────────────────────────────────┤
    │  전체 알림/체결 로그 (하단 고정)                      │
    └──────────────────────────────────────────────────────┘
    """
    MULTIPLIER = 100

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.buying_power   = 0.0
        self.active_snipers = {}
        self.amend_snipers  = {}
        self.sniper_rid     = REQ_SNIPER

        # 콜-풋탭 자동 동기화 타이머 (3초)
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(3000)
        self._sync_timer.timeout.connect(self._auto_sync)
        self._sync_timer.start()

        # 시간 조건 체크 타이머 (5초)
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(5000)
        self._time_timer.timeout.connect(self._check_time_conditions)
        self._time_timer.start()

        self._build()
        self._connect_signals()

    # ─────────────────────────────────────────────────────────
    def _spl_style(self):
        return (
            "QSplitter::handle:horizontal{"
            "  background:#5a5a9a;"
            "  border-left:1px solid #00aaff;"
            "  border-right:1px solid #00aaff;"
            "  margin:4px 0;"
            "}"
            "QSplitter::handle:horizontal:hover{"
            "  background:#5dade2;"
            "  border-left:1px solid #00e676;"
            "  border-right:1px solid #00e676;"
            "}"
            "QSplitter::handle:vertical{"
            "  background:#5a5a9a;"
            "  border-top:1px solid #00aaff;"
            "  border-bottom:1px solid #00aaff;"
            "  margin:0 4px;"
            "}"
            "QSplitter::handle:vertical:hover{"
            "  background:#5dade2;"
            "  border-top:1px solid #00e676;"
            "  border-bottom:1px solid #00e676;"
            "}"
        )

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        sty = self._spl_style()

        # ══════════════════════════════════════════════════════
        # 상단 QSplitter (수평): 옵션타겟 | 스나이퍼설정 | 활성스나이퍼 | 원클릭
        # ══════════════════════════════════════════════════════
        self._top_splitter = QSplitter(Qt.Horizontal)
        self._top_splitter.setHandleWidth(4)
        self._top_splitter.setStyleSheet(sty)
        self._top_splitter.setChildrenCollapsible(False)

        # ── 옵션 타겟 ─────────────────────────────────────────
        gb1 = QGroupBox("1. 옵션 타겟  (콜-풋 탭 자동 연동)")
        v1  = QVBoxLayout(gb1)
        info_row = QHBoxLayout()
        self.lbl_sym = QLabel("종목: ―  |  현재가: ―")
        self.lbl_sym.setStyleSheet("color:#ffd700;font-weight:bold;border:none;")
        btn_q = QPushButton("?"); btn_q.setFixedWidth(24); btn_q.setFixedHeight(22)
        btn_q.setToolTip("기능 안내")
        btn_q.clicked.connect(self._show_target_help)
        btn_manual = QPushButton("↺ 즉시 동기화")
        btn_manual.setFixedHeight(22)
        btn_manual.clicked.connect(self._load_from_main)
        info_row.addWidget(self.lbl_sym); info_row.addStretch()
        info_row.addWidget(btn_manual); info_row.addWidget(btn_q)
        v1.addLayout(info_row)
        self.tbl_opt = make_table(["C/P", "행사가", "현재가"])
        self.tbl_opt.setMinimumHeight(180)
        self.tbl_opt.cellClicked.connect(self._on_opt_click)
        v1.addWidget(self.tbl_opt)
        gb1.setMinimumWidth(160)
        self._top_splitter.addWidget(gb1)

        # ── 스나이퍼 설정 ─────────────────────────────────────
        gb2 = QGroupBox("2. 스나이퍼 설정")
        gl  = QGridLayout(gb2); gl.setSpacing(4)

        def row(label, widget, r):
            gl.addWidget(QLabel(label), r, 0)
            gl.addWidget(widget, r, 1)

        self.val_strike = QLineEdit(); self.val_strike.setReadOnly(True)
        self.val_type   = QLineEdit(); self.val_type.setReadOnly(True)
        self.in_prem    = QLineEdit(); self.in_prem.setPlaceholderText("예: 1.50")
        self.in_prem.setStyleSheet("color:#ffd700;font-weight:bold;font-size:14px;")
        self.in_prem.textChanged.connect(self._calc_qty)
        self.in_time = QLineEdit(); self.in_time.setPlaceholderText("HH:MM")
        self.in_dur  = QLineEdit("1")
        sw = QWidget(); sh = QHBoxLayout(sw); sh.setContentsMargins(0,0,0,0)
        self.in_sell = QLineEdit(); self.in_sell.setPlaceholderText("값")
        self.radio_sell_price = QRadioButton("$")
        self.radio_sell_pct   = QRadioButton("%")
        self.radio_sell_price.setChecked(True)
        sg = QButtonGroup(self)
        sg.addButton(self.radio_sell_price); sg.addButton(self.radio_sell_pct)
        sh.addWidget(self.in_sell)
        sh.addWidget(self.radio_sell_price); sh.addWidget(self.radio_sell_pct)

        row("행사가:",   self.val_strike, 0)
        row("종류:",     self.val_type,   1)
        row("목표가($):", self.in_prem,   2)
        row("시각(ET):", self.in_time,    3)
        row("유효(분):", self.in_dur,     4)
        row("매도목표:", sw,              5)

        self.lbl_funds = QLabel("$0.00")
        self.lbl_funds.setStyleSheet("color:#00cfff;font-weight:bold;border:none;")
        self.lbl_max   = QLabel("0 계약")
        self.lbl_max.setStyleSheet("color:#00ff88;font-weight:bold;font-size:14px;border:none;")
        row("가용금액:", self.lbl_funds, 6)
        row("최대수량:", self.lbl_max,   7)

        # 수량 입력 + M/H/Q 버튼
        qw = QWidget(); qh = QHBoxLayout(qw); qh.setContentsMargins(0,0,0,0)
        self.in_qty = QLineEdit("1"); self.in_qty.setFixedWidth(45)
        _S = ("QPushButton{background:#2d2d5e;color:#ffd700;"
              "border:1px solid #4a4a8a;border-radius:3px;"
              "font-size:11px;font-weight:bold;}"
              "QPushButton:hover{background:#3d4d6e;}")
        for lbl, mode in [("M","max"),("H","half"),("Q","qtr")]:
            b = QPushButton(lbl); b.setFixedWidth(26); b.setFixedHeight(24)
            b.setStyleSheet(_S)
            b.clicked.connect(lambda _, m=mode: self._set_qty(m))
            qh.addWidget(b)
        qh.insertWidget(0, self.in_qty)
        gl.addWidget(QLabel("수량:"), 8, 0); gl.addWidget(qw, 8, 1)

        self.btn_sniper = QPushButton("👁 스나이퍼 감시 시작")
        self.btn_sniper.setStyleSheet(
            "background:#1a6b3c;font-size:12px;font-weight:bold;padding:7px;")
        self.btn_sniper.clicked.connect(self._start_sniper)
        gl.addWidget(self.btn_sniper, 9, 0, 1, 2)
        gb2.setMinimumWidth(160)
        self._top_splitter.addWidget(gb2)

        # ── 활성 스나이퍼 ─────────────────────────────────────
        gb3 = QGroupBox("3. 활성 스나이퍼  (더블클릭=취소)")
        v3  = QVBoxLayout(gb3)
        self.tbl_snipe = make_table(["행사가","목표가","현재가","상태","매도목표"])
        self.tbl_snipe.cellDoubleClicked.connect(self._on_snipe_dbl)
        v3.addWidget(self.tbl_snipe)
        btn_clr = QPushButton("전체 취소"); btn_clr.clicked.connect(self._clear_snipers)
        v3.addWidget(btn_clr)
        gb3.setMinimumWidth(160)
        self._top_splitter.addWidget(gb3)

        # ── 원클릭 주문 ───────────────────────────────────────
        gb4 = QGroupBox("원클릭 주문")
        v4  = QVBoxLayout(gb4); v4.setSpacing(6)
        for txt, style, fn, tip in [
            ("🚨 PANIC SELL",
             "background:#8b0000;color:#fff;font-weight:bold;padding:8px;",
             self._panic_sell,
             "모든 0DTE 포지션을 즉시 시장가 청산"),
            ("⚡ ATM Straddle",
             "background:#1a3a6b;color:#fff;font-weight:bold;padding:6px;",
             self._atm_straddle,
             "ATM 콜+풋 각 1계약 즉시 매수"),
            ("🎯 LMT $0.10",
             "background:#1a6b3c;color:#fff;font-weight:bold;padding:6px;",
             self._lmt_sniper,
             "선택 행사가에 $0.10 지정가 매수"),
        ]:
            hl = QHBoxLayout()
            btn = QPushButton(txt); btn.setStyleSheet(style); btn.clicked.connect(fn)
            bh  = QPushButton("?"); bh.setFixedWidth(22); bh.setFixedHeight(26)
            bh.setToolTip(tip)
            bh.clicked.connect(lambda _, t=tip: QMessageBox.information(self,"기능 설명",t))
            hl.addWidget(btn, 1); hl.addWidget(bh)
            v4.addLayout(hl)
        v4.addStretch()
        gb4.setMinimumWidth(120)
        self._top_splitter.addWidget(gb4)

        self._top_splitter.setSizes([250, 220, 250, 160])
        root.addWidget(self._top_splitter, 3)

        # ══════════════════════════════════════════════════════
        # 중단 QSplitter (수평): 하단 좌측 묶음 | 스나이퍼 로그
        # ══════════════════════════════════════════════════════
        self._mid_splitter = QSplitter(Qt.Horizontal)
        self._mid_splitter.setHandleWidth(4)
        self._mid_splitter.setStyleSheet(sty)
        self._mid_splitter.setChildrenCollapsible(False)

        # ── 하단 좌측: 정정 스나이퍼 | 일반 주문창 | 지수 현재가 (수평 스플리터)
        self._bot_left_splitter = QSplitter(Qt.Horizontal)
        self._bot_left_splitter.setHandleWidth(4)
        self._bot_left_splitter.setStyleSheet(sty)
        self._bot_left_splitter.setChildrenCollapsible(False)

        # 정정 스나이퍼
        gb5 = QGroupBox("4. 정정 스나이퍼")
        v5  = QVBoxLayout(gb5)
        info_h = QHBoxLayout()
        linfo = QLabel("매도 체결 → 자동 등록  |  행 클릭 후 Enter = 시장가 정정")
        linfo.setStyleSheet("color:#aaa;font-size:10px;border:none;")
        bq2 = QPushButton("?"); bq2.setFixedWidth(22)
        bq2.clicked.connect(lambda: QMessageBox.information(self,"정정 스나이퍼",
            "매도 주문이 체결되면 자동으로 이 테이블에 등록됩니다.\n"
            "행을 클릭하고 Enter 키를 누르면\n즉시 시장가 매도 정정 주문을 전송합니다."))
        info_h.addWidget(linfo); info_h.addWidget(bq2)
        v5.addLayout(info_h)
        self.tbl_amend = make_table(["OrderID","심볼","종류","수량","현재상태"])
        self.tbl_amend.keyPressEvent = self._amend_keypress
        v5.addWidget(self.tbl_amend)
        gb5.setMinimumWidth(160)
        self._bot_left_splitter.addWidget(gb5)

        # ── 일반 주문창 (신규) ────────────────────────────────
        gb_order = QGroupBox("5. 일반 주문")
        gl_order = QGridLayout(gb_order); gl_order.setSpacing(4)
        gl_order.setContentsMargins(6, 6, 6, 6)

        # 행사가 / 종류 (읽기전용 — 옵션 타겟 클릭 시 자동 입력)
        self.ord_strike = QLineEdit(); self.ord_strike.setReadOnly(True)
        self.ord_strike.setPlaceholderText("타겟 클릭")
        self.ord_type   = QLineEdit(); self.ord_type.setReadOnly(True)
        self.ord_type.setPlaceholderText("C / P")

        # 주문 유형 (지정가 / 시장가)
        ord_type_w = QWidget(); ord_type_h = QHBoxLayout(ord_type_w)
        ord_type_h.setContentsMargins(0,0,0,0); ord_type_h.setSpacing(4)
        self.radio_lmt = QRadioButton("지정가")
        self.radio_mkt = QRadioButton("시장가")
        self.radio_lmt.setChecked(True)
        ord_grp = QButtonGroup(self)
        ord_grp.addButton(self.radio_lmt); ord_grp.addButton(self.radio_mkt)
        self.radio_lmt.toggled.connect(self._on_ord_type_toggle)
        ord_type_h.addWidget(self.radio_lmt); ord_type_h.addWidget(self.radio_mkt)

        # 지정가 입력
        self.ord_price = QLineEdit(); self.ord_price.setPlaceholderText("가격 입력")
        self.ord_price.setStyleSheet("color:#ffd700;font-weight:bold;font-size:13px;")

        # 수량
        ord_qty_w = QWidget(); ord_qty_h = QHBoxLayout(ord_qty_w)
        ord_qty_h.setContentsMargins(0,0,0,0); ord_qty_h.setSpacing(3)
        self.ord_qty = QSpinBox(); self.ord_qty.setRange(1, 9999); self.ord_qty.setValue(1)
        self.ord_qty.setFixedHeight(26)
        _S2 = ("QPushButton{background:#2d2d5e;color:#ffd700;"
               "border:1px solid #4a4a8a;border-radius:3px;"
               "font-size:11px;font-weight:bold;}"
               "QPushButton:hover{background:#3d4d6e;}")
        for lbl2, val2 in [("1",1),("5",5),("10",10)]:
            bq = QPushButton(lbl2); bq.setFixedWidth(28); bq.setFixedHeight(26)
            bq.setStyleSheet(_S2)
            bq.clicked.connect(lambda _, v=val2: self.ord_qty.setValue(v))
            ord_qty_h.addWidget(bq)
        ord_qty_h.insertWidget(0, self.ord_qty)

        gl_order.addWidget(QLabel("행사가:"),  0, 0); gl_order.addWidget(self.ord_strike, 0, 1)
        gl_order.addWidget(QLabel("종류:"),    1, 0); gl_order.addWidget(self.ord_type,   1, 1)
        gl_order.addWidget(QLabel("주문:"),    2, 0); gl_order.addWidget(ord_type_w,      2, 1)
        gl_order.addWidget(QLabel("가격:"),    3, 0); gl_order.addWidget(self.ord_price,  3, 1)
        gl_order.addWidget(QLabel("수량:"),    4, 0); gl_order.addWidget(ord_qty_w,       4, 1)

        # 매수 / 매도 버튼
        btn_ord_row = QHBoxLayout()
        self.btn_buy = QPushButton("▲ 매수")
        self.btn_buy.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:14px;"
            "font-weight:bold;padding:10px;border-radius:4px;")
        self.btn_buy.clicked.connect(lambda: self._place_order("BUY"))

        self.btn_sell = QPushButton("▼ 매도")
        self.btn_sell.setStyleSheet(
            "background:#6b1a1a;color:#ff6666;font-size:14px;"
            "font-weight:bold;padding:10px;border-radius:4px;")
        self.btn_sell.clicked.connect(lambda: self._place_order("SELL"))

        btn_ord_row.addWidget(self.btn_buy, 1)
        btn_ord_row.addWidget(self.btn_sell, 1)
        gl_order.addLayout(btn_ord_row, 5, 0, 1, 2)

        # 주문 상태 라벨
        self.lbl_ord_status = QLabel("대기 중")
        self.lbl_ord_status.setAlignment(Qt.AlignCenter)
        self.lbl_ord_status.setStyleSheet(
            "color:#888;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")
        gl_order.addWidget(self.lbl_ord_status, 6, 0, 1, 2)

        gb_order.setMinimumWidth(160)
        self._bot_left_splitter.addWidget(gb_order)

        # 지수/현재가 박스
        gb6 = QGroupBox("지수 현재가")
        v6  = QVBoxLayout(gb6); v6.setSpacing(3)
        row6 = QHBoxLayout()
        self.lbl_idx_name  = QLabel("SPX")
        self.lbl_idx_name.setStyleSheet("color:#5dade2;font-weight:bold;font-size:12px;border:none;")
        self.lbl_idx_val   = QLabel("―")
        self.lbl_idx_val.setFont(QFont("Arial", 22, QFont.Bold))
        self.lbl_idx_val.setStyleSheet("color:#ffd700;border:none;")
        self.lbl_idx_chg   = QLabel("")
        self.lbl_idx_chg.setStyleSheet("color:#aaa;font-weight:bold;font-size:12px;border:none;")
        row6.addWidget(self.lbl_idx_name)
        row6.addStretch()
        row6.addWidget(self.lbl_idx_val)
        v6.addLayout(row6)
        v6.addWidget(self.lbl_idx_chg)

        # 변동률 표시 박스
        chg_row = QHBoxLayout()
        for lbl_attr, label, col in [
            ("lbl_spx","SPX","#ffd700"),
            ("lbl_ndx","NDX","#90caf9"),
            ("lbl_vix","VIX","#ff8844"),
        ]:
            box = QWidget()
            bv  = QVBoxLayout(box); bv.setContentsMargins(4,2,4,2)
            box.setStyleSheet(f"border:1px solid #333;border-radius:4px;"
                              f"background:#0a0a18;")
            lname = QLabel(label)
            lname.setStyleSheet(f"color:{col};font-size:10px;font-weight:bold;border:none;")
            lval  = QLabel("―")
            lval.setStyleSheet(f"color:{col};font-size:13px;font-weight:bold;border:none;")
            lval.setAlignment(Qt.AlignCenter)
            bv.addWidget(lname); bv.addWidget(lval)
            setattr(self, lbl_attr, lval)
            chg_row.addWidget(box)
        v6.addLayout(chg_row)
        gb6.setMinimumWidth(130)
        self._bot_left_splitter.addWidget(gb6)

        self._bot_left_splitter.setSizes([300, 200, 180])
        self._mid_splitter.addWidget(self._bot_left_splitter)

        # ── 스나이퍼 로그 ─────────────────────────────────────
        gb7 = QGroupBox("스나이퍼 로그")
        v7  = QVBoxLayout(gb7)
        self.snipe_log = QTextEdit(); self.snipe_log.setReadOnly(True)
        v7.addWidget(self.snipe_log)
        gb7.setMinimumWidth(120)
        self._mid_splitter.addWidget(gb7)

        self._mid_splitter.setSizes([700, 300])
        root.addWidget(self._mid_splitter, 2)

        # ══════════════════════════════════════════════════════
        # 하단 고정: 전체 알림/체결 로그
        # ══════════════════════════════════════════════════════
        gb8 = QGroupBox("전체 알림 / 체결 로그")
        v8  = QVBoxLayout(gb8)

        # 지수값+변동률 인라인 표시줄
        self.lbl_log_header = QLabel("SPX: ―   NDX: ―   VIX: ―   |   변동: ―")
        self.lbl_log_header.setStyleSheet(
            "background:#07070f;color:#ffd700;font-weight:bold;"
            "font-size:11px;padding:2px 6px;border:none;"
            "border-bottom:1px solid #1e2050;")
        self.lbl_log_header.setFixedHeight(20)
        v8.addWidget(self.lbl_log_header)

        self.all_log = QTextEdit(); self.all_log.setReadOnly(True)
        fm = self.all_log.fontMetrics()
        self.all_log.setMaximumHeight(fm.height() * 4 + 14)  # 4줄
        v8.addWidget(self.all_log)
        root.addWidget(gb8)

        # ── 스나이퍼 탭 기본 폰트 23px ────────────────────────
        _sniper_font = QFont(); _sniper_font.setPointSize(23)
        self.setFont(_sniper_font)

    # ─────────────────────────────────────────────────────────
    # 일반 주문 헬퍼
    # ─────────────────────────────────────────────────────────
    def _on_ord_type_toggle(self, checked):
        """지정가/시장가 전환 — 지정가 선택 시 가격 입력 활성화."""
        self.ord_price.setEnabled(self.radio_lmt.isChecked())
        if not self.radio_lmt.isChecked():
            self.ord_price.setStyleSheet(
                "color:#666;font-weight:bold;font-size:13px;background:#111;")
        else:
            self.ord_price.setStyleSheet(
                "color:#ffd700;font-weight:bold;font-size:13px;")

    def _on_opt_click_ord(self, strike, opt_type):
        """옵션 타겟 클릭 시 일반 주문창 행사가/종류 자동 입력."""
        self.ord_strike.setText(strike)
        self.ord_type.setText(opt_type)

    def _place_order(self, action):
        """일반 주문 실행."""
        strike   = self.ord_strike.text().strip()
        opt_type = self.ord_type.text().strip()
        qty      = self.ord_qty.value()
        is_lmt   = self.radio_lmt.isChecked()
        price_txt = self.ord_price.text().strip()

        if not strike or not opt_type:
            QMessageBox.warning(self, "입력 오류",
                "옵션 타겟 테이블에서 행을 먼저 클릭하세요."); return
        if is_lmt and not price_txt:
            QMessageBox.warning(self, "입력 오류", "지정가를 입력하세요."); return

        order_type = "LMT" if is_lmt else "MKT"
        try:
            price = float(price_txt) if is_lmt else 0.0
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "유효한 가격을 입력하세요."); return

        action_kr = "매수" if action == "BUY" else "매도"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"
        msg = (f"{action_kr} {order_type}  "
               f"{strike}{opt_type}  {qty}계약  {price_disp}")

        ret = QMessageBox.question(self, f"주문 확인 — {action_kr}",
            f"⚠ 아래 주문을 전송합니다.\n\n{msg}\n\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return

        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return

        # 실제 주문 전송 (tab_trading 방식과 동일한 IBKR API 호출)
        try:
            from ibapi.order import Order as IbOrder
            cp = self.mw.tab_callput
            sym = cp.edit_sym.text().strip().upper() if cp else "SPX"
            idx = cp.combo_exp.currentIndex() if cp else 0
            _, expiry, tag = cp._expiry_list[idx] if cp else ("","","")

            contract = make_opt_contract(sym, float(strike), opt_type, expiry, tag)
            ibord = IbOrder()
            ibord.action        = action
            ibord.orderType     = order_type
            ibord.totalQuantity = qty
            if is_lmt:
                ibord.lmtPrice = price
            ibord.tif = "DAY"

            oid = self.mw.ib.nextOrderId()
            self.mw.ib.nextOrderId = lambda: oid + 1
            self.mw.ib.placeOrder(oid, contract, ibord)

            col  = "#00ff88" if action == "BUY" else "#ff6666"
            self.lbl_ord_status.setStyleSheet(
                f"color:{col};font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
            self.lbl_ord_status.setText(f"전송됨: {msg}")
            self._log(f"📤 일반주문 전송: {msg}  (OID={oid})")
        except Exception as e:
            self.lbl_ord_status.setText(f"오류: {e}")
            self._log(f"❌ 주문 오류: {e}")

    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        bridge.acct_value.connect(self._on_acct)
        bridge.open_order_sig.connect(self._on_order_fill)
        bridge.tick_price.connect(self._on_idx_tick)
        router.register_price(REQ_SNIPER, REQ_SNIPER+499, self._on_tick)

    def _log(self, msg):
        line = f"[{ts()}] {msg}"
        self.snipe_log.append(line)
        self.all_log.append(line)

    # ─────────────────────────────────────────────────────────
    # 콜-풋탭 자동 동기화
    # ─────────────────────────────────────────────────────────
    def _auto_sync(self):
        """3초마다 콜-풋탭 데이터를 자동으로 가져옴."""
        cp = getattr(self.mw, 'tab_callput', None)
        if not cp: return
        # call_strikes / put_strikes 속성이 아직 초기화 안 된 경우 방어
        if not getattr(cp, 'call_strikes', None) and not getattr(cp, 'put_strikes', None):
            return
        self._sync_from_cp(cp, silent=True)

    def _load_from_main(self):
        """수동 동기화 버튼."""
        cp = getattr(self.mw, 'tab_callput', None)
        if not cp: return
        if not getattr(cp, 'call_strikes', None) and not getattr(cp, 'put_strikes', None):
            QMessageBox.information(self,"안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_from_cp(cp, silent=False)

    def _sync_from_cp(self, cp, silent=False):
        """콜-풋탭 → 타겟 테이블 동기화."""
        sym       = cp.edit_sym.text()
        cur_price = f"{cp.und_price:,.2f}" if getattr(cp, 'und_price', None) else "―"
        header    = f"종목: {sym}  |  현재가: {cur_price}"
        self.lbl_sym.setText(header)

        call_strikes = getattr(cp, 'call_strikes', []) or []
        put_strikes  = getattr(cp, 'put_strikes',  []) or []
        call_data    = getattr(cp, 'call_data',    {})
        put_data     = getattr(cp, 'put_data',     {})
        n_call = len(call_strikes)
        n_put  = len(put_strikes)
        expected = n_call + n_put

        # 심볼이 바뀌거나 행 수가 다를 때만 전체 리빌드
        prev_sym = getattr(self, '_tgt_sym', None)
        rebuild  = (prev_sym != sym) or (self.tbl_opt.rowCount() != expected)
        self._tgt_sym = sym

        if not rebuild:
            # 현재가만 업데이트 (깜빡임 없이)
            for i in range(n_call):
                lp = call_data.get(REQ_CALL+i, {}).get("last")
                if lp:
                    it = self.tbl_opt.item(i, 2)
                    if it: it.setText(f"{lp:.2f}")
            for i in range(n_put):
                lp = put_data.get(REQ_PUT+i, {}).get("last")
                if lp:
                    it = self.tbl_opt.item(n_call+i, 2)
                    if it: it.setText(f"{lp:.2f}")
            return

        # 전체 리빌드
        self.tbl_opt.setRowCount(0)
        for i, st in enumerate(call_strikes):
            lp = call_data.get(REQ_CALL+i, {}).get("last", None)
            r  = self.tbl_opt.rowCount(); self.tbl_opt.insertRow(r)
            tbl_set(self.tbl_opt, r, 0, "C", "#33aaff")
            tbl_set(self.tbl_opt, r, 1, str(int(st)), "#ffd700")
            tbl_set(self.tbl_opt, r, 2, f"{lp:.2f}" if isinstance(lp, float) else "―")
        for i, st in enumerate(put_strikes):
            lp = put_data.get(REQ_PUT+i, {}).get("last", None)
            r  = self.tbl_opt.rowCount(); self.tbl_opt.insertRow(r)
            tbl_set(self.tbl_opt, r, 0, "P", "#ff6666")
            tbl_set(self.tbl_opt, r, 1, str(int(st)), "#ffd700")
            tbl_set(self.tbl_opt, r, 2, f"{lp:.2f}" if isinstance(lp, float) else "―")
        if not silent:
            self._log(f"타겟 동기화: {sym}  C{n_call} / P{n_put}")

    def _show_target_help(self):
        QMessageBox.information(self,"옵션 타겟 안내",
            "콜-풋 탭(탭1)의 행사가 데이터를 3초마다 자동으로 가져옵니다.\n\n"
            "• 행 클릭 → 스나이퍼 설정 패널에 행사가/종류 자동 입력\n"
            "• '↺ 즉시 동기화' 버튼으로 수동 갱신 가능\n"
            "• 콜-풋 탭에서 Zone/만기 변경 시 자동 반영됩니다.")

    # ─────────────────────────────────────────────────────────
    # 지수 박스 업데이트 (bridge.tick_price 직접 수신)
    # ─────────────────────────────────────────────────────────
    def _on_idx_tick(self, rid, tt, price):
        if rid != REQ_UND or price <= 0: return
        if tt not in (4, 68, 75): return
        cp = self.mw.tab_callput
        sym = cp.edit_sym.text() if cp else "SPX"
        self.lbl_idx_name.setText(sym)
        self.lbl_idx_val.setText(f"{price:,.2f}")

        # 등락 계산
        chg_txt = "―"
        if cp and cp.und_prev and cp.und_prev > 0:
            chg = price - cp.und_prev; pct = chg/cp.und_prev*100
            sign = "+" if chg >= 0 else ""
            col  = "#00e676" if chg >= 0 else "#ff5252"
            chg_txt = f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)"
            self.lbl_idx_chg.setText(chg_txt)
            self.lbl_idx_chg.setStyleSheet(
                f"color:{col};font-weight:bold;font-size:12px;border:none;")

        # SPX/NDX/VIX 박스 업데이트
        sym_up = sym.upper()
        if "SPX" in sym_up:
            self.lbl_spx.setText(f"{price:,.2f}")
        elif "NDX" in sym_up:
            self.lbl_ndx.setText(f"{price:,.2f}")
        elif "VIX" in sym_up:
            self.lbl_vix.setText(f"{price:,.2f}")

        # ── 로그 헤더 라벨 실시간 업데이트 ──────────────────
        spx = self.lbl_spx.text(); ndx = self.lbl_ndx.text(); vix = self.lbl_vix.text()
        self.lbl_log_header.setText(
            f"SPX: {spx}   NDX: {ndx}   VIX: {vix}   |   {sym} 변동: {chg_txt}")

    # ─────────────────────────────────────────────────────────
    # 스나이퍼 로직
    # ─────────────────────────────────────────────────────────
    def _on_acct(self, tag, val, cur, acct):
        if tag == "BuyingPower":
            try:
                self.buying_power = float(val)
                self.lbl_funds.setText(f"${self.buying_power:,.2f}")
                self._calc_qty()
            except: pass

    def _calc_qty(self):
        try:
            prem = float(self.in_prem.text())
            if prem > 0 and self.buying_power > 0:
                self.lbl_max.setText(
                    f"{int(self.buying_power//(prem*self.MULTIPLIER))} 계약")
            else: self.lbl_max.setText("0 계약")
        except: self.lbl_max.setText("0 계약")

    def _set_qty(self, mode):
        try: max_q = int(self.lbl_max.text().replace(" 계약",""))
        except: max_q = 0
        qty = (max_q if mode=="max"
               else max(1,max_q//2) if mode=="half" else max(1,max_q//4))
        self.in_qty.setText(str(qty))

    def _on_opt_click(self, row, col):
        t = self.tbl_opt.item(row,0); s = self.tbl_opt.item(row,1)
        if t and s:
            self.val_type.setText(t.text())
            self.val_strike.setText(s.text())
            self._calc_qty()
            # 일반 주문창에도 자동 입력
            self._on_opt_click_ord(s.text(), t.text())

    def _start_sniper(self):
        strike   = self.val_strike.text(); opt_type = self.val_type.text()
        prem_txt = self.in_prem.text();    qty_txt  = self.in_qty.text()
        if not (strike and opt_type and prem_txt and qty_txt):
            QMessageBox.warning(self,"입력 오류","모든 값을 확인하세요."); return
        rid = self.sniper_rid; self.sniper_rid += 1; tgt = float(prem_txt)
        sell_val  = self.in_sell.text().strip()
        sell_mode = "pct" if self.radio_sell_pct.isChecked() else "price"
        time_cond = self.in_time.text().strip()
        dur_min   = int(self.in_dur.text().strip() or "1")
        self.active_snipers[rid] = {
            "strike":strike,"type":opt_type,"target":tgt,
            "qty":int(qty_txt),"triggered":False,"row_idx":None,
            "time_cond":time_cond,"dur_min":dur_min,
            "sell_val":sell_val,"sell_mode":sell_mode}
        r = self.tbl_snipe.rowCount(); self.tbl_snipe.insertRow(r)
        tbl_set(self.tbl_snipe,r,0,f"{strike}{opt_type}")
        tbl_set(self.tbl_snipe,r,1,f"${tgt:.2f}")
        tbl_set(self.tbl_snipe,r,2,"대기중")
        tbl_set(self.tbl_snipe,r,3,"👁 감시중")
        sell_disp = (f"{sell_val}{'%' if sell_mode=='pct' else '$'}"
                     if sell_val else "―")
        tbl_set(self.tbl_snipe,r,4,sell_disp)
        self.active_snipers[rid]["row_idx"] = r
        time_txt = f"  시각={time_cond}±{dur_min}분" if time_cond else ""
        self._log(f"스나이퍼: {strike}{opt_type}  목표=${tgt:.2f}{time_txt}")

    def _check_time_conditions(self):
        now = datetime.now()
        for rid, sn in list(self.active_snipers.items()):
            if sn["triggered"] or not sn.get("time_cond"): continue
            try:
                parts = sn["time_cond"].split(":")
                tdt   = now.replace(hour=int(parts[0]),minute=int(parts[1]),second=0)
                if abs((now-tdt).total_seconds()) <= sn["dur_min"]*60:
                    sn["triggered"] = True
                    ri = sn.get("row_idx")
                    if ri is not None: tbl_set(self.tbl_snipe,ri,3,"⏰ 시간 도달!")
                    self._log(f"⏰ 시간 조건 도달: {sn['strike']}{sn['type']}")
            except: pass

    def _on_tick(self, rid, tt, price):
        if rid not in self.active_snipers or price <= 0: return
        sn = self.active_snipers[rid]; ri = sn.get("row_idx")
        if ri is not None: tbl_set(self.tbl_snipe,ri,2,f"{price:.2f}")
        if price <= sn["target"] and not sn["triggered"]:
            sn["triggered"] = True
            if ri is not None: tbl_set(self.tbl_snipe,ri,3,"🔥 조건 달성!")
            self._log(
                f"★★★ 프리미엄 조건! {sn['strike']}{sn['type']} "
                f"{price:.2f}≤{sn['target']:.2f}")

    def _on_snipe_dbl(self, row, col):
        si = self.tbl_snipe.item(row,0); ti = self.tbl_snipe.item(row,1)
        if not si: return
        raw = si.text(); opt_type = raw[-1]; strike = raw[:-1]
        target = ti.text().replace("$","") if ti else ""
        to_del = [r for r,sn in self.active_snipers.items()
                  if sn.get("strike")==strike and sn.get("type")==opt_type
                  and sn.get("row_idx")==row]
        for r in to_del: del self.active_snipers[r]
        self.tbl_snipe.removeRow(row)
        self.val_strike.setText(strike)
        self.val_type.setText(opt_type)
        self.in_prem.setText(target)
        self._log(f"스나이퍼 취소→복원: {strike}{opt_type} ${target}")

    def _on_order_fill(self, oid, sym, right, action, qty, price, status):
        if action == "SELL":
            r = self.tbl_amend.rowCount(); self.tbl_amend.insertRow(r)
            tbl_set(self.tbl_amend,r,0,str(oid)); tbl_set(self.tbl_amend,r,1,sym)
            tbl_set(self.tbl_amend,r,2,right);    tbl_set(self.tbl_amend,r,3,str(int(qty)))
            tbl_set(self.tbl_amend,r,4,status)
            self.amend_snipers[r] = {"oid":oid,"sym":sym,"right":right,"qty":qty}

    def _amend_keypress(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            row = self.tbl_amend.currentRow()
            if row < 0: return
            sn = self.amend_snipers.get(row)
            if not sn: return
            self._log(
                f"🔄 시장가 정정 매도: ID={sn['oid']} "
                f"{sn['sym']}{sn['right']} {sn['qty']}계약")
        else: QAbstractItemView.keyPressEvent(self.tbl_amend, event)

    def _clear_snipers(self):
        self.active_snipers.clear(); self.tbl_snipe.setRowCount(0)

    # ─────────────────────────────────────────────────────────
    # 원클릭 주문
    # ─────────────────────────────────────────────────────────
    def _panic_sell(self):
        ret = QMessageBox.question(self,"PANIC SELL 확인",
            "⚠ 모든 0DTE 포지션을 시장가로 즉시 청산합니다.\n계속하시겠습니까?",
            QMessageBox.Yes|QMessageBox.No)
        if ret == QMessageBox.Yes:
            self._log("🚨 PANIC SELL 실행")
            if self.mw.connected: self.mw.ib.reqPositions()

    def _atm_straddle(self): self._log("⚡ ATM Straddle 진입 요청")
    def _lmt_sniper(self):
        strike = self.val_strike.text(); opt_type = self.val_type.text()
        if not strike:
            QMessageBox.warning(self,"오류","행사가를 선택하세요."); return
        self._log(f"🎯 LMT $0.10 → {strike}{opt_type} 매수 요청")



# ══════════════════════════════════════════════════════════════