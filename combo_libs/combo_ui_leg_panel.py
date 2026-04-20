"""
combo_ui_leg_panel.py — 레그 테이블 좌측 패널 빌드
────────────────────────────────────────────────────
포함: _build_leg_left (RightPanelMixin에 mixin)
      _on_leg_item_changed / _recalc_net_price
      _set_premium_cell / _set_strategy_by_name

스트리밍 관련:
      fill_premium_from_market / _cancel_stream / cancel_all_streams
      → combo_ui_leg_stream.py 로 분리

v2.6 변경:
  - ➕ 레그 추가 / ➖ 마지막 레그 제거 버튼 (자동/수동 모드 공용)
  - 추가된 레그도 손익·증거금 계산 자동 연동
  - MAX_LEGS(8) 초과 시 버튼 자동 비활성
  - 세트 입력 패널 제거 (v2.7)
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QHeaderView,
    QLineEdit, QFrame,
)
from PyQt5.QtCore import QTimer
from combo_constants import STRATEGIES, MAX_LEGS

# Mid-price 티커 ID 범위: 8800~8815 (레그 0~15)
_TICKER_BASE = 8800


def _build_leg_left(self) -> QWidget:
    """좌측: 전략 유형 콤보 + 레그 모드 토글 + 레그 테이블 + 추가 레그 버튼."""
    w = QWidget(); v = QVBoxLayout(w)
    v.setSpacing(4); v.setContentsMargins(2, 2, 4, 2)

    # ── 전략 유형 행 ──────────────────────────────────────────
    row = QHBoxLayout()
    row.addWidget(QLabel("전략 유형:"))
    self.combo_strat = QComboBox()
    self.combo_strat.addItems(STRATEGIES)
    self.combo_strat.setStyleSheet(
        "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
        "border-radius:3px;font-size:14px;padding:3px;}"
        "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
        "selection-background-color:#1c3a6a;font-size:14px;}"
        "QComboBox::drop-down{border:none;}")
    self.combo_strat.currentIndexChanged.connect(self._on_strat_change)
    row.addWidget(self.combo_strat, 1)
    btn_info = QPushButton("❓")
    btn_info.setFixedSize(26, 26)
    btn_info.setStyleSheet(
        "QPushButton{background:#1a2a4a;color:#90caf9;border:1px solid #3a3a6a;"
        "border-radius:4px;font-size:14px;font-weight:bold;}"
        "QPushButton:hover{background:#2a3a6a;color:#ffd700;}")
    btn_info.clicked.connect(self._show_strat_desc)
    row.addWidget(btn_info)
    v.addLayout(row)

    # ── 레그 모드 행 ──────────────────────────────────────────
    mode_row = QHBoxLayout(); mode_row.setSpacing(4)
    mode_row.addWidget(QLabel("레그 설정"))
    mode_row.addStretch()
    _on  = ("QPushButton{background:#1a5c2e;color:#00ff88;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #00ff88;}"
            "QPushButton:!checked{background:#0a0a1e;color:#555;border:1px solid #333;}"
            "QPushButton:hover{background:#2a8a4a;}")
    _off = ("QPushButton{background:#0a0a1e;color:#555;font-size:10px;"
            "font-weight:bold;padding:2px 8px;border-radius:3px;border:1px solid #333;}"
            "QPushButton:checked{background:#2a1a5a;color:#ffd700;border:1px solid #ffd700;}"
            "QPushButton:hover{background:#1a1a3a;}")
    self._btn_leg_auto   = QPushButton("🔗 자동 입력")
    self._btn_leg_manual = QPushButton("✏ 수동 입력")
    for btn, style, checked in [
        (self._btn_leg_auto,   _on,  True),
        (self._btn_leg_manual, _off, False),
    ]:
        btn.setCheckable(True); btn.setChecked(checked)
        btn.setFixedHeight(22); btn.setStyleSheet(style)
    self._btn_leg_auto.clicked.connect(lambda: self._set_leg_mode("auto"))
    self._btn_leg_manual.clicked.connect(lambda: self._set_leg_mode("manual"))
    mode_row.addWidget(self._btn_leg_auto)
    mode_row.addWidget(self._btn_leg_manual)
    v.addLayout(mode_row)
    self._leg_mode = "auto"

    # ── 레그 테이블 ───────────────────────────────────────────
    self.tbl_legs = QTableWidget(0, 7)
    self.tbl_legs.setHorizontalHeaderLabels(
        ["레그", "방향", "C/P", "행사가", "프리미엄($)", "수량", "만기"])
    self.tbl_legs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.tbl_legs.verticalHeader().setVisible(False)
    self.tbl_legs.setAlternatingRowColors(True)
    self.tbl_legs.setStyleSheet(
        "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
        "color:#ccc;gridline-color:#1a1a3a;}"
        "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
        "border:1px solid #1a1a3a;font-weight:bold;}")
    v.addWidget(self.tbl_legs, 1)

    # ── 수동 모드 버튼 행 (기존) ──────────────────────────────
    self._manual_btn_row = QWidget()
    mbh = QHBoxLayout(self._manual_btn_row)
    mbh.setContentsMargins(0, 1, 0, 1); mbh.setSpacing(4)
    from combo_ui_leg_extra import _manual_add_leg, _manual_del_leg
    for text, style, fn in [
        ("➕ 레그 추가",
         "background:#1a2a4a;color:#90caf9;font-size:10px;font-weight:bold;"
         "padding:2px 8px;border-radius:3px;border:1px solid #3a5a9a;",
         lambda: _manual_add_leg(self)),
        ("➖ 레그 제거",
         "background:#2a0a1a;color:#ff6666;font-size:10px;font-weight:bold;"
         "padding:2px 8px;border-radius:3px;border:1px solid #5a1a1a;",
         lambda: _manual_del_leg(self)),
    ]:
        btn = QPushButton(text); btn.setFixedHeight(22)
        btn.setStyleSheet(style); btn.clicked.connect(fn)
        mbh.addWidget(btn)
    mbh.addWidget(QLabel("방향·C/P·행사가·프리미엄·수량·만기 직접 입력"))
    mbh.addStretch()
    self._manual_btn_row.setVisible(False)
    v.addWidget(self._manual_btn_row)

    # ── ➕ 추가 레그 버튼 행 (자동/수동 공용, v2.6 신규) ────────
    extra_row = QHBoxLayout(); extra_row.setSpacing(6)
    from combo_ui_leg_extra import _extra_add_leg, _extra_del_leg
    self._btn_extra_add = QPushButton(f"➕ 레그 추가  (최대 {MAX_LEGS}개)")
    self._btn_extra_add.setFixedHeight(24)
    self._btn_extra_add.setStyleSheet(
        "QPushButton{background:#0d2a1a;color:#44cc88;font-size:11px;"
        "font-weight:bold;padding:2px 10px;border-radius:3px;"
        "border:1px solid #1a6a3a;}"
        "QPushButton:hover{background:#1a4a2a;}"
        "QPushButton:disabled{background:#0a0a1a;color:#333;border-color:#222;}")
    self._btn_extra_add.clicked.connect(lambda: _extra_add_leg(self))

    self._btn_extra_del = QPushButton("➖ 마지막 레그 제거")
    self._btn_extra_del.setFixedHeight(24)
    self._btn_extra_del.setStyleSheet(
        "QPushButton{background:#2a0d0d;color:#cc4444;font-size:11px;"
        "font-weight:bold;padding:2px 10px;border-radius:3px;"
        "border:1px solid #6a1a1a;}"
        "QPushButton:hover{background:#4a1a1a;}"
        "QPushButton:disabled{background:#0a0a1a;color:#333;border-color:#222;}")
    self._btn_extra_del.clicked.connect(lambda: _extra_del_leg(self))

    extra_row.addWidget(self._btn_extra_add)
    extra_row.addWidget(self._btn_extra_del)
    extra_row.addStretch()
    v.addLayout(extra_row)

    # ── 방향 배너 ─────────────────────────────────────────────
    from combo_direction_banner import DirectionBanner
    self.direction_banner = DirectionBanner(self)
    v.addWidget(self.direction_banner)

    # ── Net Price 라벨 ────────────────────────────────────────
    self.lbl_net_price = QLabel("Net Price: —")
    self.lbl_net_price.setStyleSheet(
        "QLabel{background:#0a0a1e;color:#aaa;font-size:12px;font-weight:bold;"
        "border:1px solid #2a2a4a;border-radius:3px;padding:3px 8px;}")
    v.addWidget(self.lbl_net_price)

    # 재귀 방지 플래그 + itemChanged 연결
    self._leg_item_changing = False
    self._mid_ticks: dict   = {}
    self.tbl_legs.itemChanged.connect(
        lambda item: _on_leg_item_changed(self, item))
    self.tbl_legs.itemChanged.connect(
        lambda item: self.direction_banner.refresh(self.tbl_legs))

    return w


# ── Net Price 재계산 ─────────────────────────────────────────

def _on_leg_item_changed(self, item):
    if getattr(self, '_leg_item_changing', False):
        return
    if item.column() in (4, 5):
        _recalc_net_price(self)


def _recalc_net_price(self) -> float:
    rows = self.tbl_legs.rowCount()
    buy_total = sell_total = 0.0
    for r in range(rows):
        def _cell(c, _r=r):
            it = self.tbl_legs.item(_r, c)
            return it.text().strip() if it else ""
        direction = _cell(1).upper()
        prem_str  = _cell(4)
        qty_str   = _cell(5)
        if not prem_str or prem_str in ("―", ""):
            continue
        try:
            prem = float(prem_str)
            qty  = int(qty_str) if qty_str else 1
        except ValueError:
            continue
        if direction == "BUY":
            buy_total  += prem * qty
        else:
            sell_total += prem * qty

    net       = round(buy_total - sell_total, 2)
    lmt_price = round(abs(net), 2)
    lbl = getattr(self, 'lbl_net_price', None)
    if lbl is None:
        return lmt_price
    if lmt_price == 0.0:
        lbl.setText("Net Price: —")
        lbl.setStyleSheet(
            "QLabel{background:#0a0a1e;color:#aaa;font-size:12px;font-weight:bold;"
            "border:1px solid #2a2a4a;border-radius:3px;padding:3px 8px;}")
        return 0.0
    if net >= 0:
        label = f"Net Debit:  ${lmt_price:.2f}  (지불)"
        color = "#ff8888"
    else:
        label = f"Net Credit: ${lmt_price:.2f}  (수취)"
        color = "#00ff88"
    lbl.setText(label)
    lbl.setStyleSheet(
        f"QLabel{{background:#0a0a1e;color:{color};font-size:12px;font-weight:bold;"
        f"border:1px solid #2a2a4a;border-radius:3px;padding:3px 8px;}}")
    return lmt_price


# ── 스트리밍 API (combo_ui_leg_stream.py 에서 re-export) ─────

def fill_premium_from_market(self, row: int, con_id: int):
    from combo_ui_leg_stream import fill_premium_from_market as _f
    _f(self, row, con_id)


def _cancel_stream(self, ticker_id: int):
    from combo_ui_leg_stream import _cancel_stream as _f
    _f(self, ticker_id)


def cancel_all_streams(self):
    from combo_ui_leg_stream import cancel_all_streams as _f
    _f(self)


def _set_premium_cell(self, row: int, value: float):
    from combo_ui_leg_stream import _set_premium_cell as _f
    _f(self, row, value)


# ── 세트 입력 / 단축키 위임 (하위 호환 유지) ────────────────────

def _apply_set_input(self, sell_edit, buy_edit):
    from combo_ui_leg_setinput import _apply_set_input as _f
    _f(self, sell_edit, buy_edit)


def _set_strategy_by_name(self, strat_name: str):
    from combo_ui_leg_setinput import _set_strategy_by_name as _f
    _f(self, strat_name)