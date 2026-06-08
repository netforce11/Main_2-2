"""
chart_daily_worker.py — 일봉 데이터 다운로드 워커 (QThread)
[분리] chart_daily.py 에서 분리 (_DailyFillWorker)
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import requests
from datetime import datetime, timedelta, date as _date

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from PyQt5.QtCore import QThread, pyqtSignal

from chart_daily_helpers import (
    _daily_csv_path, _has_daily_marker, _set_daily_marker
)

class _DailyFillWorker(QThread):
    """
    캘린더 날짜 ± 80 캘린더일 범위에서
    마커 없는 날짜만 Polygon /1/day 로 채운다.
    완료 후 done(df) 시그널 발생.
    """
    done    = pyqtSignal(object)   # pd.DataFrame 또는 None
    status  = pyqtSignal(str)      # 상태 메시지
    error   = pyqtSignal(str)

    def __init__(self, symbol, center_date_str, api_key):
        super().__init__()
        self.symbol          = symbol.upper()
        self.center_date_str = center_date_str   # 'YYYY-MM-DD'
        self.api_key         = api_key

    def run(self):
        if not PANDAS:
            self.error.emit("pandas 없음"); return
        try:
            sym    = self.symbol
            center = datetime.strptime(self.center_date_str, "%Y-%m-%d").date()
            t_from = center - timedelta(days=80)
            t_to   = center + timedelta(days=80)

            csv_path = _daily_csv_path(sym)

            # ── 기존 CSV 로드 ──────────────────────────
            if csv_path.exists():
                try:
                    existing = pd.read_csv(str(csv_path))
                except Exception:
                    existing = pd.DataFrame()
            else:
                existing = pd.DataFrame()

            # ── 빠진 날짜 계산 ─────────────────────────
            all_dates = [t_from + timedelta(days=i)
                         for i in range((t_to - t_from).days + 1)]

            missing = []
            for d in all_dates:
                if d > _date.today(): continue
                if not _has_daily_marker(sym, d):
                    missing.append(d)

            if missing:
                self.status.emit(
                    f"📈 일봉 {len(missing)}일 다운로드 중…  ({sym})")
                self._download_missing(sym, missing, csv_path, existing)
            else:
                self.status.emit(f"📈 일봉 로컬 캐시 사용  ({sym})")

            # ── 최종 CSV 읽어서 반환 ───────────────────
            if csv_path.exists():
                df = pd.read_csv(str(csv_path))
                if not df.empty:
                    df = df.sort_values('t').reset_index(drop=True)
                    self.done.emit(df)
                    return
            self.done.emit(None)

        except Exception as e:
            self.error.emit(str(e))

    def _download_missing(self, sym, missing_dates, csv_path, existing_df):
        """빠진 날짜들을 날짜 범위로 묶어서 최소 API 호출로 채운다."""
        if not missing_dates:
            return

        chunks = []
        chunk_start = missing_dates[0]
        prev        = missing_dates[0]
        for d in missing_dates[1:]:
            if (d - prev).days > 5 or (d - chunk_start).days >= 30:
                chunks.append((chunk_start, prev))
                chunk_start = d
            prev = d
        chunks.append((chunk_start, prev))

        all_new = []
        for t_from, t_to in chunks:
            url = (
                f"https://api.polygon.io/v2/aggs/ticker/{sym}/range"
                f"/1/day/{t_from}/{t_to}"
                f"?adjusted=true&sort=asc&limit=300&apiKey={self.api_key}"
            )
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                results = r.json().get("results", [])
                if results:
                    all_new.extend(results)
                    for row in results:
                        bar_date = datetime.fromtimestamp(
                            row["t"] / 1000).date()
                        _set_daily_marker(sym, bar_date)
                d = t_from
                while d <= t_to:
                    if not _has_daily_marker(sym, d):
                        _set_daily_marker(sym, d)
                    d += timedelta(days=1)
            except Exception as e:
                print(f"[DailyFill] API 오류 {t_from}~{t_to}: {e}")

        if not all_new:
            return

        new_df = pd.DataFrame(all_new)[["t","o","h","l","c","v"]]

        if not existing_df.empty:
            cols = [c for c in ["t","o","h","l","c","v"]
                    if c in existing_df.columns]
            merged = (pd.concat([existing_df[cols], new_df])
                      .drop_duplicates(subset=["t"])
                      .sort_values("t")
                      .reset_index(drop=True))
        else:
            merged = new_df

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(str(csv_path), index=False)
        print(f"[DailyFill] {sym} 일봉 CSV 저장 완료 ({len(merged)}행)")


# ══════════════════════════════════════════════════════════════
# 위임 함수들 (self = ChartGrid 인스턴스)
# ══════════════════════════════════════════════════════════════

