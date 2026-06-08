"""
chart_candle_item.py — pyqtgraph 캔들스틱 렌더링 아이템
[분리] chart_workers.py 에서 분리
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtGui import QPicture, QPainter, QColor

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

if PG:
    class CandlestickItem(pg.GraphicsObject):
        def __init__(self, data, up="#3c78ff", dn="#ff3c3c"):
            pg.GraphicsObject.__init__(self)
            self.data = data; self.up = up; self.dn = dn
            self._gen()

        def _gen(self):
            self.picture = QPicture()
            p = QPainter(self.picture)
            for t, o, c, lo, hi in self.data:
                col = QColor(self.up if c >= o else self.dn)
                p.setPen(pg.mkPen(col, width=1))
                p.setBrush(pg.mkBrush(col))
                p.drawLine(pg.QtCore.QPointF(t, lo), pg.QtCore.QPointF(t, hi))
                p.drawRect(pg.QtCore.QRectF(t - 0.3, o, 0.6, c - o))
            p.end()

        def paint(self, p, *a): p.drawPicture(0, 0, self.picture)
        def boundingRect(self): return pg.QtCore.QRectF(self.picture.boundingRect())
