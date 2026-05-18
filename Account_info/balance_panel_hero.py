"""
balance_panel_hero.py — 히어로 바 패널  v3.0

[v3.0 변경]
  - 미실현 PnL 블록 제거
  - A(좌): 총자산NLV · 실현PnL · 가용증거금 · 유지증거금 지표
  - B(우): 전체 새로고침 · PnL 이력 저장 · 마지막 업데이트
  - 좌/우 QFrame 으로 시각적 분리
"""

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                             QLabel, QPushButton, QFrame)
from PyQt5.QtGui  import QFont
from PyQt5.QtCore import Qt
from Account_info.balance_style import CS


def build_hero(self) -> QWidget:
    """히어로 바 위젯 반환. self 에 위젯 속성 주입."""
    hero = QWidget()
    hero.setMinimumHeight(64)
    hero.setStyleSheet(
        "QWidget{"
        "background:#ffffff;"
        "border:1px solid #d1d9e0;"
        "border-radius:12px;}")
    hl = QHBoxLayout(hero)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(0)

    # ══════════════════════════════════════════════
    # A 영역 (좌) — 핵심 지표 4개
    # ══════════════════════════════════════════════
    panel_a = QWidget()
    panel_a.setStyleSheet(
        "QWidget{"
        "background:#ffffff;"
        "border:none;"
        "border-right:1px solid #e2e8f0;"
        "border-top-left-radius:12px;"
        "border-bottom-left-radius:12px;}")
    hl_a = QHBoxLayout(panel_a)
    hl_a.setContentsMargins(22, 10, 22, 10)
    hl_a.setSpacing(0)

    STATS = [
        ("총자산 NLV",  "lbl_nlv"),
        ("실현 PnL",    "lbl_rpnl"),
        ("가용 증거금", "lbl_bp"),
        ("유지 증거금", "lbl_maint"),
    ]
    for i, (label, attr) in enumerate(STATS):
        if i > 0:
            div = QFrame()
            div.setFrameShape(QFrame.VLine)
            div.setFixedWidth(1)
            div.setFixedHeight(36)
            div.setStyleSheet("border:none;border-left:1px solid #e2e8f0;")
            hl_a.addSpacing(18)
            hl_a.addWidget(div)
            hl_a.addSpacing(18)

        stat_w = QWidget()
        stat_w.setStyleSheet("border:none;")
        stat_w.setMinimumWidth(100)
        sv = QVBoxLayout(stat_w)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(2)
        sv.setAlignment(Qt.AlignCenter)

        lt = QLabel(label)
        lt.setStyleSheet(
            "color:#64748b;font-size:10px;font-weight:700;"
            "letter-spacing:0.5px;border:none;")
        lt.setAlignment(Qt.AlignCenter)

        lv = QLabel("―")
        lv.setMinimumWidth(80)
        lv.setStyleSheet(
            "color:#334155;font-size:14px;font-weight:700;border:none;")
        lv.setAlignment(Qt.AlignCenter)

        sv.addWidget(lt)
        sv.addWidget(lv)
        stat_w._val = lv
        setattr(self, attr, stat_w)
        hl_a.addWidget(stat_w)

    # ══════════════════════════════════════════════
    # B 영역 (우) — 버튼 + 시각
    # ══════════════════════════════════════════════
    panel_b = QWidget()
    panel_b.setStyleSheet(
        "QWidget{"
        "background:#f8fafc;"
        "border:none;"
        "border-top-right-radius:12px;"
        "border-bottom-right-radius:12px;}")
    hl_b = QHBoxLayout(panel_b)
    hl_b.setContentsMargins(18, 10, 18, 10)
    hl_b.setSpacing(8)
    hl_b.addStretch()

    btn_r = QPushButton("↺ 전체 새로고침")
    btn_r.setStyleSheet(CS["btn_blue"])
    btn_r.setFixedHeight(30)
    btn_r.clicked.connect(self._refresh)

    btn_sv = QPushButton("💾 PnL 이력 저장")
    btn_sv.setStyleSheet(CS["btn_gray"])
    btn_sv.setFixedHeight(30)
    btn_sv.clicked.connect(self._save_history)

    self.lbl_time = QLabel("마지막: ―")
    self.lbl_time.setStyleSheet(
        "color:#94a3b8;font-size:11px;font-weight:500;"
        "border:none;margin-left:8px;")

    hl_b.addWidget(btn_r)
    hl_b.addWidget(btn_sv)
    hl_b.addWidget(self.lbl_time)

    # ══════════════════════════════════════════════
    # 조립 — A : B = 3 : 1
    # ══════════════════════════════════════════════
    hl.addWidget(panel_a, stretch=3)
    hl.addWidget(panel_b, stretch=1)

    return hero
