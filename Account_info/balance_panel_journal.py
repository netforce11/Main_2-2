"""
balance_panel_journal.py — 매매일지 패널  v2.3
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDateEdit,
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
    tbl.setMaximumHeight(260)
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
    tbl.setMaximumHeight(260)
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

    self._jnl_tab_exec  = QPushButton("💰 체결내역")
    self._jnl_tab_order = QPushButton("📋 주문로그")
    self._jnl_tab_open  = QPushButton("🔓 미청산")

    for btn in (self._jnl_tab_exec, self._jnl_tab_order, self._jnl_tab_open):
        btn.setCheckable(True)
        btn.setStyleSheet(CS["jnl_tab"])
        hl.addWidget(btn)
    self._jnl_tab_exec.setChecked(True)

    def _switch(idx):
        pages = [self._jnl_page_exec, self._jnl_page_order, self._jnl_page_open]
        btns  = [self._jnl_tab_exec,  self._jnl_tab_order,  self._jnl_tab_open]
        for i, (p, b) in enumerate(zip(pages, btns)):
            p.setVisible(i == idx); b.setChecked(i == idx)

    self._jnl_tab_exec.clicked.connect(lambda: _switch(0))
    self._jnl_tab_order.clicked.connect(lambda: _switch(1))
    self._jnl_tab_open.clicked.connect(lambda: _switch(2))

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

    return [self._jnl_page_exec, self._jnl_page_order, self._jnl_page_open]


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
