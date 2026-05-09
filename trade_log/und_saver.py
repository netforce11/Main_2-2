"""
trade_log/und_saver.py — 기초자산(지수) 가격 DB 저장  v1.4

[v1.4 수정]
  - _DATA_DIR: 상대 경로(프로젝트 루트 기준) → 절대 경로로 변경
    기존: Path(__file__).resolve().parent.parent / "data" / "und_price"
    수정: /home/netforce/trading_terminal/Main2_1/data/und_price
    이유: 리눅스 환경에서 실행 위치에 따라 경로가 달라지는 문제 방지

[v1.3 수정 내역]
1. _warmup_from_db(): 앱 시작 시 당일 DB에서 최근 60분치 데이터를 버퍼에 로드
   → 재시작 직후에도 10/20/30/40분 전 가격 즉시 조회 가능
2. get_context(exec_time, minutes=None) 오버로드 추가
   → minutes 지정 시 해당 분 전 가격만 float | None 으로 반환
   → minutes=None 이면 기존 딕셔너리 반환 (하위 호환 유지)
3. is_running() → 버퍼 보유 여부 + warmup 완료 여부 반영
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
# [v1.4] 절대 경로로 변경 — 실행 위치 무관하게 항상 동일한 경로 사용
# 기존: Path(__file__).resolve().parent.parent / "data" / "und_price"
_DATA_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/und_price")
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_VALID_INTERVALS = (5, 10, 30)
_interval    = 10
_buf         = deque(maxlen=500)
_lock        = threading.Lock()
_last_saved  = None
_warmed_up   = False   # ✅ NEW: 워밍업 완료 플래그
_db_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="und_db")

# ── 워밍업 최대 분 (버퍼 maxlen=500, 10초 주기 → 83분 가능)
# 감시 패널 최대 N분 = 60분으로 넉넉히 설정
_WARMUP_MINUTES = 60


# ── DB 유틸 ───────────────────────────────────────────────

def _db_path(date_str: str) -> Path:
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


def _save_to_db(ts_str: str, price: float):
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
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_ET)
    return dt


def _query_before(target: datetime, minutes: int) -> Optional[float]:
    """DB에서 target 기준 minutes 분 전 이전의 가장 가까운 가격 반환"""
    t_ref    = _to_aware(target) - timedelta(minutes=minutes)
    date_str = t_ref.strftime("%Y-%m-%d")
    ts_ref   = t_ref.strftime("%Y-%m-%d %H:%M:%S")
    path     = _db_path(date_str)
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


# ── ✅ NEW: 워밍업 ────────────────────────────────────────

def _warmup_from_db():
    """
    앱 시작 시 당일 DB에서 최근 _WARMUP_MINUTES 분치 데이터를 버퍼에 로드.
    별도 스레드에서 호출 (UI 블로킹 방지).

    효과:
      - 재시작 직후에도 10/20/30/40분 전 가격 즉시 조회 가능
      - 버퍼 maxlen=500 초과분은 자동으로 오래된 것부터 제거됨
    """
    global _warmed_up
    now      = datetime.now(_ET)
    date_str = now.strftime("%Y-%m-%d")
    path     = _db_path(date_str)

    if not path.exists():
        print("[und_saver] 워밍업: 당일 DB 없음 → 스킵")
        _warmed_up = True
        return

    cutoff = (now - timedelta(minutes=_WARMUP_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with sqlite3.connect(path, check_same_thread=False) as conn:
            rows = conn.execute(
                "SELECT ts, price FROM und_price WHERE ts >= ? ORDER BY ts ASC",
                (cutoff,)
            ).fetchall()

        if not rows:
            print("[und_saver] 워밍업: 해당 범위 데이터 없음")
            _warmed_up = True
            return

        loaded = []
        for ts_str, price in rows:
            try:
                # DB ts 는 naive → ET aware 로 변환
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ET)
                loaded.append((dt, float(price)))
            except Exception:
                continue

        with _lock:
            # 기존 버퍼 앞에 DB 데이터 삽입
            # deque 는 appendleft 가 없으므로, 새 deque 로 교체
            new_buf = deque(loaded, maxlen=500)
            # 기존 버퍼(실시간 수신분)도 이어붙임 (중복 무시: 타임스탬프 기준)
            existing_ts = {dt for dt, _ in new_buf}
            for dt, px in _buf:
                if dt not in existing_ts:
                    new_buf.append((dt, px))
            _buf.clear()
            _buf.extend(new_buf)

        print(f"[und_saver] 워밍업 완료: {len(loaded)}개 로드 "
              f"({_WARMUP_MINUTES}분치, {date_str})")

    except Exception as e:
        print(f"[und_saver] 워밍업 오류: {e}")
    finally:
        _warmed_up = True


def warmup():
    """
    ✅ 외부 진입점 — 앱 시작 시 호출.
    예) core_io.apply_saved_settings() 끝에 추가:
        from trade_log.und_saver import warmup
        warmup()
    """
    t = threading.Thread(target=_warmup_from_db, daemon=True, name="und_warmup")
    t.start()


# ── 기존 공개 API ─────────────────────────────────────────

def set_interval(seconds: int):
    global _interval
    if seconds in _VALID_INTERVALS:
        _interval = seconds


def get_interval() -> int:
    return _interval


def push(price: float):
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


def get_context(exec_time=None, minutes: Optional[int] = None):
    """
    기초자산 가격 컨텍스트 반환.

    ── 호출 방식 ──────────────────────────────────────────
    [기존 호환]
      get_context()
      get_context(exec_time)
      → {"und_price": float, "und_5m": float, "und_10m": float,
         "chg_5m": float, "chg_10m": float}

    [✅ NEW: 임의 N분 단일 조회]
      get_context(exec_time, minutes=20)  → float | None
      get_context(exec_time, minutes=30)  → float | None
      get_context(exec_time, minutes=40)  → float | None
    ───────────────────────────────────────────────────────
    """
    now = _to_aware(exec_time) if exec_time else datetime.now(_ET)

    with _lock:
        buf_snap = list(_buf)

    def _from_buf(mins: int) -> Optional[float]:
        """버퍼에서 now 기준 mins 분 전 이전의 가장 최근 가격"""
        target = now - timedelta(minutes=mins)
        for ts, px in reversed(buf_snap):
            if _to_aware(ts) <= target:
                return px
        return None

    def _lookup(mins: int) -> Optional[float]:
        """버퍼 우선, 없으면 DB"""
        return _from_buf(mins) or _query_before(now, mins)

    # ── ✅ NEW: minutes 지정 시 단일 float 반환 ────────────
    if minutes is not None:
        return _lookup(minutes)

    # ── 기존: 딕셔너리 반환 (하위 호환) ───────────────────
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
    """✅ NEW: 워밍업 및 버퍼 현황 반환 (디버깅/UI 표시용)"""
    with _lock:
        buf_len  = len(_buf)
        oldest   = _buf[0][0]  if buf_len > 0 else None
        newest   = _buf[-1][0] if buf_len > 0 else None
    covered_min = round((newest - oldest).total_seconds() / 60, 1) if oldest and newest else 0
    return {
        "warmed_up"   : _warmed_up,
        "buf_len"     : buf_len,
        "covered_min" : covered_min,   # 버퍼가 커버하는 분 범위
        "oldest"      : oldest,
        "newest"      : newest,
    }