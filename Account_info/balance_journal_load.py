"""
balance_journal_load.py — 매매일지 DB 조회 로직  v2.3
"""

from __future__ import annotations
from PyQt5.QtGui     import QColor, QBrush, QFont
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import QTableWidgetItem


def _item(text: str, bold: bool = False,
          fg: str = None, bg: QColor = None) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    if bold:
        f = QFont(); f.setBold(True); item.setFont(f)
    if fg:
        item.setForeground(QBrush(QColor(fg)))
    if bg:
        item.setBackground(QBrush(bg))
    return item


# ══════════════════════════════════════════════════════════════
# DB 조회 → 탭 갱신
# ══════════════════════════════════════════════════════════════

def jnl_load(self):
    """선택 날짜 매매일지 DB 조회 → 3탭 갱신."""
    date_str = self._jnl_date.date().toString("yyyy-MM-dd")
    try:
        from trade_log import (get_grouped_executions_by_date,
                               get_order_log_by_date,
                               get_open_trades,
                               get_daily_summary)
    except ImportError:
        self._jnl_summary_lbl.setText("⚠ trade_log 모듈 없음")
        return

    # ── 탭1: 체결내역 ────────────────────────────────────
    groups = get_grouped_executions_by_date(date_str)
    self.tbl_jnl_exec.setRowCount(0)

    total_pnl  = 0.0
    trade_cnt  = 0

    for grp in groups:
        legs      = grp['legs']
        is_spread = grp['is_spread']
        s         = grp['summary']

        action    = s['action']
        net_price = s['net_price']
        pnl       = s.get('pnl')       # None or float
        ts        = s['ts'][11:19] if s.get('ts') else ''

        # 만기 / 행사가 / 콜풋
        if is_spread:
            expiry  = legs[0].get('expiry', '')
            strikes = sorted(set(int(l['strike']) for l in legs if l.get('strike')))
            stk_str = "/".join(str(k) for k in strikes)
            rights  = set(l.get('right', '') for l in legs)
            cp_str  = ("콜 스프레드" if 'C' in rights else
                       "풋 스프레드" if 'P' in rights else "스프레드")
        else:
            leg     = legs[0]
            expiry  = leg.get('expiry', '')
            stk_str = str(int(leg['strike'])) if leg.get('strike') else ''
            r_val   = leg.get('right', '')
            cp_str  = "콜" if r_val == 'C' else "풋" if r_val == 'P' else r_val

        # 매수/매도 체결가
        buy_price  = f"${net_price:.2f}" if action == 'BOT' else ""
        sell_price = f"${net_price:.2f}" if action == 'SLD' else ""

        # 손익 표시
        if pnl is not None:
            sign     = "+" if pnl >= 0 else ""
            pnl_str  = f"{sign}${pnl:.0f}"
            pnl_col  = "#16a34a" if pnl >= 0 else "#dc2626"
            total_pnl += pnl
            trade_cnt += 1
        else:
            pnl_str = ""
            pnl_col = None

        # und 컨텍스트
        ref      = legs[0]
        idx_str  = f"{ref['und_price']:.2f}"  if ref.get('und_price') else "―"
        idx5_str = f"{ref['und_5m']:.2f}"     if ref.get('und_5m')    else "―"
        idx10_str= f"{ref['und_10m']:.2f}"    if ref.get('und_10m')   else "―"

        # 배경색
        bg = QColor("#e3f2fd") if action == 'BOT' else QColor("#fce4ec")

        # 행 삽입
        r = self.tbl_jnl_exec.rowCount()
        self.tbl_jnl_exec.insertRow(r)

        row_data = [
            ts, action, s['sym'], expiry, stk_str, cp_str,
            f"{int(s['qty'])}",
            buy_price, sell_price, pnl_str,
            idx_str, idx5_str, idx10_str,
        ]
        for c, v in enumerate(row_data):
            item = _item(v, bold=True, bg=bg)
            if c == 1:   # 방향
                item.setForeground(QBrush(QColor(
                    "#1565c0" if action == 'BOT' else "#b71c1c")))
            elif c == 7 and buy_price:   # 매수체결가
                item.setForeground(QBrush(QColor("#1565c0")))
            elif c == 8 and sell_price:  # 매도체결가
                item.setForeground(QBrush(QColor("#b71c1c")))
            elif c == 9 and pnl_col:     # 손익
                item.setForeground(QBrush(QColor(pnl_col)))
            self.tbl_jnl_exec.setItem(r, c, item)

    # ── 요약바 — executions 기반 ─────────────────────────
    if groups:
        sign = "+" if total_pnl >= 0 else ""
        col  = "#16a34a" if total_pnl >= 0 else "#dc2626"
        pnl_part = (f"  실현손익: {sign}${total_pnl:.0f}"
                    if trade_cnt > 0 else "  (미청산 포지션)")
        self._jnl_summary_lbl.setText(
            f"  {date_str}  |  {len(groups)}건{pnl_part}")
        self._jnl_summary_lbl.setStyleSheet(
            f"color:{col};font-size:11px;font-weight:600;"
            "background:#f8fafc;border-bottom:1px solid #f0f2f6;"
            "padding:6px 16px;")
    else:
        self._jnl_summary_lbl.setText(f"  {date_str} — 체결 없음")
        self._jnl_summary_lbl.setStyleSheet(
            "color:#94a3b8;font-size:11px;"
            "background:#f8fafc;border-bottom:1px solid #f0f2f6;"
            "padding:6px 16px;")

    # ── 탭2: 주문 로그 ───────────────────────────────────
    orders = get_order_log_by_date(date_str)
    self.tbl_jnl_orders.setRowCount(0)
    _status_col = {
        "Filled": "#00ff88", "Cancelled": "#ff6666",
        "Submitted": "#ffd700", "PreSubmitted": "#aaa",
    }
    for o in orders:
        r = self.tbl_jnl_orders.rowCount()
        self.tbl_jnl_orders.insertRow(r)
        scol = _status_col.get(o["status"], "#ccc")
        vals = [
            o["ts"][11:], o["status"], str(o["oid"]),
            o.get("sym",""), o.get("right",""),
            str(int(o["strike"])) if o.get("strike") else "",
            o.get("action",""),
            str(int(o["qty"])) if o.get("qty") else "",
            f"{o['price']:.2f}" if o.get("price") else "",
            f"{o['und_price']:.2f}" if o.get("und_price") else "―",
        ]
        for c, v in enumerate(vals):
            from PyQt5.QtWidgets import QTableWidgetItem as _TWI
            item = _TWI(v)
            item.setTextAlignment(Qt.AlignCenter)
            if c == 1:
                item.setForeground(QBrush(QColor(scol)))
            self.tbl_jnl_orders.setItem(r, c, item)

    # ── 탭3: 미청산 ──────────────────────────────────────
    opens = get_open_trades()
    self.tbl_jnl_open.setRowCount(0)
    for o in opens:
        r = self.tbl_jnl_open.rowCount()
        self.tbl_jnl_open.insertRow(r)
        for c, v in enumerate([
            o["open_date"], o["sym"], o.get("right",""),
            str(int(o["strike"])) if o.get("strike") else "",
            str(int(o["qty"])), f"{o['entry_price']:.2f}", "―"
        ]):
            from PyQt5.QtWidgets import QTableWidgetItem as _TWI
            item = _TWI(v)
            item.setTextAlignment(Qt.AlignCenter)
            self.tbl_jnl_open.setItem(r, c, item)


# ══════════════════════════════════════════════════════════════
# IB reqExecutions → DB 저장 후 화면 갱신
# ══════════════════════════════════════════════════════════════

def jnl_fetch_ib(self):
    lbl = getattr(self, '_ib_fetch_lbl', None)

    if getattr(self, '_ib_fetch_running', False):
        if lbl: lbl.setText("⏳ 이미 요청 중…")
        return
    self._ib_fetch_running = True

    ib = None
    try:
        mw = getattr(self, 'mw', None)
        ib = getattr(mw, 'ib', None)
    except Exception:
        pass

    if ib is None:
        if lbl: lbl.setText("⚠ IB 연결 없음")
        self._ib_fetch_running = False
        return

    if lbl: lbl.setText("⏳ IB 체결내역 요청 중…")

    buf = []
    _orig_exec_details     = getattr(ib, 'execDetails',    lambda *a: None)
    _orig_exec_details_end = getattr(ib, 'execDetailsEnd', lambda *a: None)

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
        if lbl: lbl.setText(f"⏳ 수신 중… {len(buf)}건")

    def _tmp_exec_details_end(reqId):
        try: _orig_exec_details_end(reqId)
        except Exception: pass
        ib.execDetails    = _orig_exec_details
        ib.execDetailsEnd = _orig_exec_details_end
        _save_buf_to_db(self, buf, lbl)

    ib.execDetails    = _tmp_exec_details
    ib.execDetailsEnd = _tmp_exec_details_end

    _REQ_ID = 9998
    try:
        from ibapi.execution import ExecutionFilter
        ib.reqExecutions(_REQ_ID, ExecutionFilter())
    except Exception as e:
        ib.execDetails    = _orig_exec_details
        ib.execDetailsEnd = _orig_exec_details_end
        if lbl: lbl.setText(f"⚠ reqExecutions 오류: {e}")
        self._ib_fetch_running = False
        return

    def _force_end():
        if not getattr(self, '_ib_fetch_running', False):
            return
        ib.execDetails    = _orig_exec_details
        ib.execDetailsEnd = _orig_exec_details_end
        _save_buf_to_db(self, buf, lbl)

    QTimer.singleShot(6000, _force_end)


def _save_buf_to_db(self, buf: list, lbl):
    if not getattr(self, '_ib_fetch_running', False):
        return
    self._ib_fetch_running = False

    if not buf:
        if lbl: lbl.setText("ℹ IB 체결내역 없음")
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
            key = (ex['oid'], ex['sym'], ex['side'], round(float(ex['price']), 4))
            if key in existing:
                skipped += 1
                continue

            raw_time = ex.get('time', '')
            try:
                clean    = raw_time.replace(' ET','').replace('  ',' ').strip()
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
            """, (ts_str, date_str, ex['oid'], 'ib_fetch',
                  ex['sym'], ex.get('expiry',''), ex.get('right',''),
                  int(ex.get('strike', 0) or 0),
                  ex['side'], ex['qty'], ex['price'], commission))
            conn.commit()
            conn.close()

            existing.add(key)
            saved += 1

    except Exception as e:
        if lbl: lbl.setText(f"⚠ DB 저장 오류: {e}")
        return

    parts = []
    if saved:   parts.append(f"✅ {saved}건 저장")
    if skipped: parts.append(f"{skipped}건 중복 스킵")
    if lbl: lbl.setText("  ".join(parts) if parts else "ℹ 변경 없음")

    jnl_load(self)
