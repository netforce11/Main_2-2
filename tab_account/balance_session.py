"""
balance_session.py — 세션 통계·거래 기록·DB 저장 로직
════════════════════════════════════════════════════════
포함 내용:
  - BalanceSessionMixin
      _clear_session()        세션 초기화
      add_trade()             체결 내역 추가 + 통계 갱신
      _update_session_stats() 승률·평균보유·손익 갱신
      _on_order_status_log()  bridge.order_status_sig → DB 저장
      _on_exec_log()          bridge.exec_sig → DB 저장
      _apply_theme()          다크/라이트 테이블 재적용
════════════════════════════════════════════════════════
"""

from PyQt5.QtGui import QColor, QBrush
from core import tbl_set, ts, ts_full


class BalanceSessionMixin:
    """세션 통계·거래 기록·DB 저장 로직. BalanceGrid에 mixin된다."""

    def _clear_session(self):
        self._session = {"trades": [], "start_time": ts_full()}
        self.tbl_trades.setRowCount(0)
        self._update_session_stats()

    def add_trade(self, sym, direction, qty, entry, exit_p, hold_min):
        pnl = (exit_p - entry) * qty * 100 * (1 if direction == "BUY" else -1)
        self._session["trades"].append({
            "time": ts(), "sym": sym, "dir": direction, "qty": qty,
            "entry": entry, "exit": exit_p, "pnl": pnl, "hold": hold_min})
        r = self.tbl_trades.rowCount()
        self.tbl_trades.insertRow(r)
        for c, v in enumerate([ts(), sym, direction, str(qty),
                                f"{entry:.2f}", f"{exit_p:.2f}",
                                f"${pnl:,.2f}", f"{hold_min:.1f}"]):
            tbl_set(self.tbl_trades, r, c, v)
        col = "#00ff88" if pnl >= 0 else "#ff4444"
        self.tbl_trades.item(r, 6).setForeground(QBrush(QColor(col)))
        self._update_session_stats()

    def _update_session_stats(self):
        trades = self._session.get("trades", [])
        cnt    = len(trades)
        if cnt == 0:
            for lb in (self.lbl_winrate, self.lbl_avghold,
                       self.lbl_tot_pnl, self.lbl_tot_cnt):
                lb.setText(lb.text().split(":")[0] + ": ―")
            return
        wins     = sum(1 for t in trades if t["pnl"] >= 0)
        avg_hold = sum(t["hold"] for t in trades) / cnt
        tot_pnl  = sum(t["pnl"] for t in trades)
        wr_col   = "#00ff88" if wins / cnt >= 0.5 else "#ff4444"
        pnl_col  = "#00ff88" if tot_pnl >= 0 else "#ff4444"
        self.lbl_winrate.setText(f"승률: {wins/cnt*100:.1f}%")
        self.lbl_winrate.setStyleSheet(f"color:{wr_col};border:none;")
        self.lbl_avghold.setText(f"평균 보유: {avg_hold:.1f}분")
        self.lbl_tot_pnl.setText(f"누적 손익: ${tot_pnl:,.2f}")
        self.lbl_tot_pnl.setStyleSheet(f"color:{pnl_col};border:none;")
        self.lbl_tot_cnt.setText(f"총 거래: {cnt}건")

    def _on_order_status_log(self, oid: int, status: str,
                             filled: float, remaining: float) -> None:
        """bridge.order_status_sig → 모든 주문 상태변경 DB 저장."""
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
        """bridge.exec_sig → 모든 체결 DB 저장 + BUY/SELL 매칭."""
        try:
            from trade_log import log_exec, run_match, get_und_context
            log_exec(
                oid=oid, source='bridge', sym=sym, action=side,
                qty=qty, price=price, und_ctx=get_und_context(),
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
