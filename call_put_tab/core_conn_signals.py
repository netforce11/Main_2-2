"""
core_conn_signals.py — 연결 시그널 + 로그  v6.7
════════════════════════════════════════════════
분리 완료 (v6.7):
  core_conn_watchdog.py   — Watchdog + 재연결 + 텔레그램
  core_conn_fill.py       — 체결 콜백 패치 (execDetails + orderStatus)
  core_conn_tick_cache.py — 틱 캐시 + 200ms 배치 UI 갱신 (M-A)

ConnSignalsMixin 역할:
  · 버튼/시그널 연결 (_connect_signals)
  · TickRouter 등록
  · Watchdog / Fill 타이머 초기화
  · 로그 출력 (_log)
════════════════════════════════════════════════
"""

from __future__ import annotations
from collections import deque
from PyQt5.QtCore import QTimer
from core import bridge, router, ts, REQ_UND, REQ_CALL, REQ_PUT

from call_put_tab.core_conn_watchdog   import ConnWatchdogMixin
from call_put_tab.core_conn_fill       import ConnFillMixin
from call_put_tab.core_conn_tick_cache import TickCacheMixin


class ConnSignalsMixin(TickCacheMixin, ConnWatchdogMixin, ConnFillMixin):
    """
    연결 시그널·Watchdog·재연결·체결콜백·로그·틱캐시 통합 Mixin.

    MRO:
      ConnSignalsMixin
        → TickCacheMixin    (틱 캐시 + 200ms UI flush)
        → ConnWatchdogMixin (Watchdog + 재연결 + TG)
        → ConnFillMixin     (execDetails + orderStatus 패치)
    """

    def _connect_signals(self):
        # ── 버튼 시그널 ─────────────────────────────────────────
        self.btn_conn.clicked.connect(self.mw.connect_ibkr)
        self.btn_disc.clicked.connect(self.mw.disconnect_ibkr)
        self.btn_fetch.clicked.connect(self._fetch)
        bridge.connected.connect(self._on_connected)
        bridge.error_sig.connect(self._on_error)

        # ── TickRouter (26개: REQ_*+0 ~ REQ_*+25) ───────────────
        _MAX_IDX = 25
        router.register_price(REQ_UND,  REQ_UND,              self._on_tick_price)
        router.register_price(REQ_CALL, REQ_CALL + _MAX_IDX,  self._on_tick_price)
        router.register_price(REQ_PUT,  REQ_PUT  + _MAX_IDX,  self._on_tick_price)
        router.register_option(REQ_CALL, REQ_CALL + _MAX_IDX, self._on_tick_option)
        router.register_option(REQ_PUT,  REQ_PUT  + _MAX_IDX, self._on_tick_option)
        self._watch_timer.start()

        # ── 미체결 시그널 ────────────────────────────────────────
        bridge.open_order_sig.connect(self._on_bridge_open_order)

        # ── 상태 플래그 초기화 ──────────────────────────────────
        self._last_tick_time  = None
        self._mdt_verify_mode = False
        self._exec_id_cache   = deque(maxlen=20)
        self._reconnecting    = False
        self._tg_stale_sent   = False
        self._order_fill_cache   = set()
        self._fill_hooks_applied = False

        # ── [M-A] 틱 캐시 + 200ms UI flush 타이머 초기화 ────────
        self._init_tick_cache()

        # ── Watchdog 타이머 (3초) ────────────────────────────────
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(3000)
        self._watchdog_timer.timeout.connect(self._watch_dog)
        self._watchdog_timer.start()

        # ── 체결 콜백 패치 (연결 후 1초 — 즉시 체결 놓치지 않도록) ─
        QTimer.singleShot(1000, self._hook_fill_callbacks)

    def _log(self, msg: str):
        """UI 로그 창에 타임스탬프 포함 출력. 200줄 초과 시 150줄로 자름."""
        self.log.append(f"[{ts()}] {msg}")
        lines = self.log.toPlainText().split("\n")
        if len(lines) > 200:
            self.log.setPlainText("\n".join(lines[-150:]))

    def on_tab_activate(self):
        """탭 활성화 → UI flush 타이머 재시작."""
        self.resume_tick_ui_flush()
        if hasattr(super(), 'on_tab_activate'):
            super().on_tab_activate()

    def on_tab_deactivate(self):
        """탭 비활성화 → UI flush 타이머 중지 (CPU 절약)."""
        self.pause_tick_ui_flush()
        if hasattr(super(), 'on_tab_deactivate'):
            super().on_tab_deactivate()
