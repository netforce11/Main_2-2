"""
tg_config_patch.py
====================
기존 tg_config.py 에 적용할 패치 내용.

[적용 방법]
1. _DEFAULT 딕셔너리에 "watch_levels" 키 추가 (아래 참고)
2. TgConfig 클래스에 watch_level() / set_watch_level() 메서드 추가

[버그 수정]
- [FIX-2] watch_level() 반환 시 deep copy + defaults merge 순서 보장
          → stored 값이 없는 키는 반드시 defaults 로 채워짐
"""

# ─────────────────────────────────────────────────────────
# Step 1. _DEFAULT 에 추가
# ─────────────────────────────────────────────────────────
#
# 기존 _DEFAULT = { "token": ..., "chat_id": ..., ... }
# 아래 항목을 추가:
#
# _DEFAULT = {
#     ...
#     "watch_levels": {
#         "1": {"enabled": True,  "min_pt": 3.0,  "silent": True},
#         "2": {"enabled": True,  "min_pt": 8.0,  "silent": False},
#         "3": {"enabled": True,  "min_pt": 15.0, "silent": False},
#     },
# }

_WATCH_LEVELS_DEFAULT = {
    "1": {"enabled": True,  "min_pt": 3.0,  "silent": True},
    "2": {"enabled": True,  "min_pt": 8.0,  "silent": False},
    "3": {"enabled": True,  "min_pt": 15.0, "silent": False},
}


# ─────────────────────────────────────────────────────────
# Step 2. TgConfig 클래스에 아래 메서드 2개 복붙
# ─────────────────────────────────────────────────────────

def watch_level(self, level: int) -> dict:
    """
    level: 1 | 2 | 3
    반환: {"enabled": bool, "min_pt": float, "silent": bool}

    [FIX-2] defaults 먼저 복사 후 stored 로 덮어쓰기
            → JSON 에 일부 키만 저장돼 있어도 나머지는 기본값 유지
    """
    _defaults = {
        1: {"enabled": True,  "min_pt": 3.0,  "silent": True},
        2: {"enabled": True,  "min_pt": 8.0,  "silent": False},
        3: {"enabled": True,  "min_pt": 15.0, "silent": False},
    }
    base   = _defaults.get(level, {"enabled": True, "min_pt": 0.0, "silent": False}).copy()
    stored = self._data.get("watch_levels", {}).get(str(level), {})
    base.update(stored)   # stored 값으로 덮어쓰기 (없는 키는 defaults 유지)
    return base


def set_watch_level(self, level: int, enabled: bool, min_pt: float, silent: bool):
    """UI 저장 시 호출."""
    self._data.setdefault("watch_levels", {})[str(level)] = {
        "enabled": enabled,
        "min_pt":  round(float(min_pt), 2),
        "silent":  silent,
    }
