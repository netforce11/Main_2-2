"""
trade_log/und_saver.py — 기초자산(지수) 가격 저장 공개 API  v1.5
════════════════════════════════════════════════════════════════
[v1.5] M-B 버퍼링 + 파일 분리

변경:
  · DB I/O (save_to_db, query_before, warmup_from_db)
    → und_saver_db.py 로 분리
  · push(): 저장 주기(_interval) 마다 save_to_db 호출 (변경 없음)
    단, 저장 판단은 버퍼 in-memory 기준 → 디스크는 비동기

공개 API (하위 호환 유지):
  set_interval(seconds)   — 저장 주기 설정 (5/10/30초)
  get_interval() → int
  push(price)             — 실시간 가격 저장
  get_context(exec_time, minutes) → dict | float | None
  is_running() → bool
  get_warmup_status() → dict
  warmup()                — 앱 시작 시 호출 (DB → 버퍼 워밍업)
════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

try:
    from trade_log.und_saver_db import (
        save_to_db, query_before, warmup_from_db
    )
except ImportError:
    from und_saver_db import (
        save_to_db, query_before, warmup_from_db
    )

_ET = ZoneInfo("America/New_York")

_VALID_INTERVALS = (5, 10, 30)
_interval    = 10
_buf: deque  = deque(maxlen=500)
_lock        = threading.Lock()
_last_saved  = None
_warmed_up   = False


# ── 내부 유틸 ─────────────────────────────────────────────────

def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt


# ── 워밍업 ────────────────────────────────────────────────────

def _warmup_task():
    """별도 스레드에서 실행 — DB → 버퍼 로드."""
    global _warmed_up
    try:
        warmup_from_db(_buf, _lock)
    finally:
        _warmed_up = True


def warmup() -> None:
    """앱 시작 시 호출 — 당일 DB 데이터를 버퍼에 워밍업."""
    t = threading.Thread(
        target=_warmup_task, daemon=True, name="und_warmup")
    t.start()


# ── 공개 API ──────────────────────────────────────────────────

def set_interval(seconds: int) -> None:
    """저장 주기 설정. 5 / 10 / 30 중 하나."""
    global _interval
    if seconds in _VALID_INTERVALS:
        _interval = seconds


def get_interval() -> int:
    return _interval


def push(price: float) -> None:
    """
    실시간 가격 수신.
    in-memory 버퍼에 즉시 추가, _interval 마다 DB에 비동기 저장.
    """
    global _last_saved
    now    = datetime.now(_ET)
    ts_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with _lock:
        _buf.append((now, price))
        should_save = (
            _last_saved is None or
            (now - _last_saved).total_seconds() >= _interval
        )
        if should_save:
            _last_saved = now

    if should_save:
        save_to_db(ts_str, price)   # 비동기 (ThreadPoolExecutor)


def get_context(exec_time=None, minutes: Optional[int] = None):
    """
    기초자산 가격 컨텍스트 반환.

    [단일 float 반환]
      get_context(exec_time, minutes=20) → float | None

    [딕셔너리 반환 — 하위 호환]
      get_context()
      get_context(exec_time)
      → {"und_price": float, "und_5m": float, "und_10m": float,
         "chg_5m": float, "chg_10m": float}
    """
    now = _to_aware(exec_time) if exec_time else datetime.now(_ET)

    with _lock:
        buf_snap = list(_buf)

    def _from_buf(mins: int) -> Optional[float]:
        target = now - timedelta(minutes=mins)
        for ts, px in reversed(buf_snap):
            if _to_aware(ts) <= target:
                return px
        return None

    def _lookup(mins: int) -> Optional[float]:
        return _from_buf(mins) or query_before(now, mins)

    if minutes is not None:
        return _lookup(minutes)

    und_price = buf_snap[-1][1] if buf_snap else None
    und_5m    = _lookup(5)
    und_10m   = _lookup(10)
    chg_5m    = round(und_price - und_5m,  2) if und_price and und_5m  else None
    chg_10m   = round(und_price - und_10m, 2) if und_price and und_10m else None

    return {
        "und_price": und_price,
        "und_5m"   : und_5m,
        "und_10m"  : und_10m,
        "chg_5m"   : chg_5m,
        "chg_10m"  : chg_10m,
    }


def is_running() -> bool:
    with _lock:
        return len(_buf) > 0


def get_warmup_status() -> dict:
    """워밍업 및 버퍼 현황 반환 (디버깅/UI 표시용)."""
    with _lock:
        buf_len = len(_buf)
        oldest  = _buf[0][0]  if buf_len > 0 else None
        newest  = _buf[-1][0] if buf_len > 0 else None
    covered = (
        round((newest - oldest).total_seconds() / 60, 1)
        if oldest and newest else 0)
    return {
        "warmed_up"  : _warmed_up,
        "buf_len"    : buf_len,
        "covered_min": covered,
        "oldest"     : oldest,
        "newest"     : newest,
    }
