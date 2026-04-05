# -*- coding: utf-8 -*-
"""
spxw_core.py — 코어 유틸리티 모듈
포함: zday_core, MiniChartCanvas, PolygonDataProvider, RateLimiter,
      섬머타임 유틸, 1초봉 수집, xlsx 저장/읽기
"""
from __future__ import annotations

import os
import sys
import csv
import re
import math
import time
import threading
import requests as _requests_module

from datetime import date as dt_date, datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pytz
    _KST = pytz.timezone("Asia/Seoul")
except ImportError:
    pytz = None
    _KST = None

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QHBoxLayout,
    QTabWidget, QTableWidget, QHeaderView, QTableWidgetItem,
    QSplitter, QGroupBox, QMessageBox, QDateEdit, QShortcut,
    QSizePolicy, QPlainTextEdit, QListWidget, QListWidgetItem,
    QSpinBox, QProgressBar, QStatusBar, QCalendarWidget
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, QObject
from PyQt5.QtGui import QKeySequence

try:
    import openpyxl
    from openpyxl import Workbook, load_workbook
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

# 저장 기본 폴더
_SAVE_BASE_DIR = r"C:\data\Zeroday_option_1Sec"

import matplotlib  # keep for any remaining matplotlib.patches refs in this file
matplotlib.use("Qt5Agg")


# ═══════════════════════════════════════════════════════════════════
#  PART 1: zday_core 내장
# ═══════════════════════════════════════════════════════════════════

_SYMBOL_RE = re.compile(r"^SPXW\d{6}[CP]\d{8}$")
_METHOD_CACHE: Dict[int, str] = {}
_HTTP_SESSION = None


def _provider_key(provider: object) -> int:
    return id(provider)


def _http_session():
    global _HTTP_SESSION
    if _HTTP_SESSION is None:
        try:
            s = _requests_module.Session()
            s.headers.update({"User-Agent": "zday-core/1.1"})
            _HTTP_SESSION = s
        except Exception:
            _HTTP_SESSION = None
    return _HTTP_SESSION


def build_spx_zero_day_symbol(strike: Union[float, str], callput: str,
                               expiry_date: str, prefix="SPXW") -> str:
    try:
        s = float(strike)
        if not math.isfinite(s) or s <= 0:
            raise ValueError("invalid strike")
        if len(expiry_date) != 10 or expiry_date[4] != "-" or expiry_date[7] != "-":
            raise ValueError(f"expiry_date 형식 오류: {expiry_date}")
        yy = expiry_date[2:4]
        mm = expiry_date[5:7]
        dd = expiry_date[8:10]
        cp = "C" if str(callput).upper() in ("C", "CALL") else "P"
        last8 = f"{int(round(s * 1000)):08d}"
        sym = f"{prefix}{yy}{mm}{dd}{cp}{last8}"
        return sym if _SYMBOL_RE.match(sym) else ""
    except Exception as e:
        print(f"[SPX-ZERO] 심볼 생성 실패: {e}")
        return ""


def opt_ticker(symbol_raw: str) -> str:
    return symbol_raw if symbol_raw.startswith("O:") else f"O:{symbol_raw}"


def _hhmm_to_tuple(hhmm: str) -> Tuple[int, int]:
    try:
        return int(hhmm[:2]), int(hhmm[3:5])
    except Exception:
        return (0, 0)


def is_in_night_session_kst(hhmm: str) -> bool:
    try:
        h, m = _hhmm_to_tuple(hhmm)
    except Exception:
        return False
    if h == 22 and m >= 30: return True
    if h == 23: return True
    if 0 <= h < 5: return True
    if h == 5 and m == 0: return True
    return False


def _night_session_sort_key(hhmm: str) -> int:
    h, m = _hhmm_to_tuple(hhmm)
    if h < 6:
        h += 24
    return h * 60 + m


def normalize_rows(rows: Any, tz_kst: bool = True) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not rows:
        return out
    for r in rows:
        if isinstance(r, dict) and "t" in r and all(k in r for k in ("o", "h", "l", "c")):
            try:
                ts = r["t"]
                if isinstance(ts, (int, float)) and ts > 1000000000000:
                    dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                if tz_kst:
                    dt = dt + timedelta(hours=9)
                hhmm = f"{dt.hour:02d}:{dt.minute:02d}"
                out.append(dict(
                    time=hhmm, open=float(r.get("o", 0)), high=float(r.get("h", 0)),
                    low=float(r.get("l", 0)), close=float(r.get("c", 0)),
                    volume=float(r.get("v", 0))
                ))
            except Exception:
                continue
        elif isinstance(r, dict) and all(k in r for k in ("time", "open", "high", "low", "close")):
            try:
                tt = str(r["time"])[:5]
                out.append(dict(
                    time=tt, open=float(r.get("open", 0)), high=float(r.get("high", 0)),
                    low=float(r.get("low", 0)), close=float(r.get("close", 0)),
                    volume=float(r.get("volume", 0))
                ))
            except Exception:
                continue
        elif hasattr(r, "timestamp") and hasattr(r, "open"):
            try:
                dt = datetime.fromtimestamp(r.timestamp / 1000.0, tz=timezone.utc)
                if tz_kst:
                    dt = dt + timedelta(hours=9)
                hhmm = f"{dt.hour:02d}:{dt.minute:02d}"
                out.append(dict(
                    time=hhmm, open=float(r.open), high=float(r.high),
                    low=float(r.low), close=float(r.close),
                    volume=float(getattr(r, "volume", 0.0))
                ))
            except Exception:
                continue
    return out


def filter_night_session(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows2 = [r for r in rows if is_in_night_session_kst(r.get("time", ""))]
    rows2.sort(key=lambda x: _night_session_sort_key(x["time"]))
    return rows2


def limit_rows(rows: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
    if count <= 0:
        return rows
    return rows[:count]


def cache_dir(base: str, expiry: str, strike: float, side: str) -> str:
    d = os.path.join(base, expiry, f"{strike:.1f}", side.upper())
    os.makedirs(d, exist_ok=True)
    return d


def cache_file_path(base: str, expiry: str, strike: float, side: str) -> str:
    return os.path.join(
        cache_dir(base, expiry, strike, side),
        f"spxw_{expiry}_{int(round(strike))}_{side.upper()}.csv"
    )


def _npz_path_from_csv(path_csv: str) -> str:
    root, _ = os.path.splitext(path_csv)
    return root + ".npz"


def save_rows_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    try:
        if np is not None:
            times = np.array([str(r["time"])[:5] for r in rows], dtype="U5")
            opens = np.array([float(r["open"]) for r in rows], dtype=np.float64)
            highs = np.array([float(r["high"]) for r in rows], dtype=np.float64)
            lows = np.array([float(r["low"]) for r in rows], dtype=np.float64)
            closes = np.array([float(r["close"]) for r in rows], dtype=np.float64)
            vols = np.array([float(r.get("volume", 0.0)) for r in rows], dtype=np.float64)
            np.savez_compressed(_npz_path_from_csv(path),
                                time=times, open=opens, high=highs,
                                low=lows, close=closes, volume=vols)
    except Exception as e:
        print(f"[NPZ 저장 실패] {path}: {e}")


def _rows_from_npz(npz_path: str) -> List[Dict[str, Any]]:
    if np is None:
        return []
    try:
        d = np.load(npz_path, allow_pickle=False)
        times = d["time"]
        opens = d["open"]; highs = d["high"]; lows = d["low"]
        closes = d["close"]
        vols = d["volume"] if "volume" in d else np.zeros_like(opens)
        out: List[Dict[str, Any]] = []
        for i in range(len(opens)):
            t = str(times[i])[:5]
            out.append(dict(
                time=t, open=float(opens[i]), high=float(highs[i]),
                low=float(lows[i]), close=float(closes[i]), volume=float(vols[i])
            ))
        return filter_night_session(out)
    except Exception as e:
        print(f"[NPZ 로딩 실패] {npz_path}: {e}")
        return []


@lru_cache(maxsize=4096)
def _load_npz_cached(npz_path: str, mtime: float):
    return (npz_path, _rows_from_npz(npz_path))


@lru_cache(maxsize=4096)
def _load_csv_cached(csv_path: str, mtime: float):
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(csv_path):
        return (csv_path, rows)
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                rows.append(dict(
                    time=str(row["time"])[:5], open=float(row["open"]),
                    high=float(row["high"]), low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", "0") or 0)
                ))
            except Exception:
                continue
    return (csv_path, filter_night_session(rows))


def load_rows_csv(path: str) -> List[Dict[str, Any]]:
    npz_path = _npz_path_from_csv(path)
    if os.path.exists(npz_path):
        try:
            mtime = os.path.getmtime(npz_path)
            _, rows = _load_npz_cached(npz_path, mtime)
            if rows:
                return rows
        except Exception:
            pass
    if os.path.exists(path):
        try:
            mtime = os.path.getmtime(path)
            _, rows = _load_csv_cached(path, mtime)
            return rows
        except Exception:
            return []
    return []


def fetch_minutes_polygon(provider: object, symbol_raw: str, date: str,
                          limit: int, api_key: Optional[str]) -> List[Dict[str, Any]]:
    symbol = opt_ticker(symbol_raw)
    key = _provider_key(provider)

    def _try_list_aggs():
        if hasattr(provider, "list_aggs"):
            aggs = provider.list_aggs(ticker=symbol, multiplier=1, timespan="minute",
                                      from_=date, to=date, limit=limit, adjusted=True)
            rows = normalize_rows(list(aggs), tz_kst=True)
            return limit_rows(filter_night_session(rows), limit)
        return []

    def _try_get_aggs():
        if hasattr(provider, "get_aggs"):
            aggs = provider.get_aggs(ticker=symbol, multiplier=1, timespan="minute",
                                     from_=date, to=date, limit=limit, adjusted=True)
            rows = normalize_rows(aggs, tz_kst=True)
            return limit_rows(filter_night_session(rows), limit)
        return []

    def _try_http():
        if not api_key:
            return []
        try:
            sess = _http_session()
            url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol}"
                   f"/range/1/minute/{date}/{date}")
            params = dict(adjusted=True, sort="asc", limit=limit, apiKey=api_key)
            r = (sess.get(url, params=params, timeout=20)
                 if sess else _requests_module.get(url, params=params, timeout=20))
            if r.status_code == 200:
                rows = normalize_rows(
                    (r.json() or {}).get("results", []) or [], tz_kst=True)
                return limit_rows(filter_night_session(rows), limit)
            else:
                print(f"[HTTP] {symbol} {date} {r.status_code}")
        except Exception as e:
            print(f"[HTTP 오류] {symbol} {e}")
        return []

    candidates = [
        ("list_aggs", _try_list_aggs),
        ("get_aggs", _try_get_aggs),
        ("http", _try_http),
    ]
    cached = _METHOD_CACHE.get(key)
    if cached:
        candidates.sort(key=lambda x: 0 if x[0] == cached else 1)
    for name, fn in candidates:
        try:
            rows = fn()
            if rows:
                _METHOD_CACHE[key] = name
                return rows
        except Exception as e:
            print(f"[{name}] {symbol} {e}")
    return []


def merge_call_put(data_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for rows in data_list:
        for r in rows:
            t = r["time"]
            if t not in merged:
                merged[t] = dict(time=t, open=r["open"], high=r["high"],
                                 low=r["low"], close=r["close"],
                                 volume=r.get("volume", 0.0))
            else:
                m = merged[t]
                m["open"] = (m["open"] + r["open"]) / 2.0
                m["close"] = (m["close"] + r["close"]) / 2.0
                m["high"] = max(m["high"], r["high"])
                m["low"] = min(m["low"], r["low"])
                m["volume"] = m.get("volume", 0.0) + r.get("volume", 0.0)
    out = list(merged.values())
    out.sort(key=lambda x: _night_session_sort_key(x["time"]))
    return out


def scan_windows(rows: List[Dict[str, Any]], window_minutes: int,
                 thresholds: List[float]) -> List[Tuple[int, float]]:
    if not rows or window_minutes <= 0:
        return []
    th = float(min(thresholds) if thresholds else 0.0)
    if np is not None:
        try:
            highs = np.array([r["high"] for r in rows], dtype=np.float64)
            opens = np.array([r["open"] for r in rows], dtype=np.float64)
            n = highs.size
            w = min(int(window_minutes), n)
            valid = opens > 0
            try:
                sw = np.lib.stride_tricks.sliding_window_view(highs, w)
                prefix_max = sw.max(axis=1)
            except Exception:
                prefix_max = np.array([highs[i:i + w].max() for i in range(n - w + 1)])
            suffix_max = np.maximum.accumulate(highs[::-1])[::-1]
            if w == n:
                max_fwd = np.concatenate([prefix_max, suffix_max[1:]])
            else:
                tail = suffix_max[n - (w - 1):]
                max_fwd = np.concatenate([prefix_max, tail])
            safe_opens = opens.copy()
            safe_opens[~valid] = np.nan
            with np.errstate(divide='ignore', invalid='ignore'):
                pct_calc = (max_fwd - safe_opens) / safe_opens * 100.0
            pct = np.full(n, -np.inf)
            pct[valid] = pct_calc[valid]
            mask = (pct >= th) & np.isfinite(pct)
            idxs = np.nonzero(mask)[0].tolist()
            return [(int(i), float(pct[i])) for i in idxs]
        except Exception:
            pass
    out: List[Tuple[int, float]] = []
    highs2 = [r["high"] for r in rows]
    opens2 = [r["open"] for r in rows]
    n2 = len(rows)
    for i in range(n2):
        base = opens2[i]
        if base <= 0:
            continue
        mx = max(highs2[i:min(n2, i + window_minutes)])
        pct = (mx - base) / base * 100.0
        if pct >= th:
            out.append((i, pct))
    return out


def is_us_trading_day(d: dt_date) -> bool:
    if d.weekday() >= 5:
        return False
    y = d.year
    holidays = set()
    holidays.add(datetime(y, 1, 1).date())
    holidays.add(datetime(y, 1, 1).date() + timedelta(
        days=(14 - datetime(y, 1, 1).weekday()) % 7 + 14))
    holidays.add(datetime(y, 2, 1).date() + timedelta(
        days=(14 - datetime(y, 2, 1).weekday()) % 7 + 14))
    last_may = datetime(y, 5, 31)
    holidays.add((last_may - timedelta(days=last_may.weekday())).date())
    holidays.add(datetime(y, 7, 4).date())
    holidays.add(datetime(y, 9, 1).date() + timedelta(
        days=(0 - datetime(y, 9, 1).weekday()) % 7))
    holidays.add(datetime(y, 11, 1).date() + timedelta(
        days=(3 - datetime(y, 11, 1).weekday()) % 7 + 21))
    holidays.add(datetime(y, 12, 25).date())
    return d not in holidays


def _index_existing_for_expiry(base_dir: str, expiry: str) -> Set[Tuple[float, str]]:
    out: Set[Tuple[float, str]] = set()
    root = os.path.join(base_dir, expiry)
    if not os.path.isdir(root):
        return out
    try:
        for de_strike in os.scandir(root):
            if not de_strike.is_dir():
                continue
            try:
                strike = float(de_strike.name)
            except Exception:
                continue
            for de_side in os.scandir(de_strike.path):
                if not de_side.is_dir():
                    continue
                side = de_side.name.upper()
                found = False
                for de_file in os.scandir(de_side.path):
                    if de_file.is_file() and (
                            de_file.name.endswith(".csv") or de_file.name.endswith(".npz")):
                        found = True
                        break
                if found:
                    out.add((strike, side))
    except Exception as e:
        print(f"[scandir index 오류] {root}: {e}")
    return out


# ═══════════════════════════════════════════════════════════════════
#  PART 2: 차트 캔버스 — mini_chart_canvas.py 로 분리 [S9]
# ═══════════════════════════════════════════════════════════════════
from mini_chart_canvas import MiniChartCanvas  # noqa: F401  re-export


# ═══════════════════════════════════════════════════════════════════
#  PART 3: Provider / 레이트리미터 / CD-KEY 로더
# ═══════════════════════════════════════════════════════════════════

class PolygonDataProvider:
    """Polygon REST HTTP 직접 호출용 더미 provider"""
    pass


class RateLimiter:
    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._lock = threading.Lock()
        self._calls: deque = deque()

    def acquire(self):
        while True:
            with self._lock:
                now = time.time()
                while self._calls and (now - self._calls[0]) >= self.period:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                sleep_for = self.period - (now - self._calls[0])
            time.sleep(max(0.0, sleep_for))


_POLYGON_RL = RateLimiter(max_calls=5, period=60.0)


def _load_api_key_from_file(filename: str = "CD-KEY.txt") -> str:
    """CD-KEY.txt / cd-key.txt / cd_key.txt 등 대소문자 무관하게 자동 탐색."""
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        filename,
        filename.lower(),
        filename.upper(),
        "cd_key.txt",
        "CD_KEY.txt",
        "cdkey.txt",
        "CDKEY.txt",
    ]
    for name in candidates:
        path = os.path.join(base, name)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    key = f.read().strip()
                    if key and "여기에" not in key and len(key) > 5:
                        return key
        except Exception:
            continue
    return ""


# ═══════════════════════════════════════════════════════════════════
#  PART 4: 1초봉 수집  +  섬머타임 구간 관리
# ═══════════════════════════════════════════════════════════════════

# ── 섬머타임 구간 경계 ──────────────────────────────────────────────
# · 비섬머(표준시): SPXW 미국 16:00 동부 = KST 06:00  / 시장시작 KST 23:30
#   적용 날짜:  ~ 2025-03-09  및  2025-11-05 ~
# · 섬머타임:   SPXW 미국 16:00 동부 = KST 05:00  / 시장시작 KST 22:30
#   적용 날짜:  2025-03-10 ~ 2025-11-04
#
#  판단 기준: 조회 날짜(date_str) 기준
#   · 섬머 ON  : 2025-03-10 ≤ date ≤ 2025-11-04
#   · 섬머 OFF : 그 외 (포함 ~ 2025-03-09 및 2025-11-05 ~)

_SUMMER_START = dt_date(2025, 3, 10)   # 섬머타임 시작 (KST 기준)
_SUMMER_END   = dt_date(2025, 11, 4)   # 섬머타임 종료


def _is_summer_time(date_str: str) -> bool:
    """date_str('YYYY-MM-DD')이 섬머타임 구간인지 반환."""
    try:
        d = dt_date.fromisoformat(date_str)
        return _SUMMER_START <= d <= _SUMMER_END
    except Exception:
        return False


def _session_bounds(date_str: str) -> tuple:
    """
    해당 날짜의 거래 세션 (시작HH:MM, 종료HH:MM) 반환.
    섬머: 22:30 ~ 05:00  /  비섬머: 23:30 ~ 06:00
    """
    if _is_summer_time(date_str):
        return ("22:30", "05:00")
    else:
        return ("23:30", "06:00")


def _hhmmss_to_seconds(t: str, summer: bool = True) -> int:
    """
    'HH:MM:SS' → 초 (자정 기준), 야간세션 +24h 보정.
    섬머(summer=True) : 00~05 시 → +24h  (세션 종료 05:00)
    비섬머(summer=False): 00~06 시 → +24h  (세션 종료 06:00)
    """
    try:
        h, m, s = int(t[:2]), int(t[3:5]), int(t[6:8])
        cutoff = 6 if summer else 7   # 이 시간 미만이면 익일로 간주
        if h < cutoff:
            h += 24
        return h * 3600 + m * 60 + s
    except Exception:
        return 0


def _hhmm_to_seconds(hhmm: str, summer: bool = True) -> int:
    """'HH:MM' → 초. 야간세션 보정 포함."""
    try:
        h, m = int(hhmm[:2]), int(hhmm[3:5])
        cutoff = 6 if summer else 7
        if h < cutoff:
            h += 24
        return h * 3600 + m * 60
    except Exception:
        return 0


def _filter_display_window(rows: List[Dict[str, Any]],
                           start_hhmm: str = "05:30",
                           end_hhmm:   str = "05:59",
                           date_str:   str = "") -> List[Dict[str, Any]]:
    """
    start_hhmm ~ end_hhmm (KST HH:MM) 구간의 봉만 반환.
    date_str 이 주어지면 섬머타임 보정을 자동 적용.
    end_hhmm은 :59초까지 포함.
    """
    if not rows:
        return rows
    summer = _is_summer_time(date_str) if date_str else True
    start_sec = _hhmm_to_seconds(start_hhmm, summer)
    end_sec   = _hhmm_to_seconds(end_hhmm,   summer) + 59
    filtered = [r for r in rows
                if start_sec <= _hhmmss_to_seconds(r["time"], summer) <= end_sec]
    if filtered:
        return filtered
    return rows[-180:] if len(rows) > 180 else rows


def _fetch_second_bars_polygon(api_key: str, symbol: str, date_str: str,
                               limit: int = 50000) -> List[Dict[str, Any]]:
    """
    Polygon /v2/aggs/.../range/1/second 로 하루치 1초봉 전체 수집.
    ★ 필터 없이 전체 반환 — 표시 필터(_filter_display_window)는 UI에서 별도 적용.
    limit=50000 으로 하루 전체(최대 ~23400초) 커버.
    """
    ticker = opt_ticker(symbol)
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}"
           f"/range/1/second/{date_str}/{date_str}"
           f"?adjusted=false&sort=asc&limit={limit}&apiKey={api_key}")
    try:
        resp = _requests_module.get(url, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        rows: List[Dict[str, Any]] = []
        for r in results:
            ts_ms = r.get("t", 0)
            try:
                if _KST:
                    dt_kst = datetime.fromtimestamp(ts_ms / 1000.0, tz=_KST)
                else:
                    dt_kst = datetime.utcfromtimestamp(ts_ms / 1000.0) + timedelta(hours=9)
                time_str = dt_kst.strftime("%H:%M:%S")
            except Exception:
                time_str = "??:??:??"
            rows.append({
                "time":   time_str,
                "open":   float(r.get("o", 0)),
                "high":   float(r.get("h", 0)),
                "low":    float(r.get("l", 0)),
                "close":  float(r.get("c", 0)),
                "volume": float(r.get("v", 0)),
            })
        # ★ 전체 반환 (필터 없음)
        return rows
    except Exception as e:
        print(f"[1초봉 오류] {symbol}: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════
#  PART 4b: xlsx 저장 / 읽기 유틸
# ═══════════════════════════════════════════════════════════════════

_FIELDS = ["time", "open", "high", "low", "close", "volume"]


def _make_save_path(expiry: str, symbol_raw: str) -> str:
    """
    저장 경로: C:/data/Zeroday_option_1Sec/{expiry}/{expiry}_{symbol}.xlsx
    symbol_raw 의 'O:' 프리픽스는 제거.
    """
    sym = symbol_raw.replace("O:", "").strip()
    folder = os.path.join(_SAVE_BASE_DIR, expiry)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{expiry}_{sym}.xlsx")


def _save_rows_xlsx(path: str, rows: List[Dict[str, Any]]) -> None:
    """rows(전체 하루치) 를 xlsx로 저장. 필드 순서: time, open, high, low, close, volume."""
    if not _HAS_OPENPYXL:
        raise RuntimeError("openpyxl 미설치 — pip install openpyxl")
    wb = Workbook()
    ws = wb.active
    ws.title = "1sec_bars"
    ws.append(_FIELDS)           # 헤더
    for r in rows:
        ws.append([
            r.get("time", ""),
            r.get("open", 0),
            r.get("high", 0),
            r.get("low", 0),
            r.get("close", 0),
            r.get("volume", 0),
        ])
    wb.save(path)


def _load_rows_xlsx(path: str) -> List[Dict[str, Any]]:
    """xlsx 파일에서 봉 데이터를 읽어 rows 리스트로 반환."""
    if not _HAS_OPENPYXL:
        raise RuntimeError("openpyxl 미설치 — pip install openpyxl")
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows: List[Dict[str, Any]] = []
    header = None
    for row in ws.iter_rows(values_only=True):
        if header is None:
            header = [str(c).lower() for c in row]
            continue
        try:
            d = dict(zip(header, row))
            rows.append({
                "time":   str(d.get("time", "")),
                "open":   float(d.get("open",  0) or 0),
                "high":   float(d.get("high",  0) or 0),
                "low":    float(d.get("low",   0) or 0),
                "close":  float(d.get("close", 0) or 0),
                "volume": float(d.get("volume",0) or 0),
            })
        except Exception:
            continue
    wb.close()
    return rows


def _list_xlsx_for_date(expiry: str) -> List[str]:
    """저장 폴더에서 해당 만기일의 xlsx 파일 목록 반환 (파일명만)."""
    folder = os.path.join(_SAVE_BASE_DIR, expiry)
    if not os.path.isdir(folder):
        return []
    return sorted([f for f in os.listdir(folder) if f.endswith(".xlsx")])


# ═══════════════════════════════════════════════════════════════════
