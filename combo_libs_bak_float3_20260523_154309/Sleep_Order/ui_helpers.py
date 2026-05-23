"""
ui_helpers.py — Sleep Order UI 공통 헬퍼  v1.0
════════════════════════════════════════
스타일 헬퍼 함수 + KST/ET 변환 유틸
모든 UI 패널 파일에서 import 해서 사용.
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QLabel, QPushButton, QSpinBox,
    QDoubleSpinBox, QTimeEdit, QFrame, QComboBox, QCheckBox,
)
from PyQt5.QtCore import Qt, QTime


# ══ KST ↔ ET 변환 ═══════════════════════════════════════════════

def _is_edt() -> bool:
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/New_York")
    except Exception:
        try:
            from backports.zoneinfo import ZoneInfo
            tz = ZoneInfo("America/New_York")
        except Exception:
            return False
    return datetime.now(tz).utcoffset().total_seconds() == -4 * 3600


def kst_to_et(hhmm: str) -> str:
    try:
        h, m = map(int, hhmm.split(":"))
        off  = 13 if _is_edt() else 14
        t    = (h * 60 + m - off * 60) % (24 * 60)
        return f"{t//60:02d}:{t%60:02d}"
    except Exception:
        return hhmm


def et_to_kst(hhmm: str) -> str:
    try:
        h, m = map(int, hhmm.split(":"))
        off  = 13 if _is_edt() else 14
        t    = (h * 60 + m + off * 60) % (24 * 60)
        return f"{t//60:02d}:{t%60:02d}"
    except Exception:
        return hhmm


# ══ 스타일 헬퍼 ══════════════════════════════════════════════════

def gb(title: str, color: str = "#5dade2") -> QGroupBox:
    g = QGroupBox(title)
    g.setStyleSheet(
        f"QGroupBox{{font-size:16px;color:{color};font-weight:bold;"
        f"border:1px solid #2a2a5a;border-radius:6px;"
        f"margin-top:10px;padding-top:8px;}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;}}")
    return g


def lbl(text: str, color: str = "#dde0f0", size: int = 16) -> QLabel:
    w = QLabel(text)
    w.setStyleSheet(f"color:{color};font-size:{size}px;border:none;")
    return w


def btn(text: str, bg: str = "#1c1c3a", fg: str = "#dde0f0") -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton{{background:{bg};color:{fg};font-size:16px;"
        f"border:1px solid #3a3a7a;border-radius:4px;padding:4px 14px;}}"
        f"QPushButton:hover{{background:#2a2a5a;color:#fff;}}"
        f"QPushButton:pressed{{background:#0e0e2a;}}")
    return b


def spinbox(mn, mx, val, suffix="") -> QSpinBox:
    sb = QSpinBox()
    sb.setMinimum(mn); sb.setMaximum(mx); sb.setValue(val)
    if suffix:
        sb.setSuffix(f" {suffix}")
    sb.setFixedWidth(110)
    sb.setStyleSheet(
        "QSpinBox{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}")
    return sb


def dspinbox(mn: float, mx: float, val: float,
             step: float = 0.05, decimals: int = 2,
             prefix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setMinimum(mn); sb.setMaximum(mx)
    sb.setValue(val); sb.setSingleStep(step); sb.setDecimals(decimals)
    if prefix:
        sb.setPrefix(prefix)
    sb.setFixedWidth(110)
    sb.setStyleSheet(
        "QDoubleSpinBox{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}")
    return sb


def time_edit(hhmm: str = "04:40") -> QTimeEdit:
    te = QTimeEdit()
    try:
        h, m = map(int, hhmm.split(":"))
        te.setTime(QTime(h, m))
    except Exception:
        te.setTime(QTime(4, 40))
    te.setDisplayFormat("HH:mm"); te.setFixedWidth(80)
    te.setStyleSheet(
        "QTimeEdit{background:#0a0a18;border:1px solid #2e3060;font-size:16px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}")
    return te


def combo(items: list, width: int = 200) -> QComboBox:
    """items: [(label, data), ...]"""
    c = QComboBox()
    for text, data in items:
        c.addItem(text, data)
    c.setFixedWidth(width)
    c.setStyleSheet(
        "QComboBox{background:#0a0a18;border:1px solid #2e3060;font-size:14px;"
        "border-radius:4px;padding:3px 6px;color:#dde0f0;}"
        "QComboBox::drop-down{border:none;width:20px;}"
        "QComboBox QAbstractItemView{background:#0d0d20;color:#dde0f0;"
        "selection-background-color:#2a2a5a;}")
    return c


def checkbox(text: str, color: str = "#dde0f0",
             indicator_color: str = "#5dade2") -> QCheckBox:
    cb = QCheckBox(text)
    cb.setStyleSheet(
        f"QCheckBox{{color:{color};font-size:14px;border:none;font-weight:bold;}}"
        f"QCheckBox::indicator{{width:16px;height:16px;}}"
        f"QCheckBox::indicator:checked{{background:#0a1a3a;"
        f"border:2px solid {indicator_color};border-radius:3px;}}"
        f"QCheckBox::indicator:unchecked{{background:#0a0a18;"
        f"border:1px solid #3a3a7a;border-radius:3px;}}")
    return cb


def sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;")
    return f


def spike_btn_style(active: bool) -> str:
    if active:
        return ("QPushButton{background:#3a0a0a;color:#ff4444;"
                "font-size:14px;font-weight:bold;"
                "border:2px solid #ff4444;border-radius:4px;padding:4px 12px;}"
                "QPushButton:hover{background:#5a1010;}")
    return ("QPushButton{background:#1c1c3a;color:#666;"
            "font-size:14px;font-weight:bold;"
            "border:1px solid #3a3a7a;border-radius:4px;padding:4px 12px;}"
            "QPushButton:hover{background:#2a2a5a;color:#aaa;}")


def load_kst_time(te: QTimeEdit, et_value: str) -> None:
    """ET 저장값 → KST 로 변환해서 QTimeEdit 에 설정."""
    try:
        kst = et_to_kst(et_value)
        h, m = map(int, kst.split(":"))
        te.setTime(QTime(h, m))
    except Exception:
        pass


def update_et_preview(te: QTimeEdit, lbl_widget: QLabel) -> None:
    """QTimeEdit KST 값 → ET 변환해서 라벨 갱신."""
    kst = te.time().toString("HH:mm")
    tz  = "EDT" if _is_edt() else "EST"
    lbl_widget.setText(f"→ {kst_to_et(kst)} {tz}")
