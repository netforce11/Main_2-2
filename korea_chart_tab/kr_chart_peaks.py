"""
kr_chart_peaks.py — 수급 피크 분석 (±30분 최대, 구간 합산, 다중선택 합산)
"""
import re


def _parse_t(txt: str) -> int:
    """HH:MM 또는 HHMM → 분 단위 정수. 실패 시 -1."""
    txt = txt.strip()
    if re.match(r'^\d{3,4}$', txt):
        if len(txt) == 3: h, m = int(txt[0]), int(txt[1:])
        else:             h, m = int(txt[:2]), int(txt[2:])
        return h * 60 + m
    if re.match(r'^\d{1,2}:\d{2}$', txt):
        h, m = map(int, txt.split(":")); return h * 60 + m
    return -1


def _row_eok(processed, i: int) -> float:
    """current_processed[i] → 거래대금(억)"""
    try: return processed[i][2]
    except: return 0.0


def _row_time_min(processed, i: int) -> int:
    """current_processed[i] → KST 분 단위"""
    try:
        kst = processed[i][1]
        return kst.hour * 60 + kst.minute
    except: return -1


def peak1(self):
    """① 입력 시각 ±30분 내 최대 거래대금 봉 탐색."""
    raw = self.pk1_in.text()
    tmin = _parse_t(raw)
    if tmin < 0:
        self.pk1_lbl.setText("❌ 시간 형식 오류"); return
    if not self.current_processed:
        self.pk1_lbl.setText("❌ 데이터 없음"); return
    best_eok, best_t = 0.0, None
    for i, (r, kst, eok) in enumerate(self.current_processed):
        row_min = kst.hour * 60 + kst.minute
        if abs(row_min - tmin) <= 30:
            if eok > best_eok:
                best_eok = eok
                best_t   = kst.strftime("%H:%M:%S")
    if best_t:
        self.pk1_lbl.setText(f"최대: {best_t}  {best_eok:,.2f}억")
    else:
        self.pk1_lbl.setText("해당 구간 데이터 없음")


def peak2(self):
    """② 구간 합산."""
    s_min = _parse_t(self.pk2_s.text())
    e_min = _parse_t(self.pk2_e.text())
    if s_min < 0 or e_min < 0:
        self.pk2_lbl.setText("❌ 시간 형식 오류"); return
    total = 0.0
    for r, kst, eok in self.current_processed:
        row_min = kst.hour * 60 + kst.minute
        if s_min <= row_min <= e_min:
            total += eok
    self.pk2_lbl.setText(f"합산: {total:,.2f}억")


def update_peak3(self, table):
    """③ 테이블 다중 선택 합산."""
    rows = set(idx.row() for idx in table.selectedIndexes())
    total = 0.0
    for ri in rows:
        it = table.item(ri, 5)
        if it:
            try: total += float(it.text().replace(",", ""))
            except: pass
    self.pk3_lbl.setText(f"선택 합산: {total:,.2f}억")
