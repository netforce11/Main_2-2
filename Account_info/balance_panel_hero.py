"""
balance_panel_hero.py — 히어로 바 패널  v2.0
[0,0-11] 미실현 PnL · 핵심 지표 4개 · 새로고침 버튼 · 마지막 업데이트

설정하는 self 속성:
    lbl_pnl, lbl_nlv, lbl_rpnl, lbl_bp, lbl_maint, lbl_time
"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtGui     import QFont
from PyQt5.QtCore    import Qt
from Account_info.balance_style import CS


def build_hero(self) -> QWidget:
    """히어로 바 위젯 반환. self 에 위젯 속성 주입."""

    hero = QWidget()
    hero.setMinimumHeight(72)       # 잘림 방지 최소 높이
    hero.setStyleSheet(
        "QWidget{"
        "background:#ffffff;"
        "border:1px solid #d1d9e0;"
        "border-radius:12px;}")
    hl = QHBoxLayout(hero)
    hl.setContentsMargins(22, 12, 22, 12)
    hl.setSpacing(0)

    # ── 미실현 PnL 블록 ──────────────────────────────────
    pnl_block = QWidget(); pnl_block.setStyleSheet("border:none;")
    pb = QVBoxLayout(pnl_block)
    pb.setContentsMargins(0, 0, 0, 0); pb.setSpacing(3)

    lbl_title = QLabel("미실현 PnL")
    lbl_title.setStyleSheet(
        "color:#64748b;font-size:11px;font-weight:700;"
        "letter-spacing:0.5px;border:none;")

    self.lbl_pnl = QLabel("― ―")
    self.lbl_pnl.setFont(QFont("Arial", 20, QFont.Bold))
    self.lbl_pnl.setMinimumWidth(160)
    self.lbl_pnl.setStyleSheet("color:#94a3b8;border:none;font-weight:700;")

    pb.addWidget(lbl_title)
    pb.addWidget(self.lbl_pnl)
    hl.addWidget(pnl_block)

    # ── 구분선 + 지표 4개 ────────────────────────────────
    STATS = [
        ("총자산 NLV",  "lbl_nlv"),
        ("실현 PnL",    "lbl_rpnl"),
        ("가용 증거금", "lbl_bp"),
        ("유지 증거금", "lbl_maint"),
    ]
    for label, attr in STATS:
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFixedWidth(1); div.setFixedHeight(40)
        div.setStyleSheet("border:none;border-left:1px solid #e2e8f0;")
        hl.addSpacing(20); hl.addWidget(div); hl.addSpacing(20)

        stat_w = QWidget(); stat_w.setStyleSheet("border:none;")
        stat_w.setMinimumWidth(90)   # 값 라벨 잘림 방지
        sv = QVBoxLayout(stat_w)
        sv.setContentsMargins(0, 0, 0, 0); sv.setSpacing(3)
        sv.setAlignment(Qt.AlignCenter)

        lt = QLabel(label)
        lt.setStyleSheet(
            "color:#64748b;font-size:10px;font-weight:700;"
            "letter-spacing:0.5px;border:none;")
        lt.setAlignment(Qt.AlignCenter)

        lv = QLabel("―")
        lv.setMinimumWidth(80)       # 값 잘림 방지
        lv.setStyleSheet(
            "color:#334155;font-size:14px;font-weight:700;border:none;")
        lv.setAlignment(Qt.AlignCenter)

        sv.addWidget(lt); sv.addWidget(lv)
        stat_w._val = lv          # 기존 ._val 패턴 유지
        setattr(self, attr, stat_w)
        hl.addWidget(stat_w)

    hl.addStretch()

    # ── 버튼 ─────────────────────────────────────────────
    btn_r = QPushButton("↺ 전체 새로고침")
    btn_r.setStyleSheet(CS["btn_blue"])
    btn_r.clicked.connect(self._refresh)

    btn_sv = QPushButton("💾 PnL 이력 저장")
    btn_sv.setStyleSheet(CS["btn_gray"])
    btn_sv.clicked.connect(self._save_history)

    hl.addSpacing(8); hl.addWidget(btn_r)
    hl.addSpacing(6); hl.addWidget(btn_sv)

    # ── 마지막 업데이트 ──────────────────────────────────
    self.lbl_time = QLabel("마지막 업데이트: ―")
    self.lbl_time.setStyleSheet(
        "color:#94a3b8;font-size:11px;font-weight:500;border:none;margin-left:14px;")
    hl.addWidget(self.lbl_time)

    return hero