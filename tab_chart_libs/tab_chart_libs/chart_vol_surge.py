"""
chart_vol_surge.py — 기능3: 거래량 급증 캔들 하이라이트
────────────────────────────────────────────────────────
· 직전 N봉 평균 거래량의 surge_mult 배 초과 봉을 주황 테두리로 강조
· p2(거래량 바)도 주황색으로 변경
· update_display() 호출 시 자동 갱신 → 별도 타이머 불필요

외부 호출:
    from chart_vol_surge import draw_vol_surge, clear_vol_surge
    draw_vol_surge(self, candle_data, vol_data)
    clear_vol_surge(self)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

try:
    import pyqtgraph as pg
    from PyQt5.QtGui import QPicture, QPainter, QColor
    PG = True
except ImportError:
    PG = False

import numpy as np

# ── 설정값 ────────────────────────────────────────────────────
LOOKBACK   = 20       # 평균 계산 기준 봉 수
SURGE_MULT = 2.0      # 평균 대비 N배 이상이면 급증
COLOR_SURGE = "#FF8C00"   # 주황 테두리 / 바 색상
COLOR_NORM_UP = "#3c78ff"
COLOR_NORM_DN = "#ff3c3c"
COLOR_VOL_NORM = "#3a3a6a"


if PG:
    class _SurgeOverlay(pg.GraphicsObject):
        """급증 캔들에 주황 테두리를 그리는 오버레이."""

        def __init__(self, surge_rows):
            pg.GraphicsObject.__init__(self)
            self._rows = surge_rows
            self._gen()

        def _gen(self):
            self.picture = QPicture()
            p = QPainter(self.picture)
            pen = pg.mkPen(QColor(COLOR_SURGE), width=2)
            p.setPen(pen)
            p.setBrush(pg.mkBrush(None))
            for t, o, c, lo, hi in self._rows:
                lo_r = min(o, c)
                hi_r = max(o, c)
                ht   = max(hi_r - lo_r, 0.01)
                p.drawRect(
                    pg.QtCore.QRectF(t - 0.38, lo_r - ht * 0.05,
                                     0.76, ht * 1.10))
            p.end()

        def paint(self, p, *a):
            p.drawPicture(0, 0, self.picture)

        def boundingRect(self):
            return pg.QtCore.QRectF(self.picture.boundingRect())


def _calc_surge_mask(volumes, lookback=LOOKBACK, mult=SURGE_MULT):
    """급증 봉 인덱스 마스크 반환."""
    v = np.array(volumes, dtype=float)
    mask = np.zeros(len(v), dtype=bool)
    for i in range(lookback, len(v)):
        avg = v[max(0, i - lookback):i].mean()
        if avg > 0 and v[i] >= avg * mult:
            mask[i] = True
    return mask


def draw_vol_surge(self, candle_data, vol_data):
    """
    candle_data: [(x_idx, o, c, lo, hi), ...]  ← update_display p_data 와 동일
    vol_data:    [(x_idx, volume), ...]          ← enumerate(v_h) 로 전달
    """
    if not PG:
        return

    clear_vol_surge(self)

    if not candle_data or len(candle_data) < LOOKBACK + 1:
        # 데이터 부족 시 기본 거래량 바만 그리고 종료
        _draw_plain_vol(self, vol_data)
        return

    # vol_data 에서 실제 volume 추출 (인덱스 순서 보장)
    real_vols = [v for _, v in vol_data]

    mask = _calc_surge_mask(real_vols)
    surge_rows = [candle_data[i] for i in range(len(candle_data))
                  if i < len(mask) and mask[i]]

    if surge_rows:
        overlay = _SurgeOverlay(surge_rows)
        self.p1.addItem(overlay)
        self._surge_overlay = overlay

    # ── p2 거래량 바 색상 갱신 ────────────────────────────
    _redraw_vol_bars(self, vol_data, mask)


def _redraw_vol_bars(self, vol_data, mask):
    """
    p2 거래량 바 재그림.
    [수정] 봉 개수만큼 addItem → brushes 리스트 단일 BarGraphItem 으로 최적화
    """
    if not vol_data:
        return
    for item in getattr(self, '_vol_bar_items', []):
        try: self.p2.removeItem(item)
        except Exception: pass

    xs      = [x for x, _ in vol_data]
    heights = [v for _, v in vol_data]
    brushes = [COLOR_SURGE if (i < len(mask) and mask[i]) else COLOR_VOL_NORM
               for i in range(len(vol_data))]

    item = pg.BarGraphItem(x=xs, height=heights, width=0.6,
                           brushes=brushes, pen=pg.mkPen(None))
    self.p2.addItem(item)
    self._vol_bar_items = [item]


def _draw_plain_vol(self, vol_data):
    """LOOKBACK 미달 시 기본색으로 거래량 바만 그림."""
    if not vol_data:
        return
    xs = [x for x, _ in vol_data]
    hs = [v for _, v in vol_data]
    item = pg.BarGraphItem(x=xs, height=hs, width=0.6,
                            brush=COLOR_VOL_NORM, pen=pg.mkPen(None))
    self.p2.addItem(item)
    self._vol_bar_items = [item]


def clear_vol_surge(self):
    """오버레이 및 급증 표시 제거."""
    overlay = getattr(self, '_surge_overlay', None)
    if overlay:
        try:
            self.p1.removeItem(overlay)
        except Exception:
            pass
        self._surge_overlay = None

    for item in getattr(self, '_vol_bar_items', []):
        try:
            self.p2.removeItem(item)
        except Exception:
            pass
    self._vol_bar_items = []
