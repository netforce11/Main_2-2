"""
tab_options_panels.py — PanelsMixin: ctrl / tbl / bot panel builders  [S10]
변경 이력:
  [S9]  _build_tbl_panel → price/pos QSplitter, strategy_panel
  [S10] Feature A — tbl_call/tbl_put 컬럼 구성 변경: "전일" → "등락%"
        Feature B — _build_strategy_panel() 제거, sizes 조정
        Feature C — IV 비교 패널(_iv_panel) 우측에 추가
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QRadioButton, QButtonGroup,
    QSplitter, QTableWidgetItem, QGroupBox, QDateEdit,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QBrush

from core import make_table
from call_put_tab.tab_options_price import PricePanelMixin

# [S10] strategy_panel import 제거 (Feature B — 스프레드 패널 삭제)
# from strategy_panel import StrategyPanelMixin  ← 삭제


def _mk(text: str, color: str = "#dde0f0") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


class PanelsMixin(PricePanelMixin):
    """Ctrl / tbl / bot layout builders for CallPutGrid.
    [S10] StrategyPanelMixin 제거 — 스프레드 패널 공간 삭제.
    """

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
        zone_defs = [
            ("OTM2", "#00b894"),
            ("OTM1", "#00e676"),
            ("ATM",  "#ffd700"),
            ("ITM1", "#ff8800"),
            ("ITM2", "#ff4444"),
        ]
        for z, col in zone_defs:
            rb = QRadioButton(z)
            rb.setStyleSheet(f"color:{col};font-size:11px;")
            if z == "ATM": rb.setChecked(True)
            zone_grp.addButton(rb)
            def _on_zone_toggle(chk, b=rb, c=col, zname=z):
                if not chk: return
                self._on_zone_change(b)
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
        # ✅ 콜/풋 각 최대 25개 → 합산 50개 + REQ_UND 1개 = 51개 (한도 100개 이내)
        self.spin_n.setRange(1, 24); self.spin_n.setValue(24)
        self.spin_n.setFixedWidth(50); self.spin_n.setFixedHeight(24)
        self.spin_n.setStyleSheet(
            "background:#0a0a18;color:#ffd700;border:1px solid #2e3060;font-size:12px;")
        self.spin_n.setToolTip("콜/풋 각 최대 25개 (합산 51개, IBKR 한도 100개 이내)")
        # ✅ spin_n 변경 시 한도 초과 경고 + 1분 후 강제 다운그레이드
        self.spin_n.valueChanged.connect(self._on_spin_n_changed)

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
        # [S10-A] 컬럼 "전일" → "등락%" 으로 변경
        # 실제 색상 강조는 tab_options_price.py _render_chain_row() 에서 처리
        self.tbl_call = make_table(["행사가", "가격", "등락%", "Delta", "Theta", "Gamma", "잔고"])
        self.tbl_call.setMinimumHeight(0)
        self.tbl_call.horizontalHeader().sectionClicked.connect(lambda col: None)
        self.tbl_call.cellClicked.connect(lambda r, c: self._tbl_click(r, c, "C"))
        self.tbl_call.cellDoubleClicked.connect(lambda r, c: self._tbl_dbl(r, c, "C"))

        self.tbl_put = make_table(["행사가", "가격", "등락%", "Delta", "Theta", "Gamma", "잔고"])
        self.tbl_put.setMinimumHeight(0)
        self.tbl_put.cellClicked.connect(lambda r, c: self._tbl_click(r, c, "P"))
        self.tbl_put.cellDoubleClicked.connect(lambda r, c: self._tbl_dbl(r, c, "P"))

        self._tbl_splitter = self._spl(Qt.Horizontal)
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_call, "CALL", "#33aaff"))
        self._tbl_splitter.addWidget(self._wrap_tbl(self.tbl_put,  "PUT",  "#ff6666"))

        # [S8] 현재가(상단) + 잔고(하단) 수직 스플리터
        self._tbl_splitter.addWidget(self._build_price_pos_widget())

        # [S10-C] IV 비교 패널 (스프레드 패널 자리 대체)
        self._tbl_splitter.addWidget(self._build_iv_panel())

        # [S10-B] 스프레드 전략 패널 제거 — sizes도 3개로 축소
        # 기존: setSizes([440, 440, 180, 220])
        self._tbl_splitter.setSizes([420, 420, 175, 240])
        from PyQt5.QtWidgets import QSizePolicy as _SP
        self._tbl_splitter.setSizePolicy(_SP.Ignored, _SP.Ignored)
        return self._tbl_splitter

    # ── [S10-C] IV 패널 빌더 ─────────────────────────────────
    def _build_iv_panel(self) -> QWidget:
        """IVPanel 인스턴스 생성 후 self._iv_panel에 저장."""
        from iv_rank_panel import IVPanel
        self._iv_panel = IVPanel(self.mw)
        # CallPutGrid 인스턴스(self) 주입 — 조회 완료 후에도 동작하도록 지연 없이 바로 연결
        self._iv_panel.set_source(self)
        return self._iv_panel

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

        # ★ v6.5 — 감시 상태 라벨 + 토글 버튼 ─────────────────
        from PyQt5.QtCore import QTimer as _QTimer
        watch_bar = QWidget(); watch_bar.setFixedHeight(26)
        watch_bar.setStyleSheet("background:#08080f;")
        wh = QHBoxLayout(watch_bar)
        wh.setContentsMargins(6, 2, 6, 2); wh.setSpacing(6)

        self._watch_status_lbl = QLabel("⏸ WATCHING OFF")
        self._watch_status_lbl.setStyleSheet(
            "color:#555;font-size:11px;font-weight:bold;border:none;")
        wh.addWidget(self._watch_status_lbl)
        wh.addStretch()

        self._watch_toggle_btn = QPushButton("▶ 감시 켜기")
        self._watch_toggle_btn.setFixedHeight(22)
        self._watch_toggle_btn.setStyleSheet(
            "QPushButton{background:#1a2a1a;color:#00ff88;font-size:11px;"
            "border:1px solid #2a5a2a;border-radius:3px;padding:2px 8px;}"
            "QPushButton:hover{background:#2a3a2a;}")
        self._watch_toggle_btn.clicked.connect(self._toggle_watch)
        wh.addWidget(self._watch_toggle_btn)
        qv.addWidget(watch_bar)

        # 깜빡임 타이머 (0.8초 간격) — 규칙 로드 후에만 시작
        self._watch_blink_timer = _QTimer(self)
        self._watch_blink_timer.setInterval(800)
        self._watch_blink_timer.timeout.connect(self._on_watch_blink)
        # 시작 안 함 — _load_watch_rules_from_file() 에서 규칙 있을 때만 start()
        self._watch_blink_state = False
        # ────────────────────────────────────────────────────────

        qv.addWidget(self._build_quick_order_panel(), 1)

        self._bot_splitter.addWidget(qord_container)
        self._bot_splitter.setSizes([820, 300])
        self._watch_splitter = self._bot_splitter
        return self._bot_splitter

    # ── spin_n 한도 초과 경고 + 1분 후 강제 다운그레이드 ──────────
    _SPIN_N_MAX   = 25   # 콜/풋 각 최대 (합산 51개, IBKR 한도 이내)
    _SPIN_N_SAFE  = 10   # 1분 후 자동 복원값

    def _on_spin_n_changed(self, value: int):
        """
        spin_n 값 변경 시 호출.
        - 25 초과: QMessageBox 경고 + 1분 후 강제 10으로 다운그레이드
        - 25 이하: 기존 타이머 취소 (사용자가 스스로 조절)
        """
        # 이미 최대값(25)으로 하드 제한되어 있으므로
        # 이 메서드는 값이 정확히 25일 때 경고를 띄우는 용도로 사용
        if value >= self._SPIN_N_MAX:
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("⚠ 구독 한도 주의")
            msg.setIcon(QMessageBox.Warning)
            msg.setText(
                f"콜/풋 각 {value}개 조회 시\n"
                f"총 구독 수: {value * 2 + 1}개\n\n"
                f"IBKR 기본 한도(100개)에 근접합니다.\n"
                f"1분 내에 줄이지 않으면 자동으로 {self._SPIN_N_SAFE}개로 조정됩니다."
            )
            msg.setStyleSheet(
                "QMessageBox{background:#0a0a18;color:#ffd700;}"
                "QLabel{color:#ffd700;font-size:12px;}"
                "QPushButton{background:#1c1c3a;color:#dde0f0;"
                "border:1px solid #3a3a7a;border-radius:3px;padding:4px 12px;}"
            )
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

            # 1분 후 강제 다운그레이드 타이머 시작 (기존 것 있으면 재시작)
            if not hasattr(self, '_spin_n_guard_timer'):
                from PyQt5.QtCore import QTimer as _QT
                self._spin_n_guard_timer = _QT(self)
                self._spin_n_guard_timer.setSingleShot(True)
                self._spin_n_guard_timer.timeout.connect(
                    self._force_downgrade_spin_n)
            self._spin_n_guard_timer.start(60_000)   # 1분
        else:
            # 사용자가 직접 내렸으면 타이머 취소
            t = getattr(self, '_spin_n_guard_timer', None)
            if t and t.isActive():
                t.stop()

    def _force_downgrade_spin_n(self):
        """1분 후에도 조정 없으면 강제로 spin_n을 SAFE 값으로 내림."""
        if self.spin_n.value() >= self._SPIN_N_MAX:
            from PyQt5.QtWidgets import QMessageBox
            self.spin_n.setValue(self._SPIN_N_SAFE)
            msg = QMessageBox(self)
            msg.setWindowTitle("⚠ 조회 수 자동 조정")
            msg.setIcon(QMessageBox.Information)
            msg.setText(
                f"1분간 조정이 없어 조회 수를 "
                f"{self._SPIN_N_SAFE}개로 자동 조정했습니다."
            )
            msg.setStyleSheet(
                "QMessageBox{background:#0a0a18;color:#ffd700;}"
                "QLabel{color:#ffd700;font-size:12px;}"
                "QPushButton{background:#1c1c3a;color:#dde0f0;"
                "border:1px solid #3a3a7a;border-radius:3px;padding:4px 12px;}"
            )
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            self._log("⚠ 구독 한도 초과 방지: spin_n 자동 조정 → "
                      f"{self._SPIN_N_SAFE}개")

    def _on_watch_blink(self):
        """깜빡임 타이머 콜백 — ● 표시 토글."""
        lbl = getattr(self, '_watch_status_lbl', None)
        if not lbl:
            return
        self._watch_blink_state = not self._watch_blink_state
        if self._watch_blink_state:
            lbl.setText("🟢 ON WATCHING ●")
            lbl.setStyleSheet(
                "color:#00ff88;font-size:11px;font-weight:bold;border:none;")
        else:
            lbl.setText("🟢 ON WATCHING  ")
            lbl.setStyleSheet(
                "color:#007744;font-size:11px;font-weight:bold;border:none;")

    # ── 감시 팝업 ─────────────────────────────────────────────
    def _open_watch_popup(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout as _V
        from PyQt5.QtCore import Qt as _Qt
        # ✅ FIX 🔴-4: 기존 다이얼로그 재사용 (매번 새로 생성하면 이전 dlg 메모리 잔존)
        if getattr(self, '_watch_popup', None) is not None:
            self._watch_popup.show()
            self._watch_popup.raise_()
            self._watch_popup.activateWindow()
            return
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