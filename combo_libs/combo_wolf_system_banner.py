"""
combo_wolf_system_banner.py — Wolf System 상태 배너 + 5초 사운드/TG  v2.0
──────────────────────────────────────────────────────────────────────
ON  상태: 5초마다 사운드 + 텔레그램 반복 전송
OFF 상태: 타이머 중지, 알림 없음

사운드 파일 선택:
  set_on() 호출 전에 sound_path 를 지정하거나,
  테스트 버튼 [🔔 사운드 선택] 으로 다이얼로그에서 선택.
  선택된 경로는 프로그램 종료까지 유지.

사용법:
  self.wolf_banner = WolfSystemBanner()
  layout.addWidget(self.wolf_banner)

  self.wolf_banner.set_on(target_price=3.0, strategy="풋 스프레드")
  self.wolf_banner.set_off()
──────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import subprocess
import threading
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                              QLabel, QPushButton, QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

# Linux Mint 기본 사운드 경로 후보
_DEFAULT_SOUND_DIRS = [
    "/usr/share/sounds/freedesktop/stereo",
    "/usr/share/sounds/ubuntu/stereo",
    "/usr/share/sounds/LinuxMint",
    "/usr/share/sounds",
]
_DEFAULT_SOUND_FILE = ""   # 선택 전 빈값

_ON_BG  = "#001a00";  _ON_FG  = "#00ff88";  _ON_BD  = "#00cc66"
_OFF_BG = "#001a00";  _OFF_FG = "#444444";  _OFF_BD = "#222222"

def _btn_base_ss():
    try:
        import core as _c
        t = _c.THEME_PALETTES.get(_c.CURRENT_THEME, _c.THEME_PALETTES["light"])
        return (
            f"QPushButton{{background:{t['btn_bg']};color:{t['group_title']};"
            f"border:1px solid {t['btn_border']};"
            "border-radius:4px;padding:2px 7px;font-size:10px;}}"
            f"QPushButton:hover{{background:{t['btn_hover']};color:{t['btn_hover_bdr']};}}"
        )
    except Exception:
        return (
            "QPushButton{background:#111827;color:#778899;border:1px solid #334455;"
            "border-radius:4px;padding:2px 7px;font-size:10px;}"
            "QPushButton:hover{background:#1e2d3d;color:#aabbcc;}"
        )

_BTN_BASE = _btn_base_ss()


def _play_sound(path: str) -> None:
    """별도 스레드에서 사운드 재생 (블로킹 방지)."""
    if not path:
        return
    def _run():
        try:
            # paplay (PulseAudio) → aplay (ALSA) → ffplay 순으로 시도
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
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[WolfBanner] TG 실패: {e}")


class WolfSystemBanner(QWidget):
    """Wolf System ON/OFF 배너 + 5초 사운드/TG 반복."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_on       = False
        self._blink_on    = True
        self._target      = 0.0
        self._strategy    = ""
        self._sound_path  = _DEFAULT_SOUND_FILE
        self._alert_count = 0          # ON 이후 알림 횟수

        # LED 깜빡임 타이머 (800ms)
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(800)
        self._blink_timer.timeout.connect(self._blink)

        # 사운드 + TG 반복 타이머 (5초)
        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(5_000)
        self._alert_timer.timeout.connect(self._on_alert_tick)

        self._build()

    # ── 빌드 ────────────────────────────────────────────────────────

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)

        # ── 메인 배너 행 ─────────────────────────────────────────
        self._row = QWidget()
        self._row.setFixedHeight(46)
        hl = QHBoxLayout(self._row)
        hl.setContentsMargins(12, 4, 8, 4)
        hl.setSpacing(8)

        self._led = QLabel("●")
        self._led.setFixedWidth(18)
        self._led.setAlignment(Qt.AlignCenter)
        self._led.setFont(QFont("Segoe UI", 13, QFont.Bold))

        self._lbl_sys = QLabel("○  OFF WOLF SYSTEM")
        self._lbl_sys.setFont(QFont("Malgun Gothic", 11, QFont.Bold))
        self._lbl_sys.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._lbl_detail = QLabel("")
        self._lbl_detail.setFont(QFont("Consolas", 10))
        self._lbl_detail.setAlignment(Qt.AlignVCenter | Qt.AlignRight)

        # 사운드 선택 버튼
        self._btn_sound = QPushButton("🔔 사운드")
        self._btn_sound.setFixedSize(72, 22)
        self._btn_sound.setStyleSheet(_btn_base_ss())
        self._btn_sound.setToolTip("알람 사운드 파일 선택")
        self._btn_sound.clicked.connect(self._select_sound)

        hl.addWidget(self._led)
        hl.addWidget(self._lbl_sys, stretch=1)
        hl.addWidget(self._lbl_detail)
        hl.addWidget(self._btn_sound)

        vl.addWidget(self._row)
        self._apply_off()

    # ── Public API ───────────────────────────────────────────────────

    def set_on(self, target_price: float = 0.0, strategy: str = "") -> None:
        """선주문 접수 시 호출 → ON + 5초 알림 시작."""
        self._is_on       = True
        self._target      = target_price
        self._strategy    = strategy
        self._alert_count = 0
        parts = []
        if target_price:
            parts.append(f"목표 ${target_price:.2f}")
        if strategy:
            parts.append(strategy)
        self._lbl_detail.setText("  ".join(parts))
        self._apply_on()
        self._blink_timer.start()
        self._alert_timer.start()
        # 즉시 1회 알림
        self._fire_alert()

    def set_off(self) -> None:
        """체결/취소 시 호출 → OFF + 타이머 중지."""
        self._is_on       = False
        self._blink_on    = True
        self._alert_count = 0
        self._blink_timer.stop()
        self._alert_timer.stop()
        self._lbl_detail.setText("")
        self._apply_off()

    @property
    def is_on(self) -> bool:
        return self._is_on

    def set_sound_path(self, path: str) -> None:
        self._sound_path = path

    # ── 내부: 알림 ───────────────────────────────────────────────────

    def _on_alert_tick(self) -> None:
        if self._is_on:
            self._fire_alert()

    def _fire_alert(self) -> None:
        self._alert_count += 1
        _play_sound(self._sound_path)
        _tg(
            f"🐺 <b>ON WOLF SYSTEM</b>  #{self._alert_count}\n"
            f"전략: {self._strategy}\n"
            f"목표가: ${self._target:.2f}\n"
            f"선주문 감시 중 — 5초마다 알림"
        )

    # ── 내부: 사운드 선택 ────────────────────────────────────────────

    def _select_sound(self) -> None:
        start_dir = ""
        for d in _DEFAULT_SOUND_DIRS:
            import os
            if os.path.isdir(d):
                start_dir = d
                break
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택", start_dir,
            "사운드 파일 (*.wav *.ogg *.mp3 *.flac);;전체 파일 (*)")
        if path:
            self._sound_path = path
            self._btn_sound.setToolTip(f"선택됨: {path}")
            self._btn_sound.setText("🔔 ✅")
            # 미리 듣기
            _play_sound(path)

    # ── 내부: 깜빡임/스타일 ──────────────────────────────────────────

    def _blink(self) -> None:
        self._blink_on = not self._blink_on
        c = _ON_FG if self._blink_on else "#003a1a"
        self._led.setStyleSheet(
            f"color:{c};background:transparent;border:none;")

    def _apply_on(self) -> None:
        self._row.setStyleSheet(
            f"QWidget{{background:{_ON_BG};border-radius:4px;"
            f"border:1px solid {_ON_BD};}}")
        _ns = "background:transparent;border:none;"
        self._led.setStyleSheet(f"color:{_ON_FG};{_ns}")
        self._lbl_sys.setText("🐺  ON WOLF SYSTEM")
        self._lbl_sys.setStyleSheet(f"color:{_ON_FG};{_ns}")
        self._lbl_detail.setStyleSheet(f"color:#00bb66;{_ns}")

    def _apply_off(self) -> None:
        try:
            import core as _c
            t = _c.THEME_PALETTES.get(_c.CURRENT_THEME, _c.THEME_PALETTES["light"])
            off_bg = t['group_bg']
            off_bd = t['group_border']
        except Exception:
            off_bg = "#0d0d0d"; off_bd = "#222222"
        self._row.setStyleSheet(
            f"QWidget{{background:{off_bg};border-radius:4px;"
            f"border:1px solid {off_bd};}}")
        _ns = "background:transparent;border:none;"
        self._led.setStyleSheet(f"color:{_OFF_FG};{_ns}")
        self._lbl_sys.setText("○  OFF WOLF SYSTEM")
        self._lbl_sys.setStyleSheet(f"color:{_OFF_FG};{_ns}")
        self._lbl_detail.setStyleSheet(f"color:{_OFF_FG};{_ns}")