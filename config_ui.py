"""
config_ui.py — ConfigMixin: 저장 설정 UI 위젯  v1.0
════════════════════════════════════════════════════════════
  _build_config_widget() → QGroupBox
    ┌────────────────────────┐
    │ ⚙ 저장 설정            │
    │ 기초자산 저장 주기      │
    │ [10초 ▼]  ● 저장 중   │
    │ [💾 설정 저장]         │
    └────────────────────────┘
  - 저장 주기: 5초 / 10초 / 30초 (기본 10초)
  - 설정 저장 → data/settings.json
  - 변경 즉시 und_saver.set_interval() 반영
════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer


class ConfigMixin:
    """저장 설정 UI — tab_options.py CallPutGrid 다중상속에 포함."""

    def _build_config_widget(self) -> QGroupBox:
        """사이드바 하단에 붙이는 저장 설정 그룹박스."""

        gb = QGroupBox("⚙ 저장 설정")
        gb.setStyleSheet(
            "QGroupBox{font-size:11px;color:#90caf9;font-weight:bold;"
            "border:1px solid #2a2a5a;border-radius:4px;"
            "margin-top:8px;padding-top:6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;}")

        v = QVBoxLayout(gb)
        v.setContentsMargins(6, 10, 6, 6)
        v.setSpacing(5)

        # ── 라벨 ────────────────────────────────────────────
        lbl = QLabel("기초자산 저장 주기")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#aaa;font-size:11px;border:none;")
        v.addWidget(lbl)

        # ── 주기 선택 콤보 + 상태 표시 ──────────────────────
        row1 = QHBoxLayout(); row1.setSpacing(4)

        self._cfg_combo = QComboBox()
        self._cfg_combo.setFixedHeight(24)
        self._cfg_combo.setStyleSheet(
            "QComboBox{background:#0d0d1e;color:#ffd700;"
            "border:1px solid #3a3a6a;font-size:12px;"
            "font-weight:bold;padding:1px 4px;border-radius:3px;}"
            "QComboBox QAbstractItemView{background:#12122a;"
            "color:#ffd700;font-size:12px;}"
            "QComboBox::drop-down{border:none;width:16px;}")
        for label in ["5초", "10초", "30초"]:
            self._cfg_combo.addItem(label)
        self._cfg_combo.setCurrentIndex(1)   # 기본값: 10초
        self._cfg_combo.currentIndexChanged.connect(self._on_cfg_interval_change)

        self._cfg_status = QLabel("⏸ 대기")
        self._cfg_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._cfg_status.setStyleSheet("color:#555;font-size:10px;border:none;")

        row1.addWidget(self._cfg_combo)
        row1.addWidget(self._cfg_status)
        v.addLayout(row1)

        # ── 저장 버튼 ────────────────────────────────────────
        self._cfg_save_btn = QPushButton("💾 설정 저장")
        self._cfg_save_btn.setFixedHeight(24)
        self._cfg_save_btn.setStyleSheet(
            "QPushButton{background:#1a2a3a;color:#90caf9;"
            "font-size:11px;font-weight:bold;"
            "border:1px solid #2a4a6a;border-radius:3px;}"
            "QPushButton:hover{background:#2a3a4a;color:#ffffff;}"
            "QPushButton:pressed{background:#0a1a2a;}")
        self._cfg_save_btn.clicked.connect(self._on_cfg_save)
        v.addWidget(self._cfg_save_btn)

        # ── 저장 완료 메시지 라벨 (2초 후 숨김) ─────────────
        self._cfg_msg = QLabel("")
        self._cfg_msg.setAlignment(Qt.AlignCenter)
        self._cfg_msg.setStyleSheet("color:#00e676;font-size:10px;border:none;")
        v.addWidget(self._cfg_msg)

        # ── 상태 자동 갱신 타이머 (3초마다) ─────────────────
        self._cfg_timer = QTimer(self)
        self._cfg_timer.setInterval(3000)
        self._cfg_timer.timeout.connect(self._refresh_cfg_status)
        self._cfg_timer.start()

        # 초기 설정값 로드
        self._load_cfg_from_settings()

        return gb

    # ── 이벤트 핸들러 ────────────────────────────────────────

    def _on_cfg_interval_change(self, idx: int):
        """콤보 변경 → und_saver 즉시 반영."""
        seconds = [5, 10, 30][idx]
        try:
            from trade_log.und_saver import set_interval
            set_interval(seconds)
        except Exception as e:
            print(f"[config_ui] set_interval 오류: {e}")

    def _on_cfg_save(self):
        """설정 저장 버튼 → data/settings.json 저장."""
        idx     = self._cfg_combo.currentIndex()
        seconds = [5, 10, 30][idx]
        try:
            from core_io import save_json, load_json
            cfg = load_json("settings.json", {})
            cfg["und_save_interval"] = seconds
            save_json("settings.json", cfg)

            # 버튼 피드백
            self._cfg_msg.setText(f"✓ {seconds}초 저장됨")
            QTimer.singleShot(2000, lambda: self._cfg_msg.setText(""))
        except Exception as e:
            self._cfg_msg.setText("⚠ 저장 실패")
            print(f"[config_ui] 설정 저장 오류: {e}")

    def _refresh_cfg_status(self):
        """3초마다 und_saver 상태 → 라벨 갱신."""
        try:
            from trade_log.und_saver import is_running, get_interval
            if is_running():
                ivl = get_interval()
                self._cfg_status.setText(f"● 저장 중({ivl}s)")
                self._cfg_status.setStyleSheet(
                    "color:#00e676;font-size:10px;border:none;")
            else:
                self._cfg_status.setText("⏸ 대기")
                self._cfg_status.setStyleSheet(
                    "color:#555;font-size:10px;border:none;")
        except Exception:
            pass

    def _load_cfg_from_settings(self):
        """앱 시작 시 settings.json → 콤보 초기값 복원."""
        try:
            from core_io import load_json
            cfg     = load_json("settings.json", {})
            seconds = cfg.get("und_save_interval", 10)
            idx     = {5: 0, 10: 1, 30: 2}.get(seconds, 1)
            self._cfg_combo.setCurrentIndex(idx)
            # und_saver에도 적용
            from trade_log.und_saver import set_interval
            set_interval(seconds)
        except Exception:
            pass   # 파일 없으면 기본값(10초) 유지
