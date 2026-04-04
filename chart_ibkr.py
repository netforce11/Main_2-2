"""
chart_ibkr.py — IBKR reqHistoricalData fallback (v6.8)
"""

import threading
from datetime import datetime

from PyQt5.QtCore import QTimer


class IbkrHistMixin:
    """IBKR 히스토리 조회 전용 메서드. HistoryMixin에 포함된다."""

    def _ensure_hist_router(self):
        """
        historicalData / historicalDataEnd 에 reqId 라우터를 딱 한 번만 설치.
        이후 _ibkr_hist() 호출이 몇 번이든 같은 라우터를 재사용.
        """
        if getattr(self, '_hist_router_installed', False):
            return
        self._hist_router_installed = True
        self._hist_router = {}  # {req_id: {"buf":[], "evt":Event, "is_daily":bool}}

        _orig_hd  = getattr(self.mw.ib, 'historicalData',    None)
        _orig_hde = getattr(self.mw.ib, 'historicalDataEnd', None)
        router    = self._hist_router

        def _route_bar(rId, bar):
            slot = router.get(rId)
            if slot is not None:
                try:
                    fmt = "%Y%m%d" if slot["is_daily"] else "%Y%m%d %H:%M:%S"
                    t   = datetime.strptime(bar.date[:len(fmt)], fmt)
                    slot["buf"].append({
                        "t": t.timestamp(),
                        "o": bar.open,  "h": bar.high,
                        "l": bar.low,   "c": bar.close,
                        "v": bar.volume,
                    })
                except Exception:
                    pass
            if callable(_orig_hd):
                try: _orig_hd(rId, bar)
                except Exception: pass

        def _route_end(rId, *args):
            slot = router.get(rId)
            if slot is not None:
                slot["evt"].set()
            if callable(_orig_hde):
                try: _orig_hde(rId, *args)
                except Exception: pass

        self.mw.ib.historicalData    = _route_bar
        self.mw.ib.historicalDataEnd = _route_end

    def _ibkr_hist(self, sym, duration, bar_size, req_id, on_done, lbl,
                   on_timeout=None):
        """
        reqHistoricalData fallback (v6.8)
        - reqId별 독립 버퍼 → 일봉/분봉 동시 요청 충돌 없음
        - 인덱스(SPX/NDX 등) → MIDPOINT, 주식/ETF → TRADES
        - useRTH=0: 시간외 포함, timeout=8초
        """
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요")
            if callable(on_timeout):
                QTimer.singleShot(0, on_timeout)
            return

        self._ensure_hist_router()

        _INDEX   = {"SPX", "SPXW", "NDX", "VIX", "RUT", "DJX", "XSP", "MID", "GSPC"}
        what     = "MIDPOINT" if sym.upper() in _INDEX else "TRADES"
        is_daily = "day" in bar_size

        done_evt = threading.Event()
        self._hist_router[req_id] = {"buf": [], "evt": done_evt, "is_daily": is_daily}
        lbl.setText(f"⏳ IBKR {bar_size} ({what}) 조회 중… {sym}")

        def _run():
            try:
                from core import make_und_contract
                contract = make_und_contract(sym)
                self.mw.ib.reqHistoricalData(
                    req_id, contract, "", duration, bar_size, what,
                    0, 1, False, [])
                got      = done_evt.wait(timeout=8)
                slot     = self._hist_router.pop(req_id, {})
                hist_buf = slot.get("buf", [])
                if hist_buf:
                    bars_copy = list(hist_buf)
                    QTimer.singleShot(0, lambda: on_done(bars_copy))
                else:
                    msg = "❌ IBKR 타임아웃" if not got else "❌ IBKR 데이터 없음"
                    QTimer.singleShot(0, lambda: lbl.setText(msg))
                    if callable(on_timeout):
                        QTimer.singleShot(0, on_timeout)
            except Exception as e:
                err_msg = str(e)
                QTimer.singleShot(0, lambda: lbl.setText(f"❌ IBKR 오류: {err_msg}"))
                self._hist_router.pop(req_id, None)
                if callable(on_timeout):
                    QTimer.singleShot(0, on_timeout)

        threading.Thread(target=_run, daemon=True).start()
