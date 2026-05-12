"""
chart_daily_helpers.py — 일봉 CSV/마커 경로 헬퍼
[분리] chart_daily.py 에서 분리
"""
from pathlib import Path
try:
    from common import DATA_ROOT
except Exception:
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")


def _daily_csv_path(symbol_up):
    return DATA_ROOT / symbol_up / f"daily_{symbol_up}.csv"

def _daily_marker_path(symbol_up, d):
    return DATA_ROOT / symbol_up / ".downloaded_daily" / d.strftime("%Y%m%d")

def _has_daily_marker(symbol_up, d):
    return _daily_marker_path(symbol_up, d).exists()

def _set_daily_marker(symbol_up, d):
    mp = _daily_marker_path(symbol_up, d)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.touch()
