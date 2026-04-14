"""
chain_saver/worker.py — 비동기 저장 스레드
════════════════════════════════════════
역할:
  - Queue 로 row 리스트를 받아 SQLite INSERT
  - 메인(UI) 스레드와 완전 분리 → 저장 중 UI 프리즈 없음
  - 일별 DB 자동 교체 (자정 넘어가면 새 파일)

사용법:
  worker = SaveWorker()
  worker.start()
  worker.enqueue(rows)   # 메인 스레드에서 호출
  worker.stop()          # 앱 종료 시
"""
from __future__ import annotations
import queue
import threading
import logging
from datetime import date
from typing import List

from call_put_tab.chain_saver.db import open_db, insert_rows

log = logging.getLogger(__name__)

_SENTINEL = None   # stop 신호


class SaveWorker:
    def __init__(self):
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._day     = date.today().strftime("%Y%m%d")
        self._conn    = open_db(self._day)
        self._running = False

    # ── 외부 인터페이스 ──────────────────────────────────────
    def start(self):
        self._running = True
        self._thread.start()
        log.info("[SaveWorker] 저장 스레드 시작")

    def stop(self):
        """앱 종료 시 호출 — 큐 소진 후 종료."""
        self._q.put(_SENTINEL)
        self._thread.join(timeout=5)
        if self._conn:
            self._conn.close()
        log.info("[SaveWorker] 저장 스레드 종료")

    def enqueue(self, rows: List[dict]):
        """
        메인 스레드에서 호출.
        rows = buffer.flush() 결과물.
        큐가 꽉 차면 경고 후 스킵 (UI 블로킹 방지).
        """
        if not rows:
            return
        try:
            self._q.put_nowait(rows)
        except queue.Full:
            log.warning("[SaveWorker] 큐 포화 — rows %d건 스킵", len(rows))

    @property
    def queue_size(self) -> int:
        return self._q.qsize()

    # ── 내부 루프 ────────────────────────────────────────────
    def _run(self):
        while True:
            try:
                rows = self._q.get(timeout=1)
            except queue.Empty:
                continue

            if rows is _SENTINEL:
                break

            # 자정 넘어가면 DB 교체
            today = date.today().strftime("%Y%m%d")
            if today != self._day:
                self._conn.close()
                self._day  = today
                self._conn = open_db(self._day)
                log.info("[SaveWorker] DB 교체 → %s", self._day)

            cnt = insert_rows(self._conn, rows)
            log.debug("[SaveWorker] INSERT %d rows", cnt)
