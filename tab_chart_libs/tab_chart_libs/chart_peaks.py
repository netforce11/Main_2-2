"""
chart_peaks.py — 수급 피크 검색
────────────────────────────────────────────────────────
포함:
  peak1()        — ±30분 최대 검색
  peak2()        — 구간 합산
  update_peak3() — 테이블 다중선택 합산

[분리] FTD/공매도 테이블 → chart_aux_table.py
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime, timedelta

# [분리] FTD/공매도 관련 함수는 chart_aux_table 에서 re-export
from chart_aux_table import load_aux_file, on_aux_date_click  # noqa: F401


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
