"""
telegram_bot/tg_command_router.py
수신된 텔레그램 명령을 각 탭의 핸들러로 라우팅.
"""

from typing import Callable, Dict, Optional


class TgCommandRouter:
    """싱글톤. 각 탭이 자신의 명령 핸들러를 등록."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._handlers: Dict[str, Callable[[str, str], Optional[str]]] = {}
        return cls._instance

    def register(self, command: str, handler: Callable[[str, str], Optional[str]]):
        """
        command : '/buy', '/sell', '/watch', '/status' 등
        handler : fn(full_text: str, from_chat_id: str) -> Optional[str]
                  반환값이 있으면 해당 문자열을 봇이 답장으로 전송.
        """
        self._handlers[command.lower()] = handler

    def unregister(self, command: str):
        self._handlers.pop(command.lower(), None)

    def dispatch(self, text: str, from_chat_id: str) -> Optional[str]:
        """
        text : '/buy C 5000 1' 형태
        chat_id 검증은 TelegramClient 에서 선행.
        매칭 핸들러 없으면 None 반환.
        """
        parts = text.strip().split()
        if not parts:
            return None
        cmd = parts[0].lower()
        handler = self._handlers.get(cmd)
        if handler:
            try:
                return handler(text, from_chat_id)
            except Exception as e:
                return f"[오류] 명령 처리 실패: {e}"
        return f"[알 수 없는 명령] {cmd}"

    def registered_commands(self):
        return list(self._handlers.keys())
