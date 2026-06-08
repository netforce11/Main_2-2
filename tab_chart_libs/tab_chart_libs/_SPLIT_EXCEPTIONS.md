# 200줄 초과 분리 예외 파일

다음 5개 파일은 단일 클래스 또는 긴밀하게 연결된 UI 빌더로
구성되어 있어, 분리 시 오히려 복잡도가 증가하므로 현행 유지.

| 파일 | 줄 수 | 이유 |
|---|---|---|
| chart_calendar_widget.py | 238 | _CustomCalendar 단일 클래스 (분리 시 메서드 믹스인 필요 → 복잡) |
| chart_build_side.py | 235 | build_sidebar() 단일 함수 — UI 위젯 순서가 시각적 레이아웃과 1:1 대응 |
| chart_condition_ui.py | 230 | ConditionPanel 단일 클래스 (이미 _build_col_* 분리 완료) |
| chart_condition_monitor.py | 218 | Monitor 단일 클래스 — subscribe/check/place_order 상태 공유 |
| chart_memo.py | 201 | 메모 패널 UI (이미 IO/Actions 분리 완료, 나머지는 빌더 코드) |
