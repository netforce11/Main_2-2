"""
futures_monitor_tab.py — 선물 N봉 연속 상승/하락 감시 + 사운드 알림
──────────────────────────────────────────────────────────────────
기능:
  · IB reqRealTimeBars (5초봉) 또는 reqMktData 틱으로 가격 수신
  · N봉 연속 상승/하락 감지 → 사운드 + 화면 알림
  · 심볼 직접 입력 (ES, NQ, MES, MNQ, /ES 등)
  · 봉 수(N) 설정: 2~10
  · 사운드: QSound(wav) 또는 beep 폴백
  · 로그 테이블 (시각 / 방향 / N봉 / 현재가)
"""
import threading, time
from collections import deque
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QGroupBox, QCheckBox, QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor
from combo_ui_panel_constants import _pal, get_tbl_style


# ── 사운드 헬퍼 ─────────────────────────────────────────────────

# ── [ADD] 선물 감시 로그 + 텔레그램 헬퍼 ─────────────────────
import os as _os
from pathlib import Path as _Path
from datetime import datetime as _dt

def _futures_log(direction: str, price: float, n: int) -> None:
    """선물 연속봉 알림을 날짜별 CSV에 기록."""
    try:
        from zoneinfo import ZoneInfo
        now = _dt.now(ZoneInfo("America/New_York"))
    except Exception:
        now = _dt.utcnow()
    log_dir = _Path(_os.path.expanduser("~")) / "trading_logs" / "futures_monitor"
    log_dir.mkdir(parents=True, exist_ok=True)
    fname = log_dir / f"futures_{now.strftime('%Y%m%d')}.csv"
    header = not fname.exists()
    with open(fname, "a", encoding="utf-8") as f:
        if header:
            f.write("time_et,direction,n_bars,price\n")
        f.write(f"{now.strftime('%H:%M:%S')},{direction},{n},{price:.2f}\n")

def _futures_tg(direction: str, price: float, n: int) -> None:
    """선물 연속봉 알림 텔레그램 전송."""
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send(
            "order_confirm",
            f"📊 선물 변동 감시\n{direction} {n}봉 연속\n현재가: ${price:,.2f}")
    except Exception as e:
        print(f"[FuturesMonitor] TG 실패: {e}")

def _play_sound(path: str = "") -> None:
    try:
        if path:
            from PyQt5.QtMultimedia import QSound
            QSound.play(path); return
    except Exception:
        pass
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass
    try:
        import os; os.system("paplay /usr/share/sounds/freedesktop/stereo/bell.oga &")
    except Exception:
        pass


# ── Qt 시그널 브리지 ────────────────────────────────────────────
class _Bridge(QObject):
    bar_sig    = pyqtSignal(float)              # [FIX] bridge 방식 5초봉 종가
    alert_sig  = pyqtSignal(str, float, int)   # direction, price, n
    price_sig  = pyqtSignal(float)


# ── 감시 코어 (스레드) ──────────────────────────────────────────
class FuturesMonitorCore:
    def __init__(self, bridge: _Bridge):
        self._bridge   = bridge
        self._active   = False
        self._n        = 3          # 연속 N봉
        self._minutes  = 1          # 봉 단위(분)
        self._lock     = threading.Lock()
        self._last_dir = None       # 중복 알림 방지
        # 분봉 집계용
        self._bar_buf: list  = []   # 현재 분봉 내 5초봉 종가들
        self._bar_open_ts: float = 0.0
        self._candles: deque = deque(maxlen=20)  # 완성된 분봉 종가

    def configure(self, n: int, minutes: int = 1, direction: str = "both"):
        self._n         = max(2, n)
        self._minutes   = max(1, minutes)
        self._direction = direction   # "up" | "dn" | "both"

    def on_bar(self, close: float):
        """5초봉 종가 수신 → 분봉 집계 → N봉 연속 감지."""
        if not self._active or close <= 0:
            return
        now = time.monotonic()
        with self._lock:
            self._bridge.price_sig.emit(close)
            bar_secs = self._minutes * 60
            # 첫 틱이면 분봉 시작
            if self._bar_open_ts == 0.0:
                self._bar_open_ts = now
            self._bar_buf.append(close)
            # 분봉 완성 판단
            if now - self._bar_open_ts >= bar_secs:
                candle_close = self._bar_buf[-1]
                self._candles.append(candle_close)
                self._bar_buf = []
                self._bar_open_ts = now
                candles = list(self._candles)
            else:
                candles = None

        if candles is None or len(candles) < self._n:
            return
        last_n = candles[-self._n:]
        is_up = all(last_n[i] > last_n[i-1] for i in range(1, len(last_n)))
        is_dn = all(last_n[i] < last_n[i-1] for i in range(1, len(last_n)))
        d = getattr(self, '_direction', 'both')

        if is_up and d in ('up', 'both'):
            if self._last_dir != "UP":
                self._last_dir = "UP"
                self._bridge.alert_sig.emit("🔺 연속 상승", close, self._n)
        elif is_dn and d in ('dn', 'both'):
            if self._last_dir != "DN":
                self._last_dir = "DN"
                self._bridge.alert_sig.emit("🔻 연속 하락", close, self._n)
        else:
            if not is_up and not is_dn:
                self._last_dir = None

    def start(self):
        self._active = True
        self._last_dir = None
        with self._lock:
            self._bar_buf = []
            self._bar_open_ts = 0.0
            self._candles.clear()

    def stop(self): self._active = False


# ── UI 탭 위젯 ─────────────────────────────────────────────────
class FuturesMonitorTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = _Bridge()
        self._core   = FuturesMonitorCore(self._bridge)
        self._req_id = 7701          # IB reqRealTimeBars reqId
        self._sound_path = ""
        self._build_ui()
        self._bridge.alert_sig.connect(self._on_alert)
        self._bridge.price_sig.connect(self._on_price)

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build_ui(self):
        t   = _pal()
        fg  = t.get('widget_fg', '#c9d1d9')
        bg  = t.get('group_bg',  '#161b22')
        bdr = t.get('group_border', '#30363d')
        root = QVBoxLayout(self)
        root.setSpacing(6); root.setContentsMargins(6, 6, 6, 6)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"color:{fg};font-size:11px;border:none;")
            return l

        def spin(lo, hi, val, w=60):
            s = QSpinBox()
            s.setRange(lo, hi); s.setValue(val)
            s.setFixedWidth(w); s.setFixedHeight(26)
            s.setStyleSheet(
                f"QSpinBox{{background:{t.get('input_bg','#0d1117')};"
                f"color:{fg};border:1px solid {bdr};"
                "border-radius:3px;font-size:11px;padding:1px 4px;}")
            return s

        # ── 행 1: 심볼 + 봉 설정 ────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(6)
        r1.addWidget(lbl("심볼:"))
        self._edit_sym = QLineEdit("ES")
        self._edit_sym.setFixedWidth(70); self._edit_sym.setFixedHeight(26)
        self._edit_sym.setPlaceholderText("ES / NQ / MES")
        self._edit_sym.setStyleSheet(
            f"background:{t.get('input_bg','#0d1117')};color:{fg};"
            f"border:1px solid {bdr};border-radius:3px;padding:2px 4px;")
        r1.addWidget(self._edit_sym)
        r1.addWidget(lbl("N봉:"))
        self._sb_n = spin(2, 10, 3, 55)
        r1.addWidget(self._sb_n)
        r1.addWidget(lbl("봉  ×"))
        self._sb_min = spin(1, 60, 1, 55)
        self._sb_min.setSuffix(" 분")
        r1.addWidget(self._sb_min)
        r1.addStretch()
        self._lbl_price = QLabel("현재가: —")
        self._lbl_price.setStyleSheet(
            f"color:{t.get('group_title','#58a6ff')};"
            "font-size:13px;font-weight:bold;border:none;")
        r1.addWidget(self._lbl_price)
        root.addLayout(r1)

        # ── 행 2: 감시 방향 선택 ────────────────────────────────
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        r_dir = QHBoxLayout(); r_dir.setSpacing(12)
        r_dir.addWidget(lbl("감시 방향:"))

        self._rb_up   = QRadioButton("🔺 상승만")
        self._rb_dn   = QRadioButton("🔻 하락만")
        self._rb_both = QRadioButton("양방향")
        self._rb_both.setChecked(True)

        _rb_ss = f"color:{fg};font-size:11px;"
        for rb in (self._rb_up, self._rb_dn, self._rb_both):
            rb.setStyleSheet(_rb_ss)
            r_dir.addWidget(rb)

        self._dir_grp = QButtonGroup()
        self._dir_grp.addButton(self._rb_up,   0)
        self._dir_grp.addButton(self._rb_dn,   1)
        self._dir_grp.addButton(self._rb_both, 2)
        r_dir.addStretch()
        root.addLayout(r_dir)
        r2 = QHBoxLayout(); r2.setSpacing(6)
        self._chk_sound = QCheckBox("사운드")
        self._chk_sound.setChecked(True)
        self._chk_sound.setStyleSheet(f"color:{fg};font-size:11px;")
        r2.addWidget(self._chk_sound)
        self._lbl_status = QLabel("● 비활성")
        self._lbl_status.setStyleSheet("color:#888;font-size:12px;border:none;")
        r2.addWidget(self._lbl_status)
        r2.addStretch()
        self._btn = QPushButton("▶ 감시 시작")
        self._btn.setFixedHeight(28); self._btn.setCheckable(True)
        self._btn.setStyleSheet(self._btn_ss(False))
        self._btn.toggled.connect(self._on_toggle)
        r2.addWidget(self._btn)
        root.addLayout(r2)

        # ── 알림 테이블 ─────────────────────────────────────────
        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["시각(ET)", "방향", "N봉", "봉단위", "현재가"])
        self._tbl.setFont(QFont("Arial", 11))
        self._tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setStyleSheet(get_tbl_style())
        root.addWidget(self._tbl, 1)

    def _btn_ss(self, active: bool) -> str:
        t = _pal()
        if active:
            return ("QPushButton{background:#1a3a1a;color:#00ff88;"
                    "border:1px solid #00ff88;border-radius:4px;"
                    "font-size:11px;font-weight:bold;padding:3px 10px;}"
                    "QPushButton:hover{background:#003300;}")
        return (f"QPushButton{{background:{t.get('btn_bg','#21262d')};"
                f"color:{t.get('widget_fg','#c9d1d9')};"
                f"border:1px solid {t.get('btn_border','#30363d')};"
                "border-radius:4px;font-size:11px;padding:3px 10px;}"
                "QPushButton:hover{background:#30363d;}")

    # ── 시작/중지 토글 ──────────────────────────────────────────
    def _on_toggle(self, checked: bool):
        if checked:
            sym = self._edit_sym.text().strip().upper() or "ES"
            n   = self._sb_n.value()
            m   = self._sb_min.value()
            _dir_map = {0: "up", 1: "dn", 2: "both"}
            direction = _dir_map.get(self._dir_grp.checkedId(), "both")
            self._core.configure(n, m, direction)
            self._core.start()
            self._subscribe(sym)
            self._btn.setText("■ 중지")
            self._btn.setStyleSheet(self._btn_ss(True))
            _dir_label = {"up": "🔺 상승만", "dn": "🔻 하락만", "both": "양방향"}[direction]
            self._lbl_status.setText(
                f"⚡ 감시중  {sym}  {n}봉 × {m}분  {_dir_label}")
            self._lbl_status.setStyleSheet(
                "color:#00ff88;font-size:12px;border:none;")
        else:
            self._core.stop()
            self._unsubscribe()
            self._btn.setText("▶ 감시 시작")
            self._btn.setStyleSheet(self._btn_ss(False))
            self._lbl_status.setText("● 비활성")
            self._lbl_status.setStyleSheet(
                "color:#888;font-size:12px;border:none;")

    # ── IB 구독 ─────────────────────────────────────────────────
    def _subscribe(self, sym: str):
        try:
            # mw.ib 획득 — bridge에는 ib 속성이 없으므로 topLevelWidgets 탐색
            ib = None
            try:
                from PyQt5.QtWidgets import QApplication
                for w in QApplication.topLevelWidgets():
                    _ib = getattr(w, 'ib', None)
                    if _ib is not None:
                        ib = _ib
                        break
            except Exception:
                pass
            if ib is None:
                self._lbl_status.setText("❌ IB 미연결 — TWS 연결 후 다시 시도")
                self._btn.setChecked(False)
                return
            from ibapi.contract import Contract
            ct = Contract()
            ct.symbol   = sym.replace("/", "")
            ct.secType  = "FUT"
            ct.currency = "USD"
            # [FIX] 심볼별 거래소 + 만기월 자동 결정
            _exch = {
                "ES": "CME", "MES": "CME", "NQ": "CME", "MNQ": "CME",
                "RTY": "CME", "M2K": "CME", "YM": "CBOT", "MYM": "CBOT",
                "GC": "COMEX", "SI": "COMEX", "CL": "NYMEX", "NG": "NYMEX",
            }.get(ct.symbol.upper(), "CME")
            ct.exchange = _exch
            ct.lastTradeDateOrContractMonth = ""   # 최근 월물 자동 선택
            # [FIX] bridge signal 방식 — 재연결 시 콜백 소멸 버그 수정
            _req = self._req_id
            # bar_sig → core.on_bar 연결 (최초 1회)
            if not getattr(self, '_bar_sig_connected', False):
                self._bridge.bar_sig.connect(
                    self._core.on_bar, Qt.QueuedConnection)
                self._bar_sig_connected = True
            orig_rtb = getattr(ib, 'realtimeBar', lambda *a: None)
            def _on_bar(reqId, date, open_, high, low, close, vol, wap, cnt,
                        _req=_req):
                try: orig_rtb(reqId, date, open_, high, low, close, vol, wap, cnt)
                except Exception: pass
                if reqId == _req:
                    self._bridge.bar_sig.emit(float(close))
            ib.realtimeBar = _on_bar
            self._ib_ref = ib   # 재연결 감지용 보관
            ib.reqRealTimeBars(self._req_id, ct, 5, "TRADES", False, [])
            print(f"[FuturesMonitor] {sym} 구독 시작 reqId={self._req_id} exch={_exch}")
        except Exception as e:
            print(f"[FuturesMonitor] 구독 오류: {e}")
            self._lbl_status.setText(f"⚠ IB 연결 오류: {e}")

    def resubscribe_on_reconnect(self) -> None:
        """재연결 시 호출 — 감시 중이었으면 자동 재구독."""
        if not self._btn.isChecked():
            return
        sym = self._edit_sym.text().strip().upper() or "ES"
        self._log(f"🔄 재연결 감지 — {sym} 선물 감시 재구독")
        self._subscribe(sym)

    def _unsubscribe(self):
        try:
            from PyQt5.QtWidgets import QApplication
            ib = None
            for w in QApplication.topLevelWidgets():
                _ib = getattr(w, 'ib', None)
                if _ib is not None:
                    ib = _ib
                    break
            if ib: ib.cancelRealTimeBars(self._req_id)
        except Exception:
            pass

    # ── 시그널 수신 ─────────────────────────────────────────────
    def _on_alert(self, direction: str, price: float, n: int):
        if self._chk_sound.isChecked():
            _play_sound(self._sound_path)
        # [ADD] 로그 파일 기록
        _futures_log(direction, price, n)
        # [ADD] 텔레그램 전송
        _futures_tg(direction, price, n)
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S")
        except Exception:
            now = datetime.utcnow().strftime("%H:%M:%S")
        m   = getattr(self, '_sb_min', None)
        min_label = f"{m.value()}분봉" if m else "—"
        r   = self._tbl.rowCount()
        self._tbl.insertRow(r)
        color = QColor("#003300" if "상승" in direction else "#330000")
        for col, text in enumerate([now, direction, f"{n}봉", min_label, f"${price:,.2f}"]):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(color)
            it.setForeground(QColor(
                "#00ff88" if "상승" in direction else "#ff4444"))
            self._tbl.setItem(r, col, it)
        self._tbl.scrollToBottom()

    def _on_price(self, price: float):
        self._lbl_price.setText(f"현재가: ${price:,.2f}")