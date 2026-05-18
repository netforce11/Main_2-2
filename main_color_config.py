"""
main_color_config.py — 테마 전환 콜백 + 테마 버튼 바 빌더
════════════════════════════════════════════════════════════
main.py 에서 분리된 색상·테마 설정 전용 모듈.

외부에서 호출:
    from main_color_config import build_theme_bar, apply_theme

build_theme_bar(mw)
    → QWidget 반환 (menuBar().setCornerWidget 에 삽입)

apply_theme(mw, theme_name)
    → 전체 앱 테마 일괄 갱신 (외부 버튼 등에서도 호출 가능)
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QButtonGroup,
    QTableWidget,
)
from PyQt5.QtCore import Qt

from core_theme import (
    THEME_PALETTES, THEME_LABELS, THEME_ORDER,
    set_theme, make_style, DEFAULT_FONT_SIZE,
)
from core_ui import apply_theme_to_all_tables, apply_theme_to_all_frames


# ══════════════════════════════════════════════════════════════
# 테마 전환 콜백 (전체 앱 일괄 갱신)
# ══════════════════════════════════════════════════════════════

def apply_theme(mw, theme_name: str) -> None:
    """
    mw(MainWindow) 전체에 theme_name 테마를 즉시 적용.

    순서:
        ① CURRENT_THEME 변경
        ② 메인 윈도우 QSS 교체
        ③ core_ui 전역 테이블·프레임 일괄 갱신
        ④ combo 모듈 스타일 상수 재생성
        ⑤ 탭별 하드코딩 위젯 직접 갱신
        ⑥ 테마 버튼 체크 상태·스타일 동기화
    """
    set_theme(theme_name)
    t = THEME_PALETTES[theme_name]

    # ① 메인 QSS
    mw.setStyleSheet(make_style(DEFAULT_FONT_SIZE))

    # ② 전역 등록 위젯
    apply_theme_to_all_tables()
    apply_theme_to_all_frames()

    # ③ combo 모듈 상수
    try:
        import combo_constants as _cc
        import combo_ui_panel_constants as _cp
        _cc.SPLITTER_STYLE = _cc.get_splitter_style()
        _cc.TBL_STYLE      = _cc.get_tbl_style()
        _cp._TAB_STYLE     = _cp.get_tab_style()
        _cp._TBL_STYLE     = _cp.get_tbl_style()
    except Exception as e:
        print(f"[Theme] combo 상수 갱신 실패: {e}")

    # ④ 공통 QSS 스니펫
    _tbl_ss = (
        f"QTableWidget{{background:{t['tbl_bg']};color:{t['widget_fg']};"
        f"gridline-color:{t['tbl_grid']};border:1px solid {t['tbl_border']};"
        f"alternate-background-color:{t['group_bg']};}}"
        f"QTableWidget::item:selected{{background:{t['tbl_sel_bg']};color:{t['tbl_sel_fg']};}}"
        f"QHeaderView::section{{background:{t['hdr_bg']};color:{t['hdr_fg']};"
        f"border:1px solid {t['hdr_border']};font-weight:bold;padding:3px;}}"
    )
    _input_ss = (
        f"background:{t['input_bg']};color:{t['group_title']};"
        f"border:1px solid {t['input_border']};border-radius:4px;"
    )
    _combo_ss = (
        f"QComboBox{{background:{t['input_bg']};color:{t['group_title']};"
        f"border:1px solid {t['input_border']};border-radius:6px;padding:2px 6px;}}"
        f"QComboBox QAbstractItemView{{background:{t['combo_popup_bg']};"
        f"color:{t['combo_popup_fg']};"
        f"selection-background-color:{t['combo_sel_bg']};}}"
        f"QComboBox::drop-down{{border:none;}}"
    )
    _tab_ss = (
        f"QTabWidget::pane{{border:1px solid {t['pane_border']};"
        f"background:{t['pane_bg']};border-radius:0 6px 6px 6px;}}"
        f"QTabBar::tab{{background:{t['tab_bg']};color:{t['tab_fg']};"
        "padding:4px 8px;border-top-left-radius:6px;border-top-right-radius:6px;"
        f"border:1px solid {t['tab_border']};border-bottom:none;}}"
        f"QTabBar::tab:selected{{background:{t['tab_sel_bg']};color:{t['tab_sel_fg']};}}"
        f"QTabBar::tab:hover{{background:{t['btn_hover']};}}"
    )

    # ⑤-A 탭1: 콜-풋 (tab_callput)
    try:
        cp = getattr(mw, 'tab_callput', None)
        if cp:
            for attr in ('tbl_chain_call', 'tbl_chain_put', 'tbl_balance', 'tbl_orders'):
                tbl = getattr(cp, attr, None)
                if tbl:
                    tbl.setStyleSheet(_tbl_ss)
            for attr in ('edit_sym', 'edit_strike_from', 'edit_strike_to',
                         'qord_price', 'qord_side', 'qord_strike'):
                w = getattr(cp, attr, None)
                if w:
                    w.setStyleSheet(_input_ss + "font-size:14px;font-weight:bold;")
            for attr in ('combo_exp', 'combo_right', 'qord_tif', 'combo_adapt_priority'):
                w = getattr(cp, attr, None)
                if w:
                    w.setStyleSheet(_combo_ss)
            try:
                from combo_ui_left import LeftPanelMixin
                if hasattr(cp, 'tbl_chain_call'):
                    LeftPanelMixin._apply_chain_style(cp.tbl_chain_call, t['group_title'])
                if hasattr(cp, 'tbl_chain_put'):
                    LeftPanelMixin._apply_chain_style(cp.tbl_chain_put, "#ff6666")
            except Exception:
                pass
            qw = getattr(cp, '_qord_tab_widget', None)
            if qw:
                qw.setStyleSheet(_tab_ss)
    except Exception as e:
        print(f"[Theme] tab_callput 갱신 실패: {e}")

    # ⑤-B 탭2: 잔고/PnL (tab_balance)
    try:
        tb = getattr(mw, 'tab_balance', None)
        if tb:
            for attr in dir(tb):
                w = getattr(tb, attr, None)
                try:
                    if isinstance(w, QTableWidget):
                        w.setStyleSheet(_tbl_ss)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Theme] tab_balance 갱신 실패: {e}")

    # ⑤-C 탭4: 복합전략 (tab_combo)
    try:
        tc = getattr(mw, 'tab_combo', None)
        if tc:
            sp = getattr(tc, '_synthetic_panel', None)
            if sp and hasattr(sp, 'refresh_theme'):
                sp.refresh_theme()
            for attr in ('tbl_legs', 'tbl_chain_call', 'tbl_chain_put'):
                tbl = getattr(tc, attr, None)
                if tbl:
                    tbl.setStyleSheet(_tbl_ss)
            cb = getattr(tc, 'combo_strat', None)
            if cb:
                cb.setStyleSheet(_combo_ss + "font-size:14px;")
            npd = getattr(tc, 'net_price_display', None)
            if npd:
                npd.setStyleSheet(
                    f"NetPriceDisplay{{background:{t['group_bg']};"
                    f"border:1px solid {t['group_border']};border-radius:6px;}}")
                npd._btn_auto.setStyleSheet(npd._toggle_style(not npd._manual_mode))
                npd._btn_manual.setStyleSheet(npd._toggle_style(npd._manual_mode))
            db = getattr(tc, 'direction_banner', None)
            if db and hasattr(db, 'refresh'):
                tbl_legs2 = getattr(tc, 'tbl_legs', None)
                if tbl_legs2:
                    db.refresh(tbl_legs2)
                elif hasattr(db, '_apply'):
                    db._apply("none",
                        "━  레그를 설정하면 방향을 표시합니다  ━",
                        "C/P · 행사가 · BUY/SELL 조합으로 자동 판단", "")
            try:
                from combo_constants import get_splitter_style
                for attr in ('_mid_hsplit', '_main_hsplit', '_vsplit'):
                    sp2 = getattr(tc, attr, None)
                    if sp2:
                        sp2.setStyleSheet(get_splitter_style())
            except Exception:
                pass
    except Exception as e:
        print(f"[Theme] tab_combo 갱신 실패: {e}")

    # ⑤-D 탭6: Greeks Matrix (tab_greeks)
    try:
        tg = getattr(mw, 'tab_greeks', None)
        if tg:
            for attr in dir(tg):
                w = getattr(tg, attr, None)
                try:
                    if isinstance(w, QTableWidget):
                        w.setStyleSheet(_tbl_ss)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Theme] tab_greeks 갱신 실패: {e}")

    # ⑥ 테마 버튼 체크 상태 + 스타일 동기화
    _sync_theme_buttons(mw, theme_name, t)


def _sync_theme_buttons(mw, theme_name: str, t: dict) -> None:
    """테마 버튼의 체크 상태와 강조 스타일을 동기화."""
    for k, b in getattr(mw, '_theme_buttons', {}).items():
        b.setChecked(k == theme_name)
        if k == theme_name:
            b.setStyleSheet(
                f"QPushButton{{font-size:12px;border-radius:6px;padding:2px 8px;"
                f"background:{t['group_title']};color:{t['win_bg']};"
                f"border:2px solid {t['group_title']};font-weight:bold;}}"
            )
        else:
            b.setStyleSheet(
                f"QPushButton{{font-size:12px;border-radius:6px;padding:2px 8px;"
                f"background:{t['group_bg']};color:{t['group_title']};"
                f"border:1px solid {t['input_border']};}}"
                f"QPushButton:hover{{background:{t['btn_hover']};"
                f"border-color:{t['btn_hover_bdr']};}}"
            )


# ══════════════════════════════════════════════════════════════
# 테마 버튼 바 빌더
# ══════════════════════════════════════════════════════════════

def build_theme_bar(mw) -> QWidget:
    """
    8개 테마 토글 버튼이 담긴 QWidget 반환.
    mw.menuBar().setCornerWidget(build_theme_bar(mw), Qt.TopRightCorner)
    """
    import core as _core  # CURRENT_THEME 런타임 참조

    bar = QWidget()
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(4, 2, 8, 2)
    layout.setSpacing(3)

    lbl = QLabel("테마:")
    lbl.setStyleSheet("font-size:12px; font-weight:bold; border:none;")
    layout.addWidget(lbl)

    mw._theme_btn_group = QButtonGroup(bar)
    mw._theme_btn_group.setExclusive(True)
    mw._theme_buttons   = {}

    t0 = THEME_PALETTES[_core.CURRENT_THEME]

    for key in THEME_ORDER:
        btn = QPushButton(THEME_LABELS[key], bar)
        btn.setCheckable(True)
        btn.setChecked(key == _core.CURRENT_THEME)
        btn.setFixedHeight(22)
        btn.setMinimumWidth(62)

        if key == _core.CURRENT_THEME:
            btn.setStyleSheet(
                f"QPushButton{{font-size:11px;border-radius:5px;padding:1px 6px;"
                f"background:{t0['group_title']};color:{t0['win_bg']};"
                f"border:2px solid {t0['group_title']};font-weight:bold;}}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton{{font-size:11px;border-radius:5px;padding:1px 6px;"
                f"background:{t0['group_bg']};color:{t0['group_title']};"
                f"border:1px solid {t0['input_border']};}}"
                f"QPushButton:hover{{background:{t0['btn_hover']};"
                f"border-color:{t0['btn_hover_bdr']};}}"
            )

        btn.clicked.connect(lambda _, k=key: apply_theme(mw, k))
        mw._theme_btn_group.addButton(btn)
        layout.addWidget(btn)
        mw._theme_buttons[key] = btn

    return bar
