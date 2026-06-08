"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PATCH GUIDE — 기존 파일 3개 수정 내용
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] core.py — SignalBridge 에 시그널 1개 추가
────────────────────────────────────────────────────────
class SignalBridge(QObject):
    # 기존 시그널들 ...
    exec_filled = pyqtSignal(int, str, float)
    # ↑ 추가: (timestamp_ms, 'BUY'|'SELL', fill_price)


[2] chart_build_main.py — build_chart_area() 끝부분 수정
────────────────────────────────────────────────────────
# 기존 마지막 부분:
#   self.p2.setFixedHeight(110); self.p2.setXLink(self.p1)
#   ...
#   chart_v.addWidget(self.gfx, 1)

# ↓ gfx addWidget 바로 앞에 추가:
from chart_tick_speed import init_tick_speed
init_tick_speed(self)          # p3 패널 생성 (p2 다음 row=2)

# ── p1 마우스 호버 시 틱속도 라벨 위치 보정은 자동 처리됨


[3] chart_build_main.py — build_chart_area() 내 p1/p2 생성 직후
────────────────────────────────────────────────────────
# 기존:
# self.p1 = self.gfx.addPlot(row=0, col=0)
# self.p2 = self.gfx.addPlot(row=1, col=0)

# p2 높이를 조금 줄여서 p3 공간 확보 (110 → 80)
# self.p2.setFixedHeight(80)   ← 선택사항, 화면 여유 있으면 유지 가능


[4] tab_chart.py — __init__ 에 추가
────────────────────────────────────────────────────────
# _build() 호출 직후에 추가:
from chart_exec_marker import init_exec_markers
init_exec_markers(self)


[5] tab_chart.py — 위임 메서드 바인딩 블록에 추가
────────────────────────────────────────────────────────
from chart_vol_surge    import draw_vol_surge, clear_vol_surge
from chart_exec_marker  import (add_exec_marker, redraw_exec_markers,
                                 clear_exec_markers,
                                 load_exec_markers_from_db)
from chart_tick_speed   import stop_tick_speed

_draw_vol_surge         = draw_vol_surge
_clear_vol_surge        = clear_vol_surge
_add_exec_marker        = add_exec_marker
_redraw_exec_markers    = redraw_exec_markers
_clear_exec_markers     = clear_exec_markers
_load_exec_from_db      = load_exec_markers_from_db
_stop_tick_speed        = stop_tick_speed


[6] chart_data.py — update_display() 함수 끝에 추가
────────────────────────────────────────────────────────
# update_display() 내부, 캔들/볼륨 그린 직후:

from chart_vol_surge   import draw_vol_surge
from chart_exec_marker import redraw_exec_markers

# candle_data: [(t_idx, o, c, lo, hi), ...]  — CandlestickItem 과 동일
# vol_data:    [(t_idx, vol), ...]
draw_vol_surge(self, candle_data, vol_data)
redraw_exec_markers(self)


[7] core.py — TickRouter.tickPrice() 에 추가
────────────────────────────────────────────────────────
def tickPrice(self, reqId, tickType, price, attrib):
    # 기존 라우팅 로직 ...

    # ↓ 마지막에 추가 (import는 파일 상단에)
    try:
        from chart_tick_speed import on_ibkr_tick
        on_ibkr_tick(tickType, price)
    except Exception:
        pass


[8] order_logic.py — 체결 시 시그널 emit 추가
────────────────────────────────────────────────────────
# execDetails() 또는 orderStatus() 체결 확인 지점에서:
import time
from core import bridge

# Filled 확인 시:
ts_ms = int(time.time() * 1000)
action = "BUY"   # 또는 "SELL" — 주문 방향
price  = avgFillPrice
bridge.exec_filled.emit(ts_ms, action, price)
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 아래는 chart_data.py update_display() 에 삽입할 실제 코드 조각
# (update_display 함수 구조를 모르므로 패턴으로 제공)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PATCH_UPDATE_DISPLAY = """
# chart_data.py update_display() 내부
# CandlestickItem 생성 직후, p1.addItem(candle) 바로 다음에 삽입:

try:
    from chart_vol_surge import draw_vol_surge
    # candle_data 와 vol_data 는 이미 이 함수 안에서 만들어진 리스트
    draw_vol_surge(self, candle_data, vol_data)
except Exception as e:
    print(f"[VolSurge] {e}")

try:
    from chart_exec_marker import redraw_exec_markers
    redraw_exec_markers(self)
except Exception as e:
    print(f"[ExecMarker] {e}")
"""
