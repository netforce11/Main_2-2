"""
position_close_config.py — 포지션 청산 설정 저장소 v3.0
════════════════════════════════════════════════════════════════
슬롯 3개 독립 설정 (각 슬롯):
  close_from_kst       : 감시 시작 시각 (KST "HH:MM")
  close_to_kst         : 감시 종료 시각 (KST "HH:MM")
  close_premium_price  : 선매도 목표 프리미엄 ($)
  close_max_corrections: 순간 정정 최대 횟수 (기본 3)
  oid                  : 예약된 포지션 OID (None = 슬롯 비어있음)
  strategy             : 표시용 전략명
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    from core import SAVE_DIR
except ImportError:
    SAVE_DIR = Path(".")

_CONFIG_FILE = SAVE_DIR / "position_close_config.json"
_N_SLOTS = 3

_SLOT_DEFAULTS = {
    "close_from_kst":        "23:00",
    "close_to_kst":          "01:30",
    "close_premium_price":   1.00,
    "close_max_corrections": 3,
    "oid":                   None,
    "strategy":              "",
}


class PositionCloseConfig:
    _instance: "PositionCloseConfig | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._slots: list[dict] = []
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        import copy
        self._slots = [copy.deepcopy(_SLOT_DEFAULTS) for _ in range(_N_SLOTS)]
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for i in range(_N_SLOTS):
                    if i < len(saved.get("slots", [])):
                        self._slots[i].update(saved["slots"][i])
            except Exception as e:
                print(f"[PosCfg] 로드 실패: {e}")

    def save(self) -> None:
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"slots": self._slots}, f,
                          ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PosCfg] 저장 실패: {e}")

    def get_slot(self, idx: int) -> dict:
        if 0 <= idx < _N_SLOTS:
            return self._slots[idx]
        raise IndexError(f"슬롯 인덱스 범위 초과: {idx}")

    def set_slot(self, idx: int, key: str, value) -> None:
        if 0 <= idx < _N_SLOTS:
            self._slots[idx][key] = value

    def register_position(self, idx: int, pos: dict) -> None:
        slot = self.get_slot(idx)
        slot["oid"]      = pos.get("oid")
        slot["strategy"] = pos.get("strategy", "")
        self.save()

    def clear_slot(self, idx: int) -> None:
        slot = self.get_slot(idx)
        slot["oid"]      = None
        slot["strategy"] = ""
        self.save()

    def is_slot_active(self, idx: int) -> bool:
        return self.get_slot(idx).get("oid") is not None

    @property
    def n_slots(self) -> int:
        return _N_SLOTS


pos_close_cfg = PositionCloseConfig()
