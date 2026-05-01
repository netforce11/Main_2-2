# 0DTE Greeks 주요 수정 내역 — S12-patch2

**작업일: 2026-05-01**
**수정 파일: `greeks_snapshot_mgr.py` / `tab_greeks.py` / `tab_greeks_tick.py`**

---

## 수정 파일 목록

| 파일 | 수정 내용 요약 |
|------|---------------|
| `greeks_snapshot_mgr.py` | reqId 범위 충돌 해소 / tag 자동계산 / 공휴일 처리 / 스레드 안전성 / router unregister |
| `tab_greeks.py` | snap_mgr 전용 reqId 범위 router 등록 추가 |
| `tab_greeks_tick.py` | 0DTE DB 저장 복구 / ERR 504 안전 처리 |

---

## 상세 수정 내역

### 1. `greeks_snapshot_mgr.py` — reqId 범위 충돌 해소 (치명적)

**증상**
0DTE 및 D+1/D+2 Greeks가 DB에 저장되지 않음.

**원인**
`greeks_snapshot_mgr.py`의 0DTE reqId 블록이 `core.py`의 `REQ_CHAIN`과 완전히 동일한 범위를 사용.

```
기존 (충돌):
  REQ_CHAIN       = 4000~4399  ← core.py (tab_greeks_fetch.fetch() 사용)
  REQ_0DTE_C_BASE = 4000~4399  ← greeks_snapshot_mgr.py (snap_mgr 사용)

충돌 결과:
  fetch()도 4000번부터 reqId를 사용하고 snap_mgr도 동일 번호를 사용
  → 두 경로가 같은 reqId를 IBKR에 이중 요청
  → _req_map 충돌, tick 처리 경로 혼선
  → 0DTE DB 저장 누락
```

**수정**
snap_mgr 전용 블록을 core.py 전체 reqId 범위(1~9999)와 겹치지 않는 10000번대로 이동.

```python
# 기존
REQ_0DTE_C_BASE = 4000;  REQ_0DTE_P_BASE = 4200;  REQ_0DTE_RANGE = 200
REQ_1DTE_C_BASE = 5000;  REQ_1DTE_P_BASE = 5400;  REQ_1DTE_RANGE = 400
REQ_2DTE_C_BASE = 6000;  REQ_2DTE_P_BASE = 6400;  REQ_2DTE_RANGE = 400

# 수정
REQ_0DTE_C_BASE = 10000; REQ_0DTE_P_BASE = 10200; REQ_0DTE_RANGE = 200
REQ_1DTE_C_BASE = 11000; REQ_1DTE_P_BASE = 11400; REQ_1DTE_RANGE = 400
REQ_2DTE_C_BASE = 12000; REQ_2DTE_P_BASE = 12400; REQ_2DTE_RANGE = 400
```

---

### 2. `greeks_snapshot_mgr.py` — SPX/SPXW tag="" 하드코딩 제거

**증상**
D+1/D+2 스냅샷 요청 건수는 정상이나 tick이 오지 않아 저장 0건.

**원인**
`_request_snapshot()` 및 `_start_0dte_streaming()`에서 contract 생성 시
`tag=""`(또는 `"0DTE"`)로 하드코딩.
SPX/SPXW 옵션은 만기 요일에 따라 `tradingClass`가 `"SPX"` 또는 `"SPXW"`로
달라지는데, `tag=""`이면 IBKR이 계약을 찾지 못해 tick이 수신되지 않음.

**수정**
`_resolve_spx_trading_class(sym, expiry, "")` 함수로 만기일 기반 tag 자동 계산.

```python
# _start_0dte_streaming()
from core import _resolve_spx_trading_class
tag = (_resolve_spx_trading_class(self._sym, self._exp_0, "")
       if self._sym in ("SPX", "SPXW") else "")
con = self._make_con(self._sym, strike, side, self._exp_0, tag)

# _request_snapshot()
from core import _resolve_spx_trading_class
_get_tag = lambda sym, exp: (_resolve_spx_trading_class(sym, exp, "")
                              if sym in ("SPX", "SPXW") else "")
tag = _get_tag(self._sym, expiry)
con = self._make_con(self._sym, strike, side, expiry, tag)
```

---

### 3. `greeks_snapshot_mgr.py` — `_next_bday()` 공휴일 처리 누락

**원인**
`_next_bday()`가 주말(`weekday() >= 5`)만 건너뛰고 미국 공휴일(성금요일 등) 미처리.
공휴일에 잘못된 만기 날짜 계산.

**수정**
`is_trading_day()`로 주말 + 공휴일 통합 처리.

```python
# 기존
while count < n:
    d += timedelta(days=1)
    if d.weekday() < 5: count += 1

# 수정
from core import is_trading_day
while count < n:
    d += timedelta(days=1)
    if is_trading_day(d): count += 1
```

---

### 4. `greeks_snapshot_mgr.py` — `record_received()` 스레드 안전성

**원인**
`record_received()`가 IBKR EClient 스레드에서 직접 호출되어
`_recv_count` 증가 + `_notify()`(PyQt 시그널 emit) 실행.
크로스 스레드 에러 가능성.

**수정**
`QMetaObject.invokeMethod`로 메인 스레드 마샬링.
`SnapshotManager`를 `QObject`를 상속하도록 변경.

```python
class SnapshotManager(QObject):   # QObject 상속 추가
    def __init__(self, ...):
        super().__init__()         # QObject 초기화

    def record_received(self, rid: int):
        """EClient 스레드 → 메인 스레드로 마샬링."""
        QMetaObject.invokeMethod(self, "_do_record_received",
                                 Qt.QueuedConnection, Q_ARG(int, rid))

    @pyqtSlot(int)
    def _do_record_received(self, rid: int):
        """메인 스레드에서 실제 카운터 증가 + 신호등 갱신."""
        ...
```

---

### 5. `greeks_snapshot_mgr.py` — `stop()` router unregister 추가

**원인**
`stop()` 시 router에 등록된 슬롯을 해제하지 않아
재시작 시 같은 reqId 범위가 중복 등록될 가능성.

**수정**
`stop()`에 `router.unregister_option()` 추가.

```python
def stop(self):
    self._t1.stop(); self._t2.stop()
    self._pace_t.stop(); self._queue.clear()
    self._cancel_streaming(); self._req_map.clear()
    if getattr(self, '_router_registered', False):
        from core import router
        router.unregister_option(self._dummy_tick)
        self._router_registered = False
```

---

### 6. `tab_greeks.py` — snap_mgr 전용 reqId 범위 router 미등록

**증상**
D+1/D+2 tick이 IBKR에서 수신되어도 `on_tick_opt`가 호출되지 않아 저장 0건.

**원인**
`_connect_signals()`에서 `REQ_CHAIN(4000~4399)` 범위만 router에 등록.
snap_mgr 전용 범위(10000~12799)는 미등록 → TickRouter가 라우팅 슬롯을 찾지 못함.

```
IBKR tick(10000~12799) → bridge.tick_option.emit()
    → TickRouter._route_option()
    → 등록된 슬롯 없음 → on_tick_opt 미호출
    → DB 저장 0건
```

**수정**
`_connect_signals()`에 snap_mgr 전용 3블록 명시 등록.

```python
def _connect_signals(self):
    router.register_option(REQ_CHAIN, REQ_CHAIN_P + 199, self._on_tick_opt)

    # S12-patch2 추가: snap_mgr 전용 범위 등록
    from greeks_snapshot_mgr import (REQ_0DTE_C_BASE, REQ_0DTE_P_BASE, REQ_0DTE_RANGE,
                                      REQ_1DTE_C_BASE, REQ_1DTE_P_BASE, REQ_1DTE_RANGE,
                                      REQ_2DTE_C_BASE, REQ_2DTE_P_BASE, REQ_2DTE_RANGE)
    router.register_option(REQ_0DTE_C_BASE, REQ_0DTE_P_BASE + REQ_0DTE_RANGE - 1,
                           self._on_tick_opt)
    router.register_option(REQ_1DTE_C_BASE, REQ_1DTE_P_BASE + REQ_1DTE_RANGE - 1,
                           self._on_tick_opt)
    router.register_option(REQ_2DTE_C_BASE, REQ_2DTE_P_BASE + REQ_2DTE_RANGE - 1,
                           self._on_tick_opt)
```

---

### 7. `tab_greeks_tick.py` — 0DTE 저장 경로 설계 확정 + `_cell_data` sym 필드 누락

**배경**
`tab_greeks_save.py`를 확인한 결과, S12-patch1에서 이미 `autosave()`가
`self._expiry`(0DTE 만기)만 필터링하여 저장하도록 올바르게 구현되어 있었음.

```python
# tab_greeks_save.py — autosave() (S12-patch1 기존 코드, 이미 정상)
rows_0dte = [
    {**d, "ts": ts, "sym": self._sym}
    for d in self._cell_data.values()
    if d.get("expiry") == self._expiry   # ← 0DTE 만기만 저장
]
```

따라서 `slot > 0` 조건은 **의도적으로 올바른 설계**였음.
0DTE는 `autosave`(1분 주기)가, D+1/D+2는 tick 즉시 저장이 각각 담당하며 중복 없음.

**확정된 저장 구조**

| | 경로 1 (fetch, 4000번대) | 경로 3 snap_mgr (10000번대) | autosave (1분) |
|---|---|---|---|
| **0DTE** | `_cell_data` 갱신만 | `_cell_data` 갱신만 | ✅ 저장 (0DTE 필터) |
| **D+1** | — | ✅ tick 즉시 저장 | ❌ expiry 필터로 제외 |
| **D+2** | — | ✅ tick 즉시 저장 | ❌ expiry 필터로 제외 |

**수정 — `_cell_data`에 `sym` 필드 누락 발견 및 추가**

경로 1(fetch)과 경로 3(snap_mgr) 모두 `_cell_data` 저장 시 `sym` 필드가 없었음.
`autosave()`에서 `{**d, "sym": self._sym}`으로 덮어씌우므로 DB 저장 자체는 문제없었으나,
이벤트 감지(`detect_spike`), 리플레이 등 `_cell_data`를 직접 읽는 다른 경로에서
`sym` 키 접근 시 `KeyError` 발생 가능.

```python
# 기존 (경로 1 및 경로 3 공통)
self._cell_data[k] = dict(expiry=exp, strike=strike, side=side,
                          delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                          und_price=self._und_price, ts=ts)
                          # ↑ sym 없음

# 수정
self._cell_data[k] = dict(sym=self._sym, expiry=exp, strike=strike, side=side,
                          delta=delta, gamma=gamma, iv=iv, vanna=vanna,
                          und_price=self._und_price, ts=ts)
                          # ↑ sym 명시 추가
```

---

### 8. `tab_greeks_tick.py` — ERR 504 "Not connected" 안전 처리

**증상**
장 마감 후 또는 연결 해제 시 ERR 504가 다수 연속 출력.

**원인**
`_pace_t`(22ms 타이머)가 연결 해제 후에도 살아있어 `reqMktData` 연속 호출.
또는 `cancelMktData`가 연결 해제 상태에서 발사됨.
에러 핸들러에서 504를 무시하지 않고 배너에 표시 + `_req_map` 미정리로 dead reqId 누적.

**수정**
504 에러 시 dead reqId 정리 후 조용히 return.

```python
def on_ibkr_error(self, req_id: int, error_code: int, msg: str):
    if error_code == 504:
        if req_id in self._req_map:
            del self._req_map[req_id]
        if self._snap_mgr and self._snap_mgr.is_managed_req(req_id):
            try: del self._snap_mgr._req_map[req_id]
            except Exception: pass
        return  # 배너 노출 없이 처리 (연결 복구 후 자동 재구독)
    ...
```

---

## reqId 블록 전체 현황 (patch2 기준)

| 범위 | 용도 | 관리 주체 |
|------|------|-----------|
| 1 | 기초자산 현재가 (REQ_UND) | core |
| 1000~1099 | 콜 옵션 (REQ_CALL) | CallPutGrid |
| 2000~2099 | 풋 옵션 (REQ_PUT) | CallPutGrid |
| 3000~3299 | 복수현재가 (REQ_MULTI) | core |
| 4000~4199 | Greeks Matrix 콜 (REQ_CHAIN) | tab_greeks_fetch.fetch() |
| 4200~4399 | Greeks Matrix 풋 (REQ_CHAIN_P) | tab_greeks_fetch.fetch() |
| 5000~5499 | OI 조회 (REQ_OI) | core |
| 6000~6099 | IBKR 히스토리 (REQ_HIST) | core |
| 7000~7499 | 스나이퍼 (REQ_SNIPER) | Sniper |
| 9001 | 계좌 (REQ_ACCT) | core |
| **10000~10399** | **0DTE snap_mgr (콜+풋)** | **SnapshotManager** |
| **11000~11799** | **+1DTE snap_mgr (콜+풋)** | **SnapshotManager** |
| **12000~12799** | **+2DTE snap_mgr (콜+풋)** | **SnapshotManager** |

---

## `tab_greeks_save.py` 확인 결과

`tab_greeks_save.py`를 검토한 결과, 아래 두 항목 모두 **이미 S12-patch1에서 올바르게 처리**되어 있었음. 추가 수정 불필요.

**① 0DTE 중복 저장 — 문제 없음**

`autosave()`가 `self._expiry`(0DTE 만기)만 필터링하여 저장.
D+1/D+2는 autosave 대상에서 제외되므로 tick 즉시 저장(경로 3)과 중복 없음.

**② autosave(60s) vs SNAP_1DTE_MS(60s) 타이밍 충돌 — 문제 없음**

두 타이머가 같은 주기지만 서로 독립 동작하며 동일 데이터를 건드리지 않음.
autosave → 0DTE `_cell_data` 읽어 저장,  `_snap_1dte` → D+1 IBKR 재요청.
충돌 지점 없음.

**③ `save_baseline()` 0DTE rows 범위 — 정상**

`autosave()`에서 필터된 `rows_0dte`만 `save_baseline()`에 전달하므로
baseline 테이블에 D+1/D+2 데이터가 섞이지 않음.

---

## 수정 파일 최종 목록 (S12-patch2)

| 파일 | 변경 항목 수 | 주요 내용 |
|------|------------|-----------|
| `greeks_snapshot_mgr.py` | 5 | reqId 재배치 / tag 자동계산 / 공휴일 처리 / 스레드 마샬링 / router unregister |
| `tab_greeks.py` | 1 | snap_mgr 범위(10000~12799) router 등록 |
| `tab_greeks_tick.py` | 2 | `_cell_data` sym 누락 수정 / ERR 504 안전 처리 |
| `tab_greeks_save.py` | 0 | 검토 완료 — 수정 불필요 |

