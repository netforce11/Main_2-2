from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox, QCheckBox,
    QGroupBox, QScrollArea, QMessageBox,
)
from PyQt5.QtCore import Qt
from night_alert_template import (
    NightAlertConfig, NightSlot, load_config, save_config, make_preset
)

class NightAlertTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg        = load_config()
        self._rows       = []
        self._checker    = None   # NightAlertChecker 참조 (외부 주입)
        self._build_ui()
        self._load_rows()

    def set_checker(self, checker):
        """watch_alert_tab에서 NightAlertChecker 참조 주입."""
        self._checker = checker

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(6); vbox.setContentsMargins(6,6,6,6)
        vbox.addWidget(self._make_banner())       # ← 배너 맨 위
        vbox.addWidget(self._make_base_box())
        vbox.addWidget(self._make_slots_box())
        vbox.addWidget(self._make_base_adjust_box())
        vbox.addWidget(self._make_tg_box())
        vbox.addLayout(self._make_btn_bar())

    # ── 배너 ────────────────────────────────────────────────
    _BANNER_MSGS = [
        "⚠️  연 이틀 추세로 과열 체크 필수",
        "📋  D 기준 D-1 전략 체크",
    ]

    def _make_banner(self):
        from PyQt5.QtCore import QTimer
        box = QWidget()
        box.setStyleSheet(
            "background:#1a1a2e;border-radius:4px;border:1px solid #3a3a5a;"
        )
        h = QHBoxLayout(box); h.setContentsMargins(8,4,8,4)

        self._banner_lbl = QLabel(self._BANNER_MSGS[0])
        self._banner_lbl.setStyleSheet("color:#f0c040;font-size:11px;font-weight:bold;border:none;")
        self._banner_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(self._banner_lbl)

        # 편집 버튼
        btn_edit = QPushButton("✏"); btn_edit.setFixedSize(20,20)
        btn_edit.setStyleSheet("font-size:10px;padding:0;border:none;background:transparent;color:#888;")
        btn_edit.setToolTip("배너 문구 편집")
        btn_edit.clicked.connect(self._edit_banner)
        h.addWidget(btn_edit)

        self._banner_idx = 0
        self._banner_timer = QTimer(self)
        self._banner_timer.timeout.connect(self._next_banner)
        self._banner_timer.start(10000)
        return box

    def _next_banner(self):
        msgs = self.__class__._BANNER_MSGS
        if not msgs: return
        self._banner_idx = (self._banner_idx + 1) % len(msgs)
        self._banner_lbl.setText(msgs[self._banner_idx])

    def _edit_banner(self):
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit
        dlg = QDialog(self); dlg.setWindowTitle("배너 문구 편집")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("한 줄씩 입력 (엔터로 구분):"))
        te = QPlainTextEdit("\n".join(self.__class__._BANNER_MSGS))
        te.setFixedHeight(120); v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec_() == QDialog.Accepted:
            lines = [l.strip() for l in te.toPlainText().splitlines() if l.strip()]
            if lines:
                self.__class__._BANNER_MSGS = lines
                self._banner_idx = 0
                self._banner_lbl.setText(lines[0])

    # ── 기준가 설정 박스 ──────────────────────────────────────
    def _make_base_box(self):
        box = QGroupBox("기준가 설정")
        h = QHBoxLayout(box)
        h.addWidget(QLabel("기준가:"))
        self._cmb_base = QComboBox()
        self._cmb_base.addItems(["당일 22:30 시가 (자동)","전일 종가 (자동)","수동 입력"])
        self._cmb_base.setCurrentIndex({"open":0,"prev_close":1}.get(self._cfg.base_type,0))
        h.addWidget(self._cmb_base)
        h.addWidget(QLabel("ATM:"))
        self._chk_atm_auto = QCheckBox("자동")
        self._chk_atm_auto.setChecked(self._cfg.atm_auto)
        self._chk_atm_auto.toggled.connect(lambda c: self._spn_atm.setEnabled(not c))
        h.addWidget(self._chk_atm_auto)
        self._spn_atm = QDoubleSpinBox()
        self._spn_atm.setRange(0,99999); self._spn_atm.setValue(self._cfg.atm_manual)
        self._spn_atm.setEnabled(not self._cfg.atm_auto); self._spn_atm.setFixedWidth(90)
        h.addWidget(self._spn_atm); h.addStretch()
        return box

    # ── 감시 구간 박스 ────────────────────────────────────────
    def _make_slots_box(self):
        box = QGroupBox("새벽 감시 구간")
        vbox = QVBoxLayout(box)

        # 템플릿 프리셋 바
        preset_h = QHBoxLayout()
        preset_h.addWidget(QLabel("템플릿:"))
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(["직접 설정", "30분 단위 (22:30~05:00)", "45분 단위 (22:30~05:00)"])
        preset_h.addWidget(self._cmb_preset)
        btn_preset = QPushButton("불러오기"); btn_preset.setFixedHeight(22)
        btn_preset.clicked.connect(self._load_preset)
        preset_h.addWidget(btn_preset); preset_h.addStretch()
        vbox.addLayout(preset_h)

        # 헤더
        hdr = QHBoxLayout()
        for txt,w in [("ON",30),("시작",60),("종료",60),("대상",48),("배율",55),
                      ("OTM%",52),("사전%",52),("최대",40),("중복",38),("",28)]:
            l = QLabel(txt); l.setFixedWidth(w); l.setAlignment(Qt.AlignCenter)
            hdr.addWidget(l)
        vbox.addLayout(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFixedHeight(160)
        self._slot_container = QWidget()
        self._slot_vbox = QVBoxLayout(self._slot_container)
        self._slot_vbox.setSpacing(2); self._slot_vbox.addStretch()
        scroll.setWidget(self._slot_container); vbox.addWidget(scroll)

        btn = QPushButton("＋ 구간 추가"); btn.setFixedHeight(24)
        btn.clicked.connect(self._add_slot_row); vbox.addWidget(btn)
        return box

    def _add_slot_row(self, slot=None):
        if slot is None: slot = NightSlot()
        row_w = QWidget(); h = QHBoxLayout(row_w)
        h.setContentsMargins(0,0,0,0); h.setSpacing(2)

        chk   = QCheckBox(); chk.setChecked(slot.enabled); chk.setFixedWidth(30)
        edt_s = QLineEdit(slot.start_hhmm); edt_s.setFixedWidth(60)
        edt_e = QLineEdit(slot.end_hhmm);   edt_e.setFixedWidth(60)
        cmb_t = QComboBox(); cmb_t.addItems(["P","C","both"]); cmb_t.setFixedWidth(48)
        cmb_t.setCurrentText(slot.opt_type)

        spn_m = QDoubleSpinBox(); spn_m.setRange(1,100); spn_m.setValue(slot.multiplier)
        spn_m.setFixedWidth(55); spn_m.setSuffix("x")

        spn_otm = QDoubleSpinBox(); spn_otm.setRange(0,5)
        spn_otm.setValue(getattr(slot,'otm_pct',0.0))
        spn_otm.setFixedWidth(52); spn_otm.setSuffix("%"); spn_otm.setSingleStep(0.05)
        spn_otm.setToolTip("0=ATM, 0.35=0.35% OTM 행사가 기준")

        spn_pre = QDoubleSpinBox(); spn_pre.setRange(0,100)
        spn_pre.setValue(getattr(slot,'pre_alert_pct',0.0))
        spn_pre.setFixedWidth(52); spn_pre.setSuffix("x"); spn_pre.setSingleStep(0.1)
        spn_pre.setToolTip("0=비활성, 배율3.0x → 2.7 설정 시 270%에서 사전경보")

        spn_max = QSpinBox(); spn_max.setRange(0,99)
        spn_max.setValue(getattr(slot,'max_alerts',10))
        spn_max.setFixedWidth(40); spn_max.setToolTip("0=무제한")

        chk_dup = QCheckBox(); chk_dup.setChecked(getattr(slot,'no_dup',True))
        chk_dup.setFixedWidth(38); chk_dup.setToolTip("체크=같은 구간 중복 알람 억제")

        btn_del = QPushButton("✕"); btn_del.setFixedWidth(28)

        row = dict(chk=chk, edt_s=edt_s, edt_e=edt_e, cmb_t=cmb_t,
                   spn_m=spn_m, spn_otm=spn_otm, spn_pre=spn_pre,
                   spn_max=spn_max, chk_dup=chk_dup, widget=row_w)
        btn_del.clicked.connect(lambda: self._del_slot_row(row))
        for w in [chk,edt_s,edt_e,cmb_t,spn_m,spn_otm,spn_pre,spn_max,chk_dup,btn_del]:
            h.addWidget(w)
        self._slot_vbox.insertWidget(self._slot_vbox.count()-1, row_w)
        self._rows.append(row)

    def _del_slot_row(self, row):
        row["widget"].setParent(None); self._rows.remove(row)

    def _load_rows(self):
        for slot in self._cfg.slots:
            self._add_slot_row(slot)

    def _load_preset(self):
        idx = self._cmb_preset.currentIndex()
        if idx == 0:
            return
        reply = QMessageBox.question(self, "템플릿 불러오기",
            "현재 구간 설정을 덮어씁니다. 계속할까요?",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for r in self._rows:
            r["widget"].setParent(None)
        self._rows.clear()
        for slot in make_preset(idx):
            self._add_slot_row(slot)

    # ── 기준가 수동 조정 박스 ─────────────────────────────────
    def _make_base_adjust_box(self):
        box = QGroupBox("기준가 수동 조정")
        h = QHBoxLayout(box)
        h.addWidget(QLabel("구간:"))
        self._cmb_adjust = QComboBox(); self._cmb_adjust.setFixedWidth(90)
        self._cmb_adjust.setToolTip("조정할 구간 선택")
        h.addWidget(self._cmb_adjust)

        btn_up = QPushButton("▲ +5pt"); btn_up.setFixedWidth(70)
        btn_dn = QPushButton("▼ -5pt"); btn_dn.setFixedWidth(70)
        btn_up.clicked.connect(lambda: self._adjust_base(+1))
        btn_dn.clicked.connect(lambda: self._adjust_base(-1))
        h.addWidget(btn_up); h.addWidget(btn_dn)

        self._lbl_adjust_result = QLabel(""); h.addWidget(self._lbl_adjust_result)
        h.addStretch()
        # 구간 콤보 갱신 타이머 (저장할 때도 갱신)
        self._refresh_adjust_combo()
        return box

    def _refresh_adjust_combo(self):
        self._cmb_adjust.clear()
        for r in self._rows:
            lbl = r["edt_l"].text().strip() if "edt_l" in r else ""
            start = r["edt_s"].text().strip()
            self._cmb_adjust.addItem(lbl or start)

    def _adjust_base(self, direction: int):
        if self._checker is None:
            self._lbl_adjust_result.setText("checker 없음")
            return
        label = self._cmb_adjust.currentText()
        msg = self._checker.adjust_base(label, direction)
        self._lbl_adjust_result.setText(msg[-30:])  # 짧게 표시

    # ── TG 포맷 박스 ─────────────────────────────────────────
    def _make_tg_box(self):
        box = QGroupBox("텔레그램 알림")
        h = QHBoxLayout(box)
        h.addWidget(QLabel("포맷:"))
        self._edt_fmt = QLineEdit(self._cfg.tg_fmt); h.addWidget(self._edt_fmt,1)
        return box

    # ── 저장/취소 버튼 바 ─────────────────────────────────────
    def _make_btn_bar(self):
        h = QHBoxLayout()
        btn_save   = QPushButton("💾 저장");  btn_save.setFixedHeight(28)
        btn_cancel = QPushButton("취소");     btn_cancel.setFixedHeight(28)
        btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self._reload)
        h.addStretch(); h.addWidget(btn_cancel); h.addWidget(btn_save)
        return h

    def _save(self):
        slots = []
        for r in self._rows:
            lbl = r.get("edt_l")
            slots.append(NightSlot(
                start_hhmm  = r["edt_s"].text().strip(),
                end_hhmm    = r["edt_e"].text().strip(),
                opt_type    = r["cmb_t"].currentText(),
                multiplier  = r["spn_m"].value(),
                otm_pct     = r["spn_otm"].value(),
                pre_alert_pct = r["spn_pre"].value(),
                max_alerts  = r["spn_max"].value(),
                no_dup      = r["chk_dup"].isChecked(),
                abs_price   = 0.0,
                enabled     = r["chk"].isChecked(),
                label       = lbl.text().strip() if lbl else "",
            ))
        self._cfg.slots      = slots
        self._cfg.base_type  = {0:"open",1:"prev_close",2:"manual"}.get(self._cmb_base.currentIndex(),"open")
        self._cfg.atm_auto   = self._chk_atm_auto.isChecked()
        self._cfg.atm_manual = self._spn_atm.value()
        self._cfg.tg_fmt     = self._edt_fmt.text().strip()
        save_config(self._cfg)
        self._refresh_adjust_combo()
        QMessageBox.information(self,"저장","템플릿 저장 완료!")

    def _reload(self):
        self._cfg = load_config()
        for r in self._rows: r["widget"].setParent(None)
        self._rows.clear(); self._load_rows()
        self._refresh_adjust_combo()
