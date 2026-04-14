"""
watch_log_widget.py — 알람 로그·사운드·등록목록 탭 UI  v6.4
════════════════════════════════════════════════════════
수정 대상: 알람로그 레이아웃, 사운드 버튼, 등록목록 테이블
포함 메서드:
  _build_log_tab()    탭2: 알람로그 + 사운드 설정
  _build_rules_tab()  탭3: 등록된 감시목록 테이블
  _on_watch_font_change() / _apply_font_to_widget()
  _pick_alert_sound() / _clear_alert_sound() / _play_alert_sound()
════════════════════════════════════════════════════════
"""

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFileDialog, QMessageBox,
)
from PyQt5.QtGui import QFont

from core import make_table, SAVE_DIR


class WatchLogMixin:
    """알람 로그·사운드·등록목록 탭 UI. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────
    # 탭2: 알람 로그
    # ─────────────────────────────────────────────────────
    def _build_log_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)

        self.lbl_watch_file = QLabel(f"파일: {self._watch_log_file}")
        self.lbl_watch_file.setStyleSheet(
            "color:#555;font-size:9px;border:none;")
        self.lbl_watch_file.setWordWrap(True)
        v.addWidget(self.lbl_watch_file)

        self.watch_log_box = QTextEdit()
        self.watch_log_box.setReadOnly(True)
        self.watch_log_box.setStyleSheet(
            "background:#05050f;color:#00ff88;font-size:12px;"
            "border:1px solid #1a3a1a;font-family:monospace;")
        v.addWidget(self.watch_log_box, 1)

        # 사운드 설정 행
        sound_row = QHBoxLayout(); sound_row.setSpacing(4)
        sound_row.addWidget(QLabel("🔊 알람음:",
            styleSheet="color:#aaa;font-size:11px;border:none;"))
        self.lbl_sound_file = QLabel("기본 비프음")
        self.lbl_sound_file.setStyleSheet(
            "color:#ffd700;font-size:10px;border:1px solid #333;"
            "border-radius:3px;padding:1px 4px;background:#0a0a1e;")
        self.lbl_sound_file.setMaximumWidth(140)

        btn_pick  = QPushButton("📂 파일 선택"); btn_pick.setFixedHeight(22)
        btn_pick.setStyleSheet(
            "background:#1a3a6b;color:#90caf9;font-size:10px;padding:2px 5px;")
        btn_pick.clicked.connect(self._pick_alert_sound)

        btn_test  = QPushButton("▶ 테스트"); btn_test.setFixedHeight(22)
        btn_test.setStyleSheet(
            "background:#2d2d2d;color:#ffd700;font-size:10px;padding:2px 5px;")
        btn_test.clicked.connect(self._play_alert_sound)

        btn_clr_s = QPushButton("✕"); btn_clr_s.setFixedHeight(22)
        btn_clr_s.setFixedWidth(22)
        btn_clr_s.setStyleSheet(
            "background:#4a1a1a;color:#ff8888;font-size:10px;")
        btn_clr_s.setToolTip("기본 비프음으로 초기화")
        btn_clr_s.clicked.connect(self._clear_alert_sound)

        sound_row.addWidget(self.lbl_sound_file, 1)
        for b in (btn_pick, btn_test, btn_clr_s):
            sound_row.addWidget(b)
        v.addLayout(sound_row)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_clr_log = QPushButton("🗑 화면 지우기")
        btn_clr_log.setStyleSheet(
            "background:#2d2d2d;color:#aaa;font-size:10px;padding:3px;")
        btn_clr_log.clicked.connect(self.watch_log_box.clear)

        btn_open = QPushButton("📁 파일 열기")
        btn_open.setStyleSheet(
            "background:#1a3a6b;color:#90caf9;font-size:10px;padding:3px;")
        btn_open.clicked.connect(self._open_watch_log_folder)

        btn_load = QPushButton("📂 결과 불러오기")
        btn_load.setStyleSheet(
            "background:#2d4a6b;color:#90caf9;font-size:10px;padding:3px;")
        btn_load.clicked.connect(self._load_watch_log)

        btn_row.addWidget(btn_clr_log)
        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_load)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    # ─────────────────────────────────────────────────────
    # 탭3: 등록된 감시 목록
    # ─────────────────────────────────────────────────────
    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w); v.setSpacing(4); v.setContentsMargins(6, 6, 6, 6)
        v.addWidget(QLabel("더블클릭 = 삭제",
            styleSheet="color:#666;font-size:10px;border:none;"))
        self.tbl_watch_rules = make_table(["대상", "조건 요약", "AND 요약", "상태"])
        self.tbl_watch_rules.itemDoubleClicked.connect(
            lambda it: self._del_watch_rule(it.row()))
        v.addWidget(self.tbl_watch_rules, 1)
        btn_row = QHBoxLayout()
        btn_clr = QPushButton("🗑 전체 삭제")
        btn_clr.setStyleSheet(
            "background:#5a1a1a;color:#ff6666;font-weight:bold;padding:5px;")
        btn_clr.clicked.connect(self._clear_watch_rules)
        btn_row.addWidget(btn_clr); btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    # ─────────────────────────────────────────────────────
    # 폰트 변경
    # ─────────────────────────────────────────────────────
    def _on_watch_font_change(self, value: int):
        self._watch_font_size_lbl.setText(f"{value}px")
        if hasattr(self, '_watch_gb') and self._watch_gb:
            self._apply_font_to_widget(self._watch_gb, value)

    def _apply_font_to_widget(self, widget, size: int):
        from PyQt5.QtWidgets import QWidget as _QW
        skip = (self._watch_font_slider, self._watch_font_size_lbl)
        if widget in skip: return
        if hasattr(widget, 'font'):
            f = widget.font(); f.setPointSize(size); widget.setFont(f)
        for child in widget.findChildren(_QW):
            if child not in skip:
                f = child.font(); f.setPointSize(size); child.setFont(f)

    # ─────────────────────────────────────────────────────
    # 알람 사운드
    # ─────────────────────────────────────────────────────
    def _pick_alert_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택", str(Path.home()),
            "WAV 파일 (*.wav);;모든 파일 (*)")
        if not path: return
        self._alert_sound_path = path
        fname = Path(path).name
        self.lbl_sound_file.setText(fname)
        self.lbl_sound_file.setToolTip(path)
        self._log(f"🔊 알람음 설정: {fname}")

    def _clear_alert_sound(self):
        self._alert_sound_path = ""
        self.lbl_sound_file.setText("기본 비프음")
        self.lbl_sound_file.setToolTip("")
        self._log("🔊 알람음: 기본 비프음으로 초기화")

    def _play_alert_sound(self):
        if self._alert_sound_path:
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(self._alert_sound_path); return
            except ImportError: pass
            try:
                import winsound
                winsound.PlaySound(self._alert_sound_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC); return
            except Exception: pass
            try:
                import subprocess, sys
                cmd = (["afplay"] if sys.platform == "darwin" else ["aplay"])
                subprocess.Popen(cmd + [self._alert_sound_path]); return
            except Exception as e:
                self._log(f"🔊 사운드 재생 실패: {e}")
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.beep()
        except Exception: pass
