"""
order_panel/emergency.py — 긴급매도·전체 취소 로직
════════════════════════════════════════════════════
포함 메서드 (OrderPanelMixin에 mixin):
  _emergency_sell_all()        잔고 전체 LMT 매도 + 미체결 전부 취소
  _emergency_sell_positions()  포지션 전체 LMT 매도 (v7.1 L-A)
  _emergency_cancel_orders()   미체결 전체 주문 취소
  _on_global_cancel()          reqGlobalCancel (취소 탭)
"""

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox


class EmergencyMixin:
    """긴급매도·전체취소 로직. OrderPanelMixin에 mixin된다."""

    def _emergency_sell_all(self):
        """잔고 전체 LMT 매도 + 미체결 매수 전부 취소."""
        self._emergency_sell_positions()
        self._emergency_cancel_orders()

    def _emergency_cancel_orders(self):
        """미체결 전체 주문(BUY + SELL) 취소."""
        if not self.mw.connected:
            self._log("🚨 미체결취소: 미연결"); return
        orders = getattr(self, '_open_orders_buf', [])
        if not orders:
            self._log("🚨 미체결취소: 미체결 주문 없음 (먼저 [미체결 조회] 클릭)"); return
        for o in orders:
            try:
                self.mw.ib.cancelOrder(o['oid'])
                self._log(f"🚨 취소 전송: OID={o['oid']} {o['action']} {o['symbol']}")
            except Exception as e:
                self._log(f"❌ 취소 오류 OID={o['oid']}: {e}")

    def _on_global_cancel(self):
        """취소 탭: 전체 미체결 주문 강제 취소 (reqGlobalCancel)."""
        ret = QMessageBox.warning(
            self, "⚠ 전체 취소 확인",
            "현재 API 세션의 모든 미체결 주문을 즉시 취소합니다.\n"
            "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes: return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        try:
            self.mw.ib.reqGlobalCancel()
            if hasattr(self, 'lbl_cancel_status'):
                self.lbl_cancel_status.setText(
                    "✅ reqGlobalCancel 전송 완료 — 전체 주문 취소 요청됨")
            self._log("🚨 reqGlobalCancel 전송 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"reqGlobalCancel 실패: {e}")
            self._log(f"❌ reqGlobalCancel 오류: {e}")

    def _emergency_sell_positions(self):
        """
        [v7.1 L-A] IBKR 포지션 전체를 LMT(지정가)로 즉시 매도.

        price_tick_sig 구독 방식으로 ib.tickPrice 직접 교체 제거.
        가격 결정 우선순위: Bid → Last → avg_cost → 스킵
        """
        if not self.mw.connected:
            self._log("🚨 긴급매도: 미연결"); return

        ib = self.mw.ib
        self._emrg_bid_cache    = {}
        self._emrg_last_cache   = {}
        self._emrg_reqid_to_sym = {}
        _pos_buf = []

        try:
            from call_put_tab.bridge_price_tick import subscribe as _sub
            from call_put_tab.bridge_price_tick import unsubscribe as _unsub
            _use_router = True
        except ImportError:
            _use_router = False

        def _emrg_tick(req_id: int, tick_type: int, price: float) -> None:
            if price <= 0: return
            sym = self._emrg_reqid_to_sym.get(req_id)
            if not sym: return
            if tick_type == 1:   self._emrg_bid_cache[sym]  = price
            elif tick_type == 4: self._emrg_last_cache[sym] = price

        if _use_router:
            _sub(_emrg_tick)

        def _on_pos(account, contract, pos, avg_cost):
            if getattr(contract, 'secType', '') == 'OPT' and int(pos) > 0:
                _pos_buf.append((contract, int(pos), float(avg_cost or 0)))

        def _on_pos_end():
            if not _pos_buf:
                self._log("🚨 긴급매도: 보유 포지션 없음")
                _restore(); return
            _base_rid = 8850
            for i, (contract, qty, avg_cost) in enumerate(_pos_buf):
                sym = (getattr(contract, 'localSymbol', '')
                       or getattr(contract, 'symbol', '') or f"OPT_{i}")
                rid = _base_rid + i
                self._emrg_reqid_to_sym[rid] = sym
                try:
                    ib.reqMktData(rid, contract, "", True, False, [])
                except Exception:
                    pass
            QTimer.singleShot(500, lambda: _fire_orders(_pos_buf))

        def _fire_orders(pos_buf):
            from ibapi.order import Order as IBOrder
            try:
                from order_logic import get_emergency_sell_lmt_price
            except ImportError:
                import math as _m
                def get_emergency_sell_lmt_price(bid, sym="", ticks_below=2):
                    if not bid or bid <= 0: return 0.05
                    tick = 0.01 if sym.upper() == "XSP" else (0.10 if bid >= 3.0 else 0.05)
                    raw  = max(bid - tick * ticks_below, tick)
                    inv  = 1.0 / tick
                    dec  = max(0, -int(_m.floor(_m.log10(tick)))) if tick < 1 else 0
                    return round(_m.floor(raw * inv) / inv, dec)

            sent, skipped = 0, 0
            for i, (contract, qty, avg_cost) in enumerate(pos_buf):
                sym  = (getattr(contract, 'localSymbol', '')
                        or getattr(contract, 'symbol', '') or f"OPT_{i}")
                bid  = self._emrg_bid_cache.get(sym)
                last = self._emrg_last_cache.get(sym)
                ref  = (bid  if (bid  and bid  > 0) else
                        last if (last and last > 0) else avg_cost)
                if not ref or ref <= 0:
                    self._log(f"⚠ 긴급매도 스킵: {sym} — 가격 미수신")
                    skipped += 1; continue
                price_src = ("Bid"      if bid  and bid  > 0 else
                             "Last"     if last and last > 0 else "avg_cost")
                lmt_price = get_emergency_sell_lmt_price(ref, sym=sym, ticks_below=2)
                order = IBOrder()
                order.action        = "SELL"; order.orderType = "LMT"
                order.lmtPrice      = lmt_price; order.totalQuantity = qty
                order.tif           = "DAY";  order.eTradeOnly = False
                order.firmQuoteOnly = False
                try:
                    oid = (ib.get_next_id() if hasattr(ib, 'get_next_id')
                           else getattr(ib, 'nextOrderId', 0))
                    ib.placeOrder(oid, contract, order)
                    self._log(
                        f"🚨 긴급매도 전송: {sym}  {qty}계약  "
                        f"LMT ${lmt_price:.2f}  ({price_src}={ref:.2f} 기준 2틱↓)")
                    sent += 1
                except Exception as e:
                    self._log(f"❌ 긴급매도 오류 {sym}: {e}"); skipped += 1
                try:
                    ib.cancelMktData(8850 + i)
                except Exception:
                    pass
            self._log(f"🚨 긴급매도 완료: {sent}건 전송 / {skipped}건 스킵")
            _restore()

        def _restore():
            if _use_router:
                try:
                    _unsub(_emrg_tick)
                except Exception:
                    pass
            ib.position    = ib._orig_pos
            ib.positionEnd = ib._orig_posEnd

        ib._orig_pos    = getattr(ib, 'position',    lambda *a: None)
        ib._orig_posEnd = getattr(ib, 'positionEnd', lambda: None)
        ib.position    = _on_pos
        ib.positionEnd = _on_pos_end
        try:
            ib.reqPositions()
        except Exception as e:
            self._log(f"❌ 긴급매도 포지션조회 오류: {e}"); _restore()
        QTimer.singleShot(5000, _restore)
