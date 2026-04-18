"""
report_left.py — 좌측 패널 (리포트 리스트 / 검색 / 필터 / 추가·삭제)
════════════════════════════════════════════════════════════════════
위치: IBKR/MAIN2/STRATEGY_REPORT/report_left.py

ReportLeftPanel: QWidget 서브클래스
  - 검색창 (edt_search)
  - 중요도 필터 콤보 (cmb_filter_imp)
  - 리포트 리스트 (lst_reports)
  - 추가(+) / 삭제(-) 버튼
  - 리포트 건수 표시 (lbl_count)

공개 메서드:
  load_list(conn, keyword, imp_idx) → 리스트 갱신
  current_report_id() → 현재 선택된 report id (없으면 None)
  select_item(report_id) → 해당 id 항목 선택
  item_selected  시그널 → (report_id: int) 연결 대상
"""

from __future__ import annotations

import sqlite3

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from .report_const import FS_TITLE, FS_BODY, FS_SMALL, FS_LIST


# ══════════════════════════════════════════════════════════════
class ReportLeftPanel(QWidget):
    """좌측 리포트 목록 패널."""

    item_selected = pyqtSignal(int)   # report_id 전달

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(260)
        self.setMaximumWidth(380)
        self._build()

    # ── UI 조립 ───────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        # 타이틀
        title = QLabel("📋  매매 복기 리포트")
        title.setStyleSheet(
            f"font-weight:bold;font-size:{FS_TITLE};"
            f"color:#aef;padding:2px;"
        )
        lay.addWidget(title)

        # 검색창
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("🔍  제목 / 날짜 검색...")
        self.edt_search.setStyleSheet(
            f"background:#1e1e2e;color:#fff;border:1px solid #555;"
            f"border-radius:4px;padding:5px 8px;font-size:{FS_BODY};"
        )
        lay.addWidget(self.edt_search)

        # 중요도 필터
        flt_row = QHBoxLayout()
        lbl_f = QLabel("중요도:")
        lbl_f.setStyleSheet(f"font-size:{FS_BODY};color:#aaa;")
        flt_row.addWidget(lbl_f)

        self.cmb_filter_imp = QComboBox()
        self.cmb_filter_imp.addItems(["전체", "★★★★★", "★★★★", "★★★", "★★", "★"])
        self.cmb_filter_imp.setStyleSheet(
            f"background:#1e1e2e;color:#ccc;border:1px solid #555;"
            f"border-radius:4px;padding:3px 6px;font-size:{FS_BODY};"
        )
        flt_row.addWidget(self.cmb_filter_imp)
        flt_row.addStretch()
        lay.addLayout(flt_row)

        # 리스트
        self.lst_reports = QListWidget()
        self.lst_reports.setStyleSheet(
            f"QListWidget{{"
            f"  background:#1a1a2e;border:1px solid #444;"
            f"  border-radius:4px;font-size:{FS_LIST};"
            f"}}"
            f"QListWidget::item{{"
            f"  padding:8px 10px;color:#ccc;"
            f"  border-bottom:1px solid #333;"
            f"}}"
            f"QListWidget::item:selected{{background:#2a4a7a;color:#fff;}}"
            f"QListWidget::item:hover{{background:#253050;}}"
        )
        self.lst_reports.currentItemChanged.connect(self._on_item_change)
        lay.addWidget(self.lst_reports, 1)

        # 추가 / 삭제 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_add = QPushButton("＋  새 리포트")
        self.btn_add.setStyleSheet(
            f"background:#1a5276;color:#fff;border-radius:4px;"
            f"padding:8px;font-size:{FS_BODY};font-weight:bold;"
        )
        btn_row.addWidget(self.btn_add)

        self.btn_del = QPushButton("🗑  삭제")
        self.btn_del.setStyleSheet(
            f"background:#5a1a1a;color:#faa;border-radius:4px;"
            f"padding:8px;font-size:{FS_BODY};"
        )
        btn_row.addWidget(self.btn_del)
        lay.addLayout(btn_row)

        # 건수 표시
        self.lbl_count = QLabel("0 건")
        self.lbl_count.setStyleSheet(f"color:#888;font-size:{FS_SMALL};")
        lay.addWidget(self.lbl_count)

    # ── 내부 슬롯 ─────────────────────────────────────────────
    def _on_item_change(self, current, previous):
        if current is None:
            return
        report_id = current.data(Qt.UserRole)
        if report_id is not None:
            self.item_selected.emit(report_id)

    # ══════════════════════════════════════════════════════════
    # 공개 메서드
    # ══════════════════════════════════════════════════════════

    def load_list(self, conn: sqlite3.Connection):
        """DB 쿼리 후 리스트 갱신 (검색어·필터 현재 상태 반영)."""
        keyword = self.edt_search.text().strip()
        imp_idx = self.cmb_filter_imp.currentIndex()

        sql    = "SELECT id, date, title, importance FROM reports WHERE 1=1"
        params: list = []

        if keyword:
            sql    += " AND (title LIKE ? OR date LIKE ?)"
            params += [f"%{keyword}%", f"%{keyword}%"]

        if imp_idx > 0:
            imp_val = 6 - imp_idx       # index 1→5, 2→4, ...
            sql    += " AND importance = ?"
            params.append(imp_val)

        sql += " ORDER BY date DESC, id DESC"

        self.lst_reports.blockSignals(True)
        self.lst_reports.clear()
        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            stars = "★" * row["importance"] + "☆" * (5 - row["importance"])
            text  = f"[{row['date']}]  {stars}\n{row['title'] or '(제목 없음)'}"
            item  = QListWidgetItem(text)
            item.setData(Qt.UserRole, row["id"])
            item.setForeground(QColor("#cccccc"))
            self.lst_reports.addItem(item)

        self.lst_reports.blockSignals(False)
        self.lbl_count.setText(f"{len(rows)} 건")

    def current_report_id(self) -> int | None:
        item = self.lst_reports.currentItem()
        return item.data(Qt.UserRole) if item else None

    def select_item(self, report_id: int):
        """리스트에서 해당 id 항목 선택."""
        for i in range(self.lst_reports.count()):
            item = self.lst_reports.item(i)
            if item.data(Qt.UserRole) == report_id:
                self.lst_reports.setCurrentItem(item)
                break
