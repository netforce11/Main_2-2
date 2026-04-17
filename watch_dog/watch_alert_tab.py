"""
watch_alert_tab.py — SPX 감시 패널 (항상 위, 좌측 하단 고정)
- 조건A: 두 행 독립, 각각 방향 선택 (상승/하락/양방향)
- 조건B: 최대 5개 행사가 (콜-풋 탭 클릭 → 자동 추가)
- 신호등: 감시중(초록) / 정지(회색) / 알람(빨강)
- 알람 횟수 표시 / 로그 확인 버튼
- 알람 5회 도달 시 해당 조건 억제 (로그에는 기록)
- X 버튼 → hide() (종료 아님)
"""

import os, sys, subprocess
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit,
    QListWidget, QListWidgetItem, QGroupBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont

# watch_dog/ 폴더를 sys.path 에 추가 (같은 폴더 내 모듈 참조)
_WATCH_DOG_DIR = str(Path(__file__).resolve().parent)
if _WATCH_DOG_DIR not in sys.path:
    sys.path.insert(0, _WATCH_DOG_DIR)

from alert_engine   import AlertEngine, CondARow
from alert_notifier import AlertNotifier, LEVEL_COLORS
from alert_logger   import AlertLogger


# ─────────────────────────────────────────────────────────
#  감시 패널 메인 위젯
# ─────────────────────────────────────────────────────────

class WatchAlertPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SPX 감시 패널")
        self.setWindowFlags(
            Qt.Tool | Qt.WindowStaysOnTopHint | Qt.CustomizeWindowHint |
            Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint
        )
        self.setFixedWidth(360)

        # 의존성 초기화
        self._logger   = AlertLogger()
        self._notifier = AlertNotifier()
        self._engine   = AlertEngine(on_alert=self._on_alert)
        self._notifier.set_ui_callback(self._on_alert_ui)

        self._alert_total = 0   # 전체 알람 횟수

        self._build_ui()
        self._position_bottom_left()

        # 1분 타이머 → 신호등 깜빡 방지 / 상태 갱신
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._on_tick)

    # ── UI 구성 ────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        root.addLayout(self._make_header())
        root.addWidget(self._make_cond_a_box())
        root.addWidget(self._make_cond_b_box())
        root.addLayout(self._make_control_bar())
        root.addWidget(self._make_log_box())

    def _make_header(self) -> QHBoxLayout:
        hb = QHBoxLayout()
        title = QLabel("🔍 SPX 감시")
        title.setFont(QFont("Arial", 10, QFont.Bold))
        hb.addWidget(title)
        hb.addStretch()

        # 신호등
        self._light = QLabel("●")
        self._light.setStyleSheet("color: #888; font-size: 18px;")
        hb.addWidget(self._light)

        # 알람 횟수
        self._cnt_label = QLabel("알람 0회")
        self._cnt_label.setStyleSheet("color: #aaa; font-size: 10px;")
        hb.addWidget(self._cnt_label)
        return hb

    def _make_cond_a_box(self) -> QGroupBox:
        box = QGroupBox("조건A — SPX 등락")
        vb  = QVBoxLayout(box)
        self._cond_a_rows: list[dict] = []
        for i in range(2):
            row = self._make_cond_a_row(i)
            vb.addLayout(row["layout"])
            self._cond_a_rows.append(row)
        return box

    def _make_cond_a_row(self, idx: int) -> dict:
        hb  = QHBoxLayout()
        lbl = QLabel(f"A{idx+1}")
        lbl.setFixedWidth(22)

        min_sp = QSpinBox(); min_sp.setRange(1, 60); min_sp.setValue(5)
        min_sp.setSuffix("분"); min_sp.setFixedWidth(60)

        pt_sp = QDoubleSpinBox(); pt_sp.setRange(0.1, 999); pt_sp.setValue(5.0)
        pt_sp.setSuffix("pt"); pt_sp.setFixedWidth(70)

        dir_cb = QComboBox()
        dir_cb.addItems(["하락", "상승", "양방향"])
        dir_cb.setFixedWidth(70)

        hb.addWidget(lbl); hb.addWidget(min_sp); hb.addWidget(pt_sp)
        hb.addWidget(dir_cb); hb.addStretch()
        return {"layout": hb, "min": min_sp, "pt": pt_sp, "dir": dir_cb}

    def _make_cond_b_box(self) -> QGroupBox:
        box = QGroupBox("조건B — 옵션 등락 (행사가 최대 5개)")
        vb  = QVBoxLayout(box)

        self._strike_list = QListWidget()
        self._strike_list.setMaximumHeight(90)
        self._strike_list.setToolTip("콜-풋 탭에서 행사가 클릭 시 자동 추가")

        btn_rm = QPushButton("선택 제거")
        btn_rm.setFixedHeight(22)
        btn_rm.clicked.connect(self._remove_selected_strike)

        pct_hb = QHBoxLayout()
        pct_hb.addWidget(QLabel("기준%:"))
        self._pct_sp = QDoubleSpinBox(); self._pct_sp.setRange(10, 9999)
        self._pct_sp.setValue(500); self._pct_sp.setSuffix("%"); self._pct_sp.setFixedWidth(80)
        self._dir_b = QComboBox(); self._dir_b.addItems(["양방향", "상승", "하락"])
        pct_hb.addWidget(self._pct_sp); pct_hb.addWidget(self._dir_b); pct_hb.addStretch()

        vb.addWidget(self._strike_list)
        vb.addWidget(btn_rm)
        vb.addLayout(pct_hb)
        return box

    def _make_control_bar(self) -> QHBoxLayout:
        hb = QHBoxLayout()
        self._btn_start = QPushButton("▶ 감시 시작")
        self._btn_stop  = QPushButton("■ 중지")
        btn_log         = QPushButton("📂 로그")
        self._btn_stop.setEnabled(False)

        self._btn_start.clicked.connect(self._start)
        self._btn_stop.clicked.connect(self._stop)
        btn_log.clicked.connect(self._open_log)

        for b in (self._btn_start, self._btn_stop, btn_log):
            b.setFixedHeight(26)
            hb.addWidget(b)
        return hb

    def _make_log_box(self) -> QTextEdit:
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setMaximumHeight(120)
        self._log_box.setStyleSheet("background:#1a1a1a; color:#ddd; font-size:10px;")
        return self._log_box

    # ── 제어 ──────────────────────────────────────────────

    def _start(self):
        self._apply_cond_a()
        self._engine.reset_counts()
        self._alert_total = 0
        self._cnt_label.setText("알람 0회")
        self._engine.start()
        self._timer.start()
        self._set_light("green")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._log("🟢 감시 시작")

    def _stop(self):
        self._engine.stop()
        self._timer.stop()
        self._set_light("gray")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._log("⬛ 감시 중지")

    def _apply_cond_a(self):
        for idx, row in enumerate(self._cond_a_rows):
            self._engine.cond_a[idx] = CondARow(
                minutes   = row["min"].value(),
                points    = row["pt"].value(),
                direction = row["dir"].currentText(),
                enabled   = True,
            )

    # ── 행사가 추가 (외부 콜-풋 탭에서 호출) ───────────────

    def add_strike_from_chain(self, strike: float, opt_type: str):
        """콜-풋 탭 클릭 시 외부에서 호출"""
        pct = self._pct_sp.value()
        direction = self._dir_b.currentText()
        added = self._engine.add_strike(strike, opt_type, pct, direction)
        if added:
            label = f"{opt_type}  {strike:.1f}  ±{pct:.0f}%  [{direction}]"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, (strike, opt_type))
            self._strike_list.addItem(item)
        else:
            self._log(f"⚠ 최대 5개 / 중복: {opt_type} {strike}")

    def _remove_selected_strike(self):
        item = self._strike_list.currentItem()
        if not item:
            return
        strike, opt_type = item.data(Qt.UserRole)
        self._engine.remove_strike(strike, opt_type)
        self._strike_list.takeItem(self._strike_list.row(item))

    # ── 알람 수신 ─────────────────────────────────────────

    def _on_alert(self, level: int, msg: str):
        """AlertEngine 콜백 → logger + notifier"""
        self._logger.write(level, msg)
        self._notifier.notify(level, msg)

    def _on_alert_ui(self, level: int, msg: str):
        """AlertNotifier UI 콜백 → 화면 갱신"""
        self._alert_total += 1
        self._cnt_label.setText(f"알람 {self._alert_total}회")
        self._set_light("red")
        color = LEVEL_COLORS.get(level, "#fff")
        ts    = datetime.now().strftime("%H:%M:%S")
        html  = (f'<span style="color:{color}">'
                 f'[{ts}] LV{level} {msg}</span>')
        self._log_box.append(html)
        # 2초 후 초록으로 복귀 (감시중이면)
        QTimer.singleShot(2000, self._restore_light)

    # ── UI 보조 ───────────────────────────────────────────

    def _set_light(self, state: str):
        color = {"green": "#00e676", "red": "#ff1744", "gray": "#888"}.get(state, "#888")
        self._light.setStyleSheet(f"color: {color}; font-size: 18px;")

    def _restore_light(self):
        if self._engine.is_running():
            self._set_light("green")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.append(f'<span style="color:#aaa">[{ts}] {msg}</span>')

    def _open_log(self):
        path = self._logger.log_path_today()
        if not path.exists():
            path.touch()
        try:
            os.startfile(str(path))
        except Exception:
            subprocess.Popen(["notepad.exe", str(path)])

    def _on_tick(self):
        """1분 주기 — 외부 데이터 연동 후 push_spx 등 호출 예정"""
        pass  # TODO: SPX/VIX 데이터 연동 시 여기서 push_spx() 호출

    def _position_bottom_left(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.left() + 8
        y = screen.bottom() - self.sizeHint().height() - 8
        self.move(x, y)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
