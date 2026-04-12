"""
tab_greeks.py — Greeks Matrix 탭  v3.0
════════════════════════════════════════════════════════════════
실시간 수신 (GreeksGrid) + 리플레이 (ReplayPanel) 탭 통합.
기능별 로직은 greeks_db / greeks_render / greeks_chart / greeks_replay 로 분리.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QSplitter, QSlider, QCheckBox,
    QMessageBox, QTabWidget, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui  import QFont

from core import (
    bridge, router, GridTab,
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_UND, REQ_CHAIN, REQ_CHAIN_P,
    GREEKS_MATRIX_N,
    build_expiry_list, make_opt_contract,
    is_market_open,
)
from greeks_db     import open_db, open_events_db, save_snapshot, detect_spike
from greeks_render import init_table, init_row, render_rows, NCOLS
from greeks_chart  import GexSkewPanel, NormalBandPanel
from greeks_replay import ReplayPanel

AUTOSAVE_MS = 60_000
THROTTLE_MS = 300
BAND_UPDATE_MS = 60_000   # Normal Band 1분마다 갱신


# ══════════════════════════════════════════════════════════════
class GreeksGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
        self.mw        = mw
        self.sym       = "SPX"
        self.expiry    = ""
        self.exp_tag   = ""
        self.und_price = 0.0
        self.strikes   = []
        self.atm_strike = 0.0
        self.call_info  = {}
        self.put_info   = {}
        self._cell_data: dict = {}
        self._prev:      dict = {}
        self._spike_st:  set  = set()
        self._dirty     = False

        # 타이머
        self._throttle   = QTimer(self); self._throttle.setSingleShot(True)
        self._throttle.setInterval(THROTTLE_MS)
        self._throttle.timeout.connect(self._flush)

        self._autosave_t = QTimer(self)
        self._autosave_t.setInterval(AUTOSAVE_MS)
        self._autosave_t.timeout.connect(self._autosave)
        self._autosave_t.start()

        self._band_t = QTimer(self)
        self._band_t.setInterval(BAND_UPDATE_MS)
        self._band_t.timeout.connect(self._update_band)
        self._band_t.start()

        # DB
        self._db    = open_db()
        self._edb   = open_events_db()
        from greeks_db import GREEKS_DIR
        print(f"[GreeksGrid] 저장 경로: {GREEKS_DIR}")

        self._exp_list = build_expiry_list()
        self._build()
        self._connect_signals()
        # 저장 경로 초기 표시
        from greeks_db import GREEKS_DIR
        QTimer.singleShot(500, lambda: self.lbl_save.setText(
            f"경로:{str(GREEKS_DIR)}"))

    # ─────────────────────────────────────────────────────────
    # UI 빌드
    # ─────────────────────────────────────────────────────────
    def _build(self):
        # 상위 탭: [실시간] / [리플레이]
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab{padding:5px 16px;font-weight:bold;}"
            "QTabBar::tab:selected{background:#1a3a6b;color:#ffd700;}")
        self.add(self._tabs, 0, 0, 4, 12)

        # ── 실시간 탭 ─────────────────────────────────────────
        rt = QWidget()
        rt_v = QVBoxLayout(rt)
        rt_v.setContentsMargins(4, 4, 4, 4)
        rt_v.setSpacing(4)
        rt_v.addLayout(self._build_ctrl())

        h_split = QSplitter(Qt.Horizontal)
        h_split.setHandleWidth(6)
        h_split.setStyleSheet(
            "QSplitter::handle{background:#2a2a5a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        # 테이블
        self.tbl = QTableWidget(0, NCOLS)
        init_table(self.tbl)
        h_split.addWidget(self.tbl)

        # 차트 수직 분할
        c_split = QSplitter(Qt.Vertical)
        self._gex_skew = GexSkewPanel()
        self._normal_band = NormalBandPanel()
        c_split.addWidget(self._gex_skew)
        c_split.addWidget(self._normal_band)
        c_split.setSizes([350, 250])
        h_split.addWidget(c_split)
        h_split.setSizes([700, 500])

        rt_v.addWidget(h_split)

        # 급변동 이벤트 로그 (하단 접이식)
        self._evt_box = QGroupBox("🚨 급변동 이벤트 로그")
        evt_v = QVBoxLayout(self._evt_box)
        self.lbl_evt = QLabel("―")
        self.lbl_evt.setWordWrap(True)
        self.lbl_evt.setStyleSheet("color:#ff8888;font-size:11px;border:none;")
        evt_v.addWidget(self.lbl_evt)
        self._evt_box.setMaximumHeight(80)
        rt_v.addWidget(self._evt_box)

        self._tabs.addTab(rt, "📡 실시간")

        # ── 리플레이 탭 ───────────────────────────────────────
        self._replay = ReplayPanel()
        self._tabs.addTab(self._replay, "⏪ 리플레이")
        self._tabs.currentChanged.connect(self._on_tab_switch)

    def _build_ctrl(self) -> QHBoxLayout:
        def lbl(t): return QLabel(t)
        cl = QHBoxLayout(); cl.setSpacing(6)
        self.edit_sym  = QLineEdit("SPX"); self.edit_sym.setFixedWidth(56)
        self.combo_exp = QComboBox();      self.combo_exp.setMinimumWidth(120)
        for l, _, _ in self._exp_list: self.combo_exp.addItem(l)
        btn = QPushButton("▶ 조회")
        btn.setStyleSheet("background:#1a3a6b;font-weight:bold;padding:4px 10px;")
        btn.clicked.connect(self._fetch)
        self.lbl_und = QLabel("SPX: ―")
        self.lbl_und.setFont(QFont("Arial", 14, QFont.Bold))
        self.lbl_und.setStyleSheet("color:#ffd700;padding:0 10px;border:none;")
        self.sld_delta = QSlider(Qt.Horizontal)
        self.sld_delta.setRange(0, 50); self.sld_delta.setValue(5); self.sld_delta.setFixedWidth(90)
        self.sld_delta.valueChanged.connect(self._apply_delta_filter)
        self.lbl_dv  = QLabel("0.05"); self.lbl_dv.setStyleSheet("color:#aaa;border:none;min-width:28px;")
        self.chk_auto = QCheckBox("1분저장"); self.chk_auto.setChecked(True)
        self.lbl_save = QLabel("저장:―"); self.lbl_save.setStyleSheet("color:#555;font-size:11px;border:none;")
        btn_sv = QPushButton("💾 즉시"); btn_sv.clicked.connect(self._manual_save)
        for w in (lbl("심볼:"), self.edit_sym, lbl("만기:"), self.combo_exp, btn,
                  self.lbl_und, _vline(), lbl("Delta≥"), self.sld_delta, self.lbl_dv,
                  _vline(), self.chk_auto, self.lbl_save, btn_sv):
            cl.addWidget(w)
        cl.addStretch()
        return cl

    # ─────────────────────────────────────────────────────────
    # 시그널 연결
    # ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        router.register_price(REQ_UND, REQ_UND, self._on_tick_price)
        router.register_price(REQ_CHAIN,   REQ_CHAIN   + 199, self._on_tick_price)
        router.register_price(REQ_CHAIN_P, REQ_CHAIN_P + 199, self._on_tick_price)
        router.register_option(REQ_CHAIN,   REQ_CHAIN   + 199, self._on_tick_opt)
        router.register_option(REQ_CHAIN_P, REQ_CHAIN_P + 199, self._on_tick_opt)

    # ─────────────────────────────────────────────────────────
    # 데이터 조회
    # ─────────────────────────────────────────────────────────
    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요."); return
        self.sym = self.edit_sym.text().strip().upper()
        cp = getattr(self.mw, 'tab_callput', None)
        und = getattr(cp, 'und_price', None) or self.und_price
        if not und:
            QMessageBox.information(self, "대기", "콜-풋 탭에서 현재가를 먼저 수신하세요.")
            return
        idx = self.combo_exp.currentIndex()
        _, code, tag = self._exp_list[idx]
        self.expiry = code; self.exp_tag = tag
        base = "SPX" if self.sym == "SPXW" else self.sym
        _, _, _, step = SYMBOL_CFG.get(base, DEFAULT_CFG)
        self.atm_strike = round(und / step) * step
        self.strikes = sorted({
            self.atm_strike + i * step
            for i in range(-GREEKS_MATRIX_N, GREEKS_MATRIX_N + 1)
        })
        self.call_info.clear(); self.put_info.clear(); self._cell_data.clear()
        self.tbl.setRowCount(len(self.strikes))
        for r, st in enumerate(self.strikes):
            init_row(self.tbl, r, st, self.atm_strike)
        for i, st in enumerate(self.strikes):
            rc, rp = REQ_CHAIN + i, REQ_CHAIN_P + i
            self.call_info[rc] = {"row": i, "strike": st}
            self.put_info[rp]  = {"row": i, "strike": st}
            tks = "100,101,106"
            self.mw.ib.reqMktData(rc, make_opt_contract(self.sym, st, "C", self.expiry, self.exp_tag), tks, False, False, [])
            self.mw.ib.reqMktData(rp, make_opt_contract(self.sym, st, "P", self.expiry, self.exp_tag), tks, False, False, [])

    # ─────────────────────────────────────────────────────────
    # Tick 수신
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        if price > 0 and rid == REQ_UND and tt in (4, 14, 75):
            self.und_price = price
            self.lbl_und.setText(f"{self.sym}: {price:,.2f}")

    def _on_tick_opt(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (12, 13): return
        info = self.call_info.get(rid) or self.put_info.get(rid)
        if not info: return
        side = "C" if rid in self.call_info else "P"
        r, st = info["row"], info["strike"]
        vanna = round(vega * delta, 6) if vega and delta else 0.0

        # IV 유효성 체크 — IBKR은 계산 불가 시 -1 또는 1e308 반환
        iv_clean = iv if (iv is not None and 0 < iv < 10) else 0.0

        # 기존 IV가 유효했는데 새 값이 0이면 기존 값 유지 (순간 끊김 방지)
        prev_d = self._cell_data.get((r, side), {})
        if iv_clean == 0.0 and prev_d.get("iv", 0.0) > 0:
            iv_clean = prev_d["iv"]

        self._cell_data[(r, side)] = {
            "delta": delta, "gamma": gamma,
            "iv": iv_clean, "vanna": vanna, "strike": st,
        }
        self._dirty = True
        if not self._throttle.isActive():
            self._throttle.start()

    # ─────────────────────────────────────────────────────────
    # 렌더링
    # ─────────────────────────────────────────────────────────
    def _flush(self):
        if not self._dirty: return
        self._dirty = False
        render_rows(self.tbl, self.strikes, self.atm_strike,
                    self._cell_data, self._prev, self._spike_st)
        self._apply_delta_filter()
        self._gex_skew.update(self.strikes, self._cell_data)

    def _apply_delta_filter(self):
        thr = self.sld_delta.value() / 100.0
        self.lbl_dv.setText(f"{thr:.2f}")
        for r, st in enumerate(self.strikes):
            cd = self._cell_data.get((r, "C"))
            pd = self._cell_data.get((r, "P"))
            ca = abs(cd["delta"]) if cd else 0.0
            pa = abs(pd["delta"]) if pd else 0.0
            hide = (st != self.atm_strike) and ca < thr and pa < thr
            self.tbl.setRowHidden(r, hide)

    # ─────────────────────────────────────────────────────────
    # Normal Band 갱신
    # ─────────────────────────────────────────────────────────
    def _update_band(self):
        from datetime import datetime
        from greeks_db import load_snapshots, available_days
        today = datetime.now().strftime("%Y%m%d")
        if not self.atm_strike: return
        atm   = self.atm_strike
        hist_rows = sum([load_snapshots(d) for d in available_days()
                         if d < today][-10:], [])
        def _g(rows):
            g, iv = [], []
            for r in rows:
                if abs(r["strike"] - atm) < 1e-3 and r["side"] == "C":
                    g.append(r["gamma"] or 0.0); iv.append(r["iv"] or 0.0)
            return g, iv
        tg, ti = _g(load_snapshots(today))
        hg, hi = _g(hist_rows)
        if tg:
            self._normal_band.update_band(list(range(len(tg))), tg, ti, hg, hi)

    # ─────────────────────────────────────────────────────────
    # SQLite 저장 + 급변동 감지
    # ─────────────────────────────────────────────────────────
    def _autosave(self):
        if not self.chk_auto.isChecked(): return
        if not is_market_open(): return

        # ── 콜-풋 탭에서 strikes/und_price 자동 연동 ──────────
        # Greeks 탭에서 직접 조회하지 않아도, 콜-풋 탭이 수신 중이면
        # 해당 strikes와 현재가를 가져와서 자동 저장에 활용
        if not self.strikes:
            cp = getattr(self.mw, 'tab_callput', None)
            if cp:
                cp_strikes = getattr(cp, 'strikes', [])
                cp_und     = getattr(cp, 'und_price', 0.0)
                cp_expiry  = getattr(cp, 'expiry', '')
                cp_sym     = getattr(cp, 'sym', '')
                if cp_strikes and cp_und:
                    self.strikes    = cp_strikes
                    self.und_price  = cp_und
                    self.expiry     = cp_expiry
                    self.sym        = cp_sym or self.sym
                    self.atm_strike = min(cp_strikes,
                                         key=lambda s: abs(s - cp_und))

        if not self.strikes or not self._cell_data: return
        self._do_save()

    def _manual_save(self):
        self._do_save()
        QMessageBox.information(self, "저장", "Greeks 스냅샷 저장 완료")

    def _do_save(self):
        from datetime import datetime
        rows = []
        cur_gamma, cur_iv = {}, {}
        for r, st in enumerate(self.strikes):
            for side in ("C", "P"):
                d = self._cell_data.get((r, side))
                if not d: continue
                rows.append((st, side, d["delta"], d["gamma"], d["iv"], d["vanna"]))
                if side == "C":
                    cur_gamma[st] = d["gamma"]
                cur_iv[(st, side)] = d["iv"]
        if not rows: return
        try:
            save_snapshot(self._db, self.sym, self.expiry, self.und_price, rows)
            self.lbl_save.setText(f"저장:{datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"[GreeksGrid] DB 저장 오류: {e}")

        # 급변동 감지
        today = datetime.now().strftime("%Y%m%d")
        evts  = detect_spike(today, self.sym, cur_gamma, cur_iv,
                             self.und_price, self._edb)
        if evts:
            self._spike_st = {e["strike"] for e in evts}
            msgs = [f"[{e['trigger']}] {e['strike']:.0f}  "
                    f"{e['value']:.4f} (avg:{e['prev_avg']:.4f})" for e in evts]
            self.lbl_evt.setText("  |  ".join(msgs))
        else:
            self._spike_st.clear()

    # ─────────────────────────────────────────────────────────
    def _on_tab_switch(self, idx: int):
        if idx == 1:
            self._replay.refresh()

    def on_tab_activate(self): pass
    def on_tab_deactivate(self): pass

    def _apply_theme(self):
        from core import _apply_table_theme
        _apply_table_theme(self.tbl, getattr(self, 'dark_mode', True))


# ── 유틸 ──────────────────────────────────────────────────────
def _vline():
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setStyleSheet("color:#2e3060;")
    return f