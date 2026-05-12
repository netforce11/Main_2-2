"""
core_fetch_table.py — 테이블 클릭/더블클릭 및 옵션 차트 스냅샷
════════════════════════════════════════════════════════
포함 내용:
  - _DummyLabel                    chart_lbl 더미 클래스
  - CoreFetchTableMixin
      _tbl_click()                 1클릭: 현재가 패널 옵션 모드 전환
      _tbl_dbl()                   2클릭: 분봉 차트 조회
      _fetch_option_snapshot()     옵션 스냅샷 reqHistoricalData
      _on_opt_snapshot_done()      스냅샷 완료 콜백
      _on_opt_snapshot_timeout()   스냅샷 타임아웃 콜백
      _notify_sniper_sync()        스나이퍼 탭 동기화
════════════════════════════════════════════════════════
"""

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtCore import QTimer

from core import REQ_CALL, REQ_PUT, auto_mdt
from call_put_tab.core_fetch_subscribe import CoreFetchSubscribeMixin  # _req_und, _refresh_und, chain
from call_put_tab.core_fetch_contracts import make_opt_contract_safe, _alive


class _DummyLabel:
    """chart_lbl 위젯이 없을 때 _poll_hist의 lbl 자리를 채우는 더미."""
    def setText(self, *_): pass


class CoreFetchTableMixin(CoreFetchSubscribeMixin):
    """테이블 클릭/더블클릭 및 옵션 차트 스냅샷 로직."""

    # 옵션 스냅샷 차트용 reqId (REQ_HIST 6000~6099 범위 밖)
    _OPT_SNAP_REQ = 6500

    # 지수 심볼 세트
    _INDEX_SYMS = {"SPX", "NDX", "RUT", "VIX", "DJX", "XSP", "NQ", "ES", "MES", "MNQ"}

    def _tbl_click(self, row, col, side):
        """1클릭 → 현재가 패널 옵션 모드 전환 + 이후 tick 자동 수신.

        - _chart_strike / _chart_side 설정 → _apply_tick_price() 조건 통과
        - cancelMktData/재구독 금지: _fetch()가 구독 중인 rid를 cancel하면
          Bid/Ask 한쪽만 오는 TWS 버그 발생
        """
        if getattr(self, '_dbl_pending', False):
            return

        strikes = self.call_strikes if side == "C" else self.put_strikes
        if row >= len(strikes):
            return

        strike = strikes[row]
        rid    = (REQ_CALL if side == "C" else REQ_PUT) + row

        self._chart_strike  = strike
        self._chart_side    = side
        self._pp_mode       = 'opt'
        self._pp_opt_side   = side
        self._pp_opt_strike = str(int(strike))
        self._pp_opt_bid    = None
        self._pp_opt_ask    = None

        # 미구독 상태면 신규 구독
        data_dict_chk = self.call_data if side == "C" else self.put_data
        if self.mw.connected and rid not in data_dict_chk:
            try:
                expiry, tag = self._get_expiry()
                sym = self.edit_sym.text().strip().upper() or "SPX"
                contract = make_opt_contract_safe(sym, strike, side, expiry, tag)
                self.mw.ib.reqMktData(rid, contract, "100,101,104,106", False, False, [])
                self._log(f"{'CALL' if side=='C' else 'PUT'} {int(strike)} 호가 신규 구독")
            except Exception as e:
                self._log(f"⚠ 호가 구독 오류: {e}")

        # 기존 수신 데이터 읽기
        data_dict  = self.call_data if side == "C" else self.put_data
        tick_entry = data_dict.get(rid, {})

        _p = tick_entry.get("last") or tick_entry.get("bid") or tick_entry.get("ask")
        cur_price = _p
        cur_delta = tick_entry.get("delta")
        cur_bid   = tick_entry.get("bid")
        cur_ask   = tick_entry.get("ask")

        if cur_price is None:
            tbl  = self.tbl_call if side == "C" else self.tbl_put
            item = tbl.item(row, 1)
            if item:
                try: cur_price = float(item.text())
                except Exception: pass
        if cur_delta is None:
            tbl  = self.tbl_call if side == "C" else self.tbl_put
            item = tbl.item(row, 3)
            if item:
                try: cur_delta = float(item.text())
                except Exception: pass

        if cur_bid is not None: self._pp_opt_bid = cur_bid
        if cur_ask is not None: self._pp_opt_ask = cur_ask

        if hasattr(self, '_update_price_panel_opt'):
            self._update_price_panel_opt(
                side, str(int(strike)), cur_bid, cur_ask, cur_delta)

        self._qord_fill(side, str(int(strike)), cur_price, source="← 테이블 클릭")

        if hasattr(self, 'watch_side'):   self.watch_side.setText(side)
        if hasattr(self, 'watch_strike'): self.watch_strike.setText(str(int(strike)))

        # 잔고 컬럼 → 포지션 매도 패널
        if col == 6 and hasattr(self, '_show_pos_sell_panel'):
            tbl      = self.tbl_call if side == "C" else self.tbl_put
            pos_item = tbl.item(row, 6)
            hold_qty = 0
            if pos_item:
                try: hold_qty = int(pos_item.text())
                except Exception: pass
            if hold_qty > 0:
                self._show_pos_sell_panel(
                    side, str(int(strike)), qty=hold_qty, price=cur_price)

        # 스나이퍼 탭 자동 입력
        try:
            expiry_sn, _ = self._get_expiry()
            if expiry_sn and hasattr(self, 'set_sniper_target'):
                self.set_sniper_target(
                    strike=str(int(strike)), right=side, expiry=expiry_sn)
        except Exception:
            pass

        label = 'CALL' if side == 'C' else 'PUT'
        self._log(f"1클릭: {label} {int(strike)}"
                  + (f"  bid={cur_bid:.2f}" if cur_bid else "")
                  + (f"  ask={cur_ask:.2f}" if cur_ask else ""))

    def _tbl_dbl(self, row, col, side):
        """2클릭 → 차트 분봉(reqHistoricalData) 조회."""
        strikes = self.call_strikes if side == "C" else self.put_strikes
        if not strikes or row >= len(strikes):
            return

        self._dbl_pending = True
        QTimer.singleShot(0, lambda: setattr(self, '_dbl_pending', False))

        strike = strikes[row]
        label  = 'CALL' if side == 'C' else 'PUT'

        self._chart_strike = strike
        self._chart_side   = side

        if PG:
            self._prices.clear()
            self._price_times.clear()
            self._deltas.clear()
            self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()

        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(f"차트: {label}  {int(strike)}  ⏳ 분봉 조회 중…")

        self._log(f"차트 2클릭: {label} {int(strike)}  → 분봉 reqHistoricalData")
        self._fetch_option_snapshot(strike, side)

    def _fetch_option_snapshot(self, strike: float, side: str):
        """
        행사가·방향에 대한 옵션 분봉 히스토리를 스냅샷(1회) 방식으로 조회.

        chart_ibkr.py의 IbkrHistMixin 인프라를 재활용한다.
        whatToShow="TRADES", useRTH=0, barSizeSetting="1 min", durationStr="2 D"
        """
        if not self.mw.connected:
            self._log("⚠ 옵션 차트 조회: IBKR 미연결")
            if hasattr(self, 'chart_lbl'):
                self.chart_lbl.setText("차트: ⚠ IBKR 미연결")
            return

        try:
            expiry, tag = self._get_expiry()
        except Exception:
            expiry, tag = None, None
        if not expiry:
            self._log("⚠ 옵션 차트 조회: 만기일 미설정")
            return

        sym   = self.edit_sym.text().strip().upper() or "SPX"
        label = 'CALL' if side == 'C' else 'PUT'
        req   = self._OPT_SNAP_REQ

        if hasattr(self, '_stop_live'):
            self._stop_live()
        try:
            self.mw.ib.cancelHistoricalData(req)
        except Exception:
            pass
        if hasattr(self, '_hist_router'):
            self._hist_router.pop(req, None)

        self._ensure_hist_router()
        self._hist_router[req] = {"buf": [], "done": False, "is_daily": False}

        contract = make_opt_contract_safe(sym, strike, side, expiry, tag)
        self._log(f"📊 옵션 스냅샷 조회: {label} {int(strike)}  만기={expiry}")
        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(f"차트: {label}  {int(strike)}  ⏳ 조회 중…")

        # MDT 임시 전환 (스냅샷 전 저장 후 4로 전환)
        _prev_mdt = getattr(self, '_current_mdt', None)
        if _prev_mdt is None:
            try:
                _prev_mdt = auto_mdt(self.mw.ib)
            except Exception:
                _prev_mdt = 3
        try:
            self.mw.ib.reqMarketDataType(4)
        except Exception:
            pass

        try:
            self.mw.ib.reqHistoricalData(
                req, contract, "", "2 D", "1 min", "TRADES",
                0, 1, False, []
            )
        except Exception as e:
            self._log(f"⚠ 옵션 reqHistoricalData 오류: {e}")
            if hasattr(self, 'chart_lbl'):
                self.chart_lbl.setText(f"차트: {label}  {int(strike)}  ❌ 요청 실패")
            self._hist_router.pop(req, None)
            try:
                self.mw.ib.reqMarketDataType(_prev_mdt)
            except Exception:
                pass
            return

        _lbl          = getattr(self, 'chart_lbl', _DummyLabel())
        _strike_snap  = strike
        _side_snap    = side

        def _restore_mdt():
            try:
                self.mw.ib.reqMarketDataType(_prev_mdt)
            except Exception:
                pass

        def _on_done_with_restore(bars):
            _restore_mdt()
            self._on_opt_snapshot_done(bars, _strike_snap, _side_snap)

        def _on_timeout_with_restore():
            _restore_mdt()
            if hasattr(self, '_hist_router'):
                self._hist_router.pop(req, None)
            self._on_opt_snapshot_timeout()

        self._poll_hist(
            req, _on_done_with_restore, _lbl, _on_timeout_with_restore, ms=10_000,
        )

    def _on_opt_snapshot_done(self, bars, strike: float, side: str):
        """스냅샷 조회 완료 — 분봉 탭(탭2) 렌더링 후 탭 전환."""
        label = 'CALL' if side == 'C' else 'PUT'

        if not bars:
            self._log(f"⚠ 옵션 스냅샷: 데이터 없음 ({label} {int(strike)})")
            if hasattr(self, 'chart_lbl'):
                self.chart_lbl.setText(f"차트: {label}  {int(strike)}  ⚠ 데이터 없음")
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(0)
            return

        self._log(f"✅ 옵션 스냅샷: {label} {int(strike)}  {len(bars)}봉")
        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(f"차트: {label}  {int(strike)}  📊 {len(bars)}봉")

        sym       = self.edit_sym.text().strip().upper() or "SPX"
        label_sym = f"{sym} {label} {int(strike)}"
        tf        = getattr(self, '_intra_cache_tf', 1)
        maxbars   = getattr(self, '_intra_cache_maxbars', 399)

        # _intra_cache_bars 백업·복원: 옵션 봉으로 덮어쓰기 방지
        _prev_cache = getattr(self, '_intra_cache_bars', None)
        _prev_sym   = getattr(self, '_intra_cache_sym', '')

        if hasattr(self, '_on_intra_done'):
            try:
                self._on_intra_done(bars, label_sym, tf, maxbars)
            except Exception as e:
                self._log(f"⚠ 옵션 차트 렌더링 오류: {e}")

        self._intra_cache_bars = _prev_cache
        self._intra_cache_sym  = _prev_sym

        if hasattr(self, '_chart_tabs'):
            self._chart_tabs.setCurrentIndex(2)

    def _on_opt_snapshot_timeout(self):
        """폴링 타임아웃(10초) — 실시간 탭(탭0) 유지."""
        strike = getattr(self, '_chart_strike', None)
        side   = getattr(self, '_chart_side', 'C')
        label  = 'CALL' if side == 'C' else 'PUT'
        s_txt  = str(int(strike)) if strike else "?"
        self._log(f"⚠ 옵션 스냅샷 타임아웃 ({label} {s_txt}) — 실시간 탭 유지")
        if hasattr(self, '_chart_tabs'):
            self._chart_tabs.setCurrentIndex(0)

    def _notify_sniper_sync(self):
        try:
            sniper = getattr(self.mw, 'tab_sniper', None)
            if sniper and hasattr(sniper, '_sync_from_cp'):
                sniper._sync_from_cp(self, silent=True)
        except Exception:
            pass
