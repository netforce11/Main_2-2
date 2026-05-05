"""
balance_journal_load.py — 매매일지 DB 조회 로직  (BalanceGrid._jnl_load)
tab_balance.py 에서 mixin 방식으로 import.
"""

from __future__ import annotations
from PyQt5.QtGui     import QColor, QBrush
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import QTableWidgetItem


# ══════════════════════════════════════════════════════════════
# DB 조회 → 탭 갱신
# ══════════════════════════════════════════════════════════════

def jnl_load(self):
    """선택 날짜 매매일지 DB 조회 → 3탭 갱신."""
    date_str = self._jnl_date.date().toString("yyyy-MM-dd")
    try:
        from trade_log import (get_executions_by_date,
                               get_order_log_by_date,
                               get_open_trades,
                               get_daily_summary)
    except ImportError:
        self._jnl_summary_lbl.setText("⚠ trade_log 모듈 없음")
        return

    # ── 탭1: 체결내역 ────────────────────────────────────
    execs = get_executions_by_date(date_str)
    self.tbl_jnl_exec.setRowCount(0)
    for e in execs:
        r = self.tbl_jnl_exec.rowCount()
        self.tbl_jnl_exec.insertRow(r)
        col = "#00ff88" if e["action"] == "BUY" else "#ff6666"
        vals = [
            e["ts"][11:],
            e["action"],
            e["sym"],
            e.get("expiry",""),
            e.get("right",""),
            str(int(e["strike"])) if e.get("strike") else "",
            str(int(e["qty"])),
            f"{e['price']:.2f}",
            f"{e['und_price']:.2f}"  if e.get("und_price") else "―",
            f"{e['und_5m']:.2f}"     if e.get("und_5m")    else "―",
            f"{e['und_10m']:.2f}"    if e.get("und_10m")   else "―",
            f"{e['chg_5m']:+.2f}"    if e.get("chg_5m")  is not None else "―",
            f"{e['chg_10m']:+.2f}"   if e.get("chg_10m") is not None else "―",
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignCenter)
            if c == 1:
                item.setForeground(QBrush(QColor(col)))
            self.tbl_jnl_exec.setItem(r, c, item)

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
            o.get("action",""), str(int(o["qty"])) if o.get("qty") else "",
            f"{o['price']:.2f}" if o.get("price") else "",
            f"{o['und_price']:.2f}" if o.get("und_price") else "―",
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
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
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignCenter)
            self.tbl_jnl_open.setItem(r, c, item)

    # ── 일일 요약 ─────────────────────────────────────────
    s = get_daily_summary(date_str)
    if s["trades"]:
        col = "#16a34a" if s["net_pnl"] >= 0 else "#dc2626"
        sign = "+" if s["net_pnl"] >= 0 else ""
        self._jnl_summary_lbl.setText(
            f"  {date_str}  |  {s['trades']}건  "
            f"실현손익: {sign}${s['realized_pnl']:,.2f}  "
            f"수수료: ${s['commission']:.2f}  "
            f"순손익: {sign}${s['net_pnl']:,.2f}")
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


# ══════════════════════════════════════════════════════════════
# ★ IB reqExecutions → DB 저장 후 화면 갱신
# exec_sig 재연결 없이 ib 객체 콜백을 직접 임시 패치하는 방식
# ══════════════════════════════════════════════════════════════

def jnl_fetch_ib(self):
    """
    IB reqExecutions() 호출 → 체결 수신 → DB 저장 → 화면 갱신.
    exec_sig 를 재연결하지 않고 ib 객체 콜백을 직접 임시 패치.
    """
    lbl = getattr(self, '_ib_fetch_lbl', None)

    # 이미 진행 중이면 무시 (중복 클릭 방지)
    if getattr(self, '_ib_fetch_running', False):
        if lbl: lbl.setText("⏳ 이미 요청 중…")
        return
    self._ib_fetch_running = True

    # ── IB 객체 확인 ─────────────────────────────────────
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

    # ── 수신 버퍼 초기화 ─────────────────────────────────
    buf = []

    # ── IB 콜백 임시 패치 ────────────────────────────────
    _orig_exec_details    = getattr(ib, 'execDetails',    lambda *a: None)
    _orig_exec_details_end = getattr(ib, 'execDetailsEnd', lambda *a: None)

    def _tmp_exec_details(reqId, contract, execution):
        try: _orig_exec_details(reqId, contract, execution)
        except Exception: pass
        buf.append({
            'oid':    execution.orderId,
            'sym':    contract.symbol,
            'side':   execution.side,   # 'BOT' or 'SLD'
            'qty':    execution.shares,
            'price':  execution.price,
            'expiry': contract.lastTradeDateOrContractMonth,
            'right':  contract.right,
            'strike': contract.strike,
        })
        if lbl: lbl.setText(f"⏳ 수신 중… {len(buf)}건")

    def _tmp_exec_details_end(reqId):
        try: _orig_exec_details_end(reqId)
        except Exception: pass
        # 콜백 원복 후 저장
        ib.execDetails    = _orig_exec_details
        ib.execDetailsEnd = _orig_exec_details_end
        _save_buf_to_db(self, buf, lbl)

    ib.execDetails    = _tmp_exec_details
    ib.execDetailsEnd = _tmp_exec_details_end

    # ── reqExecutions 호출 ───────────────────────────────
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

    # 안전망: 6초 후 강제 완료 (execDetailsEnd 안 오는 경우 대비)
    def _force_end():
        if not getattr(self, '_ib_fetch_running', False):
            return  # 이미 정상 완료됨
        ib.execDetails    = _orig_exec_details
        ib.execDetailsEnd = _orig_exec_details_end
        _save_buf_to_db(self, buf, lbl)

    QTimer.singleShot(6000, _force_end)


def _save_buf_to_db(self, buf: list, lbl):
    """수신된 체결 버퍼 → DB 저장 (중복 제외) → 화면 갱신."""
    if not getattr(self, '_ib_fetch_running', False):
        return   # 이미 처리됨 (force_end 중복 방지)
    self._ib_fetch_running = False

    if not buf:
        if lbl: lbl.setText("ℹ IB 체결내역 없음")
        return

    saved   = 0
    skipped = 0

    try:
        from trade_log import log_exec
        from trade_log.db import get_conn

        conn = get_conn()
        # oid + sym + action + price 조합으로 중복 체크
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
            commission = round(float(ex['qty']) * 1.0, 2)
            log_exec(
                oid=ex['oid'],
                source='ib_fetch',
                sym=ex['sym'],
                action=ex['side'],
                qty=ex['qty'],
                price=ex['price'],
                expiry=ex.get('expiry', ''),
                right=ex.get('right', ''),
                strike=float(ex.get('strike', 0)),
                commission=commission,
            )
            existing.add(key)
            saved += 1

    except Exception as e:
        if lbl: lbl.setText(f"⚠ DB 저장 오류: {e}")
        return

    # ── 결과 표시 + 화면 갱신 ────────────────────────────
    parts = []
    if saved:   parts.append(f"✅ {saved}건 저장")
    if skipped: parts.append(f"{skipped}건 중복 스킵")
    if lbl: lbl.setText("  ".join(parts) if parts else "ℹ 변경 없음")

    from PyQt5.QtCore import QDate
    self._jnl_date.setDate(QDate.currentDate())
    jnl_load(self)