"""
core_tab_wrapper.py — TabWrapper (폰트 슬라이더 + 다크모드 + 설정 저장/복원)
core.py 300줄 초과로 분리.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider,
)
from PyQt5.QtCore import Qt, QTimer

from core import DEFAULT_FONT_SIZE, SAVE_DIR, _all_tables, _apply_table_theme
from core_io import save_json, load_json

class TabWrapper(QWidget):
    """FontBar + 다크모드 토글 + GridTab을 수직으로 묶는 래퍼.
    각 탭의 설정(다크모드, 폰트크기 등)을 data/tab_settings.json에 저장/복원."""

    # 앱 전체 다크모드 상태 (공유)
    _global_dark: bool = False
    _instances: list = []

    def __init__(self, grid_tab, tab_name: str = "", parent=None):
        super().__init__(parent)
        self.grid_tab = grid_tab
        self.tab_name = tab_name or type(grid_tab).__name__
        TabWrapper._instances.append(self)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── 상단 바 (폰트 + 다크모드) ──────────────────────────
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet("background:#07070f;border-bottom:1px solid #1e2050;")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(6, 2, 6, 2); bh.setSpacing(6)

        # 폰트 슬라이더
        lbl_f = QLabel("폰트:")
        lbl_f.setStyleSheet("color:#5dade2;font-size:11px;border:none;")
        lbl_f.setFixedWidth(36)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(10, 28)
        self.slider.setValue(DEFAULT_FONT_SIZE)
        self.slider.setFixedWidth(120); self.slider.setFixedHeight(16)
        self.lbl_v = QLabel(f"{DEFAULT_FONT_SIZE}px")
        self.lbl_v.setStyleSheet("color:#ffd700;font-size:11px;border:none;min-width:32px;")
        self.slider.valueChanged.connect(self._on_font)

        # 다크모드 버튼
        self.btn_dark = QPushButton("🌙 다크")
        self.btn_dark.setCheckable(True)
        self.btn_dark.setFixedHeight(22)
        self.btn_dark.setFixedWidth(72)
        self.btn_dark.setStyleSheet(
            "QPushButton{background:#1c1c3a;color:#aaa;border:1px solid #3a3a7a;"
            "border-radius:3px;font-size:11px;padding:1px 4px;}"
            "QPushButton:checked{background:#23395d;color:#90caf9;border-color:#5599cc;}")
        self.btn_dark.clicked.connect(self._on_dark_btn)

        bh.addWidget(lbl_f); bh.addWidget(self.slider); bh.addWidget(self.lbl_v)
        bh.addStretch()
        bh.addWidget(self.btn_dark)

        vl.addWidget(bar)
        vl.addWidget(grid_tab, 1)

        self.font_bar = bar   # 하위 호환성

        # ── 저장된 설정 복원 ────────────────────────────────────
        self._restore_settings()

    # ── 폰트 ─────────────────────────────────────────────────
    def _on_font(self, fs: int):
        self.lbl_v.setText(f"{fs}px")
        self._apply_font(fs)
        self._save_settings()

    def _apply_font(self, fs: int):
        self.grid_tab.setStyleSheet(
            f"QWidget{{font-size:{fs}px;}}"
            f"QLabel{{font-size:{fs}px;}}"
            f"QTableWidget{{font-size:{fs}px;}}"
            f"QPushButton{{font-size:{fs}px;}}"
            f"QLineEdit,QComboBox,QSpinBox{{font-size:{fs}px;}}"
            f"QHeaderView::section{{font-size:{fs}px;}}"
            f"QListWidget{{font-size:{fs}px;}}"
            f"QTextEdit{{font-size:{max(10,fs-4)}px;}}")

    # ── 다크모드 ──────────────────────────────────────────────
    def _on_dark_btn(self, checked: bool):
        TabWrapper._global_dark = checked
        # 모든 탭에 동기 적용
        for inst in TabWrapper._instances:
            inst._apply_dark(checked)
            inst.btn_dark.blockSignals(True)
            inst.btn_dark.setChecked(checked)
            inst.btn_dark.blockSignals(False)
        self._save_settings()

    def _apply_dark(self, dark: bool):
        """탭 위젯 자체 + grid_tab에 다크/라이트 테마 적용 + 모든 테이블 테마 동기화."""
        if dark:
            style = (
                "QWidget{background:#1e1e2e;color:#e0e0f0;}"
                "QGroupBox{border:1px solid #3a3a6a;border-radius:4px;"
                "margin-top:8px;padding-top:6px;font-weight:bold;}"
                "QGroupBox::title{subcontrol-origin:margin;left:6px;color:#90caf9;}"
                "QLineEdit,QSpinBox,QListWidget,QCalendarWidget"
                "{background:#12122a;color:#e0e0f0;border:1px solid #3a3a6a;border-radius:3px;}"
                "QPushButton{background:#1c1c3a;color:#e0e0f0;"
                "border:1px solid #3a3a7a;border-radius:3px;padding:2px 6px;}"
                "QPushButton:hover{background:#2a2a5a;}"
                "QComboBox{background:#12122a;color:#e0e0f0;border:1px solid #3a3a6a;"
                "border-radius:3px;}"
                "QComboBox QAbstractItemView{background:#12122a;color:#e0e0f0;"
                "selection-background-color:#1c3a6a;}"
                "QTextEdit{background:#050510;color:#00e676;border:1px solid #2a2a4a;}"
                "QCheckBox,QRadioButton{color:#e0e0f0;background:transparent;}"
                "QLabel{color:#e0e0f0;background:transparent;}"
                "QScrollArea{border:none;}"
            )
        else:
            style = (
                "QWidget{background:#f0f2f5;color:#111;}"
                "QGroupBox{border:1px solid #bbb;border-radius:4px;"
                "margin-top:8px;padding-top:6px;font-weight:bold;}"
                "QGroupBox::title{subcontrol-origin:margin;left:6px;color:#1565c0;}"
                "QLineEdit,QSpinBox,QListWidget,QCalendarWidget"
                "{background:#fff;color:#111;border:1px solid #bbb;border-radius:3px;}"
                "QPushButton{background:#e8eaf0;color:#111;"
                "border:1px solid #bbb;border-radius:3px;padding:2px 6px;}"
                "QPushButton:hover{background:#c5cae9;}"
                "QComboBox{background:#fff;color:#111;border:1px solid #bbb;border-radius:3px;}"
                "QComboBox QAbstractItemView{background:#fff;color:#111;"
                "selection-background-color:#bbdefb;}"
                "QTextEdit{background:#fff;color:#222;border:1px solid #ccc;}"
                "QCheckBox,QRadioButton{color:#111;background:transparent;}"
                "QLabel{color:#111;background:transparent;}"
                "QScrollArea{border:none;}"
            )
        self.grid_tab.setStyleSheet(style)

        # ── 테이블은 별도 QSS로 강제 적용 (부모 스타일 오염 방지) ──
        from core import _all_tables, _apply_table_theme
        for tbl in _all_tables:
            try:
                _apply_table_theme(tbl, dark=dark)
            except Exception:
                pass

        # tab_chart.py처럼 _apply_theme()을 가진 탭은 별도 처리
        if hasattr(self.grid_tab, '_apply_theme'):
            self.grid_tab.dark_mode = dark
            self.grid_tab._apply_theme()

    # ── 설정 저장/복원 ────────────────────────────────────────
    def _settings_key(self) -> str:
        return f"tab_settings_{self.tab_name}"

    def _save_settings(self):
        all_s = load_json("tab_settings.json", {})
        data = {
            "dark": self.btn_dark.isChecked(),
            "font": self.slider.value(),
        }
        # grid_tab이 _get_extra_settings() 를 구현하면 추가 저장
        if hasattr(self.grid_tab, '_get_extra_settings'):
            try:
                data.update(self.grid_tab._get_extra_settings())
            except Exception as e:
                print(f"[settings save] {e}")
        all_s[self.tab_name] = data
        save_json("tab_settings.json", all_s)

    def _restore_settings(self):
        all_s = load_json("tab_settings.json", {})
        s = all_s.get(self.tab_name, {})
        dark = s.get("dark", False)
        fs   = s.get("font", DEFAULT_FONT_SIZE)
        self.slider.blockSignals(True)
        self.slider.setValue(fs)
        self.slider.blockSignals(False)
        self.lbl_v.setText(f"{fs}px")
        self._apply_font(fs)
        if dark:
            self.btn_dark.blockSignals(True)
            self.btn_dark.setChecked(True)
            self.btn_dark.blockSignals(False)
            TabWrapper._global_dark = True
        self._apply_dark(dark)
        # grid_tab이 _apply_extra_settings() 를 구현하면 복원 위임
        # (grid_tab이 아직 완전히 초기화된 후 호출되도록 QTimer 사용)
        if hasattr(self.grid_tab, '_apply_extra_settings') and s:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(300, lambda: self._restore_extra(s))

    def _restore_extra(self, s: dict):
        try:
            self.grid_tab._apply_extra_settings(s)
        except Exception as e:
            print(f"[settings restore] {e}")


