# Sleep Order 패치 v3.0 — 변경 요약 및 적용 가이드

> 작성일: 2026-05  
> 상태: 코드 완성 / 드라이런 테스트 필요

---

## 1. 변경 파일 목록

| 파일 | 버전 | 주요 변경 |
|------|------|----------|
| `sleep_order_config.py` | v2.0 → v3.0 | 신규 필드 6개 추가 |
| `sleep_order_spike.py` | v1.0 → v2.0 | 시간 기준가 트래커, 전용 시간대, 자동 매도 |
| `sleep_order_watcher.py` | v2.1 → v2.2 | fill_price 전달, spike 시간 체크 위임 |
| `sleep_order_ui_patch.py` | 신규 | 설정 UI 위젯 2개 (SpikeScheduleWidget, AutoSellWidget) |

---

## 2. 신규 설정 필드

### 섹션 B2 — 급락 캐치 시간 / 기준가

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `spike_use_own_schedule` | bool | True | True → spike_start/end 사용, False → 예약주문 시간 공유 |
| `spike_start` | str | "16:53" | 급락 감시 시작 (ET, 자정 넘김 지원) |
| `spike_end` | str | "05:14" | 급락 감시 종료 (ET) |
| `spike_ref_mode` | str | "time" | `"time"` = 분 기준 고가 / `"tick"` = 틱 평균 |
| `spike_ref_minutes` | int | 3 | 기준가 lookback 분 (mode=time) |

### 섹션 C — 자동 매도

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `auto_sell_enabled` | bool | False | 체결 즉시 익절 매도 ON/OFF |
| `auto_sell_mode` | str | "multiplier" | `"fixed"` = 고정가 / `"multiplier"` = 체결가 × 배수 |
| `auto_sell_fixed_price` | float | 2.50 | 고정 매도가 (mode=fixed) |
| `auto_sell_multiplier` | float | 3.0 | 매수 체결가 × 배수 (mode=multiplier) |

---

## 3. 기준가 산출 방식 상세

### mode = "time" (신규 권장)

```
감시 시작
  └─ PriceTimeRefTracker.update(net_price) 매 1초 호출
       └─ spike_ref_minutes 분간 수신 가격을 deque 보관
            └─ N분 경과 시 → 기간 내 최고가 = ref_price (확정, 이후 고정)

급락 판단:
  (1 - 현재가 / ref_price) >= drop_ratio%
  AND 현재가 <= abs_floor
```

예시: `spike_ref_minutes=3`, `drop_ratio=40`, `abs_floor=1.0`
- 3분 전 고가 $5.60 → ref_price = $5.60
- 현재가 $0.80 → 낙폭 = (1 - 0.80/5.60) = 85.7% ≥ 40% → **발동**

### mode = "tick" (기존 유지)

최근 `tick_window`개 틱 가격의 평균을 ref_price 로 사용.

---

## 4. 자동 매도 흐름

```
급락 캐치 매수 체결 (combo_order_callbacks.py Filled)
  └─ SleepSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avgFillPrice)  ← [변경]
       └─ SpikeCatcher.on_filled(fill_price)
            └─ 정정 타이머 중단
            └─ _place_sell_order(fill_price)
                 ├─ mode=fixed      → sell_lmt = auto_sell_fixed_price
                 └─ mode=multiplier → sell_lmt = fill_price × auto_sell_multiplier
                      └─ ref._sleep_place_sell_order(legs, sell_lmt, qty, ...)
```

---

## 5. 적용 절차

### 5-1. 파일 교체

```
Sleep_Order/
  sleep_order_config.py   ← 교체
  sleep_order_spike.py    ← 교체
  sleep_order_watcher.py  ← 교체
  sleep_order_ui_patch.py ← 신규 추가
```

### 5-2. sleep_order_ui.py 수정

기존 설정 탭 `__init__()` 끝부분에 추가:

```python
from Sleep_Order.sleep_order_ui_patch import SpikeScheduleWidget, AutoSellWidget

self._spike_schedule_w = SpikeScheduleWidget()
self._auto_sell_w      = AutoSellWidget()
layout.addWidget(self._spike_schedule_w)
layout.addWidget(self._auto_sell_w)
```

저장 버튼 핸들러에 추가:
```python
self._spike_schedule_w.save()
self._auto_sell_w.save()
```

로드 시 추가:
```python
self._spike_schedule_w.load()
self._auto_sell_w.load()
```

### 5-3. combo_order_callbacks.py 수정

```python
# Filled 핸들러
# 기존
SleepSpikeWatcher.get().unwatch_by_oid(oid)
# 변경
SleepSpikeWatcher.get().unwatch_by_oid(oid, fill_price=avgFillPrice)

# Cancelled 핸들러
# 기존
SleepSpikeWatcher.get().unwatch_by_oid(oid)
# 변경
SleepSpikeWatcher.get().unwatch_cancelled_by_oid(oid)
```

### 5-4. ref 객체에 콜백 추가 (sleep_order_mixin.py)

```python
def _sleep_place_sell_order(self, legs, lmt_price, qty,
                             strat="", tag="") -> Optional[int]:
    """급락 캐치 자동 익절 매도 주문."""
    return self._sleep_place_order(
        legs=legs, lmt_price=lmt_price, qty=qty,
        strat=strat, tag=tag,
        action="SELL"   # 기존 _sleep_place_order 에 action 파라미터 추가 필요
    )
```

> `_sleep_place_order` 에 `action` 파라미터가 없으면 SELL 전용 메서드를 별도 작성.

---

## 6. 드라이런 테스트 체크리스트

```
□ spike_use_own_schedule=True → spike_start/end 시간대에만 발동 확인
□ spike_ref_mode="time", spike_ref_minutes=3
    → 3분 후 기준가 확정 로그 출력 확인
    → "[SpikeTracker] 기준가 확정 $X.XX (N샘플 / 3.0분)"
□ drop_ratio/abs_floor 조건 충족 시 드라이런 TG 수신 확인
□ auto_sell_enabled=True, dry_run=True
    → 매수 드라이런 직후 "자동 매도 시뮬" TG 수신 확인
□ 기존 예약주문(schedule_start/end) 동작 무영향 확인
```

---

## 7. 주의사항

- `PriceTimeRefTracker` 는 **감시 시작 후 N분간 데이터 수집 후 기준가 확정**.  
  감시 시작 직후 N분 동안은 급락 감지 불가 (수집 중).
- 자동 매도는 **매수 체결가 기준** 으로 확정되므로 드라이런 TG의 금액과 실제 금액이 다를 수 있음.
- `_sleep_place_sell_order` 콜백 미구현 시 TG 경고 발송 후 **수동 대응** 필요.
