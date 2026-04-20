"""
telegram_bot/tg_client.py
봇 싱글톤 — 송신, getUpdates polling, chat_id 검증.
UI 콜백(on_message_cb)을 통해 tg_config_widget 의 채팅창에 메시지를 표시.
"""

import threading
import time
import urllib.request
import urllib.parse
import urllib.error
import json
from typing import Callable, List, Optional

from .tg_config import TgConfig
from .tg_command_router import TgCommandRouter


class TelegramClient:
    """싱글톤."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cfg = TgConfig()
        self._router = TgCommandRouter()
        self._polling_thread: Optional[threading.Thread] = None
        self._polling_active = False
        self._last_update_id = 0

        # UI 채팅창에 메시지를 전달하는 콜백 목록
        # fn(direction, tag, text, raw_cmd)
        #   direction : 'incoming' | 'outgoing'
        #   tag       : 'ORDER' | 'ALERT' | 'CONFIRM' | 'INFO'
        self._chat_callbacks: List[Callable] = []

    # ──────────────────────────────────────────
    # 외부 API (각 탭에서 호출)
    # ──────────────────────────────────────────
    @classmethod
    def get(cls) -> "TelegramClient":
        return cls()

    def send(self, tag: str, message: str) -> bool:
        """
        tag : 'watch_alert' | 'sniper_alert' | 'order_confirm'
        토큰·Chat ID 설정 + 개별 tag enabled 가 True 일 때 전송.
        전역 enabled 는 채팅창 직접 입력용 — 알람 자동 전송은 별도 tag 설정으로 제어.
        """
        if not self._cfg.token or not self._cfg.chat_id:
            return False
        if not self._cfg.notify_enabled(tag):
            return False
        ok = self._send_raw(message)
        if ok:
            self._fire_callback("outgoing", "CONFIRM", "전송 완료.", message)
        return ok

    def start_polling(self):
        """앱 시작 시 1회 호출. 백그라운드 스레드로 수신 루프 실행."""
        if self._polling_active:
            return
        self._polling_active = True
        self._polling_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="TgPolling"
        )
        self._polling_thread.start()

    def stop_polling(self):
        self._polling_active = False

    def register_chat_callback(self, fn: Callable):
        """채팅창 UI가 자신을 등록. fn(direction, tag, text, raw)"""
        if fn not in self._chat_callbacks:
            self._chat_callbacks.append(fn)

    def unregister_chat_callback(self, fn: Callable):
        self._chat_callbacks = [c for c in self._chat_callbacks if c != fn]

    # ──────────────────────────────────────────
    # Polling loop
    # ──────────────────────────────────────────
    def _poll_loop(self):
        while self._polling_active:
            try:
                if self._cfg.enabled and self._cfg.token:
                    updates = self._get_updates()
                    for upd in updates:
                        self._handle_update(upd)
            except Exception:
                pass
            time.sleep(2)

    def _get_updates(self) -> list:
        url = (
            f"https://api.telegram.org/bot{self._cfg.token}/getUpdates"
            f"?offset={self._last_update_id + 1}&timeout=1"
        )
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
            if data.get("ok"):
                return data.get("result", [])
        except Exception:
            pass
        return []

    def _handle_update(self, upd: dict):
        self._last_update_id = upd.get("update_id", self._last_update_id)
        msg = upd.get("message") or upd.get("edited_message")
        if not msg:
            return

        from_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text:
            return

        # chat_id 화이트리스트 검증
        if self._cfg.chat_id and from_id != str(self._cfg.chat_id):
            return

        # 태그 분류
        tag = self._classify_tag(text)

        # UI 채팅창에 수신 메시지 표시
        self._fire_callback("incoming", tag, text, text)

        # 명령 처리
        if text.startswith("/"):
            # 주문 명령은 order_enabled 이중 검증
            if self._is_order_cmd(text) and not self._cfg.order_enabled:
                reply = "[거부] 주문 수신이 비활성화 상태입니다."
                self._send_raw(reply)
                self._fire_callback("outgoing", "INFO", reply, text)
                return

            reply = self._router.dispatch(text, from_id)
            confirm = f"주인님으로부터 수신 완료.\n원문: {text}"
            self._send_raw(confirm)
            self._fire_callback("outgoing", "CONFIRM", "주인님으로부터 수신 완료.", text)

            if reply:
                self._send_raw(reply)
                self._fire_callback("outgoing", "INFO", reply, "")
        else:
            # 일반 텍스트 수신
            confirm = f"주인님으로부터 수신 완료.\n원문: {text}"
            self._send_raw(confirm)
            self._fire_callback("outgoing", "CONFIRM", "주인님으로부터 수신 완료.", text)

    # ──────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────
    def _send_raw(self, text: str) -> bool:
        if not self._cfg.token or not self._cfg.chat_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{self._cfg.token}/sendMessage"
            payload = json.dumps({
                "chat_id": self._cfg.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
            return True
        except Exception:
            return False

    def test_connection(self) -> str:
        """연결 테스트. UI에서 호출."""
        if not self._cfg.token:
            return "토큰이 없습니다."
        try:
            url = f"https://api.telegram.org/bot{self._cfg.token}/getMe"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = json.loads(r.read())
            if data.get("ok"):
                name = data["result"].get("username", "")
                return f"연결 성공: @{name}"
            return "응답 오류"
        except Exception as e:
            return f"연결 실패: {e}"

    @staticmethod
    def _classify_tag(text: str) -> str:
        t = text.lower()
        if any(t.startswith(c) for c in ["/buy", "/sell"]):
            return "ORDER"
        if t.startswith("/"):
            return "ALERT"
        return "INFO"

    @staticmethod
    def _is_order_cmd(text: str) -> bool:
        t = text.lower()
        return t.startswith("/buy") or t.startswith("/sell")

    def _fire_callback(self, direction: str, tag: str, text: str, raw: str):
        for fn in self._chat_callbacks:
            try:
                fn(direction, tag, text, raw)
            except Exception:
                pass