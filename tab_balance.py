"""
tab_balance.py — 잔고/PnL 탭  v6.1  (Tab 2: BalanceGrid)
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

PNL_HIST_CSV = "pnl_history.csv"


class BalanceGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self._acct_rows   = {}
        self._pnl_history = []
        self._session     = {"trades": [], "start_time": ts_full()}
        self._pnl_acct_id = ""          # reqPnL 구독에 사용할 계좌 ID
        self._pnl_req_id  = 9900        # reqPnL 전용 reqId
        self._rt_pnl_active = False     # 실시간 PnL 구독 중 여부
        self._build()
        self._connect_signals()
        self._load_history()

    # ── 공통 스타일 상수 (Clean Card Light) ──────────────────────
    def _build(self):
        """패널별 빌더 호출만. 실제 UI 코드는 balance_panel_*.py 참조."""
        from Account_info.balance_style         import CS
        from Account_info.balance_panel_hero    import build_hero
        from Account_info.balance_panel_top     import (build_acct_panel,
                                           build_kpi_panel,
                                           build_position_panel)
        from Account_info.balance_panel_mid     import (build_chart_panel,
                                           build_session_panel,
                                           build_order_panel)
        from Account_info.balance_panel_journal import build_journal

        self.setStyleSheet(CS["root"])
        self.add(build_hero(self),           0, 0, 1, 12)
        self.add(build_acct_panel(self),     1, 0, 1,  4)
        self.add(build_kpi_panel(self),      1, 4, 1,  4)
        self.add(build_position_panel(self), 1, 8, 1,  4)
        self.add(build_chart_panel(self),    2, 0, 1,  4)
        self.add(build_session_panel(self),  2, 4, 1,  4)
        self.add(build_order_panel(self),    2, 8, 1,  4)
        self.add(build_journal(self),        3, 0, 1, 12)

    def _connect_signals(self):
        bridge.acct_value.connect(self._on_acct)
        bridge.position_sig.connect(self._on_pos)
        bridge.open_order_sig.connect(self._on_order)
        # ── 실시간 PnL 브릿지 연결 ─────────────────────────────
        if hasattr(bridge, 'pnl_sig'):
            bridge.pnl_sig.connect(self._on_rt_pnl)
        # ── 주문/체결 DB 저장 — 콜-풋/콤보 통합 ────────────────
        if hasattr(bridge, 'order_status_sig'):
            bridge.order_status_sig.connect(self._on_order_status_log)
        if hasattr(bridge, 'exec_sig'):
            try: bridge.exec_sig.disconnect(self._on_exec_log)
            except Exception: pass
            bridge.exec_sig.connect(self._on_exec_log)

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

    # ── 탭 포커스 자동 로딩 ─────────────────────────────────────
    def on_tab_activate(self):
        """
        main.py _on_tab_changed() 에서 Tab2 포커스 시 자동 호출.
        연결 상태면 즉시 새로고침 + 실시간 PnL 구독 시작.
        """
        if self.mw.connected:
            self._refresh()
            self._start_rt_pnl()
        self._jnl_load()   # 오늘 날짜 매매일지 자동 조회

    def on_tab_deactivate(self):
        """Tab2 에서 벗어날 때 호출 — 실시간 PnL 구독 해지."""
        self._stop_rt_pnl()

    # ── 실시간 PnL 구독 (reqPnL) ────────────────────────────────
    def _start_rt_pnl(self):
        """
        IBKR reqPnL() 로 실시간 미실현/실현 PnL 구독 시작.
        계좌 ID는 reqAccountSummary 응답에서 자동 추출.
        """
        if self._rt_pnl_active: return
        if not self.mw.connected or not self.mw.ib: return
        acct = self._pnl_acct_id
        if not acct:
            # 계좌 ID 아직 미수신 → 2초 후 재시도
            QTimer.singleShot(2000, self._start_rt_pnl)
            return
        try:
            self.mw.ib.reqPnL(self._pnl_req_id, acct, "")
            self._rt_pnl_active = True
            # IBapi.pnl 콜백을 직접 패치 (bridge.pnl_sig 없는 환경 대응)
            self._hook_pnl_callback()
        except Exception as e:
            print(f"[BalanceGrid] reqPnL 오류: {e}")

    def _stop_rt_pnl(self):
        """탭 비활성 시 실시간 PnL 구독 해지."""
        if not self._rt_pnl_active: return
        try:
            if self.mw.ib:
                self.mw.ib.cancelPnL(self._pnl_req_id)
        except Exception:
            pass
        self._rt_pnl_active = False

    def _hook_pnl_callback(self):
        """
        IBapi.pnl 콜백을 직접 패치해 실시간 PnL 수신.
        bridge.pnl_sig 가 없는 환경에서도 동작.
        """
        if not self.mw.ib: return
        ib = self.mw.ib
        _orig_pnl = getattr(ib, 'pnl', lambda *a: None)

        def _on_pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL):
            try: _orig_pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)
            except: pass
            if reqId != self._pnl_req_id: return
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._apply_rt_pnl(
                dailyPnL, unrealizedPnL, realizedPnL))

        ib.pnl = _on_pnl

    def _apply_rt_pnl(self, daily_pnl, unrealized, realized):
        """실시간 PnL 수신 → UI 즉시 갱신."""
        try:
            # 미실현 PnL (대형 라벨)
            sign = "+" if unrealized >= 0 else ""
            col  = "#00ff88" if unrealized >= 0 else "#ff4444"
            self.lbl_pnl.setText(f"{sign}${unrealized:,.2f}")
            self.lbl_pnl.setStyleSheet(
                f"color:{col};border:none;font-size:22px;font-weight:bold;")

            # 실현 PnL (주요 지표)
            rcol = "#00ff88" if realized >= 0 else "#ff4444"
            self.lbl_rpnl._val.setText(f"${realized:,.2f}")
            self.lbl_rpnl._val.setStyleSheet(f"color:{rcol};border:none;")

            # 마지막 업데이트 시각
            self.lbl_time.setText(f"실시간: {ts()}")
            self._record_pnl(0.0, unrealized)
        except Exception as e:
            print(f"[BalanceGrid] _apply_rt_pnl 오류: {e}")

    def _on_rt_pnl(self, req_id, daily_pnl, unrealized, realized):
        """bridge.pnl_sig 연결용 슬롯 (core.py 에 pnl_sig 있을 때)."""
        if req_id != self._pnl_req_id: return
        self._apply_rt_pnl(daily_pnl, unrealized, realized)

    def _on_acct(self, tag, val, cur, acct):
        # ── 계좌 ID 자동 추출 (reqPnL 구독용) ──────────────────
        if acct and not self._pnl_acct_id:
            self._pnl_acct_id = acct
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
                self.lbl_pnl.setText(f"{sign}${v:,.2f}")
                self.lbl_pnl.setStyleSheet(
                    f"color:{col};border:none;font-size:22px;font-weight:bold;")
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

    # ══════════════════════════════════════════════════════════════
    # 매매일지 패널
    # ══════════════════════════════════════════════════════════════
    def _jnl_load(self):
        """매매일지 DB 조회 → 3탭 갱신. 로직은 balance_journal_load.py 참조."""
        from Account_info.balance_journal_load import jnl_load
        jnl_load(self)
    def _jnl_fetch_ib(self):
        """IB reqExecutions → DB 저장 후 화면 갱신."""
        from Account_info.balance_journal_load import jnl_fetch_ib
        jnl_fetch_ib(self)

    def _on_order_status_log(self, oid: int, status: str,
                             filled: float, remaining: float) -> None:
        """bridge.order_status_sig → 모든 주문 상태변경 DB 저장."""
        try:
            from trade_log import log_order, get_und_context
            ctx = get_und_context()
            log_order(
                oid=oid,
                source='bridge',
                status=status,
                qty=filled + remaining,
                price=0.0,
                und_price=ctx.get('und_price'),
            )
        except Exception as e:
            print(f"[trade_log] order_log 저장 오류: {e}")

    def _on_exec_log(self, oid: int, sym: str,
                     side: str, qty: float, price: float) -> None:
        """bridge.exec_sig → 모든 체결 DB 저장 + BUY/SELL 매칭."""
        try:
            from trade_log import log_exec, run_match, get_und_context
            from trade_log.db import get_conn
            # 중복 체크
            conn = get_conn()
            exists = conn.execute(
                "SELECT 1 FROM executions WHERE oid=? AND sym=? AND action=? AND price=?",
                (oid, sym, side, price)).fetchone()
            conn.close()
            if exists:
                return  # 이미 있으면 스킵
            log_exec(
                oid=oid, source='bridge', sym=sym,
                action=side, qty=qty, price=price,
                und_ctx=get_und_context(),
            )
            run_match('bridge', sym, '', '', 0)
        except Exception as e:
          print(f"[trade_log] executions 저장 오류: {e}")
    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 호출 — 테이블 색상 명시 재적용."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        for tbl in (self.tbl_acct, self.tbl_pos, self.tbl_ord, self.tbl_trades,
                    self.tbl_jnl_exec, self.tbl_jnl_orders, self.tbl_jnl_open):
            _apply_table_theme(tbl, dark)


# ══════════════════════════════════════════════════════════════
# Tab 5: 복수 현재가
# 트리거: 등록 테이블 (수정 가능) + 등록 상태 표시
# ══════════════════════════════════════════════════════════════
