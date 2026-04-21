"""
kr_chart_markers.py — 시간 마커 + 차트 캡쳐
"""
import re
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox
try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

CAPTURE_DIR = Path(r"C:\data\chart_save")


def _parse_time(txt: str) -> str:
    txt = txt.strip()
    if re.match(r'^\d{1,2}:\d{2}$', txt):
        p = txt.split(":")
        return f"{int(p[0]):02d}:{int(p[1]):02d}"
    if re.match(r'^\d{3,4}$', txt):
        h, m = (int(txt[0]), int(txt[1:])) if len(txt) == 3 else (int(txt[:2]), int(txt[2:]))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    return ""


def _t2min(t: str) -> int:
    try: h, m = map(int, t.split(":")); return h * 60 + m
    except: return 0


def add_time_marker(self):
    if not PG or not hasattr(self, 'p1'): return
    if not hasattr(self, '_x_time_map') or not self._x_time_map:
        self.lbl_hline_info.setText("⚠ 데이터를 먼저 로드하세요"); return
    raw = self.time_marker_in.text().strip()
    target = _parse_time(raw)
    if not target:
        self.lbl_hline_info.setText("⚠ 시간 형식 오류 — 0930 또는 09:30"); return
    self.time_marker_in.setText(target)
    tmin = _t2min(target)
    best_x = min(self._x_time_map, key=lambda x: abs(_t2min(self._x_time_map[x][-5:]) - tmin), default=None)
    if best_x is None: return
    slot = next((i for i in range(self._marker_slots) if i not in self._time_markers), None)
    if slot is None:
        self.lbl_hline_info.setText("⚠ 마커 슬롯 5개 꽉 참"); return
    pen = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
    marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
    marker._marker_time = target
    try: marker.setLabel(target, position=0.95, color='#ff9800', fill=(50, 30, 0, 120))
    except: pass
    self.p1.addItem(marker)
    self._time_markers[slot] = {'time': target, 'line': marker}
    chk = self._marker_chks[slot]
    chk.blockSignals(True); chk.setChecked(True); chk.setEnabled(True)
    chk.setStyleSheet("color:#ff9800;font-size:10px;font-weight:bold;"); chk.blockSignals(False)
    self.lbl_hline_info.setText(f"마커[{slot+1}] {target} 추가됨")


def on_marker_chk(self, slot_idx: int, state: int):
    if state == Qt.Checked or slot_idx not in self._time_markers: return
    info = self._time_markers.pop(slot_idx)
    try: self.p1.removeItem(info['line'])
    except: pass
    chk = self._marker_chks[slot_idx]
    chk.blockSignals(True); chk.setChecked(False); chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;"); chk.blockSignals(False)


def redraw_time_markers(self):
    if not hasattr(self, '_time_markers') or not hasattr(self, '_x_time_map'): return
    for slot, info in list(self._time_markers.items()):
        try: self.p1.removeItem(info['line'])
        except: pass
        tmin = _t2min(info['time'])
        best_x = min(self._x_time_map, key=lambda x: abs(_t2min(self._x_time_map[x][-5:]) - tmin), default=None)
        if best_x is None: continue
        pen = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
        marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
        try: marker.setLabel(info['time'], position=0.95, color='#ff9800', fill=(50, 30, 0, 120))
        except: pass
        self.p1.addItem(marker)
        self._time_markers[slot]['line'] = marker


def capture_chart(self):
    if not PG or not hasattr(self, 'gfx'):
        QMessageBox.warning(self, "캡쳐 불가", "차트가 초기화되지 않았습니다."); return
    try: CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e: QMessageBox.critical(self, "캡쳐 오류", str(e)); return
    chart_date = (self.selected_date.strftime("%Y%m%d") if self.selected_date
                  else datetime.now().strftime("%Y%m%d"))
    fname = f"{chart_date}_{datetime.now().strftime('%H%M%S')}_{self.current_sym}.png"
    fpath = CAPTURE_DIR / fname
    try:
        pixmap = self.gfx.grab()
        if not pixmap.isNull(): pixmap.save(str(fpath), "PNG")
        self.lbl_hline_info.setText(f"📷 저장: {fname}")
    except Exception as e:
        QMessageBox.critical(self, "캡쳐 오류", str(e))
