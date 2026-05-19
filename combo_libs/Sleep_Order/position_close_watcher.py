"""
position_close_watcher.py — 포지션 청산 예약 감시 v3.0
════════════════════════════════════════════════════════════════
동작:
  From ~ To KST 시간 창 안에서 1초마다 폴링
  현재가(current) ≤ 설정가 - 2틱  →  사정권 도달
  즉시 설정가로 선매도 주문 발사
  미체결 → -1틱씩 정정 최대 N회
  초과 → 시장가 전환

자정 넘기는 경우 처리:
  From=23:00, To=01:30 이면
  datetime 기반으로 날짜 넘김 정확히 계산
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, time as dtime
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo   # type: ignore
    except ImportError:
        ZoneInfo = None                           # type: ignore

_KST     = ZoneInfo("Asia/Seoul") if ZoneInfo else None
_N_SLOTS = 3


# ── 틱 크기 ────────────────────────────────────────────────────
# XSP: $0.01 고정
# SPX/SPXW: $3.00 이상 $0.10, 미만 $0.05
_XSP_SYMBOLS = {"XSP", "XSPC", "XSPP"}

def _tick_size(price: float, symbol: str = "") -> float:
    if symbol.upper() in _XSP_SYMBOLS:
        return 0.01
    return 0.10 if price >= 3.00 else 0.05


# ── 사정권 판단: current ≤ 설정가 - 2틱 ──────────────────────
def _in_range(current: float, target: float, symbol: str = "") -> bool:
    tick      = _tick_size(target, symbol)
    threshold = round(target - 2 * tick, 2)
    return current <= threshold


# ── 자정 넘기는 시간 범위 판단 ────────────────────────────────
def _in_time_window(now_dt: datetime, from_str: str, to_str: str) -> bool:
    """
    now_dt: KST datetime (tzinfo 포함 or naive)
    from_str, to_str: "HH:MM"

    자정을 넘기는 경우(예: 23:00 ~ 01:30) 도 정확히 처리.
    """
    fh, fm = map(int, from_str.split(":"))
    th, tm = map(int, to_str.split(":"))

    # 오늘 날짜 기준 from/to datetime 구성
    today   = now_dt.date()
    from_dt = datetime(today.year, today.month, today.day, fh, fm,
                       tzinfo=now_dt.tzinfo)
    to_dt   = datetime(today.year, today.month, today.day, th, tm,
                       tzinfo=now_dt.tzinfo)

    # to < from 이면 자정을 넘기는 범위 → to 를 +1일로
    if to_dt <= from_dt:
        to_dt += timedelta(days=1)

    return from_dt <= now_dt <= to_dt


# ── 텔레그램 ───────────────────────────────────────────────────
def _tg(msg: str) -> None:
    def _run():
        try:
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get()._send_raw(msg)
        except Exception as e:
            print(f"[ClosWatcher] TG 실패: {e}")
    threading.Thread(target=_run, daemon=True).start()


# ══════════════════════════════════════════════════════════════
# 슬롯 상태
# ══════════════════════════════════════════════════════════════
class _SlotState:
    IDLE    = "idle"
    WAITING = "waiting"   # 시간 창 대기 / 가격 감시 중
    ORDERED = "ordered"   # 주문 발사 후 체결 대기
    DONE    = "done"

    def __init__(self, idx: int):
        self.idx              = idx
        self.state            = self.IDLE
        self.pos: dict | None = None
        self.ref              = None
        self.order_price      = 0.0   # 발사된 주문가 (설정가)
        self.correction_count = 0
        self.active_oid: "int | None"  = None  # 발사된 주문 OID
        self.market_sent: bool          = False # [FIX-LOOP] 시장가 발사 여부 플래그
        self._last_order_sent_at: float = 0.0   # [FIX-4] 마지막 주문 발사 시각
        # [FIX-SLOT-OBJ] 주문 객체를 slot에 직접 저장 — ref 공유 객체 의존 제거
        self._bag_contract = None   # IB BAG Contract
        self._bag_order    = None   # IB Order (lmtPrice 정정용)
        self._bag_oid: "int | None" = None   # 발사된 OID (active_oid 대체)

    def reset(self):
        self.state                 = self.IDLE
        self.pos                   = None
        self.ref                   = None
        self.order_price           = 0.0
        self.correction_count      = 0
        self.active_oid            = None
        self.market_sent           = False # [FIX-LOOP]
        self._resort_sent          = False # [FIX-LOOP]
        self._last_order_sent_at   = 0.0   # [FIX-4]
        self._bag_contract         = None  # [FIX-SLOT-OBJ]
        self._bag_order            = None  # [FIX-SLOT-OBJ]
        self._bag_oid              = None  # [FIX-SLOT-OBJ]


# ══════════════════════════════════════════════════════════════
# PositionCloseWatcher
# ══════════════════════════════════════════════════════════════
class PositionCloseWatcher(QObject):
    """
    포지션 청산 예약 감시 싱글톤.
    Signals:
        slot_status_changed(int, str)
    """
    slot_status_changed = pyqtSignal(int, str)

    _instance: "PositionCloseWatcher | None" = None

    @classmethod
    def get(cls) -> "PositionCloseWatcher":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slots = [_SlotState(i) for i in range(_N_SLOTS)]
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_all)
        self._timer.start()

    # ── Public API ────────────────────────────────────────────

    def register(self, idx: int, pos: dict, ref) -> None:
        from Sleep_Order.position_close_config import pos_close_cfg
        slot = self._slots[idx]
        slot.state            = _SlotState.WAITING
        slot.pos              = dict(pos)
        slot.ref              = ref
        slot.correction_count = 0

        cfg   = pos_close_cfg.get_slot(idx)
        strat = pos.get("strategy", "")
        oid   = pos.get("oid")
        frm   = cfg["close_from_kst"]
        to    = cfg["close_to_kst"]
        price = cfg["close_premium_price"]
        max_c = cfg["close_max_corrections"]
        _sym  = str((pos.get("legs") or [{}])[0].get("symbol","") or
                    pos.get("strategy","").split()[0] if pos.get("strategy") else "").upper()
        tick  = _tick_size(price, _sym)
        thresh = round(price - 2 * tick, 2)

        pos_close_cfg.register_position(idx, pos)
        self._emit(idx, f"⏳ 감시중 — {frm}~{to} KST")
        _tg(
            f"🔔 [슬롯{idx+1}] 청산 예약 등록\n"
            f"🏷 종목: [{_sym}] {strat}\n"
            f"OID={oid}\n"
            f"⏰ {frm} ~ {to} KST\n"
            f"💰 선매도가: ${price:.2f}  사정권: ≤${thresh:.2f}\n"
            f"🔄 최대 {max_c}회 정정"
        )
        print(f"[ClosWatcher] 슬롯{idx+1} 등록: OID={oid} / "
              f"{frm}~{to} KST / 선매도 ${price:.2f} / 사정권 ≤${thresh:.2f}")

        # [FIX-INSTANT] 등록 시점 현재가 즉시 체크
        # 현재가 > 설정가  → 현재가로 즉시 매도
        # 현재가 ≤ 사정권  → 설정가로 즉시 매도
        current = self._get_current_price(slot)
        if current is not None:
            if current > price:
                # 현재가가 설정가보다 높음 → 현재가로 즉시 발사
                slot.order_price = current
                slot.state       = _SlotState.ORDERED
                _tg(
                    f"⚡ [슬롯{idx+1}] 등록 즉시 발사 (현재가 > 설정가)\n"
                    f"📌 {strat}\n"
                    f"💰 현재가 ${current:.2f} > 설정가 ${price:.2f} → 즉시 매도"
                )
                print(f"[ClosWatcher] 슬롯{idx+1} 즉시 발사: 현재가(${current:.2f}) > 설정가(${price:.2f})")
                self._send_order(slot, is_correction=False)
            elif _in_range(current, price, _sym):
                # 현재가가 이미 사정권 이하 → 설정가로 즉시 발사
                slot.order_price = price
                slot.state       = _SlotState.ORDERED
                _tg(
                    f"⚡ [슬롯{idx+1}] 등록 즉시 발사 (이미 사정권)\n"
                    f"📌 {strat}\n"
                    f"💰 현재가 ${current:.2f} ≤ 사정권 ${thresh:.2f} → 설정가 ${price:.2f}로 즉시 매도"
                )
                print(f"[ClosWatcher] 슬롯{idx+1} 즉시 발사: 현재가(${current:.2f}) ≤ 사정권(${thresh:.2f})")
                self._send_order(slot, is_correction=False)

    def cancel(self, idx: int) -> None:
        from Sleep_Order.position_close_config import pos_close_cfg
        slot = self._slots[idx]
        if slot.state == _SlotState.ORDERED:
            self._emit(idx, "⚠️ 주문 발사 후 취소 불가")
            return
        strat = (slot.pos or {}).get("strategy", "")
        slot.reset()
        pos_close_cfg.clear_slot(idx)
        self._emit(idx, "⏸ 비활성")
        _tg(f"🚫 [슬롯{idx+1}] 청산 예약 취소: {strat}")

    def is_active(self, idx: int) -> bool:
        return self._slots[idx].state not in (_SlotState.IDLE, _SlotState.DONE)

    # ── 이벤트 드리븐 진입점 ──────────────────────────────────

    def on_order_placed(self, oid: int, pos_oid: int = None,
                         bag_contract=None, bag_order=None) -> None:
        """[FIX-SLOT-OBJ] placeOrder 성공 직후 호출.
        pos_oid로 정확한 슬롯 매칭 후 bag_contract/order/oid 를 slot에 직접 저장.
        ref 공유 객체(_chaser_bag_contract 등) 의존을 완전히 제거.
        """
        import copy
        for slot in self._slots:
            if slot.state != _SlotState.ORDERED:
                continue
            if slot._bag_oid is not None:
                continue
            # pos_oid 로 정확히 매칭
            if pos_oid is not None:
                if (slot.pos or {}).get("oid") != pos_oid:
                    continue
            # slot 에 직접 저장
            slot._bag_oid      = oid
            slot.active_oid    = oid   # 호환성 유지
            slot._bag_contract = bag_contract
            slot._bag_order    = copy.copy(bag_order) if bag_order else None
            print(f"[ClosWatcher] on_order_placed: 슬롯{slot.idx+1} "
                  f"bag_oid={oid} pos_oid={pos_oid} 저장완료")
            break

    def on_price_update(self, oid: int, current_price: float) -> None:
        """[EVENT-DRIVEN] update_position_prices 에서 호출.
        해당 OID 를 감시 중인 WAITING 슬롯에 즉시 사정권 체크.
        1초 폴링을 기다리지 않고 틱 수신 즉시 반응.
        """
        for slot in self._slots:
            if slot.state != _SlotState.WAITING:
                continue
            if not slot.pos:
                continue
            if slot.pos.get("oid") != oid:
                continue
            try:
                self._check_price(slot, current_price)
            except Exception as e:
                print(f"[ClosWatcher] on_price_update 슬롯{slot.idx+1} 오류: {e}")

    # ── 1초 폴링 ──────────────────────────────────────────────

    def _tick_all(self) -> None:
        for slot in self._slots:
            try:
                if slot.state == _SlotState.WAITING:
                    self._tick_waiting(slot)
                elif slot.state == _SlotState.ORDERED:
                    self._tick_ordered(slot)
            except Exception as e:
                print(f"[ClosWatcher] 슬롯{slot.idx+1} tick 오류: {e}")

    def _tick_waiting(self, slot: _SlotState) -> None:
        from Sleep_Order.position_close_config import pos_close_cfg
        cfg   = pos_close_cfg.get_slot(slot.idx)
        frm   = cfg["close_from_kst"]
        to    = cfg["close_to_kst"]
        price = float(cfg["close_premium_price"])

        # 수동 청산 감지
        if not self._pos_exists(slot):
            self._finish(slot, "잔고에서 사라짐 (수동 청산)")
            return

        now_dt = self._now_kst_dt()

        # 시간 창 밖이면 대기
        if not _in_time_window(now_dt, frm, to):
            if self._window_passed(now_dt, frm, to):
                self._finish(slot, f"시간 창 종료 ({frm}~{to} KST) — 미발사")
            return

        # 시간 창 안 — 현재가 가져오기 (폴링 보조: 이벤트 미수신 구간 커버)
        current = self._get_current_price(slot)
        if current is None:
            self._emit(slot.idx, f"⏳ 감시중 — 현재가 수신 대기")
            return

        self._check_price(slot, current)

    def _check_price(self, slot: _SlotState, current: float) -> None:
        """[EVENT-DRIVEN + POLLING 공용] 사정권 판단 및 선매도 발사.
        _tick_waiting(폴링) 과 on_price_update(이벤트) 양쪽에서 호출.
        """
        from Sleep_Order.position_close_config import pos_close_cfg
        cfg   = pos_close_cfg.get_slot(slot.idx)
        frm   = cfg["close_from_kst"]
        to    = cfg["close_to_kst"]
        price = float(cfg["close_premium_price"])

        # 이벤트 경로에서도 시간 창 체크
        now_dt = self._now_kst_dt()
        if not _in_time_window(now_dt, frm, to):
            return

        sym    = self._get_symbol(slot)
        tick   = _tick_size(price, sym)
        thresh = round(price - 2 * tick, 2)

        self._emit(slot.idx,
                   f"👁 감시중 | 현재 ${current:.2f} → 사정권 ≤${thresh:.2f}")

        # 사정권 도달 → 선매도 발사
        if _in_range(current, price, sym):
            slot.order_price = price
            slot.state       = _SlotState.ORDERED
            self._send_order(slot, is_correction=False)

    def _tick_ordered(self, slot: _SlotState) -> None:
        from Sleep_Order.position_close_config import pos_close_cfg
        from Sleep_Order.sleep_order_config    import sleep_cfg
        cfg   = pos_close_cfg.get_slot(slot.idx)
        max_c = int(cfg["close_max_corrections"])

        # 체결 확인 — 잔고에서 oid 사라짐
        if not self._pos_exists(slot):
            self._finish(slot, "체결 완료")
            return

        # [FIX-LOOP] 시장가 이미 발사됨 → 폴링 중복 차단
        if slot.market_sent:
            return

        # [FIX-4] 정정 비활성화 시 대기만
        if not sleep_cfg.correction_enabled:
            return

        # [FIX-4] N초 미체결 후 정정 — 마지막 주문 발사 시각 기준
        import time as _t
        wait_sec = sleep_cfg.correction_wait_sec
        last_sent = getattr(slot, '_last_order_sent_at', 0.0)
        if _t.monotonic() - last_sent < wait_sec:
            return   # 아직 N초 안 지남 → 대기

        # 미체결 → 정정 or 시장가
        if slot.correction_count >= max_c:
            self._send_market(slot)
        else:
            tick             = _tick_size(slot.order_price, self._get_symbol(slot))
            new_p            = max(0.01, round(slot.order_price - tick, 2))
            slot.order_price = new_p
            self._send_order(slot, is_correction=True)

    # ── 주문 발사 ─────────────────────────────────────────────

    def _send_order(self, slot: _SlotState, is_correction: bool) -> None:
        if is_correction:
            slot.correction_count += 1
            label = f"정정 #{slot.correction_count}"
        else:
            label = "선매도 발사"

        price = slot.order_price
        strat = (slot.pos or {}).get("strategy", "")
        pos_oid = (slot.pos or {}).get("oid")

        # [FIX-SLOT-OBJ] 정정 시 slot에 저장된 객체 직접 사용 — ref 의존 제거
        if is_correction and slot._bag_oid is not None:
            try:
                self._modify_order(slot, slot._bag_oid, price)
                self._emit(slot.idx, f"📤 {label} | ${price:.2f} (OID={slot._bag_oid})")
                _tg(
                    f"🔄 정정 [슬롯{slot.idx+1}]\n"
                    f"({label})  📌 {strat}  OID={slot._bag_oid}\n"
                    f"💰 주문가: ${price:.2f}"
                )
                print(f"[ClosWatcher] 슬롯{slot.idx+1} {label}: "
                      f"OID={slot._bag_oid} ${price:.2f} (정정)")
                # [FIX-4] 정정 발사 시각 갱신
                import time as _t
                slot._last_order_sent_at = _t.monotonic()
            except Exception as e:
                self._emit(slot.idx, f"⚠️ {label} 실패: {e}")
                print(f"[ClosWatcher] 슬롯{slot.idx+1} {label} 실패: {e}")
            return

        # [FIX-SLOT-OBJ] 최초 발사 — 신규 주문, slot에 직접 저장
        try:
            from combo_order_logic import _on_close_position_order
            _on_close_position_order(slot.ref, slot.pos, lmt_price=price, _auto=True)

            # [FIX-4] 발사 시각 기록
            import time as _t
            slot._last_order_sent_at = _t.monotonic()

            # [FIX-SLOT-OBJ] on_order_placed() 콜백에서 slot에 직접 저장됨

            self._emit(slot.idx, f"📤 {label} | ${price:.2f}")
            _sym_s = self._get_symbol(slot)
            _tg(
                f"📤 선매도 발사 [슬롯{slot.idx+1}]\n"
                f"🏷 종목: [{_sym_s}] {strat}\n"
                f"({label})  pos_oid={pos_oid}\n"
                f"💰 주문가: ${price:.2f}"
            )
            print(f"[ClosWatcher] 슬롯{slot.idx+1} {label}: "
                  f"pos_oid={pos_oid} ${price:.2f}")

        except Exception as e:
            self._emit(slot.idx, f"⚠️ {label} 실패: {e}")
            print(f"[ClosWatcher] 슬롯{slot.idx+1} {label} 실패: {e}")
            if not is_correction:
                slot.state = _SlotState.WAITING   # 첫 주문 실패 → 재시도

    def _modify_order(self, slot: _SlotState, oid: int, new_price: float) -> None:
        """[FIX-SLOT-OBJ] slot에 저장된 bag_contract/bag_order로 정정.
        ref._chaser_bag_order 완전히 제거 — 다른 주문에 의한 덮어씌움 방지.
        """
        import copy
        ref   = slot.ref
        ib    = getattr(getattr(ref, 'mw', None), 'ib', None)
        # [FIX-SLOT-OBJ] ref 대신 slot에서 직접 읽기
        bag   = slot._bag_contract
        order = slot._bag_order
        if ib is None or bag is None or order is None:
            raise RuntimeError(
                f"정정에 필요한 객체 없음 — slot에 저장된 bag/order 없음 "
                f"(ib={ib is not None}, bag={bag is not None}, order={order is not None})"
            )
        order_copy          = copy.copy(order)
        order_copy.lmtPrice = new_price
        ib.placeOrder(oid, bag, order_copy)
        print(f"[ClosWatcher] placeOrder 정정: OID={oid} lmt=${new_price:.2f}")

    def _send_market(self, slot: _SlotState) -> None:
        """[FIX-SLIPPAGE+LOOP] Simulated MKT — market_sent 플래그로 중복 차단."""
        if slot.market_sent:
            return
        slot.market_sent = True

        strat = (slot.pos or {}).get("strategy", "")
        oid   = (slot.pos or {}).get("oid")
        bid_price = self._get_bid_price(slot)

        if bid_price and bid_price > 0:
            slot.order_price = bid_price
            slot.active_oid  = None
            # [FIX-TIMER-SLOT] 타이머 발사 시점에 슬롯 식별용 스냅샷 저장
            _snap_idx     = slot.idx
            _snap_pos_oid = (slot.pos or {}).get("oid")
            self._send_order(slot, is_correction=False)
            self._emit(slot.idx,
                       f"🚨 Simulated MKT (Bid ${bid_price:.2f}) "
                       f"정정 {slot.correction_count}회 초과")
            _tg(
                f"🚨 [슬롯{slot.idx+1}] Simulated MKT\n"
                f"📌 {strat}  OID={oid}\n"
                f"💰 Bid 지정가: ${bid_price:.2f}  (정정 {slot.correction_count}회 초과)\n"
                f"⏱ 5초 후 미체결 시 진짜 시장가 발사"
            )
            print(f"[ClosWatcher] 슬롯{slot.idx+1} Simulated MKT Bid=${bid_price:.2f}")
            QTimer.singleShot(5000,
                lambda s=slot, si=_snap_idx, sp=_snap_pos_oid:
                    self._last_resort_market(s, snap_idx=si, snap_pos_oid=sp))
        else:
            print(f"[ClosWatcher] 슬롯{slot.idx+1} Bid 조회 실패 → 즉시 시장가")
            self._last_resort_market(slot)

    def _last_resort_market(self, slot: _SlotState,
                             snap_idx: int = None,
                             snap_pos_oid: int = None) -> None:
        """[FIX-SLIPPAGE+LOOP+TIMER-SLOT] 최후 시장가 — 1회만 발사.
        [FIX-TIMER-SLOT] 5초 타이머 만료 시점에 슬롯이 교체됐는지 검증.
        """
        # [FIX-TIMER-SLOT] 슬롯 교체 여부 확인
        if snap_idx is not None and slot.idx != snap_idx:
            return
        if snap_pos_oid is not None:
            cur_pos_oid = (slot.pos or {}).get("oid")
            if cur_pos_oid != snap_pos_oid:
                print(f"[ClosWatcher] _last_resort_market 슬롯 교체 감지 — 발사 취소")
                return
        if slot.state != _SlotState.ORDERED:
            return
        if not self._pos_exists(slot):
            return
        if getattr(slot, "_resort_sent", False):
            return
        slot._resort_sent = True

        strat = (slot.pos or {}).get("strategy", "")
        oid   = (slot.pos or {}).get("oid")
        try:
            from combo_order_logic import _on_close_position_order
            _on_close_position_order(slot.ref, slot.pos, lmt_price=None, _auto=True)
            self._emit(slot.idx, "🚨🚨 최후 시장가 발사")
            _tg(
                f"🚨🚨 [슬롯{slot.idx+1}] 최후 시장가\n"
                f"📌 {strat}  OID={oid}\n"
                f"Simulated MKT 5초 미체결 → 진짜 시장가"
            )
        except Exception as e:
            self._emit(slot.idx, f"⚠️ 최후 시장가 실패: {e}")

    def _finish(self, slot: _SlotState, reason: str) -> None:
        from Sleep_Order.position_close_config import pos_close_cfg
        strat = (slot.pos or {}).get("strategy", "")
        oid   = (slot.pos or {}).get("oid")
        self._emit(slot.idx, f"✅ {reason}")
        _tg(
            f"✅ [슬롯{slot.idx+1}] 완료\n"
            f"📌 {strat}  OID={oid}\n사유: {reason}"
        )
        print(f"[ClosWatcher] 슬롯{slot.idx+1} 완료: {reason}")
        pos_close_cfg.clear_slot(slot.idx)
        slot.reset()
        slot.state = _SlotState.DONE
        QTimer.singleShot(5000, lambda: self._reset_idle(slot.idx))

    def _reset_idle(self, idx: int) -> None:
        if self._slots[idx].state == _SlotState.DONE:
            self._slots[idx].state = _SlotState.IDLE
            self._emit(idx, "⏸ 비활성")

    # ── 잔고 / 현재가 헬퍼 ───────────────────────────────────

    def _pos_exists(self, slot: _SlotState) -> bool:
        if not slot.pos:
            return False
        oid = slot.pos.get("oid")
        if oid is None:
            return False
        try:
            panel     = getattr(slot.ref, "synthetic_panel", None)
            positions = getattr(panel, "_positions", []) if panel else []
            for p in positions:
                if p.get("oid") == oid:
                    # [FIX-XSP] qty=0 이면 만기 현금결제 완료로 판단
                    try:
                        if float(p.get("qty", 1)) == 0:
                            print(f"[ClosWatcher] 슬롯{slot.idx+1} qty=0 감지 → 청산 완료")
                            return False
                    except (TypeError, ValueError):
                        pass
                    # [FIX-XSP] ORDERED 상태에서 status="청산중" 이면 체결 처리
                    if slot.state == _SlotState.ORDERED:
                        if str(p.get("status", "")).strip() == "청산중":
                            print(f"[ClosWatcher] 슬롯{slot.idx+1} status=청산중 감지 → 체결 완료")
                            return False
                    return True
            return False   # OID 자체가 목록에 없음 = 청산 완료
        except Exception as e:
            print(f"[ClosWatcher] 잔고 확인 오류: {e}")
            return True

    def _get_current_price(self, slot: _SlotState) -> Optional[float]:
        """panel._positions 에서 해당 포지션의 current 가져오기."""
        if not slot.pos:
            return None
        oid = slot.pos.get("oid")
        try:
            panel     = getattr(slot.ref, "synthetic_panel", None)
            positions = getattr(panel, "_positions", []) if panel else []
            for p in positions:
                if p.get("oid") == oid:
                    cur = p.get("current", p.get("entry", 0))
                    return float(cur) if cur else None
        except Exception as e:
            print(f"[ClosWatcher] 현재가 조회 오류: {e}")
        return None

    def _get_bid_price(self, slot: _SlotState) -> Optional[float]:
        """[FIX-SLIPPAGE] panel._positions 에서 bid 가격 조회.
        bid 키 없으면 current 로 폴백 (Simulated MKT 용)."""
        if not slot.pos:
            return None
        oid = slot.pos.get("oid")
        try:
            panel     = getattr(slot.ref, "synthetic_panel", None)
            positions = getattr(panel, "_positions", []) if panel else []
            for p in positions:
                if p.get("oid") == oid:
                    val = p.get("bid") or p.get("current") or p.get("entry")
                    return float(val) if val else None
        except Exception as e:
            print(f"[ClosWatcher] bid 조회 오류: {e}")
        return None

    def _get_symbol(self, slot: "_SlotState") -> str:
        """[XSP-TICK] pos 또는 legs 에서 심볼 추출. 없으면 빈 문자열."""
        if not slot.pos:
            return ""
        # legs 에서 직접 읽기
        legs = slot.pos.get("legs") or []
        if legs:
            sym = str(legs[0].get("symbol", "") or "").upper()
            if sym:
                return sym
        # strategy 첫 단어에서 추출 (예: "XSP 풋스프레드 ...")
        strat = str(slot.pos.get("strategy", "")).strip()
        if strat:
            return strat.split()[0].upper()
        return ""

    # ── 시각 유틸 ─────────────────────────────────────────────

    def _now_kst_dt(self) -> datetime:
        """현재 KST datetime (초 단위, tzinfo 포함)."""
        if _KST:
            return datetime.now(_KST).replace(second=0, microsecond=0)
        from datetime import timezone, timedelta
        utc_now = datetime.utcnow().replace(second=0, microsecond=0)
        return utc_now + timedelta(hours=9)

    @staticmethod
    def _window_passed(now_dt: datetime, frm: str, to: str) -> bool:
        """
        To 시각이 완전히 지났는지 판단.
        자정 넘김 처리: to < from 이면 to 는 다음날.
        """
        fh, fm = map(int, frm.split(":"))
        th, tm = map(int, to.split(":"))
        today  = now_dt.date()
        from_dt = datetime(today.year, today.month, today.day, fh, fm,
                           tzinfo=now_dt.tzinfo)
        to_dt   = datetime(today.year, today.month, today.day, th, tm,
                           tzinfo=now_dt.tzinfo)
        if to_dt <= from_dt:
            to_dt += timedelta(days=1)
        # now 가 to 를 지났으면 True
        return now_dt > to_dt

    def _emit(self, idx: int, text: str) -> None:
        self.slot_status_changed.emit(idx, text)
