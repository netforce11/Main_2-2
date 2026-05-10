"""
trade_log/und_saver_db.py — 기초자산 가격 DB I/O 전용  v1.0
════════════════════════════════════════════════════════════
und_saver.py에서 DB 관련 로직을 분리.

포함:
  _db_path(date_str)      — DB 파일 경로 반환
  _ensure_table(conn)     — und_price 테이블 + 인덱스 생성
  save_to_db(ts_str, price) — 비동기(ThreadPoolExecutor) DB INSERT
  query_before(target, minutes) — target 기준 minutes 분 전 가격 조회
  warmup_from_db(buf, lock)     — 앱 시작 시 당일 DB → 버퍼 로드
════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import sqlite3
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
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
_DATA_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/und_price")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_WARMUP_MINUTES = 60

# 단일 쓰기 스레드 (DB locked 방지)
_db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="und_db")


# ── DB 유틸 ───────────────────────────────────────────────────

def _db_path(date_str: str) -> Path:
    return _DATA_DIR / f"und_{date_str}.db"


def _ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS und_price (
            ts    TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON und_price(ts)")
    conn.commit()


def _to_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt


# ── 비동기 DB 쓰기 ────────────────────────────────────────────

def save_to_db(ts_str: str, price: float) -> None:
    """DB에 가격 1건 INSERT (ThreadPoolExecutor 비동기)."""
    def _write():
        date_str = ts_str[:10]
        path     = _db_path(date_str)
        try:
            with sqlite3.connect(str(path), check_same_thread=False) as conn:
                _ensure_table(conn)
                conn.execute(
                    "INSERT INTO und_price(ts, price) VALUES(?, ?)",
                    (ts_str, price))
        except Exception as e:
            print(f"[und_saver_db] DB 저장 오류: {e}")

    _db_executor.submit(_write)


# ── DB 조회 ───────────────────────────────────────────────────

def query_before(target: datetime, minutes: int) -> Optional[float]:
    """
    target 기준 minutes 분 이전의 가장 가까운 가격 반환.
    해당 DB 없거나 데이터 없으면 None.
    """
    t_ref    = _to_aware(target) - timedelta(minutes=minutes)
    date_str = t_ref.strftime("%Y-%m-%d")
    ts_ref   = t_ref.strftime("%Y-%m-%d %H:%M:%S")
    path     = _db_path(date_str)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(str(path), check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT price FROM und_price "
                "WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                (ts_ref,)
            ).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


# ── 워밍업 ────────────────────────────────────────────────────

def warmup_from_db(buf: deque, lock: Lock) -> None:
    """
    앱 시작 시 당일 DB에서 최근 _WARMUP_MINUTES 분치 데이터를 buf에 로드.
    별도 스레드에서 호출 (UI 블로킹 방지).

    Args:
        buf  : und_saver._buf  (deque, maxlen=500)
        lock : und_saver._lock
    """
    now      = datetime.now(_ET)
    date_str = now.strftime("%Y-%m-%d")
    path     = _db_path(date_str)

    if not path.exists():
        print("[und_saver_db] 워밍업: 당일 DB 없음 → 스킵")
        return

    cutoff = (now - timedelta(minutes=_WARMUP_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(str(path), check_same_thread=False) as conn:
            rows = conn.execute(
                "SELECT ts, price FROM und_price "
                "WHERE ts >= ? ORDER BY ts ASC",
                (cutoff,)
            ).fetchall()

        if not rows:
            print("[und_saver_db] 워밍업: 해당 범위 데이터 없음")
            return

        loaded = []
        for ts_str, price in rows:
            try:
                dt = datetime.strptime(
                    ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ET)
                loaded.append((dt, float(price)))
            except Exception:
                continue

        with lock:
            new_buf = deque(loaded, maxlen=500)
            existing_ts = {dt for dt, _ in new_buf}
            for dt, px in buf:
                if dt not in existing_ts:
                    new_buf.append((dt, px))
            buf.clear()
            buf.extend(new_buf)

        print(f"[und_saver_db] 워밍업 완료: {len(loaded)}개 로드 "
              f"({_WARMUP_MINUTES}분치, {date_str})")

    except Exception as e:
        print(f"[und_saver_db] 워밍업 오류: {e}")
