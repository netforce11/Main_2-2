from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, time
from pathlib import Path

_SAVE_PATH = Path(__file__).parent / "night_alert_templates.json"

_SAMPLE_MINUTES = 15   # 구간 시작 몇 분 전부터 샘플링

@dataclass
class NightSlot:
    start_hhmm:    str   = "01:00"
    end_hhmm:      str   = "02:00"
    opt_type:      str   = "P"
    multiplier:    float = 5.0
    abs_price:     float = 0.0
    otm_pct:       float = 0.0   # 0=ATM, 0.35=ATM 대비 0.35% OTM 행사가 기준
    pre_alert_pct: float = 0.0   # 0=비활성, 예: multiplier=3.0 → 2.7 설정 시 270%에서 사전경보
    max_alerts:    int   = 10    # 한 구간 내 최대 알람 횟수 (0=무제한)
    no_dup:        bool  = True  # True=같은 구간 중복 알람 억제
    enabled:       bool  = True
    label:         str   = ""
    # ✅ NEW: 장외 구간 — ES 선물 지수 기반
    use_es:        bool  = False   # True=ES 선물 기준 행사가 (-25pt 오프셋)
    es_offset:     float = -25.0   # ES에서 뺄 포인트 (기본 -25pt)
    # 런타임 전용 — JSON 직렬화 제외
    base_prem:     float = field(default=0.0, compare=False, repr=False)
    base_strike:   float = field(default=0.0, compare=False, repr=False)
    base_set_at:   str   = field(default="",  compare=False, repr=False)
    # ✅ NEW: 런타임 추적 행사가 (UI 표시용)
    tracked_strike: float = field(default=0.0, compare=False, repr=False)
    tracked_type:   str   = field(default="",  compare=False, repr=False)

    def is_in_sampling_window(self) -> bool:
        """구간 시작 _SAMPLE_MINUTES분 전 ~ 시작 직전 = 기준가 수집 구간."""
        if not self.enabled:
            return False
        try:
            sh, sm = map(int, self.start_hhmm.split(":"))
        except ValueError:
            return False
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        start_min = sh * 60 + sm

        # ✅ FIX BUG4: 자정 경계 일반화
        # 남은 시간(분) 계산: 시작이 현재보다 이전처럼 보이면 +1440(익일)로 보정
        diff = start_min - now_min
        if diff <= -(_SAMPLE_MINUTES + 1):
            diff += 1440   # 현재가 23시, 시작이 00~01시인 경우
        elif diff > 23 * 60:
            diff -= 1440

        return 0 < diff <= _SAMPLE_MINUTES

    def is_active_now(self) -> bool:
        if not self.enabled:
            return False
        now = datetime.now().time()
        try:
            sh, sm = map(int, self.start_hhmm.split(":"))
            eh, em = map(int, self.end_hhmm.split(":"))
        except ValueError:
            return False
        t_start = time(sh, sm)
        t_end   = time(eh, em)
        if t_start <= t_end:
            return t_start <= now <= t_end
        return now >= t_start or now <= t_end

    def should_fire(self, current_prem: float, fallback_base: float = 0.0) -> bool:
        """base_prem이 세팅된 경우 우선 사용, 없으면 fallback_base 사용."""
        base = self.base_prem if self.base_prem > 0 else fallback_base
        if base <= 0:
            return False
        pct    = current_prem / base
        mult_ok = pct >= self.multiplier
        abs_ok  = (self.abs_price > 0 and current_prem >= self.abs_price)
        return mult_ok or abs_ok

@dataclass
class NightAlertConfig:
    slots:         list = field(default_factory=list)
    base_type:     str  = "open"
    atm_auto:      bool = True
    atm_manual:    float = 0.0
    tg_fmt:        str  = "🚨 [{slot}] {opt_type}{strike} {pct:.0f}% 급등"
    snapshot_done: bool = False
    snapshot_time: str  = ""

    @classmethod
    def default(cls):
        return cls(slots=[
            NightSlot("00:30","02:00","P", 5.0, label="구간1"),
            NightSlot("02:00","03:30","P", 3.0, label="구간2"),
            NightSlot("03:30","05:00","P", 2.0, label="구간3"),
        ])

def load_config() -> NightAlertConfig:
    if not _SAVE_PATH.exists():
        return NightAlertConfig.default()
    try:
        raw   = json.loads(_SAVE_PATH.read_text(encoding="utf-8"))
        _RT   = {"base_prem", "base_strike", "base_set_at", "tracked_strike", "tracked_type"}
        slots = [NightSlot(**{k: v for k, v in s.items() if k not in _RT})
                 for s in raw.get("slots", [])]
        return NightAlertConfig(
            slots=slots,
            base_type=raw.get("base_type", "open"),
            atm_auto=raw.get("atm_auto", True),
            atm_manual=raw.get("atm_manual", 0.0),
            tg_fmt=raw.get("tg_fmt", "🚨 [{slot}] {opt_type}{strike} {pct:.0f}% 급등"),
            snapshot_done=raw.get("snapshot_done", False),   # ✅ FIX BUG8
            snapshot_time=raw.get("snapshot_time", ""),      # ✅ FIX BUG8
        )
    except Exception:
        return NightAlertConfig.default()

def save_config(cfg: NightAlertConfig) -> None:
    # 런타임 전용 필드 제외하고 직렬화
    _RT  = {"base_prem", "base_strike", "base_set_at", "tracked_strike", "tracked_type"}
    data = asdict(cfg)
    for s in data.get("slots", []):
        for k in _RT:
            s.pop(k, None)
    _SAVE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def get_active_slots(cfg: NightAlertConfig) -> list:
    return [s for s in cfg.slots if s.is_active_now()]


def parse_hhmm(raw: str) -> str:
    """
    ✅ NEW: 숫자만 입력해도 HH:MM 형식으로 변환.
    "0930" → "09:30", "1100" → "11:00", "09:30" → "09:30"
    """
    s = raw.strip().replace(":", "")
    if len(s) == 3:
        s = "0" + s   # "930" → "0930"
    if len(s) == 4 and s.isdigit():
        return f"{s[:2]}:{s[2:]}"
    # 이미 "HH:MM" 형식이면 그대로
    if len(raw.strip()) == 5 and raw.strip()[2] == ":":
        return raw.strip()
    return raw.strip()


def make_preset(preset_id: int) -> list:
    """
    preset_id=1 : 22:30~05:00, 30분 단위 야간 (13구간)
    preset_id=2 : 22:30~05:00, 45분 단위 야간 (10구간)
    preset_id=3 : 장외 10:00~22:30, 30분 단위 (ES 기준, -25pt 오프셋)
                  10:00~13:00 / 13:00~18:00 / 18:00~22:30 세 블록
    """
    if preset_id == 3:
        return _make_daytime_preset()

    start_h, start_m = 22, 30
    end_h,   end_m   =  5,  0
    step = 30 if preset_id == 1 else 45

    slots = []
    cur = start_h * 60 + start_m
    end = end_h   * 60 + end_m + 24 * 60   # 익일 05:00

    idx = 1
    while cur < end:
        nxt = min(cur + step, end)
        s_hh, s_mm = divmod(cur % (24 * 60), 60)
        e_hh, e_mm = divmod(nxt % (24 * 60), 60)
        slots.append(NightSlot(
            start_hhmm=f"{s_hh:02d}:{s_mm:02d}",
            end_hhmm  =f"{e_hh:02d}:{e_mm:02d}",
            opt_type="P", multiplier=3.0, max_alerts=10, no_dup=True,
            label=f"T{preset_id}-{idx}",
        ))
        cur = nxt
        idx += 1
    return slots


def _make_daytime_preset() -> list:
    """
    ✅ NEW: 장외 템플릿 — 10:00~22:30, 30분씩
    ES 선물 기준, -25pt 오프셋으로 행사가 탐색
    블록: 10:00~13:00 / 13:00~18:00 / 18:00~22:30
    """
    blocks = [
        (10*60,   13*60),   # 10:00~13:00
        (13*60,   18*60),   # 13:00~18:00
        (18*60,   22*60+30),# 18:00~22:30
    ]
    step = 30
    slots = []
    idx = 1
    for blk_start, blk_end in blocks:
        cur = blk_start
        while cur < blk_end:
            nxt = min(cur + step, blk_end)
            s_hh, s_mm = divmod(cur,  60)
            e_hh, e_mm = divmod(nxt,  60)
            slots.append(NightSlot(
                start_hhmm = f"{s_hh:02d}:{s_mm:02d}",
                end_hhmm   = f"{e_hh:02d}:{e_mm:02d}",
                opt_type   = "P",
                multiplier = 3.0,
                max_alerts = 10,
                no_dup     = True,
                use_es     = True,    # ✅ ES 선물 기준
                es_offset  = -25.0,   # ✅ ES - 25pt = 행사가
                label      = f"D-{idx}",
            ))
            cur = nxt
            idx += 1
    return slots
