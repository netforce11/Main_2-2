"""
tab_options_watch.py — 감시 시스템  v6.4
════════════════════════════════════════════════════════════════
  CallPutGrid 에서 분리 (tab_options.py 에서 mixin으로 사용)

  포함 기능:
  - _build_watch_widget()   감시설정+알람로그+등록목록 통합 탭 위젯
  - _build_watch_tab()      감시 조건 / AND 조건 탭 내용
  - _build_log_tab()        알람 로그 + 사운드 탭 내용
  - _build_rules_tab()      등록된 감시 목록 탭 내용
  - _on_watch_font_change / _apply_font_to_widget
  - _pick_alert_sound / _clear_alert_sound / _play_alert_sound
  - _add_watch_rule / _del_watch_rule / _clear_watch_rules
  - _eval_op / _check_watch_rules
  - _load_watch_log / _open_watch_log_folder
════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QTextEdit, QCheckBox, QTabWidget,
    QSlider, QFileDialog, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

from core import make_table, tbl_set, ts, SAVE_DIR


class WatchMixin:
    """감시 시스템 전용 메서드 모음. CallPutGrid 에 mixin된다."""

    # ─────────────────────────────────────────────────────────
    # 통합 감시 위젯 빌더  (감시설정 | 알람로그 | 등록목록 탭)
    # ─────────────────────────────────────────────────────────
    def _build_watch_widget(self) -> QWidget:
        """감시설정 + 알람로그 + 등록목록을 QTabWidget 하나로 통합."""
        outer = QGroupBox("🔔 감시")
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(4, 6, 4, 4)
        outer_v.setSpacing(2)

        _tab_style = (
            "QTabWidget::pane{border:1px solid #2a2a5a;background:#07070f;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:5px 10px;"
            "border:1px solid #2a2a5a;border-bottom:none;font-size:12px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;font-weight:bold;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")

        self._watch_tabs = QTabWidget()
        self._watch_tabs.setStyleSheet(_tab_style)

        # 탭1: 감시 조건 설정
        tab_cond = self._build_watch_tab()
        self._watch_tabs.addTab(tab_cond, "🔔 조건 설정")

        # 탭2: 알람 로그
        tab_log = self._build_log_tab()
        self._watch_tabs.addTab(tab_log, "📋 알람 로그")

        # 탭3: 등록된 감시 목록
        tab_rules = self._build_rules_tab()
        self._watch_tabs.addTab(tab_rules, "📌 등록 목록")

        outer_v.addWidget(self._watch_tabs)
        self._watch_gb = outer
        return outer

    # ─────────────────────────────────────────────────────────
    # 탭1: 감시 조건 설정
    # ─────────────────────────────────────────────────────────
    def _build_watch_tab(self) -> QWidget:
        w = QWidget()
        root_v = QVBoxLayout(w)
        root_v.setSpacing(4)
        root_v.setContentsMargins(6, 6, 6, 6)

        # ── 화면설정 저장/불러오기 ──────────────────────────
        layout_row = QHBoxLayout(); layout_row.setSpacing(3)
        layout_row.addWidget(QLabel("화면설정:", styleSheet="color:#aaa;font-size:10px;border:none;"))
        self.combo_layout_name = QLineEdit()
        self.combo_layout_name.setPlaceholderText("프리셋 이름")
        self.combo_layout_name.setFixedHeight(22); self.combo_layout_name.setFixedWidth(90)
        self.combo_layout_name.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #333;"
            "font-size:10px;border-radius:2px;padding:1px 3px;")
        self.combo_layout_preset = QComboBox()
        self.combo_layout_preset.setFixedHeight(22); self.combo_layout_preset.setMinimumWidth(80)
        self.combo_layout_preset.setStyleSheet(
            "QComboBox{background:#12122a;color:#90caf9;border:1px solid #3a3a6a;"
            "font-size:10px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#90caf9;font-size:10px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        for lbl_t, fn, col in [
            ("💾 저장", self._save_layout_preset, "#1a3a6b"),
            ("📂 불러오기", self._load_layout_preset, "#2d2d2d"),
        ]:
            b = QPushButton(lbl_t); b.setFixedHeight(22)
            b.setStyleSheet(f"background:{col};color:#90caf9;font-size:10px;padding:1px 5px;border-radius:2px;")
            b.clicked.connect(fn); layout_row.addWidget(b)
        layout_row.addWidget(self.combo_layout_preset)
        btn_del = QPushButton("✕"); btn_del.setFixedHeight(22); btn_del.setFixedWidth(22)
        btn_del.setStyleSheet("background:#4a1a1a;color:#ff8888;font-size:10px;border-radius:2px;")
        btn_del.setToolTip("선택 프리셋 삭제"); btn_del.clicked.connect(self._del_layout_preset)
        layout_row.addWidget(self.combo_layout_name)
        layout_row.addWidget(btn_del)
        root_v.addLayout(layout_row)
        QTimer.singleShot(200, self._refresh_layout_presets)

        # ── 폰트 슬라이더 ───────────────────────────────────
        font_row = QHBoxLayout(); font_row.setSpacing(4)
        font_row.addWidget(QLabel("글씨 크기:", styleSheet="color:#aaa;font-size:11px;border:none;"))
        self._watch_font_slider = QSlider(Qt.Horizontal)
        self._watch_font_slider.setRange(9, 22); self._watch_font_slider.setValue(13)
        self._watch_font_slider.setFixedWidth(90)
        self._watch_font_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
            "QSlider::handle:horizontal{background:#ffd700;width:12px;height:12px;"
            "margin:-4px 0;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#3a6a9a;border-radius:2px;}")
        self._watch_font_size_lbl = QLabel("13px")
        self._watch_font_size_lbl.setStyleSheet("color:#ffd700;font-size:10px;border:none;min-width:28px;")
        self._watch_font_slider.valueChanged.connect(self._on_watch_font_change)
        font_row.addWidget(self._watch_font_slider)
        font_row.addWidget(self._watch_font_size_lbl)
        font_row.addStretch()
        root_v.addLayout(font_row)

        # ── 대상 행사가 ─────────────────────────────────────
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("대상:"))
        self.watch_side = QLineEdit(); self.watch_side.setReadOnly(True)
        self.watch_side.setPlaceholderText("C/P"); self.watch_side.setFixedWidth(30)
        self.watch_strike = QLineEdit(); self.watch_strike.setReadOnly(True)
        self.watch_strike.setPlaceholderText("행사가"); self.watch_strike.setFixedWidth(60)
        self.watch_side.setStyleSheet("color:#ffd700;font-weight:bold;")
        self.watch_strike.setStyleSheet("color:#ffd700;font-weight:bold;")
        row0.addWidget(self.watch_side); row0.addWidget(self.watch_strike); row0.addStretch()
        root_v.addLayout(row0)

        # ── 공통 스타일 ─────────────────────────────────────
        _chk_s = "color:#ffd700;font-size:13px;font-weight:bold;"
        _val_s = ("background:#0a0a1e;color:#fff;"
                  "border:1px solid #444;font-size:13px;padding:1px 4px;")
        _comb_s = (
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #4a4a7a;"
            "border-radius:3px;font-size:13px;padding:1px 4px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;font-size:13px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        _OPS = ["<", "<=", ">", ">="]
        _ROW_H = 26

        # ── 감시조건 + AND조건 통합 GroupBox ─────────────────
        cond_gb = QGroupBox("감시 조건 / AND 조건")
        cond_gb.setStyleSheet(
            "QGroupBox{font-size:12px;color:#90caf9;font-weight:bold;"
            "border:1px solid #3a3a6a;border-radius:4px;margin-top:6px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;top:0px;}")
        cond_gl = QGridLayout(cond_gb)
        cond_gl.setVerticalSpacing(6); cond_gl.setHorizontalSpacing(6)
        cond_gl.setContentsMargins(8, 12, 8, 8)
        cond_gl.setColumnMinimumWidth(0, 58)
        cond_gl.setColumnMinimumWidth(1, 52)
        cond_gl.setColumnMinimumWidth(2, 72)
        cond_gl.setColumnStretch(3, 1)

        # 헤더 행0
        lbl_cond = QLabel("▶ 감시 조건")
        lbl_cond.setStyleSheet("color:#ffd700;font-size:13px;font-weight:bold;border:none;")
        lbl_cond.setFixedHeight(22)
        cond_gl.addWidget(lbl_cond, 0, 0, 1, 3)
        cond_gl.setRowMinimumHeight(0, 22)

        # 감시조건 위젯
        self.wc_price_chk = QCheckBox("가격"); self.wc_price_chk.setChecked(True)
        self.wc_price_op  = QComboBox(); self.wc_price_op.addItems(_OPS)
        self.wc_price_val = QLineEdit(); self.wc_price_val.setPlaceholderText("$")

        self.wc_delta_chk = QCheckBox("Delta")
        self.wc_delta_op  = QComboBox(); self.wc_delta_op.addItems(_OPS)
        self.wc_delta_val = QLineEdit(); self.wc_delta_val.setPlaceholderText("0.00")

        self.wc_theta_chk = QCheckBox("Theta")
        self.wc_theta_op  = QComboBox(); self.wc_theta_op.addItems(_OPS)
        self.wc_theta_val = QLineEdit(); self.wc_theta_val.setPlaceholderText("0.00")

        self.wc_gamma_chk = QCheckBox("Gamma")
        self.wc_gamma_op  = QComboBox(); self.wc_gamma_op.addItems(_OPS)
        self.wc_gamma_val = QLineEdit(); self.wc_gamma_val.setPlaceholderText("0.00")

        for row_i, (chk, op, val) in enumerate([
            (self.wc_price_chk, self.wc_price_op, self.wc_price_val),
            (self.wc_delta_chk, self.wc_delta_op, self.wc_delta_val),
            (self.wc_theta_chk, self.wc_theta_op, self.wc_theta_val),
            (self.wc_gamma_chk, self.wc_gamma_op, self.wc_gamma_val),
        ], start=1):
            chk.setStyleSheet(_chk_s); chk.setFixedHeight(_ROW_H)
            op.setStyleSheet(_comb_s); op.setFixedWidth(52); op.setFixedHeight(_ROW_H)
            val.setStyleSheet(_val_s); val.setFixedHeight(_ROW_H)
            cond_gl.addWidget(chk, row_i, 0)
            cond_gl.addWidget(op,  row_i, 1)
            cond_gl.addWidget(val, row_i, 2)
            cond_gl.setRowMinimumHeight(row_i, _ROW_H)

        # 구분선 행5
        sep = QLabel(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:#2a2a5a;border:none;")
        cond_gl.addWidget(sep, 5, 0, 1, 3)
        cond_gl.setRowMinimumHeight(5, 8)

        # AND 헤더 행6
        lbl_and = QLabel("▶ AND 조건")
        lbl_and.setStyleSheet("color:#90caf9;font-size:13px;font-weight:bold;border:none;")
        lbl_and.setFixedHeight(22)
        cond_gl.addWidget(lbl_and, 6, 0, 1, 3)
        cond_gl.setRowMinimumHeight(6, 22)

        # AND 조건 위젯
        self.wa_time_chk  = QCheckBox("시간")
        self.wa_time_op   = QComboBox(); self.wa_time_op.addItems(_OPS); self.wa_time_op.setCurrentText(">=")
        self.wa_time_val  = QLineEdit(); self.wa_time_val.setPlaceholderText("HH:MM ET")

        self.wa_delta_chk = QCheckBox("Delta")
        self.wa_delta_op  = QComboBox(); self.wa_delta_op.addItems(_OPS)
        self.wa_delta_val = QLineEdit(); self.wa_delta_val.setPlaceholderText("0.00")

        self.wa_gamma_chk = QCheckBox("Gamma")
        self.wa_gamma_op  = QComboBox(); self.wa_gamma_op.addItems(_OPS)
        self.wa_gamma_val = QLineEdit(); self.wa_gamma_val.setPlaceholderText("0.00")

        self.wa_theta_chk = QCheckBox("Theta")
        self.wa_theta_op  = QComboBox(); self.wa_theta_op.addItems(_OPS)
        self.wa_theta_val = QLineEdit(); self.wa_theta_val.setPlaceholderText("0.00")

        for row_i, (chk, op, val) in enumerate([
            (self.wa_time_chk,  self.wa_time_op,  self.wa_time_val),
            (self.wa_delta_chk, self.wa_delta_op, self.wa_delta_val),
            (self.wa_gamma_chk, self.wa_gamma_op, self.wa_gamma_val),
            (self.wa_theta_chk, self.wa_theta_op, self.wa_theta_val),
        ], start=7):
            chk.setStyleSheet(_chk_s); chk.setFixedHeight(_ROW_H)
            op.setStyleSheet(_comb_s); op.setFixedWidth(52); op.setFixedHeight(_ROW_H)
            val.setStyleSheet(_val_s); val.setFixedHeight(_ROW_H)
            cond_gl.addWidget(chk, row_i, 0)
            cond_gl.addWidget(op,  row_i, 1)
            cond_gl.addWidget(val, row_i, 2)
            cond_gl.setRowMinimumHeight(row_i, _ROW_H)

        root_v.addWidget(cond_gb)

        # ── 감시 등록 버튼 ───────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        btn_add = QPushButton("➕ 감시 등록")
        btn_add.setStyleSheet("background:#1a5c2e;color:#00ff88;font-weight:bold;padding:6px;font-size:12px;")
        btn_add.clicked.connect(self._add_watch_rule)
        btn_clr = QPushButton("🗑 전체 삭제")
        btn_clr.setStyleSheet("background:#5a1a1a;color:#ff6666;font-weight:bold;padding:6px;font-size:12px;")
        btn_clr.clicked.connect(self._clear_watch_rules)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_clr)
        root_v.addLayout(btn_row)
        root_v.addStretch()

        self._watch_gb_root = root_v
        return w

    # ─────────────────────────────────────────────────────────
    # 탭2: 알람 로그
    # ─────────────────────────────────────────────────────────
    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        # 저장 경로 표시
        self.lbl_watch_file = QLabel(f"파일: {self._watch_log_file}")
        self.lbl_watch_file.setStyleSheet("color:#555;font-size:9px;border:none;")
        self.lbl_watch_file.setWordWrap(True)
        v.addWidget(self.lbl_watch_file)

        self.watch_log_box = QTextEdit()
        self.watch_log_box.setReadOnly(True)
        self.watch_log_box.setStyleSheet(
            "background:#05050f;color:#00ff88;font-size:12px;"
            "border:1px solid #1a3a1a;font-family:monospace;")
        v.addWidget(self.watch_log_box, 1)

        # 사운드 설정
        sound_row = QHBoxLayout(); sound_row.setSpacing(4)
        sound_row.addWidget(QLabel("🔊 알람음:", styleSheet="color:#aaa;font-size:11px;border:none;"))
        self.lbl_sound_file = QLabel("기본 비프음")
        self.lbl_sound_file.setStyleSheet(
            "color:#ffd700;font-size:10px;border:1px solid #333;"
            "border-radius:3px;padding:1px 4px;background:#0a0a1e;")
        self.lbl_sound_file.setMaximumWidth(140)
        btn_pick  = QPushButton("📂 파일 선택"); btn_pick.setFixedHeight(22)
        btn_pick.setStyleSheet("background:#1a3a6b;color:#90caf9;font-size:10px;padding:2px 5px;")
        btn_pick.clicked.connect(self._pick_alert_sound)
        btn_test  = QPushButton("▶ 테스트"); btn_test.setFixedHeight(22)
        btn_test.setStyleSheet("background:#2d2d2d;color:#ffd700;font-size:10px;padding:2px 5px;")
        btn_test.clicked.connect(self._play_alert_sound)
        btn_clr_s = QPushButton("✕"); btn_clr_s.setFixedHeight(22); btn_clr_s.setFixedWidth(22)
        btn_clr_s.setStyleSheet("background:#4a1a1a;color:#ff8888;font-size:10px;")
        btn_clr_s.setToolTip("기본 비프음으로 초기화")
        btn_clr_s.clicked.connect(self._clear_alert_sound)
        sound_row.addWidget(self.lbl_sound_file, 1)
        for b in (btn_pick, btn_test, btn_clr_s): sound_row.addWidget(b)
        v.addLayout(sound_row)

        btn_row2 = QHBoxLayout()
        btn_clr_log = QPushButton("🗑 화면 지우기")
        btn_clr_log.setStyleSheet("background:#2d2d2d;color:#aaa;font-size:10px;padding:3px;")
        btn_clr_log.clicked.connect(self.watch_log_box.clear)
        btn_open = QPushButton("📁 파일 열기")
        btn_open.setStyleSheet("background:#1a3a6b;color:#90caf9;font-size:10px;padding:3px;")
        btn_open.clicked.connect(self._open_watch_log_folder)
        btn_load = QPushButton("📂 결과 불러오기")
        btn_load.setStyleSheet("background:#2d4a6b;color:#90caf9;font-size:10px;padding:3px;")
        btn_load.clicked.connect(self._load_watch_log)
        btn_row2.addWidget(btn_clr_log); btn_row2.addWidget(btn_open)
        btn_row2.addWidget(btn_load); btn_row2.addStretch()
        v.addLayout(btn_row2)
        return w

    # ─────────────────────────────────────────────────────────
    # 탭3: 등록된 감시 목록
    # ─────────────────────────────────────────────────────────
    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(QLabel("더블클릭 = 삭제", styleSheet="color:#666;font-size:10px;border:none;"))
        self.tbl_watch_rules = make_table(["대상", "조건 요약", "AND 요약", "상태"])
        self.tbl_watch_rules.itemDoubleClicked.connect(
            lambda it: self._del_watch_rule(it.row()))
        v.addWidget(self.tbl_watch_rules, 1)
        btn_row = QHBoxLayout()
        btn_clr = QPushButton("🗑 전체 삭제")
        btn_clr.setStyleSheet("background:#5a1a1a;color:#ff6666;font-weight:bold;padding:5px;")
        btn_clr.clicked.connect(self._clear_watch_rules)
        btn_row.addWidget(btn_clr); btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    # ─────────────────────────────────────────────────────────
    # 폰트 변경
    # ─────────────────────────────────────────────────────────
    def _on_watch_font_change(self, value: int):
        self._watch_font_size_lbl.setText(f"{value}px")
        if hasattr(self, '_watch_gb') and self._watch_gb:
            self._apply_font_to_widget(self._watch_gb, value)

    def _apply_font_to_widget(self, widget, size: int):
        skip = (self._watch_font_slider, self._watch_font_size_lbl)
        if widget in skip: return
        if hasattr(widget, 'font'):
            f = widget.font(); f.setPointSize(size); widget.setFont(f)
        for child in widget.findChildren(QWidget):
            if child not in skip:
                f = child.font(); f.setPointSize(size); child.setFont(f)

    # ─────────────────────────────────────────────────────────
    # 알람 사운드
    # ─────────────────────────────────────────────────────────
    def _pick_alert_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택", str(Path.home()),
            "WAV 파일 (*.wav);;모든 파일 (*)")
        if not path: return
        self._alert_sound_path = path
        fname = Path(path).name
        self.lbl_sound_file.setText(fname)
        self.lbl_sound_file.setToolTip(path)
        self._log(f"🔊 알람음 설정: {fname}")

    def _clear_alert_sound(self):
        self._alert_sound_path = ""
        self.lbl_sound_file.setText("기본 비프음")
        self.lbl_sound_file.setToolTip("")
        self._log("🔊 알람음: 기본 비프음으로 초기화")

    def _play_alert_sound(self):
        if self._alert_sound_path:
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(self._alert_sound_path); return
            except ImportError: pass
            try:
                import winsound
                winsound.PlaySound(self._alert_sound_path,
                                   winsound.SND_FILENAME | winsound.SND_ASYNC); return
            except Exception: pass
            try:
                import subprocess, sys
                cmd = ["afplay" if sys.platform == "darwin" else "aplay",
                       self._alert_sound_path]
                subprocess.Popen(cmd); return
            except Exception as e:
                self._log(f"🔊 사운드 재생 실패: {e}")
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.beep()
        except Exception: pass

    # ─────────────────────────────────────────────────────────
    # 감시 규칙 등록 / 삭제
    # ─────────────────────────────────────────────────────────
    def _add_watch_rule(self):
        side   = self.watch_side.text().strip()
        strike = self.watch_strike.text().strip()
        if not side or not strike:
            QMessageBox.warning(self, "입력 오류", "콜-풋 테이블에서 행을 먼저 클릭하세요."); return

        def _flt(chk, ed):
            if not chk.isChecked(): return None
            try: return float(ed.text().strip())
            except: return None

        cond = {
            "price": _flt(self.wc_price_chk, self.wc_price_val),
            "price_op": self.wc_price_op.currentText(),
            "delta": _flt(self.wc_delta_chk, self.wc_delta_val),
            "delta_op": self.wc_delta_op.currentText(),
            "theta": _flt(self.wc_theta_chk, self.wc_theta_val),
            "theta_op": self.wc_theta_op.currentText(),
            "gamma": _flt(self.wc_gamma_chk, self.wc_gamma_val),
            "gamma_op": self.wc_gamma_op.currentText(),
        }
        and_c = {
            "time":     self.wa_time_val.text().strip() if self.wa_time_chk.isChecked() else None,
            "time_op":  self.wa_time_op.currentText(),
            "delta":    _flt(self.wa_delta_chk, self.wa_delta_val),
            "delta_op": self.wa_delta_op.currentText(),
            "gamma":    _flt(self.wa_gamma_chk, self.wa_gamma_val),
            "gamma_op": self.wa_gamma_op.currentText(),
            "theta":    _flt(self.wa_theta_chk, self.wa_theta_val),
            "theta_op": self.wa_theta_op.currentText(),
        }
        if all(cond.get(k) is None for k in ("price","delta","theta","gamma")):
            QMessageBox.warning(self, "입력 오류",
                "감시 조건(가격/Delta/Theta/Gamma)을 하나 이상 체크하고 값을 입력하세요."); return

        has_and = any(and_c.get(k) is not None for k in ("time","delta","gamma","theta"))
        rule = {"side": side, "strike": strike,
                "cond": cond, "and": and_c, "has_and": has_and, "fired": False}
        idx = len(self._watch_rules)
        self._watch_rules.append(rule)
        self._watch_prev[idx] = {"price": None, "delta": None, "theta": None, "gamma": None}

        r = self.tbl_watch_rules.rowCount()
        self.tbl_watch_rules.insertRow(r)
        tbl_set(self.tbl_watch_rules, r, 0, f"{side} {strike}", "#ffd700")

        cond_parts = []
        if cond["price"] is not None: cond_parts.append(f"P{cond['price_op']}{cond['price']:.2f}")
        if cond["delta"] is not None: cond_parts.append(f"Δ{cond['delta_op']}{cond['delta']:.3f}")
        if cond["theta"] is not None: cond_parts.append(f"θ{cond['theta_op']}{cond['theta']:.3f}")
        if cond["gamma"] is not None: cond_parts.append(f"γ{cond['gamma_op']}{cond['gamma']:.4f}")
        tbl_set(self.tbl_watch_rules, r, 1, " & ".join(cond_parts) or "―")

        and_parts = []
        if and_c["time"]:  and_parts.append(f"T{and_c['time_op']}{and_c['time']}")
        if and_c["delta"] is not None: and_parts.append(f"Δ{and_c['delta_op']}{and_c['delta']:.3f}")
        if and_c["gamma"] is not None: and_parts.append(f"γ{and_c['gamma_op']}{and_c['gamma']:.4f}")
        if and_c["theta"] is not None: and_parts.append(f"θ{and_c['theta_op']}{and_c['theta']:.3f}")
        tbl_set(self.tbl_watch_rules, r, 2, " & ".join(and_parts) or "―", "#aaa")
        tbl_set(self.tbl_watch_rules, r, 3, "👁 감시 중", "#00ff88")
        # 등록 목록 탭으로 자동 전환
        self._watch_tabs.setCurrentIndex(2)
        self._log(f"감시 등록: {side} {strike}  조건={cond_parts}")

    def _del_watch_rule(self, row):
        if row < 0 or row >= len(self._watch_rules): return
        self._watch_rules.pop(row)
        self._watch_prev.pop(row, None)
        new_prev = {(k if k < row else k-1): v
                    for k, v in self._watch_prev.items() if k != row}
        self._watch_prev = new_prev
        self.tbl_watch_rules.removeRow(row)
        self._log(f"감시 삭제: row {row}")

    def _clear_watch_rules(self):
        self._watch_rules.clear(); self._watch_prev.clear()
        self.tbl_watch_rules.setRowCount(0)
        self._log("감시 전체 삭제")

    # ─────────────────────────────────────────────────────────
    # 감시 조건 평가
    # ─────────────────────────────────────────────────────────
    def _eval_op(self, actual, op: str, threshold) -> bool:
        if actual is None or threshold is None: return False
        if op in ("≤", "<="): return actual <= threshold
        elif op in ("≥", ">="): return actual >= threshold
        elif op == "<": return actual < threshold
        elif op == ">": return actual > threshold
        return False

    def _check_watch_rules(self):
        if not self._watch_rules: return
        from core import REQ_CALL, REQ_PUT
        now_et  = datetime.utcnow() - timedelta(hours=4 if self._is_dst() else 5)
        now_str = now_et.strftime("%H:%M")

        for idx, rule in enumerate(self._watch_rules):
            if rule["fired"]: continue
            side     = rule["side"]
            strike_f = float(rule["strike"])
            rid_base = REQ_CALL if side == "C" else REQ_PUT
            strikes  = self.call_strikes if side == "C" else self.put_strikes
            data_map = self.call_data if side == "C" else self.put_data
            tbl      = self.tbl_call if side == "C" else self.tbl_put

            rid = next((rid_base + i for i, st in enumerate(strikes)
                        if abs(st - strike_f) < 0.5), None)
            if rid is None: continue

            cur_price = data_map.get(rid, {}).get("last")
            row_idx   = rid - rid_base

            def _cell(r, c):
                it = tbl.item(r, c)
                if it:
                    try: return float(it.text().replace("―","").replace("+",""))
                    except: pass
                return None

            cur_delta = _cell(row_idx, 3)
            cur_theta = _cell(row_idx, 4)
            cur_gamma = _cell(row_idx, 5)
            cond = rule["cond"]; and_c = rule["and"]

            cond_ok = True
            if cond.get("price") is not None:
                if not self._eval_op(cur_price, cond["price_op"], cond["price"]): cond_ok = False
            if cond.get("delta") is not None:
                val = abs(cur_delta) if cur_delta is not None else None
                thr = abs(cond["delta"])
                op_d = cond.get("delta_op", "<=")
                if op_d in ("<=","≤"):
                    if val is None or val > thr: cond_ok = False
                else:
                    if val is None or val < thr: cond_ok = False
            if cond.get("theta") is not None:
                if not self._eval_op(cur_theta, cond["theta_op"], cond["theta"]): cond_ok = False
            if cond.get("gamma") is not None:
                if not self._eval_op(cur_gamma, cond["gamma_op"], cond["gamma"]): cond_ok = False
            if not cond_ok: continue

            has_and = rule.get("has_and", False)
            and_ok  = True
            if has_and:
                if and_c.get("time"):
                    try:
                        tp = and_c["time"].split(":")
                        t_now = now_et.hour * 60 + now_et.minute
                        t_req = int(tp[0]) * 60 + int(tp[1])
                        op_t  = and_c.get("time_op", ">=")
                        if op_t in (">=","≥"):
                            if t_now < t_req: and_ok = False
                        else:
                            if t_now > t_req: and_ok = False
                    except: pass
                if and_c.get("delta") is not None:
                    val = abs(cur_delta) if cur_delta is not None else None
                    thr = abs(and_c["delta"])
                    op_d = and_c.get("delta_op","<=")
                    if op_d in ("<=","≤"):
                        if val is None or val > thr: and_ok = False
                    else:
                        if val is None or val < thr: and_ok = False
                if and_c.get("gamma") is not None:
                    if not self._eval_op(cur_gamma, and_c.get("gamma_op",">="), and_c["gamma"]): and_ok = False
                if and_c.get("theta") is not None:
                    if not self._eval_op(cur_theta, and_c.get("theta_op","<="), and_c["theta"]): and_ok = False
            if not and_ok: continue

            rule["fired"] = True
            tbl_set(self.tbl_watch_rules, idx, 3, "🔥 조건 성립!", "#ff8800")

            p_str = f"{cur_price:.2f}" if cur_price is not None else "―"
            d_str = f"{cur_delta:.4f}" if cur_delta is not None else "―"
            t_str = f"{cur_theta:.4f}" if cur_theta is not None else "―"
            g_str = f"{cur_gamma:.6f}" if cur_gamma is not None else "―"
            mode  = "단일조건" if not has_and else "AND조건"
            msg   = (f"[{now_str} ET] 🔔 감시 조건 성립! ({mode}) "
                     f"{side} {rule['strike']}  P={p_str}  Δ={d_str}  θ={t_str}  γ={g_str}")

            self.watch_log_box.append(msg)
            try:
                self._watch_log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._watch_log_file, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception as e:
                self._log(f"감시 파일 기록 오류: {e}")
            self._log(msg)
            self._play_alert_sound()
            source = f"🔔 감시 성립 [{now_str}] P={p_str} Δ={d_str}"
            self._qord_fill(side, rule["strike"], cur_price, source=source)
            # 알람 로그 탭으로 자동 전환
            self._watch_tabs.setCurrentIndex(1)

    def _load_watch_log(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "감시 알람 파일 불러오기", str(SAVE_DIR),
            "텍스트 파일 (*.txt);;모든 파일 (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.watch_log_box.setPlainText(f.read())
            self._log(f"감시 로그 불러오기: {path}")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"파일 읽기 실패:\n{e}")

    def _open_watch_log_folder(self):
        import subprocess, sys
        try:
            folder = str(self._watch_log_file.parent)
            if sys.platform == "win32":   subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin": subprocess.Popen(["open", folder])
            else:                          subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            self._log(f"폴더 열기 실패: {e}")
