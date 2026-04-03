"""
core_fetch.py — 조회·기초자산·테이블클릭·관심종목 로직  v6.4
════════════════════════════════════════════════════════
수정 대상: 조회 동작, 기초자산 요청, 테이블 클릭 동작
포함 메서드:
  _req_und() / _refresh_und()
  _fetch() / _init_tbl()
  _tbl_click() / _tbl_dbl()
  _on_watch_dbl() / _on_watch_single_click()
  _w_add() / _w_del()
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox, QInputDialog

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_UND, REQ_CALL, REQ_PUT,
    make_opt_contract, make_und_contract,
    auto_mdt, tbl_set,
)


class CoreFetchMixin:
    """조회·기초자산·테이블클릭·관심종목 로직. CallPutGrid에 mixin된다."""

    def _req_und(self, sym):
        sym = sym.upper().replace("SPXW", "SPX")
        if not self.mw.connected: return
        try: self.mw.ib.cancelMktData(REQ_UND)
        except: pass
        auto_mdt(self.mw.ib)
        self.mw.ib.reqMktData(
            REQ_UND, make_und_contract(sym), "232", False, False, [])

    def _refresh_und(self):
        if not self.mw.connected: return
        from core import is_market_open
        if is_market_open():
            # 장 중에는 이미 실시간 구독 중 → 재구독 불필요, 타이머 중단
            self._und_timer.stop()
            return
        # 장외(지연/동결 모드)일 때만 주기적으로 재구독해서 최신값 갱신
        sym = self.edit_sym.text().strip().upper().replace("SPXW","SPX")
        self._req_und(sym)

    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","먼저 TWS에 연결하세요."); return
        # ✅ 중복 호출 차단 — cancel/구독 진행 중 새 _fetch() 무시
        if getattr(self, '_fetch_busy', False):
            self._log("⚠ 구독 진행 중 — 중복 조회 요청 무시 (잠시 후 재시도)")
            return
        if self.und_price is None:
            sym = self.edit_sym.text().strip().upper() or "SPX"
            retry = getattr(self, '_fetch_retry', 0)
            if retry >= 5:
                # 5회 재시도 후 포기 → 루프 방지
                self._fetch_retry = 0
                self._log(f"⚠ 현재가 수신 실패 ({sym}) — TWS 연결 상태를 확인하세요.")
                return
            self._fetch_retry = retry + 1
            self._log(f"현재가 수신 중… ({sym}) 잠시 후 재시도합니다. ({self._fetch_retry}/5)")
            self._req_und(sym); QTimer.singleShot(2000, self._fetch); return
        self._fetch_retry = 0   # 성공 시 카운터 초기화
        expiry, tag = self._get_expiry()
        if not expiry: return
        sym = self.edit_sym.text().strip().upper() or "SPX"
        n   = self.spin_n.value(); self._n_strikes = n

        from core import _resolve_spx_trading_class
        display_tc = (_resolve_spx_trading_class(sym, expiry, tag)
                      if sym in ("SPX","SPXW") else sym)
        _,_,_,step = SYMBOL_CFG.get(
            sym if sym != "SPXW" else "SPX", DEFAULT_CFG)

        # ── ① cancel 순차 처리 (30ms 간격) ─────────────────────
        # 한꺼번에 cancel 후 바로 구독하면 IBKR이 cancel 반영 전에
        # 새 요청을 받아 충돌 → 장외 스냅샷 모드에서 데이터 드랍 발생
        cancel_ids = [REQ_UND]
        for i in range(self._MAX_STRIKES):
            cancel_ids.append(REQ_CALL + i)
            cancel_ids.append(REQ_PUT  + i)

        self._fetch_busy = True   # 🔒 진행 중 플래그
        self._log(f"{display_tc}  구독 초기화 중…  만기={expiry}  Zone={self._zone}  n={n}")

        def _cancel_seq(idx):
            if idx >= len(cancel_ids):
                # ── ② cancel 완료 → 500ms 후 구독 시작 ──────
                QTimer.singleShot(500, _prepare_and_subscribe)
                return
            try: self.mw.ib.cancelMktData(cancel_ids[idx])
            except: pass
            QTimer.singleShot(30, lambda: _cancel_seq(idx + 1))

        def _prepare_and_subscribe():
            self.call_data.clear(); self.put_data.clear()
            if PG:
                self._prices.clear(); self._deltas.clear(); self._spreads.clear()

            atm = round(self.und_price / step) * step
            self.call_strikes, self.put_strikes = \
                self._strikes_for_zone(atm, step, n)

            self._init_tbl(self.tbl_call, self.call_strikes)
            self._init_tbl(self.tbl_put,  self.put_strikes)

            ticks = "100,101,106"
            if self.call_strikes:
                _c0 = make_opt_contract(sym, self.call_strikes[0], "C", expiry, tag)
                self._log(
                    f"계약: symbol={_c0.symbol} "
                    f"tc={getattr(_c0,'tradingClass','')} "
                    f"exch={_c0.exchange} ATM={atm}")

            # ── ③ reqMktData 150ms 간격 순차 전송 ────────────
            # 장외 스냅샷(MDT=3) 모드에서 50ms 간격은 드랍 발생
            # 150ms로 늘려 IBKR 응답 여유 확보
            all_reqs = []
            for i, st in enumerate(self.call_strikes):
                rid = REQ_CALL + i; self.call_data[rid] = {"row": i}
                all_reqs.append((rid, make_opt_contract(sym, st, "C", expiry, tag)))
            for i, st in enumerate(self.put_strikes):
                rid = REQ_PUT + i; self.put_data[rid] = {"row": i}
                all_reqs.append((rid, make_opt_contract(sym, st, "P", expiry, tag)))

            # ✅ _req_und를 옵션 구독 시작 전에 먼저 호출
            # _send_req(0) 직후 호출하면 콜 1~2행 응답을 밀어내는 현상 발생
            self._req_und(sym)
            self._und_timer.start()

            # snapshot=True + generic ticks 조합은 ERR 321 발생 → snapshot=False 고정
            # 장외 데이터 누락은 cancel 순차화 + 150ms 간격으로 대응
            def _send_req(idx):
                if idx >= len(all_reqs):
                    self._fetch_busy = False   # 🔓 완료 시 플래그 해제
                    self._log(f"✅ 구독 완료: 총 {len(all_reqs)}개 계약")
                    # ✅ 스나이퍼 탭 즉시 동기화 — _fetch() 완료 후 콜-풋 데이터 반영
                    QTimer.singleShot(500, self._notify_sniper_sync)
                    # ✅ 포지션 조회 → 잔고 컬럼 자동 갱신
                    QTimer.singleShot(800, self._refresh_positions)
                    return
                rid, contract = all_reqs[idx]
                try:
                    self.mw.ib.reqMktData(rid, contract, ticks, False, False, [])
                except Exception as e:
                    self._log(f"⚠ reqMktData 오류 rid={rid}: {e}")
                QTimer.singleShot(150, lambda: _send_req(idx + 1))

            _send_req(0)

        _cancel_seq(0)

    def _init_tbl(self, tbl, strikes):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor, QBrush
        from tab_options import _mk
        tbl.clearContents(); tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r, 0, _mk(str(int(s)), "#ffd700"))
            for c in range(1, 6): tbl.setItem(r, c, _mk("―"))
            # 잔고 컬럼 초기값 (―)
            tbl.setItem(r, 6, _mk("―", "#aaaaaa"))

    # ── 테이블 클릭 ─────────────────────────────────────────
    def _tbl_click(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            # ✅ X/Y 버퍼 항상 동시에 clear (shape 불일치 방지)
            self._prices.clear(); self._price_times.clear()
            self._deltas.clear(); self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        self.chart_lbl.setText(
            f"차트: {label}  {int(strikes[row])}  (실시간 추적 중)")
        self._log(f"차트 선택: {label} {int(strikes[row])}")

        # ✅ 실시간 차트 탭(index=0)으로 전환 — 클릭한 행사가 즉시 표시
        if hasattr(self, '_chart_tabs'):
            self._chart_tabs.setCurrentIndex(0)

        self.watch_side.setText(side)
        self.watch_strike.setText(str(int(strikes[row])))
        tbl = self.tbl_call if side=="C" else self.tbl_put
        price_item = tbl.item(row, 1)
        delta_item = tbl.item(row, 3)
        cur_price  = None
        cur_delta  = None
        if price_item:
            try: cur_price = float(price_item.text())
            except: pass
        if delta_item:
            try: cur_delta = float(delta_item.text())
            except: pass
        self._qord_fill(side, str(int(strikes[row])),
                        cur_price, source="← 테이블 클릭")

        # ✅ 잔고 컬럼(col=6) 클릭 시 매도 패널 자동 표시
        if col == 6 and hasattr(self, '_show_pos_sell_panel'):
            pos_item = tbl.item(row, 6)
            hold_qty = 0
            if pos_item:
                try: hold_qty = int(pos_item.text())
                except: pass
            if hold_qty > 0:
                self._show_pos_sell_panel(
                    side, str(int(strikes[row])),
                    qty=hold_qty, price=cur_price)

        # 현재가 패널 → 옵션 모드로 전환
        if hasattr(self, '_pp_opt_bid'):
            self._pp_opt_bid = None
            self._pp_opt_ask = None
        # 테이블에서 Bid/Ask 초기값 (Last 가격으로 대체)
        if hasattr(self, '_update_price_panel_opt'):
            self._update_price_panel_opt(
                side, str(int(strikes[row])),
                None, cur_price, cur_delta)

    def _tbl_dbl(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            # ✅ X/Y 버퍼 항상 동시에 clear (shape 불일치 방지)
            self._prices.clear(); self._price_times.clear()
            self._deltas.clear(); self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        self.chart_lbl.setText(
            f"차트: {label}  {int(strikes[row])}  ✔ 확정")
        self._log(f"차트 확정: {label} {int(strikes[row])}")

    # ── 관심종목 ────────────────────────────────────────────
    # 지수 심볼 목록 (현재가 패널에서 지수 가격으로 표시)
    _INDEX_SYMS = {"SPX","NDX","RUT","VIX","DJX","XSP","NQ","ES","MES","MNQ"}

    def _on_watch_dbl(self, item):
        """더블클릭 → 종목 변경 + 옵션 테이블 전체 재조회."""
        sym = item.text().strip().upper().replace("SPXW","SPX")
        self.edit_sym.setText(sym)
        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        self.und_price = None; self.lbl_und.setText("조회 중…")
        # 현재가 패널 und 모드 복귀
        if hasattr(self, '_pp_switch_to_und'): self._pp_switch_to_und()
        # ✅ 종목에 맞게 만기 콤보 재구성
        if hasattr(self, '_refresh_expiry_list'):
            self._refresh_expiry_list()
        self._req_und(sym)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, self._fetch)

    def _on_watch_single_click(self, item):
        """단일클릭 → 종목 세팅 + 기초자산 구독 + 히스토리 차트 즉시 조회."""
        sym = item.text().strip().upper().replace("SPXW", "SPX")

        # ① edit_sym 동기화
        if hasattr(self, 'edit_sym'):
            self.edit_sym.setText(sym)

        # ② 현재가 패널 und 모드로 복귀 + 종목명 즉시 갱신
        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()
        if hasattr(self, '_pp_lbl_sym'):
            self._pp_lbl_sym.setText(sym)
        if hasattr(self, '_pp_bid'):  self._pp_bid = None
        if hasattr(self, '_pp_ask'):  self._pp_ask = None
        if hasattr(self, '_pp_lbl_price'):
            self._pp_lbl_price.setText("조회 중…")
        if hasattr(self, '_pp_tbl_quote'):
            from tab_options import _mk
            self._pp_tbl_quote.setItem(0, 1, _mk("―", "#ff6666"))
            self._pp_tbl_quote.setItem(1, 1, _mk("―", "#33aaff"))

        # ③ 기초자산 시세 재구독
        self._req_und(sym)

        # ④ 실시간 차트 버퍼 초기화
        if PG:
            self._und_hist.clear()
            if hasattr(self, '_c_und'):
                self._c_und.setData([])

        # ⑤ 히스토리 차트 조회
        #    - 분봉: 장중/장외 모두 허용 (1분봉은 장중에도 유효)
        #    - 일봉: 장외에만 조회
        from core import is_market_open
        market_open = is_market_open()

        if market_open:
            # 장 중 — 분봉만 조회, 분봉 탭으로 전환
            if hasattr(self, '_fetch_intraday'):
                self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(2)   # 분봉 탭(index=2)
            self._log(f"관심종목 선택: {sym}  (장 중 — 분봉 차트 조회)")
        else:
            # 장 외 — 일봉+분봉 모두 조회, 일봉 탭으로 전환
            if hasattr(self, '_fetch_daily'):    self._fetch_daily()
            if hasattr(self, '_fetch_intraday'): self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):     self._chart_tabs.setCurrentIndex(1)  # 일봉 탭
            self._log(f"관심종목 선택: {sym}  (장 외 — 일봉+분봉 차트 조회)")

    def _notify_sniper_sync(self):
        """_fetch() 완료 후 스나이퍼 탭에 즉시 동기화 요청."""
        try:
            sniper = getattr(self.mw, 'tab_sniper', None)
            if sniper and hasattr(sniper, '_sync_from_cp'):
                sniper._sync_from_cp(self, silent=True)
        except Exception:
            pass

    def _w_add(self):
        t, ok = QInputDialog.getText(self, "추가", "심볼:")
        if ok and t.strip():
            self.watchlist.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watchlist.currentRow()
        if r >= 0: self.watchlist.takeItem(r)
    # ── 포지션 조회 → 잔고 컬럼 갱신 ───────────────────────────
    def _refresh_positions(self):
        """IBKR reqPositions() 호출 → 콜-풋 테이블 잔고 컬럼(col=6) 갱신."""
        if not self.mw.connected: return
        from tab_options import _mk
        ib = self.mw.ib

        _pos_buf = {}        # { (symbol, right, strike, expiry): qty }
        _avg_buf = {}        # { (symbol, right, strike, expiry): avg_cost }

        def _on_position(account, contract, pos, avg_cost):
            if getattr(contract, 'secType', '') != 'OPT': return
            key = (
                getattr(contract, 'symbol', ''),
                getattr(contract, 'right', ''),
                int(getattr(contract, 'strike', 0)),
                getattr(contract, 'lastTradeDateOrContractMonth', '')[:8],
            )
            _pos_buf[key] = int(pos)
            _avg_buf[key] = avg_cost

        def _on_position_end():
            from PyQt5.QtCore import QTimer
            # avg_cost 딕셔너리를 특별 키로 함께 전달
            _pos_buf['avg_cost'] = _avg_buf
            QTimer.singleShot(0, lambda: self._apply_positions(_pos_buf))

        # 기존 콜백 임시 교체
        ib._orig_position    = getattr(ib, 'position',    lambda *a: None)
        ib._orig_positionEnd = getattr(ib, 'positionEnd', lambda: None)
        ib.position    = _on_position
        ib.positionEnd = _on_position_end

        try:
            ib.reqPositions()
        except Exception as e:
            self._log(f"⚠ 포지션 조회 오류: {e}")

        # 3초 후 콜백 복원
        QTimer.singleShot(3000, lambda: (
            setattr(ib, 'position',    ib._orig_position),
            setattr(ib, 'positionEnd', ib._orig_positionEnd),
        ))

    def _apply_positions(self, pos_buf: dict):
        """포지션 데이터를 콜-풋 테이블 잔고 컬럼(col=6) + 잔고 패널에 반영."""
        from tab_options import _mk
        sym    = self.edit_sym.text().strip().upper().replace('SPXW', 'SPX')
        expiry, _ = self._get_expiry()
        if not expiry: return

        # 콜-풋 테이블 잔고 컬럼 전체 초기화
        for r in range(self.tbl_call.rowCount()):
            self.tbl_call.setItem(r, 6, _mk("―", "#aaaaaa"))
        for r in range(self.tbl_put.rowCount()):
            self.tbl_put.setItem(r, 6, _mk("―", "#aaaaaa"))

        # 잔고 패널 테이블 초기화
        if hasattr(self, 'tbl_positions'):
            self.tbl_positions.setRowCount(0)

        found = 0
        avg_cost_map = pos_buf.get('avg_cost', {})
        for (p_sym, p_right, p_strike, p_expiry), qty in pos_buf.items():
            if not isinstance(p_sym, str): continue   # avg_cost 키 건너뜀
            if p_sym != sym or p_expiry != expiry[:8]: continue
            if qty == 0: continue

            color = "#00ff88" if qty > 0 else "#ff6666"
            text  = str(qty)

            # ── 콜-풋 테이블 잔고 컬럼 갱신 ──
            if p_right == 'C':
                for r, st in enumerate(self.call_strikes):
                    if int(st) == p_strike:
                        self.tbl_call.setItem(r, 6, _mk(text, color))
                        break
            elif p_right == 'P':
                for r, st in enumerate(self.put_strikes):
                    if int(st) == p_strike:
                        self.tbl_put.setItem(r, 6, _mk(text, color))
                        break

            # ── 잔고 패널 테이블에 행 추가 ──
            if hasattr(self, 'tbl_positions'):
                avg = avg_cost_map.get((p_sym, p_right, p_strike, p_expiry), 0)
                r = self.tbl_positions.rowCount()
                self.tbl_positions.insertRow(r)
                cp_color = "#33aaff" if p_right == "C" else "#ff6666"
                self.tbl_positions.setItem(r, 0, _mk("CALL" if p_right=="C" else "PUT", cp_color))
                self.tbl_positions.setItem(r, 1, _mk(str(p_strike), "#ffd700"))
                self.tbl_positions.setItem(r, 2, _mk(text, color))
                self.tbl_positions.setItem(r, 3, _mk(f"{avg:.2f}" if avg else "―", "#aaa"))

            found += 1

        if found:
            self._log(f"📊 잔고 갱신: {found}개 포지션 반영")
        else:
            self._log("📊 현재 만기 포지션 없음")