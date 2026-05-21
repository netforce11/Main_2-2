"""
tg_client_patch.py
====================
기존 TelegramClient 클래스에 _send_raw_silent() 메서드 추가.
_send_raw() 바로 아래에 복붙하세요.
"""

import json
import urllib.request


def _send_raw_silent(self, text: str) -> bool:
    """
    disable_notification=True 로 무음 전송 (LV1 약알람용).
    _send_raw() 와 동일하되 알림음/진동 없음.
    """
    if not self._cfg.token or not self._cfg.chat_id:
        return False
    if len(text) > 4096:
        text = text[:4090] + "\n..."
    try:
        url     = f"https://api.telegram.org/bot{self._cfg.token}/sendMessage"
        payload = json.dumps({
            "chat_id":              self._cfg.chat_id,
            "text":                 text,
            "parse_mode":           "HTML",
            "disable_notification": True,    # ← LV1 무음 핵심
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        return True
    except Exception as e:
        print(f"[TG] _send_raw_silent error: {e}")
        return False
