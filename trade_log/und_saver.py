"""
trade_log/und_saver.py — 기초자산(지수) 가격 DB 저장  v1.2
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
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "und_price"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_VALID_INTERVALS = (5, 10, 30)
_interval = 10
_buf = deque(maxlen=500)
_lock = threading.Lock()
_last_saved = None
_db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="und_db")


def _db_path(date_str):
    return _DATA_DIR / f"und_{date_str}.db"


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS und_price (
            ts    TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON und_price(ts)")
    conn.commit()


def _save_to_db(ts_str, price):
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


def _to_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt


def _query_before(target, minutes):
    t_ref    = _to_aware(target) - timedelta(minutes=minutes)
    date_str = t_ref.strftime("%Y-%m-%d")
    ts_ref   = t_ref.strftime("%Y-%m-%d %H:%M:%S")
    path = _db_path(date_str)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path, check_same_thread=False) as conn:
            row = conn.execute(
                "SELECT price FROM und_price WHERE ts <= ? ORDER BY ts DESC LIMIT 1",
                (ts_ref,)
            ).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


def set_interval(seconds):
    global _interval
    if seconds in _VALID_INTERVALS:
        _interval = seconds


def get_interval():
    return _interval


def push(price):
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
        _db_executor.submit(_save_to_db, ts_str, price)


def get_context(exec_time=None):
    now = _to_aware(exec_time) if exec_time else datetime.now(_ET)
    with _lock:
        buf_snap = list(_buf)
    und_price = buf_snap[-1][1] if buf_snap else None

    def _from_buf(minutes):
        target = now - timedelta(minutes=minutes)
        for ts, px in reversed(buf_snap):
            if ts <= target:
                return px
        return None

    und_5m  = _from_buf(5)  or _query_before(now, 5)
    und_10m = _from_buf(10) or _query_before(now, 10)
    chg_5m  = round(und_price - und_5m,  2) if und_price and und_5m  else None
    chg_10m = round(und_price - und_10m, 2) if und_price and und_10m else None

    return {
        "und_price": und_price,
        "und_5m"  : und_5m,
        "und_10m" : und_10m,
        "chg_5m"  : chg_5m,
        "chg_10m" : chg_10m,
    }


def is_running():
    with _lock:
        return len(_buf) > 0
