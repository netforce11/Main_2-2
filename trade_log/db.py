"""
trade_log/db.py — SQLite 연결 / 테이블 초기화  v1.1
DB 파일: data/trades.db  (영구 보존)

테이블:
  executions  — 체결 원본 (지수 컨텍스트 포함)
  order_log   — 주문 접수/미체결 상태 (초단위)
  trades      — BUY/SELL 매칭 완성 거래 (실현손익)
"""

import sqlite3
from pathlib import Path

_DB_PATH = Path("data/trades.db")


def get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS executions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           TEXT    NOT NULL,   -- 체결 시각 ET (YYYY-MM-DD HH:MM:SS)
        date         TEXT    NOT NULL,   -- 날짜 (YYYY-MM-DD)
        oid          INTEGER NOT NULL,
        source       TEXT    NOT NULL,   -- 'callput' | 'combo'
        sym          TEXT    NOT NULL,
        expiry       TEXT,
        right        TEXT,               -- C / P
        strike       REAL,
        action       TEXT    NOT NULL,   -- BUY / SELL
        qty          REAL    NOT NULL,
        price        REAL    NOT NULL,
        commission   REAL    DEFAULT 0,
        und_price    REAL,               -- 체결 시 기초자산 현재가
        und_5m       REAL,               -- 5분 전 기초자산 가격
        und_10m      REAL,               -- 10분 전 기초자산 가격
        chg_5m       REAL,               -- und_price - und_5m
        chg_10m      REAL                -- und_price - und_10m
    );

    CREATE TABLE IF NOT EXISTS order_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           TEXT    NOT NULL,   -- 주문/상태변경 시각 (초단위)
        date         TEXT    NOT NULL,
        oid          INTEGER NOT NULL,
        source       TEXT    NOT NULL,
        sym          TEXT,
        expiry       TEXT,
        right        TEXT,
        strike       REAL,
        action       TEXT,               -- BUY / SELL
        qty          REAL,
        price        REAL,               -- 주문가
        order_type   TEXT,               -- LMT / MKT
        status       TEXT    NOT NULL,   -- Submitted/Filled/Cancelled/...
        und_price    REAL                -- 상태변경 시 기초자산 가격
    );

    CREATE TABLE IF NOT EXISTS trades (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        open_date    TEXT    NOT NULL,
        close_date   TEXT,
        source       TEXT    NOT NULL,
        sym          TEXT    NOT NULL,
        expiry       TEXT,
        right        TEXT,
        strike       REAL,
        qty          REAL    NOT NULL,
        entry_price  REAL    NOT NULL,
        exit_price   REAL,
        realized_pnl REAL,
        commission   REAL    DEFAULT 0,
        status       TEXT    DEFAULT 'open'
    );

    CREATE INDEX IF NOT EXISTS idx_exec_date    ON executions(date);
    CREATE INDEX IF NOT EXISTS idx_exec_oid     ON executions(oid);
    CREATE INDEX IF NOT EXISTS idx_ordlog_date  ON order_log(date);
    CREATE INDEX IF NOT EXISTS idx_ordlog_oid   ON order_log(oid);
    CREATE INDEX IF NOT EXISTS idx_trades_date  ON trades(open_date);
    """)
    conn.commit()
