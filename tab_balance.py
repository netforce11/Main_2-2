"""
tab_balance.py — 잔고/PnL 탭  v6.2  (Tab 2: BalanceGrid)
변경:
  - IB 연결 시 자동 reqExecutions() → DB 저장
  - 30분마다 자동 반복 저장 (장 중 체결 누락 방지)
  - on_tab_activate() 에서 오늘 날짜 자동 조회
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

# 자동 저장 주기 (밀리초)
_AUTO_FETCH_INTERVAL_MS = 30 * 60 * 1000   # 30분


class BalanceGrid(GridTab):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self._acct_rows   = {}
        self._pnl_history = []
        self._session     = {"trades": [], "start_time": ts_full()}
        self._pnl_acct_id = ""
        self._pnl_req_id  = 9900
        self._rt_pnl_active = False

        # ── 자동 체결 저장 타이머 ──────────────────────────
        self._auto_fetch_timer = QTimer(self)
        self._auto_fetch_timer.timeout.connect(self._auto_fetch_executions)

        self._build()
        self._connect_signals()
        self._load_history()

    # ── UI 빌드 ─────────────────────────────────────────────────
    def _build(self):
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
        if hasattr(bridge, 'pnl_sig'):
            bridge.pnl_sig.connect(self._on_rt_pnl)
        if hasattr(bridge, 'order_status_sig'):
            bridge.order_status_sig.connect(self._on_order_status_log)
        if hasattr(bridge, 'exec_sig'):
            bridge.exec_sig.connect(self._on_exec_log)
        # IB 연결 시 자동 체결 저장 시작
        if hasattr(bridge, 'connected'):
            bridge.connected.connect(self._on_ib_connected)

    # ── IB 연결 시 자동 실행 ────────────────────────────────────
    def _on_ib_connected(self):
        """IB 연결 완료 → 즉시 체결 저장 + 30분 타이머 시작."""
        # 약간 딜레이 후 실행 (연결 안정화 대기)
        QTimer.singleShot(3000, self._auto_fetch_executions)
        # 30분 반복 타이머 시작
        self._auto_fetch_timer.start(_AUTO_FETCH_INTERVAL_MS)
        print("[BalanceGrid] 자동 체결 저장 타이머 시작 (30분 간격)")

    def _auto_fetch_executions(self):
        """
        자동 reqExecutions() → DB 저장.
        버튼 없이 백그라운드에서 실행. 상태 라벨에 표시.
        """
        ib = getattr(self.mw, 'ib', None)
        if not ib or not getattr(self.mw, 'connected', False):
            return

        lbl = getattr(self, '_ib_fetch_lbl', None)
        if lbl: lbl.setText("⏳ 자동 저장 중…")

        buf = []
        _orig_exec_details     = getattr(ib, 'execDetails',    lambda *a: None)
        _orig_exec_details_end = getattr(ib, 'execDetailsEnd', lambda *a: None)
        _running = [True]   # 중복 완료 방지용 플래그

        def _tmp_exec_details(reqId, contract, execution):
            try: _orig_exec_details(reqId, contract, execution)
            except Exception: pass
            buf.append({
                'oid':    execution.orderId,
                'sym':    contract.symbol,
                'side':   execution.side,
                'qty':    execution.shares,
                'price':  execution.price,
                'time':   execution.time,
                'expiry': contract.lastTradeDateOrContractMonth,
                'right':  contract.right,
                'strike': contract.strike,
            })

        def _tmp_exec_details_end(reqId):
            try: _orig_exec_details_end(reqId)
            except Exception: pass
            ib.execDetails    = _orig_exec_details
            ib.execDetailsEnd = _orig_exec_details_end
            if _running[0]:
                _running[0] = False
                self._save_auto_executions(buf, lbl)

        ib.execDetails    = _tmp_exec_details
        ib.execDetailsEnd = _tmp_exec_details_end

        try:
            from ibapi.execution import ExecutionFilter
            ib.reqExecutions(9997, ExecutionFilter())
        except Exception as e:
            ib.execDetails    = _orig_exec_details
            ib.execDetailsEnd = _orig_exec_details_end
            if lbl: lbl.setText(f"⚠ 자동저장 오류: {e}")
            return

        # 6초 안전망
        def _force():
            if not _running[0]: return
            _running[0] = False
            ib.execDetails    = _orig_exec_details
            ib.execDetailsEnd = _orig_exec_details_end
            self._save_auto_executions(buf, lbl)

        QTimer.singleShot(6000, _force)

    def _save_auto_executions(self, buf: list, lbl):
        """백그라운드 저장 완료 처리."""
        if not buf:
            if lbl: lbl.setText("")
            return

        saved = skipped = 0
        try:
            from trade_log.db import get_conn
            from datetime import datetime, timezone, timedelta
            _ET = timezone(timedelta(hours=-5))

            conn = get_conn()
            existing = set()
            for r in conn.execute(
                    "SELECT oid, sym, action, price FROM executions").fetchall():
                existing.add((r[0], r[1], r[2], round(float(r[3]), 4)))
            conn.close()

            for ex in buf:
                key = (ex['oid'], ex['sym'], ex['side'],
                       round(float(ex['price']), 4))
                if key in existing:
                    skipped += 1
                    continue

                raw = ex.get('time', '')
                try:
                    clean    = raw.replace(' ET','').replace('  ',' ').strip()
                    dt       = datetime.strptime(clean, "%Y%m%d %H:%M:%S")
                    ts_str   = dt.strftime("%Y-%m-%d %H:%M:%S")
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    now      = datetime.now(_ET)
                    ts_str   = now.strftime("%Y-%m-%d %H:%M:%S")
                    date_str = now.strftime("%Y-%m-%d")

                commission = round(float(ex['qty']) * 1.0, 2)
                conn = get_conn()
                conn.execute("""
                    INSERT INTO executions
                      (ts, date, oid, source, sym, expiry, right, strike,
                       action, qty, price, commission)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (ts_str, date_str, ex['oid'], 'auto_fetch',
                      ex['sym'], ex.get('expiry',''), ex.get('right',''),
                      int(ex.get('strike', 0) or 0),
                      ex['side'], ex['qty'], ex['price'], commission))
                conn.commit()
                conn.close()
                existing.add(key)
                saved += 1

        except Exception as e:
            if lbl: lbl.setText(f"⚠ 자동저장 DB오류: {e}")
            return

        if saved:
            if lbl: lbl.setText(f"✅ 자동저장 {saved}건")
            print(f"[BalanceGrid] 자동저장 완료: {saved}건 저장 / {skipped}건 스킵")
            # 현재 탭이 열려 있으면 화면 갱신
            self._jnl_load()
        else:
            if lbl: lbl.setText("")

    # ── 탭 포커스 ───────────────────────────────────────────────
    def on_tab_activate(self):
        """Tab2 포커스 시 자동 호출."""
        if self.mw.connected:
            self._refresh()
            self._start_rt_pnl()
        # ★ 오늘 날짜로 자동 조회
        from PyQt5.QtCore import QDate
        self._jnl_date.setDate(QDate.currentDate())
        self._jnl_load()

    def on_tab_deactivate(self):
        self._stop_rt_pnl()

    # ── 새로고침 ─────────────────────────────────────────────────
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

    # ── 실시간 PnL ───────────────────────────────────────────────
    def _start_rt_pnl(self):
        if self._rt_pnl_active: return
        if not self.mw.connected or not self.mw.ib: return
        acct = self._pnl_acct_id
        if not acct:
            QTimer.singleShot(2000, self._start_rt_pnl)
            return
        try:
            self.mw.ib.reqPnL(self._pnl_req_id, acct, "")
            self._rt_pnl_active = True
            self._hook_pnl_callback()
        except Exception as e:
            print(f"[BalanceGrid] reqPnL 오류: {e}")

    def _stop_rt_pnl(self):
        if not self._rt_pnl_active: return
        try:
            if self.mw.ib:
                self.mw.ib.cancelPnL(self._pnl_req_id)
        except Exception:
            pass
        self._rt_pnl_active = False

    def _hook_pnl_callback(self):
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
        try:
            sign = "+" if unrealized >= 0 else ""
            col  = "#00ff88" if unrealized >= 0 else "#ff4444"
            self.lbl_pnl.setText(f"{sign}${unrealized:,.2f}")
            self.lbl_pnl.setStyleSheet(
                f"color:{col};border:none;font-size:22px;font-weight:bold;")
            rcol = "#00ff88" if realized >= 0 else "#ff4444"
            self.lbl_rpnl._val.setText(f"${realized:,.2f}")
            self.lbl_rpnl._val.setStyleSheet(f"color:{rcol};border:none;")
            self.lbl_time.setText(f"실시간: {ts()}")
            self._record_pnl(0.0, unrealized)
        except Exception as e:
            print(f"[BalanceGrid] _apply_rt_pnl 오류: {e}")

    def _on_rt_pnl(self, req_id, daily_pnl, unrealized, realized):
        if req_id != self._pnl_req_id: return
        self._apply_rt_pnl(daily_pnl, unrealized, realized)

    # ── 계좌/포지션/주문 ─────────────────────────────────────────
    def _on_acct(self, tag, val, cur, acct):
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
        for c,v in enumerate([str(oid),sym,right,action,str(int(qty)),
                               f"{price:.2f}",status]):
            tbl_set(self.tbl_ord,r,c,v)
        col = "#33aaff" if action=="BUY" else "#ff8844"
        self.tbl_ord.item(r,3).setForeground(QBrush(QColor(col)))

    # ── 차트 / 세션 ─────────────────────────────────────────────
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
            for lb in (self.lbl_winrate,self.lbl_avghold,
                       self.lbl_tot_pnl,self.lbl_tot_cnt):
                lb.setText("―")
            return
        wins=sum(1 for t in trades if t["pnl"]>=0)
        avg_hold=sum(t["hold"] for t in trades)/cnt
        tot_pnl=sum(t["pnl"] for t in trades)
        wr_col="#00ff88" if wins/cnt>=0.5 else "#ff4444"
        pnl_col="#00ff88" if tot_pnl>=0 else "#ff4444"
        self.lbl_winrate.setText(f"{wins/cnt*100:.1f}%")
        self.lbl_winrate.setStyleSheet(f"color:{wr_col};border:none;")
        self.lbl_avghold.setText(f"{avg_hold:.1f}분")
        self.lbl_tot_pnl.setText(f"${tot_pnl:,.2f}")
        self.lbl_tot_pnl.setStyleSheet(f"color:{pnl_col};border:none;")
        self.lbl_tot_cnt.setText(f"{cnt}건")

    # ══════════════════════════════════════════════════════════════
    # 매매일지 패널
    # ══════════════════════════════════════════════════════════════
    def _jnl_load(self):
        from Account_info.balance_journal_load import jnl_load
        jnl_load(self)

    def _jnl_fetch_ib(self):
        from Account_info.balance_journal_load import jnl_fetch_ib
        jnl_fetch_ib(self)

    # ── DB 저장 핸들러 ───────────────────────────────────────────
    def _on_order_status_log(self, oid: int, status: str,
                             filled: float, remaining: float) -> None:
        try:
            from trade_log import log_order, get_und_context
            ctx = get_und_context()
            log_order(
                oid=oid, source='bridge', status=status,
                qty=filled + remaining, price=0.0,
                und_price=ctx.get('und_price'),
            )
        except Exception as e:
            print(f"[trade_log] order_log 저장 오류: {e}")

    def _on_exec_log(self, oid: int, sym: str,
                     side: str, qty: float, price: float) -> None:
        try:
            from trade_log import log_exec, run_match, get_und_context
            from trade_log.db import get_conn
            # 중복 체크
            conn = get_conn()
            exists = conn.execute(
                "SELECT 1 FROM executions "
                "WHERE oid=? AND sym=? AND action=? AND price=?",
                (oid, sym, side, price)).fetchone()
            conn.close()
            if exists:
                return
            log_exec(
                oid=oid, source='bridge', sym=sym,
                action=side, qty=qty, price=price,
                und_ctx=get_und_context(),
            )
            run_match('bridge', sym, '', '', 0)
        except Exception as e:
            print(f"[trade_log] executions 저장 오류: {e}")

    def _apply_theme(self):
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        for tbl in (self.tbl_acct, self.tbl_pos, self.tbl_ord, self.tbl_trades,
                    self.tbl_jnl_exec, self.tbl_jnl_orders, self.tbl_jnl_open):
            _apply_table_theme(tbl, dark)
