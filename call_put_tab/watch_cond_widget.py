"""
watch_cond_widget.py — WatchCondMixin  v7.0
════════════════════════════════════════════════════════════════
변경 (v6.7 → v7.0):
  - [🚨SPX감시] 탭 완전 재설계
    · 조건A: 고정 2행 → 동적 리스트 테이블 (추가/삭제/저장)
    · 조건B: QListWidget → 테이블 방식 (C/P·행사가·%·방향)
    · 저장/불러오기: C:\data\Greeks_history\spx_watch.json
  - AlertEngine v2 인터페이스 연동
    · push_spx(minutes_ago, price_then, price_now)
    · push_opt(strike, opt_type, price_now, price_prev)
    · push_vix(vix_now, vix_prev)
  - is_running → @property (괄호 없이)
════════════════════════════════════════════════════════════════
"""

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QGroupBox, QTabWidget, QSlider,
    QSpinBox, QDoubleSpinBox, QListWidget, QListWidgetItem,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor

from core import make_table, SAVE_DIR
from watch_dog.alert_engine import AlertEngine, CondARow, CondBStrike
from watch_dog.alert_logger import AlertLogger

_WATCH_SAVE_PATH = Path(r"C:\data\Greeks_history\spx_watch.json")

_OP_ITEMS  = ["<=", ">=", "<", ">"]
_FONT_SIZE = 12
_TAB_SS = (
    "QTabBar::tab{font-size:12px;font-weight:bold;padding:4px 10px;color:#aaa;}"
    "QTabBar::tab:selected{color:#5dade2;border-bottom:2px solid #5dade2;}"
    "QTabBar::tab:hover{color:#fff;}"
)
_TBL_SS = (
    "QTableWidget{background:#08080f;color:#ddd;gridline-color:#1a1a3a;"
    "font-size:12px;border:1px solid #1a1a3a;}"
    "QHeaderView::section{background:#0d0d20;color:#90caf9;"
    "font-size:12px;font-weight:bold;border:1px solid #1a1a3a;}"
)


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
    f = widget.font(); f.setPointSize(size); widget.setFont(f)
    for child in widget.findChildren(QWidget):
        f2 = child.font(); f2.setPointSize(size); child.setFont(f2)

def _tbl_item(text, color="#ddd"):
    it = QTableWidgetItem(str(text))
    it.setForeground(QColor(color))
    it.setTextAlignment(Qt.AlignCenter)
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    return it

def _del_btn():
    b = QPushButton("X")
    b.setFixedSize(24, 20)
    b.setStyleSheet("background:#3a1a1a;color:#ff8888;font-size:11px;"
                    "font-weight:bold;border:none;border-radius:2px;")
    return b


# ══════════════════════════════════════════════════════════════
# 1. WatchAlertTabMixin
# ══════════════════════════════════════════════════════════════

class WatchAlertTabMixin:

    def _init_spx_engine(self):
        if hasattr(self, '_spx_engine'):
            return
        self._spx_logger     = AlertLogger()
        self._spx_engine     = AlertEngine(on_alert=self._on_spx_alert)
        self._spx_alert_total = 0

    # ── 탭 최상위 빌더 ───────────────────────────────────

    def _build_spx_tab(self):
        self._init_spx_engine()
        w  = QWidget()
        vb = QVBoxLayout(w)
        vb.setSpacing(5); vb.setContentsMargins(6, 6, 6, 6)
        vb.addLayout(self._build_spx_header())
        vb.addWidget(self._build_spx_cond_a())
        vb.addWidget(self._build_spx_cond_b())
        vb.addLayout(self._build_spx_ctrl())
        vb.addWidget(self._build_spx_log_box())
        return w

    def _build_spx_header(self):
        hb = QHBoxLayout()
        self._spx_light = QLabel("●")
        self._spx_light.setStyleSheet("color:#888;font-size:20px;")
        self._spx_cnt   = _label("알람 0회", "#aaa", 11)
        btn_log = _btn("  로그", "#1a2a1a", "#aaa")
        btn_log.setFixedHeight(22)
        btn_log.clicked.connect(self._open_spx_log)
        hb.addWidget(self._spx_light)
        hb.addWidget(self._spx_cnt)
        hb.addStretch()
        hb.addWidget(btn_log)
        return hb

    # ── 조건A 그룹 ───────────────────────────────────────

    def _build_spx_cond_a(self):
        gb = QGroupBox("조건A — SPX 등락")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#90caf9;"
            "border:1px solid #1a2a4a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        vb = QVBoxLayout(gb)
        vb.setSpacing(3); vb.setContentsMargins(4, 8, 4, 4)

        self._tbl_a = QTableWidget(0, 4)
        self._tbl_a.setHorizontalHeaderLabels(["분", "pt", "방향", "삭제"])
        self._tbl_a.setStyleSheet(_TBL_SS)
        self._tbl_a.verticalHeader().setVisible(False)
        self._tbl_a.setFixedHeight(100)
        self._tbl_a.setSelectionBehavior(QAbstractItemView.SelectRows)
        hdr = self._tbl_a.horizontalHeader()
        for col, w in enumerate([55, 65, 70, 40]):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._tbl_a.setColumnWidth(col, w)
        vb.addWidget(self._tbl_a)

        add_hb = QHBoxLayout()
        self._a_min = QSpinBox()
        self._a_min.setRange(1, 60); self._a_min.setValue(10)
        self._a_min.setSuffix("분"); self._a_min.setFixedWidth(62)
        self._a_min.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._a_pt  = QDoubleSpinBox()
        self._a_pt.setRange(0.1, 999); self._a_pt.setValue(5.0)
        self._a_pt.setSuffix("pt"); self._a_pt.setFixedWidth(72)
        self._a_pt.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._a_dir = QComboBox()
        self._a_dir.addItems(["하락", "상승", "양방향"])
        self._a_dir.setFixedWidth(76)
        self._a_dir.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        btn_add_a = _btn("+ 추가", "#1a3a1a", "#88ff88")
        btn_add_a.setFixedWidth(58)
        btn_add_a.clicked.connect(self._spx_add_cond_a)
        for w in (self._a_min, self._a_pt, self._a_dir, btn_add_a):
            add_hb.addWidget(w)
        add_hb.addStretch()
        vb.addLayout(add_hb)
        return gb

    # ── 조건B 그룹 ───────────────────────────────────────

    def _build_spx_cond_b(self):
        gb = QGroupBox("조건B — 옵션 등락 (콜/풋 탭 클릭 또는 직접 추가, 최대 5개)")
        gb.setStyleSheet(
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#ffd700;"
            "border:1px solid #3a2a1a;border-radius:3px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:6px;}")
        vb = QVBoxLayout(gb)
        vb.setSpacing(3); vb.setContentsMargins(4, 8, 4, 4)

        self._tbl_b = QTableWidget(0, 5)
        self._tbl_b.setHorizontalHeaderLabels(["C/P", "행사가", "기준%", "방향", "삭제"])
        self._tbl_b.setStyleSheet(_TBL_SS)
        self._tbl_b.verticalHeader().setVisible(False)
        self._tbl_b.setFixedHeight(100)
        self._tbl_b.setSelectionBehavior(QAbstractItemView.SelectRows)
        hdr = self._tbl_b.horizontalHeader()
        for col, w in enumerate([38, 62, 68, 68, 40]):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._tbl_b.setColumnWidth(col, w)
        vb.addWidget(self._tbl_b)

        add_hb = QHBoxLayout()
        self._b_type = QComboBox()
        self._b_type.addItems(["C", "P"]); self._b_type.setFixedWidth(44)
        self._b_type.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._b_strike = QDoubleSpinBox()
        self._b_strike.setRange(1, 99999); self._b_strike.setValue(7000)
        self._b_strike.setDecimals(0); self._b_strike.setFixedWidth(78)
        self._b_strike.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._b_pct = QDoubleSpinBox()
        self._b_pct.setRange(10, 9999); self._b_pct.setValue(300)
        self._b_pct.setSuffix("%"); self._b_pct.setFixedWidth(88)
        self._b_pct.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        self._b_dir = QComboBox()
        self._b_dir.addItems(["양방향", "상승", "하락"]); self._b_dir.setFixedWidth(76)
        self._b_dir.setStyleSheet(f"font-size:{_FONT_SIZE}px;")
        btn_add_b = _btn("+ 추가", "#3a2a1a", "#ffdd88")
        btn_add_b.setFixedWidth(58)
        btn_add_b.clicked.connect(self._spx_add_cond_b_manual)
        for w in (self._b_type, self._b_strike, self._b_pct, self._b_dir, btn_add_b):
            add_hb.addWidget(w)
        add_hb.addStretch()
        vb.addLayout(add_hb)
        return gb

    # ── 제어 버튼 ─────────────────────────────────────────

    def _build_spx_ctrl(self):
        hb = QHBoxLayout()
        self._spx_btn_start = _btn("  감시 시작", "#1a4a1a", "#00ff88")
        self._spx_btn_stop  = _btn("  중지",      "#3a1a1a", "#ff6666")
        self._spx_btn_stop.setEnabled(False)
        btn_save = _btn("  저장",      "#1a2a4a", "#90caf9")
        btn_load = _btn("  불러오기",  "#2a1a2a", "#cc99ff")
        self._spx_btn_start.clicked.connect(self._spx_start)
        self._spx_btn_stop.clicked.connect(self._spx_stop)
        btn_save.clicked.connect(self._spx_save)
        btn_load.clicked.connect(self._spx_load)
        for b in (self._spx_btn_start, self._spx_btn_stop, btn_save, btn_load):
            hb.addWidget(b)
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

    # ── 조건A 추가/삭제 ──────────────────────────────────

    def _spx_add_cond_a(self):
        if self._tbl_a.rowCount() >= 10:
            return
        r = self._tbl_a.rowCount()
        self._tbl_a.insertRow(r)
        self._tbl_a.setItem(r, 0, _tbl_item(f"{self._a_min.value()}분", "#90caf9"))
        self._tbl_a.setItem(r, 1, _tbl_item(f"{self._a_pt.value():.1f}pt", "#aaddff"))
        self._tbl_a.setItem(r, 2, _tbl_item(self._a_dir.currentText(), "#ffd700"))
        b = _del_btn()
        b.clicked.connect(self._spx_del_row_a)
        self._tbl_a.setCellWidget(r, 3, b)
        self._tbl_a.setRowHeight(r, 24)

    def _spx_del_row_a(self):
        btn = self.sender()
        for r in range(self._tbl_a.rowCount()):
            if self._tbl_a.cellWidget(r, 3) == btn:
                self._tbl_a.removeRow(r)
                return

    # ── 조건B 추가/삭제 ──────────────────────────────────

    def _spx_add_cond_b_manual(self):
        self._spx_add_cond_b_row(
            self._b_type.currentText(),
            self._b_strike.value(),
            self._b_pct.value(),
            self._b_dir.currentText())

    def _spx_add_cond_b_row(self, opt_type, strike, pct, direction):
        if self._tbl_b.rowCount() >= 5:
            return False
        r = self._tbl_b.rowCount()
        color = "#33aaff" if opt_type == "C" else "#ff6666"
        self._tbl_b.insertRow(r)
        self._tbl_b.setItem(r, 0, _tbl_item(opt_type, color))
        self._tbl_b.setItem(r, 1, _tbl_item(f"{float(strike):.0f}", "#ffd700"))
        self._tbl_b.setItem(r, 2, _tbl_item(f"{float(pct):.0f}%", "#aaa"))
        self._tbl_b.setItem(r, 3, _tbl_item(direction, "#ccc"))
        b = _del_btn()
        b.clicked.connect(self._spx_del_row_b)
        self._tbl_b.setCellWidget(r, 4, b)
        self._tbl_b.setRowHeight(r, 24)
        return True

    def _spx_del_row_b(self):
        btn = self.sender()
        for r in range(self._tbl_b.rowCount()):
            if self._tbl_b.cellWidget(r, 4) == btn:
                self._tbl_b.removeRow(r)
                return

    # ── 콜/풋 탭 클릭 → 조건B 자동 추가 ─────────────────

    def add_strike_from_chain(self, strike: float, opt_type: str):
        self._init_spx_engine()
        pct       = self._b_pct.value()
        direction = self._b_dir.currentText()
        if self._spx_add_cond_b_row(opt_type, strike, pct, direction):
            self._spx_log(f"조건B 추가: {opt_type} {strike:.0f}  기준 {pct:.0f}%")

    # ── 감시 시작/중지 ────────────────────────────────────

    def _spx_start(self):
        self._init_spx_engine()

        # 조건A 적용
        self._spx_engine.cond_a.clear()
        for r in range(self._tbl_a.rowCount()):
            try:
                minutes   = int(self._tbl_a.item(r, 0).text().replace("분", ""))
                points    = float(self._tbl_a.item(r, 1).text().replace("pt", ""))
                direction = self._tbl_a.item(r, 2).text()
                self._spx_engine.cond_a.append(
                    CondARow(minutes=minutes, points=points, direction=direction))
            except Exception:
                continue

        # 조건B 적용
        self._spx_engine.cond_b.clear()
        for r in range(self._tbl_b.rowCount()):
            try:
                opt_type  = self._tbl_b.item(r, 0).text()
                strike    = float(self._tbl_b.item(r, 1).text())
                pct       = float(self._tbl_b.item(r, 2).text().replace("%", ""))
                direction = self._tbl_b.item(r, 3).text()
                self._spx_engine.add_strike(strike, opt_type, pct, direction)
            except Exception:
                continue

        self._spx_engine.reset_counts()
        self._spx_alert_total = 0
        self._spx_cnt.setText("알람 0회")
        self._spx_engine.start()
        self._spx_set_light("green")
        self._spx_btn_start.setEnabled(False)
        self._spx_btn_stop.setEnabled(True)
        a_cnt = len(self._spx_engine.cond_a)
        b_cnt = len(self._spx_engine.cond_b)
        self._spx_log(f"SPX 감시 시작 — 조건A {a_cnt}개 / 조건B {b_cnt}개")
        # ★ 메인 화면 깜빡임 라벨 ON 연동
        if hasattr(self, '_update_watch_status_label'):
            self._update_watch_status_label(True)

    def _spx_stop(self):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.stop()
        self._spx_set_light("gray")
        self._spx_btn_start.setEnabled(True)
        self._spx_btn_stop.setEnabled(False)
        self._spx_log("SPX 감시 중지")
        # ★ 메인 화면 깜빡임 라벨 — _watch_timer도 꺼져 있으면 OFF 연동
        if hasattr(self, '_update_watch_status_label'):
            watch_timer_on = (hasattr(self, '_watch_timer')
                              and self._watch_timer.isActive())
            self._update_watch_status_label(watch_timer_on)

    # ── 저장 / 불러오기 ──────────────────────────────────

    def _spx_save(self):
        data = {"cond_a": [], "cond_b": []}
        for r in range(self._tbl_a.rowCount()):
            try:
                data["cond_a"].append({
                    "minutes":   int(self._tbl_a.item(r, 0).text().replace("분", "")),
                    "points":    float(self._tbl_a.item(r, 1).text().replace("pt", "")),
                    "direction": self._tbl_a.item(r, 2).text(),
                })
            except Exception:
                continue
        for r in range(self._tbl_b.rowCount()):
            try:
                data["cond_b"].append({
                    "opt_type":  self._tbl_b.item(r, 0).text(),
                    "strike":    float(self._tbl_b.item(r, 1).text()),
                    "pct":       float(self._tbl_b.item(r, 2).text().replace("%", "")),
                    "direction": self._tbl_b.item(r, 3).text(),
                })
            except Exception:
                continue
        try:
            _WATCH_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _WATCH_SAVE_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._spx_log(f"저장 완료: {_WATCH_SAVE_PATH}")
        except Exception as e:
            self._spx_log(f"저장 실패: {e}")

    def _spx_load(self):
        # 기본 경로 자동 시도, 없으면 파일 다이얼로그
        if _WATCH_SAVE_PATH.exists():
            path = str(_WATCH_SAVE_PATH)
        else:
            path, _ = QFileDialog.getOpenFileName(
                None, "SPX 감시 조건 불러오기",
                str(_WATCH_SAVE_PATH.parent),
                "JSON (*.json);;모든 파일 (*)")
            if not path:
                return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as e:
            self._spx_log(f"불러오기 실패: {e}")
            return

        self._tbl_a.setRowCount(0)
        for row in data.get("cond_a", []):
            self._a_min.setValue(int(row.get("minutes", 10)))
            self._a_pt.setValue(float(row.get("points", 5.0)))
            idx = self._a_dir.findText(row.get("direction", "하락"))
            if idx >= 0:
                self._a_dir.setCurrentIndex(idx)
            self._spx_add_cond_a()

        self._tbl_b.setRowCount(0)
        for row in data.get("cond_b", []):
            self._spx_add_cond_b_row(
                row.get("opt_type", "C"),
                float(row.get("strike", 7000)),
                float(row.get("pct", 300)),
                row.get("direction", "양방향"))

        self._spx_log(f"불러오기 완료 — A:{len(data.get('cond_a',[]))}개  "
                      f"B:{len(data.get('cond_b',[]))}개")

    # ── 신호등 / 로그 ────────────────────────────────────

    def _spx_set_light(self, state):
        c = {"green": "#00ff88", "red": "#ff3333", "gray": "#888"}.get(state, "#888")
        self._spx_light.setStyleSheet(f"color:{c};font-size:20px;")

    def _spx_log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._spx_log_box.append(
            f'<span style="color:#aaa;font-size:{_FONT_SIZE}px">[{ts}] {msg}</span>')

    # ── AlertEngine 콜백 ─────────────────────────────────

    def _on_spx_alert(self, level: int, msg: str):
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
            self._spx_set_light("green") if self._spx_engine.is_running else None))

        # ── 텔레그램 전송 ──────────────────────────────────
        try:
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get().send("watch_alert", f"[LV{level}] {msg}")
        except Exception:
            pass

    def _open_spx_log(self):
        import os, subprocess
        path = self._spx_logger.log_path_today()
        if not path.exists():
            path.touch()
        try:
            os.startfile(str(path))
        except Exception:
            subprocess.Popen(["notepad.exe", str(path)])

    # ── feed 메서드 (tab_options_chart → 엔진) ───────────

    def feed_spx_to_watch(self, price: float):
        """tick 수신마다 호출 — N분 전 가격과 비교해 엔진에 push"""
        if not hasattr(self, '_spx_engine'):
            return
        if not hasattr(self, '_spx_price_history'):
            self._spx_price_history = deque(maxlen=600)
        now = datetime.now()
        self._spx_price_history.append((now, price))
        for row in self._spx_engine.cond_a:
            for ts, p in self._spx_price_history:
                elapsed_min = (now - ts).total_seconds() / 60
                if elapsed_min >= row.minutes:
                    self._spx_engine.push_spx(row.minutes, p, price)
                    break

    def feed_opt_to_watch(self, strike: float, opt_type: str,
                          price_now: float, price_prev: float):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.push_opt(strike, opt_type, price_now, price_prev)

    def feed_vix_to_watch(self, vix_now: float, vix_prev: float):
        if hasattr(self, '_spx_engine'):
            self._spx_engine.push_vix(vix_now, vix_prev)


# ══════════════════════════════════════════════════════════════
# 2. WatchCondMixin
# ══════════════════════════════════════════════════════════════

class WatchCondMixin(WatchAlertTabMixin):

    def _build_watch_panel(self):
        _gb_ss = (
            f"QGroupBox{{font-size:{_FONT_SIZE}px;color:#5dade2;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:4px;}}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")
        self._watch_gb = QGroupBox("  감시 조건")
        self._watch_gb.setStyleSheet(_gb_ss)
        vb = QVBoxLayout(self._watch_gb)
        vb.setContentsMargins(4, 6, 4, 4); vb.setSpacing(3)
        vb.addLayout(self._build_font_row())
        self._watch_tabs = QTabWidget()
        self._watch_tabs.setStyleSheet(_TAB_SS)
        self._watch_tabs.addTab(self._build_cond_tab(),  "조건설정")
        self._watch_tabs.addTab(self._build_log_tab(),   "알람로그")
        self._watch_tabs.addTab(self._build_rules_tab(), "등록목록")
        self._watch_tabs.addTab(self._build_spx_tab(),   "  SPX감시")
        vb.addWidget(self._watch_tabs, 1)
        return self._watch_gb

    def _build_watch_widget(self):
        w  = QWidget()
        vb = QVBoxLayout(w)
        vb.setContentsMargins(0, 0, 0, 0); vb.setSpacing(0)
        vb.addWidget(self._build_watch_panel())
        return w

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
        btn_add = _btn("+ 감시 등록", "#1a4a1a", "#00ff88")
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
        self.wa_time_op  = _op_cb([">=", "<=", ">", "<"])
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

    def _build_log_tab(self):
        if hasattr(super(), '_build_log_tab'):
            return super()._build_log_tab()
        return QWidget()

    def _build_rules_tab(self):
        w = self._build_rules_tab_raw()
        if hasattr(self, 'tbl_watch_rules'):
            hdr = self.tbl_watch_rules.horizontalHeader()
            f = hdr.font(); f.setPointSize(_FONT_SIZE); f.setBold(True)
            hdr.setFont(f)
        return w

    def _build_rules_tab_raw(self):
        if hasattr(super(), '_build_rules_tab'):
            return super()._build_rules_tab()
        return QWidget()

    def _on_watch_font_change(self, size: int):
        self._watch_font_size_lbl.setText(f"{size}px")
        _apply_font(self._watch_gb, size)

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