"""
watch_dog/alert_notifier.py
알람 통보 담당 — 소리 + 텔레그램.
교체가 필요할 때 이 파일만 수정.
"""

import platform

from telegram_bot.tg_client import TelegramClient


class AlertNotifier:

    def notify(self, level: int, condition: str, detail: str):
        """
        level     : 1 / 2
        condition : '조건A' | '조건B' | '조건C'
        detail    : 'SPX -15pt' 등 상세 내용
        """
        # ── 소리
        self._beep(level)

        # ── 텔레그램
        msg = f"[LV{level}] [{condition}] {detail}"
        TelegramClient.get().send("watch_alert", msg)

    # ──────────────────────────────────────────
    @staticmethod
    def _beep(level: int):
        if platform.system() != "Windows":
            return
        try:
            import winsound
            freq, dur = (1000, 200) if level == 1 else (1500, 400)
            winsound.Beep(freq, dur)
        except Exception:
            pass
