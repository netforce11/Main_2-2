"""
chain_saver/db.py — 옵션 체인 SQLite 스키마 + CRUD
════════════════════════════════════════════════
테이블 구조:
  chain_data: 체인 전체 (ATM 스트림 + OTM/ITM/내일만기 스냅샷)
역할 분리:
  - db.py       : 스키마 정의, open/insert/query
  - buffer.py   : 메모리 버퍼 관리
  - worker.py   : 비동기 저장 스레드
  - scheduler.py: 타이머 + 장중 체크
"""
from __future__ import annotations
import os, sqlite3, logging
from typing import List, Dict

log = logging.getLogger(__name__)

# ── 저장 경로 (greeks_db.py 와 동일 디렉터리) ──────────────
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
    source      TEXT             -- 'stream' / 'snapshot'
)
"""
_IDX_SQL = """
CREATE INDEX IF NOT EXISTS idx_chain_ts_sym
    ON chain_data (ts, sym, expiry, strike, side)
"""

# ── 연결 ────────────────────────────────────────────────────
def open_db(day: str) -> sqlite3.Connection:
    """일별 DB 열기 (없으면 생성)."""
    conn = sqlite3.connect(_db_path(day), check_same_thread=False)
    conn.execute(_CREATE_SQL)
    conn.execute(_IDX_SQL)
    conn.commit()
    log.info("[ChainDB] open %s", _db_path(day))
    return conn

# ── INSERT ──────────────────────────────────────────────────
_INSERT_SQL = """
INSERT INTO chain_data
    (ts, sym, expiry, strike, side,
     bid, ask, last, iv, delta, gamma, vega, theta,
     und_price, source)
VALUES
    (?,?,?,?,?, ?,?,?,?,?,?,?,?, ?,?)
"""

def insert_rows(conn: sqlite3.Connection, rows: List[Dict]) -> int:
    """rows: buffer.py 에서 넘어오는 dict 리스트. 성공 건수 반환."""
    if not rows:
        return 0
    params = [
        (
            r["ts"], r["sym"], r["expiry"], r["strike"], r["side"],
            r.get("bid"), r.get("ask"), r.get("last"),
            r.get("iv"), r.get("delta"), r.get("gamma"),
            r.get("vega"), r.get("theta"),
            r.get("und_price"), r.get("source", "stream"),
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
_COLS = ["ts","sym","expiry","strike","side",
         "bid","ask","last","iv","delta","gamma","vega","theta",
         "und_price","source"]

def load_chain(day: str, sym: str = "",
               expiry: str = "", strike: float = 0.0) -> List[Dict]:
    """조건별 조회. 모두 빈값이면 전체 반환."""
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
