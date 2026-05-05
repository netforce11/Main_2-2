"""
trade_log/query.py — 체결/주문/매매 조회  v1.3
"""

from __future__ import annotations
from .db import get_conn


def get_executions_by_date(date: str) -> list[dict]:
    """날짜별 체결 내역. BAG 수준(strike=0) 제외."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date=? AND strike > 0 ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_grouped_executions_by_date(date: str) -> list[dict]:
    """
    날짜별 체결 내역을 주문별로 묶어서 반환.
    - oid > 0 : oid 기준 그룹핑
    - oid = 0 : ts(초단위) 기준 그룹핑 (IB가 orderId=0으로 보내는 청산 BAG)
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date=? AND strike > 0 ORDER BY ts, id",
        (date,)
    ).fetchall()
    conn.close()

    from collections import defaultdict

    # oid>0 그룹, oid=0 그룹 분리
    named   = defaultdict(list)   # oid -> [legs]
    unnamed = defaultdict(list)   # ts초 -> [legs]

    for r in rows:
        d = dict(r)
        if d['oid'] and d['oid'] > 0:
            named[d['oid']].append(d)
        else:
            # ts 초단위 (HH:MM:SS) 로 묶기
            ts_key = d['ts'][11:19] if d.get('ts') else 'unknown'
            unnamed[ts_key].append(d)

    # 두 그룹 합치기 (시각 순 정렬)
    all_groups = []
    for oid, legs in named.items():
        all_groups.append(('oid', oid, legs))
    for ts_key, legs in unnamed.items():
        all_groups.append(('ts', ts_key, legs))

    # 첫 번째 레그의 ts 기준 정렬
    all_groups.sort(key=lambda x: x[2][0]['ts'])

    result = []
    for _, key, legs in all_groups:
        is_spread = len(legs) >= 2
        summary   = _make_summary(legs, is_spread)
        result.append({
            'oid':       key,
            'is_spread': is_spread,
            'summary':   summary,
            'legs':      legs,
        })

    return result


def _make_summary(legs: list, is_spread: bool) -> dict:
    """레그 목록에서 요약 딕셔너리 생성."""
    bot_sum = sum(l['price'] * l['qty'] for l in legs if l['action'] == 'BOT')
    sld_sum = sum(l['price'] * l['qty'] for l in legs if l['action'] == 'SLD')
    net     = round(bot_sum - sld_sum, 4)
    total_commission = round(sum(l.get('commission', 0) or 0 for l in legs), 2)
    qty  = legs[0]['qty']
    ts   = legs[0]['ts']
    sym  = legs[0]['sym']

    if net > 0:
        action    = 'BOT'
        net_price = round(net / qty, 4)
    elif net < 0:
        action    = 'SLD'
        net_price = round(abs(net) / qty, 4)
    else:
        action    = legs[0]['action']
        net_price = 0.0

    return {
        'ts':         ts,
        'action':     action,
        'sym':        sym,
        'net_price':  net_price,
        'qty':        qty,
        'commission': total_commission,
        'is_spread':  is_spread,
    }


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
