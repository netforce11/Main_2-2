"""
sleep_order_config.py — 수면 예약 주문 설정 저장소  v3.0
════════════════════════════════════════════════════════════════
v3.0 변경 (신규 필드):
  [섹션 B] 급락 캐치
    spike_use_own_schedule  전용 시간대 사용 여부
    spike_start             급락 캐치 전용 감시 시작 (HH:MM, ET)
    spike_end               급락 캐치 전용 감시 종료 (HH:MM, ET)
    spike_ref_mode          기준가 산출 방식 ('time' | 'tick')
    spike_ref_minutes       시간 기준 lookback 분 (mode=time)

  [섹션 C] 자동 매도 (체결 즉시 익절)
    auto_sell_enabled       자동 매도 ON/OFF
    auto_sell_mode          주문가 방식 ('fixed' | 'multiplier')
    auto_sell_fixed_price   고정 매도가 (mode=fixed)
    auto_sell_multiplier    매수 체결가 × 배수 (mode=multiplier)
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import json
from pathlib import Path

try:
    from core import SAVE_DIR
except ImportError:
    SAVE_DIR = Path(".")

_CONFIG_FILE = SAVE_DIR / "sleep_order_settings.json"

_DEFAULTS: dict = {
    # ── 섹션 A: 예약 주문 ──────────────────────────────────────
    "schedule_start":   "04:40",
    "schedule_end":     "05:14",
    "expiry_offset":    1,
    "strike_dist_min":  0.60,
    "strike_dist_max":  0.95,
    "spread_width":     20,
    "target_price_1":   0.50,
    "target_price_2":   0.40,
    "max_budget":       100,
    "schedule_enabled": False,

    # ── 섹션 B: 급락 캐치 ──────────────────────────────────────
    "spike_enabled":        False,

    # [신규] 급락 캐치 전용 시간 설정
    "spike_use_own_schedule": True,   # True → spike_start/end 사용
                                      # False → schedule_start/end 공유
    "spike_start":          "16:53",  # 급락 감시 시작 (ET)
    "spike_end":            "05:14",  # 급락 감시 종료 (ET)

    # [신규] 기준가 산출 방식
    "spike_ref_mode":       "time",   # "time" | "tick"
    "spike_ref_minutes":    3,        # lookback 분 (mode=time)
    "tick_window":          7,        # 틱 평균 개수 (mode=tick)

    # 급락 판단 임계값
    "drop_ratio":           40,       # % (40 → 40% 이상 급락)
    "abs_floor":            0.20,     # 절대가 상한

    # 주문 방식
    "order_mode":           "ask+1",  # 'ask+1' | 'fixed'
    "fixed_price":          0.15,
    "spike_budget":         100,

    # 정정 루프
    "modify_wait_sec":      2,
    "modify_step":          0.05,
    "modify_max_count":     3,
    "modify_price_cap":     0.30,

    # ── 섹션 C: 자동 매도 (체결 즉시 익절) ────────────────────
    "auto_sell_enabled":    False,
    "auto_sell_mode":       "multiplier",  # "fixed" | "multiplier"
    "auto_sell_fixed_price":  2.50,        # mode=fixed 일 때 매도 지정가
    "auto_sell_multiplier":   3.0,         # mode=multiplier: 체결가 × N배

    # ── 수익률 필터 ────────────────────────────────────────────
    "roi_min":              0,
    "roi_max":              1200,

    # ── Aggressive Entry ──────────────────────────────────────
    "aggressive_entry":     True,
    "aggressive_ticks":     1,

    # ── 취소 후 쿨다운 ────────────────────────────────────────
    "cancel_cooldown_sec":  120,

    # ── 드라이런 ──────────────────────────────────────────────
    "dry_run":              False,
}


class SleepOrderConfigStore:
    """수면 예약 주문 설정 싱글톤 저장소."""
    _instance: "SleepOrderConfigStore | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data: dict = {}
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        import copy
        self._data = copy.deepcopy(_DEFAULTS)
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception as e:
                print(f"[SleepOrderConfig] 로드 실패: {e}")

    def save(self) -> None:
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[SleepOrderConfig] 저장 실패: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value

    def all(self) -> dict:
        import copy
        return copy.deepcopy(self._data)

    # ── 섹션 A 프로퍼티 ───────────────────────────────────────
    @property
    def schedule_start(self) -> str:
        return str(self._data.get("schedule_start", "04:40"))

    @property
    def schedule_end(self) -> str:
        return str(self._data.get("schedule_end", "05:14"))

    @property
    def expiry_offset(self) -> int:
        return int(self._data.get("expiry_offset", 1))

    @property
    def strike_dist_min(self) -> float:
        return float(self._data.get("strike_dist_min", 0.60))

    @property
    def strike_dist_max(self) -> float:
        return float(self._data.get("strike_dist_max", 0.95))

    @property
    def spread_width(self) -> int:
        return int(self._data.get("spread_width", 20))

    @property
    def target_price_1(self) -> float:
        return float(self._data.get("target_price_1", 0.50))

    @property
    def target_price_2(self) -> float:
        return float(self._data.get("target_price_2", 0.40))

    @property
    def max_budget(self) -> int:
        return int(self._data.get("max_budget", 100))

    @property
    def schedule_enabled(self) -> bool:
        return bool(self._data.get("schedule_enabled", False))

    # ── 섹션 B 프로퍼티 ───────────────────────────────────────
    @property
    def spike_enabled(self) -> bool:
        return bool(self._data.get("spike_enabled", False))

    @property
    def spike_use_own_schedule(self) -> bool:
        return bool(self._data.get("spike_use_own_schedule", True))

    @property
    def spike_start(self) -> str:
        """급락 캐치 전용 감시 시작. spike_use_own_schedule=False 면 schedule_start 반환."""
        if not self.spike_use_own_schedule:
            return self.schedule_start
        return str(self._data.get("spike_start", "16:53"))

    @property
    def spike_end(self) -> str:
        """급락 캐치 전용 감시 종료. spike_use_own_schedule=False 면 schedule_end 반환."""
        if not self.spike_use_own_schedule:
            return self.schedule_end
        return str(self._data.get("spike_end", "05:14"))

    @property
    def spike_ref_mode(self) -> str:
        return str(self._data.get("spike_ref_mode", "time"))

    @property
    def spike_ref_minutes(self) -> int:
        return int(self._data.get("spike_ref_minutes", 3))

    @property
    def tick_window(self) -> int:
        return int(self._data.get("tick_window", 7))

    @property
    def drop_ratio(self) -> int:
        return int(self._data.get("drop_ratio", 40))

    @property
    def abs_floor(self) -> float:
        return float(self._data.get("abs_floor", 0.20))

    @property
    def order_mode(self) -> str:
        return str(self._data.get("order_mode", "ask+1"))

    @property
    def fixed_price(self) -> float:
        return float(self._data.get("fixed_price", 0.15))

    @property
    def spike_budget(self) -> int:
        return int(self._data.get("spike_budget", 100))

    @property
    def modify_wait_sec(self) -> int:
        return int(self._data.get("modify_wait_sec", 2))

    @property
    def modify_step(self) -> float:
        return float(self._data.get("modify_step", 0.05))

    @property
    def modify_max_count(self) -> int:
        return int(self._data.get("modify_max_count", 3))

    @property
    def modify_price_cap(self) -> float:
        return float(self._data.get("modify_price_cap", 0.30))

    # ── 섹션 C 프로퍼티 ───────────────────────────────────────
    @property
    def auto_sell_enabled(self) -> bool:
        return bool(self._data.get("auto_sell_enabled", False))

    @property
    def auto_sell_mode(self) -> str:
        return str(self._data.get("auto_sell_mode", "multiplier"))

    @property
    def auto_sell_fixed_price(self) -> float:
        return float(self._data.get("auto_sell_fixed_price", 2.50))

    @property
    def auto_sell_multiplier(self) -> float:
        return float(self._data.get("auto_sell_multiplier", 3.0))

    # ── 기타 프로퍼티 ─────────────────────────────────────────
    @property
    def roi_min(self) -> int:
        return int(self._data.get("roi_min", 0))

    @property
    def roi_max(self) -> int:
        return int(self._data.get("roi_max", 1200))

    @property
    def dry_run(self) -> bool:
        return bool(self._data.get("dry_run", False))

    @property
    def aggressive_entry(self) -> bool:
        return bool(self._data.get("aggressive_entry", True))

    @property
    def aggressive_ticks(self) -> int:
        return int(self._data.get("aggressive_ticks", 1))

    @property
    def cancel_cooldown_sec(self) -> int:
        return int(self._data.get("cancel_cooldown_sec", 120))


# 전역 싱글톤
sleep_cfg = SleepOrderConfigStore()
