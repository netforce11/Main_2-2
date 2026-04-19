"""
trade_log/query.py — 체결/주문/매매 조회  v1.1
"""

from __future__ import annotations
from .db import get_conn


def get_executions_by_date(date: str) -> list[dict]:
    """날짜별 체결 내역 (und 컨텍스트 포함)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date=? ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_executions_range(start: str, end: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date BETWEEN ? AND ? ORDER BY id",
        (start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_log_by_date(date: str) -> list[dict]:
    """날짜별 주문 접수/미체결 로그 (초단위 시각 포함)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM order_log WHERE date=? ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_log_by_oid(oid: int) -> list[dict]:
    """특정 주문 ID의 전체 상태 변화 이력."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM order_log WHERE oid=? ORDER BY id", (oid,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trades_by_date(date: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE close_date=? ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_trades() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE status='open' ORDER BY open_date, id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summary(date: str) -> dict:
    """하루 요약: 거래 수 / 실현손익 / 수수료 / 순손익."""
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) AS trades,
               SUM(realized_pnl) AS realized_pnl,
               SUM(commission)   AS commission
        FROM trades
        WHERE close_date=? AND status='closed'
    """, (date,)).fetchone()
    conn.close()
    if not row or row["trades"] == 0:
        return {"trades": 0, "realized_pnl": 0.0,
                "commission": 0.0, "net_pnl": 0.0}
    pnl  = row["realized_pnl"] or 0.0
    comm = row["commission"]    or 0.0
    return {
        "trades":       row["trades"],
        "realized_pnl": round(pnl, 2),
        "commission":   round(comm, 2),
        "net_pnl":      round(pnl - comm, 2),
    }
