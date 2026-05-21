"""
combo_order_callbacks.py — BAG 주문 상태 콜백  v2.5
──────────────────────────────────────────────────
[FIX-BUG3] _on_order_status Inactive 분기:
  _close_oid_set.discard(oid) 추가 — 누수 방지
  _exec_known_oids.discard(oid) 추가

[FIX-BUG4] 청산 부분체결 후 최종 체결 처리:
  _pending_close_source_oid 를 return 전 보존
  is_close_match 판별을 부분체결 return 전에 저장

[FIX-RECONN2] _check_executions_and_clean 핸들러 충돌 방지:
  ib.execDetails 덮어쓰기 대신 bridge 시그널 구독 방식 사용

[FIX-CACHE] _exec_avg_cache 재연결 후 정리:
  connect_order_callbacks() 호출마다 캐시 초기화
──────────────────────────────────────────────────
"""

from __future__ import annotations
from typing import Optional
from functools import partial
from PyQt5.QtCore import Qt


_STATUS_SUBMITTED = ("Submitted", "PreSubmitted")
_STATUS_FILLED    = ("Filled",)
_STATUS_CANCELLED = ("Cancelled",)
_STATUS_INACTIVE  = ("Inactive",)

_POS_STREAM_BASE = 9200
# [FIX-B6] reqId 충돌 방지: oid*10+i 방식은 oid가 커지면 범위 초과 위험
# 전역 카운터로 순차 할당 → 고유성 보장
_pos_stream_tid_counter = _POS_STREAM_BASE


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def _alloc_stream_tid() -> int:
    """[FIX-B6] 순차 reqId 할당 — oid*10+i 충돌 방지."""
    global _pos_stream_tid_counter
    _pos_stream_tid_counter += 1
    # 상한 도달 시 base 이후 재순환 (앞서 해제된 tid 재사용 안전)
    if _pos_stream_tid_counter > _POS_STREAM_BASE + 8000:
        _pos_stream_tid_counter = _POS_STREAM_BASE + 1
    return _pos_stream_tid_counter


def connect_order_callbacks(self) -> None:
    if getattr(self, '_cb_connected', False):
        return
    from core import bridge
    _slot_status = partial(_on_order_status, self)
    _slot_exec   = partial(_on_exec_details, self)
    bridge.order_status_sig.connect(_slot_status, Qt.QueuedConnection)
    bridge.exec_sig.connect(_slot_exec,           Qt.QueuedConnection)
    self._cb_slot_status  = _slot_status
    self._cb_slot_exec    = _slot_exec
    self._cb_connected    = True
    # [FIX-B1] 재연결마다 stale OID 캐시 제거 — 무조건 초기화
    # 기존 코드: if not hasattr → 최초 1회만 초기화 → 재연결 시 이전 세션 OID 잔존 버그
    self._exec_avg_cache = {}


def disconnect_order_callbacks(self) -> None:
    if not getattr(self, '_cb_connected', False):
        return
    try:
        from core import bridge
        bridge.order_status_sig.disconnect(self._cb_slot_status)
        bridge.exec_sig.disconnect(self._cb_slot_exec)
    except Exception:
        pass
    self._cb_connected = False


# ══════════════════════════════════════════════════════════════
# 주문 상태 핸들러
# ══════════════════════════════════════════════════════════════

def _on_order_status(self, oid: int, status: str,
                     filled: float, remaining: float,
                     avg_fill: float) -> None:
    pending          = getattr(self, '_pending_position', None)
    close_oids_check = getattr(self, '_close_oid_set', set())
    is_pending_match = bool(pending and pending.get('oid') == oid)
    is_close_match   = oid in close_oids_check

    is_pending_close = (
        is_pending_match
        and str((pending or {}).get('strategy', '')).startswith("청산:")
    )
    if is_pending_close:
        close_oids_check.add(oid)
        is_close_match = True

    if not is_pending_match and not is_close_match:
        return

    panel = getattr(self, 'synthetic_panel', None)

    # ── 접수 ─────────────────────────────────────────────────
    if status in _STATUS_SUBMITTED:
        self._log(f"📨 OID={oid} 주문 접수됨 ({status})")
        if is_close_match:
            src_oid = getattr(self, '_pending_close_source_oid', None)
            if src_oid and panel and hasattr(panel, 'mark_position_closing'):
                panel.mark_position_closing(src_oid)
        else:
            _set_panel_status(panel, oid, "⏳ 접수됨")

        pending_close = getattr(self, '_pending_close_oid', None)
        if pending_close and pending_close == oid:
            try:
                from combo_position_store import safe_remove_after_order
                src_oid = getattr(self, '_pending_close_source_oid', pending_close)
                safe_remove_after_order(src_oid, log_fn=self._log)
            except Exception as e:
                self._log(f"⚠ 청산 파일 제거 실패: {e}")
            self._pending_close_oid = None

    # ── 체결 ─────────────────────────────────────────────────
    elif status in _STATUS_FILLED:
        # [FIX-BUG4] is_close 판별을 return 전에 확정
        close_oids = getattr(self, '_close_oid_set', set())
        is_close   = (oid in close_oids) or is_pending_close

        if remaining > 0:
            self._log(f"⚡ OID={oid} 부분체결: {filled:.0f}체결 / {remaining:.0f}잔여")
            _set_panel_status(panel, oid, f"⚡ 부분체결({filled:.0f})")
            # [FIX-B3] 딕셔너리 교체(= 덮어쓰기) 대신 기존 딕셔너리에 업데이트
            # 기존 코드: self._partial_fill_is_close = {oid: is_close}
            #   → 복수 포지션 동시 부분체결 시 이전 OID 정보가 소멸됨
            _pfc = getattr(self, '_partial_fill_is_close', None)
            if not isinstance(_pfc, dict):
                _pfc = {}
            _pfc[oid] = is_close
            self._partial_fill_is_close = _pfc
            return

        if avg_fill > 0:
            avg = round(avg_fill, 2)
            self._log(f"✅ OID={oid} 체결완료  avg=${avg:.2f}")
        else:
            avg = _get_avg_price(self, oid)
            msg = f"✅ OID={oid} 체결완료"
            msg += f"  avg=${avg:.2f}" if avg else "  avg=미수신"
            self._log(msg)

        # [FIX-BUG4] 부분체결 후 최종 체결인 경우 저장된 is_close 사용
        partial_map = getattr(self, '_partial_fill_is_close', {})
        if isinstance(partial_map, dict) and oid in partial_map:
            is_close = partial_map.pop(oid)

        if is_close:
            src_oid = getattr(self, '_pending_close_source_oid', None) or oid
            self._log(f"🔴 OID={oid} 청산 체결 완료 (원본 OID={src_oid})")
            if panel and hasattr(panel, 'remove_position_by_oid'):
                panel.remove_position_by_oid(src_oid)
            try:
                from combo_position_store import remove_position
                remove_position(src_oid)
            except Exception:
                pass
            close_oids.discard(oid)
            self._pending_close_source_oid = None
            self._pending_position         = None
            try:
                stop_position_price_stream(self, src_oid)
            except Exception:
                pass
        else:
            pending = getattr(self, '_pending_position', None)
            if pending and pending.get('oid') == oid:
                if avg:
                    pending['entry']   = avg
                    pending['current'] = avg
                pending['status'] = '보유'
                if panel and hasattr(panel, 'add_position'):
                    panel.add_position(pending)
                _start_position_price_stream(self, pending)
                try:
                    from combo_position_store import save_one_position
                    save_one_position(pending)
                except Exception as e:
                    self._log(f"⚠ 잔고 저장 실패: {e}")
                # [FIX-B2] _pending_position = None 을 TG 알림 이후로 이동
                # 기존 코드: 여기서 None 처리 후 아래에서 _pend 재조회 → 항상 None → notify_filled 미호출
                # 수정: pending 지역변수를 보존해 두고 None 처리는 TG 알림 이후에 수행

        # SpecialFillWatcher / SpikeWatcher / TG 알림
        try:
            from combo_order_special_condition import (
                SpecialFillWatcher, notify_filled, notify_closed)
            SpecialFillWatcher.get().unwatch(oid)
            try:
                from Sleep_Order.spike_watcher_debit import DebitSpikeWatcher
                DebitSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avg or 0.0)
            except Exception:
                pass
            try:
                from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher
                SingleOptSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avg or 0.0)
            except Exception:
                pass
            if is_close:
                pos_for_tg = next(
                    (p for p in getattr(panel, '_positions', [])
                     if p.get('oid') == oid), None)
                if pos_for_tg:
                    if avg:
                        pos_for_tg['current'] = avg
                    notify_closed(pos_for_tg)
            else:
                # [FIX-B2] self._pending_position 대신 위에서 확보한 pending 지역변수 사용
                # 기존 코드: _pend = getattr(self, '_pending_position', None)
                #   → 이미 None 처리된 후라 항상 None → notify_filled 호출 안됨
                _pend_for_tg = getattr(self, '_pending_position', None)
                if _pend_for_tg is None:
                    # pending 이 이미 None 처리된 경우, 위 블록에서 보존한 변수 사용
                    _pend_for_tg = pending if 'pending' in dir() else None
                if _pend_for_tg and _pend_for_tg.get('oid') == oid:
                    notify_filled(_pend_for_tg, avg or 0.0)
        except Exception:
            pass

        # [FIX-B2] _pending_position None 처리를 TG 알림 이후로 이동 (신규 체결 경우)
        if not is_close:
            _cur_pend = getattr(self, '_pending_position', None)
            if _cur_pend and _cur_pend.get('oid') == oid:
                self._pending_position = None

        try:
            _wolf = getattr(panel, 'wolf_banner', None)
            if _wolf and hasattr(_wolf, 'set_off'):
                _wolf.set_off()
        except Exception:
            pass

        _set_panel_filled(panel, oid, avg)
        _deactivate_chaser_safe(self, reason="체결 완료")
        self._chaser_current_oid = None
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(30_000, lambda: getattr(
            self, '_exec_known_oids', set()).discard(oid))

    # ── 취소 확인 ────────────────────────────────────────────
    elif status in _STATUS_CANCELLED:
        self._log(f"✕ OID={oid} 취소 확인됨")
        _set_panel_cancelled(panel, oid)
        _deactivate_chaser_safe(self, reason="취소 확인")
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().unwatch(oid)
        except Exception:
            pass
        try:
            from Sleep_Order.spike_watcher_debit import DebitSpikeWatcher
            DebitSpikeWatcher.get().unwatch_cancelled_by_oid(oid)
        except Exception:
            pass
        try:
            from Sleep_Order.spike_watcher_single import SingleOptSpikeWatcher
            SingleOptSpikeWatcher.get().unwatch_cancelled_by_oid(oid)
        except Exception:
            pass
        try:
            stop_position_price_stream(self, oid)
        except Exception:
            pass
        if getattr(self, '_pending_position', None) and \
                getattr(self, '_pending_position', {}).get('oid') == oid:
            self._pending_position = None
        self._bag_session        = None
        self._chaser_current_oid = None
        getattr(self, '_exec_known_oids', set()).discard(oid)
        # [FIX-BUG3] 취소 시 _close_oid_set 정리
        getattr(self, '_close_oid_set', set()).discard(oid)
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None
        try:
            from combo_position_store import remove_position
            remove_position(oid)
        except Exception:
            pass
        try:
            _wolf = getattr(panel, 'wolf_banner', None)
            if _wolf and hasattr(_wolf, 'set_off'):
                _wolf.set_off()
        except Exception:
            pass

    # ── 거절/비활성 ──────────────────────────────────────────
    elif status in _STATUS_INACTIVE:
        self._log(f"❌ OID={oid} 주문 거절/비활성")
        _set_panel_status(panel, oid, "❌ 거절됨")
        _deactivate_chaser_safe(self, reason="주문 거절")
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().unwatch(oid)
        except Exception:
            pass
        try:
            stop_position_price_stream(self, oid)
        except Exception:
            pass
        # [FIX-BUG3] Inactive 시 _close_oid_set 누수 방지
        getattr(self, '_close_oid_set', set()).discard(oid)
        # [FIX-OID4] Inactive 시 _exec_known_oids 정리
        getattr(self, '_exec_known_oids', set()).discard(oid)
        self._bag_session        = None
        self._chaser_current_oid = None
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None
        try:
            _wolf = getattr(panel, 'wolf_banner', None)
            if _wolf and hasattr(_wolf, 'set_off'):
                _wolf.set_off()
        except Exception:
            pass


def _on_exec_details(self, oid: int, sym: str,
                     side: str, qty: float, price: float) -> None:
    """execDetails 콜백 — 폴백 캐시 저장 + 로그."""
    pending      = getattr(self, '_pending_position', None)
    known        = getattr(self, '_exec_known_oids', set())
    is_pending   = bool(pending and pending.get('oid') == oid)
    is_close_known = oid in getattr(self, '_close_oid_set', set())
    if not is_pending and oid not in known and not is_close_known:
        return

    commission = round(float(qty) * 1.0, 2)
    self._log(
        f"💰 체결내역: OID={oid}  {side}  qty={qty:.0f}"
        f"  price=${price:.2f}  수수료=${commission:.2f}")

    cache = getattr(self, '_exec_avg_cache', {})
    if oid not in cache:
        cache[oid] = price
        self._exec_avg_cache = cache

    pending  = getattr(self, '_pending_position', None)
    strategy = pending.get('strategy', "") if pending and pending.get('oid') == oid else ""

    try:
        from trade_log import log_exec
        try:
            from trade_log.und_saver import get_context as _get_ctx
            und_ctx = _get_ctx()
        except Exception:
            und_ctx = None
        legs = pending.get('legs', []) if pending and pending.get('oid') == oid else []
        leg  = next((l for l in legs if l.get('sym') == sym), legs[0] if legs else {})
        log_exec(
            oid=oid, source='combo', sym=sym,
            action=side, qty=qty, price=price,
            expiry=leg.get('expiry', ''), right=leg.get('cp', ''),
            strike=float(leg.get('strike', 0)), commission=commission,
            strategy=strategy, und_ctx=und_ctx)
    except Exception:
        pass

    panel = getattr(self, 'synthetic_panel', None)
    if panel and hasattr(panel, 'mark_position_filled'):
        panel.mark_position_filled(oid)


# ══════════════════════════════════════════════════════════════
# 실시간 손익 스트림
# ══════════════════════════════════════════════════════════════

def _start_position_price_stream(self, pending: dict) -> None:
    """
    체결 완료 후 BAG net mid-price 실시간 구독.
    [FIX-N] tid = _POS_STREAM_BASE + oid * 10 + leg_index
    [FIX-O] panel.update_position_prices(oid, net) 호출
    """
    from core import router

    legs = pending.get('legs', [])
    oid  = pending.get('oid', 0)
    if not legs or not oid:
        return

    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib:
        return

    if not hasattr(self, '_pos_mid_ticks'):    self._pos_mid_ticks    = {}
    if not hasattr(self, '_pos_stream_tids'):  self._pos_stream_tids  = {}
    if not hasattr(self, '_pos_stream_slots'): self._pos_stream_slots = {}

    self._pos_mid_ticks[oid]    = {}
    self._pos_stream_tids[oid]  = []
    self._pos_stream_slots[oid] = []

    panel = getattr(self, 'synthetic_panel', None)

    def _make_tick_handler(leg_idx: int):
        def _on_tick(req_id: int, tick_type: int, price: float):
            if price <= 0 or tick_type not in (1, 2, 4, 9):
                return
            ticks = self._pos_mid_ticks.get(oid, {})
            if leg_idx not in ticks:
                ticks[leg_idx] = {}
            ticks[leg_idx][tick_type] = price
            self._pos_mid_ticks[oid]  = ticks

            net = _calc_bag_net(self, oid, legs)
            if net is None:
                return
            net_rounded = round(net, 2)

            if panel and hasattr(panel, 'update_position_prices'):
                panel.update_position_prices(oid, net_rounded)
            try:
                from combo_position_store import update_position_current
                update_position_current(oid, net_rounded)
            except Exception:
                pass
            try:
                _pos = next(
                    (p for p in getattr(panel, '_positions', [])
                     if p.get('oid') == oid), None)
                if _pos:
                    entry = float(_pos.get('entry', net_rounded) or net_rounded)
                    side  = _pos.get('side', 'SELL')
                    if entry > 0:
                        pct = ((entry - net_rounded) / entry * 100
                               if side == 'SELL'
                               else (net_rounded - entry) / entry * 100)
                        banner = getattr(self, 'profit_alert_banner', None)
                        if banner and hasattr(banner, 'update_pct'):
                            banner.update_pct(pct)
                        try:
                            from combo_order_special_condition import SpecialFillWatcher
                            SpecialFillWatcher.get().on_net_price_update(oid, net_rounded)
                        except Exception:
                            pass
            except Exception:
                pass
        return _on_tick

    for i, leg in enumerate(legs):
        con_id = _get_leg_conid(self, leg)
        if not con_id:
            self._log(f"⚠ 실시간 손익: 레그{i+1} conId 없음 — 구독 스킵")
            continue
        tid  = _alloc_stream_tid()  # [FIX-B6] 전역 카운터 — oid*10+i 충돌 방지
        slot = _make_tick_handler(i)
        router.register_price(tid, tid, slot)
        self._pos_stream_tids[oid].append(tid)
        self._pos_stream_slots[oid].append(slot)
        try:
            from ibapi.contract import Contract as IbContract
            c = IbContract()
            c.conId    = con_id
            c.exchange = "SMART"
            ib.reqMktData(tid, c, "", False, False, [])
            self._log(
                f"📡 실시간 손익 구독: 레그{i+1} "
                f"{leg.get('dir','')} {leg.get('cp','')} {leg.get('strike','')} "
                f"(conId={con_id}, tid={tid})")
        except Exception as e:
            router.unregister_price(slot)
            self._log(f"❌ 실시간 손익 reqMktData 레그{i+1}: {e}")


def _calc_bag_net(self, oid: int, legs: list) -> Optional[float]:
    """
    레그별 mid price → BAG net mid price.
    [v2.4] 틱 스냅 적용. 미수신 레그는 Last→Close 폴백.
    """
    ticks = self._pos_mid_ticks.get(oid, {})
    net   = 0.0
    for i, leg in enumerate(legs):
        leg_ticks = ticks.get(i, {})
        bid = leg_ticks.get(1)
        ask = leg_ticks.get(2)
        if bid is None or ask is None:
            last  = leg_ticks.get(4)
            close = leg_ticks.get(9)
            mid   = last if last is not None and last > 0 else close
            if mid is None or mid <= 0:
                return None
        else:
            mid = (bid + ask) / 2.0

        from combo_order_chaser import _get_tick_size, _snap_to_tick
        tick        = _get_tick_size(mid)
        mid_snapped = _snap_to_tick(mid, tick, "buy")
        net += mid_snapped if leg.get('dir') == 'BUY' else -mid_snapped
    return net


def _get_leg_conid(self, leg: dict) -> int:
    if leg.get('con_id'):
        return int(leg['con_id'])
    try:
        from combo_order_bag import _CONID_CACHE, _conid_key
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = sym_w.text().strip().upper() if sym_w else "SPX"
        symbol = symbol.replace("SPXW", "SPX")
        key    = _conid_key(
            symbol, str(leg.get('cp', '')),
            float(leg.get('strike', 0)), str(leg.get('expiry', '')))
        return int(_CONID_CACHE.get(key, 0))
    except Exception:
        return 0


def stop_position_price_stream(self, oid: int) -> None:
    """청산/취소 시 해당 포지션 실시간 구독 해제."""
    from core import router
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    tids  = getattr(self, '_pos_stream_tids',  {}).pop(oid, [])
    slots = getattr(self, '_pos_stream_slots', {}).pop(oid, [])
    getattr(self, '_pos_mid_ticks', {}).pop(oid, None)
    for tid in tids:
        if ib:
            try: ib.cancelMktData(tid)
            except Exception: pass
    for slot in slots:
        router.unregister_price(slot)
    if tids:
        self._log(f"📡 실시간 손익 구독 해제: OID={oid} ({len(tids)}레그)")


# ══════════════════════════════════════════════════════════════
# panel 헬퍼 (None-safe)
# ══════════════════════════════════════════════════════════════

def _set_panel_status(panel, oid: int, text: str) -> None:
    if panel is None: return
    for pos in getattr(panel, '_positions', []):
        if pos.get('oid') == oid:
            pos['status'] = text
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()


def _set_panel_filled(panel, oid: int, avg_price: Optional[float]) -> None:
    if panel is None: return
    for pos in getattr(panel, '_positions', []):
        if pos.get('oid') == oid:
            pos['status'] = '보유'
            if avg_price:
                pos['entry']   = avg_price
                pos['current'] = avg_price
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()
    tabs = getattr(panel, '_tabs', None)
    if tabs:
        tabs.setCurrentIndex(1)


def _set_panel_cancelled(panel, oid: int) -> None:
    if panel is None: return
    if hasattr(panel, 'mark_position_cancelled'):
        panel.mark_position_cancelled(oid)


def _update_panel_entry_price(panel, oid: int, price: float) -> None:
    if panel is None: return
    for pos in getattr(panel, '_positions', []):
        if pos.get('oid') == oid:
            pos['entry']   = price
            pos['current'] = price
    if hasattr(panel, '_refresh_pos_table'):
        panel._refresh_pos_table()


# ══════════════════════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════════════════════

def _get_avg_price(self, oid: int) -> Optional[float]:
    return getattr(self, '_exec_avg_cache', {}).get(oid)


def _deactivate_chaser_safe(self, reason: str = "") -> None:
    try:
        from combo_order_chaser import deactivate_chaser
        deactivate_chaser(self, reason=reason)
    except Exception:
        pass
