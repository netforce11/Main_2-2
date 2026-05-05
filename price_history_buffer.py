"""
price_history_buffer.py — 기초자산 가격 히스토리 버퍼

콜-풋탭이 und_price를 수신할 때마다 push()를 호출하고,
AlertEngine이 get_change(10/20/30)으로 N분 전 대비 변화를 읽는다.

사용법:
    # main.py TradingDashboard.__init__ 에서
    from price_history_buffer import PriceHistoryBuffer
    self.price_history = PriceHistoryBuffer()

    # 콜-풋탭 _update_und_display() 에서 (쓰기, 1분 1회 자동 제한)
    if hasattr(self, 'mw') and hasattr(self.mw, 'price_history'):
        self.mw.price_history.push(price)

    # AlertEngine 에서 (읽기)
    change_10 = mw.price_history.get_change(10)  # 10분 전 대비
    change_20 = mw.price_history.get_change(20)
    change_30 = mw.price_history.get_change(30)

    # 앱 재시작 시 greeks_db에서 복원
    mw.price_history.restore_from_db(rows)  # rows: [{'ts': ..., 'und_price': ...}, ...]
"""

import time
import threading
from collections import deque
from typing import Optional, List


class PriceHistoryBuffer:
    """
    기초자산 가격 1분 단위 스냅샷 버퍼.

    - push()는 틱마다 호출해도 안전. 1분에 1번만 실제로 저장.
    - 최대 60분치 보관 (deque maxlen=60).
    - get_change(n): 현재가 - n분 전 가격 반환.
    - get_price_n_minutes_ago(n): n분 전 가격만 반환.
    """

    MAX_MINUTES = 60   # 최대 보관 분 수

    def __init__(self):
        # [(unix_timestamp, price), ...]  1분 단위, 최대 60개
        self._buf: deque = deque(maxlen=self.MAX_MINUTES)
        self._lock = threading.Lock()
        self._last_push_min: int = -1   # 마지막으로 저장한 분(minute 단위 정수)

    # ── 쓰기 ────────────────────────────────────────────────────
    def push(self, price: float):
        """
        현재가를 받아 1분에 1번만 버퍼에 저장.
        틱마다 호출해도 중복 저장 없음.
        """
        if price is None or price <= 0:
            return
        current_min = int(time.time() // 60)
        with self._lock:
            if current_min != self._last_push_min:
                self._buf.append((time.time(), float(price)))
                self._last_push_min = current_min

    def push_forced(self, price: float, ts: Optional[float] = None):
        """
        강제 저장 (복원 시 사용). 중복 체크 없이 그대로 추가.
        ts가 None이면 현재 시각 사용.
        """
        if price is None or price <= 0:
            return
        with self._lock:
            self._buf.append((ts or time.time(), float(price)))

    # ── 읽기 ────────────────────────────────────────────────────
    def current_price(self) -> Optional[float]:
        """가장 최근 저장된 가격."""
        with self._lock:
            if not self._buf:
                return None
            return self._buf[-1][1]

    def get_price_n_minutes_ago(self, n: int) -> Optional[float]:
        """
        n분 전에 가장 가까운 가격 반환.
        버퍼가 비어있거나 n분치 데이터가 없으면 None.
        """
        target_ts = time.time() - (n * 60)
        with self._lock:
            if not self._buf:
                return None
            # target_ts에 가장 가까운 항목 탐색
            closest = min(self._buf, key=lambda x: abs(x[0] - target_ts))
            # n분보다 2분 이상 벗어난 데이터는 신뢰하지 않음
            if abs(closest[0] - target_ts) > (n + 2) * 60:
                return None
            return closest[1]

    def get_change(self, n: int) -> Optional[float]:
        """
        현재가 - n분 전 가격.
        데이터 부족 시 None 반환.

        예) get_change(10) → +5.25  (10분 전보다 5.25 상승)
        """
        current = self.current_price()
        past    = self.get_price_n_minutes_ago(n)
        if current is None or past is None:
            return None
        return current - past

    def get_change_pct(self, n: int) -> Optional[float]:
        """
        (현재가 - n분 전 가격) / n분 전 가격 × 100 (%)
        """
        current = self.current_price()
        past    = self.get_price_n_minutes_ago(n)
        if current is None or past is None or past == 0:
            return None
        return (current - past) / past * 100

    def get_summary(self) -> dict:
        """
        10/20/30분 전 변화 요약. AlertEngine에서 한번에 읽을 때 사용.

        반환: {
            'current': float | None,
            'change_10': float | None,
            'change_20': float | None,
            'change_30': float | None,
            'pct_10': float | None,
            'pct_20': float | None,
            'pct_30': float | None,
        }
        """
        return {
            'current':   self.current_price(),
            'change_10': self.get_change(10),
            'change_20': self.get_change(20),
            'change_30': self.get_change(30),
            'pct_10':    self.get_change_pct(10),
            'pct_20':    self.get_change_pct(20),
            'pct_30':    self.get_change_pct(30),
        }

    # ── 복원 ────────────────────────────────────────────────────
    def restore_from_db(self, rows: List[dict]):
        """
        앱 재시작 시 greeks_db에서 과거 60분치 복원.

        rows 형식: [{'ts': '2026-05-05 09:30:00', 'und_price': 5500.0}, ...]
        또는:      [{'ts': 1746400000.0,          'und_price': 5500.0}, ...]

        ts는 문자열(ET 기준 YYYY-MM-DD HH:MM:SS) 또는 unix timestamp 모두 허용.
        """
        from datetime import datetime, timezone, timedelta

        parsed = []
        for row in rows:
            try:
                ts_raw    = row.get('ts')
                und_price = row.get('und_price')
                if und_price is None or und_price <= 0:
                    continue

                # ts 파싱
                if isinstance(ts_raw, (int, float)):
                    ts = float(ts_raw)
                elif isinstance(ts_raw, str):
                    # ET 기준 문자열 → unix timestamp
                    dt = datetime.strptime(ts_raw, '%Y-%m-%d %H:%M:%S')
                    # ET = UTC-4 (DST) 또는 UTC-5 (표준시) → 근사값 UTC-4 사용
                    dt_utc = dt + timedelta(hours=4)
                    ts = dt_utc.replace(tzinfo=timezone.utc).timestamp()
                else:
                    continue

                parsed.append((ts, float(und_price)))
            except Exception:
                continue

        # 시간순 정렬 후 1분 단위로 decimation
        parsed.sort(key=lambda x: x[0])
        last_min = -1
        with self._lock:
            self._buf.clear()
            for ts, price in parsed:
                minute = int(ts // 60)
                if minute != last_min:
                    self._buf.append((ts, price))
                    last_min = minute

    # ── 관리 ────────────────────────────────────────────────────
    def clear(self):
        """버퍼 초기화."""
        with self._lock:
            self._buf.clear()
            self._last_push_min = -1

    def size(self) -> int:
        """저장된 항목 수."""
        with self._lock:
            return len(self._buf)

    def __repr__(self):
        current = self.current_price()
        return (f"<PriceHistoryBuffer size={self.size()} "
                f"current={current}>")
