"""
trade_log/matcher.py — BUY/SELL 매칭 → 실현손익 계산
log_exec() 호출 직후 run_match() 를 호출하면 자동으로 매칭.

매칭 규칙 (FIFO):
  동일 (source, sym, expiry, right, strike) 기준
  BUY → trades 에 'open' 행 생성
  SELL → 가장 오래된 open 행과 매칭 → 'closed' + realized_pnl 계산
"""

from __future__ import annotations
from .db import get_conn

_MULTIPLIER = 100   # SPX/SPXW 옵션 승수


def run_match(source: str, sym: str, expiry: str,
              right: str, strike: float) -> None:
    """
    새 체결이 들어온 뒤 해당 종목의 BUY/SELL 을 FIFO 매칭.
    log_exec() 직후 호출.
    """
    try:
        conn = get_conn()
        _match(conn, source, sym, expiry, right, strike)
        conn.close()
    except Exception as e:
        print(f"[trade_log] 매칭 오류: {e}")


def _match(conn, source, sym, expiry, right, strike) -> None:
    key = (source, sym, expiry, right, strike)

    # 아직 매칭 안 된 executions 전체 (시간순)
    rows = conn.execute("""
        SELECT id, date, action, qty, price, commission
        FROM executions
        WHERE source=? AND sym=? AND expiry=? AND right=? AND strike=?
        ORDER BY id
    """, key).fetchall()

    # FIFO 스택: [(qty, price, date, commission), ...]
    open_stack: list[dict] = []

    for r in rows:
        action, qty, price, comm = r["action"], r["qty"], r["price"], r["commission"]

        if action == "BUY":
            open_stack.append({
                "qty": qty, "price": price,
                "date": r["date"], "comm": comm
            })
        else:  # SELL
            remaining = qty
            while remaining > 0 and open_stack:
                top = open_stack[0]
                matched = min(top["qty"], remaining)

                pnl = (price - top["price"]) * matched * _MULTIPLIER
                total_comm = (comm / qty * matched) + (top["comm"] / top["qty"] * matched)

                # trades 테이블에 없으면 INSERT, 있으면 갱신
                conn.execute("""
                    INSERT INTO trades
                      (open_date, close_date, source, sym, expiry, right,
                       strike, qty, entry_price, exit_price,
                       realized_pnl, commission, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'closed')
                """, (top["date"], r["date"], source, sym, expiry, right,
                      strike, matched, top["price"], price,
                      round(pnl, 2), round(total_comm, 2)))

                top["qty"] -= matched
                remaining  -= matched
                if top["qty"] <= 0:
                    open_stack.pop(0)

            # 미매칭 SELL (숏 진입) — open 으로 기록
            if remaining > 0:
                open_stack.append({
                    "qty": -remaining, "price": price,
                    "date": r["date"], "comm": comm
                })

    # 남은 open_stack → trades 'open' 행 재생성 (기존 open 삭제 후)
    conn.execute("""
        DELETE FROM trades
        WHERE source=? AND sym=? AND expiry=? AND right=? AND strike=?
          AND status='open'
    """, key)

    for item in open_stack:
        if item["qty"] == 0:
            continue
        conn.execute("""
            INSERT INTO trades
              (open_date, source, sym, expiry, right,
               strike, qty, entry_price, commission, status)
            VALUES (?,?,?,?,?,?,?,?,?,'open')
        """, (item["date"], source, sym, expiry, right,
              strike, item["qty"], item["price"], item["comm"]))

    conn.commit()
