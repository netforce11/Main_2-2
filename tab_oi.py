"""
tab_oi.py — OI 추적 탭  v6.2
════════════════════════════════════════════════════════════════
  Tab 8  OITrackerGrid  OI 추적
════════════════════════════════════════════════════════════════
"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QMessageBox, QTableWidgetItem,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QBrush, QColor

from core import (
    GridTab, make_table, tbl_set,
    SYMBOL_CFG, DEFAULT_CFG,
    REQ_OI,
    build_expiry_list, make_opt_contract,
    save_json, load_json, SAVE_DIR,
)


def _mk(text, color=None):
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    if color:
        it.setForeground(QBrush(QColor(color)))
    return it

class OITrackerGrid(GridTab):
    OI_FILE="oi_history.json"

    def __init__(self, mw):
        super().__init__()
        self.mw=mw; self._oi_db={}; self._exp_list=build_expiry_list()
        self._build(); self._load_oi()

    def _build(self):
        ctrl1=QWidget(); cl=QHBoxLayout(ctrl1); cl.setContentsMargins(0,0,0,0)
        cl.addWidget(QLabel("심볼:"))
        self.edit_sym=QLineEdit("SPX"); self.edit_sym.setFixedWidth(60); cl.addWidget(self.edit_sym)
        cl.addWidget(QLabel("만기:"))
        self.combo_exp=QComboBox()
        for lbl,_,_ in self._exp_list: self.combo_exp.addItem(lbl)
        cl.addWidget(self.combo_exp)
        bf=QPushButton("▶ OI 조회"); bf.setStyleSheet("background:#1a3a6b;font-weight:bold;padding:5px 12px;")
        bf.clicked.connect(self._fetch_oi); cl.addWidget(bf)
        for lbl,fn in [("💾 저장",self._save_oi),("📂 불러오기",self._load_oi),("🗑 초기화",self._clear_oi)]:
            b=QPushButton(lbl); b.clicked.connect(fn); cl.addWidget(b)
        cl.addStretch()
        self.add(ctrl1, 0, 0, 1, 6)
        ctrl2=QWidget(); c2=QHBoxLayout(ctrl2); c2.setContentsMargins(0,0,0,0)
        c2.addWidget(QLabel("날짜 비교:"))
        self.combo_d1=QComboBox(); self.combo_d1.setMinimumWidth(110)
        self.combo_d2=QComboBox(); self.combo_d2.setMinimumWidth(110)
        self.combo_d1.currentIndexChanged.connect(self._refresh_table)
        self.combo_d2.currentIndexChanged.connect(self._refresh_table)
        c2.addWidget(self.combo_d1); c2.addWidget(QLabel("↔")); c2.addWidget(self.combo_d2); c2.addStretch()
        self.lbl_date=QLabel("저장된 날짜: ―"); self.lbl_date.setStyleSheet("color:#aaa;font-size:11px;border:none;")
        c2.addWidget(self.lbl_date); self.add(ctrl2, 0, 6, 1, 6)
        gb=QGroupBox("OI 일자별 추이  (행사가 × OI 변화량)"); vl=QVBoxLayout(gb)
        self.tbl_oi=make_table(["행사가","콜 OI","풋 OI","콜 변화","풋 변화","비고"])
        vl.addWidget(self.tbl_oi); self.add(gb, 1, 0, 2, 12)
        gb2=QGroupBox("OI 분석 가이드"); vl2=QVBoxLayout(gb2)
        desc=QLabel("OI(미결제약정): 아직 청산되지 않은 계약 수 — 장 마감 후 T+1 오전에 업데이트.\n"
                    "콜 OI 급증 → 상승 베팅 / 풋 OI 급증 → 하락 베팅\n"
                    "OI 최고 행사가 ≈ Max Pain (시장조성자 유리한 만기 가격)\n"
                    "사용법: 매일 장 마감 후 '▶ OI 조회' → '💾 저장'으로 이력 축적")
        desc.setWordWrap(True); desc.setStyleSheet("color:#aaa;font-size:12px;border:none;")
        vl2.addWidget(desc); self.add(gb2, 3, 0, 1, 12)

    def _get_expiry(self):
        idx=self.combo_exp.currentIndex(); _,code,tag=self._exp_list[idx]
        if code=="CUSTOM": return None, ""
        return code, tag

    def _fetch_oi(self):
        if not self.mw.connected: QMessageBox.warning(self,"미연결","TWS에 연결하세요."); return
        expiry, tag = self._get_expiry()
        if not expiry: return
        sym=self.edit_sym.text().strip().upper()
        cp=self.mw.tab_callput; und_price=cp.und_price if cp else None
        if not und_price: QMessageBox.information(self,"대기","콜-풋 탭에서 현재가를 수신하세요."); return
        _,_,_,step=SYMBOL_CFG.get(sym if sym!="SPXW" else "SPX", DEFAULT_CFG)
        atm=round(und_price/step)*step
        strikes=[atm+i*step for i in range(-20,21)]
        today_s=datetime.today().strftime("%Y-%m-%d"); self._oi_db.setdefault(today_s,{})
        for i,st in enumerate(strikes):
            self.mw.ib.reqMktData(REQ_OI+i,    make_opt_contract(sym,st,"C",expiry,tag),"101",False,False,[])
            self.mw.ib.reqMktData(REQ_OI+100+i, make_opt_contract(sym,st,"P",expiry,tag),"101",False,False,[])
        bridge.tick_price.connect(self._on_oi_tick)
        QTimer.singleShot(5000,self._stop_oi_fetch)
        self.lbl_date.setText(f"조회 중: {today_s}  {sym}")

    def _on_oi_tick(self,rid,tt,price):
        if tt not in (86,87): return
        today_s=datetime.today().strftime("%Y-%m-%d"); self._oi_db.setdefault(today_s,{})
        offset=rid-REQ_OI
        if 0<=offset<100:
            st_k=str(offset); self._oi_db[today_s].setdefault(st_k,{})
            self._oi_db[today_s][st_k]["call"]=int(price)
        elif 100<=offset<200:
            st_k=str(offset-100); self._oi_db[today_s].setdefault(st_k,{})
            self._oi_db[today_s][st_k]["put"]=int(price)

    def _stop_oi_fetch(self):
        for i in range(200):
            try: self.mw.ib.cancelMktData(REQ_OI+i)
            except: pass
        try: bridge.tick_price.disconnect(self._on_oi_tick)
        except: pass
        self._refresh_table(); self.lbl_date.setText("저장된 날짜: "+", ".join(sorted(self._oi_db.keys())[-5:]))

    def _refresh_table(self):
        dates=sorted(self._oi_db.keys())
        for cb in (self.combo_d1,self.combo_d2):
            cur=cb.currentText(); cb.blockSignals(True); cb.clear(); cb.addItems(dates)
            idx=cb.findText(cur)
            if idx>=0: cb.setCurrentIndex(idx)
            cb.blockSignals(False)
        d1=self.combo_d1.currentText(); d2=self.combo_d2.currentText()
        d1_db=self._oi_db.get(d1,{}); d2_db=self._oi_db.get(d2,{})
        keys=sorted(set(list(d1_db)+list(d2_db)),key=lambda x:int(x) if x.isdigit() else 0)
        self.tbl_oi.setRowCount(len(keys))
        for r,st in enumerate(keys):
            c_oi=d2_db.get(st,{}).get("call",0); p_oi=d2_db.get(st,{}).get("put",0)
            c_prev=d1_db.get(st,{}).get("call",0); p_prev=d1_db.get(st,{}).get("put",0)
            c_chg=c_oi-c_prev; p_chg=p_oi-p_prev
            tbl_set(self.tbl_oi,r,0,st,"#ffd700")
            tbl_set(self.tbl_oi,r,1,f"{c_oi:,}"); tbl_set(self.tbl_oi,r,2,f"{p_oi:,}")
            cc="#00ff88" if c_chg>0 else ("#ff4444" if c_chg<0 else "#888")
            pc="#00ff88" if p_chg>0 else ("#ff4444" if p_chg<0 else "#888")
            tbl_set(self.tbl_oi,r,3,f"{c_chg:+,}",cc); tbl_set(self.tbl_oi,r,4,f"{p_chg:+,}",pc)
            tbl_set(self.tbl_oi,r,5,"C↑" if c_chg>p_chg else ("P↑" if p_chg>c_chg else ""))

    def _save_oi(self):
        save_json(self.OI_FILE,self._oi_db)
        QMessageBox.information(self,"저장",f"OI 저장 완료\n({SAVE_DIR/self.OI_FILE})")

    def _load_oi(self):
        self._oi_db=load_json(self.OI_FILE,{}); self._refresh_table()
        self.lbl_date.setText("저장된 날짜: "+", ".join(sorted(self._oi_db.keys())[-5:]))

    def _clear_oi(self):
        ret=QMessageBox.question(self,"초기화","모든 OI 데이터를 삭제합니까?",QMessageBox.Yes|QMessageBox.No)
        if ret==QMessageBox.Yes: self._oi_db.clear(); self.tbl_oi.setRowCount(0)