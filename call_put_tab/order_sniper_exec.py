"""
order_sniper_exec.py — 스나이퍼 틱 수신·조건 평가·주문 발동 로직
════════════════════════════════════════════════════════
포함 내용:
  - OrderSniperExecMixin
      _sniper_tick()    틱 수신 (Last/Close/Bid/Ask 확장)
      _sniper_check()   2초 타이머: 조건 평가 → 자동 발주
      _sniper_fire()    placeOrder 전송 (성공 시 True)

[v6.6 수정]
  ① triggered=True를 placeOrder 성공 후로 이동 (중복 발주 버그 수정)
  틱 타입 확장: 지연 시세(MDT=3) 환경 대응
════════════════════════════════════════════════════════
"""

from core import make_opt_contract


class OrderSniperExecMixin:
    """스나이퍼 틱 수신·조건 평가·주문 발동 로직."""

    def _sniper_tick(self, rid: int, tt: int, price: float):
        """
        [v6.6] 틱 타입 범위 확대 — 지연 시세(MDT=3) 환경 대응.

        가격 결정 우선순위:
          Last(4) > DelayedLast(68) > Close(9,75,14) > Mid(Bid+Ask/2)
        """
        if rid not in self._snipers or price <= 0:
            return

        _LAST_TYPES  = (4, 68)
        _CLOSE_TYPES = (9, 75, 14)
        _QUOTE_TYPES = (1, 2)

        if tt not in _LAST_TYPES + _CLOSE_TYPES + _QUOTE_TYPES:
            return

        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor, QBrush
        sn = self._snipers[rid]

        if tt in _QUOTE_TYPES:
            # Bid/Ask 캐시에 모아뒀다가 둘 다 있으면 Mid 계산
            cache     = sn.setdefault("_quote_cache", {})
            cache[tt] = price
            bid, ask  = cache.get(1), cache.get(2)
            if bid and ask and bid > 0 and ask > 0:
                display_price = (bid + ask) / 2.0
            else:
                return  # 한 쪽만 있으면 대기
        else:
            # Last / Close 계열: 더 신뢰도 높은 타입이 오면 덮어씀
            prev    = sn.get("cur_price")
            prev_tt = sn.get("_last_tt", 99)
            _prio   = {4: 0, 68: 1, 9: 2, 75: 3, 14: 4}
            if prev is not None and _prio.get(tt, 9) > _prio.get(prev_tt, 9):
                return
            sn["_last_tt"] = tt
            display_price  = price

        sn["cur_price"] = display_price
        ri = sn.get("row_idx")
        if ri is not None:
            it = QTableWidgetItem(f"{display_price:.2f}")
            it.setForeground(QBrush(QColor("#00cfff")))
            self.snp_tbl.setItem(ri, 2, it)

    def _sniper_check(self):
        """2초 타이머 콜백: 조건 평가 → 자동 발주."""
        from datetime import datetime, timedelta

        for rid, sn in list(self._snipers.items()):
            if sn["triggered"]: continue
            cur = sn.get("cur_price")

            # 1) 시간 조건
            time_ok = True
            if sn["time_kst"]:
                try:
                    h, m    = map(int, sn["time_kst"].split(":"))
                    margin  = sn["time_margin"]
                    now_kst = datetime.utcnow() + timedelta(hours=9)
                    if margin == 0:
                        time_ok = (now_kst.hour == h and now_kst.minute == m)
                    else:
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
                self.snp_status.setText(
                    f"🔥 발동: {int(sn['strike'])}{sn['right']} @ {cur:.2f}")
                self.snp_status.setStyleSheet(
                    "color:#ff4444;font-size:11px;font-weight:bold;"
                    "border:1px solid #ff4444;border-radius:3px;padding:2px;")
                # [v6.6 ①] triggered=True는 placeOrder 성공 후 설정
                fired = self._sniper_fire(rid, sn)
                if fired:
                    sn["triggered"] = True

        if all(s["triggered"] for s in self._snipers.values()):
            self._sniper_timer.stop()

    def _sniper_fire(self, rid: int, sn: dict) -> bool:
        """
        [v6.6 ①] placeOrder 성공 시 True, 실패 시 False 반환.
        호출자(_sniper_check)에서 반환값으로 triggered=True 여부를 결정한다.
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
                return False
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
            return True
        except Exception as e:
            self._log(f"[스나이퍼] 주문 오류: {e} — triggered 복구, 재시도 가능")
            ri = sn.get("row_idx")
            if ri is not None:
                from PyQt5.QtWidgets import QTableWidgetItem
                from PyQt5.QtGui import QColor, QBrush
                it = QTableWidgetItem(f"❌ 오류: {e}")
                it.setForeground(QBrush(QColor("#ff4444")))
                self.snp_tbl.setItem(ri, 4, it)
            return False
