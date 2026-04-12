"""
tab_options_panels.py — PanelsMixin: ctrl / tbl / bot panel builders  [S9]
변경: _build_tbl_panel → 현재가+잔고를 _build_price_pos_widget() 수직 스플리터로 교체
      _build_quick_order_panel 탭 위젯 ref(_qord_tab_widget) 저장
      placeholder → _build_strategy_panel() 스프레드 전략 패널 [S9]
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QRadioButton, QButtonGroup,
    QSplitter, QTableWidgetItem, QGroupBox, QDateEdit,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QBrush

from core import make_table
from tab_options_price import PricePanelMixin
from strategy_panel import StrategyPanelMixin


def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


class PanelsMixin(PricePanelMixin, StrategyPanelMixin):
    """Ctrl / tbl / bot layout builders for CallPutGrid."""

    def _wrap_tbl(self, tbl, title, color):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(1)
        lbl = QLabel(title); lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color:{color};font-weight:bold;border:none;")
        v.addWidget(lbl); v.addWidget(tbl)
        return w

    # ── ② Control bar ─────────────────────────────────────────
    def _build_ctrl_panel(self) -> QSplitter:
        self._ctrl_splitter = self._spl(Qt.Horizontal)

        _gb = ("QGroupBox{font-size:10px;color:#5dade2;"
               "border:1px solid #2a2a5a;border-radius:4px;"
               "margin-top:8px;padding-top:4px;}"
               "QGroupBox::title{subcontrol-origin:margin;left:6px;top:0px;}")
        _btn = ("QPushButton{background:#1c1c3a;color:#dde0f0;"
                "border:1px solid #3a3a7a;border-radius:3px;"
                "padding:2px 7px;font-size:11px;}"
                "QPushButton:hover{background:#2a2a5a;}"
                "QPushButton:pressed{background:#0e0e2a;}")

        def _gb_w(title):
            g = QGroupBox(title); g.setStyleSheet(_gb)
            h = QHBoxLayout(g); h.setContentsMargins(5, 10, 5, 2); h.setSpacing(4)
            return g, h

        g1, h1 = _gb_w("IBKR")
        self.btn_conn = QPushButton("🔌 연결"); self.btn_conn.setStyleSheet(_btn)
        self.btn_disc = QPushButton("⏏ 해제");  self.btn_disc.setStyleSheet(_btn)
        self.lbl_status = QLabel("● 미연결")
        self.lbl_status.setStyleSheet("color:#ff5252;font-weight:bold;border:none;font-size:11px;")
        for w in (self.btn_conn, self.btn_disc, self.lbl_status): h1.addWidget(w)
        self._ctrl_splitter.addWidget(g1)

        g2, h2 = _gb_w("시세모드")
        self.radio_live  = QRadioButton("실시간")
        self.radio_delay = QRadioButton("지연")
        self.radio_live.setChecked(True)
        mdt_grp = QButtonGroup(self)
        for rb in (self.radio_live, self.radio_delay):
            rb.setStyleSheet("color:#ffd700;font-size:11px;")
            rb.toggled.connect(self._apply_mdt_manual)
            mdt_grp.addButton(rb); h2.addWidget(rb)
        self._ctrl_splitter.addWidget(g2)

        g3, h3 = _gb_w("SPXW 0DTE")
        self.combo_spxw = QComboBox(); self.combo_spxw.setFixedHeight(24)
        self.combo_spxw.setStyleSheet(
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
            "font-size:11px;padding:1px 3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        self._build_spxw_combo()
        self.combo_spxw.currentIndexChanged.connect(self._on_spxw_select)
        h3.addWidget(self.combo_spxw)
        self._ctrl_splitter.addWidget(g3)

        g4, h4 = _gb_w("종목 / 만기  📅")
        self.edit_sym = QLineEdit("SPX"); self.edit_sym.setFixedWidth(66)
        self.edit_sym.setFixedHeight(24)
        self.edit_sym.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;"
            "font-size:12px;font-weight:bold;padding:2px;")
        self.edit_sym.editingFinished.connect(self._refresh_expiry_list)
        self.combo_exp = QComboBox(); self.combo_exp.setFixedHeight(24)
        self.combo_exp.setMinimumWidth(92)
        self.combo_exp.setStyleSheet(
            "QComboBox{background:#12122a;color:#90caf9;border:1px solid #3a3a6a;"
            "font-size:11px;padding:1px 3px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#90caf9;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        for label, code, tag in self._expiry_list:
            self.combo_exp.addItem(label)
        self.combo_exp.currentIndexChanged.connect(self._on_exp_change)
        self.edit_custom = QLineEdit(); self.edit_custom.setPlaceholderText("YYYYMMDD")
        self.edit_custom.setFixedWidth(78); self.edit_custom.setFixedHeight(24)
        self.edit_custom.setVisible(False)
        self.edit_custom.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;font-size:11px;")
        self.date_edit = QDateEdit(); self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate()); self.date_edit.setFixedHeight(24)
        self.date_edit.setVisible(False)
        self.date_edit.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;font-size:11px;")
        self.date_edit.dateChanged.connect(self._on_date_edit_changed)
        self.btn_cal = QPushButton("📅"); self.btn_cal.setFixedSize(26, 24)
        self.btn_cal.setStyleSheet(_btn); self.btn_cal.setToolTip("날짜 선택")
        self.btn_cal.clicked.connect(self._open_calendar)
        for w in (self.edit_sym, self.combo_exp,
                  self.edit_custom, self.date_edit, self.btn_cal):
            h4.addWidget(w)
        self._ctrl_splitter.addWidget(g4)

        g5, h5 = _gb_w("Zone")
        self._zone_btns: dict = {}
        zone_grp = QButtonGroup(self)
        # OTM2(외가심층) → OTM1(외가) → ATM(등가) → ITM1(내가) → ITM2(내가심층)
        zone_defs = [
            ("OTM2", "#00b894"),   # 짙은 초록 — 외가 심층
            ("OTM1", "#00e676"),   # 밝은 초록 — 외가
            ("ATM",  "#ffd700"),   # 노랑       — 등가
            ("ITM1", "#ff8800"),   # 주황       — 내가
            ("ITM2", "#ff4444"),   # 빨강       — 내가 심층
        ]
        for z, col in zone_defs:
            rb = QRadioButton(z)
            rb.setStyleSheet(f"color:{col};font-size:11px;")
            if z == "ATM": rb.setChecked(True)
            zone_grp.addButton(rb)
            def _on_zone_toggle(chk, b=rb, c=col, zname=z):
                if not chk: return
                self._on_zone_change(b)
                # 사이드바 Zone 라벨 즉시 동기화
                if hasattr(self, '_side_und_zone'):
                    self._side_und_zone.setText(f"Zone: {zname}")
                    self._side_und_zone.setStyleSheet(
                        f"color:{c};font-size:10px;border:none;")
            rb.toggled.connect(_on_zone_toggle)
            self._zone_btns[z] = rb; h5.addWidget(rb)
        self._ctrl_splitter.addWidget(g5)

        g6, h6 = _gb_w("조회")
        h6.addWidget(QLabel("행:", styleSheet="color:#aaa;font-size:11px;border:none;"))
        self.spin_n = QSpinBox()
        self.spin_n.setRange(1, self._MAX_STRIKES); self.spin_n.setValue(10)
        self.spin_n.setFixedWidth(50); self.spin_n.setFixedHeight(24)
        self.spin_n.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;font-size:12px;")
        # "10 조회" 원클릭 빠른버튼
        self.btn_fetch_10 = QPushButton("10조회"); self.btn_fetch_10.setFixedHeight(26)
        self.btn_fetch_10.setFixedWidth(54)
        self.btn_fetch_10.setStyleSheet(
            "QPushButton{background:#1a3a2a;color:#00ff88;font-size:11px;"
            "font-weight:bold;border-radius:3px;border:1px solid #2a5a3a;}"
            "QPushButton:hover{background:#2a4a3a;}"
            "QPushButton:pressed{background:#0a2a1a;}")
        self.btn_fetch_10.setToolTip("행 수를 10으로 설정하고 즉시 조회")
        self.btn_fetch_10.clicked.connect(
            lambda: (self.spin_n.setValue(10), self.btn_fetch.click()))
        self.btn_fetch = QPushButton("🔍 조회"); self.btn_fetch.setFixedHeight(26)
        self.btn_fetch.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:12px;"
            "font-weight:bold;padding:2px 10px;border-radius:4px;")
        h6.addWidget(self.spin_n); h6.addWidget(self.btn_fetch_10); h6.addWidget(self.btn_fetch)
        self._ctrl_splitter.addWidget(g6)

        g7, h7 = _gb_w("기초자산  (클릭→히스토리)")
        self.lbl_und = QLabel("―")
        self.lbl_und.setStyleSheet(
            "color:#ffd700;font-size:16px;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;padding:1px 8px;background:#08080f;")
        self.lbl_und.setCursor(Qt.PointingHandCursor)
        self.lbl_und.setToolTip("클릭 → 일봉/분봉 히스토리 조회")
        self.lbl_und.mousePressEvent = lambda e: self._on_und_label_clicked()
        self.lbl_chg = QLabel("")
        self.lbl_chg.setStyleSheet("color:#aaa;font-size:12px;border:none;")
        h7.addWidget(self.lbl_und); h7.addWidget(self.lbl_chg)
        self._ctrl_splitter.addWidget(g7)

        self._ctrl_splitter.setSizes([150, 110, 165, 275, 220, 160, 210])
        from PyQt5.QtWidgets import QSizePolicy as _SP
        self._ctrl_splitter.setSizePolicy(_SP.Ignored, _SP.Ignored)
        return self._ctrl_splitter

    # ── ③ Table row ───────────────────────────────────────────
    def _build_tbl_panel(self) -> QSplitter:
        self.tbl_call = make_table(["행사가","가격","전일","Delta","Theta","Gamma","잔고"])
        self.tbl_call.setMinimumHeight(0)
        self.tbl_call.horizontalHeader().sectionClicked.connect(lambda col: None)
        self.tbl_call.cellClicked.connect(lambda r, c: self._tbl_click(r, c, "C"))
        self.tbl_call.cellDoubleClicked.connect(lambda r, c: self._tbl_dbl(r, c, "C"))

        self.tbl_put = make_table(["행사가","가격","전일","Delta","Theta","Gamma","잔고"])
        self.tbl_put.setMinimumHeight(0)
        self.tbl_put.cellClicked.connect(lambda r, c: self._tbl_click(r, c, "P"))
        self.tbl_put.cellDoubleClicked.connect(lambda r, c: self._tbl_dbl(r, c, "P"))

        self._tbl_splitter = self._spl(Qt.Horizontal)
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_call, "CALL", "#33aaff"))
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_put,  "PUT",  "#ff6666"))

        # [S8] 현재가(상단) + 잔고(하단) 수직 스플리터
        self._tbl_splitter.addWidget(self._build_price_pos_widget())

        # [S9] 스프레드 전략 패널
        self._tbl_splitter.addWidget(self._build_strategy_panel())

        self._tbl_splitter.setSizes([440, 440, 180, 220])
        from PyQt5.QtWidgets import QSizePolicy as _SP
        self._tbl_splitter.setSizePolicy(_SP.Ignored, _SP.Ignored)
        return self._tbl_splitter

    # ── ④ Bottom row ──────────────────────────────────────────
    def _build_bot_panel(self) -> QSplitter:
        self._bot_splitter = self._spl(Qt.Horizontal)
        self._bot_splitter.addWidget(self._build_chart_panel())

        qord_container = QWidget(); qord_container.setStyleSheet("background:#06060e;")
        qv = QVBoxLayout(qord_container)
        qv.setContentsMargins(0, 0, 0, 0); qv.setSpacing(0)

        btn_watch_popup = QPushButton("🔔  감시 패널 열기")
        btn_watch_popup.setFixedHeight(28)
        btn_watch_popup.setStyleSheet(
            "QPushButton{background:#1a2a1a;color:#00e676;font-size:12px;"
            "font-weight:bold;border:1px solid #2a5a2a;border-radius:0px;}"
            "QPushButton:hover{background:#2a3a2a;color:#00ff88;}"
            "QPushButton:pressed{background:#0a1a0a;}")
        btn_watch_popup.clicked.connect(self._open_watch_popup)
        qv.addWidget(btn_watch_popup)
        qv.addWidget(self._build_quick_order_panel(), 1)

        self._bot_splitter.addWidget(qord_container)
        self._bot_splitter.setSizes([820, 300])
        self._watch_splitter = self._bot_splitter
        return self._bot_splitter

    # ── 감시 팝업 ─────────────────────────────────────────────
    def _open_watch_popup(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout as _V
        from PyQt5.QtCore import Qt as _Qt
        if getattr(self, '_watch_popup', None) and self._watch_popup.isVisible():
            self._watch_popup.raise_(); self._watch_popup.activateWindow(); return
        dlg = QDialog(self)
        dlg.setWindowTitle("🔔 감시 패널")
        dlg.setWindowFlags(
            _Qt.Window | _Qt.WindowCloseButtonHint |
            _Qt.WindowMinimizeButtonHint | _Qt.WindowMaximizeButtonHint)
        dlg.setMinimumSize(520, 600); dlg.resize(620, 720)
        dlg.setStyleSheet("QDialog{background:#06060e;}QLabel{color:#dde0f0;}")
        v = _V(dlg); v.setContentsMargins(4, 4, 4, 4); v.setSpacing(0)
        v.addWidget(self._build_watch_widget())
        self._watch_popup = dlg; dlg.show()