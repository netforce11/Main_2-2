"""
trade_log/logger.py — 체결/주문 DB 저장  v1.2

[v1.2 수정] SQLite DB locked 방지
  - GUI 스레드와 시세 스레드가 동시에 DB에 쓰면 "database is locked" 에러 발생
  - 해결: _db_write_queue (Queue) + 전용 단일 스레드(_db_worker)로 모든 쓰기 직렬화
  - log_exec / log_order / log_commission 은 Queue에 작업 추가만 수행 (논블로킹)
  - 앱 종료 시 _flush_db_queue()로 잔여 작업 처리
"""

from __future__ import annotations
import queue
import threading
from datetime import datetime, timezone, timedelta
from .db import get_conn

_ET = timezone(timedelta(hours=-5))

# ── [v1.2] 쓰기 전용 단일 스레드 큐 ─────────────────────────
_db_write_queue: queue.Queue = queue.Queue()
_db_worker_thread: threading.Thread | None = None
_db_worker_running = False


def _db_worker():
    """DB 쓰기 전용 스레드 — 큐에서 작업을 꺼내 순차 실행."""
    while _db_worker_running or not _db_write_queue.empty():
        try:
            fn = _db_write_queue.get(timeout=0.5)
            try:
                fn()
            except Exception as e:
                print(f"[trade_log] DB 쓰기 오류: {e}")
            finally:
                _db_write_queue.task_done()
        except queue.Empty:
            continue


def start_db_worker():
    """앱 시작 시 호출하여 DB 쓰기 스레드를 가동."""
    global _db_worker_thread, _db_worker_running
    if _db_worker_thread and _db_worker_thread.is_alive():
        return
    _db_worker_running = True
    _db_worker_thread = threading.Thread(
        target=_db_worker, daemon=True, name="trade_log_db_worker")
    _db_worker_thread.start()


def flush_db_queue():
    """앱 종료 시 호출 — 큐에 남은 모든 쓰기 작업을 완료 후 반환."""
    global _db_worker_running
    _db_worker_running = False
    _db_write_queue.join()


# 워커 자동 시작 (import 시 즉시)
start_db_worker()


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
    strategy:   str   = "",
    und_ctx:    dict  = None,
) -> None:
    """체결 1건 → executions INSERT (큐에 추가, 논블로킹)."""
    ts, date = _et_now()
    ctx = und_ctx or {}
    # 인자 스냅샷을 클로저로 캡처
    _args = (ts, date, oid, source, sym, expiry, right,
             int(strike) if strike else 0,
             action, strategy or None, qty, price, commission,
             ctx.get("und_price"), ctx.get("und_5m"), ctx.get("und_10m"),
             ctx.get("chg_5m"),    ctx.get("chg_10m"))

    def _write():
        try:
            conn = get_conn()
            conn.execute("""
                INSERT INTO executions
                  (ts, date, oid, source, sym, expiry, right, strike,
                   action, strategy, qty, price, commission,
                   und_price, und_5m, und_10m, chg_5m, chg_10m)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, _args)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[trade_log] executions INSERT 오류: {e}")

    _db_write_queue.put(_write)


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
    """주문 접수/상태변경 1건 → order_log INSERT (큐에 추가, 논블로킹)."""
    ts, date = _et_now()
    _args = (ts, date, oid, source, sym, expiry, right,
             int(strike) if strike else 0,
             action, qty, price, order_type, status, und_price)

    def _write():
        try:
            conn = get_conn()
            conn.execute("""
                INSERT INTO order_log
                  (ts, date, oid, source, sym, expiry, right, strike,
                   action, qty, price, order_type, status, und_price)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, _args)
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[trade_log] order_log INSERT 오류: {e}")

    _db_write_queue.put(_write)


def log_commission(oid: int, commission: float) -> None:
    """CommissionReport 콜백 → executions 수수료 갱신 (큐에 추가, 논블로킹)."""
    def _write():
        try:
            conn = get_conn()
            conn.execute(
                "UPDATE executions SET commission=? WHERE oid=?",
                (commission, oid))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[trade_log] commission 갱신 오류: {e}")

    _db_write_queue.put(_write)