"""
order_sniper_manage.py — 스나이퍼 조건 관리 로직
════════════════════════════════════════════════════════
포함 내용:
  - OrderSniperManageMixin
      set_sniper_target()     행사가 클릭 → 자동 입력
      _sniper_add()           조건 등록 + 시세 구독
      _sniper_row_click()     행 클릭 → 개별 해제
      _sniper_remove()        단일 조건 해제
      _sniper_clear_all()     전체 해제
      _sniper_save()          JSON 저장 (절대경로+날짜)
      _sniper_load()          JSON 복원 (가장 최근 파일)
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QMessageBox

from core import make_opt_contract


from call_put_tab.order_sniper_persist import OrderSniperPersistMixin


class OrderSniperManageMixin(OrderSniperPersistMixin):
    """스나이퍼 조건 등록/해제/저장/복원 로직."""

    def set_sniper_target(self, strike: str, right: str, expiry: str):
        """core_fetch._tbl_click()에서 호출.
        행사가·C/P·만기를 신규 탭 및 스나이퍼 탭 입력 필드에 공통 입력한다.
        """
        if hasattr(self, 'qord_side'):   self.qord_side.setText(right.upper())
        if hasattr(self, 'qord_strike'): self.qord_strike.setText(str(strike))

        if hasattr(self, 'snp_strike'): self.snp_strike.setText(str(strike))
        if hasattr(self, 'snp_right'):
            self.snp_right.setCurrentIndex(0 if right.upper() == "C" else 1)
        if hasattr(self, 'snp_expiry'): self.snp_expiry.setText(str(expiry))

        tab_w = getattr(self, '_qord_tab_widget', None)
        if tab_w:
            for i in range(tab_w.count()):
                if "신규" in tab_w.tabText(i):
                    tab_w.setCurrentIndex(i)
                    break

        if hasattr(self, 'snp_status'):
            self.snp_status.setText(f"✅ 자동 입력: {strike}{right}  만기={expiry}")
            self.snp_status.setStyleSheet(
                "color:#00ff88;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")

    def _sniper_add(self):
        """입력값 검증 → 시세 구독 → 활성 목록 추가."""
        from PyQt5.QtGui import QColor, QBrush
        from PyQt5.QtWidgets import QTableWidgetItem

        strike_txt = self.snp_strike.text().strip()
        right      = self.snp_right.currentText()
        expiry     = self.snp_expiry.text().strip()
        price_txt  = self.snp_price.text().strip()
        time_txt   = self.snp_time.text().strip()
        margin     = self.snp_margin.value()
        action     = self.snp_action.currentText()
        otype      = self.snp_otype.currentText()
        oprice_txt = self.snp_oprice.text().strip()
        qty        = self.snp_qty.value()
        cmp_idx    = self.snp_cmp.currentIndex()

        if not strike_txt:
            QMessageBox.warning(self, "입력 오류", "행사가를 입력하세요."); return
        try:
            strike = float(strike_txt)
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "행사가는 숫자여야 합니다."); return
        if not expiry or len(expiry) != 8:
            QMessageBox.warning(self, "입력 오류",
                "만기일을 YYYYMMDD 형식으로 입력하세요."); return
        if not price_txt:
            QMessageBox.warning(self, "입력 오류", "목표가를 입력하세요."); return
        try:
            target_price = float(price_txt)
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "목표가는 숫자여야 합니다."); return
        if otype == "LMT" and not oprice_txt:
            QMessageBox.warning(self, "입력 오류", "LMT 주문가격을 입력하세요."); return
        try:
            order_price = float(oprice_txt) if oprice_txt else 0.0
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "주문가격은 숫자여야 합니다."); return
        if len(self._snipers) >= 20:
            QMessageBox.warning(self, "한도 초과", "최대 20개까지 등록 가능합니다."); return

        cmp_op = "<=" if cmp_idx == 0 else ">="
        rid    = self._sniper_next_rid
        self._sniper_next_rid += 1
        if self._sniper_next_rid >= 8120:
            self._sniper_next_rid = 8100

        sym = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "SPX"
        try:
            contract = make_opt_contract(sym, strike, right, expiry)
            if self.mw.connected:
                from core import router
                self.mw.ib.reqMktData(rid, contract, "232", False, False, [])
                router.register_price(rid, rid, self._sniper_tick)
        except Exception as e:
            self._log(f"[스나이퍼] 시세 요청 오류: {e}")

        def _mk_item(text, color="#ccc"):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(0x0004)
            it.setForeground(QBrush(QColor(color)))
            return it

        row_idx   = self.snp_tbl.rowCount()
        cmp_disp  = f"{cmp_op} ${target_price:.2f}"
        time_disp = f"{time_txt} ±{margin}분" if time_txt else "항상"
        self.snp_tbl.insertRow(row_idx)
        self.snp_tbl.setItem(row_idx, 0, _mk_item(f"{int(strike)}{right}", "#ffd700"))
        self.snp_tbl.setItem(row_idx, 1, _mk_item(cmp_disp,    "#00ff88"))
        self.snp_tbl.setItem(row_idx, 2, _mk_item("―"))
        self.snp_tbl.setItem(row_idx, 3, _mk_item(time_disp,   "#5dade2"))
        self.snp_tbl.setItem(row_idx, 4, _mk_item("👁 감시중", "#aaa"))

        self._snipers[rid] = {
            "sym": sym, "strike": strike, "right": right, "expiry": expiry,
            "target_price": target_price, "cmp_op": cmp_op,
            "time_kst": time_txt, "time_margin": margin,
            "qty": qty, "action": action, "order_type": otype,
            "order_price": order_price, "triggered": False,
            "row_idx": row_idx, "cur_price": None,
        }

        if not self._sniper_timer.isActive():
            self._sniper_timer.start()

        cmp_lbl = "이하" if cmp_op == "<=" else "이상"
        self._log(
            f"[스나이퍼 등록] {sym} {int(strike)}{right}  "
            f"목표 ${target_price:.2f} {cmp_lbl}  "
            f"시간={time_disp}  {action} {qty}계약 {otype}")
        self.snp_status.setText(
            f"✅ 등록: {int(strike)}{right}  {cmp_disp}  {time_disp}")
        self.snp_status.setStyleSheet(
            "color:#00ff88;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")

    def _sniper_row_click(self, row: int, col: int):
        """행 클릭 → 개별 스나이퍼 해제."""
        target_rid = None
        for rid, sn in self._snipers.items():
            if sn.get("row_idx") == row:
                target_rid = rid; break
        if target_rid is None: return
        sn    = self._snipers[target_rid]
        label = f"{int(sn['strike'])}{sn['right']}"
        ret   = QMessageBox.question(
            self, "스나이퍼 해제",
            f"{label} 스나이퍼를 해제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        self._sniper_remove(target_rid)
        self._log(f"[스나이퍼 해제] {label}")
        self.snp_status.setText(f"해제됨: {label}")
        self.snp_status.setStyleSheet(
            "color:#aaa;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")

    def _sniper_remove(self, rid: int):
        """단일 조건 해제 + 시세 구독 취소."""
        if rid not in self._snipers: return
        sn = self._snipers.pop(rid)
        try:
            if self.mw.connected:
                self.mw.ib.cancelMktData(rid)
            from core import router
            router.unregister_price(self._sniper_tick)
        except Exception:
            pass
        ri = sn.get("row_idx")
        if ri is not None and ri < self.snp_tbl.rowCount():
            self.snp_tbl.removeRow(ri)
            for s in self._snipers.values():
                if s.get("row_idx", 0) > ri:
                    s["row_idx"] -= 1

    def _sniper_clear_all(self):
        """전체 스나이퍼 조건 해제."""
        if not self._snipers: return
        ret = QMessageBox.question(
            self, "전체 해제",
            f"스나이퍼 조건 {len(self._snipers)}개를 모두 해제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        for rid in list(self._snipers.keys()):
            try:
                if self.mw.connected: self.mw.ib.cancelMktData(rid)
            except Exception: pass
        self._snipers.clear()
        self.snp_tbl.setRowCount(0)
        self._sniper_timer.stop()
        self._log("[스나이퍼] 전체 해제")
        self.snp_status.setText("전체 해제됨")
        self.snp_status.setStyleSheet(
            "color:#aaa;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")
