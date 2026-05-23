"""
core_theme.py — 테마 팔레트 / QSS 생성 / 테마 전환 유틸
════════════════════════════════════════════════════════
core.py 에서 분리된 색상 설정 전용 모듈.

사용법:
    from core_theme import (
        THEME_PALETTES, THEME_LABELS, THEME_ORDER,
        CURRENT_THEME, DEFAULT_FONT_SIZE,
        set_theme, make_style, make_theme_selector,
    )

테마 목록 (8가지):
    "light"    ☀️  라이트   — 밝은 회색, 주간 트레이딩
    "dark"     🌙  다크     — 차콜 다크, 눈 피로 최소화
    "midnight" 🌌  미드나잇 — 딥 다크 블루, 야간 집중
    "matrix"   💻  매트릭스 — 터미널 블랙 + 형광 초록
    "amber"    🟡  앰버     — 빈티지 터미널, 황금 호박색
    "mocha"    ☕  모카     — 에스프레소 브라운 + 크림
    "ocean"    🌊  오션     — 딥 네이비 + 청록
    "nordic"   ❄️  노르딕   — 회청 소프트 다크 (눈 가장 편함)
"""

from __future__ import annotations

DEFAULT_FONT_SIZE: int = 16
CURRENT_THEME:    str  = "light"   # 전역 현재 테마

# ══════════════════════════════════════════════════════════════
# 팔레트 딕셔너리 (키 목록은 파일 하단 참조)
# ══════════════════════════════════════════════════════════════
THEME_PALETTES: dict[str, dict[str, str]] = {

    # ─────────────────────────────────────────────────────────
    # 1. LIGHT — 밝은 회색 (주간 트레이딩)
    # ─────────────────────────────────────────────────────────
    "light": {
        "win_bg":        "#d1d5db",
        "widget_fg":     "#111827",
        "group_bg":      "#e5e7eb",
        "group_border":  "#a1a1aa",
        "group_title":   "#1e40af",
        "btn_bg":        "#f3f4f6",
        "btn_fg":        "#111827",
        "btn_border":    "#cbd5e1",
        "btn_hover":     "#e2e8f0",
        "btn_hover_bdr": "#94a3b8",
        "btn_press":     "#cbd5e1",
        "input_bg":      "#ffffff",
        "input_fg":      "#111827",
        "input_border":  "#cbd5e1",
        "grp_input_bg":  "#f9fafb",
        "grp_input_bdr": "#babdc2",
        "combo_popup_bg":"#ffffff",
        "combo_popup_fg":"#111827",
        "combo_sel_bg":  "#dbeafe",
        "combo_sel_fg":  "#1e40af",
        "list_bg":       "#ffffff",
        "list_border":   "#9ca3af",
        "log_bg":        "#f9fafb",
        "log_border":    "#cbd5e1",
        "log_fg":        "#b91c1c",
        "tbl_bg":        "#ffffff",
        "tbl_grid":      "#e5e7eb",
        "tbl_border":    "#9ca3af",
        "tbl_sel_bg":    "#dbeafe",
        "tbl_sel_fg":    "#1e40af",
        "hdr_bg":        "#e5e7eb",
        "hdr_fg":        "#111827",
        "hdr_border":    "#cbd5e1",
        "radio_fg":      "#111827",
        "tab_bg":        "#e5e7eb",
        "tab_fg":        "#4b5563",
        "tab_border":    "#cbd5e1",
        "tab_sel_bg":    "#ffffff",
        "tab_sel_fg":    "#1d4ed8",
        "tab_sel_bdr":   "#ffffff",
        "pane_bg":       "#ffffff",
        "pane_border":   "#cbd5e1",
        "splitter":      "#cbd5e1",
        "slider_groove": "#cbd5e1",
        "slider_handle": "#1d4ed8",
    },

    # ─────────────────────────────────────────────────────────
    # 2. DARK — 차콜 다크 (야간, 눈 피로 최소화)
    # ─────────────────────────────────────────────────────────
    "dark": {
        "win_bg":        "#1e1e2e",
        "widget_fg":     "#cdd6f4",
        "group_bg":      "#2a2a3e",
        "group_border":  "#45475a",
        "group_title":   "#89b4fa",
        "btn_bg":        "#313244",
        "btn_fg":        "#cdd6f4",
        "btn_border":    "#45475a",
        "btn_hover":     "#3d3f5a",
        "btn_hover_bdr": "#89b4fa",
        "btn_press":     "#45475a",
        "input_bg":      "#262637",
        "input_fg":      "#cdd6f4",
        "input_border":  "#45475a",
        "grp_input_bg":  "#2a2a3e",
        "grp_input_bdr": "#585b70",
        "combo_popup_bg":"#313244",
        "combo_popup_fg":"#cdd6f4",
        "combo_sel_bg":  "#45475a",
        "combo_sel_fg":  "#89b4fa",
        "list_bg":       "#262637",
        "list_border":   "#45475a",
        "log_bg":        "#1e1e2e",
        "log_border":    "#45475a",
        "log_fg":        "#f38ba8",
        "tbl_bg":        "#262637",
        "tbl_grid":      "#313244",
        "tbl_border":    "#45475a",
        "tbl_sel_bg":    "#45475a",
        "tbl_sel_fg":    "#89b4fa",
        "hdr_bg":        "#313244",
        "hdr_fg":        "#cdd6f4",
        "hdr_border":    "#45475a",
        "radio_fg":      "#cdd6f4",
        "tab_bg":        "#2a2a3e",
        "tab_fg":        "#6c7086",
        "tab_border":    "#45475a",
        "tab_sel_bg":    "#1e1e2e",
        "tab_sel_fg":    "#89b4fa",
        "tab_sel_bdr":   "#1e1e2e",
        "pane_bg":       "#1e1e2e",
        "pane_border":   "#45475a",
        "splitter":      "#45475a",
        "slider_groove": "#45475a",
        "slider_handle": "#89b4fa",
    },

    # ─────────────────────────────────────────────────────────
    # 3. MIDNIGHT — 딥 다크 블루 (야간 집중)
    # ─────────────────────────────────────────────────────────
    "midnight": {
        "win_bg":        "#0a0e1a",
        "widget_fg":     "#a8c8ff",
        "group_bg":      "#0d1626",
        "group_border":  "#1a3050",
        "group_title":   "#4fc3f7",
        "btn_bg":        "#0d2040",
        "btn_fg":        "#7eb8ff",
        "btn_border":    "#1a3a6a",
        "btn_hover":     "#123060",
        "btn_hover_bdr": "#4fc3f7",
        "btn_press":     "#1a3a6a",
        "input_bg":      "#080c18",
        "input_fg":      "#a8c8ff",
        "input_border":  "#1a3050",
        "grp_input_bg":  "#0d1626",
        "grp_input_bdr": "#204070",
        "combo_popup_bg":"#0d2040",
        "combo_popup_fg":"#a8c8ff",
        "combo_sel_bg":  "#1a3a6a",
        "combo_sel_fg":  "#4fc3f7",
        "list_bg":       "#080c18",
        "list_border":   "#1a3050",
        "log_bg":        "#0a0e1a",
        "log_border":    "#1a3050",
        "log_fg":        "#ff6b9d",
        "tbl_bg":        "#080c18",
        "tbl_grid":      "#0d2040",
        "tbl_border":    "#1a3050",
        "tbl_sel_bg":    "#1a3a6a",
        "tbl_sel_fg":    "#4fc3f7",
        "hdr_bg":        "#0d2040",
        "hdr_fg":        "#7eb8ff",
        "hdr_border":    "#1a3050",
        "radio_fg":      "#a8c8ff",
        "tab_bg":        "#0d1626",
        "tab_fg":        "#3a6090",
        "tab_border":    "#1a3050",
        "tab_sel_bg":    "#0a0e1a",
        "tab_sel_fg":    "#4fc3f7",
        "tab_sel_bdr":   "#0a0e1a",
        "pane_bg":       "#0a0e1a",
        "pane_border":   "#1a3050",
        "splitter":      "#1a3050",
        "slider_groove": "#1a3050",
        "slider_handle": "#4fc3f7",
    },

    # ─────────────────────────────────────────────────────────
    # 4. MATRIX — 터미널 블랙 + 형광 초록
    # ─────────────────────────────────────────────────────────
    "matrix": {
        "win_bg":        "#020b02",
        "widget_fg":     "#00cc44",
        "group_bg":      "#061006",
        "group_border":  "#0a3010",
        "group_title":   "#00ff66",
        "btn_bg":        "#071407",
        "btn_fg":        "#00cc44",
        "btn_border":    "#0a3010",
        "btn_hover":     "#0d2010",
        "btn_hover_bdr": "#00ff66",
        "btn_press":     "#0a3010",
        "input_bg":      "#020802",
        "input_fg":      "#00cc44",
        "input_border":  "#0a3010",
        "grp_input_bg":  "#061006",
        "grp_input_bdr": "#104010",
        "combo_popup_bg":"#071407",
        "combo_popup_fg":"#00cc44",
        "combo_sel_bg":  "#0a3010",
        "combo_sel_fg":  "#00ff66",
        "list_bg":       "#020802",
        "list_border":   "#0a3010",
        "log_bg":        "#020b02",
        "log_border":    "#0a3010",
        "log_fg":        "#00ff88",
        "tbl_bg":        "#020802",
        "tbl_grid":      "#071407",
        "tbl_border":    "#0a3010",
        "tbl_sel_bg":    "#0a3010",
        "tbl_sel_fg":    "#00ff66",
        "hdr_bg":        "#071407",
        "hdr_fg":        "#00cc44",
        "hdr_border":    "#0a3010",
        "radio_fg":      "#00cc44",
        "tab_bg":        "#061006",
        "tab_fg":        "#1a6020",
        "tab_border":    "#0a3010",
        "tab_sel_bg":    "#020b02",
        "tab_sel_fg":    "#00ff66",
        "tab_sel_bdr":   "#020b02",
        "pane_bg":       "#020b02",
        "pane_border":   "#0a3010",
        "splitter":      "#0a3010",
        "slider_groove": "#0a3010",
        "slider_handle": "#00ff66",
    },

    # ─────────────────────────────────────────────────────────
    # 5. AMBER — 빈티지 터미널, 황금 호박색
    # ─────────────────────────────────────────────────────────
    "amber": {
        "win_bg":        "#100a00",
        "widget_fg":     "#d4940a",
        "group_bg":      "#1a1200",
        "group_border":  "#3d2800",
        "group_title":   "#ffb800",
        "btn_bg":        "#1f1500",
        "btn_fg":        "#d4940a",
        "btn_border":    "#3d2800",
        "btn_hover":     "#2e1f00",
        "btn_hover_bdr": "#ffb800",
        "btn_press":     "#3d2800",
        "input_bg":      "#0c0700",
        "input_fg":      "#d4940a",
        "input_border":  "#3d2800",
        "grp_input_bg":  "#1a1200",
        "grp_input_bdr": "#5a3c00",
        "combo_popup_bg":"#1f1500",
        "combo_popup_fg":"#d4940a",
        "combo_sel_bg":  "#3d2800",
        "combo_sel_fg":  "#ffb800",
        "list_bg":       "#0c0700",
        "list_border":   "#3d2800",
        "log_bg":        "#100a00",
        "log_border":    "#3d2800",
        "log_fg":        "#ff8c00",
        "tbl_bg":        "#0c0700",
        "tbl_grid":      "#1f1500",
        "tbl_border":    "#3d2800",
        "tbl_sel_bg":    "#3d2800",
        "tbl_sel_fg":    "#ffb800",
        "hdr_bg":        "#1f1500",
        "hdr_fg":        "#d4940a",
        "hdr_border":    "#3d2800",
        "radio_fg":      "#d4940a",
        "tab_bg":        "#1a1200",
        "tab_fg":        "#6b4400",
        "tab_border":    "#3d2800",
        "tab_sel_bg":    "#100a00",
        "tab_sel_fg":    "#ffb800",
        "tab_sel_bdr":   "#100a00",
        "pane_bg":       "#100a00",
        "pane_border":   "#3d2800",
        "splitter":      "#3d2800",
        "slider_groove": "#3d2800",
        "slider_handle": "#ffb800",
    },

    # ─────────────────────────────────────────────────────────
    # 6. MOCHA — 에스프레소 브라운 + 크림
    # ─────────────────────────────────────────────────────────
    "mocha": {
        "win_bg":        "#1c1410",
        "widget_fg":     "#e8d5b7",
        "group_bg":      "#261c16",
        "group_border":  "#4a3528",
        "group_title":   "#d4a574",
        "btn_bg":        "#302318",
        "btn_fg":        "#e8d5b7",
        "btn_border":    "#4a3528",
        "btn_hover":     "#3d2e22",
        "btn_hover_bdr": "#d4a574",
        "btn_press":     "#4a3528",
        "input_bg":      "#160f0a",
        "input_fg":      "#e8d5b7",
        "input_border":  "#4a3528",
        "grp_input_bg":  "#261c16",
        "grp_input_bdr": "#5c4030",
        "combo_popup_bg":"#302318",
        "combo_popup_fg":"#e8d5b7",
        "combo_sel_bg":  "#4a3528",
        "combo_sel_fg":  "#d4a574",
        "list_bg":       "#160f0a",
        "list_border":   "#4a3528",
        "log_bg":        "#1c1410",
        "log_border":    "#4a3528",
        "log_fg":        "#e07050",
        "tbl_bg":        "#160f0a",
        "tbl_grid":      "#302318",
        "tbl_border":    "#4a3528",
        "tbl_sel_bg":    "#4a3528",
        "tbl_sel_fg":    "#d4a574",
        "hdr_bg":        "#302318",
        "hdr_fg":        "#e8d5b7",
        "hdr_border":    "#4a3528",
        "radio_fg":      "#e8d5b7",
        "tab_bg":        "#261c16",
        "tab_fg":        "#7a5c40",
        "tab_border":    "#4a3528",
        "tab_sel_bg":    "#1c1410",
        "tab_sel_fg":    "#d4a574",
        "tab_sel_bdr":   "#1c1410",
        "pane_bg":       "#1c1410",
        "pane_border":   "#4a3528",
        "splitter":      "#4a3528",
        "slider_groove": "#4a3528",
        "slider_handle": "#d4a574",
    },

    # ─────────────────────────────────────────────────────────
    # 7. OCEAN — 딥 네이비 + 청록
    # ─────────────────────────────────────────────────────────
    "ocean": {
        "win_bg":        "#071420",
        "widget_fg":     "#b0e0e8",
        "group_bg":      "#0b1e2e",
        "group_border":  "#164060",
        "group_title":   "#00c8d4",
        "btn_bg":        "#0f2438",
        "btn_fg":        "#b0e0e8",
        "btn_border":    "#164060",
        "btn_hover":     "#153050",
        "btn_hover_bdr": "#00c8d4",
        "btn_press":     "#164060",
        "input_bg":      "#050e18",
        "input_fg":      "#b0e0e8",
        "input_border":  "#164060",
        "grp_input_bg":  "#0b1e2e",
        "grp_input_bdr": "#1e5070",
        "combo_popup_bg":"#0f2438",
        "combo_popup_fg":"#b0e0e8",
        "combo_sel_bg":  "#164060",
        "combo_sel_fg":  "#00c8d4",
        "list_bg":       "#050e18",
        "list_border":   "#164060",
        "log_bg":        "#071420",
        "log_border":    "#164060",
        "log_fg":        "#40e0d0",
        "tbl_bg":        "#050e18",
        "tbl_grid":      "#0f2438",
        "tbl_border":    "#164060",
        "tbl_sel_bg":    "#164060",
        "tbl_sel_fg":    "#00c8d4",
        "hdr_bg":        "#0f2438",
        "hdr_fg":        "#b0e0e8",
        "hdr_border":    "#164060",
        "radio_fg":      "#b0e0e8",
        "tab_bg":        "#0b1e2e",
        "tab_fg":        "#2a6080",
        "tab_border":    "#164060",
        "tab_sel_bg":    "#071420",
        "tab_sel_fg":    "#00c8d4",
        "tab_sel_bdr":   "#071420",
        "pane_bg":       "#071420",
        "pane_border":   "#164060",
        "splitter":      "#164060",
        "slider_groove": "#164060",
        "slider_handle": "#00c8d4",
    },

    # ─────────────────────────────────────────────────────────
    # 8. NORDIC — 회청 소프트 다크 (눈 가장 편함, Nord 팔레트)
    # ─────────────────────────────────────────────────────────
    "nordic": {
        "win_bg":        "#2e3440",
        "widget_fg":     "#eceff4",
        "group_bg":      "#3b4252",
        "group_border":  "#4c566a",
        "group_title":   "#88c0d0",
        "btn_bg":        "#434c5e",
        "btn_fg":        "#eceff4",
        "btn_border":    "#4c566a",
        "btn_hover":     "#4c566a",
        "btn_hover_bdr": "#88c0d0",
        "btn_press":     "#4c566a",
        "input_bg":      "#2e3440",
        "input_fg":      "#eceff4",
        "input_border":  "#4c566a",
        "grp_input_bg":  "#3b4252",
        "grp_input_bdr": "#5e6779",
        "combo_popup_bg":"#434c5e",
        "combo_popup_fg":"#eceff4",
        "combo_sel_bg":  "#4c566a",
        "combo_sel_fg":  "#88c0d0",
        "list_bg":       "#2e3440",
        "list_border":   "#4c566a",
        "log_bg":        "#2e3440",
        "log_border":    "#4c566a",
        "log_fg":        "#bf616a",
        "tbl_bg":        "#2e3440",
        "tbl_grid":      "#3b4252",
        "tbl_border":    "#4c566a",
        "tbl_sel_bg":    "#4c566a",
        "tbl_sel_fg":    "#88c0d0",
        "hdr_bg":        "#3b4252",
        "hdr_fg":        "#eceff4",
        "hdr_border":    "#4c566a",
        "radio_fg":      "#eceff4",
        "tab_bg":        "#3b4252",
        "tab_fg":        "#6c7a8a",
        "tab_border":    "#4c566a",
        "tab_sel_bg":    "#2e3440",
        "tab_sel_fg":    "#88c0d0",
        "tab_sel_bdr":   "#2e3440",
        "pane_bg":       "#2e3440",
        "pane_border":   "#4c566a",
        "splitter":      "#4c566a",
        "slider_groove": "#4c566a",
        "slider_handle": "#88c0d0",
    },

    # ─────────────────────────────────────────────────────────
    # 9. GITHUB_DARK — GitHub Dark 스타일 (선명한 컨트라스트)
    # ─────────────────────────────────────────────────────────
    "github_dark": {
        "win_bg":        "#0d1117",
        "widget_fg":     "#c9d1d9",
        "group_bg":      "#161b22",
        "group_border":  "#30363d",
        "group_title":   "#58a6ff",
        "btn_bg":        "#21262d",
        "btn_fg":        "#c9d1d9",
        "btn_border":    "#30363d",
        "btn_hover":     "#30363d",
        "btn_hover_bdr": "#58a6ff",
        "btn_press":     "#388bfd",
        "input_bg":      "#0d1117",
        "input_fg":      "#c9d1d9",
        "input_border":  "#30363d",
        "grp_input_bg":  "#161b22",
        "grp_input_bdr": "#3d444d",
        "combo_popup_bg":"#161b22",
        "combo_popup_fg":"#c9d1d9",
        "combo_sel_bg":  "#1f6feb",
        "combo_sel_fg":  "#ffffff",
        "list_bg":       "#0d1117",
        "list_border":   "#30363d",
        "log_bg":        "#0d1117",
        "log_border":    "#30363d",
        "log_fg":        "#f85149",
        "tbl_bg":        "#0d1117",
        "tbl_grid":      "#21262d",
        "tbl_border":    "#30363d",
        "tbl_sel_bg":    "#1f6feb",
        "tbl_sel_fg":    "#ffffff",
        "hdr_bg":        "#161b22",
        "hdr_fg":        "#8b949e",
        "hdr_border":    "#21262d",
        "radio_fg":      "#c9d1d9",
        "tab_bg":        "#161b22",
        "tab_fg":        "#8b949e",
        "tab_border":    "#30363d",
        "tab_sel_bg":    "#0d1117",
        "tab_sel_fg":    "#58a6ff",
        "tab_sel_bdr":   "#0d1117",
        "pane_bg":       "#0d1117",
        "pane_border":   "#30363d",
        "splitter":      "#30363d",
        "slider_groove": "#21262d",
        "slider_handle": "#388bfd",
    },
}

# ── 테마 메타 ───────────────────────────────────────────────────
THEME_LABELS: dict[str, str] = {
    "light":    "☀️  라이트",
    "dark":     "🌙  다크",
    "midnight": "🌌  미드나잇",
    "matrix":   "💻  매트릭스",
    "amber":    "🟡  앰버",
    "mocha":    "☕  모카",
    "ocean":    "🌊  오션",
    "nordic":   "❄️  노르딕",
    "github_dark": "🖥  깃허브 다크",
}

THEME_ORDER: list[str] = [
    "light", "dark", "midnight", "matrix",
    "amber", "mocha", "ocean", "nordic", "github_dark",
]


# ══════════════════════════════════════════════════════════════
# 팔레트 헬퍼 함수
# ══════════════════════════════════════════════════════════════

def set_theme(name: str) -> None:
    """현재 테마를 변경합니다."""
    global CURRENT_THEME
    if name in THEME_PALETTES:
        CURRENT_THEME = name
    else:
        print(f"[경고] 알 수 없는 테마: {name!r}  사용 가능: {list(THEME_PALETTES)}")


def current_palette() -> dict[str, str]:
    """현재 테마 팔레트 반환 (런타임 참조용)."""
    return THEME_PALETTES.get(CURRENT_THEME, THEME_PALETTES["light"])


# ══════════════════════════════════════════════════════════════
# QSS 생성
# ══════════════════════════════════════════════════════════════

def make_style(fs: int = DEFAULT_FONT_SIZE, theme: str = None) -> str:
    """
    지정 테마(또는 CURRENT_THEME)로 전체 QSS 문자열 반환.

    Args:
        fs    : 기본 폰트 크기 (px)
        theme : 테마 이름. None 이면 CURRENT_THEME 사용.
    """
    t      = THEME_PALETTES.get(theme or CURRENT_THEME, THEME_PALETTES["light"])
    logfs  = max(10, fs - 4)
    tfs    = max(11, fs - 2)

    return f"""
/* ═══ 메인창 / 다이얼로그 ═══ */
QMainWindow, QDialog {{
    background-color: {t['win_bg']};
}}
QWidget {{
    background-color: transparent;
    color: {t['widget_fg']};
    font-size: {fs}px;
}}

/* ═══ 그룹박스 ═══ */
QGroupBox {{
    border: 1px solid {t['group_border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
    background-color: {t['group_bg']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    color: {t['group_title']};
}}

/* ═══ 버튼 ═══ */
QPushButton {{
    background-color: {t['btn_bg']};
    color: {t['btn_fg']};
    border: 1px solid {t['btn_border']};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: {fs}px;
}}
QPushButton:hover {{
    background-color: {t['btn_hover']};
    border-color: {t['btn_hover_bdr']};
}}
QPushButton:pressed {{
    background-color: {t['btn_press']};
    border-radius: 6px;
}}
QPushButton:checked {{
    border-radius: 6px;
    border: 2px solid {t['btn_hover_bdr']};
}}

/* ═══ 입력창 ═══ */
QLineEdit, QComboBox, QSpinBox {{
    background-color: {t['input_bg']};
    border: 1px solid {t['input_border']};
    border-radius: 6px;
    padding: 3px 8px;
    color: {t['input_fg']};
    font-size: {fs}px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {t['btn_hover_bdr']};
}}
QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox {{
    background-color: {t['grp_input_bg']};
    border: 1px solid {t['grp_input_bdr']};
    border-radius: 6px;
}}
QComboBox::drop-down {{
    border: none;
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 18px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['combo_popup_bg']};
    color: {t['combo_popup_fg']};
    selection-background-color: {t['combo_sel_bg']};
    selection-color: {t['combo_sel_fg']};
    border: 1px solid {t['input_border']};
    border-radius: 4px;
    padding: 2px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    border-radius: 3px;
    width: 14px;
}}

/* ═══ 리스트 / 텍스트 편집 ═══ */
QListWidget {{
    background-color: {t['list_bg']};
    border: 1px solid {t['list_border']};
    border-radius: 6px;
    font-size: {fs}px;
}}
QTextEdit {{
    background-color: {t['log_bg']};
    border: 1px solid {t['log_border']};
    border-radius: 6px;
    color: {t['log_fg']};
    font-family: Consolas, monospace;
    font-size: {logfs}px;
}}

/* ═══ 테이블 ═══ */
QTableWidget {{
    background-color: {t['tbl_bg']};
    gridline-color: {t['tbl_grid']};
    border: 1px solid {t['tbl_border']};
    border-radius: 6px;
    font-size: {fs}px;
}}
QTableWidget::item {{ padding: 2px; }}
QTableWidget::item:selected {{
    background-color: {t['tbl_sel_bg']};
    color: {t['tbl_sel_fg']};
}}
QHeaderView::section {{
    background-color: {t['hdr_bg']};
    color: {t['hdr_fg']};
    border: 1px solid {t['hdr_border']};
    padding: 4px;
    font-size: {fs}px;
    font-weight: bold;
}}
QHeaderView::section:first {{ border-top-left-radius: 6px; }}
QHeaderView::section:last  {{ border-top-right-radius: 6px; }}

/* ═══ 라디오 / 체크박스 ═══ */
QRadioButton, QCheckBox {{
    color: {t['radio_fg']};
    font-size: {fs}px;
}}

/* ═══ 탭 바 ═══ */
QTabBar::tab {{
    background-color: {t['tab_bg']};
    color: {t['tab_fg']};
    padding: 6px 16px;
    border: 1px solid {t['tab_border']};
    border-bottom: none;
    font-size: {tfs}px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {t['tab_sel_bg']};
    color: {t['tab_sel_fg']};
    font-weight: bold;
    border-bottom: 1px solid {t['tab_sel_bdr']};
}}
QTabBar::tab:hover:!selected {{ background-color: {t['btn_hover']}; }}
QTabWidget::pane {{
    border: 1px solid {t['pane_border']};
    border-radius: 0px 6px 6px 6px;
    background-color: {t['pane_bg']};
}}

/* ═══ 스플리터 / 슬라이더 ═══ */
QSplitter::handle {{
    background-color: {t['splitter']};
    border-radius: 2px;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background-color: {t['slider_groove']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px;
    background-color: {t['slider_handle']};
    border-radius: 7px;
    margin: -5px 0;
}}

/* ═══ 스크롤바 ═══ */
QScrollBar:vertical {{
    background: {t['win_bg']};
    width: 8px; border-radius: 4px; margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {t['splitter']};
    border-radius: 4px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover  {{ background: {t['btn_hover_bdr']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    background: {t['win_bg']};
    height: 8px; border-radius: 4px; margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {t['splitter']};
    border-radius: 4px; min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t['btn_hover_bdr']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
"""


# ══════════════════════════════════════════════════════════════
# 테마 선택 위젯 (툴바 삽입용)
# ══════════════════════════════════════════════════════════════

def make_theme_selector(parent=None, on_change=None):
    """
    8개 테마 버튼 QWidget 반환.

    Args:
        parent    : 부모 위젯
        on_change : 테마 변경 후 호출할 콜백 fn(theme_name: str)
    """
    from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup

    container = QWidget(parent)
    layout    = QHBoxLayout(container)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(3)

    btn_group = QButtonGroup(container)
    btn_group.setExclusive(True)
    _btns: dict = {}

    def _apply(theme_name: str):
        set_theme(theme_name)
        if callable(on_change):
            on_change(theme_name)

    for key in THEME_ORDER:
        btn = QPushButton(THEME_LABELS[key], container)
        btn.setCheckable(True)
        btn.setChecked(key == CURRENT_THEME)
        btn.setFixedHeight(26)
        btn.clicked.connect(lambda _, k=key: _apply(k))
        btn_group.addButton(btn)
        layout.addWidget(btn)
        _btns[key] = btn

    container._btns = _btns
    return container


# ── 하위 호환: BASE_STYLE ───────────────────────────────────────
BASE_STYLE = make_style(DEFAULT_FONT_SIZE)

# ══════════════════════════════════════════════════════════════
# 팔레트 키 목록 (참고용)
# ══════════════════════════════════════════════════════════════
# win_bg          group_bg        group_border    group_title
# btn_bg          btn_fg          btn_border      btn_hover
# btn_hover_bdr   btn_press       input_bg        input_fg
# input_border    grp_input_bg    grp_input_bdr   combo_popup_bg
# combo_popup_fg  combo_sel_bg    combo_sel_fg    list_bg
# list_border     log_bg          log_border      log_fg
# tbl_bg          tbl_grid        tbl_border      tbl_sel_bg
# tbl_sel_fg      hdr_bg          hdr_fg          hdr_border
# radio_fg        tab_bg          tab_fg          tab_border
# tab_sel_bg      tab_sel_fg      tab_sel_bdr     pane_bg
# pane_border     splitter        slider_groove   slider_handle
