"""
watch_cond_widget.py — 감시 조건 설정 탭 UI  v6.4
════════════════════════════════════════════════════════
수정 대상: 감시조건·AND조건 레이아웃, 연산자, 폰트슬라이더,
           화면설정 저장/불러오기, 대상 행사가 표시
포함 메서드:
  _build_watch_widget()   통합 QTabWidget (조건설정|알람로그|등록목록)
  _build_watch_tab()      탭1: 감시조건 + AND조건 GroupBox
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QCheckBox, QTabWidget, QSlider,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont


class WatchCondMixin:
    """감시 조건 설정 탭 UI. CallPutGrid에 mixin된다."""

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
        self._watch_tabs.addTab(self._build_watch_tab(),  "🔔 조건 설정")
        self._watch_tabs.addTab(self._build_log_tab(),    "📋 알람 로그")
        self._watch_tabs.addTab(self._build_rules_tab(),  "📌 등록 목록")

        outer_v.addWidget(self._watch_tabs)
        self._watch_gb = outer
        return outer

    def _build_watch_tab(self) -> QWidget:
        """탭1: 화면설정 + 폰트슬라이더 + 대상 + 감시조건/AND조건."""
        w = QWidget()
        root_v = QVBoxLayout(w)
        root_v.setSpacing(4); root_v.setContentsMargins(6, 6, 6, 6)

        # ── 화면설정 저장/불러오기 ───────────────────────────
        layout_row = QHBoxLayout(); layout_row.setSpacing(3)
        layout_row.addWidget(QLabel("화면설정:",
            styleSheet="color:#aaa;font-size:10px;border:none;"))
        self.combo_layout_name = QLineEdit()
        self.combo_layout_name.setPlaceholderText("프리셋 이름")
        self.combo_layout_name.setFixedHeight(22)
        self.combo_layout_name.setFixedWidth(90)
        self.combo_layout_name.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #333;"
            "font-size:10px;border-radius:2px;padding:1px 3px;")
        self.combo_layout_preset = QComboBox()
        self.combo_layout_preset.setFixedHeight(22)
        self.combo_layout_preset.setMinimumWidth(80)
        self.combo_layout_preset.setStyleSheet(
            "QComboBox{background:#12122a;color:#90caf9;border:1px solid #3a3a6a;"
            "font-size:10px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#90caf9;font-size:10px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        for lbl_t, fn, col in [
            ("💾 저장",    self._save_layout_preset, "#1a3a6b"),
            ("📂 불러오기", self._load_layout_preset, "#2d2d2d"),
        ]:
            b = QPushButton(lbl_t); b.setFixedHeight(22)
            b.setStyleSheet(
                f"background:{col};color:#90caf9;font-size:10px;"
                "padding:1px 5px;border-radius:2px;")
            b.clicked.connect(fn); layout_row.addWidget(b)
        layout_row.addWidget(self.combo_layout_preset)
        btn_del = QPushButton("✕"); btn_del.setFixedHeight(22); btn_del.setFixedWidth(22)
        btn_del.setStyleSheet(
            "background:#4a1a1a;color:#ff8888;font-size:10px;border-radius:2px;")
        btn_del.setToolTip("선택 프리셋 삭제")
        btn_del.clicked.connect(self._del_layout_preset)
        layout_row.addWidget(self.combo_layout_name)
        layout_row.addWidget(btn_del)
        root_v.addLayout(layout_row)
        QTimer.singleShot(200, self._refresh_layout_presets)

        # ── 폰트 슬라이더 ────────────────────────────────────
        font_row = QHBoxLayout(); font_row.setSpacing(4)
        font_row.addWidget(QLabel("글씨 크기:",
            styleSheet="color:#aaa;font-size:11px;border:none;"))
        self._watch_font_slider = QSlider(Qt.Horizontal)
        self._watch_font_slider.setRange(9, 22)
        self._watch_font_slider.setValue(13)
        self._watch_font_slider.setFixedWidth(90)
        self._watch_font_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#333;border-radius:2px;}"
            "QSlider::handle:horizontal{background:#ffd700;width:12px;height:12px;"
            "margin:-4px 0;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#3a6a9a;border-radius:2px;}")
        self._watch_font_size_lbl = QLabel("13px")
        self._watch_font_size_lbl.setStyleSheet(
            "color:#ffd700;font-size:10px;border:none;min-width:28px;")
        self._watch_font_slider.valueChanged.connect(self._on_watch_font_change)
        font_row.addWidget(self._watch_font_slider)
        font_row.addWidget(self._watch_font_size_lbl)
        font_row.addStretch()
        root_v.addLayout(font_row)

        # ── 대상 행사가 ───────────────────────────────────────
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("대상:"))
        self.watch_side = QLineEdit(); self.watch_side.setReadOnly(True)
        self.watch_side.setPlaceholderText("C/P"); self.watch_side.setFixedWidth(30)
        self.watch_strike = QLineEdit(); self.watch_strike.setReadOnly(True)
        self.watch_strike.setPlaceholderText("행사가"); self.watch_strike.setFixedWidth(60)
        self.watch_side.setStyleSheet("color:#ffd700;font-weight:bold;")
        self.watch_strike.setStyleSheet("color:#ffd700;font-weight:bold;")
        row0.addWidget(self.watch_side); row0.addWidget(self.watch_strike)
        row0.addStretch()
        root_v.addLayout(row0)

        # ── 공통 스타일 ───────────────────────────────────────
        _chk_s = "color:#ffd700;font-size:13px;font-weight:bold;"
        _val_s  = ("background:#0a0a1e;color:#fff;"
                   "border:1px solid #444;font-size:13px;padding:1px 4px;")
        _comb_s = (
            "QComboBox{background:#12122a;color:#ffd700;border:1px solid #4a4a7a;"
            "border-radius:3px;font-size:13px;padding:1px 4px;}"
            "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
            "selection-background-color:#1c3a6a;font-size:13px;}"
            "QComboBox::drop-down{border:none;width:14px;}")
        _OPS   = ["<", "<=", ">", ">="]
        _ROW_H = 26

        # ── 감시조건 + AND조건 통합 GroupBox ─────────────────
        cond_gb = QGroupBox("감시 조건 / AND 조건")
        cond_gb.setStyleSheet(
            "QGroupBox{font-size:12px;color:#90caf9;font-weight:bold;"
            "border:1px solid #3a3a6a;border-radius:4px;"
            "margin-top:6px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;top:0px;}")
        cond_gl = QGridLayout(cond_gb)
        cond_gl.setVerticalSpacing(6); cond_gl.setHorizontalSpacing(6)
        cond_gl.setContentsMargins(8, 12, 8, 8)
        cond_gl.setColumnMinimumWidth(0, 58)
        cond_gl.setColumnMinimumWidth(1, 52)
        cond_gl.setColumnMinimumWidth(2, 72)
        cond_gl.setColumnStretch(3, 1)

        # 헤더 행0: ▶ 감시 조건
        lbl_cond = QLabel("▶ 감시 조건")
        lbl_cond.setStyleSheet(
            "color:#ffd700;font-size:13px;font-weight:bold;border:none;")
        lbl_cond.setFixedHeight(22)
        cond_gl.addWidget(lbl_cond, 0, 0, 1, 3)
        cond_gl.setRowMinimumHeight(0, 22)

        # 감시조건 4행 (행1~4)
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
            val.setStyleSheet(_val_s);  val.setFixedHeight(_ROW_H)
            cond_gl.addWidget(chk, row_i, 0)
            cond_gl.addWidget(op,  row_i, 1)
            cond_gl.addWidget(val, row_i, 2)
            cond_gl.setRowMinimumHeight(row_i, _ROW_H)

        # 구분선 행5
        sep = QLabel(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:#2a2a5a;border:none;")
        cond_gl.addWidget(sep, 5, 0, 1, 3)
        cond_gl.setRowMinimumHeight(5, 8)

        # 헤더 행6: ▶ AND 조건
        lbl_and = QLabel("▶ AND 조건")
        lbl_and.setStyleSheet(
            "color:#90caf9;font-size:13px;font-weight:bold;border:none;")
        lbl_and.setFixedHeight(22)
        cond_gl.addWidget(lbl_and, 6, 0, 1, 3)
        cond_gl.setRowMinimumHeight(6, 22)

        # AND조건 4행 (행7~10)
        self.wa_time_chk  = QCheckBox("시간")
        self.wa_time_op   = QComboBox(); self.wa_time_op.addItems(_OPS)
        self.wa_time_op.setCurrentText(">=")
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
            val.setStyleSheet(_val_s);  val.setFixedHeight(_ROW_H)
            cond_gl.addWidget(chk, row_i, 0)
            cond_gl.addWidget(op,  row_i, 1)
            cond_gl.addWidget(val, row_i, 2)
            cond_gl.setRowMinimumHeight(row_i, _ROW_H)

        root_v.addWidget(cond_gb)

        # ── 등록 버튼 ─────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        btn_add = QPushButton("➕ 감시 등록")
        btn_add.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-weight:bold;"
            "padding:6px;font-size:12px;")
        btn_add.clicked.connect(self._add_watch_rule)
        btn_clr = QPushButton("🗑 전체 삭제")
        btn_clr.setStyleSheet(
            "background:#5a1a1a;color:#ff6666;font-weight:bold;"
            "padding:6px;font-size:12px;")
        btn_clr.clicked.connect(self._clear_watch_rules)
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_clr)
        root_v.addLayout(btn_row)
        root_v.addStretch()

        self._watch_gb_root = root_v
        return w
