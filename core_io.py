"""
core_io.py — 저장/불러오기 유틸 / 장 시간 판별 / auto_mdt
core.py 300줄 초과로 분리.
"""
import os, json, csv
from datetime import datetime, timedelta, time as dt_time, date as dt_date
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

from pathlib import Path
from core import SAVE_DIR

def save_json(filename: str, data: dict):
    path = SAVE_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # router 는 module-level 에서 이미 export 됨

def load_json(filename: str, default=None):
    path = SAVE_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

def append_csv(filename: str, row: dict):
    """CSV에 행 추가 (헤더 없으면 자동 생성)"""
    path = SAVE_DIR / filename
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if write_header: w.writeheader()
        w.writerow(row)

def load_csv(filename: str) -> list:
    path = SAVE_DIR / filename
    if not path.exists(): return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ══════════════════════════════════════════════════════════════
# 11. 장 마감 감지 + MarketDataType 자동 전환
# ══════════════════════════════════════════════════════════════
_ET = ZoneInfo("America/New_York")

# 미국 주식 시장 정규장: 월~금 09:30~16:00 ET
_MARKET_OPEN  = dt_time(9, 30)
_MARKET_CLOSE = dt_time(16, 0)

def is_market_open() -> bool:
    """현재 시각이 미국 정규장(ET 09:30~16:00, 월~금) 안인지 반환."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:          # 토(5) · 일(6)
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE

def auto_mdt(ib) -> int:
    """
    장중        → MarketDataType 1 (LIVE)
    장외/평일   → MarketDataType 3 (DELAYED)
    주말        → MarketDataType 4 (DELAYED-FROZEN) : 마지막 종가 고정 표시
    반환값: 실제 설정된 MarketDataType 번호
    """
    now = datetime.now(_ET)
    if is_market_open():
        mdt = 1   # LIVE
    elif now.weekday() >= 5:
        mdt = 4   # 주말 → Delayed-Frozen (마지막 종가)
    else:
        mdt = 3   # 평일 장외 → Delayed
    try:
        ib.reqMarketDataType(mdt)
    except Exception as e:
        print(f"[auto_mdt] reqMarketDataType({mdt}) 실패: {e}")
    return mdt
