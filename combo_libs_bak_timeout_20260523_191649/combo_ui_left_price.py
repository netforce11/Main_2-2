"""
combo_ui_left_price.py — 현재가 조회 · tick 수신 · 거리% 갱신
combo_ui_left.py 에서 분리. v3.1
"""

from PyQt5.QtCore import QTimer


def _req_sym_price(self):
    """종목 입력 → 현재가 조회."""
    sym = self.edit_sym_combo.text().strip().upper()
    if not sym:
        return
    cp = self.mw.tab_callput

    # Case 1: 탭1과 심볼 동일 → 캐시 즉시 사용
    if cp and cp.und_price and cp.edit_sym.text().strip().upper() == sym:
        price = cp.und_price
        self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
        if hasattr(self, 'edit_stock_price'):
            self.edit_stock_price.setText(f"{price:.2f}")
        self._und_price = price
        self._log(f"현재가 수신 (콜-풋탭): {sym} = {price:,.2f}")
        return

    # Case 2: 심볼 다름 → 직접 reqMktData 구독
    ib = getattr(self.mw, 'ib', None)
    if not ib or not getattr(self.mw, 'connected', False):
        self._log("❌ TWS 미연결 — 먼저 연결하세요.")
        return

    REQ_COMBO_UND = 8500
    prev_sym = getattr(self, '_combo_und_sym', None)
    if prev_sym and prev_sym != sym:
        try:
            ib.cancelMktData(REQ_COMBO_UND)
        except Exception:
            pass
        from core import router
        router.unregister_price(self._on_combo_und_tick)
        self._log(f"🔌 이전 구독 해지: {prev_sym}")

    self._combo_und_sym = sym
    self.lbl_sym_price.setText("현재가: 조회 중…")
    self._log(f"🔍 {sym} 현재가 직접 구독 중... (REQ_ID={REQ_COMBO_UND})")

    from core import router
    router.register_price(REQ_COMBO_UND, REQ_COMBO_UND, self._on_combo_und_tick)
    try:
        from core_contract import make_und_contract
        ib.reqMktData(REQ_COMBO_UND, make_und_contract(sym), "", False, False, [])
    except Exception as e:
        self._log(f"❌ reqMktData 오류: {e}")


def _on_combo_und_tick(self, rid, tt, price):
    """콤보탭 전용 기초자산 tick 수신 (백그라운드 스레드 → 메인 스레드 위임)."""
    if tt not in (4, 68, 75) or price <= 0:
        return
    self._und_price = price
    QTimer.singleShot(0, lambda p=price: _apply_und_price_ui(self, p))


def _apply_und_price_ui(self, price: float):
    """메인 스레드에서 UI 위젯 갱신."""
    try:
        self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
        if hasattr(self, 'edit_stock_price') and not self.edit_stock_price.text().strip():
            self.edit_stock_price.setText(f"{price:.2f}")
        _refresh_dist_col(self, price)
    except RuntimeError:
        pass


def _refresh_dist_col(self, und_price: float):
    """CALL·PUT 체인 테이블 거리% 컬럼(col 3) 일괄 재계산."""
    from combo_ui_left_chain import _make_dist_item
    for tbl, strikes, side in [
        (getattr(self, 'tbl_chain_call', None), getattr(self, '_call_strikes', []), "C"),
        (getattr(self, 'tbl_chain_put',  None), getattr(self, '_put_strikes',  []), "P"),
    ]:
        if tbl is None:
            continue
        for r, st in enumerate(strikes):
            if r >= tbl.rowCount():
                break
            tbl.setItem(r, 3, _make_dist_item(st, und_price, side))
