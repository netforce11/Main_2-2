"""
chart_condition_order.py — 조건부 주문 공개 API (진입점)
────────────────────────────────────────────────────────
외부에서 이 파일만 import 하면 됩니다.
실제 구현:
  chart_condition_monitor.py — Monitor 클래스 (구독·조건·주문)
  chart_condition_ui.py      — ConditionPanel UI

[분리] v2: 783줄 → 3개 파일로 분리
  chart_condition_order.py   ~30줄  (이 파일, 공개 API)
  chart_condition_monitor.py ~160줄 (Monitor)
  chart_condition_ui.py      ~200줄 (ConditionPanel)
"""

from chart_condition_ui      import ConditionPanel
from chart_condition_monitor import Monitor


def build_condition_panel(mw):
    """chart_build_main.py 에서 호출."""
    return ConditionPanel(mw)


def stop_condition_monitor(panel_widget):
    """RT 중지 / 탭 전환 시 호출."""
    try:
        panel_widget._mon.unsubscribe()
        panel_widget._mon.running = False
    except Exception:
        pass
