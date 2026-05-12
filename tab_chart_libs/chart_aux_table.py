"""
chart_aux_table.py — FTD / 공매도 보조 파일 테이블
[분리] chart_peaks.py 에서 분리 (load_aux_file, _fill_aux_table, on_aux_date_click)
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime
from PyQt5.QtWidgets import QTableWidgetItem, QHeaderView
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QDate

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from chart_theme import _THEME
try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")


def load_aux_file(self):
    C   = _THEME[self.dark_mode]
    sym = (self.file_sym_in.text().strip().lower()
           or self.sym_in.text().strip().lower())
    if not sym:
        self.file_status_lbl.setText("⚠ 종목을 입력하세요"); return
    file_type = self.file_type_combo.currentIndex()
    if file_type == 0:
        fp = DATA_ROOT / f"nyse-{sym}.fails_to_deliver.csv"; label = "FTD"
    else:
        fp = DATA_ROOT / f"nyse-{sym}.short_volume.csv";     label = "공매도"
    if not fp.exists():
        self.file_status_lbl.setText(f"❌ 파일 없음: {fp.name}")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:red;"); return
    if not PANDAS:
        self.file_status_lbl.setText("❌ pandas 미설치"); return

    df = None
    try:
        df = pd.read_csv(str(fp), encoding='latin-1', sep=None, engine='python')
    except Exception:
        try:
            from io import StringIO
            with open(str(fp), 'rb') as f:
                raw = f.read().decode('latin-1', errors='replace')
            df = pd.read_csv(StringIO(raw), sep=None, engine='python')
        except Exception as ex:
            self.file_status_lbl.setText(f"❌ 파일 읽기 실패: {str(ex)[:50]}")
            self.file_status_lbl.setStyleSheet("font-size:11px;color:red;"); return

    df.columns = [c.strip() for c in df.columns]

    def clean(val):
        v = str(val).strip().replace(",", "").replace(" ", "")
        return v if v not in ("", "-") else "0"

    self.table_r.setRowCount(0)
    # [수정] 중복 연결 방지: disconnect 후 재연결
    try: self.table_r.cellClicked.disconnect()
    except Exception: pass
    self.table_r.cellClicked.connect(lambda r, c: on_aux_date_click(self, r, c))

    try:
        _fill_aux_table(self, df, file_type, label, clean, C)
        count = self.table_r.rowCount()
        self.file_status_lbl.setText(f"✅ {label} {count}행 로드 (최신순)")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:green;")
        self.table_r.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_r.scrollToTop()
    except Exception as ex:
        self.file_status_lbl.setText(f"❌ 파싱 오류: {str(ex)[:60]}")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:red;")
        import traceback; traceback.print_exc()



# [분리] 테이블 채우기 + 날짜 클릭 핸들러 → chart_aux_fill.py
from chart_aux_fill import (  # noqa: F401
    _fill_aux_table, _set_ftd_row, _set_short_row,
    on_aux_date_click,
)
