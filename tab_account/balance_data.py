"""
balance_data.py — 계좌/포지션/주문 수신 + PnL 이력 로직
════════════════════════════════════════════════════════
포함 내용:
  - BalanceDataMixin
      _on_acct()       계좌 요약 수신 → 테이블 + KPI 갱신
      _on_pos()        포지션 수신 → 테이블 갱신
      _on_order()      미체결 주문 수신 → 테이블 갱신
      _record_pnl()    일자별 PnL 이력 기록
      _update_chart()  PnL 차트 갱신
      _save_history()  PnL 이력 CSV 저장
      _load_history()  PnL 이력 CSV 복원
════════════════════════════════════════════════════════
"""

from datetime import date

from PyQt5.QtGui import QColor, QBrush

from core import tbl_set, append_csv, load_csv

PNL_HIST_CSV = "pnl_history.csv"

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False


class BalanceDataMixin:
    """계좌·포지션·주문 수신 및 PnL 이력 로직. BalanceGrid에 mixin된다."""

    def _on_acct(self, tag, val, cur, acct):
        if acct and not self._pnl_acct_id:
            self._pnl_acct_id = acct
        if tag not in self._acct_rows:
            r = self.tbl_acct.rowCount()
            self.tbl_acct.insertRow(r)
            self._acct_rows[tag] = r
            tbl_set(self.tbl_acct, r, 0, tag)
        r = self._acct_rows[tag]
        try:
            disp = f"{float(val):,.2f}"
        except Exception:
            disp = val
        tbl_set(self.tbl_acct, r, 1, disp)
        tbl_set(self.tbl_acct, r, 2, cur)
        if tag == "UnrealizedPnL":
            try:
                v    = float(val)
                sign = "+" if v >= 0 else ""
                col  = "#00ff88" if v >= 0 else "#ff4444"
                self.lbl_pnl.setText(f"{sign}${v:,.2f}")
                self.lbl_pnl.setStyleSheet(
                    f"color:{col};border:none;font-size:22px;font-weight:bold;")
                self.tbl_acct.item(r, 1).setForeground(QBrush(QColor(col)))
                self._record_pnl(0.0, v)
            except Exception:
                pass
        if tag == "NetLiquidation":
            try:
                self.lbl_nlv._val.setText(f"${float(val):,.0f}")
                self._record_pnl(float(val), 0.0)
            except Exception:
                pass
        if tag == "BuyingPower":
            try:
                self.lbl_bp._val.setText(f"${float(val):,.0f}")
            except Exception:
                pass
        if tag == "RealizedPnL":
            try:
                v   = float(val)
                col = "#00ff88" if v >= 0 else "#ff4444"
                self.lbl_rpnl._val.setText(f"${v:,.2f}")
                self.lbl_rpnl._val.setStyleSheet(f"color:{col};border:none;")
            except Exception:
                pass

    def _on_pos(self, acct, sym, right, pos, avg):
        r = self.tbl_pos.rowCount()
        self.tbl_pos.insertRow(r)
        for c, v in enumerate([acct, sym, right, str(int(pos)), f"{avg:.2f}"]):
            tbl_set(self.tbl_pos, r, c, v)
        col = "#00ff88" if pos > 0 else "#ff4444"
        self.tbl_pos.item(r, 3).setForeground(QBrush(QColor(col)))

    def _on_order(self, oid, sym, right, action, qty, price, status):
        for rr in range(self.tbl_ord.rowCount()):
            if self.tbl_ord.item(rr, 0) and self.tbl_ord.item(rr, 0).text() == str(oid):
                tbl_set(self.tbl_ord, rr, 6, status)
                return
        r = self.tbl_ord.rowCount()
        self.tbl_ord.insertRow(r)
        for c, v in enumerate([str(oid), sym, right, action,
                                str(int(qty)), f"{price:.2f}", status]):
            tbl_set(self.tbl_ord, r, c, v)
        col = "#33aaff" if action == "BUY" else "#ff8844"
        self.tbl_ord.item(r, 3).setForeground(QBrush(QColor(col)))

    def _record_pnl(self, nlv, pnl):
        today = date.today().isoformat()
        if not self._pnl_history or self._pnl_history[-1][0] != today:
            if nlv > 0:
                self._pnl_history.append((today, nlv, pnl))
                self._update_chart()

    def _update_chart(self):
        if not PG or len(self._pnl_history) < 1:
            return
        xs   = list(range(len(self._pnl_history)))
        nlvs = [h[1] for h in self._pnl_history]
        pnls = [h[2] for h in self._pnl_history]
        self.curve_nlv.setData(xs, nlvs)
        self.curve_pnl.setData(xs, pnls)

    def _save_history(self):
        from PyQt5.QtWidgets import QMessageBox
        from core import SAVE_DIR
        for date_s, nlv, pnl in self._pnl_history:
            append_csv(PNL_HIST_CSV, {"date": date_s, "nlv": nlv, "pnl": pnl})
        QMessageBox.information(self, "저장",
            f"PnL 이력 저장 완료 ({SAVE_DIR / PNL_HIST_CSV})")

    def _load_history(self):
        rows = load_csv(PNL_HIST_CSV)
        self._pnl_history = [
            (r["date"], float(r["nlv"]), float(r["pnl"])) for r in rows]
        self._update_chart()
        self._update_session_stats()
