"""
chart_build_main.py — 차트탭 UI 빌드 (진입점)
[분리] v2:
  chart_build_tables.py  — build_tables()
  chart_build_chart.py   — build_chart_area()
  chart_build_handlers.py — 토글 핸들러
"""
from chart_build_tables  import build_tables       # noqa: F401
from chart_build_chart   import build_chart_area   # noqa: F401
from chart_build_handlers import (                 # noqa: F401
    _on_order_panel_toggle, _toggle_table_panel
)
