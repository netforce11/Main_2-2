"""
kr_chart_labels.py — 텍스트 레이블 (숫자/문자)
"""
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False
from PyQt5.QtCore import Qt

LABEL_ITEMS = ["1","2","3","4","5","A","B","C","D","E"]


def on_chart_label_click(self, event):
    if not PG: return
    pos = event.scenePos()
    if not self.p1.sceneBoundingRect().contains(pos): return
    mp = self.p1.getViewBox().mapSceneToView(pos)
    label_txt = self.label_combo.currentText()
    slot = next((i for i, lbl in enumerate(LABEL_ITEMS)
                 if lbl == label_txt and i not in self._chart_labels), None)
    if slot is None:
        self.lbl_hline_info.setText(f"⚠ 레이블 [{label_txt}] 이미 사용 중"); return
    txt_item = pg.TextItem(text=label_txt, color='#00e5ff', anchor=(0.5, 1))
    txt_item.setPos(mp.x(), mp.y())
    self.p1.addItem(txt_item)
    self._chart_labels[slot] = {'text': label_txt, 'x': mp.x(), 'y': mp.y(), 'item': txt_item}
    chk = self._label_chks[slot]
    chk.blockSignals(True); chk.setChecked(True); chk.setEnabled(True)
    chk.setStyleSheet("color:#00e5ff;font-size:10px;font-weight:bold;"); chk.blockSignals(False)
    self.lbl_hline_info.setText(f"레이블 [{label_txt}] 추가됨")


def on_label_chk(self, slot_idx: int, state: int):
    if state == Qt.Checked or slot_idx not in self._chart_labels: return
    try: self.p1.removeItem(self._chart_labels.pop(slot_idx)['item'])
    except: pass
    chk = self._label_chks[slot_idx]
    chk.blockSignals(True); chk.setChecked(False); chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;"); chk.blockSignals(False)


def del_labels(self):
    for info in list(self._chart_labels.values()):
        try: self.p1.removeItem(info['item'])
        except: pass
    self._chart_labels.clear()
    for chk in self._label_chks:
        chk.blockSignals(True); chk.setChecked(False)
        chk.setEnabled(False); chk.setStyleSheet("color:#444;font-size:10px;")
        chk.blockSignals(False)


def redraw_labels(self):
    if not hasattr(self, '_chart_labels'): return
    for slot, info in list(self._chart_labels.items()):
        try: self.p1.removeItem(info['item'])
        except: pass
        txt_item = pg.TextItem(text=info['text'], color='#00e5ff', anchor=(0.5, 1))
        txt_item.setPos(info['x'], info['y'])
        self.p1.addItem(txt_item)
        self._chart_labels[slot]['item'] = txt_item
