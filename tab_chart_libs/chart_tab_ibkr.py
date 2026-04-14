"""
chart_tab_ibkr.py — IBKR/Polygon 과거 데이터 요청 (tab_chart 전용)
────────────────────────────────────────────────────────
포함:
  fetch_ibkr_history()    — IBKR reqHistoricalData
  fetch_polygon_history() — Polygon REST fallback
  load_day_df()           — pickle → CSV → API 삼단 fallback
  download_day()          — Polygon API → CSV 저장
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


import requests
from datetime import datetime, timedelta, time

from PyQt5.QtWidgets import QMessageBox

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from core import bridge, make_und_contract, REQ_HIST, auto_mdt

try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path(r"C:\data\US_StockData")

def _marker_path(symbol_up, tgt):
    """다운로드 완료 마커 파일 경로"""
    from pathlib import Path
    return DATA_ROOT / symbol_up / ".downloaded" / tgt.strftime("%Y%m%d")

def _set_marker(symbol_up, tgt):
    """다운로드 완료 마커 생성"""
    mp = _marker_path(symbol_up, tgt)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.touch()

def _has_marker(symbol_up, tgt):
    return _marker_path(symbol_up, tgt).exists()

def _clear_marker(symbol_up, tgt):
    mp = _marker_path(symbol_up, tgt)
    if mp.exists():
        mp.unlink()

def force_redownload(self, symbol: str, tgt):
    """마커 삭제 + CSV에서 해당 날짜 행 제거 → API 재다운로드 → 화면 갱신"""
    if not PANDAS: return
    symbol_up = symbol.upper()
    month_str = tgt.strftime("%Y%m")
    from pathlib import Path
    csv_path  = DATA_ROOT / symbol_up / f"{month_str}.csv"

    # 1) 마커 삭제
    _clear_marker(symbol_up, tgt)

    # 2) CSV에서 해당 날짜 행만 제거
    if csv_path.exists():
        try:
            full = pd.read_csv(str(csv_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            cleaned = full[full['_d'] != tgt].drop(columns=['_d'])
            cleaned.to_csv(str(csv_path), index=False)
            print(f"[ChartTab] {tgt} 기존 데이터 제거 완료")
        except Exception as ex:
            print(f"[ChartTab] CSV 정리 실패: {ex}")

    # 3) 재다운로드 후 화면 갱신
    fetch_polygon_history(self, symbol_up, tgt)

def fetch_ibkr_history(self, symbol, tgt):
    if not self.mw.connected:
        QMessageBox.warning(self, "미연결", "TWS에 연결하세요."); return
    auto_mdt(self.mw.ib)
    c     = make_und_contract(symbol)
    end_s = datetime.combine(tgt, time(23, 59, 59)).strftime("%Y%m%d %H:%M:%S")
    self.df_raw.clear()
    self.mw.ib.reqHistoricalData(
        REQ_HIST, c, end_s, "1 D", "1 min", "TRADES", 1, 1, False, [])
    bridge.hist_bar.connect(_on_ibkr_hist_bar.__get__(self))
    bridge.hist_end.connect(_on_ibkr_hist_end.__get__(self))


def _on_ibkr_hist_bar(self, rid, bar):
    if rid != REQ_HIST: return
    try:
        dt = datetime.strptime(bar.date, "%Y%m%d  %H:%M:%S")
        self.df_raw.append({"t": int(dt.timestamp() * 1000),
            "o": bar.open, "h": bar.high, "l": bar.low,
            "c": bar.close, "v": bar.volume})
    except Exception: pass


def _on_ibkr_hist_end(self, rid):
    if rid != REQ_HIST: return
    try: bridge.hist_bar.disconnect(_on_ibkr_hist_bar.__get__(self))
    except Exception: pass
    try: bridge.hist_end.disconnect(_on_ibkr_hist_end.__get__(self))
    except Exception: pass
    self._update_display()
    if PANDAS and self.df_raw:
        try: self.df = pd.DataFrame(self.df_raw)
        except Exception: pass
    self._push_trend_df()


# ── Polygon 과거 ────────────────────────────────────────

def fetch_polygon_history(self, symbol, tgt):
    df = load_day_df(self, symbol, tgt)
    if df is not None and not df.empty:
        self.df = df
        self.df_raw = df.to_dict('records')
        self.status_lbl.setText(f"📅 {tgt} 복기 (ET)")
        self._update_display()
        if PG: self.p1.autoRange()
        self._push_trend_df()
    else:
        QMessageBox.warning(self, "데이터 없음",
            f"{tgt} 데이터가 없습니다.\n(휴장일 또는 API 오류)")


def load_day_df(self, symbol: str, tgt):
    if not PANDAS: return None
    symbol_up  = symbol.upper()
    year, month = tgt.year, tgt.month
    from pathlib import Path

    # ── 1단계: pickle ───────────────────────────────────
    pkl_dir  = DATA_ROOT / symbol_up / "minute" / str(year) / f"{month:02d}"
    pkl_path = pkl_dir / f"{symbol_up}_{year}_{month:02d}.pkl"
    if pkl_path.exists():
        try:
            full = pd.read_pickle(str(pkl_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty:
                return res.drop(columns=['_d'])   # pickle은 완성본으로 간주
        except Exception as ex:
            print(f"[ChartTab] pickle 읽기 실패: {ex}")

    month_str = tgt.strftime("%Y%m")
    csv_path  = DATA_ROOT / symbol_up / f"{month_str}.csv"

    # ── 2단계: 마커 있으면 CSV 그대로 신뢰 ────────────
    if _has_marker(symbol_up, tgt) and csv_path.exists():
        try:
            full = pd.read_csv(str(csv_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty:
                return res.drop(columns=['_d'])
        except Exception as ex:
            print(f"[ChartTab] CSV 읽기 실패: {ex}")

    # ── 3단계: 마커 없음 → API 재다운로드 ──────────────
    print(f"[ChartTab] {tgt} 마커 없음 → API 다운로드")
    download_day(self, symbol_up, tgt, csv_path)
    if csv_path.exists():
        try:
            full = pd.read_csv(str(csv_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty:
                return res.drop(columns=['_d'])
        except Exception as ex:
            print(f"[ChartTab] API 다운로드 후 읽기 실패: {ex}")
    return None


def download_day(self, symbol: str, tgt, fp):
    if not self.api_key: return
    ds  = tgt.strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}"
           f"/range/1/minute/{ds}/{ds}"
           f"?apiKey={self.api_key}&limit=50000")
    try:
        r = requests.get(url, timeout=15).json()
        if 'results' in r and r['results']:
            ndf = pd.DataFrame(r['results'])
            fp.parent.mkdir(parents=True, exist_ok=True)
            if fp.exists():
                ndf = (pd.concat([pd.read_csv(str(fp)), ndf])
                       .drop_duplicates(subset=['t']).reset_index(drop=True))
            ndf.to_csv(str(fp), index=False)
            _set_marker(symbol.upper(), tgt)   # ✅ 완료 마커 생성
            print(f"[ChartTab] {tgt} 다운로드 완료 ({len(ndf)}행) → 마커 생성")
        else:
            print(f"[ChartTab] {tgt} API 결과 없음 (휴장일 가능성)")
    except Exception as e:
        print(f"[ChartTab] _download_day: {e}")


# ── 디스플레이 업데이트 ─────────────────────────────────

# ── tab_chart.py 위임 연결 안내 ────────────────────────
# ChartGrid.__init__ 또는 _bind() 에 아래 추가 필요:
#
#   from chart_tab_ibkr import force_redownload
#
#   def _on_force_reload(self):
#       tgt = self.calendar.selectedDate().toPyDate()
#       sym = self.sym_in.text().strip().upper()
#       if sym:
#           force_redownload(self, sym, tgt)