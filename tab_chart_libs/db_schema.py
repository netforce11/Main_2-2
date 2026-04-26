"""
data/db_schema.py — SQLite 스키마 정의 + DB 초기화
────────────────────────────────────────────────────────
테이블:
  pnl_history  — 체결/PnL 이력
  watch_alerts — 감시 알람 이력
  tick_speed   — 틱/호가 속도 집계 (10s/30s/60s)
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pnl_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    action      TEXT NOT NULL,
    qty         INTEGER NOT NULL,
    price       REAL NOT NULL,
    commission  REAL DEFAULT 0.0,
    pnl         REAL DEFAULT 0.0,
    strategy    TEXT DEFAULT '',
    spx_price   REAL DEFAULT 0.0,
    vix         REAL DEFAULT 0.0,
    note        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS watch_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    alert_type  TEXT NOT NULL,
    condition   TEXT DEFAULT '',
    triggered   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tick_speed (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,      -- ISO8601: '2026-04-24T09:31:02'
    symbol      TEXT NOT NULL,      -- 'SPX'
    w10_tick    INTEGER DEFAULT 0,  -- 10초 Last 틱 카운트
    w10_quote   INTEGER DEFAULT 0,  -- 10초 Bid/Ask 변경 카운트
    w30_tick    INTEGER DEFAULT 0,
    w30_quote   INTEGER DEFAULT 0,
    w60_tick    INTEGER DEFAULT 0,
    w60_quote   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pnl_ts       ON pnl_history(ts);
CREATE INDEX IF NOT EXISTS idx_pnl_symbol   ON pnl_history(symbol);
CREATE INDEX IF NOT EXISTS idx_alert_ts     ON watch_alerts(ts);
CREATE INDEX IF NOT EXISTS idx_tick_ts      ON tick_speed(ts);
CREATE INDEX IF NOT EXISTS idx_tick_symbol  ON tick_speed(symbol);
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[DB] 초기화 완료: {DB_PATH}")

if __name__ == "__main__":
    init_db()
