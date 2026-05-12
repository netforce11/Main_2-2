"""
balance_journal.py — 매매일지 DB 조회 로직
════════════════════════════════════════════════════════
포함 내용:
  - BalanceJournalMixin
      _jnl_load()   선택 날짜 매매일지 DB 조회 → 3탭 갱신
                    (체결내역 / 주문로그 / 미청산 + 일일 요약)
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor, QBrush


class BalanceJournalMixin:
    """매매일지 DB 조회 로직. BalanceGrid에 mixin된다."""

    def _jnl_load(self):
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

        # ── 탭1: 체결내역 ────────────────────────────────────────
        execs = get_executions_by_date(date_str)
        self.tbl_jnl_exec.setRowCount(0)
        for e in execs:
            r   = self.tbl_jnl_exec.rowCount()
            col = "#00ff88" if e["action"] == "BUY" else "#ff6666"
            self.tbl_jnl_exec.insertRow(r)
            vals = [
                e["ts"][11:],
                e["action"],
                e["sym"],
                e.get("expiry", ""),
                e.get("right", ""),
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

        # ── 탭2: 주문 로그 ───────────────────────────────────────
        orders = get_order_log_by_date(date_str)
        self.tbl_jnl_orders.setRowCount(0)
        _status_col = {
            "Filled":       "#00ff88",
            "Cancelled":    "#ff6666",
            "Submitted":    "#ffd700",
            "PreSubmitted": "#aaa",
        }
        for o in orders:
            r    = self.tbl_jnl_orders.rowCount()
            scol = _status_col.get(o["status"], "#ccc")
            self.tbl_jnl_orders.insertRow(r)
            vals = [
                o["ts"][11:], o["status"], str(o["oid"]),
                o.get("sym", ""), o.get("right", ""),
                str(int(o["strike"])) if o.get("strike") else "",
                o.get("action", ""),
                str(int(o["qty"])) if o.get("qty") else "",
                f"{o['price']:.2f}"     if o.get("price")     else "",
                f"{o['und_price']:.2f}" if o.get("und_price") else "―",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 1:
                    item.setForeground(QBrush(QColor(scol)))
                self.tbl_jnl_orders.setItem(r, c, item)

        # ── 탭3: 미청산 ─────────────────────────────────────────
        opens = get_open_trades()
        self.tbl_jnl_open.setRowCount(0)
        for o in opens:
            r = self.tbl_jnl_open.rowCount()
            self.tbl_jnl_open.insertRow(r)
            for c, v in enumerate([
                o["open_date"], o["sym"], o.get("right", ""),
                str(int(o["strike"])) if o.get("strike") else "",
                str(int(o["qty"])), f"{o['entry_price']:.2f}", "―"
            ]):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                self.tbl_jnl_open.setItem(r, c, item)

        # ── 일일 요약 ─────────────────────────────────────────────
        s = get_daily_summary(date_str)
        if s["trades"]:
            col  = "#16a34a" if s["net_pnl"] >= 0 else "#dc2626"
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
