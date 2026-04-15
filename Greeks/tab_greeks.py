# tab_greeks.py  — GreeksGrid 메인 탭
# Python 3.8 호환  |  S11 patch 기준
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from PyQt5.QtCore    import QTimer, Qt
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
                              QLabel, QPushButton, QComboBox, QSlider,
                              QSplitter, QTableWidget, QLineEdit)
import greeks_db as gdb
from greeks_render  import init_table, init_row, render_rows
from greeks_chart   import GexSkewPanel, NormalBandPanel
from greeks_replay  import ReplayPanel
from greeks_context import ContextDetector
from core import (router, REQ_CHAIN, REQ_CHAIN_P,
                  make_opt_contract, build_expiry_list, SYMBOL_CFG, DEFAULT_CFG)

log = logging.getLogger(__name__)

THROTTLE_MS          = 300
AUTOSAVE_MS          = 60_000
NEXT_EXPIRY_DELAY_MS = 600_000   # 장 시작 10분 후 내일 만기 요청
ATM_WING             = 10        # ATM ± 10  [S10 축소: ±15→±10, 62→42개]
SNAPSHOT_MODE        = True       # [S10] True=snapshot(1회수신후해제), False=스트림

# Greeks 전용 reqId 블록 (core.py 기준)
# REQ_CHAIN   = 4000  콜  4000~4199  (200개 = ATM±15×콜풋 = 62개 여유 충분)
# REQ_CHAIN_P = 4200  풋  4200~4399
# 내일 만기 스냅샷용 블록: 4400~4599 (콜), 4600~4799 (풋)
REQ_NEXT_C = REQ_CHAIN_P + 200   # 4400
REQ_NEXT_P = REQ_CHAIN_P + 400   # 4600


class GreeksGrid(QWidget):
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self._main    = main_win          # ib는 매번 참조 (재연결 시 교체되므로)
        self._callput = getattr(main_win, "tab_callput", None)
        # 상태
        self._cell_data: Dict[Tuple, dict] = {}
        self._prev_data: Dict[Tuple, dict] = {}
        self._sym       = "SPX"
        self._expiry    = ""
        self._tag       = ""
        self._und_price = 0.0
        self._day       = date.today().strftime("%Y%m%d")
        self._conn      = gdb.open_db(self._day)
        self._econn     = gdb.open_events_db()
        self._ctx       = ContextDetector()
        # reqId 카운터 (블록 내에서 순차 할당)
        self._rid_c  = REQ_CHAIN      # 콜 현재만기
        self._rid_p  = REQ_CHAIN_P    # 풋 현재만기
        self._rid_nc = REQ_NEXT_C     # 콜 내일만기
        self._rid_np = REQ_NEXT_P     # 풋 내일만기
        # reqId → (strike, side, expiry) 맵
        self._req_map:  Dict[int, Tuple] = {}
        self._next_map: Dict[int, Tuple] = {}
        self._flush_t = QTimer(self)
        self._flush_t.setSingleShot(True)
        self._flush_t.timeout.connect(self._flush)
        self._build()
        self._connect_signals()
        self._refresh_expiry()           # 앱 시작 시 만기 목록 자동 채우기
        QTimer.singleShot(NEXT_EXPIRY_DELAY_MS, self._fetch_next_expiry)

    # ── UI ───────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.addLayout(self._build_ctrl())
        tabs = QTabWidget()
        rt = QWidget(); rt_v = QVBoxLayout(rt)
        sp = QSplitter(Qt.Horizontal)
        self._table = QTableWidget()
        init_table(self._table)
        sp.addWidget(self._table)
        rsp = QSplitter(Qt.Vertical)
        self._gex  = GexSkewPanel()
        self._band = NormalBandPanel()
        rsp.addWidget(self._gex); rsp.addWidget(self._band)
        sp.addWidget(rsp)
        rt_v.addWidget(sp)
        self._banner = QLabel("")
        self._banner.setStyleSheet("color:orange;font-weight:bold;")
        rt_v.addWidget(self._banner)
        tabs.addTab(rt, "📡 실시간")
        tabs.addTab(ReplayPanel(), "⏪ 리플레이")
        root.addWidget(tabs)
        for ms, slot in [(AUTOSAVE_MS, self._autosave), (60_000, self._update_band)]:
            t = QTimer(self); t.timeout.connect(slot); t.start(ms)

    def _build_ctrl(self) -> QHBoxLayout:
        hb = QHBoxLayout()
        self._sym_cb = QComboBox()
        self._sym_cb.addItems(list(SYMBOL_CFG.keys()))
        self._sym_cb.setCurrentText("SPX")
        self._sym_cb.currentTextChanged.connect(self._on_sym_changed)
        self._exp_cb = QComboBox()           # build_expiry_list() 로 자동 채움
        self._exp_cb.setMinimumWidth(110)
        btn = QPushButton("조회"); btn.clicked.connect(self._fetch)
        btn_ref = QPushButton("만기갱신"); btn_ref.clicked.connect(self._refresh_expiry)
        # 직접입력용 QLineEdit (CUSTOM 선택 시만 활성화)
        self._exp_edit = QLineEdit(); self._exp_edit.setPlaceholderText("YYYYMMDD")
        self._exp_edit.setMaximumWidth(90); self._exp_edit.setVisible(False)
        self._exp_cb.currentIndexChanged.connect(self._on_expiry_changed)
        self._delta_sl = QSlider(Qt.Horizontal)
        self._delta_sl.setRange(0, 100)
        self._delta_sl.valueChanged.connect(self._apply_delta_filter)
        hb.addWidget(QLabel("심볼")); hb.addWidget(self._sym_cb)
        hb.addWidget(QLabel("만기")); hb.addWidget(self._exp_cb)
        hb.addWidget(self._exp_edit)
        hb.addWidget(btn); hb.addWidget(btn_ref)
        hb.addWidget(QLabel("Delta 필터")); hb.addWidget(self._delta_sl)
        hb.addStretch()
        hb.addWidget(QLabel(f"저장: {gdb.GREEKS_DIR}"))
        return hb

    def _connect_signals(self):
        # core.TickRouter: register_price/option(rid_start, rid_end, slot)
        router.register_price(1, 1, self._on_tick_price)          # REQ_UND=1
        router.register_option(REQ_CHAIN,  REQ_CHAIN_P + 199, self._on_tick_opt)
        router.register_option(REQ_NEXT_C, REQ_NEXT_P  + 199, self._on_tick_opt)
        # IBKR 에러 + raw tick_option 감시 (디버그용)
        from core import bridge
        bridge.error_sig.connect(self._on_ibkr_error)
        bridge.tick_option.connect(self._on_raw_tick_option)

    def _on_ibkr_error(self, req_id: int, error_code: int, msg: str):
        if req_id in self._req_map:
            print(f"[Greeks] ❌ IBKR 에러 reqId={req_id} code={error_code}: {msg}")
            self._banner.setText(f"❌ IBKR 에러 {error_code}: {msg}")

    def _on_raw_tick_option(self, req_id: int, tick_type: int,
                             iv: float, delta: float, op: float,
                             gamma: float, vega: float, theta: float):
        """bridge.tick_option 원시 수신 — Greeks reqId 범위만 첫 10개 출력"""
        if REQ_CHAIN <= req_id <= REQ_CHAIN_P + 199:
            if not hasattr(self, '_raw_tick_count'):
                self._raw_tick_count = 0
            if self._raw_tick_count < 10:
                print(f"[Greeks] raw tick reqId={req_id} tt={tick_type} iv={iv:.4f} delta={delta:.4f}")
                self._raw_tick_count += 1

    # ── 만기 목록 ────────────────────────────────────────
    def _refresh_expiry(self):
        """build_expiry_list()로 만기 ComboBox 자동 채우기"""
        try:
            exps = build_expiry_list(self._sym)   # ["20260414", "20260416", ...]
        except Exception as e:
            log.error("[GreeksGrid] build_expiry_list 오류: %s", e)
            return
        self._exp_cb.blockSignals(True)
        self._exp_cb.clear()
        for e in exps:
            # build_expiry_list → (label, YYYYMMDD, tag) 3-튜플
            label, code, tag = e[0], e[1], e[2]
            self._exp_cb.addItem(label, userData=code)
        self._exp_cb.blockSignals(False)
        if self._exp_cb.count():
            self._exp_cb.setCurrentIndex(0)
        log.info("[GreeksGrid] 만기 목록 갱신: %d개", self._exp_cb.count())

    def _on_sym_changed(self, sym: str):
        self._sym = sym
        self._refresh_expiry()

    def _on_expiry_changed(self, idx: int):
        """CUSTOM 선택 시 직접입력 QLineEdit 표시"""
        code = self._exp_cb.currentData()
        self._exp_edit.setVisible(code == "CUSTOM")

    def _current_expiry(self) -> tuple:
        """ComboBox에서 선택된 (YYYYMMDD, tag) 반환"""
        code = self._exp_cb.currentData() or ""
        if code == "CUSTOM":
            return self._exp_edit.text().strip(), ""
        # userData = code(YYYYMMDD), tag는 addItem 시 저장 안 됨 → expiry로 추론
        idx  = self._exp_cb.currentIndex()
        text = self._exp_cb.currentText()
        tag  = "0DTE" if "0DTE" in text else "W" if "[W]" in text else "M" if "[M]" in text else ""
        return code, tag

    # ── 조회 ────────────────────────────────────────────
    def _fetch(self):
        self._sym           = self._sym_cb.currentText()
        self._expiry, self._tag = self._current_expiry()
        print(f"[Greeks] 조회 시작 sym={self._sym} expiry={self._expiry} tag={self._tag} und={self._und_price}")
        if not self._expiry:
            msg = "만기 미선택 — 만기갱신 버튼을 누르세요"
            self._banner.setText(f"⚠ {msg}"); log.warning("[GreeksGrid] %s", msg); return
        if self._und_price <= 0:
            msg = f"⚠ 기초자산 가격 미수신 (und={self._und_price}) — IBKR 연결 확인"
            self._banner.setText(msg); print(f"[Greeks] {msg}"); return
        # 기존 구독 reqId 초기화
        self._req_map.clear()
        self._rid_c = REQ_CHAIN
        self._rid_p = REQ_CHAIN_P
        cfg  = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step = cfg[3]
        strikes = self._calc_strikes(self._und_price, ATM_WING, step)
        # [S10] 기존 구독 먼저 모두 취소 (재조회 시 중복 방지)
        for rid in list(self._req_map.keys()):
            try: self._main.ib.cancelMktData(rid)
            except Exception: pass

        ok = 0; fail = 0
        # [S10] SNAPSHOT_MODE=True → snapshot=True(1회수신후자동해제)
        #       티커 한도 소비 없음 — Max tickers 오류 해결
        snap = SNAPSHOT_MODE
        for s in strikes:
            for side, counter_attr, end in [
                    ("C", "_rid_c", REQ_CHAIN_P   - 1),
                    ("P", "_rid_p", REQ_CHAIN_P + 199)]:
                rid = getattr(self, counter_attr)
                if rid > end:
                    log.warning("[GreeksGrid] reqId 블록 초과 side=%s", side); continue
                self._req_map[rid] = (s, side, self._expiry)
                setattr(self, counter_attr, rid + 1)
                try:
                    self._main.ib.reqMktData(
                        rid,
                        make_opt_contract(self._sym, s, side, self._expiry, self._tag),
                        "", snap, False, [])
                    ok += 1
                except Exception as e:
                    log.error("[GreeksGrid] reqMktData 오류 %s %s: %s", s, side, e)
                    fail += 1

        atm_check = round(self._und_price / (cfg[3] if cfg[3] else 5)) * (cfg[3] if cfg[3] else 5)
        mode_str  = "📸 스냅샷" if snap else "📡 스트림"
        msg = (f"{mode_str} {self._sym} {self._expiry} | ATM={atm_check} ±{ATM_WING} | "
               f"요청 {ok}건" + (f" (실패 {fail}건)" if fail else ""))
        self._banner.setText(msg)
        print(f"[Greeks] {msg}")
        print(f"[Greeks] reqId 범위: 콜={REQ_CHAIN}~{self._rid_c-1} 풋={REQ_CHAIN_P}~{self._rid_p-1}")
        print(f"[Greeks] router 등록 범위: option {REQ_CHAIN}~{REQ_CHAIN_P+199}")
        print(f"[Greeks] strikes 샘플: {strikes[:3]}...{strikes[-3:]}")
        print(f"[Greeks] SNAPSHOT_MODE={snap}  ATM_WING=±{ATM_WING}  총={ok}개")

    def _fetch_next_expiry(self):
        """장 시작 10분 후 — 내일 만기 ATM ± 15 스냅샷 요청 후 3초 뒤 cancel"""
        nxt = self._next_trading_expiry()
        if not nxt:
            log.info("[GreeksGrid] 내일 만기 없음"); return
        if self._und_price <= 0:
            log.warning("[GreeksGrid] 내일 만기 스킵 — 기초자산 미수신"); return
        self._next_map.clear()
        self._rid_nc = REQ_NEXT_C; self._rid_np = REQ_NEXT_P
        cfg  = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step = cfg[3]
        log.info("[GreeksGrid] 내일 만기 요청: %s ±%d", nxt, ATM_WING)
        for s in self._calc_strikes(self._und_price, ATM_WING, step):
            for side, counter_attr, end in [
                    ("C", "_rid_nc", REQ_NEXT_P   - 1),
                    ("P", "_rid_np", REQ_NEXT_P + 199)]:
                rid = getattr(self, counter_attr)
                if rid > end: continue
                self._next_map[rid] = (s, side, nxt)
                setattr(self, counter_attr, rid + 1)
                try:
                    self._main.ib.reqMktData(
                        rid, make_opt_contract(self._sym, s, side, nxt, ""),
                        "", False, False, [])
                except Exception as e:
                    log.error("[GreeksGrid] 내일만기 reqMktData 오류: %s", e)
        QTimer.singleShot(3000, self._cancel_next_expiry)

    def _cancel_next_expiry(self):
        for rid in list(self._next_map):
            try: self._main.ib.cancelMktData(rid)
            except Exception: pass
        log.info("[GreeksGrid] 내일 만기 cancel (%d건)", len(self._next_map))
        self._next_map.clear()

    # ── Tick ────────────────────────────────────────────
    # core._route_price  → slot(rid, tt, price)
    def _on_tick_price(self, req_id: int, tick_type: int, price: float):
        if price and price > 0:
            self._und_price = price

    # core._route_option → slot(rid, tt, iv, delta, op, gamma, vega, theta)
    def _on_tick_opt(self, req_id: int, tick_type: int,
                     iv: float, delta: float, option_price: float,
                     gamma: float, vega: float, theta: float):
        # tickType 13 = MODEL_OPTION (유효한 Greeks), 그 외는 무시
        if tick_type not in (10, 11, 12, 13):
            return
        if not iv or not (0 < iv < 10): return
        vanna = vega * delta if (vega and delta) else 0.0
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if req_id in self._req_map:
            strike, side, exp = self._req_map[req_id]
            k = (exp, strike, side)
            is_new = k not in self._cell_data
            if is_new and len(self._cell_data) == 0:
                print(f"[Greeks] ✅ 첫 tick 수신! req_id={req_id} strike={strike} {side} iv={iv:.4f} delta={delta:.4f} tt={tick_type}")
            self._prev_data[k] = self._cell_data.get(k, {}).copy()
            self._cell_data[k] = dict(expiry=exp, strike=strike, side=side,
                delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                und_price=self._und_price, ts=ts)
            # 수신 진행상황: 10개 단위로 콘솔 출력
            n = len(self._cell_data)
            total = len(self._req_map)
            if is_new and (n % 10 == 0 or n == total):
                pct = int(n / total * 100) if total else 0
                print(f"[Greeks] tick 수신 {n}/{total} ({pct}%) strike={strike} {side} iv={iv:.3f}")
                self._banner.setText(
                    f"📡 수신 중 {n}/{total} ({pct}%) | 마지막: {side}{int(strike)} iv={iv:.3f}")
        elif req_id in self._next_map:
            s, side, exp = self._next_map[req_id]
            gdb.save_snapshot(self._conn, [dict(
                ts=ts, sym=self._sym, expiry=exp, strike=s, side=side,
                delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                und_price=self._und_price)])
        if not self._flush_t.isActive():
            self._flush_t.start(THROTTLE_MS)

    # ── 렌더·필터·밴드 ──────────────────────────────────
    def _flush(self):
        try:
            if not self._cell_data:
                return
            cfg      = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
            step     = cfg[3]
            strikes  = self._calc_strikes(self._und_price, ATM_WING, step)
            atm      = min(strikes, key=lambda s: abs(s - self._und_price))

            # render_rows 기대 형식: cell_data[(row_idx, side)]
            # tab_greeks 내부 형식: _cell_data[(expiry, strike, side)]
            # → 변환
            # (expiry,strike,side) → (row_idx,side) 변환
            strike_idx = {s: i for i, s in enumerate(strikes)}
            rd: dict = {}
            for (exp, strike, side), d in self._cell_data.items():
                if exp != self._expiry:
                    continue
                if strike in strike_idx:
                    rd[(strike_idx[strike], side)] = d

            n = len(rd)
            # 테이블 행 수 맞추기 (처음 1회)
            if self._table.rowCount() != len(strikes):
                self._table.setRowCount(len(strikes))
                for r, st in enumerate(strikes):
                    init_row(self._table, r, st, atm)

            render_rows(self._table, strikes, atm, rd, self._prev_data)
            print(f"[Greeks] 테이블 렌더 완료: {n}개 셀 / 총 {len(strikes)*2}개")
            if n == len(strikes) * 2:
                self._banner.setText(
                    f"✅ {self._sym} {self._expiry} | "
                    f"ATM={int(atm)} | {n}개 수신 완료")
        except Exception as e:
            log.error("[GreeksGrid] render_rows: %s", e)
            print(f"[Greeks] render_rows 오류: {e}")
        # GexSkewPanel 갱신 — update(strikes, cell_data)
        # GexSkewPanel은 cell_data[(row_idx, side)] 형식을 기대함
        try:
            cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
            step    = cfg[3]
            strikes = self._calc_strikes(self._und_price, ATM_WING, step)
            gex_data = {}
            for i, s in enumerate(strikes):
                for side in ("C", "P"):
                    k = (self._expiry, s, side)
                    if k in self._cell_data:
                        gex_data[(i, side)] = self._cell_data[k]
            self._gex.update(strikes, gex_data)
        except Exception as e:
            log.error("[GreeksGrid] gex update: %s", e)

    def _apply_delta_filter(self, val: int):
        thresh = val / 100.0
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                try: self._table.setRowHidden(row, abs(float(item.text())) < thresh)
                except ValueError: pass

    def _update_band(self):
        """1분마다 호출 — DB에서 오늘 ATM Gamma/IV 시계열 + 과거 평균 계산 후 NormalBandPanel 갱신"""
        if not self._cell_data:
            return
        try:
            import time as _time
            # ① 오늘 스냅샷 로드
            snaps = gdb.load_snapshots(self._day)
            if not snaps:
                return
            # ATM 행사가 추정 (und_price 기준 가장 가까운 strike)
            und = self._und_price
            strikes = sorted({r["strike"] for r in snaps})
            if not strikes:
                return
            atm = min(strikes, key=lambda s: abs(s - und))
            # 오늘 ATM 콜 시계열 구성
            atm_rows = sorted(
                [r for r in snaps if r["strike"] == atm and r["side"] == "C"],
                key=lambda r: r["ts"])
            if not atm_rows:
                return
            today_ts    = list(range(len(atm_rows)))   # 분 인덱스
            today_gamma = [r["gamma"] or 0.0 for r in atm_rows]
            today_iv    = [r["iv"]    or 0.0 for r in atm_rows]
            # ② 과거 5일 같은 ATM strike 데이터 → 히스토리 평균용
            hist_gamma: list = []
            hist_iv:    list = []
            for past_day in gdb.available_days()[-6:-1]:   # 최근 5일
                past = gdb.load_snapshots(past_day)
                for r in past:
                    if r["strike"] == atm and r["side"] == "C":
                        if r["gamma"]: hist_gamma.append(r["gamma"])
                        if r["iv"]:    hist_iv.append(r["iv"])
            self._band.update_band(today_ts, today_gamma, today_iv,
                                   hist_gamma, hist_iv)
        except Exception as e:
            log.error("[GreeksGrid] band update: %s", e)

    # ── 자동저장 ────────────────────────────────────────
    def _autosave(self):
        if not self._cell_data and self._callput:
            und = getattr(self._callput, "und_price", 0.0)
            if und and und > 0:
                self._und_price = und
        if not self._cell_data: return
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [{**d, "ts": ts, "sym": self._sym} for d in self._cell_data.values()]
        try:
            gdb.save_snapshot(self._conn, rows)
            evts  = gdb.detect_spike(self._day, self._sym, rows,
                                     self._und_price, self._econn)
            evts += self._ctx.detect(rows, self._day, self._sym)
            if evts: self._banner.setText(" | ".join(evts[-3:]))
        except Exception as e: log.error("[GreeksGrid] autosave: %s", e)
        now = datetime.now()
        if now.hour == 15 and now.minute == 0:
            self._save_baseline(rows)

    def _save_baseline(self, rows: List[dict]):
        cutoff = datetime.now() - timedelta(minutes=gdb.BASELINE_CUT_MIN)
        valid  = [r for r in rows
                  if datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S") < cutoff]
        if not valid: return
        agg: Dict[Tuple, Dict] = {}
        for r in valid:
            k = (r["sym"], r["expiry"], r["strike"], r["side"])
            agg.setdefault(k, {"iv": [], "gamma": []})
            if r.get("iv"):    agg[k]["iv"].append(r["iv"])
            if r.get("gamma"): agg[k]["gamma"].append(r["gamma"])
        bl = [dict(sym=k[0], expiry=k[1], strike=k[2], side=k[3],
                   iv_avg   =sum(v["iv"])   /len(v["iv"])    if v["iv"]    else 0.0,
                   gamma_avg=sum(v["gamma"])/len(v["gamma"]) if v["gamma"] else 0.0)
              for k, v in agg.items()]
        try: gdb.save_baseline(bl)
        except Exception as e: log.error("[GreeksGrid] save_baseline: %s", e)

    # ── 유틸 ────────────────────────────────────────────
    def _calc_strikes(self, und: float, wing: int, step: int = 5) -> List[float]:
        atm = round(und / step) * step
        return [atm + i * step for i in range(-wing, wing + 1)]

    def _next_trading_expiry(self) -> Optional[str]:  # SPX 0DTE 월/수/금
        nxt = date.today() + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        return nxt.strftime("%Y%m%d") if nxt.weekday() in (0, 2, 4) else None