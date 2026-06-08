"""
chart_tab_ibkr.py — IBKR/Polygon 과거 데이터 요청 (tab_chart 전용)
────────────────────────────────────────────────────────
포함:
  fetch_ibkr_history()    — IBKR reqHistoricalData
  fetch_polygon_history() — Polygon REST fallback
  load_day_df()           — pickle → CSV → API 삼단 fallback
  download_day()          — Polygon API → CSV 저장
  force_redownload()      — CSV 삭제 후 강제 재다운로드
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
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")

# ── chart_data 에서 update_display / push_trend_df 를 직접 import 하지 않음
# ── 순환참조 방지: 각 함수 내부에서 lazy import 사용


def fetch_ibkr_history(self, symbol, tgt):
    if not self.mw.connected:
        QMessageBox.warning(self, "미연결", "TWS에 연결하세요."); return
    auto_mdt(self.mw.ib)
    c     = make_und_contract(symbol)
    end_s = datetime.combine(tgt, time(23, 59, 59)).strftime("%Y%m%d %H:%M:%S")
    self.df_raw.clear()

    # [수정] 이전 연결이 남아있으면 먼저 해제 (반복 조회 시 중복 연결 방지)
    try: bridge.hist_bar.disconnect(_on_ibkr_hist_bar.__get__(self))
    except Exception: pass
    try: bridge.hist_end.disconnect(_on_ibkr_hist_end.__get__(self))
    except Exception: pass

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

    # ── 순환참조 방지: lazy import ──────────────────────────
    from chart_data import update_display, push_trend_df

    update_display(self)
    if PANDAS and self.df_raw:
        try: self.df = pd.DataFrame(self.df_raw)
        except Exception: pass
    push_trend_df(self)


# ── Polygon 과거 ────────────────────────────────────────

def fetch_polygon_history(self, symbol, tgt):
    df = load_day_df(self, symbol, tgt)
    if df is not None and not df.empty:
        self.df = df
        self.df_raw = df.to_dict('records')
        self.status_lbl.setText(f"📅 {tgt} 복기 (ET)")

        # ── 순환참조 방지: lazy import ──────────────────────
        from chart_data import update_display, push_trend_df

        update_display(self)
        if PG: self.p1.autoRange()
        push_trend_df(self)
    else:
        QMessageBox.warning(self, "데이터 없음",
            f"{tgt} 데이터가 없습니다.\n(휴장일 또는 API 오류)")


def load_day_df(self, symbol: str, tgt):
    if not PANDAS: return None
    symbol_up  = symbol.upper()
    year, month = tgt.year, tgt.month
    from pathlib import Path
    pkl_dir  = DATA_ROOT / symbol_up / "minute" / str(year) / f"{month:02d}"
    pkl_path = pkl_dir / f"{symbol_up}_{year}_{month:02d}.pkl"
    if pkl_path.exists():
        try:
            full = pd.read_pickle(str(pkl_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty: return res.drop(columns=['_d'])
        except Exception as ex:
            print(f"[ChartTab] pickle 읽기 실패: {ex}")
    month_str = tgt.strftime("%Y%m")
    csv_path  = DATA_ROOT / symbol_up / f"{month_str}.csv"
    if csv_path.exists():
        try:
            full = pd.read_csv(str(csv_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty: return res.drop(columns=['_d'])
        except Exception as ex:
            print(f"[ChartTab] CSV 읽기 실패: {ex}")
    download_day(self, symbol_up, tgt, csv_path)
    if csv_path.exists():
        try:
            full = pd.read_csv(str(csv_path))
            full['_d'] = (pd.to_datetime(full['t'], unit='ms')
                .dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.date)
            res = full[full['_d'] == tgt].copy()
            if not res.empty: return res.drop(columns=['_d'])
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
    except Exception as e:
        print(f"[ChartTab] _download_day: {e}")



# [분리] force_redownload → chart_tab_ibkr_force.py
from chart_tab_ibkr_force import force_redownload  # noqa: F401
