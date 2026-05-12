"""
greeks_grid.py — GreeksGrid (Greeks Matrix 탭) v6.1
════════════════════════════════════════════════════════
포함 내용:
  - GreeksGrid(GridTab)
      __init__()         초기화 + 자동저장 타이머
      _build()           컨트롤 + 테이블 UI 구성
      _connect_signals() 라우터 시그널 등록
      _get_expiry()      현재 만기 반환
      _fetch()           Greeks Matrix reqMktData 요청
      _on_tick_price()   가격 틱 수신
      _on_tick_opt()     옵션 틱 수신 (Delta·Gamma·ΔGamma·IV)
      _apply_theme()     다크/라이트 테이블 재적용

의존:
  account.greeks_save  스냅샷·자동저장·즉시저장
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox,
)
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont

from core import (
    GridTab, make_table, tbl_set, router,
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_UND, REQ_CHAIN, REQ_CHAIN_P,
    GREEKS_MATRIX_N, GREEKS_AUTOSAVE_S,
    build_expiry_list, make_opt_contract, auto_mdt,
)
from tab_account.greeks_save import GreeksSaveMixin, GREEKS_CSV


class GreeksGrid(GreeksSaveMixin, GridTab):
    """
    Greeks Matrix 탭 (Tab 6).

    MRO:
      GreeksGrid
        → GreeksSaveMixin  (스냅샷·자동저장)
        → GridTab
    """

    def __init__(self, mw):
        GridTab.__init__(self)
        self.mw          = mw
        self.strikes     = []
        self.call_data   = {}
        self.put_data    = {}
        self.prev_gammas = {}
        self._exp_list   = build_expiry_list()
        self._build()
        self._connect_signals()
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start(GREEKS_AUTOSAVE_S * 1000)

    def _build(self):
        ctrl = QWidget()
        cl   = QHBoxLayout(ctrl); cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(QLabel("심볼:"))
        self.edit_sym = QLineEdit("SPX"); self.edit_sym.setFixedWidth(60)
        cl.addWidget(self.edit_sym)
        cl.addWidget(QLabel("만기:"))
        self.combo_exp = QComboBox()
        for lbl, _, _ in self._exp_list:
            self.combo_exp.addItem(lbl)
        cl.addWidget(self.combo_exp)
        btn = QPushButton("▶ Greeks Matrix 조회")
        btn.setStyleSheet("background:#1a3a6b;font-weight:bold;padding:5px 12px;")
        btn.clicked.connect(self._fetch); cl.addWidget(btn)
        self.lbl_und = QLabel("SPX: ―")
        self.lbl_und.setFont(QFont("Arial", 15, QFont.Bold))
        self.lbl_und.setStyleSheet("color:#ffd700;padding:0 12px;border:none;")
        cl.addWidget(self.lbl_und); cl.addStretch()
        self.lbl_save = QLabel("자동저장: ―")
        self.lbl_save.setStyleSheet("color:#555;font-size:11px;border:none;")
        cl.addWidget(self.lbl_save)
        btn_sv = QPushButton("💾 즉시 저장"); btn_sv.clicked.connect(self._manual_save)
        cl.addWidget(btn_sv)
        self.add(ctrl, 0, 0, 1, 12)

        cols = ["행사가",
                "C 가격", "C Delta", "C Gamma", "C ΔGamma",
                "P 가격", "P Delta", "P Gamma", "P ΔGamma",
                "IV(C)", "IV(P)", "비고"]
        self.tbl = make_table(cols, GREEKS_MATRIX_N * 2 + 1)
        self.add(self.tbl, 1, 0, 3, 12)

    def _connect_signals(self):
        router.register_price(REQ_UND,     REQ_UND,           self._on_tick_price)
        router.register_price(REQ_CHAIN,   REQ_CHAIN + 199,   self._on_tick_price)
        router.register_price(REQ_CHAIN_P, REQ_CHAIN_P + 199, self._on_tick_price)
        router.register_option(REQ_CHAIN,  REQ_CHAIN + 199,   self._on_tick_opt)
        router.register_option(REQ_CHAIN_P, REQ_CHAIN_P + 199, self._on_tick_opt)

    def _get_expiry(self):
        idx = self.combo_exp.currentIndex()
        _, code, tag = self._exp_list[idx]
        if code == "CUSTOM": return None, ""
        return code, tag

    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요."); return
        auto_mdt(self.mw.ib)
        sym       = self.edit_sym.text().strip().upper()
        cp        = self.mw.tab_callput
        und_price = cp.und_price if cp else None
        if not und_price:
            QMessageBox.information(
                self, "대기", "콜-풋 탭에서 먼저 현재가를 수신하세요."); return
        expiry, tag = self._get_expiry()
        if not expiry: return
        _, _, _, step = SYMBOL_CFG.get(sym if sym != "SPXW" else "SPX", DEFAULT_CFG)
        atm = round(und_price / step) * step
        self.strikes = sorted(set([
            atm + i * step for i in range(-GREEKS_MATRIX_N, GREEKS_MATRIX_N + 1)]))
        self.tbl.setRowCount(len(self.strikes))
        self.call_data.clear(); self.put_data.clear(); self.prev_gammas.clear()
        for r, st in enumerate(self.strikes):
            col = "#00ff88" if st == atm else "#ffd700"
            tbl_set(self.tbl, r, 0, str(int(st)), col)
            for c in range(1, 12): tbl_set(self.tbl, r, c, "―")
        ticks = "100,101,106"
        for i, st in enumerate(self.strikes):
            rid_c = REQ_CHAIN + i; rid_p = REQ_CHAIN_P + i
            self.call_data[rid_c] = {"row": i, "strike": st}
            self.put_data[rid_p]  = {"row": i, "strike": st}
            self.mw.ib.reqMktData(
                rid_c, make_opt_contract(sym, st, "C", expiry, tag), ticks, False, False, [])
            self.mw.ib.reqMktData(
                rid_p, make_opt_contract(sym, st, "P", expiry, tag), ticks, False, False, [])

    def _on_tick_price(self, rid, tt, price):
        if price <= 0: return
        if rid == REQ_UND and tt in (4, 14, 75):
            self.lbl_und.setText(f"{self.edit_sym.text()}: {price:,.2f}")
        elif rid in self.call_data and tt in (4, 68):
            tbl_set(self.tbl, self.call_data[rid]["row"], 1, f"{price:.2f}", "#33aaff")
        elif rid in self.put_data and tt in (4, 68):
            tbl_set(self.tbl, self.put_data[rid]["row"], 5, f"{price:.2f}", "#ff6666")

    def _on_tick_opt(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (12, 13): return
        if rid in self.call_data:
            r  = self.call_data[rid]["row"]; st = self.call_data[rid]["strike"]
            tbl_set(self.tbl, r, 2, f"{delta:+.4f}", "#aaddff")
            prev = self.prev_gammas.get((st, "C"), gamma); dg = gamma - prev
            tbl_set(self.tbl, r, 3, f"{gamma:.6f}", "#88ff44")
            tbl_set(self.tbl, r, 4, f"{dg:+.6f}", "#ff4444" if abs(dg) > 0.0001 else "#888")
            self.prev_gammas[(st, "C")] = gamma
            tbl_set(self.tbl, r, 9, f"{iv:.4f}" if iv else "―")
        elif rid in self.put_data:
            r  = self.put_data[rid]["row"]; st = self.put_data[rid]["strike"]
            tbl_set(self.tbl, r, 6, f"{delta:+.4f}", "#ffaaaa")
            prev = self.prev_gammas.get((st, "P"), gamma); dg = gamma - prev
            tbl_set(self.tbl, r, 7, f"{gamma:.6f}", "#88ff44")
            tbl_set(self.tbl, r, 8, f"{dg:+.6f}", "#ff4444" if abs(dg) > 0.0001 else "#888")
            self.prev_gammas[(st, "P")] = gamma
            tbl_set(self.tbl, r, 10, f"{iv:.4f}" if iv else "―")
            c_g = self.prev_gammas.get((st, "C"), 0)
            tbl_set(self.tbl, r, 11,
                    "C↑" if c_g > gamma else ("P↑" if gamma > c_g else ""))

    def _apply_theme(self):
        from core import _apply_table_theme
        _apply_table_theme(self.tbl, getattr(self, 'dark_mode', True))
