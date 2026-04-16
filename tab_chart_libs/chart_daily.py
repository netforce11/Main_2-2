"""
chart_daily.py — 일봉 추가 보기  v6.4
────────────────────────────────────────────────────────
분봉(chart_tab_ibkr.py)과 동일한 마커 캐시 구조 사용.

저장 경로:
  C:\\data\\US_StockData\\{SYM}\\daily_{SYM}.csv
  C:\\data\\US_StockData\\{SYM}\\.downloaded_daily\\YYYYMMDD

동작:
  · 날짜별 마커 파일로 다운로드 여부 체크
  · 마커 있는 날짜 → CSV에서 읽기 (API 호출 없음)
  · 마커 없는 날짜 → Polygon /1/day API → CSV에 누적 저장 → 마커 생성
  · 캘린더 날짜 기준 앞뒤 ~50 영업일(총 ~100봉) 범위 자동 보충

위임 함수 (tab_chart.py 바인딩):
  toggle_daily_view(self)
  load_daily_data(self)
  render_daily(self, df)
  center_on_calendar(self, plot, bars)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import requests
from datetime import datetime, timedelta, date as _date

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui  import QColor, QPainter, QPicture
from PyQt5.QtWidgets import QSizePolicy

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

try:
    from common import DATA_ROOT
except Exception:
    from pathlib import Path
    DATA_ROOT = Path(r"C:\data\US_StockData")


# ══════════════════════════════════════════════════════════════
# 마커 헬퍼 (분봉과 동일한 패턴, 일봉 전용 폴더 사용)
# ══════════════════════════════════════════════════════════════

def _daily_csv_path(symbol_up):
    """일봉 CSV 경로:  DATA_ROOT/{SYM}/daily_{SYM}.csv"""
    from pathlib import Path
    return DATA_ROOT / symbol_up / f"daily_{symbol_up}.csv"

def _daily_marker_path(symbol_up, d):
    """마커 파일 경로:  DATA_ROOT/{SYM}/.downloaded_daily/YYYYMMDD"""
    from pathlib import Path
    return DATA_ROOT / symbol_up / ".downloaded_daily" / d.strftime("%Y%m%d")

def _has_daily_marker(symbol_up, d):
    return _daily_marker_path(symbol_up, d).exists()

def _set_daily_marker(symbol_up, d):
    mp = _daily_marker_path(symbol_up, d)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.touch()


# ══════════════════════════════════════════════════════════════
# 캔들스틱 아이템 (일봉 전용)
# ══════════════════════════════════════════════════════════════

class _DailyCandle(pg.GraphicsObject):
    def __init__(self, data, body_w=0.55):
        super().__init__()
        self._data = data; self._body_w = body_w
        self._pic  = None; self._gen()

    def _gen(self):
        self._pic = QPicture()
        p = QPainter(self._pic)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self._body_w / 2
        for idx, o, h, l, c in self._data:
            col = QColor("#26a69a") if c >= o else QColor("#ef5350")
            p.setPen(pg.mkPen(col, width=1))
            p.setBrush(pg.mkBrush(col))
            p.drawLine(pg.QtCore.QPointF(idx, l), pg.QtCore.QPointF(idx, h))
            top = max(o, c); bot = min(o, c)
            p.drawRect(pg.QtCore.QRectF(idx - w, bot, 2 * w, max(top - bot, 0.0001)))
        p.end()

    def paint(self, p, *args): p.drawPicture(0, 0, self._pic)
    def boundingRect(self):    return pg.QtCore.QRectF(self._pic.boundingRect())


# ══════════════════════════════════════════════════════════════
# 다운로드 워커 (QThread) — 빠진 날짜만 API 호출
# ══════════════════════════════════════════════════════════════

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
            # 범위 내 모든 날짜 생성 (주말 제외하지 않음 — 마커로 판단)
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

        # 연속 범위로 묶기 (최대 30일 단위)
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
                    # 수신된 날짜에 마커 생성
                    for row in results:
                        bar_date = datetime.fromtimestamp(
                            row["t"] / 1000).date()
                        _set_daily_marker(sym, bar_date)
                # 결과가 없어도 (휴장일 등) 해당 범위 마커 생성
                d = t_from
                while d <= t_to:
                    if not _has_daily_marker(sym, d):
                        _set_daily_marker(sym, d)   # 휴장일도 마킹
                    d += timedelta(days=1)
            except Exception as e:
                print(f"[DailyFill] API 오류 {t_from}~{t_to}: {e}")

        if not all_new:
            return

        new_df = pd.DataFrame(all_new)[["t","o","h","l","c","v"]]

        # 기존 CSV와 합치기
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

def toggle_daily_view(self):
    """btn_daily 클릭 → 분차트 테이블 ↔ 일봉 차트 전환"""
    on = self.btn_daily.isChecked()
    if on:
        self.btn_daily.setText("📈 일봉 보기 ✔")
        self._tbl_splitter.hide()
        self.daily_container.show()
        self._load_daily_data()
    else:
        self.btn_daily.setText("📈 일봉 추가 보기")
        self.daily_container.hide()
        self._tbl_splitter.show()
        # 진행 중인 워커 중지
        if getattr(self, "_daily_worker", None):
            self._daily_worker.quit()
            self._daily_worker = None


def load_daily_data(self):
    """심볼 + 캘린더 날짜 기준으로 일봉 데이터 로드 (캐시 우선)"""
    sym = self.sym_in.text().strip().upper()
    if not sym:
        self.status_lbl.setText("일봉 조회 실패: 종목을 먼저 입력하세요.")
        return

    cal_date = self.calendar.selectedDate().toString("yyyy-MM-dd")
    self.status_lbl.setText(f"📈 일봉 확인 중…  {sym}  ({cal_date} 기준)")

    # 이전 워커 정리
    if getattr(self, "_daily_worker", None):
        self._daily_worker.quit()

    self._daily_worker = _DailyFillWorker(sym, cal_date, self.api_key)
    self._daily_worker.status.connect(
        lambda msg: self.status_lbl.setText(msg))
    self._daily_worker.done.connect(
        lambda df: render_daily(self, df))
    self._daily_worker.error.connect(
        lambda msg: self.status_lbl.setText(f"일봉 오류: {msg}"))
    self._daily_worker.start()


def render_daily(self, df):
    """
    df: pd.DataFrame  columns=[t, o, h, l, c, v]
    daily_container 안을 비우고 캔들 + 볼륨 플롯 렌더링.
    캘린더 날짜가 x축 중앙에 오도록 범위 설정.
    """
    if df is None or (PANDAS and df.empty):
        self.status_lbl.setText("일봉 데이터 없음.")
        return

    layout = self.daily_container.layout()
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w: w.deleteLater()

    # bars: [(ts_ms, o, h, l, c, v), ...]
    bars = list(df[["t","o","h","l","c","v"]].itertuples(index=False, name=None))

    # ── 캔들 플롯 ──────────────────────────────────────
    candle_plot = pg.PlotWidget(background="#1a1a2e")
    candle_plot.setMenuEnabled(False)
    candle_plot.showGrid(x=False, y=True, alpha=0.15)
    candle_plot.getAxis("left").setTextPen(pg.mkPen("#aaaaaa"))
    candle_plot.getAxis("bottom").hide()
    candle_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ── 볼륨 플롯 ──────────────────────────────────────
    vol_plot = pg.PlotWidget(background="#1a1a2e")
    vol_plot.setMenuEnabled(False)
    vol_plot.setFixedHeight(80)
    vol_plot.getAxis("left").setTextPen(pg.mkPen("#888888"))

    # x축 날짜 눈금
    dates = [datetime.fromtimestamp(b[0] / 1000).strftime("%y/%m/%d")
             for b in bars]
    step  = max(1, len(bars) // 10)
    ticks = [(i, dates[i]) for i in range(0, len(bars), step)]
    vol_plot.getAxis("bottom").setTicks([ticks])
    vol_plot.getAxis("bottom").setTextPen(pg.mkPen("#777777"))

    candle_plot.setXLink(vol_plot)

    # 캔들
    candle_data = [(i, b[1], b[2], b[3], b[4]) for i, b in enumerate(bars)]
    candle_plot.addItem(_DailyCandle(candle_data, body_w=0.55))

    # 볼륨
    for i, b in enumerate(bars):
        col = "#26a69a" if b[4] >= b[1] else "#ef5350"
        vol_plot.addItem(pg.BarGraphItem(
            x=[i], height=[b[5]], width=0.6,
            brush=pg.mkBrush(col), pen=pg.mkPen(None)))

    # 캘린더 날짜 중앙 정렬 + y축 범위 + 수직선 (center_on_calendar 내부에서 처리)
    center_on_calendar(self, candle_plot, bars)

    # autoRange 비활성화 (볼륨 등 외부 데이터에 끌려가지 않도록)
    candle_plot.getViewBox().disableAutoRange()
    vol_plot.getViewBox().disableAutoRange()

    layout.addWidget(candle_plot, stretch=4)
    layout.addWidget(vol_plot,    stretch=1)

    sym      = self.sym_in.text().strip().upper()
    cal_date = self.calendar.selectedDate().toString("yyyy-MM-dd")
    self.status_lbl.setText(
        f"📈 일봉  {sym}  ·  {cal_date} 중심  ·  {len(bars)}봉")


def center_on_calendar(self, plot, bars):
    """캘린더 선택 날짜가 x축 중앙에 오도록 뷰 범위 설정.
    표시 구간 내 고가/저가 기준으로 y축 범위도 명시적으로 설정한다.
    캘린더 날짜 수직선도 여기서 재드로우 (캘린더 변경 시 항상 최신 상태 유지)."""
    cal_date = self.calendar.selectedDate().toPyDate()

    best_idx, best_delta = None, timedelta(days=9999)
    for i, b in enumerate(bars):
        delta = abs(datetime.fromtimestamp(b[0] / 1000).date() - cal_date)
        if delta < best_delta:
            best_delta = delta; best_idx = i

    if best_idx is None:
        return

    half  = 50
    x_min = max(0, best_idx - half)
    x_max = min(len(bars) - 1, best_idx + half)
    plot.setXRange(x_min, x_max, padding=0.02)

    # 표시 구간 내 봉들의 고가/저가로 y축 범위 계산
    # bars 구조: (ts_ms, o, h, l, c, v)  → h=index2, l=index3
    visible = bars[x_min: x_max + 1]
    if visible:
        y_lo = min(b[3] for b in visible)
        y_hi = max(b[2] for b in visible)
        margin = (y_hi - y_lo) * 0.06   # 위아래 6% 여백
        plot.setYRange(y_lo - margin, y_hi + margin, padding=0)

    # 기존 수직선 제거 후 재드로우 (캘린더 날짜 변경 시 항상 최신 위치 반영)
    if hasattr(plot, '_cal_vline') and plot._cal_vline is not None:
        try:
            plot.removeItem(plot._cal_vline)
        except Exception:
            pass
    plot._cal_vline = None
    for i, b in enumerate(bars):
        if datetime.fromtimestamp(b[0] / 1000).date() == cal_date:
            vline = pg.InfiniteLine(
                pos=i, angle=90,
                pen=pg.mkPen("#f9a825", width=1, style=Qt.DashLine),
                label=str(cal_date),
                labelOpts={"color": "#f9a825", "position": 0.92})
            plot.addItem(vline)
            plot._cal_vline = vline
            break


# ── 내부 헬퍼 ──────────────────────────────────────────────

def _draw_cal_vline(plot, bars, calendar):
    cal_date = calendar.selectedDate().toPyDate()
    for i, b in enumerate(bars):
        if datetime.fromtimestamp(b[0] / 1000).date() == cal_date:
            plot.addItem(pg.InfiniteLine(
                pos=i, angle=90,
                pen=pg.mkPen("#f9a825", width=1, style=Qt.DashLine),
                label=str(cal_date),
                labelOpts={"color": "#f9a825", "position": 0.92}))
            break