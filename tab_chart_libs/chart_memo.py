"""
chart_memo.py — 날짜별 메모 관리 모듈  v1.0
════════════════════════════════════════════════════════════════
기능:
  - 날짜별 메모 추가 / 수정 / 삭제
  - JSON 파일로 영구 저장
    저장 경로: /home/netforce/US_Data/chart_memos.json
  - 캘린더 날짜 클릭 시 해당 날짜 메모 자동 출력
  - 메모 패널 토글 (열기/닫기)

외부 API:
  build_memo_panel(self) → QWidget   사이드바에 삽입할 패널
  toggle_memo_panel(self)             패널 열기/닫기 토글
  on_memo_date_changed(self, qdate)   캘린더 클릭 시 호출 → 해당일 메모 표시
════════════════════════════════════════════════════════════════
"""

import json
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFrame,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QFont

# ── 저장 경로 ────────────────────────────────────────────────
_MEMO_FILE = Path("/home/netforce/US_Data/chart_memos.json")


# ══════════════════════════════════════════════════════════════
# 내부 저장/로드 헬퍼
# ══════════════════════════════════════════════════════════════
def _load_memos() -> dict:
    """JSON 파일에서 메모 딕셔너리 로드. {날짜문자열: 메모내용}"""
    try:
        if _MEMO_FILE.exists():
            return json.loads(_MEMO_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Memo] 로드 오류: {e}")
    return {}


def _save_memos(memos: dict):
    """메모 딕셔너리를 JSON 파일로 저장."""
    try:
        _MEMO_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MEMO_FILE.write_text(
            json.dumps(memos, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[Memo] 저장 오류: {e}")


def _date_key(qdate) -> str:
    """QDate → 'YYYY-MM-DD' 문자열"""
    if isinstance(qdate, QDate):
        return qdate.toString("yyyy-MM-dd")
    return str(qdate)


# ══════════════════════════════════════════════════════════════
# 패널 빌드
# ══════════════════════════════════════════════════════════════
def build_memo_panel(self) -> QWidget:
    """
    메모 패널 QWidget 생성 후 반환.
    self._memo_panel, self._memo_edit, self._memo_date_lbl 등을 self에 설정.
    """
    # 패널 컨테이너
    panel = QWidget()
    panel.setObjectName("MemoPanel")
    panel.setStyleSheet(
        "QWidget#MemoPanel{"
        "  background:#0f0f1f;"
        "  border:1px solid #2a2a5a;"
        "  border-radius:4px;"
        "}"
    )
    vbox = QVBoxLayout(panel)
    vbox.setContentsMargins(6, 4, 6, 6)
    vbox.setSpacing(4)

    # ── 날짜 표시 헤더 ────────────────────────────────────────
    hdr = QHBoxLayout(); hdr.setSpacing(4)
    self._memo_date_lbl = QLabel("📝 날짜를 선택하세요")
    self._memo_date_lbl.setStyleSheet(
        "color:#5dade2; font-weight:bold; font-size:12px;")
    hdr.addWidget(self._memo_date_lbl, 1)
    vbox.addLayout(hdr)

    # ── 구분선 ────────────────────────────────────────────────
    sep = QFrame(); sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet("color:#2a2a5a; margin:0px;")
    vbox.addWidget(sep)

    # ── 텍스트 편집 영역 ──────────────────────────────────────
    self._memo_edit = QTextEdit()
    self._memo_edit.setPlaceholderText(
        "이 날짜에 대한 메모를 입력하세요.\n\n"
        "예) 시장 분위기, 주요 이벤트, 매매 일지 등"
    )
    self._memo_edit.setMinimumHeight(100)
    self._memo_edit.setMaximumHeight(200)
    self._memo_edit.setStyleSheet(
        "QTextEdit{"
        "  background:#131325;"
        "  color:#dde0f0;"
        "  border:1px solid #2a2a5a;"
        "  border-radius:3px;"
        "  font-size:12px;"
        "  padding:4px;"
        "}"
        "QTextEdit:focus{"
        "  border:1px solid #5dade2;"
        "}"
    )
    vbox.addWidget(self._memo_edit)

    # ── 버튼 행 ───────────────────────────────────────────────
    btn_row = QHBoxLayout(); btn_row.setSpacing(4)

    btn_save = QPushButton("💾 저장")
    btn_save.setFixedHeight(26)
    btn_save.setStyleSheet(
        "QPushButton{"
        "  background:#1a3a5a;color:#5dade2;"
        "  border:1px solid #2a5a8a;border-radius:3px;"
        "  font-weight:bold;font-size:11px;}"
        "QPushButton:hover{background:#1e4a7a;color:#7dc7f5;}"
        "QPushButton:pressed{background:#142a4a;}"
    )
    btn_save.setToolTip("현재 날짜에 메모를 저장합니다")
    btn_save.clicked.connect(lambda: _memo_save(self))
    btn_row.addWidget(btn_save)

    btn_del = QPushButton("🗑 삭제")
    btn_del.setFixedHeight(26)
    btn_del.setStyleSheet(
        "QPushButton{"
        "  background:#2a1a1a;color:#e57373;"
        "  border:1px solid #5a2a2a;border-radius:3px;"
        "  font-weight:bold;font-size:11px;}"
        "QPushButton:hover{background:#3a2020;color:#ef9a9a;}"
        "QPushButton:pressed{background:#1a1010;}"
    )
    btn_del.setToolTip("현재 날짜의 메모를 삭제합니다")
    btn_del.clicked.connect(lambda: _memo_delete(self))
    btn_row.addWidget(btn_del)

    btn_clr = QPushButton("✕ 지우기")
    btn_clr.setFixedHeight(26)
    btn_clr.setStyleSheet(
        "QPushButton{"
        "  background:#1a1a2a;color:#888;"
        "  border:1px solid #333;border-radius:3px;"
        "  font-size:11px;}"
        "QPushButton:hover{background:#222238;color:#aaa;}"
    )
    btn_clr.setToolTip("편집 창만 지웁니다 (저장된 메모는 유지)")
    btn_clr.clicked.connect(lambda: self._memo_edit.clear())
    btn_row.addWidget(btn_clr)

    vbox.addLayout(btn_row)

    # ── 상태 라벨 ─────────────────────────────────────────────
    self._memo_status_lbl = QLabel("")
    self._memo_status_lbl.setStyleSheet(
        "color:#4caf50;font-size:10px;padding-left:2px;")
    vbox.addWidget(self._memo_status_lbl)

    # ── 내부 상태 초기화 ──────────────────────────────────────
    self._memo_current_date = None   # 현재 편집 중인 날짜 키
    self._memo_data = _load_memos()  # 전체 메모 딕셔너리

    # 패널은 처음에 숨김 (토글로 열기)
    panel.hide()
    self._memo_panel = panel
    return panel


# ══════════════════════════════════════════════════════════════
# 토글
# ══════════════════════════════════════════════════════════════
def toggle_memo_panel(self):
    """메모 패널 열기/닫기 토글. btn_memo_toggle 버튼 텍스트도 갱신."""
    panel = getattr(self, "_memo_panel", None)
    if panel is None:
        return
    visible = panel.isVisible()
    panel.setVisible(not visible)
    # 버튼 텍스트 갱신
    btn = getattr(self, "btn_memo_toggle", None)
    if btn:
        if visible:   # 지금 막 닫힘
            btn.setText("📝 메모 열기")
            btn.setChecked(False)
        else:          # 지금 막 열림
            btn.setText("📝 메모 닫기")
            btn.setChecked(True)


# ══════════════════════════════════════════════════════════════
# 날짜 변경 → 메모 로드
# ══════════════════════════════════════════════════════════════
def on_memo_date_changed(self, qdate):
    """
    캘린더 날짜 클릭 시 호출.
    해당 날짜의 메모를 _memo_edit에 표시.
    """
    key = _date_key(qdate)
    self._memo_current_date = key

    # 날짜 헤더 갱신
    lbl = getattr(self, "_memo_date_lbl", None)
    if lbl:
        lbl.setText(f"📝 {key}")

    # 메모 내용 로드
    edit = getattr(self, "_memo_edit", None)
    if edit is None:
        return

    memo_text = self._memo_data.get(key, "")
    edit.setPlainText(memo_text)

    # 상태 라벨 갱신
    status = getattr(self, "_memo_status_lbl", None)
    if status:
        if memo_text:
            status.setText(f"✅ 메모 있음 ({len(memo_text)}자)")
            status.setStyleSheet("color:#4caf50;font-size:10px;padding-left:2px;")
        else:
            status.setText("메모 없음")
            status.setStyleSheet("color:#555;font-size:10px;padding-left:2px;")


# ══════════════════════════════════════════════════════════════
# 저장 / 삭제
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
