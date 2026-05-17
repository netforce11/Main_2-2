"""
core.py — 공통 상수 / 시그널 브릿지 / IBKR 래퍼 / 헬퍼 함수
════════════════════════════════════════════════════════════════
모든 탭 모듈이 이 파일에서 import 합니다.
변경 사항: 설정 상수, reqId 범위, 종목 파라미터, 스타일

【경로 수정】 2026-04-23
- SAVE_DIR: data → /home/netforce/US_Data/Data
- GREEKS_HISTORY_DIR: (신규) → /home/netforce/US_Data/Greeks_history
"""

import os, json, csv
from datetime import datetime, timedelta, time as dt_time, date as dt_date
from pathlib import Path
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo   # pip install backports.zoneinfo
    except ImportError:
        # 최후 fallback: pytz 사용
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

# ── ibapi ─────────────────────────────────────────────────────
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IBAPI_AVAILABLE = True
except ModuleNotFoundError:
    IBAPI_AVAILABLE = False
    print("[경고] ibapi 미설치 → pip install ibapi")

# ── pyqtgraph ─────────────────────────────────────────────────
try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QPushButton, QSlider, QSizeGrip, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QBrush

# ══════════════════════════════════════════════════════════════
# 1. 전역 설정 상수 (【경로 수정】)
# ══════════════════════════════════════════════════════════════
TWS_HOST   = "127.0.0.1"
TWS_PORT   = 4001
CLIENT_ID  = 1

# 【경로 수정】기본 경로: /home/netforce/US_Data/
BASE_DATA_DIR = Path("/home/netforce/US_Data")

# SAVE_DIR: JSON, CSV, 설정 저장
SAVE_DIR = BASE_DATA_DIR / "Data"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# GREEKS_HISTORY_DIR: Greeks DB 저장
GREEKS_HISTORY_DIR = BASE_DATA_DIR / "Greeks_history"
GREEKS_HISTORY_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FONT_SIZE  = 16
ALERT_COOLDOWN     = 600           # 추적기 재알림 쿨다운 (초)
N_STRIKES          = 24            # 콜/풋 테이블 최대 행 수 (SpinBox로 실제 사용 수 조절)
GREEKS_MATRIX_N    = 20            # Greeks Matrix ATM 기준 상하 개수
GREEKS_AUTOSAVE_S  = 15            # Greeks 자동저장 주기 (초)

# ── reqId 범위 (겹치지 않게 100 단위로 구분) ──────────────────
REQ_UND       = 1          # 기초자산 현재가
REQ_CALL      = 1000       # 콜 옵션 1000~1099
REQ_PUT       = 2000       # 풋 옵션 2000~2099
REQ_MULTI     = 3000       # 복수현재가 3000~3299 (슬롯당 100)
REQ_CHAIN     = 4000       # Greeks Matrix 콜 4000~4199
REQ_CHAIN_P   = 4200       # Greeks Matrix 풋 4200~4399
REQ_OI        = 5000       # OI 조회 5000~5499
REQ_HIST      = 6000       # IBKR 히스토리 6000~6099
REQ_SNIPER    = 7000       # 스나이퍼 시세 7000~7499
REQ_ACCT      = 9001

# ── 종목 파라미터 ─────────────────────────────────────────────
# symbol → (secType, exchange, multiplier, strike_step)
SYMBOL_CFG = {
    # symbol → (secType, exchange, multiplier, strike_step)
    # exchange는 reqMktData 기준 → 인덱스/주식 옵션 모두 SMART
    # tradingClass는 make_opt_contract에서 별도 설정
    "SPX":   ("OPT", "SMART", "100",  5),
    "SPXW":  ("OPT", "SMART", "100",  5),
    "NDX":   ("OPT", "SMART", "100", 25),
    "RUT":   ("OPT", "SMART", "100",  5),
    "VIX":   ("OPT", "SMART", "100",  1),
    "XSP":   ("OPT", "SMART", "100",  1),
    "AAPL":  ("OPT", "SMART", "100",  1),
    "TSLA":  ("OPT", "SMART", "100",  2),
    "NVDA":  ("OPT", "SMART", "100",  2),
    "AMZN":  ("OPT", "SMART", "100",  2),
    "MSFT":  ("OPT", "SMART", "100",  2),
    "META":  ("OPT", "SMART", "100",  2),
    "GOOG":  ("OPT", "SMART", "100",  2),
    "GOOGL": ("OPT", "SMART", "100",  2),
    "QQQ":   ("OPT", "SMART", "100",  1),
    "SPY":   ("OPT", "SMART", "100",  1),
    "IWM":   ("OPT", "SMART", "100",  1),
    "CL":    ("FOP", "NYMEX", "1000", 1),   # 원유 선물 옵션 (20분 지연)
}
DEFAULT_CFG  = ("OPT", "SMART", "100", 1)
INDEX_SYM    = {"SPX","SPXW","NDX","RUT","VIX","DJX","XSP"}
FUT_SYM      = {"CL"}   # 선물 기초자산 (secType="FUT", exchange="NYMEX")

ACCT_TAGS = ("NetLiquidation,TotalCashValue,BuyingPower,"
             "UnrealizedPnL,RealizedPnL,GrossPositionValue,"
             "MaintMarginReq,InitMarginReq")
# ══════════════════════════════════════════════════════════════
# 2. 테마 시스템 (5가지 테마 선택 가능)
# ══════════════════════════════════════════════════════════════
#
# 테마 목록:
#   "light"       — 밝은 회색 (기존 기본 테마)
#   "dark"        — 다크 차콜 (눈 피로 최소화)
#   "midnight"    — 미드나잇 블루 (딥 다크 + 블루 강조)
#   "matrix"      — 매트릭스 터미널 (검정 + 초록)
#   "amber"       — 앰버 나이트 (검정 + 황금)
#
# 사용법 (main.py 등):
#   from core import make_style, set_theme, CURRENT_THEME
#   set_theme("dark")          # 테마 변경
#   app.setStyleSheet(make_style(16))
# ══════════════════════════════════════════════════════════════

CURRENT_THEME = "light"   # 기본값

THEME_PALETTES = {
    # ─────────────────────────────────────────────────────────
    # 1. LIGHT — 밝은 회색 (기존 기본 테마, 주간 트레이딩)
    # ─────────────────────────────────────────────────────────
    "light": {
        "win_bg":        "#d1d5db",   # 메인창 배경
        "widget_fg":     "#111827",   # 기본 글자
        "group_bg":      "#e5e7eb",   # 그룹박스 배경
        "group_border":  "#a1a1aa",   # 그룹박스 테두리
        "group_title":   "#1e40af",   # 그룹박스 타이틀
        "btn_bg":        "#f3f4f6",   # 버튼 배경
        "btn_fg":        "#111827",   # 버튼 글자
        "btn_border":    "#cbd5e1",
        "btn_hover":     "#e2e8f0",
        "btn_hover_bdr": "#94a3b8",
        "btn_press":     "#cbd5e1",
        "input_bg":      "#ffffff",   # 입력창 배경
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
        "log_fg":        "#b91c1c",   # 로그 글자 (빨강)
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
    # 2. DARK — 다크 차콜 (야간 트레이딩, 눈 피로 최소화)
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
    # 3. MIDNIGHT — 미드나잇 블루 (딥 다크 + 블루 강조)
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
    # 4. MATRIX — 매트릭스 터미널 (검정 + 형광 초록)
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
    # 5. AMBER — 앰버 나이트 (검정 + 황금 호박색, 빈티지 터미널)
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
}

# 테마 이름 → 표시명 (버튼용)
THEME_LABELS = {
    "light":    "☀️  라이트",
    "dark":     "🌙  다크",
    "midnight": "🌌  미드나잇",
    "matrix":   "💻  매트릭스",
    "amber":    "🟡  앰버",
}

THEME_ORDER = ["light", "dark", "midnight", "matrix", "amber"]

# ── 테마 전환 함수 ────────────────────────────────────────────
def set_theme(name: str) -> None:
    """현재 테마를 변경합니다. make_style() 호출 전에 실행하세요."""
    global CURRENT_THEME
    if name in THEME_PALETTES:
        CURRENT_THEME = name
    else:
        print(f"[경고] 알 수 없는 테마: {name!r}. 사용 가능: {list(THEME_PALETTES)}")


def make_style(fs: int = DEFAULT_FONT_SIZE, theme: str = None) -> str:
    """
    지정 테마(또는 CURRENT_THEME)로 QSS 문자열을 반환합니다.

    매개변수:
        fs    — 기본 폰트 크기
        theme — 테마 이름 (None이면 CURRENT_THEME 사용)
    """
    t = THEME_PALETTES.get(theme or CURRENT_THEME, THEME_PALETTES["light"])
    logfs = max(10, fs - 4)
    tfs   = max(11, fs - 2)

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

/* ═══ 입력창 (LineEdit / ComboBox / SpinBox) ═══ */
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
QTableWidget::item {{
    padding: 2px;
}}
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
QHeaderView::section:first {{
    border-top-left-radius: 6px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 6px;
}}

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
QTabBar::tab:hover:!selected {{
    background-color: {t['btn_hover']};
}}
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
    width: 14px;
    height: 14px;
    background-color: {t['slider_handle']};
    border-radius: 7px;
    margin: -5px 0;
}}

/* ═══ 스크롤바 ═══ */
QScrollBar:vertical {{
    background: {t['win_bg']};
    width: 8px;
    border-radius: 4px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {t['splitter']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['btn_hover_bdr']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {t['win_bg']};
    height: 8px;
    border-radius: 4px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {t['splitter']};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t['btn_hover_bdr']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""


# ── 테마 선택 위젯 (메인 툴바 등에 삽입용) ───────────────────
def make_theme_selector(parent=None, on_change=None):
    """
    5개 테마 버튼이 담긴 QWidget을 반환합니다.

    매개변수:
        parent    — 부모 위젯
        on_change — 테마 변경 후 호출할 콜백 fn(theme_name: str)
                    (예: lambda t: app.setStyleSheet(make_style()))
    사용 예:
        selector = make_theme_selector(self, on_change=lambda t: app.setStyleSheet(make_style()))
        toolbar_layout.addWidget(selector)
    """
    from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QButtonGroup

    container = QWidget(parent)
    layout    = QHBoxLayout(container)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(3)

    btn_group = QButtonGroup(container)
    btn_group.setExclusive(True)

    _btns = {}

    def _apply(theme_name):
        set_theme(theme_name)
        if callable(on_change):
            on_change(theme_name)

    for key in THEME_ORDER:
        label = THEME_LABELS[key]
        btn   = QPushButton(label, container)
        btn.setCheckable(True)
        btn.setChecked(key == CURRENT_THEME)
        btn.setFixedHeight(26)
        btn.clicked.connect(lambda _, k=key: _apply(k))
        btn_group.addButton(btn)
        layout.addWidget(btn)
        _btns[key] = btn

    container._btns = _btns   # 외부에서 참조 가능
    return container


# ── 하위 호환: BASE_STYLE (직접 참조하는 코드가 있을 경우) ─────
# 기존 코드에서 BASE_STYLE 을 직접 사용한다면 현재 테마 스타일로 대체됩니다.
@property
def _BASE_STYLE_compat():
    return make_style(DEFAULT_FONT_SIZE)
BASE_STYLE = make_style(DEFAULT_FONT_SIZE)   # 모듈 로드 시 한 번 생성 (하위 호환)


# ══════════════════════════════════════════════════════════════
# 3. 시그널 브릿지 (스레드 → Qt UI 안전 통신)
# ══════════════════════════════════════════════════════════════
class SignalBridge(QObject):
    tick_price     = pyqtSignal(int, int, float)
    tick_option    = pyqtSignal(int, int, float, float, float, float, float, float)
    connected      = pyqtSignal()
    error_sig      = pyqtSignal(int, int, str)
    # 계좌
    acct_value     = pyqtSignal(str, str, str, str)   # tag,val,cur,acct
    acct_end       = pyqtSignal()
    # 포지션
    position_sig   = pyqtSignal(str, str, str, float, float)
    position_end   = pyqtSignal()
    # 미체결
    open_order_sig = pyqtSignal(int, str, str, str, float, float, str)
    # 체결 (execDetails)
    exec_sig       = pyqtSignal(int, str, str, float, float)  # oid,sym,side,qty,price
    # 주문 상태
    order_status_sig = pyqtSignal(int, str, float, float, float)  # oid,status,filled,remaining,avgFillPrice
    # whatIf 증거금 조회 결과
    whatif_sig = pyqtSignal(int, float, float, float, float, str)  # oid,initBefore,initAfter,maintBefore,maintAfter,commission
    # contractDetails — BAG conId 조회용
    contract_details_sig = pyqtSignal(int, object)   # reqId, contractDetails
    contract_details_end_sig = pyqtSignal(int)        # reqId
    # 히스토리
    hist_bar       = pyqtSignal(int, dict)   # bar를 dict로 직렬화 후 emit (object는 cross-thread 크래시)
    hist_end       = pyqtSignal(int)
    hist_ticks     = pyqtSignal(int, list, bool)  # reqId, ticks(list of dict), done
    hist_bar_update = pyqtSignal(int, dict)
    # ── 체결 마커용 (chart_exec_marker.py 에서 수신) ─────────
    exec_filled     = pyqtSignal(int, str, float)  # (ts_ms, 'BUY'|'SELL', fill_price)

# 전역 브릿지 싱글턴
bridge = SignalBridge()

# ══════════════════════════════════════════════════════════════
# 비동기 tick 라우터
# ── 탭별 reqId 범위를 등록해두고 tick이 오면 해당 탭의
#    전용 슬롯으로만 emit → 탭 간 상호 간섭·처리 지연 최소화
# ══════════════════════════════════════════════════════════════
class TickRouter(QObject):
    """
    tick_price / tick_option 시그널을 reqId 범위로 분기한다.
    각 탭은 register(rid_start, rid_end, slot) 으로 구독,
    전역 bridge.tick_price 를 직접 연결하는 대신 이 라우터를
    경유하면 불필요한 탭까지 wake-up 되는 현상을 방지한다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._price_routes  = []   # [(start,end,slot), ...]
        self._option_routes = []
        bridge.tick_price.connect(self._route_price,  Qt.QueuedConnection)
        bridge.tick_option.connect(self._route_option, Qt.QueuedConnection)

    def register_price(self, rid_start: int, rid_end: int, slot):
        self._price_routes.append((rid_start, rid_end, slot))

    def register_option(self, rid_start: int, rid_end: int, slot):
        self._option_routes.append((rid_start, rid_end, slot))

    def unregister_price(self, slot):
        self._price_routes = [(s,e,fn) for s,e,fn in self._price_routes if fn!=slot]

    def unregister_option(self, slot):
        self._option_routes = [(s,e,fn) for s,e,fn in self._option_routes if fn!=slot]

    def _route_price(self, rid: int, tt: int, price: float):
        for start, end, slot in self._price_routes:
            if start <= rid <= end:
                try: slot(rid, tt, price)
                except Exception as ex: print(f"[Router] price slot err: {ex}")
        # ── 틱/호가 속도 인디케이터 (chart_tick_speed.py) ─────
        if tt in (1, 2, 4):   # Bid=1, Ask=2, Last=4
            try:
                from chart_tick_speed import on_ibkr_tick
                on_ibkr_tick(tt, price)
            except Exception:
                pass

    def _route_option(self, rid: int, tt: int, iv, delta, op, gamma, vega, theta):
        for start, end, slot in self._option_routes:
            if start <= rid <= end:
                try: slot(rid, tt, iv, delta, op, gamma, vega, theta)
                except Exception as ex: print(f"[Router] option slot err: {ex}")

# 전역 라우터 싱글턴 (main.py 에서 초기화 후 각 탭이 사용)
router = TickRouter()


# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
# Re-export — 기존 import 호환성 유지
# 다른 모듈에서 "from core import ..." 가 그대로 동작하도록
# ══════════════════════════════════════════════════════════════
from core_expiry import (
    _easter, _us_market_holidays, _HOLIDAY_CACHE,
    is_trading_day, next_wd, next_trading_friday, build_expiry_list,
)
from core_io import (
    save_json, load_json, append_csv, load_csv,
    is_market_open, auto_mdt,
)
from core_ui import (
    _all_tables, _apply_table_theme, make_table, tbl_set,
    ts, ts_full, _FloatWin, _ResizableFrame, GridTab,
)
from core_tab_wrapper import TabWrapper
from core_contract import IBapi, make_opt_contract, make_und_contract, _resolve_spx_trading_class
# FUT_SYM 은 core.py 자체에서 정의 — re-export 불필요