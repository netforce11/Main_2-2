"""
chart_condition_ui.py — 조건부 주문 패널 UI (ConditionPanel)
────────────────────────────────────────────────────────
· 3컬럼 그리드: 조건 설정 | 실시간 현황 | 자동 주문
· 1초 폴링으로 가격·틱속도 갱신
· 알림음 재생
"""
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer

from chart_condition_monitor import Monitor, _kst_str_to_et_str

ALERT_SOUND = Path("/home/netforce/US_Data/alert.wav")

# ── 색상 ─────────────────────────────────────────────────────
C_BG     = "#0d0d1a";  C_PANEL  = "#0a0a18";  C_BORDER = "#1e1e3a"
C_BORD2  = "#2a2a4a";  C_BLUE   = "#5dade2";  C_GREEN  = "#00e676"
C_ORANGE = "#FF8C00";  C_RED    = "#E24B4A";  C_GRAY   = "#888888"
C_DIM    = "#444444";  C_TEXT   = "#dde0f0";  C_YELLOW = "#ffd700"
C_TEAL   = "#1D9E75"

SS_INPUT = (f"background:{C_PANEL}; border:1px solid #2e3060;"
            f"border-radius:3px; color:{C_TEXT}; padding:2px 5px; font-size:11px;")


# ── 헬퍼 위젯 팩토리 ─────────────────────────────────────────


# [분리] 위젯 헬퍼 → chart_condition_widgets.py
from chart_condition_widgets import _lbl, _inp, _sep, _vsep, _mini_title, _spin_widget  # noqa: F401

class ConditionPanel(QWidget):

    def __init__(self, mw, parent=None):
        super().__init__(parent)
        self._mon       = Monitor(mw)
        self._log_lines = []
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    # ── 빌드 ─────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6); root.setSpacing(5)

        cols = QHBoxLayout(); cols.setSpacing(0)
        cols.addWidget(self._build_col_cond())
        cols.addWidget(_vsep())
        cols.addWidget(self._build_col_live())
        cols.addWidget(_vsep())
        cols.addWidget(self._build_col_order())
        root.addLayout(cols)

        root.addWidget(_sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self.btn_start = QPushButton("🔔 감시 시작")
        self.btn_start.setFixedHeight(26)
        self.btn_start.setStyleSheet(
            f"QPushButton{{background:#1a6b3c;color:#fff;font-weight:bold;"
            f"border:1px solid #2a9b5c;border-radius:4px;padding:2px 10px;}}"
            f"QPushButton:hover{{background:#1e8048;}}")
        self.btn_start.clicked.connect(self._on_start)

        self.btn_stop = QPushButton("■ 중지")
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setStyleSheet(
            f"QPushButton{{background:#6b1a1a;color:#fff;font-weight:bold;"
            f"border:1px solid #9b2a2a;border-radius:4px;padding:2px 10px;}}"
            f"QPushButton:hover{{background:#801e1e;}}")
        self.btn_stop.clicked.connect(self._on_stop)

        self.lbl_status = QLabel("● STOPPED")
        self.lbl_status.setStyleSheet(f"color:{C_DIM}; font-size:11px; font-weight:bold;")
        self.lbl_reason = QLabel("")
        self.lbl_reason.setStyleSheet(f"color:{C_GRAY}; font-size:10px;")

        btn_row.addWidget(self.btn_start); btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.lbl_status); btn_row.addWidget(self.lbl_reason)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self.log_box = QLabel("")
        self.log_box.setTextFormat(Qt.RichText)
        self.log_box.setStyleSheet(
            f"background:#050510; border:1px solid {C_BORDER};"
            f"border-radius:3px; font-size:10px; padding:4px 6px;")
        self.log_box.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.log_box.setWordWrap(True); self.log_box.setFixedHeight(62)
        root.addWidget(self.log_box)


    def _on_price_chk(self, state): self._price_detail.setVisible(bool(state))
    def _on_price_op(self, op):
        is_range = (op == "범위")
        self._lbl_tilde.setVisible(is_range); self.inp_pv2.setVisible(is_range)
    def _on_limit_chk(self, state):
        self._limit_detail.setVisible(bool(state))
        self.lbl_limit_hint.setVisible(not bool(state))

    # ── 설정 수집 ─────────────────────────────────────────────
    def _get_cfg(self) -> dict:
        return {
            "time_start":    self.inp_ts.text().strip() or "09:30",
            "time_end":      self.inp_te.text().strip() or "16:00",
            "tick_thresh":   self.inp_tick.value(),
            "strike":        self.inp_strike.text().strip().upper(),
            "price_enabled": self.chk_price.isChecked(),
            "price_op":      self.sel_price_op.currentText(),
            "price_val1":    self.inp_pv1.value(),
            "price_val2":    self.inp_pv2.value(),
            "auto_order":    self.chk_auto.isChecked(),
            "order_qty":     self.inp_qty.value(),
            "order_side":    self.sel_side.currentText(),
            "limit_enabled": self.chk_limit.isChecked(),
            "limit_price":   self.inp_limit.value(),
        }

    # ── 시작 / 중지 ───────────────────────────────────────────
    def _on_start(self):
        cfg = self._get_cfg()
        if not cfg["strike"]:
            self._log("⚠ 행사가를 입력하세요", warn=True); return
        self._mon.running     = True
        self._mon._order_sent = False
        self._mon.unsubscribe(); self._mon.subscribe(cfg["strike"])
        self._set_status("WATCHING")
        self.lbl_et_range.setText(self._mon.et_range_str(cfg))
        price_info = ""
        if cfg["price_enabled"]:
            price_info = f"  현재가 {cfg['price_op']} {cfg['price_val1']:.2f}"
            if cfg["price_op"] == "범위":
                price_info += f"~{cfg['price_val2']:.2f}"
        lmt_info = (f"  지정가={cfg['limit_price']:.2f}"
                    if cfg["limit_enabled"] else "  Last+0.05")
        self._log(f"▶ 시작: {cfg['strike']}  틱>{cfg['tick_thresh']}"
                  f"  {cfg['time_start']}~{cfg['time_end']}(KST){price_info}{lmt_info}")

    def _on_stop(self):
        self._mon.running = False
        self._mon.unsubscribe()
        self.lbl_et_range.setText("")
        self._set_status("STOPPED")
        self._log("■ 감시 중지", warn=True)

    # ── 1초 폴링 ─────────────────────────────────────────────
    def _tick(self):
        cfg   = self._get_cfg()
        price = self._mon.get_price()
        tick  = self._mon.tick_10s()
        for key in ("bid", "last", "ask"):
            v   = price[key]
            lbl = getattr(self, f"lv_{key}")
            lbl.setText(f"{v:.2f}" if v > 0 else "—")
            lbl.setStyleSheet(
                f"color:{C_GREEN}; font-size:14px; font-weight:bold;" if v > 0
                else f"color:{C_DIM}; font-size:14px; font-weight:bold;")
        thresh  = max(cfg["tick_thresh"], 1)
        pct     = min(tick / (thresh * 2), 1.0)
        g_color = (C_RED if tick > thresh * 2 else
                   C_ORANGE if tick > thresh else C_TEAL)
        self.lv_tick.setText(str(tick))
        self.lv_tick.setStyleSheet(f"color:{g_color}; font-size:13px; font-weight:bold;")
        w = int(self._gauge_bg.width() * pct)
        self._gauge_fill.setFixedWidth(max(w, 0))
        self._gauge_fill.setStyleSheet(f"background:{g_color}; border-radius:4px; border:none;")
        if not self._mon.running:
            return
        triggered, tick_10s, reason = self._mon.check(cfg)
        self.lbl_reason.setText(reason if reason not in ("OK", "", None) else "")
        if triggered:
            self._set_status("TRIGGERED")
            self._log(f"🔔 조건 충족! 틱={tick_10s}  Last={price['last']:.2f}  {cfg['strike']}", warn=True)
            _play_alert()
            if cfg["auto_order"] and not self._mon._order_sent:
                result = self._mon.place_order(cfg)
                self._log(f"📋 {result}")

    # ── 상태 뱃지 ─────────────────────────────────────────────
    def _set_status(self, status: str):
        s = {
            "WATCHING":  (f"color:{C_BLUE}; font-size:11px; font-weight:bold;",  "● WATCHING"),
            "TRIGGERED": (f"color:{C_RED};  font-size:12px; font-weight:bold;",  "🔔 TRIGGERED"),
            "STOPPED":   (f"color:{C_DIM};  font-size:11px; font-weight:bold;",  "● STOPPED"),
        }
        ss, txt = s.get(status, s["STOPPED"])
        self.lbl_status.setStyleSheet(ss); self.lbl_status.setText(txt)

    # ── 로그 ─────────────────────────────────────────────────
    def _log(self, msg: str, warn: bool = False):
        ts    = datetime.now().strftime("%H:%M:%S")
        color = C_ORANGE if warn else C_GREEN
        self._log_lines.append(f'<span style="color:{color}">[{ts}] {msg}</span>')
        self._log_lines = self._log_lines[-4:]
        self.log_box.setText("<br>".join(self._log_lines))


# ── 알림음 ───────────────────────────────────────────────────
def _play_alert():
    try:
        if ALERT_SOUND.exists():
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(str(ALERT_SOUND)); return
            except Exception:
                pass
            try:
                import playsound
                playsound.playsound(str(ALERT_SOUND), block=False); return
            except Exception:
                pass
        print("\a", end="", flush=True)
    except Exception:
        pass


# [분리] 컬럼 빌더 → chart_condition_columns.py
from chart_condition_columns import (
    _build_col_cond, _build_col_live, _build_col_order
)

# 모듈 레벨 임포트만으로는 클래스 메서드로 인식되지 않으므로 직접 바인딩
ConditionPanel._build_col_cond  = _build_col_cond
ConditionPanel._build_col_live  = _build_col_live
ConditionPanel._build_col_order = _build_col_order