"""
combo_ui_leg_panel.py — 레그 테이블 좌측 패널 빌드
────────────────────────────────────────────────────
포함: _build_leg_left (RightPanelMixin에 mixin)

v2.5.1 변경:
  - 행사가 자동 입력 시 reqMktData(snapshot) → Mid price 자동 조회
  - 프리미엄 셀 변경 시 _recalc_net_price() 자동 호출 → Net Price 라벨 갱신
  - 공개 API: fill_premium_from_market(row, conId)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QTableWidget, QHeaderView,
)
from PyQt5.QtCore import QTimer
from combo_constants import STRATEGIES

# ── Mid-price 티커 ID 범위: 8800~8815 (레그 0~15) ────────────────
_TICKER_BASE = 8800


def _build_leg_left(self) -> QWidget:
    """좌측: 전략 유형 콤보 + 레그 모드 토글 + 레그 테이블."""
    w = QWidget(); v = QVBoxLayout(w)
    v.setSpacing(4); v.setContentsMargins(2, 2, 4, 2)

    # ── 전략 유형 행 ──────────────────────────────────────────
    row = QHBoxLayout()
    row.addWidget(QLabel("전략 유형:"))
    self.combo_strat = QComboBox()
    self.combo_strat.addItems(STRATEGIES)
    self.combo_strat.setStyleSheet(
        "QComboBox{background:#12122a;color:#ffd700;border:1px solid #3a3a6a;"
        "border-radius:3px;font-size:12px;padding:3px;}"
        "QComboBox QAbstractItemView{background:#12122a;color:#ffd700;"
        "selection-background-color:#1c3a6a;}"
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

    # ── 수동 모드 버튼 행 ─────────────────────────────────────
    self._manual_btn_row = QWidget()
    mbh = QHBoxLayout(self._manual_btn_row)
    mbh.setContentsMargins(0, 1, 0, 1); mbh.setSpacing(4)
    for text, style, fn in [
        ("➕ 레그 추가",
         "background:#1a2a4a;color:#90caf9;font-size:10px;font-weight:bold;"
         "padding:2px 8px;border-radius:3px;border:1px solid #3a5a9a;",
         self._manual_add_leg),
        ("➖ 레그 제거",
         "background:#2a0a1a;color:#ff6666;font-size:10px;font-weight:bold;"
         "padding:2px 8px;border-radius:3px;border:1px solid #5a1a1a;",
         self._manual_del_leg),
    ]:
        btn = QPushButton(text); btn.setFixedHeight(22)
        btn.setStyleSheet(style); btn.clicked.connect(fn)
        mbh.addWidget(btn)
    mbh.addWidget(QLabel("방향·C/P·행사가·프리미엄·수량·만기 직접 입력"))
    mbh.addStretch()
    self._manual_btn_row.setVisible(False)
    v.addWidget(self._manual_btn_row)

    # ── Net Price 라벨 ────────────────────────────────────────
    self.lbl_net_price = QLabel("Net Price: —")
    self.lbl_net_price.setStyleSheet(
        "QLabel{background:#0a0a1e;color:#aaa;font-size:12px;font-weight:bold;"
        "border:1px solid #2a2a4a;border-radius:3px;padding:3px 8px;}")
    v.addWidget(self.lbl_net_price)

    # 재귀 방지 플래그 + itemChanged 연결
    self._leg_item_changing = False
    self._mid_ticks: dict = {}
    self.tbl_legs.itemChanged.connect(lambda item: _on_leg_item_changed(self, item))

    return w


# ── Net Price 재계산 ─────────────────────────────────────────────

def _on_leg_item_changed(self, item):
    """프리미엄(4) 또는 수량(5) 변경 시 Net Price 갱신."""
    if getattr(self, '_leg_item_changing', False):
        return
    if item.column() in (4, 5):
        _recalc_net_price(self)


def _recalc_net_price(self) -> float:
    """
    레그 테이블 기준 Net lmtPrice 계산 후 라벨 갱신.

    반환값:
      양수  → 데빗(BUY)    전략: 지불할 금액
      양수  → 크레딧(SELL) 전략: 수취할 금액
      0.0   → 미입력 or 계산 불가
    """
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


# ── Mid-price 실시간 스트리밍 (공개 API) ─────────────────────────

def fill_premium_from_market(self, row: int, con_id: int):
    """
    행사가 입력 직후 호출.
    router.register_price() → bridge.tick_price 시그널 경유 → Mid price 자동 갱신.

    실제 tick 흐름:
      IBapi.tickPrice()
        → bridge.tick_price.emit()   (SignalBridge, core.py)
        → router._route_price()      (TickRouter, core.py)
        → 여기서 register_price()로 등록한 슬롯 호출

    ib.tickPrice 를 직접 덮어쓰면 bridge → router 경로를 우회할 수 없어
    콜백이 절대 호출되지 않음 → router 방식으로 수정.

    Parameters
    ----------
    row    : 레그 테이블 행 번호 (0-based)
    con_id : IBKR conId (옵션 컨트랙트)
    """
    from core import router

    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ib is None or con_id <= 0:
        return

    if not hasattr(self, '_mid_ticks'):
        self._mid_ticks = {}
    if not hasattr(self, '_stream_conids'):
        self._stream_conids = {}   # {ticker_id: con_id} — 활성 스트림 추적
    if not hasattr(self, '_stream_slots'):
        self._stream_slots = {}    # {ticker_id: slot_fn} — router 해제용

    ticker_id = _TICKER_BASE + row

    # 이미 같은 레그로 스트림 중이면 기존 것 먼저 해제
    _cancel_stream(self, ticker_id)

    self._mid_ticks[ticker_id]     = {}
    self._stream_conids[ticker_id] = con_id

    # ── router 슬롯 정의 ──────────────────────────────────────
    def _on_tick(req_id: int, tick_type: int, price: float):
        # 이 스트림이 이미 취소됐으면 무시 (con_id 불일치)
        if self._stream_conids.get(ticker_id) != con_id:
            return
        # tick_type 1=Bid, 2=Ask
        if tick_type in (1, 2) and price > 0:
            self._mid_ticks[ticker_id][tick_type] = price
            bid = self._mid_ticks[ticker_id].get(1)
            ask = self._mid_ticks[ticker_id].get(2)
            if bid and ask:
                mid = round((bid + ask) / 2, 2)
                _set_premium_cell(self, row, mid)

    # router 에 등록 (ticker_id 단일 범위)
    router.register_price(ticker_id, ticker_id, _on_tick)
    self._stream_slots[ticker_id] = _on_tick   # 나중에 unregister 용

    # IbContract 로 reqMktData 호출
    try:
        from ibapi.contract import Contract as IbContract
        c = IbContract()
        c.conId    = con_id
        c.exchange = "SMART"
        # snapshot=False → 호가 변경마다 콜백 수신 (실시간 스트리밍)
        ib.reqMktData(ticker_id, c, "", False, False, [])
        self._log(f"📡 레그{row+1} 실시간 호가 구독 시작 (conId={con_id}, tid={ticker_id})")
    except Exception as e:
        router.unregister_price(_on_tick)
        self._stream_slots.pop(ticker_id, None)
        self._log(f"❌ reqMktData 레그{row+1}: {e}")


def _cancel_stream(self, ticker_id: int):
    """단일 레그 스트림 해제 (router 슬롯 포함)."""
    from core import router
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    if ticker_id in getattr(self, '_stream_conids', {}):
        if ib:
            try:
                ib.cancelMktData(ticker_id)
            except Exception:
                pass
        slot = getattr(self, '_stream_slots', {}).pop(ticker_id, None)
        if slot:
            router.unregister_price(slot)
        self._stream_conids.pop(ticker_id, None)
        self._mid_ticks.pop(ticker_id, None)


def cancel_all_streams(self):
    """
    전략 변경·초기화 시 모든 실시간 스트림 일괄 해제.
    _on_strat_change / _reset_legs 에서 호출.
    """
    from core import router
    ib = getattr(self, 'mw', None)
    ib = getattr(ib, 'ib', None) if ib else None
    for tid in list(getattr(self, '_stream_conids', {}).keys()):
        if ib:
            try:
                ib.cancelMktData(tid)
            except Exception:
                pass
        slot = getattr(self, '_stream_slots', {}).pop(tid, None)
        if slot:
            router.unregister_price(slot)
    self._stream_conids = {}
    self._stream_slots  = {}
    self._mid_ticks     = {}
    self._log("📡 전체 호가 스트림 해제")


def _set_premium_cell(self, row: int, value: float):
    """프리미엄 셀을 재귀 없이 안전하게 설정 후 Net Price 갱신."""
    from PyQt5.QtWidgets import QTableWidgetItem
    self._leg_item_changing = True
    try:
        it = self.tbl_legs.item(row, 4)
        if it is None:
            it = QTableWidgetItem()
            self.tbl_legs.setItem(row, 4, it)
        it.setText(str(value))
    finally:
        self._leg_item_changing = False
    _recalc_net_price(self)