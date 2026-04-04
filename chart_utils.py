"""
chart_utils.py — Polygon API 키 로드 / DST·KST 유틸 / FetchSignal
"""

import os
from datetime import datetime, timedelta, date as _date

from PyQt5.QtCore import QObject, pyqtSignal


# ──────────────────────────────────────────────────────────────
# Polygon API 키
# ──────────────────────────────────────────────────────────────
def _polygon_key() -> str:
    """
    Polygon.io API 키 로드 순서:
    1. 실행 폴더의 stock_api_key 파일 (첫 번째 줄)
    2. core.py 의 POLYGON_API_KEY 상수
    3. 환경변수 POLYGON_API_KEY
    """
    try:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "stock_api_key")
        with open(key_file, "r", encoding="utf-8") as f:
            key = f.readline().strip()
        if key:
            return key
    except Exception:
        pass
    try:
        from core import POLYGON_API_KEY
        if POLYGON_API_KEY:
            return POLYGON_API_KEY
    except ImportError:
        pass
    return os.environ.get("POLYGON_API_KEY", "")


def polygon_aggs(sym: str, start: _date, end: _date,
                 multiplier: int, timespan: str) -> list:
    """Polygon REST /v2/aggs 공통 호출."""
    key = _polygon_key()
    if not key:
        return []

    _INDEX_SET = {"SPX", "NDX", "VIX", "RUT", "DJX", "XSP", "MID", "GSPC"}
    ticker_map = {
        "SPX": "I:SPX", "NDX": "I:NDX", "VIX": "I:VIX", "RUT": "I:RUT",
        "DJX": "I:DJX", "XSP": "I:XSP", "MID": "I:MID",
        "QQQ": "QQQ",  "SPY": "SPY",  "AAPL": "AAPL",
        "TSLA": "TSLA", "NVDA": "NVDA",
    }
    ticker = (ticker_map.get(sym, f"I:{sym}") if sym in _INDEX_SET
              else ticker_map.get(sym, sym))

    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}"
           f"/range/{multiplier}/{timespan}"
           f"/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
           f"?adjusted=true&sort=asc&limit=5000&apiKey={key}")
    try:
        import urllib.request, json
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        return [{"t": b["t"] / 1000, "o": b["o"], "h": b["h"],
                 "l": b["l"], "c": b["c"], "v": b.get("v", 0)}
                for b in data.get("results", [])]
    except Exception:
        return []


# ──────────────────────────────────────────────────────────────
# DST / KST 유틸
# ──────────────────────────────────────────────────────────────
def is_dst(dt=None) -> bool:
    if dt is None:
        dt = datetime.utcnow()
    y = dt.year
    dst_start = datetime(y, 3, 8)  + timedelta(days=(6 - datetime(y, 3, 8).weekday())  % 7)
    dst_end   = datetime(y, 11, 1) + timedelta(days=(6 - datetime(y, 11, 1).weekday()) % 7)
    return dst_start <= dt < dst_end


def et_to_kst(dt_et):
    return dt_et + timedelta(hours=13 if is_dst(dt_et) else 14)


# ──────────────────────────────────────────────────────────────
# 공통 QSS 스타일 상수
# ──────────────────────────────────────────────────────────────
CB_STYLE = (
    "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
    "font-size:11px;padding:1px;}"
    "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;font-size:11px;}"
    "QComboBox::drop-down{border:none;}"
)
SB_STYLE = (
    "QSpinBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
    "font-size:11px;padding:1px;}"
    "QSpinBox::up-button,QSpinBox::down-button{width:14px;}"
)
BTN_STYLE = (
    "QPushButton{background:#1a3a5c;color:#90caf9;font-size:11px;"
    "font-weight:bold;padding:1px 7px;border-radius:3px;"
    "border:1px solid #2a5a8a;}"
    "QPushButton:hover{background:#2a4a7c;}"
)
QUERY_BTN_STYLE = (
    "background:#1a5c2e;color:#00ff88;font-size:11px;"
    "font-weight:bold;padding:1px 8px;border-radius:3px;"
)
TAB_STYLE = (
    "QTabWidget::pane{border:1px solid #2a2a5a;background:#06060e;}"
    "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 10px;"
    "border:1px solid #2a2a5a;border-bottom:none;font-size:11px;}"
    "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
    "border-bottom:1px solid #12122a;font-weight:bold;}"
    "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}"
)

# ──────────────────────────────────────────────────────────────
# 신호 클래스
# ──────────────────────────────────────────────────────────────
class _FetchSignal(QObject):
    done = pyqtSignal(list)
    err  = pyqtSignal(str)
