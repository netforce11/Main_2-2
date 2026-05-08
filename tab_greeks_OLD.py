"""
tab_greeks.py — Greeks Matrix 탭  (Tab 6: GreeksGrid)
"""

import json, csv
from datetime import datetime, date, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QTextEdit, QMessageBox,
    QInputDialog, QFileDialog, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QCheckBox, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, GridTab, make_table, tbl_set, ts, ts_full,
    SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM,
    REQ_UND, REQ_CHAIN, REQ_CHAIN_P, REQ_MULTI, REQ_ACCT,
    GREEKS_MATRIX_N, GREEKS_AUTOSAVE_S,
    build_expiry_list, make_opt_contract, make_und_contract,
    save_json, load_json, append_csv, load_csv, SAVE_DIR, ACCT_TAGS,
    auto_mdt, is_market_open,
)

GREEKS_CSV = "greeks_{date}_{sym}.csv"


class GreeksGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
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
        # [0,0-11] 컨트롤
        ctrl = QWidget(); cl = QHBoxLayout(ctrl); cl.setContentsMargins(0,0,0,0)
        cl.addWidget(QLabel("심볼:"))
        self.edit_sym = QLineEdit("SPX"); self.edit_sym.setFixedWidth(60)
        cl.addWidget(self.edit_sym); cl.addWidget(QLabel("만기:"))
        self.combo_exp = QComboBox()
        for lbl,_,_ in self._exp_list: self.combo_exp.addItem(lbl)
        cl.addWidget(self.combo_exp)
        btn = QPushButton("▶ Greeks Matrix 조회")
        btn.setStyleSheet("background:#1a3a6b;font-weight:bold;padding:5px 12px;")
        btn.clicked.connect(self._fetch); cl.addWidget(btn)
        self.lbl_und = QLabel("SPX: ―")
        self.lbl_und.setFont(QFont("Arial",15,QFont.Bold))
        self.lbl_und.setStyleSheet("color:#ffd700;padding:0 12px;border:none;")
        cl.addWidget(self.lbl_und); cl.addStretch()
        self.lbl_save = QLabel("자동저장: ―")
        self.lbl_save.setStyleSheet("color:#555;font-size:11px;border:none;")
        cl.addWidget(self.lbl_save)
        btn_sv = QPushButton("💾 즉시 저장"); btn_sv.clicked.connect(self._manual_save)
        cl.addWidget(btn_sv)
        self.add(ctrl, 0, 0, 1, 12)

        # [1-3,0-11] Greeks 테이블
        cols = ["행사가",
                "C 가격","C Delta","C Gamma","C ΔGamma",
                "P 가격","P Delta","P Gamma","P ΔGamma",
                "IV(C)","IV(P)","비고"]
        self.tbl = make_table(cols, GREEKS_MATRIX_N*2+1)
        self.add(self.tbl, 1, 0, 3, 12)

    def _connect_signals(self):
        # Greeks Matrix 전용 범위만 라우팅 (REQ_UND 도 포함하여 기초자산 가격 수신)
        router.register_price(REQ_UND,    REQ_UND,         self._on_tick_price)
        router.register_price(REQ_CHAIN,  REQ_CHAIN+199,   self._on_tick_price)
        router.register_price(REQ_CHAIN_P,REQ_CHAIN_P+199, self._on_tick_price)
        router.register_option(REQ_CHAIN, REQ_CHAIN+199,   self._on_tick_opt)
        router.register_option(REQ_CHAIN_P,REQ_CHAIN_P+199,self._on_tick_opt)

    def _get_expiry(self):
        idx = self.combo_exp.currentIndex(); _,code,tag = self._exp_list[idx]
        if code=="CUSTOM": return None, ""
        return code, tag

    def _fetch(self):
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        auto_mdt(self.mw.ib)
        sym = self.edit_sym.text().strip().upper()
        cp  = self.mw.tab_callput
        und_price = cp.und_price if cp else None
        if not und_price:
            QMessageBox.information(self,"대기","콜-풋 탭에서 먼저 현재가를 수신하세요."); return
        expiry, tag = self._get_expiry()
        if not expiry: return
        _,_,_,step = SYMBOL_CFG.get(sym if sym!="SPXW" else "SPX", DEFAULT_CFG)
        atm = round(und_price/step)*step
        self.strikes = sorted(set([atm+i*step for i in range(-GREEKS_MATRIX_N,GREEKS_MATRIX_N+1)]))
        self.tbl.setRowCount(len(self.strikes))
        self.call_data.clear(); self.put_data.clear(); self.prev_gammas.clear()
        for r,st in enumerate(self.strikes):
            col="#00ff88" if st==atm else "#ffd700"
            tbl_set(self.tbl,r,0,str(int(st)),col)
            for c in range(1,12): tbl_set(self.tbl,r,c,"―")
        ticks = "100,101,106"   # OPT 허용 ticks (ERR 321 방지)
        for i,st in enumerate(self.strikes):
            rid_c=REQ_CHAIN+i; rid_p=REQ_CHAIN_P+i
            self.call_data[rid_c]={"row":i,"strike":st}
            self.put_data[rid_p]={"row":i,"strike":st}
            self.mw.ib.reqMktData(rid_c,make_opt_contract(sym,st,"C",expiry,tag),ticks,False,False,[])
            self.mw.ib.reqMktData(rid_p,make_opt_contract(sym,st,"P",expiry,tag),ticks,False,False,[])

    def _on_tick_price(self, rid, tt, price):
        if price<=0: return
        if rid==REQ_UND and tt in (4,14,75):
            self.lbl_und.setText(f"{self.edit_sym.text()}: {price:,.2f}")
        elif rid in self.call_data and tt in (4,68):
            r=self.call_data[rid]["row"]; tbl_set(self.tbl,r,1,f"{price:.2f}","#33aaff")
        elif rid in self.put_data and tt in (4,68):
            r=self.put_data[rid]["row"]; tbl_set(self.tbl,r,5,f"{price:.2f}","#ff6666")

    def _on_tick_opt(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (12,13): return
        if rid in self.call_data:
            r=self.call_data[rid]["row"]; st=self.call_data[rid]["strike"]
            tbl_set(self.tbl,r,2,f"{delta:+.4f}","#aaddff")
            prev=self.prev_gammas.get((st,"C"),gamma); dg=gamma-prev
            tbl_set(self.tbl,r,3,f"{gamma:.6f}","#88ff44")
            tbl_set(self.tbl,r,4,f"{dg:+.6f}","#ff4444" if abs(dg)>0.0001 else "#888")
            self.prev_gammas[(st,"C")]=gamma
            tbl_set(self.tbl,r,9,f"{iv:.4f}" if iv else "―")
        elif rid in self.put_data:
            r=self.put_data[rid]["row"]; st=self.put_data[rid]["strike"]
            tbl_set(self.tbl,r,6,f"{delta:+.4f}","#ffaaaa")
            prev=self.prev_gammas.get((st,"P"),gamma); dg=gamma-prev
            tbl_set(self.tbl,r,7,f"{gamma:.6f}","#88ff44")
            tbl_set(self.tbl,r,8,f"{dg:+.6f}","#ff4444" if abs(dg)>0.0001 else "#888")
            self.prev_gammas[(st,"P")]=gamma
            tbl_set(self.tbl,r,10,f"{iv:.4f}" if iv else "―")
            c_g=self.prev_gammas.get((st,"C"),0)
            tbl_set(self.tbl,r,11,"C↑" if c_g>gamma else ("P↑" if gamma>c_g else ""))

    def _snapshot(self):
        rows=[]; ts_now=ts_full()
        for r in range(self.tbl.rowCount()):
            def g(c): return (self.tbl.item(r,c).text() if self.tbl.item(r,c) else "")
            rows.append({"time":ts_now,"strike":g(0),
                         "c_price":g(1),"c_delta":g(2),"c_gamma":g(3),"c_dgamma":g(4),
                         "p_price":g(5),"p_delta":g(6),"p_gamma":g(7),"p_dgamma":g(8),
                         "iv_c":g(9),"iv_p":g(10)})
        return rows

    def _autosave(self):
        if not self.strikes: return
        snap=self._snapshot()
        if not snap: return
        sym=self.edit_sym.text().strip().upper()
        fname=GREEKS_CSV.format(date=date.today().isoformat(),sym=sym)
        path=SAVE_DIR/fname; write_hdr=not path.exists()
        with open(path,"a",newline="",encoding="utf-8") as f:
            import csv as _csv
            w=_csv.DictWriter(f,fieldnames=snap[0].keys())
            if write_hdr: w.writeheader()
            w.writerows(snap)
        self.lbl_save.setText(f"자동저장: {ts()}")

    def _manual_save(self):
        self._autosave()
        QMessageBox.information(self,"저장","Greeks 스냅샷 저장 완료")

    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 호출 — 테이블 색상 명시 재적용."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        _apply_table_theme(self.tbl, dark)