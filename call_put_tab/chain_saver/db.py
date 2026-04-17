"""
chain_saver/db.py — 옵션 체인 SQLite 스키마 + CRUD
════════════════════════════════════════════════
테이블 구조:
  chain_data: 체인 전체 (ATM 스트림 + OTM/ITM/내일만기 스냅샷)
  ── v6.6 추가 컬럼: mid (중간가), theo (이론가), mispct (저고평가%)
"""
from __future__ import annotations
import os, sqlite3, logging
from typing import List, Dict

log = logging.getLogger(__name__)


def _resolve_dir() -> str:
    candidates = [
        r"C:\data\Greeks_history",
        os.path.join(os.path.expanduser("~"), "Downloads"),
        os.path.join(os.path.expanduser("~"), "Documents"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    os.makedirs(r"C:\data\Greeks_history", exist_ok=True)
    return r"C:\data\Greeks_history"

CHAIN_DIR: str = _resolve_dir()

def _db_path(day: str) -> str:
    return os.path.join(CHAIN_DIR, f"chain_{day}.db")


# ── 스키마 ──────────────────────────────────────────────────
_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS chain_data (
    ts          TEXT NOT NULL,   -- 저장 시각 (YYYY-MM-DD HH:MM:SS)
    sym         TEXT NOT NULL,   -- 종목 (SPX, SPXW ...)
    expiry      TEXT NOT NULL,   -- 만기 (YYYYMMDD)
    strike      REAL NOT NULL,   -- 행사가
    side        TEXT NOT NULL,   -- C / P
    bid         REAL,
    ask         REAL,
    last        REAL,
    iv          REAL,            -- Implied Volatility
    delta       REAL,
    gamma       REAL,
    vega        REAL,
    theta       REAL,
    und_price   REAL,            -- 기초자산 현재가
    source      TEXT,            -- 'stream' / 'snapshot'
    mid         REAL,            -- 중간가 (bid+ask)/2
    theo        REAL,            -- BS 이론가
    mispct      REAL             -- 저고평가% ((mid-theo)/theo*100)
)
"""
_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chain_ts_sym
    ON chain_data (ts, sym, expiry, strike, side)
"""

# 기존 DB 에 신규 컬럼 추가 (없을 경우에만)
_MIGRATE_SQLS = [
    "ALTER TABLE chain_data ADD COLUMN mid    REAL",
    "ALTER TABLE chain_data ADD COLUMN theo   REAL",
    "ALTER TABLE chain_data ADD COLUMN mispct REAL",
]


def _migrate(conn: sqlite3.Connection):
    """기존 DB 파일에 신규 컬럼이 없으면 추가."""
    for sql in _MIGRATE_SQLS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass   # 이미 존재하면 무시
    conn.commit()


# ── 연결 ────────────────────────────────────────────────────
def open_db(day: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(day), check_same_thread=False)
    conn.execute(_CREATE_SQL)
    conn.execute(_IDX_SQL)
    _migrate(conn)
    conn.commit()
    log.info("[ChainDB] open %s", _db_path(day))
    return conn


# ── INSERT ──────────────────────────────────────────────────
_INSERT_SQL = """
INSERT INTO chain_data
    (ts, sym, expiry, strike, side,
     bid, ask, last, iv, delta, gamma, vega, theta,
     und_price, source, mid, theo, mispct)
VALUES
    (?,?,?,?,?, ?,?,?,?,?,?,?,?, ?,?,?,?,?)
"""

def insert_rows(conn: sqlite3.Connection, rows: List[Dict]) -> int:
    if not rows:
        return 0
    params = [
        (
            r["ts"], r["sym"], r["expiry"], r["strike"], r["side"],
            r.get("bid"), r.get("ask"), r.get("last"),
            r.get("iv"), r.get("delta"), r.get("gamma"),
            r.get("vega"), r.get("theta"),
            r.get("und_price"), r.get("source", "stream"),
            r.get("mid"), r.get("theo"), r.get("mispct"),
        )
        for r in rows
    ]
    try:
        conn.executemany(_INSERT_SQL, params)
        conn.commit()
        return len(params)
    except sqlite3.Error as e:
        log.error("[ChainDB] insert 실패: %s", e)
        conn.rollback()
        return 0


# ── QUERY ───────────────────────────────────────────────────
_COLS = ["ts", "sym", "expiry", "strike", "side",
         "bid", "ask", "last", "iv", "delta", "gamma", "vega", "theta",
         "und_price", "source", "mid", "theo", "mispct"]

def load_chain(day: str, sym: str = "",
               expiry: str = "", strike: float = 0.0) -> List[Dict]:
    path = _db_path(day)
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    q = "SELECT * FROM chain_data WHERE 1=1"
    p: list = []
    if sym:    q += " AND sym=?";    p.append(sym)
    if expiry: q += " AND expiry=?"; p.append(expiry)
    if strike: q += " AND strike=?"; p.append(strike)
    q += " ORDER BY ts, expiry, strike, side"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(zip(_COLS, r)) for r in rows]


def available_days() -> list:
    return sorted([
        f[6:14] for f in os.listdir(CHAIN_DIR)
        if f.startswith("chain_") and f.endswith(".db")
    ])


# ── 수신 확인 쿼리 ───────────────────────────────────────────
def check_recent(day: str, minutes: int = 5) -> dict:
    """
    최근 N분간 저장된 데이터 현황 반환.
    scheduler 또는 디버그 콘솔에서 호출해 수신 상태 확인 가능.

    반환 예시:
      {
        'total_rows': 412,
        'with_iv':    398,
        'with_theo':  391,
        'streams':    310,
        'snapshots':  102,
        'latest_ts':  '2026-04-14 14:23:05',
        'coverage_iv':   '96.6%',
        'coverage_theo': '95.0%',
      }
    """
    path = _db_path(day)
    if not os.path.exists(path):
        return {"error": "DB 없음"}
    try:
        conn = sqlite3.connect(path)
        from datetime import datetime, timedelta, timezone
        # ★ ET 기준으로 cutoff 계산 (DB ts 컬럼이 ET 기준이므로 일치시킴)
        def _et_now():
            now_utc = datetime.now(timezone.utc)
            y = now_utc.year
            from datetime import timedelta as _td
            mar1 = datetime(y, 3, 1, tzinfo=timezone.utc)
            dst_start = mar1 + _td(days=(6 - mar1.weekday()) % 7 + 7)
            dst_start = dst_start.replace(hour=7)
            nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
            dst_end = nov1 + _td(days=(6 - nov1.weekday()) % 7)
            dst_end = dst_end.replace(hour=6)
            offset = _td(hours=-4 if dst_start <= now_utc < dst_end else -5)
            return now_utc + offset
        cutoff = (_et_now() - timedelta(minutes=minutes)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT iv, theo, source FROM chain_data WHERE ts >= ?",
            (cutoff,)
        ).fetchall()
        latest = conn.execute(
            "SELECT MAX(ts) FROM chain_data"
        ).fetchone()[0]
        conn.close()

        total     = len(rows)
        with_iv   = sum(1 for r in rows if r[0] is not None)
        with_theo = sum(1 for r in rows if r[1] is not None)
        streams   = sum(1 for r in rows if r[2] == "stream")
        snaps     = sum(1 for r in rows if r[2] == "snapshot")

        def pct(n): return f"{n/total*100:.1f}%" if total else "N/A"

        return {
            "total_rows":    total,
            "with_iv":       with_iv,
            "with_theo":     with_theo,
            "streams":       streams,
            "snapshots":     snaps,
            "latest_ts":     latest or "없음",
            "coverage_iv":   pct(with_iv),
            "coverage_theo": pct(with_theo),
        }
    except sqlite3.Error as e:
        return {"error": str(e)}