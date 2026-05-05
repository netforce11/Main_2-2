"""
trade_log/query.py — 체결/주문/매매 조회  v1.5
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
    손익: 행사가 조합별 FIFO 매칭 (같은 행사가 여러 번, 다른 행사가 혼용 모두 대응)
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date=? AND strike > 0 ORDER BY ts, id",
        (date,)
    ).fetchall()
    conn.close()

    from collections import defaultdict
    from collections import deque

    # ── 그룹핑 ───────────────────────────────────────────
    named   = defaultdict(list)   # oid>0  → oid 기준
    unnamed = defaultdict(list)   # oid=0  → ts초 기준

    for r in rows:
        d = dict(r)
        if d['oid'] and d['oid'] > 0:
            named[d['oid']].append(d)
        else:
            ts_key = d['ts'][11:19] if d.get('ts') else 'unknown'
            unnamed[ts_key].append(d)

    all_groups = []
    for oid, legs in named.items():
        all_groups.append(legs)
    for legs in unnamed.values():
        all_groups.append(legs)

    # 시각 순 정렬
    all_groups.sort(key=lambda legs: legs[0]['ts'])

    # ── 요약 생성 ─────────────────────────────────────────
    summaries = [_make_summary(legs) for legs in all_groups]

    # ── FIFO 손익 매칭 ───────────────────────────────────
    # key: frozenset of strikes → deque of (net_price, qty, summary_idx)
    bot_queues: dict = defaultdict(deque)

    for idx, s in enumerate(summaries):
        strikes_key = frozenset(
            int(l['strike']) for l in all_groups[idx] if l.get('strike'))
        action    = s['action']
        net_price = s['net_price']
        qty       = s['qty']

        if action == 'BOT':
            bot_queues[strikes_key].append({
                'price': net_price,
                'qty':   qty,
                'idx':   idx,
            })
        elif action == 'SLD':
            queue = bot_queues.get(strikes_key)
            if queue:
                entry = queue.popleft()   # FIFO: 가장 먼저 산 것과 매칭
                pnl = round((net_price - entry['price']) * qty * 100, 2)
                summaries[idx]['pnl'] = pnl
            # else: 매칭되는 BOT 없음 (공매도 등) → pnl=None 유지

    # ── 결과 조립 ─────────────────────────────────────────
    result = []
    for idx, (legs, summary) in enumerate(zip(all_groups, summaries)):
        result.append({
            'oid':       legs[0].get('oid', 0),
            'is_spread': len(legs) >= 2,
            'summary':   summary,
            'legs':      legs,
        })

    return result


def _make_summary(legs: list) -> dict:
    """레그 목록에서 요약 딕셔너리 생성."""
    bot_sum = sum(l['price'] * l['qty'] for l in legs if l['action'] == 'BOT')
    sld_sum = sum(l['price'] * l['qty'] for l in legs if l['action'] == 'SLD')
    net     = round(bot_sum - sld_sum, 4)
    total_commission = round(sum(l.get('commission', 0) or 0 for l in legs), 2)
    qty = legs[0]['qty']
    ts  = legs[0]['ts']
    sym = legs[0]['sym']

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
        'pnl':        None,   # FIFO 매칭 후 채워짐
    }


def get_executions_range(start: str, end: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date BETWEEN ? AND ? ORDER BY id",
        (start, end)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_log_by_date(date: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM order_log WHERE date=? ORDER BY id", (date,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_order_log_by_oid(oid: int) -> list[dict]:
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
    """executions 기반 일일 요약."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT action, qty, price, commission FROM executions "
        "WHERE date=? AND strike > 0", (date,)
    ).fetchall()
    conn.close()

    if not rows:
        return {"trades": 0, "realized_pnl": 0.0,
                "commission": 0.0, "net_pnl": 0.0}

    total_comm = round(sum(r['commission'] or 0 for r in rows), 2)
    return {
        "trades":       len(rows),
        "realized_pnl": 0.0,
        "commission":   total_comm,
        "net_pnl":      0.0,
    }