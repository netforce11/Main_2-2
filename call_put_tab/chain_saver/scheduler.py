"""
chain_saver/scheduler.py — 저장 스케줄러
════════════════════════════════════════
역할:
  - 5초마다: OTM/ITM 스냅샷 요청 → 버퍼 flush → 저장 enqueue
  - 60초마다: 내일 만기 스냅샷 요청
  - 장중(is_market_open)일 때만 저장 실행
  - 사이드바 상태 라벨 업데이트

스냅샷 요청 로직은 snapshot.py 에 분리됨.
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Dict, Tuple

from PyQt5.QtCore import QTimer, QObject

from core_io import is_market_open
from call_put_tab.chain_saver.buffer import ChainBuffer
from call_put_tab.chain_saver.worker import SaveWorker
from call_put_tab.chain_saver import snapshot as snap

log = logging.getLogger(__name__)


class ChainScheduler(QObject):
    def __init__(self, cp, buf: ChainBuffer, worker: SaveWorker,
                 parent=None):
        super().__init__(parent)
        self._cp      = cp
        self._buf     = buf
        self._worker  = worker
        self._status_lbl = None
        self._snap_map: Dict[int, Tuple] = {}
        self._next_map: Dict[int, Tuple] = {}

        self._t5  = QTimer(self); self._t5.setInterval(5_000)
        self._t60 = QTimer(self); self._t60.setInterval(60_000)
        self._t5.timeout.connect(self._on_5s)
        self._t60.timeout.connect(self._on_60s)

    # ── 외부 인터페이스 ──────────────────────────────────────
    def set_status_label(self, lbl):
        self._status_lbl = lbl

    def start(self):
        self._t5.start(); self._t60.start()

    def stop(self):
        self._t5.stop(); self._t60.stop()

    # ── 5초 tick ────────────────────────────────────────────
    def _on_5s(self):
        if not is_market_open():
            self._set_status("pause"); return

        cp  = self._cp
        sym = cp.edit_sym.text().strip().upper() or "SPX"
        und = cp.und_price or 0.0
        self._buf.set_context(sym, und)

        expiry, tag = cp._get_expiry(silent=True)
        if not expiry or und <= 0:
            return

        n_atm = getattr(cp, '_n_strikes', 10)
        snap.request_otm(cp.mw.ib, sym, expiry, tag,
                         und, n_atm, self._snap_map)
        QTimer.singleShot(3_500, self._flush_and_save)

    def _flush_and_save(self):
        rows = self._buf.flush()
        if rows:
            self._worker.enqueue(rows)
            self._set_status("saving", len(rows))

    # ── 60초 tick — 내일 만기 ────────────────────────────────
    def _on_60s(self):
        if not is_market_open():
            return
        cp  = self._cp
        sym = cp.edit_sym.text().strip().upper() or "SPX"
        und = cp.und_price or 0.0
        if und <= 0:
            return
        nxt = snap.request_next(cp.mw.ib, sym, und, self._next_map)
        if nxt:
            QTimer.singleShot(3_000, self._cancel_next)

    def _cancel_next(self):
        snap.cancel_map(self._cp.mw.ib, self._next_map)

    # ── tick 수신 (router 에서 호출) ─────────────────────────
    def on_tick_price(self, req_id: int, tick_type: int, price: float):
        entry = self._snap_map.get(req_id) or self._next_map.get(req_id)
        if not entry:
            return
        expiry, strike, side = entry
        bid = ask = last = None
        if   tick_type == 1: bid  = price
        elif tick_type == 2: ask  = price
        elif tick_type == 4: last = price
        else: return
        self._buf.update_snapshot(expiry, strike, side,
                                  bid=bid, ask=ask, last=last)

    def on_tick_option(self, req_id: int, tick_type: int,
                       iv: float, delta: float, option_price: float,
                       gamma: float, vega: float, theta: float):
        if tick_type not in (10, 11, 12, 13):
            return
        entry = self._snap_map.get(req_id) or self._next_map.get(req_id)
        if not entry:
            return
        expiry, strike, side = entry
        self._buf.update_snapshot(
            expiry, strike, side,
            iv=iv if iv and 0 < iv < 10 else None,
            delta=delta, gamma=gamma, vega=vega, theta=theta)

    # ── 상태 라벨 ────────────────────────────────────────────
    def _set_status(self, state: str, count: int = 0):
        if not self._status_lbl:
            return
        now = datetime.now().strftime("%H:%M:%S")
        if state == "saving":
            txt = f"💾 저장 중  {now}  ({count}건)"
            css = "color:#00e676;font-size:10px;border:none;"
        else:
            txt = "⏸ 장 마감 — 저장 중지"
            css = "color:#555;font-size:10px;border:none;"
        self._status_lbl.setText(txt)
        self._status_lbl.setStyleSheet(css)
