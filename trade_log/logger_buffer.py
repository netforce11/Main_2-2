"""
trade_log/logger_buffer.py — 로그/시세 기록 버퍼  v1.0
════════════════════════════════════════════════════════
[M-B] 로그 버퍼링 — 1분 or 10개 단위 flush

문제:
  alert_logger.py, und_saver.py 등이 매 이벤트마다
  파일/DB를 open→write→close → 장중 디스크 I/O 부하 급증

해결:
  LogLineBuffer: 텍스트 로그 줄을 deque에 모아 flush
    · 10개 쌓이면 즉시 flush
    · 1분 경과하면 flush (빈 버퍼도 타이머로 처리)
    · 앱 종료 시 flush_all()로 잔여 기록 보장

사용:
  from trade_log.logger_buffer import LogLineBuffer

  _alert_buf = LogLineBuffer(
      path_fn=lambda: Path("/home/.../Greeks_history") / f"alert_{today}.log",
      max_count=10,
      max_seconds=60,
  )
  _alert_buf.push(f"2026-05-10 14:23:05 [LV3] SPX -18.0P | 풋옵션 급등\n")
════════════════════════════════════════════════════════
"""

from __future__ import annotations
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable


class LogLineBuffer:
    """
    텍스트 줄을 버퍼에 모아 일괄 flush하는 범용 버퍼.

    Args:
        path_fn      : flush 시점에 호출되어 파일 경로를 반환하는 callable.
                       날짜가 바뀌어도 항상 올바른 파일을 가리킬 수 있음.
        max_count    : 버퍼가 이 개수에 도달하면 즉시 flush (기본 10)
        max_seconds  : 마지막 flush 후 이 초가 지나면 flush (기본 60초 = 1분)
        encoding     : 파일 인코딩 (기본 utf-8)
    """

    def __init__(
        self,
        path_fn: Callable[[], Path],
        max_count:   int = 10,
        max_seconds: int = 60,
        encoding:    str = "utf-8",
    ):
        self._path_fn     = path_fn
        self._max_count   = max_count
        self._max_seconds = max_seconds
        self._encoding    = encoding

        self._buf:       deque[str] = deque()
        self._lock:      threading.Lock = threading.Lock()
        self._last_flush: float = time.monotonic()

        # 백그라운드 타이머 스레드 (max_seconds 주기 flush)
        self._running = True
        self._timer_thread = threading.Thread(
            target=self._timer_loop, daemon=True,
            name=f"LogLineBuf-{id(self)}")
        self._timer_thread.start()

    # ── 공개 API ──────────────────────────────────────────────
    def push(self, line: str) -> None:
        """
        버퍼에 한 줄 추가.
        max_count 도달 시 즉시 flush.
        """
        with self._lock:
            self._buf.append(line)
            if len(self._buf) >= self._max_count:
                self._flush_locked()

    def flush_all(self) -> None:
        """잔여 버퍼를 즉시 파일에 기록. 앱 종료 시 반드시 호출."""
        with self._lock:
            if self._buf:
                self._flush_locked()

    def stop(self) -> None:
        """타이머 스레드 종료 + 잔여 flush."""
        self._running = False
        self.flush_all()

    # ── 내부 ──────────────────────────────────────────────────
    def _flush_locked(self) -> None:
        """_lock 보유 상태에서 호출. 버퍼 내용을 파일에 일괄 기록."""
        if not self._buf:
            return
        lines = list(self._buf)
        self._buf.clear()
        self._last_flush = time.monotonic()

        # 파일 기록은 락 밖에서 해도 되지만,
        # 여기서는 단순성을 위해 락 안에서 수행
        try:
            path: Path = self._path_fn()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding=self._encoding) as f:
                f.writelines(lines)
        except OSError as e:
            print(f"[LogLineBuffer] 파일 기록 실패: {e}")

    def _timer_loop(self) -> None:
        """백그라운드에서 max_seconds마다 flush."""
        while self._running:
            time.sleep(1)
            elapsed = time.monotonic() - self._last_flush
            if elapsed >= self._max_seconds:
                with self._lock:
                    if self._buf:
                        self._flush_locked()
