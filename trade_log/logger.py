"""
trade_log/logger.py — 체결/주문 DB 저장  v1.1
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from .db import get_conn

_ET = timezone(timedelta(hours=-5))


def _et_now() -> tuple[str, str]:
    now = datetime.now(_ET)
    return now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d")


def log_exec(
    oid:        int,
    source:     str,
    sym:        str,
    action:     str,
    qty:        float,
    price:      float,
    expiry:     str   = "",
    right:      str   = "",
    strike:     float = 0.0,
    commission: float = 0.0,
    strategy:   str   = "",   # ★ NEW: 전략명 (콜스프레드 / 풋스프레드 등)
    und_ctx:    dict  = None,
) -> None:
    """체결 1건 → executions INSERT."""
    ts, date = _et_now()
    ctx = und_ctx or {}
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO executions
              (ts, date, oid, source, sym, expiry, right, strike,
               action, strategy, qty, price, commission,
               und_price, und_5m, und_10m, chg_5m, chg_10m)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ts, date, oid, source, sym, expiry, right,
              int(strike) if strike else 0,
              action, strategy or None, qty, price, commission,
              ctx.get("und_price"), ctx.get("und_5m"), ctx.get("und_10m"),
              ctx.get("chg_5m"),    ctx.get("chg_10m")))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[trade_log] executions INSERT 오류: {e}")


def log_order(
    oid:        int,
    source:     str,
    status:     str,
    sym:        str   = "",
    expiry:     str   = "",
    right:      str   = "",
    strike:     float = 0.0,
    action:     str   = "",
    qty:        float = 0,
    price:      float = 0.0,
    order_type: str   = "",
    und_price:  float = None,
) -> None:
    """주문 접수/상태변경 1건 → order_log INSERT."""
    ts, date = _et_now()
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO order_log
              (ts, date, oid, source, sym, expiry, right, strike,
               action, qty, price, order_type, status, und_price)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ts, date, oid, source, sym, expiry, right,
              int(strike) if strike else 0,
              action, qty, price, order_type, status, und_price))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[trade_log] order_log INSERT 오류: {e}")


def log_commission(oid: int, commission: float) -> None:
    """
    CommissionReport 콜백 → executions 수수료 갱신.
    자동 계산값($1×qty) 포함 모든 기존 값을 실제 수수료로 덮어씀.
    """
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE executions SET commission=? WHERE oid=?",
            (commission, oid))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[trade_log] commission 갱신 오류: {e}")