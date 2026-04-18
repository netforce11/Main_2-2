# tab_greeks.py  — GreeksGrid 메인 탭
# Python 3.8 호환  |  S11 patch 기준
from __future__ import annotations
import logging
import os
import sys
import subprocess
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from PyQt5.QtCore    import QTimer, Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
                              QLabel, QPushButton, QComboBox, QSlider,
                              QSplitter, QTableWidget, QLineEdit)
import greeks_db as gdb
from greeks_db import (load_merged_snapshots, available_days_merged,
                        available_expiries_for_day)
try:
    from call_put_tab.chain_saver.buffer import et_to_kst, today_et
except ImportError:
    def et_to_kst(s): return s
    def today_et():
        from datetime import date; return date.today()
from greeks_render  import (init_table, init_row, render_rows,
                              init_table_replay, init_row_replay, render_rows_replay,
                              REPLAY_NCOLS, RCOL_STRIKE)
from greeks_chart   import GexSkewPanel, NormalBandPanel
from greeks_replay  import ReplayPanel
from greeks_context import ContextDetector
from core import (router, REQ_CHAIN, REQ_CHAIN_P,
                  make_opt_contract, build_expiry_list, SYMBOL_CFG, DEFAULT_CFG)

# chain_saver 버퍼 연동 (Optional — 없으면 기존 IBKR 직접 구독 유지)
try:
    from call_put_tab.chain_saver.buffer import ChainBuffer
    _CHAIN_BUFFER_AVAILABLE = True
except ImportError:
    _CHAIN_BUFFER_AVAILABLE = False

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

        # ── chain_saver 버퍼 연동 ────────────────────────────
        # attach_chain_buffer() 로 주입되면 IBKR 직접 구독 대신 콜백 수신
        self._chain_buf: Optional["ChainBuffer"] = None
        self._use_chain_buf = False

        self._build()
        self._connect_signals()
        self._refresh_expiry()           # 앱 시작 시 만기 목록 자동 채우기
        QTimer.singleShot(NEXT_EXPIRY_DELAY_MS, self._fetch_next_expiry)

    # ── UI ───────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.addLayout(self._build_ctrl())

        # ★ 리플레이 컨트롤 바 (실시간 탭 내부)
        self._replay_bar = self._build_replay_bar()
        root.addLayout(self._replay_bar)

        # ★ 리플레이 슬라이더 (리플레이 모드에서만 표시)
        self._rp_slider = QSlider(Qt.Horizontal)
        self._rp_slider.setMinimum(0)
        self._rp_slider.setMaximum(0)
        self._rp_slider.valueChanged.connect(self._rp_on_slider)
        self._rp_slider.setVisible(False)
        root.addWidget(self._rp_slider)

        # ★ 테이블: 실시간(9col) / 리플레이(19col) 공용 스택
        from PyQt5.QtWidgets import QStackedWidget
        self._stack = QStackedWidget()

        # 실시간 페이지
        rt_page = QWidget(); rt_v = QVBoxLayout(rt_page)
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
        self._stack.addWidget(rt_page)   # index 0 = 실시간

        # 리플레이 페이지 (실시간과 동일한 9컬럼 테이블 + 차트)
        rp_page = QWidget(); rp_v = QVBoxLayout(rp_page)
        rsp2 = QSplitter(Qt.Horizontal)
        self._replay_table = QTableWidget()
        init_table(self._replay_table)   # 9컬럼 — 실시간과 동일
        rsp2.addWidget(self._replay_table)
        rsp3 = QSplitter(Qt.Vertical)
        self._replay_gex  = GexSkewPanel()
        self._replay_band = NormalBandPanel()
        rsp3.addWidget(self._replay_gex)
        rsp3.addWidget(self._replay_band)
        rsp2.addWidget(rsp3)
        rp_v.addWidget(rsp2)
        self._stack.addWidget(rp_page)   # index 1 = 리플레이

        root.addWidget(self._stack)

        self._banner = QLabel("")
        self._banner.setStyleSheet("color:orange;font-weight:bold;")
        root.addWidget(self._banner)

        # 별도 리플레이 탭 유지 (19컬럼 상세용)
        self._replay_panel = ReplayPanel()

        # 리플레이 상태
        self._replay_mode    = False
        self._replay_frames: dict = {}
        self._replay_ts_list: list = []
        self._replay_strikes: list = []
        self._replay_atm:    float = 0.0
        self._replay_prev:   dict  = {}
        self._replay_cur:    int   = 0
        self._replay_playing = False
        self._replay_timer   = QTimer(self)
        self._replay_timer.timeout.connect(self._replay_step)

        for ms, slot in [(AUTOSAVE_MS, self._autosave), (60_000, self._update_band)]:
            t = QTimer(self); t.timeout.connect(slot); t.start(ms)

    def _build_replay_bar(self):
        """실시간 탭 내부 리플레이 컨트롤 바."""
        from PyQt5.QtWidgets import QHBoxLayout
        hb = QHBoxLayout()

        # 모드 토글
        self.btn_live = QPushButton("📡 실시간")
        self.btn_live.setCheckable(True); self.btn_live.setChecked(True)
        self.btn_live.setStyleSheet(
            "background:#1a4a1a;color:#00e676;font-weight:bold;padding:4px 10px;")
        self.btn_live.clicked.connect(lambda: self._set_replay_mode(False))

        self.btn_replay_mode = QPushButton("⏮ 리플레이")
        self.btn_replay_mode.setCheckable(True)
        self.btn_replay_mode.setStyleSheet(
            "background:#1a1a4a;color:#aaaaff;font-weight:bold;padding:4px 10px;")
        self.btn_replay_mode.clicked.connect(lambda: self._set_replay_mode(True))

        hb.addWidget(self.btn_live)
        hb.addWidget(self.btn_replay_mode)
        hb.addWidget(QLabel("  |  날짜:"))

        self.rp_cmb_day = QComboBox(); self.rp_cmb_day.setMinimumWidth(90)
        self.rp_cmb_day.currentTextChanged.connect(self._rp_on_day_changed)
        hb.addWidget(self.rp_cmb_day)

        hb.addWidget(QLabel("만기:"))
        self.rp_cmb_expiry = QComboBox(); self.rp_cmb_expiry.setMinimumWidth(100)
        hb.addWidget(self.rp_cmb_expiry)

        hb.addWidget(QLabel("From:"))
        self.rp_edit_from = QLineEdit(); self.rp_edit_from.setPlaceholderText("HH:MM")
        self.rp_edit_from.setFixedWidth(70)
        hb.addWidget(self.rp_edit_from)

        hb.addWidget(QLabel("To:"))
        self.rp_edit_to = QLineEdit(); self.rp_edit_to.setPlaceholderText("HH:MM")
        self.rp_edit_to.setFixedWidth(70)
        hb.addWidget(self.rp_edit_to)

        self.rp_btn_load = QPushButton("불러오기")
        self.rp_btn_load.clicked.connect(self._rp_load)
        hb.addWidget(self.rp_btn_load)

        # 재생 컨트롤
        hb.addWidget(QLabel("  속도:"))
        self.rp_cmb_speed = QComboBox()
        for k in ("x1", "x5", "x10"): self.rp_cmb_speed.addItem(k)
        hb.addWidget(self.rp_cmb_speed)

        self.rp_btn_play = QPushButton("▶ 재생")
        self.rp_btn_play.setStyleSheet("background:#1a5a1a;font-weight:bold;padding:4px 10px;")
        self.rp_btn_play.clicked.connect(self._rp_toggle_play)
        hb.addWidget(self.rp_btn_play)

        self.rp_btn_stop = QPushButton("■ 정지")
        self.rp_btn_stop.clicked.connect(self._rp_stop)
        hb.addWidget(self.rp_btn_stop)

        # 저장 주기 설정
        hb.addWidget(QLabel("  |  저장주기:"))
        self.cmb_save_interval = QComboBox()
        for label, ms in [("1초", 1000), ("3초", 3000), ("5초", 5000),
                           ("10초", 10000), ("30초", 30000)]:
            self.cmb_save_interval.addItem(label, ms)
        self.cmb_save_interval.setCurrentIndex(2)   # 기본값 5초
        self.cmb_save_interval.currentIndexChanged.connect(self._on_save_interval_changed)
        hb.addWidget(self.cmb_save_interval)

        self.rp_lbl_ts = QLabel("-")
        self.rp_lbl_ts.setStyleSheet("color:#ffd700;font-weight:bold;padding:0 8px;border:none;")
        hb.addWidget(self.rp_lbl_ts)

        # 슬라이더
        hb.addStretch()

        # 리플레이 바는 처음에 숨김 (실시간 모드)
        for w in [self.rp_cmb_day, self.rp_cmb_expiry,
                  self.rp_edit_from, self.rp_edit_to,
                  self.rp_btn_load, self.rp_cmb_speed,
                  self.rp_btn_play, self.rp_btn_stop, self.rp_lbl_ts]:
            w.setVisible(False)

        return hb

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

        # ChainSaver 저장 로그 열기 버튼
        btn_log = QPushButton("📋 저장 로그")
        btn_log.setToolTip("ChainSaver 30초 통계 로그 파일 열기")
        btn_log.setStyleSheet(
            "background:#1a2a1a;color:#00e676;padding:4px 8px;"
            "font-size:11px;border:1px solid #2a5a2a;border-radius:3px;")
        btn_log.clicked.connect(self._open_chainsaver_log)
        hb.addWidget(btn_log)

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

    # ── chain_saver 버퍼 연동 ────────────────────────────────
    def attach_chain_buffer(self, buf: "ChainBuffer"):
        """
        _init_saver.py 에서 호출.
        chain_saver ChainBuffer 를 주입하면 IBKR 직접 구독 대신
        버퍼 콜백으로 Greeks 수신 → 티커 슬롯 0개 추가 사용.

        사용 예:
            # _init_saver.py
            self.tab_greeks.attach_chain_buffer(chain_buf)
        """
        if not _CHAIN_BUFFER_AVAILABLE:
            log.warning("[GreeksGrid] ChainBuffer import 불가 — IBKR 직접 구독 유지")
            return
        self._chain_buf    = buf
        self._use_chain_buf = True
        buf.register_greeks_subscriber(self._on_chain_buf_update)
        log.info("[GreeksGrid] chain_saver 버퍼 연동 완료 ✅")
        print("[Greeks] 🔗 chain_saver 버퍼 연동 — IBKR 직접 구독 생략")

    def _on_chain_buf_update(self, expiry: str, strike: float,
                              side: str, data: dict):
        """
        chain_saver buffer 브로드캐스트 콜백.
        ★ IBKR EClient 스레드에서 호출됨 — UI 접근 금지 ★
        데이터 유효성만 확인 후 메인 스레드로 마샬링.
        """
        # 빠른 필터링 (스레드 안전한 값만 읽기)
        if expiry != self._expiry:
            return
        iv = data.get("iv")
        if not iv or not (0 < iv < 10):
            return

        # 메인 스레드에서 실제 처리 — invokeMethod로 안전하게 전달
        import json
        try:
            payload = json.dumps({
                "expiry": expiry,
                "strike": strike,
                "side":   side,
                "iv":     data.get("iv"),
                "delta":  data.get("delta"),
                "gamma":  data.get("gamma"),
                "vega":   data.get("vega"),
                "theta":  data.get("theta"),
                "und_price": data.get("und_price"),
                "theo":   data.get("theo"),
                "mid":    data.get("mid"),
                "mispct": data.get("mispct"),
            })
        except Exception:
            return
        QMetaObject.invokeMethod(
            self, "_apply_chain_buf_update",
            Qt.QueuedConnection,
            Q_ARG(str, payload),
        )

    @pyqtSlot(str)
    def _apply_chain_buf_update(self, payload: str):
        """
        메인 스레드에서 실행 — UI/데이터 갱신 안전.
        """
        import json
        try:
            data = json.loads(payload)
        except Exception:
            return

        expiry = data["expiry"]
        strike = data["strike"]
        side   = data["side"]

        cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step    = cfg[3]
        strikes = self._calc_strikes(self._und_price, ATM_WING, step)
        if strike not in strikes:
            return

        iv    = data.get("iv")
        delta = data.get("delta")
        gamma = data.get("gamma")
        vega  = data.get("vega")
        theta = data.get("theta")
        und   = data.get("und_price") or self._und_price

        vanna = (vega * delta) if (vega and delta) else 0.0
        ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        k     = (expiry, strike, side)

        is_new = k not in self._cell_data
        if is_new and len(self._cell_data) == 0:
            print(f"[Greeks] ✅ 첫 chain_buf tick! strike={strike} {side} "
                  f"iv={iv:.4f} delta={delta:.4f} "
                  f"theo={data.get('theo')} mispct={data.get('mispct')}")

        self._prev_data[k] = self._cell_data.get(k, {}).copy()
        self._cell_data[k] = dict(
            expiry=expiry, strike=strike, side=side,
            delta=delta, gamma=gamma, iv=iv, vanna=vanna,
            und_price=und, ts=ts,
            theo=data.get("theo"),
            mid=data.get("mid"),
            mispct=data.get("mispct"),
        )

        # 수신 진행 현황 (10개 단위)
        n     = len(self._cell_data)
        total = len(strikes) * 2
        if is_new and (n % 10 == 0 or n == total):
            pct = int(n / total * 100) if total else 0
            print(f"[Greeks] buf 수신 {n}/{total} ({pct}%) "
                  f"strike={strike} {side} iv={iv:.3f}")
            self._banner.setText(
                f"🔗 버퍼 수신 {n}/{total} ({pct}%) | {side}{int(strike)} iv={iv:.3f}")

        if not self._flush_t.isActive():
            self._flush_t.start(THROTTLE_MS)

    # ── 조회 ────────────────────────────────────────────
    def _fetch(self):
        self._sym           = self._sym_cb.currentText()
        self._expiry, self._tag = self._current_expiry()
        print(f"[Greeks] 조회 시작 sym={self._sym} expiry={self._expiry} "
              f"tag={self._tag} und={self._und_price} "
              f"mode={'chain_buf' if self._use_chain_buf else 'IBKR'}")
        if not self._expiry:
            msg = "만기 미선택 — 만기갱신 버튼을 누르세요"
            self._banner.setText(f"⚠ {msg}"); log.warning("[GreeksGrid] %s", msg); return
        if self._und_price <= 0:
            msg = f"⚠ 기초자산 가격 미수신 (und={self._und_price}) — IBKR 연결 확인"
            self._banner.setText(msg); print(f"[Greeks] {msg}"); return

        cfg    = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step   = cfg[3]
        strikes = self._calc_strikes(self._und_price, ATM_WING, step)
        atm_check = round(self._und_price / (step if step else 5)) * (step if step else 5)

        # ── chain_buf 모드: IBKR 구독 생략, 콜백 대기 ──────────
        if self._use_chain_buf:
            self._cell_data.clear()
            self._prev_data.clear()
            msg = (f"🔗 chain_buf 대기 중 | {self._sym} {self._expiry} "
                   f"ATM={atm_check} ±{ATM_WING} | {len(strikes)*2}개")
            self._banner.setText(msg)
            print(f"[Greeks] {msg}")
            return

        # ── IBKR 직접 구독 모드 (기존 로직) ────────────────────
        self._req_map.clear()
        self._rid_c = REQ_CHAIN
        self._rid_p = REQ_CHAIN_P
        # 기존 구독 먼저 취소
        for rid in list(self._req_map.keys()):
            try: self._main.ib.cancelMktData(rid)
            except Exception: pass

        ok = 0; fail = 0
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

        mode_str = "📸 스냅샷" if snap else "📡 스트림"
        msg = (f"{mode_str} {self._sym} {self._expiry} | ATM={atm_check} ±{ATM_WING} | "
               f"요청 {ok}건" + (f" (실패 {fail}건)" if fail else ""))
        self._banner.setText(msg)
        print(f"[Greeks] {msg}")
        print(f"[Greeks] reqId 범위: 콜={REQ_CHAIN}~{self._rid_c-1} 풋={REQ_CHAIN_P}~{self._rid_p-1}")
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

    # ── ChainSaver 로그 파일 열기 ──────────────────────────
    def _open_chainsaver_log(self):
        """ChainSaver 30초 통계 로그 파일을 OS 기본 뷰어로 열기."""
        # scheduler 참조 시도
        sched = None
        try:
            sched = self.mw.tab_callput._saver_scheduler
        except AttributeError:
            pass

        if sched and hasattr(sched, 'log_path_today'):
            path = sched.log_path_today()
        else:
            today = date.today().strftime("%Y%m%d")
            path  = os.path.join(r"C:\data\Greeks_history",
                                 f"chainsaver_{today}.log")

        # 파일 없으면 빈 파일 생성
        if not os.path.exists(path):
            try:
                open(path, "w", encoding="utf-8").close()
            except OSError:
                pass

        try:
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            log.error("[GreeksGrid] 로그 파일 열기 실패: %s", e)

    # ── 자동저장 ────────────────────────────────────────
    def _autosave(self):
        if not self._cell_data and self._callput:
            und = getattr(self._callput, "und_price", 0.0)
            if und and und > 0:
                self._und_price = und
        if not self._cell_data: return
        try:
            from call_put_tab.chain_saver.buffer import now_et
            ts = now_et().strftime("%Y-%m-%d %H:%M:%S")
        except ImportError:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
    # ══════════════════════════════════════════════════════════
    # ★ 실시간 탭 내 리플레이 모드
    # ══════════════════════════════════════════════════════════

    def _set_replay_mode(self, on: bool):
        """실시간 ↔ 리플레이 모드 전환."""
        self._replay_mode = on
        self._stack.setCurrentIndex(1 if on else 0)
        self.btn_live.setChecked(not on)
        self.btn_replay_mode.setChecked(on)

        # 리플레이 컨트롤 가시성
        widgets = [self.rp_cmb_day, self.rp_cmb_expiry,
                   self.rp_edit_from, self.rp_edit_to,
                   self.rp_btn_load, self.rp_cmb_speed,
                   self.rp_btn_play, self.rp_btn_stop, self.rp_lbl_ts]
        for w in widgets:
            w.setVisible(on)
        self._rp_slider.setVisible(on)

        if on:
            self._rp_refresh_days()
        else:
            self._rp_stop()

    def _rp_refresh_days(self):
        self.rp_cmb_day.clear()
        for d in reversed(available_days_merged()):
            self.rp_cmb_day.addItem(d)
        first = self.rp_cmb_day.currentText()
        self._rp_refresh_expiries(first)

    def _rp_on_day_changed(self, day: str):
        self.rp_edit_from.clear()
        self.rp_edit_to.clear()
        self._rp_refresh_expiries(day)

    def _rp_refresh_expiries(self, day: str):
        self.rp_cmb_expiry.clear()
        if not day:
            return
        from datetime import datetime as _dt
        self.rp_cmb_expiry.addItem("전체 만기", "")
        for exp in available_expiries_for_day(day):
            try:
                exp_dt  = _dt.strptime(exp, "%Y%m%d")
                base_dt = _dt.strptime(day, "%Y%m%d")
                diff = (exp_dt - base_dt).days
                if diff == 0:   label = f"{exp[4:6]}/{exp[6:8]} (당일)"
                elif diff == 1: label = f"{exp[4:6]}/{exp[6:8]} (내일)"
                elif diff > 0:  label = f"{exp[4:6]}/{exp[6:8]} (+{diff}일)"
                else:           label = f"{exp[4:6]}/{exp[6:8]} (만료)"
            except Exception:
                label = exp
            self.rp_cmb_expiry.addItem(label, exp)

    def _rp_load(self):
        """DB에서 데이터 로드 후 리플레이 테이블 초기화."""
        self._rp_stop()
        day    = self.rp_cmb_day.currentText()
        t_fr   = self.rp_edit_from.text().strip()
        t_to   = self.rp_edit_to.text().strip()
        expiry = self.rp_cmb_expiry.currentData() or ""

        if not day:
            self.rp_lbl_ts.setText("날짜 선택 필요"); return

        try:
            from datetime import datetime as _dt, timedelta as _td
            base_dt  = _dt.strptime(day, "%Y%m%d")
            next_dt  = base_dt + _td(days=1)
            date_str = base_dt.strftime("%Y-%m-%d")
            next_str = next_dt.strftime("%Y-%m-%d")

            def _to_full(t, end=False):
                if not t: return ""
                parts = t.split(":")
                hh = int(parts[0])
                mm = parts[1].zfill(2) if len(parts) > 1 else "00"
                ss = "59" if end else "00"
                d  = next_str if hh <= 8 else date_str
                return f"{d} {hh:02d}:{mm}:{ss}"

            if t_fr or t_to:
                from_ts = _to_full(t_fr, False)
                to_ts   = _to_full(t_to, True)
            else:
                from_ts = f"{date_str} 09:00:00"
                to_ts   = f"{next_str} 16:30:00"
        except Exception as e:
            self.rp_lbl_ts.setText(f"시간 오류: {e}"); return

        self.rp_lbl_ts.setText("로딩 중...")
        rows = load_merged_snapshots(day, from_ts, to_ts, expiry=expiry)
        if not rows:
            self.rp_lbl_ts.setText("데이터 없음"); return

        ts_set = dict.fromkeys(r["ts"] for r in rows)
        self._replay_ts_list = list(ts_set.keys())
        strikes_set = sorted({r["strike"] for r in rows})
        self._replay_strikes = strikes_set

        und = next((r["und_price"] for r in rows if r["und_price"]), 0)
        self._replay_atm = (min(strikes_set, key=lambda s: abs(s - und))
                            if und and strikes_set else 0.0)

        # 프레임 구성 (9컬럼용 — delta/gamma/iv/vanna)
        self._replay_frames = {}
        for r in rows:
            ts   = r["ts"]
            st   = r["strike"]
            side = r["side"]
            row  = strikes_set.index(st)
            self._replay_frames.setdefault(ts, {})[(row, side)] = {
                "delta":  r.get("delta")  or 0.0,
                "gamma":  r.get("gamma")  or 0.0,
                "iv":     r.get("iv")     or 0.0,
                "vanna":  r.get("vanna")  or 0.0,
            }

        # 테이블 초기화 (실시간과 동일한 9컬럼)
        self._replay_table.setRowCount(len(strikes_set))
        for i, st in enumerate(strikes_set):
            init_row(self._replay_table, i, st, self._replay_atm)

        # 슬라이더
        self._rp_slider.setMaximum(max(0, len(self._replay_ts_list) - 1))
        self._rp_slider.setValue(0)
        self._replay_cur  = 0
        self._replay_prev = {}

        self.rp_lbl_ts.setText(
            f"로드완료: {len(self._replay_ts_list)}시점 / "
            f"{len(strikes_set)}행사가")
        self._rp_render(0)

    def _rp_toggle_play(self):
        speeds = {"x1": 1000, "x5": 200, "x10": 100}
        if self._replay_playing:
            self._replay_playing = False
            self._replay_timer.stop()
            self.rp_btn_play.setText("▶ 재생")
        else:
            if not self._replay_ts_list: return
            ms = speeds.get(self.rp_cmb_speed.currentText(), 1000)
            self._replay_playing = True
            self._replay_timer.start(ms)
            self.rp_btn_play.setText("⏸ 일시정지")

    def _rp_stop(self):
        self._replay_playing = False
        self._replay_timer.stop()
        self.rp_btn_play.setText("▶ 재생")
        self._replay_cur = 0
        if self._replay_ts_list:
            self._rp_slider.setValue(0)

    def _replay_step(self):
        if self._replay_cur >= len(self._replay_ts_list) - 1:
            self._rp_stop(); return
        self._replay_cur += 1
        self._rp_slider.blockSignals(True)
        self._rp_slider.setValue(self._replay_cur)
        self._rp_slider.blockSignals(False)
        self._rp_render(self._replay_cur)

    def _rp_on_slider(self, val: int):
        self._replay_cur = val
        self._rp_render(val)

    def _rp_render(self, idx: int):
        if not self._replay_ts_list or idx >= len(self._replay_ts_list):
            return
        ts     = self._replay_ts_list[idx]
        cell_d = self._replay_frames.get(ts, {})
        kst    = et_to_kst(ts)
        self.rp_lbl_ts.setText(f"{kst} (KST)  /  {ts} (ET)")

        render_rows(self._replay_table, self._replay_strikes,
                    self._replay_atm, cell_d, self._replay_prev)

        # 차트도 갱신
        try:
            gex_data = {}
            for i, s in enumerate(self._replay_strikes):
                for side in ("C", "P"):
                    k = (i, side)
                    if k in cell_d:
                        gex_data[k] = cell_d[k]
            self._replay_gex.update(self._replay_strikes, gex_data)
        except Exception:
            pass

    # ── 저장 주기 변경 ────────────────────────────────────────
    def _on_save_interval_changed(self, idx: int):
        ms = self.cmb_save_interval.itemData(idx)
        try:
            sched = getattr(self._main, '_chain_sched', None)
            if sched and hasattr(sched, '_t5'):
                sched._t5.setInterval(ms)
                log.info("[GreeksGrid] 저장 주기 변경 → %dms", ms)
                self._banner.setText(f"💾 저장 주기 변경: {self.cmb_save_interval.currentText()}")
        except Exception as e:
            log.error("[GreeksGrid] 저장 주기 변경 실패: %s", e)