"""
trade_log/matcher.py — BUY/SELL 매칭 → 실현손익 계산  v1.2

[v1.1 수정] SQLite DB locked 방지
  - run_match()를 logger.py의 _db_write_queue에 직렬화하여 실행

[v1.2 신규] expire_worthless() — 만기 소멸 처리
  - 만기일에 결제 없이 휴지된 포지션을 'expired' 상태로 처리
  - 매수 포지션: exit_price=0 → 실현손익 = -entry_price × qty × 100
  - 매도(숏) 포지션: exit_price=0 → 실현손익 = +entry_price × qty × 100
  - DB의 'open' 포지션을 'expired'로 전환
  - logger._db_write_queue에 작업을 넣어 DB locked 방지

매칭 규칙 (FIFO):
  동일 (source, sym, expiry, right, strike) 기준
  BUY → trades 에 'open' 행 생성
  SELL → 가장 오래된 open 행과 매칭 → 'closed' + realized_pnl 계산
"""

from __future__ import annotations
from .db import get_conn
from .logger import _db_write_queue   # [v1.1] 공유 큐 사용

_MULTIPLIER = 100   # SPX/SPXW 옵션 승수


def run_match(source: str, sym: str, expiry: str,
              right: str, strike: float) -> None:
    """
    새 체결이 들어온 뒤 해당 종목의 BUY/SELL 을 FIFO 매칭.
    log_exec() 직후 호출.

    [v1.1] logger._db_write_queue에 작업을 추가하여
    DB 쓰기 스레드에서 순차 처리 → DB locked 방지.
    """
    _key = (source, sym, expiry, right, strike)

    def _write():
        try:
            conn = get_conn()
            _match(conn, *_key)
            conn.close()
        except Exception as e:
            print(f"[trade_log] 매칭 오류: {e}")

    _db_write_queue.put(_write)


# ──────────────────────────────────────────────────────────────────
# [v1.2 신규] expire_worthless
# ──────────────────────────────────────────────────────────────────

def expire_worthless(sym: str, expiry: str, right: str,
                     strike: float, expired_date: str,
                     source: str | None = None) -> int:
    """
    만기 소멸 처리 — DB 쓰기 큐에 작업 추가.

    Parameters
    ----------
    sym          : 기초자산 심볼 (예: 'SPX')
    expiry       : 옵션 만기일 (예: '20260117')
    right        : 'C' 또는 'P'
    strike       : 행사가 (int 혹은 float 모두 허용)
    expired_date : 소멸 처리 기준일 (예: '2026-01-17')  YYYY-MM-DD
    source       : 'callput' / 'combo' / None(=전체)

    Returns
    -------
    처리 예약된 건수 (큐 투입 시점의 open 행 수).
    실제 DB 반영은 비동기이므로 참고용.
    """
    # 큐 투입 전 open 행 수를 미리 읽어 반환값으로 사용
    try:
        conn = get_conn()
        count = _count_open(conn, sym, expiry, right, strike, source)
        conn.close()
    except Exception:
        count = -1

    if count == 0:
        return 0   # 처리할 포지션 없음

    # 스냅샷 캡처 후 큐에 추가
    _args = (sym, expiry, right, strike, expired_date, source)

    def _write():
        try:
            conn = get_conn()
            _expire(conn, *_args)
            conn.close()
        except Exception as e:
            print(f"[trade_log] expire_worthless 오류: {e}")

    _db_write_queue.put(_write)
    return count


def expire_worthless_by_expiry(expired_date: str) -> int:
    """
    특정 만기일에 해당하는 모든 open 포지션을 일괄 소멸 처리.

    앱 시작 시 자동 호출하거나,
    매매일지 탭 '📛 만기소멸 처리' 버튼에서 호출.

    Parameters
    ----------
    expired_date : 처리할 만기일  YYYY-MM-DD 형식
                   (DB의 expiry 컬럼은 YYYYMMDD → 변환 후 비교)

    Returns
    -------
    처리 예약된 open 행 수.
    """
    # YYYY-MM-DD → YYYYMMDD
    expiry_compact = expired_date.replace('-', '')

    try:
        conn = get_conn()
        rows = conn.execute(
            "SELECT DISTINCT source, sym, expiry, right, strike "
            "FROM trades WHERE status='open' AND expiry=?",
            (expiry_compact,)
        ).fetchall()
        count = len(rows)
        conn.close()
    except Exception as e:
        print(f"[trade_log] expire_worthless_by_expiry 조회 오류: {e}")
        return -1

    if count == 0:
        return 0

    def _write():
        try:
            conn = get_conn()
            affected = conn.execute(
                "SELECT id FROM trades WHERE status='open' AND expiry=?",
                (expiry_compact,)
            ).fetchall()
            for row in affected:
                _expire_by_id(conn, row['id'], expired_date)
            conn.commit()
            conn.close()
            print(f"[trade_log] 만기소멸 처리 완료: {len(affected)}건 (만기 {expired_date})")
        except Exception as e:
            print(f"[trade_log] expire_worthless_by_expiry 오류: {e}")

    _db_write_queue.put(_write)
    return count


def get_expired_trades(date: str | None = None) -> list[dict]:
    """
    만기소멸 처리된 포지션 조회.

    Parameters
    ----------
    date : 소멸 처리 기준일 (YYYY-MM-DD). None이면 전체 반환.
    """
    conn = get_conn()
    if date:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='expired' AND close_date=? "
            "ORDER BY close_date, id", (date,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='expired' "
            "ORDER BY close_date, id"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ──────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────────

def _count_open(conn, sym, expiry, right, strike, source) -> int:
    expiry_compact = str(expiry).replace('-', '')
    if source:
        return conn.execute(
            "SELECT COUNT(*) FROM trades "
            "WHERE status='open' AND sym=? AND expiry=? "
            "AND right=? AND strike=? AND source=?",
            (sym, expiry_compact, right, int(float(strike)), source)
        ).fetchone()[0]
    else:
        return conn.execute(
            "SELECT COUNT(*) FROM trades "
            "WHERE status='open' AND sym=? AND expiry=? "
            "AND right=? AND strike=?",
            (sym, expiry_compact, right, int(float(strike)))
        ).fetchone()[0]


def _expire(conn, sym, expiry, right, strike, expired_date, source) -> None:
    """
    특정 종목의 open 포지션을 expired 로 전환.
    매수 포지션 → 전액 손실, 매도(숏) 포지션 → 전액 이익.
    """
    expiry_compact = str(expiry).replace('-', '')
    strike_int = int(float(strike))

    if source:
        open_rows = conn.execute(
            "SELECT id, qty, entry_price, commission FROM trades "
            "WHERE status='open' AND sym=? AND expiry=? "
            "AND right=? AND strike=? AND source=? "
            "ORDER BY open_date ASC",
            (sym, expiry_compact, right, strike_int, source)
        ).fetchall()
    else:
        open_rows = conn.execute(
            "SELECT id, qty, entry_price, commission FROM trades "
            "WHERE status='open' AND sym=? AND expiry=? "
            "AND right=? AND strike=? "
            "ORDER BY open_date ASC",
            (sym, expiry_compact, right, strike_int)
        ).fetchall()

    for row in open_rows:
        _expire_by_id(conn, row['id'], expired_date)

    conn.commit()


def _expire_by_id(conn, trade_id: int, expired_date: str) -> None:
    """
    단일 trades 행을 expired 처리.
    qty > 0  → 롱(매수) 포지션 → 손실
    qty < 0  → 숏(매도) 포지션 → 이익
    """
    row = conn.execute(
        "SELECT qty, entry_price FROM trades WHERE id=?", (trade_id,)
    ).fetchone()
    if not row:
        return

    qty, entry_price = row['qty'], row['entry_price']

    # 롱: qty > 0 → exit_price=0 이므로 손실
    # 숏: qty < 0 → entry_price를 받아놨으므로 이익
    if qty >= 0:
        realized_pnl = round(-entry_price * qty * _MULTIPLIER, 2)
    else:
        realized_pnl = round(entry_price * abs(qty) * _MULTIPLIER, 2)

    conn.execute("""
        UPDATE trades
        SET exit_price  = 0,
            close_date  = ?,
            realized_pnl = ?,
            status      = 'expired'
        WHERE id = ?
    """, (expired_date, realized_pnl, trade_id))


# ──────────────────────────────────────────────────────────────────
# 기존 내부 매칭 로직 (변경 없음)
# ──────────────────────────────────────────────────────────────────

def _match(conn, source, sym, expiry, right, strike) -> None:
    # BAG 수준 체결(strike=0, expiry/right 없음) 매칭 제외 → 쓰레기 데이터 방지
    if not strike or int(float(strike)) == 0 or not expiry or not right:
        return

    key = (source, sym, expiry, right, strike)

    rows = conn.execute("""
        SELECT id, date, action, qty, price, commission
        FROM executions
        WHERE source=? AND sym=? AND expiry=? AND right=? AND strike=?
        ORDER BY id
    """, key).fetchall()

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

            if remaining > 0:
                open_stack.append({
                    "qty": -remaining, "price": price,
                    "date": r["date"], "comm": comm
                })

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
