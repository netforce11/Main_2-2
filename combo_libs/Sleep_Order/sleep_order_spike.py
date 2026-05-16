"""
sleep_order_spike.py — 급락 캐치 감시 + 주문 정정  v2.0
════════════════════════════════════════════════════════════════
v2.0 변경:
  [1] 급락 캐치 전용 시간대 독립 지원
      → SpikeCatcher.on_price_update() 에서 spike_start/spike_end 사용
      → sleep_cfg.spike_use_own_schedule 로 전환

  [2] 기준가 산출 방식 이원화
      spike_ref_mode = "time"  → PriceTimeRefTracker (분 기준 lookback)
                       "tick"  → PriceRefTracker (기존 틱 평균, 하위 호환)

      PriceTimeRefTracker:
        · 첫 수신 후 spike_ref_minutes 분간의 가격을 deque 로 보관
        · ref_price = 그 기간 중 최고가 (고점 기준으로 낙폭 판단)
        · 기간이 지난 데이터는 자동 만료

  [3] 자동 매도 — 체결 즉시 익절 주문
      SpikeCatcher.on_filled(fill_price) 로 체결가 수신
      auto_sell_mode = "fixed"      → auto_sell_fixed_price 지정가 매도
                       "multiplier" → fill_price × auto_sell_multiplier 매도
      ref._sleep_place_sell_order(legs, lmt_price, qty, strat, tag) 콜백 필요

역할:
  · PriceTimeRefTracker : 시간 기준 기준가 산출 (신규)
  · PriceRefTracker     : 틱 평균 기준가 산출 (기존 유지)
  · SpikeCatcher        : 급락 감지 → 즉시 주문 → 미체결 시 자동 정정
                          → 체결 즉시 자동 매도
  · SleepSpikeWatcher   : 스프레드별 SpikeCatcher 관리 싱글톤

연동:
  · SleepOrderWatcher._scan_and_check() 에서 on_price_update() 호출
  · combo_order_callbacks.py Filled 에서 on_filled(oid, fill_price) 호출
  · combo_order_callbacks.py Cancelled 에서 on_cancelled(oid) 호출
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
import time as _time
from collections import deque
from typing import Dict, List, Optional, Tuple


def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[SleepSpike] TG 실패: {e}")


def _tick_size(price: float) -> float:
    return 0.10 if price >= 3.0 else 0.05


def _in_time_window_now(start: str, end: str) -> bool:
    """
    현재 ET 시각이 start~end 범위 안인지 확인.
    자정 넘기는 시간대(예: 16:53~05:14) 지원.
    """
    try:
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
        now   = datetime.now(tz) if tz else datetime.utcnow()
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        now_m  = now.hour * 60 + now.minute
        s_m    = sh * 60 + sm
        e_m    = eh * 60 + em
        if s_m <= e_m:
            return s_m <= now_m <= e_m
        else:
            return now_m >= s_m or now_m <= e_m
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# PriceRefTracker — 틱 N개 평균 기준가 (기존, mode=tick)
# ══════════════════════════════════════════════════════════════

class PriceRefTracker:
    """최근 N개 틱 가격 평균을 ref_price 로 제공."""

    def __init__(self, window: int = 7):
        self._window = max(1, window)
        self._prices: deque = deque(maxlen=self._window)
        self._lock   = threading.Lock()

    def set_window(self, window: int) -> None:
        with self._lock:
            self._window = max(1, window)
            self._prices = deque(list(self._prices)[-self._window:],
                                 maxlen=self._window)

    def update(self, price: float) -> None:
        if price <= 0:
            return
        with self._lock:
            self._prices.append(price)

    @property
    def ref_price(self) -> Optional[float]:
        with self._lock:
            if not self._prices:
                return None
            return sum(self._prices) / len(self._prices)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._prices)

    def reset(self) -> None:
        with self._lock:
            self._prices.clear()


# ══════════════════════════════════════════════════════════════
# PriceTimeRefTracker — 시간 기준 기준가 (신규, mode=time)
# ══════════════════════════════════════════════════════════════

class PriceTimeRefTracker:
    """
    spike_ref_minutes 분간 수신된 가격 중 최고가를 ref_price 로 사용.

    동작 방식:
      · 첫 update() 호출부터 spike_ref_minutes 분이 경과하면
        그 기간의 최고가가 확정 기준가가 됨
      · 기준가 확정 후에는 변경되지 않음 (스냅샷 고정)
      · reset() 호출 시 처음부터 다시 수집

    예) spike_ref_minutes=3, 3분 전 고가=$5.60 → ref_price=5.60
        현재가=$0.80, drop_ratio=40% → (1-0.80/5.60)=85.7% >= 40% → 발동
    """

    def __init__(self, minutes: int = 3):
        self._minutes  = max(1, minutes)
        # (timestamp, price) 리스트
        self._samples: List[Tuple[float, float]] = []
        self._ref_fixed: Optional[float] = None   # 확정된 기준가
        self._lock = threading.Lock()

    def set_minutes(self, minutes: int) -> None:
        with self._lock:
            self._minutes = max(1, minutes)
            # 분 변경 시 재수집
            self._ref_fixed = None
            self._prune()

    def update(self, price: float) -> None:
        if price <= 0:
            return
        with self._lock:
            if self._ref_fixed is not None:
                return  # 기준가 확정 후 업데이트 불필요
            now = _time.monotonic()
            self._samples.append((now, price))
            self._prune()
            # 첫 샘플 이후 N분 경과 시 기준가 확정
            if self._samples:
                elapsed = now - self._samples[0][0]
                if elapsed >= self._minutes * 60:
                    self._ref_fixed = max(p for _, p in self._samples)
                    print(f"[SpikeTracker] 기준가 확정 ${self._ref_fixed:.2f}"
                          f"  ({len(self._samples)}샘플 / {elapsed/60:.1f}분)")

    def _prune(self) -> None:
        """_minutes 분 초과 샘플 제거 (lock 내부에서만 호출)."""
        if not self._samples:
            return
        cutoff = _time.monotonic() - self._minutes * 60
        self._samples = [(t, p) for t, p in self._samples if t >= cutoff]

    @property
    def ref_price(self) -> Optional[float]:
        """
        확정 기준가 반환.
        아직 N분 미경과 시 None (데이터 수집 중).
        """
        with self._lock:
            return self._ref_fixed

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._samples)

    @property
    def seconds_until_ready(self) -> float:
        """기준가 확정까지 남은 초. 이미 확정되면 0."""
        with self._lock:
            if self._ref_fixed is not None:
                return 0.0
            if not self._samples:
                return float(self._minutes * 60)
            elapsed = _time.monotonic() - self._samples[0][0]
            return max(0.0, self._minutes * 60 - elapsed)

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._ref_fixed = None


# ══════════════════════════════════════════════════════════════
# SpikeCatcher — 스프레드 1개 급락 감시 + 주문 정정 + 자동 매도
# ══════════════════════════════════════════════════════════════

class SpikeCatcher:
    """
    스프레드 1개의 급락을 감시.
    급락 감지 → 즉시 매수 → 미체결 시 정정 루프
              → 체결 즉시 자동 매도 (auto_sell_enabled=True)
    """

    def __init__(self, spread_key: str, ref: object,
                 legs: list, strat: str = ""):
        self._key   = spread_key
        self._ref   = ref
        self._legs  = legs
        self._strat = strat
        self._fired = False
        self._oid:            Optional[int]   = None
        self._sell_oid:       Optional[int]   = None
        self._current_lmt:    float           = 0.0
        self._qty:            int             = 0
        self._modify_count:   int             = 0
        self._modify_timer:   Optional[threading.Timer] = None
        self._lock = threading.Lock()

        # 기준가 트래커 — mode 에 따라 생성
        self._tracker_tick = PriceRefTracker()
        self._tracker_time = PriceTimeRefTracker()

    # ── 설정 리로드 ─────────────────────────────────────────────
    def reconfigure(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        self._tracker_tick.set_window(sleep_cfg.tick_window)
        self._tracker_time.set_minutes(sleep_cfg.spike_ref_minutes)

    def _active_tracker(self):
        """현재 설정에 맞는 트래커 반환."""
        from Sleep_Order.sleep_order_config import sleep_cfg
        if sleep_cfg.spike_ref_mode == "time":
            return self._tracker_time
        return self._tracker_tick

    # ── 가격 업데이트 진입점 ────────────────────────────────────
    def on_price_update(self, net_price: float,
                        ask_price: float = 0.0) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        # 두 트래커 모두 업데이트 (모드 전환 시 데이터 유지)
        self._tracker_tick.update(net_price)
        self._tracker_time.update(net_price)

        if self._fired:
            return
        if not sleep_cfg.spike_enabled:
            return

        # ── [v2.0] 급락 캐치 전용 시간대 체크 ─────────────────
        if not _in_time_window_now(sleep_cfg.spike_start,
                                   sleep_cfg.spike_end):
            return

        ref_price = self._active_tracker().ref_price
        if ref_price is None:
            secs = getattr(self._active_tracker(), 'seconds_until_ready', None)
            if secs and secs > 0:
                pass  # 수집 중 — 정상
            return

        drop_threshold = sleep_cfg.drop_ratio / 100.0
        drop_ratio     = net_price / ref_price if ref_price > 0 else 1.0

        is_spike = (
            (1.0 - drop_ratio) >= drop_threshold
            and net_price <= sleep_cfg.abs_floor
        )

        if is_spike:
            self._fire(net_price, ask_price, ref_price)

    # ── 매수 주문 발사 ──────────────────────────────────────────
    def _fire(self, net_price: float, ask_price: float,
              ref_price: float) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        with self._lock:
            if self._fired:
                return
            self._fired = True

        # 주문가 결정
        if sleep_cfg.order_mode == "ask+1":
            tick = _tick_size(ask_price if ask_price > 0 else net_price)
            lmt  = round((ask_price if ask_price > 0 else net_price) + tick, 2)
        else:
            lmt = sleep_cfg.fixed_price

        cost_per = lmt * 100
        qty = max(1, int(sleep_cfg.spike_budget // cost_per)) if cost_per > 0 else 1

        mode_label = (f"시간기준 {sleep_cfg.spike_ref_minutes}분"
                      if sleep_cfg.spike_ref_mode == "time"
                      else f"틱평균 {sleep_cfg.tick_window}개")

        print(f"[SleepSpike] ⚡ 급락 캐치 발동  key={self._key}"
              f"  [{mode_label}] ref=${ref_price:.2f} → net=${net_price:.2f}"
              f"  lmt=${lmt:.2f}  qty={qty}")

        # ── [드라이런] ─────────────────────────────────────────
        if sleep_cfg.dry_run:
            auto_sell_note = self._auto_sell_preview(lmt)
            dry_msg = (
                "🧪 <b>[드라이런] 급락 캐치 시뮬레이션</b>\n"
                f"전략: {self._strat}\n"
                f"기준가 산출: {mode_label}\n"
                f"기준가: ${ref_price:.2f} → 현재: ${net_price:.2f}"
                f"  (낙폭: {(1-net_price/ref_price)*100:.1f}%)\n"
                f"매수 주문가: <b>${lmt:.2f}</b>  수량: {qty}계약\n"
                + auto_sell_note
                + "\n⚠ 드라이런 모드 — 실제 주문 미전송"
            )
            _tg(dry_msg)
            print(f"[SleepSpike][DRYRUN] 매수 시뮬  lmt=${lmt:.2f}  qty={qty}")
            return

        oid = self._place_order(lmt, qty)
        if oid is None:
            self._fired = False
            return

        with self._lock:
            self._oid         = oid
            self._current_lmt = lmt
            self._qty         = qty
            self._modify_count = 0

        auto_sell_note = self._auto_sell_preview(lmt)
        _tg(
            f"⚡ <b>급락 캐치 발동</b>\n"
            f"전략: {self._strat}\n"
            f"기준가 산출: {mode_label}\n"
            f"기준가: ${ref_price:.2f} → 현재: ${net_price:.2f}"
            f"  (낙폭: {(1-net_price/ref_price)*100:.1f}%)\n"
            f"매수 주문가: <b>${lmt:.2f}</b>  수량: {qty}계약\n"
            + auto_sell_note
            + f"\nOID: {oid}"
        )

        self._arm_modify_timer()

    def _auto_sell_preview(self, buy_lmt: float) -> str:
        """TG 메시지용 자동 매도 예상가 텍스트."""
        from Sleep_Order.sleep_order_config import sleep_cfg
        if not sleep_cfg.auto_sell_enabled:
            return "자동 매도: OFF"
        if sleep_cfg.auto_sell_mode == "fixed":
            return f"자동 매도: 고정 ${sleep_cfg.auto_sell_fixed_price:.2f}"
        sell_lmt = round(buy_lmt * sleep_cfg.auto_sell_multiplier, 2)
        return (f"자동 매도: 체결가 × {sleep_cfg.auto_sell_multiplier}배"
                f"  ≈ ${sell_lmt:.2f} (체결가 기준 확정)")

    # ── 정정 루프 ───────────────────────────────────────────────
    def _arm_modify_timer(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg
        t = threading.Timer(sleep_cfg.modify_wait_sec, self._try_modify)
        t.daemon = True
        t.start()
        with self._lock:
            self._modify_timer = t

    def _try_modify(self) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        with self._lock:
            if self._oid is None:
                return
            if self._modify_count >= sleep_cfg.modify_max_count:
                _tg(
                    f"🚨 <b>급락 캐치 수동 대응 필요</b>\n"
                    f"전략: {self._strat}\n"
                    f"최대 정정 {sleep_cfg.modify_max_count}회 후 미체결\n"
                    f"OID: {self._oid}"
                )
                return

            new_lmt = round(self._current_lmt + sleep_cfg.modify_step, 2)
            if new_lmt > sleep_cfg.modify_price_cap:
                _tg(
                    f"⛔ <b>급락 캐치 정정 상한 도달</b>\n"
                    f"전략: {self._strat}\n"
                    f"상한가: ${sleep_cfg.modify_price_cap:.2f}\n"
                    f"OID: {self._oid}"
                )
                return

            self._modify_count += 1
            count = self._modify_count
            oid   = self._oid
            prev  = self._current_lmt
            self._current_lmt = new_lmt

        self._modify_order(oid, new_lmt)
        _tg(
            f"⚠️ <b>급락 캐치 정정 {count}차</b>\n"
            f"전략: {self._strat}\n"
            f"${prev:.2f} → <b>${new_lmt:.2f}</b>\n"
            f"OID: {oid}"
        )
        self._arm_modify_timer()

    # ── IBKR 매수 주문/정정 ─────────────────────────────────────
    def _place_order(self, lmt: float, qty: int) -> Optional[int]:
        try:
            fn = getattr(self._ref, '_sleep_place_order', None)
            if fn is None:
                print(f"[SleepSpike] ❌ _sleep_place_order 콜백 없음")
                return None
            return fn(legs=self._legs, lmt_price=lmt, qty=qty,
                      strat=self._strat, tag="SPIKE_CATCH")
        except Exception as e:
            print(f"[SleepSpike] ❌ 매수 주문 실패: {e}")
            return None

    def _modify_order(self, oid: int, new_lmt: float) -> None:
        try:
            fn = getattr(self._ref, '_sleep_modify_order', None)
            if fn:
                fn(oid=oid, new_lmt=new_lmt, legs=self._legs,
                   qty=self._qty, strat=self._strat)
        except Exception as e:
            print(f"[SleepSpike] ❌ 정정 실패 OID={oid}: {e}")

    # ── [v2.0 신규] 체결 즉시 자동 매도 ────────────────────────
    def _place_sell_order(self, fill_price: float) -> None:
        """
        매수 체결 직후 호출.
        fill_price: 실제 체결가 (0이면 주문가 사용)
        """
        from Sleep_Order.sleep_order_config import sleep_cfg

        if not sleep_cfg.auto_sell_enabled:
            return

        buy_price = fill_price if fill_price > 0 else self._current_lmt

        if sleep_cfg.auto_sell_mode == "fixed":
            sell_lmt = sleep_cfg.auto_sell_fixed_price
        else:
            sell_lmt = round(buy_price * sleep_cfg.auto_sell_multiplier, 2)
            # 틱 단위 정렬
            tick = _tick_size(sell_lmt)
            sell_lmt = round(round(sell_lmt / tick) * tick, 2)

        qty = self._qty

        print(f"[SleepSpike] 💰 자동 매도 주문  key={self._key}"
              f"  buy=${buy_price:.2f} → sell=${sell_lmt:.2f}"
              f"  qty={qty}"
              f"  mode={sleep_cfg.auto_sell_mode}")

        if sleep_cfg.dry_run:
            _tg(
                f"🧪 <b>[드라이런] 자동 매도 시뮬</b>\n"
                f"전략: {self._strat}\n"
                f"매수 체결가: ${buy_price:.2f}\n"
                f"매도 주문가: <b>${sell_lmt:.2f}</b>  수량: {qty}계약\n"
                f"⚠ 드라이런 — 실제 주문 미전송"
            )
            return

        try:
            fn = getattr(self._ref, '_sleep_place_sell_order', None)
            if fn is None:
                print(f"[SleepSpike] ❌ _sleep_place_sell_order 콜백 없음")
                _tg(
                    f"❌ <b>자동 매도 실패</b>\n"
                    f"전략: {self._strat}\n"
                    f"_sleep_place_sell_order 콜백 없음\n"
                    f"수동 매도 필요! qty={qty}  목표=${sell_lmt:.2f}"
                )
                return
            sell_oid = fn(legs=self._legs, lmt_price=sell_lmt,
                          qty=qty, strat=self._strat, tag="SPIKE_AUTO_SELL")
            with self._lock:
                self._sell_oid = sell_oid

            _tg(
                f"💰 <b>자동 매도 주문 전송</b>\n"
                f"전략: {self._strat}\n"
                f"매수 체결가: ${buy_price:.2f}\n"
                f"매도 주문가: <b>${sell_lmt:.2f}</b>  수량: {qty}계약\n"
                f"OID: {sell_oid}"
            )
        except Exception as e:
            print(f"[SleepSpike] ❌ 자동 매도 주문 실패: {e}")
            _tg(
                f"❌ <b>자동 매도 주문 실패</b>\n"
                f"전략: {self._strat}  오류: {e}\n"
                f"수동 매도 필요! qty={qty}  목표=${sell_lmt:.2f}"
            )

    # ── 외부에서 체결/취소 통보 ─────────────────────────────────
    def on_filled(self, fill_price: float = 0.0) -> None:
        """
        매수 체결 완료 시 호출.
        fill_price: 실제 체결가 (콜백에서 수신한 avgFillPrice)
        → 정정 타이머 중단 + 자동 매도 주문
        """
        with self._lock:
            oid = self._oid
            self._oid = None
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None

        if oid is not None:
            # 매수 체결 → 즉시 자동 매도
            self._place_sell_order(fill_price)

    def on_cancelled(self) -> None:
        """취소 시 → 재시도 허용."""
        with self._lock:
            self._oid   = None
            self._fired = False
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None

    def reset(self) -> None:
        """감시 세션 초기화."""
        with self._lock:
            self._fired        = False
            self._oid          = None
            self._sell_oid     = None
            self._modify_count = 0
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None
        self._tracker_tick.reset()
        self._tracker_time.reset()


# ══════════════════════════════════════════════════════════════
# SleepSpikeWatcher — 스프레드별 SpikeCatcher 관리 싱글톤
# ══════════════════════════════════════════════════════════════

class SleepSpikeWatcher:
    """싱글톤. SpikeCatcher 딕셔너리 관리 + 외부 콜백 라우팅."""

    _inst: Optional["SleepSpikeWatcher"] = None
    _mu   = threading.Lock()

    def __new__(cls):
        with cls._mu:
            if cls._inst is None:
                o = super().__new__(cls)
                o._catchers: Dict[str, SpikeCatcher] = {}
                cls._inst = o
        return cls._inst

    @classmethod
    def get(cls) -> "SleepSpikeWatcher":
        return cls()

    def register(self, spread_key: str, ref: object,
                 legs: list, strat: str = "") -> SpikeCatcher:
        with self._mu:
            if spread_key not in self._catchers:
                c = SpikeCatcher(spread_key, ref, legs, strat)
                c.reconfigure()
                self._catchers[spread_key] = c
            return self._catchers[spread_key]

    def on_price_update(self, spread_key: str,
                        net_price: float, ask_price: float = 0.0) -> None:
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_price_update(net_price, ask_price)

    def on_filled(self, spread_key: str,
                  fill_price: float = 0.0) -> None:
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_filled(fill_price)

    def on_cancelled(self, spread_key: str) -> None:
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_cancelled()

    def unwatch_by_oid(self, oid: int,
                       fill_price: float = 0.0) -> None:
        """
        OID 기준으로 체결 통보.
        combo_order_callbacks.py 의 Filled 핸들러에서 호출.
        fill_price: avgFillPrice (없으면 0.0)
        """
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_filled(fill_price)
                return
            # 매도 주문 체결 시 (sell_oid 매칭)
            if c._sell_oid == oid:
                print(f"[SleepSpike] ✅ 자동 매도 체결  OID={oid}")
                _tg(
                    f"✅ <b>자동 매도 체결 완료</b>\n"
                    f"전략: {c._strat}\n"
                    f"체결가: ${fill_price:.2f}  OID: {oid}"
                )
                with c._lock:
                    c._sell_oid = None
                return

    def unwatch_cancelled_by_oid(self, oid: int) -> None:
        """OID 기준으로 취소 통보."""
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_cancelled()
                return

    def reset_all(self) -> None:
        with self._mu:
            for c in self._catchers.values():
                c.reset()
            self._catchers.clear()

    def reconfigure_all(self) -> None:
        """설정 변경 시 모든 catcher 에 새 설정 적용."""
        with self._mu:
            for c in self._catchers.values():
                c.reconfigure()
