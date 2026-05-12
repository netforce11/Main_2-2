"""
multi_price_logic.py — MultiPriceGrid 슬롯·틱·트리거 로직
════════════════════════════════════════════════════════
포함 내용:
  - MultiPriceLogicMixin
      _connect_signals()   라우터 시그널 등록
      _on_watch_click()    관심종목 클릭 → 빈 슬롯 자동 로딩
      _load_from_input()   심볼 입력 → 슬롯 로딩
      _load_slot()         IBKR reqMktData 요청
      _on_tick()           가격 틱 수신 (현재가·거래량·전일종가·등락률)
      _on_tick_opt()       옵션 틱 수신 (Delta·Gamma·Theta)
      _add_trigger()       트리거 등록
      _on_trg_dbl()        트리거 더블클릭 편집
      _trg_keypress()      Del 키 → 삭제
      _del_trigger()       선택 트리거 삭제
      _clr_triggers()      전체 트리거 초기화
      _check_triggers()    가격 수신 시 조건 평가

의존:
  account.multi_price_sound  사운드·파일·관심종목 로직
════════════════════════════════════════════════════════
"""

from datetime import datetime

from PyQt5.QtWidgets import QMessageBox, QTableWidget, QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

from core import router, tbl_set, make_und_contract, auto_mdt, ts, REQ_MULTI
from tab_account.multi_price_sound import MultiPriceSoundMixin


class MultiPriceLogicMixin(MultiPriceSoundMixin):
    """슬롯·틱·트리거 로직 Mixin (사운드·파일·관심종목 포함)."""

    def _connect_signals(self):
        router.register_price(REQ_MULTI, REQ_MULTI + 299, self._on_tick)
        router.register_option(REQ_MULTI, REQ_MULTI + 299, self._on_tick_opt)

    # ── 슬롯 로딩 ─────────────────────────────────────────────────
    def _on_watch_click(self, item):
        sym  = item.text().split()[0]
        slot = next((i for i, d in enumerate(self.slot_data) if not d.get("sym")), 0)
        self._load_slot(slot, sym)

    def _load_from_input(self, idx):
        sym = self.slot_w[idx]["input"].text().strip().upper()
        if sym: self._load_slot(idx, sym)

    def _load_slot(self, idx, sym):
        if not self.mw.connected:
            self.slot_w[idx]["price"].setText("미연결"); return
        auto_mdt(self.mw.ib)
        rid = self.slot_rids[idx]
        try: self.mw.ib.cancelMktData(rid)
        except Exception: pass
        self.slot_data[idx] = {"sym": sym}
        self.slot_w[idx]["sym"].setText(sym)
        self.slot_w[idx]["price"].setText("조회 중…")
        self.slot_w[idx]["input"].setText(sym)
        self.mw.ib.reqMktData(rid, make_und_contract(sym), "232", False, False, [])

    # ── Tick 수신 ─────────────────────────────────────────────────
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
                cur = self.slot_data[i].get("price")
                tbl_set(self.slot_w[i]["tbl"], 5, 1, f"{price:,.2f}")
                self.slot_data[i]["prev_close"] = price
                if cur and price > 0:
                    chg  = cur - price; pct = chg / price * 100
                    col  = "#00e676" if chg >= 0 else "#ff5252"
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
            tbl_set(self.slot_w[i]["tbl"], 3, 1, f"{gamma:.6f}",  "#88ff44")
            tbl_set(self.slot_w[i]["tbl"], 4, 1, f"{theta:.4f}",  "#ff8844")

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
        ret = QMessageBox.question(self, "초기화", "모든 트리거를 삭제합니까?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes: self.tbl_trg.setRowCount(0)

    def _check_triggers(self, slot_idx, price):
        now_s = datetime.now().strftime("%H:%M:%S")
        for r in range(self.tbl_trg.rowCount()):
            st_item = self.tbl_trg.item(r, 3)
            if not st_item or st_item.text() == "발동!": continue
            p_item = self.tbl_trg.item(r, 0); t_item = self.tbl_trg.item(r, 1)
            d_item = self.tbl_trg.item(r, 2)
            price_ok = True; time_ok = True
            if p_item and p_item.text().strip():
                try:
                    if float(p_item.text()) < price: price_ok = False
                except Exception: pass
            if t_item and t_item.text().strip():
                time_ok = now_s >= t_item.text().strip()
            if price_ok and time_ok:
                st_item.setText("발동!")
                st_item.setForeground(QBrush(QColor("#ffd700")))
                desc = d_item.text() if d_item else "―"
                msg  = f"★ 트리거 발동! 슬롯{slot_idx+1} {price:,.2f} ({desc})"
                self.trg_log.append(f"[{ts()}] {msg}")
                self.trigger_logs.append({"time": ts(), "msg": msg})
                self._play_alert_sound()
