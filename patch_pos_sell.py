"""
patch_pos_sell.py — 잔고 청산 매도 버그 패치
══════════════════════════════════════════════════════════════
수정 대상:
  1. call_put_tab/order_panel_util.py
       · _pos_sell_execute() : 화면 만기 → 보유 포지션 실제 만기 사용
       · _build_inline_position_panel() 호출 누락은 별도 수정 (하단 안내)

  2. call_put_tab/order_panel/tab_new_order.py
       · build_new_order_tab() 끝에 잔고 인라인 패널 addWidget 추가

사용법:
  python patch_pos_sell.py
  → 백업: *.bak 생성 후 원본 파일 수정
══════════════════════════════════════════════════════════════
"""
import shutil
import sys
from pathlib import Path

# ── 프로젝트 루트 ────────────────────────────────────────────
ROOT = Path("/home/netforce/trading_terminal/Main2_1")

# ══════════════════════════════════════════════════════════════
# 패치 1: order_panel_util.py — _pos_sell_execute() 교체
# ══════════════════════════════════════════════════════════════
UTIL_PATH = ROOT / "call_put_tab" / "order_panel_util.py"

OLD_POS_SELL = '''\
    def _pos_sell_execute(self):
        side   = getattr(self, '_ps_side',   None)
        strike = getattr(self, '_ps_strike', None)
        if not side or not strike:
            self._log("⚠ 매도 대상 없음. 잔고 테이블을 다시 클릭하세요."); return
        price_txt = self._ps_price.text().strip()
        self._qord_fill(side, strike,
                        float(price_txt) if price_txt else None,
                        source="← 잔고 청산")
        self.qord_qty.setValue(self._ps_qty.value())
        self._pos_sell_panel.setVisible(False)
        self._qord_place("SELL")'''

NEW_POS_SELL = '''\
    def _pos_sell_execute(self):
        side   = getattr(self, '_ps_side',   None)
        strike = getattr(self, '_ps_strike', None)
        if not side or not strike:
            self._log("⚠ 매도 대상 없음. 잔고 테이블을 다시 클릭하세요.")
            return

        # ── 만기/심볼: 보유 포지션 기준 (화면 combo_exp 무관) ──
        expiry = getattr(self, '_ps_expiry', None)
        sym    = getattr(self, '_ps_sym',    None)

        # fallback: 저장값 없으면 화면값 사용
        if not expiry:
            expiry, _ = self._get_expiry()
        if not expiry:
            self._log("⚠ 만기 정보 없음 — 잔고 테이블을 다시 클릭하세요.")
            return
        if not sym:
            sym = self.edit_sym.text().strip().upper()

        qty       = self._ps_qty.value()
        price_txt = self._ps_price.text().strip()
        is_lmt    = bool(price_txt)

        try:
            price = float(price_txt) if is_lmt else 0.0
        except ValueError:
            self._log("⚠ 가격 형식 오류 — 숫자를 입력하세요.")
            return

        # ── 주문 확인 다이얼로그 ──────────────────────────────
        label      = "CALL" if side == "C" else "PUT"
        price_disp = f"${price:.2f}" if is_lmt else "시장가"
        msg = (f"매도 {'LMT' if is_lmt else 'MKT'}  "
               f"{sym} {label} {strike}  {qty}계약  {price_disp}")

        from PyQt5.QtWidgets import QMessageBox
        dlg = QMessageBox(self)
        dlg.setWindowTitle("잔고 청산 확인")
        dlg.setText(f"⚠ 보유 포지션을 청산합니다.\n\n{msg}\n\n계속하시겠습니까?")
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dlg.setDefaultButton(QMessageBox.Yes)
        yes_btn = dlg.button(QMessageBox.Yes)
        if yes_btn:
            yes_btn.setStyleSheet(
                "QPushButton{background:#6b1a1a;color:#ff6666;"
                "font-weight:bold;padding:4px 16px;border-radius:4px;"
                "border:1px solid #ff6666;}"
                "QPushButton:hover{background:#8b2a2a;}")
        if dlg.exec_() != QMessageBox.Yes:
            return

        if not self.mw.connected:
            self._log("⚠ TWS 미연결 — 먼저 연결하세요.")
            return

        try:
            from ibapi.order import Order as IbOrder
            from core_contract import make_opt_contract
            from call_put_tab.core_expiry_utils import _is_monthly_expiry

            # Monthly 만기(세 번째 금요일)는 반드시 SPX 티커로 조회
            if _is_monthly_expiry(expiry):
                sym = "SPX"

            contract = make_opt_contract(sym, float(strike), side, expiry, "")

            ibord = IbOrder()
            ibord.action        = "SELL"
            ibord.orderType     = "LMT" if is_lmt else "MKT"
            ibord.totalQuantity = qty
            ibord.tif           = "DAY"
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False
            if is_lmt:
                ibord.lmtPrice = price

            oid = self.mw.ib.get_next_id()
            if oid is None:
                self._log("⚠ 주문 ID 획득 실패")
                return

            self.mw.ib.placeOrder(oid, contract, ibord)
            self._pos_sell_panel.setVisible(False)

            col = "#ff6666"
            self.lbl_qord_status.setStyleSheet(
                f"color:{col};font-size:11px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            self.lbl_qord_status.setText(f"전송(청산): {msg}")
            self._log(f"📤 잔고 청산 매도: {msg}  (OID={oid})")

        except Exception as e:
            self._log(f"❌ 잔고 청산 주문 오류: {e}")'''


# ══════════════════════════════════════════════════════════════
# 패치 2: tab_new_order.py — 잔고 인라인 패널 addWidget 추가
# ══════════════════════════════════════════════════════════════
TAB_NEW_PATH = ROOT / "call_put_tab" / "order_panel" / "tab_new_order.py"

OLD_NEW_ORDER_END = '''\
    # ── 버튼 영역 (별도 모듈) ────────────────────────────────
    build_new_order_buttons(m, root_v)
    return new_w'''

NEW_NEW_ORDER_END = '''\
    # ── 버튼 영역 (별도 모듈) ────────────────────────────────
    build_new_order_buttons(m, root_v)
    # ── 잔고 인라인 패널 ─────────────────────────────────────
    root_v.addWidget(m._build_inline_position_panel())
    return new_w'''


# ══════════════════════════════════════════════════════════════
# 공통 패치 함수
# ══════════════════════════════════════════════════════════════
def apply_patch(path: Path, old: str, new: str, label: str) -> bool:
    if not path.exists():
        print(f"[ERROR] 파일 없음: {path}")
        return False

    src = path.read_text(encoding="utf-8")

    if old not in src:
        print(f"[SKIP]  {label} — 대상 코드 없음 (이미 패치됐거나 버전 불일치)")
        return False

    # 백업
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    print(f"[BAK]   {bak.name}")

    patched = src.replace(old, new, 1)
    path.write_text(patched, encoding="utf-8")
    print(f"[OK]    {label} 패치 완료 → {path.relative_to(ROOT)}")
    return True


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  잔고 청산 매도 버그 패치")
    print("=" * 60)

    ok1 = apply_patch(
        UTIL_PATH,
        OLD_POS_SELL,
        NEW_POS_SELL,
        "order_panel_util.py :: _pos_sell_execute()",
    )

    ok2 = apply_patch(
        TAB_NEW_PATH,
        OLD_NEW_ORDER_END,
        NEW_NEW_ORDER_END,
        "tab_new_order.py :: 잔고 인라인 패널 추가",
    )

    print("=" * 60)
    if ok1 or ok2:
        print("✅ 패치 완료. 앱을 재시작하세요.")
    else:
        print("⚠  적용된 패치 없음. 위 메시지를 확인하세요.")
    print("=" * 60)
