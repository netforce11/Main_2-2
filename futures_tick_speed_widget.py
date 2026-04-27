# futures_tick_speed_widget.py — 선물 틱 속도 모니터 위젯  [신규]
# ════════════════════════════════════════════════════════════════
# 위치: chart_panel_tabs.py 의 _build_tick_tab() 내부,
#        ▶ 조회 버튼 아래 두 번째 행에 삽입
#
# 연결 (tab_options_chart.py 의 _apply_tick_price() 에 한 줄 추가):
#   self.futures_tick_speed.update_tick(price)
#
# 호가 변화 연결 (bid/ask 처리 후):
#   self.futures_tick_speed.update_quote(bid, ask)
# ════════════════════════════════════════════════════════════════

from __future__ import annotations
from collections import deque

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QSpinBox, QFrame,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

import time


_BOLD = QFont()
_BOLD.setBold(True)

_SS_NORMAL = "color:#e0e0e0;"
_SS_WARN   = "color:#ff4444;font-weight:bold;"
_SS_HEADER = "color:#aaaaaa;font-size:11px;"
_SS_WAIT   = "color:#666666;font-size:11px;"


class FuturesTickSpeedWidget(QWidget):
    """
    선물틱속도 모니터 위젯
    표시: ⚡선물틱속도 | 기준:__틱 | 10s: N틱 | 호가변화: M | 30s: N틱 | 호가변화: M
    알람: 기준 > 0 이고 현재틱 < 기준이면 적색 강조 + ⚠ 경고 텍스트
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ticks: deque[float]         = deque()   # 틱 수신 timestamp
        self._quote_changes: deque[float] = deque()   # 호가 변화 timestamp
        self._last_bid: float | None = None
        self._last_ask: float | None = None
        self._waiting = True   # 첫 틱 수신 전 대기 상태

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1_000)

    # ── UI 구성 ──────────────────────────────────────────────────
    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        # ⚡ 헤더 — 틱탭 어디에 있는지 바로 확인
        hdr = QLabel("⚡선물틱속도")
        hdr.setStyleSheet(_SS_HEADER)
        lay.addWidget(hdr)
        lay.addWidget(self._vsep())

        # 기준값 SpinBox
        lay.addWidget(QLabel("기준:"))
        self.spin_base = QSpinBox()
        self.spin_base.setRange(0, 999)
        self.spin_base.setValue(0)
        self.spin_base.setFixedWidth(52)
        self.spin_base.setToolTip("기준 틱 수 (0 = 알람 비활성)")
        lay.addWidget(self.spin_base)
        lay.addWidget(QLabel("틱"))
        lay.addWidget(self._vsep())

        # 10초 틱 수
        lay.addWidget(QLabel("10s:"))
        self.lbl_10s = QLabel("0")          # 초기값 "0" (바로 렌더 확인 가능)
        self.lbl_10s.setFont(_BOLD)
        self.lbl_10s.setStyleSheet(_SS_NORMAL)
        lay.addWidget(self.lbl_10s)
        lay.addWidget(QLabel("틱"))
        lay.addWidget(self._vsep())

        # 10초 호가변화
        lay.addWidget(QLabel("호가변화:"))
        self.lbl_q10 = QLabel("0")
        self.lbl_q10.setStyleSheet(_SS_NORMAL)
        lay.addWidget(self.lbl_q10)
        lay.addWidget(self._vsep())

        # 30초 틱 수
        lay.addWidget(QLabel("30s:"))
        self.lbl_30s = QLabel("0")
        self.lbl_30s.setFont(_BOLD)
        self.lbl_30s.setStyleSheet(_SS_NORMAL)
        lay.addWidget(self.lbl_30s)
        lay.addWidget(QLabel("틱"))
        lay.addWidget(self._vsep())

        # 30초 호가변화
        lay.addWidget(QLabel("호가변화:"))
        self.lbl_q30 = QLabel("0")
        self.lbl_q30.setStyleSheet(_SS_NORMAL)
        lay.addWidget(self.lbl_q30)
        lay.addWidget(self._vsep())

        # 알람 라벨
        self.lbl_alarm = QLabel("")
        self.lbl_alarm.setStyleSheet(_SS_WARN)
        lay.addWidget(self.lbl_alarm)

        # 틱수신대기 안내 라벨 (첫 틱 수신 시 자동으로 사라짐)
        self.lbl_wait = QLabel("※ 틱수신대기 — update_tick(price) 연결필요")
        self.lbl_wait.setStyleSheet(_SS_WAIT)
        lay.addWidget(self.lbl_wait)

        lay.addStretch()

    @staticmethod
    def _vsep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.VLine)
        f.setStyleSheet("color:#333;")
        return f

    # ── 외부 호출 API ─────────────────────────────────────────────
    def update_tick(self, price: float):
        """틱 수신 — tab_options_chart._apply_tick_price() 에서 호출."""
        self._ticks.append(time.monotonic())
        if self._waiting:
            self._waiting = False
            self.lbl_wait.hide()   # 첫 틱 수신 시 안내 라벨 자동 제거

    def update_quote(self, bid: float, ask: float):
        """호가 변화 — bid/ask 가 달라질 때마다 호출."""
        if bid != self._last_bid or ask != self._last_ask:
            self._last_bid, self._last_ask = bid, ask
            self._quote_changes.append(time.monotonic())

    # ── 1초 주기 갱신 ─────────────────────────────────────────────
    def _refresh(self):
        now     = time.monotonic()
        cut10   = now - 10
        cut30   = now - 30

        # 오래된 항목 제거
        while self._ticks         and self._ticks[0]         < cut30: self._ticks.popleft()
        while self._quote_changes and self._quote_changes[0] < cut30: self._quote_changes.popleft()

        t10 = sum(1 for t in self._ticks         if t >= cut10)
        t30 = len(self._ticks)
        q10 = sum(1 for t in self._quote_changes if t >= cut10)
        q30 = len(self._quote_changes)

        self.lbl_10s.setText(str(t10))
        self.lbl_30s.setText(str(t30))
        self.lbl_q10.setText(str(q10))
        self.lbl_q30.setText(str(q30))

        base = self.spin_base.value()
        if base > 0 and not self._waiting:
            warn10 = t10 < base
            warn30 = t30 < base
            if warn10 or warn30:
                parts = []
                if warn10: parts.append(f"{t10}(10s)")
                if warn30: parts.append(f"{t30}(30s)")
                self.lbl_alarm.setText(f"⚠ 기준{base}틱 > 현재{'/ '.join(parts)}")
                self.lbl_10s.setStyleSheet(_SS_WARN if warn10 else _SS_NORMAL)
                self.lbl_30s.setStyleSheet(_SS_WARN if warn30 else _SS_NORMAL)
            else:
                self.lbl_alarm.setText("")
                self.lbl_10s.setStyleSheet(_SS_NORMAL)
                self.lbl_30s.setStyleSheet(_SS_NORMAL)
        else:
            self.lbl_alarm.setText("")
            self.lbl_10s.setStyleSheet(_SS_NORMAL)
            self.lbl_30s.setStyleSheet(_SS_NORMAL)