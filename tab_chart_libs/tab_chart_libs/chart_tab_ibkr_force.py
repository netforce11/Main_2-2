"""
chart_tab_ibkr_force.py — 강제 재다운로드 (force_redownload)
[분리] chart_tab_ibkr.py 에서 분리
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import QMessageBox
try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False

try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")

# ── 강제 재다운로드 ──────────────────────────────────────

def force_redownload(self):
    """기존 CSV 캐시를 삭제하고 Polygon API에서 강제 재다운로드."""
    if not PANDAS:
        QMessageBox.warning(self, "오류", "pandas 가 설치되지 않았습니다."); return
    symbol = self.sym_in.text().upper().strip()
    if not symbol:
        QMessageBox.warning(self, "오류", "종목 코드를 입력하세요."); return
    qd  = self.calendar.selectedDate()
    from datetime import date
    tgt = date(qd.year(), qd.month(), qd.day())
    month_str = tgt.strftime("%Y%m")
    from pathlib import Path
    csv_path = DATA_ROOT / symbol / f"{month_str}.csv"
    # 기존 CSV 삭제
    if csv_path.exists():
        try:
            csv_path.unlink()
            print(f"[ChartTab] 캐시 삭제: {csv_path}")
        except Exception as e:
            print(f"[ChartTab] 캐시 삭제 실패: {e}")
    # 재다운로드 후 표시
    download_day(self, symbol, tgt, csv_path)
    from chart_data import update_display, push_trend_df
    df = load_day_df(self, symbol, tgt)
    if df is not None and not df.empty:
        self.df = df
        self.df_raw = df.to_dict('records')
        self.status_lbl.setText(f"📅 {tgt} 강제 재다운로드 완료 (ET)")
        update_display(self)
        try:
            import pyqtgraph as pg
            self.p1.autoRange()
        except Exception: pass
        push_trend_df(self)
    else:
        QMessageBox.warning(self, "데이터 없음",
            f"{tgt} 재다운로드 실패.\n(휴장일 또는 API 오류)")