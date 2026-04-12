# Feature Map — Greeks Matrix 탭
> 파일: `feature_map_greeks.md`  |  Last updated: 2026-04-12  |  Current session: S11

---

## 파일 구성 (v3.0 — S11 분리)

| 파일 | 줄 수 | 역할 |
|------|------:|------|
| `tab_greeks.py`    | ~200 | GreeksGrid 메인 탭 — 실시간 수신·탭 조립·급변동 감지 호출 |
| `greeks_db.py`     | ~170 | SQLite 저장/불러오기/이벤트 감지 (`detect_spike`) |
| `greeks_render.py` | ~165 | 테이블 렌더링 유틸 — 색상·셀·헤더 (실시간+리플레이 공용) |
| `greeks_chart.py`  | ~175 | 차트 패널 — GEX/Skew + Normal Band (급변동 판단) |
| `greeks_replay.py` | ~175 | 리플레이 패널 — 날짜/시간 선택, 슬라이더 재생 |

---

## 데이터 저장 경로

```
C:\data\Greeks_history\
  ├─ greeks_20260412.db   ← 날짜별 실시간 스냅샷
  ├─ greeks_20260411.db
  └─ events_log.db        ← 급변동 이벤트 통합 기록
```

### greeks_YYYYMMDD.db 스키마 (`greeks` 테이블)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| ts | TEXT | 타임스탬프 (`YYYY-MM-DD HH:MM:SS`) |
| sym | TEXT | 심볼 (SPX 등) |
| expiry | TEXT | 만기 코드 |
| strike | REAL | 행사가 |
| side | TEXT | `C` / `P` |
| delta | REAL | Delta |
| gamma | REAL | Gamma |
| iv | REAL | Implied Volatility |
| vanna | REAL | Vanna 추정 (`vega × delta`) |
| und_price | REAL | 기초자산 현재가 |

### events_log.db 스키마 (`events` 테이블)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| ts | TEXT | 감지 시각 |
| sym | TEXT | 심볼 |
| trigger_type | TEXT | `Gamma` / `IV_C` / `IV_P` |
| strike | REAL | 급변동 행사가 |
| value | REAL | 현재 값 |
| prev_avg | REAL | 과거 N분 평균 |
| und_price | REAL | 기초자산 현재가 |

---

## 탭 레이아웃

```
GreeksGrid (GridTab)
└── QTabWidget
    ├── [📡 실시간]
    │   ├── 컨트롤바 (심볼/만기/조회/Delta필터/저장)
    │   ├── QSplitter(Horizontal)
    │   │   ├── Greeks Matrix 테이블 (중앙 행사가)
    │   │   └── QSplitter(Vertical)
    │   │       ├── GexSkewPanel  (GEX 막대 + IV Skew)
    │   │       └── NormalBandPanel  (ATM Gamma/IV 시계열 + ±1σ 밴드)
    │   └── 급변동 이벤트 로그 (하단 배너)
    └── [⏪ 리플레이]
        ├── 날짜/시간범위/속도 컨트롤
        ├── 슬라이더
        └── Greeks Matrix 테이블 (재생용)
```

---

## 기능 상세

### tab_greeks.py — GreeksGrid

| 메서드 | 역할 |
|--------|------|
| `_build()` | QTabWidget 조립 (실시간/리플레이 탭) |
| `_build_ctrl()` | 컨트롤바 HBoxLayout 반환 |
| `_connect_signals()` | router 구독 (REQ_UND, REQ_CHAIN, REQ_CHAIN_P) |
| `_fetch()` | 행사가 목록 계산 + reqMktData 호출 |
| `_on_tick_price()` | 기초자산 현재가 수신 |
| `_on_tick_opt()` | 옵션 Greeks tick 수신 → `_cell_data` 캐시 |
| `_flush()` | throttle 300ms 후 일괄 렌더 |
| `_apply_delta_filter()` | Delta 슬라이더 기준 행 숨김 |
| `_update_band()` | 1분마다 NormalBandPanel 과거 평균±σ 갱신 |
| `_do_save()` | DB 저장 + `detect_spike()` 호출 → 이벤트 배너 표시 |

### greeks_db.py

| 함수 | 역할 |
|------|------|
| `open_db(day)` | 날짜별 SQLite 연결 + 테이블 초기화 |
| `open_events_db()` | 이벤트 통합 DB 연결 |
| `save_snapshot(conn, ...)` | Greeks 스냅샷 저장 |
| `save_event(econn, ...)` | 급변동 이벤트 저장 |
| `load_snapshots(day, from, to)` | 날짜+시간범위 조회 → list[dict] |
| `available_days()` | 저장된 날짜 목록 |
| `load_timestamps(day)` | 해당 날짜 타임스탬프 목록 |
| `detect_spike(day, sym, ...)` | 과거 20분 평균 대비 급변동 감지 |

**급변동 임계값 (greeks_db.py 상단)**
```python
GAMMA_SPIKE_MULT = 2.5   # 과거 평균 대비 N배 이상
IV_CHANGE_PCT    = 5.0   # 분당 IV 변화율 %
DELTA_JUMP       = 0.05  # 틱당 delta 점프 (향후 확장)
```

### greeks_render.py

| 함수 | 역할 |
|------|------|
| `init_table(tbl)` | 헤더 스타일 + 공통 옵션 |
| `init_row(tbl, row, strike, atm)` | 행 초기화 + ATM 하이라이트 |
| `set_cell(...)` | 셀 1개 렌더 (값/색상/화살표/heatmap/spike) |
| `render_rows(...)` | `cell_data` 전체 → 테이블 일괄 렌더 |
| `gamma_bg(gamma, max)` | Gamma heatmap 보라 계열 배경 |
| `delta_color(delta, side)` | Delta 글자색 (Call 파랑 / Put 빨강) |
| `arrow_str/color(curr, prev)` | ▲▼ 화살표 문자·색상 |

### greeks_chart.py

| 클래스 | 역할 |
|--------|------|
| `GexSkewPanel` | GEX 막대 (Call+파랑/Put-빨강) + IV Skew 라인 + Zero Gamma 점선 |
| `NormalBandPanel` | ATM Gamma/IV 시계열 오늘(빨강/파랑) + 과거평균(회색점선) + ±1σ 음영 밴드 |

**NormalBandPanel 활용법**
- 오늘 선이 음영 밴드 밖으로 이탈 = 평소와 다른 구간
- 마감 30분 전 Gamma가 밴드 상단 이탈 시 스퀴즈 진입 신호
- IV가 밴드 하단 이탈 시 IV 수축 → 프리미엄 매도 기회

### greeks_replay.py — ReplayPanel

| 메서드 | 역할 |
|--------|------|
| `_refresh_days()` | 저장된 날짜 목록 ComboBox 갱신 |
| `_load()` | 날짜+시간범위 데이터 로드 → 프레임 구성 |
| `_toggle_play()` | ▶/⏸ 전환, QTimer 속도 설정 |
| `_step()` | 1프레임 전진 |
| `_render(idx)` | 해당 타임스탬프 cell_data → 테이블 렌더 |

**재생 속도**
| 선택 | 프레임 간격 |
|------|------------|
| x1  | 1,000ms (실시간 1분봉) |
| x5  | 200ms |
| x10 | 100ms |

---

## 연동 관계

```
tab_greeks.GreeksGrid
  ├── greeks_db.open_db()           ← 날짜별 DB
  ├── greeks_db.open_events_db()    ← 이벤트 DB
  ├── greeks_db.save_snapshot()     ← 1분 자동저장
  ├── greeks_db.detect_spike()      ← 급변동 감지
  ├── greeks_render.init_table/row  ← 테이블 초기화
  ├── greeks_render.render_rows()   ← throttle 후 렌더
  ├── greeks_chart.GexSkewPanel     ← GEX/Skew 차트
  ├── greeks_chart.NormalBandPanel  ← Normal Band 차트
  └── greeks_replay.ReplayPanel     ← 리플레이 탭

core.py (공용)
  ├── router.register_option/price  ← tick 라우팅
  ├── build_expiry_list()
  ├── make_opt_contract()
  └── is_market_open()
```

---

## 변경 이력

| Session | 변경 내용 |
|---------|-----------|
| S6 초기 | `tab_account.py` 내 `GreeksGrid` (line 601~757) — ATM±20, CSV 저장 |
| S8 | `tab_greeks.py` 분리, 중앙 행사가 레이아웃, Gamma Heatmap, Delta 필터, GEX/Skew 차트, SQLite 1분 저장 |
| S11 | **파일 5분리** — greeks_db / render / chart / replay 독립. 저장경로 `C:\data\Greeks_history\`. 리플레이 패널 신규. NormalBandPanel (급변동 판단) 신규. 급변동 이벤트 로그 배너 신규. |
