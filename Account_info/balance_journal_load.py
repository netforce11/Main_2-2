"""
balance_journal_load.py — 매매일지 DB 조회 로직  (BalanceGrid._jnl_load)
tab_balance.py 에서 mixin 방식으로 import.
"""

from __future__ import annotations
from PyQt5.QtGui     import QColor, QBrush, QFont
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import QTableWidgetItem

# 요약 행 배경색
_COLOR_SUMMARY_BOT = QColor("#e8f5e9")   # 연초록 — 데빗(매수)
_COLOR_SUMMARY_SLD = QColor("#fce4ec")   # 연분홍 — 크레딧(매도)
_COLOR_LEG         = QColor("#f8fafc")   # 레그 행 배경


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

    # ── 탭1: 체결내역 (그룹별 표시) ──────────────────────
    groups = get_grouped_executions_by_date(date_str)
    self.tbl_jnl_exec.setRowCount(0)

    for grp in groups:
        summary   = grp['summary']
        legs      = grp['legs']
        is_spread = grp['is_spread']

        # ── 요약 행 ──────────────────────────────────────
        r = self.tbl_jnl_exec.rowCount()
        self.tbl_jnl_exec.insertRow(r)

        action    = summary['action']
        act_col   = "#1565c0" if action == 'BOT' else "#b71c1c"
        bg_color  = _COLOR_SUMMARY_BOT if action == 'BOT' else _COLOR_SUMMARY_SLD
        label     = "▶ 스프레드" if is_spread else "▶ 단일"

        summary_vals = [
            summary['ts'][11:19],          # 시각
            action,                        # 방향
            summary['sym'],                # 종목
            "",                            # 만기 (합산행은 비움)
            "",                            # CP
            label,                         # 행사가 자리에 라벨
            f"{summary['qty']:.0f}",       # 수량
            f"${summary['net_price']:.2f}",# net price
            "", "", "", "", "",            # und 컨텍스트 비움
        ]
        for c, v in enumerate(summary_vals):
            item = QTableWidgetItem(v)
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(QBrush(bg_color))
            font = QFont(); font.setBold(True)
            item.setFont(font)
            if c == 1:
                item.setForeground(QBrush(QColor(act_col)))
            self.tbl_jnl_exec.setItem(r, c, item)

        # 스프레드가 아닌 단일 체결이면 레그 행 생략
        if not is_spread:
            continue

        # ── 레그 행 (들여쓰기 효과) ──────────────────────
        for leg in legs:
            r = self.tbl_jnl_exec.rowCount()
            self.tbl_jnl_exec.insertRow(r)
            leg_action = leg['action']
            leg_col    = "#2e7d32" if leg_action == 'BOT' else "#c62828"
            vals = [
                "  " + leg['ts'][11:19],
                leg_action,
                leg['sym'],
                leg.get('expiry', ''),
                leg.get('right', ''),
                str(int(leg['strike'])) if leg.get('strike') else "",
                f"{leg['qty']:.0f}",
                f"${leg['price']:.2f}",
                f"{leg['und_price']:.2f}"  if leg.get('und_price') else "―",
                f"{leg['und_5m']:.2f}"     if leg.get('und_5m')    else "―",
                f"{leg['und_10m']:.2f}"    if leg.get('und_10m')   else "―",
                f"{leg['chg_5m']:+.2f}"    if leg.get('chg_5m')  is not None else "―",
                f"{leg['chg_10m']:+.2f}"   if leg.get('chg_10m') is not None else "―",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QBrush(_COLOR_LEG))
                if c == 1:
                    item.setForeground(QBrush(QColor(leg_col)))
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
# ══════════════════════════════════════════════════════════════

def jnl_fetch_ib(self):
    """IB reqExecutions() 호출 → 체결 수신 → DB 저장 → 화면 갱신."""
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

    _orig_exec_details    = getattr(ib, 'execDetails',    lambda *a: None)
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
            'time':   execution.time,          # ★ IB 실제 체결 시각
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
    """수신된 체결 버퍼 → DB 저장 (중복 제외) → 화면 갱신."""
    if not getattr(self, '_ib_fetch_running', False):
        return
    self._ib_fetch_running = False

    if not buf:
        if lbl: lbl.setText("ℹ IB 체결내역 없음")
        return

    saved   = 0
    skipped = 0

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

            # ★ IB 실제 체결 시각 파싱 (형식: "20260504 21:59:57 ET" 또는 "20260504 21:59:57")
            raw_time = ex.get('time', '')
            try:
                # IB time 형식: "20260504  21:59:57 ET" (공백 2개인 경우도 있음)
                clean = raw_time.replace(' ET', '').replace('  ', ' ').strip()
                dt = datetime.strptime(clean, "%Y%m%d %H:%M:%S")
                ts_str   = dt.strftime("%Y-%m-%d %H:%M:%S")
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                now = datetime.now(_ET)
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
