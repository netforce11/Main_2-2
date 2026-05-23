"""
position_close_watcher_cancel_patch.py
──────────────────────────────────────────────────────────────
[BUG-1] 청산 취소 버그 수정 (PositionCloseWatcher.cancel 교체)

문제 A: ORDERED 상태(주문 발사 후)에도 취소 불가 → 취소+IB cancelOrder 연동
문제 B: 슬롯에 들어간 Sleep 예약 주문이 청산 취소 시 같이 취소 안 됨
        → SleepOrderWatcher에서 해당 OID 예약도 함께 해제

교체 대상: PositionCloseWatcher.cancel()
──────────────────────────────────────────────────────────────
"""


def cancel(self, idx: int) -> None:
    """
    [BUG-1] 청산 예약 취소.
    - WAITING: 바로 리셋
    - ORDERED: IB cancelOrder 후 리셋 (기존엔 취소 불가였음)
    - 슬롯에 연동된 Sleep 예약 주문도 함께 해제
    """
    from Sleep_Order.position_close_config import pos_close_cfg

    slot  = self._slots[idx]
    strat = (slot.pos or {}).get("strategy", "")
    oid   = (slot.pos or {}).get("oid")

    if slot.state == _SlotState.ORDERED:
        # [FIX-A] ORDERED 상태: 발사된 주문 IB 취소 시도
        bag_oid = slot._bag_oid or slot.active_oid
        if bag_oid is not None:
            try:
                from core import bridge as _br
                ib = getattr(_br, "ib", None) or getattr(_br, "_ib", None)
                if ib is not None:
                    ib.cancelOrder(bag_oid)
                    print(f"[ClosWatcher] 슬롯{idx+1} IB cancelOrder({bag_oid})")
                    self._emit(idx, f"🚫 취소 요청 전송 (OID={bag_oid})")
                else:
                    print(f"[ClosWatcher] 슬롯{idx+1} ib 객체 없음 — 로컬 리셋만")
            except Exception as e:
                print(f"[ClosWatcher] 슬롯{idx+1} cancelOrder 실패: {e}")
        else:
            print(f"[ClosWatcher] 슬롯{idx+1} bag_oid 없음 — 로컬 리셋")

    # [FIX-B] 슬롯 OID에 연동된 Sleep 예약 주문도 함께 해제
    if oid is not None:
        _cancel_sleep_reservation(idx, oid)

    slot.reset()
    pos_close_cfg.clear_slot(idx)
    self._emit(idx, "⏸ 비활성")
    _tg(f"🚫 [슬롯{idx+1}] 청산 예약 취소: {strat}")


# ── Sleep 예약 취소 헬퍼 ────────────────────────────────────────
def _cancel_sleep_reservation(slot_idx: int, pos_oid: int) -> None:
    """
    [BUG-1-B] 청산 슬롯에 연동된 SleepOrder 예약을 해제.
    SleepOrderWatcher의 슬롯 중 pos_oid가 일치하는 항목을 취소.
    """
    try:
        from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
        watcher = SleepOrderWatcher.get()
        for i, s in enumerate(getattr(watcher, "_slots", [])):
            cfg_oid = None
            try:
                cfg_oid = (s.pos or {}).get("oid") if hasattr(s, "pos") else None
            except Exception:
                pass
            if cfg_oid == pos_oid and hasattr(watcher, "cancel"):
                watcher.cancel(i)
                print(f"[ClosWatcher] Sleep 예약 슬롯{i+1} 해제 (pos_oid={pos_oid})")
    except ImportError:
        pass   # SleepOrderWatcher 없으면 무시
    except Exception as e:
        print(f"[ClosWatcher] Sleep 예약 해제 오류: {e}")


# ──────────────────────────────────────────────────────────────
# 적용 방법:
#
# position_close_watcher.py 안의 PositionCloseWatcher 클래스에서
# 기존 cancel() 메서드를 위의 cancel() 함수로 교체하고,
# _cancel_sleep_reservation() 를 모듈 레벨에 추가하세요.
#
# 또는 아래처럼 monkey-patch 방식으로 적용도 가능:
#
#   from Sleep_Order.position_close_watcher import PositionCloseWatcher
#   import types, position_close_watcher_cancel_patch as _p
#   PositionCloseWatcher.cancel = types.MethodType(_p.cancel, ...)
# ──────────────────────────────────────────────────────────────
