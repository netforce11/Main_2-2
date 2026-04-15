"""
chart_labels.py — 차트 텍스트 레이블 (숫자 1~5 / 문자 A~E)
────────────────────────────────────────────────────────
포함:
  on_chart_label_click()  — 클릭 → 레이블 추가
  on_label_chk()          — 체크박스 해제 → 삭제
  del_labels()            — 전체 삭제
  redraw_labels()         — 재렌더링 후 복원
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

# 슬롯 레이블 목록 (슬롯 0~9)
LABEL_ITEMS = ["1", "2", "3", "4", "5", "A", "B", "C", "D", "E"]


def _label_color(text: str) -> str:
    """숫자 → 주황, 문자 → 하늘색"""
    return "#ff9800" if text.isdigit() else "#00e5ff"


def _make_text_item(label: str, x: float, y: float) -> "pg.TextItem":
    color = _label_color(label)
    item = pg.TextItem(
        text=label,
        color=color,
        anchor=(0.5, 1.0),  # 텍스트 하단 중앙이 클릭 지점에 오도록
    )
    item.setPos(x, y)
    f = QFont()
    f.setPointSize(13)
    f.setBold(True)
    item.setFont(f)
    return item


def on_chart_label_click(self, event):
    """
    p1 클릭 → 레이블 모드(btn_label ON)일 때
    콤보박스에서 선택된 레이블을 클릭 위치에 추가.
    같은 슬롯에 이미 레이블이 있으면 위치만 이동.
    """
    if not PG or not hasattr(self, 'p1'):
        return
    if not hasattr(self, 'btn_label') or not self.btn_label.isChecked():
        return

    try:
        pos  = self.p1.vb.mapSceneToView(event.scenePos())
        x, y = pos.x(), pos.y()

        label = self.label_combo.currentText()
        if label not in LABEL_ITEMS:
            return
        slot = LABEL_ITEMS.index(label)

        # 같은 슬롯 기존 아이템 제거
        if slot in self._chart_labels:
            try:
                self.p1.removeItem(self._chart_labels[slot]['item'])
            except Exception:
                pass

        item = _make_text_item(label, x, y)
        self.p1.addItem(item)
        self._chart_labels[slot] = {
            'label': label, 'x': x, 'y': y, 'item': item
        }

        chk = self._label_chks[slot]
        chk.blockSignals(True)
        chk.setChecked(True)
        chk.setEnabled(True)
        chk.setStyleSheet(
            f"color:{_label_color(label)};font-size:10px;font-weight:bold;")
        chk.setToolTip(f"{label}  x={x:.1f}  y={y:.2f}")
        chk.blockSignals(False)

        if hasattr(self, 'lbl_hline_info'):
            self.lbl_hline_info.setText(
                f"레이블 [{label}] 추가  (총 {len(self._chart_labels)}개)")

    except Exception as e:
        print(f"[Labels] on_chart_label_click 오류: {e}")


def on_label_chk(self, slot_idx: int, state: int):
    """체크박스 해제 → 해당 슬롯 레이블 삭제."""
    if state == Qt.Checked:
        return
    if slot_idx not in self._chart_labels:
        return

    info = self._chart_labels.pop(slot_idx)
    try:
        self.p1.removeItem(info['item'])
    except Exception:
        pass

    chk = self._label_chks[slot_idx]
    chk.blockSignals(True)
    chk.setChecked(False)
    chk.setEnabled(False)
    chk.setStyleSheet("color:#444;font-size:10px;")
    chk.setToolTip("")
    chk.blockSignals(False)

    if hasattr(self, 'lbl_hline_info'):
        self.lbl_hline_info.setText(
            f"레이블 [{info['label']}] 삭제  (남은 {len(self._chart_labels)}개)")


def del_labels(self):
    """등록된 레이블 전체 삭제."""
    for info in self._chart_labels.values():
        try:
            self.p1.removeItem(info['item'])
        except Exception:
            pass
    self._chart_labels.clear()

    for chk in self._label_chks:
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.setEnabled(False)
        chk.setStyleSheet("color:#444;font-size:10px;")
        chk.setToolTip("")
        chk.blockSignals(False)

    if hasattr(self, 'lbl_hline_info'):
        self.lbl_hline_info.setText("레이블 전체 삭제 완료")


def redraw_labels(self):
    """차트 재렌더링 후 저장된 레이블을 다시 그림."""
    if not hasattr(self, '_chart_labels'):
        return
    for slot, info in list(self._chart_labels.items()):
        try:
            self.p1.removeItem(info['item'])
        except Exception:
            pass
        item = _make_text_item(info['label'], info['x'], info['y'])
        self.p1.addItem(item)
        self._chart_labels[slot]['item'] = item
