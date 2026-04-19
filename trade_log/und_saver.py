"""
trade_log/und_saver.py — 기초자산(지수) 가격 DB 저장  v1.1
════════════════════════════════════════════════════════════
  - 5 / 10 / 30초 저장 주기 선택 가능 (기본값: 10초)
  - DB: C:\data\Greeks_history\und_price\und_YYYYMMDD.db
  - 버퍼(deque) + DB 이중 조회 → 앱 재시작 후에도 정확
  - push(price)        : 가격 수신 시 호출
  - get_context(now)   : 체결 시점 기준 5분/20분 전 값 반환
  - set_interval(sec)  : 저장 주기 변경 (실시간 반영)

v1.1 수정사항:
  [1] trade_log/__init__.py — price_buffer → und_saver 교체
  [2] Python 3.9 호환: datetime | None → Optional[datetime]
  [3] exec_time naive/aware 혼용 TypeError 방지: _to_aware() 변환
  [4] DB 커넥션 누수 방지: with 문 사용 + ThreadPoolExecutor 재사용
════════════════════════════════════════════════════════════
"""

import sqlite3
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
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

_ET       = ZoneInfo("America/New_York")
_DATA_DIR = Path(r"C:\data\Greeks_history\und_price")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 저장 주기 (초) ─────────────────────────────────────────
_VALID_INTERVALS = (5, 10, 30)
_interval: int   = 10

# ── 인메모리 버퍼 ─────────────────────────────────────────
_buf: deque = deque(maxlen=500)
_lock = threading.Lock()

# ── 마지막 저장 시각 ───────────────────────────────────────
_last_saved: Optional[datetime] = None   # [수정2] Optional[datetime]

# ── DB IO 전용 스레드풀 (max_workers=1 → 순차 실행 + 스레드 재사용)
_db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="und_db")  # [수정4]


# ══════════════════════════════════════════════════════════
# 내부 유틸
# ══════════════════════════════════════════════════════════

def _db_path(date_str: str) -> Path:
    return _DATA_DIR / f"und_{date_str}.db"


def _ensure_table(conn: sqlite3.Connection) -> None:
    """테이블 및 인덱스 보장."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS und_price (
            ts    TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON und_price(ts)")
    conn.commit()


def _save_to_db(ts_str: str, price: float) -> None:
    """날짜별 DB 저장. with 문으로 커넥션 자동 close."""  # [수정4]
    date_str = ts_str[:10]
    path = _db_path(date_str)
    try:
        with sqlite3.connect(path, check_same_thread=False) as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO und_price(ts, price) VALUES(?, ?)",
                (ts_str, price)
            )
    except Exception as e:
        print(f"[und_saver] DB 저장 오류: {e}")


def _to_aware(dt: datetime) -> datetime:
    """naive datetime → ET aware 변환. 이미 aware면 그대로."""  # [수정3]
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt


def _query_before(target: datetime, minutes: int) -> Optional[float]:
    """target 기준 minutes분 전의 가장 가까운 직전 DB 저장값."""
    t_ref    = _to_aware(target) - timedelta(minutes=minutes)
    date_str = t_ref.strftime("%Y-%m-%d")
    ts_ref   = t_ref.strftime("%Y-%m-%d %H:%M:%S")

    path = _db_path(date_str)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path, check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT price FROM und_price "
                "WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                (ts_ref,)
            ).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════

def set_interval(seconds: int) -> None:
    """저장 주기 변경. 유효값: 5, 10, 30."""
    global _interval
    if seconds in _VALID_INTERVALS:
        _interval = seconds
        print(f"[und_saver] 저장 주기: {_interval}초")


def get_interval() -> int:
    return _interval


def push(price: float) -> None:
    """가격 수신 시 호출. 버퍼 저장 + 주기마다 DB 저장."""
    global _last_saved
    now    = datetime.now(_ET)          # 항상 aware
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
        _db_executor.submit(_save_to_db, ts_str, price)   # [수정4]


def get_context(exec_time: Optional[datetime] = None) -> dict:   # [수정2]
    """
    체결 시각 기준 5분 / 20분 전 기초자산 가격 반환.
    exec_time이 naive이면 ET로 자동 변환.           [수정3]
    """
    now = _to_aware(exec_time) if exec_time else datetime.now(_ET)

    with _lock:
        buf_snap = list(_buf)

    und_now = buf_snap[-1][1] if buf_snap else None

    def _from_buf(minutes: int) -> Optional[float]:
        target = now - timedelta(minutes=minutes)
        for ts, px in reversed(buf_snap):
            if ts <= target:   # buf ts는 항상 aware — 비교 안전
                return px
        return None

    und_5m  = _from_buf(5)  or _query_before(now, 5)
    und_20m = _from_buf(20) or _query_before(now, 20)

    chg_5m  = round(und_now - und_5m,  2) if und_now and und_5m  else None
    chg_20m = round(und_now - und_20m, 2) if und_now and und_20m else None

    return {
        "und_now" : und_now,
        "und_5m"  : und_5m,
        "und_20m" : und_20m,
        "chg_5m"  : chg_5m,
        "chg_20m" : chg_20m,
    }


def is_running() -> bool:
    with _lock:
        return len(_buf) > 0