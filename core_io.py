"""
core_io.py — 저장/불러오기 유틸 / 장 시간 판별 / auto_mdt
core.py 300줄 초과로 분리.

【경로 수정】 2026-04-23
- SAVE_DIR: data → /home/netforce/US_Data/Data
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

# ══════════════════════════════════════════════════════════════
# 【경로 수정】SAVE_DIR 설정
# core.py 와 순환 import 방지 — SAVE_DIR 을 여기서 직접 정의
# ══════════════════════════════════════════════════════════════
BASE_DATA_DIR = Path("/home/netforce/US_Data")
SAVE_DIR = BASE_DATA_DIR / "Data"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════
# JSON 저장/로드 함수
# ══════════════════════════════════════════════════════════════
def save_json(filename: str, data: dict):
    """
    JSON 파일 저장
    
    Args:
        filename: 파일명 (예: "settings.json", "conid_cache.json")
        data: 저장할 딕셔너리
    
    저장 경로: /home/netforce/US_Data/Data/{filename}
    """
    path = SAVE_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(filename: str, default=None):
    """
    JSON 파일 로드
    
    Args:
        filename: 파일명 (예: "settings.json", "conid_cache.json")
        default: 파일 없을 시 반환할 기본값
    
    로드 경로: /home/netforce/US_Data/Data/{filename}
    
    Returns:
        로드된 딕셔너리 또는 default 값
    """
    path = SAVE_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}

# ══════════════════════════════════════════════════════════════
# CSV 저장/로드 함수
# ══════════════════════════════════════════════════════════════
def append_csv(filename: str, row: dict):
    """
    CSV에 행 추가 (헤더 없으면 자동 생성)
    
    Args:
        filename: 파일명 (예: "trade_log.csv")
        row: 저장할 행 (딕셔너리)
    
    저장 경로: /home/netforce/US_Data/Data/{filename}
    """
    path = SAVE_DIR / filename
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if write_header: 
            w.writeheader()
        w.writerow(row)

def load_csv(filename: str) -> list:
    """
    CSV 파일 로드
    
    Args:
        filename: 파일명 (예: "trade_log.csv")
    
    로드 경로: /home/netforce/US_Data/Data/{filename}
    
    Returns:
        행의 리스트 (각 행은 딕셔너리)
    """
    path = SAVE_DIR / filename
    if not path.exists(): 
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ══════════════════════════════════════════════════════════════
# 장 시간 판별 및 MarketDataType 자동 전환
# ══════════════════════════════════════════════════════════════
_ET = ZoneInfo("America/New_York")

# 미국 주식 시장 정규장: 월~금 09:30~16:00 ET
_MARKET_OPEN  = dt_time(9, 30)
_MARKET_CLOSE = dt_time(16, 0)

def is_market_open() -> bool:
    """
    현재 시각이 미국 정규장(ET 09:30~16:00, 월~금) 안인지 반환.
    
    Returns:
        bool: 정규장 시간이면 True, 아니면 False
    """
    now = datetime.now(_ET)
    if now.weekday() >= 5:          # 토(5) · 일(6)
        return False
    return _MARKET_OPEN <= now.time() < _MARKET_CLOSE

def auto_mdt(ib) -> int:
    """
    장 시간에 따라 MarketDataType 자동 설정
    
    - 장중 (09:30~16:00)     → MarketDataType 1 (LIVE)
    - 평일 장외              → MarketDataType 3 (DELAYED)
    - 주말                   → MarketDataType 4 (DELAYED-FROZEN) : 마지막 종가 고정 표시
    
    Args:
        ib: IBapi 인스턴스
    
    Returns:
        int: 실제 설정된 MarketDataType 번호
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


# ══════════════════════════════════════════════════════════════
# 설정 초기화
# ══════════════════════════════════════════════════════════════
def apply_saved_settings() -> None:
    """
    앱 시작 시 1회 호출 — settings.json 읽어 각 모듈에 적용.
    main.py 의 TradingDashboard.__init__() 에서 호출 권장.
    
    로드 경로: /home/netforce/US_Data/Data/settings.json
    """
    try:
        cfg = load_json("settings.json", {})
        # 기초자산 저장 주기
        interval = cfg.get("und_save_interval", 10)
        try:
            from trade_log.und_saver import set_interval
            set_interval(interval)
        except ImportError:
            pass
        print(f"[Settings] 기초자산 저장 주기: {interval}초")
    except Exception as e:
        print(f"[Settings] 설정 로드 오류: {e}")


# ══════════════════════════════════════════════════════════════
# 경로 정보 조회 헬퍼
# ══════════════════════════════════════════════════════════════
def get_data_dir() -> Path:
    """
    데이터 저장 디렉토리 반환
    
    Returns:
        Path: /home/netforce/US_Data/Data
    """
    return SAVE_DIR

def get_conid_cache_path() -> Path:
    """
    conId 캐시 파일 경로 반환
    
    Returns:
        Path: /home/netforce/US_Data/Data/conid_cache.json
    """
    return SAVE_DIR / "conid_cache.json"