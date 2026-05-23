"""
combo_ui_leg_stream.py — Mid-price 실시간 스트리밍 로직
──────────────────────────────────────────────────────
combo_ui_leg_panel.py 에서 분리.
포함:
  fill_premium_from_market — conId → reqMktData → Mid price → 프리미엄 셀
  _cancel_stream           — 단일 레그 스트림 해제
  cancel_all_streams       — 전체 스트림 일괄 해제
  _set_premium_cell        — 프리미엄 셀 안전 설정

v2.1 변경:
  - ★ fill_premium_from_market: 레그 테이블에서 symbol/right/strike/expiry 읽어
    호가 구독 시점에 combo_order_bag._CONID_CACHE 에 즉시 저장
    → 주문 전 증거금 조회(BAG whatIf)가 첫 조회부터 서버 방식 사용 가능
"""

from PyQt5.QtWidgets import QTableWidgetItem

_TICKER_BASE = 8800


def _cache_conid_from_row(self, row: int, con_id: int):
    """
    레그 테이블 row에서 symbol/right/strike/expiry를 읽어
    combo_order_bag._CONID_CACHE에 저장.
    실패 시 조용히 무시 (캐시는 선택적 최적화이므로).
    """
    try:
        from combo_order_bag import _CONID_CACHE, _conid_key, _save_conid_cache
        from combo_order_utils import _parse_expiry_display

        def _cell(c):
            it = self.tbl_legs.item(row, c)
            return it.text().strip() if it else ""

        cp     = _cell(2).upper()   # 열2: C/P
        strike = _cell(3)           # 열3: 행사가
        expiry = _cell(6)           # 열6: 만기

        if not cp or not strike or not expiry:
            return
        try:
            strike_f = float(strike)
        except ValueError:
            return

        raw_expiry = _parse_expiry_display(expiry)
        if not raw_expiry:
            return

        # symbol: edit_sym_combo 위젯 → 없으면 "SPX" 기본값
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = sym_w.text().strip().upper() if sym_w else "SPX"
        symbol = symbol.replace("SPXW", "SPX")   # BAG용 심볼 통일

        key = _conid_key(symbol, cp, strike_f, raw_expiry)
        if _CONID_CACHE.get(key) != con_id:
            _CONID_CACHE[key] = con_id
            _save_conid_cache()
    except Exception:
        pass   # 캐시 저장 실패는 무시


def fill_premium_from_market(self, row: int, con_id: int):
    """
    행사가 입력 직후 호출.
    router.register_price() → bridge.tick_price → Mid price → 프리미엄 셀 자동 입력.
    ★ conId를 _CONID_CACHE에 즉시 저장 → 증거금 조회 시 BAG whatIf 서버 방식 사용 가능.
    """
    from core import router

    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ib is None or con_id <= 0:
        return

    if not hasattr(self, '_mid_ticks'):
        self._mid_ticks = {}
    if not hasattr(self, '_stream_conids'):
        self._stream_conids = {}
    if not hasattr(self, '_stream_slots'):
        self._stream_slots = {}

    ticker_id = _TICKER_BASE + row
    _cancel_stream(self, ticker_id)

    self._mid_ticks[ticker_id]     = {}
    self._stream_conids[ticker_id] = con_id

    # ★ conId 캐시 저장 (레그 테이블에서 심볼·CP·행사가·만기 읽기)
    _cache_conid_from_row(self, row, con_id)

    def _on_tick(req_id: int, tick_type: int, price: float):
        if self._stream_conids.get(ticker_id) != con_id:
            return
        if tick_type in (1, 2) and price > 0:
            self._mid_ticks[ticker_id][tick_type] = price
            bid = self._mid_ticks[ticker_id].get(1)
            ask = self._mid_ticks[ticker_id].get(2)
            if bid and ask:
                mid = round((bid + ask) / 2, 2)
                _set_premium_cell(self, row, mid)

    router.register_price(ticker_id, ticker_id, _on_tick)
    self._stream_slots[ticker_id] = _on_tick

    try:
        from ibapi.contract import Contract as IbContract
        from combo_order_bag import _get_selected_exchange as _gse
        c = IbContract()
        c.conId    = con_id
        c.exchange = _gse(self)
        ib.reqMktData(ticker_id, c, "", False, False, [])
        self._log(
            f"📡 레그{row+1} 실시간 호가 구독 시작 "
            f"(conId={con_id}, tid={ticker_id})")
    except Exception as e:
        router.unregister_price(_on_tick)
        self._stream_slots.pop(ticker_id, None)
        self._log(f"❌ reqMktData 레그{row+1}: {e}")


def _cancel_stream(self, ticker_id: int):
    """단일 레그 스트림 해제 (router 슬롯 포함)."""
    from core import router
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ticker_id in getattr(self, '_stream_conids', {}):
        if ib:
            try:
                ib.cancelMktData(ticker_id)
            except Exception:
                pass
        slot = getattr(self, '_stream_slots', {}).pop(ticker_id, None)
        if slot:
            router.unregister_price(slot)
        self._stream_conids.pop(ticker_id, None)
        self._mid_ticks.pop(ticker_id, None)


def cancel_all_streams(self):
    """전략 변경·초기화 시 모든 실시간 스트림 일괄 해제."""
    from core import router
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    for tid in list(getattr(self, '_stream_conids', {}).keys()):
        if ib:
            try:
                ib.cancelMktData(tid)
            except Exception:
                pass
        slot = getattr(self, '_stream_slots', {}).pop(tid, None)
        if slot:
            router.unregister_price(slot)
    self._stream_conids = {}
    self._stream_slots  = {}
    self._mid_ticks     = {}
    self._log("📡 전체 호가 스트림 해제")


def _set_premium_cell(self, row: int, value: float):
    """프리미엄 셀을 재귀 없이 안전하게 설정 후 Net Price 갱신."""
    from combo_ui_leg_panel import _recalc_net_price
    self._leg_item_changing = True
    try:
        it = self.tbl_legs.item(row, 4)
        if it is None:
            it = QTableWidgetItem()
            self.tbl_legs.setItem(row, 4, it)
        it.setText(str(value))
    finally:
        self._leg_item_changing = False
    _recalc_net_price(self)