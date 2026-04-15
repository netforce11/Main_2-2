"""combo_ui_synthetic_panel.py — SyntheticStatusPanel 위젯
탭1: 📊 증거금 확인 (update_margin)  탭2: 📋 합성 잔고 (add_position)
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QTableWidget, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QSizePolicy, QPushButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

# ── 폰트 상수 (setFont로 적용 — QSS font-size 캐스케이딩 우회) ───
def _f(pt, bold=False):
    f = QFont(); f.setPointSize(pt)
    if bold: f.setBold(True)
    return f

_TAB_STYLE = """
QTabWidget::pane { border:1px solid #1a1a3a; background:#07070f; }
QTabBar::tab { background:#0d0d22; color:#666688;
    padding:5px 12px; border:1px solid #1a1a3a; border-bottom:none; }
QTabBar::tab:selected { background:#07070f; color:#e0e0ff; border-top:2px solid #00ff88; }
QTabBar::tab:hover { color:#aaaacc; }
"""
_TBL_STYLE = """
QTableWidget { background:#07070f; alternate-background-color:#0c0c20;
    color:#cccccc; gridline-color:#1a1a3a; border:none; }
QTableWidget::item:selected { background:#1a1a3a; color:#ffffff; }
QHeaderView::section { background:#0a0a1e; color:#90caf9;
    border:1px solid #1a1a3a; font-weight:bold; padding:3px 6px; }
"""


class SyntheticStatusPanel(QWidget):
    """합성 주문 상태 패널 (v2.5)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#07070f;")
        self._positions = []
        self._close_pos_callback     = None
        self._chaser_mode_callback   = None
        self._manual_modify_callback = None
        self._margin_mode_callback   = None
        self._build_ui()

    def _build_ui(self):
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # ── 증거금 모드 라디오 행 ────────────────────────────────
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(6, 4, 6, 2); mode_row.setSpacing(8)
        lbl = QLabel("💰 증거금:")
        lbl.setStyleSheet("color:#888;font-size:11px;border:none;")
        mode_row.addWidget(lbl)

        self._rb_margin_local  = QRadioButton("🖥 로컬")
        self._rb_margin_server = QRadioButton("☁ 서버")
        self._rb_margin_local.setChecked(True)
        for rb in (self._rb_margin_local, self._rb_margin_server):
            rb.setStyleSheet(
                "color:#ccc;font-size:11px;border:none;"
                "QRadioButton::indicator{width:12px;height:12px;}")
        self._margin_grp = QButtonGroup(self)
        self._margin_grp.addButton(self._rb_margin_local,  0)
        self._margin_grp.addButton(self._rb_margin_server, 1)
        mode_row.addWidget(self._rb_margin_local)
        mode_row.addWidget(self._rb_margin_server)

        self._lbl_margin_mode_desc = QLabel("즉시 계산")
        self._lbl_margin_mode_desc.setStyleSheet(
            "color:#445566;font-size:10px;border:none;")
        mode_row.addWidget(self._lbl_margin_mode_desc)
        mode_row.addStretch()

        self._rb_margin_local.toggled.connect(self._on_margin_mode_toggle)
        self._rb_margin_server.toggled.connect(self._on_margin_mode_toggle)

        mode_widget = QWidget(); mode_widget.setStyleSheet("background:#07070f;")
        mode_widget.setLayout(mode_row)
        root.addWidget(mode_widget)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#1a1a3a;max-height:1px;"); root.addWidget(sep)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.tabBar().setFont(_f(12, bold=True))
        self._tabs.addTab(self._build_margin_tab(),   "📊 증거금 확인")
        self._tabs.addTab(self._build_position_tab(), "📋 합성 잔고")
        self._tabs.addTab(self._build_open_orders_tab(), "📋 미체결")
        root.addWidget(self._tabs)

    def _build_margin_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(5)

        def kv(label):
            row = QHBoxLayout()
            lk = QLabel(label); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
            lv = QLabel("―");   lv.setStyleSheet("color:#e0e0e0;border:none;"); lv.setFont(_f(13, True))
            row.addWidget(lk); row.addStretch(); row.addWidget(lv)
            return row, lv

        row_s, self._lbl_m_strategy  = kv("전략명")
        row_c, self._lbl_m_cost      = kv("순 비용")
        row_a, self._lbl_m_available = kv("주문가능")
        row_r, self._lbl_m_required  = kv("필요증거금")

        for row in (row_s, row_c): lay.addLayout(row)
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color:#1a1a3a; max-height:1px;"); lay.addWidget(sep1)
        for row in (row_a, row_r): lay.addLayout(row)
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#1a1a3a; max-height:1px;"); lay.addWidget(sep2)

        self._lbl_margin_status = QLabel("―")
        self._lbl_margin_status.setAlignment(Qt.AlignCenter)
        self._lbl_margin_status.setFont(_f(13, bold=True))
        self._lbl_margin_status.setStyleSheet(
            "color:#555577;padding:7px;border:1px solid #2a2a4a;"
            "border-radius:4px;background:#0a0a1e;")
        lay.addWidget(self._lbl_margin_status)
        lay.addStretch()
        return w

    def _build_position_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        summary = QHBoxLayout()
        lk = QLabel("총 손익"); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
        self._lbl_total_pnl = QLabel("$0.00")
        self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
        self._lbl_total_pnl.setFont(_f(14, bold=True))
        summary.addWidget(lk); summary.addStretch(); summary.addWidget(self._lbl_total_pnl)
        lay.addLayout(summary)

        self._lbl_no_pos = QLabel("합성 주문 내역이 없습니다.")
        self._lbl_no_pos.setAlignment(Qt.AlignCenter)
        self._lbl_no_pos.setFont(_f(12))
        self._lbl_no_pos.setStyleSheet("color:#333355;padding:14px;")
        lay.addWidget(self._lbl_no_pos)

        # 컬럼: 전략명 / 수량 / 진입가 / 현재가 / 손익 / 상태
        self._tbl_pos = QTableWidget(0, 6)
        self._tbl_pos.setHorizontalHeaderLabels(
            ["전략명", "수량", "진입가", "현재가", "손익", "상태"])
        self._tbl_pos.setFont(_f(12))
        self._tbl_pos.horizontalHeader().setFont(_f(11, bold=True))
        self._tbl_pos.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 6):
            self._tbl_pos.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._tbl_pos.verticalHeader().setVisible(False)
        self._tbl_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_pos.setAlternatingRowColors(True)
        self._tbl_pos.setStyleSheet(_TBL_STYLE)
        self._tbl_pos.setVisible(False)
        self._tbl_pos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_pos.cellClicked.connect(self._on_pos_row_clicked)
        lay.addWidget(self._tbl_pos, 1)

        # 하단 버튼 행
        btn_row = QHBoxLayout()
        self._lbl_pos_hint = QLabel("행을 클릭하세요")
        self._lbl_pos_hint.setStyleSheet("color:#444466;font-size:11px;border:none;")
        btn_row.addWidget(self._lbl_pos_hint)
        btn_row.addStretch()

        self._btn_cancel_pos = QPushButton("✖ 주문 취소")
        self._btn_cancel_pos.setFixedHeight(26)
        self._btn_cancel_pos.setEnabled(False)
        self._btn_cancel_pos.setStyleSheet(
            "background:#2a1a0a;color:#ffaa44;font-size:12px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;padding:2px 10px;")
        self._btn_cancel_pos.clicked.connect(self._on_cancel_pos_order)
        btn_row.addWidget(self._btn_cancel_pos)

        self._btn_close_pos = QPushButton("🔴 청산 주문")
        self._btn_close_pos.setFixedHeight(26)
        self._btn_close_pos.setEnabled(False)
        self._btn_close_pos.setStyleSheet(
            "background:#2a0a0a;color:#ff6666;font-size:12px;"
            "font-weight:bold;border:1px solid #6a1a1a;border-radius:3px;padding:2px 10px;")
        self._btn_close_pos.clicked.connect(self._on_close_position)
        btn_row.addWidget(self._btn_close_pos)
        lay.addLayout(btn_row)
        return w

    def _on_pos_row_clicked(self, row, col):
        """잔고 행 클릭 → 상태에 따라 버튼 활성화."""
        if row < 0 or row >= len(self._positions):
            self._btn_close_pos.setEnabled(False)
            self._btn_cancel_pos.setEnabled(False)
            self._lbl_pos_hint.setText("행을 클릭하세요")
            return
        pos = self._positions[row]
        status = pos.get("status", "미체결")
        strat  = pos.get("strategy", "―")
        current = pos.get("current", 0)

        self._lbl_pos_hint.setText(
            f"{'⏳ 미체결' if status == '미체결' else '✅ 체결'}: {strat}")

        # 미체결이면 취소 버튼, 체결완료면 청산 버튼
        is_pending = (status == "미체결")
        self._btn_cancel_pos.setEnabled(is_pending)
        self._btn_close_pos.setEnabled(not is_pending)
        if not is_pending:
            self._btn_close_pos.setText(f"🔴 청산  ${current:.2f}")

    def _on_cancel_pos_order(self):
        """미체결 주문 취소."""
        row = self._tbl_pos.currentRow()
        if row < 0 or row >= len(self._positions):
            return
        pos = self._positions[row]
        oid = pos.get("oid")
        if not oid:
            return
        if callable(getattr(self, '_cancel_order_callback', None)):
            self._cancel_order_callback(oid)

    def set_cancel_order_callback(self, fn):
        """주문 취소 콜백. fn(oid)"""
        self._cancel_order_callback = fn

    def mark_position_filled(self, oid: int):
        """OID 기준으로 미체결 → 체결완료 상태 갱신."""
        for pos in self._positions:
            if pos.get("oid") == oid:
                pos["status"] = "체결완료"
        self._refresh_pos_table()

    def mark_position_cancelled(self, oid: int):
        """OID 기준으로 항목 제거 (취소 완료)."""
        self._positions = [p for p in self._positions if p.get("oid") != oid]
        self._refresh_pos_table()

    def _on_close_position(self):
        """청산 주문 요청 → 외부 콜백 호출."""
        row = self._tbl_pos.currentRow()
        if row < 0 or row >= len(self._positions):
            return
        pos = self._positions[row]
        if callable(getattr(self, '_close_pos_callback', None)):
            self._close_pos_callback(pos)

    def set_margin_mode_callback(self, fn):
        """증거금 모드 전환 콜백. fn(is_server: bool)"""
        self._margin_mode_callback = fn

    def _on_margin_mode_toggle(self):
        is_server = self._rb_margin_server.isChecked()
        self._lbl_margin_mode_desc.setText(
            "서버 whatIf (느림)" if is_server else "즉시 계산")
        if callable(self._margin_mode_callback):
            self._margin_mode_callback(is_server)

    def set_close_pos_callback(self, fn):
        """청산 주문 콜백 등록. fn(pos_dict) 형태."""
        self._close_pos_callback = fn

    # ── 하위 호환 별칭 ────────────────────────────────────────
    def set_close_position_callback(self, fn):
        """set_close_pos_callback 별칭 (ComboUI / ComboStrategyGrid 호환)."""
        self.set_close_pos_callback(fn)

    # ── Public API ────────────────────────────────────────────
    def update_margin(self, available: float, required: float,
                      strategy: str = "―", cost: str = "―"):
        self._lbl_m_strategy.setText(strategy or "―")
        self._lbl_m_cost.setText(cost or "―")
        self._lbl_m_available.setText(f"${available:,.2f}")
        self._lbl_m_required.setText(f"${required:,.2f}")
        if required <= 0:
            st, col, bg, bc = "— 데이터 없음 —", "#555577", "#0a0a1e", "#2a2a4a"
        elif available >= required:
            surplus = available - required
            st, col, bg, bc = f"✅  주문 가능  (여유 ${surplus:,.2f})", "#00ff88", "#071a0e", "#00ff88"
        else:
            shortage = required - available
            st, col, bg, bc = f"❌  증거금 부족  (${shortage:,.2f} 부족)", "#ff4444", "#1a0707", "#ff4444"
        self._lbl_margin_status.setText(st)
        self._lbl_margin_status.setStyleSheet(
            f"color:{col};padding:7px;border:1px solid {bc};"
            f"border-radius:4px;background:{bg};")
        self._tabs.setCurrentIndex(0)

    def add_position(self, fill_info: dict):
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def update_position_prices(self, strategy: str, current_price: float):
        for pos in self._positions:
            if pos.get("strategy") == strategy:
                pos["current"] = current_price
        self._refresh_pos_table()

    def clear_positions(self):
        self._positions.clear()
        self._refresh_pos_table()

    def _build_open_orders_tab(self) -> QWidget:
        """미체결 주문 탭 — Chaser 자동/수동 토글 포함."""
        from PyQt5.QtWidgets import QRadioButton, QDoubleSpinBox, QButtonGroup
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(4,4,4,4); lay.setSpacing(4)

        # ── Chaser 모드 행 ─────────────────────────────────────
        chaser_row = QHBoxLayout(); chaser_row.setSpacing(6)

        mode_lbl = QLabel("정정 모드:")
        mode_lbl.setStyleSheet("color:#888;border:none;font-size:11px;")
        chaser_row.addWidget(mode_lbl)

        self._rb_chaser_auto   = QRadioButton("🤖 자동")
        self._rb_chaser_manual = QRadioButton("✏ 수동")
        self._rb_chaser_auto.setChecked(True)
        for rb in (self._rb_chaser_auto, self._rb_chaser_manual):
            rb.setStyleSheet("color:#ccc;font-size:11px;border:none;")
        self._chaser_mode_grp = QButtonGroup(w)
        self._chaser_mode_grp.addButton(self._rb_chaser_auto,   0)
        self._chaser_mode_grp.addButton(self._rb_chaser_manual, 1)
        chaser_row.addWidget(self._rb_chaser_auto)
        chaser_row.addWidget(self._rb_chaser_manual)

        # 수동 모드: net price 직접 입력
        self._spin_manual_price = QDoubleSpinBox()
        self._spin_manual_price.setRange(0.01, 999.99)
        self._spin_manual_price.setSingleStep(0.05)
        self._spin_manual_price.setDecimals(2)
        self._spin_manual_price.setPrefix("$")
        self._spin_manual_price.setFixedWidth(80)
        self._spin_manual_price.setFixedHeight(24)
        self._spin_manual_price.setVisible(False)
        self._spin_manual_price.setStyleSheet(
            "background:#0a1a2a;color:#ffdd88;border:1px solid #3a5a9a;"
            "border-radius:3px;font-size:12px;font-weight:bold;")
        chaser_row.addWidget(self._spin_manual_price)

        self._btn_manual_send = QPushButton("전송")
        self._btn_manual_send.setFixedSize(46, 24)
        self._btn_manual_send.setVisible(False)
        self._btn_manual_send.setStyleSheet(
            "background:#1a3a1a;color:#aaffaa;font-size:11px;"
            "font-weight:bold;border:1px solid #3a8a3a;border-radius:3px;")
        self._btn_manual_send.clicked.connect(self._on_manual_price_send)
        chaser_row.addWidget(self._btn_manual_send)

        chaser_row.addStretch()
        lay.addLayout(chaser_row)

        # 모드 전환 연결
        self._rb_chaser_auto.toggled.connect(self._on_chaser_mode_toggle)
        self._rb_chaser_manual.toggled.connect(self._on_chaser_mode_toggle)

        # 자동 모드 설명 라벨
        self._lbl_chaser_desc = QLabel("⏱ 미체결 5초 후 자동 1틱 정정 (최대 3회)")
        self._lbl_chaser_desc.setStyleSheet("color:#556677;font-size:10px;border:none;")
        lay.addWidget(self._lbl_chaser_desc)

        # ── 버튼 행 ────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)

        self._btn_refresh_orders = QPushButton("↺ 조회")
        self._btn_refresh_orders.setFixedHeight(24)
        self._btn_refresh_orders.setStyleSheet(
            "background:#1a2a4a;color:#90caf9;font-size:11px;"
            "font-weight:bold;border:1px solid #3a5a9a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_refresh_orders)

        self._btn_modify_p1 = QPushButton("+1호가 정정")
        self._btn_modify_p1.setFixedHeight(24)
        self._btn_modify_p1.setStyleSheet(
            "background:#1a2a0a;color:#aaffaa;font-size:11px;"
            "font-weight:bold;border:1px solid #3a6a2a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_modify_p1)

        self._btn_modify_m1 = QPushButton("-1호가 정정")
        self._btn_modify_m1.setFixedHeight(24)
        self._btn_modify_m1.setStyleSheet(
            "background:#2a1a0a;color:#ffaa44;font-size:11px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_modify_m1)

        self._btn_cancel_all = QPushButton("✖ 전체 취소")
        self._btn_cancel_all.setFixedHeight(24)
        self._btn_cancel_all.setStyleSheet(
            "background:#2a0a0a;color:#ff4444;font-size:11px;"
            "font-weight:bold;border:1px solid #6a1a1a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_cancel_all)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # ── 미체결 테이블 ──────────────────────────────────────
        self._tbl_open_orders = QTableWidget(0, 6)
        self._tbl_open_orders.setHorizontalHeaderLabels(
            ["OID","종목","방향","수량","지정가","상태"])
        self._tbl_open_orders.setFont(_f(11))
        self._tbl_open_orders.horizontalHeader().setFont(_f(10, bold=True))
        self._tbl_open_orders.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_open_orders.verticalHeader().setVisible(False)
        self._tbl_open_orders.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_open_orders.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_open_orders.setAlternatingRowColors(True)
        self._tbl_open_orders.setStyleSheet(_TBL_STYLE)
        self._tbl_open_orders.cellClicked.connect(self._on_order_row_clicked)
        lay.addWidget(self._tbl_open_orders, 1)
        return w

    def _on_chaser_mode_toggle(self):
        """자동/수동 모드 전환."""
        is_manual = self._rb_chaser_manual.isChecked()
        self._spin_manual_price.setVisible(is_manual)
        self._btn_manual_send.setVisible(is_manual)
        self._btn_modify_p1.setVisible(not is_manual)
        self._btn_modify_m1.setVisible(not is_manual)
        if is_manual:
            self._lbl_chaser_desc.setText("✏ Net Price를 직접 입력 후 [전송] 클릭")
        else:
            self._lbl_chaser_desc.setText("⏱ 미체결 5초 후 자동 1틱 정정 (최대 3회)")
        # 외부에 모드 변경 알림
        if callable(getattr(self, '_chaser_mode_callback', None)):
            self._chaser_mode_callback("manual" if is_manual else "auto")

    def _on_order_row_clicked(self, row, col):
        """미체결 행 클릭 → 수동 모드일 때 현재 지정가를 spin에 자동 입력."""
        if not self._rb_chaser_manual.isChecked():
            return
        tbl = self._tbl_open_orders
        price_item = tbl.item(row, 4)
        if price_item:
            try:
                price = float(price_item.text().replace("$",""))
                self._spin_manual_price.setValue(price)
            except ValueError:
                pass

    def _on_manual_price_send(self):
        """수동 입력가로 정정 요청."""
        new_price = self._spin_manual_price.value()
        row = self._tbl_open_orders.currentRow()
        if row < 0:
            return
        oid_item = self._tbl_open_orders.item(row, 0)
        if not oid_item:
            return
        try:
            oid = int(oid_item.text())
        except ValueError:
            return
        if callable(getattr(self, '_manual_modify_callback', None)):
            self._manual_modify_callback(oid, new_price)

    def set_chaser_mode_callback(self, fn):
        """모드 전환 시 외부 알림 콜백. fn("auto"|"manual")"""
        self._chaser_mode_callback = fn

    def set_manual_modify_callback(self, fn):
        """수동 정정 콜백. fn(oid, new_price)"""
        self._manual_modify_callback = fn

    def is_auto_chaser(self) -> bool:
        """현재 자동 모드 여부."""
        return self._rb_chaser_auto.isChecked()

    def set_current_order_price(self, price: float):
        """체결 대기 중인 주문 가격을 수동 spin에 미리 채워줌."""
        self._spin_manual_price.setValue(round(price, 2))

    def update_open_orders(self, orders: list):
        """미체결 주문 목록 갱신."""
        tbl = self._tbl_open_orders
        tbl.setRowCount(0)
        for o in orders:
            r = tbl.rowCount(); tbl.insertRow(r)
            def _it(text, color="#ccc"):
                from PyQt5.QtGui import QColor
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it
            action_col = "#00ff88" if o.get("action") == "BUY" else "#ff6666"
            tbl.setItem(r, 0, _it(o.get("oid",""),    "#888"))
            tbl.setItem(r, 1, _it(o.get("sym",""),    "#ffd700"))
            tbl.setItem(r, 2, _it(o.get("action",""), action_col))
            tbl.setItem(r, 3, _it(o.get("qty",""),    "#ccc"))
            tbl.setItem(r, 4, _it(f"{o.get('lmt',0):.2f}" if o.get('lmt') else "MKT", "#ffaa44"))
            st = o.get("status","")
            st_col = "#00ff88" if "Submit" in st else "#ffaa44" if "Pending" in st else "#888"
            tbl.setItem(r, 5, _it(st, st_col))
        self._tabs.setCurrentIndex(2)

    def get_selected_order(self):
        """미체결 탭에서 선택된 주문 행 인덱스 반환."""
        return self._tbl_open_orders.currentRow()

    def clear_positions(self):
        self._positions.clear()
        self._refresh_pos_table()

    def _refresh_pos_table(self):
        tbl = self._tbl_pos
        tbl.setRowCount(0)
        if not self._positions:
            self._lbl_no_pos.setVisible(True); tbl.setVisible(False)
            self._lbl_total_pnl.setText("$0.00")
            self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
            return
        self._lbl_no_pos.setVisible(False); tbl.setVisible(True)
        tbl.setRowCount(len(self._positions))
        total_pnl = 0.0
        for r, pos in enumerate(self._positions):
            qty     = pos.get("qty", 1)
            entry   = pos.get("entry", 0.0)
            current = pos.get("current", entry)
            pnl     = (current - entry) * qty * 100
            total_pnl += pnl
            pnl_col = "#00ff88" if pnl > 0 else "#ff4444" if pnl < 0 else "#888899"

            status  = pos.get("status", "미체결")
            is_filled = (status == "체결완료")
            # 미체결이면 손익 계산 제외
            if is_filled:
                pnl = (current - entry) * qty * 100
                total_pnl += pnl
            else:
                pnl = 0.0
            pnl_col = "#00ff88" if pnl > 0 else "#ff4444" if pnl < 0 else "#888899"

            def _it(text, color="#cccccc", align=Qt.AlignCenter):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            st_col  = "#00ff88" if is_filled else "#ffaa44"
            st_text = "✅ 체결" if is_filled else "⏳ 미체결"
            tbl.setItem(r, 0, _it(pos.get("strategy","―"), "#e0e0ff", Qt.AlignLeft|Qt.AlignVCenter))
            tbl.setItem(r, 1, _it(str(qty),                  "#aaaaaa"))
            tbl.setItem(r, 2, _it(f"${entry:.2f}",           "#aaaaaa"))
            tbl.setItem(r, 3, _it(f"${current:.2f}",         "#e0e0e0"))
            tbl.setItem(r, 4, _it(f"${pnl:+,.2f}" if is_filled else "―", pnl_col))
            tbl.setItem(r, 5, _it(st_text,                   st_col))

        tc = "#00ff88" if total_pnl > 0 else "#ff4444" if total_pnl < 0 else "#888899"
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")