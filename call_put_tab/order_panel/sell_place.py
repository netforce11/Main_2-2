"""
order_panel/sell_place.py — LMT SELL 공통 주문 전송 헬퍼
════════════════════════════════════════════════════════
포함:
  SellPlaceMixin
    _place_sell_lmt()  contract 생성 → placeOrder → 상태 라벨 갱신

[버그수정]
  ① error 핸들러 복원 누락:
    - 기존: placeOrder 이후 _catch_err 고착 → 재연결 트리거(ERR 1100) 등 무시
    - 수정: placeOrder 완료 2초 후 원본 핸들러로 복원
  ② conId 주입 (P3-⑤):
    - _pos_snapshot에 저장된 conId를 조회해 contract.conId에 주입
    - IBKR 내부 종목 재조회 생략 → 레이턴시 개선
"""

from PyQt5.QtCore import QTimer

from .helpers import _spx_tag


class SellPlaceMixin:
    """LMT SELL 공통 주문 전송 로직. SellActionsMixin에 mixin된다."""

    def _place_sell_lmt(self, side, strike_txt, sym, qty, price, lbl, msg):
        """공통 LMT SELL 주문 전송."""
        try:
            from ibapi.order import Order as IbOrder
            from call_put_tab.core import make_opt_contract
            expiry = getattr(self, '_ps_expiry', None)
            if not expiry:
                expiry, tag = self._get_expiry()
                if expiry is None:
                    if lbl: lbl.setText("❌ 만기일을 확인할 수 없습니다")
                    return
            else:
                tag = _spx_tag(sym, expiry)

            contract = make_opt_contract(sym, float(strike_txt), side, expiry, tag)

            # ── [버그수정 ②] conId 주입: _pos_snapshot 조회 ─────────────
            # 보유 포지션 청산 매도 경로이므로 스냅샷에 conId가 있을 가능성이 높음.
            # 찾지 못해도 기존 동작(IB 내부 재조회)으로 폴백되므로 안전.
            try:
                snapshot = getattr(self, '_pos_snapshot', {})
                strike_int = int(float(strike_txt))
                for key, info in snapshot.items():
                    if (isinstance(key, tuple) and len(key) == 4
                            and key[1] == side and int(key[2]) == strike_int):
                        con_id = info.get('con_id')
                        if con_id:
                            contract.conId = con_id
                            self._log(f"  conId 주입: {con_id} ({side} {strike_txt})")
                        break
            except Exception as _ce:
                self._log(f"  conId 조회 실패 (무시): {_ce}")

            ibord           = IbOrder()
            ibord.action    = "SELL"; ibord.orderType     = "LMT"
            ibord.totalQuantity = qty; ibord.lmtPrice     = price
            ibord.tif       = "DAY";  ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            oid = self.mw.ib.get_next_id()
            if oid is None:
                if lbl: lbl.setText("❌ 주문 ID 없음"); return

            # ── [버그수정 ①] error 핸들러: 교체 후 2초 뒤 원본 복원 ────
            # 기존 코드는 _catch_err 교체 후 복원 코드가 없어 글로벌 에러
            # 핸들러가 _catch_err로 영구 교체되는 버그가 있었음.
            _orig_err = getattr(self.mw.ib, 'error', None)
            def _catch_err(reqId, errorCode, errorString, *a):
                self._log(
                    f"‼ IB ERROR  reqId={reqId}  code={errorCode}  msg={errorString}")
                if _orig_err:
                    try: _orig_err(reqId, errorCode, errorString, *a)
                    except Exception: pass
            self.mw.ib.error = _catch_err
            # placeOrder 완료 후 2초 뒤 원본 핸들러 복원
            QTimer.singleShot(2000,
                lambda: setattr(self.mw.ib, 'error', _orig_err)
                if getattr(self.mw.ib, 'error', None) is _catch_err else None)

            self.mw.ib.placeOrder(oid, contract, ibord)
            result_msg = f"✅ 빠른매도: {msg}  (OID={oid})"
            if lbl:
                lbl.setStyleSheet(
                    "color:#ff6666;font-size:11px;"
                    "border:1px solid #333;border-radius:3px;padding:2px;")
                lbl.setText(result_msg)
            self._log(f"📤 {result_msg}")
            QTimer.singleShot(1500, self._fetch_open_orders)
        except Exception as e:
            if lbl: lbl.setText(f"❌ 오류: {e}")
            self._log(f"❌ 빠른매도 오류: {e}")