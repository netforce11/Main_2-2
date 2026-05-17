"""
chart_daily_overlay.py — p1 위에 드래그 가능한 일봉 오버레이
════════════════════════════════════════════════════════════════
· p1 scene 위에 QGraphicsObject(_DragOverlay) 를 올림
· 상단 타이틀바(14px)를 드래그 → 자유롭게 이동
· 이동 후 위치 비율을 self._overlay_pos_frac 에 저장
  → 창 크기 바뀌어도 상대 위치 유지
· 캘린더 날짜 변경 / update_display() 호출 시 자동 갱신

외부 호출:
    from chart_daily_overlay import (
        init_daily_overlay,    # __init__ 에서 1회
        update_daily_overlay,  # update_display / on_calendar 에서 호출
        clear_daily_overlay,   # 오버레이 완전 제거
    )
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime, timedelta

try:
    import pyqtgraph as pg
    from pyqtgraph import QtCore, QtGui, QtWidgets
    PG = True
except ImportError:
    PG = False

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False

# ── 기본 위치/크기 (p1 scene 비율) ───────────────────────────
_DEF_X = 0.58   # 초기 x 위치 (p1 폭 대비)
_DEF_Y = 0.02   # 초기 y 위치 (p1 높이 대비)

# ※ 기본 너비/높이는 config_store 에서 읽음 (_DEF_W/_DEF_H 는 fallback)
_DEF_W = 0.31   # 너비 비율 fallback (기존 0.41 × 75%)
_DEF_H = 0.33   # 높이 비율 fallback (기존 0.44 × 75%)

BODY_W         = 0.4
COLOR_UP       = "#26a69a"
COLOR_DN       = "#ef5350"
COLOR_BG       = (8, 8, 24, 220)
COLOR_BORDER   = "#3a3a7a"
COLOR_CAL_LINE = "#f9a825"
COLOR_LABEL    = "#5dade2"
COLOR_TITLEBAR = (30, 30, 60, 230)
TITLEBAR_H     = 14    # 드래그 핸들 높이 (px)


# ── config_store 읽기 헬퍼 ────────────────────────────────────

def _cfg_half() -> int:
    """캘린더 날짜 기준 앞뒤 봉 수 (±N). config_store 우선."""
    try:
        from Main_config import config_store
        return max(1, config_store.overlay_candle_half)
    except Exception:
        return 10

def _cfg_w() -> float:
    """오버레이 너비 비율 (0.0~1.0). config_store 우선."""
    try:
        from Main_config import config_store
        return max(0.05, config_store.overlay_width_pct / 100.0)
    except Exception:
        return _DEF_W

def _cfg_h() -> float:
    """오버레이 높이 비율 (0.0~1.0). config_store 우선."""
    try:
        from Main_config import config_store
        return max(0.05, config_store.overlay_height_pct / 100.0)
    except Exception:
        return _DEF_H


# ══════════════════════════════════════════════════════════════
# 드래그 컨테이너
# ══════════════════════════════════════════════════════════════

class _DragOverlay(QtWidgets.QGraphicsObject):
    """
    scene 위에 올라가는 드래그 가능한 오버레이 컨테이너.
    상단 TITLEBAR_H px 영역을 마우스로 누르면 드래그.
    내부 ViewBox(self.vb)에 캔들 아이템을 addItem.
    """

    def __init__(self, chart_self, x, y, w, h):
        super().__init__()
        self._cs         = chart_self
        self._rect       = QtCore.QRectF(0, 0, w, h)
        self._drag_start = None
        self._pos_start  = None

        self.setPos(x, y)
        self.setZValue(50)
        self.setAcceptHoverEvents(True)

        # 내장 ViewBox
        self._vb = pg.ViewBox()
        self._vb.setMouseEnabled(x=False, y=False)
        self._vb.setMenuEnabled(False)
        self._vb.setParentItem(self)
        self._vb.setGeometry(QtCore.QRectF(
            1, TITLEBAR_H + 1, w - 2, h - TITLEBAR_H - 2))
        self._vb.setZValue(51)

        self._border_pen = pg.mkPen(COLOR_BORDER, width=1)

    @property
    def vb(self):
        return self._vb

    def resize(self, x, y, w, h):
        self.setPos(x, y)
        self._rect = QtCore.QRectF(0, 0, w, h)
        self._vb.setGeometry(QtCore.QRectF(
            1, TITLEBAR_H + 1, w - 2, h - TITLEBAR_H - 2))
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        r = self._rect

        # 배경
        painter.setBrush(QtGui.QBrush(QtGui.QColor(*COLOR_BG)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(r)

        # 타이틀바
        painter.setBrush(QtGui.QBrush(QtGui.QColor(*COLOR_TITLEBAR)))
        painter.drawRect(QtCore.QRectF(0, 0, r.width(), TITLEBAR_H))

        # 타이틀 텍스트
        painter.setPen(QtGui.QPen(QtGui.QColor(COLOR_LABEL)))
        font = QtGui.QFont("Arial", 8)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRectF(4, 0, r.width() - 8, TITLEBAR_H),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            "≡ 일봉  (타이틀바 드래그로 이동)")

        # 테두리
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(self._border_pen)
        painter.drawRect(QtCore.QRectF(
            0.5, 0.5, r.width() - 1, r.height() - 1))

    # ── 드래그 ────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            if ev.pos().y() <= TITLEBAR_H:
                self._drag_start = ev.scenePos()
                self._pos_start  = QtCore.QPointF(self.pos())
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_start is not None:
            delta   = ev.scenePos() - self._drag_start
            new_pos = self._pos_start + delta
            self.setPos(new_pos)
            self._save_frac()
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag_start is not None:
            self._drag_start = None
            self._pos_start  = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def hoverMoveEvent(self, ev):
        if ev.pos().y() <= TITLEBAR_H:
            self.setCursor(QtCore.Qt.SizeAllCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
        super().hoverMoveEvent(ev)

    def _save_frac(self):
        """현재 위치를 p1 scene 비율로 저장 → 창 리사이즈 후에도 유지."""
        try:
            sr  = self._cs.p1.getViewBox().sceneBoundingRect()
            pos = self.pos()
            self._cs._overlay_pos_frac = (
                (pos.x() - sr.x()) / sr.width(),
                (pos.y() - sr.y()) / sr.height(),
            )
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# 초기화
# ══════════════════════════════════════════════════════════════

def init_daily_overlay(self):
    """ChartGrid.__init__ 에서 1회 호출."""
    if not PG:
        return
    self._overlay_obj      = None
    self._overlay_items    = []
    self._overlay_visible  = True
    self._overlay_bars     = []
    self._overlay_pos_frac = (_DEF_X, _DEF_Y)


# ══════════════════════════════════════════════════════════════
# 외부 진입점
# ══════════════════════════════════════════════════════════════

def update_daily_overlay(self):
    """update_display() / on_calendar() 에서 호출."""
    if not PG:
        return
    if not getattr(self, '_overlay_visible', True):
        return

    sym = getattr(self, 'sym_in', None)
    sym = sym.text().strip().upper() if sym else ""
    if not sym:
        return

    cal_date = self.calendar.selectedDate().toString("yyyy-MM-dd")

    _prev = getattr(self, '_overlay_worker', None)
    if _prev:
        try:
            _prev.quit()
        except Exception:
            pass
        self._overlay_worker = None

    try:
        from chart_daily_worker import _DailyFillWorker
        w = _DailyFillWorker(sym, cal_date, getattr(self, 'api_key', ''))
        w.done.connect(lambda df: _draw_overlay(self, df, cal_date))
        w.error.connect(
            lambda msg: print(f"[Overlay] 일봉 로드 실패: {msg}"))
        w.start()
        self._overlay_worker = w
    except Exception as e:
        print(f"[Overlay] worker 생성 실패: {e}")


# ══════════════════════════════════════════════════════════════
# 렌더링
# ══════════════════════════════════════════════════════════════

def _draw_overlay(self, df, cal_date_str: str):
    """일봉 데이터 수신 → 오버레이에 캔들 렌더."""
    if not PG:
        return
    if df is None or (PANDAS and df.empty):
        return

    try:
        cal_date = datetime.strptime(cal_date_str, "%Y-%m-%d").date()
    except Exception:
        return

    OVERLAY_HALF = _cfg_half()   # config_store 에서 읽기

    bars_all = list(df[["t","o","h","l","c","v"]].itertuples(
                    index=False, name=None))
    if not bars_all:
        return

    best_i, best_d = 0, timedelta(days=9999)
    for i, b in enumerate(bars_all):
        d = abs(datetime.fromtimestamp(b[0] / 1000).date() - cal_date)
        if d < best_d:
            best_d = d; best_i = i

    lo   = max(0, best_i - OVERLAY_HALF)
    hi   = min(len(bars_all) - 1, best_i + OVERLAY_HALF)
    bars = bars_all[lo: hi + 1]
    cal_local_idx = best_i - lo

    if not bars:
        return

    self._overlay_bars = bars

    obj = _ensure_overlay_obj(self)
    if obj is None:
        return
    vb = obj.vb

    _clear_overlay_items(self, vb)

    n    = len(bars)
    y_lo = min(b[3] for b in bars)
    y_hi = max(b[2] for b in bars)
    mg   = (y_hi - y_lo) * 0.08 if (y_hi - y_lo) > 0 else y_hi * 0.01
    c_ylo, c_yhi = y_lo - mg, y_hi + mg

    for i, b in enumerate(bars):
        o_, h_, l_, c_ = b[1], b[2], b[3], b[4]
        col = COLOR_UP if c_ >= o_ else COLOR_DN
        pen = pg.mkPen(col, width=1)
        bru = pg.mkBrush(col)

        wick = pg.PlotDataItem(x=[i, i], y=[l_, h_], pen=pen)
        vb.addItem(wick); _track(self, wick)

        top = max(o_, c_); bot = min(o_, c_)
        bh  = max(top - bot, (y_hi - y_lo) * 0.001)
        body = QtWidgets.QGraphicsRectItem(i - BODY_W/2, bot, BODY_W, bh)
        body.setPen(pen); body.setBrush(bru)
        vb.addItem(body); _track(self, body)

    vline = pg.InfiniteLine(
        pos=cal_local_idx, angle=90,
        pen=pg.mkPen(COLOR_CAL_LINE, width=1,
                     style=QtCore.Qt.DashLine))
    vb.addItem(vline); _track(self, vline)

    d_s = datetime.fromtimestamp(bars[0][0]  / 1000).strftime("%m/%d")
    d_e = datetime.fromtimestamp(bars[-1][0] / 1000).strftime("%m/%d")
    lbl = pg.TextItem(
        text=f"{d_s} ~ {d_e}  (±{OVERLAY_HALF})",
        color=COLOR_LABEL, anchor=(1, 0))
    lbl.setPos(n - 0.5, c_yhi)
    lbl.setZValue(20)
    vb.addItem(lbl); _track(self, lbl)

    vb.setYRange(c_ylo, c_yhi, padding=0)
    vb.setXRange(-0.5, n - 0.5, padding=0)


# ══════════════════════════════════════════════════════════════
# 컨테이너 생성 / 재배치
# ══════════════════════════════════════════════════════════════

def _ensure_overlay_obj(self):
    if not PG:
        return None
    try:
        p1    = self.p1
        scene = p1.scene()
    except AttributeError:
        return None

    sr = p1.getViewBox().sceneBoundingRect()
    w  = sr.width()  * _cfg_w()   # config_store 에서 읽기
    h  = sr.height() * _cfg_h()   # config_store 에서 읽기

    obj = getattr(self, '_overlay_obj', None)

    # scene 이 바뀌었으면 기존 것 제거
    if obj is not None:
        try:
            if obj.scene() is not scene:
                obj.scene().removeItem(obj)
                obj = None
        except Exception:
            obj = None

    if obj is None:
        xf, yf = getattr(self, '_overlay_pos_frac', (_DEF_X, _DEF_Y))
        x = sr.x() + sr.width()  * xf
        y = sr.y() + sr.height() * yf
        obj = _DragOverlay(self, x, y, w, h)
        scene.addItem(obj)
        self._overlay_obj = obj

        # p1 리사이즈 시 위치/크기 재계산
        try:
            p1.getViewBox().sigResized.connect(
                lambda _=None: _refit_overlay(self))
        except Exception:
            pass
    else:
        _refit_overlay(self)

    return obj


def _refit_overlay(self):
    """p1 크기 변경 시 오버레이 위치/크기를 비율 기준으로 재계산."""
    obj = getattr(self, '_overlay_obj', None)
    if obj is None:
        return
    try:
        sr  = self.p1.getViewBox().sceneBoundingRect()
        xf, yf = getattr(self, '_overlay_pos_frac', (_DEF_X, _DEF_Y))
        x   = sr.x() + sr.width()  * xf
        y   = sr.y() + sr.height() * yf
        w   = sr.width()  * _cfg_w()   # config_store 에서 읽기
        h   = sr.height() * _cfg_h()   # config_store 에서 읽기
        obj.resize(x, y, w, h)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 아이템 추적 / 정리
# ══════════════════════════════════════════════════════════════

def _track(self, item):
    if not hasattr(self, '_overlay_items'):
        self._overlay_items = []
    self._overlay_items.append(item)


def _clear_overlay_items(self, vb):
    for item in getattr(self, '_overlay_items', []):
        try:
            vb.removeItem(item)
        except Exception:
            pass
    self._overlay_items = []


def clear_daily_overlay(self):
    """오버레이 완전 제거."""
    obj = getattr(self, '_overlay_obj', None)
    if obj is not None:
        try:
            obj.scene().removeItem(obj)
        except Exception:
            pass
        self._overlay_obj = None
    self._overlay_items = []