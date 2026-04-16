"""
watch_alert_tab.py — SPX 알람 탭 UI  v1.0
════════════════════════════════════════════════════
역할:
  WatchAlertTabMixin 을 WatchCondMixin 과 함께 CallPutGrid에 mixin.
  _build_watch_widget() 에서 탭 하나만 추가:
      self._watch_tabs.addTab(self._build_alert_tab(), "🚨 SPX 알람")

  연동:
    - AlertEngine.push_spx()  ← watch_logic.py 의 und_price 수신부에서 호출
    - AlertLogger             ← 일별 .log 파일 기록
    - QTimer(1분)             ← 상태 라벨 갱신

  외부 데이터 수신부는 건드리지 않음.
  und_price 가 들어오는 기존 콜백 끝에 아래 한 줄만 추가하면 됨:
      if hasattr(self, '_alert_engine') and self._alert_engine.is_running:
          self._alert_engine.push_spx(price)

Python 3.8 호환
════════════════════════════════════════════════════
"""

from __future__ import annotations
import os
import subprocess
import sys
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QGroupBox, QRadioButton, QButtonGroup,
    QTextEdit, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from call_put_tab.alert_engine import AlertEngine
from call_put_tab.alert_logger import AlertLogger


# ── 공통 스타일 상수 ──────────────────────────────────────────
_FS   = 15          # 기본 폰트 크기 (크게)
_FS_S = "font-size:15px;"
_LBL  = f"color:#aaa;{_FS_S}border:none;"
_VAL  = f"color:#ffd700;font-weight:bold;{_FS_S}border:none;"
_GB   = (
    f"QGroupBox{{font-size:14px;color:#90caf9;font-weight:bold;"
    "border:1px solid #3a3a6a;border-radius:4px;"
    "margin-top:8px;padding-top:12px;}}"
    "QGroupBox::title{subcontrol-origin:margin;left:8px;top:0px;}"
)
_SPIN = (
    f"QDoubleSpinBox,QSpinBox{{background:#0a0a1e;color:#ffd700;"
    f"border:1px solid #4a4a7a;border-radius:3px;{_FS_S}padding:2px 4px;}}"
)


class WatchAlertTabMixin:
    """
    SPX 알람 탭 UI + AlertEngine 제어.
    CallPutGrid 에 WatchCondMixin 과 함께 mixin.
    """

    # ════════════════════════════════════════════════════════
    # 탭 빌드
    # ════════════════════════════════════════════════════════

    def _build_alert_tab(self) -> QWidget:
        """🚨 SPX 알람 탭 전체 위젯."""
        self._alert_logger: AlertLogger = AlertLogger()
        self._alert_engine: Optional[AlertEngine] = None

        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(6)
        v.setContentsMargins(8, 8, 8, 8)

        v.addWidget(self._build_cond_group())   # 조건 A/B/C 설정
        v.addWidget(self._build_level_group())  # 알람 레벨
        v.addLayout(self._build_ctrl_row())     # 시작/중지 버튼
        v.addWidget(self._build_status_box())   # 상태 + 인라인 로그
        v.addStretch()

        # 1분 타이머: 상태 라벨 자동 갱신
        self._alert_status_timer = QTimer()
        self._alert_status_timer.setInterval(60_000)
        self._alert_status_timer.timeout.connect(self._refresh_alert_status)

        return w

    # ── 조건 설정 GroupBox ────────────────────────────────────

    def _build_cond_group(self) -> QGroupBox:
        gb = QGroupBox("감시 조건 설정")
        gb.setStyleSheet(_GB)
        gl = QGridLayout(gb)
        gl.setSpacing(8)
        gl.setContentsMargins(10, 14, 10, 10)

        def lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(_LBL)
            return l

        # 조건 A
        gl.addWidget(lbl("조건 A  SPX"), 0, 0)
        self._asp_window = QSpinBox()
        self._asp_window.setRange(1, 60)
        self._asp_window.setValue(20)
        self._asp_window.setSuffix(" 분 전 대비")
        self._asp_window.setStyleSheet(_SPIN)
        self._asp_window.setFixedHeight(30)
        gl.addWidget(self._asp_window, 0, 1)

        self._asp_drop = QDoubleSpinBox()
        self._asp_drop.setRange(1.0, 100.0)
        self._asp_drop.setValue(15.0)
        self._asp_drop.setSuffix(" P 이상 하락")
        self._asp_drop.setStyleSheet(_SPIN)
        self._asp_drop.setFixedHeight(30)
        gl.addWidget(self._asp_drop, 0, 2)

        # 조건 B
        gl.addWidget(lbl("조건 B  풋옵션"), 1, 0)
        self._asp_opt = QDoubleSpinBox()
        self._asp_opt.setRange(50.0, 2000.0)
        self._asp_opt.setValue(200.0)
        self._asp_opt.setSingleStep(50.0)
        self._asp_opt.setSuffix(" % 이상 급등")
        self._asp_opt.setStyleSheet(_SPIN)
        self._asp_opt.setFixedHeight(30)
        gl.addWidget(self._asp_opt, 1, 1, 1, 2)

        # 조건 C
        gl.addWidget(lbl("조건 C  VIX"), 2, 0)
        self._asp_vix = QDoubleSpinBox()
        self._asp_vix.setRange(0.5, 30.0)
        self._asp_vix.setValue(3.0)
        self._asp_vix.setSingleStep(0.5)
        self._asp_vix.setSuffix(" % 이상 급등")
        self._asp_vix.setStyleSheet(_SPIN)
        self._asp_vix.setFixedHeight(30)
        gl.addWidget(self._asp_vix, 2, 1, 1, 2)

        gl.setColumnStretch(2, 1)
        return gb

    # ── 알람 레벨 GroupBox ────────────────────────────────────

    def _build_level_group(self) -> QGroupBox:
        gb = QGroupBox("알람 레벨  (조건 충족 최소 기준)")
        gb.setStyleSheet(_GB)
        h = QHBoxLayout(gb)
        h.setSpacing(16)
        h.setContentsMargins(10, 14, 10, 10)

        _radio_s = f"color:#ffd700;{_FS_S}font-weight:bold;"
        self._asp_level_grp = QButtonGroup(gb)

        for idx, (label, tip) in enumerate([
            ("LV1  (A만)",    "지수 낙폭만 감지"),
            ("LV2  (A+B)",   "지수 + 옵션 급등"),
            ("LV3  (A+B+C)", "지수 + 옵션 + VIX"),
        ]):
            rb = QRadioButton(label)
            rb.setStyleSheet(_radio_s)
            rb.setToolTip(tip)
            self._asp_level_grp.addButton(rb, idx + 1)
            h.addWidget(rb)

        # 기본: LV1
        self._asp_level_grp.button(1).setChecked(True)
        h.addStretch()
        return gb

    # ── 시작/중지 버튼 행 ─────────────────────────────────────

    def _build_ctrl_row(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(8)

        self._btn_alert_start = QPushButton("▶  감시 시작")
        self._btn_alert_start.setFixedHeight(36)
        self._btn_alert_start.setStyleSheet(
            f"background:#1a5c2e;color:#00ff88;font-weight:bold;{_FS_S}"
            "border-radius:4px;")
        self._btn_alert_start.clicked.connect(self._on_alert_start)

        self._btn_alert_stop = QPushButton("■  중지")
        self._btn_alert_stop.setFixedHeight(36)
        self._btn_alert_stop.setEnabled(False)
        self._btn_alert_stop.setStyleSheet(
            f"background:#5a1a1a;color:#ff6666;font-weight:bold;{_FS_S}"
            "border-radius:4px;")
        self._btn_alert_stop.clicked.connect(self._on_alert_stop)

        self._btn_open_log = QPushButton("📂  로그 파일 열기")
        self._btn_open_log.setFixedHeight(36)
        self._btn_open_log.setStyleSheet(
            f"background:#1a2a4a;color:#90caf9;font-weight:bold;{_FS_S}"
            "border-radius:4px;")
        self._btn_open_log.clicked.connect(self._on_open_log)

        h.addWidget(self._btn_alert_start)
        h.addWidget(self._btn_alert_stop)
        h.addWidget(self._btn_open_log)
        return h

    # ── 상태 + 인라인 로그 박스 ──────────────────────────────

    def _build_status_box(self) -> QWidget:
        gb = QGroupBox("상태 / 최근 알람")
        gb.setStyleSheet(_GB)
        v = QVBoxLayout(gb)
        v.setContentsMargins(8, 14, 8, 8)
        v.setSpacing(4)

        self._alert_status_lbl = QLabel("● 대기 중")
        self._alert_status_lbl.setStyleSheet(
            f"color:#555;{_FS_S}font-weight:bold;border:none;")
        v.addWidget(self._alert_status_lbl)

        self._alert_log_box = QTextEdit()
        self._alert_log_box.setReadOnly(True)
        self._alert_log_box.setFixedHeight(120)
        self._alert_log_box.setStyleSheet(
            f"background:#07070f;color:#00e676;{_FS_S}"
            "border:1px solid #2a2a5a;border-radius:3px;")
        self._alert_log_box.setFont(QFont("Consolas", _FS - 1))
        v.addWidget(self._alert_log_box)

        return gb

    # ════════════════════════════════════════════════════════
    # 버튼 핸들러
    # ════════════════════════════════════════════════════════

    def _on_alert_start(self) -> None:
        cfg = {
            "window_min": self._asp_window.value(),
            "drop_pt":    self._asp_drop.value(),
            "opt_pct":    self._asp_opt.value(),
            "vix_pct":    self._asp_vix.value(),
            "min_level":  self._asp_level_grp.checkedId(),
        }
        self._alert_engine = AlertEngine(
            cfg, self._alert_logger, on_alert=self._on_alert_fired
        )
        self._alert_engine.start()
        self._alert_logger.write_info(
            f"감시 시작 — 조건: A({cfg['drop_pt']}P/{cfg['window_min']}분) "
            f"B({cfg['opt_pct']}%) C({cfg['vix_pct']}%) LV{cfg['min_level']}"
        )

        self._btn_alert_start.setEnabled(False)
        self._btn_alert_stop.setEnabled(True)
        self._alert_status_lbl.setStyleSheet(
            f"color:#00e676;{_FS_S}font-weight:bold;border:none;")
        self._alert_status_lbl.setText("● 감시 중")
        self._alert_status_timer.start()

    def _on_alert_stop(self) -> None:
        if self._alert_engine:
            self._alert_engine.stop()
            self._alert_logger.write_info("감시 중지")
        self._alert_status_timer.stop()
        self._btn_alert_start.setEnabled(True)
        self._btn_alert_stop.setEnabled(False)
        self._alert_status_lbl.setStyleSheet(
            f"color:#555;{_FS_S}font-weight:bold;border:none;")
        self._alert_status_lbl.setText("● 중지")

    def _on_open_log(self) -> None:
        """오늘 로그 파일을 OS 기본 뷰어(메모장 등)로 열기."""
        path = self._alert_logger.today_path()
        if not os.path.exists(path):
            self._alert_logger.write_info("(로그 파일 첫 생성)")
        try:
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            self._alert_log_box.append(f"[오류] 파일 열기 실패: {e}")

    # ════════════════════════════════════════════════════════
    # 콜백 / 갱신
    # ════════════════════════════════════════════════════════

    def _on_alert_fired(self, level: str, msg: str) -> None:
        """AlertEngine 이 조건 충족 시 호출 → 인라인 로그에 추가."""
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} [{level}] {msg}"

        color = {"LV1": "#ffd700", "LV2": "#ff8800", "LV3": "#ff4444"}.get(level, "#fff")
        self._alert_log_box.append(
            f'<span style="color:{color};font-weight:bold;">{line}</span>'
        )
        # 스크롤 최하단 유지
        sb = self._alert_log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_alert_status(self) -> None:
        """1분마다 상태 라벨 갱신."""
        if self._alert_engine and self._alert_engine.is_running:
            txt = self._alert_engine.status_text()
            self._alert_status_lbl.setText(f"● {txt}")
