"""
chart_condition_order.py — 조건부 주문 공개 API (진입점)
────────────────────────────────────────────────────────
⚠ [피뢰침 포착 비활성화] 이 파일의 기능은 현재 비활성화 상태입니다.
  아래 import 및 함수는 모두 주석 처리되어 있습니다.
  재활성화 시 주석 해제 후 chart_build_main.py (build_chart_area / build_tables)
  에서 해당 호출부도 함께 복원하세요.
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

# ── [피뢰침 포착 비활성화] import 주석 처리 ───────────────────
# from chart_condition_ui      import ConditionPanel
# from chart_condition_monitor import Monitor
# ── [피뢰침 포착 비활성화 끝] ─────────────────────────────────


def build_condition_panel(mw):
    """[피뢰침 포착 비활성화] — 호출 시 None 반환."""
    # ── [피뢰침 포착 비활성화] ────────────────────────────────
    # return ConditionPanel(mw)
    # ── [피뢰침 포착 비활성화 끝] ─────────────────────────────
    return None


def stop_condition_monitor(panel_widget):
    """[피뢰침 포착 비활성화] — 호출 시 아무 동작 안 함."""
    # ── [피뢰침 포착 비활성화] ────────────────────────────────
    # try:
    #     panel_widget._mon.unsubscribe()
    #     panel_widget._mon.running = False
    # except Exception:
    #     pass
    # ── [피뢰침 포착 비활성화 끝] ─────────────────────────────
    pass
