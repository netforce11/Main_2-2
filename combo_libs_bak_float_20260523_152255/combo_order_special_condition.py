"""
combo_order_special_condition.py — 특수 조건 감시 + 텔레그램 알림  v1.1
────────────────────────────────────────────────────────────────────────
변경 (v1.1):
  [FIX-W1] watch() 파라미터에 bag_contract, qty 추가
    · 기존: Chaser의 _chaser_bag_contract / _chaser_qty 에 의존
    · 수정: 선주문 접수 시점(combo_order_bag.py)에서 직접 전달받아 저장
    · 이유: Chaser 기본값이 OFF라 _chaser_bag_contract=None 상태에서
            정정주문이 조용히 실패하는 버그 수정

  [FIX-W2] _modify 를 _modify_direct() 로 교체
    · 기존: combo_order_chaser._modify_order(ref, oid, price) 경유
            → Chaser 상태값(bag/action/qty)에 의존 → OFF 시 정정 실패
    · 수정: watch()에서 저장한 bag_contract / action / qty 로
            ib.placeOrder(oid, bag, order) 직접 호출

호출 위치:
  combo_order_bag.py     placeOrder 성공 후
    SpecialFillWatcher.get().watch(
        self, oid, lmt_price, action, legs, strat,
        bag_contract=bag,   # ← v1.1 추가
        qty=qty             # ← v1.1 추가
    )
  combo_order_callbacks.py  Filled 블록
    notify_filled(pending, avg);  SpecialFillWatcher.get().unwatch(oid)
  combo_order_callbacks.py  is_close 블록
    notify_closed(pos);           SpecialFillWatcher.get().unwatch(oid)
  combo_order_callbacks.py  net price 갱신 시
    SpecialFillWatcher.get().on_net_price_update(oid, net_price)
────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import threading
from typing import Dict, Optional


# ── 헬퍼 ────────────────────────────────────────────────────────────

def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[SpecialCond] TG 실패: {e}")


def _tick(price: float) -> float:
    return 0.10 if price >= 3.0 else 0.05


def _modify_direct(w: dict, new_price: float) -> None:
    """
    [FIX-W2] Chaser 경유 없이 watch() 에 저장된 값으로 직접 정정주문 전송.
    IBKR 정정 = 동일 OID 로 placeOrder 재호출.
    """
    ref          = w["ref"]
    oid          = w["oid"]
    bag_contract = w.get("bag_contract")
    action       = w.get("action", "SELL")
    qty          = w.get("qty", 1)

    if bag_contract is None:
        print(f"[SpecialCond] ❌ 정정 취소: bag_contract 없음 OID={oid}")
        return

    try:
        from ibapi.order import Order as IbOrder
        ib = ref.mw.ib

        ibord               = IbOrder()
        ibord.action        = action
        ibord.orderType     = "LMT"
        ibord.totalQuantity = qty
        ibord.lmtPrice      = new_price
        ibord.tif           = "DAY"
        ibord.eTradeOnly    = False
        ibord.firmQuoteOnly = False
        ibord.transmit      = True

        ib.placeOrder(oid, bag_contract, ibord)
        print(f"[SpecialCond] ✅ 정정 주문 전송: OID={oid}"
              f"  lmtPrice=${new_price:.2f}  qty={qty}  action={action}")
    except Exception as e:
        print(f"[SpecialCond] ❌ 정정 실패 OID={oid}: {e}")


# ── 기능 1: 알림 ─────────────────────────────────────────────────────

def notify_filled(pos: dict, avg_price: float) -> None:
    """신규 체결 텔레그램 알림."""
    legs   = pos.get("legs", [])
    expiry = legs[0].get("expiry", "") if legs else ""
    side   = "매도(SELL)" if pos.get("side") == "SELL" else "매수(BUY)"
    _tg(
        f"✅ <b>체결 완료</b>\n"
        f"전략: {pos.get('strategy','')}\n"
        f"방향: {side}  체결가: <b>${avg_price:.2f}</b>\n"
        f"수량: {pos.get('qty',1)}계약  만기: {expiry}\n"
        f"OID: {pos.get('oid','')}"
    )


def notify_closed(pos: dict) -> None:
    """청산 체결 텔레그램 알림."""
    entry   = float(pos.get("entry", 0))
    current = float(pos.get("current", entry))
    qty     = pos.get("qty", 1)
    pnl     = round((current - entry) * qty * 100, 2)
    sign    = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    _tg(
        f"🔴 <b>청산 완료</b>\n"
        f"전략: {pos.get('strategy','')}\n"
        f"진입가: ${entry:.2f} → 청산가: ${current:.2f}\n"
        f"손익: <b>{sign}</b>  수량: {qty}계약\n"
        f"OID: {pos.get('oid','')}"
    )


# ── 기능 2: 선주문 감시 ───────────────────────────────────────────────

class SpecialFillWatcher:
    """싱글톤. 선주문 net price 감시 → 미체결 시 자동 정정 + TG."""

    _inst: Optional["SpecialFillWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                o._watches: Dict[int, dict] = {}
                cls._inst = o
        return cls._inst

    @classmethod
    def get(cls) -> "SpecialFillWatcher":
        return cls()

    def watch(self, ref, oid: int, target: float,
              action: str, legs: list, strat: str = "",
              bag_contract=None,   # [FIX-W1] BAG 컨트랙트 직접 전달
              qty: int = 1         # [FIX-W1] 수량 직접 전달
              ) -> None:
        """
        선주문 등록 직후 호출.

        [FIX-W1] bag_contract, qty 를 직접 받아 저장.
        combo_order_bag.py placeOrder 성공 후:
            SpecialFillWatcher.get().watch(
                self, oid, lmt_price, action, legs, strat,
                bag_contract=bag, qty=qty
            )
        """
        if bag_contract is None:
            print(f"[SpecialCond] ⚠️ watch() 호출 시 bag_contract=None — "
                  f"정정주문이 실패할 수 있습니다. OID={oid}")

        with self._mu:
            self._watches[oid] = dict(
                ref=ref, oid=oid, target=target, action=action,
                legs=legs, strat=strat, step=0,
                triggered=False, timer=None,
                bag_contract=bag_contract,  # [FIX-W1]
                qty=qty,                    # [FIX-W1]
            )
        print(f"[SpecialCond] 감시 등록 OID={oid} 목표=${target:.2f}"
              f"  action={action}  qty={qty}"
              f"  bag={'있음' if bag_contract else '없음'}")

    def unwatch(self, oid: int) -> None:
        """체결/취소/청산 시 반드시 호출."""
        with self._mu:
            w = self._watches.pop(oid, None)
        if w:
            t = w.get("timer")
            if t:
                t.cancel()
            print(f"[SpecialCond] 감시 해제 OID={oid}")

    def on_net_price_update(self, oid: int, net_price: float) -> None:
        """
        실시간 net price 갱신 시 호출.
        combo_order_callbacks.py 의 _on_tick 에서 자동 호출.

        매도 선주문: 프리미엄이 올라 target 이상이 되면 체결 가능
        → net_price >= target 조건 유지 (정상)
        """
        with self._mu:
            w = self._watches.get(oid)
        if not w or w["step"] >= 3 or w["triggered"]:
            return
        if net_price >= w["target"]:
            w["triggered"] = True
            print(f"[SpecialCond] OID={oid} 목표가 도달 ${net_price:.2f} → 10초 대기")
            self._arm(oid, 10)

    # ── 내부 ────────────────────────────────────────────────────────

    def _arm(self, oid: int, delay: int) -> None:
        with self._mu:
            w = self._watches.get(oid)
            if not w:
                return
            if w.get("timer"):
                w["timer"].cancel()
            t = threading.Timer(delay, self._fire, args=(oid,))
            t.daemon = True
            t.start()
            w["timer"] = t

    def _fire(self, oid: int) -> None:
        with self._mu:
            w = self._watches.get(oid)
        if not w:
            return  # 이미 체결/해제됨

        step   = w["step"]
        target = w["target"]
        strat  = w["strat"]
        tk     = _tick(target)

        if step == 0:                          # 1차 정정 −3틱
            p = max(round(target - tk * 3, 2), tk)
            w["step"] = 1
            _modify_direct(w, p)              # [FIX-W2]
            _tg(f"⚠️ <b>미체결 1차 정정</b>\n전략: {strat}\n"
                f"목표가 ${target:.2f} 도달 후 10초 미체결\n"
                f"→ <b>${p:.2f}</b> 으로 정정 (−3틱)\nOID: {oid}")
            self._arm(oid, 10)

        elif step == 1:                        # 2차 정정 −2틱 추가
            p = max(round(target - tk * 5, 2), tk)
            w["step"] = 2
            _modify_direct(w, p)              # [FIX-W2]
            _tg(f"⚠️ <b>미체결 2차 정정</b>\n전략: {strat}\n"
                f"→ <b>${p:.2f}</b> 으로 추가 정정 (−2틱)\nOID: {oid}")
            self._arm(oid, 10)

        elif step == 2:                        # 포기 — 수동 대응
            w["step"] = 3
            _tg(f"🚨 <b>수동 대응 필요</b>\n전략: {strat}\n"
                f"2차 정정 후에도 10초 이상 미체결\n"
                f"직접 확인 후 정정 또는 취소하세요.\nOID: {oid}")
