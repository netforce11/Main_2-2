"""
core_fetch.py — 조회·기초자산·테이블클릭·관심종목 로직 v6.5
════════════════════════════════════════════════════════
[장외 선물 전환 추가] v6.5 → v6.5-FUT
  - _req_und(): SPX/SPXW 장외 시간에 /ES 선물 자동 전환 구독
  - _refresh_und(): 장외→장중 전환 감지 시 /ES 해제 후 SPX 재구독
  - _make_es_front_month(): /ES 최근월물 만기 계산 (3월/6월/9월/12월 3째주 금요일)
  - _und_is_futures: bool 플래그로 현재 기초자산이 선물인지 추적
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
    SYMBOL_CFG, DEFAULT_CFG, REQ_UND, REQ_CALL, REQ_PUT,
    make_opt_contract, make_und_contract, auto_mdt, tbl_set,
)


def make_opt_contract_safe(sym: str, strike: float, right: str, expiry: str, tag: str):
    """
    make_opt_contract 래퍼. FOP 종목(CL 등)은
    SYMBOL_CFG의 secType/exchange를 강제 적용한다.
    """
    c = make_opt_contract(sym, strike, right, expiry, tag)
    sec_type, exchange, multiplier, _step = SYMBOL_CFG.get(sym, DEFAULT_CFG)
    if sec_type == "FOP":
        c.secType    = "FOP"
        c.exchange   = exchange
        c.multiplier = multiplier
        if not getattr(c, 'tradingClass', ''):
            c.tradingClass = sym
    return c


from call_put_tab.core_fetch_pos import CoreFetchPosMixin

# ── 종목별 강제 지연 세트 ─────────────────────────────────────────
_DELAYED_SYMS = {"VIX", "CL"}


def _mdt_for_sym(sym: str, ib) -> int:
    """
    종목별 MarketDataType 결정.

    _DELAYED_SYMS(VIX, CL 등):
      - 장중(auto_mdt=1): MDT=3 (20분 지연) 강제
      - 평일 장외(auto_mdt=3): MDT=3 유지
      - 주말(auto_mdt=4): MDT=4 (frozen 종가) 사용
        → 주말에 MDT=3으로 고정하면 VIX IND도 ERR 200 발생
        → MDT=4로 설정해야 전일 종가라도 수신 가능

    나머지: auto_mdt() 그대로 (장중=1, 평일장외=3, 주말=4).
    """
    if sym.upper() in _DELAYED_SYMS:
        base = auto_mdt(ib)          # 장중=1, 평일장외=3, 주말=4
        actual = max(base, 3)        # 장중(1)이어도 최소 3 보장
        try:
            ib.reqMarketDataType(actual)
        except Exception as e:
            print(f"[mdt_for_sym] MDT={actual} 설정 실패({sym}): {e}")
        return actual
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
    _FUT_UND_CFG = {
        "CL": ("NYMEX", "USD", "1000"),
        "GC": ("COMEX", "USD", "100"),
        "SI": ("COMEX", "USD", "5000"),
        "ES": ("CME",   "USD", "50"),
        "NQ": ("CME",   "USD", "20"),
    }

    # ── /ES 장외 대체 구독 대상 종목 ────────────────────────────
    # 이 종목들이 edit_sym에 입력되었을 때 장외 시간이면 /ES로 자동 전환
    _SPX_SYMS = {"SPX", "SPXW"}

    @staticmethod
    def _cl_front_month() -> str:
        """CL(WTI 원유) front-month 만기 계산 → 'YYYYMM' 반환."""
        from datetime import date, timedelta

        def _expiry_for_month(y: int, m: int) -> date:
            cnt = 0
            cur = date(y, m, 25) - timedelta(days=1)
            while cnt < 3:
                if cur.weekday() < 5:
                    cnt += 1
                cur -= timedelta(days=1)
            return cur + timedelta(days=1)

        today = date.today()
        y, m = today.year, today.month
        exp = _expiry_for_month(y, m)

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

    @staticmethod
    def _es_front_month() -> str:
        """
        /ES E-mini S&P500 최근월물 만기 계산 → 'YYYYMM' 반환.

        /ES 만기 규칙:
          - 분기물: 3월/6월/9월/12월의 세 번째 금요일
          - 만기 5영업일 이전이면 다음 분기월로 롤오버
        """
        from datetime import date, timedelta

        QUARTERLY = [3, 6, 9, 12]

        def _third_friday(y: int, m: int) -> date:
            """해당 연월의 세 번째 금요일 반환."""
            d = date(y, m, 1)
            # 첫 번째 금요일 찾기
            days_to_fri = (4 - d.weekday()) % 7   # 4 = 금요일
            first_fri = d + timedelta(days=days_to_fri)
            return first_fri + timedelta(weeks=2)  # 세 번째 금요일

        today = date.today()
        y, m = today.year, today.month

        # 현재 달 또는 이후의 가장 가까운 분기월 찾기
        candidate_months = []
        for qm in QUARTERLY:
            if qm >= m:
                candidate_months.append((y, qm))
        if not candidate_months:
            candidate_months.append((y + 1, 3))

        # 첫 번째 후보 분기월의 만기일 계산
        cy, cm = candidate_months[0]
        exp = _third_friday(cy, cm)

        # 만기 5영업일 이내면 다음 분기월로 롤오버
        biz_remaining = 0
        d = today
        while d < exp:
            if d.weekday() < 5:
                biz_remaining += 1
            d += timedelta(days=1)

        if biz_remaining <= 5:
            if len(candidate_months) > 1:
                cy, cm = candidate_months[1]
            else:
                # 다음 해 3월
                cy, cm = y + 1, 3

        return f"{cy}{cm:02d}"

    def _make_fut_contract(self, sym: str):
        """선물 종목용 FUT 계약 생성. front-month 만기 직접 지정."""
        from ibapi.contract import Contract as _C
        exch, cur, mult = self._FUT_UND_CFG.get(sym, ("SMART", "USD", ""))
        c = _C()
        c.symbol     = sym
        c.secType    = "FUT"
        c.exchange   = exch
        c.currency   = cur
        c.multiplier = mult

        if sym == "CL":
            c.lastTradeDateOrContractMonth = self._cl_front_month()
        elif sym == "ES":
            c.lastTradeDateOrContractMonth = self._es_front_month()
        else:
            from datetime import date
            today = date.today()
            c.lastTradeDateOrContractMonth = f"{today.year}{today.month:02d}"

        return c

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 장외 다음 거래일 만기 자동 선택
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    @staticmethod
    def _next_trading_day() -> str:
        """
        오늘 기준 다음 거래일을 'YYYYMMDD' 문자열로 반환.

        규칙:
          - 오늘이 평일(월~금)이고 장이 아직 열리지 않았으면 → 오늘
          - 오늘이 평일이고 장이 이미 끝났으면 → 다음 평일
          - 오늘이 주말이면 → 다음 월요일
        미국 공휴일은 별도 처리하지 않음 (combo_exp 목록에서 자동 필터됨).
        """
        from datetime import date, timedelta
        from core import is_market_open

        today = date.today()
        wd = today.weekday()  # 0=월 … 6=일

        # 주말이면 다음 월요일
        if wd == 5:   # 토
            return (today + timedelta(days=2)).strftime("%Y%m%d")
        if wd == 6:   # 일
            return (today + timedelta(days=1)).strftime("%Y%m%d")

        # 평일: 장이 열려 있으면 오늘, 장 마감 후면 내일(주말 건너뜀)
        if is_market_open():
            return today.strftime("%Y%m%d")

        # 장 마감 후 평일
        next_d = today + timedelta(days=1)
        while next_d.weekday() >= 5:   # 주말 건너뜀
            next_d += timedelta(days=1)
        return next_d.strftime("%Y%m%d")

    def _auto_select_next_expiry(self):
        """
        장외 /ES 구독 시 combo_exp(만기 콤보)를 다음 거래일 SPXW로
        자동 선택한다.

        흐름:
          1. _next_trading_day() 로 목표 날짜 계산
          2. combo_exp 항목 중 해당 날짜(code)와 일치하는 인덱스 탐색
          3. 일치 항목이 있으면 combo_exp.setCurrentIndex() 로 선택
          4. 없으면 로그만 출력 (수동 선택 안내)

        호출 위치: _req_und() 에서 /ES 전환 시 1초 후 QTimer.singleShot
        """
        if not getattr(self, '_und_is_futures', False):
            return  # 장중이면 실행 안 함

        # ★ _auto_fetch_spxw_today() 가 이미 오늘 날짜로 세팅했으면 덮어쓰지 않음
        # (연결 초기화 시 _req_und(300ms) → 타이머(1초=1300ms) 가
        #  _auto_fetch_spxw_today(2500ms) 보다 먼저 발화되어 내일 날짜로 바꾸는 버그 방지)
        if getattr(self, '_spxw_today_selected', False):
            return

        target = self._next_trading_day()

        # combo_exp 항목 탐색: _expiry_list = [(label, code, tag), ...]
        expiry_list = getattr(self, '_expiry_list', [])
        found_idx = -1
        for i, (label, code, tag) in enumerate(expiry_list):
            if code == target:
                found_idx = i
                break

        if found_idx < 0:
            self._log(
                f"🌙 장외 만기 자동 선택: {target} 항목 없음 "
                f"— 만기 콤보에서 직접 선택하세요.")
            return

        # combo_exp 에 반영
        if hasattr(self, 'combo_exp'):
            self.combo_exp.blockSignals(True)
            self.combo_exp.setCurrentIndex(found_idx)
            self.combo_exp.blockSignals(False)

        self._log(f"🌙 장외 만기 자동 선택: {target} (다음 거래일 SPXW)")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 기초자산 구독
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _req_und(self, sym: str):
        """
        기초자산 시세 구독.

        [장외 선물 전환 로직]
        - sym이 SPX/SPXW이고 is_market_open()==False 이면
          /ES 최근월물 FUT으로 대체 구독한다.
        - _und_is_futures=True 플래그를 설정하여 ChartMixin에서
          UI 뱃지("[/ES]")를 표시할 수 있게 한다.
        - 장중에는 항상 SPX 현물로 구독하고 플래그를 False로 복원한다.
        """
        sym = sym.upper().replace("SPXW", "SPX").replace("NANOS", "SPX")
        if not self.mw.connected:
            return

        # ── __init__ 미초기화 방어: 속성이 없으면 False로 보장 ──
        if not hasattr(self, '_und_is_futures'):
            self._und_is_futures = False

        from core import is_market_open

        # ── /ES 장외 전환 판단 ───────────────────────────────────
        use_futures = (sym in self._SPX_SYMS) and (not is_market_open())

        if use_futures:
            # /ES 선물 계약으로 전환
            contract = self._make_fut_contract("ES")
            self._und_is_futures = True
            exp_label = contract.lastTradeDateOrContractMonth
            self._log(f"🌙 장외 시간 — /ES 선물({exp_label}) 기초자산 전환")
            # 다음 거래일 만기 자동 선택 (1초 후: combo_exp 빌드 완료 후)
            # _next_expiry_timer 에 저장 → _on_watch_dbl 에서 취소 가능
            t_exp = getattr(self, '_next_expiry_timer', None)
            if t_exp is None:
                self._next_expiry_timer = QTimer(self)
                self._next_expiry_timer.setSingleShot(True)
                self._next_expiry_timer.timeout.connect(self._auto_select_next_expiry)
            else:
                self._next_expiry_timer.stop()
            self._next_expiry_timer.start(1000)
        elif sym in self._FUT_UND_CFG:
            # CL/GC 등 원래부터 선물 종목
            contract = self._make_fut_contract(sym)
            self._und_is_futures = True
            self._log(f"📌 {sym} 기초자산: FUT {contract.lastTradeDateOrContractMonth}")
        else:
            # 일반 현물 (SPX 장중, NDX, VIX 등)
            contract = make_und_contract(sym)
            self._und_is_futures = False

        # ── MDT 설정 + cancel → 딜레이 → reqMktData ─────────────
        _mdt_for_sym(sym, self.mw.ib)
        try:
            self.mw.ib.cancelMktData(REQ_UND)
        except:
            pass

        gen = getattr(self, '_und_gen', 0) + 1
        self._und_gen = gen

        def _send(g=gen, c=contract):
            if not _alive(self): return               # 위젯 파괴 방어
            if getattr(self, '_und_gen', 0) != g: return
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
        """
        장외 5초 타이머 콜백.

        [장외→장중 전환 감지]
        - 현재 _und_is_futures=True(선물 구독 중)이고 is_market_open()=True
          가 되면 → /ES 해제 후 SPX 현물로 재구독한다.
        - 장중이면 타이머를 중지한다(기존 동작 유지).
        - 선물 구독 중이고 가격이 이미 수신된 경우 → 재구독 스킵
          (5초마다 cancelMktData 반복으로 TWS 소켓 버퍼 누적 방지)
        """
        if not self.mw.connected:
            return

        from core import is_market_open

        if is_market_open():
            self._und_timer.stop()

            # 선물 구독 중이었다면 SPX 현물로 전환
            if getattr(self, '_und_is_futures', False):
                sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
                self._log(f"☀ 정규장 개장 — {sym} 현물로 전환합니다.")
                self._und_is_futures = False
                self.und_price = None
                self.und_prev  = None
                self._req_und(sym)
                if hasattr(self, 'lbl_und'):
                    self.lbl_und.setText("조회 중…")
            return

        # 장외: 선물 구독 중이고 가격이 이미 수신됐으면 재구독 불필요
        if getattr(self, '_und_is_futures', False) and self.und_price is not None:
            return

        # 장외: 아직 가격 미수신 → 재구독 시도
        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
        self._req_und(sym)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 이하 기존 코드 완전 보존
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

    def _fetch(self):
        if not _alive(self):
            return

        if getattr(self, '_fetch_busy', False):
            self._log("⚠ 구독 진행 중 — 중복 조회 요청 무시 (잠시 후 재시도)")
            return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "먼저 TWS에 연결하세요.")
            return
        if self.und_price is None:
            sym = self.edit_sym.text().strip().upper() or "SPX"
            retry = getattr(self, '_fetch_retry', 0)
            if retry >= 5:
                self._fetch_retry = 0
                self._log(f"⚠ 현재가 수신 실패 ({sym}) — TWS 연결 상태를 확인하세요.")
                return
            self._fetch_retry = retry + 1
            self._log(f"현재가 수신 중… ({sym}) 잠시 후 재시도합니다. ({self._fetch_retry}/5)")
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
        if not expiry:
            return
        sym = self.edit_sym.text().strip().upper() or "SPX"
        n   = self.spin_n.value()
        self._n_strikes = n

        from core import _resolve_spx_trading_class
        display_tc = (_resolve_spx_trading_class(sym, expiry, tag)
                      if sym in ("SPX", "SPXW") else sym)
        _, _, _, step = SYMBOL_CFG.get(
            sym if sym != "SPXW" else "SPX", DEFAULT_CFG)

        active_rids = list(self.call_data.keys()) + list(self.put_data.keys())
        cancel_ids  = [REQ_UND] + active_rids

        self._fetch_busy = True
        self._arm_fetch_timeout()
        self._log(f"{display_tc}  구독 초기화 중…  만기={expiry}  Zone={self._zone}  n={n}  cancel={len(cancel_ids)}건")

        gen = getattr(self, '_fetch_gen', 0) + 1
        self._fetch_gen = gen

        def _cancel_seq(idx):
            if self._fetch_gen != gen: return
            if not _alive(self): return
            if idx >= len(cancel_ids):
                QTimer.singleShot(300, _prepare_and_subscribe)
                return
            try:
                self.mw.ib.cancelMktData(cancel_ids[idx])
            except:
                pass
            QTimer.singleShot(80, lambda: _cancel_seq(idx + 1))

        def _prepare_and_subscribe():
            if self._fetch_gen != gen: return
            if not _alive(self): return
            self.call_data.clear()
            self.put_data.clear()
            if PG:
                self._prices.clear()
                self._deltas.clear()
                self._spreads.clear()

            # ── /ES → SPX ATM 보정 ──────────────────────────────
            # 장외 선물 구독 중일 때 /ES 가격과 SPX 현물 간 basis 차이를
            # 보정하여 ATM 행사가 오차를 줄인다.
            # basis ≈ 선물 - 현물 = +5pt (선물 프리미엄) → 차감
            raw_price = self.und_price
            if getattr(self, '_und_is_futures', False) and sym in self._SPX_SYMS:
                ES_BASIS_OFFSET = 5.0
                raw_price = self.und_price - ES_BASIS_OFFSET
                self._log(
                    f"📐 /ES→SPX ATM 보정: {self.und_price:,.2f} → "
                    f"{raw_price:,.2f} (basis -{ES_BASIS_OFFSET}pt)")

            atm = round(raw_price / step) * step
            self.call_strikes, self.put_strikes = \
                self._strikes_for_zone(atm, step, n)

            self._init_tbl(self.tbl_call, self.call_strikes)
            self._init_tbl(self.tbl_put,  self.put_strikes)

            # 100=옵션거래량, 101=OI, 104=히스토리컬IV, 106=IV
            ticks = "100,101,104,106"
            if self.call_strikes:
                _c0 = make_opt_contract_safe(sym, self.call_strikes[0], "C", expiry, tag)
                self._log(
                    f"계약: symbol={_c0.symbol} "
                    f"tc={getattr(_c0,'tradingClass','')} "
                    f"exch={_c0.exchange} ATM={atm}")

            call_reqs = []
            for i, st in enumerate(self.call_strikes):
                rid = REQ_CALL + i
                self.call_data[rid] = {"row": i}
                call_reqs.append((rid, make_opt_contract_safe(sym, st, "C", expiry, tag)))
            put_reqs = []
            for i, st in enumerate(self.put_strikes):
                rid = REQ_PUT + i
                self.put_data[rid] = {"row": i}
                put_reqs.append((rid, make_opt_contract_safe(sym, st, "P", expiry, tag)))

            all_reqs = []
            for i in range(max(len(call_reqs), len(put_reqs))):
                if i < len(call_reqs): all_reqs.append(call_reqs[i])
                if i < len(put_reqs):  all_reqs.append(put_reqs[i])

            self._req_und(sym)
            self._und_timer.start()
            total = len(all_reqs)

            def _send_req(idx):
                if self._fetch_gen != gen: return
                if not _alive(self): return
                if idx >= total:
                    self._fetch_busy = False
                    t = getattr(self, '_fetch_timeout_timer', None)
                    if t: t.stop()
                    self._log(f"✅ 구독 완료: 총 {total}개 계약")
                    if hasattr(self, 'lbl_status'):
                        self.lbl_status.setText("● 연결됨")
                        self.lbl_status.setStyleSheet(
                            "color:#00ff88;font-weight:bold;border:none;")
                    QTimer.singleShot(500, self._notify_sniper_sync)
                    return

                done = idx + 1
                if done % 5 == 0 or done == total:
                    self._log(f"구독 중… [{done}/{total}]")
                if hasattr(self, 'lbl_status'):
                    self.lbl_status.setText(f"● 로딩 [{done}/{total}]")
                    self.lbl_status.setStyleSheet(
                        "color:#7c7cff;font-weight:bold;border:none;")

                rid, contract = all_reqs[idx]

                def _do_req(r=rid, c=contract, next_idx=idx + 1):
                    if self._fetch_gen != gen: return
                    try:
                        self.mw.ib.reqMktData(r, c, ticks, False, False, [])
                    except Exception as e:
                        self._log(f"⚠ reqMktData 오류 rid={r}: {e}")
                    QTimer.singleShot(150, lambda: _send_req(next_idx))

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
        from call_put_tab.tab_options import _mk

        tbl.clearContents()
        tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r, 0, _mk(str(int(s)), "#ffd700"))
            for c in range(1, 6):
                tbl.setItem(r, c, _mk("―"))

    def _tbl_click(self, row, col, side):
        # ── 더블클릭 억제: Qt는 dblclick 직전에 click을 먼저 발화한다.
        #    _tbl_dbl 에서 플래그를 True 로 세우고 QTimer(0) 으로 리셋하므로,
        #    연속 click+dblclick 구분이 가능하다.
        if getattr(self, '_dbl_pending', False):
            return

        strikes = self.call_strikes if side == "C" else self.put_strikes
        if row >= len(strikes): return

        # ── 주문 패널용 가격·델타 조회 ──────────────────────────
        rid        = (REQ_CALL if side == "C" else REQ_PUT) + row
        data_dict  = (self.call_data if side == "C" else self.put_data)
        tick_entry = data_dict.get(rid, {})

        # ※ or 체인 대신 is None 체크: 가격이 0.0이면 or 체인에서 falsy로 건너뜀
        _p = tick_entry.get("last")
        if _p is None: _p = tick_entry.get("bid")
        if _p is None: _p = tick_entry.get("ask")
        cur_price = _p
        cur_delta = tick_entry.get("delta")

        if cur_price is None:
            tbl = self.tbl_call if side == "C" else self.tbl_put
            price_item = tbl.item(row, 1)
            if price_item:
                try:
                    cur_price = float(price_item.text())
                except:
                    pass
        if cur_delta is None:
            tbl = self.tbl_call if side == "C" else self.tbl_put
            delta_item = tbl.item(row, 3)
            if delta_item:
                try:
                    cur_delta = float(delta_item.text())
                except:
                    pass

        # ── 빠른 주문 패널에 행사가·가격·정보 전달 ──────────────
        self._qord_fill(side, str(int(strikes[row])), cur_price, source="← 테이블 클릭")

        # ── 감시 패널 행사가 동기화 ──────────────────────────────
        if hasattr(self, 'watch_side'):   self.watch_side.setText(side)
        if hasattr(self, 'watch_strike'): self.watch_strike.setText(str(int(strikes[row])))

        # ── 잔고 컬럼 클릭 시 포지션 매도 패널 ──────────────────
        if col == 6 and hasattr(self, '_show_pos_sell_panel'):
            tbl = self.tbl_call if side == "C" else self.tbl_put
            pos_item = tbl.item(row, 6)
            hold_qty = 0
            if pos_item:
                try:
                    hold_qty = int(pos_item.text())
                except:
                    pass
            if hold_qty > 0:
                self._show_pos_sell_panel(
                    side, str(int(strikes[row])), qty=hold_qty, price=cur_price)

        # ── 현재가 패널 옵션 정보 업데이트 ──────────────────────
        if hasattr(self, '_pp_opt_bid'):
            self._pp_opt_bid = None
            self._pp_opt_ask = None
        if hasattr(self, '_update_price_panel_opt'):
            self._update_price_panel_opt(
                side, str(int(strikes[row])), None, cur_price, cur_delta)

        # ── 스나이퍼 탭 타깃 동기화 ─────────────────────────────
        try:
            expiry_sn, _ = self._get_expiry()
            if expiry_sn and hasattr(self, 'set_sniper_target'):
                self.set_sniper_target(
                    strike=str(int(strikes[row])),
                    right=side,
                    expiry=expiry_sn,
                )
        except Exception:
            pass

        label = 'CALL' if side == 'C' else 'PUT'
        self._log(f"주문 패널 전달: {label} {int(strikes[row])}"
                  + (f"  가격={cur_price:.2f}" if cur_price else ""))

    def _tbl_dbl(self, row, col, side):
        """더블클릭 → 옵션 행사가 차트 스냅샷 조회.

        처리 순서:
          1. _dbl_pending 플래그 설정 → 선행 cellClicked(_tbl_click) 억제
          2. _chart_strike / _chart_side 확정
          3. 차트 실시간 버퍼 초기화 (탭0 깨끗하게 비움)
          4. 옵션 계약 스냅샷 히스토리 조회 (_fetch_option_snapshot)
          5. 차트 탭을 분봉(탭2) 또는 실시간(탭0)으로 전환
        """
        # ── 범위 체크를 플래그 설정 전에 수행 ───────────────────
        # _dbl_pending=True 설정 후 return 하면 _tbl_click 이 억제된 채
        # QTimer(0) 리셋도 발화되지 않아 이후 단클릭이 모두 무시된다.
        strikes = self.call_strikes if side == "C" else self.put_strikes
        if not strikes or row >= len(strikes):
            return

        # ── 더블클릭 억제 플래그: QTimer(0)으로 이벤트 루프 직후 리셋 ──
        self._dbl_pending = True
        QTimer.singleShot(0, lambda: setattr(self, '_dbl_pending', False))

        strike = strikes[row]
        label  = 'CALL' if side == 'C' else 'PUT'

        # ── _chart_strike 확정 ───────────────────────────────────
        self._chart_strike = strike
        self._chart_side   = side

        # ── 실시간 차트 버퍼 초기화 (탭0) ───────────────────────
        if PG:
            self._prices.clear()
            self._price_times.clear()
            self._deltas.clear()
            self._candle_bars.clear()
            self._candle_items.clear()
            self._redraw_candles()

        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(f"차트: {label}  {int(strike)}  📊 조회 중…")

        self._log(f"차트 더블클릭: {label} {int(strike)}  → 스냅샷 차트 조회")

        # ── 옵션 스냅샷 차트 조회 ────────────────────────────────
        self._fetch_option_snapshot(strike, side)

    # ── 옵션 스냅샷 차트 조회 ────────────────────────────────────
    # ── 옵션 스냅샷 차트용 reqId ────────────────────────────────
    # REQ_HIST(6000~6099) 범위 밖, REQ_SNIPER(7000~) 이전의 빈 공간 사용
    _OPT_SNAP_REQ = 6500

    def _fetch_option_snapshot(self, strike: float, side: str):
        """
        행사가·방향에 대한 옵션 분봉 히스토리를 스냅샷(1회) 방식으로 조회.

        chart_ibkr.py의 IbkrHistMixin 인프라(_ensure_hist_router, _poll_hist)를
        직접 재활용한다.

        흐름:
          1. _ensure_hist_router() — bridge.hist_bar / hist_end 시그널 라우터 등록
          2. _hist_router[6500] 슬롯 등록
          3. reqHistoricalData(keepUpToDate=False) 스냅샷 전송
          4. _poll_hist(10초 폴링) → on_done → _on_opt_snapshot_done()

        옵션 계약 IBKR 주의사항:
          - whatToShow = "TRADES"  (옵션은 BID_ASK/MIDPOINT 제한 있음)
          - useRTH = 0             (전체 세션, 0DTE는 장 전후 체결 포함)
          - barSizeSetting = "1 min"
          - durationStr = "1 D"    (당일 분봉)
          - endDateTime = ""       (현재 시각 기준 최신)
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

        # ── 이전 조회 취소 + 라우터 슬롯 초기화 ────────────────
        # keepUpToDate=True 실시간 스트림이 켜져 있으면 _hist_router[9801]이
        # 살아있어 _poll_hist 의 done 신호를 가로챌 수 있다 → 먼저 중지.
        if hasattr(self, '_stop_live'):
            self._stop_live()
        try:
            self.mw.ib.cancelHistoricalData(req)
        except Exception:
            pass
        if hasattr(self, '_hist_router'):
            self._hist_router.pop(req, None)

        # ── chart_ibkr.IbkrHistMixin 라우터 등록 ─────────────
        # _ensure_hist_router() 는 IbkrHistMixin에 정의되어 있다.
        # CallPutGrid 가 IbkrHistMixin 을 상속하므로 self 에서 호출 가능.
        self._ensure_hist_router()
        self._hist_router[req] = {"buf": [], "done": False, "is_daily": False}

        # ── 옵션 계약 생성 ───────────────────────────────────────
        contract = make_opt_contract_safe(sym, strike, side, expiry, tag)

        self._log(f"📊 옵션 스냅샷 조회: {label} {int(strike)}  만기={expiry}")
        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(
                f"차트: {label}  {int(strike)}  ⏳ 조회 중…")

        # ── MDT 임시 전환: 스냅샷 요청 전 현재 MDT 저장 후 4로 전환 ──
        # _current_mdt 는 core_conn.py 가 갱신하는 속성.
        # 없으면 auto_mdt()로 현재 값을 직접 계산하여 복원 기준으로 삼는다.
        _prev_mdt = getattr(self, '_current_mdt', None)
        if _prev_mdt is None:
            try:
                _prev_mdt = auto_mdt(self.mw.ib)
            except Exception:
                _prev_mdt = 3   # 안전 기본값: 지연
        try:
            self.mw.ib.reqMarketDataType(4)
        except Exception:
            pass

        # ── reqHistoricalData 전송 ───────────────────────────────
        try:
            self.mw.ib.reqHistoricalData(
                req,
                contract,
                "",          # endDateTime: 빈 문자열 = 현재 시각
                "1 D",       # durationStr
                "1 min",     # barSizeSetting
                "TRADES",    # whatToShow — 옵션은 TRADES가 가장 안정적
                0,           # useRTH: 0 = 전체 세션
                1,           # formatDate: 1 = yyyymmdd hh:mm:ss
                False,       # keepUpToDate: False = 스냅샷
                []           # chartOptions
            )
        except Exception as e:
            self._log(f"⚠ 옵션 reqHistoricalData 오류: {e}")
            if hasattr(self, 'chart_lbl'):
                self.chart_lbl.setText(f"차트: {label}  {int(strike)}  ❌ 요청 실패")
            self._hist_router.pop(req, None)
            # MDT 복원
            try:
                self.mw.ib.reqMarketDataType(_prev_mdt)
            except Exception:
                pass
            return

        # ── _poll_hist로 폴링 (10초 타임아웃) ────────────────────
        # chart_ibkr.py _poll_hist 시그니처:
        #   _poll_hist(self, req_id, on_done, lbl, on_timeout, ms=10_000)
        # lbl은 setText가 있는 객체이면 됨 — chart_lbl 또는 더미 객체 사용
        _lbl = getattr(self, 'chart_lbl', _DummyLabel())

        _strike_snap = strike   # 클로저 캡처용
        _side_snap   = side

        def _restore_mdt():
            """스냅샷 완료/실패 후 MDT를 이전 값으로 복원."""
            try:
                self.mw.ib.reqMarketDataType(_prev_mdt)
            except Exception:
                pass

        def _on_done_with_restore(bars):
            _restore_mdt()
            self._on_opt_snapshot_done(bars, _strike_snap, _side_snap)

        def _on_timeout_with_restore():
            _restore_mdt()
            self._on_opt_snapshot_timeout()

        self._poll_hist(
            req,
            _on_done_with_restore,
            _lbl,
            _on_timeout_with_restore,
            ms=10_000,
        )

    def _on_opt_snapshot_done(self, bars, strike: float, side: str):
        """스냅샷 조회 완료 — 분봉 탭(탭2) 렌더링 후 탭 전환.

        bars: List[dict]  {"t": timestamp, "o", "h", "l", "c", "v"}
          — chart_ibkr._parse_bar() 가 생성한 포맷.
          — _on_intra_done 은 내부에서 _bars_to_rows() 를 호출하므로 그대로 전달 가능.

        주의: _intra_cache_bars 를 옵션 봉으로 덮어쓰지 않는다.
              덮어쓰면 이후 기초자산 분봉 재조회 시 _redraw_intraday_cache 가
              옵션 봉 데이터로 잘못 렌더링된다.
        """
        label = 'CALL' if side == 'C' else 'PUT'

        if not bars:
            self._log(f"⚠ 옵션 스냅샷: 데이터 없음 ({label} {int(strike)})")
            if hasattr(self, 'chart_lbl'):
                self.chart_lbl.setText(
                    f"차트: {label}  {int(strike)}  ⚠ 데이터 없음")
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(0)   # 실시간 탭 유지
            return

        self._log(f"✅ 옵션 스냅샷: {label} {int(strike)}  {len(bars)}봉")

        if hasattr(self, 'chart_lbl'):
            self.chart_lbl.setText(
                f"차트: {label}  {int(strike)}  📊 {len(bars)}봉")

        # ── 분봉 탭(탭2) 렌더러 호출 ────────────────────────────
        # _on_intra_done(bars, sym, tf, maxbars) 시그니처 (chart_history.py 기준)
        # sym 자리에 옵션 레이블 전달 → lbl_intra_status 에 종목명 표시
        sym       = self.edit_sym.text().strip().upper() or "SPX"
        label_sym = f"{sym} {label} {int(strike)}"
        tf        = getattr(self, '_intra_cache_tf', 1)
        maxbars   = getattr(self, '_intra_cache_maxbars', 399)

        # ── _intra_cache_bars 백업·복원: 옵션 봉으로 덮어쓰기 방지 ──
        # _on_intra_done 내부에서 self._intra_cache_bars 를 갱신하지 않으므로
        # 실제로는 안전하지만, 혹시 구현이 바뀌어도 문제없도록 명시적 보호.
        _prev_cache = getattr(self, '_intra_cache_bars', None)
        _prev_sym   = getattr(self, '_intra_cache_sym', '')

        if hasattr(self, '_on_intra_done'):
            try:
                self._on_intra_done(bars, label_sym, tf, maxbars)
            except Exception as e:
                self._log(f"⚠ 옵션 차트 렌더링 오류: {e}")

        # 캐시 복원 — 기초자산 분봉 데이터 보존
        self._intra_cache_bars = _prev_cache
        self._intra_cache_sym  = _prev_sym

        # ── 분봉 탭으로 전환 ─────────────────────────────────────
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

    # ─────────────────────────────────────────────────────────
    _INDEX_SYMS = {"SPX", "NDX", "RUT", "VIX", "DJX", "XSP", "NQ", "ES", "MES", "MNQ"}

    def _on_watch_dbl(self, item):
        """더블클릭 → 종목 변경 + 옵션 테이블 전체 재조회 (스트림 구독).

        [크래시 방어 수정]
        1. _alive 체크: 위젯 파괴 후 콜백 진입 방어
        2. _und_timer 중지: 더블클릭 직후 _refresh_und 가 동시에
           _req_und 를 재호출하면 cancelMktData 중복 → 소켓 버퍼 누적
        3. _und_is_futures 리셋: 이전 /ES 구독 상태가 남아있으면
           새 종목 _req_und 에서 잘못된 선물 계약으로 분기될 수 있음
        4. _auto_select_next_expiry QTimer 취소: 이전 /ES 전환으로
           예약된 만기 자동 선택이 새 종목 선택 후 발화되면 만기 덮어쓰기
        """
        if not _alive(self):
            return

        sym = item.text().strip().upper().replace("SPXW", "SPX")

        if getattr(self, '_fetch_busy', False):
            self._log(f"⚠ 구독 진행 중 — {sym} 더블클릭 무시 (완료 후 재시도)")
            return

        self.edit_sym.setText(sym)
        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요.")
            return

        # ① _und_timer 즉시 중지 — _refresh_und 동시 실행 방지
        self._und_timer.stop()

        # ② 이전 /ES 상태 리셋 — 새 종목은 항상 현물부터 시도
        self._und_is_futures = False

        # ③ 예약된 만기 자동 선택 타이머 취소
        t_exp = getattr(self, '_next_expiry_timer', None)
        if t_exp is not None:
            t_exp.stop()

        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()):
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

        self.und_price = None
        self.lbl_und.setText("조회 중…")
        if hasattr(self, '_pp_switch_to_und'):
            self._pp_switch_to_und()

        self._req_und(sym)

        # ④ _req_und 내부에서 재예약된 만기 자동 선택 타이머 즉시 재취소
        # → 더블클릭 시 combo_exp 날짜가 강제 변경되는 버그 방지
        #   (_req_und 가 장외 감지 시 _next_expiry_timer.start(1000) 을 재호출하므로
        #    ③번 취소만으로는 부족하며, _req_und 호출 직후 한 번 더 취소해야 함)
        t_exp = getattr(self, '_next_expiry_timer', None)
        if t_exp is not None:
            t_exp.stop()

        t = getattr(self, '_watch_dbl_timer', None)
        if t is None:
            self._watch_dbl_timer = QTimer(self)
            self._watch_dbl_timer.setSingleShot(True)
            self._watch_dbl_timer.timeout.connect(self._fetch)
        else:
            self._watch_dbl_timer.stop()
        self._watch_dbl_timer.start(1000)

    def _on_watch_single_click(self, item):
        """단일클릭 → 기초자산 스냅샷만 조회."""
        sym = item.text().strip().upper().replace("SPXW", "SPX")

        if hasattr(self, 'edit_sym'):
            self.edit_sym.setText(sym)

        if sym in getattr(self, '_IBKR_EXPIRY_SYMS', set()) and self.mw.connected:
            if hasattr(self, '_refresh_expiry_list'):
                self._refresh_expiry_list()

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

        # ── _req_und 호출 전에 _und_is_futures 미리 결정 ────────
        # _req_und() 내부에서 플래그를 설정하지만,
        # 차트 조회(_fetch_intraday 등)가 즉시 이어지므로
        # 여기서 먼저 판단해서 설정해야 use_fut 조건이 올바르게 동작함.
        from core import is_market_open
        market_open = is_market_open()
        is_spx = sym in getattr(self, '_SPX_SYMS', {"SPX", "SPXW"})

        if not market_open and is_spx:
            self._und_is_futures = True
        else:
            self._und_is_futures = False

        self._req_und(sym)

        if PG:
            self._und_hist.clear()
            if hasattr(self, '_c_und'):
                self._c_und.setData([])

        if market_open:
            # 장중: 분봉 탭
            if hasattr(self, '_fetch_intraday'):
                self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(2)
            self._log(f"관심종목 선택: {sym}  (장 중 — 분봉 차트 조회)")
        else:
            # 장외: /ES 선물이면 선물 차트, 아니면 기존 Polygon/IBKR
            if hasattr(self, '_fetch_daily'):
                self._fetch_daily()
            if hasattr(self, '_fetch_intraday'):
                self._fetch_intraday()
            if hasattr(self, '_chart_tabs'):
                # SPX 장외 → 분봉 탭(/ES 히스토리) 바로 표시
                # 기타 종목 → 일봉 탭
                tab_idx = 2 if (is_spx and not market_open) else 1
                self._chart_tabs.setCurrentIndex(tab_idx)
            if is_spx:
                self._log(f"관심종목 선택: {sym}  (장 외 — /ES 선물 차트 조회)")
            else:
                self._log(f"관심종목 선택: {sym}  (장 외 — 일봉+분봉 차트 조회)")

    def on_tab_deactivate(self):
        old_gen = getattr(self, '_fetch_gen', 0)
        self._fetch_gen = old_gen + 1
        if getattr(self, '_fetch_busy', False):
            self._fetch_busy = False
            t = getattr(self, '_fetch_timeout_timer', None)
            if t:
                t.stop()
            self._log("⏸ 탭 비활성화 — 구독 루프 중단, _fetch_busy 해제")

    def on_tab_activate(self):
        if not getattr(getattr(self, 'mw', None), 'connected', False):
            return
        if getattr(self, 'und_price', None) is None:
            return
        if getattr(self, '_fetch_busy', False):
            return
        self._log("▶ 탭 활성화 — 체인 재구독")
        self._fetch()

    def _notify_sniper_sync(self):
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
        if r >= 0:
            self.watchlist.takeItem(r)

# ──────────────────────────────────────────────────────────────
# _DummyLabel — _poll_hist lbl 인자용 더미 (CoreFetchMixin 외부)
# ──────────────────────────────────────────────────────────────
class _DummyLabel:
    """chart_lbl 위젯이 없을 때 _poll_hist의 lbl 자리를 채우는 더미.
    setText 호출을 조용히 무시한다."""
    def setText(self, *_): pass