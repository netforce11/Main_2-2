"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PATCH GUIDE v2 — 체결 마커 XSP/SPX 지수환산 + 시간보정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

신규/변경 파일:
  ✅ chart_exec_marker.py    — v2 교체 (기존 덮어쓰기)
  ✅ chart_exec_marker_ui.py — 신규 (사이드바 UI 패널)

기존 파일 수정 2곳:
  [A] chart_build_side_bottom.py  — UI 패널 삽입
  [B] PATCH_GUIDE.py [4][5] — 기존 패치 그대로 유지 (변경 없음)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[A] chart_build_side_bottom.py — 체결 마커 패널 삽입
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_bottom_section(self, side):
    ...
    # ── 기존 메모 토글 버튼 앞에 아래 3줄 추가 ─────────────────
    from chart_exec_marker_ui import build_exec_marker_panel
    side.addWidget(build_exec_marker_panel(self))
    # ── 이하 기존 코드 유지 ────────────────────────────────────
    self.btn_memo_toggle = QPushButton("📝 메모")
    ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B] tab_chart.py — 위임 메서드 (기존 PATCH_GUIDE [5] 에 추가)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from chart_exec_marker import (add_exec_marker, redraw_exec_markers,
                                clear_exec_markers,
                                load_exec_markers_from_db,
                                convert_exec_price)   # ← convert_exec_price 추가

_add_exec_marker       = add_exec_marker
_redraw_exec_markers   = redraw_exec_markers
_clear_exec_markers    = clear_exec_markers
_load_exec_from_db     = load_exec_markers_from_db
_convert_exec_price    = convert_exec_price            # ← 추가

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[C] order_logic.py — 체결 emit 시 symbol·qty 추가 (선택)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 기존:
bridge.exec_filled.emit(ts_ms, action, price)

# 변경 (symbol, qty 포함):
# core.py SignalBridge 에 시그널 정의도 함께 수정:
#   exec_filled = pyqtSignal(int, str, float, str, int)
#                             ts   act  price  sym  qty
bridge.exec_filled.emit(ts_ms, action, avgFillPrice, contract.symbol, filled_qty)

# chart_exec_marker.py init_exec_markers() 에서 lambda 도 수정:
bridge.exec_filled.connect(
    lambda ts, act, px, sym, qty: add_exec_marker(self, ts, act, px, sym, qty))

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
기능 정리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. XSP ↔ SPX 자동 환산
   - DB에 XSP 체결(예: 575.30) 저장 → SPX 차트 표시 시 ×10 → 5753.0
   - DB에 SPX 체결(예: 5753.0) 저장 → XSP 차트 표시 시 ÷10 → 575.3
   - 환산된 마커는 색상이 다름: BUY=연녹색, SELL=주황 (원래: 녹/적)

2. ET 시간 자동 보정
   - DB ts 컬럼이 naive("2026-05-01T09:31:00") → ET로 가정, DST 자동 판정
   - KST aware("2026-05-01T22:31:00+09:00") → UTC 변환 후 봉 매핑
   - epoch_ms 기준으로 가장 가까운 봉에 마커 표시

3. 사이드바 UI (chart_exec_marker_ui.py)
   - 날짜 입력 (비우면 오늘, YYYYMMDD 자동 포맷)
   - 종목 필터 (ALL / XSP / SPX)
   - [📥 체결 로드] / [🗑 지우기] 버튼
   - 상태 라벨 (건수·에러 표시)
"""
