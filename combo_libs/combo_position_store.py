"""
combo_position_store.py — 합성 잔고 영속화 (저장 / 불러오기)
──────────────────────────────────────────────────────────────
저장 경로: data/synthetic_positions.json

저장 시점:
  - 체결 완료(_on_order_status "Filled")
  - 포지션 청산 / 취소로 제거

불러오기 시점:
  - 탭 초기화(_build) 완료 후 QTimer.singleShot(800, ...)

저장 형식:
  [
    {
      "strategy": "아이언 콘도르",
      "qty": 1,
      "entry": 2.35,
      "current": 2.35,
      "side": "BUY",
      "oid": 12345,
      "legs": [...],
      "status": "체결완료",
      "saved_at": "2025-05-02T14:30:00"
    },
    ...
  ]

설계 원칙:
  - 파일 I/O 실패는 조용히 무시 (거래 로직에 영향 없음)
  - "체결완료" 상태만 저장 (미체결은 재시작 후 의미 없음)
  - 날짜가 7일 이상 지난 항목은 자동 purge
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path

_STORE_FILE = Path("data/synthetic_positions.json")
_MAX_AGE_DAYS = 7


# ──────────────────────────────────────────────────────────────
# 저장
# ──────────────────────────────────────────────────────────────

def save_positions(positions: list) -> None:
    """
    positions 리스트 중 status == '체결완료' 항목만 JSON으로 저장.
    기존 파일을 덮어씁니다.
    """
    try:
        to_save = []
        for pos in positions:
            if pos.get("status") != "체결완료":
                continue
            entry = dict(pos)
            # legs 안의 객체는 직렬화 가능한 기본 타입만 있어야 함
            # (combo_order_bag._do_send_body에서 dict로 구성되므로 OK)
            entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
            to_save.append(entry)

        _STORE_FILE.parent.mkdir(exist_ok=True)
        _STORE_FILE.write_text(
            json.dumps(to_save, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass   # 저장 실패는 무시


def save_one_position(pos: dict) -> None:
    """
    단일 포지션 추가 저장.
    기존 저장 목록을 불러와 oid 중복 확인 후 append.
    """
    if pos.get("status") != "체결완료":
        return
    try:
        existing = load_positions()
        # oid 중복이면 갱신, 없으면 추가
        oid = pos.get("oid")
        for i, p in enumerate(existing):
            if oid and p.get("oid") == oid:
                existing[i] = dict(pos)
                existing[i].setdefault(
                    "saved_at", datetime.now().isoformat(timespec="seconds"))
                save_positions(existing)
                return
        entry = dict(pos)
        entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
        existing.append(entry)
        save_positions(existing)
    except Exception:
        pass


def remove_position(oid: int) -> None:
    """oid에 해당하는 포지션을 파일에서 제거."""
    try:
        existing = load_positions()
        updated  = [p for p in existing if p.get("oid") != oid]
        if len(updated) != len(existing):
            save_positions(updated)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# 불러오기
# ──────────────────────────────────────────────────────────────

def load_positions() -> list:
    """
    저장된 포지션 목록을 반환.
    파일 없거나 파싱 실패 시 빈 리스트 반환.
    7일 이상 지난 항목은 자동 제거.
    """
    try:
        if not _STORE_FILE.exists():
            return []
        data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []

        cutoff = datetime.now() - timedelta(days=_MAX_AGE_DAYS)
        filtered = []
        for p in data:
            saved_at = p.get("saved_at", "")
            try:
                dt = datetime.fromisoformat(saved_at)
                if dt < cutoff:
                    continue  # 오래된 항목 제거
            except (ValueError, TypeError):
                pass  # saved_at 없거나 파싱 불가 → 유지
            filtered.append(p)

        # purge 발생 시 파일 갱신
        if len(filtered) != len(data):
            save_positions(filtered)

        return filtered
    except Exception:
        return []
