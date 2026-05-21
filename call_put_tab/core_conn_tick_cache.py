"""
core_conn_tick_cache.py — 틱 수신 캐시 + 200ms UI 배치 갱신  v1.1
════════════════════════════════════════════════════════════════
[M-A] UI 갱신 병목 해소

문제:
  IBKR 틱은 초당 수십~수백 개. 매 틱마다 즉시 UI를 갱신하면
  PyQt5 메인 스레드가 화면 렌더링에 잠식 → 프리징 발생.

해결:
  틱 수신 → _price_cache(dict)에만 저장 (UI 작업 없음)
  QTimer 200ms → 캐시에서 읽어 tbl_call/tbl_put 한꺼번에 갱신

구조:
  TickCacheMixin
    · _price_cache    : {reqId: {tickType: price}}
    · _option_cache   : {reqId: {field: value}}   (Greeks)
    · _ui_flush_timer : QTimer 200ms → _flush_tick_ui()
    · _on_tick_price  : 캐시 저장 + 타임스탬프만 갱신
    · _flush_tick_ui  : 캐시 → tbl_call/tbl_put 배치 갱신

주의:
  스나이퍼(_sniper_check), 알람엔진(AlertEngine),
  Watchdog(_watch_dog)은 캐시에서 직접 읽으므로
  배치 주기(200ms)와 무관하게 실시간 정확도 유지.

[v1.1] sleep_order 콜백 연동 / [v1.2] 버그 수정 2건
  기존: IBKR tick → cache → 200ms → call_data/put_data → 3초 → scan_and_check
        최악 지연 4.2초

  변경: IBKR tick → cache → 즉시 _notify_sleep_watcher()
          → _patch_chain_price() (_price_cache 직접 참조, reqId 1개만 반영)
          → watcher.on_price_update() (윈도우·fired 체크 + scan_and_check 위임)
        지연 수십ms 이내

  [v1.2 수정 ①] _patch_chain_price: call_data 대신 _price_cache 직접 참조
    call_data 는 200ms flush 후 갱신 → 틱 수신 직후엔 직전 값
    → _price_cache(tickType 1/2/4) 에서 직접 bid/ask/last 읽도록 수정

  [v1.2 수정 ②] _notify_sleep_watcher: scan_and_check 직접 호출 제거
    → watcher.on_price_update() 위임
    → 윈도우 체크·fired 체크·scan_and_check 중복 제거

  sleep_order watcher 비활성 시 _notify_sleep_watcher()는 즉시 리턴
  — 평상시 오버헤드 없음.
════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from datetime import datetime
from PyQt5.QtCore import QTimer
from core import REQ_UND, REQ_CALL, REQ_PUT

# UI 갱신 주기 (ms). 50~500 사이에서 조절 가능.
_UI_FLUSH_INTERVAL_MS = 200

# ── 컬럼 인덱스 상수 ────────────────────────────────────────
# tbl_call / tbl_put 헤더:
#   0=행사가  1=가격  2=등락%  3=Delta  4=Theta  5=Gamma  6=잔고
COL_STRIKE  = 0
COL_PRICE   = 1   # Last 가격
COL_CHG_PCT = 2   # 등락% (전일 종가 대비)
COL_DELTA   = 3
COL_THETA   = 4
COL_GAMMA   = 5
COL_HOLD    = 6   # 잔고

# 틱 타입 → 가격 컬럼 (Last만 "가격" 컬럼에 표시)
# Bid/Ask는 현재가 패널(_pp_lbl_bid/ask)로만 보내고 테이블엔 안 씀
_TT_TO_COL = {
    4: COL_PRICE,   # Last → 가격 컬럼
}


class TickCacheMixin:
    """
    틱 수신 캐시 + 200ms 배치 UI 갱신 Mixin.
    ConnSignalsMixin 앞에 MRO에 배치하여 _on_tick_price를 가로챔.
    """

    # ── 초기화 ──────────────────────────────────────────────────
    def _init_tick_cache(self):
        """
        _connect_signals() 내에서 호출.
        캐시 딕셔너리와 UI flush 타이머를 초기화한다.
        """
        # {reqId: {tickType: price}}  — 최신 틱만 유지 (덮어씀)
        self._price_cache:  dict[int, dict[int, float]] = {}
        # {reqId: {field: value}}     — Greeks 캐시
        self._option_cache: dict[int, dict[str, float]] = {}
        # 더티 플래그: flush 대기 reqId 집합 (성능 최적화)
        self._dirty_req_ids: set[int] = set()

        self._ui_flush_timer = QTimer(self)
        self._ui_flush_timer.setInterval(_UI_FLUSH_INTERVAL_MS)
        self._ui_flush_timer.timeout.connect(self._flush_tick_ui)
        self._ui_flush_timer.start()

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

        # [v1.1] sleep_order 즉시 스캔 트리거
        _notify_sleep_watcher(self, reqId)

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

        # [v1.1] sleep_order 즉시 스캔 트리거 (Greeks 갱신도 가격 변동으로 봄)
        _notify_sleep_watcher(self, reqId)

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

        # 가격 틱 갱신 (Last=4 → 가격 컬럼)
        last_price = None
        for tt, col in _TT_TO_COL.items():
            price = price_ticks.get(tt)
            if price is not None and price > 0:
                self._set_cell_price(tbl, row, col, price, req_id, tt)
                if tt == 4:
                    last_price = price

        # Bid/Ask → data_dict 동기화 (테이블엔 표시 안 함, 패널/스나이퍼용)
        for tt_ba, key_ba in ((1, "bid"), (2, "ask")):
            val_ba = price_ticks.get(tt_ba)
            if val_ba is not None and val_ba > 0:
                data_dict_ba = (self.call_data if tbl is getattr(self, "tbl_call", None)
                                else self.put_data)
                if req_id in data_dict_ba:
                    data_dict_ba[req_id][key_ba] = val_ba

        # [v1.1] _chain_call / _chain_put 즉시 반영 (3초 _auto_sync_chain 대기 제거)
        # call_data / put_data 가 위에서 갱신된 직후 호출 → 항상 최신값 반영
        _flush_chain_price(self, req_id)

        # Greeks 갱신
        if option_ticks:
            self._apply_greeks_to_row(tbl, row, option_ticks, req_id)

        # 지수대비거리% 갱신 (und_price 수신 후 매 flush 마다 재계산)
        self._update_dist_pct(tbl, row, req_id)

        # 현재가 패널 갱신 (1클릭으로 선택된 reqId만)
        if req_id == getattr(self, '_pp_opt_req_id', None):
            self._refresh_opt_panel_from_cache(req_id)

    def _set_cell_price(self, tbl, row: int, col: int,
                        price: float, req_id: int, tt: int):
        """
        테이블 셀에 가격 기록. 변화 없으면 스킵 (불필요한 repaint 방지).
        Last(tt=4)만 COL_PRICE 에 기록. Bid/Ask는 테이블에 쓰지 않음.
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush

        # Last 가격: 흰색으로 표시
        color = "#ffffff"

        item = tbl.item(row, col)
        new_text = f"{price:.2f}"
        if item and item.text() == new_text:
            return  # 값 동일 → repaint 생략

        new_item = QTableWidgetItem(new_text)
        new_item.setForeground(QBrush(QColor(color)))
        tbl.setItem(row, col, new_item)

        # call_data / put_data 딕셔너리도 동기화 (스나이퍼, 알람엔진 직접 참조)
        _tt_key = {1: "bid", 2: "ask", 4: "last"}
        key = _tt_key.get(tt)
        if key:
            data_dict = (self.call_data if tbl is getattr(self, "tbl_call", None)
                         else self.put_data)
            if req_id in data_dict:
                data_dict[req_id][key] = price

    def _apply_greeks_to_row(self, tbl, row: int,
                              cache: dict, req_id: int):
        """
        Greeks 캐시 → 테이블 Greeks 컬럼 + data_dict 동기화.
        컬럼: Delta=3, Theta=4, Gamma=5
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush

        def _set(col, val, color="#aaddff"):
            if tbl.columnCount() <= col:
                return
            new_text = f"{val:+.4f}"
            item = tbl.item(row, col)
            if item and item.text() == new_text:
                return
            it = QTableWidgetItem(new_text)
            it.setForeground(QBrush(QColor(color)))
            tbl.setItem(row, col, it)

        delta = cache.get("delta")
        theta = cache.get("theta")
        gamma = cache.get("gamma")

        if delta is not None:
            col = "#00e5ff" if delta >= 0 else "#ff6b9d"
            _set(COL_DELTA, delta, col)
        if theta is not None:
            _set(COL_THETA, theta, "#ff9a3c")
        if gamma is not None:
            _set(COL_GAMMA, gamma, "#b39ddb")

        # data_dict 동기화 (스나이퍼, 알람엔진 직접 참조)
        data_dict = (self.call_data if tbl is getattr(self, "tbl_call", None)
                     else self.put_data)
        if req_id in data_dict:
            for field in ("iv", "delta", "gamma", "theta", "vega"):
                val = cache.get(field)
                if val is not None:
                    data_dict[req_id][field] = val

    def _get_spx_ref_price(self) -> float | None:
        """
        SPX 기준가 반환.
        - 장중: und_price (SPX 현물) 그대로 사용
        - 장외: und_price(/ES 선물) - ES_BASIS_OFFSET(5pt) 로 보정
          → _fetch_chain_seq 와 동일한 보정 로직 적용
        """
        und = getattr(self, "und_price", None)
        if not und or und <= 0:
            return None
        if getattr(self, "_und_is_futures", False):
            ES_BASIS_OFFSET = 5.0
            return und - ES_BASIS_OFFSET
        return und

    def _update_dist_pct(self, tbl, row: int, req_id: int):
        """
        지수대비거리% = (strike - ref_price) / ref_price * 100
        - 부호 O: 행사가 > 현재가 → + (위쪽), 행사가 < 현재가 → - (아래쪽)
        - 장외: /ES 선물가에서 basis 5pt 차감한 SPX 추정가 사용
        - 소수점 2자리, 표기: +0.45% / -0.45%
        """
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush

        ref = self._get_spx_ref_price()
        if ref is None:
            return
        if tbl.columnCount() <= COL_CHG_PCT:
            return

        # 행사가: col0 텍스트에서 읽음
        strike_item = tbl.item(row, COL_STRIKE)
        if strike_item is None:
            return
        try:
            strike = float(strike_item.text().replace(",", ""))
        except (ValueError, TypeError):
            return

        # 부호 있는 거리% — 콜/풋 모두 동일 기준
        # + : 행사가가 현재가보다 위 (콜 기준 OTM, 풋 기준 ITM)
        # - : 행사가가 현재가보다 아래 (콜 기준 ITM, 풋 기준 OTM)
        dist_pct = (strike - ref) / ref * 100
        sign     = "+" if dist_pct >= 0 else ""
        new_text = f"{sign}{dist_pct:.2f}%"

        item = tbl.item(row, COL_CHG_PCT)
        if item and item.text() == new_text:
            return

        # 색상: ATM 근접(±0.5%) 노란, OTM 방향 파랑, ITM 방향 주황
        abs_pct = abs(dist_pct)
        if abs_pct < 0.5:
            color = "#ffd700"   # ATM 근접
        elif dist_pct > 0:
            color = "#90caf9"   # 위쪽 (OTM콜/ITM풋)
        else:
            color = "#ffaa55"   # 아래쪽 (ITM콜/OTM풋)

        it = QTableWidgetItem(new_text)
        it.setForeground(QBrush(QColor(color)))
        tbl.setItem(row, COL_CHG_PCT, it)

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


def _flush_chain_price(cp, reqId: int) -> None:
    """
    [v1.1] _flush_one_req() 에서 호출.
    call_data / put_data 갱신 직후, 같은 reqId를
    mw.tab_combo 의 _chain_call / _chain_put 에도 반영.

    _auto_sync_chain() 의 3초 루프를 기다리지 않고
    200ms flush 주기에 맞춰 combo_tab 체인 데이터를 최신 상태로 유지.

    cp  = CallPutGrid (tab_callput) — call_data / put_data 보유
    combo_tab = LeftPanelMixin 계열 — _chain_call / _chain_put 보유
    """
    try:
        mw = getattr(cp, 'mw', None)
        if mw is None:
            return
        combo_tab = getattr(mw, 'tab_combo', None)
        if combo_tab is None:
            return
        # _chain_call / _chain_put 이 초기화되지 않았으면 스킵
        if not hasattr(combo_tab, '_chain_call') or not hasattr(combo_tab, '_chain_put'):
            return
        _patch_chain_price(combo_tab, cp, reqId)
    except Exception:
        pass


# ── [v1.1] sleep_order 즉시 스캔 연동 ───────────────────────────
# TickCacheMixin 외부 모듈 함수 (self = CallPutGrid 인스턴스)

def _notify_sleep_watcher(cp, reqId: int) -> None:
    """
    옵션 틱 수신 즉시 watcher.on_price_update() 를 호출.

    [v1.1 → v1.2 변경]
    · scan_and_check() 직접 호출 제거
      → watcher.on_price_update() 위임
      → 윈도우 체크 / fired 체크 / scan_and_check() 모두 watcher 내부에서 처리
      → 중복 로직 제거, watcher 설계 의도에 맞게 수정

    · _patch_chain_price() 호출 유지
      → _price_cache 에서 직접 읽도록 수정 (call_data 타이밍 버그 수정)

    오버헤드:
      · watcher 비활성 시 속성 조회 3회 후 즉시 리턴 — 무시할 수준
      · 활성 시 _patch_chain_price() 로 변경된 reqId 1개만 갱신 → O(1)
    """
    # REQ_CALL / REQ_PUT 범위만 처리 (스나이퍼·긴급매도 등 제외)
    if not (REQ_CALL <= reqId <= REQ_CALL + 25 or
            REQ_PUT  <= reqId <= REQ_PUT  + 25):
        return

    try:
        mw = getattr(cp, 'mw', None)
        if mw is None:
            return
        combo_tab = getattr(mw, 'tab_combo', None)
        if combo_tab is None:
            return
        watcher = getattr(combo_tab, '_sleep_watcher', None)
        if watcher is None or not watcher._active:
            return

        # _price_cache 에서 직접 읽어 _chain_call/put 즉시 갱신
        # (call_data 는 200ms 후 flush 때 갱신되므로 직접 읽어야 최신값 보장)
        _patch_chain_price(combo_tab, cp, reqId)

        # watcher.on_price_update() 에 위임
        # 내부에서 _in_window / fired 체크 + scan_and_check() 까지 처리
        watcher.on_price_update(combo_tab, 0.0)

    except Exception:
        pass  # sleep_order 연동 실패가 메인 틱 흐름을 절대 막으면 안 됨


def _patch_chain_price(combo_tab, cp, reqId: int) -> None:
    """
    변경된 reqId 1개에 해당하는 행사가 가격만
    combo_tab._chain_call / _chain_put 에 즉시 반영.

    [v1.2 수정] call_data / put_data 대신 _price_cache 직접 참조.
    call_data 는 200ms flush 후에야 갱신되므로
    틱 수신 직후 호출 시 직전 값을 읽는 버그 수정.

    가격 계산: bid/ask mid 우선, 없으면 last.
    기존 _sync_chain_from_cp() 전체 루프 대비 O(1).
    """
    try:
        # _price_cache 에서 직접 bid/ask/last 읽기
        price_cache = getattr(cp, '_price_cache', {})
        d    = price_cache.get(reqId, {})
        bid  = d.get(1)   # tickType 1 = bid
        ask  = d.get(2)   # tickType 2 = ask
        last = d.get(4)   # tickType 4 = last

        lp = None
        if bid and ask and bid > 0 and ask > 0:
            lp = round((bid + ask) / 2, 2)
        elif last and last > 0:
            lp = last

        if not lp or lp <= 0:
            return

        # 콜 체인
        if REQ_CALL <= reqId <= REQ_CALL + 25:
            idx = reqId - REQ_CALL
            strikes = getattr(cp, 'call_strikes', [])
            if idx < len(strikes):
                combo_tab._chain_call[strikes[idx]] = lp
            return

        # 풋 체인
        if REQ_PUT <= reqId <= REQ_PUT + 25:
            idx = reqId - REQ_PUT
            strikes = getattr(cp, 'put_strikes', [])
            if idx < len(strikes):
                combo_tab._chain_put[strikes[idx]] = lp

    except Exception:
        pass