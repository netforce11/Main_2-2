"""
chart_ibkr.py — IBKR reqHistoricalData fallback (v7.6)
핵심 수정:
  이전 버전의 근본 문제:
    bridge.hist_end 는 Qt.QueuedConnection → 메인 Qt 이벤트 루프에서만 실행됨.
    백그라운드 스레드에서 threading.Event().wait() 로 폴링하면
    Qt 이벤트 루프가 그 스레드에서 돌지 않으므로 _on_end 가 영원히 호출 안 됨.
    → done_evt.set() 이 절대 안 걸림 → 10초 후 "데이터 없음" 으로만 끝남.

  해결:
    백그라운드 스레드 제거.
    reqHistoricalData 호출 후 QTimer(50ms) 로 메인 스레드에서 버퍼를 폴링.
    Qt 이벤트 루프가 계속 돌므로 bridge.hist_bar/hist_end 슬롯이 정상 실행됨.
"""

from datetime import datetime

from PyQt5.QtCore import QTimer

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

_ET    = ZoneInfo("America/New_York")
_INDEX = {"SPX", "SPXW", "NDX", "VIX", "RUT", "DJX", "XSP", "MID", "GSPC"}


def _hist_what_rth(sym: str):
    """
    요청 시점(ET 기준) → (whatToShow, useRTH).
    주말: IND → BID_ASK + 1 / STK → TRADES + 1
    평일: IND → MIDPOINT + 0  / STK → TRADES + 0
    """
    is_idx     = sym.upper() in _INDEX
    is_weekend = datetime.now(_ET).weekday() >= 5
    if is_weekend:
        return ("BID_ASK" if is_idx else "TRADES"), 1
    return ("MIDPOINT" if is_idx else "TRADES"), 0


def _make_hist_contract(sym: str, is_weekend: bool = False):
    """
    히스토리 전용 contract.
    주말 IND → exchange=SMART  (CBOE 지정 시 ERR 200)
    평일 IND → exchange=CBOE
    STK      → exchange=SMART
    primaryExch 는 항상 빈 문자열.
    """
    try:
        from ibapi.contract import Contract
    except ImportError:
        class Contract:
            pass

    sym_up = sym.upper().replace("SPXW", "SPX")
    c = Contract()
    c.currency    = "USD"
    c.primaryExch = ""

    if sym_up in _INDEX:
        c.symbol   = sym_up
        c.secType  = "IND"
        c.exchange = "SMART" if is_weekend else "CBOE"
    else:
        c.symbol   = sym_up
        c.secType  = "STK"
        c.exchange = "SMART"

    return c


class IbkrHistMixin:

    def _ensure_hist_router(self):
        """
        bridge.hist_bar / bridge.hist_end 에 슬롯 연결.
        재연결(IBapi 재생성) 시에도 슬롯이 중복 누적되지 않도록
        기존 슬롯을 먼저 disconnect 후 재연결한다.
        """
        from core import bridge
        from PyQt5.QtCore import Qt

        # 이전에 연결된 슬롯이 있으면 먼저 해제
        prev_bar = getattr(self, '_hist_slot_bar', None)
        prev_end = getattr(self, '_hist_slot_end', None)
        if prev_bar is not None:
            try: bridge.hist_bar.disconnect(prev_bar)
            except Exception: pass
        if prev_end is not None:
            try: bridge.hist_end.disconnect(prev_end)
            except Exception: pass

        if not hasattr(self, '_hist_router'):
            self._hist_router = {}

        def _on_bar(req_id, bar_dict):
            slot = self._hist_router.get(req_id)
            if slot is None:
                return
            try:
                parts = bar_dict["date"].split()
                if slot["is_daily"]:
                    t = datetime.strptime(parts[0], "%Y%m%d")
                else:
                    date_part = parts[0]
                    time_part = parts[1] if len(parts) >= 2 else "00:00:00"
                    t = datetime.strptime(f"{date_part} {time_part}", "%Y%m%d %H:%M:%S")
                slot["buf"].append({
                    "t": t.timestamp(),
                    "o": bar_dict["open"],  "h": bar_dict["high"],
                    "l": bar_dict["low"],   "c": bar_dict["close"],
                    "v": bar_dict["volume"],
                })
            except Exception as e:
                print(f"[hist bar parse] {bar_dict.get('date','?')!r}: {e}")

        def _on_end(req_id):
            slot = self._hist_router.get(req_id)
            if slot is not None:
                slot["done"] = True

        bridge.hist_bar.connect(_on_bar, Qt.QueuedConnection)
        bridge.hist_end.connect(_on_end, Qt.QueuedConnection)

        # 슬롯 참조 보관 → 다음 호출 시 disconnect에 사용
        self._hist_slot_bar = _on_bar
        self._hist_slot_end = _on_end
        self._hist_router_installed = True

    def _ibkr_hist(self, sym, duration, bar_size, req_id, on_done, lbl,
                   on_timeout=None, end_date_time: str = ""):
        """
        reqHistoricalData (v7.7)

        흐름:
          1. reqMarketDataType(4) 강제 (주말 분봉 권한)
          2. reqHistoricalData 호출
          3. QTimer(50ms) 로 메인 스레드에서 done 플래그 폴링
             → Qt 이벤트 루프가 계속 돌므로 bridge 슬롯 정상 실행
          4. done=True 되면 버퍼 전달 / 10초 초과 시 타임아웃

        end_date_time: "YYYYMMDD HH:MM:SS US/Eastern" 형식.
                       비어있으면("") IBKR 기본(현재 시각) 기준.
                       Feature 1: 캘린더 날짜 선택 조회 시 사용.
        """
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요")
            if callable(on_timeout):
                QTimer.singleShot(0, on_timeout)
            return

        # 슬롯 재등록 — 재연결(IBapi 재생성) 후에도 중복 없이 최신 슬롯 유지
        self._ensure_hist_router()

        is_weekend    = datetime.now(_ET).weekday() >= 5
        what, use_rth = _hist_what_rth(sym)
        is_daily      = "day" in bar_size
        contract      = _make_hist_contract(sym, is_weekend)

        # 이전 동일 req_id 잔류 슬롯 정리
        self._hist_router.pop(req_id, None)
        self._hist_router[req_id] = {"buf": [], "done": False, "is_daily": is_daily}

        rth_tag = "RTH" if use_rth else "ALL"
        date_tag = f"  [{end_date_time[:8]}]" if end_date_time else ""
        lbl.setText(f"⏳ IBKR {bar_size} ({what}/{rth_tag}) 조회 중… {sym}{date_tag}")

        # ① Frozen 데이터 타입 강제 (주말 분봉 핵심)
        try:
            self.mw.ib.reqMarketDataType(4)
        except Exception:
            pass

        # ② 연결 상태 이중 확인 — mw.connected는 2초 타이머 기반이라 끊긴 직후 오판 가능
        try:
            if not self.mw.ib.isConnected():
                lbl.setText("❌ TWS 연결 끊김 — 재연결 후 시도")
                self._hist_router.pop(req_id, None)
                if callable(on_timeout):
                    QTimer.singleShot(0, on_timeout)
                return
        except Exception:
            pass

        # ③ 히스토리 요청 (end_date_time 반영)
        try:
            self.mw.ib.reqHistoricalData(
                req_id, contract,
                end_date_time,   # "" → 현재 / "YYYYMMDD 23:59:59 US/Eastern" → 특정 날짜
                duration, bar_size, what,
                use_rth, 1, False, [])
        except Exception as e:
            lbl.setText(f"❌ IBKR 요청 실패: {e}")
            self._hist_router.pop(req_id, None)
            if callable(on_timeout):
                QTimer.singleShot(0, on_timeout)
            return

        # ③ QTimer 폴링 — 메인 스레드에서 50ms 마다 done 체크
        elapsed = [0]
        TIMEOUT_MS = 10_000   # 10초

        timer = QTimer()
        timer.setInterval(50)

        def _poll():
            elapsed[0] += 50
            slot = self._hist_router.get(req_id)
            if slot is None:
                timer.stop()
                return

            if slot["done"]:
                timer.stop()
                buf = self._hist_router.pop(req_id, {}).get("buf", [])
                if buf:
                    on_done(list(buf))
                else:
                    lbl.setText("❌ IBKR 데이터 없음")
                    if callable(on_timeout):
                        QTimer.singleShot(0, on_timeout)
                return

            if elapsed[0] >= TIMEOUT_MS:
                timer.stop()
                self._hist_router.pop(req_id, None)
                lbl.setText("❌ IBKR 타임아웃")
                if callable(on_timeout):
                    QTimer.singleShot(0, on_timeout)

        timer.timeout.connect(_poll)
        timer.start()

    def _ibkr_tick_chart(self, sym, num_ticks, req_id, on_done, lbl,
                          on_timeout=None):
        """
        reqHistoricalTicks — 틱 차트 (20틱 등) 조회.
        IBKR API: reqHistoricalTicks(reqId, contract, startDateTime,
                  endDateTime, numberOfTicks, whatToShow, useRth,
                  ignoreSize, miscOptions)
        - numberOfTicks: 최대 1000 (IBKR 제한)
        - whatToShow: "TRADES" (주식/ETF) / "BID_ASK" (지수)
        - 결과: historicalTicks / historicalTicksBidAsk 콜백
        bridge.hist_tick_done(reqId, ticks) 로 전달.
        """
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요")
            if callable(on_timeout):
                QTimer.singleShot(0, on_timeout)
            return

        # 연결 이중 확인
        try:
            if not self.mw.ib.isConnected():
                lbl.setText("❌ TWS 연결 끊김")
                if callable(on_timeout):
                    QTimer.singleShot(0, on_timeout)
                return
        except Exception:
            pass

        is_weekend = datetime.now(_ET).weekday() >= 5
        contract   = _make_hist_contract(sym, is_weekend)
        is_idx     = sym.upper() in _INDEX
        what       = "BID_ASK" if is_idx else "TRADES"

        lbl.setText(f"⏳ IBKR {num_ticks}틱 조회 중… {sym}")

        # 틱 버퍼 (req_id 기반)
        if not hasattr(self, '_tick_router'):
            self._tick_router = {}
        self._tick_router[req_id] = {"buf": [], "done": False}

        # bridge에 틱 콜백 슬롯 연결 (한 번만)
        if not getattr(self, '_tick_router_installed', False):
            self._tick_router_installed = True
            from core import bridge
            from PyQt5.QtCore import Qt

            def _on_hist_ticks(req_id_t, ticks, done_flag):
                slot = self._tick_router.get(req_id_t)
                if slot is None:
                    return
                for t in ticks:
                    try:
                        slot["buf"].append({
                            "t": float(t.time),
                            "p": float(t.price),
                            "s": int(t.size),
                        })
                    except Exception:
                        pass
                if done_flag:
                    slot["done"] = True

            # historicalTicks (TRADES)
            bridge.hist_ticks.connect(_on_hist_ticks, Qt.QueuedConnection)

        try:
            self.mw.ib.reqHistoricalTicks(
                req_id, contract,
                "",    # startDateTime: 비워두면 현재 기준 역방향
                "",    # endDateTime: 현재
                num_ticks,
                what,
                1,     # useRth
                True,  # ignoreSize
                [],    # miscOptions
            )
        except Exception as e:
            lbl.setText(f"❌ 틱 요청 실패: {e}")
            self._tick_router.pop(req_id, None)
            if callable(on_timeout):
                QTimer.singleShot(0, on_timeout)
            return

        # QTimer 폴링
        elapsed = [0]
        TIMEOUT_MS = 10_000
        timer = QTimer()
        timer.setInterval(50)

        def _poll_tick():
            elapsed[0] += 50
            slot = self._tick_router.get(req_id)
            if slot is None:
                timer.stop(); return
            if slot["done"]:
                timer.stop()
                buf = self._tick_router.pop(req_id, {}).get("buf", [])
                if buf:
                    on_done(list(buf))
                else:
                    lbl.setText("❌ 틱 데이터 없음")
                    if callable(on_timeout):
                        QTimer.singleShot(0, on_timeout)
                return
            if elapsed[0] >= TIMEOUT_MS:
                timer.stop()
                self._tick_router.pop(req_id, None)
                lbl.setText("❌ 틱 조회 타임아웃")
                if callable(on_timeout):
                    QTimer.singleShot(0, on_timeout)

        timer.timeout.connect(_poll_tick)
        timer.start()