"""
chart_markers.py — 시간 마커 + 차트 캡쳐
────────────────────────────────────────────────────────
포함:
  parse_time_input()    — 숫자만 입력(HHMM) → HH:MM 자동 변환 (신규)
  add_time_marker()     — ▼ 마커 버튼 핸들러
  on_marker_chk()       — 마커 체크박스 해제 → 삭제
  redraw_time_markers() — 차트 재렌더링 후 마커 복원
  capture_chart()       — 📷 차트 캡쳐 → C:/data/chart_save/ 저장 (신규)
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


import re
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

# 캡쳐 저장 경로 — [수정] 크로스플랫폼 (기존: Windows 전용 경로)
import platform as _platform
if _platform.system() == "Windows":
    CAPTURE_DIR = Path(r"C:\data\chart_save")
else:
    CAPTURE_DIR = Path("/home/netforce/US_Data/chart_save")


def parse_time_input(txt: str) -> str:
    """
    시간 입력 자동 포맷 변환.
    - "1030"   → "10:30"
    - "930"    → "09:30"
    - "10:30"  → "10:30"  (그대로)
    - "1030a"  → "" (오류)
    반환: "HH:MM" 문자열 또는 "" (파싱 실패)
    """
    txt = txt.strip()
    if not txt:
        return ""
    # 이미 HH:MM 형식
    if re.match(r'^\d{1,2}:\d{2}$', txt):
        parts = txt.split(":")
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    # 숫자만 (3~4자리)
    if re.match(r'^\d{3,4}$', txt):
        if len(txt) == 3:
            h, m = int(txt[0]), int(txt[1:])
        else:
            h, m = int(txt[:2]), int(txt[2:])
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"
    return ""


def _time_to_min(t_str: str) -> int:
    try:
        h, m = map(int, t_str.split(":"))
        return h * 60 + m
    except Exception:
        return 0


def add_time_marker(self):
    """▼ 마커 버튼 — HH:MM 또는 숫자만 입력 모두 지원."""
    if not PG or not hasattr(self, 'p1'):
        self.lbl_hline_info.setText("⚠ 차트 미초기화"); return
    if not hasattr(self, '_x_time_map') or not self._x_time_map:
        self.lbl_hline_info.setText("⚠ 차트 데이터 없음 — 먼저 데이터를 로드하세요"); return

    raw = self.time_marker_in.text().strip()
    target_time = parse_time_input(raw)
    if not target_time:
        self.lbl_hline_info.setText("⚠ 시간 형식 오류 — 1030 또는 10:30 으로 입력"); return

    # 입력 필드를 HH:MM 형식으로 자동 교정
    self.time_marker_in.setText(target_time)

    target_min = _time_to_min(target_time)
    best_x, best_diff = None, float('inf')
    for x, t_str in self._x_time_map.items():
        t_part = t_str[-5:]
        diff = abs(_time_to_min(t_part) - target_min)
        if diff < best_diff:
            best_diff = diff; best_x = x
    if best_x is None:
        self.lbl_hline_info.setText("⚠ 해당 시간 데이터 없음"); return

    # 빈 슬롯 탐색
    slot = None
    for i in range(self._marker_slots):
        if i not in self._time_markers:
            slot = i; break
    if slot is None:
        self.lbl_hline_info.setText("⚠ 마커 슬롯 5개 꽉 참 — 체크 해제로 삭제"); return

    pen    = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
    marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
    marker._marker_time = target_time
    marker._marker_slot = slot
    try:
        marker.setLabel(target_time, position=0.95,
                        color='#ff9800', fill=(50, 30, 0, 120))
    except AttributeError:
        try:
            pg.InfLineLabel(marker, target_time, position=0.95,
                            color='#ff9800', fill=(50, 30, 0, 120))
        except Exception:
            pass
    self.p1.addItem(marker)
    self._time_markers[slot] = {'time': target_time, 'line': marker}

    chk = self._marker_chks[slot]
    chk.blockSignals(True)
    chk.setChecked(True); chk.setEnabled(True)
    chk.setStyleSheet("color:#ff9800;font-size:10px;font-weight:bold;")
    chk.setToolTip(target_time)
    chk.blockSignals(False)
    self.lbl_hline_info.setText(
        f"마커[{slot+1}] {target_time} → x={best_x}  (총 {len(self._time_markers)}개)")


def on_marker_chk(self, slot_idx: int, state: int):
    """마커 체크박스 해제 → 해당 슬롯 마커 삭제."""
    if state == Qt.Checked:
        return
    if slot_idx not in self._time_markers:
        return
    info = self._time_markers.pop(slot_idx)
    try:
        self.p1.removeItem(info['line'])
    except Exception:
        pass
    chk = self._marker_chks[slot_idx]
    chk.blockSignals(True)
    chk.setChecked(False); chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;")
    chk.setToolTip("")
    chk.blockSignals(False)
    self.lbl_hline_info.setText(
        f"마커 [{slot_idx+1}] 삭제됨  (남은 {len(self._time_markers)}개)")


def redraw_time_markers(self):
    """차트 재렌더링 후 시간 마커 복원."""
    if not hasattr(self, '_time_markers'): return
    if not hasattr(self, '_x_time_map') or not self._x_time_map: return
    for slot, info in list(self._time_markers.items()):
        try:
            self.p1.removeItem(info['line'])
        except Exception:
            pass
        m_time     = info['time']
        target_min = _time_to_min(m_time)
        best_x, best_diff = None, float('inf')
        for x, t_str in self._x_time_map.items():
            diff = abs(_time_to_min(t_str[-5:]) - target_min)
            if diff < best_diff:
                best_diff = diff; best_x = x
        if best_x is None:
            continue
        pen    = pg.mkPen('#ff9800', width=2, style=Qt.SolidLine)
        marker = pg.InfiniteLine(pos=best_x, angle=90, pen=pen, movable=False)
        marker._marker_time = m_time
        marker._marker_slot = slot
        try:
            marker.setLabel(m_time, position=0.95,
                            color='#ff9800', fill=(50, 30, 0, 120))
        except AttributeError:
            try:
                pg.InfLineLabel(marker, m_time, position=0.95,
                                color='#ff9800', fill=(50, 30, 0, 120))
            except Exception:
                pass
        self.p1.addItem(marker)
        self._time_markers[slot]['line'] = marker



# [분리] capture_chart → chart_capture.py
from chart_capture import capture_chart  # noqa: F401
