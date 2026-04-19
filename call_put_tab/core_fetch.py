"""
core_fetch.py — 조회·기초자산·테이블클릭·관심종목 로직  v6.5
════════════════════════════════════════════════════════
v6.5 개선 사항:
  [1] 구독 진행률 표시
      - _send_req 내부에서 [N/전체] 카운터를 로그에 표시
      - lbl_status 에도 실시간 반영
  [2] 관심종목 단일클릭 스냅샷 이원화
      - 단일클릭: snapshot=True 기초자산 가격만 빠르게 조회
      - 더블클릭: 기존 전체 체인 스트림 구독
  [3] 테이블 클릭 슬리피지 방지
      - UI 텍스트 파싱 대신 call_data/put_data 딕셔너리 직접 참조
  [4] _fetch_busy 30초 타임아웃 (Safety Net)
      - 네트워크 오류로 루프 미완료 시 강제 해제

포함 메서드:
  _req_und() / _refresh_und()
  _fetch() / _init_tbl()
  _tbl_click() / _tbl_dbl()
  _on_watch_dbl() / _on_watch_single_click()
  _w_add() / _w_del()
════════════════════════════════════════════════════════
"""

from collections import deque

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


def _make_opt_contract_safe(sym: str, strike: float, right: str,
                             expiry: str, tag: str):
    """
    make_opt_contract 래퍼.
    FOP 종목(CL 등)은 SYMBOL_CFG의 secType/exchange를 강제 적용한다.
    make_opt_contract가 OPT/SMART로 만들더라도 여기서 교정.
    """
    c = make_opt_contract(sym, strike, right, expiry, tag)
    sec_type, exchange, multiplier, _ = SYMBOL_CFG.get(sym, DEFAULT_CFG)
    if sec_type == "FOP":
        # 선물 옵션 필수 필드 강제 설정
        c.secType    = "FOP"
        c.exchange   = exchange        # NYMEX
        c.multiplier = multiplier      # 1000
        # tradingClass는 만기 조회로 수신한 tc 값 우선, 없으면 sym 그대로
        if not getattr(c, 'tradingClass', ''):
            c.tradingClass = sym       # "CL"
    return c
from call_put_tab.core_fetch_pos import CoreFetchPosMixin


# ── 종목별 강제 지연 세트 ─────────────────────────────────────────
# 장중에도 실시간 권한이 없는 종목 → MDT=3(20분 지연) 강제
_DELAYED_SYMS = {"VIX", "CL"}

def _mdt_for_sym(sym: str, ib) -> int:
    """
    종목별 MarketDataType 결정.
    _DELAYED_SYMS 에 속하면 장중/장외 무관하게 항상 3(지연) 반환.
    나머지는 auto_mdt() 로 자동 판별 (장중=1, 평일장외=3, 주말=4).
    """
    if sym.upper() in _DELAYED_SYMS:
        try:
            ib.reqMarketDataType(3)
        except Exception as e:
            print(f"[mdt_for_sym] MDT=3 설정 실패({sym}): {e}")
        return 3
    return auto_mdt(ib)


def _alive(widget):
    """위젯이 파괴되지 않았는지 확인."""
    try:
        widget.objectName()
        return True
    except RuntimeError:
        return False


class CoreFetchMixin(CoreFetchPosMixin):
    """조회·기초자산·테이블클릭·관심종목 로직. CallPutGrid에 mixin된다."""

    # ── 선물 종목별 설정 테이블 ──────────────────────────────────
    # CONTFUT은 구버전 TWS에서 "invalid security type" 에러 발생.
    # 대신 FUT + front-month 만기를 로컬 계산으로 직접 지정한다.
    #   sym : (exchange, currency, multiplier)
    _FUT_UND_CFG = {
        "CL": ("NYMEX", "USD", "1000"),   # WTI 원유 선물
        "GC": ("COMEX", "USD", "100"),    # 금 선물
        "SI": ("COMEX", "USD", "5000"),   # 은 선물
        "ES": ("CME",   "USD", "50"),     # E-mini S&P500 선물
        "NQ": ("CME",   "USD", "20"),     # E-mini Nasdaq 선물
    }

    @staticmethod
    def _cl_front_month() -> str:
        """
        CL(WTI 원유) front-month 만기 계산 → 'YYYYMM' 반환.

        IBKR 계약 만기 규칙:
          - CL 선물 만기 = 해당 월 25일의 3영업일 전
          - 오늘이 그 만기일을 지났으면 다음 달 월물 사용
        """
        from datetime import date, timedelta

        def _expiry_for_month(y: int, m: int) -> date:
            """해당 연월의 CL 만기일 계산."""
            d25 = date(y, m, 25)
            biz = 0
            d = d25 - timedelta(days=1)
            while biz < 3:
                if d.weekday() < 5:   # 월~금
                    biz += 1
                    if biz < 3:
                        d -= timedelta(days=1)
                else:
                    d -= timedelta(days=1)
            # 3영업일 전 = d25에서 역산한 마지막 d
            # 간단 버전: 25일에서 3영업일 전
            cnt = 0
            cur = d25 - timedelta(days=1)
            while cnt < 3:
                if cur.weekday() < 5:
                    cnt += 1
                cur -= timedelta(days=1)
            return cur + timedelta(days=1)   # 루프 1일 초과 보정

        today = date.today()
        y, m = today.year, today.month
        exp = _expiry_for_month(y, m)

        # 만기 5영업일 이내면 다음 달 월물로 롤오버
        # IBKR은 만기 임박 계약(~5영업일)을 더 이상 제공하지 않음
        # 오늘=4/18, 만기=4/22 → 영업일 4일 → 202605로 롤오버
        biz_remaining = 0
        d = today
        while d < exp:
            if d.weekday() < 5:
                biz_remaining += 1
            d += timedelta(days=1)

        if biz_remaining <= 5:
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1

        return f"{y}{m:02d}"

    def _make_fut_contract(self, sym: str):
        """
        선물 종목용 FUT 계약 생성.
        front-month 만기를 로컬 계산으로 직접 지정 → CONTFUT 불필요.
        """
        from ibapi.contract import Contract as _C
        exch, cur, mult = self._FUT_UND_CFG.get(sym, ("SMART", "USD", ""))
        c = _C()
        c.symbol     = sym
        c.secType    = "FUT"
        c.exchange   = exch
        c.currency   = cur
        c.multiplier = mult

        # CL은 자체 계산, 나머지는 일반적인 front-month(현재 달 or 다음 달)
        if sym == "CL":
            c.lastTradeDateOrContractMonth = self._cl_front_month()
        else:
            from datetime import date
            today = date.today()
            c.lastTradeDateOrContractMonth = f"{today.year}{today.month:02d}"

        return c

    def _req_und(self, sym):
        sym = sym.upper().replace("SPXW", "SPX").replace("NANOS", "SPX")
        if not self.mw.connected: return

        # ── 선물 종목: FUT + front-month 만기로 현재가 조회 ─────
        if sym in self._FUT_UND_CFG:
            contract = self._make_fut_contract(sym)
            self._log(f"📌 {sym} 기초자산: FUT {contract.lastTradeDateOrContractMonth}")
        else:
            contract = make_und_contract(sym)

        # ── MDT 설정 후 cancel → 300ms 딜레이 → reqMktData ──────
        # ERR 354: reqMarketDataType 직후 바로 reqMktData 하면 MDT 전환
        #          미완료 상태에서 요청이 도달해 "권한 없음" 거부.
        # ERR 322: cancel 직후 딜레이 사이에 _req_und 재호출 시
        #          같은 REQ_UND로 중복 요청 발생.
        # 해결: cancel + MDT 설정을 먼저 하고,
        #       _und_pending 세대 카운터로 중복 요청 폐기.
        _mdt_for_sym(sym, self.mw.ib)
        try: self.mw.ib.cancelMktData(REQ_UND)
        except: pass

        gen = getattr(self, '_und_gen', 0) + 1
        self._und_gen = gen

        def _send(g=gen, c=contract):
            if getattr(self, '_und_gen', 0) != g: return  # 세대 폐기
            if not self.mw.connected: return
            try:
                self.mw.ib.reqMktData(REQ_UND, c, "232", False, False, [])
            except Exception as e:
                self._log(f"⚠ _req_und reqMktData 오류: {e}")

        delay = 300 if sym in _DELAYED_SYMS else 0
        if delay:
            QTimer.singleShot(delay, _send)
        else:
            _send()

    def _refresh_und(self):
        if not self.mw.connected: return
        from core import is_market_open
        if is_market_open():
            self._und_timer.stop()
            return
        sym = self.edit_sym.text().strip().upper().replace("SPXW","SPX")
        self._req_und(sym)

    # ── [v6.5-4] _fetch_busy 강제 해제 타임아웃 ─────────────────
    def _arm_fetch_timeout(self):
        """_fetch_busy=True 설정 후 호출. 30초 후 강제 해제."""
        t = getattr(self, '_fetch_timeout_timer', None)
        if t is None:
            self._fetch_timeout_timer = QTimer(self)
            self._fetch_timeout_timer.setSingleShot(True)
            self._fetch_timeout_timer.timeout.connect(self._force_release_busy)
        self._fetch_timeout_timer.start(30_000)

    def _force_release_busy(self):
        if getattr(self, '_fetch_busy', False):
            self._fetch_busy = False
            self._log("⚠ 구독 타임아웃 (30초) — _fetch_busy 강제 해제. 재조회 가능합니다.")

    # ── 메인 조회 ────────────────────────────────────────────────
    def _fetch(self):
        if not _alive(self): return

        # ✅ 중복 호출 차단
        if getattr(self, '_fetch_busy', False):
            self._log("⚠ 구독 진행 중 — 중복 조회 요청 무시 (잠시 후 재시도)")
            return
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","먼저 TWS에 연결하세요."); return
        if self.und_price is None:
            sym = self.edit_sym.text().strip().upper() or "SPX"
            retry = getattr(self, '_fetch_retry', 0)
            if retry >= 5:
                self._fetch_retry = 0
                self._log(f"⚠ 현재가 수신 실패 ({sym}) — TWS 연결 상태를 확인하세요.")
                return
            self._fetch_retry = retry + 1
            self._log(f"현재가 수신 중… ({sym}) 잠시 후 재시도합니다. ({self._fetch_retry}/5)")
            # retry==1(첫 시도)에만 _req_und 호출
            # 이후 재시도에서는 이미 요청 진행 중이므로 중복 호출 안 함
            if self._fetch_retry == 1:
                self._req_und(sym)
            t = getattr(self, '_fetch_retry_timer', None)
            if t is None:
                self._fetch_retry_timer = QTimer(self)
                self._fetch_retry_timer.setSingleShot(True)
                self._fetch_retry_timer.timeout.connect(self._fetch)
                t = self._fetch_retry_timer
            else:
                t.stop()
            t.start(2000)
            return

        self._fetch_retry = 0
        expiry, tag = self._get_expiry()
        if not expiry: return
        sym = self.edit_sym.text().strip().upper() or "SPX"
        n   = self.spin_n.value(); self._n_strikes = n

        from core import _resolve_spx_trading_class
        display_tc = (_resolve_spx_trading_class(sym, expiry, tag)
                      if sym in ("SPX","SPXW") else sym)
        _,_,_,step = SYMBOL_CFG.get(
            sym if sym != "SPXW" else "SPX", DEFAULT_CFG)

        # ── [v6.6] cancel 대상: 실제 구독 중인 reqId 만 ────────────
        # 기존: _MAX_STRIKES 전체(최대 81개) 무조건 cancel
        #       → 30ms 간격 81개 = 2.4초, EClient 소켓 버퍼 overflow → 0xC0000005
        # 변경: call_data / put_data 에 실제 등록된 rid 만 cancel
        #       → 첫 조회 시 0개, 이후 실제 구독수(보통 40개 이하)
        active_rids = list(self.call_data.keys()) + list(self.put_data.keys())
        cancel_ids  = [REQ_UND] + active_rids   # UND 는 항상 포함

        self._fetch_busy = True
        self._arm_fetch_timeout()
        self._log(f"{display_tc}  구독 초기화 중…  만기={expiry}  Zone={self._zone}  n={n}  cancel={len(cancel_ids)}건")

        # ── [v6.6] 세대(generation) 카운터 ─────────────────────────
        # _fetch() 재호출 시 +1 증가.
        # 이전 세대 _cancel_seq / _send_req 체인은 gen 불일치 시 즉시 종료.
        gen = getattr(self, '_fetch_gen', 0) + 1
        self._fetch_gen = gen

        def _cancel_seq(idx):
            if self._fetch_gen != gen: return   # 세대 폐기
            if not _alive(self): return
            if idx >= len(cancel_ids):
                QTimer.singleShot(300, _prepare_and_subscribe)
                return
            try: self.mw.ib.cancelMktData(cancel_ids[idx])
            except: pass
            QTimer.singleShot(80, lambda: _cancel_seq(idx + 1))   # 30→80ms

        def _prepare_and_subscribe():
            if self._fetch_gen != gen: return   # 세대 폐기
            if not _alive(self): return
            self.call_data.clear(); self.put_data.clear()
            if PG:
                # [v6.5 tip] deque 기반이면 .clear() 그대로 사용
                self._prices.clear(); self._deltas.clear(); self._spreads.clear()

            atm = round(self.und_price / step) * step
            self.call_strikes, self.put_strikes = \
                self._strikes_for_zone(atm, step, n)

            self._init_tbl(self.tbl_call, self.call_strikes)
            self._init_tbl(self.tbl_put,  self.put_strikes)

            ticks = "100,101,106"
            if self.call_strikes:
                _c0 = _make_opt_contract_safe(sym, self.call_strikes[0], "C", expiry, tag)
                self._log(
                    f"계약: symbol={_c0.symbol} "
                    f"tc={getattr(_c0,'tradingClass','')} "
                    f"exch={_c0.exchange} ATM={atm}")

            # ── 구독 요청 목록 조립 ───────────────────────────────
            # [v6.5] ATM 중심 인터리빙 순서로 변경
            # 기존: CALL 전체(0→n) → PUT 전체(0→n)
            #       OTM이 리스트 뒤쪽 → 40개 기준 6초 후에야 구독
            # 변경: C[0],P[0], C[1],P[1], C[2],P[2] ... 교차 전송
            #       ATM(index 0)이 가장 먼저, OTM도 균등하게 빨라짐
            #       40개 기준 ATM 구독 완료 = 0.3초, 전체 = 3초

            call_reqs = []
            for i, st in enumerate(self.call_strikes):
                rid = REQ_CALL + i; self.call_data[rid] = {"row": i}
                call_reqs.append((rid, _make_opt_contract_safe(sym, st, "C", expiry, tag)))
            put_reqs = []
            for i, st in enumerate(self.put_strikes):
                rid = REQ_PUT + i; self.put_data[rid] = {"row": i}
                put_reqs.append((rid, _make_opt_contract_safe(sym, st, "P", expiry, tag)))

            # CALL/PUT 인터리빙
            all_reqs = []
            for i in range(max(len(call_reqs), len(put_reqs))):
                if i < len(call_reqs): all_reqs.append(call_reqs[i])
                if i < len(put_reqs):  all_reqs.append(put_reqs[i])

            self._req_und(sym)
            self._und_timer.start()
            total = len(all_reqs)

            # ── [v6.5-1] 진행률 표시 포함 구독 루프 ──────────────
            def _send_req(idx):
                if self._fetch_gen != gen: return   # 세대 폐기
                if not _alive(self): return
                if idx >= total:
                    self._fetch_busy = False   # 🔓 완료
                    # [v6.5-4] 타임아웃 타이머 해제
                    t = getattr(self, '_fetch_timeout_timer', None)
                    if t: t.stop()
                    self._log(f"✅ 구독 완료: 총 {total}개 계약")
                    # 상태 라벨 복원
                    if hasattr(self, 'lbl_status'):
                        self.lbl_status.setText("● 연결됨")
                        self.lbl_status.setStyleSheet(
                            "color:#00ff88;font-weight:bold;border:none;")
                    QTimer.singleShot(500, self._notify_sniper_sync)
                    return

                # [v6.5-1] 진행률 로그 (5개마다 + 마지막)
                done = idx + 1
                if done % 5 == 0 or done == total:
                    self._log(f"구독 중… [{done}/{total}]")
                # [v6.5-1] 상태 라벨에도 표시
                if hasattr(self, 'lbl_status'):
                    self.lbl_status.setText(f"● 로딩 [{done}/{total}]")
                    self.lbl_status.setStyleSheet(
                        "color:#7c7cff;font-weight:bold;border:none;")

                rid, contract = all_reqs[idx]

                def _do_req(r=rid, c=contract, next_idx=idx+1):
                    if self._fetch_gen != gen: return
                    try:
                        self.mw.ib.reqMktData(r, c, ticks, False, False, [])
                    except Exception as e:
                        self._log(f"⚠ reqMktData 오류 rid={r}: {e}")
                    QTimer.singleShot(150, lambda: _send_req(next_idx))

                # 첫 구독 시 MDT 재설정 → 200ms 딜레이 후 첫 요청
                # (ERR 354: MDT 전환 완료 전에 reqMktData 도달 방지)
                if idx == 0 and sym in _DELAYED_SYMS:
                    _mdt_for_sym(sym, self.mw.ib)
                    QTimer.singleShot(200, _do_req)
                else:
                    _do_req()

            _send_req(0)

        _cancel_seq(0)

    def _init_tbl(self, tbl, strikes):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor, QBrush
        # 변경 후
        from call_put_tab.tab_options import _mk

        tbl.clearContents(); tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r, 0, _mk(str(int(s)), "#ffd700"))
            for c in range(1, 6): tbl.setItem(r, c, _mk("―"))

    # ── 테이블 클릭 ─────────────────────────────────────────────
    def _tbl_click(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            self._prices.clear(); self._price_times.clear()
            self._deltas.clear(); self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(
                f"차트: {label}  {int(strikes[row])}  (실시간 추적 중)")
        self._log(f"차트 선택: {label} {int(strikes[row])}")

        if hasattr(self, '_chart_tabs'):
            self._chart_tabs.setCurrentIndex(0)

        if hasattr(self, 'watch_side'):   self.watch_side.setText(side)
        if hasattr(self, 'watch_strike'): self.watch_strike.setText(str(int(strikes[row])))

        # ── [v6.5-3] 슬리피지 방지: 딕셔너리 직접 참조 ───────────
        # UI 텍스트 파싱(지연 가능) 대신 최신 틱 딕셔너리에서 직접 추출
        rid        = (REQ_CALL if side == "C" else REQ_PUT) + row
        data_dict  = (self.call_data if side == "C" else self.put_data)
        tick_entry = data_dict.get(rid, {})

        cur_price = tick_entry.get("last") or tick_entry.get("bid") or tick_entry.get("ask")
        cur_delta = tick_entry.get("delta")

        # 딕셔너리에 값이 없으면 UI 텍스트로 폴백 (하위 호환)
        if cur_price is None:
            tbl = self.tbl_call if side=="C" else self.tbl_put
            price_item = tbl.item(row, 1)
            if price_item:
                try: cur_price = float(price_item.text())
                except: pass
        if cur_delta is None:
            tbl = self.tbl_call if side=="C" else self.tbl_put
            delta_item = tbl.item(row, 3)
            if delta_item:
                try: cur_delta = float(delta_item.text())
                except: pass

        self._qord_fill(side, str(int(strikes[row])),
                        cur_price, source="← 테이블 클릭")

        if col == 2 and hasattr(self, '_show_pos_sell_panel'):
            tbl = self.tbl_call if side=="C" else self.tbl_put
            pos_item = tbl.item(row, 2)
            hold_qty = 0
            if pos_item:
                try: hold_qty = int(pos_item.text())
                except: pass
            if hold_qty > 0:
                self._show_pos_sell_panel(
                    side, str(int(strikes[row])),
                    qty=hold_qty, price=cur_price)

        if hasattr(self, '_pp_opt_bid'):
            self._pp_opt_bid = None
            self._pp_opt_ask = None
        if hasattr(self, '_update_price_panel_opt'):
            self._update_price_panel_opt(
                side, str(int(strikes[row])),
                None, cur_price, cur_delta)

    def _tbl_dbl(self, row, col, side):
        strikes = self.call_strikes if side=="C" else self.put_strikes
        if row >= len(strikes): return
        self._chart_strike = strikes[row]; self._chart_side = side
        if PG:
            self._prices.clear(); self._price_times.clear()
            self._deltas.clear(); self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()
        label = 'CALL' if side=='C' else 'PUT'
        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(
                f"차트: {label}  {int(strikes[row])}  ✔ 확정")
        self._log(f"차트 확정: {label} {int(strikes[row])}")

    # ── 관심종목 ─────────────────────────────────────────────────
    _INDEX_SYMS = {"SPX","NDX","RUT","VIX","DJX","XSP","NQ","ES","MES","MNQ"}

    def _on_watch_dbl(self, item):
        """더블클릭 → 종목 변경 + 옵션 테이블 전체 재조회 (스트림 구독).

        빠른 연속 더블클릭 시 _cancel_seq / _send_req 루프가 중첩되어
        0xC0000005 크래시가 발생하므로:
          1. _fetch_busy 중이면 즉시 차단
          2. 이전 예약된 _fetch QTimer 취소 후 재예약
        """
        sym = item.text().strip().upper().replace("SPXW", "SPX")

        # ── 중복 호출 방지 ────────────────────────────────────────
        if getattr(self, '_fetch_busy', False):
            self._log(f"⚠ 구독 진행 중 — {sym} 더블클릭 무시 (완료 후 재시도)")
            return

        self.edit_sym.setText(sym)
        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요.")
            return

        # ── CL/VIX: 만기 목록 자동 갱신 (더블클릭 시) ───────────
        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()):
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

        self.und_price = None
        self.lbl_und.setText("조회 중…")
        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()
        self._req_und(sym)

        # ── 기존 예약된 _fetch 타이머 취소 후 재예약 ─────────────
        t = getattr(self, '_watch_dbl_timer', None)
        if t is None:
            self._watch_dbl_timer = QTimer(self)
            self._watch_dbl_timer.setSingleShot(True)
            self._watch_dbl_timer.timeout.connect(self._fetch)
        else:
            self._watch_dbl_timer.stop()
        self._watch_dbl_timer.start(1000)

    def _on_watch_single_click(self, item):
        """
        단일클릭 → 기초자산 스냅샷만 조회 (전체 체인 구독 안 함).
        [v6.5-2] snapshot 이원화:
          - 단일클릭: reqMktData snapshot=True 로 현재가만 빠르게 수신
          - 더블클릭: _on_watch_dbl → 전체 체인 스트림 구독
        CL/VIX 등 IBKR 만기 조회 종목은 단일클릭 시 combo_exp 자동 갱신.
        """
        sym = item.text().strip().upper().replace("SPXW", "SPX")

        # ① edit_sym 동기화
        if hasattr(self, 'edit_sym'):
            self.edit_sym.setText(sym)

        # ① - 1. CL/VIX: 만기 목록 자동 갱신 (IBKR 조회)
        # TWS 연결 중일 때만 시도 — 연결 전엔 무시
        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()) and self.mw.connected:
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

        # ② 현재가 패널 und 모드 복귀
        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()
        if hasattr(self, '_pp_lbl_sym'):
            self._pp_lbl_sym.setText(sym)
        if hasattr(self, '_pp_bid'):  self._pp_bid = None
        if hasattr(self, '_pp_ask'):  self._pp_ask = None
        if hasattr(self, '_pp_lbl_price'):
            self._pp_lbl_price.setText("조회 중…")
        if hasattr(self, '_pp_tbl_quote'):
            from call_put_tab.tab_options import _mk
            self._pp_tbl_quote.setItem(0, 1, _mk("―", "#ff6666"))
            self._pp_tbl_quote.setItem(1, 1, _mk("―", "#33aaff"))

        # ③ 기초자산 시세 재구독 (스트림 — 현재가 패널 Bid/Ask 실시간 유지)
        # snapshot=True 는 1회 수신 후 구독이 끊겨 현재가 패널 호가가 멈추므로 사용 안 함
        # 단일클릭은 전체 옵션 체인 구독(_fetch)만 하지 않음 — 기초자산은 스트림 유지
        self._req_und(sym)

        # ④ 실시간 차트 버퍼 초기화
        if PG:
            self._und_hist.clear()
            if hasattr(self, '_c_und'):
                self._c_und.setData([])

        # ⑤ 히스토리 차트 조회
        from core import is_market_open
        market_open = is_market_open()

        if market_open:
            if hasattr(self, '_fetch_intraday'):
                self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(2)
            self._log(f"관심종목 선택: {sym}  (장 중 — 분봉 차트 조회)")
        else:
            if hasattr(self, '_fetch_daily'):    self._fetch_daily()
            if hasattr(self, '_fetch_intraday'): self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):     self._chart_tabs.setCurrentIndex(1)
            self._log(f"관심종목 선택: {sym}  (장 외 — 일봉+분봉 차트 조회)")

    # ── Tab lifecycle: deactivate / activate ─────────────────────
    def on_tab_deactivate(self):
        """
        Called by TabWrapper when this tab is hidden.
        Bumps _fetch_gen to abort any in-progress _cancel_seq / _send_req
        chain, then releases _fetch_busy so re-activation can call _fetch().
        """
        old_gen = getattr(self, '_fetch_gen', 0)
        self._fetch_gen = old_gen + 1          # invalidates running QTimer chain
        if getattr(self, '_fetch_busy', False):
            self._fetch_busy = False
            t = getattr(self, '_fetch_timeout_timer', None)
            if t:
                t.stop()
            self._log("⏸ 탭 비활성화 — 구독 루프 중단, _fetch_busy 해제")

    def on_tab_activate(self):
        """
        Called by TabWrapper when this tab becomes visible.
        Re-subscribe only when connected and und_price is available.
        """
        if not getattr(getattr(self, 'mw', None), 'connected', False):
            return
        if getattr(self, 'und_price', None) is None:
            return
        if getattr(self, '_fetch_busy', False):
            return
        self._log("▶ 탭 활성화 — 체인 재구독")
        self._fetch()

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