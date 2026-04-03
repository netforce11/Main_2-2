"""
tab_account.py — 계좌·그릭스 관련 탭  v6.1
════════════════════════════════════════════════════════════════
  Tab 2  BalanceGrid       잔고/PnL — 계좌 요약 상단 좌측 배치
  Tab 5  MultiPriceGrid    복수 현재가 — 트리거 등록·수정 가능 테이블
  Tab 6  GreeksGrid        Greeks Matrix — 15초 자동저장
════════════════════════════════════════════════════════════════
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
    QSplitter, QCheckBox,
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

PNL_HIST_CSV = "pnl_history.csv"


# ══════════════════════════════════════════════════════════════
# Tab 2: 잔고 / PnL
# 레이아웃:
#   [0,0-11] 대형 PnL 표시
#   [1,0-3]  계좌 요약 (상단 좌측)  [1,4-7] 주요 지표  [1,8-11] 포지션
#   [2,0-3]  일자별 차트             [2,4-7] Session Stats  [2,8-11] 미체결
#   [3,0-11] 버튼 바
# ══════════════════════════════════════════════════════════════
class BalanceGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self._acct_rows = {}
        self._pnl_history = []
        self._session = {"trades": [], "start_time": ts_full()}
        self._build()
        self._connect_signals()
        self._load_history()

    def _build(self):
        # [0,0-11] 대형 PnL
        self.lbl_pnl = QLabel("미실현 PnL: ―")
        self.lbl_pnl.setFont(QFont("Arial", 42, QFont.Bold))
        self.lbl_pnl.setAlignment(Qt.AlignCenter)
        self.lbl_pnl.setStyleSheet(
            "color:#aaa;background:#0a0a1a;border-radius:10px;border:none;")
        self.add(self.lbl_pnl, 0, 0, 1, 12)

        # [1,0-3] 계좌 요약 테이블 (상단 좌측)
        gb1 = QGroupBox("계좌 요약")
        v1  = QVBoxLayout(gb1)
        self.tbl_acct = make_table(["항목", "값", "통화"], 0)
        self.tbl_acct.setRowCount(0)
        v1.addWidget(self.tbl_acct)
        self.add(gb1, 1, 0, 1, 4)

        # [1,4-7] 주요 지표 (빅 넘버)
        gb_big = QGroupBox("주요 지표")
        v_big  = QVBoxLayout(gb_big)
        self.lbl_nlv  = self._big("총자산 (NLV)", "#ffd700")
        self.lbl_bp   = self._big("사용가능 증거금", "#00cfff")
        self.lbl_rpnl = self._big("실현 PnL", "#00ff88")
        for w in (self.lbl_nlv, self.lbl_bp, self.lbl_rpnl):
            v_big.addWidget(w)
        self.add(gb_big, 1, 4, 1, 4)

        # [1,8-11] 포지션
        gb2 = QGroupBox("현재 포지션")
        v2  = QVBoxLayout(gb2)
        self.tbl_pos = make_table(["계좌", "심볼", "종류", "수량", "평균단가"], 0)
        self.tbl_pos.setRowCount(0)
        v2.addWidget(self.tbl_pos)
        self.add(gb2, 1, 8, 1, 4)

        # [2,0-3] 일자별 잔고·손익 차트
        gb_chart = QGroupBox("일자별 잔고·손익 추이")
        vc = QVBoxLayout(gb_chart)
        if PG:
            pg.setConfigOption('background', '#08080f')
            pg.setConfigOption('foreground', '#ccc')
            self.pw_nlv = pg.PlotWidget(title="총자산")
            self.pw_nlv.showGrid(x=True, y=True, alpha=0.2)
            self.pw_nlv.setMaximumHeight(100)
            self.curve_nlv = self.pw_nlv.plot(
                pen=pg.mkPen('#ffd700', width=2), symbol='o',
                symbolSize=5, symbolBrush='#ffd700')
            self.pw_pnl = pg.PlotWidget(title="일별 손익")
            self.pw_pnl.showGrid(x=True, y=True, alpha=0.2)
            self.pw_pnl.setMaximumHeight(100)
            self.pw_pnl.addLine(y=0, pen=pg.mkPen('#555', width=1))
            self.curve_pnl = self.pw_pnl.plot(
                pen=pg.mkPen('#00ff88', width=2), symbol='o',
                symbolSize=5, symbolBrush='#00ff88')
            vc.addWidget(self.pw_nlv); vc.addWidget(self.pw_pnl)
        else:
            vc.addWidget(QLabel("pip install pyqtgraph"))
        self.add(gb_chart, 2, 0, 1, 4)

        # [2,4-7] Session Stats
        gb3 = QGroupBox("Session Stats (누적 통계)")
        g3  = QGridLayout(gb3)
        self.lbl_winrate = QLabel("승률: ―")
        self.lbl_avghold = QLabel("평균 보유: ―")
        self.lbl_tot_pnl = QLabel("누적 손익: ―")
        self.lbl_tot_cnt = QLabel("총 거래: ―")
        for lb, col in [(self.lbl_winrate,"#00ff88"),(self.lbl_avghold,"#5dade2"),
                        (self.lbl_tot_pnl,"#ffd700"),(self.lbl_tot_cnt,"#dde0f0")]:
            lb.setFont(QFont("Arial", 14, QFont.Bold))
            lb.setStyleSheet(f"color:{col};border:none;"); lb.setAlignment(Qt.AlignCenter)
        g3.addWidget(self.lbl_winrate, 0, 0); g3.addWidget(self.lbl_avghold, 0, 1)
        g3.addWidget(self.lbl_tot_pnl, 1, 0); g3.addWidget(self.lbl_tot_cnt, 1, 1)
        self.tbl_trades = make_table(
            ["시간","심볼","방향","수량","진입가","청산가","PnL","보유(분)"], 0)
        g3.addWidget(self.tbl_trades, 2, 0, 1, 2)
        btn_clr = QPushButton("Session 초기화"); btn_clr.clicked.connect(self._clear_session)
        g3.addWidget(btn_clr, 3, 0, 1, 2)
        self.add(gb3, 2, 4, 1, 4)

        # [2,8-11] 미체결 주문
        gb4 = QGroupBox("미체결 주문")
        v4  = QVBoxLayout(gb4)
        self.tbl_ord = make_table(
            ["ID","심볼","종류","매수/도","수량","지정가","상태"], 0)
        self.tbl_ord.setRowCount(0)
        v4.addWidget(self.tbl_ord)
        self.add(gb4, 2, 8, 1, 4)

        # [3,0-11] 버튼 바
        br = QWidget(); bl = QHBoxLayout(br)
        btn_r = QPushButton("↺ 전체 새로고침")
        btn_r.setStyleSheet("background:#1a4a6b;font-size:14px;font-weight:bold;padding:8px;")
        btn_r.clicked.connect(self._refresh)
        btn_sv = QPushButton("💾 PnL 이력 저장"); btn_sv.clicked.connect(self._save_history)
        bl.addWidget(btn_r); bl.addWidget(btn_sv); bl.addStretch()
        self.lbl_time = QLabel("마지막 업데이트: ―")
        self.lbl_time.setStyleSheet("color:#555;font-size:11px;border:none;")
        bl.addWidget(self.lbl_time)
        self.add(br, 3, 0, 1, 12)

    def _big(self, title, color):
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(4, 2, 4, 2)
        lt = QLabel(title); lt.setStyleSheet("color:#888;font-size:11px;border:none;")
        lv = QLabel("―"); lv.setFont(QFont("Arial", 18, QFont.Bold))
        lv.setStyleSheet(f"color:{color};border:none;"); lv.setAlignment(Qt.AlignCenter)
        v.addWidget(lt); v.addWidget(lv); w._val = lv; return w

    def _connect_signals(self):
        bridge.acct_value.connect(self._on_acct)
        bridge.position_sig.connect(self._on_pos)
        bridge.open_order_sig.connect(self._on_order)

    def _refresh(self):
        self.tbl_acct.setRowCount(0); self.tbl_pos.setRowCount(0)
        self.tbl_ord.setRowCount(0); self._acct_rows.clear()
        if self.mw.connected:
            try:
                self.mw.ib.reqAccountSummary(REQ_ACCT, "All", ACCT_TAGS)
                self.mw.ib.reqPositions()
                self.mw.ib.reqAllOpenOrders()
            except Exception as e: print(f"계좌 조회 오류: {e}")
        self.lbl_time.setText(f"마지막: {ts()}")

    def _on_acct(self, tag, val, cur, acct):
        if tag not in self._acct_rows:
            r = self.tbl_acct.rowCount(); self.tbl_acct.insertRow(r)
            self._acct_rows[tag] = r; tbl_set(self.tbl_acct, r, 0, tag)
        r = self._acct_rows[tag]
        try: disp = f"{float(val):,.2f}"
        except: disp = val
        tbl_set(self.tbl_acct, r, 1, disp); tbl_set(self.tbl_acct, r, 2, cur)
        if tag == "UnrealizedPnL":
            try:
                v = float(val); sign = "+" if v >= 0 else ""
                col = "#00ff88" if v >= 0 else "#ff4444"
                self.lbl_pnl.setText(f"미실현 PnL: {sign}${v:,.2f}")
                self.lbl_pnl.setStyleSheet(
                    f"color:{col};background:#0a0a1a;border-radius:10px;"
                    "font-size:42px;font-weight:bold;border:none;")
                self.tbl_acct.item(r,1).setForeground(QBrush(QColor(col)))
                self._record_pnl(0.0, v)
            except: pass
        if tag == "NetLiquidation":
            try:
                self.lbl_nlv._val.setText(f"${float(val):,.0f}")
                self._record_pnl(float(val), 0.0)
            except: pass
        if tag == "BuyingPower":
            try: self.lbl_bp._val.setText(f"${float(val):,.0f}")
            except: pass
        if tag == "RealizedPnL":
            try:
                v = float(val); col = "#00ff88" if v >= 0 else "#ff4444"
                self.lbl_rpnl._val.setText(f"${v:,.2f}")
                self.lbl_rpnl._val.setStyleSheet(f"color:{col};border:none;")
            except: pass

    def _on_pos(self, acct, sym, right, pos, avg):
        r = self.tbl_pos.rowCount(); self.tbl_pos.insertRow(r)
        for c, v in enumerate([acct, sym, right, str(int(pos)), f"{avg:.2f}"]):
            tbl_set(self.tbl_pos, r, c, v)
        col = "#00ff88" if pos > 0 else "#ff4444"
        self.tbl_pos.item(r,3).setForeground(QBrush(QColor(col)))

    def _on_order(self, oid, sym, right, action, qty, price, status):
        for rr in range(self.tbl_ord.rowCount()):
            if self.tbl_ord.item(rr,0) and self.tbl_ord.item(rr,0).text()==str(oid):
                tbl_set(self.tbl_ord,rr,6,status); return
        r = self.tbl_ord.rowCount(); self.tbl_ord.insertRow(r)
        for c,v in enumerate([str(oid),sym,right,action,str(int(qty)),f"{price:.2f}",status]):
            tbl_set(self.tbl_ord,r,c,v)
        col = "#33aaff" if action=="BUY" else "#ff8844"
        self.tbl_ord.item(r,3).setForeground(QBrush(QColor(col)))

    def _record_pnl(self, nlv, pnl):
        today = date.today().isoformat()
        if not self._pnl_history or self._pnl_history[-1][0] != today:
            if nlv > 0:
                self._pnl_history.append((today, nlv, pnl))
                self._update_chart()

    def _update_chart(self):
        if not PG or len(self._pnl_history) < 1: return
        xs   = list(range(len(self._pnl_history)))
        nlvs = [h[1] for h in self._pnl_history]
        pnls = [h[2] for h in self._pnl_history]
        self.curve_nlv.setData(xs, nlvs); self.curve_pnl.setData(xs, pnls)

    def _save_history(self):
        for date_s, nlv, pnl in self._pnl_history:
            append_csv(PNL_HIST_CSV, {"date": date_s, "nlv": nlv, "pnl": pnl})
        QMessageBox.information(self, "저장",
            f"PnL 이력 저장 완료 ({SAVE_DIR/PNL_HIST_CSV})")

    def _load_history(self):
        rows = load_csv(PNL_HIST_CSV)
        self._pnl_history = [
            (r["date"], float(r["nlv"]), float(r["pnl"])) for r in rows]
        self._update_chart()
        self._update_session_stats()

    def _clear_session(self):
        self._session = {"trades": [], "start_time": ts_full()}
        self.tbl_trades.setRowCount(0); self._update_session_stats()

    def add_trade(self, sym, direction, qty, entry, exit_p, hold_min):
        pnl = (exit_p-entry)*qty*100*(1 if direction=="BUY" else -1)
        self._session["trades"].append({
            "time":ts(),"sym":sym,"dir":direction,"qty":qty,
            "entry":entry,"exit":exit_p,"pnl":pnl,"hold":hold_min})
        r = self.tbl_trades.rowCount(); self.tbl_trades.insertRow(r)
        for c,v in enumerate([ts(),sym,direction,str(qty),
                               f"{entry:.2f}",f"{exit_p:.2f}",
                               f"${pnl:,.2f}",f"{hold_min:.1f}"]):
            tbl_set(self.tbl_trades,r,c,v)
        col="#00ff88" if pnl>=0 else "#ff4444"
        self.tbl_trades.item(r,6).setForeground(QBrush(QColor(col)))
        self._update_session_stats()

    def _update_session_stats(self):
        trades=self._session.get("trades",[])
        cnt=len(trades)
        if cnt==0:
            for lb in (self.lbl_winrate,self.lbl_avghold,self.lbl_tot_pnl,self.lbl_tot_cnt):
                lb.setText(lb.text().split(":")[0]+": ―")
            return
        wins=sum(1 for t in trades if t["pnl"]>=0)
        avg_hold=sum(t["hold"] for t in trades)/cnt
        tot_pnl=sum(t["pnl"] for t in trades)
        wr_col="#00ff88" if wins/cnt>=0.5 else "#ff4444"
        pnl_col="#00ff88" if tot_pnl>=0 else "#ff4444"
        self.lbl_winrate.setText(f"승률: {wins/cnt*100:.1f}%")
        self.lbl_winrate.setStyleSheet(f"color:{wr_col};border:none;")
        self.lbl_avghold.setText(f"평균 보유: {avg_hold:.1f}분")
        self.lbl_tot_pnl.setText(f"누적 손익: ${tot_pnl:,.2f}")
        self.lbl_tot_pnl.setStyleSheet(f"color:{pnl_col};border:none;")
        self.lbl_tot_cnt.setText(f"총 거래: {cnt}건")

    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 호출 — 테이블 색상 명시 재적용."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        for tbl in (self.tbl_acct, self.tbl_pos, self.tbl_ord, self.tbl_trades):
            _apply_table_theme(tbl, dark)


# ══════════════════════════════════════════════════════════════
# Tab 5: 복수 현재가
# 트리거: 등록 테이블 (수정 가능) + 등록 상태 표시
# ══════════════════════════════════════════════════════════════
class MultiPriceGrid(GridTab):
    """
    복수 현재가 탭 v2.0
    레이아웃 (12열 × 4행):
      [0,0-1]  관심종목 (좁게)
      [0,2-5]  슬롯1
      [0,6-9]  슬롯2
      [0,10-11] 슬롯3 (우측)
      [1,2-5]  슬롯3 (슬롯3은 행1에 배치)
      ↓ 실제 배치:
      행0: 관심종목(0-1) | 슬롯1(2-5) | 슬롯2(6-9) | 슬롯3(10-11+행1)
      행1: 관심종목이어짐 | 트리거등록(2-5) | 트리거등록이어짐
      행2: 등록된 트리거(0-7) | [우측여백]
      행3: 트리거 이벤트 로그(0-7) | 저장버튼(8-11)

    → 슬롯 3개 가로 나란히, 관심종목 좁게, 트리거는 하단
    """
    SLOTS = 3

    def __init__(self, mw):
        super().__init__()
        self.mw        = mw
        self.slot_data = [{} for _ in range(self.SLOTS)]
        self.slot_rids = [REQ_MULTI + i*100 for i in range(self.SLOTS)]
        self.trigger_logs = []
        self._alert_sound_path = ""   # 트리거 발동 알람 사운드 경로
        self._build()
        self._connect_signals()
        self._restore_sound_setting()

    def _build(self):
        # ── [0-1, 0-1] 관심종목 (좁게, 2열 × 2행) ──────────────
        gb_w = QGroupBox("관심종목")
        vw   = QVBoxLayout(gb_w)
        self.watch = QListWidget()
        self.watch.addItems([
            "SPX","SPXW","NDX","QQQ","SPY",
            "AAPL","TSLA","NVDA","AMZN","MSFT"])
        self.watch.itemClicked.connect(self._on_watch_click)
        vw.addWidget(self.watch)
        wa = QHBoxLayout()
        ba = QPushButton("추가"); bd = QPushButton("삭제")
        ba.setFixedHeight(22); bd.setFixedHeight(22)
        ba.clicked.connect(self._w_add); bd.clicked.connect(self._w_del)
        wa.addWidget(ba); wa.addWidget(bd)
        vw.addLayout(wa)
        # 관심종목은 슬롯 수평 스플리터 앞에 별도 배치 불가 → 슬롯1 상단에 통합
        # (슬롯 수평 스플리터가 행0 전체를 차지하므로 watchlist는 별도 탭으로 이동)
        # 관심종목을 별도 좁은 위젯으로 왼쪽에 배치 (행 0-1, 별도 GridTab 셀)
        self.add(gb_w, 1, 0, 1, 1)   # 행1 좁게

        # ── 슬롯 스플리터 스타일 ─────────────────────────────────
        _sh = ("QSplitter::handle:horizontal{background:#5a5a9a;border-left:1px solid #00aaff;border-right:1px solid #00aaff;margin:4px 0;}QSplitter::handle:horizontal:hover{background:#5dade2;border-left:1px solid #00e676;border-right:1px solid #00e676;}QSplitter::handle:vertical{background:#5a5a9a;border-top:1px solid #00aaff;border-bottom:1px solid #00aaff;margin:0 4px;}QSplitter::handle:vertical:hover{background:#5dade2;border-top:1px solid #00e676;border-bottom:1px solid #00e676;}")

        # ── 슬롯 3개 + 스플리터 (가로로 나란히, row0 전체) ──────
        # 슬롯 너비: 3열, 3열, 4열 → 단일 수평 스플리터로 묶어 행0 전체 차지
        self.slot_w = []
        self._slot_splitters = []   # 각 슬롯 내부 수직 스플리터

        # 전체 3슬롯을 하나의 수평 스플리터로 묶기
        self._slots_hsplit = QSplitter(Qt.Horizontal)
        self._slots_hsplit.setHandleWidth(5)
        self._slots_hsplit.setStyleSheet(_sh)
        self._slots_hsplit.setChildrenCollapsible(False)

        for i in range(self.SLOTS):
            gb = QGroupBox(f"슬롯 {i+1}")
            # 슬롯 내부: 수직 스플리터 (현재가 패널 | 상세 테이블)
            v_spl = QSplitter(Qt.Vertical)
            v_spl.setHandleWidth(5)
            v_spl.setStyleSheet(_sh)
            v_spl.setChildrenCollapsible(False)

            # ── 상단 패널: 심볼 + 현재가 + 입력 ──────────────────
            top_w = QWidget(); top_v = QVBoxLayout(top_w)
            top_v.setSpacing(3); top_v.setContentsMargins(4,4,4,4)

            lsym = QLabel("―")
            lsym.setFont(QFont("Arial", 12, QFont.Bold))
            lsym.setStyleSheet("color:#ffd700;border:none;")
            lsym.setAlignment(Qt.AlignCenter)

            lprice = QLabel("현재가: ―")
            lprice.setFont(QFont("Arial", 22, QFont.Bold))
            lprice.setAlignment(Qt.AlignCenter)
            lprice.setStyleSheet(
                "color:#00ff88;background:#07070f;"
                "border-radius:6px;padding:6px;border:1px solid #1e2050;")
            lprice.setMinimumHeight(54)

            sym_in = QLineEdit()
            sym_in.setPlaceholderText(f"종목 입력 (슬롯{i+1})")
            sym_in.setFixedHeight(24)
            btn_load = QPushButton("조회")
            btn_load.setFixedHeight(24); btn_load.setFixedWidth(48)
            btn_load.clicked.connect(lambda _, idx=i: self._load_from_input(idx))
            sym_in.returnPressed.connect(lambda idx=i: self._load_from_input(idx))
            inp_row = QHBoxLayout(); inp_row.setContentsMargins(0,0,0,0)
            inp_row.addWidget(sym_in); inp_row.addWidget(btn_load)

            top_v.addWidget(lsym)
            top_v.addWidget(lprice)
            top_v.addLayout(inp_row)
            v_spl.addWidget(top_w)

            # ── 하단 패널: 상세 테이블 ────────────────────────────
            tbl = make_table(["항목","값"], 0)
            for kk in ["체결가","거래량","Delta","Gamma","Theta","전일종가"]:
                r2 = tbl.rowCount(); tbl.insertRow(r2)
                tbl_set(tbl, r2, 0, kk); tbl_set(tbl, r2, 1, "―")
            v_spl.addWidget(tbl)
            v_spl.setSizes([120, 200])

            # gb 레이아웃에 수직 스플리터 넣기
            gb_v = QVBoxLayout(gb); gb_v.setContentsMargins(2,2,2,2)
            gb_v.addWidget(v_spl)

            self._slot_splitters.append(v_spl)
            self.slot_w.append({
                "sym": lsym, "price": lprice, "tbl": tbl, "input": sym_in})
            self._slots_hsplit.addWidget(gb)

        self._slots_hsplit.setSizes([400, 400, 400])
        self.add(self._slots_hsplit, 0, 0, 1, 12)  # 행0 전체 12열

        # ══════════════════════════════════════════════════════
        # 하단 수평 스플리터: 트리거 영역 | 파일·사운드 패널
        # ══════════════════════════════════════════════════════
        self._bot_hsplit = QSplitter(Qt.Horizontal)
        self._bot_hsplit.setHandleWidth(5)
        self._bot_hsplit.setStyleSheet(_sh)
        self._bot_hsplit.setChildrenCollapsible(False)

        # ── 좌측: 트리거 등록 + 목록 + 로그 (수직 스플리터) ─────
        self._bot_left_vsplit = QSplitter(Qt.Vertical)
        self._bot_left_vsplit.setHandleWidth(5)
        self._bot_left_vsplit.setStyleSheet(_sh)
        self._bot_left_vsplit.setChildrenCollapsible(False)

        # 트리거 등록 패널
        gb_trg = QGroupBox("조건 트리거 등록")
        gl = QGridLayout(gb_trg); gl.setSpacing(4)
        gl.addWidget(QLabel("가격 조건 (≤):"), 0, 0)
        self.trg_price = QLineEdit(); self.trg_price.setPlaceholderText("예: 5.00")
        gl.addWidget(self.trg_price, 0, 1)
        gl.addWidget(QLabel("시간 조건 (≥):"), 0, 2)
        self.trg_time = QLineEdit(); self.trg_time.setPlaceholderText("HH:MM:SS")
        gl.addWidget(self.trg_time, 0, 3)
        gl.addWidget(QLabel("설명:"), 1, 0)
        self.trg_desc = QLineEdit(); self.trg_desc.setPlaceholderText("예: 09:45 급락 감지")
        gl.addWidget(self.trg_desc, 1, 1, 1, 2)
        btn_add = QPushButton("▶ 트리거 등록")
        btn_add.setStyleSheet("background:#1a3a6b;font-weight:bold;")
        btn_add.clicked.connect(self._add_trigger)
        gl.addWidget(btn_add, 1, 3)
        gb_trg.setMinimumHeight(80)
        self._bot_left_vsplit.addWidget(gb_trg)

        # 등록된 트리거 목록
        gb3 = QGroupBox("등록된 트리거  (더블클릭→수정 / Del→삭제)")
        v3  = QVBoxLayout(gb3)
        self.tbl_trg = QTableWidget(0, 4)
        self.tbl_trg.setHorizontalHeaderLabels(["가격조건","시간조건","설명","상태"])
        self.tbl_trg.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_trg.verticalHeader().setVisible(False)
        self.tbl_trg.setAlternatingRowColors(True)
        self.tbl_trg.setStyleSheet("QTableWidget{alternate-background-color:#0c0c20;}")
        self.tbl_trg.cellDoubleClicked.connect(self._on_trg_dbl)
        self.tbl_trg.keyPressEvent = self._trg_keypress
        v3.addWidget(self.tbl_trg)
        tr = QHBoxLayout()
        btn_del = QPushButton("선택 삭제"); btn_del.clicked.connect(self._del_trigger)
        btn_clr = QPushButton("전체 초기화"); btn_clr.clicked.connect(self._clr_triggers)
        tr.addWidget(btn_del); tr.addWidget(btn_clr); tr.addStretch()
        v3.addLayout(tr)
        gb3.setMinimumHeight(80)
        self._bot_left_vsplit.addWidget(gb3)

        # 트리거 이벤트 로그
        gb4 = QGroupBox("트리거 이벤트 로그")
        v4  = QVBoxLayout(gb4)
        self.trg_log = QTextEdit(); self.trg_log.setReadOnly(True)
        v4.addWidget(self.trg_log)
        gb4.setMinimumHeight(60)
        self._bot_left_vsplit.addWidget(gb4)
        self._bot_left_vsplit.setSizes([90, 150, 120])

        self._bot_hsplit.addWidget(self._bot_left_vsplit)

        # ── 우측: 파일 저장 + 사운드 설정 (수직 스플리터) ───────
        self._bot_right_vsplit = QSplitter(Qt.Vertical)
        self._bot_right_vsplit.setHandleWidth(5)
        self._bot_right_vsplit.setStyleSheet(_sh)
        self._bot_right_vsplit.setChildrenCollapsible(False)

        # 파일 저장/불러오기
        gb5 = QGroupBox("파일")
        v5  = QVBoxLayout(gb5); v5.setSpacing(6)
        btn_sv = QPushButton("💾 로그 저장"); btn_sv.clicked.connect(self._save_log)
        btn_ld = QPushButton("📂 로그 불러오기"); btn_ld.clicked.connect(self._load_log)
        self.lbl_file = QLabel("파일: ―")
        self.lbl_file.setStyleSheet("color:#555;font-size:11px;border:none;")
        self.lbl_file.setWordWrap(True)
        for w in (btn_sv, btn_ld, self.lbl_file): v5.addWidget(w)
        v5.addStretch()
        gb5.setMinimumHeight(80)
        self._bot_right_vsplit.addWidget(gb5)

        # 🔊 사운드 설정 (트리거 발동 알람)
        gb_snd = QGroupBox("🔊 알람 사운드 설정")
        v_snd  = QVBoxLayout(gb_snd); v_snd.setSpacing(6)

        snd_row1 = QHBoxLayout()
        lbl_snd = QLabel("선택 파일:")
        lbl_snd.setStyleSheet("color:#aaa;font-size:11px;border:none;")
        self.lbl_snd_file = QLabel("기본 비프음")
        self.lbl_snd_file.setStyleSheet(
            "color:#ffd700;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:1px 4px;background:#0a0a1e;")
        self.lbl_snd_file.setWordWrap(False)
        self.lbl_snd_file.setMaximumWidth(160)
        snd_row1.addWidget(lbl_snd)
        snd_row1.addWidget(self.lbl_snd_file, 1)
        v_snd.addLayout(snd_row1)

        snd_row2 = QHBoxLayout(); snd_row2.setSpacing(4)
        btn_snd_pick = QPushButton("📂 파일 선택")
        btn_snd_pick.setStyleSheet(
            "background:#1a3a6b;color:#90caf9;font-size:10px;padding:3px 6px;")
        btn_snd_pick.clicked.connect(self._pick_alert_sound)
        btn_snd_test = QPushButton("▶ 테스트")
        btn_snd_test.setStyleSheet(
            "background:#2d2d2d;color:#ffd700;font-size:10px;padding:3px 6px;")
        btn_snd_test.clicked.connect(self._play_alert_sound)
        btn_snd_clr = QPushButton("✕ 초기화")
        btn_snd_clr.setStyleSheet(
            "background:#4a1a1a;color:#ff8888;font-size:10px;padding:3px 6px;")
        btn_snd_clr.clicked.connect(self._clear_alert_sound)
        snd_row2.addWidget(btn_snd_pick)
        snd_row2.addWidget(btn_snd_test)
        snd_row2.addWidget(btn_snd_clr)
        v_snd.addLayout(snd_row2)

        # 기본값으로 저장 체크박스
        self.chk_snd_default = QCheckBox("이 파일을 기본값으로 저장")
        self.chk_snd_default.setStyleSheet("color:#90caf9;font-size:10px;")
        self.chk_snd_default.setChecked(True)
        v_snd.addWidget(self.chk_snd_default)
        v_snd.addStretch()

        gb_snd.setMinimumHeight(80)
        self._bot_right_vsplit.addWidget(gb_snd)
        self._bot_right_vsplit.setSizes([120, 140])
        self._bot_right_vsplit.setMaximumWidth(280)

        self._bot_hsplit.addWidget(self._bot_right_vsplit)
        self._bot_hsplit.setSizes([800, 220])

        self.add(self._bot_hsplit, 1, 1, 3, 11)

    def _connect_signals(self):
        router.register_price(REQ_MULTI, REQ_MULTI+299, self._on_tick)
        router.register_option(REQ_MULTI, REQ_MULTI+299, self._on_tick_opt)

    # ── 슬롯 로딩 ────────────────────────────────────────────────
    def _on_watch_click(self, item):
        sym  = item.text().split()[0]
        slot = next((i for i,d in enumerate(self.slot_data) if not d.get("sym")), 0)
        self._load_slot(slot, sym)

    def _load_from_input(self, idx):
        sym = self.slot_w[idx]["input"].text().strip().upper()
        if sym: self._load_slot(idx, sym)

    def _load_slot(self, idx, sym):
        if not self.mw.connected:
            self.slot_w[idx]["price"].setText("미연결")
            return
        auto_mdt(self.mw.ib)
        rid = self.slot_rids[idx]
        try: self.mw.ib.cancelMktData(rid)
        except: pass
        self.slot_data[idx] = {"sym": sym}
        self.slot_w[idx]["sym"].setText(sym)
        self.slot_w[idx]["price"].setText("조회 중…")
        self.slot_w[idx]["input"].setText(sym)
        self.mw.ib.reqMktData(rid, make_und_contract(sym), "232", False, False, [])

    # ── Tick 수신 ────────────────────────────────────────────────
    def _on_tick(self, rid, tt, price):
        if price <= 0: return
        for i, base in enumerate(self.slot_rids):
            if rid != base: continue
            if tt in (4, 14, 68):
                self.slot_w[i]["price"].setText(f"{price:,.2f}")
                tbl_set(self.slot_w[i]["tbl"], 0, 1, f"{price:,.2f}", "#00ff88")
                self.slot_data[i]["price"] = price
                self._check_triggers(i, price)
            elif tt == 8:
                tbl_set(self.slot_w[i]["tbl"], 1, 1, f"{int(price):,}")
            elif tt in (9, 75):
                prev = self.slot_data[i].get("prev_close")
                cur  = self.slot_data[i].get("price")
                tbl_set(self.slot_w[i]["tbl"], 5, 1, f"{price:,.2f}")
                self.slot_data[i]["prev_close"] = price
                # 등락률 표시
                if cur and price > 0:
                    chg = cur - price; pct = chg / price * 100
                    col = "#00e676" if chg >= 0 else "#ff5252"
                    sign = "+" if chg >= 0 else ""
                    self.slot_w[i]["price"].setStyleSheet(
                        f"color:{col};background:#07070f;"
                        "border-radius:6px;padding:6px;border:1px solid #1e2050;")
                    self.slot_w[i]["sym"].setText(
                        f"{self.slot_data[i].get('sym','―')}  "
                        f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)")

    def _on_tick_opt(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (12, 13): return
        for i, base in enumerate(self.slot_rids):
            if rid != base: continue
            tbl_set(self.slot_w[i]["tbl"], 2, 1, f"{delta:+.4f}", "#aaddff")
            tbl_set(self.slot_w[i]["tbl"], 3, 1, f"{gamma:.6f}", "#88ff44")
            tbl_set(self.slot_w[i]["tbl"], 4, 1, f"{theta:.4f}", "#ff8844")

    # ── 트리거 ────────────────────────────────────────────────────
    def _add_trigger(self):
        p = self.trg_price.text().strip()
        t = self.trg_time.text().strip()
        d = self.trg_desc.text().strip() or "―"
        r = self.tbl_trg.rowCount(); self.tbl_trg.insertRow(r)
        for c, v in enumerate([p, t, d]):
            item = QTableWidgetItem(v); item.setTextAlignment(Qt.AlignCenter)
            self.tbl_trg.setItem(r, c, item)
        st = QTableWidgetItem("대기중"); st.setTextAlignment(Qt.AlignCenter)
        st.setForeground(QBrush(QColor("#00ff88")))
        st.setFlags(st.flags() & ~Qt.ItemIsEditable)
        self.tbl_trg.setItem(r, 3, st)
        self.trg_log.append(f"[{ts()}] 트리거 등록: 가격≤{p}  시간≥{t}  ({d})")

    def _on_trg_dbl(self, row, col):
        if col == 3: return
        self.tbl_trg.editItem(self.tbl_trg.item(row, col))

    def _trg_keypress(self, event):
        if event.key() == Qt.Key_Delete: self._del_trigger()
        else: QTableWidget.keyPressEvent(self.tbl_trg, event)

    def _del_trigger(self):
        rows = sorted(set(i.row() for i in self.tbl_trg.selectedItems()), reverse=True)
        for r in rows: self.tbl_trg.removeRow(r)

    def _clr_triggers(self):
        ret = QMessageBox.question(self,"초기화","모든 트리거를 삭제합니까?",
            QMessageBox.Yes|QMessageBox.No)
        if ret == QMessageBox.Yes: self.tbl_trg.setRowCount(0)

    def _check_triggers(self, slot_idx, price):
        now_s = datetime.now().strftime("%H:%M:%S")
        for r in range(self.tbl_trg.rowCount()):
            st_item = self.tbl_trg.item(r, 3)
            if not st_item or st_item.text() == "발동!": continue
            p_item = self.tbl_trg.item(r, 0)
            t_item = self.tbl_trg.item(r, 1)
            d_item = self.tbl_trg.item(r, 2)
            price_ok = True; time_ok = True
            if p_item and p_item.text().strip():
                try:
                    if float(p_item.text()) < price: price_ok = False
                except: pass
            if t_item and t_item.text().strip():
                time_ok = now_s >= t_item.text().strip()
            if price_ok and time_ok:
                st_item.setText("발동!")
                st_item.setForeground(QBrush(QColor("#ffd700")))
                desc = d_item.text() if d_item else "―"
                msg  = f"★ 트리거 발동! 슬롯{slot_idx+1} {price:,.2f} ({desc})"
                self.trg_log.append(f"[{ts()}] {msg}")
                self.trigger_logs.append({"time": ts(), "msg": msg})
                self._play_alert_sound()   # 알람 사운드 재생

    # ─────────────────────────────────────────────────────────
    # 알람 사운드 관련 메서드
    # ─────────────────────────────────────────────────────────
    def _pick_alert_sound(self):
        """파일 다이얼로그로 .wav 선택."""
        from pathlib import Path as _Path
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택",
            str(_Path.home()), "WAV 파일 (*.wav);;모든 파일 (*)")
        if not path:
            return
        self._alert_sound_path = path
        fname = _Path(path).name
        self.lbl_snd_file.setText(fname)
        self.lbl_snd_file.setToolTip(path)
        # 기본값 저장 체크 시 JSON에 저장
        if self.chk_snd_default.isChecked():
            self._save_sound_setting(path)

    def _clear_alert_sound(self):
        self._alert_sound_path = ""
        self.lbl_snd_file.setText("기본 비프음")
        self.lbl_snd_file.setToolTip("")
        self._save_sound_setting("")

    def _play_alert_sound(self):
        """사운드 재생 — .wav 있으면 파일, 없으면 비프."""
        from pathlib import Path as _Path
        if self._alert_sound_path and _Path(self._alert_sound_path).exists():
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(self._alert_sound_path); return
            except ImportError:
                pass
            try:
                import winsound
                winsound.PlaySound(self._alert_sound_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC); return
            except Exception:
                pass
            try:
                import subprocess, sys
                if sys.platform == "darwin":
                    subprocess.Popen(["afplay", self._alert_sound_path])
                else:
                    subprocess.Popen(["aplay", self._alert_sound_path])
                return
            except Exception:
                pass
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass

    def _save_sound_setting(self, path: str):
        """사운드 경로를 설정 JSON에 저장."""
        try:
            cfg = load_json("multiprice_sound.json", {})
            cfg["alert_sound"] = path
            save_json("multiprice_sound.json", cfg)
        except Exception:
            pass

    def _restore_sound_setting(self):
        """앱 시작 시 저장된 사운드 경로 복원."""
        try:
            from pathlib import Path as _Path
            cfg = load_json("multiprice_sound.json", {})
            path = cfg.get("alert_sound", "")
            if path and _Path(path).exists():
                self._alert_sound_path = path
                self.lbl_snd_file.setText(_Path(path).name)
                self.lbl_snd_file.setToolTip(path)
        except Exception:
            pass

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,"저장","trigger_log.json","JSON (*.json)")
        if not path: return
        with open(path,"w",encoding="utf-8") as f:
            json.dump(self.trigger_logs, f, ensure_ascii=False, indent=2)
        self.lbl_file.setText(f"저장: {Path(path).name}")

    def _load_log(self):
        path, _ = QFileDialog.getOpenFileName(self,"불러오기","","JSON (*.json)")
        if not path: return
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        self.trigger_logs = data; self.trg_log.clear()
        for d in data: self.trg_log.append(f"[{d.get('time','')}] {d.get('msg','')}")
        self.lbl_file.setText(f"불러옴: {Path(path).name}")

    def _w_add(self):
        t, ok = QInputDialog.getText(self,"추가","심볼:")
        if ok and t.strip(): self.watch.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watch.currentRow()
        if r >= 0: self.watch.takeItem(r)

    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 호출."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        tbls = [s["tbl"] for s in self.slot_w] + [self.tbl_trg]
        for tbl in tbls:
            _apply_table_theme(tbl, dark)

    def _get_extra_settings(self) -> dict:
        """스플리터 비율 저장."""
        d = {}
        try:
            d["slots_hsplit"]    = list(self._slots_hsplit.sizes())
            d["bot_hsplit"]      = list(self._bot_hsplit.sizes())
            d["bot_left_vsplit"] = list(self._bot_left_vsplit.sizes())
            d["bot_right_vsplit"]= list(self._bot_right_vsplit.sizes())
            d["slot_vsplits"]    = [list(v.sizes()) for v in self._slot_splitters]
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        """스플리터 비율 복원."""
        def _restore():
            try:
                if s.get("slots_hsplit"):     self._slots_hsplit.setSizes(s["slots_hsplit"])
                if s.get("bot_hsplit"):        self._bot_hsplit.setSizes(s["bot_hsplit"])
                if s.get("bot_left_vsplit"):   self._bot_left_vsplit.setSizes(s["bot_left_vsplit"])
                if s.get("bot_right_vsplit"):  self._bot_right_vsplit.setSizes(s["bot_right_vsplit"])
                if s.get("slot_vsplits"):
                    for i, sz in enumerate(s["slot_vsplits"]):
                        if i < len(self._slot_splitters):
                            self._slot_splitters[i].setSizes(sz)
            except Exception:
                pass
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, _restore)


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