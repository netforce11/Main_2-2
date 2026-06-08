"""
chart_exec_marker.py — 기능5: 체결 마커 오버레이  (v2 – XSP/SPX 지수환산 + 시간보정)
────────────────────────────────────────────────────────────────────────────────
변경점 (v2):
  · XSP ↔ SPX 지수 자동 환산  (XSP = SPX / 10, 오차 ±0.5 이내 보정)
  · 체결 symbol 이 차트 symbol 과 달라도 가격을 맞춰 마커 표시
  · 시간대 보정: DB ts (ET 또는 KST) → epoch_ms 안전 변환
  · load_exec_markers_from_db() — 날짜 + symbol 필터, 환산 포함
  · 마커 툴팁: 가격 · 수량 · 환산여부 표시
  · 차트 symbol 감지: self.current_sym 또는 self.sym_in

외부 호출:
    from chart_exec_marker import (
        init_exec_markers, add_exec_marker,
        redraw_exec_markers, clear_exec_markers,
        load_exec_markers_from_db, convert_exec_price,
    )

tab_chart.py __init__ 에서:
    from chart_exec_marker import init_exec_markers
    init_exec_markers(self)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime, timezone, timedelta

try:
    import pyqtgraph as pg
    import numpy as np
    PG = True
except ImportError:
    PG = False

# ── 설정 ─────────────────────────────────────────────────────────────────────
COLOR_BUY    = "#00e676"   # 녹색 ▲
COLOR_SELL   = "#ff1744"   # 적색 ▼
COLOR_BUY_C  = "#69f0ae"   # 환산 BUY (연녹색)
COLOR_SELL_C = "#ff6d00"   # 환산 SELL (주황)
MARKER_SIZE  = 14
OFFSET_PCT   = 0.003       # 캔들 고/저가 대비 오프셋 비율

# XSP ↔ SPX 변환 비율 (XSP ≈ SPX / 10)
_XSP_RATIO   = 10.0


# ── 지수 환산 ─────────────────────────────────────────────────────────────────

def _get_chart_symbol(self) -> str:
    """현재 차트의 종목 심볼 반환 (대문자)."""
    sym = (getattr(self, 'current_sym', None)
           or (self.sym_in.text().strip() if hasattr(self, 'sym_in') else '')
           or '')
    return sym.upper()


def convert_exec_price(trade_symbol: str, trade_price: float,
                        chart_symbol: str) -> tuple:
    """
    체결 심볼 가격을 차트 심볼 가격으로 변환.

    반환: (converted_price: float, was_converted: bool)

    변환 규칙:
      XSP → SPX : price × 10
      SPX → XSP : price / 10
      동일 심볼  : 변환 없음
      그 외 조합 : 변환 없음 (원래 가격 반환)
    """
    ts = trade_symbol.upper().strip()
    cs = chart_symbol.upper().strip()

    if ts == cs:
        return trade_price, False

    # XSP 체결 → SPX 차트
    if ts == 'XSP' and cs in ('SPX', 'SPXW'):
        return round(trade_price * _XSP_RATIO, 2), True

    # SPX/SPXW 체결 → XSP 차트
    if ts in ('SPX', 'SPXW') and cs == 'XSP':
        return round(trade_price / _XSP_RATIO, 2), True

    # 알 수 없는 조합 — 원래 가격 그대로
    return trade_price, False


# ── 시간 변환 ─────────────────────────────────────────────────────────────────

def _ts_to_epoch_ms(ts_str: str) -> int:
    """
    DB ts 컬럼(ISO8601 문자열)을 epoch milliseconds 로 변환.

    지원 형식:
      "2026-05-01T09:31:00"          — naive → ET(America/New_York) 가정
      "2026-05-01T09:31:00-04:00"    — timezone-aware
      "2026-05-01 09:31:00"          — 공백 구분자
      "2026-05-01T22:31:00+09:00"    — KST (자동 UTC 변환)
    """
    if not ts_str:
        return 0
    try:
        # Python 3.7+ fromisoformat (공백·T 모두 처리)
        s = ts_str.strip().replace(' ', 'T')

        # timezone-aware
        if '+' in s[10:] or (s.count('-') > 2):
            try:
                dt_aware = datetime.fromisoformat(s)
                return int(dt_aware.timestamp() * 1000)
            except ValueError:
                pass

        # naive → ET 가정
        dt_naive = datetime.fromisoformat(s)
        # ET 오프셋 추정: DST 여부 단순 판정 (3월~11월 둘째 주 일 ~ 11월 첫째 주 일)
        et_offset = _et_utc_offset(dt_naive.date())
        dt_utc = dt_naive - timedelta(hours=et_offset)
        return int(dt_utc.replace(tzinfo=timezone.utc).timestamp() * 1000)
    except Exception:
        return 0


def _et_utc_offset(d) -> int:
    """
    날짜 d 의 ET UTC 오프셋 반환: DST(-4) 또는 표준시(-5).
    간이 판정 — 3월 둘째 주 일요일 ~ 11월 첫째 주 일요일.
    """
    from datetime import date as _date, timedelta as _td
    def _nth_sun(year, month, nth):
        d0 = _date(year, month, 1)
        cnt = 0
        for off in range(31):
            dd = d0 + _td(days=off)
            if dd.month != month:
                break
            if dd.weekday() == 6:
                cnt += 1
                if cnt == nth:
                    return dd
        return None

    dst_start = _nth_sun(d.year, 3, 2)   # 3월 둘째 일요일
    dst_end   = _nth_sun(d.year, 11, 1)  # 11월 첫째 일요일
    if dst_start and dst_end and dst_start <= d < dst_end:
        return -4   # EDT
    return -5       # EST


# ── 초기화 ────────────────────────────────────────────────────────────────────

def init_exec_markers(self):
    """ChartGrid.__init__ 에서 1회 호출."""
    self._exec_markers     = []   # [(ts_ms, action, price, symbol, qty), ...]
    self._exec_marker_item = []

    try:
        from core import bridge
        bridge.exec_filled.connect(
            lambda ts, act, px: add_exec_marker(self, ts, act, px))
    except AttributeError:
        pass


# ── 마커 추가 ─────────────────────────────────────────────────────────────────

def add_exec_marker(self, ts_ms: int, action: str, price: float,
                     symbol: str = '', qty: int = 0):
    """
    체결 발생 시 호출.
    ts_ms  : 체결 시각 (epoch milliseconds, ET 기준)
    action : 'BUY' 또는 'SELL'
    price  : 체결가
    symbol : 체결 종목 (없으면 차트 종목과 동일로 간주)
    qty    : 수량 (툴팁용)
    """
    self._exec_markers.append(
        (int(ts_ms), action.upper(), float(price),
         symbol.upper() if symbol else _get_chart_symbol(self),
         int(qty))
    )
    redraw_exec_markers(self)


# ── 마커 렌더링 ───────────────────────────────────────────────────────────────

def redraw_exec_markers(self):
    """차트 데이터(self.current_processed)와 매칭해 마커를 다시 그림."""
    if not PG:
        return

    clear_exec_markers(self)

    markers = getattr(self, '_exec_markers', [])
    proc    = getattr(self, 'current_processed', [])
    if not markers or not proc:
        return

    chart_sym = _get_chart_symbol(self)
    flipped   = getattr(self, '_chart_flipped', False)

    # current_processed: [(r_dict, et_datetime, eok), ...]
    # r_dict 에는 't' (epoch_ms) 키 있음
    ts_list = [item[0].get('t', 0) for item in proc]

    buy_x,  buy_y,  buy_tips  = [], [], []
    sell_x, sell_y, sell_tips = [], [], []
    buy_x_c, buy_y_c, buy_tips_c   = [], [], []
    sell_x_c, sell_y_c, sell_tips_c = [], [], []

    for ts_ms, action, price, sym, qty in markers:
        if not ts_list:
            break

        # 가장 가까운 봉 인덱스
        idx = int(np.argmin([abs(t - ts_ms) for t in ts_list]))
        bar = proc[idx][0]

        lo = bar.get('l', bar.get('low',  price))
        hi = bar.get('h', bar.get('high', price))
        offset = (hi - lo) * 0.15 if (hi - lo) > 0 else price * OFFSET_PCT

        # 지수 환산
        conv_price, was_conv = convert_exec_price(sym, price, chart_sym)

        # 툴팁 문자열
        conv_note = f" [환산:{sym}→{chart_sym}]" if was_conv else ""
        tip = (f"{action} {conv_price:,.2f}"
               + (f" (원가 {price:,.2f})" if was_conv else "")
               + (f"  ×{qty}" if qty else "")
               + conv_note)

        x = idx
        if action == 'BUY':
            y = hi + offset if flipped else lo - offset
            if was_conv:
                buy_x_c.append(x); buy_y_c.append(y); buy_tips_c.append(tip)
            else:
                buy_x.append(x);   buy_y.append(y);   buy_tips.append(tip)
        else:
            y = lo - offset if flipped else hi + offset
            if was_conv:
                sell_x_c.append(x); sell_y_c.append(y); sell_tips_c.append(tip)
            else:
                sell_x.append(x);   sell_y.append(y);   sell_tips.append(tip)

    items = []

    def _add_scatter(xs, ys, symbol_shape, color, tips):
        if not xs:
            return
        item = pg.ScatterPlotItem(
            x=xs, y=ys,
            symbol=symbol_shape,
            size=MARKER_SIZE,
            brush=pg.mkBrush(color),
            pen=pg.mkPen(None),
            data=tips,          # 툴팁용 데이터 바인딩
        )
        item.setToolTip('\n'.join(tips))
        self.p1.addItem(item)
        items.append(item)

    _add_scatter(buy_x,   buy_y,   't1', COLOR_BUY,    buy_tips)    # BUY ▲
    _add_scatter(sell_x,  sell_y,  't',  COLOR_SELL,   sell_tips)   # SELL ▼
    _add_scatter(buy_x_c, buy_y_c, 't1', COLOR_BUY_C,  buy_tips_c)  # 환산 BUY ▲
    _add_scatter(sell_x_c,sell_y_c,'t',  COLOR_SELL_C, sell_tips_c) # 환산 SELL ▼

    self._exec_marker_item = items


# ── 마커 제거 ─────────────────────────────────────────────────────────────────

def clear_exec_markers(self):
    """마커 아이템만 제거 (데이터는 유지)."""
    for item in (getattr(self, '_exec_marker_item', []) or []):
        try:
            self.p1.removeItem(item)
        except Exception:
            pass
    self._exec_marker_item = []


# ── DB 로드 ──────────────────────────────────────────────────────────────────

def load_exec_markers_from_db(self, date_str: str = None,
                               filter_symbol: str = None):
    """
    DB pnl_history 에서 체결 이력을 로드해 마커로 표시.

    Parameters
    ----------
    date_str      : 'YYYY-MM-DD' 형식. None 이면 오늘.
    filter_symbol : 특정 종목만 로드. None 이면 XSP+SPX 모두 로드.

    동작:
      1. DB fetch_pnl() 호출 (date + symbol 필터)
      2. ts 컬럼 → epoch_ms 변환 (ET naive 가정, KST +09:00 자동 처리)
      3. symbol ↔ 차트 symbol 가격 환산
      4. redraw_exec_markers() 호출
    """
    try:
        from db_manager import DBManager
        db = DBManager.get()

        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        # symbol 필터: None이면 XSP·SPX·SPXW 모두, 아니면 지정 심볼
        target_syms = (
            [filter_symbol.upper()]
            if filter_symbol
            else ['XSP', 'SPX', 'SPXW']
        )

        new_markers = []
        for sym in target_syms:
            df = db.fetch_pnl(symbol=sym, date=date_str)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                try:
                    ts_ms = _ts_to_epoch_ms(str(row.get('ts', '')))
                    if ts_ms == 0:
                        continue
                    action = str(row.get('action', '')).upper()
                    if action not in ('BUY', 'SELL'):
                        continue
                    price  = float(row.get('price', 0.0))
                    qty    = int(row.get('qty', 0))
                    new_markers.append((ts_ms, action, price, sym, qty))
                except Exception:
                    continue

        if new_markers:
            self._exec_markers = new_markers
            redraw_exec_markers(self)
            _log(f"[ExecMarker] DB 로드 완료: {len(new_markers)}건 ({date_str})")
        else:
            _log(f"[ExecMarker] DB 로드: {date_str} 체결 없음")

    except Exception as e:
        _log(f"[ExecMarker] DB 로드 실패: {e}")


def _log(msg: str):
    """콘솔 출력 (향후 StatusBar 연동 가능)."""
    print(msg)
