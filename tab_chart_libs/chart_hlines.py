"""
chart_hlines.py — 차트 가로 라인 (슬롯 기반)
────────────────────────────────────────────────────────
포함:
  on_chart_click()  — 클릭 → 수평선 추가
  on_hline_chk()    — 체크박스 해제 → 라인 삭제
  del_hlines()      — 전체 라인 삭제
  redraw_hlines()   — 재렌더링 후 라인 복원
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


from PyQt5.QtCore import Qt

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False


def on_chart_click(self, event):
    """p1 클릭 → 라인 긋기 모드일 때 빈 슬롯에 수평선 추가."""
    if not hasattr(self, 'btn_hline'): return
    if not self.btn_hline.isChecked(): return
    try:
        pos   = self.p1.vb.mapSceneToView(event.scenePos())
        price = round(pos.y(), 2)
        for s in self._hlines.values():
            if abs(s['price'] - price) < 0.01: return
        slot = None
        for i in range(self._hline_slots):
            if i not in self._hlines:
                slot = i; break
        if slot is None:
            self.lbl_hline_info.setText("⚠ 슬롯 10개 꽉 참 — 체크 해제로 삭제"); return
        pen  = pg.mkPen('#00e5ff', width=1, style=Qt.DashLine)
        line = pg.InfiniteLine(pos=price, angle=0, pen=pen, movable=True)
        line.setToolTip(f"[{slot+1}] {price:,.2f}")
        self.p1.addItem(line)
        self._hlines[slot] = {'price': price, 'line': line}
        chk = self._hline_chks[slot]
        chk.blockSignals(True)
        chk.setChecked(True); chk.setEnabled(True)
        chk.setStyleSheet("color:#00e5ff;font-size:10px;font-weight:bold;")
        chk.setToolTip(f"{price:,.2f}")
        chk.blockSignals(False)
        self.lbl_hline_info.setText(
            f"[{slot+1}] {price:,.2f}  (총 {len(self._hlines)}개)")
    except Exception as e:
        print(f"[hline] {e}")


def on_hline_chk(self, slot_idx: int, state: int):
    """체크박스 해제 → 해당 슬롯 라인 삭제."""
    if state == Qt.Checked: return
    if slot_idx not in self._hlines: return
    info = self._hlines.pop(slot_idx)
    try: self.p1.removeItem(info['line'])
    except Exception: pass
    chk = self._hline_chks[slot_idx]
    chk.blockSignals(True)
    chk.setChecked(False); chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;")
    chk.setToolTip("")
    chk.blockSignals(False)
    self.lbl_hline_info.setText(
        f"라인 [{slot_idx+1}] 삭제됨  (남은 {len(self._hlines)}개)")


def del_hlines(self):
    """등록된 가로 라인 전체 삭제."""
    for info in self._hlines.values():
        try: self.p1.removeItem(info['line'])
        except Exception: pass
    self._hlines.clear()
    for chk in self._hline_chks:
        chk.blockSignals(True)
        chk.setChecked(False); chk.setEnabled(False)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.blockSignals(False)
    if hasattr(self, 'lbl_hline_info'):
        self.lbl_hline_info.setText("라인 전체 삭제 완료")


def redraw_hlines(self):
    """차트 재렌더링 후 저장된 라인을 다시 그림."""
    for slot, info in list(self._hlines.items()):
        price = info['price']
        try: self.p1.removeItem(info['line'])
        except Exception: pass
        pen  = pg.mkPen('#00e5ff', width=1, style=Qt.DashLine)
        line = pg.InfiniteLine(pos=price, angle=0, pen=pen, movable=True)
        line.setToolTip(f"[{slot+1}] {price:,.2f}")
        self.p1.addItem(line)
        self._hlines[slot]['line'] = line
