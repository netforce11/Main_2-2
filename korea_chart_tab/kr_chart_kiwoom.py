"""
kr_chart_kiwoom.py — 키움 opt10080 분봉 과거 데이터 수집
────────────────────────────────────────────────────────
키움 opt10080 실제 동작 (실측 확인):
  - 기준일자 파라미터 무시 → 항상 서버 최신 기준
  - _remained_data 로 연속 판단 불가
  - 연속 요청: next=2 로 block_request 재호출
  - 연속 종료 조건: 반환 봉 수 < 900 이거나 반환 df가 비어있음

수집 전략:
  page 0: next=0 → 최신 900봉
  page 1: next=2 → 이전 900봉
  page 2: next=2 → 더 이전 900봉
  ...
  봉 수 < 900 또는 빈 데이터 → 종료
  전체 레코드를 날짜별 분류 저장
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt5.QtCore import QTimer

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

KR_DATA_ROOT = Path(r"C:\data\Korea\stock_1M")
MAX_BARS_PER_PAGE = 900   # opt10080 1회 최대 봉 수

# ── 마커 유틸 ─────────────────────────────────────────────────

def _marker_path(code, tgt):
    return KR_DATA_ROOT / code / ".downloaded" / tgt.strftime("%Y%m%d")

def _set_marker(code, tgt):
    mp = _marker_path(code, tgt)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.touch()

def _has_marker(code, tgt):
    return _marker_path(code, tgt).exists()

def _clear_marker(code, tgt):
    mp = _marker_path(code, tgt)
    if mp.exists():
        mp.unlink()

def _csv_path(code, tgt):
    return KR_DATA_ROOT / code / f"{tgt.strftime('%Y%m')}.csv"


# ── DataFrame 파싱 ────────────────────────────────────────────

_COL_CACHE = {}

def _parse_df(code, df):
    global _COL_CACHE
    if code not in _COL_CACHE:
        ct = next((c for c in df.columns if "체결시간" in c), None)
        co = next((c for c in df.columns if "시가"    in c), None)
        ch = next((c for c in df.columns if "고가"    in c), None)
        cl = next((c for c in df.columns if "저가"    in c), None)
        cc = next((c for c in df.columns if "현재가"  in c or "종가" in c), None)
        cv = next((c for c in df.columns if "거래량"  in c), None)
        print(f"[KrChart] 컬럼: time={ct} close={cc} vol={cv}")
        _COL_CACHE[code] = (ct, co, ch, cl, cc, cv)

    ct, co, ch, cl, cc, cv = _COL_CACHE[code]
    if not ct or not cc:
        return []

    records = []
    for _, row in df.iterrows():
        try:
            dt_str = str(row[ct]).strip()
            dt     = datetime.strptime(dt_str, "%Y%m%d%H%M%S")
            ms     = int(dt.timestamp() * 1000)
            o = abs(float(str(row[co]).strip())) if co else 0.0
            h = abs(float(str(row[ch]).strip())) if ch else 0.0
            l = abs(float(str(row[cl]).strip())) if cl else 0.0
            c = abs(float(str(row[cc]).strip()))
            v = abs(float(str(row[cv]).strip())) if cv else 0.0
            records.append({"t": ms, "o": o, "h": h, "l": l, "c": c, "v": v})
        except Exception as ex:
            print(f"[KrChart] 파싱 오류: {ex}")
    return records


def _date_range_str(records):
    if not PANDAS or not records:
        return "없음"
    try:
        s = pd.to_datetime(
            pd.DataFrame(records)["t"], unit="ms"
        ).dt.tz_localize("UTC").dt.tz_convert("Asia/Seoul").dt.date
        return f"{s.min()}~{s.max()}"
    except Exception:
        return "?"

def _oldest_date(records):
    if not PANDAS or not records:
        return None
    try:
        s = pd.to_datetime(
            pd.DataFrame(records)["t"], unit="ms"
        ).dt.tz_localize("UTC").dt.tz_convert("Asia/Seoul").dt.date
        return s.min()
    except Exception:
        return None


# ── opt10080 단일 TR 요청 ─────────────────────────────────────

def download_opt10080(self, code, is_next=False):
    """
    opt10080 1회 동기 조회.
    연속 종료 판단: 반환된 봉 수가 MAX_BARS_PER_PAGE 미만이면 마지막 페이지.
    반환: (records: list[dict], has_next: bool)
    """
    if not self.kiwoom:
        return [], False

    kw        = self.kiwoom
    today_str = date.today().strftime("%Y%m%d")

    try:
        data = kw.block_request(
            "opt10080",
            종목코드=code,
            기준일자=today_str,
            틱범위="1",
            수정주가구분="1",
            output="주식분봉차트조회",
            next=2 if is_next else 0,
        )
    except Exception as ex:
        print(f"[KrChart] block_request 오류: {ex}")
        return [], False

    if data is None:
        return [], False

    # DataFrame 또는 dict 처리
    if PANDAS and hasattr(data, 'empty'):
        if data.empty:
            return [], False
        df = data
    elif isinstance(data, dict) and PANDAS:
        df = pd.DataFrame(data)
        if df.empty:
            return [], False
    else:
        return [], False

    records = _parse_df(code, df)

    # 연속 여부: 반환 봉 수가 최대치면 다음 페이지 있음
    has_next = (len(records) >= MAX_BARS_PER_PAGE)

    print(f"[KrChart] {code} next={is_next} → {len(records)}봉  "
          f"범위={_date_range_str(records)}  연속={has_next}")
    return records, has_next


# ── 날짜별 분류 저장 ──────────────────────────────────────────

def _save_by_date(code, records):
    """전체 records를 날짜별 분류 후 월별 CSV에 저장. 마커 생성."""
    if not PANDAS or not records:
        return 0
    df = pd.DataFrame(records)
    df["_d"] = (pd.to_datetime(df["t"], unit="ms")
                .dt.tz_localize("UTC")
                .dt.tz_convert("Asia/Seoul").dt.date)
    saved = 0
    for tgt, grp in df.groupby("_d"):
        grp = grp.drop(columns=["_d"])
        fp  = _csv_path(code, tgt)
        fp.parent.mkdir(parents=True, exist_ok=True)
        if fp.exists():
            try:
                merged = (pd.concat([pd.read_csv(str(fp)), grp])
                          .drop_duplicates(subset=["t"])
                          .sort_values("t").reset_index(drop=True))
                merged.to_csv(str(fp), index=False)
            except Exception as ex:
                print(f"[KrChart] CSV 병합 실패 {tgt}: {ex}")
                grp.to_csv(str(fp), index=False)
        else:
            grp.sort_values("t").reset_index(drop=True).to_csv(str(fp), index=False)
        _set_marker(code, tgt)
        saved += 1
    print(f"[KrChart] {code} 날짜별 저장: {saved}일")
    return saved


# ── 단일 날짜 조회 ────────────────────────────────────────────

def fetch_history(self, code, tgt):
    """캘린더 날짜 분봉 조회. 캐시 있으면 바로 표시."""
    if not self.kiwoom:
        self.status_lbl.setText("⚠ 키움 미연결 — 연결 버튼을 눌러주세요.")
        return

    # 캐시 확인
    if _has_marker(code, tgt):
        df = load_day_df(self, code, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict("records")
            self.selected_date = tgt
            self.status_lbl.setText(f"📅 {tgt} 캐시 ({len(df)}봉)")
            self._update_display()
            try: self.p1.autoRange()
            except Exception: pass
            self._push_trend_df()
            return

    # API 조회
    self.status_lbl.setText(f"🔄 {code} {tgt} 조회 중…")
    records, _ = download_opt10080(self, code, is_next=False)
    if records:
        _save_by_date(code, records)
        df = load_day_df(self, code, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict("records")
            self.selected_date = tgt
            self.status_lbl.setText(f"📅 {tgt} ({len(df)}봉)")
            self._update_display()
            try: self.p1.autoRange()
            except Exception: pass
            self._push_trend_df()
            return
    self.status_lbl.setText(
        f"⚠ {tgt} — 과거 데이터는 📥 최대조회로 먼저 수집하세요.")


# ── 최대 조회 ─────────────────────────────────────────────────

def fetch_max(self):
    """연속 요청으로 최대 분봉 수집 후 날짜별 저장."""
    if not self.kiwoom:
        self.status_lbl.setText("⚠ 키움 미연결 — 연결 버튼을 눌러주세요.")
        return
    code = self.sym_in.text().strip().zfill(6)
    tgt  = self.calendar.selectedDate().toPyDate()
    self._fetch_max_mode = True
    self._fetch_pages    = 0
    self._fetch_all_recs = []
    self._fetch_max_code = code
    self._fetch_max_tgt  = tgt
    self.btn_fetch_max.setEnabled(False)
    self.status_lbl.setText(f"📥 {code} 최대 조회 시작…")
    _fetch_max_step(self)

def _fetch_max_step(self):
    code    = self._fetch_max_code
    is_next = (self._fetch_pages > 0)
    records, has_next = download_opt10080(self, code, is_next=is_next)
    if records:
        self._fetch_all_recs.extend(records)
        self._fetch_pages += 1
        self.status_lbl.setText(
            f"📥 {code} {self._fetch_pages}p "
            f"{len(self._fetch_all_recs)}봉 "
            f"{_date_range_str(self._fetch_all_recs)}")
    if has_next and records:
        QTimer.singleShot(600, lambda: _fetch_max_step(self))
    else:
        _fetch_max_done(self)

def _fetch_max_done(self):
    code  = self._fetch_max_code
    tgt   = self._fetch_max_tgt
    recs  = self._fetch_all_recs
    saved = _save_by_date(code, recs) if recs else 0
    self._fetch_max_mode = False
    self.btn_fetch_max.setEnabled(True)
    self.status_lbl.setText(
        f"✅ {code} 최대조회 완료 {len(recs)}봉 {saved}일 저장")
    if recs:
        df = load_day_df(self, code, tgt)
        if df is not None and not df.empty:
            self.df = df; self.df_raw = df.to_dict("records")
            self.selected_date = tgt
            self._update_display(); self._push_trend_df()


# ── 20일 조회 ─────────────────────────────────────────────────

def fetch_20days(self):
    """연속 요청으로 20거래일치 수집 후 날짜별 저장."""
    if not self.kiwoom:
        self.status_lbl.setText("⚠ 키움 미연결 — 연결 버튼을 눌러주세요.")
        return
    code  = self.sym_in.text().strip().zfill(6)
    today = date.today()
    target_dates = []
    d = today
    while len(target_dates) < 20:
        if d.weekday() < 5:
            target_dates.append(d)
        d -= timedelta(days=1)
    oldest = min(target_dates)

    self._20d_code     = code
    self._20d_oldest   = oldest
    self._20d_all_recs = []
    self._20d_pages    = 0
    self.btn_fetch_20d.setEnabled(False)
    self.status_lbl.setText(
        f"📅 {code} 20일 조회  목표: {oldest}~오늘")
    _fetch_20days_step(self)

def _fetch_20days_step(self):
    code    = self._20d_code
    oldest  = self._20d_oldest
    is_next = (self._20d_pages > 0)

    records, has_next = download_opt10080(self, code, is_next=is_next)
    if records:
        self._20d_all_recs.extend(records)
        self._20d_pages += 1

    oldest_recv = _oldest_date(self._20d_all_recs)
    self.status_lbl.setText(
        f"📥 {code} {self._20d_pages}p "
        f"{len(self._20d_all_recs)}봉 "
        f"{_date_range_str(self._20d_all_recs)}")

    reached = (oldest_recv is not None and oldest_recv <= oldest)
    if reached or not has_next or not records:
        saved = _save_by_date(code, self._20d_all_recs)
        self.btn_fetch_20d.setEnabled(True)
        self.status_lbl.setText(
            f"✅ {code} 20일 완료 "
            f"{len(self._20d_all_recs)}봉 {saved}일 저장")
    else:
        QTimer.singleShot(700, lambda: _fetch_20days_step(self))


# ── 강제 재다운로드 ──────────────────────────────────────────

def force_redownload(self, code, tgt):
    if not PANDAS: return
    _clear_marker(code, tgt)
    fp = _csv_path(code, tgt)
    if fp.exists():
        try:
            full = pd.read_csv(str(fp))
            full["_d"] = (pd.to_datetime(full["t"], unit="ms")
                          .dt.tz_localize("UTC")
                          .dt.tz_convert("Asia/Seoul").dt.date)
            full[full["_d"] != tgt].drop(columns=["_d"]).to_csv(str(fp), index=False)
        except Exception as ex:
            print(f"[KrChart] CSV 정리 실패: {ex}")
    fetch_history(self, code, tgt)


# ── CSV 로드 ─────────────────────────────────────────────────

def load_day_df(self, code, tgt):
    if not PANDAS: return None
    fp = _csv_path(code, tgt)
    if not fp.exists(): return None
    try:
        full = pd.read_csv(str(fp))
        full["_d"] = (pd.to_datetime(full["t"], unit="ms")
                      .dt.tz_localize("UTC")
                      .dt.tz_convert("Asia/Seoul").dt.date)
        res = full[full["_d"] == tgt].drop(columns=["_d"]).copy()
        return res if not res.empty else None
    except Exception as ex:
        print(f"[KrChart] load_day_df 실패: {ex}")
        return None