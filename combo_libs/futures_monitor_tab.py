"""
futures_monitor_tab.py — 📈 선물 감시 탭  v2.0
────────────────────────────────────────────────────────────────────────────
[기존 기능]
  · N봉 연속 상승/하락 감지 → 사운드 + 화면 알림
  · 심볼 직접 입력 (ES, NQ, MES, MNQ 등)
  · 봉 수(N) 설정, 감시 방향 선택 (상승/하락/양방향)
  · 로그 테이블, 텔레그램 전송, CSV 기록

[watch_panel 통합 추가 기능]
  · 조건 타입 선택:
      ① N봉 연속 상승/하락  (틱 데이터로 1분봉 조립 → N봉 감시)
      ② ATM 프리미엄 추적   (기준가 대비 +X% 이상)
      ③ 지지/저항선 근접    (목표가 ± 허용오차 %)
      ④ 쌍바닥              (1차 저점 → 반등Xpt → 재하락)
  · AND 조건: N봉 누적 변동폭 최소값 (CONSEC 전용)
  · 사운드 알람 (paplay / winsound / beep 폴백)
  · 텔레그램 전송 (HTML parse_mode, QThread 비동기)
  · 감시 목록 테이블 (등록된 조건 목록, 개별 삭제)
  · 발화 이력 테이블 (시각 / 조건 / 상세)
  · Cooldown 60초 (동일 조건 재발화 억제)
────────────────────────────────────────────────────────────────────────────
의존:
  · combo_ui_panel_constants.py  (_pal, get_tbl_style)
  · telegram_bot.tg_client       (TelegramClient — 기존 combo 방식)
  · ibapi                        (IB TWS/Gateway)
────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import os, time, threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QLineEdit, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QFrame, QRadioButton, QButtonGroup, QSizePolicy,
)
from PyQt5.QtCore  import Qt, QObject, pyqtSignal, QThread
from PyQt5.QtGui   import QFont, QColor, QBrush

try:
    from combo_ui_panel_constants import _pal, get_tbl_style
except ImportError:
    def _pal():
        return {
            "group_bg": "#0d1117", "widget_fg": "#c9d1d9",
            "pane_bg": "#0d1117", "pane_border": "#30363d",
            "input_bg": "#0d1117", "btn_bg": "#21262d",
            "btn_border": "#30363d", "group_title": "#58a6ff",
            "tab_bg": "#161b22", "tab_fg": "#8b949e",
            "tab_sel_bg": "#0d1117", "tab_sel_fg": "#58a6ff",
        }
    def get_tbl_style():
        return (
            "QTableWidget{background:#0d1117;color:#c9d1d9;"
            "border:1px solid #30363d;gridline-color:#21262d;}"
            "QTableWidget::item{padding:3px 6px;}"
            "QTableWidget::item:selected{background:#1f3d6b;}"
            "QHeaderView::section{background:#161b22;color:#8b949e;"
            "border:none;border-bottom:1px solid #30363d;padding:4px;}"
        )


# ════════════════════════════════════════════════════════════════════════════
# ① 헬퍼: 로그 / 사운드 / 텔레그램
# ════════════════════════════════════════════════════════════════════════════

def _now_et() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S")
    except Exception:
        return datetime.utcnow().strftime("%H:%M:%S")


def _futures_log(direction: str, price: float, n: int, cond_type: str = "CONSEC") -> None:
    """날짜별 CSV 기록"""
    try:
        log_dir = Path(os.path.expanduser("~")) / "trading_logs" / "futures_monitor"
        log_dir.mkdir(parents=True, exist_ok=True)
        fname  = log_dir / f"futures_{datetime.now().strftime('%Y%m%d')}.csv"
        header = not fname.exists()
        with open(fname, "a", encoding="utf-8") as f:
            if header:
                f.write("time_et,cond_type,direction,n_bars,price\n")
            f.write(f"{_now_et()},{cond_type},{direction},{n},{price:.2f}\n")
    except Exception as e:
        print(f"[FuturesMonitor] 로그 기록 실패: {e}")


def _tg_send(msg: str) -> None:
    """텔레그램 비동기 전송 — 실패 시 무시"""
    def _send():
        try:
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get().send("order_confirm", msg)
        except Exception as e:
            print(f"[FuturesMonitor] TG 실패: {e}")
    threading.Thread(target=_send, daemon=True).start()


def _play_sound(path: str = "") -> None:
    def _do():
        try:
            if path:
                from PyQt5.QtMultimedia import QSound
                QSound.play(path); return
        except Exception:
            pass
        try:
            import subprocess
            for _ in range(2):
                subprocess.run(
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.3)
            return
        except Exception:
            pass
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            print("\a", end="", flush=True)
    threading.Thread(target=_do, daemon=True).start()


# ════════════════════════════════════════════════════════════════════════════
# ② 조건 데이터 클래스
# ════════════════════════════════════════════════════════════════════════════

COOLDOWN_SEC  = 60
CLOSE_HISTORY = 30

@dataclass
class WatchCondition:
    cond_id:    str
    cond_type:  str   # CONSEC_UP | CONSEC_DOWN | PREMIUM_PCT | LEVEL | DOUBLE_BOTTOM
    symbol:     str   # 감시 심볼 (선물: ES, NQ … / 지수: SPX, NDX …)

    # CONSEC_*
    n:          int   = 3
    min_pt:     float = 0.0   # AND 누적 변동폭 최소값 (0 = 비활성)

    # PREMIUM_PCT
    pct:        float = 300.0
    base_price: float = 0.0
    opt_symbol: str   = ""
    prem_lo:    float = 1.5
    prem_hi:    float = 2.5

    # LEVEL
    level:      float = 0.0
    tolerance:  float = 0.01   # 허용 오차 %
    direction:  str   = "both" # "above" | "below" | "both"

    # DOUBLE_BOTTOM
    bounce_pt:  float = 10.0
    db_min_min: int   = 30
    db_max_min: int   = 60
    db_tol_pct: float = 0.01

    # 공통 알람
    sound:    bool = True
    telegram: bool = False
    label:    str  = ""

    # 런타임 상태 (repr 제외)
    _last_fired:   float = field(default=0.0,        repr=False, compare=False)
    _close_buf:    deque = field(default_factory=lambda: deque(maxlen=CLOSE_HISTORY),
                                  repr=False, compare=False)
    _last_price:   float = field(default=0.0,        repr=False, compare=False)
    _level_armed:  bool  = field(default=True,       repr=False, compare=False)
    _db_phase:     str   = field(default="watching", repr=False, compare=False)
    _db_bottom1:   float = field(default=0.0,        repr=False, compare=False)
    _db_bottom1_t: float = field(default=0.0,        repr=False, compare=False)
    _db_peak:      float = field(default=0.0,        repr=False, compare=False)
    _db_watch_low: float = field(default=0.0,        repr=False, compare=False)


# ════════════════════════════════════════════════════════════════════════════
# ③ Qt 시그널 브릿지
# ════════════════════════════════════════════════════════════════════════════

class _Bridge(QObject):
    tick_sig   = pyqtSignal(str, float)          # (symbol, price) — 틱 기반 1분봉용
    watch_sig  = pyqtSignal(dict)                # 통합 조건 발화 이벤트
    price_sig  = pyqtSignal(float)               # 현재가 표시용


# ════════════════════════════════════════════════════════════════════════════
# ④ 감시 코어 (스레드 세이프)
# ════════════════════════════════════════════════════════════════════════════

class FuturesMonitorCore:
    """
    · 틱 기반 1분봉 조립 (IND / 지수 심볼용)
    · LEVEL / DOUBLE_BOTTOM 틱 직접 평가
    · PREMIUM_PCT — 외부에서 mid 가격 주입 (_on_option)
    """

    def __init__(self, bridge: _Bridge):
        self._bridge   = bridge
        self._active   = False
        self._lock     = threading.Lock()
        self._conds:   list[WatchCondition] = []

        # 틱 기반 1분봉 버퍼 {sym: {cur_min, open, high, low, close}}
        self._tick_buf: dict = {}


    # ── 조건 CRUD ────────────────────────────────────────────────
    def add_cond(self, cond: WatchCondition):
        with self._lock:
            self._conds.append(cond)

    def remove_cond(self, cond_id: str):
        with self._lock:
            self._conds = [c for c in self._conds if c.cond_id != cond_id]

    def all_conds(self) -> list[WatchCondition]:
        with self._lock:
            return list(self._conds)

    # ── 틱 수신 (지수 심볼 등 realtimeBar 불가 심볼용) ───────────
    def on_tick(self, sym: str, price: float):
        # _active: ① 선물 감시 버튼 ON 상태
        # _ind_active: IND 조건이 1개 이상 등록된 상태 (버튼 무관)
        if price <= 0:
            return
        if not self._active and not getattr(self, '_ind_active', False):
            return
        sym = sym.upper()
        self._bridge.price_sig.emit(price)
        self._build_tick_candle(sym, price)
        self._eval_tick_conds(sym, price)

    def _build_tick_candle(self, sym: str, price: float):
        """틱 → 1분봉 조립; 분이 바뀌면 _eval_candle_conds 호출."""
        needed = any(
            c.cond_type in ("CONSEC_UP", "CONSEC_DOWN") and c.symbol == sym
            for c in self._conds
        )
        if not needed:
            return
        import datetime as _dt
        cur_min = _dt.datetime.now().strftime("%H:%M")
        buf = self._tick_buf.get(sym)
        if buf is None:
            self._tick_buf[sym] = dict(cur_min=cur_min, open=price,
                                        high=price, low=price, close=price)
            return
        if buf["cur_min"] == cur_min:
            buf["high"]  = max(buf["high"],  price)
            buf["low"]   = min(buf["low"],   price)
            buf["close"] = price
        else:
            completed_close = buf["close"]
            self._tick_buf[sym] = dict(cur_min=cur_min, open=price,
                                        high=price, low=price, close=price)
            self._eval_candle_conds(sym, completed_close)

    def _eval_candle_conds(self, sym: str, close: float):
        with self._lock:
            conds = [c for c in self._conds
                     if c.cond_type in ("CONSEC_UP", "CONSEC_DOWN")
                     and c.symbol == sym]
        for c in conds:
            c._close_buf.append(close)
            self._eval_consec(c)

    def _eval_consec_for_sym(self, sym: str, close: float):
        with self._lock:
            conds = [c for c in self._conds
                     if c.cond_type in ("CONSEC_UP", "CONSEC_DOWN")
                     and c.symbol == sym]
        for c in conds:
            c._close_buf.append(close)
            self._eval_consec(c)

    def _eval_tick_conds(self, sym: str, price: float):
        with self._lock:
            conds = [c for c in self._conds
                     if c.cond_type in ("LEVEL", "DOUBLE_BOTTOM")
                     and c.symbol == sym]
        for c in conds:
            if c.cond_type == "LEVEL":
                self._eval_level(c, price)
            elif c.cond_type == "DOUBLE_BOTTOM":
                self._eval_double_bottom(c, price)

    # ── 옵션 mid 수신 (PREMIUM_PCT) ──────────────────────────────
    def on_option(self, sym: str, bid: float, ask: float):
        sym = sym.upper()
        mid = (bid + ask) / 2
        if mid <= 0:
            return
        with self._lock:
            conds = [c for c in self._conds
                     if c.cond_type == "PREMIUM_PCT"
                     and c.opt_symbol.upper() == sym]
        for c in conds:
            if c.base_price > 0:
                pct = (mid / c.base_price - 1) * 100
                if pct >= c.pct:
                    self._fire(c, dict(current=mid, base=c.base_price,
                                       pct=round(pct, 1)))

    # ── 조건 평가 ────────────────────────────────────────────────
    def _eval_consec(self, c: WatchCondition):
        buf = list(c._close_buf)
        if len(buf) < c.n:
            return
        tail = buf[-c.n:]
        if c.cond_type == "CONSEC_UP":
            ok = all(tail[i] > tail[i-1] for i in range(1, len(tail)))
        else:
            ok = all(tail[i] < tail[i-1] for i in range(1, len(tail)))
        if not ok:
            return
        if c.min_pt > 0 and abs(tail[-1] - tail[0]) < c.min_pt:
            return
        self._fire(c, dict(
            closes=[round(x, 2) for x in tail],
            total_pt=round(abs(tail[-1] - tail[0]), 2),
        ))

    def _eval_level(self, c: WatchCondition, price: float):
        tol    = c.level * c.tolerance / 100
        lo, hi = c.level - tol, c.level + tol
        in_zone = lo <= price <= hi
        if c.direction == "above" and price < c.level:
            in_zone = False
        elif c.direction == "below" and price > c.level:
            in_zone = False
        if in_zone and c._level_armed:
            self._fire(c, dict(level=c.level, price=round(price, 2),
                                diff=round(price - c.level, 2),
                                tol_pct=c.tolerance))
            c._level_armed = False
        elif not in_zone:
            c._level_armed = True
        c._last_price = price

    def _eval_double_bottom(self, c: WatchCondition, price: float):
        now = time.monotonic()
        if c._db_phase == "watching":
            if c._last_price == 0.0:
                c._db_bottom1 = c._db_peak = c._db_watch_low = price
                c._db_bottom1_t = now
            elif price < c._db_watch_low:
                c._db_watch_low = price
            drop_needed = c.bounce_pt * 0.5
            if (c._db_watch_low > 0 and c._last_price > 0 and
                    c._last_price - c._db_watch_low >= drop_needed):
                c._db_bottom1   = c._db_watch_low
                c._db_bottom1_t = now
                c._db_peak      = price
                c._db_watch_low = price
                c._db_phase     = "bottom1"
        elif c._db_phase == "bottom1":
            if price > c._db_peak:
                c._db_peak = price
            if c._db_peak - c._db_bottom1 >= c.bounce_pt:
                c._db_phase = "bounced"
        elif c._db_phase == "bounced":
            elapsed_min = (now - c._db_bottom1_t) / 60
            tol = c._db_bottom1 * c.db_tol_pct / 100
            if elapsed_min > c.db_max_min:
                self._reset_db(c, price)
                return
            if elapsed_min >= c.db_min_min and abs(price - c._db_bottom1) <= tol:
                self._fire(c, dict(
                    bottom1=round(c._db_bottom1, 2),
                    peak=round(c._db_peak, 2),
                    bounce_pt=round(c._db_peak - c._db_bottom1, 1),
                    current=round(price, 2),
                    elapsed_min=round(elapsed_min, 1),
                    diff=round(price - c._db_bottom1, 2),
                ))
                self._reset_db(c, price)
        c._last_price = price

    def _reset_db(self, c: WatchCondition, price: float):
        c._db_phase     = "watching"
        c._db_bottom1   = price
        c._db_bottom1_t = time.monotonic()
        c._db_peak      = price
        c._db_watch_low = price

    def _fire(self, c: WatchCondition, detail: dict):
        now = time.monotonic()
        if now - c._last_fired < COOLDOWN_SEC:
            return
        c._last_fired = now
        self._bridge.watch_sig.emit({
            "cond_id":   c.cond_id,
            "cond_type": c.cond_type,
            "symbol":    c.symbol,
            "label":     c.label or c.cond_id,
            "sound":     c.sound,
            "telegram":  c.telegram,
            "detail":    detail,
        })


# ════════════════════════════════════════════════════════════════════════════
# ⑤ UI 탭 위젯
# ════════════════════════════════════════════════════════════════════════════

_TYPE_MAP = {
    0: "CONSEC_UP",
    1: "CONSEC_DOWN",
    2: "PREMIUM_PCT",
    3: "LEVEL",
    4: "DOUBLE_BOTTOM",
}
_TYPE_LABEL = {
    "CONSEC_UP":     "N봉↑",
    "CONSEC_DOWN":   "N봉↓",
    "PREMIUM_PCT":   "프리미엄%",
    "LEVEL":         "지지/저항",
    "DOUBLE_BOTTOM": "쌍바닥",
}
_DIR_MAP = {0: "both", 1: "above", 2: "below"}


class FuturesMonitorTab(QWidget):
    """
    선물 감시 탭 — 기존 N봉 감시 + watch_panel 전체 조건 통합
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge     = _Bridge()
        self._core       = FuturesMonitorCore(self._bridge)
        self._sound_path = ""
        self._cond_rows: dict[str, int] = {}   # cond_id → 감시 목록 row

        self._build_ui()
        self._connect_signals()

    # ════════════════════════════════════════════════════════════
    # UI 구성
    # ════════════════════════════════════════════════════════════

    def _build_ui(self):
        t   = _pal()
        fg  = t.get("widget_fg",  "#c9d1d9")
        bg  = t.get("group_bg",   "#161b22")
        bdr = t.get("pane_border","#30363d")
        inp = t.get("input_bg",   "#0d1117")
        acc = t.get("group_title","#58a6ff")

        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(6, 6, 6, 6)

        # ─── 공통 스타일 헬퍼 ───────────────────────────────────
        _GRP = (f"QGroupBox{{color:{fg};font-size:9pt;"
                f"border:1px solid {bdr};border-radius:4px;margin-top:8px;}}"
                f"QGroupBox::title{{subcontrol-origin:margin;"
                f"left:8px;padding:0 4px;}}")
        _CMB = (f"QComboBox{{background:{inp};color:{fg};"
                f"border:1px solid {bdr};border-radius:3px;"
                "font-size:10pt;padding:2px 6px;}"
                f"QComboBox::drop-down{{border:none;}}"
                f"QComboBox QAbstractItemView{{background:{inp};color:{fg};}}")
        _SPN = (f"QSpinBox,QDoubleSpinBox{{background:{inp};color:{fg};"
                f"border:1px solid {bdr};border-radius:3px;"
                "font-size:10pt;padding:2px;}"
                "QSpinBox::up-button,QSpinBox::down-button,"
                "QDoubleSpinBox::up-button,QDoubleSpinBox::down-button"
                f"{{background:{bdr};width:14px;}}")
        _EDT = (f"QLineEdit{{background:{inp};color:{fg};"
                f"border:1px solid {bdr};border-radius:3px;"
                "font-size:10pt;padding:2px 6px;}")
        _CHK = (f"QCheckBox{{color:{fg};font-size:9pt;background:transparent;}}"
                "QCheckBox::indicator{width:13px;height:13px;}"
                "QCheckBox::indicator:checked{background:#3FB950;"
                "border:1px solid #3FB950;border-radius:2px;}"
                "QCheckBox::indicator:unchecked{"
                f"background:{inp};border:1px solid {bdr};border-radius:2px;}}")
        _RB  = f"QRadioButton{{color:{fg};font-size:10pt;background:transparent;}}"
        _BTN_OK  = ("QPushButton{background:#1A3D2B;color:#3FB950;"
                    "border:2px solid #3FB950;border-radius:4px;"
                    "font-size:10pt;font-weight:bold;padding:4px 12px;}"
                    "QPushButton:hover{background:#3FB950;color:#000;}")

        def lbl(text, color=""):
            l = QLabel(text)
            l.setStyleSheet(f"color:{color or fg};font-size:9pt;background:transparent;")
            return l

        def hline():
            f = QFrame(); f.setFrameShape(QFrame.HLine)
            f.setFixedHeight(1)
            f.setStyleSheet(f"background:{bdr};border:none;")
            return f

        # ════════════════════════════════════════════════════════
        # ② 조건 등록 그룹 (watch_panel 통합)
        # ════════════════════════════════════════════════════════
        reg_grp = QGroupBox("① 감시 조건 등록 (N봉/프리미엄/지지저항/쌍바닥)")
        reg_grp.setStyleSheet(_GRP)
        regl = QVBoxLayout(reg_grp)
        regl.setSpacing(4); regl.setContentsMargins(6, 14, 6, 6)

        # 타입 + 심볼
        cr1 = QHBoxLayout(); cr1.setSpacing(6)
        cr1.addWidget(lbl("타입:"))
        self._type_cmb = QComboBox()
        self._type_cmb.setStyleSheet(_CMB); self._type_cmb.setFixedWidth(165)
        self._type_cmb.addItems([
            "N봉 연속 상승",
            "N봉 연속 하락",
            "ATM 프리미엄 추적",
            "지지/저항선 근접",
            "쌍바닥",
        ])
        self._type_cmb.currentIndexChanged.connect(self._on_type_changed)
        cr1.addWidget(self._type_cmb)
        cr1.addSpacing(8)
        cr1.addWidget(lbl("심볼:"))
        self._sym_cmb = QComboBox()
        self._sym_cmb.setStyleSheet(_CMB); self._sym_cmb.setFixedWidth(95)
        self._sym_cmb.addItems(["ES", "NQ", "RTY", "YM", "MES", "MNQ",
                                 "SPX", "NDX", "RUT"])
        self._sym_cmb.setEditable(True)
        cr1.addWidget(self._sym_cmb)
        cr1.addStretch()
        regl.addLayout(cr1)

        # ── 파라미터 행: N봉 연속 ────────────────────────────────
        self._consec_row = QWidget()
        crl = QHBoxLayout(self._consec_row)
        crl.setContentsMargins(0, 0, 0, 0); crl.setSpacing(6)
        crl.addWidget(lbl("연속 봉 수:"))
        self._c_n_spin = self._make_spin(2, 20, 3, _SPN, w=64)
        crl.addWidget(self._c_n_spin)
        crl.addSpacing(10)
        self._pt_chk = QCheckBox("AND ≥")
        self._pt_chk.setStyleSheet(_CHK)
        self._pt_chk.setToolTip("누적 변동폭 최소값 조건 활성화")
        crl.addWidget(self._pt_chk)
        self._pt_spin = self._make_dspin(0.5, 500.0, 5.0, _SPN, w=82, suffix=" pt")
        self._pt_spin.setEnabled(False)
        self._pt_chk.stateChanged.connect(lambda s: self._pt_spin.setEnabled(bool(s)))
        crl.addWidget(self._pt_spin)
        crl.addStretch()
        regl.addWidget(self._consec_row)

        # ── 파라미터 행: ATM 프리미엄 ────────────────────────────
        self._prem_row = QWidget()
        prl = QHBoxLayout(self._prem_row)
        prl.setContentsMargins(0, 0, 0, 0); prl.setSpacing(6)
        prl.addWidget(lbl("목표 상승률:"))
        self._pct_spin = self._make_dspin(50, 2000, 300, _SPN, w=90, suffix=" %")
        prl.addWidget(self._pct_spin)
        prl.addSpacing(8)
        prl.addWidget(lbl("프리미엄 범위:"))
        self._prem_lo = self._make_dspin(0.1, 50, 1.5, _SPN, w=72, prefix="$")
        prl.addWidget(self._prem_lo)
        prl.addWidget(lbl("~"))
        self._prem_hi = self._make_dspin(0.1, 50, 2.5, _SPN, w=72, prefix="$")
        prl.addWidget(self._prem_hi)
        prl.addStretch()
        self._prem_row.setVisible(False)
        regl.addWidget(self._prem_row)

        # ── 파라미터 행: 지지/저항선 ─────────────────────────────
        self._level_row = QWidget()
        lvl = QHBoxLayout(self._level_row)
        lvl.setContentsMargins(0, 0, 0, 0); lvl.setSpacing(6)
        lvl.addWidget(lbl("목표가:"))
        self._level_spin = self._make_dspin(1, 999999, 5000, _SPN, w=100, decimals=2)
        lvl.addWidget(self._level_spin)
        lvl.addSpacing(8)
        lvl.addWidget(lbl("오차:"))
        self._tol_spin = self._make_dspin(0.001, 1.0, 0.01, _SPN, w=82,
                                           decimals=3, suffix=" %")
        lvl.addWidget(self._tol_spin)
        lvl.addSpacing(8)
        lvl.addWidget(lbl("방향:"))
        self._dir_cmb = QComboBox()
        self._dir_cmb.setStyleSheet(_CMB); self._dir_cmb.setFixedWidth(120)
        self._dir_cmb.addItems(["양방향", "위(저항돌파)", "아래(지지이탈)"])
        lvl.addWidget(self._dir_cmb)
        lvl.addStretch()
        self._level_row.setVisible(False)
        regl.addWidget(self._level_row)

        # ── 파라미터 행: 쌍바닥 ──────────────────────────────────
        self._db_row = QWidget()
        dbl = QHBoxLayout(self._db_row)
        dbl.setContentsMargins(0, 0, 0, 0); dbl.setSpacing(6)
        dbl.addWidget(lbl("반등 최소:"))
        self._bounce_spin = self._make_dspin(1, 9999, 10, _SPN, w=82, suffix=" pt")
        dbl.addWidget(self._bounce_spin)
        dbl.addSpacing(6)
        dbl.addWidget(lbl("유효시간:"))
        self._db_min_spin = self._make_spin(5, 240, 30, _SPN, w=72, suffix=" 분")
        dbl.addWidget(self._db_min_spin)
        dbl.addWidget(lbl("~"))
        self._db_max_spin = self._make_spin(5, 480, 60, _SPN, w=72, suffix=" 분")
        dbl.addWidget(self._db_max_spin)
        dbl.addSpacing(6)
        dbl.addWidget(lbl("오차:"))
        self._db_tol_spin = self._make_dspin(0.001, 1.0, 0.01, _SPN, w=78,
                                              decimals=3, suffix=" %")
        dbl.addWidget(self._db_tol_spin)
        dbl.addStretch()
        self._db_row.setVisible(False)
        regl.addWidget(self._db_row)

        # 알람 옵션 + 등록 버튼
        cr3 = QHBoxLayout(); cr3.setSpacing(6)
        self._sound_chk = QCheckBox("🔔 사운드")
        self._sound_chk.setStyleSheet(_CHK); self._sound_chk.setChecked(True)
        cr3.addWidget(self._sound_chk)
        self._tg_chk = QCheckBox("📨 텔레그램")
        self._tg_chk.setStyleSheet(_CHK)
        cr3.addWidget(self._tg_chk)
        cr3.addStretch()
        self._add_btn = QPushButton("＋ 등록")
        self._add_btn.setStyleSheet(_BTN_OK)
        self._add_btn.clicked.connect(self._on_add)
        cr3.addWidget(self._add_btn)
        regl.addLayout(cr3)
        root.addWidget(reg_grp)

        # ════════════════════════════════════════════════════════
        # ③ 감시 목록 테이블
        # ════════════════════════════════════════════════════════
        list_grp = QGroupBox("② 등록된 감시 조건 목록")
        list_grp.setStyleSheet(_GRP)
        ll = QVBoxLayout(list_grp)
        ll.setContentsMargins(4, 14, 4, 4)
        self._tbl_cond = QTableWidget(0, 5)
        self._tbl_cond.setStyleSheet(get_tbl_style())
        self._tbl_cond.setHorizontalHeaderLabels(["조건", "심볼", "파라미터", "알람", ""])
        self._tbl_cond.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_cond.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_cond.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_cond.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_cond.verticalHeader().setVisible(False)
        self._tbl_cond.setFixedHeight(140)
        ll.addWidget(self._tbl_cond)
        root.addWidget(list_grp)

        # ════════════════════════════════════════════════════════
        # ④ 발화 이력 테이블
        # ════════════════════════════════════════════════════════
        log_grp = QGroupBox("③ 발화 이력")
        log_grp.setStyleSheet(_GRP)
        logl = QVBoxLayout(log_grp)
        logl.setContentsMargins(4, 14, 4, 4)
        self._tbl_log = QTableWidget(0, 4)
        self._tbl_log.setStyleSheet(get_tbl_style())
        self._tbl_log.setHorizontalHeaderLabels(["시각(ET)", "조건", "심볼", "상세"])
        self._tbl_log.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._tbl_log.verticalHeader().setVisible(False)
        self._tbl_log.setEditTriggers(QAbstractItemView.NoEditTriggers)
        btn_clear = QPushButton("🗑 이력 지우기")
        btn_clear.setFixedHeight(22)
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{bg};color:#ff6666;"
            f"border:1px solid #5a1a1a;border-radius:3px;font-size:10px;padding:1px 8px;}}"
            f"QPushButton:hover{{background:#2a0a0a;}}")
        btn_clear.clicked.connect(lambda: self._tbl_log.setRowCount(0))
        logl.addWidget(btn_clear)
        logl.addWidget(self._tbl_log)
        root.addWidget(log_grp)

        # 상태 라벨
        self._lbl_status = QLabel("조건을 등록하면 자동으로 감시가 시작됩니다")
        self._lbl_status.setStyleSheet("color:#484F58;font-size:9pt;background:transparent;")
        root.addWidget(self._lbl_status)

    # ════════════════════════════════════════════════════════════
    # 시그널 연결
    # ════════════════════════════════════════════════════════════

    def _connect_signals(self):
        self._bridge.watch_sig.connect(self._on_watch_alert)
        self._bridge.price_sig.connect(self._on_price)

    # ════════════════════════════════════════════════════════════
    # ② 조건 등록 / 삭제
    # ════════════════════════════════════════════════════════════

    def _on_type_changed(self, idx: int):
        self._consec_row.setVisible(idx in (0, 1))
        self._prem_row.setVisible(idx == 2)
        self._level_row.setVisible(idx == 3)
        self._db_row.setVisible(idx == 4)

    def _on_add(self):
        import uuid
        idx    = self._type_cmb.currentIndex()
        ctype  = _TYPE_MAP.get(idx, "CONSEC_UP")
        symbol = self._sym_cmb.currentText().strip().upper()
        if not symbol:
            self._set_status("⚠ 심볼을 입력하세요"); return

        cond_id = f"{ctype}_{symbol}_{int(time.time())}"
        sound   = self._sound_chk.isChecked()
        tg      = self._tg_chk.isChecked()

        if ctype in ("CONSEC_UP", "CONSEC_DOWN"):
            n      = self._c_n_spin.value()
            use_pt = self._pt_chk.isChecked()
            min_pt = self._pt_spin.value() if use_pt else 0.0
            arrow  = "연속↑" if ctype == "CONSEC_UP" else "연속↓"
            pt_sfx = f" AND≥{min_pt:.1f}pt" if use_pt else ""
            label  = f"{symbol} {n}봉 {arrow}{pt_sfx}"
            param  = f"연속 {n}봉{pt_sfx}"
            cond   = WatchCondition(cond_id=cond_id, cond_type=ctype,
                                    symbol=symbol, n=n, min_pt=min_pt,
                                    sound=sound, telegram=tg, label=label)

        elif ctype == "PREMIUM_PCT":
            pct   = self._pct_spin.value()
            lo    = self._prem_lo.value()
            hi    = self._prem_hi.value()
            label = f"{symbol} ATM프리미엄 +{pct:.0f}%"
            param = f"+{pct:.0f}% | ${lo:.1f}~${hi:.1f}"
            cond  = WatchCondition(cond_id=cond_id, cond_type="PREMIUM_PCT",
                                   symbol=symbol, pct=pct,
                                   prem_lo=lo, prem_hi=hi,
                                   sound=sound, telegram=tg, label=label)

        elif ctype == "LEVEL":
            level = self._level_spin.value()
            tol   = self._tol_spin.value()
            direc = _DIR_MAP.get(self._dir_cmb.currentIndex(), "both")
            dtxt  = ["양방향", "위(저항↑)", "아래(지지↓)"][self._dir_cmb.currentIndex()]
            label = f"{symbol} {level:.0f} 근접 ({dtxt})"
            param = f"목표 {level:.2f} ±{tol:.3f}%"
            cond  = WatchCondition(cond_id=cond_id, cond_type="LEVEL",
                                   symbol=symbol, level=level,
                                   tolerance=tol, direction=direc,
                                   sound=sound, telegram=tg, label=label)

        else:  # DOUBLE_BOTTOM
            bounce  = self._bounce_spin.value()
            db_min  = self._db_min_spin.value()
            db_max  = self._db_max_spin.value()
            db_tol  = self._db_tol_spin.value()
            label   = f"{symbol} 쌍바닥 ({db_min}~{db_max}분)"
            param   = f"반등 {bounce:.0f}pt | {db_min}~{db_max}분 | ±{db_tol:.3f}%"
            cond    = WatchCondition(cond_id=cond_id, cond_type="DOUBLE_BOTTOM",
                                     symbol=symbol, bounce_pt=bounce,
                                     db_min_min=db_min, db_max_min=db_max,
                                     db_tol_pct=db_tol,
                                     sound=sound, telegram=tg, label=label)

        self._core.add_cond(cond)
        self._add_cond_row(cond, param)
        # ★ 등록 즉시 해당 심볼 가격 구독 자동 시작
        self._ensure_subscribed(symbol, cond.cond_type)
        self._set_status(f"✅ 등록: {label}")

    def _add_cond_row(self, cond: WatchCondition, param: str):
        row = self._tbl_cond.rowCount()
        self._tbl_cond.insertRow(row)
        self._cond_rows[cond.cond_id] = row
        alarm = ("🔔" if cond.sound else "") + ("📨" if cond.telegram else "")
        for col, txt in enumerate([
            _TYPE_LABEL.get(cond.cond_type, cond.cond_type),
            cond.symbol, param, alarm,
        ]):
            it = QTableWidgetItem(txt)
            it.setForeground(QColor("#E6EDF3"))
            it.setTextAlignment(Qt.AlignCenter)
            self._tbl_cond.setItem(row, col, it)
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 22)
        del_btn.setStyleSheet(
            "QPushButton{background:#1C2128;color:#484F58;border:none;}"
            "QPushButton:hover{color:#F85149;}")
        del_btn.clicked.connect(lambda _, cid=cond.cond_id: self._on_delete(cid))
        self._tbl_cond.setCellWidget(row, 4, del_btn)

    def _on_delete(self, cond_id: str):
        # 삭제 전 심볼 파악
        deleted = next((c for c in self._core.all_conds() if c.cond_id == cond_id), None)

        row = self._cond_rows.pop(cond_id, -1)
        if row >= 0:
            self._tbl_cond.removeRow(row)
            self._cond_rows = {
                cid: (r - 1 if r > row else r)
                for cid, r in self._cond_rows.items()}
        self._core.remove_cond(cond_id)

        # IND(SPX 등) 조건이 하나도 없으면 _ind_active 해제
        if deleted and deleted.symbol.upper() in self._IND_SYMS:
            any_ind_left = any(
                c.symbol.upper() in self._IND_SYMS
                for c in self._core.all_conds()
            )
            self._core._ind_active = any_ind_left

    # ════════════════════════════════════════════════════════════
    # ③ 발화 이벤트 처리 (등록 조건)
    # ════════════════════════════════════════════════════════════

    def _on_watch_alert(self, data: dict):
        label    = data.get("label", "")
        ctype    = data.get("cond_type", "")
        symbol   = data.get("symbol", "")
        detail   = data.get("detail", {})
        detail_s = self._format_detail(ctype, detail)
        now      = _now_et()

        if data.get("sound"):
            _play_sound(self._sound_path)
        if data.get("telegram"):
            _tg_send(self._tg_format(now, label, ctype, symbol, detail, detail_s))

        _futures_log(label, detail.get("closes", [detail.get("price", 0)])[-1]
                     if isinstance(detail.get("closes"), list)
                     else detail.get("price", detail.get("current", 0)),
                     data.get("detail", {}).get("n", 0), ctype)
        self._add_log_row(now, _TYPE_LABEL.get(ctype, ctype), symbol, detail_s,
                          up=(ctype == "CONSEC_UP" or
                              (ctype == "LEVEL" and detail.get("diff", 0) >= 0)))
        self._set_status(f"🚨 {label} — {detail_s}")

    def _format_detail(self, ctype: str, d: dict) -> str:
        if ctype in ("CONSEC_UP", "CONSEC_DOWN"):
            closes  = d.get("closes", [])
            flow    = " → ".join(f"{c:.2f}" for c in closes[-4:])
            total   = d.get("total_pt", 0)
            sign    = "+" if closes and closes[-1] >= closes[0] else "-"
            if total:
                flow += f"  ({sign}{total:.2f}pt)"
            return flow
        elif ctype == "PREMIUM_PCT":
            return (f"${d.get('base',0):.2f}→${d.get('current',0):.2f}"
                    f" (+{d.get('pct',0):.1f}%)")
        elif ctype == "LEVEL":
            diff = d.get("diff", 0)
            sign = "+" if diff >= 0 else ""
            return (f"목표 {d.get('level',0):.2f} | "
                    f"현재 {d.get('price',0):.2f} ({sign}{diff:.2f})")
        elif ctype == "DOUBLE_BOTTOM":
            return (f"저점1 {d.get('bottom1',0):.2f} | "
                    f"반등 +{d.get('bounce_pt',0):.1f}pt | "
                    f"현재 {d.get('current',0):.2f} | "
                    f"{d.get('elapsed_min',0):.0f}분 경과")
        return str(d)

    def _tg_format(self, now: str, label: str, ctype: str,
                   symbol: str, d: dict, detail_s: str) -> str:
        if ctype in ("CONSEC_UP", "CONSEC_DOWN"):
            closes = d.get("closes", [])
            arrow  = "↑" if ctype == "CONSEC_UP" else "↓"
            n      = len(closes) or d.get("n", "?")
            flow   = " → ".join(f"{c:.2f}" for c in closes[-5:]) if closes else detail_s
            delta  = (f"+{closes[-1]-closes[0]:.2f}pt"
                      if len(closes) >= 2 else "")
            lines  = [f"🚨 [{now}] <b>{symbol} {n}봉 연속{arrow}</b>", flow]
            if delta:
                lines.append(delta)
            return "\n".join(lines)
        return f"🚨 [{now}] <b>{label}</b>\n{detail_s}"

    # ════════════════════════════════════════════════════════════
    # 로그 테이블 행 추가
    # ════════════════════════════════════════════════════════════

    def _add_log_row(self, ts: str, direction: str, sym: str,
                     detail: str, up: bool = True):
        row = self._tbl_log.rowCount()
        self._tbl_log.insertRow(row)
        color_fg = QColor("#00ff88" if up else "#ff4444")
        color_bg = QColor("#003300" if up else "#330000")
        for col, txt in enumerate([ts, direction, sym, detail]):
            it = QTableWidgetItem(txt)
            it.setTextAlignment(Qt.AlignCenter)
            it.setBackground(color_bg)
            it.setForeground(color_fg)
            self._tbl_log.setItem(row, col, it)
        self._tbl_log.scrollToBottom()

    # ════════════════════════════════════════════════════════════
    # IB 구독 / 해제
    # ════════════════════════════════════════════════════════════

    # SPX 등 기초자산 — 콜-풋 탭이 이미 REQ_UND로 구독 중인 price_tick_sig 사용
    # IND 전용 reqMktData 불필요
    _IND_SYMS = {"SPX", "NDX", "RUT", "VIX", "DJI"}

    def _ensure_subscribed(self, symbol: str, cond_type: str):
        """
        조건 등록 시 호출.
        bridge_price_tick.subscribe() 로 REQ_UND(SPX) 또는
        선물 reqId(7701) 틱을 필터링해서 수신.
        """
        sym = symbol.upper()

        # tick_sig → core.on_tick 연결 (최초 1회)
        if not getattr(self, "_tick_sig_connected", False):
            self._bridge.tick_sig.connect(
                self._core.on_tick, Qt.QueuedConnection)
            self._tick_sig_connected = True

        if sym in self._IND_SYMS:
            # SPX 등 — price_tick_sig 는 이미 콜-풋 탭이 REQ_UND 로 구독 중
            # REQ_UND reqId 필터로 구독만 추가
            if not getattr(self, "_spx_tick_connected", False):
                try:
                    from core import REQ_UND
                    from bridge_price_tick import subscribe as pt_subscribe
                    _self = self
                    _sym  = sym

                    def _on_und_tick(req_id, tick_type, price,
                                     _r=REQ_UND, _s=_sym):
                        if req_id == _r and tick_type in (4, 68, 2) and price > 0:
                            _self._bridge.tick_sig.emit(_s, float(price))

                    pt_subscribe(_on_und_tick, req_ids={REQ_UND})
                    self._und_tick_cb      = _on_und_tick  # GC 방지
                    self._spx_tick_connected = True
                    self._core._ind_active = True
                    self._set_status(f"📡 {sym} price_tick_sig 구독 시작")
                except Exception as e:
                    self._set_status(f"⚠ price_tick_sig 구독 실패: {e}")
            else:
                self._core._ind_active = True

        else:
            # 선물 (ES, NQ 등) — reqMktData 후 reqId=7701 필터로 구독
            if not getattr(self, "_fut_subscribed_syms", None):
                self._fut_subscribed_syms = set()
            if sym not in self._fut_subscribed_syms:
                self._core._active = True
                self._core._current_sym = sym
                self._subscribe(sym)
                self._fut_subscribed_syms.add(sym)
                self._set_status(f"📡 {sym} 선물 구독 시작")

    def _subscribe(self, sym: str):
        try:
            ib = self._find_ib()
            if ib is None:
                self._set_status("❌ IB 미연결 — TWS 연결 후 다시 시도"); return

            from ibapi.contract import Contract
            from bridge_price_tick import subscribe as pt_subscribe

            ct = Contract()
            ct.symbol   = sym.replace("/", "")
            ct.secType  = "FUT"
            ct.currency = "USD"
            ct.exchange = {
                "ES": "CME", "MES": "CME", "NQ": "CME", "MNQ": "CME",
                "RTY": "CME", "M2K": "CME", "YM": "CBOT", "MYM": "CBOT",
                "GC": "COMEX", "SI": "COMEX", "CL": "NYMEX", "NG": "NYMEX",
            }.get(ct.symbol.upper(), "CME")
            ct.lastTradeDateOrContractMonth = ""

            _req  = 7701
            _sym  = sym
            _self = self

            def _on_fut_tick(req_id, tick_type, price,
                             _r=_req, _s=_sym):
                if req_id == _r and tick_type in (4, 68, 2) and price > 0:
                    _self._bridge.tick_sig.emit(_s, float(price))

            # bridge_price_tick 라우터에 reqId=7701 필터로 구독
            pt_subscribe(_on_fut_tick, req_ids={_req})
            self._fut_tick_cb = _on_fut_tick  # GC 방지

            ib.reqMktData(_req, ct, "", False, False, [])
            print(f"[FuturesMonitor] {sym} 선물 reqMktData 구독 reqId={_req}")
        except Exception as e:
            self._set_status(f"⚠ {sym} 구독 실패: {e}")
            print(f"[FuturesMonitor] 구독 오류: {e}")

    def _unsubscribe(self):
        try:
            from bridge_price_tick import unsubscribe as pt_unsub
            if getattr(self, "_fut_tick_cb", None):
                pt_unsub(self._fut_tick_cb)
            if getattr(self, "_und_tick_cb", None):
                pt_unsub(self._und_tick_cb)
                self._spx_tick_connected = False
            ib = self._find_ib()
            if ib:
                ib.cancelMktData(7701)
        except Exception as e:
            print(f"[FuturesMonitor] 구독 해제 오류: {e}")

    def _find_ib(self):
        try:
            from PyQt5.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                _ib = getattr(w, "ib", None)
                if _ib is not None:
                    return _ib
        except Exception:
            pass
        return None

    def resubscribe_on_reconnect(self) -> None:
        """재연결 시 호출 — 등록된 선물 심볼 자동 재구독."""
        for sym in getattr(self, "_fut_subscribed_syms", set()):
            self._set_status(f"🔄 재연결 감지 — {sym} 선물 감시 재구독")
            self._subscribe(sym)

    # ════════════════════════════════════════════════════════════
    # 가격 표시
    # ════════════════════════════════════════════════════════════

    def _on_price(self, price: float):
        pass  # 현재가 표시 위젯 없음 (필요시 _lbl_status 사용)

    # ════════════════════════════════════════════════════════════
    # 상태 표시
    # ════════════════════════════════════════════════════════════

    def _set_status(self, t: str):
        self._lbl_status.setText(t)

    # ════════════════════════════════════════════════════════════
    # 위젯 헬퍼
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _make_spin(lo, hi, val, style, w=70, suffix="") -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi); s.setValue(val)
        if suffix: s.setSuffix(suffix)
        s.setFixedWidth(w); s.setFixedHeight(26)
        s.setStyleSheet(style)
        return s

    @staticmethod
    def _make_dspin(lo, hi, val, style, w=80, suffix="", prefix="",
                    decimals=1) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(lo, hi); s.setValue(val)
        s.setDecimals(decimals)
        if suffix: s.setSuffix(suffix)
        if prefix: s.setPrefix(prefix)
        s.setFixedWidth(w); s.setFixedHeight(26)
        s.setStyleSheet(style)
        return s
