"""
telegram_bot/tg_command_router.py
수신된 텔레그램 명령을 각 탭의 핸들러로 라우팅.

[FIX-R1] dispatch_info_select: item_no==7 에서 return False → 직접 처리
  기존: return False → tg_client 가 handled=False 로 받아 fall-through
        → "주인님으로부터 수신 완료" 만 전송, 스프레드 버튼 미전송.
  수정: item_no==7 도 여기서 직접 인라인 버튼 전송 후 return True.
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

    # ──────────────────────────────────────────
    # "정보" 메뉴 처리
    # ──────────────────────────────────────────
    def register_info_handler(self, fn):
        """
        fn(item_no: int, chat_id: str) → None
        main.py 에서 1회 등록.
        """
        self._info_handler = fn

    def dispatch_info(self, chat_id: str):
        """'정보' 수신 시 메뉴 전송 + pending_menu 등록."""
        from .tg_client import TelegramClient
        menu = (
            "📋 정보 메뉴\n"
            "번호를 입력하세요:\n\n"
            "1  1분 차트\n"
            "2  옵션 체인 ATM\n"
            "3  옵션 체인 OTM\n"
            "4  잔고\n"
            "5  현재 선물 지수 (/ES)\n"
            "6  실시간 현물 지수 (SPX)\n"
            "7  스프레드 조회"
        )
        client = TelegramClient.get()
        client._send_raw(menu)
        client._pending_menu[str(chat_id)] = "info_menu"

    def dispatch_info_select(self, text: str, chat_id: str) -> bool:
        """
        info_menu 대기 상태에서 번호 처리.
        처리 성공 True, 번호 아닌 입력 False.
        """
        from .tg_client import TelegramClient
        client = TelegramClient.get()

        if not text.isdigit():
            return False

        item_no = int(text)
        if item_no < 1 or item_no > 7:
            client._send_raw("⚠️ 1~7 사이 번호를 입력해주세요.")
            return True

        # [FIX-R1] 7번: 스프레드 인라인 버튼 — 여기서 직접 처리 후 True 반환
        # 기존: return False → tg_client 에서 handled=False → fall-through
        #       → "주인님으로부터 수신 완료" 만 전송되고 버튼 미전송
        if item_no == 7:
            try:
                from spread_tele.spread_config import CB_CALL, CB_PUT, CB_CANCEL
                ok = client._send_inline_keyboard(
                    "스프레드 종류를 선택하세요:",
                    [
                        [
                            {"text": "📈 콜 스프레드", "callback_data": CB_CALL},
                            {"text": "📉 풋 스프레드", "callback_data": CB_PUT},
                        ],
                        [{"text": "❌ 취소", "callback_data": CB_CANCEL}],
                    ]
                )
                if not ok:
                    client._send_raw("⚠️ 스프레드 버튼 전송 실패")
            except Exception as e:
                client._send_raw(f"⚠️ 스프레드 모듈 오류: {e}")
            return True  # ← 핵심 수정: False → True

        # 1~6번: info_handler 로 처리
        handler = getattr(self, '_info_handler', None)
        if handler:
            import threading
            threading.Thread(
                target=handler, args=(item_no, str(chat_id)), daemon=True
            ).start()
        else:
            client._send_raw("⚠️ 정보 핸들러가 등록되지 않았습니다.")
        return True