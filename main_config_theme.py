"""
main_config_theme.py — 테마 설정 패널 (좌측 배치용)
0DTE Master Dashboard v6.5

기능:
  - 프리셋 5종 (light/dark/midnight/matrix/amber) 원클릭 선택
  - 3개 카테고리 미세조정: 배경색, 패널색, 폰트색 (각 5개 항목)
  - JSON 저장/불러오기 (main_config.json 의 "theme" 키)
  - apply_callback 으로 main.py 의 _apply_theme() 에 연결

사용법:
    from main_config_theme import ThemeConfigPanel

    panel = ThemeConfigPanel(parent=self, apply_callback=self._apply_theme)
    # 좌측 레이아웃에 추가
    left_layout.addWidget(panel)

    # main.py 에서 테마 적용 후 버튼 동기화
    panel.sync_preset_buttons(current_theme_name)
"""

import json
import os
from typing import Callable, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QGridLayout, QColorDialog, QButtonGroup,
    QScrollArea, QFrame, QSizePolicy, QSpacerItem,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont


# ── 기본 설정 경로 ──────────────────────────────────────────────────────────
_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "main_config.json"
)


# ── 미세조정 항목 정의 ───────────────────────────────────────────────────────
# (label, palette_key)
BG_ITEMS = [
    ("메인 배경",       "win_bg"),
    ("그룹 배경",       "group_bg"),
    ("테이블 배경",     "tbl_bg"),
    ("입력창 배경",     "input_bg"),
    ("로그 배경",       "log_bg"),
]

PANEL_ITEMS = [
    ("버튼 배경",       "btn_bg"),
    ("버튼 호버",       "btn_hover"),
    ("탭 배경",         "tab_bg"),
    ("선택 탭",         "tab_sel_bg"),
    ("스플리터",        "splitter"),
]

FONT_ITEMS = [
    ("기본 텍스트",     "widget_fg"),
    ("버튼 텍스트",     "btn_fg"),
    ("헤더 텍스트",     "hdr_fg"),
    ("탭 텍스트",       "tab_fg"),
    ("로그 텍스트",     "log_fg"),
]

CATEGORY_DEFS = [
    ("배경 색상",   BG_ITEMS),
    ("패널 색상",   PANEL_ITEMS),
    ("폰트 색상",   FONT_ITEMS),
]


# ── 색상 버튼 ────────────────────────────────────────────────────────────────
class _ColorSwatch(QPushButton):
    """색상 미리보기 + 클릭 시 QColorDialog."""

    color_changed = pyqtSignal(str, str)  # (palette_key, hex_color)

    def __init__(self, palette_key: str, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._key = palette_key
        self._color = color
        self.setFixedSize(28, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._refresh()
        self.clicked.connect(self._pick)

    def set_color(self, color: str):
        self._color = color
        self._refresh()

    def _refresh(self):
        c = QColor(self._color)
        # 대비 테두리 (밝으면 어둡게, 어두우면 밝게)
        luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        border = "#555" if luma > 128 else "#aaa"
        self.setStyleSheet(
            f"QPushButton {{ background:{self._color}; border:1px solid {border};"
            f" border-radius:3px; }} "
            f"QPushButton:hover {{ border:2px solid #4da6ff; }}"
        )

    def _pick(self):
        dlg = QColorDialog(QColor(self._color), self)
        dlg.setOption(QColorDialog.ShowAlphaChannel, False)
        if dlg.exec_():
            hex_c = dlg.selectedColor().name()
            self._color = hex_c
            self._refresh()
            self.color_changed.emit(self._key, hex_c)

    @property
    def color(self):
        return self._color


# ── 메인 패널 ────────────────────────────────────────────────────────────────
class ThemeConfigPanel(QWidget):
    """
    테마 설정 패널 — 좌측 배치용 위젯.

    Parameters
    ----------
    apply_callback : Callable[[str], None]
        테마 이름을 받아 앱 전체에 적용하는 함수.
        (예: main.py 의 self._apply_theme)
    config_path : str, optional
        main_config.json 경로. 기본값: 스크립트 디렉토리.
    """

    PRESET_ORDER = ["light", "dark", "midnight", "matrix", "amber"]
    PRESET_LABELS = {
        "light":    "☀  라이트",
        "dark":     "🌙 다크",
        "midnight": "🌌 미드나잇",
        "matrix":   "💻 매트릭스",
        "amber":    "🟡 앰버",
    }

    def __init__(
        self,
        parent=None,
        apply_callback: Optional[Callable] = None,
        config_path: str = _DEFAULT_CONFIG_PATH,
    ):
        super().__init__(parent)
        self._callback = apply_callback
        self._config_path = config_path
        self._swatches: dict[str, _ColorSwatch] = {}   # palette_key → swatch
        self._preset_btns: dict[str, QPushButton] = {}
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._custom_overrides: dict[str, str] = {}    # 미세조정 오버라이드

        self._build_ui()
        self._load_config()

    # ── UI 빌드 ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # 타이틀
        title = QLabel("🎨 테마 설정")
        title.setFont(QFont("", 11, QFont.Bold))
        root.addWidget(title)

        # ① 프리셋 버튼 그룹
        preset_box = QGroupBox("프리셋 테마")
        pb_lay = QVBoxLayout(preset_box)
        pb_lay.setSpacing(4)

        for key in self.PRESET_ORDER:
            btn = QPushButton(self.PRESET_LABELS[key])
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, k=key: self._on_preset(k))
            self._btn_group.addButton(btn)
            self._preset_btns[key] = btn
            pb_lay.addWidget(btn)

        root.addWidget(preset_box)

        # ② 미세조정 스크롤 영역
        fine_label = QLabel("미세 조정")
        fine_label.setFont(QFont("", 9, QFont.Bold))
        root.addWidget(fine_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 4, 0)
        inner_lay.setSpacing(6)

        for cat_label, items in CATEGORY_DEFS:
            grp = QGroupBox(cat_label)
            grp_lay = QGridLayout(grp)
            grp_lay.setHorizontalSpacing(6)
            grp_lay.setVerticalSpacing(4)

            for row_i, (lbl_text, pal_key) in enumerate(items):
                lbl = QLabel(lbl_text)
                lbl.setFixedWidth(80)
                swatch = _ColorSwatch(pal_key, "#888888")
                swatch.color_changed.connect(self._on_swatch_change)
                self._swatches[pal_key] = swatch
                grp_lay.addWidget(lbl, row_i, 0)
                grp_lay.addWidget(swatch, row_i, 1)

            inner_lay.addWidget(grp)

        inner_lay.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # ③ 하단 버튼 (저장 / 리셋)
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 저장")
        save_btn.setFixedHeight(28)
        save_btn.clicked.connect(self._save_config)

        reset_btn = QPushButton("↺ 리셋")
        reset_btn.setFixedHeight(28)
        reset_btn.clicked.connect(self._reset_overrides)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(reset_btn)
        root.addLayout(btn_row)

    # ── 이벤트 ──────────────────────────────────────────────────────────────
    def _on_preset(self, theme_name: str):
        """프리셋 선택 → 앱 적용 → 스와치 갱신."""
        # 오버라이드 초기화 (프리셋 클릭 시 미세조정 리셋)
        self._custom_overrides.clear()
        if self._callback:
            self._callback(theme_name)
        self._sync_swatches_from_core(theme_name)

    def _on_swatch_change(self, palette_key: str, hex_color: str):
        """미세조정 색상 변경 → 런타임 팔레트 패치 → 즉시 적용."""
        self._custom_overrides[palette_key] = hex_color
        self._patch_and_apply()

    def _patch_and_apply(self):
        """_custom_overrides 를 현재 팔레트에 덮어쓰고 스타일 재적용."""
        try:
            import core as _core
            pal = _core.THEME_PALETTES.get(_core.CURRENT_THEME, {})
            pal.update(self._custom_overrides)
            if self._callback:
                self._callback(_core.CURRENT_THEME)
        except Exception as e:
            print(f"[ThemeConfigPanel] patch error: {e}")

    def _reset_overrides(self):
        """미세조정 초기화 → 현재 프리셋 재적용."""
        self._custom_overrides.clear()
        try:
            import core as _core
            name = _core.CURRENT_THEME
        except Exception:
            name = "light"
        if self._callback:
            self._callback(name)
        self._sync_swatches_from_core(name)

    # ── 스와치 동기화 ────────────────────────────────────────────────────────
    def _sync_swatches_from_core(self, theme_name: str):
        """core.py 팔레트에서 스와치 색상 갱신."""
        try:
            import core as _core
            pal = _core.THEME_PALETTES.get(theme_name, {})
            for key, swatch in self._swatches.items():
                color = pal.get(key) or pal.get("win_bg", "#1e1e2e")
                swatch.set_color(color)
        except Exception as e:
            print(f"[ThemeConfigPanel] sync error: {e}")

    def sync_preset_buttons(self, theme_name: str):
        """외부(main.py)에서 호출 — 현재 테마 버튼 체크 상태 동기화."""
        btn = self._preset_btns.get(theme_name)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self._sync_swatches_from_core(theme_name)

    # ── JSON 저장/로드 ───────────────────────────────────────────────────────
    def _load_config(self):
        """main_config.json 에서 "theme" 섹션 복원."""
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            theme_cfg = cfg.get("theme", {})

            preset = theme_cfg.get("preset", "light")
            overrides = theme_cfg.get("overrides", {})

            # 프리셋 먼저 적용
            btn = self._preset_btns.get(preset)
            if btn:
                btn.setChecked(True)
            if self._callback:
                self._callback(preset)

            # 오버라이드 복원
            if overrides:
                self._custom_overrides = overrides
                self._patch_and_apply()

            self._sync_swatches_from_core(preset)

        except Exception as e:
            print(f"[ThemeConfigPanel] load error: {e}")

    def _save_config(self):
        """현재 테마 + 미세조정을 main_config.json 에 저장."""
        try:
            import core as _core
            current_preset = _core.CURRENT_THEME
        except Exception:
            current_preset = "light"

        # 기존 JSON 병합 저장 (다른 키 보존)
        cfg: dict = {}
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}

        cfg.setdefault("theme", {})
        cfg["theme"]["preset"] = current_preset
        cfg["theme"]["overrides"] = dict(self._custom_overrides)

        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        print(f"[ThemeConfigPanel] saved → {self._config_path}  preset={current_preset}")


# ── 텍스트 가시성 버그 픽스 헬퍼 ─────────────────────────────────────────────
def get_safe_palette_light() -> dict:
    """
    라이트 모드에서 텍스트가 안 보이는 버그 수정용 팔레트.
    core.py 의 THEME_PALETTES["light"] 에 아래 값이 누락된 경우 병합하세요.

    문제 원인: widget_fg / tbl_fg 등 전경색 키가 없거나
               흰색(#ffffff)으로 설정되어 밝은 배경에서 안 보임.
    """
    return {
        # 전경색 (라이트 모드: 어두운 색)
        "widget_fg":    "#1a1a2e",
        "btn_fg":       "#1a1a2e",
        "hdr_fg":       "#0d1b2a",
        "tbl_fg":       "#1a1a2e",
        "tab_fg":       "#2c2c54",
        "log_fg":       "#1a1a2e",
        "radio_fg":     "#1a1a2e",
        "input_fg":     "#1a1a2e",
        "combo_popup_fg":"#1a1a2e",
        "combo_sel_fg": "#ffffff",
        "list_fg":      "#1a1a2e",
        "tbl_sel_fg":   "#ffffff",
        "group_title":  "#0d1b2a",
    }


def apply_light_fg_fix():
    """
    라이트 모드 전경색 누락 버그를 런타임에 즉시 수정.
    main.py 초기화 시점에 호출하세요:

        from main_config_theme import apply_light_fg_fix
        apply_light_fg_fix()
    """
    try:
        import core as _core
        fix = get_safe_palette_light()
        pal = _core.THEME_PALETTES.get("light", {})
        for k, v in fix.items():
            if k not in pal or pal[k] in ("#ffffff", "#fff", "white", ""):
                pal[k] = v
        _core.THEME_PALETTES["light"] = pal
        print("[apply_light_fg_fix] 라이트 모드 전경색 수정 완료.")
    except Exception as e:
        print(f"[apply_light_fg_fix] 오류: {e}")
