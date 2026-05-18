"""
balance_journal.py — 매매일지 DB 조회 로직
════════════════════════════════════════════════════════
포함 내용:
  - BalanceJournalMixin
      _jnl_load()          선택 날짜 매매일지 DB 조회 → 3탭 갱신
                           (체결내역 / 주문로그 / 미청산 + 일일 요약)
      _monthly_load()      월간 합산 손익 조회 → 월간탭 갱신
      _monthly_expire_dialog()  만기소멸 수동 처리 다이얼로그
════════════════════════════════════════════════════════

[v2.4 신규]
  - 월간 합산 탭 (📅 월간합산) 추가
  - 만기소멸(expired) 포함 집계
  - 앱 시작 시 과거 만기 포지션 자동 소멸 처리
"""

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (QTableWidgetItem, QDialog, QFormLayout,
                             QDialogButtonBox, QDateEdit, QLineEdit,
                             QLabel, QMessageBox)
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

    # ══════════════════════════════════════════════════════════════
    # [v2.4 신규] 월간 합산 탭
    # ══════════════════════════════════════════════════════════════

    def _monthly_load(self):
        """월간 합산 조회 → 월간탭 갱신."""
        year  = self._monthly_year.value()
        month = self._monthly_month.value()

        try:
            from trade_log import get_monthly_summary, get_monthly_daily_breakdown
        except ImportError:
            self._monthly_summary_lbl.setText("⚠ trade_log 모듈 없음")
            return

        summary   = get_monthly_summary(year, month)
        breakdown = get_monthly_daily_breakdown(year, month)

        # ── 요약 라벨 ──────────────────────────────────────
        if summary['trade_cnt'] == 0:
            self._monthly_summary_lbl.setText(
                f"  {summary['year_month']} — 거래 없음")
            self._monthly_summary_lbl.setStyleSheet(
                "color:#94a3b8;font-size:11px;"
                "background:#f8fafc;border-bottom:1px solid #f0f2f6;"
                "padding:6px 16px;")
        else:
            net  = summary['net_pnl']
            sign = "+" if net >= 0 else ""
            col  = "#16a34a" if net >= 0 else "#dc2626"
            expired_note = (f"  ☠ 만기소멸 {summary['expired_cnt']}건 포함"
                            if summary['expired_cnt'] else "")
            self._monthly_summary_lbl.setText(
                f"  {summary['year_month']}  |  {summary['trade_cnt']}건"
                f"{expired_note}"
                f"   실현손익: {sign}${summary['gross_pnl']:,.2f}"
                f"   수수료: -${summary['commission']:,.2f}"
                f"   순손익: {sign}${net:,.2f}")
            self._monthly_summary_lbl.setStyleSheet(
                f"color:{col};font-size:11px;font-weight:600;"
                "background:#f8fafc;border-bottom:1px solid #f0f2f6;"
                "padding:6px 16px;")

        # ── 일별 브레이크다운 테이블 ───────────────────────
        tbl = self._monthly_table
        tbl.setRowCount(0)

        for row in breakdown:
            r = tbl.rowCount()
            tbl.insertRow(r)

            net      = row['net_pnl']
            gross    = row['gross_pnl']
            has_exp  = row['expired_cnt'] > 0
            net_str  = f"+${net:,.2f}"   if net   >= 0 else f"-${abs(net):,.2f}"
            gross_str= f"+${gross:,.2f}" if gross >= 0 else f"-${abs(gross):,.2f}"
            exp_str  = f"☠{row['expired_cnt']}" if has_exp else ""

            vals = [
                row['date'],
                str(row['trade_cnt']),
                exp_str,
                gross_str,
                f"${row['commission']:,.2f}",
                net_str,
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                # 만기소멸 있는 날 → 행 전체 회색 처리
                if has_exp and c not in (5,):
                    item.setForeground(QBrush(QColor("#888888")))
                # 순손익 컬럼 색상
                if c == 5:
                    item.setForeground(QBrush(
                        QColor("#16a34a") if net >= 0 else QColor("#dc2626")))
                tbl.setItem(r, c, item)

    def _monthly_expire_dialog(self):
        """만기소멸 수동 처리 다이얼로그."""
        try:
            from trade_log import expire_worthless, expire_worthless_by_expiry
        except ImportError:
            QMessageBox.warning(self, "오류", "trade_log 모듈을 찾을 수 없습니다.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("📛 만기소멸 처리")
        layout = QFormLayout(dlg)

        date_edit = QDateEdit(QDate.currentDate())
        date_edit.setCalendarPopup(True)
        layout.addRow("만기일:", date_edit)

        note = QLabel(
            "특정 종목만 처리하려면 아래 항목을 입력하세요.\n"
            "비워두면 해당 만기일의 모든 open 포지션을 처리합니다.")
        note.setStyleSheet("color:#64748b;font-size:10px;")
        layout.addRow(note)

        sym_edit    = QLineEdit(); sym_edit.setPlaceholderText("SPX  (비우면 전체)")
        expiry_edit = QLineEdit(); expiry_edit.setPlaceholderText("20260117  (비우면 만기일 자동 사용)")
        right_edit  = QLineEdit(); right_edit.setPlaceholderText("C 또는 P  (비우면 전체)")
        strike_edit = QLineEdit(); strike_edit.setPlaceholderText("5500  (비우면 전체)")

        layout.addRow("종목 (sym):", sym_edit)
        layout.addRow("만기 YYYYMMDD:", expiry_edit)
        layout.addRow("콜/풋 (C/P):", right_edit)
        layout.addRow("행사가:", strike_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addRow(btns)

        if dlg.exec_() != QDialog.Accepted:
            return

        expired_date = date_edit.date().toString("yyyy-MM-dd")
        sym    = sym_edit.text().strip()
        expiry = expiry_edit.text().strip()
        right  = right_edit.text().strip().upper()
        strike = strike_edit.text().strip()

        # 4개 항목 모두 입력 시 특정 종목 처리, 아니면 만기일 일괄 처리
        if sym and expiry and right and strike:
            try:
                cnt = expire_worthless(sym, expiry, right,
                                       float(strike), expired_date)
            except Exception as e:
                QMessageBox.warning(self, "오류", f"처리 중 오류: {e}")
                return
        else:
            cnt = expire_worthless_by_expiry(expired_date)

        if cnt == 0:
            QMessageBox.information(
                self, "결과",
                f"{expired_date} 기준 처리할 open 포지션이 없습니다.")
        else:
            QMessageBox.information(
                self, "완료",
                f"만기소멸 처리 예약: {cnt}건\n"
                f"(만기일: {expired_date})\n\n"
                f"'📂 조회' 버튼을 누르면 결과가 반영됩니다.")
            # 자동으로 월간 탭 갱신
            self._monthly_load()
