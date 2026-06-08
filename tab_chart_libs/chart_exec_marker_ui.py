"""
chart_exec_marker_ui.py — 체결 마커 UI 패널 (사이드바 삽입용)
────────────────────────────────────────────────────────────────────────────────
호출:
    from chart_exec_marker_ui import build_exec_marker_panel
    side.addWidget(build_exec_marker_panel(self))   # chart_build_side_bottom.py 에서

제공 기능:
  · [체결 로드] 버튼 — DB에서 오늘 날짜 XSP·SPX 체결 로드
  · 날짜 입력 — YYYYMMDD 또는 YYYY-MM-DD 자동 포맷
  · 심볼 필터 콤보 — ALL / XSP / SPX
  · [마커 지우기] 버튼 — 화면·데이터 모두 초기화
  · 상태 라벨 — 로드 건수 / 에러 메시지
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import datetime
import re

try:
    from PyQt5.QtWidgets import (
        QGroupBox, QVBoxLayout, QHBoxLayout,
        QPushButton, QLineEdit, QLabel, QComboBox,
    )
    from PyQt5.QtCore import Qt
    QT = True
except ImportError:
    QT = False


def build_exec_marker_panel(self) -> 'QGroupBox':
    """
    체결 마커 UI 패널을 만들어 반환.
    self 는 tab_chart (ChartGrid) 인스턴스.
    """
    if not QT:
        from PyQt5.QtWidgets import QWidget
        return QWidget()

    grp = QGroupBox("📌 체결 마커")
    v   = QVBoxLayout(grp)
    v.setSpacing(3); v.setContentsMargins(4, 6, 4, 4)

    # ── 날짜 + 심볼 필터 행 ──────────────────────────────────
    row1 = QHBoxLayout(); row1.setSpacing(3)

    self.exec_date_in = QLineEdit()
    self.exec_date_in.setPlaceholderText("YYYYMMDD (오늘)")
    self.exec_date_in.setFixedHeight(22)
    self.exec_date_in.setFixedWidth(100)
    self.exec_date_in.setToolTip(
        "날짜 입력 (비우면 오늘)\n"
        "형식: 20260501 또는 2026-05-01"
    )

    self.exec_sym_combo = QComboBox()
    self.exec_sym_combo.addItems(["ALL", "XSP", "SPX", "SPY"])
    self.exec_sym_combo.setFixedHeight(22)
    self.exec_sym_combo.setFixedWidth(62)
    self.exec_sym_combo.setToolTip(
        "ALL: 심볼 무관 전체 조회\n"
        "특정 종목만 보려면 선택\n"
        "차트 심볼과 달라도 시간 기준으로 마커 표시"
    )

    row1.addWidget(QLabel("날짜:")); row1.addWidget(self.exec_date_in)
    row1.addWidget(QLabel("종목:")); row1.addWidget(self.exec_sym_combo)
    v.addLayout(row1)

    # ── 버튼 행 ────────────────────────────────────────────────
    row2 = QHBoxLayout(); row2.setSpacing(3)

    btn_load = QPushButton("📥 체결 로드")
    btn_load.setFixedHeight(24)
    btn_load.setToolTip("DB에서 체결 이력을 불러와 차트에 마커로 표시")
    btn_load.setStyleSheet(
        "QPushButton{background:#1a3a1a;color:#00e676;border:1px solid #00e676;"
        "border-radius:3px;font-size:11px;}"
        "QPushButton:hover{background:#2a4a2a;}"
    )
    btn_load.clicked.connect(lambda: _on_load(self))

    btn_clear = QPushButton("🗑 지우기")
    btn_clear.setFixedHeight(24)
    btn_clear.setToolTip("체결 마커 전체 제거 (데이터도 초기화)")
    btn_clear.setStyleSheet(
        "QPushButton{background:#2a1a1a;color:#ff6d6d;border:1px solid #ff4444;"
        "border-radius:3px;font-size:11px;}"
        "QPushButton:hover{background:#3a2a2a;}"
    )
    btn_clear.clicked.connect(lambda: _on_clear(self))

    row2.addWidget(btn_load); row2.addWidget(btn_clear)
    v.addLayout(row2)

    # ── 환산 안내 라벨 ─────────────────────────────────────────
    lbl_hint = QLabel("심볼 무관 · 시간 기준 마커 · KST 자동 변환")
    lbl_hint.setStyleSheet("color:#888;font-size:10px;")
    lbl_hint.setAlignment(Qt.AlignCenter)
    v.addWidget(lbl_hint)

    # ── 상태 라벨 ──────────────────────────────────────────────
    self.exec_status_lbl = QLabel("대기")
    self.exec_status_lbl.setStyleSheet(
        "color:#aaa;font-size:10px;border:1px solid #333;"
        "padding:2px 4px;border-radius:3px;"
    )
    self.exec_status_lbl.setAlignment(Qt.AlignCenter)
    self.exec_status_lbl.setWordWrap(True)
    v.addWidget(self.exec_status_lbl)

    return grp


# ── 내부 핸들러 ───────────────────────────────────────────────────────────────

def _parse_date(txt: str) -> str:
    """
    사용자 입력 날짜 → 'YYYY-MM-DD' 반환.
    빈 문자열 → 오늘 날짜.
    """
    txt = txt.strip().replace('/', '-')
    if not txt:
        return datetime.now().strftime('%Y-%m-%d')
    # 이미 YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', txt):
        return txt
    # YYYYMMDD → YYYY-MM-DD
    if re.match(r'^\d{8}$', txt):
        return f"{txt[:4]}-{txt[4:6]}-{txt[6:]}"
    # 기타: 오늘 반환
    return datetime.now().strftime('%Y-%m-%d')


def _on_load(self):
    """[체결 로드] 버튼 핸들러."""
    try:
        from chart_exec_marker import load_exec_markers_from_db, convert_exec_price
    except ImportError as e:
        _set_status(self, f"⚠ import 실패: {e}", error=True)
        return

    date_str    = _parse_date(getattr(self, 'exec_date_in',
                                      type('', (), {'text': lambda: ''})()).text()
                              if hasattr(self, 'exec_date_in') else '')
    combo_val   = (self.exec_sym_combo.currentText()
                   if hasattr(self, 'exec_sym_combo') else 'ALL')
    filter_sym  = None if combo_val == 'ALL' else combo_val

    _set_status(self, f"로딩 중… {date_str}", error=False)

    try:
        load_exec_markers_from_db(self,
                                  date_str=date_str,
                                  filter_symbol=filter_sym)
        cnt = len(getattr(self, '_exec_markers', []))
        if cnt:
            _set_status(self,
                        f"✅ {cnt}건 표시 ({date_str})", error=False)
        else:
            _set_status(self,
                        f"ℹ {date_str} 체결 없음", error=False)
    except Exception as e:
        _set_status(self, f"⚠ {e}", error=True)


def _on_clear(self):
    """[지우기] 버튼 핸들러."""
    try:
        from chart_exec_marker import clear_exec_markers
        self._exec_markers = []
        clear_exec_markers(self)
        _set_status(self, "마커 초기화 완료", error=False)
    except Exception as e:
        _set_status(self, f"⚠ {e}", error=True)


def _set_status(self, msg: str, error: bool = False):
    if hasattr(self, 'exec_status_lbl'):
        color = '#ff6d6d' if error else '#aaa'
        self.exec_status_lbl.setStyleSheet(
            f"color:{color};font-size:10px;border:1px solid #333;"
            "padding:2px 4px;border-radius:3px;"
        )
        self.exec_status_lbl.setText(msg)
