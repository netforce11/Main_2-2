"""
chart_aux_fill.py — FTD / 공매도 테이블 셀 채우기 로직
[분리] chart_aux_table.py 에서 분리
  _fill_aux_table, _set_ftd_row, _set_short_row
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

try:
    import pandas as pd
except ImportError:
    pd = None

def _fill_aux_table(self, df, file_type, label, clean, C):
    if file_type == 0:
        date_col = "settlement"
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(
                df[date_col].astype(str).str.strip(),
                format="%Y%m%d", errors='coerce')
            df = df.sort_values(date_col, ascending=False).reset_index(drop=True)
        self.table_r.setColumnCount(7)
        self.table_r.setHorizontalHeaderLabels(
            ["결제일", "FTD수량", "가격($)", "변화량", "명목금액($)", "T+35일", "구분"])
        for _, row in df.iterrows():
            ri = self.table_r.rowCount(); self.table_r.insertRow(ri)
            raw_d = row.get(date_col, None)
            settle_val = (raw_d.strftime("%Y-%m-%d")
                          if pd.notna(raw_d) and hasattr(raw_d, 'strftime')
                          else str(row.get(date_col, "-")).strip())
            vals = [settle_val,
                    clean(row.get("ftd", row.get(" ftd ", "0"))),
                    clean(row.get("price", "0")),
                    clean(row.get("change", "0")),
                    clean(row.get("notional", row.get(" notional ", "0"))),
                    str(row.get("t35", "-")).strip(), label]
            _set_ftd_row(self, ri, vals, C)
    else:
        date_col = "Date"
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(
                df[date_col].astype(str).str.strip(),
                infer_datetime_format=True, errors='coerce')
            df = df.sort_values(date_col, ascending=False).reset_index(drop=True)
        self.table_r.setColumnCount(7)
        self.table_r.setHorizontalHeaderLabels(
            ["날짜", "총보고량", "총공매도", "총롱", "공매도비율(%)", "FINRA", "구분"])
        for _, row in df.iterrows():
            ri = self.table_r.rowCount(); self.table_r.insertRow(ri)
            raw_d    = row.get(date_col, None)
            date_val = (raw_d.strftime("%Y-%m-%d")
                        if pd.notna(raw_d) and hasattr(raw_d, 'strftime')
                        else str(row.get(date_col, "-")).strip())
            reported = clean(row.get("total_reported", "0"))
            short    = clean(row.get("total_short", "0"))
            long_    = clean(row.get("total_long", "0"))
            finra    = clean(row.get("FINRA", "0"))
            ratio_r  = row.get("Short_ratio", None)
            if ratio_r is not None and str(ratio_r).strip() not in ("", "-"):
                try:   ratio_val = f"{float(str(ratio_r).replace(',', '')):.2f}"
                except: ratio_val = "0.00"
            else:
                try:
                    s = float(short); rep = float(reported)
                    ratio_val = f"{s/rep*100:.2f}" if rep > 0 else "0.00"
                except: ratio_val = "0.00"
            vals = [date_val, reported, short, long_, ratio_val, finra, label]
            _set_short_row(self, ri, vals, C)


def _set_ftd_row(self, ri, vals, C):
    for j, v in enumerate(vals):
        it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter)
        it.setForeground(QColor(C['fg']))
        if j == 1:
            try:
                q = float(v)
                if   q >= 500_000: it.setBackground(QColor(C['row_hi']))
                elif q >= 100_000: it.setBackground(QColor(C['row_mid']))
                elif q >= 10_000:  it.setBackground(QColor(C['row_lo']))
            except Exception: pass
        if j == 3:
            try:
                fv = float(v)
                if fv < 0:  it.setForeground(QColor("#ff5555"))
                elif fv > 0: it.setForeground(QColor("#55cc55"))
            except Exception: pass
        self.table_r.setItem(ri, j, it)


def _set_short_row(self, ri, vals, C):
    for j, v in enumerate(vals):
        it = QTableWidgetItem(v); it.setTextAlignment(Qt.AlignCenter)
        it.setForeground(QColor(C['fg']))
        if j == 4:
            try:
                rv = float(v)
                if   rv >= 60: it.setBackground(QColor(C['row_hi']))
                elif rv >= 50: it.setBackground(QColor(C['row_mid']))
                elif rv >= 40: it.setBackground(QColor(C['row_lo']))
            except Exception: pass
        if j == 2:
            try:
                sv = float(v.replace(",", ""))
                if   sv >= 50_000_000: it.setBackground(QColor(C['row_hi']))
                elif sv >= 20_000_000: it.setBackground(QColor(C['row_mid']))
                elif sv >= 10_000_000: it.setBackground(QColor(C['row_lo']))
            except Exception: pass
        self.table_r.setItem(ri, j, it)


def on_aux_date_click(self, row: int, col: int):
    if col != 0: return
    item = self.table_r.item(row, col)
    if not item: return
    date_str = item.text().strip()
    if not date_str or date_str == "-": return

    tgt = None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
        try: tgt = datetime.strptime(date_str, fmt).date(); break
        except ValueError: continue
    if tgt is None:
        self.file_status_lbl.setText(f"⚠ 날짜 파싱 실패: {date_str}"); return

    sym = (self.file_sym_in.text().strip().upper()
           or self.sym_in.text().strip().upper())
    if not sym:
        self.file_status_lbl.setText("⚠ 종목을 입력하세요"); return

    from chart_rt import stop_rt
    stop_rt(self)
    self.sym_in.setText(sym)
    self.calendar.setSelectedDate(QDate(tgt.year, tgt.month, tgt.day))

    from chart_data import load_day_df, update_display
    df = load_day_df(self, sym, tgt)
    if df is None or df.empty:
        self.file_status_lbl.setText(f"⚠ {tgt} 차트 데이터 없음 (휴장일?)")
        self.file_status_lbl.setStyleSheet("font-size:11px;color:orange;"); return

    self.df = df; self.df_raw = df.to_dict('records')
    self.selected_date = tgt
    self.file_status_lbl.setText(f"✅ {tgt} 차트 로드 완료")
    self.file_status_lbl.setStyleSheet("font-size:11px;color:green;")
    update_display(self)
    try:
        import pyqtgraph as pg; self.p1.autoRange()
    except Exception: pass
