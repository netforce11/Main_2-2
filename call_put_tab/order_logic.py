"""
order_logic.py — 주문 실행 로직  v6.6
════════════════════════════════════════════════════════
수정 대상: 주문 전송 동작, TIF, 확인 팝업
포함 메서드:
  _amend_order()   정정 전송
  _cancel_order()  취소 전송
  _qord_fill()     주문창 자동 입력
  _qord_place()    신규 주문 전송

[v6.6 수정]
  ① 중복 주문 발주 위험 수정 (_sniper_check / _sniper_fire):
    - triggered=True 설정을 placeOrder 성공 후로 이동
    - placeOrder 예외 시 triggered=False 복구 + UI 오류 표시
    - OrderID 없음 시에도 triggered=False 복구

  ② 정정 주문 Contract 소실 방지 (_amend_order):
    - 재시작 후 _open_orders_buf 비어있으면 자동으로 미체결 조회 후 재시도
    - 5초 후 재시도 1회 (QTimer.singleShot)

  ③ 스나이퍼 JSON 저장 경로 절대경로 + 날짜 포함 파일명
  ④ get_emergency_sell_lmt_price() 헬퍼 추가 (ERR 201 대응)
════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QMessageBox

from core import make_opt_contract


class OrderLogicMixin:
    """주문 실행 로직. CallPutGrid에 mixin된다."""

    def _amend_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            oid   = int(self.amend_oid.text().strip())
            price = float(self.amend_price.text().strip())
            qty   = self.amend_qty.value()
        except ValueError:
            QMessageBox.warning(self, "입력 오류",
                "주문ID와 새 가격을 올바르게 입력하세요."); return
        try:
            from ibapi.order import Order as IbOrder

            # ✅ 미체결 버퍼에서 OID에 해당하는 contract 조회
            buf = getattr(self, '_open_orders_buf', [])
            matched = next((o for o in buf if o["oid"] == oid), None)

            # [v6.6 ②] Contract 소실 방지: 버퍼 비어있으면 자동 조회 후 재시도
            if matched is None or matched.get("contract") is None:
                if not buf:
                    self._log(f"⚠ 정정: _open_orders_buf 비어있음 → 미체결 자동 조회 후 재시도")
                    if hasattr(self, '_fetch_open_orders'):
                        self._fetch_open_orders()
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(5000, self._amend_order)
                    self.lbl_amend_status.setText("⏳ 미체결 조회 중… 5초 후 재시도")
                    self.lbl_amend_status.setStyleSheet(
                        "color:#ffbb00;font-size:11px;"
                        "border:1px solid #333;border-radius:3px;padding:2px;")
                else:
                    QMessageBox.warning(self, "정정 오류",
                        f"OID={oid} 의 contract 정보를 찾을 수 없습니다.\n"
                        "'미체결 주문 조회'를 먼저 클릭하세요.")
                return
            contract = matched["contract"]

            ibord = IbOrder()
            ibord.action        = matched["action"]   # ✅ ERR 321 fix — BUY/SELL 반드시 설정
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = matched.get("tif", "DAY")   # 원래 TIF 유지, 없으면 DAY
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            self.mw.ib.placeOrder(oid, contract, ibord)
            self.lbl_amend_status.setStyleSheet(
                "color:#90caf9;font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_amend_status.setText(
                f"전송: OID={oid} @ ${price:.2f} ×{qty}")
            self._log(f"✏ 정정: OID={oid}  새가격=${price:.2f}  수량={qty}")
        except Exception as e:
            self.lbl_amend_status.setText(f"오류: {e}")
            self._log(f"❌ 정정 오류: {e}")

    def _cancel_order(self):
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            oid = int(self.cancel_oid.text().strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "주문ID를 입력하세요."); return
        ret = QMessageBox.question(self, "취소 확인",
            f"주문 OID={oid} 를 취소하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        try:
            self.mw.ib.cancelOrder(oid)
            self.lbl_cancel_status.setStyleSheet(
                "color:#ff6666;font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_cancel_status.setText(f"취소 전송: OID={oid}")
            self._log(f"✕ 취소: OID={oid}")
        except Exception as e:
            self.lbl_cancel_status.setText(f"오류: {e}")
            self._log(f"❌ 취소 오류: {e}")

    def _qord_fill(self, side: str, strike: str,
                   price: float = None, source: str = ""):
        self.qord_side.setText(side)
        self.qord_strike.setText(strike)
        if price is not None:
            self.qord_price.setText(f"{price:.2f}")
        self.lbl_qord_src.setText(source)

    def _qord_place(self, action: str):
        side      = self.qord_side.text().strip()
        strike    = self.qord_strike.text().strip()
        qty       = self.qord_qty.value()
        is_lmt    = self.qord_lmt.isChecked()
        price_txt = self.qord_price.text().strip()
        tif       = self.qord_tif.currentText()
        sym       = self.edit_sym.text().strip().upper() if hasattr(self,'edit_sym') else ""

        # ── 주식/지수 vs 옵션 자동 판별 ──────────────────────
        # 현재가 패널이 옵션 모드이거나, side가 C/P이면 옵션 주문
        pp_mode   = getattr(self, '_pp_mode', 'und')
        is_option = (side in ("C","P")) and bool(strike)
        is_stock  = not is_option

        if is_stock:
            # 주식/ETF/지수 현물 주문 (side/strike 없어도 됨)
            if not sym:

                QMessageBox.warning(self,"입력 오류","종목이 선택되지 않았습니다.")
                return
        else:
            if is_lmt and not price_txt:

                QMessageBox.warning(self,"입력 오류","지정가를 입력하세요.")
                return

        order_type = "LMT" if is_lmt else "MKT"
        try:
            price = float(price_txt) if is_lmt and price_txt else 0.0
        except ValueError:

            QMessageBox.warning(self,"입력 오류","유효한 가격을 입력하세요.")
            return

        action_kr  = "매수" if action == "BUY" else "매도"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"

        if is_option:
            label = "CALL" if side=="C" else "PUT"
            msg = (f"{action_kr} {order_type}  "
                   f"{sym} {label} {strike}  {qty}계약  {price_disp}  {tif}")
        else:
            msg = (f"{action_kr} {order_type}  "
                   f"{sym}  {qty}주  {price_disp}  {tif}")

        # chk_order_confirm OFF 시 _skip_order_confirm=True → 팝업 건너뜀
        skip_confirm = getattr(self, '_skip_order_confirm', False)
        if not skip_confirm:
            dlg = QMessageBox(self)
            dlg.setWindowTitle(f"주문 확인 — {action_kr}")
            dlg.setText(f"⚠ 아래 주문을 전송합니다.\n\n{msg}\n\n계속하시겠습니까?")
            dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            dlg.setDefaultButton(QMessageBox.Yes)   # 기본값 Yes
            yes_btn = dlg.button(QMessageBox.Yes)   # Yes 버튼 녹색 강조
            if yes_btn:
                yes_btn.setStyleSheet(
                    "QPushButton{background:#1a5c2e;color:#00ff88;"
                    "font-weight:bold;padding:4px 16px;border-radius:4px;"
                    "border:1px solid #00ff88;}"
                    "QPushButton:hover{background:#2a7c3e;}")
            if dlg.exec_() != QMessageBox.Yes:
                return
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 먼저 연결하세요.")
            return

        try:
            from ibapi.order import Order as IbOrder
            from ibapi.contract import Contract

            ibord = IbOrder()
            ibord.action        = action
            ibord.orderType     = order_type
            ibord.totalQuantity = qty
            ibord.tif           = tif
            ibord.eTradeOnly    = False   # ✅ ERR 10268 fix
            ibord.firmQuoteOnly = False   # ✅ ERR 10268 fix
            if is_lmt and price: ibord.lmtPrice = price

            if is_option:
                # 옵션 계약
                expiry, tag = self._get_expiry()   # ✅ CUSTOM 포함 실제 날짜 반환
                if expiry is None: return           # 만기일 오류 시 중단
                contract = make_opt_contract(sym, float(strike), side, expiry, tag)
            else:
                # 주식/ETF 계약
                from core import INDEX_SYM
                contract = Contract()
                contract.symbol   = sym
                contract.currency = "USD"
                contract.exchange = "SMART"
                if sym in INDEX_SYM:
                    # 지수는 현물 거래 불가 — CFD or 선물로 안내
                    QMessageBox.warning(self,"주문 불가",
                        f"{sym}은 지수로 직접 거래할 수 없습니다.\n"
                        "ETF(SPY/QQQ 등)나 선물(ES/NQ)로 주문하세요.")
                    return
                contract.secType  = "STK"

            oid = self.mw.ib.get_next_id()
            if oid is None:
                QMessageBox.warning(self,"주문 오류","주문 ID를 가져올 수 없습니다.")
                return
            self.mw.ib.placeOrder(oid, contract, ibord)

            col = "#00ff88" if action == "BUY" else "#ff6666"
            self.lbl_qord_status.setStyleSheet(
                f"color:{col};font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_qord_status.setText(f"전송: {msg}")
            self._log(f"📤 빠른주문: {msg}  (OID={oid})")
        except Exception as e:
            self.lbl_qord_status.setText(f"오류: {e}")
            self._log(f"❌ 주문 오류: {e}")

    # ─────────────────────────────────────────────────────────
    # 수량 자동 계산 버튼
    # ─────────────────────────────────────────────────────────
    def _get_current_price_for_qty(self):
        """현재 주문창 가격 반환. 없으면 테이블 선택 종목 Last 가격."""
        try:
            p = float(self.qord_price.text().strip())
            if p > 0: return p
        except: pass
        side = self.qord_side.text().strip()
        strike_txt = self.qord_strike.text().strip()
        if side and strike_txt:
            try:
                tbl = self.tbl_call if side == "C" else self.tbl_put
                strikes = self.call_strikes if side == "C" else self.put_strikes
                target = float(strike_txt)
                row = min(range(len(strikes)), key=lambda i: abs(strikes[i]-target))
                item = tbl.item(row, 1)
                if item: return float(item.text())
            except: pass
        return None

    def _calc_qty_max(self):
        """잔고 기준 최대 수량 계산 → qord_qty 자동 입력."""
        if not self.mw.connected:
            self._log("❌ MAX 수량: TWS 연결 필요"); return
        price = self._get_current_price_for_qty()
        if not price or price <= 0:
            self._log("❌ MAX 수량: 가격을 먼저 입력하세요."); return

        av_funds = [None]
        orig_as  = getattr(self.mw.ib, 'accountSummary',    lambda *a: None)
        orig_ase = getattr(self.mw.ib, 'accountSummaryEnd', lambda *a: None)

        def _on_summary(reqId, account, tag, value, currency):
            if tag == "AvailableFunds":
                try: av_funds[0] = float(value)
                except: pass

        def _on_summary_end(reqId):
            pass

        self.mw.ib.accountSummary    = _on_summary
        self.mw.ib.accountSummaryEnd = _on_summary_end
        try:
            self.mw.ib.reqAccountSummary(9900, "All", "AvailableFunds")
        except Exception as e:
            self._log(f"❌ 잔고 조회 오류: {e}"); return

        from PyQt5.QtCore import QTimer
        def _apply():
            self.mw.ib.accountSummary    = orig_as
            self.mw.ib.accountSummaryEnd = orig_ase
            if av_funds[0] is None:
                self._log("❌ MAX 수량: 잔고 수신 실패 (재시도)"); return
            contract_cost = price * 100   # 옵션 1계약 = premium × 100주
            qty = max(1, int(av_funds[0] / contract_cost))
            self.qord_qty.setValue(qty)
            self._log(f"💰 MAX 수량: 잔고 ${av_funds[0]:,.0f} ÷ 계약비용 ${contract_cost:.0f} → {qty}계약")
        QTimer.singleShot(1500, _apply)

    def _calc_qty_200(self):
        """$200 기준 수량 계산 → qord_qty 자동 입력."""
        price = self._get_current_price_for_qty()
        if not price or price <= 0:
            self._log("❌ $200 수량: 가격을 먼저 입력하세요."); return
        budget = 200.0
        contract_cost = price * 100
        qty = max(1, int(budget / contract_cost))
        self.qord_qty.setValue(qty)
        self._log(f"💵 $200 수량: ${budget:.0f} ÷ 계약비용 ${contract_cost:.0f} → {qty}계약")

    # ═════════════════════════════════════════════════════════
    # 스나이퍼 주문 로직  (order_panel.py 탭5 "🎯 스나이퍼" 연동)
    # ═════════════════════════════════════════════════════════

    # ── 콜풋탭 행사가 클릭 → 자동 입력 ──────────────────────
    def set_sniper_target(self, strike: str, right: str, expiry: str):
        """
        core_fetch._tbl_click() 에서 호출.
        행사가·C/P·만기를 신규 탭 및 스나이퍼 탭 입력 필드에 공통 입력한다.
        포커스는 신규 탭으로 전환한다.
        """
        # ── 신규 탭 공통 입력 (qord_side / qord_strike) ──────
        if hasattr(self, 'qord_side'):
            self.qord_side.setText(right.upper())
        if hasattr(self, 'qord_strike'):
            self.qord_strike.setText(str(strike))

        # ── 스나이퍼 탭 공통 입력 ────────────────────────────
        if hasattr(self, 'snp_strike'):
            self.snp_strike.setText(str(strike))
        if hasattr(self, 'snp_right'):
            self.snp_right.setCurrentIndex(0 if right.upper() == "C" else 1)
        if hasattr(self, 'snp_expiry'):
            self.snp_expiry.setText(str(expiry))

        # ── 신규 탭으로 포커스 전환 (기존: 스나이퍼 탭) ─────
        tab_w = getattr(self, '_qord_tab_widget', None)
        if tab_w:
            for i in range(tab_w.count()):
                if "신규" in tab_w.tabText(i):
                    tab_w.setCurrentIndex(i)
                    break

        if hasattr(self, 'snp_status'):
            self.snp_status.setText(
                f"✅ 자동 입력: {strike}{right}  만기={expiry}")
            self.snp_status.setStyleSheet(
                "color:#00ff88;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")

    # ── 조건 등록 ─────────────────────────────────────────────
    def _sniper_add(self):
        """입력값 검증 → 시세 구독 → 활성 목록 추가."""
        from PyQt5.QtWidgets import QMessageBox
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

        # 검증
        if not strike_txt:
            QMessageBox.warning(self, "입력 오류", "행사가를 입력하세요."); return
        try:
            strike = float(strike_txt)
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "행사가는 숫자여야 합니다."); return
        if not expiry or len(expiry) != 8:
            QMessageBox.warning(self, "입력 오류", "만기일을 YYYYMMDD 형식으로 입력하세요."); return
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

        # 시세 구독
        rid = self._sniper_next_rid
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

        # 테이블 행 추가
        def _mk_item(text, color="#ccc"):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(0x0004)  # AlignCenter
            it.setForeground(QBrush(QColor(color)))
            return it

        row_idx = self.snp_tbl.rowCount()
        self.snp_tbl.insertRow(row_idx)
        self.snp_tbl.setItem(row_idx, 0, _mk_item(f"{int(strike)}{right}", "#ffd700"))
        cmp_disp = f"{cmp_op} ${target_price:.2f}"
        self.snp_tbl.setItem(row_idx, 1, _mk_item(cmp_disp, "#00ff88"))
        self.snp_tbl.setItem(row_idx, 2, _mk_item("―"))
        time_disp = f"{time_txt} ±{margin}분" if time_txt else "항상"
        self.snp_tbl.setItem(row_idx, 3, _mk_item(time_disp, "#5dade2"))
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
            f"시간={time_disp}  {action} {qty}계약 {otype}"
        )
        self.snp_status.setText(f"✅ 등록: {int(strike)}{right}  {cmp_disp}  {time_disp}")
        self.snp_status.setStyleSheet(
            "color:#00ff88;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")

    # ── 시세 틱 수신 ─────────────────────────────────────────
    def _sniper_tick(self, rid: int, tt: int, price: float):
        if rid not in self._snipers or price <= 0: return
        if tt not in (4, 68, 75, 14): return
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush
        sn = self._snipers[rid]
        sn["cur_price"] = price
        ri = sn.get("row_idx")
        if ri is not None:
            it = QTableWidgetItem(f"{price:.2f}")
            it.setForeground(QBrush(QColor("#00cfff")))
            self.snp_tbl.setItem(ri, 2, it)

    # ── 2초 타이머: 조건 평가 → 자동 발주 ────────────────────
    def _sniper_check(self):
        from datetime import datetime, timedelta

        for rid, sn in list(self._snipers.items()):
            if sn["triggered"]: continue
            cur = sn.get("cur_price")

            # 1) 시간 조건
            time_ok = True
            if sn["time_kst"]:
                try:
                    h, m = map(int, sn["time_kst"].split(":"))
                    margin = sn["time_margin"]
                    now_kst = datetime.utcnow() + timedelta(hours=9)

                    if margin == 0:
                        # 0분 = 해당 분 정확히 (HH:MM:00 ~ HH:MM:59)
                        time_ok = (now_kst.hour == h and now_kst.minute == m)
                    else:
                        # N분 = 설정 시각 기준 ±N분 이내 (초 단위)
                        target_dt = now_kst.replace(
                            hour=h, minute=m, second=0, microsecond=0)
                        diff_sec  = abs((now_kst - target_dt).total_seconds())
                        time_ok   = diff_sec <= margin * 60
                except Exception:
                    time_ok = False

            # 2) 프리미엄 조건
            price_ok = False
            if cur is not None and cur > 0:
                price_ok = (cur <= sn["target_price"] if sn["cmp_op"] == "<="
                            else cur >= sn["target_price"])

            # 3) 두 조건 모두 충족 → 발주
            if time_ok and price_ok:
                # [v6.6 ①] triggered=True는 placeOrder 성공 후 설정
                # (기존: 발주 전 True → 예외 시 영구 잠금 버그 수정)
                ri = sn.get("row_idx")
                if ri is not None:
                    from PyQt5.QtWidgets import QTableWidgetItem
                    from PyQt5.QtGui import QColor, QBrush
                    it = QTableWidgetItem("🔥 조건 달성!")
                    it.setForeground(QBrush(QColor("#ff4444")))
                    self.snp_tbl.setItem(ri, 4, it)
                cmp_lbl = "이하" if sn["cmp_op"] == "<=" else "이상"
                self._log(
                    f"[스나이퍼 발동] {sn['sym']} {int(sn['strike'])}{sn['right']}  "
                    f"현재가={cur:.2f}  목표 {sn['target_price']:.2f} {cmp_lbl}")
                self.snp_status.setText(f"🔥 발동: {int(sn['strike'])}{sn['right']} @ {cur:.2f}")
                self.snp_status.setStyleSheet(
                    "color:#ff4444;font-size:11px;font-weight:bold;"
                    "border:1px solid #ff4444;border-radius:3px;padding:2px;")
                fired = self._sniper_fire(rid, sn)
                # placeOrder 성공 시에만 triggered=True
                if fired:
                    sn["triggered"] = True

        # 모두 triggered면 타이머 중지
        if all(s["triggered"] for s in self._snipers.values()):
            self._sniper_timer.stop()

    # ── 주문 전송 ─────────────────────────────────────────────
    def _sniper_fire(self, rid: int, sn: dict) -> bool:
        """
        [v6.6 ①] placeOrder 성공 시 True, 실패 시 False 반환.
        호출자(_sniper_check)에서 반환값으로 triggered=True 여부를 결정한다.
        예외 발생 시 triggered는 여전히 False → 다음 타이머 주기에 재시도 가능.
        """
        if not self.mw.connected:
            self._log("[스나이퍼] TWS 미연결 — 주문 전송 불가")
            return False
        try:
            from ibapi.order import Order as IbOrder
            contract = make_opt_contract(
                sn["sym"], sn["strike"], sn["right"], sn["expiry"])
            ibord = IbOrder()
            ibord.action        = sn["action"]
            ibord.orderType     = sn["order_type"]
            ibord.totalQuantity = sn["qty"]
            ibord.tif           = "DAY"
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            if sn["order_type"] == "LMT" and sn["order_price"] > 0:
                ibord.lmtPrice = sn["order_price"]
            oid = self.mw.ib.get_next_id()
            if oid is None:
                self._log("[스나이퍼] OrderID 없음 — triggered 복구, 재시도 가능")
                return False  # triggered=True 설정 안 함
            self.mw.ib.placeOrder(oid, contract, ibord)
            self._log(
                f"[스나이퍼 주문전송] oid={oid}  "
                f"{sn['action']} {sn['qty']}계약  "
                f"{sn['order_type']}  ${sn['order_price']:.2f}")
            ri = sn.get("row_idx")
            if ri is not None:
                from PyQt5.QtWidgets import QTableWidgetItem
                from PyQt5.QtGui import QColor, QBrush
                it = QTableWidgetItem(f"📤 전송 oid={oid}")
                it.setForeground(QBrush(QColor("#00e676")))
                self.snp_tbl.setItem(ri, 4, it)
            return True  # ✅ 성공
        except Exception as e:
            self._log(f"[스나이퍼] 주문 오류: {e} — triggered 복구, 재시도 가능")
            # UI에 오류 표시
            ri = sn.get("row_idx")
            if ri is not None:
                from PyQt5.QtWidgets import QTableWidgetItem
                from PyQt5.QtGui import QColor, QBrush
                it = QTableWidgetItem(f"❌ 오류: {e}")
                it.setForeground(QBrush(QColor("#ff4444")))
                self.snp_tbl.setItem(ri, 4, it)
            return False  # triggered=True 설정 안 함 → 재시도 가능

    # ── 행 클릭 → 개별 해제 ──────────────────────────────────
    def _sniper_row_click(self, row: int, col: int):
        from PyQt5.QtWidgets import QMessageBox
        target_rid = None
        for rid, sn in self._snipers.items():
            if sn.get("row_idx") == row:
                target_rid = rid; break
        if target_rid is None: return
        sn = self._snipers[target_rid]
        label = f"{int(sn['strike'])}{sn['right']}"
        ret = QMessageBox.question(
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

    # ── 전체 해제 ─────────────────────────────────────────────
    def _sniper_clear_all(self):
        from PyQt5.QtWidgets import QMessageBox
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

    # ── JSON 저장 ─────────────────────────────────────────────
    def _sniper_save(self):
        import json
        from pathlib import Path
        from datetime import datetime
        # [v6.6] 절대 경로 + 날짜 포함 파일명
        _SNIPER_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/sniper")
        date_str    = datetime.now().strftime("%Y%m%d")
        save_path   = _SNIPER_DIR / f"sniper_conditions_{date_str}.json"
        data = []
        for sn in self._snipers.values():
            data.append({
                "sym": sn["sym"], "strike": sn["strike"],
                "right": sn["right"], "expiry": sn["expiry"],
                "target_price": sn["target_price"], "cmp_op": sn["cmp_op"],
                "time_kst": sn["time_kst"], "time_margin": sn["time_margin"],
                "qty": sn["qty"], "action": sn["action"],
                "order_type": sn["order_type"], "order_price": sn["order_price"],
            })
        try:
            _SNIPER_DIR.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"[스나이퍼] {len(data)}개 저장 → {save_path}")
            self.snp_status.setText(f"💾 {len(data)}개 저장 완료")
            self.snp_status.setStyleSheet(
                "color:#00cfff;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
        except Exception as e:
            self._log(f"[스나이퍼] 저장 오류: {e}")

    # ── JSON 복원 ─────────────────────────────────────────────
    def _sniper_load(self):
        import json
        from pathlib import Path
        # [v6.6] 절대 경로에서 가장 최근 날짜 파일 자동 선택
        _SNIPER_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/sniper")
        candidates  = sorted(
            _SNIPER_DIR.glob("sniper_conditions_????????.json"),
            reverse=True)
        if not candidates:
            self._log("[스나이퍼] 복원할 파일 없음"); return
        save_path = candidates[0]
        try:
            data = json.loads(save_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._log(f"[스나이퍼] 복원 오류: {e}"); return
        for item in data:
            self.snp_strike.setText(str(int(item.get("strike", 0))))
            self.snp_right.setCurrentIndex(0 if item.get("right", "C") == "C" else 1)
            self.snp_expiry.setText(item.get("expiry", ""))
            self.snp_price.setText(str(item.get("target_price", "")))
            self.snp_cmp.setCurrentIndex(0 if item.get("cmp_op", "<=") == "<=" else 1)
            self.snp_time.setText(item.get("time_kst", ""))
            self.snp_margin.setValue(item.get("time_margin", 1))
            self.snp_action.setCurrentText(item.get("action", "BUY"))
            self.snp_otype.setCurrentText(item.get("order_type", "LMT"))
            self.snp_oprice.setText(str(item.get("order_price", "")) if item.get("order_price") else "")
            self.snp_qty.setValue(item.get("qty", 1))
            self._sniper_add()
        self._log(f"[스나이퍼] {len(data)}개 조건 복원 완료")
        if data:
            self.snp_status.setText(f"📂 {len(data)}개 복원됨")
            self.snp_status.setStyleSheet(
                "color:#00cfff;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")

# ═══════════════════════════════════════════════════════
# [v6.6] ERR 201 대응 헬퍼 — 긴급 옵션 매도 LMT 가격 계산
# ═══════════════════════════════════════════════════════
import math as _math


def get_emergency_sell_lmt_price(
    bid: float,
    sym: str = "",
    ticks_below: int = 2,
) -> float:
    """
    긴급 매도 시 MKT 대신 사용할 LMT 가격.
    Bid에서 ticks_below 틱 아래, 틱 단위로 정렬하여 반환.

    틱 사이즈: XSP=$0.01 / $3 미만=$0.05 / $3 이상=$0.10
    """
    if not bid or bid <= 0:
        return 0.05
    tick = 0.01 if sym.upper() == "XSP" else (0.10 if bid >= 3.0 else 0.05)
    raw  = max(bid - tick * ticks_below, tick)
    inv  = 1.0 / tick
    dec  = max(0, -int(_math.floor(_math.log10(tick)))) if tick < 1 else 0
    return round(_math.floor(raw * inv) / inv, dec)