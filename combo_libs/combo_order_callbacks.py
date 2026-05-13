"""
combo_order_callbacks.py — BAG 주문 상태 콜백 연결 / UI 갱신
──────────────────────────────────────────────────────────────
[v2.4] 소수점 정밀도 수정:
  _calc_bag_net:
    · tick_type 1,2 외에 Last(4), Close(9) 폴백 추가 (OTM 유동성 낮은 레그 대응)
    · 레그 mid를 _snap_to_tick으로 틱 단위 정렬 후 합산
  _make_tick_handler:
    · tick_type 캐싱 범위를 (1,2) → (1,2,4,9) 로 확장 (폴백 데이터 확보)
──────────────────────────────────────────────────────────────
[FIX-E] Filled 시 신규/청산 주문 구분
[FIX-F] Submitted 시 청산 파일 제거
[FIX-G] save_one_position 실패 로그 추가
[FIX-N] tid 충돌 수정
  기존: _POS_STREAM_BASE + (oid % 100) * 10 + leg_index
        oid 끝 두 자리 같으면(101, 201 등) tid 완전 충돌
        → 두 포지션 가격이 동일하게 엉켜 출력
  수정: _POS_STREAM_BASE + oid * 10 + leg_index
        oid 직접 사용 → 포지션마다 독립 tid 대역
[FIX-O] update_position_prices 호출 — strategy 문자열 → oid 전달
  패널 FIX-K 와 연동 (oid 기준 갱신)
[FIX-P] _on_order_status 필터 수정 — 합성주문 체결 후 잔고 누락 버그 수정
  기존: _chaser_current_oid 필터만 사용
        → Smart Chaser 모드 OFF 시 콜백 무시 → 잔고 리스트에 미표시
  수정: _pending_position oid 기반 필터로 변경
        → Chaser 모드 ON/OFF 무관하게 모든 합성주문 체결 처리
        _on_exec_details 도 동일하게 수정
──────────────────────────────────────────────────────────────
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


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════

def connect_order_callbacks(self) -> None:
    if getattr(self, '_cb_connected', False):
        return
    from core import bridge
    _slot_status = partial(_on_order_status, self)
    _slot_exec   = partial(_on_exec_details, self)
    bridge.order_status_sig.connect(_slot_status, Qt.QueuedConnection)
    bridge.exec_sig.connect(_slot_exec,           Qt.QueuedConnection)
    self._cb_slot_status = _slot_status
    self._cb_slot_exec   = _slot_exec
    self._cb_connected   = True


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
    # [FIX-P] 필터 수정: _chaser_current_oid → _pending_position 기반으로 변경
    # 기존: Smart Chaser 모드 OFF 시 _chaser_current_oid=None → 콜백 무시
    #       → 합성주문 체결 후 잔고 리스트에 미표시 버그
    # 수정: _pending_position 의 oid 기준으로 필터링
    #       → Chaser ON/OFF 무관하게 모든 합성주문 체결 처리
    # 단, _close_oid_set 등록된 청산 주문은 pending 없어도 처리해야 하므로 OR 조건 유지
    pending          = getattr(self, '_pending_position', None)
    close_oids_check = getattr(self, '_close_oid_set', set())
    is_pending_match = bool(pending and pending.get('oid') == oid)
    is_close_match   = oid in close_oids_check
    if not is_pending_match and not is_close_match:
        return

    panel = getattr(self, 'synthetic_panel', None)

    # ── 접수 ─────────────────────────────────────────────────
    if status in _STATUS_SUBMITTED:
        self._log(f"📨 OID={oid} 주문 접수됨 ({status})")
        _set_panel_status(panel, oid, "⏳ 접수됨")

        # [FIX-F] 청산 주문 접수 확인 → 파일 제거
        pending_close = getattr(self, '_pending_close_oid', None)
        if pending_close and pending_close == oid:
            try:
                from combo_position_store import safe_remove_after_order
                safe_remove_after_order(oid, log_fn=self._log)
            except Exception as e:
                self._log(f"⚠ 청산 파일 제거 실패: {e}")
            self._pending_close_oid = None

    # ── 체결 ─────────────────────────────────────────────────
    elif status in _STATUS_FILLED:

        if remaining > 0:
            self._log(f"⚡ OID={oid} 부분체결: {filled:.0f}체결 / {remaining:.0f}잔여")
            _set_panel_status(panel, oid, f"⚡ 부분체결({filled:.0f})")
            return

        if avg_fill > 0:
            avg = round(avg_fill, 2)
            self._log(f"✅ OID={oid} 체결완료  avg(BAG net)=${avg:.2f}")
        else:
            avg = _get_avg_price(self, oid)
            msg = f"✅ OID={oid} 체결완료"
            msg += f"  avg(exec캐시)=${avg:.2f}" if avg else "  avg=미수신"
            self._log(msg)

        # [FIX-E] 청산 oid 여부 판별
        close_oids = getattr(self, '_close_oid_set', set())
        is_close   = (oid in close_oids)

        if is_close:
            # 청산 체결 → 패널/파일에서 제거
            self._log(f"🔴 OID={oid} 청산 체결 완료")
            if panel and hasattr(panel, 'remove_position_by_oid'):
                panel.remove_position_by_oid(oid)
            try:
                from combo_position_store import remove_position
                remove_position(oid)
            except Exception:
                pass
            close_oids.discard(oid)
            # [FIX-ST1] 청산 체결 시 실시간 가격 구독 해제 — 미해제 시 레그 tick 계속 수신
            try:
                stop_position_price_stream(self, oid)
            except Exception:
                pass

        else:
            # 신규 체결 → 패널 추가 + 파일 저장
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

                self._pending_position = None

        # [FIX-SC2] SpecialFillWatcher 해제 + TG 알림
        try:
            from combo_order_special_condition import (
                SpecialFillWatcher, notify_filled, notify_closed)
            SpecialFillWatcher.get().unwatch(oid)
            if is_close:
                # 청산 체결 TG
                pos_for_tg = next(
                    (p for p in getattr(panel, '_positions', [])
                     if p.get('oid') == oid), None)
                if pos_for_tg:
                    if avg:
                        pos_for_tg['current'] = avg
                    notify_closed(pos_for_tg)
            else:
                # 신규 체결 TG
                _pend = getattr(self, '_pending_position', None)
                if _pend and _pend.get('oid') == oid:
                    notify_filled(_pend, avg or 0.0)
        except Exception as _e:
            pass

        # [WOLF-OFF] 체결(신규/청산) 시 Wolf System OFF
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
        # [FIX-SC3] 취소 시 SpecialFillWatcher 해제 — zombie timer 방지
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().unwatch(oid)
        except Exception:
            pass
        # [FIX-ST2] 취소 시 실시간 가격 구독 해제
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
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None
        try:
            from combo_position_store import remove_position
            remove_position(oid)
        except Exception:
            pass
        # [WOLF-OFF] 취소 시 Wolf OFF
        try:
            _wolf = getattr(panel, 'wolf_banner', None)
            if _wolf and hasattr(_wolf, 'set_off'):
                _wolf.set_off()
        except Exception:
            pass

    elif status in _STATUS_INACTIVE:
        self._log(f"❌ OID={oid} 주문 거절/비활성")
        _set_panel_status(panel, oid, "❌ 거절됨")
        _deactivate_chaser_safe(self, reason="주문 거절")
        # [FIX-SC4] 거절 시 SpecialFillWatcher 해제 — zombie timer 방지
        try:
            from combo_order_special_condition import SpecialFillWatcher
            SpecialFillWatcher.get().unwatch(oid)
        except Exception:
            pass
        # [FIX-ST3] 거절 시 실시간 가격 구독 해제
        try:
            stop_position_price_stream(self, oid)
        except Exception:
            pass
        self._bag_session        = None
        self._chaser_current_oid = None
        if getattr(self, '_cancel_sent_oid', None) == oid:
            self._cancel_sent_oid = None
        # [WOLF-OFF] 거절 시 Wolf OFF
        try:
            _wolf = getattr(panel, 'wolf_banner', None)
            if _wolf and hasattr(_wolf, 'set_off'):
                _wolf.set_off()
        except Exception:
            pass


def _on_exec_details(self, oid: int, sym: str,
                     side: str, qty: float, price: float) -> None:
    """execDetails 콜백 — 폴백 캐시 저장 + 로그 전용."""
    # [FIX-P] _pending_position 기반 필터로 변경 (known oids 보조)
    pending    = getattr(self, '_pending_position', None)
    known      = getattr(self, '_exec_known_oids', set())
    is_pending = bool(pending and pending.get('oid') == oid)
    if not is_pending and oid not in known:
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
            expiry=leg.get('expiry', ''),
            right=leg.get('cp', ''),
            strike=float(leg.get('strike', 0)),
            commission=commission,
            strategy=strategy,
            und_ctx=und_ctx,
        )
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
      oid 직접 사용 → 포지션마다 완전히 독립된 tid 대역 보장
      (기존 oid % 100 방식은 oid=101, 201 처럼 끝 두 자리 같으면 충돌)

    [FIX-O] panel.update_position_prices(oid, net) 으로 호출
      strategy 문자열 → oid 기준으로 변경
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
            # [v2.4] Bid(1), Ask(2), Last(4), Close(9) 모두 캐싱
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

            # [FIX-O] oid 기준으로 패널 갱신
            if panel and hasattr(panel, 'update_position_prices'):
                panel.update_position_prices(oid, net_rounded)

            # [FIX-ENTRY] 현재가 파일 저장 (재접속 후 수익률 복원용)
            try:
                from combo_position_store import update_position_current
                update_position_current(oid, net_rounded)
            except Exception:
                pass

            # [FIX-ENTRY] 수익률 계산 후 배너/Wolf 감시에 전달
            try:
                _pos = next(
                    (p for p in getattr(panel, '_positions', [])
                     if p.get('oid') == oid), None)
                if _pos:
                    entry  = float(_pos.get('entry', net_rounded) or net_rounded)
                    side   = _pos.get('side', 'SELL')
                    if entry > 0:
                        if side == 'SELL':
                            pct = (entry - net_rounded) / entry * 100
                        else:
                            pct = (net_rounded - entry) / entry * 100
                        # 수익률 배너 갱신
                        banner = getattr(self, 'profit_alert_banner', None)
                        if banner and hasattr(banner, 'update_pct'):
                            banner.update_pct(pct)

                        # [FIX-SC1] SpecialFillWatcher 목표가 감시
                        # on_net_price_update 미호출 시 10초 타이머가 절대 시작 안 됨
                        try:
                            from combo_order_special_condition import SpecialFillWatcher
                            SpecialFillWatcher.get().on_net_price_update(
                                oid, net_rounded)
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

        # [FIX-N] tid 충돌 수정: oid * 10 + leg_index
        tid  = _POS_STREAM_BASE + oid * 10 + i
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

    [v2.4] 틱 스냅 적용: 개별 레그 mid를 틱 단위로 정렬 후 합산.
    미수신 레그 bid/ask는 Last → Close 순으로 폴백 (None 방지).
    모든 레그 시세가 완전히 없으면 None 반환.
    """
    ticks = self._pos_mid_ticks.get(oid, {})
    net   = 0.0
    for i, leg in enumerate(legs):
        leg_ticks = ticks.get(i, {})
        bid = leg_ticks.get(1)
        ask = leg_ticks.get(2)

        if bid is None or ask is None:
            # 폴백: Last(4) → Close(9) 순으로 사용
            last  = leg_ticks.get(4)
            close = leg_ticks.get(9)
            mid   = last if last is not None and last > 0 else close
            if mid is None or mid <= 0:
                return None  # 폴백도 없으면 포기
        else:
            mid = (bid + ask) / 2.0

        # [v2.4] 레그 mid를 틱 단위 스냅
        from combo_order_chaser import _get_tick_size, _snap_to_tick
        tick      = _get_tick_size(mid)
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
            symbol,
            str(leg.get('cp', '')),
            float(leg.get('strike', 0)),
            str(leg.get('expiry', '')),
        )
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
            pos['status'] = '보유'   # [FIX-S] "체결완료" → "보유"
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