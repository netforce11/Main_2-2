"""
und_saver.py — get_context() 업그레이드 패치
기존: get_context(exec_time) → {"m5": price, "m20": price}  (5/20분 고정)
수정: get_context(exec_time, minutes=None) → 임의 N분 지원

[변경 부분만 표시 — 기존 und_saver.py 에 아래 내용 적용]
"""

# ── 기존 get_context() 를 아래로 교체 ─────────────────────────────────────

def get_context(exec_time, minutes=None):
    """
    체결 시각 기준 N분 전 기초자산 가격 반환.

    호출 방식:
      get_context(exec_time)            → {"m5": p, "m20": p}  (기존 호환)
      get_context(exec_time, minutes=5) → float | None          (임의 분 지원)
      get_context(exec_time, minutes=30)→ float | None
    """
    from datetime import timedelta
    import sqlite3
    from pathlib import Path

    def _lookup(target_dt):
        """버퍼 → DB 순서로 target_dt 에 가장 가까운 가격 반환"""
        # 1) 인메모리 버퍼 조회
        target_ts = target_dt.timestamp()
        best_price = None
        best_diff  = float("inf")
        for ts, price in _buffer:           # _buffer = deque (und_saver 내부 변수)
            diff = abs(ts - target_ts)
            if diff < best_diff:
                best_diff  = diff
                best_price = price
        if best_price is not None and best_diff <= 120:  # 2분 이내
            return best_price

        # 2) DB 조회
        db_path = Path(r"C:\data\Greeks_history\und_price") / \
                  f"und_{target_dt.strftime('%Y%m%d')}.db"
        if not db_path.exists():
            return None
        try:
            with sqlite3.connect(str(db_path)) as con:
                ts_str = target_dt.strftime("%Y-%m-%d %H:%M:%S")
                # 목표 시각 전후 2분 범위에서 가장 가까운 행
                row = con.execute(
                    """
                    SELECT price FROM und_price
                    WHERE ts <= datetime(?, '+120 seconds')
                      AND ts >= datetime(?, '-120 seconds')
                    ORDER BY ABS(strftime('%s', ts) - strftime('%s', ?))
                    LIMIT 1
                    """,
                    (ts_str, ts_str, ts_str)
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None

    if minutes is not None:
        # 임의 N분 전 단일 조회
        from datetime import timedelta
        target = exec_time - timedelta(minutes=minutes)
        return _lookup(target)
    else:
        # 기존 호환: 5분/20분 딕셔너리 반환
        from datetime import timedelta
        result = {}
        for m in (5, 20):
            target = exec_time - timedelta(minutes=m)
            result[f"m{m}"] = _lookup(target)
        return result
