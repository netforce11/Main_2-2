"""
core_conn_tick_cache.py — 틱 수신 캐시 + 200ms UI 배치 갱신  v1.2
════════════════════════════════════════════════════════════════
[M-A]  틱 → _price_cache 저장 → 200ms 배치 UI 갱신 (freeze 방지)
[v1.1] price_tick_sig 구독 방식으로 전환 (ib.tickPrice 오버라이드 제거)
[v1.2] sleep_order 즉시 트리거 + _chain_call/_chain_put 실시간 갱신 이식
  · _on_tick_price 에 _notify_sleep_watcher() 즉시 호출 추가
  · _flush_one_req 에 _flush_chain_price() 호출 추가
  · 모듈 함수 3개 추가:
      _notify_sleep_watcher  — watcher.on_price_update() 트리거
      _flush_chain_price     — 200ms flush 시 combo_tab 체인 갱신
      _patch_chain_price     — reqId 1개 O(1) 갱신 (_price_cache 직접 참조)
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from datetime import datetime
from PyQt5.QtCore import QTimer
from core import REQ_UND, REQ_CALL, REQ_PUT

try:
    from combo_libs.bridge_price_tick import subscribe as _tick_subscribe
    from combo_libs.bridge_price_tick import unsubscribe as _tick_unsubscribe
    _HAS_ROUTER = True
except ImportError:
    _HAS_ROUTER = False
    def _tick_subscribe(cb, req_ids=None): pass
    def _tick_unsubscribe(cb): pass

# [v1.2] sleep_order 연동 함수 분리 모듈
try:
    from core_conn_tick_cache_sleep import (
        _notify_sleep_watcher, _flush_chain_price, _patch_chain_price)
except ImportError:
    def _notify_sleep_watcher(cp, r): pass
    def _flush_chain_price(cp, r): pass
    def _patch_chain_price(ct, cp, r): pass

_UI_FLUSH_INTERVAL_MS = 200

_TT_TO_COL = {1: 1, 2: 2, 4: 3}   # Bid / Ask / Last


class TickCacheMixin:
    """틱 수신 캐시 + 200ms 배치 UI 갱신 Mixin."""

    def _init_tick_cache(self):
        self._price_cache:   dict[int, dict[int, float]] = {}
        self._option_cache:  dict[int, dict[str, float]] = {}
        self._dirty_req_ids: set[int] = set()

        self._ui_flush_timer = QTimer(self)
        self._ui_flush_timer.setInterval(_UI_FLUSH_INTERVAL_MS)
        self._ui_flush_timer.timeout.connect(self._flush_tick_ui)
        self._ui_flush_timer.start()

        # [v1.1] price_tick_sig 전체 구독
        _tick_unsubscribe(self._on_tick_price)
        _tick_subscribe(self._on_tick_price)

    # ── 틱 수신 ─────────────────────────────────────────────────
    def _on_tick_price(self, reqId: int, tickType: int,
                       price: float, attrib=None):
        self._last_tick_time = datetime.now()

        if reqId not in self._price_cache:
            self._price_cache[reqId] = {}
        self._price_cache[reqId][tickType] = price

        if reqId != REQ_UND:
            self._dirty_req_ids.add(reqId)

        if getattr(self, '_mdt_verify_mode', False) and reqId == REQ_UND:
            self._mdt_verify_mode = False
            is_live = tickType < 66
            if getattr(self, '_requested_live', False) and not is_live:
                self._log("⚠ 실시간 시세 권한 없음 — 지연 데이터 수신 중.")
                self.lbl_status.setText("● 권한 없음(지연)")
                self.lbl_status.setStyleSheet(
                    "color:#ff9800;font-weight:bold;border:none;")
            elif is_live:
                self._log("✅ 실시간 시세 정상 수신")

        if reqId == REQ_UND:
            super()._on_tick_price(reqId, tickType, price, attrib)
            return

        # [v1.2] sleep_order 즉시 스캔 트리거
        _notify_sleep_watcher(self, reqId)

    def _on_tick_option(self, reqId: int, tickType: int,
                        impliedVol: float, delta: float,
                        optPrice: float, pvDividend: float,
                        gamma: float, vega: float,
                        theta: float, undPrice: float):
        if reqId not in self._option_cache:
            self._option_cache[reqId] = {}
        c = self._option_cache[reqId]
        c.update(iv=impliedVol, delta=delta, gamma=gamma,
                 theta=theta, vega=vega,
                 optPrice=optPrice, undPrice=undPrice)
        self._dirty_req_ids.add(reqId)
        # [v1.2] Greeks 갱신도 즉시 트리거
        _notify_sleep_watcher(self, reqId)

    # ── 200ms 배치 UI 갱신 ──────────────────────────────────────
    def _flush_tick_ui(self):
        if not self._dirty_req_ids:
            return
        dirty_snap = self._dirty_req_ids.copy()
        self._dirty_req_ids.clear()
        for req_id in dirty_snap:
            self._flush_one_req(req_id)

    def _flush_one_req(self, req_id: int):
        price_ticks  = self._price_cache.get(req_id, {})
        option_ticks = self._option_cache.get(req_id, {})
        if not price_ticks and not option_ticks:
            return

        if REQ_CALL <= req_id <= REQ_CALL + 25:
            tbl = getattr(self, 'tbl_call', None)
            row = req_id - REQ_CALL
        elif REQ_PUT <= req_id <= REQ_PUT + 25:
            tbl = getattr(self, 'tbl_put', None)
            row = req_id - REQ_PUT
        else:
            self._apply_tick_price_direct(req_id, price_ticks)
            return

        if tbl is None or row < 0 or row >= tbl.rowCount():
            return

        for tt, col in _TT_TO_COL.items():
            price = price_ticks.get(tt)
            if price is not None and price > 0:
                self._set_cell_price(tbl, row, col, price, req_id, tt)

        if option_ticks:
            self._apply_greeks_to_row(tbl, row, option_ticks, req_id)

        if req_id == getattr(self, '_pp_opt_req_id', None):
            self._refresh_opt_panel_from_cache(req_id)

        # [v1.2] 200ms flush 시 combo_tab 체인도 갱신
        _flush_chain_price(self, req_id)

    def _set_cell_price(self, tbl, row: int, col: int,
                        price: float, req_id: int, tt: int):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush
        item = tbl.item(row, col)
        new_text = f"{price:.2f}"
        if item and item.text() == new_text:
            return
        _COLOR = {1: "#33aaff", 2: "#ffaa33", 4: "#ffffff"}
        new_item = QTableWidgetItem(new_text)
        new_item.setForeground(QBrush(QColor(_COLOR.get(tt, "#cccccc"))))
        tbl.setItem(row, col, new_item)
        _tt_key = {1: 'bid', 2: 'ask', 4: 'last'}
        key = _tt_key.get(tt)
        if key:
            data_dict = (self.call_data if tbl is getattr(self, 'tbl_call', None)
                         else self.put_data)
            if req_id in data_dict:
                data_dict[req_id][key] = price

    def _apply_greeks_to_row(self, tbl, row: int,
                              cache: dict, req_id: int):
        data_dict = (self.call_data if tbl is getattr(self, 'tbl_call', None)
                     else self.put_data)
        if req_id in data_dict:
            for field in ('iv', 'delta', 'gamma', 'theta', 'vega'):
                val = cache.get(field)
                if val is not None:
                    data_dict[req_id][field] = val

    def _apply_tick_price_direct(self, req_id: int, price_ticks: dict):
        for tt, price in price_ticks.items():
            try:
                super()._on_tick_price(req_id, tt, price)
            except Exception:
                pass

    def _refresh_opt_panel_from_cache(self, req_id: int):
        if getattr(self, '_pp_mode', '') != 'opt':
            return
        ticks = self._price_cache.get(req_id, {})
        bid = ticks.get(1, 0); ask = ticks.get(2, 0)
        if bid > 0 and ask > 0 and hasattr(self, '_pp_set_quote'):
            self._pp_set_quote(bid, ask)

    def get_cached_price(self, req_id: int, tick_type: int) -> float | None:
        return self._price_cache.get(req_id, {}).get(tick_type)

    def get_cached_greek(self, req_id: int, field: str) -> float | None:
        return self._option_cache.get(req_id, {}).get(field)

    def pause_tick_ui_flush(self):
        if hasattr(self, '_ui_flush_timer'):
            self._ui_flush_timer.stop()

    def resume_tick_ui_flush(self):
        if hasattr(self, '_ui_flush_timer'):
            self._ui_flush_timer.start()


# ── [v1.2] sleep_order 즉시 스캔 연동 모듈 함수 ────────────────

