"""
balance_panel_top.py — 상단 3패널  v2.0
[1,0-3] 계좌 요약  /  [1,4-7] 주요 지표  /  [1,8-11] 현재 포지션

설정하는 self 속성:
    tbl_acct, tbl_pos
    lbl_nlv._val, lbl_bp._val, lbl_rpnl._val  (히어로 바와 공유)
"""

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
)
from PyQt5.QtCore    import Qt
from core            import make_table
from Account_info.balance_style import CS


def build_acct_panel(self) -> QGroupBox:
    """[1,0-3] 계좌 요약 테이블."""
    gb = QGroupBox("계좌 요약")
    gb.setStyleSheet(CS["card"])
    v = QVBoxLayout(gb)
    self.tbl_acct = make_table(["항목", "값", "통화"], 0)
    self.tbl_acct.setStyleSheet(CS["tbl"])
    self.tbl_acct.setAlternatingRowColors(True)
    self.tbl_acct.setRowCount(0)
    v.addWidget(self.tbl_acct)
    return gb


def build_kpi_panel(self) -> QGroupBox:
    """[1,4-7] 주요 지표 — 히어로 바의 ._val 에 lbl_v 를 연결."""
    gb = QGroupBox("주요 지표")
    gb.setStyleSheet(CS["card"])
    v = QVBoxLayout(gb); v.setSpacing(7)

    KPI = [
        ("총자산 (NLV)",    "lbl_nlv"),
        ("사용가능 증거금", "lbl_bp"),
        ("실현 PnL",        "lbl_rpnl"),
    ]
    for label, attr in KPI:
        row = QWidget()
        row.setMinimumHeight(44)     # 행 높이 확보 (텍스트 잘림 방지)
        row.setStyleSheet(
            "background:#f1f5f9;border-radius:8px;border:none;")
        rh = QHBoxLayout(row); rh.setContentsMargins(14, 8, 14, 8)

        lbl_k = QLabel(label)
        lbl_k.setStyleSheet(
            "color:#475569;font-size:11px;font-weight:600;border:none;")

        lbl_v = QLabel("―")
        lbl_v.setMinimumWidth(70)    # 숫자 잘림 방지
        lbl_v.setStyleSheet(
            "color:#1e293b;font-size:14px;font-weight:700;border:none;")
        lbl_v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        rh.addWidget(lbl_k); rh.addStretch(); rh.addWidget(lbl_v)

        # 히어로 바에서 생성된 stat_w 의 ._val 을 교체 → 같은 라벨 공유
        getattr(self, attr)._val = lbl_v
        v.addWidget(row)
    return gb


def build_position_panel(self) -> QGroupBox:
    """[1,8-11] 현재 포지션 테이블."""
    gb = QGroupBox("현재 포지션")
    gb.setStyleSheet(CS["card"])
    v = QVBoxLayout(gb)
    self.tbl_pos = make_table(["계좌", "심볼", "종류", "수량", "평균단가"], 0)
    self.tbl_pos.setStyleSheet(CS["tbl"])
    self.tbl_pos.setAlternatingRowColors(True)
    self.tbl_pos.setRowCount(0)
    v.addWidget(self.tbl_pos)
    return gb