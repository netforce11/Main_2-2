# tab_greeks.py  — GreeksGrid 메인 조립  S12-fix2
# Python 3.8 호환
#
# S12-patch1 변경:
#   [논리결함2] fetch_next_expiry / cancel_next_expiry 제거
#   [심각2]     REQ_NEXT_C / REQ_NEXT_P 상수 및 import 제거
#
# S12-patch2 변경:
#   snap_mgr 전용 reqId 범위(10000~12799) router 등록 추가
#
# S12-fix2 변경:
#   [FIX-5]  __init__ 에서 self._day를 ET 기준으로 초기화 (_today_et() 사용)
#   [FIX-13] _autosave_t 타이머를 명시적으로 __init__ 에서 생성 및 참조 보장
#   [FIX-14] _on_expiry_changed() / _current_expiry() 에서 expiry 정규화 적용
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore    import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QWidget

import greeks_db as gdb
from greeks_db import _today_et
from greeks_render        import init_table
from greeks_chart         import GexSkewPanel, NormalBandPanel
from greeks_replay        import ReplayPanel
from greeks_context       import ContextDetector
from core import (router, REQ_CHAIN, REQ_CHAIN_P,
                  make_opt_contract, build_expiry_list, SYMBOL_CFG, DEFAULT_CFG,
                  GREEKS_HISTORY_DIR)

try:
    from call_put_tab.chain_saver.buffer import ChainBuffer
    _CHAIN_BUFFER_AVAILABLE = True
except ImportError:
    _CHAIN_BUFFER_AVAILABLE = False

try:
    from greeks_snapshot_mgr import SnapshotManager
    _SNAP_MGR_AVAILABLE = True
except ImportError:
    _SNAP_MGR_AVAILABLE = False

try:
    from greeks_render_throttle import RenderThrottle, ViewportClipper
    _THROTTLE_AVAILABLE = True
except ImportError:
    _THROTTLE_AVAILABLE = False

import tab_greeks_ui      as _ui
import tab_greeks_status  as _st
import tab_greeks_fetch   as _fe
import tab_greeks_tick    as _tk
import tab_greeks_render  as _re
import tab_greeks_save    as _sv
import tab_greeks_replay  as _rp

log = logging.getLogger(__name__)

ATM_WING    = 10
THROTTLE_MS = 300
AUTOSAVE_MS = 60_000


class GreeksGrid(QWidget):
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self._main    = main_win
        self._callput = getattr(main_win, "tab_callput", None)

        # ── 상태 ──────────────────────────────────────────────────────────────
        self._cell_data: Dict[Tuple, dict] = {}
        self._prev_data: Dict[Tuple, dict] = {}
        self._sym       = "SPX"; self._expiry = ""; self._tag = ""
        self._und_price = 0.0

        # [FIX-5] ET 기준 날짜로 초기화 (한국 시간대에서 실행 시 어제 날짜 오류 방지)
        self._day = _today_et()

        # ── DB ────────────────────────────────────────────────────────────────
        self._conn  = gdb.open_db(self._day)
        self._econn = gdb.open_events_db()
        self._ctx   = ContextDetector()

        # ── reqId 카운터 (0DTE fetch 전용) ────────────────────────────────────
        self._rid_c  = REQ_CHAIN
        self._rid_p  = REQ_CHAIN_P
        self._req_map: Dict[int, Tuple] = {}

        # ── Throttle flush 타이머 ─────────────────────────────────────────────
        self._flush_t = QTimer(self)
        self._flush_t.setSingleShot(True)
        self._flush_t.timeout.connect(self._flush)

        # ── chain_buf ─────────────────────────────────────────────────────────
        self._chain_buf     = None
        self._use_chain_buf = False

        # ── SharedChainStore 연동 ─────────────────────────────────────────────
        self._chain_store     = None
        self._use_chain_store = False
        self._chain_store_timer = QTimer(self)
        self._chain_store_timer.setInterval(2000)
        self._chain_store_timer.timeout.connect(
            lambda: _fe._poll_chain_store(self))

        # ── SnapshotManager (+1DTE / +2DTE 전담) ─────────────────────────────
        self._snap_mgr: Optional[SnapshotManager] = None
        if _SNAP_MGR_AVAILABLE:
            self._snap_mgr = SnapshotManager(
                ib=self._main.ib,
                make_contract_fn=make_opt_contract,
                on_data_fn=self._on_snap_data,
                on_status_fn=self._on_snap_status,
            )
            log.info("[GreeksGrid] SnapshotManager 초기화 완료")

        # ── RenderThrottle ────────────────────────────────────────────────────
        self._render_throttle = None
        self._viewport_clip   = None

        # ── 신호등 카운터 ─────────────────────────────────────────────────────
        self._snap_count_0dte = 0
        self._snap_count_1dte = 0
        self._snap_count_2dte = 0

        self._build()
        self._connect_signals()
        self._refresh_expiry()

        QTimer.singleShot(60_000, self._auto_fetch_if_market_hours)

        # [FIX-13] 자정 날짜 변경 감지 타이머 (1분마다 ET 날짜 체크)
        self._date_check_t = QTimer(self)
        self._date_check_t.setInterval(60_000)
        self._date_check_t.timeout.connect(self._check_date_change)
        self._date_check_t.start()

    # [FIX-13] 자정 날짜 변경 감지
    def _check_date_change(self):
        """
        1분마다 ET 기준 오늘 날짜와 self._day 비교.
        날짜가 바뀌면 autosave에서 처리하도록 로그만 출력.
        실제 conn 재생성은 tab_greeks_save._refresh_conn_if_needed()가 담당.
        """
        today = _today_et()
        if today != self._day:
            log.info("[GreeksGrid] 날짜 변경 감지: %s → %s (다음 autosave 시 conn 갱신)",
                     self._day, today)

    # ── 빌드 / 시그널 ─────────────────────────────────────────────────────────

    def _build(self):
        _ui.build_main(self, AUTOSAVE_MS, THROTTLE_MS,
                       _THROTTLE_AVAILABLE,
                       RenderThrottle if _THROTTLE_AVAILABLE else None,
                       ViewportClipper if _THROTTLE_AVAILABLE else None)

    def _connect_signals(self):
        router.register_price(1, 1, self._on_tick_price)
        router.register_option(REQ_CHAIN, REQ_CHAIN_P + 199, self._on_tick_opt)

        # S12-patch2: snap_mgr 전용 범위(10000~12799) 명시 등록
        # [🔴 FIX] _SNAP_MGR_AVAILABLE 체크 + try/except 방어
        #          greeks_snapshot_mgr.py 없으면 ImportError로 앱 크래시했던 문제 해소
        if _SNAP_MGR_AVAILABLE:
            try:
                from greeks_snapshot_mgr import (
                    REQ_0DTE_C_BASE, REQ_0DTE_P_BASE, REQ_0DTE_RANGE,
                    REQ_1DTE_C_BASE, REQ_1DTE_P_BASE, REQ_1DTE_RANGE,
                    REQ_2DTE_C_BASE, REQ_2DTE_P_BASE, REQ_2DTE_RANGE)
                router.register_option(REQ_0DTE_C_BASE, REQ_0DTE_P_BASE + REQ_0DTE_RANGE - 1,
                                       self._on_tick_opt)
                router.register_option(REQ_1DTE_C_BASE, REQ_1DTE_P_BASE + REQ_1DTE_RANGE - 1,
                                       self._on_tick_opt)
                router.register_option(REQ_2DTE_C_BASE, REQ_2DTE_P_BASE + REQ_2DTE_RANGE - 1,
                                       self._on_tick_opt)
                log.info("[GreeksGrid] snap_mgr reqId 범위(10000~12799) router 등록 완료")
            except ImportError as e:
                log.error("[GreeksGrid] snap_mgr router 등록 실패: %s", e)
        else:
            log.warning("[GreeksGrid] SnapshotManager 미사용 — snap_mgr router 미등록")

        from core import bridge
        bridge.error_sig.connect(self._on_ibkr_error)
        bridge.tick_option.connect(self._on_raw_tick_option)

    # ── 만기 콤보박스 ─────────────────────────────────────────────────────────

    def _refresh_expiry(self):
        try: exps = build_expiry_list(self._sym)
        except Exception as e:
            log.error("[GreeksGrid] build_expiry_list: %s", e); return
        self._exp_cb.blockSignals(True); self._exp_cb.clear()
        for label, code, tag in exps:
            self._exp_cb.addItem(label, userData=code)
        self._exp_cb.blockSignals(False)
        if self._exp_cb.count(): self._exp_cb.setCurrentIndex(0)

    def _on_sym_changed(self, sym: str):
        self._sym = sym; self._refresh_expiry()

    def _on_expiry_changed(self, idx: int):
        self._exp_edit.setVisible(self._exp_cb.currentData() == "CUSTOM")

    def _current_expiry(self) -> tuple:
        code = self._exp_cb.currentData() or ""
        if code == "CUSTOM":
            raw = self._exp_edit.text().strip()
            # [FIX-14] CUSTOM 입력값도 정규화
            return _fe._normalize_expiry(raw), ""
        text = self._exp_cb.currentText()
        tag  = ("0DTE" if "0DTE" in text else
                "W"    if "[W]"  in text else
                "M"    if "[M]"  in text else "")
        # [FIX-14] combo 값 정규화
        return _fe._normalize_expiry(code), tag

    def _calc_strikes(self, und: float, wing: int = ATM_WING,
                      step: int = 5) -> List[float]:
        atm = round(und / step) * step
        return [atm + i * step for i in range(-wing, wing + 1)]

    def _next_trading_expiry(self) -> Optional[str]:
        nxt = date.today() + timedelta(days=1)
        while nxt.weekday() >= 5: nxt += timedelta(days=1)
        return nxt.strftime("%Y%m%d") if nxt.weekday() in (0, 2, 4) else None

    # ── 위임 메서드 ───────────────────────────────────────────────────────────
    def _fetch(self):                       _fe.fetch(self)
    def _auto_fetch_if_market_hours(self):  _fe.auto_fetch_if_market_hours(self)
    def attach_chain_buffer(self, buf):     _fe.attach_chain_buffer(self, buf)
    def attach_chain_store(self, store):    _fe.attach_chain_store(self, store)
    def _on_chain_buf_update(self, *a):     _fe.on_chain_buf_update(self, *a)
    @pyqtSlot(str)
    def _apply_chain_buf_update(self, p):   _fe.apply_chain_buf_update(self, p)

    def _on_tick_price(self, *a):           _tk.on_tick_price(self, *a)
    def _on_tick_opt(self, *a):             _tk.on_tick_opt(self, *a)
    def _on_snap_data(self, *a):            _tk.on_snap_data(self, *a)
    def _on_ibkr_error(self, *a):           _tk.on_ibkr_error(self, *a)
    def _on_raw_tick_option(self, *a):      _tk.on_raw_tick_option(self, *a)

    def _flush(self):                       _re.flush(self)
    def _apply_delta_filter(self, v):       _re.apply_delta_filter(self, v)
    def _update_band(self):                 _re.update_band(self)
    def _render_dirty_cells(self, dc):      _re.render_dirty_cells(self, dc)

    def _autosave(self):                    _sv.autosave(self)
    def _save_baseline(self, rows):         _sv.save_baseline(self, rows)
    def _on_save_interval_changed(self, i): _sv.on_save_interval_changed(self, i)

    def _open_chainsaver_log(self):         _ui.open_chainsaver_log(self)

    def _blink_tick(self):                  _st.blink_tick(self)
    def _status_saving(self, s, c, l):      _st.status_saving(self, s, c, l)
    def _status_done(self, s, c, l):        _st.status_done(self, s, c, l)
    def _status_idle(self, s, r="대기"):    _st.status_idle(self, s, r)
    def _status_offhour(self, v):           _st.status_offhour(self, v)
    def _status_req_count(self, n):         _st.status_req_count(self, n)
    def _on_snap_status(self, *a):          _st.on_snap_status(self, *a)

    def _set_replay_mode(self, on):         _rp.set_replay_mode(self, on)
    def _rp_refresh_days(self):             _rp.rp_refresh_days(self)
    def _rp_on_day_changed(self, d):        _rp.rp_on_day_changed(self, d)
    def _rp_refresh_expiries(self, d):      _rp.rp_refresh_expiries(self, d)
    def _rp_load(self):                     _rp.rp_load(self)
    def _rp_toggle_play(self):              _rp.rp_toggle_play(self)
    def _rp_stop(self):                     _rp.rp_stop(self)
    def _replay_step(self):                 _rp.replay_step(self)
    def _rp_on_slider(self, v):             _rp.rp_on_slider(self, v)
    def _rp_render(self, idx):              _rp.rp_render(self, idx)
