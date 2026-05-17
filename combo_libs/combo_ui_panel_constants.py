"""combo_ui_panel_constants.py — 공통 상수 · 스타일 · 폰트 헬퍼

SyntheticStatusPanel 관련 모듈에서 공유하는 상수/스타일을 한 곳에 모읍니다.
다른 모듈에서: from combo_ui_panel_constants import _f, get_tab_style, get_tbl_style

[테마 연동 수정]
- _TAB_STYLE / _TBL_STYLE 하드코딩 제거
- get_tab_style() / get_tbl_style() 함수로 대체 → 테마 전환 즉시 반영
- 하위 호환: _TAB_STYLE / _TBL_STYLE 변수는 유지 (모듈 로드 시 1회 생성)
"""
from PyQt5.QtGui import QFont


def _f(pt: int, bold: bool = False) -> QFont:
    """포인트 크기·굵기를 지정한 QFont 반환."""
    f = QFont()
    f.setPointSize(pt)
    if bold:
        f.setBold(True)
    return f


# ── 테마 팔레트 참조 헬퍼 ─────────────────────────────────────
def _pal() -> dict:
    """현재 CURRENT_THEME 팔레트 반환 (런타임 참조)."""
    try:
        import core as _core
        return _core.THEME_PALETTES.get(_core.CURRENT_THEME,
                                        _core.THEME_PALETTES["light"])
    except Exception:
        return {
            "pane_bg": "#ffffff", "pane_border": "#cbd5e1",
            "tab_bg": "#e5e7eb", "tab_fg": "#4b5563",
            "tab_border": "#cbd5e1", "tab_sel_bg": "#ffffff",
            "tab_sel_fg": "#1d4ed8", "btn_hover_bdr": "#94a3b8",
            "tbl_bg": "#ffffff", "group_bg": "#e5e7eb",
            "widget_fg": "#111827", "tbl_grid": "#e5e7eb",
            "tbl_border": "#9ca3af", "tbl_sel_bg": "#dbeafe",
            "tbl_sel_fg": "#1e40af", "hdr_bg": "#e5e7eb",
            "hdr_fg": "#111827", "hdr_border": "#cbd5e1",
        }


def get_tab_style() -> str:
    """현재 테마에 맞는 QTabWidget QSS 반환."""
    t = _pal()
    return (
        f"QTabWidget::pane{{border:1px solid {t['pane_border']};"
        f"background:{t['pane_bg']};border-radius:0px 6px 6px 6px;}}"
        f"QTabBar::tab{{background:{t['tab_bg']};color:{t['tab_fg']};"
        f"padding:5px 12px;border:1px solid {t['tab_border']};"
        f"border-bottom:none;border-top-left-radius:6px;border-top-right-radius:6px;"
        f"margin-right:2px;}}"
        f"QTabBar::tab:selected{{background:{t['tab_sel_bg']};color:{t['tab_sel_fg']};"
        f"border-top:2px solid {t['btn_hover_bdr']};}}"
        f"QTabBar::tab:hover{{color:{t['btn_hover_bdr']};}}"
    )


def get_tbl_style() -> str:
    """현재 테마에 맞는 QTableWidget QSS 반환."""
    t = _pal()
    return (
        f"QTableWidget{{background:{t['tbl_bg']};"
        f"alternate-background-color:{t['group_bg']};"
        f"color:{t['widget_fg']};gridline-color:{t['tbl_grid']};"
        f"border:none;border-radius:4px;}}"
        f"QTableWidget::item:selected{{background:{t['tbl_sel_bg']};"
        f"color:{t['tbl_sel_fg']};}}"
        f"QHeaderView::section{{background:{t['hdr_bg']};color:{t['hdr_fg']};"
        f"border:1px solid {t['hdr_border']};font-weight:bold;padding:3px 6px;}}"
    )


# ── 하위 호환: 기존 코드에서 _TAB_STYLE / _TBL_STYLE 을 직접 참조하는 경우
# 모듈 로드 시 한 번 생성됩니다. 테마 전환 후엔 get_tab_style() / get_tbl_style() 을 호출하세요.
_TAB_STYLE = get_tab_style()
_TBL_STYLE = get_tbl_style()