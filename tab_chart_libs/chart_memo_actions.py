"""
chart_memo_actions.py — 메모 저장/삭제/상태 핸들러
[분리] chart_memo.py 에서 분리 (_memo_save, _memo_delete, _set_memo_status)
"""
from chart_memo_io import _save_memos

# ══════════════════════════════════════════════════════════════
def _memo_save(self):
    """현재 날짜에 메모 저장."""
    key = getattr(self, "_memo_current_date", None)
    if not key:
        _set_memo_status(self, "⚠ 캘린더에서 날짜를 먼저 선택하세요.", error=True)
        return

    edit = getattr(self, "_memo_edit", None)
    text = edit.toPlainText().strip() if edit else ""

    if not text:
        _set_memo_status(self, "⚠ 내용이 비어 있습니다.", error=True)
        return

    # 메모 딕셔너리 갱신 후 저장
    self._memo_data[key] = text
    _save_memos(self._memo_data)
    _set_memo_status(self, f"💾 저장 완료 ({key})", error=False)


def _memo_delete(self):
    """현재 날짜의 메모 삭제 (확인 후)."""
    key = getattr(self, "_memo_current_date", None)
    if not key:
        _set_memo_status(self, "⚠ 캘린더에서 날짜를 먼저 선택하세요.", error=True)
        return

    if key not in self._memo_data:
        _set_memo_status(self, "삭제할 메모가 없습니다.", error=True)
        return

    reply = QMessageBox.question(
        None, "메모 삭제",
        f"{key} 의 메모를 삭제하시겠습니까?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    if reply != QMessageBox.Yes:
        return

    del self._memo_data[key]
    _save_memos(self._memo_data)

    edit = getattr(self, "_memo_edit", None)
    if edit:
        edit.clear()
    _set_memo_status(self, f"🗑 삭제 완료 ({key})", error=True)


def _set_memo_status(self, msg: str, error: bool = False):
    """메모 상태 라벨 텍스트 & 색상 설정."""
    lbl = getattr(self, "_memo_status_lbl", None)
    if lbl is None:
        return
    lbl.setText(msg)
    color = "#ef5350" if error else "#4caf50"
    lbl.setStyleSheet(f"color:{color};font-size:10px;padding-left:2px;")
