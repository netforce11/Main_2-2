"""
chart_history_vline.py — VlineMixin: vline add / toggle / clear  [NEW — S6]
Extracted from chart_history.py to keep both files ≤ 300 lines.
"""

from PyQt5.QtWidgets import QCheckBox
from PyQt5.QtCore import Qt


class VlineMixin:
    """Manages vertical line overlays on MiniChartCanvas (intraday tab)."""

    _CIRCLE_NUMS = [
        "①","②","③","④","⑤","⑥","⑦","⑧","⑨","⑩",
        "⑪","⑫","⑬","⑭","⑮","⑯","⑰","⑱","⑲","⑳",
    ]

    def _on_intra_time_changed(self, text: str):
        """Auto-insert colon after 2 digits (HH:MM format)."""
        if not hasattr(self, 'intra_time_input'):
            return
        digits = text.replace(":", "")
        if len(digits) >= 2 and ":" not in text:
            self.intra_time_input.blockSignals(True)
            new_text = digits[:2] + ":" + digits[2:]
            self.intra_time_input.setText(new_text)
            self.intra_time_input.setCursorPosition(len(new_text))
            self.intra_time_input.blockSignals(False)

    def _on_add_vline(self):
        """HH:MM input → add vline to MiniChartCanvas + register checkbox."""
        if not hasattr(self, 'intra_time_input'):
            return
        text = self.intra_time_input.text().strip()
        if len(text) != 5 or text[2] != ":":
            if hasattr(self, 'lbl_intra_status'):
                self.lbl_intra_status.setText("⚠ 시간 형식 오류: HH:MM")
            return

        existing = [v[0] for v in getattr(self, '_vlines', [])]
        if text in existing:
            if hasattr(self, 'lbl_intra_status'):
                self.lbl_intra_status.setText(f"⚠ {text} 세로선이 이미 존재합니다")
            return

        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas is None:
            return

        try:
            canvas.add_vline(text)
        except AttributeError:
            pass

        idx     = len(getattr(self, '_vlines', []))
        num_str = (self._CIRCLE_NUMS[idx]
                   if idx < len(self._CIRCLE_NUMS) else f"({idx+1})")
        label_text = f"{num_str} {text}"

        cb = QCheckBox(label_text)
        cb.setChecked(True)
        cb.setStyleSheet(
            "QCheckBox{color:#ffd700;font-size:11px;}"
            "QCheckBox::indicator{width:12px;height:12px;}"
            "QCheckBox::indicator:checked{background:#ffd700;border:1px solid #aaa;}"
            "QCheckBox::indicator:unchecked{background:#1a1a3a;border:1px solid #555;}")
        cb.stateChanged.connect(
            lambda state, t=text: self._on_vline_toggle(t, state))

        if hasattr(self, '_vline_panel_layout'):
            layout = self._vline_panel_layout
            layout.insertWidget(layout.count() - 1, cb)

        if not hasattr(self, '_vlines'):
            self._vlines = []
        self._vlines.append((text, cb))
        self.intra_time_input.clear()

        if hasattr(self, 'lbl_intra_status'):
            self.lbl_intra_status.setText(f"✅ 세로선 추가: {label_text}")

    def _on_vline_toggle(self, time_str: str, state: int):
        """Checkbox ON/OFF → show/hide vline on MiniChartCanvas."""
        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas is None:
            return
        visible = (state == Qt.Checked)
        try:
            canvas.set_vline_visible(time_str, visible)
        except AttributeError:
            pass

    def _on_clear_all_vlines(self):
        """Delete all vlines and clear checkbox list."""
        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas:
            try:
                canvas.clear_vlines()
            except AttributeError:
                pass

        for _, cb in getattr(self, '_vlines', []):
            cb.deleteLater()
        self._vlines = []

        if hasattr(self, 'lbl_intra_status'):
            self.lbl_intra_status.setText("세로선 전체 삭제 완료")
