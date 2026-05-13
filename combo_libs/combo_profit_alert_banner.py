"""
combo_profit_alert_banner.py — 수익률 경고 배너 + 5초 TG/사운드  v4.1
──────────────────────────────────────────────────────────────────────
v4.1 변경:
  [FIX-THR] 임계값(L1/L2/L3) JSON 파일 저장/로드
    · 저장 위치: data/profit_alert_settings.json
    · 기본값: L1=350% / L2=450% / L3=500%
    · 폼 로딩 시 파일값 자동 적용
    · load_thresholds() / save_thresholds() 공개 함수 추가

수익률 L1%+ 진입 시:
  · 5초마다 텔레그램 알림 반복
  · 5초마다 사운드 재생 반복
  · 구간 상승 시(L1→L2→L3) 즉시 추가 알림

테스트 패널 (▶ TEST 클릭):
  [ 0% ][ 400% ][ 460% ][ 510% ][ 📨 TG ][ 🐺 ON ][ ○ OFF ][ ⏱ 감시 ][ ↺ 리셋 ]
──────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import json
import subprocess
import threading
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                              QLabel, QPushButton, QFileDialog)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont

# ── 수익률 임계값 설정 파일 ─────────────────────────────────────────
_SETTINGS_PATH = Path(__file__).resolve().parent / "data" / "profit_alert_settings.json"
_THRESHOLD_DEFAULTS = {"t1": 350, "t2": 450, "t3": 500}


def load_thresholds() -> dict:
    """저장된 임계값 로드. 파일 없으면 기본값(350/450/500) 반환."""
    try:
        if _SETTINGS_PATH.exists():
            v = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            return {
                "t1": int(v.get("t1", _THRESHOLD_DEFAULTS["t1"])),
                "t2": int(v.get("t2", _THRESHOLD_DEFAULTS["t2"])),
                "t3": int(v.get("t3", _THRESHOLD_DEFAULTS["t3"])),
            }
    except Exception as e:
        print(f"[ProfitBanner] 설정 로드 실패: {e}")
    return _THRESHOLD_DEFAULTS.copy()


def save_thresholds(t1: int, t2: int, t3: int) -> None:
    """임계값을 JSON 파일로 저장."""
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(
            json.dumps({"t1": t1, "t2": t2, "t3": t3}, indent=2),
            encoding="utf-8")
        print(f"[ProfitBanner] 임계값 저장: {t1}% / {t2}% / {t3}%")
    except Exception as e:
        print(f"[ProfitBanner] 설정 저장 실패: {e}")


def _build_levels(t1: int, t2: int, t3: int) -> list:
    """임계값 기반 구간 리스트 생성."""
    return [
        (t3, 9999, "#3b0000", "#ff4444", "🚨",
         f"{t3}%+ 수익확보  반대포지션 1계약 매수 검토"),
        (t2,  t3 - 1, "#2d1a00", "#ff8c00", "⚠️",
         f"수익 {t2}%+  전략 전환 검토 구간"),
        (t1,  t2 - 1, "#2a2200", "#f0c040", "💡",
         f"수익 {t1}%+  반대 포지션 선매수 고려"),
        (  0,  t1 - 1, "#0d1520", "#3a4a5a", "📊",
         "수익률 정상 보유 구간"),
    ]


# 모듈 로드 시 파일에서 임계값 읽어 구간 초기화
_thr             = load_thresholds()
_LEVELS          = _build_levels(_thr["t1"], _thr["t2"], _thr["t3"])
_ALERT_THRESHOLD = _thr["t1"]   # L1 이상부터 알림 시작
_ALERT_INTERVAL  = 5_000         # 5초

_BTN_BASE = (
    "QPushButton{background:#111827;color:#778899;border:1px solid #334455;"
    "border-radius:3px;padding:2px 7px;font-size:10px;}"
    "QPushButton:hover{background:#1e2d3d;color:#aabbcc;}"
    "QPushButton:pressed{background:#0d1a26;}"
)

_DEFAULT_SOUND_DIRS = [
    "/usr/share/sounds/freedesktop/stereo",
    "/usr/share/sounds/ubuntu/stereo",
    "/usr/share/sounds/LinuxMint",
    "/usr/share/sounds",
]


def calc_sell_pct(entry: float, current: float) -> float:
    if not entry or entry <= 0:
        return 0.0
    return round((entry - current) / entry * 100, 1)


def calc_buy_pct(entry: float, current: float) -> float:
    if not entry or entry <= 0:
        return 0.0
    return round((current - entry) / entry * 100, 1)


def _play_sound(path: str) -> None:
    """별도 스레드에서 사운드 재생."""
    if not path:
        return
    def _run():
        for cmd in (
            ["paplay", path],
            ["aplay", "-q", path],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
        ):
            try:
                subprocess.run(cmd, timeout=4,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                return
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
    threading.Thread(target=_run, daemon=True).start()


def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[ProfitBanner] TG 실패: {e}")


def _level_tag(pct: float, t1: int = 350, t2: int = 450, t3: int = 500) -> str:
    """수익률 → 구간 태그 반환 (임계값 반영)."""
    if pct >= t3: return f"{t3}%+"
    if pct >= t2: return f"{t2}%+"
    if pct >= t1: return f"{t1}%+"
    return "정상"


# ══════════════════════════════════════════════════════════════════
class ProfitAlertBanner(QWidget):
    """수익률 경고 배너 + 5초 TG/사운드 + 테스트 패널."""

    def __init__(self, parent=None, wolf_banner=None):
        super().__init__(parent)
        self._pct          = 0.0
        self._prev_level   = ""       # 이전 구간 태그 (구간 변화 감지용)
        self._wolf         = wolf_banner
        self._test_open    = False
        self._sound_path   = ""
        self._alert_count  = 0

        # [FIX-THR] 폼 로딩 시 파일에서 임계값 읽어 인스턴스 변수로 저장
        _thr = load_thresholds()
        self._t1              = _thr["t1"]
        self._t2              = _thr["t2"]
        self._t3              = _thr["t3"]
        self._levels          = _build_levels(self._t1, self._t2, self._t3)
        self._alert_threshold = self._t1

        # 5초 반복 알림 타이머
        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(_ALERT_INTERVAL)
        self._alert_timer.timeout.connect(self._on_alert_tick)

        self._build()

    # ── 빌드 ────────────────────────────────────────────────────────

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)

        # ── 메인 배너 행 ─────────────────────────────────────────
        self._banner_row = QWidget()
        self._banner_row.setFixedHeight(46)
        hl = QHBoxLayout(self._banner_row)
        hl.setContentsMargins(12, 4, 8, 4)
        hl.setSpacing(8)

        self._lbl_icon = QLabel("📊")
        self._lbl_icon.setFixedWidth(22)
        self._lbl_icon.setAlignment(Qt.AlignCenter)
        self._lbl_icon.setFont(QFont("Segoe UI Emoji", 13))

        self._lbl_msg = QLabel("포지션 없음")
        self._lbl_msg.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        self._lbl_msg.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._lbl_pct = QLabel("")
        self._lbl_pct.setFont(QFont("Consolas", 12, QFont.Bold))
        self._lbl_pct.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._lbl_pct.setFixedWidth(72)

        # 사운드 선택
        self._btn_sound = QPushButton("🔔")
        self._btn_sound.setFixedSize(30, 22)
        self._btn_sound.setStyleSheet(_BTN_BASE)
        self._btn_sound.setToolTip("알람 사운드 파일 선택")
        self._btn_sound.clicked.connect(self._select_sound)

        self._btn_test_toggle = QPushButton("▶ TEST")
        self._btn_test_toggle.setFixedSize(62, 22)
        self._btn_test_toggle.setStyleSheet(_BTN_BASE)
        self._btn_test_toggle.clicked.connect(self._toggle_test)

        hl.addWidget(self._lbl_icon)
        hl.addWidget(self._lbl_msg, stretch=1)
        hl.addWidget(self._lbl_pct)
        hl.addWidget(self._btn_sound)
        hl.addWidget(self._btn_test_toggle)

        # ── 테스트 패널 (접이식) ─────────────────────────────────
        self._test_panel = QWidget()
        self._test_panel.setMaximumHeight(0)
        self._test_panel.setStyleSheet(
            "QWidget{background:#080e18;border:1px solid #1a2a3a;border-radius:4px;}")
        tl = QHBoxLayout(self._test_panel)
        tl.setContentsMargins(8, 4, 8, 4)
        tl.setSpacing(5)

        tl.addWidget(QLabel("수익률:") )
        self._test_panel.findChildren(QLabel)[-1].setStyleSheet(
            "color:#556677;font-size:10px;border:none;background:transparent;")

        for val, label, color in [
            ( 50,  " 0%",  "#445566"),
            (400,  "400%", "#c8a000"),
            (460,  "460%", "#cc6600"),
            (510,  "500%", "#cc2222"),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(44, 22)
            btn.setStyleSheet(
                f"QPushButton{{background:#0d1520;color:{color};"
                f"border:1px solid {color}55;border-radius:3px;font-size:10px;font-weight:bold;}}"
                f"QPushButton:hover{{background:{color}22;}}")
            btn.clicked.connect(lambda _, v=val: self.update_pct(v))
            tl.addWidget(btn)

        tl.addSpacing(4)

        for label, tip, fn in [
            ("📨 TG",    "TG 테스트 발송",          self._test_tg),
            ("🐺 ON",    "Wolf ON 테스트",           self._test_wolf_on),
            ("○ OFF",    "Wolf OFF 테스트",           self._test_wolf_off),
            ("⏱ 감시",  "SpecialFillWatcher 테스트", self._test_watcher),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 22)
            btn.setStyleSheet(_BTN_BASE)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            tl.addWidget(btn)

        tl.addStretch()
        btn_reset = QPushButton("↺ 리셋")
        btn_reset.setFixedSize(52, 22)
        btn_reset.setStyleSheet(_BTN_BASE)
        btn_reset.clicked.connect(self.clear)
        tl.addWidget(btn_reset)

        vl.addWidget(self._banner_row)
        vl.addWidget(self._test_panel)

        self._set_style("#0d1520", "#3a4a5a", "📊", "포지션 없음", "")

    # ── Public API ───────────────────────────────────────────────────

    def update_pct(self, pct: float) -> None:
        """수익률(%) 갱신. _refresh_pos_table 또는 _on_tick 에서 자동 호출."""
        self._pct = pct
        bg, fg, icon, msg = "#0d1520", "#3a4a5a", "📊", "수익률 정상 보유 구간"
        for min_p, max_p, bg_, fg_, icon_, msg_ in self._levels:
            if min_p <= pct <= max_p:
                bg, fg, icon, msg = bg_, fg_, icon_, msg_
                break
        sign = "+" if pct >= 0 else ""
        self._set_style(bg, fg, icon, msg, f"{sign}{pct:.0f}%")

        # 알림 타이머 관리
        cur_level = _level_tag(pct, self._t1, self._t2, self._t3)
        if pct >= self._alert_threshold:
            if not self._alert_timer.isActive():
                # 경고 구간 최초 진입 → 즉시 1회 발송 후 타이머 시작
                self._alert_count = 0
                self._fire_profit_alert(pct, cur_level)
                self._alert_timer.start()
            elif cur_level != self._prev_level:
                # 구간 상승 (400→450, 450→500) → 즉시 추가 발송
                self._fire_profit_alert(pct, cur_level)
        else:
            # 정상 구간 복귀 → 타이머 중지
            if self._alert_timer.isActive():
                self._alert_timer.stop()
                self._alert_count = 0

        self._prev_level = cur_level

    def clear(self) -> None:
        self._pct = 0.0
        self._prev_level = ""
        self._alert_count = 0
        self._alert_timer.stop()
        self._set_style("#0d1520", "#3a4a5a", "📊", "포지션 없음", "")

    def set_sound_path(self, path: str) -> None:
        self._sound_path = path

    def reload_thresholds(self) -> None:
        """저장된 임계값을 다시 읽어 구간/알림 기준 즉시 갱신."""
        _thr = load_thresholds()
        self._t1              = _thr["t1"]
        self._t2              = _thr["t2"]
        self._t3              = _thr["t3"]
        self._levels          = _build_levels(self._t1, self._t2, self._t3)
        self._alert_threshold = self._t1
        print(f"[ProfitBanner] 임계값 갱신: L1={self._t1}% L2={self._t2}% L3={self._t3}%")

    # ── 내부: 알림 ───────────────────────────────────────────────────

    def _on_alert_tick(self) -> None:
        if self._pct >= self._alert_threshold:
            self._fire_profit_alert(self._pct, _level_tag(self._pct, self._t1, self._t2, self._t3))

    def _fire_profit_alert(self, pct: float, level: str) -> None:
        self._alert_count += 1
        _play_sound(self._sound_path)

        if pct >= self._t3:
            icon = "🚨"
            msg_body = "즉시 반대 포지션 매수 권고"
        elif pct >= self._t2:
            icon = "⚠️"
            msg_body = "전략 전환 검토 구간"
        else:
            icon = "💡"
            msg_body = "반대 포지션 선매수 고려"

        _tg(
            f"{icon} <b>수익률 {level} 경고</b>  #{self._alert_count}\n"
            f"현재 수익률: <b>+{pct:.0f}%</b>\n"
            f"{msg_body}\n"
            f"5초마다 알림 전송 중"
        )

    # ── 내부: 사운드 선택 ────────────────────────────────────────────

    def _select_sound(self) -> None:
        import os
        start_dir = ""
        for d in _DEFAULT_SOUND_DIRS:
            if os.path.isdir(d):
                start_dir = d
                break
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택", start_dir,
            "사운드 파일 (*.wav *.ogg *.mp3 *.flac);;전체 파일 (*)")
        if path:
            self._sound_path = path
            self._btn_sound.setToolTip(f"선택됨: {path}")
            self._btn_sound.setText("🔔✅")
            # wolf 배너에도 동일 사운드 적용
            if self._wolf and hasattr(self._wolf, 'set_sound_path'):
                self._wolf.set_sound_path(path)
            _play_sound(path)   # 미리 듣기

    # ── 내부: 테스트 핸들러 ──────────────────────────────────────────

    def _toggle_test(self) -> None:
        self._test_open = not self._test_open
        target_h = 36 if self._test_open else 0
        self._btn_test_toggle.setText(
            "▼ TEST" if self._test_open else "▶ TEST")
        anim = QPropertyAnimation(self._test_panel, b"maximumHeight", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setStartValue(self._test_panel.maximumHeight())
        anim.setEndValue(target_h)
        anim.start()
        self._anim = anim

    def _test_tg(self) -> None:
        self._fire_profit_alert(400.0, "400%+")

    def _test_wolf_on(self) -> None:
        if self._wolf and hasattr(self._wolf, 'set_on'):
            self._wolf.set_on(target_price=3.00, strategy="[TEST] 풋 스프레드")
        else:
            print("[TEST] wolf_banner 미연결")

    def _test_wolf_off(self) -> None:
        if self._wolf and hasattr(self._wolf, 'set_off'):
            self._wolf.set_off()

    def _test_watcher(self) -> None:
        try:
            from combo_order_special_condition import SpecialFillWatcher
            w = SpecialFillWatcher.get()
            TEST_OID = 99999
            w.unwatch(TEST_OID)
            w.watch(None, oid=TEST_OID, target=3.0, action="SELL",
                    legs=[], strat="[TEST] 풋 스프레드",
                    bag_contract=None, qty=1)
            w.on_net_price_update(TEST_OID, net_price=3.05)
            print("[TEST] SpecialFillWatcher 시작 — 10초 후 TG 확인")
        except Exception as e:
            print(f"[TEST] Watcher 실패: {e}")

    # ── 내부: 스타일 ────────────────────────────────────────────────

    def _set_style(self, bg, fg, icon, msg, pct_text) -> None:
        self._banner_row.setStyleSheet(
            f"QWidget{{background:{bg};border-radius:4px;"
            f"border:1px solid {fg}44;}}")
        _ns = f"color:{fg};background:transparent;border:none;"
        self._lbl_icon.setText(icon)
        self._lbl_msg.setText(msg)
        self._lbl_msg.setStyleSheet(_ns)
        self._lbl_pct.setText(pct_text)
        self._lbl_pct.setStyleSheet(_ns)