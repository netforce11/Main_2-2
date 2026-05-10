"""
core_conn_tick_cache.py — 틱 수신 캐시 + 200ms UI 배치 갱신  v1.1
════════════════════════════════════════════════════════════════
[M-A] UI 갱신 병목 해소
[v1.1 L-A] price_tick_sig 구독 방식으로 전환
  · ib.tickPrice 직접 오버라이드 제거
  · _init_tick_cache()에서 bridge_price_tick.subscribe() 로 등록
  · 재연결 시 unsubscribe → subscribe 재등록
════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from datetime import datetime
from PyQt5.QtCore import QTimer
from core import REQ_UND, REQ_CALL, REQ_PUT

try:
    from call_put_tab.bridge_price_tick import subscribe as _tick_subscribe
    from call_put_tab.bridge_price_tick import unsubscribe as _tick_unsubscribe
    _HAS_ROUTER = True
except ImportError:
    _HAS_ROUTER = False
    def _tick_subscribe(cb, req_ids=None): pass
    def _tick_unsubscribe(cb): pass

_UI_FLUSH_INTERVAL_MS = 200

_TT_TO_COL = {
    1: 1,   # Bid
    2: 2,   # Ask
    4: 3,   # Last
}


class TickCacheMixin:
    """
    틱 수신 캐시 + 200ms 배치 UI 갱신 Mixin.
    [v1.1] ib.tickPrice 오버라이드 없이 price_tick_sig 구독으로 동작.
    """

    def _init_tick_cache(self):
        """
        _connect_signals() 내에서 호출.
        캐시 딕셔너리, UI flush 타이머, price_tick_sig 구독 초기화.
        """
        self._price_cache:   dict[int, dict[int, float]] = {}
        self._option_cache:  dict[int, dict[str, float]] = {}
        self._dirty_req_ids: set[int] = set()

        self._ui_flush_timer = QTimer(self)
        self._ui_flush_timer.setInterval(_UI_FLUSH_INTERVAL_MS)
        self._ui_flush_timer.timeout.connect(self._flush_tick_ui)
        self._ui_flush_timer.start()

        # [v1.1 L-A] price_tick_sig 전체 구독 (reqId 필터 없음 = 전체 수신)
        # 재연결 시 중복 구독 방지: 먼저 해제 후 재등록
        _tick_unsubscribe(self._on_tick_price)
        _tick_subscribe(self._on_tick_price)

    # ── 틱 수신 — 캐시만 갱신 ──────────────────────────────────
    def _on_tick_price(self, reqId: int, tickType: int, price: float, attrib=None):
        """
        [M-A] 모든 틱을 _price_cache에 저장.
        UI 갱신은 하지 않음 → _flush_tick_ui가 200ms마다 처리.

        기초자산(REQ_UND) 틱은 즉시 und_price를 갱신해야
        ATM 계산, 스나이퍼 등이 정확하게 동작하므로
        캐시 저장과 함께 super() 호출로 und_price를 갱신.
        """
        # 항상 타임스탬프 갱신 (Watchdog 용)
        self._last_tick_time = datetime.now()

        # 캐시에 저장
        if reqId not in self._price_cache:
            self._price_cache[reqId] = {}
        self._price_cache[reqId][tickType] = price

        # 더티 표시 (옵션 reqId만 — 기초자산은 즉시 처리)
        if reqId != REQ_UND:
            self._dirty_req_ids.add(reqId)

        # MDT 검증 (첫 틱에서만 수행)
        if getattr(self, '_mdt_verify_mode', False) and reqId == REQ_UND:
            self._mdt_verify_mode = False
            is_live = tickType < 66
            if getattr(self, '_requested_live', False) and not is_live:
                self._log(
                    "⚠ 실시간 시세 권한 없음 — 지연 데이터 수신 중. "
                    "TWS 시세 구독 권한을 확인하세요.")
                self.lbl_status.setText("● 권한 없음(지연)")
                self.lbl_status.setStyleSheet(
                    "color:#ff9800;font-weight:bold;border:none;")
            elif is_live:
                self._log("✅ 실시간 시세 정상 수신")

        # 기초자산 틱은 즉시 und_price 갱신 (ATM 계산, 스나이퍼 연동)
        # 스나이퍼용 가격 캐시도 즉시 갱신
        if reqId == REQ_UND:
            super()._on_tick_price(reqId, tickType, price, attrib)
            return

        # 옵션 틱: super() 호출 생략 → _flush_tick_ui에서 배치 처리
        # (스나이퍼는 _price_cache를 직접 참조하므로 정확도 영향 없음)

    def _on_tick_option(self, reqId: int, tickType: int,
                        impliedVol: float, delta: float,
                        optPrice: float, pvDividend: float,
                        gamma: float, vega: float,
                        theta: float, undPrice: float):
        """
        [M-A] Greeks 틱도 캐시에 저장, 200ms 배치 갱신.
        """
        if reqId not in self._option_cache:
            self._option_cache[reqId] = {}
        cache = self._option_cache[reqId]
        cache['iv']       = impliedVol
        cache['delta']    = delta
        cache['gamma']    = gamma
        cache['theta']    = theta
        cache['vega']     = vega
        cache['optPrice'] = optPrice
        cache['undPrice'] = undPrice
        self._dirty_req_ids.add(reqId)

    # ── 200ms 배치 UI 갱신 ──────────────────────────────────────
    def _flush_tick_ui(self):
        """
        200ms마다 호출. _dirty_req_ids에 쌓인 reqId만 처리.
        더티 목록을 스왑 후 처리하여 처리 중 새 틱과 충돌 방지.
        """
        if not self._dirty_req_ids:
            return

        # 더티 목록 스냅샷 (처리 중 새 항목 추가에 안전)
        dirty_snap = self._dirty_req_ids.copy()
        self._dirty_req_ids.clear()

        for req_id in dirty_snap:
            self._flush_one_req(req_id)

    def _flush_one_req(self, req_id: int):
        """
        단일 reqId의 캐시를 tbl_call / tbl_put에 반영.

        reqId 범위로 콜/풋 구분:
          REQ_CALL ~ REQ_CALL+25 → tbl_call
          REQ_PUT  ~ REQ_PUT+25  → tbl_put
        row = reqId - REQ_CALL (또는 REQ_PUT)
        """
        price_ticks  = self._price_cache.get(req_id, {})
        option_ticks = self._option_cache.get(req_id, {})

        if not price_ticks and not option_ticks:
            return

        # 콜/풋 구분 및 행 인덱스
        if REQ_CALL <= req_id <= REQ_CALL + 25:
            tbl = getattr(self, 'tbl_call', None)
            row = req_id - REQ_CALL
        elif REQ_PUT <= req_id <= REQ_PUT + 25:
            tbl = getattr(self, 'tbl_put', None)
            row = req_id - REQ_PUT
        else:
            # 범위 밖(긴급매도, 스나이퍼 등) → 원본 경로로 위임
            self._apply_tick_price_direct(req_id, price_ticks)
            return

        if tbl is None or row < 0 or row >= tbl.rowCount():
            return

        # 가격 틱 갱신 (Bid=1, Ask=2, Last=4)
        for tt, col in _TT_TO_COL.items():
            price = price_ticks.get(tt)
            if price is not None and price > 0:
                self._set_cell_price(tbl, row, col, price, req_id, tt)

        # Greeks 갱신 (Delta 등 — 테이블 컬럼 존재 시)
        if option_ticks:
            self._apply_greeks_to_row(tbl, row, option_ticks, req_id)

        # 현재가 패널 갱신 (1클릭으로 선택된 reqId만)
        if req_id == getattr(self, '_pp_opt_req_id', None):
            self._refresh_opt_panel_from_cache(req_id)

    def _set_cell_price(self, tbl, row: int, col: int,
                        price: float, req_id: int, tt: int):
        """
        테이블 셀에 가격 기록. 변화 없으면 스킵 (불필요한 repaint 방지).
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush

        item = tbl.item(row, col)
        new_text = f"{price:.2f}"
        if item and item.text() == new_text:
            return  # 값 동일 → repaint 생략

        # 색상: Bid=청색, Ask=주황, Last=흰색
        _COLOR = {1: "#33aaff", 2: "#ffaa33", 4: "#ffffff"}
        color = _COLOR.get(tt, "#cccccc")

        new_item = QTableWidgetItem(new_text)
        new_item.setForeground(QBrush(QColor(color)))
        tbl.setItem(row, col, new_item)

        # call_data / put_data 딕셔너리도 동기화 (스나이퍼, 알람엔진 직접 참조)
        _tt_key = {1: 'bid', 2: 'ask', 4: 'last'}
        key = _tt_key.get(tt)
        if key:
            data_dict = (self.call_data if tbl is getattr(self, 'tbl_call', None)
                         else self.put_data)
            if req_id in data_dict:
                data_dict[req_id][key] = price

    def _apply_greeks_to_row(self, tbl, row: int,
                              cache: dict, req_id: int):
        """
        Greeks 캐시 → 테이블 Greeks 컬럼 갱신.
        Delta 컬럼(col=7 등)이 존재하는 경우에만 작동.
        """
        # tbl_call/put Greeks 컬럼은 구현마다 다름 — super()로 위임
        # super()._apply_tick_option을 직접 호출할 수 없으므로
        # call_data/put_data만 업데이트하여 다른 로직이 읽을 수 있도록 함
        data_dict = (self.call_data if tbl is getattr(self, 'tbl_call', None)
                     else self.put_data)
        if req_id in data_dict:
            for field in ('iv', 'delta', 'gamma', 'theta', 'vega'):
                val = cache.get(field)
                if val is not None:
                    data_dict[req_id][field] = val

    def _apply_tick_price_direct(self, req_id: int, price_ticks: dict):
        """
        범위 밖 reqId(스나이퍼 8100~, 긴급매도 8850~ 등)는
        원본 super() 경로로 개별 전달.
        """
        for tt, price in price_ticks.items():
            try:
                super()._on_tick_price(req_id, tt, price)
            except Exception:
                pass

    def _refresh_opt_panel_from_cache(self, req_id: int):
        """
        현재가 패널이 옵션 모드(_pp_mode='opt')이고
        선택된 reqId가 갱신됐을 때 패널만 업데이트.
        """
        if getattr(self, '_pp_mode', '') != 'opt':
            return
        ticks = self._price_cache.get(req_id, {})
        bid   = ticks.get(1, 0)
        ask   = ticks.get(2, 0)
        if bid > 0 and ask > 0 and hasattr(self, '_pp_set_quote'):
            self._pp_set_quote(bid, ask)

    # ── 캐시 직접 조회 유틸 (스나이퍼, 알람 엔진 연동) ───────────
    def get_cached_price(self, req_id: int, tick_type: int) -> float | None:
        """
        외부 모듈(스나이퍼, AlertEngine)이 실시간 캐시 가격을 읽을 때 사용.
        배치 갱신 주기와 무관하게 항상 최신 틱을 반환.
        """
        return self._price_cache.get(req_id, {}).get(tick_type)

    def get_cached_greek(self, req_id: int, field: str) -> float | None:
        """Greeks 캐시 직접 조회."""
        return self._option_cache.get(req_id, {}).get(field)

    # ── 타이머 제어 (탭 활성/비활성 연동) ──────────────────────
    def pause_tick_ui_flush(self):
        """탭 비활성화 시 UI flush 타이머 중지 (CPU 절약)."""
        if hasattr(self, '_ui_flush_timer'):
            self._ui_flush_timer.stop()

    def resume_tick_ui_flush(self):
        """탭 활성화 시 UI flush 타이머 재시작."""
        if hasattr(self, '_ui_flush_timer'):
            self._ui_flush_timer.start()
