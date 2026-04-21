"""
kr_chart_daily.py — 일봉 추가 보기
────────────────────────────────────────────────────────
toggle_daily_view() — 버튼 토글 → 분봉 테이블 숨기기/복원
load_daily_data()   — opt10083 (일봉) 데이터 수신
render_daily()      — 일봉 캔들 + 거래량 렌더링
center_on_calendar()— 캘린더 날짜 중앙 정렬
"""
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

from datetime import datetime, timedelta
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt


def toggle_daily_view(self):
    active = self.btn_daily.isChecked()
    self._daily_view_active = active
    if active:
        self._tbl_splitter.hide()
        self.daily_container.show()
        load_daily_data(self)
    else:
        self.daily_container.hide()
        self._tbl_splitter.show()


def load_daily_data(self):
    """opt10083 — 주식일봉차트조회 (±50봉 기준)."""
    if not self.kiwoom:
        return
    code = self.sym_in.text().strip().zfill(6)
    qd   = self.calendar.selectedDate()
    date_str = f"{qd.year():04d}{qd.month():02d}{qd.day():02d}"

    kw = self.kiwoom
    kw.SetInputValue("종목코드", code)
    kw.SetInputValue("기준일자", date_str)
    kw.SetInputValue("수정주가구분", "1")
    ret = kw.CommRqData("주식일봉차트조회", "opt10083", 0, "0102")
    if ret != 0:
        print(f"[KrDaily] opt10083 요청 실패: ret={ret}")
        return

    count = kw.GetRepeatCnt("opt10083", "주식일봉차트조회")
    records = []
    for i in range(min(count, 100)):   # ±50봉 = 최대 100봉
        def g(f, _i=i): return kw.GetCommData("opt10083", "주식일봉차트조회", _i, f).strip()
        dt_str = g("일자")
        try:
            dt  = datetime.strptime(dt_str, "%Y%m%d")
            o   = abs(float(g("시가")))
            h   = abs(float(g("고가")))
            l   = abs(float(g("저가")))
            c   = abs(float(g("현재가")))
            v   = abs(float(g("거래량")))
            records.append({"t": int(dt.timestamp() * 1000),
                            "o": o, "h": h, "l": l, "c": c, "v": v})
        except Exception:
            continue

    if records:
        render_daily(self, records, date_str)


def render_daily(self, records: list, center_date_str: str = ""):
    """일봉 캔들 + 거래량을 daily_container 에 렌더링."""
    if not PG: return

    # 기존 위젯 제거
    layout = self.daily_container.layout()
    while layout and layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    gfx = pg.GraphicsLayoutWidget()
    p1  = gfx.addPlot(row=0, col=0)
    p2  = gfx.addPlot(row=1, col=0)
    p2.setFixedHeight(80); p2.setXLink(p1)

    from kr_chart_workers import CandlestickItem
    from kr_chart_theme   import _THEME

    C = _THEME[self.dark_mode]
    gfx.setBackground(C['chart_bg'])

    records_sorted = sorted(records, key=lambda r: r['t'])
    p_data = []; v_h = []; v_b = []; x_t = []
    center_x = None

    for i, r in enumerate(records_sorted):
        o = r['o']; c_ = r['c']; lo = r['l']; hi = r['h']; v = r['v']
        p_data.append((i, o, c_, lo, hi))
        v_h.append(v)
        v_b.append(C['candle_up'] if c_ >= o else C['candle_dn'])
        dt = datetime.utcfromtimestamp(r['t'] / 1000)
        label = dt.strftime("%m/%d")
        if i % 5 == 0: x_t.append((i, label))
        if center_date_str and dt.strftime("%Y%m%d") == center_date_str:
            center_x = i

    p1.addItem(CandlestickItem(p_data, C['candle_up'], C['candle_dn']))
    p2.addItem(pg.BarGraphItem(
        x=range(len(v_h)), height=v_h, width=0.6, brushes=v_b))
    for pl in (p1, p2):
        pl.getAxis('bottom').setTicks([x_t])

    # 중앙 정렬: 캘린더 날짜 봉을 뷰 중앙에 배치
    if center_x is not None:
        half = 25
        p1.setXRange(center_x - half, center_x + half, padding=0)

    self.daily_container.layout().addWidget(gfx)


def center_on_calendar(self):
    """캘린더 날짜 기준으로 일봉 뷰 중앙 재정렬 (외부 호출용)."""
    if not self._daily_view_active: return
    load_daily_data(self)