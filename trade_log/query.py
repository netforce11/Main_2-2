"""
trade_log/query.py — 체결/주문/매매 조회  v1.6

[v1.6 신규]
  - get_monthly_summary()  : 월간 합산 손익 (실현+만기소멸 모두 포함)
  - get_monthly_detail()   : 월간 거래 목록 (closed + expired)
  - get_daily_summary()    : trades 테이블 기반으로 개선 (정확한 실현손익 반영)
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
    손익: 행사가 조합별 FIFO 매칭
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM executions WHERE date=? AND strike > 0 ORDER BY ts, id",
        (date,)
    ).fetchall()
    conn.close()

    from collections import defaultdict, deque

    named   = defaultdict(list)
    unnamed = defaultdict(list)

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

    all_groups.sort(key=lambda legs: legs[0]['ts'])

    summaries = [_make_summary(legs) for legs in all_groups]

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
                entry = queue.popleft()
                pnl = round((net_price - entry['price']) * qty * 100, 2)
                summaries[idx]['pnl'] = pnl

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
        'pnl':        None,
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
    """
    trades 테이블 기반 일일 요약.
    closed + expired 모두 포함 → 만기소멸 손실도 반영.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT realized_pnl, commission FROM trades "
        "WHERE close_date=? AND status IN ('closed', 'expired')",
        (date,)
    ).fetchall()
    conn.close()

    if not rows:
        return {"trades": 0, "realized_pnl": 0.0,
                "commission": 0.0, "net_pnl": 0.0}

    gross   = round(sum(r['realized_pnl'] or 0 for r in rows), 2)
    comm    = round(sum(r['commission']   or 0 for r in rows), 2)
    return {
        "trades":       len(rows),
        "realized_pnl": gross,
        "commission":   comm,
        "net_pnl":      round(gross - comm, 2),
    }


# ──────────────────────────────────────────────────────────────────
# [v1.6 신규] 월간 집계
# ──────────────────────────────────────────────────────────────────

def get_monthly_summary(year: int, month: int) -> dict:
    """
    월간 합산 손익.

    closed  : 체결로 청산된 거래
    expired : 만기소멸 처리된 거래 (expire_worthless 호출 후)
    두 가지 모두 합산하여 반환.

    Parameters
    ----------
    year  : 4자리 연도 (예: 2026)
    month : 월 (1~12)

    Returns
    -------
    {
        "year_month"  : "2026-04",
        "trade_cnt"   : 38,          # closed + expired 합계 건수
        "closed_cnt"  : 35,          # 체결 청산 건수
        "expired_cnt" : 3,           # 만기소멸 건수
        "gross_pnl"   : 2450.00,     # 실현손익 합계 (수수료 미차감)
        "commission"  : 92.00,       # 수수료 합계
        "net_pnl"     : 2358.00,     # 순손익 (gross - commission)
    }
    """
    ym = f"{year:04d}-{month:02d}"
    conn = get_conn()

    rows = conn.execute("""
        SELECT
            status,
            COUNT(*)        AS cnt,
            SUM(realized_pnl) AS gross,
            SUM(commission)   AS comm
        FROM trades
        WHERE strftime('%Y-%m', close_date) = ?
          AND status IN ('closed', 'expired')
        GROUP BY status
    """, (ym,)).fetchall()
    conn.close()

    result = {
        "year_month":  ym,
        "trade_cnt":   0,
        "closed_cnt":  0,
        "expired_cnt": 0,
        "gross_pnl":   0.0,
        "commission":  0.0,
        "net_pnl":     0.0,
    }

    for row in rows:
        status = row['status']
        cnt    = row['cnt']   or 0
        gross  = row['gross'] or 0.0
        comm   = row['comm']  or 0.0

        result['trade_cnt'] += cnt
        result['gross_pnl'] += gross
        result['commission'] += comm

        if status == 'closed':
            result['closed_cnt'] = cnt
        elif status == 'expired':
            result['expired_cnt'] = cnt

    result['gross_pnl']  = round(result['gross_pnl'],  2)
    result['commission'] = round(result['commission'],  2)
    result['net_pnl']    = round(result['gross_pnl'] - result['commission'], 2)

    return result


def get_monthly_detail(year: int, month: int) -> list[dict]:
    """
    월간 거래 목록 (closed + expired 모두).

    날짜별 정렬하여 반환.
    각 행에 status 포함 → UI에서 'expired' 행을 회색 등으로 구분 가능.

    Parameters
    ----------
    year  : 4자리 연도
    month : 월 (1~12)

    Returns
    -------
    list of dict — trades 테이블 컬럼 + status 포함
    """
    ym = f"{year:04d}-{month:02d}"
    conn = get_conn()
    rows = conn.execute("""
        SELECT *
        FROM trades
        WHERE strftime('%Y-%m', close_date) = ?
          AND status IN ('closed', 'expired')
        ORDER BY close_date, id
    """, (ym,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_daily_breakdown(year: int, month: int) -> list[dict]:
    """
    월간 일별 손익 브레이크다운.

    월간 요약 아래에 날짜별 소계를 표시할 때 사용.
    예: 2026-04-01: 3건  +$150.00 / 2026-04-02: 휴지 1건  -$200.00

    Returns
    -------
    [
        {
            "date":        "2026-04-01",
            "trade_cnt":   3,
            "expired_cnt": 0,
            "gross_pnl":   150.00,
            "commission":  6.00,
            "net_pnl":     144.00,
        },
        ...
    ]
    """
    ym = f"{year:04d}-{month:02d}"
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            close_date,
            COUNT(*)            AS trade_cnt,
            SUM(CASE WHEN status='expired' THEN 1 ELSE 0 END) AS expired_cnt,
            SUM(realized_pnl)   AS gross,
            SUM(commission)     AS comm
        FROM trades
        WHERE strftime('%Y-%m', close_date) = ?
          AND status IN ('closed', 'expired')
        GROUP BY close_date
        ORDER BY close_date
    """, (ym,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        gross = r['gross'] or 0.0
        comm  = r['comm']  or 0.0
        result.append({
            "date":        r['close_date'],
            "trade_cnt":   r['trade_cnt']   or 0,
            "expired_cnt": r['expired_cnt'] or 0,
            "gross_pnl":   round(gross, 2),
            "commission":  round(comm,  2),
            "net_pnl":     round(gross - comm, 2),
        })

    return result
