"""
balance_panel_journal.py — 매매일지 패널  v2.3
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDateEdit,
    QSpinBox, QDialog, QFormLayout, QDialogButtonBox, QLineEdit, QMessageBox,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui  import QColor, QBrush
from Account_info.balance_style import CS


def _make_exec_tbl() -> QTableWidget:
    headers = [
        "시각", "방향", "종목", "만기", "행사가", "콜/풋",
        "수량", "매수체결가", "매도체결가", "손익",
        "지수", "5분전", "10분전",
    ]
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    hdr = tbl.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setAlternatingRowColors(True)
    tbl.setStyleSheet(CS["jnl_tbl"])
    return tbl


def _make_tbl(headers: list) -> QTableWidget:
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    tbl.verticalHeader().setVisible(False)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setAlternatingRowColors(True)
    tbl.setStyleSheet(CS["jnl_tbl"])
    return tbl


def _wrap(widget: QWidget) -> QWidget:
    w = QWidget(); v = QVBoxLayout(w)
    v.setContentsMargins(0, 4, 0, 0); v.addWidget(widget)
    return w


def build_journal(self) -> QWidget:
    outer = QWidget()
    outer.setObjectName("jnl_outer")
    outer.setStyleSheet(
        "QWidget#jnl_outer{"
        "background:#ffffff;"
        "border:1px solid #d1d9e0;"
        "border-radius:12px;}")
    root = QVBoxLayout(outer)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    root.addWidget(_build_header(self))
    root.addWidget(_build_summary_bar(self))
    for page in _build_pages(self):
        root.addWidget(page)
    root.addWidget(_build_footer(self))

    return outer


def _build_header(self) -> QWidget:
    hdr = QWidget()
    hdr.setStyleSheet(
        "background:#ffffff;"
        "border-bottom:1px solid #e2e8f0;"
        "border-top-left-radius:12px;"
        "border-top-right-radius:12px;")
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(0, 0, 14, 0)
    hl.setSpacing(0)

    self._jnl_tab_exec    = QPushButton("💰 체결내역")
    self._jnl_tab_order   = QPushButton("📋 주문로그")
    self._jnl_tab_open    = QPushButton("🔓 미청산")
    self._jnl_tab_monthly = QPushButton("📅 월간합산")

    for btn in (self._jnl_tab_exec, self._jnl_tab_order,
                self._jnl_tab_open, self._jnl_tab_monthly):
        btn.setCheckable(True)
        btn.setStyleSheet(CS["jnl_tab"])
        hl.addWidget(btn)
    self._jnl_tab_exec.setChecked(True)

    def _switch(idx):
        pages = [self._jnl_page_exec, self._jnl_page_order,
                 self._jnl_page_open, self._jnl_page_monthly]
        btns  = [self._jnl_tab_exec,  self._jnl_tab_order,
                 self._jnl_tab_open,  self._jnl_tab_monthly]
        for i, (p, b) in enumerate(zip(pages, btns)):
            p.setVisible(i == idx); b.setChecked(i == idx)

    self._jnl_tab_exec.clicked.connect(lambda: _switch(0))
    self._jnl_tab_order.clicked.connect(lambda: _switch(1))
    self._jnl_tab_open.clicked.connect(lambda: _switch(2))
    self._jnl_tab_monthly.clicked.connect(lambda: _switch(3))

    hl.addStretch()

    self._jnl_date = QDateEdit()
    self._jnl_date.setCalendarPopup(True)
    self._jnl_date.setDate(QDate.currentDate())
    self._jnl_date.setDisplayFormat("yyyy-MM-dd")
    self._jnl_date.setFixedHeight(30)
    self._jnl_date.setFixedWidth(115)
    self._jnl_date.setStyleSheet(
        "QDateEdit{background:#f1f5f9;color:#1e293b;"
        "border:1px solid #cbd5e1;border-radius:6px;"
        "font-size:11px;font-weight:600;padding:2px 6px;}"
        "QDateEdit::drop-down{border:none;}")

    btn_load = QPushButton("조회")
    btn_load.setFixedHeight(30)
    btn_load.setStyleSheet(CS["btn_blue"] + "padding:4px 14px;")
    btn_load.clicked.connect(self._jnl_load)

    btn_today = QPushButton("오늘")
    btn_today.setFixedHeight(30)
    btn_today.setStyleSheet(CS["btn_green"] + "padding:4px 10px;")
    btn_today.clicked.connect(
        lambda: (self._jnl_date.setDate(QDate.currentDate()), self._jnl_load()))

    for w in (self._jnl_date, btn_load, btn_today):
        hl.addSpacing(6); hl.addWidget(w)

    return hdr


def _build_summary_bar(self) -> QLabel:
    self._jnl_summary_lbl = QLabel("")
    self._jnl_summary_lbl.setStyleSheet(
        "color:#64748b;font-size:11px;font-weight:600;"
        "background:#f8fafc;border-bottom:1px solid #e2e8f0;"
        "padding:7px 18px;")
    return self._jnl_summary_lbl


def _build_pages(self) -> list:
    # ── 탭1: 체결내역 ─────────────────────────────────────
    self.tbl_jnl_exec   = _make_exec_tbl()
    self._jnl_page_exec = _wrap(self.tbl_jnl_exec)

    # ── 탭2: 주문로그 ─────────────────────────────────────
    self.tbl_jnl_orders  = _make_tbl([
        "시각","상태","OID","종목","CP","행사가","방향","수량","주문가","지수"])
    self._jnl_page_order = _wrap(self.tbl_jnl_orders)
    self._jnl_page_order.setVisible(False)

    # ── 탭3: 미청산 ───────────────────────────────────────
    self.tbl_jnl_open   = _make_tbl([
        "진입일","종목","CP","행사가","수량","진입가","현재손익"])
    self._jnl_page_open = _wrap(self.tbl_jnl_open)
    self._jnl_page_open.setVisible(False)

    # ── 탭4: 월간합산 ─────────────────────────────────────
    self._jnl_page_monthly = _build_monthly_page(self)
    self._jnl_page_monthly.setVisible(False)

    return [self._jnl_page_exec, self._jnl_page_order,
            self._jnl_page_open, self._jnl_page_monthly]


def _build_monthly_page(self) -> QWidget:
    """월간합산 탭 전체 페이지 빌드."""
    page = QWidget()
    vl   = QVBoxLayout(page)
    vl.setContentsMargins(10, 8, 10, 8)
    vl.setSpacing(6)

    # ── 컨트롤 바 ─────────────────────────────────────────
    ctrl = QHBoxLayout()

    self._monthly_year = QSpinBox()
    self._monthly_year.setRange(2020, 2035)
    self._monthly_year.setValue(QDate.currentDate().year())
    self._monthly_year.setFixedWidth(70)
    self._monthly_year.setFixedHeight(30)
    self._monthly_year.setStyleSheet(
        "QSpinBox{background:#f1f5f9;color:#1e293b;"
        "border:1px solid #cbd5e1;border-radius:6px;"
        "font-size:11px;font-weight:600;padding:2px 4px;}")

    self._monthly_month = QSpinBox()
    self._monthly_month.setRange(1, 12)
    self._monthly_month.setValue(QDate.currentDate().month())
    self._monthly_month.setFixedWidth(50)
    self._monthly_month.setFixedHeight(30)
    self._monthly_month.setStyleSheet(self._monthly_year.styleSheet())

    btn_load = QPushButton("📂 조회")
    btn_load.setFixedHeight(30)
    btn_load.setStyleSheet(CS["btn_blue"] + "padding:4px 14px;")

    btn_expire = QPushButton("📛 만기소멸 처리")
    btn_expire.setFixedHeight(30)
    btn_expire.setToolTip(
        "만기일이 지난 미청산 포지션을 소멸 처리합니다.\n"
        "롱 포지션 → 프리미엄 전액 손실\n"
        "숏 포지션 → 프리미엄 전액 이익")
    btn_expire.setStyleSheet(
        "QPushButton{background:#fff7ed;color:#9a3412;"
        "border:1px solid #fdba74;border-radius:6px;"
        "font-size:11px;font-weight:700;padding:4px 12px;}"
        "QPushButton:hover{background:#ffedd5;}")

    ctrl.addWidget(QLabel("연도:"))
    ctrl.addWidget(self._monthly_year)
    ctrl.addSpacing(6)
    ctrl.addWidget(QLabel("월:"))
    ctrl.addWidget(self._monthly_month)
    ctrl.addSpacing(4)
    ctrl.addWidget(btn_load)
    ctrl.addStretch()
    ctrl.addWidget(btn_expire)
    vl.addLayout(ctrl)

    # ── 요약 라벨 ─────────────────────────────────────────
    self._monthly_summary_lbl = QLabel("연도/월을 선택하고 조회 버튼을 누르세요.")
    self._monthly_summary_lbl.setStyleSheet(
        "color:#94a3b8;font-size:11px;font-weight:600;"
        "background:#f8fafc;border:1px solid #e2e8f0;"
        "border-radius:6px;padding:6px 14px;")
    vl.addWidget(self._monthly_summary_lbl)

    # ── 일별 브레이크다운 테이블 ──────────────────────────
    headers = ["날짜", "건수", "소멸", "실현손익", "수수료", "순손익"]
    self._monthly_table = QTableWidget(0, len(headers))
    self._monthly_table.setHorizontalHeaderLabels(headers)
    hdr = self._monthly_table.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.Stretch)
    self._monthly_table.verticalHeader().setVisible(False)
    self._monthly_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    self._monthly_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    self._monthly_table.setAlternatingRowColors(True)
    self._monthly_table.setStyleSheet(CS["jnl_tbl"])
    vl.addWidget(self._monthly_table)

    # ── 버튼 시그널 연결 ──────────────────────────────────
    from Account_info.balance_journal_load import monthly_load
    btn_load.clicked.connect(lambda: monthly_load(self))

    # _monthly_expire_dialog: BalanceJournalMixin(balance_journal.py)에 정의.
    # 구버전 호환: 메서드가 없으면 인라인으로 직접 실행.
    def _on_expire_click():
        if hasattr(self, '_monthly_expire_dialog'):
            self._monthly_expire_dialog()
        else:
            _inline_expire_dialog(self)

    btn_expire.clicked.connect(_on_expire_click)

    return page


def _inline_expire_dialog(self) -> None:
    """
    만기소멸 처리 다이얼로그 — 인라인 버전.
    BalanceJournalMixin(_monthly_expire_dialog)가 없을 때 폴백으로 실행.
    balance_journal.py를 최신 버전으로 교체하면 해당 메서드가 우선 사용됨.
    """
    try:
        from trade_log import expire_worthless, expire_worthless_by_expiry
    except ImportError:
        QMessageBox.warning(self, "오류", "trade_log 모듈을 찾을 수 없습니다.")
        return

    dlg = QDialog(self)
    dlg.setWindowTitle("📛 만기소멸 처리")
    layout = QFormLayout(dlg)

    date_edit = QDateEdit(QDate.currentDate())
    date_edit.setCalendarPopup(True)
    layout.addRow("만기일:", date_edit)

    note = QLabel(
        "특정 종목만 처리하려면 아래 항목을 모두 입력하세요.\n"
        "비워두면 해당 만기일의 모든 open 포지션을 처리합니다.")
    note.setStyleSheet("color:#64748b;font-size:10px;")
    layout.addRow(note)

    sym_edit    = QLineEdit(); sym_edit.setPlaceholderText("SPX  (비우면 전체)")
    expiry_edit = QLineEdit(); expiry_edit.setPlaceholderText("20260117  (비우면 만기일 자동 사용)")
    right_edit  = QLineEdit(); right_edit.setPlaceholderText("C 또는 P  (비우면 전체)")
    strike_edit = QLineEdit(); strike_edit.setPlaceholderText("5500  (비우면 전체)")
    layout.addRow("종목 (sym):", sym_edit)
    layout.addRow("만기 YYYYMMDD:", expiry_edit)
    layout.addRow("콜/풋 (C/P):", right_edit)
    layout.addRow("행사가:", strike_edit)

    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addRow(btns)

    if dlg.exec_() != QDialog.Accepted:
        return

    expired_date = date_edit.date().toString("yyyy-MM-dd")
    sym    = sym_edit.text().strip()
    expiry = expiry_edit.text().strip()
    right  = right_edit.text().strip().upper()
    strike = strike_edit.text().strip()

    try:
        if sym and expiry and right and strike:
            cnt = expire_worthless(sym, expiry, right, float(strike), expired_date)
        else:
            cnt = expire_worthless_by_expiry(expired_date)
    except Exception as e:
        QMessageBox.warning(self, "오류", f"처리 중 오류: {e}")
        return

    if cnt == 0:
        QMessageBox.information(
            self, "결과",
            f"{expired_date} 기준 처리할 open 포지션이 없습니다.")
    else:
        QMessageBox.information(
            self, "완료",
            f"만기소멸 처리 예약: {cnt}건\n"
            f"(만기일: {expired_date})\n\n"
            f"'📂 조회' 버튼을 누르면 결과가 반영됩니다.")
        from Account_info.balance_journal_load import monthly_load
        monthly_load(self)


def _build_footer(self) -> QWidget:
    footer = QWidget()
    footer.setStyleSheet(
        "background:#f8fafc;"
        "border-top:1px solid #e2e8f0;"
        "border-bottom-left-radius:12px;"
        "border-bottom-right-radius:12px;")
    hl = QHBoxLayout(footer)
    hl.setContentsMargins(14, 6, 14, 6)
    hl.setSpacing(6)
    hl.addStretch()

    self._ib_fetch_lbl = QLabel("")
    self._ib_fetch_lbl.setStyleSheet(
        "color:#64748b;font-size:11px;border:none;")
    hl.addWidget(self._ib_fetch_lbl)

    btn_fetch = QPushButton("📥 IB 체결내역 불러오기")
    btn_fetch.setFixedHeight(30)
    btn_fetch.setStyleSheet(
        "background:#fef9c3;color:#854d0e;"
        "border:1px solid #fde047;border-radius:6px;"
        "font-size:11px;font-weight:700;padding:4px 14px;")
    btn_fetch.clicked.connect(self._jnl_fetch_ib)
    hl.addWidget(btn_fetch)

    return footer
