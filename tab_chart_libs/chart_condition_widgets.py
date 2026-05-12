"""
chart_condition_widgets.py — 조건 패널 위젯 팩토리 헬퍼
[분리] chart_condition_ui.py 에서 분리
"""
from PyQt5.QtWidgets import (
    QLabel, QLineEdit, QFrame, QSpinBox, QDoubleSpinBox
)

C_BG     = "#0d0d1a"
C_GRAY   = "#888888"
C_DIM    = "#444444"
C_PANEL  = "#0a0a18"
C_TEXT   = "#dde0f0"
C_BORDER = "#1e1e3a"
C_BORD2  = "#2a2a4a"
C_BLUE   = "#5dade2"
C_GREEN  = "#00e676"
C_ORANGE = "#FF8C00"
C_RED    = "#E24B4A"
C_YELLOW = "#ffd700"
C_TEAL   = "#1D9E75"
SS_INPUT = (f"background:{C_PANEL}; border:1px solid #2e3060;"
            f"border-radius:3px; color:{C_TEXT}; padding:2px 5px; font-size:11px;")

def _lbl(text, color=C_GRAY, bold=False):
    l = QLabel(text)
    w = "bold" if bold else "normal"
    l.setStyleSheet(f"color:{color}; font-size:11px; font-weight:{w};")
    return l

def _inp(default="", width=64):
    e = QLineEdit(default)
    e.setFixedWidth(width); e.setFixedHeight(22)
    e.setStyleSheet(SS_INPUT)
    return e

def _sep():
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C_BORDER}; margin:3px 0;")
    return f

def _vsep():
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color:{C_BORD2}; margin:0 4px;")
    return f

def _mini_title(text):
    l = QLabel(text)
    l.setStyleSheet(f"color:{C_BLUE}; font-size:10px; font-weight:bold;"
                    f"letter-spacing:0.5px; border-bottom:1px solid {C_BORDER};"
                    f"padding-bottom:2px; margin-bottom:2px;")
    return l

def _spin_widget(lo, hi, val, w=58, decimals=0, step=1):
    from PyQt5.QtWidgets import QSpinBox, QDoubleSpinBox
    if decimals == 0:
        s = QSpinBox(); s.setRange(int(lo), int(hi)); s.setValue(int(val))
    else:
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setValue(val)
        s.setDecimals(decimals); s.setSingleStep(step)
    s.setFixedWidth(w); s.setFixedHeight(22)
    s.setStyleSheet(SS_INPUT)
    return s


# ══════════════════════════════════════════════════════════════
# ConditionPanel
# ══════════════════════════════════════════════════════════════

