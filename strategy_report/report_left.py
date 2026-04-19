"""
report_left.py — 좌측 통합 리스트 패널   v2.0
════════════════════════════════════════════════
위치: IBKR/MAIN2/strategy_report/report_left.py

변경:
  v2.0 — 복기/상품 두 타입을 하나의 리스트로 통합
         타입 필터 콤보 추가 (전체 / 복기만 / 상품만)
         "＋ 복기" / "＋ 상품" 버튼 분리
         item 배지: [복기] 파란색, [상품] 초록색
"""

from __future__ import annotations

import sqlite3

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from .report_const import (
    FS_TITLE, FS_BODY, FS_SMALL, FS_LIST,
    REC_TRADE, REC_PRODUCT,
)

# 타입별 색상
COLOR_TRADE   = QColor("#3a7bd5")   # 파랑 — 복기
COLOR_PRODUCT = QColor("#27ae60")   # 초록 — 상품


class ReportLeftPanel(QWidget):
    """복기·상품 통합 목록 패널."""

    # 선택된 레코드 id + 타입 전달
    item_selected = pyqtSignal(int, str)   # (id, rec_type)
    add_trade     = pyqtSignal()
    add_product   = pyqtSignal()
    delete_record = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(270)
        self.setMaximumWidth(390)
        self._build()

    # ── UI 조립 ───────────────────────────────────────────────
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        # 타이틀
        title = QLabel("📋  매매 노트")
        title.setStyleSheet(
            f"font-weight:bold;font-size:{FS_TITLE};"
            f"color:#aef;padding:2px;"
        )
        lay.addWidget(title)

        # 검색창
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("🔍  제목 / 심볼 / 날짜 검색...")
        self.edt_search.setStyleSheet(
            f"background:#1e1e2e;color:#fff;border:1px solid #555;"
            f"border-radius:4px;padding:5px 8px;font-size:{FS_BODY};"
        )
        lay.addWidget(self.edt_search)

        # 타입 필터 + 중요도 필터
        flt_row = QHBoxLayout()
        flt_row.setSpacing(6)

        lbl_t = QLabel("분류:")
        lbl_t.setStyleSheet(f"font-size:{FS_BODY};color:#aaa;")
        flt_row.addWidget(lbl_t)

        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["전체", "📒 복기", "📗 상품"])
        self.cmb_type.setFixedWidth(100)
        self.cmb_type.setStyleSheet(
            f"background:#1e1e2e;color:#ccc;border:1px solid #555;"
            f"border-radius:4px;padding:3px 6px;font-size:{FS_BODY};"
        )
        flt_row.addWidget(self.cmb_type)

        lbl_i = QLabel("중요도:")
        lbl_i.setStyleSheet(f"font-size:{FS_BODY};color:#aaa;")
        flt_row.addWidget(lbl_i)

        self.cmb_filter_imp = QComboBox()
        self.cmb_filter_imp.addItems(["전체", "★★★★★", "★★★★", "★★★", "★★", "★"])
        self.cmb_filter_imp.setFixedWidth(90)
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
            f"  padding:6px 10px;color:#ccc;"
            f"  min-height:44px;"
            f"  border-bottom:1px solid #2a2a3e;"
            f"}}"
            f"QListWidget::item:selected{{background:#2a4a7a;color:#fff;}}"
            f"QListWidget::item:hover{{background:#253050;}}"
        )
        self.lst_reports.currentItemChanged.connect(self._on_item_change)
        lay.addWidget(self.lst_reports, 1)

        # 추가 버튼 2개
        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        self.btn_add_trade = QPushButton("📒 ＋ 복기")
        self.btn_add_trade.setStyleSheet(
            f"background:#1a3a6a;color:#7af;border-radius:4px;"
            f"padding:8px;font-size:{FS_BODY};font-weight:bold;"
        )
        self.btn_add_trade.clicked.connect(self.add_trade)
        add_row.addWidget(self.btn_add_trade)

        self.btn_add_product = QPushButton("📗 ＋ 상품")
        self.btn_add_product.setStyleSheet(
            f"background:#1a4a2a;color:#7fa;border-radius:4px;"
            f"padding:8px;font-size:{FS_BODY};font-weight:bold;"
        )
        self.btn_add_product.clicked.connect(self.add_product)
        add_row.addWidget(self.btn_add_product)

        lay.addLayout(add_row)

        # 삭제 버튼
        self.btn_del = QPushButton("🗑  선택 삭제")
        self.btn_del.setStyleSheet(
            f"background:#3a1a1a;color:#faa;border-radius:4px;"
            f"padding:7px;font-size:{FS_BODY};"
        )
        self.btn_del.clicked.connect(self.delete_record)
        lay.addWidget(self.btn_del)

        # 건수
        self.lbl_count = QLabel("0 건")
        self.lbl_count.setStyleSheet(f"color:#888;font-size:{FS_SMALL};")
        lay.addWidget(self.lbl_count)

    # ── 내부 슬롯 ─────────────────────────────────────────────
    def _on_item_change(self, current, previous):
        if current is None:
            return
        rec_id   = current.data(Qt.UserRole)
        rec_type = current.data(Qt.UserRole + 1)
        if rec_id is not None:
            self.item_selected.emit(rec_id, rec_type)

    # ══════════════════════════════════════════════════════════
    # 공개 메서드
    # ══════════════════════════════════════════════════════════
    def load_list(self, conn: sqlite3.Connection):
        """DB에서 복기·상품 목록을 통합 조회해 리스트 갱신."""
        keyword  = self.edt_search.text().strip()
        type_idx = self.cmb_type.currentIndex()       # 0=전체, 1=복기, 2=상품
        imp_idx  = self.cmb_filter_imp.currentIndex() # 0=전체, 1~5=별점

        rows_all = []

        # ── 복기 쿼리 ──────────────────────────────────────────
        if type_idx in (0, 1):
            sql = ("SELECT id, date AS sort_key, title, importance, "
                   "'' AS symbol, 'trade' AS rec_type "
                   "FROM reports WHERE 1=1")
            params: list = []
            if keyword:
                sql    += " AND (title LIKE ? OR date LIKE ?)"
                params += [f"%{keyword}%", f"%{keyword}%"]
            if imp_idx > 0:
                sql    += " AND importance = ?"
                params.append(6 - imp_idx)
            rows_all += list(conn.execute(sql, params).fetchall())

        # ── 상품 쿼리 ──────────────────────────────────────────
        if type_idx in (0, 2):
            sql = ("SELECT id, updated_at AS sort_key, title, importance, "
                   "symbol, 'product' AS rec_type "
                   "FROM products WHERE 1=1")
            params = []
            if keyword:
                sql    += " AND (title LIKE ? OR symbol LIKE ?)"
                params += [f"%{keyword}%", f"%{keyword}%"]
            if imp_idx > 0:
                sql    += " AND importance = ?"
                params.append(6 - imp_idx)
            rows_all += list(conn.execute(sql, params).fetchall())

        # ── 정렬: sort_key 역순 ────────────────────────────────
        rows_all.sort(key=lambda r: (r["sort_key"] or ""), reverse=True)

        self.lst_reports.blockSignals(True)
        self.lst_reports.clear()

        for row in rows_all:
            rtype  = row["rec_type"]
            stars  = "★" * row["importance"]
            title  = (row["title"] or "(제목 없음)")[:24]   # 최대 24자
            symbol = row["symbol"] or ""
            date   = (row["sort_key"] or "")[:10]

            if rtype == REC_TRADE:
                badge = "📒"
                # 날짜(10) + 별(importance개) + 제목
                text  = f"{badge} {date}  {stars}\n     {title}"
                color = COLOR_TRADE
            else:
                badge   = "📗"
                sym_str = f" [{symbol}]" if symbol else ""
                # 별 + 심볼 + 제목
                text  = f"{badge}{sym_str}  {stars}\n     {title}"
                color = COLOR_PRODUCT

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole,     row["id"])
            item.setData(Qt.UserRole + 1, rtype)
            item.setForeground(color)
            self.lst_reports.addItem(item)

        self.lst_reports.blockSignals(False)
        self.lbl_count.setText(
            f"{len(rows_all)} 건  "
            f"(복기 {sum(1 for r in rows_all if r['rec_type']==REC_TRADE)}  "
            f"/ 상품 {sum(1 for r in rows_all if r['rec_type']==REC_PRODUCT)})"
        )

    def current_record(self) -> tuple[int, str] | tuple[None, None]:
        """(id, rec_type) 반환. 선택 없으면 (None, None)."""
        item = self.lst_reports.currentItem()
        if item is None:
            return None, None
        return item.data(Qt.UserRole), item.data(Qt.UserRole + 1)

    def select_item(self, rec_id: int, rec_type: str):
        for i in range(self.lst_reports.count()):
            item = self.lst_reports.item(i)
            if (item.data(Qt.UserRole) == rec_id and
                    item.data(Qt.UserRole + 1) == rec_type):
                self.lst_reports.setCurrentItem(item)
                break