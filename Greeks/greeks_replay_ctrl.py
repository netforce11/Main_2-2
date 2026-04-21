"""
greeks_replay_ctrl.py — 리플레이 컨트롤바 + 뷰 모드 라디오버튼
════════════════════════════════════════════════════════════════
ReplayPanel에서 분리된 UI 빌드 모듈.

뷰 모드 (VIEW_MODES):
  "greeks"   → Delta / Gamma / IV / Vanna
  "premium"  → Bid / Ask / Last / Mid  (콜·풋 프리미엄)
  "theory"   → Theo / Mispct / 등락률
"""

from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider,
    QLineEdit, QButtonGroup, QRadioButton, QWidget,
)
from PyQt5.QtCore import Qt

# ── 뷰 모드 정의 ──────────────────────────────────────────────
VIEW_MODES = {
    "greeks":  {
        "label":   "📐 Greeks",
        "tooltip": "Delta / Gamma / IV / Vanna",
        "cols":    ["delta", "gamma", "iv", "vanna"],
    },
    "premium": {
        "label":   "💰 프리미엄",
        "tooltip": "Bid / Ask / Mid / Last  (콜·풋 옵션값)",
        "cols":    ["bid", "ask", "mid", "last"],
    },
    "theory":  {
        "label":   "📊 이론가",
        "tooltip": "Theo(이론가) / Mispct(이론가대비%) / 등락률",
        "cols":    ["theo", "mispct", "chg_pct"],
    },
}

REPLAY_SPEEDS = {"x1": 1000, "x5": 200, "x10": 100}

_CTRL_STYLE  = (
    "background:#0a0a18;color:#ffd700;"
    "border:1px solid #2e3060;font-size:11px;padding:1px 3px;"
)
_RADIO_STYLE = (
    "QRadioButton{color:#ccc;font-size:11px;padding:2px 6px;}"
    "QRadioButton:checked{color:#ffd700;font-weight:bold;}"
    "QRadioButton::indicator{width:11px;height:11px;}"
)


# ── 빌더 함수 ─────────────────────────────────────────────────

def build_ctrl_bar(panel: QWidget) -> QVBoxLayout:
    """
    컨트롤 전체 레이아웃(VBox)을 생성하여 반환.
    panel 속성으로 위젯을 등록하므로 ReplayPanel에서 self.xxx 로 접근 가능.
    반환값을 ReplayPanel._build() 에서 vlay.addLayout() 으로 추가하면 됨.
    """
    vbox = QVBoxLayout()
    vbox.setSpacing(3)

    vbox.addLayout(_build_top_row(panel))
    vbox.addLayout(_build_view_row(panel))
    return vbox


def _build_top_row(panel: QWidget) -> QHBoxLayout:
    """날짜·만기·시간범위·불러오기·속도·재생·정지·타임스탬프 한 줄."""
    row = QHBoxLayout()
    row.setSpacing(4)

    # 날짜
    row.addWidget(_lbl("날짜:"))
    panel.cmb_day = QComboBox()
    panel.cmb_day.setMinimumWidth(100)
    panel.cmb_day.currentTextChanged.connect(panel._on_day_changed)
    row.addWidget(panel.cmb_day)

    # 만기
    row.addWidget(_lbl("만기:"))
    panel.cmb_expiry = QComboBox()
    panel.cmb_expiry.setMinimumWidth(110)
    panel.cmb_expiry.setStyleSheet(_CTRL_STYLE)
    row.addWidget(panel.cmb_expiry)

    # From / To
    for attr, caption, ph in [
        ("edit_from", "From:", "HH:MM (선택)"),
        ("edit_to",   "To:",   "HH:MM (선택)"),
    ]:
        lbl = QLabel(caption)
        lbl.setStyleSheet("color:#888;font-size:10px;border:none;")
        row.addWidget(lbl)
        edit = QLineEdit("")
        edit.setPlaceholderText(ph)
        edit.setFixedWidth(80)
        edit.setToolTip("비워두면 해당 날짜 전체 로드")
        edit.setStyleSheet(_CTRL_STYLE)
        row.addWidget(edit)
        setattr(panel, attr, edit)

    # 불러오기
    panel.btn_load = QPushButton("불러오기")
    panel.btn_load.clicked.connect(panel._load)
    row.addWidget(panel.btn_load)

    # 속도
    row.addWidget(_lbl("  속도:"))
    panel.cmb_speed = QComboBox()
    for k in REPLAY_SPEEDS:
        panel.cmb_speed.addItem(k)
    panel.cmb_speed.currentTextChanged.connect(panel._on_speed)
    row.addWidget(panel.cmb_speed)

    # 재생 / 정지
    panel.btn_play = QPushButton("재생")
    panel.btn_play.setStyleSheet(
        "background:#1a5a1a;font-weight:bold;padding:4px 12px;")
    panel.btn_play.clicked.connect(panel._toggle_play)
    row.addWidget(panel.btn_play)

    panel.btn_stop = QPushButton("정지")
    panel.btn_stop.clicked.connect(panel._stop)
    row.addWidget(panel.btn_stop)

    # 타임스탬프
    panel.lbl_ts = QLabel("-")
    panel.lbl_ts.setStyleSheet(
        "color:#ffd700;font-weight:bold;padding:0 8px;border:none;")
    row.addWidget(panel.lbl_ts)

    row.addStretch()
    return row


def _build_view_row(panel: QWidget) -> QHBoxLayout:
    """뷰 모드 라디오버튼 한 줄."""
    row = QHBoxLayout()
    row.setSpacing(2)

    row.addWidget(_lbl("보기:"))

    panel._view_group = QButtonGroup(panel)
    panel._cur_view   = "greeks"          # 기본값

    for key, meta in VIEW_MODES.items():
        rb = QRadioButton(meta["label"])
        rb.setToolTip(meta["tooltip"])
        rb.setStyleSheet(_RADIO_STYLE)
        rb.setChecked(key == "greeks")
        # lambda 캡처 주의: default arg 로 고정
        rb.toggled.connect(lambda checked, k=key, p=panel: _on_view_toggled(checked, k, p))
        panel._view_group.addButton(rb)
        row.addWidget(rb)

    row.addStretch()
    return row


def _on_view_toggled(checked: bool, key: str, panel: QWidget):
    if not checked:
        return
    panel._cur_view = key
    # 현재 렌더된 프레임 재렌더 (인덱스 유지)
    if hasattr(panel, "_cur_idx") and panel._ts_list:
        panel._render(panel._cur_idx)


# ── 헬퍼 ──────────────────────────────────────────────────────

def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("color:#888;font-size:10px;border:none;")
    return l