"""
chart_data_render.py — update_display 테이블 렌더링 (hi_rows → table_l)
[분리] chart_data.py 에서 분리
"""
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from chart_theme import _THEME

def _render_left_table(self, hi_rows, fx, C):
    hi_sorted = sorted(hi_rows, key=lambda x: -x[3])
    self.table_l.setRowCount(len(hi_sorted))
    for ri, (i, r, et, eok) in enumerate(hi_sorted):
        et_s = et.strftime('%H:%M:%S')
        vals = [et_s,
                f"{r.get('o', 0):,.2f}", f"{r.get('h', 0):,.2f}",
                f"{r.get('l', 0):,.2f}", f"{r.get('c', 0):,.2f}",
                f"{eok:,.2f}"]
        for ci, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignCenter)
            it.setForeground(QColor(C['fg']))
            self.table_l.setItem(ri, ci, it)
            if ci == 5:
                bg = (C['row_hi'] if eok >= 5000
                      else (C['row_mid'] if eok >= 3000 else C['row_lo']))
                self.table_l.item(ri, ci).setBackground(QColor(bg))
