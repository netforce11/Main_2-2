"""
chart_peaks.py — 수급 피크 검색 + FTD/공매도 보조 파일
────────────────────────────────────────────────────────
포함:
  peak1()             — ±30분 최대 검색
  peak2()             — 구간 합산
  update_peak3()      — 테이블 다중선택 합산
  load_aux_file()     — FTD/공매도 CSV 로드
  on_aux_date_click() — 날짜 셀 클릭 → 차트 이동
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


from datetime import datetime, timedelta

from PyQt5.QtWidgets import QTableWidgetItem, QHeaderView
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, QDate

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False
    pd = None

from chart_theme import _THEME

try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")


def _time_to_min(t_str: str) -> int:
    try:
        h, m = map(int, t_str.split(":"))
        return h * 60 + m
    except Exception:
        return 0


def peak1(self):
    if not self.current_processed:
        self.pk1_lbl.setText("데이터 없음"); return
    try:
        t0 = datetime.strptime(self.pk1_in.text().strip(), "%H:%M")
        s  = (t0 - timedelta(minutes=30)).time()
        e  = (t0 + timedelta(minutes=30)).time()
        w  = [(r, et, eok) for r, et, eok in self.current_processed
              if s <= et.time() <= e]
        if not w: self.pk1_lbl.setText("데이터 없음"); return
        mx = max(w, key=lambda x: x[2])
        self.pk1_lbl.setText(
            f"피크: {mx[1].strftime('%H:%M')}\n최대: {mx[2]:.2f}억")
    except Exception:
        self.pk1_lbl.setText("형식 오류 (HH:MM)")


def peak2(self):
    if not self.current_processed:
        self.pk2_lbl.setText("데이터 없음"); return
    try:
        s = datetime.strptime(self.pk2_s.text().strip(), "%H:%M").time()
        e = datetime.strptime(self.pk2_e.text().strip(), "%H:%M").time()
        w = [(r, et, eok) for r, et, eok in self.current_processed
             if s <= et.time() <= e]
        if not w: self.pk2_lbl.setText("데이터 없음"); return
        tot = sum(x[2] for x in w)
        mx  = max(w, key=lambda x: x[2])
        self.pk2_lbl.setText(
            f"합산: {tot:.2f}억 ({len(w)}봉)\n"
            f"피크: {mx[1].strftime('%H:%M')} ({mx[2]:.2f}억)")
    except Exception:
        self.pk2_lbl.setText("형식 오류 (HH:MM)")


def update_peak3(self, tbl):
    rows  = set(it.row() for it in tbl.selectedItems())
    total = 0.0; times = []
    for r in sorted(rows):
        ei = tbl.item(r, 5); ti = tbl.item(r, 0)
        if ei and ti:
            try:
                total += float(ei.text()); times.append(ti.text()[:5])
            except Exception:
                pass
    if rows:
        self.pk3_lbl.setText(
            f"선택 {len(rows)}봉 합산:\n{total:.2f}억\n"
            f"({', '.join(times[:6])}{'...' if len(times) > 6 else ''})")
    else:
        self.pk3_lbl.setText("선택 합산: 0.00억")


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
    try:
        self.table_r.cellClicked.disconnect(on_aux_date_click)
    except Exception:
        pass
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
    """FTD/공매도 테이블 날짜 셀 클릭 → 해당 날짜 차트 자동 이동."""
    if col != 0: return
    item = self.table_r.item(row, col)
    if not item: return
    date_str = item.text().strip()
    if not date_str or date_str == "-": return

    from datetime import date as _date
    tgt = None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            tgt = datetime.strptime(date_str, fmt).date(); break
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

    self.df = df
    self.df_raw = df.to_dict('records')
    self.selected_date = tgt
    self.file_status_lbl.setText(f"✅ {tgt} 차트 로드 완료")
    self.file_status_lbl.setStyleSheet("font-size:11px;color:green;")
    update_display(self)
    try:
        import pyqtgraph as pg
        self.p1.autoRange()
    except Exception: pass