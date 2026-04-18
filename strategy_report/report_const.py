"""
report_const.py — 상수 / DB 초기화 / 헬퍼 위젯
════════════════════════════════════════════════
위치: IBKR/MAIN2/STRATEGY_REPORT/report_const.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QToolButton, QLabel, QFrame
from PyQt5.QtCore import Qt

# ══════════════════════════════════════════════════════════════
# 경로 상수
# ══════════════════════════════════════════════════════════════
REPORT_DIR = Path(r"C:\data\Report_save")
CHART_DIR  = REPORT_DIR / "charts"
DB_PATH    = REPORT_DIR / "reports.db"

# ══════════════════════════════════════════════════════════════
# 폰트 크기 기준 (+3 적용 — 기본 10pt 기준 → 13pt)
# ══════════════════════════════════════════════════════════════
FS_BODY    = "16px"   # 일반 본문 (기존 13px → +3)
FS_SMALL   = "14px"   # 보조/힌트 (기존 11px → +3)
FS_SECTION = "16px"   # 섹션 헤더 (기존 13px → +3)
FS_TITLE   = "17px"   # 타이틀 (기존 14px → +3)
FS_HINT    = "15px"   # 전략 힌트 (기존 12px → +3)
FS_LIST    = "14px"   # 리스트 아이템 (기존 11px → +3)

# ══════════════════════════════════════════════════════════════
# 전략 목록 + 자동 힌트
# ══════════════════════════════════════════════════════════════
STRATEGY_LIST = [
    ("call_spread",  "콜 스프레드"),
    ("put_spread",   "풋 스프레드"),
    ("naked_call",   "네이키드 콜"),
    ("naked_put",    "네이키드 풋"),
    ("leaps",        "LEAPS 옵션"),
    ("iron_condor",  "아이언 콘도르"),
    ("straddle",     "스트래들"),
    ("strangle",     "스트랭글"),
    ("etf",          "ETF"),
    ("stock",        "주식"),
]

STRATEGY_HINTS = {
    "call_spread":  "최대손실 = 스프레드 폭 − 수취 프리미엄\n"
                    "만기 SPX > 숏 행사가 → 최대손실 구간",
    "put_spread":   "최대손실 = 스프레드 폭 − 수취 프리미엄\n"
                    "만기 SPX < 숏 행사가 → 최대손실 구간",
    "naked_call":   "⚠ 무제한 손실 위험\n"
                    "마진 요구 높음 — 계좌 여유 확인 필수",
    "naked_put":    "최대손실 = 행사가 − 수취 프리미엄\n"
                    "SPX 급락 시 대규모 손실 가능",
    "leaps":        "Theta 영향 적으나 초기 프리미엄 부담 큼\n"
                    "Vega 민감도 높음 — IV 변화 주시",
    "iron_condor":  "최대손실 = Max(콜/풋 스프레드폭) − 수취 프리미엄\n"
                    "양쪽 wing 동시 돌파 시 위험",
    "straddle":     "ATM 매수 — 큰 방향성 움직임 필요\n"
                    "Theta 손실 빠름 — 이벤트 직후 진입 주의",
    "strangle":     "OTM 매수 — 비용 낮으나 더 큰 움직임 필요\n"
                    "만기 가까울수록 Theta 급속 증가",
    "etf":          "섹터/지수 분산 효과\n배당 일정 확인",
    "stock":        "개별 종목 리스크 — 실적/이벤트 일정 확인\n"
                    "옵션 헤지 병행 여부 기록",
}

# ══════════════════════════════════════════════════════════════
# 이벤트 태그 목록
# ══════════════════════════════════════════════════════════════
EVENT_TAGS = [
    "", "FOMC", "CPI", "PPI", "NFP", "OPEX", "QE", "GDP",
    "지정학", "기술적", "변동성 급등", "기타",
]

# ══════════════════════════════════════════════════════════════
# DB 초기화
# ══════════════════════════════════════════════════════════════
def init_db() -> sqlite3.Connection:
    """DB와 디렉토리를 생성하고 연결 반환."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT    NOT NULL,
            title          TEXT    DEFAULT '',
            importance     INTEGER DEFAULT 3,
            spx_price      REAL    DEFAULT 0.0,
            vix_level      REAL    DEFAULT 0.0,
            event_tag      TEXT    DEFAULT '',
            event_analysis TEXT    DEFAULT '',
            strategies     TEXT    DEFAULT '[]',
            product_detail TEXT    DEFAULT '',
            difficult_zone TEXT    DEFAULT '',
            response_plan  TEXT    DEFAULT '',
            chart_path     TEXT    DEFAULT '',
            memo           TEXT    DEFAULT '',
            created_at     TEXT    DEFAULT ''
        )
    """)
    conn.commit()
    return conn

# ══════════════════════════════════════════════════════════════
# 헬퍼 UI 함수
# ══════════════════════════════════════════════════════════════
def hline() -> QFrame:
    """수평 구분선."""
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    f.setStyleSheet("color:#555;")
    return f


def section_label(text: str) -> QLabel:
    """섹션 헤더 레이블."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-weight:bold;font-size:{FS_SECTION};"
        f"color:#ddd;padding:4px 0 2px 0;"
    )
    return lbl


# ══════════════════════════════════════════════════════════════
# 별점 위젯
# ══════════════════════════════════════════════════════════════
class StarWidget(QWidget):
    """1~5 별점 선택 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 3
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._btns: list[QToolButton] = []
        for i in range(1, 6):
            btn = QToolButton()
            btn.setText("★")
            btn.setFixedSize(30, 30)
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QToolButton{{border:none;font-size:19px;color:#ccc;}}"
                f"QToolButton:checked{{color:#f5a623;}}"
            )
            btn.clicked.connect(lambda _, v=i: self._set(v))
            layout.addWidget(btn)
            self._btns.append(btn)
        self._refresh()

    def _set(self, v: int):
        self._value = v
        self._refresh()

    def _refresh(self):
        for i, btn in enumerate(self._btns):
            btn.setChecked(i < self._value)

    def value(self) -> int:
        return self._value

    def setValue(self, v: int):
        self._value = max(1, min(5, v))
        self._refresh()
