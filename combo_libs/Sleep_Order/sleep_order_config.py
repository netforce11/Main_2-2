"""
sleep_order_config.py — 수면 예약 주문 설정 저장소  v1.0
════════════════════════════════════════════════════════════════
Main_config.py 의 MainConfigStore 패턴 동일하게 적용.
JSON 파일로 영구 저장, 앱 재시작 후에도 유지.

설정 항목:
  [섹션 A] 예약 주문
    schedule_start      감시 시작 시간 (HH:MM)
    schedule_end        감시 종료 시간 (HH:MM)
    expiry_offset       만기 오프셋 (0=D+0, 1=D+1, 2=D+2)
    strike_dist_min     행사가 거리 하한 (%)
    strike_dist_max     행사가 거리 상한 (%)
    spread_width        스프레드 폭 ($)
    target_price_1      목표 net price 1
    target_price_2      목표 net price 2
    max_budget          최대 투자 금액 ($)
    schedule_enabled    예약 감시 ON/OFF

  [섹션 B] 급락 캐치
    tick_window         틱 평균 개수 N (5~10)
    drop_ratio          급락 판단 비율 (%)
    abs_floor           절대가 상한
    order_mode          주문 방식 ('ask+1' | 'fixed')
    fixed_price         고정 주문가 (order_mode='fixed' 일 때)
    modify_wait_sec     정정 대기 시간 (초)
    modify_step         정정 단위 ($)
    modify_max_count    최대 정정 횟수
    modify_price_cap    정정 상한가 ($)
    spike_budget        급락 캐치 최대 금액 ($)
    spike_enabled       급락 캐치 ON/OFF
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
    "expiry_offset":    1,          # D+1
    "strike_dist_min":  0.60,       # %
    "strike_dist_max":  0.95,       # %
    "spread_width":     20,         # $
    "target_price_1":   0.50,
    "target_price_2":   0.40,
    "max_budget":       100,        # $
    "schedule_enabled": False,

    # ── 섹션 B: 급락 캐치 ──────────────────────────────────────
    "tick_window":        7,        # 틱 평균 개수
    "drop_ratio":         40,       # % (40 → 40% 이상 급락)
    "abs_floor":          0.20,     # 절대가 상한
    "order_mode":         "ask+1",  # 'ask+1' | 'fixed'
    "fixed_price":        0.15,
    "modify_wait_sec":    2,        # 정정 대기 초
    "modify_step":        0.05,     # 정정 단위
    "modify_max_count":   3,        # 최대 정정 횟수
    "modify_price_cap":   0.30,     # 정정 상한가
    "spike_budget":       100,      # $
    "spike_enabled":      False,

    # ── 수익률 필터 ────────────────────────────────────────────
    # 만기 최대 수익률 범위 (%). 범위 밖 스프레드는 주문/감시 대상 제외.
    # 계산식: (spread_width×100 - 진입가×100) / (진입가×100) × 100
    # 예) 진입가 $1.60, 폭 $20 → (2000-160)/160×100 = 1150%  → 500~1200 통과
    "roi_min":            500,   # 최소 수익률 (%)
    "roi_max":            1200,  # 최대 수익률 (%)

    # ── 드라이런 (테스트 모드) ─────────────────────────────────
    # True = 실제 주문 전송 안 하고 로그 + TG 알림만 발송
    "dry_run":            False,
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
        """전체 설정값 복사본 반환."""
        import copy
        return copy.deepcopy(self._data)

    # ── 편의 프로퍼티 ──────────────────────────────────────────
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

    @property
    def spike_budget(self) -> int:
        return int(self._data.get("spike_budget", 100))

    @property
    def spike_enabled(self) -> bool:
        return bool(self._data.get("spike_enabled", False))

    @property
    def roi_min(self) -> int:
        return int(self._data.get("roi_min", 500))

    @property
    def roi_max(self) -> int:
        return int(self._data.get("roi_max", 1200))

    @property
    def dry_run(self) -> bool:
        return bool(self._data.get("dry_run", False))


# 전역 싱글톤
sleep_cfg = SleepOrderConfigStore()
