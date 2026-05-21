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
        vbox = QVBoxLayout(box)

        # ── 행1: 기준가 종류 + ATM ──────────────────────────
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("기준가:"))
        self._cmb_base = QComboBox()
        self._cmb_base.addItems(["당일 22:30 시가 (자동)","전일 종가 (자동)","수동 입력"])
        self._cmb_base.setCurrentIndex({"open":0,"prev_close":1}.get(self._cfg.base_type,0))
        h1.addWidget(self._cmb_base)
        h1.addWidget(QLabel("ATM:"))
        self._chk_atm_auto = QCheckBox("자동")
        self._chk_atm_auto.setChecked(self._cfg.atm_auto)
        self._chk_atm_auto.toggled.connect(lambda c: self._spn_atm.setEnabled(not c))
        h1.addWidget(self._chk_atm_auto)
        self._spn_atm = QDoubleSpinBox()
        self._spn_atm.setRange(0, 99999)
        self._spn_atm.setValue(self._cfg.atm_manual)
        self._spn_atm.setEnabled(not self._cfg.atm_auto)
        self._spn_atm.setFixedWidth(90)
        h1.addWidget(self._spn_atm)
        h1.addStretch()
        vbox.addLayout(h1)

        # ── 행2: 프리미엄 자동탐색 ──────────────────────────
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("목표프리미엄:"))

        self._night_target_prem = QDoubleSpinBox()
        self._night_target_prem.setRange(0.01, 999.0)
        self._night_target_prem.setValue(2.0)
        self._night_target_prem.setSingleStep(0.25)
        self._night_target_prem.setDecimals(2)
        # ✅ FIX: 단위를 pt로 변경 (SPX 옵션 1pt = $100)
        self._night_target_prem.setSuffix(" pt")
        self._night_target_prem.setFixedWidth(80)
        self._night_target_prem.setToolTip(
            "SPX 옵션 프리미엄 (포인트 단위)\n"
            "예) 2.00pt = 실제 $200\n"
            "이 범위의 행사가를 ATM으로 자동 탐색합니다."
        )

        self._night_prem_tol = QDoubleSpinBox()
        self._night_prem_tol.setRange(1, 80)
        self._night_prem_tol.setValue(25)
        self._night_prem_tol.setSingleStep(5)
        self._night_prem_tol.setSuffix("%")
        self._night_prem_tol.setFixedWidth(62)
        self._night_prem_tol.setToolTip("허용 오차 %\n예) 2.00pt ±25% → 1.50~2.50pt 범위 탐색")

        # ✅ 범위 실시간 표시 레이블
        self._lbl_prem_range = QLabel("")
        self._lbl_prem_range.setStyleSheet("color:#888;font-size:9px;")
        def _update_range():
            t = self._night_target_prem.value()
            r = self._night_prem_tol.value() / 100
            self._lbl_prem_range.setText(f"({t*(1-r):.2f}~{t*(1+r):.2f}pt)")
        self._night_target_prem.valueChanged.connect(_update_range)
        self._night_prem_tol.valueChanged.connect(_update_range)
        _update_range()

        self._night_prem_type = QComboBox()
        self._night_prem_type.addItems(["P", "C", "both"])
        self._night_prem_type.setFixedWidth(48)
        self._night_prem_type.setToolTip("탐색 대상 옵션 종류")

        btn_find = QPushButton("🎯 행사가 탐색")
        btn_find.setFixedHeight(22)
        btn_find.setToolTip(
            "콜-풋탭 현재 시세에서 목표 프리미엄 범위에 맞는\n"
            "행사가를 찾아 ATM 값으로 자동 설정합니다.\n"
            "※ 콜-풋탭 체인 조회 후 사용하세요."
        )
        btn_find.clicked.connect(self._find_and_set_atm_by_premium)

        self._night_find_status = QLabel("")
        self._night_find_status.setStyleSheet("color:#90caf9; font-size:9px;")

        h2.addWidget(self._night_target_prem)
        h2.addWidget(QLabel("±"))
        h2.addWidget(self._night_prem_tol)
        h2.addWidget(self._lbl_prem_range)
        h2.addWidget(self._night_prem_type)
        h2.addWidget(btn_find)
        h2.addWidget(self._night_find_status)
        h2.addStretch()
        vbox.addLayout(h2)

        return box

    # ── 프리미엄 기반 ATM 자동 탐색 ───────────────────────────

    def set_main_window(self, mw):
        """
        메인윈도우 참조 주입.
        watch_alert_tab.py 에서 NightAlertTab 생성 후 호출:
            self._night_alert_tab.set_main_window(mw)
        콜-풋탭 시세 캐시(call_data / put_data)에 접근하기 위해 필요.
        """
        self._mw = mw

    def _find_and_set_atm_by_premium(self):
        """
        🎯 행사가 탐색 버튼 핸들러.

        동작 순서
        ---------
        1. mw.call_data / put_data 에서 mid=(bid+ask)/2 또는 last 조회
        2. 목표 프리미엄 ±허용오차 범위 필터
        3. 목표에 가장 가까운 행사가를 ATM 스핀박스에 설정
           + 자동 체크 해제(수동 모드로 전환)하여 값이 유지되게 함
        4. 결과 없으면 상태 라벨에 안내

        전제
        ----
        - mw 가 주입되어 있어야 함 (set_main_window 호출 필요)
        - 콜-풋탭에서 해당 만기 체인 조회가 완료되어 시세 캐시가 채워진 상태
        """
        mw = getattr(self, "_mw", None)
        if mw is None:
            self._night_find_status.setText("mw 미연결 — set_main_window 필요")
            return

        target   = self._night_target_prem.value()
        tol_pct  = self._night_prem_tol.value()
        opt_type = self._night_prem_type.currentText()   # "P" | "C" | "both"

        lo = target * (1 - tol_pct / 100)
        hi = target * (1 + tol_pct / 100)

        # 캐시 스캔
        candidates = []   # [(strike, side, mid), ...]

        def _scan(strikes, data_dict, side_label):
            if not strikes or not data_dict:
                return
            for req_id, info in data_dict.items():
                row_idx = info.get("row")
                if row_idx is None or row_idx >= len(strikes):
                    continue
                strike = strikes[row_idx]
                bid    = info.get("bid", 0) or 0
                ask    = info.get("ask", 0) or 0
                last   = info.get("last", 0) or 0
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                elif last > 0:
                    mid = last
                else:
                    continue
                if lo <= mid <= hi:
                    candidates.append((strike, side_label, mid))

        if opt_type in ("P", "both"):
            _scan(
                getattr(mw, "put_strikes", []),
                getattr(mw, "put_data",    {}),
                "P",
            )
        if opt_type in ("C", "both"):
            _scan(
                getattr(mw, "call_strikes", []),
                getattr(mw, "call_data",    {}),
                "C",
            )

        if not candidates:
            und = getattr(mw, "und_price", None)
            ref = f" (SPX≈{und:.0f})" if und else ""
            msg = f"{lo:.2f}~{hi:.2f}pt 범위 없음{ref}"
            self._night_find_status.setText(msg)
            return

        candidates.sort(key=lambda x: abs(x[2] - target))
        best_strike, best_side, best_mid = candidates[0]

        self._chk_atm_auto.setChecked(False)
        self._spn_atm.setEnabled(True)
        self._spn_atm.setValue(best_strike)

        result_strs = [f"{s}:{k:.0f}({m:.2f}pt)" for k, s, m in candidates[:3]]
        self._night_find_status.setText(f"✅ ATM={best_strike:.0f} [{best_side}] {best_mid:.2f}pt  후보: {', '.join(result_strs)}")

    # ── 감시 구간 박스 ────────────────────────────────────────
    def _make_slots_box(self):
        box = QGroupBox("새벽 감시 구간")
        vbox = QVBoxLayout(box)

        # 템플릿 프리셋 바
        preset_h = QHBoxLayout()
        preset_h.addWidget(QLabel("템플릿:"))
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems([
            "직접 설정",
            "30분 단위 야간 (22:30~05:00)",
            "45분 단위 야간 (22:30~05:00)",
            "장외 30분 (10:00~22:30, ES기준)",   # ✅ NEW
        ])
        preset_h.addWidget(self._cmb_preset)
        btn_preset = QPushButton("불러오기"); btn_preset.setFixedHeight(22)
        btn_preset.clicked.connect(self._load_preset)
        preset_h.addWidget(btn_preset); preset_h.addStretch()
        vbox.addLayout(preset_h)

        # 헤더
        hdr = QHBoxLayout()
        for txt, w in [
            ("ON",  24), ("시작", 52), ("종료", 52), ("대상", 40), ("배율", 46),
            ("OTM%", 40), ("사전%", 40), ("최대", 32), ("중복", 28),
            ("ES",  24), ("추적행사가", 75), ("상태", 22), ("", 22),
        ]:
            l = QLabel(txt); l.setFixedWidth(w); l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet("font-size:9px;color:#aaa;")
            hdr.addWidget(l)
        vbox.addLayout(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200); scroll.setMaximumHeight(340)
        self._slot_container = QWidget()
        self._slot_vbox = QVBoxLayout(self._slot_container)
        self._slot_vbox.setSpacing(3); self._slot_vbox.addStretch()
        scroll.setWidget(self._slot_container); vbox.addWidget(scroll)

        btn = QPushButton("＋ 구간 추가"); btn.setFixedHeight(24)
        btn.clicked.connect(self._add_slot_row); vbox.addWidget(btn)

        # ✅ NEW: 추적 행사가 갱신 타이머 (10초)
        from PyQt5.QtCore import QTimer
        self._track_timer = QTimer(self)
        self._track_timer.setInterval(10_000)
        self._track_timer.timeout.connect(self._refresh_tracked)
        self._track_timer.start()

        return box

    def _refresh_tracked(self):
        """10초마다 추적 행사가 + 신호등 갱신."""
        if self._checker is None:
            return
        for r in self._rows:
            lbl_track  = r.get("lbl_track")
            lbl_status = r.get("lbl_status")
            if lbl_track is None:
                continue

            start_txt = r["edt_s"].text().strip()
            rt = None
            for label, slot in self._checker._slots.items():
                if slot.start_hhmm == start_txt or label == start_txt:
                    rt = slot
                    break

            # ── 신호등 갱신 ────────────────────────────────
            if lbl_status is not None:
                if rt is None or not r["chk"].isChecked():
                    # 비활성
                    lbl_status.setStyleSheet("color:#555;font-size:14px;")
                    lbl_status.setToolTip("⚫ 비활성")
                else:
                    is_active = rt.is_active_now() if hasattr(rt, "is_active_now") else False
                    in_sample = rt.is_in_sampling_window() if hasattr(rt, "is_in_sampling_window") else False
                    # 마지막 알람 발생 여부 (1분 이내 = 빨간불)
                    last_fired = self._checker._fired.get(rt.label or start_txt)
                    from datetime import datetime
                    just_fired = (
                        last_fired is not None and
                        (datetime.now() - last_fired).total_seconds() < 60
                    )
                    if just_fired:
                        lbl_status.setStyleSheet("color:#ff1744;font-size:14px;")
                        lbl_status.setToolTip("🔴 알람 발생!")
                    elif is_active:
                        lbl_status.setStyleSheet("color:#00e676;font-size:14px;")
                        lbl_status.setToolTip("🟢 감시중")
                    elif in_sample:
                        lbl_status.setStyleSheet("color:#ffd740;font-size:14px;")
                        lbl_status.setToolTip("🟡 기준가 수집중")
                    else:
                        lbl_status.setStyleSheet("color:#555;font-size:14px;")
                        lbl_status.setToolTip("⚫ 대기중")

            # ── 추적 행사가 갱신 ────────────────────────────
            if rt and rt.tracked_strike > 0:
                lb = self._checker._last_best.get(rt.label or rt.start_hhmm)
                pct_now = f" {lb[2]:.0f}%" if lb else ""
                lbl_track.setText(f"{rt.tracked_type}{int(rt.tracked_strike)}{pct_now}")
                color = "#ff8a65" if lb and lb[2] >= rt.multiplier * 100 else "#90caf9"
                lbl_track.setStyleSheet(f"color:{color};font-size:9px;font-weight:bold;")
            else:
                lbl_track.setText("—")
                lbl_track.setStyleSheet("color:#555;font-size:9px;")

    def _add_slot_row(self, slot=None):
        if slot is None: slot = NightSlot()
        row_w = QWidget(); h = QHBoxLayout(row_w)
        h.setContentsMargins(0,0,0,0); h.setSpacing(2)

        chk   = QCheckBox(); chk.setChecked(slot.enabled); chk.setFixedWidth(24)

        from night_alert_template import parse_hhmm
        edt_s = QLineEdit(slot.start_hhmm); edt_s.setFixedWidth(52)
        edt_e = QLineEdit(slot.end_hhmm);   edt_e.setFixedWidth(52)
        edt_s.setPlaceholderText("0930")
        edt_e.setPlaceholderText("1030")
        edt_s.editingFinished.connect(lambda e=edt_s: e.setText(parse_hhmm(e.text())))
        edt_e.editingFinished.connect(lambda e=edt_e: e.setText(parse_hhmm(e.text())))

        cmb_t = QComboBox(); cmb_t.addItems(["P","C","both"]); cmb_t.setFixedWidth(40)
        cmb_t.setCurrentText(slot.opt_type)

        spn_m = QDoubleSpinBox(); spn_m.setRange(1,100); spn_m.setValue(slot.multiplier)
        spn_m.setFixedWidth(46); spn_m.setSuffix("x")

        spn_otm = QDoubleSpinBox(); spn_otm.setRange(0,5)
        spn_otm.setValue(getattr(slot,'otm_pct',0.0))
        spn_otm.setFixedWidth(40); spn_otm.setSuffix("%"); spn_otm.setSingleStep(0.05)
        spn_otm.setToolTip("0=ATM, 0.35=0.35% OTM 행사가 기준")

        spn_pre = QDoubleSpinBox(); spn_pre.setRange(0,100)
        spn_pre.setValue(getattr(slot,'pre_alert_pct',0.0))
        spn_pre.setFixedWidth(40); spn_pre.setSuffix("x"); spn_pre.setSingleStep(0.1)
        spn_pre.setToolTip(
            "사전경보 배율\n"
            "예) 본알림 3.0x, 사전경보 2.7 → 270% 도달시 pre 메시지 발송\n"
            "0=비활성"
        )

        spn_max = QSpinBox(); spn_max.setRange(0,99)
        spn_max.setValue(getattr(slot,'max_alerts',10))
        spn_max.setFixedWidth(32); spn_max.setToolTip("0=무제한")

        chk_dup = QCheckBox(); chk_dup.setChecked(getattr(slot,'no_dup',True))
        chk_dup.setFixedWidth(28); chk_dup.setToolTip("체크=같은 구간 중복 알람 억제")

        chk_es = QCheckBox(); chk_es.setChecked(getattr(slot,'use_es',False))
        chk_es.setFixedWidth(24)
        chk_es.setToolTip("ES 선물 기준 행사가 (장외시간)\nES - 25pt 오프셋 적용")

        lbl_track = QLabel("—"); lbl_track.setFixedWidth(75)
        lbl_track.setAlignment(Qt.AlignCenter)
        lbl_track.setStyleSheet("color:#555;font-size:9px;")
        lbl_track.setToolTip("현재 가장 높은 상승률 행사가 (10초 갱신)")

        lbl_status = QLabel("●"); lbl_status.setFixedWidth(22)
        lbl_status.setAlignment(Qt.AlignCenter)
        lbl_status.setStyleSheet("color:#555;font-size:12px;")
        lbl_status.setToolTip("⚫ 비활성  🟢 감시중  🔴 알람발생")

        btn_del = QPushButton("✕"); btn_del.setFixedWidth(22)

        row = dict(chk=chk, edt_s=edt_s, edt_e=edt_e, cmb_t=cmb_t,
                   spn_m=spn_m, spn_otm=spn_otm, spn_pre=spn_pre,
                   spn_max=spn_max, chk_dup=chk_dup, chk_es=chk_es,
                   lbl_track=lbl_track, lbl_status=lbl_status, widget=row_w)
        btn_del.clicked.connect(lambda: self._del_slot_row(row))
        for w in [chk,edt_s,edt_e,cmb_t,spn_m,spn_otm,spn_pre,spn_max,
                  chk_dup,chk_es,lbl_track,lbl_status,btn_del]:
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
        from night_alert_template import parse_hhmm
        slots = []
        for r in self._rows:
            lbl = r.get("edt_l")
            slots.append(NightSlot(
                start_hhmm  = parse_hhmm(r["edt_s"].text()),   # ✅ 저장 시에도 자동 파싱
                end_hhmm    = parse_hhmm(r["edt_e"].text()),
                opt_type    = r["cmb_t"].currentText(),
                multiplier  = r["spn_m"].value(),
                otm_pct     = r["spn_otm"].value(),
                pre_alert_pct = r["spn_pre"].value(),
                max_alerts  = r["spn_max"].value(),
                no_dup      = r["chk_dup"].isChecked(),
                abs_price   = 0.0,
                enabled     = r["chk"].isChecked(),
                label       = lbl.text().strip() if lbl else "",
                use_es      = r["chk_es"].isChecked(),   # ✅ NEW
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
