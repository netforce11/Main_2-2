# tab_greeks.py  — GreeksGrid 메인 조립  S12
# Python 3.8 호환
# 기능별 분리:
#   tab_greeks_ui.py      UI 빌더 (ctrl 바, replay 바)
#   tab_greeks_status.py  신호등 패널 + 헬퍼
#   tab_greeks_fetch.py   조회·auto_fetch·chain_buf
#   tab_greeks_tick.py    tick 수신 처리
#   tab_greeks_render.py  렌더·필터·밴드
#   tab_greeks_save.py    자동저장·베이스라인
#   tab_greeks_replay.py  리플레이 모드
#   greeks_snapshot_mgr.py SnapshotManager (버그수정)
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore    import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QWidget

import greeks_db as gdb
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

ATM_WING             = 10
THROTTLE_MS          = 300
AUTOSAVE_MS          = 60_000
NEXT_EXPIRY_DELAY_MS = 600_000
REQ_NEXT_C = REQ_CHAIN_P + 200
REQ_NEXT_P = REQ_CHAIN_P + 400

class GreeksGrid(QWidget):

    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self._main    = main_win
        self._callput = getattr(main_win, "tab_callput", None)

        # 상태
        self._cell_data: Dict[Tuple, dict] = {}
        self._prev_data: Dict[Tuple, dict] = {}
        self._sym       = "SPX"; self._expiry = ""; self._tag = ""
        self._und_price = 0.0
        self._day       = date.today().strftime("%Y%m%d")

        # DB
        self._conn  = gdb.open_db(self._day)
        self._econn = gdb.open_events_db()
        self._ctx   = ContextDetector()

        # reqId 카운터
        self._rid_c  = REQ_CHAIN;   self._rid_p  = REQ_CHAIN_P
        self._rid_nc = REQ_NEXT_C;  self._rid_np = REQ_NEXT_P
        self._req_map:  Dict[int, Tuple] = {}
        self._next_map: Dict[int, Tuple] = {}

        # Throttle flush 타이머
        self._flush_t = QTimer(self)
        self._flush_t.setSingleShot(True)
        self._flush_t.timeout.connect(self._flush)

        # chain_buf
        self._chain_buf     = None
        self._use_chain_buf = False

        # SnapshotManager
        self._snap_mgr: Optional[SnapshotManager] = None
        if _SNAP_MGR_AVAILABLE:
            self._snap_mgr = SnapshotManager(
                ib=self._main.ib,
                make_contract_fn=make_opt_contract,
                on_data_fn=self._on_snap_data,
                on_status_fn=self._on_snap_status,
            )
            log.info("[GreeksGrid] SnapshotManager 초기화 완료")

        # RenderThrottle
        self._render_throttle = None; self._viewport_clip = None

        # 신호등 카운터
        self._snap_count_0dte = 0
        self._snap_count_1dte = 0
        self._snap_count_2dte = 0

        self._build()
        self._connect_signals()
        self._refresh_expiry()
        QTimer.singleShot(NEXT_EXPIRY_DELAY_MS, self._fetch_next_expiry)
        QTimer.singleShot(60_000, self._auto_fetch_if_market_hours)

    def _build(self):
        _ui.build_main(self, AUTOSAVE_MS, THROTTLE_MS,
                       _THROTTLE_AVAILABLE,
                       RenderThrottle if _THROTTLE_AVAILABLE else None,
                       ViewportClipper if _THROTTLE_AVAILABLE else None)

    def _connect_signals(self):
        router.register_price(1, 1, self._on_tick_price)
        router.register_option(REQ_CHAIN,  REQ_CHAIN_P + 199, self._on_tick_opt)
        router.register_option(REQ_NEXT_C, REQ_NEXT_P  + 199, self._on_tick_opt)
        from core import bridge
        bridge.error_sig.connect(self._on_ibkr_error)
        bridge.tick_option.connect(self._on_raw_tick_option)

    def _refresh_expiry(self):
        try: exps = build_expiry_list(self._sym)
        except Exception as e: log.error("[GreeksGrid] build_expiry_list: %s", e); return
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
        if code == "CUSTOM": return self._exp_edit.text().strip(), ""
        text = self._exp_cb.currentText()
        tag  = "0DTE" if "0DTE" in text else "W" if "[W]" in text else "M" if "[M]" in text else ""
        return code, tag

    def _calc_strikes(self, und: float, wing: int = ATM_WING, step: int = 5) -> List[float]:
        atm = round(und / step) * step
        return [atm + i * step for i in range(-wing, wing + 1)]

    def _next_trading_expiry(self) -> Optional[str]:
        nxt = date.today() + timedelta(days=1)
        while nxt.weekday() >= 5: nxt += timedelta(days=1)
        return nxt.strftime("%Y%m%d") if nxt.weekday() in (0, 2, 4) else None

    def _fetch(self):                       _fe.fetch(self)
    def _fetch_next_expiry(self):           _fe.fetch_next_expiry(self)
    def _cancel_next_expiry(self):          _fe.cancel_next_expiry(self)
    def _auto_fetch_if_market_hours(self):  _fe.auto_fetch_if_market_hours(self)
    def attach_chain_buffer(self, buf):     _fe.attach_chain_buffer(self, buf)
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
