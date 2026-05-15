"""
sleep_order_spike.py — 급락 캐치 감시 + 주문 정정  v1.0
════════════════════════════════════════════════════════════════
역할:
  · PriceRefTracker  : 틱 N개 평균으로 기준가 산출
  · SpikeCatcher     : 급락 감지 → 즉시 주문 → 미체결 시 자동 정정
  · SleepSpikeWatcher: 스프레드별 SpikeCatcher 관리 싱글톤

급락 판단:
  평균 틱 N개 대비 drop_ratio% 이상 하락 AND net_price ≤ abs_floor

주문 방식 (order_mode):
  'ask+1'  : 현재 ask + 1호가 (틱 1개 위)
  'fixed'  : fixed_price 고정값

정정 루프:
  체결 안 되면 modify_wait_sec 초 대기 후
  lmt_price += modify_step 씩 올림 (최대 modify_max_count 회, modify_price_cap 초과 금지)

연동:
  · SleepOrderWatcher._on_chain_price_update() 에서 on_price_update() 호출
  · combo_order_callbacks.py Filled/Cancelled 에서 unwatch(oid) 호출
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Dict, Optional


def _tg(msg: str) -> None:
    try:
        from telegram_bot.tg_client import TelegramClient
        TelegramClient.get().send("order_confirm", msg)
    except Exception as e:
        print(f"[SleepSpike] TG 실패: {e}")


def _tick_size(price: float) -> float:
    return 0.10 if price >= 3.0 else 0.05


# ══════════════════════════════════════════════════════════════
# PriceRefTracker — 틱 N개 평균 기준가 산출
# ══════════════════════════════════════════════════════════════

class PriceRefTracker:
    """
    최근 N개 틱 가격을 deque 로 관리.
    평균값을 기준가(ref_price)로 제공.
    """

    def __init__(self, window: int = 7):
        self._window = max(1, window)
        self._prices: deque = deque(maxlen=self._window)
        self._lock   = threading.Lock()

    def set_window(self, window: int) -> None:
        with self._lock:
            self._window = max(1, window)
            # maxlen 변경: 새 deque 로 재생성
            self._prices = deque(list(self._prices)[-self._window:],
                                 maxlen=self._window)

    def update(self, price: float) -> None:
        if price <= 0:
            return
        with self._lock:
            self._prices.append(price)

    @property
    def ref_price(self) -> Optional[float]:
        """틱 N개 평균. 데이터 부족 시 None."""
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
# SpikeCatcher — 스프레드 1개 급락 감시 + 주문 정정
# ══════════════════════════════════════════════════════════════

class SpikeCatcher:
    """
    스프레드 1개의 급락을 감시.
    급락 감지 → 즉시 주문 → 미체결 시 정정 루프.
    """

    def __init__(self, spread_key: str, ref: object,
                 legs: list, strat: str = ""):
        self._key    = spread_key
        self._ref    = ref          # SyntheticStatusPanel 의 부모 (combo grid)
        self._legs   = legs
        self._strat  = strat
        self._fired  = False
        self._oid: Optional[int] = None
        self._modify_count = 0
        self._modify_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self.tracker = PriceRefTracker()

    # ── 설정 리로드 ─────────────────────────────────────────────
    def reconfigure(self, window: int) -> None:
        self.tracker.set_window(window)

    # ── 가격 업데이트 진입점 ────────────────────────────────────
    def on_price_update(self, net_price: float,
                        ask_price: float = 0.0) -> None:
        """
        매 틱 호출.
        net_price : 스프레드 net mid price
        ask_price : ask (order_mode='ask+1' 에 사용)
        """
        from Sleep_Order.sleep_order_config import sleep_cfg

        self.tracker.update(net_price)

        if self._fired:
            return
        if not sleep_cfg.spike_enabled:
            return

        # ── [안전장치] 설정 시간대 외 발동 절대 차단 ───────────
        if not _in_time_window_now(sleep_cfg.schedule_start,
                                   sleep_cfg.schedule_end):
            return

        ref = self.tracker.ref_price
        if ref is None:
            return  # 데이터 부족

        drop_threshold = sleep_cfg.drop_ratio / 100.0
        drop_ratio     = net_price / ref if ref > 0 else 1.0

        is_spike = (
            (1.0 - drop_ratio) >= drop_threshold   # N% 이상 급락
            and net_price <= sleep_cfg.abs_floor    # 절대가 조건
        )

        if is_spike:
            self._fire(net_price, ask_price, ref)

    # ── 주문 발사 ───────────────────────────────────────────────
    def _fire(self, net_price: float, ask_price: float,
              ref_price: float) -> None:
        from Sleep_Order.sleep_order_config import sleep_cfg

        with self._lock:
            if self._fired:
                return
            self._fired = True

        # 주문가 결정
        if sleep_cfg.order_mode == "ask+1":
            tick   = _tick_size(ask_price if ask_price > 0 else net_price)
            lmt    = round((ask_price if ask_price > 0 else net_price) + tick, 2)
        else:
            lmt = sleep_cfg.fixed_price

        # $100 한도 수량 계산
        cost_per = lmt * 100
        qty = max(1, int(sleep_cfg.spike_budget // cost_per)) if cost_per > 0 else 1

        print(f"[SleepSpike] ⚡ 급락 캐치 발동  key={self._key}"
              f"  ref=${ref_price:.2f} → net=${net_price:.2f}"
              f"  lmt=${lmt:.2f}  qty={qty}")

        # ── [드라이런] 실제 주문 차단 ──────────────────────────
        if sleep_cfg.dry_run:
            dry_msg = (
                "🧪 <b>[드라이런] 급락 캐치 시뮬레이션</b>\n"
                + "전략: " + self._strat + "\n"
                + f"기준가: ${ref_price:.2f} → 현재: ${net_price:.2f}\n"
                + f"주문가: <b>${lmt:.2f}</b>  수량: {qty}계약\n"
                + "⚠ 드라이런 모드 — 실제 주문 미전송"
            )
            _tg(dry_msg)
            print(f"[SleepSpike][DRYRUN] 주문 시뮬  lmt=${lmt:.2f}  qty={qty}")
            return

        oid = self._place_order(lmt, qty)
        if oid is None:
            self._fired = False  # 주문 실패 → 재시도 허용
            return

        self._oid          = oid
        self._current_lmt  = lmt
        self._qty          = qty
        self._modify_count = 0

        _tg(
            f"⚡ <b>급락 캐치 발동</b>\n"
            f"전략: {self._strat}\n"
            f"기준가: ${ref_price:.2f} → 현재: ${net_price:.2f}\n"
            f"주문가: <b>${lmt:.2f}</b>  수량: {qty}계약\n"
            f"OID: {oid}"
        )

        # 정정 대기 타이머 시작
        self._arm_modify_timer()

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
                return  # 이미 체결/취소됨
            if self._modify_count >= sleep_cfg.modify_max_count:
                # 최대 정정 횟수 초과
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
            count  = self._modify_count
            oid    = self._oid
            strat  = self._strat
            prev   = self._current_lmt
            self._current_lmt = new_lmt

        # lock 밖에서 실행
        self._modify_order(oid, new_lmt)

        _tg(
            f"⚠️ <b>급락 캐치 정정 {count}차</b>\n"
            f"전략: {strat}\n"
            f"${prev:.2f} → <b>${new_lmt:.2f}</b>\n"
            f"OID: {oid}"
        )

        self._arm_modify_timer()

    # ── IBKR 주문/정정 ──────────────────────────────────────────
    def _place_order(self, lmt: float, qty: int) -> Optional[int]:
        """
        BAG 주문 실제 전송.
        실제 환경에서는 combo_order_bag 경로를 통해 placeOrder 호출.
        여기서는 ref 객체에 주입된 _sleep_place_order 콜백 사용.
        """
        try:
            fn = getattr(self._ref, '_sleep_place_order', None)
            if fn is None:
                print(f"[SleepSpike] ❌ _sleep_place_order 콜백 없음")
                return None
            oid = fn(
                legs=self._legs,
                lmt_price=lmt,
                qty=qty,
                strat=self._strat,
                tag="SPIKE_CATCH"
            )
            return oid
        except Exception as e:
            print(f"[SleepSpike] ❌ 주문 실패: {e}")
            return None

    def _modify_order(self, oid: int, new_lmt: float) -> None:
        try:
            fn = getattr(self._ref, '_sleep_modify_order', None)
            if fn:
                fn(oid=oid, new_lmt=new_lmt, legs=self._legs,
                   qty=self._qty, strat=self._strat)
        except Exception as e:
            print(f"[SleepSpike] ❌ 정정 실패 OID={oid}: {e}")

    # ── 외부에서 체결/취소 통보 ─────────────────────────────────
    def on_filled(self) -> None:
        """체결 완료 시 호출 → 정정 타이머 중단."""
        with self._lock:
            self._oid = None
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None

    def on_cancelled(self) -> None:
        """취소 시 호출 → 재시도 허용."""
        with self._lock:
            self._oid    = None
            self._fired  = False
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None

    def reset(self) -> None:
        """감시 세션 초기화 (새 시간대 시작 시)."""
        with self._lock:
            self._fired  = False
            self._oid    = None
            self._modify_count = 0
            if self._modify_timer:
                self._modify_timer.cancel()
                self._modify_timer = None
        self.tracker.reset()


# ══════════════════════════════════════════════════════════════
# SleepSpikeWatcher — 스프레드별 SpikeCatcher 관리 싱글톤
# ══════════════════════════════════════════════════════════════

class SleepSpikeWatcher:
    """
    싱글톤.
    SleepOrderWatcher 가 체인 스캔 중 발견한 스프레드마다
    SpikeCatcher 를 등록하고 가격 업데이트를 전달.
    """
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
        """스프레드 등록 (없으면 생성, 있으면 반환)."""
        from Sleep_Order.sleep_order_config import sleep_cfg
        with self._mu:
            if spread_key not in self._catchers:
                c = SpikeCatcher(spread_key, ref, legs, strat)
                c.reconfigure(sleep_cfg.tick_window)
                self._catchers[spread_key] = c
            return self._catchers[spread_key]

    def on_price_update(self, spread_key: str,
                        net_price: float, ask_price: float = 0.0) -> None:
        """SleepOrderWatcher 의 틱 핸들러에서 호출."""
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_price_update(net_price, ask_price)

    def on_filled(self, spread_key: str) -> None:
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_filled()

    def on_cancelled(self, spread_key: str) -> None:
        with self._mu:
            c = self._catchers.get(spread_key)
        if c:
            c.on_cancelled()

    def unwatch_by_oid(self, oid: int) -> None:
        """OID 기준으로 체결/취소 통보 (combo_order_callbacks 연동)."""
        with self._mu:
            catchers = list(self._catchers.values())
        for c in catchers:
            if c._oid == oid:
                c.on_filled()
                break

    def reset_all(self) -> None:
        """새 감시 세션 시작 시 모든 catcher 초기화."""
        with self._mu:
            for c in self._catchers.values():
                c.reset()
            self._catchers.clear()

    def reconfigure_all(self) -> None:
        """설정 변경 시 모든 catcher 에 새 window 적용."""
        from Sleep_Order.sleep_order_config import sleep_cfg
        with self._mu:
            for c in self._catchers.values():
                c.reconfigure(sleep_cfg.tick_window)


# ── 시간 유틸 (스레드 안전, 별도 import 불필요) ──────────────────

def _in_time_window_now(start: str, end: str) -> bool:
    """
    현재 ET 시각이 start~end 범위 안인지 확인.
    자정 넘기는 시간대(예: 16:53~05:14) 지원.
    SpikeCatcher 가 별도 스레드에서 호출하므로 독립 함수로 분리.
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
            # 자정 넘김 (예: 16:53 ~ 05:14)
            return now_m >= s_m or now_m <= e_m
    except Exception:
        return False