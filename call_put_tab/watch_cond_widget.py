"""
watch_cond_widget.py — WatchCondMixin  v6.7
════════════════════════════════════════════════════════════════
탭 구성 (하나의 팝업 안):
  [조건설정]  가격/Delta/Theta/Gamma + AND조건
  [알람로그]  WatchLogMixin._build_log_tab()
  [등록목록]  WatchLogMixin._build_rules_tab()
  [🚨SPX감시] 조건A/B/C (watch_dog.AlertEngine 연동)

폰트 정책:
  탭바 글씨 : 12px bold
  내부 위젯 : 12px (체크박스/레이블/버튼 통일)
  등록목록 테이블 헤더 : 12px bold (탭바와 동일)

클래스 순서 (Python 정의 순서 중요):
  1. WatchAlertTabMixin  ← SPX 감시 탭 내용 빌더
  2. WatchCondMixin(WatchAlertTabMixin) ← 전체 패널 조립
════════════════════════════════════════════════════════════════
"""

from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QGroupBox, QTabWidget, QSlider,
    QSpinBox, QDoubleSpinBox, QListWidget, QListWidgetItem,
    QTextEdit,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from core import make_table, SAVE_DIR
from watch_dog.alert_engine import AlertEngine, CondARow
from watch_dog.alert_logger import AlertLogger


# ── 공통 상수 ─────────────────────────────────────────────
_OP_ITEMS  = ["≤", "≥", "<", ">"]
_FONT_SIZE = 12          # 내부 위젯 기본 폰트 크기
_TAB_SS = (
    "QTabBar::tab{font-size:12px;font-weight:bold;padding:4px 10px;color:#aaa;}"
    "QTabBar::tab:selected{color:#5dade2;border-bottom:2px solid #5dade2;}"
    "QTabBar::tab:hover{color:#fff;}"
)


# ── 헬퍼 함수 ─────────────────────────────────────────────

def _label(text, color="#ccc", size=_FONT_SIZE):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{color};font-size:{size}px;border:none;")
    return lbl

def _op_cb(items=None):
    cb = QComboBox()
    cb.addItems(items or _OP_ITEMS)
    cb.setFixedWidth(48)
    cb.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
    return cb

def _val_ed(placeholder="0.00", width=70):
    ed = QLineEdit()
    ed.setPlaceholderText(placeholder)
    ed.setFixedWidth(width)
    ed.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
    return ed

def _chk(label):
    cb = QCheckBox(label)
    cb.setStyleSheet(f"color:#ccc;font-size:{_FONT_SIZE}px;")
    return cb

def _btn(text, bg="#1a3a6b", fg="#90caf9"):
    b = QPushButton(text)
    b.setFixedHeight(26)
    b.setStyleSheet(
        f"background:{bg};color:{fg};font-size:{_FONT_SIZE}px;"
        "font-weight:bold;border-radius:3px;padding:2px 8px;")
    return b

def _row_chk_op_val(chk_label, op_items=None, val_ph="0.000"):
    return _chk(chk_label), _op_cb(op_items), _val_ed(val_ph)

def _apply_font(widget, size=_FONT_SIZE):
    """위젯과 모든 자식에 폰트 크기 적용"""
    f = widget.font(); f.setPointSize(size); widget.setFont(f)
    for child in widget.findChildren(QWidget):
        f2 = child.font(); f2.setPointSize(size); child.setFont(f2)


# ══════════════════════════════════════════════════════════════
# 1. WatchAlertTabMixin — SPX 감시 탭 내용 (반드시 먼저 정의)
# ══════════════════════════════════════════════════════════════

class WatchAlertTabMixin:
    """
    [🚨SPX감시] 탭 내용을 빌드하고 AlertEngine 을 관리.
    WatchCondMixin 이 상속 → CallPutGrid 는 WatchCondMixin 만 상속하면 됨.
    """

    def _init_spx_engine(self):
        """AlertEngine 초기화 (최초 1회)"""
        if hasattr(self, '_spx_engine'):
            return
        self._spx_logger = AlertLogger()
        self._spx_engine = AlertEngine(on_alert=self._on_spx_alert)
        self._spx_alert_total = 0

    # ── SPX 감시 탭 UI 빌더 ──────────────────────────────

    def _build_spx_tab(self):
        """[🚨SPX감시] 탭 위젯 반환"""
        self._init_spx_engine()
        w  = QWidget()
        vb = QVBoxLayout(w); vb.setSpacing(6); vb.setContentsMargins(6, 6, 6, 6)

        vb.addLayout(self._build_spx_header())
        vb.addWidget(self._build_spx_cond_a())
        vb.addWidget(self._build_spx_cond_b())
        vb.addLayout(self._build_spx_ctrl())
        vb.addWidget(self._build_spx_log_box())
        return w

    def _build_spx_header(self):
        """신호등 + 알람 횟수 + 로그 버튼"""
        hb = QHBoxLayout()
        self._spx_light = QLabel("●")
        self._spx_light.setStyleSheet("color:#888;font-size:20px;")
        self._spx_cnt   = _label("알람 0회", "#aaa", 11)
        btn_log = _btn("📂 로그", "#1a2a1a", "#aaa")
        btn_log.setFixedHeight(22)
        btn_log.clicked.connect(self._open_spx_log)
        hb.addWidget(self._spx_light)
        hb.addWidget(self._spx_cnt)
        hb.addStretch()
        hb.addWidget(btn_log)
        return hb

    def _build_spx_cond_a(self):
        gb = QGroupBox("조건A — SPX 등락")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#90caf9;"
            "border:1px solid #1a2a4a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        vb = QVBoxLayout(gb); vb.setSpacing(3); vb.setContentsMargins(4, 8, 4, 4)
        self._spx_a_rows = []
        for i in range(2):
            hb  = QHBoxLayout()
            lbl = _label(f"A{i+1}", "#ffd700", _FONT_SIZE)
            lbl.setFixedWidth(22)
            min_sp = QSpinBox(); min_sp.setRange(1, 60); min_sp.setValue(5)
            min_sp.setSuffix("분"); min_sp.setFixedWidth(62)
            min_sp.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
            pt_sp  = QDoubleSpinBox(); pt_sp.setRange(0.1, 999); pt_sp.setValue(5.0)
            pt_sp.setSuffix("pt"); pt_sp.setFixedWidth(72)
            pt_sp.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
            dir_cb = QComboBox(); dir_cb.addItems(["하락", "상승", "양방향"])
            dir_cb.setFixedWidth(76)
            dir_cb.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
            for w in (lbl, min_sp, pt_sp, dir_cb):
                hb.addWidget(w)
            hb.addStretch()
            vb.addLayout(hb)
            self._spx_a_rows.append({"min": min_sp, "pt": pt_sp, "dir": dir_cb})
        return gb

    def _build_spx_cond_b(self):
        gb = QGroupBox("조건B — 옵션 등락 (행사가 최대 5개, 콜/풋 탭 클릭 추가)")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#ffd700;"
            "border:1px solid #3a2a1a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        vb = QVBoxLayout(gb); vb.setSpacing(3); vb.setContentsMargins(4, 8, 4, 4)

        self._spx_strike_list = QListWidget()
        self._spx_strike_list.setMaximumHeight(80)
        self._spx_strike_list.setStyleSheet(
            f"font-size:{_FONT_SIZE}px;background:#08080f;color:#ffd700;")
        self._spx_strike_list.setToolTip("콜/풋 탭 행사가 클릭 → 자동 추가")
        btn_rm = _btn("선택 제거", "#3a1a1a", "#ff8888")
        btn_rm.setFixedHeight(22)
        btn_rm.clicked.connect(self._spx_remove_strike)

        pct_hb = QHBoxLayout()
        pct_hb.addWidget(_label("기준%:", "#aaa"))
        self._spx_pct = QDoubleSpinBox(); self._spx_pct.setRange(10, 9999)
        self._spx_pct.setValue(500); self._spx_pct.setSuffix("%")
        self._spx_pct.setFixedWidth(88)
        self._spx_pct.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._spx_dir_b = QComboBox(); self._spx_dir_b.addItems(["양방향", "상승", "하락"])
        self._spx_dir_b.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        pct_hb.addWidget(self._spx_pct); pct_hb.addWidget(self._spx_dir_b)
        pct_hb.addStretch()

        vb.addWidget(self._spx_strike_list)
        vb.addWidget(btn_rm)
        vb.addLayout(pct_hb)
        return gb

    def _build_spx_ctrl(self):
        hb = QHBoxLayout()
        self._spx_btn_start = _btn("▶ 감시 시작", "#1a4a1a", "#00ff88")
        self._spx_btn_stop  = _btn("■ 중지",      "#3a1a1a", "#ff6666")
        self._spx_btn_stop.setEnabled(False)
        self._spx_btn_start.clicked.connect(self._spx_start)
        self._spx_btn_stop.clicked.connect(self._spx_stop)
        hb.addWidget(self._spx_btn_start)
        hb.addWidget(self._spx_btn_stop)
        hb.addStretch()
        return hb

    def _build_spx_log_box(self):
        self._spx_log_box = QTextEdit()
        self._spx_log_box.setReadOnly(True)
        self._spx_log_box.setMaximumHeight(110)
        self._spx_log_box.setStyleSheet(
            f"background:#0a0a1e;color:#ddd;font-size:{_FONT_SIZE}px;"
            "border:1px solid #1a1a3a;")
        return self._spx_log_box

    # ── SPX 감시 제어 ─────────────────────────────────────

    def _spx_start(self):
        self._init_spx_engine()
        for i, row in enumerate(self._spx_a_rows):
            self._spx_engine.cond_a[i] = CondARow(
                minutes=row["min"].value(),
                points=row["pt"].value(),
                direction=row["dir"].currentText(),
                enabled=True,
            )
        self._spx_engine.reset_counts()
        self._spx_alert_total = 0
        self._spx_cnt.setText("알람 0회")
        self._spx_engine.start()
        self._spx_set_light("green")
        self._spx_btn_start.setEnabled(False)
        self._spx_btn_stop.setEnabled(True)
        self._spx_log("🟢 SPX 감시 시작")

    def _spx_stop(self):
        self._spx_engine.stop()
        self._spx_set_light("gray")
        self._spx_btn_start.setEnabled(True)
        self._spx_btn_stop.setEnabled(False)
        self._spx_log("⬛ SPX 감시 중지")

    def _spx_set_light(self, state):
        color = {"green": "#00e676", "red": "#ff1744", "gray": "#888"}.get(state, "#888")
        self._spx_light.setStyleSheet(f"color:{color};font-size:20px;")

    def _spx_log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._spx_log_box.append(
            f'<span style="color:#aaa;font-size:{_FONT_SIZE}px">[{ts}] {msg}</span>')

    def _on_spx_alert(self, level, msg):
        """AlertEngine 콜백"""
        from datetime import datetime
        self._spx_logger.write(level, msg)
        self._spx_alert_total += 1
        self._spx_cnt.setText(f"알람 {self._spx_alert_total}회")
        self._spx_set_light("red")
        colors = {1: "#FFD700", 2: "#FF8C00", 3: "#FF3333"}
        color  = colors.get(level, "#fff")
        ts     = datetime.now().strftime("%H:%M:%S")
        self._spx_log_box.append(
            f'<span style="color:{color};font-size:{_FONT_SIZE}px">'
            f'[{ts}] LV{level} {msg}</span>')
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(2000, lambda: (
            self._spx_set_light("green") if self._spx_engine.is_running() else None))

    def _open_spx_log(self):
        import os, subprocess
        path = self._spx_logger.log_path_today()
        if not path.exists(): path.touch()
        try:
            os.startfile(str(path))
        except Exception:
            subprocess.Popen(["notepad.exe", str(path)])

    # ── 행사가 추가 (콜/풋 탭 클릭 → 외부 호출) ──────────

    def add_strike_from_chain(self, strike, opt_type):
        """콜/풋 탭 테이블 클릭 시 외부에서 호출"""
        self._init_spx_engine()
        pct = self._spx_pct.value()
        direction = self._spx_dir_b.currentText()
        added = self._spx_engine.add_strike(strike, opt_type, pct, direction)
        if added:
            label = f"{opt_type}  {strike:.1f}  ±{pct:.0f}%  [{direction}]"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, (strike, opt_type))
            self._spx_strike_list.addItem(item)
            self._spx_log(f"행사가 추가: {opt_type} {strike}")
        else:
            self._spx_log(f"⚠ 최대 5개 / 중복: {opt_type} {strike}")

    def _spx_remove_strike(self):
        item = self._spx_strike_list.currentItem()
        if not item: return
        strike, opt_type = item.data(Qt.UserRole)
        self._spx_engine.remove_strike(strike, opt_type)
        self._spx_strike_list.takeItem(self._spx_strike_list.row(item))

    # ── 데이터 피드 (외부 1분 타이머에서 호출) ────────────

    def feed_spx_to_watch(self, minutes_ago, price_then, price_now):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.push_spx(minutes_ago, price_then, price_now)

    def feed_opt_to_watch(self, strike, opt_type, price_now, price_prev):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.push_opt(strike, opt_type, price_now, price_prev)

    def feed_vix_to_watch(self, vix_now, vix_prev):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.push_vix(vix_now, vix_prev)


# ══════════════════════════════════════════════════════════════
# 2. WatchCondMixin — 전체 감시 패널 조립 (WatchAlertTabMixin 상속)
# ══════════════════════════════════════════════════════════════

class WatchCondMixin(WatchAlertTabMixin):
    """
    감시조건 패널 UI Mixin.
    탭 구성: [조건설정] [알람로그] [등록목록] [🚨SPX감시]
    폰트: 탭바 12px bold, 내부 위젯 12px 통일.
    """

    # ── 최상위 패널 ───────────────────────────────────────

    def _build_watch_panel(self):
        _gb_ss = (
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#5dade2;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        self._watch_gb = QGroupBox("👁 감시 조건")
        self._watch_gb.setStyleSheet(_gb_ss)
        vb = QVBoxLayout(self._watch_gb)
        vb.setContentsMargins(4, 6, 4, 4); vb.setSpacing(3)

        vb.addLayout(self._build_font_row())

        self._watch_tabs = QTabWidget()
        self._watch_tabs.setStyleSheet(_TAB_SS)
        self._watch_tabs.addTab(self._build_cond_tab(),  "조건설정")
        self._watch_tabs.addTab(self._build_log_tab(),   "알람로그")
        self._watch_tabs.addTab(self._build_rules_tab(), "등록목록")
        self._watch_tabs.addTab(self._build_spx_tab(),   "🚨 SPX감시")
        vb.addWidget(self._watch_tabs, 1)
        return self._watch_gb

    def _build_watch_widget(self):
        """tab_options_panels.py _open_watch_popup() 에서 호출"""
        w  = QWidget()
        vb = QVBoxLayout(w)
        vb.setContentsMargins(0, 0, 0, 0); vb.setSpacing(0)
        vb.addWidget(self._build_watch_panel())
        return w

    # ── 폰트 슬라이더 행 ─────────────────────────────────

    def _build_font_row(self):
        hb = QHBoxLayout(); hb.setSpacing(4)
        hb.addWidget(_label("글자크기:", "#666", 10))
        self._watch_font_slider = QSlider(Qt.Horizontal)
        self._watch_font_slider.setRange(8, 18)
        self._watch_font_slider.setValue(_FONT_SIZE)
        self._watch_font_slider.setFixedWidth(80)
        self._watch_font_size_lbl = _label(f"{_FONT_SIZE}px", "#888", 10)
        self._watch_font_slider.valueChanged.connect(self._on_watch_font_change)
        hb.addWidget(self._watch_font_slider)
        hb.addWidget(self._watch_font_size_lbl)
        hb.addStretch()
        return hb

    # ── 탭1: 조건설정 ─────────────────────────────────────

    def _build_cond_tab(self):
        w  = QWidget()
        vb = QVBoxLayout(w); vb.setSpacing(6); vb.setContentsMargins(6, 6, 6, 6)

        info_hb = QHBoxLayout()
        info_hb.addWidget(_label("대상:"))
        self.watch_side = QLineEdit(); self.watch_side.setReadOnly(True)
        self.watch_side.setFixedWidth(30)
        self.watch_side.setStyleSheet(
            f"background:#08080f;color:#ffd700;font-size:{_FONT_SIZE}px;"
            "border:1px solid #2a2a5a;border-radius:2px;")
        self.watch_strike = QLineEdit(); self.watch_strike.setReadOnly(True)
        self.watch_strike.setFixedWidth(65)
        self.watch_strike.setStyleSheet(
            f"background:#08080f;color:#ffd700;font-size:{_FONT_SIZE}px;"
            "border:1px solid #2a2a5a;border-radius:2px;")
        info_hb.addWidget(self.watch_side); info_hb.addWidget(self.watch_strike)
        info_hb.addStretch()
        vb.addLayout(info_hb)

        vb.addWidget(self._build_main_cond_group())
        vb.addWidget(self._build_and_cond_group())

        btn_add = _btn("＋ 감시 등록", "#1a4a1a", "#00ff88")
        btn_add.clicked.connect(self._add_watch_rule)
        vb.addWidget(btn_add)
        vb.addStretch()
        return w

    def _build_main_cond_group(self):
        gb = QGroupBox("감시 조건")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#90caf9;"
            "border:1px solid #1a2a4a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        g = QGridLayout(gb); g.setSpacing(4); g.setContentsMargins(6, 10, 6, 6)

        self.wc_price_chk, self.wc_price_op, self.wc_price_val = \
            _row_chk_op_val("가격", val_ph="0.00")
        self.wc_delta_chk, self.wc_delta_op, self.wc_delta_val = \
            _row_chk_op_val("Delta", val_ph="0.000")
        self.wc_theta_chk, self.wc_theta_op, self.wc_theta_val = \
            _row_chk_op_val("Theta", val_ph="0.000")
        self.wc_gamma_chk, self.wc_gamma_op, self.wc_gamma_val = \
            _row_chk_op_val("Gamma", val_ph="0.0000")

        for i, (chk, op, val) in enumerate([
            (self.wc_price_chk, self.wc_price_op, self.wc_price_val),
            (self.wc_delta_chk, self.wc_delta_op, self.wc_delta_val),
            (self.wc_theta_chk, self.wc_theta_op, self.wc_theta_val),
            (self.wc_gamma_chk, self.wc_gamma_op, self.wc_gamma_val),
        ]):
            g.addWidget(chk, i, 0); g.addWidget(op, i, 1); g.addWidget(val, i, 2)
        return gb

    def _build_and_cond_group(self):
        gb = QGroupBox("AND 조건 (동시 충족)")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#ffd700;"
            "border:1px solid #3a2a1a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        g = QGridLayout(gb); g.setSpacing(4); g.setContentsMargins(6, 10, 6, 6)

        self.wa_time_chk = _chk("시간(ET)")
        self.wa_time_op  = _op_cb(["≥", "≤", ">", "<"])
        self.wa_time_val = _val_ed("HH:MM", 58)
        self.wa_delta_chk, self.wa_delta_op, self.wa_delta_val = \
            _row_chk_op_val("Delta", val_ph="0.000")
        self.wa_gamma_chk, self.wa_gamma_op, self.wa_gamma_val = \
            _row_chk_op_val("Gamma", val_ph="0.0000")
        self.wa_theta_chk, self.wa_theta_op, self.wa_theta_val = \
            _row_chk_op_val("Theta", val_ph="0.000")

        for i, (chk, op, val) in enumerate([
            (self.wa_time_chk,  self.wa_time_op,  self.wa_time_val),
            (self.wa_delta_chk, self.wa_delta_op, self.wa_delta_val),
            (self.wa_gamma_chk, self.wa_gamma_op, self.wa_gamma_val),
            (self.wa_theta_chk, self.wa_theta_op, self.wa_theta_val),
        ]):
            g.addWidget(chk, i, 0); g.addWidget(op, i, 1); g.addWidget(val, i, 2)
        return gb

    # ── 탭2/3 WatchLogMixin 위임 ──────────────────────────

    def _build_log_tab(self):
        if hasattr(super(), '_build_log_tab'):
            return super()._build_log_tab()
        return QWidget()

    def _build_rules_tab(self):
        """등록목록 탭 — 테이블 헤더 폰트를 탭바와 동일하게 적용"""
        w = self._build_rules_tab_raw()
        # 헤더 폰트 강제 적용
        if hasattr(self, 'tbl_watch_rules'):
            hdr = self.tbl_watch_rules.horizontalHeader()
            f = hdr.font(); f.setPointSize(_FONT_SIZE); f.setBold(True)
            hdr.setFont(f)
        return w

    def _build_rules_tab_raw(self):
        if hasattr(super(), '_build_rules_tab'):
            return super()._build_rules_tab()
        return QWidget()

    # ── DST 판별 ──────────────────────────────────────────

    def _is_dst(self):
        from datetime import datetime as _dt
        now = _dt.utcnow()
        if now.month < 3 or now.month > 11: return False
        if 3 < now.month < 11:              return True
        if now.month == 3:
            second_sun = 8 + (6 - _dt(now.year, 3, 1).weekday()) % 7
            return now.day >= second_sun
        first_sun = 1 + (6 - _dt(now.year, 11, 1).weekday()) % 7
        return now.day < first_sun