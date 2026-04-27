"""
combo_ui_leg_panel.py — 레그 테이블 좌측 패널 빌드
────────────────────────────────────────────────────
v3.1 버그 수정:
  BUG-9  _on_leg_item_changed에서 _update_guide_btn_state 제거
         → combo_strat.currentIndexChanged에만 연결
  BUG-13 가이드가 없는 전략에서 📋 버튼을 hide()로 숨김
         (비활성이 아닌 미표시 → UX 혼란 제거)
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QHeaderView,
    QLineEdit, QFrame,
)
from PyQt5.QtCore import QTimer
from combo_constants import STRATEGIES, MAX_LEGS, STRATEGY_SETUP_GUIDE
from combo_ui_net_price_display import NetPriceDisplay

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

    # ❓ 전략 설명 버튼
    btn_info = QPushButton("❓")
    btn_info.setFixedSize(26, 26)
    btn_info.setToolTip("전략 설명 보기")
    btn_info.setStyleSheet(
        "QPushButton{background:#1a2a4a;color:#90caf9;border:1px solid #3a3a6a;"
        "border-radius:4px;font-size:14px;font-weight:bold;}"
        "QPushButton:hover{background:#2a3a6a;color:#ffd700;}")
    btn_info.clicked.connect(self._show_strat_desc)
    row.addWidget(btn_info)

    # 📋 전략 구성 가이드 버튼 (v3.0 신규 / v3.1 BUG-13 수정)
    btn_guide = QPushButton("📋")
    btn_guide.setFixedSize(26, 26)
    btn_guide.setToolTip("전략 구성 가이드 보기")
    btn_guide.setStyleSheet(
        "QPushButton{background:#1a3a1a;color:#44cc88;border:1px solid #2a6a2a;"
        "border-radius:4px;font-size:14px;}"
        "QPushButton:hover{background:#2a5a2a;color:#88ff44;}")
    btn_guide.clicked.connect(lambda: _show_guide_popup(self))
    self._btn_guide = btn_guide
    row.addWidget(btn_guide)
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

    # ── 수동 모드 버튼 행 ─────────────────────────────────────
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

    # ── ➕ 추가 레그 버튼 행 (자동/수동 공용) ─────────────────
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

    # ── Net Price 전광판 ──────────────────────────────────────
    self.net_price_display = NetPriceDisplay(self)
    v.addWidget(self.net_price_display)

    # 재귀 방지 플래그 + itemChanged 연결
    self._leg_item_changing = False
    self._mid_ticks: dict   = {}
    self.tbl_legs.itemChanged.connect(
        lambda item: _on_leg_item_changed(self, item))
    self.tbl_legs.itemChanged.connect(
        lambda item: self.direction_banner.refresh(self.tbl_legs))

    # BUG-9: 가이드 버튼 상태는 콤보박스 변경 시에만 갱신
    self.combo_strat.currentIndexChanged.connect(
        lambda _: _update_guide_btn_state(self))

    # 초기 상태 적용
    _update_guide_btn_state(self)

    return w


# ── 가이드 버튼 표시/숨김 ────────────────────────────────────

def _update_guide_btn_state(self):
    """
    현재 전략에 구성 가이드가 있으면 📋 버튼을 show(), 없으면 hide().
    BUG-13 수정: setEnabled(False) 대신 setVisible(False)로 혼란 제거.
    BUG-9  수정: combo_strat.currentIndexChanged에서만 호출
                 (_on_leg_item_changed에서 제거).
    """
    btn = getattr(self, '_btn_guide', None)
    if btn is None:
        return
    strat = self.combo_strat.currentText() if hasattr(self, 'combo_strat') else ""
    has_guide = (strat in STRATEGY_SETUP_GUIDE or
                 any(key in strat for key in STRATEGY_SETUP_GUIDE))
    btn.setVisible(has_guide)
    if has_guide:
        btn.setToolTip("전략 구성 가이드 보기")


# ── 가이드 팝업 직접 호출 (📋 버튼) ─────────────────────────

def _show_guide_popup(self):
    """
    📋 버튼 직접 클릭 → suppress 무시하고 강제 표시.
    BUG-4(suppress 사전 체크)와 독립적으로 동작.
    """
    strat = self.combo_strat.currentText() if hasattr(self, 'combo_strat') else ""
    guide = STRATEGY_SETUP_GUIDE.get(strat)
    if guide is None:
        for key, val in STRATEGY_SETUP_GUIDE.items():
            if key in strat:
                guide = val
                break
    if guide is None:
        return
    try:
        from combo_strategy_guide_popup import StrategyGuidePopup, _SUPPRESS_SET
        # 버튼 직접 클릭은 suppress를 무시
        _SUPPRESS_SET.discard(guide.get("title", ""))
        popup = StrategyGuidePopup(guide, parent=self)
        popup.show()
    except Exception:
        pass


# ── itemChanged 핸들러 ────────────────────────────────────────

def _on_leg_item_changed(self, item):
    """
    BUG-9 수정: _update_guide_btn_state 호출 제거
    (프리미엄/수량 변경과 가이드 버튼 상태는 무관).
    """
    if getattr(self, '_leg_item_changing', False):
        return
    if item.column() in (4, 5):
        _recalc_net_price(self)


# ── Net Price 재계산 ─────────────────────────────────────────

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

    display = getattr(self, 'net_price_display', None)
    if display is not None:
        if lmt_price == 0.0:
            display.reset()
        else:
            display.refresh(round(buy_total, 2), round(sell_total, 2))

    return lmt_price


# ── 스트리밍 API (combo_ui_leg_stream.py re-export) ──────────

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


# ── 세트 입력 / 단축키 위임 (하위 호환) ──────────────────────

def _apply_set_input(self, sell_edit, buy_edit):
    from combo_ui_leg_setinput import _apply_set_input as _f
    _f(self, sell_edit, buy_edit)

def _set_strategy_by_name(self, strat_name: str):
    from combo_ui_leg_setinput import _set_strategy_by_name as _f
    _f(self, strat_name)
