"""
chart_data_table.py — 우측 테이블 추가/초기화 + 추세판 push
[분리] chart_data.py 에서 분리 (append_right, clr_right, push_trend_df)
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from chart_theme import _THEME

def append_right(self, data, eok):
    C = _THEME[self.dark_mode]
    from core import ts
    try:
        et_s = (pd.Timestamp(data['s'], unit='ms', tz='UTC')
                .tz_convert('America/New_York').strftime('%H:%M:%S')
                if PANDAS else ts())
    except Exception:
        et_s = ts()
    r = self.table_r.rowCount(); self.table_r.insertRow(r)
    vals = [et_s,
            f"{data.get('o', 0):,.2f}", f"{data.get('h', 0):,.2f}",
            f"{data.get('l', 0):,.2f}", f"{data.get('c', 0):,.2f}",
            f"{eok:,.2f}", "실시간"]
    for ci, v in enumerate(vals):
        it = QTableWidgetItem(str(v))
        it.setTextAlignment(Qt.AlignCenter)
        it.setForeground(QColor(C['fg']))
        self.table_r.setItem(r, ci, it)
        if ci == 5:
            bg = (C['row_hi'] if eok >= 5000
                  else (C['row_mid'] if eok >= 3000 else C['row_lo']))
            self.table_r.item(r, ci).setBackground(QColor(bg))
    self.table_r.scrollToBottom()


def clr_right(self):
    self.table_r.setRowCount(0)


def push_trend_df(self):
    if not PANDAS or self.df is None or self.df.empty: return
    try:
        combo = getattr(self.mw, 'tab_combo', None)
        if combo and hasattr(combo, 'set_trend_df'):
            col_map = {'o': 'open', 'h': 'high', 'l': 'low',
                       'c': 'close', 'v': 'volume'}
            combo.set_trend_df(self.df.rename(columns=col_map))
    except Exception as e:
        print(f"[ChartGrid] _push_trend_df 오류: {e}")