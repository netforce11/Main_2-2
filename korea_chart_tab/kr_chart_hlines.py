"""
kr_chart_hlines.py — 가로 라인 (클릭 → 추가, 체크 해제 → 삭제)
"""
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False
from PyQt5.QtCore import Qt


def on_chart_click(self, event):
    """차트 클릭 → 가로 라인 또는 레이블 추가."""
    if not PG: return
    # 레이블 모드
    if hasattr(self, 'btn_label') and self.btn_label.isChecked():
        from kr_chart_labels import on_chart_label_click
        on_chart_label_click(self, event); return
    # 가로 라인 모드
    if not (hasattr(self, 'btn_hline') and self.btn_hline.isChecked()): return
    pos = event.scenePos()
    if not self.p1.sceneBoundingRect().contains(pos): return
    mp = self.p1.getViewBox().mapSceneToView(pos)
    price = mp.y()
    slot = next((i for i in range(self._hline_slots) if i not in self._hlines), None)
    if slot is None:
        self.lbl_hline_info.setText("⚠ 라인 슬롯 10개 꽉 참"); return
    pen = pg.mkPen('#00e676', width=1, style=Qt.DashLine)
    line = pg.InfiniteLine(pos=price, angle=0, pen=pen, movable=True,
                           label=f"{price:,.0f}", labelOpts={'color': '#00e676'})
    self.p1.addItem(line)
    self._hlines[slot] = {'price': price, 'line': line}
    chk = self._hline_chks[slot]
    chk.blockSignals(True); chk.setChecked(True); chk.setEnabled(True)
    chk.setStyleSheet("color:#00e676;font-size:10px;font-weight:bold;"); chk.blockSignals(False)
    self.lbl_hline_info.setText(f"라인[{slot+1}] {price:,.0f}원 추가")


def on_hline_chk(self, slot_idx: int, state: int):
    if state == Qt.Checked or slot_idx not in self._hlines: return
    try: self.p1.removeItem(self._hlines.pop(slot_idx)['line'])
    except: pass
    chk = self._hline_chks[slot_idx]
    chk.blockSignals(True); chk.setChecked(False); chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;"); chk.blockSignals(False)


def del_hlines(self):
    for info in list(self._hlines.values()):
        try: self.p1.removeItem(info['line'])
        except: pass
    self._hlines.clear()
    for chk in self._hline_chks:
        chk.blockSignals(True); chk.setChecked(False)
        chk.setEnabled(False); chk.setStyleSheet("color:#444;font-size:10px;")
        chk.blockSignals(False)


def redraw_hlines(self):
    if not hasattr(self, '_hlines'): return
    for slot, info in list(self._hlines.items()):
        try: self.p1.removeItem(info['line'])
        except: pass
        pen = pg.mkPen('#00e676', width=1, style=Qt.DashLine)
        line = pg.InfiniteLine(pos=info['price'], angle=0, pen=pen, movable=True,
                               label=f"{info['price']:,.0f}",
                               labelOpts={'color': '#00e676'})
        self.p1.addItem(line)
        self._hlines[slot]['line'] = line
