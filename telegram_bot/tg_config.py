"""
telegram_bot/tg_config.py
텔레그램 봇 설정값을 JSON 파일로 영구 저장/로드.
"""

import json
import os
from typing import Dict, Any

CONFIG_PATH = r"C:\data\Greeks_history\tg_config.json"

_DEFAULT: Dict[str, Any] = {
    "token": "8701369714:AAEbEZ070pqTinq8hoJFnqVq5_XTD64-ptQ",
    "chat_id": "8682300594",          # 주인님 chat_id (화이트리스트)
    "enabled": False,
    "notify": {
        "watch_alert":   True,   # 감시패널 알람 전송
        "sniper_alert":  True,   # 스나이퍼 알람 전송
        "order_confirm": True,   # 주문 체결 알람 전송
    },
    "command": {
        "order_enabled": False,  # 텔레그램 → 주문 수신 허용 (이중 잠금)
    },
}


class TgConfig:
    """싱글톤. 설정값 로드/저장."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: Dict[str, Any] = {}
            cls._instance._load()
        return cls._instance

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────
    @property
    def token(self) -> str:
        return self._data.get("token", "")

    @token.setter
    def token(self, v: str):
        self._data["token"] = v

    @property
    def chat_id(self) -> str:
        return self._data.get("chat_id", "")

    @chat_id.setter
    def chat_id(self, v: str):
        self._data["chat_id"] = v

    @property
    def enabled(self) -> bool:
        return self._data.get("enabled", False)

    @enabled.setter
    def enabled(self, v: bool):
        self._data["enabled"] = v

    def notify_enabled(self, tag: str) -> bool:
        """tag: 'watch_alert' | 'sniper_alert' | 'order_confirm'"""
        return self._data.get("notify", {}).get(tag, True)

    def set_notify(self, tag: str, v: bool):
        self._data.setdefault("notify", {})[tag] = v

    @property
    def order_enabled(self) -> bool:
        return self._data.get("command", {}).get("order_enabled", False)

    @order_enabled.setter
    def order_enabled(self, v: bool):
        self._data.setdefault("command", {})["order_enabled"] = v

    def save(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ──────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────
    def _load(self):
        import copy
        self._data = copy.deepcopy(_DEFAULT)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._deep_merge(self._data, saved)
            except Exception:
                pass  # 파일 손상 시 기본값 사용

    @staticmethod
    def _deep_merge(base: dict, override: dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                TgConfig._deep_merge(base[k], v)
            else:
                base[k] = v
