"""
chart_ibkr.py — IBKR reqHistoricalData fallback (v8.2)  [S10]

[S10] 변경사항:
  - _hist_what_rth(): Index(IND) 평일 whatToShow를 MIDPOINT → TRADES 로 변경
    · MIDPOINT는 SPX/IND@CBOE 에서 ERR 162 발생 (미지원)
    · 주말(BID_ASK)은 유지, 평일은 Index/STK 모두 TRADES 사용

[S9] 실시간 분봉(keepUpToDate=True) 지원 추가:
  - _ibkr_hist_live()   : 장중 실시간 분봉 요청
  - _ensure_live_slot() : bridge.hist_bar_update 슬롯 연결
  - _stop_live()        : 스트림 + 타이머 정지
  - _start_live_render_timer(): 500ms 스로틀 렌더

[S9 bugfix] pyqtgraph AxisItem TypeError 수정:
  - _parse_bar(): None/NaN 값 방어 추가
  - _ensure_live_slot(): upsert 전 None 포함 bar 필터링
  - _ibkr_hist_live(): 초기 배치 None 봉 필터링
  - _start_live_render_timer(): 렌더 전 유효 봉만 전달

롤백 기준 (v7.6):
  - keepUpToDate=False 고정
  - hist_bar_update 시그널 없음
  - _ibkr_hist_live / _stop_live 없음
"""

import math
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

_ET      = ZoneInfo("America/New_York")
_INDEX   = {"SPX", "SPXW", "NDX", "VIX", "RUT", "DJX", "XSP", "MID", "GSPC"}
_LIVE_ID = 9801


# VIX는 MIDPOINT, SPX/NDX 등 나머지 IND는 TRADES
# - VIX IND: 실제 체결(TRADES) 데이터 없음 → MIDPOINT 사용
# - SPX IND: MIDPOINT ERR 162 발생 → TRADES 사용
_VIX_SYMS = {"VIX"}

def _hist_what_rth(sym: str):
    """
    IBKR whatToShow 결정.

    종목별 지원 여부:
    - VIX (IND): TRADES 없음 → MIDPOINT 사용 (주말은 BID_ASK)
    - SPX/NDX 등 (IND): MIDPOINT ERR 162 → TRADES 사용
    - STK/ETF: TRADES 고정
    """
    sym_up = sym.upper()
    is_wkd = datetime.now(_ET).weekday() >= 5

    if is_wkd:
        is_idx = sym_up in _INDEX
        return ("BID_ASK" if is_idx else "TRADES"), 1

    # 평일
    if sym_up in _VIX_SYMS:
        return "MIDPOINT", 0   # VIX는 TRADES 미지원 → MIDPOINT
    return "TRADES", 0         # SPX/NDX 등 IND + STK/ETF


def _make_hist_contract(sym: str, is_weekend: bool = False,
                        use_futures: bool = False, fut_expiry: str = ""):
    """
    IBKR 히스토리 조회용 계약 생성.

    [장외 선물 차트 지원]
    use_futures=True 이면 FUT(/ES) 계약으로 생성한다.
    fut_expiry: 'YYYYMM' 형식 최근월물 만기 (비어있으면 현재 달)

    use_futures=False (기본): 기존 IND/STK 계약 그대로.
    """
    try:
        from ibapi.contract import Contract
    except ImportError:
        class Contract: pass

    sym_up = sym.upper().replace("SPXW", "SPX")
    c = Contract(); c.currency = "USD"; c.primaryExch = ""

    # ── /ES 선물 계약 ────────────────────────────────────────
    if use_futures and sym_up in ("SPX",):
        from datetime import date
        c.symbol   = "ES"
        c.secType  = "FUT"
        c.exchange = "CME"
        c.lastTradeDateOrContractMonth = (
            fut_expiry if fut_expiry
            else f"{date.today().year}{date.today().month:02d}"
        )
        return c

    # ── 기존 IND / STK 계약 ──────────────────────────────────
    if sym_up in _INDEX:
        c.symbol = sym_up; c.secType = "IND"
        c.exchange = "SMART" if is_weekend else "CBOE"
    else:
        c.symbol = sym_up; c.secType = "STK"; c.exchange = "SMART"
    return c


def _is_valid_bar(bar: dict) -> bool:
    """[S9 bugfix] bar dict의 숫자 필드에 None/NaN/Inf가 없는지 확인."""
    for k in ("o", "h", "l", "c", "v"):
        v = bar.get(k)
        if v is None:
            return False
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return False
        except (TypeError, ValueError):
            return False
    # timestamp 확인
    t = bar.get("t")
    if t is None:
        return False
    try:
        f = float(t)
        if math.isnan(f) or math.isinf(f):
            return False
    except (TypeError, ValueError):
        return False
    return True


def _parse_bar(bd: dict, is_daily: bool) -> dict:
    parts = bd["date"].split()
    if is_daily:
        t = datetime.strptime(parts[0], "%Y%m%d")
    else:
        tp = parts[1] if len(parts) >= 2 else "00:00:00"
        t  = datetime.strptime(f"{parts[0]} {tp}", "%Y%m%d %H:%M:%S")
    return {"t": t.timestamp(), "o": bd["open"], "h": bd["high"],
            "l": bd["low"], "c": bd["close"], "v": bd["volume"]}


class IbkrHistMixin:

    def _ensure_hist_router(self):
        """bridge.hist_bar / hist_end 슬롯 연결 (중복 방지)."""
        from core import bridge
        from PyQt5.QtCore import Qt
        for attr, sig in (('_hist_slot_bar', bridge.hist_bar),
                          ('_hist_slot_end', bridge.hist_end)):
            prev = getattr(self, attr, None)
            if prev:
                try: sig.disconnect(prev)
                except Exception: pass
        if not hasattr(self, '_hist_router'):
            self._hist_router = {}

        def _on_bar(rid, bd):
            s = self._hist_router.get(rid)
            if s:
                try:
                    bar = _parse_bar(bd, s["is_daily"])
                    # [S9 bugfix] None/NaN 포함 봉은 버퍼에 추가하지 않음
                    if _is_valid_bar(bar):
                        s["buf"].append(bar)
                except Exception as e: print(f"[hist bar] {e}")

        def _on_end(rid):
            s = self._hist_router.get(rid)
            if s: s["done"] = True

        bridge.hist_bar.connect(_on_bar, Qt.QueuedConnection)
        bridge.hist_end.connect(_on_end, Qt.QueuedConnection)
        self._hist_slot_bar = _on_bar; self._hist_slot_end = _on_end

    def _ensure_live_slot(self):
        """[S9] bridge.hist_bar_update 슬롯 — 한 번만 등록."""
        if getattr(self, '_live_slot_installed', False): return
        from core import bridge
        from PyQt5.QtCore import Qt
        self._live_buf = []; self._live_dirty = False

        def _on_update(rid, bd):
            if rid != _LIVE_ID: return
            try:
                bar = _parse_bar(bd, False)
                # [S9 bugfix] None/NaN 포함 봉 무시
                if not _is_valid_bar(bar):
                    return
                if self._live_buf and self._live_buf[-1]["t"] == bar["t"]:
                    self._live_buf[-1] = bar  # 같은 분봉 → 덮어쓰기
                else:
                    self._live_buf.append(bar)  # 새 분봉 → 추가
                self._live_dirty = True
            except Exception as e: print(f"[live update] {e}")

        bridge.hist_bar_update.connect(_on_update, Qt.QueuedConnection)
        self._live_slot_installed = True

    def _ibkr_hist(self, sym, duration, bar_size, req_id, on_done, lbl,
                   on_timeout=None, end_date_time: str = "",
                   use_futures: bool = False, fut_expiry: str = ""):
        """과거 분봉/일봉 조회 (keepUpToDate=False).

        [장외 선물 차트]
        use_futures=True 이면 /ES FUT 계약으로 요청한다.
        fut_expiry: 'YYYYMM' 최근월물 만기 문자열
        """
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요")
            if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            return
        self._ensure_hist_router()
        is_wkd = datetime.now(_ET).weekday() >= 5

        # 선물 조회 시 whatToShow = TRADES (FUT는 MIDPOINT/BID_ASK 미지원)
        if use_futures:
            what, use_rth = "TRADES", 0
        else:
            what, use_rth = _hist_what_rth(sym)

        is_daily = "day" in bar_size
        c = _make_hist_contract(sym, is_wkd,
                                use_futures=use_futures,
                                fut_expiry=fut_expiry)
        self._hist_router[req_id] = {"buf": [], "done": False, "is_daily": is_daily}

        sym_label = f"/ES({fut_expiry})" if use_futures else sym
        lbl.setText(f"⏳ IBKR {bar_size} 조회 중… {sym_label}")
        try: self.mw.ib.reqMarketDataType(4)
        except Exception: pass
        try:
            self.mw.ib.reqHistoricalData(req_id, c, end_date_time,
                duration, bar_size, what, use_rth, 1, False, [])
        except Exception as e:
            lbl.setText(f"❌ 요청 실패: {e}"); self._hist_router.pop(req_id, None)
            if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            return
        self._poll_hist(req_id, on_done, lbl, on_timeout)

    def _poll_hist(self, req_id, on_done, lbl, on_timeout, ms=10_000):
        """공통 폴링 타이머. QTimer에 부모(self) 지정 → 위젯 파괴 시 자동 정리."""
        elapsed = [0]
        timer = QTimer(self)   # ← 부모 지정: 위젯 파괴 시 자동 stop/delete
        timer.setInterval(50)
        def _poll():
            elapsed[0] += 50
            s = self._hist_router.get(req_id)
            if s is None:
                timer.stop(); timer.deleteLater(); return
            if s["done"]:
                timer.stop(); timer.deleteLater()
                buf = self._hist_router.pop(req_id, {}).get("buf", [])
                if buf: on_done(list(buf))
                else:
                    lbl.setText("❌ 데이터 없음")
                    if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            elif elapsed[0] >= ms:
                timer.stop(); timer.deleteLater()
                self._hist_router.pop(req_id, None)
                lbl.setText("❌ 타임아웃")
                if callable(on_timeout): QTimer.singleShot(0, on_timeout)
        timer.timeout.connect(_poll); timer.start()

    def _ibkr_hist_live(self, sym, bar_size, on_initial_done, lbl,
                        use_futures: bool = False, fut_expiry: str = ""):
        """[S9] 장중 실시간 분봉 (keepUpToDate=True).

        [장외 선물 지원]
        use_futures=True 이면 /ES FUT 계약으로 요청한다.
        whatToShow=TRADES, useRTH=0 강제 적용.
        """
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요"); return
        self._stop_live()
        self._ensure_hist_router(); self._ensure_live_slot()
        is_wkd = datetime.now(_ET).weekday() >= 5

        if use_futures:
            what, use_rth = "TRADES", 0
        else:
            what, use_rth = _hist_what_rth(sym)

        c = _make_hist_contract(sym, is_wkd,
                                use_futures=use_futures,
                                fut_expiry=fut_expiry)
        self._live_buf = []; self._live_dirty = False
        self._live_sym = f"/ES({fut_expiry})" if use_futures else sym
        self._hist_router[_LIVE_ID] = {"buf": [], "done": False, "is_daily": False}

        sym_label = f"/ES({fut_expiry})" if use_futures else sym
        lbl.setText(f"⏳ 실시간 {bar_size} 수신 중… {sym_label}")
        try: self.mw.ib.reqMarketDataType(4)
        except Exception: pass
        try:
            self.mw.ib.reqHistoricalData(_LIVE_ID, c, "", "1 D", bar_size,
                what, use_rth, 1, True, [])   # keepUpToDate=True
        except Exception as e:
            lbl.setText(f"❌ 실시간 요청 실패: {e}"); return

        elapsed = [0]; init_t = QTimer(self); init_t.setInterval(50)
        def _poll_init():
            elapsed[0] += 50
            s = self._hist_router.get(_LIVE_ID)
            if s is None: init_t.stop(); init_t.deleteLater(); return
            if s["done"]:
                init_t.stop(); init_t.deleteLater()
                self._live_buf = [b for b in s["buf"] if _is_valid_bar(b)]
                self._hist_router.pop(_LIVE_ID, None)
                if self._live_buf:
                    on_initial_done(list(self._live_buf))
                    lbl.setText(f"🟢 실시간 {bar_size} — {sym_label}  자동갱신 중")
                    self._start_live_render_timer(lbl)
                else:
                    lbl.setText("❌ 유효한 초기 데이터 없음")
            elif elapsed[0] >= 15_000:
                init_t.stop(); init_t.deleteLater()
                self._hist_router.pop(_LIVE_ID, None)
                lbl.setText("❌ 실시간 초기 로딩 타임아웃")
        init_t.timeout.connect(_poll_init); init_t.start()
        self._live_init_timer = init_t

    def _start_live_render_timer(self, lbl):
        """[S9] 500ms 스로틀 렌더. 탭 숨김 중엔 dirty만 유지, 복귀 시 on_tab_activate가 처리."""
        t = QTimer(); t.setInterval(500)
        def _render():
            if not self._live_dirty: return
            if not self._live_buf: return

            # ── 탭 가시성 체크: 콜-풋 탭(self) 자체가 숨겨진 상태면 스킵 ──
            # mini_chart_intra 대신 self(CallPutGrid)의 isVisible() 사용
            # → 내부 차트탭이 실시간/일봉 탭이어도 콜-풋 탭이 활성이면 렌더 허용
            try:
                if not self.isVisible():
                    return  # dirty 유지 → on_tab_activate()가 복귀 시 처리
            except Exception:
                pass  # isVisible 실패 시 렌더 허용 (안전 fallback)

            valid_bars = [b for b in self._live_buf if _is_valid_bar(b)]
            if not valid_bars:
                return

            self._live_dirty = False
            try:
                self._on_intra_done(valid_bars,
                    getattr(self, '_live_sym', ""),
                    getattr(self, '_intra_cache_tf', 1),
                    getattr(self, '_intra_cache_maxbars', 399))
            except Exception as e:
                lbl.setText(f"⚠ 실시간 렌더 오류: {e}")
                print(f"[live render] {e}")
        t.timeout.connect(_render); t.start()
        self._live_render_timer = t

    def _stop_live(self):
        """[S9] 실시간 스트림 + 타이머 정지."""
        for attr in ('_live_render_timer', '_live_init_timer'):
            t = getattr(self, attr, None)
            if t:
                try: t.stop()
                except Exception: pass
            setattr(self, attr, None)
        try:
            if getattr(self, 'mw', None) and self.mw.connected:
                self.mw.ib.cancelHistoricalData(_LIVE_ID)  # 9801만 cancel
        except Exception: pass
        # router 잔여분 정리 (_LIVE_ID + 과거 조회 9802)
        if hasattr(self, '_hist_router'):
            self._hist_router.pop(_LIVE_ID, None)
            self._hist_router.pop(9802, None)
        self._live_buf = []; self._live_dirty = False

    def _ibkr_tick_chart(self, sym, num_ticks, req_id, on_done, lbl,
                          on_timeout=None):
        """틱 차트 조회 (변경 없음)."""
        if not self.mw.connected:
            lbl.setText("❌ TWS/Gateway 연결 필요")
            if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            return
        is_wkd = datetime.now(_ET).weekday() >= 5
        c      = _make_hist_contract(sym, is_wkd)
        what   = "BID_ASK" if sym.upper() in _INDEX else "TRADES"
        lbl.setText(f"⏳ {num_ticks}틱 조회 중… {sym}")
        if not hasattr(self, '_tick_router'): self._tick_router = {}
        self._tick_router[req_id] = {"buf": [], "done": False}
        if not getattr(self, '_tick_router_installed', False):
            self._tick_router_installed = True
            from core import bridge
            from PyQt5.QtCore import Qt
            def _on_ticks(rid, ticks, done):
                s = self._tick_router.get(rid)
                if not s: return
                for t in ticks:
                    try: s["buf"].append({"t": float(t.time), "p": float(t.price), "s": int(t.size)})
                    except Exception: pass
                if done: s["done"] = True
            bridge.hist_ticks.connect(_on_ticks, Qt.QueuedConnection)
        try:
            self.mw.ib.reqHistoricalTicks(req_id, c, "", "", num_ticks, what, 1, True, [])
        except Exception as e:
            lbl.setText(f"❌ 틱 요청 실패: {e}"); self._tick_router.pop(req_id, None)
            if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            return
        elapsed = [0]
        timer = QTimer(self)   # 부모 지정
        timer.setInterval(50)
        def _poll():
            elapsed[0] += 50
            s = self._tick_router.get(req_id)
            if s is None: timer.stop(); timer.deleteLater(); return
            if s["done"]:
                timer.stop(); timer.deleteLater()
                buf = self._tick_router.pop(req_id, {}).get("buf", [])
                if buf: on_done(list(buf))
                else:
                    lbl.setText("❌ 틱 데이터 없음")
                    if callable(on_timeout): QTimer.singleShot(0, on_timeout)
            elif elapsed[0] >= 10_000:
                timer.stop(); timer.deleteLater()
                self._tick_router.pop(req_id, None)
                lbl.setText("❌ 틱 타임아웃")
                if callable(on_timeout): QTimer.singleShot(0, on_timeout)
        timer.timeout.connect(_poll); timer.start()