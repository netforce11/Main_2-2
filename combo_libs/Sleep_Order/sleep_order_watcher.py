"""
sleep_order_watcher.py — 수면 예약 주문 감시 루프  v2.2
════════════════════════════════════════════════════════════════
v2.2 변경:
  · unwatch_by_oid(oid, fill_price) 호출 시 fill_price 전달
    → SpikeCatcher.on_filled(fill_price) → 자동 매도 트리거
  · _scan_and_check() 에서 SleepSpikeWatcher 시간 체크 제거
    → 시간 체크는 SpikeCatcher.on_price_update() 내부에서
       spike_start/spike_end 기준으로 독립 수행

v2.1 변경:
  · start(): ref._sleep_subscribe_chain() 호출
  · stop(): ref._sleep_unsubscribe_chain() 호출
  · 가격 소스 우선순위: 실시간 mid > _chain_put 3초 캐시(폴백)

외부 연동:
  combo_ui_synthetic_panel.py 의 SyntheticStatusPanel 에서
  SleepOrderWatcher.get().toggle(ref) 호출

연동 메서드 (ref 객체에 주입 필요):
  ref._sleep_subscribe_chain()
  ref._sleep_unsubscribe_chain()
  ref._sleep_place_order(legs, lmt_price, qty, strat, tag) → oid
  ref._sleep_place_sell_order(legs, lmt_price, qty, strat, tag) → oid  ← [신규]
  ref._sleep_modify_order(oid, new_lmt, legs, qty, strat)
  ref._sleep_get_chain(expiry_offset) → [{strike, put_net, put_ask, legs}, ...]
  ref._sleep_get_underlying_price()   → float

combo_order_callbacks.py 연동 (변경 사항):
  Filled  → SleepSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avgFillPrice)
  Cancel  → SleepSpikeWatcher.get().unwatch_cancelled_by_oid(oid)
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[SleepWatcher] TG 실패: {e}")


def _calc_entry_price(net_rounded: float, sleep_cfg) -> float:
    """
    Aggressive Entry ON 시 현재가에 N틱을 더해 주문가 결정.
    틱 크기: net < $3.00 → $0.05 / net >= $3.00 → $0.10
    """
    if not sleep_cfg.aggressive_entry:
        return net_rounded
    tick  = 0.10 if net_rounded >= 3.00 else 0.05
    ticks = max(1, int(sleep_cfg.aggressive_ticks))
    return round(net_rounded + tick * ticks, 2)


# ══════════════════════════════════════════════════════════════
# SleepOrderWatcher
# ══════════════════════════════════════════════════════════════

class SleepOrderWatcher(QObject):
    """싱글톤 QObject. QTimer 로 1초마다 시간/가격 조건 체크."""

    status_changed = pyqtSignal(str)

    _inst: Optional["SleepOrderWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls, parent=None):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                cls._inst = o
        return cls._inst

    def __init__(self, parent=None):
        if getattr(self, '_initialized', False):
            return
        super().__init__(parent)
        self._initialized  = True
        self._ref          = None
        self._active       = False
        self._fired        = False
        self._last_range_reset: float = 0.0
        self._timer        = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    @classmethod
    def get(cls) -> "SleepOrderWatcher":
        with cls._mu:
            if cls._inst is None:
                inst = super(SleepOrderWatcher, cls).__new__(cls)
                inst._initialized = False
                cls._inst = inst
                inst.__init__()
        return cls._inst

    # ── 외부 API ────────────────────────────────────────────────

    def toggle(self, ref: object) -> bool:
        if self._active:
            self.stop()
            return False
        else:
            self.start(ref)
            return True

    def start(self, ref: object) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        from Sleep_Order.sleep_order_spike   import SleepSpikeWatcher

        self._ref    = ref
        self._active = True
        self._fired  = False
        self._last_range_reset = 0.0
        SleepSpikeWatcher.get().reset_all()

        if hasattr(ref, '_sleep_subscribe_chain'):
            ref._sleep_subscribe_chain()

        # 급락 캐치 전용 시간 표시
        spike_time = (f"{sleep_cfg.spike_start}~{sleep_cfg.spike_end}"
                      if sleep_cfg.spike_use_own_schedule
                      else f"{sleep_cfg.schedule_start}~{sleep_cfg.schedule_end} (공유)")
        ref_mode = (f"시간기준 {sleep_cfg.spike_ref_minutes}분"
                    if sleep_cfg.spike_ref_mode == "time"
                    else f"틱평균 {sleep_cfg.tick_window}개")

        msg = (
            f"🌙 감시 시작\n"
            f"예약주문: {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}"
            f"  D+{sleep_cfg.expiry_offset}\n"
            f"급락캐치: {spike_time}  [{ref_mode}]"
        )
        self.status_changed.emit(
            f"🟢 감시중  {sleep_cfg.schedule_start}~{sleep_cfg.schedule_end}")
        _tg(msg)
        print(f"[SleepWatcher] {msg}")
        self._timer.start()

    def stop(self, reason: str = "수동 중지") -> None:
        self._active = False
        self._timer.stop()

        ref = getattr(self, '_ref', None)
        if ref is not None and hasattr(ref, '_sleep_unsubscribe_chain'):
            ref._sleep_unsubscribe_chain()

        self.status_changed.emit("🌙 예약 주문")
        print(f"[SleepWatcher] 감시 종료: {reason}")

    @property
    def is_active(self) -> bool:
        return self._active

    # ── 1초 틱 ──────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self._active:
            return

        from Sleep_Order.sleep_order_config import sleep_cfg

        in_window = self._in_time_window(
            sleep_cfg.schedule_start, sleep_cfg.schedule_end)

        if not in_window:
            if self._fired:
                self.stop(reason="주문 완료 후 시간 종료")
            else:
                now_str = self._now_et_str()
                if self._past_end(sleep_cfg.schedule_end):
                    _tg(
                        f"⏰ <b>수면 예약 시간 종료</b>\n"
                        f"{sleep_cfg.schedule_end} 도달  미주문 상태\n"
                        f"ET {now_str}"
                    )
                    self.stop(reason="시간 초과 미주문")
            return

        if self._fired:
            return

        self._scan_and_check()

    # ── 체인 스캔 ────────────────────────────────────────────────

    def _scan_and_check(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        from Sleep_Order.sleep_order_spike   import SleepSpikeWatcher
        import time

        ref = self._ref
        if ref is None:
            return

        # ── [안전장치 1] 시간대 이중 체크 ──────────────────────
        if not self._in_time_window(sleep_cfg.schedule_start,
                                    sleep_cfg.schedule_end):
            print("[SleepWatcher] ⛔ 시간대 외 _scan_and_check 차단")
            return

        # ── [안전장치 2] 체인 데이터 유효성 체크 ───────────────
        put_strikes = getattr(ref, '_put_strikes', [])
        chain_put   = getattr(ref, '_chain_put', {})
        if not put_strikes or not chain_put:
            print("[SleepWatcher] ⚠ 체인 데이터 없음 — 동기화 대기")
            return
        valid_prices = [v for v in chain_put.values() if v and v > 0]
        if len(valid_prices) < 3:
            print(f"[SleepWatcher] ⚠ 유효 체인 가격 부족 ({len(valid_prices)}개) — 대기")
            return

        # ── [안전장치 3] 미체결 주문 존재 시 신규 주문 차단 ────
        pending_oid    = getattr(ref, '_chaser_current_oid', None)
        pending_status = getattr(ref, '_pending_position', {}).get('status', '')
        if pending_oid is not None and pending_status == '미체결':
            print(f"[SleepWatcher] ⏳ 미체결 주문 존재"
                  f"  OID={pending_oid} — 신규 주문 차단")
            return

        # 지수 현재가
        try:
            und_price = ref._sleep_get_underlying_price()
        except Exception as e:
            print(f"[SleepWatcher] 지수 조회 실패: {e}")
            return
        if not und_price or und_price <= 0:
            print("[SleepWatcher] ⚠ 지수 가격 없음 — 대기")
            return

        # ── 1분 보정: 범위 이탈 행사가 제거 ───────────────────
        now_ts = time.monotonic()
        if now_ts - self._last_range_reset >= 60:
            self._last_range_reset = now_ts
            self._evict_out_of_range_catchers(und_price, sleep_cfg)

        # 체인 조회
        try:
            chain = ref._sleep_get_chain(sleep_cfg.expiry_offset)
        except Exception as e:
            print(f"[SleepWatcher] 체인 조회 실패: {e}")
            return
        if not chain:
            print("[SleepWatcher] ⚠ 스프레드 체인 없음 — 대기")
            return

        dist_min = sleep_cfg.strike_dist_min / 100.0
        dist_max = sleep_cfg.strike_dist_max / 100.0
        roi_min  = sleep_cfg.roi_min
        roi_max  = sleep_cfg.roi_max
        sw       = sleep_cfg.spread_width
        tp1      = sleep_cfg.target_price_1
        tp2      = sleep_cfg.target_price_2

        for item in chain:
            strike    = float(item.get("strike", 0))
            net_price = float(item.get("put_net", 0))
            ask_price = float(item.get("put_ask", 0))
            legs      = item.get("legs", [])

            if strike <= 0 or not legs:
                continue

            # 조건 1: 행사가 거리 범위
            dist = abs(und_price - strike) / und_price
            if not (dist_min <= dist <= dist_max):
                print(f"[DEBUG] ⛔ 거리탈락  strike={strike}"
                      f"  dist={dist*100:.3f}%"
                      f"  허용={sleep_cfg.strike_dist_min}~{sleep_cfg.strike_dist_max}%")
                continue

            # 조건 2: 수익률 필터
            if net_price > 0:
                max_profit_dollar = (sw - net_price) * 100
                if max_profit_dollar <= 0:
                    print(f"[DEBUG] ⛔ ROI계산불가  strike={strike}"
                          f"  net=${net_price:.2f}")
                    continue
                roi_pct = (max_profit_dollar / (net_price * 100)) * 100
                if not (roi_min <= roi_pct <= roi_max):
                    print(f"[SleepWatcher] ⛳ ROI 필터 탈락"
                          f"  strike={strike}  net=${net_price:.2f}"
                          f"  ROI={roi_pct:.0f}%  허용={roi_min}~{roi_max}%")
                    continue

            # 급락 캐치 등록 + 가격 전달
            # [v2.2] 시간 체크는 SpikeCatcher 내부에서 spike_start/spike_end 기준으로 수행
            spread_key = f"{strike}_{sleep_cfg.expiry_offset}"
            strat      = f"PUT_SPREAD D+{sleep_cfg.expiry_offset} {strike}"
            SleepSpikeWatcher.get().register(spread_key, ref, legs, strat)
            SleepSpikeWatcher.get().on_price_update(spread_key, net_price, ask_price)

            # 조건 3: 예약 주문 가격 체크
            if self._fired:
                continue

            net_rounded = round(net_price * 20) / 20

            if net_rounded > tp1:
                print(f"[DEBUG] ⛔ 목표가초과  strike={strike}"
                      f"  net=${net_price:.2f}"
                      f"  rounded=${net_rounded:.2f}"
                      f"  tp1=${tp1:.2f}")
                continue

            matched_target = tp2 if net_rounded <= tp2 else tp1
            lmt      = _calc_entry_price(net_rounded, sleep_cfg)
            cost_per = lmt * 100
            qty      = max(1, int(sleep_cfg.max_budget // cost_per))

            print(f"[DEBUG] ✅ 주문조건충족  strike={strike}"
                  f"  net=${net_rounded:.2f}  lmt=${lmt:.2f}"
                  f"  matched=tp{'2' if matched_target == tp2 else '1'}"
                  f"  qty={qty}  총비용=${qty * lmt * 100:.0f}")

            self._fire_order(legs, net_rounded, qty, strat)
            break

    def _evict_out_of_range_catchers(self, und_price: float,
                                     sleep_cfg) -> None:
        from Sleep_Order.sleep_order_spike import SleepSpikeWatcher

        dist_min = sleep_cfg.strike_dist_min / 100.0
        dist_max = sleep_cfg.strike_dist_max / 100.0

        spike_watcher = SleepSpikeWatcher.get()
        with spike_watcher._mu:
            keys_to_remove = []
            for key in list(spike_watcher._catchers):
                try:
                    strike  = float(key.split("_")[0])
                    dist    = abs(und_price - strike) / und_price
                    catcher = spike_watcher._catchers[key]
                    if not (dist_min <= dist <= dist_max) and not catcher._fired:
                        keys_to_remove.append(key)
                except Exception:
                    pass
            for k in keys_to_remove:
                del spike_watcher._catchers[k]

        if keys_to_remove:
            print(f"[SleepWatcher] 📍 1분 보정 — 범위 이탈 제거: {keys_to_remove}")

    def _fire_order(self, legs: list, net_price: float,
                    qty: int, strat: str) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        ref = self._ref
        if ref is None:
            return

        # 발사 직전 시간대 최종 확인
        if not self._in_time_window(sleep_cfg.schedule_start,
                                    sleep_cfg.schedule_end):
            print("[SleepWatcher] ⛔ 시간대 외 _fire_order 차단")
            _tg("⛔ <b>예약 주문 차단</b>\n시간대 외 발동 시도 — 주문 미전송")
            return

        lmt      = _calc_entry_price(net_price, sleep_cfg)
        cost_per = lmt * 100
        qty      = max(1, int(sleep_cfg.max_budget // cost_per))
        total_cost = round(lmt * qty * 100, 2)
        agg_tag    = (f" (+{sleep_cfg.aggressive_ticks}틱 보정)"
                      if sleep_cfg.aggressive_entry else "")

        if sleep_cfg.dry_run:
            self._fired = True
            msg = (
                f"🧪 <b>[드라이런] 예약 주문 시뮬레이션</b>\n"
                f"전략: {strat}\n"
                f"현재가: ${net_price:.2f}  →  주문가: <b>${lmt:.2f}</b>{agg_tag}\n"
                f"수량: {qty}계약  총 금액: ${total_cost}\n"
                f"⚠ 드라이런 모드 — 실제 주문 미전송"
            )
            _tg(msg)
            print(f"[SleepWatcher][DRYRUN] 주문 시뮬"
                  f"  net=${net_price:.2f}  lmt=${lmt:.2f}  qty={qty}")
            self.status_changed.emit(f"🧪 드라이런  ${lmt:.2f} × {qty}")
            return

        try:
            oid = ref._sleep_place_order(
                legs=legs, lmt_price=lmt, qty=qty,
                strat=strat, tag="SLEEP_ORDER")
        except Exception as e:
            print(f"[SleepWatcher] ❌ 주문 실패: {e}")
            _tg(f"❌ <b>수면 예약 주문 실패</b>\n오류: {e}")
            return

        if oid is None:
            return

        self._fired = True
        print(f"[SleepWatcher] ✅ 예약 주문 실행  OID={oid}"
              f"  net=${net_price:.2f}  lmt=${lmt:.2f}{agg_tag}"
              f"  qty={qty}  총=${total_cost}")
        _tg(
            f"🌙 <b>수면 예약 주문 실행</b>\n"
            f"전략: {strat}\n"
            f"현재가: ${net_price:.2f}  →  주문가: <b>${lmt:.2f}</b>{agg_tag}\n"
            f"수량: {qty}계약  총 금액: ${total_cost}\n"
            f"OID: {oid}"
        )
        self.status_changed.emit(f"✅ 주문완료  ${lmt:.2f} × {qty}")

    # ── 시간 유틸 ────────────────────────────────────────────────

    @staticmethod
    def _now_et() -> tuple:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            try:
                from backports.zoneinfo import ZoneInfo
                tz = ZoneInfo("America/New_York")
            except Exception:
                tz = None
        now = datetime.now(tz) if tz else datetime.utcnow()
        return now.hour, now.minute

    @staticmethod
    def _now_et_str() -> str:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            tz = None
        now = datetime.now(tz) if tz else datetime.utcnow()
        return now.strftime("%H:%M")

    def _in_time_window(self, start: str, end: str) -> bool:
        try:
            sh, sm = map(int, start.split(":"))
            eh, em = map(int, end.split(":"))
            h, m   = self._now_et()
            now_m  = h * 60 + m
            s_m    = sh * 60 + sm
            e_m    = eh * 60 + em
            if s_m <= e_m:
                return s_m <= now_m <= e_m
            else:
                return now_m >= s_m or now_m <= e_m
        except Exception:
            return False

    def _past_end(self, end: str) -> bool:
        try:
            from Sleep_Order.sleep_order_config import sleep_cfg
            sh, sm = map(int, sleep_cfg.schedule_start.split(":"))
            eh, em = map(int, end.split(":"))
            h, m   = self._now_et()
            now_m  = h * 60 + m
            s_m    = sh * 60 + sm
            e_m    = eh * 60 + em
            if s_m <= e_m:
                return now_m > e_m
            else:
                if now_m >= s_m:
                    return False
                return now_m > e_m
        except Exception:
            return False
