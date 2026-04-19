"""
tab_report.py — 매매 노트 탭  v2.0
════════════════════════════════════════════════════════════════
위치: IBKR/MAIN2/strategy_report/tab_report.py

구조:
  좌측 ReportLeftPanel  — 복기·상품 통합 리스트
  우측 QTabWidget       — [📒 매매 복기] / [📗 상품·전략 메모] 전환

변경:
  v2.0 — 상품·전략 메모 폼(ProductFormPanel) 추가
         products DB 테이블 CRUD
         리스트 클릭 시 타입에 따라 탭 자동 전환
"""

from __future__ import annotations

import os
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter,
    QTabWidget, QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QPixmap, QKeySequence
from PyQt5.QtWidgets import QShortcut

from .report_const  import init_db, STRATEGY_HINTS, CHART_DIR, REC_TRADE, REC_PRODUCT
from .report_left   import ReportLeftPanel
from .report_right  import TradeFormPanel
from .report_product import ProductFormPanel


class ReportTab(QWidget):
    """
    매매 노트 탭 — 복기 + 상품·전략 메모 통합.

    main.py 에서:
        from strategy_report.tab_report import ReportTab
        self.tab_report = ReportTab(self)
        self.tabs.addTab(self.tab_report, "📋 매매 노트")
    """

    def __init__(self, dashboard=None):
        super().__init__()
        self.dashboard   = dashboard
        self.conn        = init_db()
        self._trade_id:   int | None = None
        self._product_id: int | None = None

        self._build_ui()
        self._connect_signals()
        self._load_list()

    # ══════════════════════════════════════════════════════════
    # UI 조립
    # ══════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(5)

        # 좌측 리스트
        self.left = ReportLeftPanel(self)

        # 우측 탭위젯
        self.right_tabs = QTabWidget()
        self.right_tabs.setTabPosition(QTabWidget.North)
        self.right_tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #333;background:#111;}"
            "QTabBar::tab{background:#1a1a2e;color:#aaa;padding:8px 18px;"
            "  font-size:15px;border:1px solid #333;border-bottom:none;}"
            "QTabBar::tab:selected{background:#2a2a4e;color:#fff;"
            "  font-weight:bold;}"
            "QTabBar::tab:hover{background:#222240;}"
        )

        self.trade_form   = TradeFormPanel(self)
        self.product_form = ProductFormPanel(self)

        self.right_tabs.addTab(self.trade_form,   "📒  매매 복기")
        self.right_tabs.addTab(self.product_form, "📗  상품·전략 메모")

        self.splitter.addWidget(self.left)
        self.splitter.addWidget(self.right_tabs)
        self.splitter.setSizes([310, 1100])

        root.addWidget(self.splitter)

    # ══════════════════════════════════════════════════════════
    # 시그널 연결
    # ══════════════════════════════════════════════════════════
    def _connect_signals(self):
        # 리스트
        self.left.item_selected.connect(self._on_item_selected)
        self.left.add_trade.connect(self._new_trade)
        self.left.add_product.connect(self._new_product)
        self.left.delete_record.connect(self._delete_record)
        self.left.edt_search.textChanged.connect(self._load_list)
        self.left.cmb_type.currentIndexChanged.connect(self._load_list)
        self.left.cmb_filter_imp.currentIndexChanged.connect(self._load_list)

        # 복기 폼
        tf = self.trade_form
        for key, chk in tf._chk_strategies.items():
            chk.stateChanged.connect(lambda _, k=key: self._update_hint())
        tf.btn_chart_pick.clicked.connect(self._pick_chart)
        tf.btn_chart_clear.clicked.connect(self._clear_chart)
        tf.btn_save.clicked.connect(self._save_trade)
        tf.btn_save_new.clicked.connect(self._save_trade_and_new)

        # 상품 폼
        pf = self.product_form
        pf.btn_save.clicked.connect(self._save_product)
        pf.btn_save_new.clicked.connect(self._save_product_and_new)

        # Ctrl+S — 현재 활성 탭 저장
        sc = QShortcut(QKeySequence("Ctrl+S"), self)
        sc.activated.connect(self._save_current)

    # ══════════════════════════════════════════════════════════
    # 리스트 이벤트
    # ══════════════════════════════════════════════════════════
    def _load_list(self):
        self.left.load_list(self.conn)

    def _on_item_selected(self, rec_id: int, rec_type: str):
        """리스트 클릭 → 타입에 따라 탭 전환 + 폼 로드."""
        if rec_type == REC_TRADE:
            self.right_tabs.setCurrentIndex(0)
            self._load_trade(rec_id)
        else:
            self.right_tabs.setCurrentIndex(1)
            self._load_product(rec_id)

    # ══════════════════════════════════════════════════════════
    # 삭제
    # ══════════════════════════════════════════════════════════
    def _delete_record(self):
        rec_id, rec_type = self.left.current_record()
        if rec_id is None:
            return
        type_str = "복기" if rec_type == REC_TRADE else "상품 메모"
        ret = QMessageBox.question(
            self, "삭제 확인",
            f"선택한 [{type_str}] 를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        table = "reports" if rec_type == REC_TRADE else "products"
        self.conn.execute(f"DELETE FROM {table} WHERE id=?", (rec_id,))
        self.conn.commit()
        if rec_type == REC_TRADE:
            self._trade_id = None
            self._clear_trade_form()
        else:
            self._product_id = None
            self._clear_product_form()
        self._load_list()

    # ══════════════════════════════════════════════════════════
    # ── 매매 복기 CRUD ────────────────────────────────────────
    # ══════════════════════════════════════════════════════════
    def _new_trade(self):
        self._trade_id = None
        self._clear_trade_form()
        self._auto_fill_market_data()
        self.right_tabs.setCurrentIndex(0)

    def _load_trade(self, report_id: int):
        row = self.conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not row:
            return
        self._trade_id = report_id
        tf = self.trade_form

        tf.edt_date.setDate(QDate.fromString(row["date"], "yyyy-MM-dd"))
        tf.edt_title.setText(row["title"] or "")
        tf.wgt_stars.setValue(row["importance"] or 3)

        idx = tf.cmb_event_tag.findText(row["event_tag"] or "")
        tf.cmb_event_tag.setCurrentIndex(idx if idx >= 0 else 0)

        tf.edt_spx.setText(f"{row['spx_price']:.2f}" if row["spx_price"] else "0.00")
        tf.edt_vix.setText(f"{row['vix_level']:.2f}" if row["vix_level"] else "0.00")
        tf.txt_event.setPlainText(row["event_analysis"]  or "")
        tf.txt_product.setPlainText(row["product_detail"] or "")
        tf.txt_difficult.setPlainText(row["difficult_zone"] or "")
        tf.txt_response.setPlainText(row["response_plan"]  or "")
        tf.txt_memo.setPlainText(row["memo"] or "")

        try:
            strats = json.loads(row["strategies"] or "[]")
        except Exception:
            strats = []
        for key, chk in tf._chk_strategies.items():
            chk.blockSignals(True)
            chk.setChecked(key in strats)
            chk.blockSignals(False)
        self._update_hint()
        self._set_chart_image(row["chart_path"] or "")

    def _clear_trade_form(self):
        tf = self.trade_form
        tf.edt_date.setDate(QDate.currentDate())
        tf.edt_title.clear()
        tf.wgt_stars.setValue(3)
        tf.cmb_event_tag.setCurrentIndex(0)
        tf.edt_spx.setText("0.00")
        tf.edt_vix.setText("0.00")
        tf.txt_event.clear()
        tf.txt_product.clear()
        tf.txt_difficult.clear()
        tf.txt_response.clear()
        tf.txt_memo.clear()
        for chk in tf._chk_strategies.values():
            chk.setChecked(False)
        tf.lbl_hint.setText("전략을 선택하면 리스크 힌트가 표시됩니다.")
        self._set_chart_image("")

    def _save_trade(self):
        self._auto_fill_market_data(overwrite=False)
        tf   = self.trade_form
        path = tf.lbl_chart_path.text()
        data = {
            "date":           tf.edt_date.date().toString("yyyy-MM-dd"),
            "title":          tf.edt_title.text().strip(),
            "importance":     tf.wgt_stars.value(),
            "spx_price":      self._safe_float(tf.edt_spx.text()),
            "vix_level":      self._safe_float(tf.edt_vix.text()),
            "event_tag":      tf.cmb_event_tag.currentText(),
            "event_analysis": tf.txt_event.toPlainText(),
            "strategies":     json.dumps(self._get_strategies()),
            "product_detail": tf.txt_product.toPlainText(),
            "difficult_zone": tf.txt_difficult.toPlainText(),
            "response_plan":  tf.txt_response.toPlainText(),
            "memo":           tf.txt_memo.toPlainText(),
            "chart_path":     "" if path == "(선택된 이미지 없음)" else path,
            "created_at":     datetime.now().isoformat(),
        }
        if self._trade_id is None:
            cur = self.conn.execute("""
                INSERT INTO reports
                  (date,title,importance,spx_price,vix_level,event_tag,
                   event_analysis,strategies,product_detail,
                   difficult_zone,response_plan,memo,chart_path,created_at)
                VALUES
                  (:date,:title,:importance,:spx_price,:vix_level,:event_tag,
                   :event_analysis,:strategies,:product_detail,
                   :difficult_zone,:response_plan,:memo,:chart_path,:created_at)
            """, data)
            self._trade_id = cur.lastrowid
        else:
            data["id"] = self._trade_id
            self.conn.execute("""
                UPDATE reports SET
                  date=:date,title=:title,importance=:importance,
                  spx_price=:spx_price,vix_level=:vix_level,
                  event_tag=:event_tag,event_analysis=:event_analysis,
                  strategies=:strategies,product_detail=:product_detail,
                  difficult_zone=:difficult_zone,response_plan=:response_plan,
                  memo=:memo,chart_path=:chart_path,created_at=:created_at
                WHERE id=:id
            """, data)
        self.conn.commit()
        self._load_list()
        self.left.select_item(self._trade_id, REC_TRADE)

    def _save_trade_and_new(self):
        self._save_trade()
        self._new_trade()

    # ══════════════════════════════════════════════════════════
    # ── 상품 메모 CRUD ─────────────────────────────────────────
    # ══════════════════════════════════════════════════════════
    def _new_product(self):
        self._product_id = None
        self._clear_product_form()
        self.right_tabs.setCurrentIndex(1)

    def _load_product(self, product_id: int):
        row = self.conn.execute(
            "SELECT * FROM products WHERE id=?", (product_id,)
        ).fetchone()
        if not row:
            return
        self._product_id = product_id
        pf = self.product_form

        pf.edt_title.setText(row["title"] or "")
        pf.edt_symbol.setText(row["symbol"] or "")
        pf.wgt_stars.setValue(row["importance"] or 3)

        idx = pf.cmb_category.findText(row["category"] or "")
        pf.cmb_category.setCurrentIndex(idx if idx >= 0 else 0)

        # 호가 단위
        tick = row["tick_size"] or ""
        from .report_const import TICK_SIZES
        if tick in TICK_SIZES:
            pf.cmb_tick_size.setCurrentText(tick)
        elif tick:
            pf.cmb_tick_size.setCurrentText("직접입력")
            pf.edt_tick_custom.setText(tick)
            pf.edt_tick_custom.setVisible(True)

        pf.edt_tick_value.setText(row["tick_value"]    or "")
        pf.edt_contract_unit.setText(row["contract_unit"] or "")
        pf.edt_related.setText(row["related_products"] or "")
        pf.edt_opposite.setText(row["opposite_product"] or "")

        idx2 = pf.cmb_expiry_type.findText(row["expiry_type"] or "")
        pf.cmb_expiry_type.setCurrentIndex(idx2 if idx2 >= 0 else 0)

        pf.txt_expiry_features.setPlainText(row["expiry_features"]  or "")
        pf.txt_characteristics.setPlainText(row["characteristics"]  or "")
        pf.txt_strategy_memo.setPlainText(row["strategy_memo"]    or "")
        pf.txt_entry.setPlainText(row["entry_conditions"] or "")
        pf.txt_exit.setPlainText(row["exit_conditions"]  or "")
        pf.txt_risk_memo.setPlainText(row["risk_memo"]       or "")
        pf.txt_memo.setPlainText(row["memo"]             or "")

    def _clear_product_form(self):
        pf = self.product_form
        pf.edt_title.clear()
        pf.edt_symbol.clear()
        pf.wgt_stars.setValue(3)
        pf.cmb_category.setCurrentIndex(0)
        pf.cmb_tick_size.setCurrentIndex(0)
        pf.edt_tick_custom.clear()
        pf.edt_tick_custom.setVisible(False)
        pf.edt_tick_value.clear()
        pf.edt_contract_unit.clear()
        pf.edt_related.clear()
        pf.edt_opposite.clear()
        pf.cmb_expiry_type.setCurrentIndex(0)
        pf.txt_expiry_features.clear()
        pf.txt_characteristics.clear()
        pf.txt_strategy_memo.clear()
        pf.txt_entry.clear()
        pf.txt_exit.clear()
        pf.txt_risk_memo.clear()
        pf.txt_memo.clear()

    def _save_product(self):
        pf  = self.product_form
        now = datetime.now().isoformat()
        data = {
            "title":            pf.edt_title.text().strip(),
            "category":         pf.cmb_category.currentText(),
            "symbol":           pf.edt_symbol.text().strip(),
            "contract_unit":    pf.edt_contract_unit.text().strip(),
            "tick_size":        pf.tick_size_value(),
            "tick_value":       pf.edt_tick_value.text().strip(),
            "related_products": pf.edt_related.text().strip(),
            "opposite_product": pf.edt_opposite.text().strip(),
            "expiry_type":      pf.cmb_expiry_type.currentText(),
            "expiry_features":  pf.txt_expiry_features.toPlainText(),
            "characteristics":  pf.txt_characteristics.toPlainText(),
            "strategy_memo":    pf.txt_strategy_memo.toPlainText(),
            "entry_conditions": pf.txt_entry.toPlainText(),
            "exit_conditions":  pf.txt_exit.toPlainText(),
            "risk_memo":        pf.txt_risk_memo.toPlainText(),
            "memo":             pf.txt_memo.toPlainText(),
            "importance":       pf.wgt_stars.value(),
            "updated_at":       now,
        }
        if self._product_id is None:
            data["created_at"] = now
            cur = self.conn.execute("""
                INSERT INTO products
                  (title,category,symbol,contract_unit,tick_size,tick_value,
                   related_products,opposite_product,expiry_type,expiry_features,
                   characteristics,strategy_memo,entry_conditions,exit_conditions,
                   risk_memo,memo,importance,created_at,updated_at)
                VALUES
                  (:title,:category,:symbol,:contract_unit,:tick_size,:tick_value,
                   :related_products,:opposite_product,:expiry_type,:expiry_features,
                   :characteristics,:strategy_memo,:entry_conditions,:exit_conditions,
                   :risk_memo,:memo,:importance,:created_at,:updated_at)
            """, data)
            self._product_id = cur.lastrowid
        else:
            data["id"] = self._product_id
            self.conn.execute("""
                UPDATE products SET
                  title=:title,category=:category,symbol=:symbol,
                  contract_unit=:contract_unit,tick_size=:tick_size,
                  tick_value=:tick_value,related_products=:related_products,
                  opposite_product=:opposite_product,expiry_type=:expiry_type,
                  expiry_features=:expiry_features,characteristics=:characteristics,
                  strategy_memo=:strategy_memo,entry_conditions=:entry_conditions,
                  exit_conditions=:exit_conditions,risk_memo=:risk_memo,
                  memo=:memo,importance=:importance,updated_at=:updated_at
                WHERE id=:id
            """, data)
        self.conn.commit()
        self._load_list()
        self.left.select_item(self._product_id, REC_PRODUCT)

    def _save_product_and_new(self):
        self._save_product()
        self._new_product()

    # ══════════════════════════════════════════════════════════
    # Ctrl+S 분기
    # ══════════════════════════════════════════════════════════
    def _save_current(self):
        if self.right_tabs.currentIndex() == 0:
            self._save_trade()
        else:
            self._save_product()

    # ══════════════════════════════════════════════════════════
    # 전략 힌트 (복기 폼 전용)
    # ══════════════════════════════════════════════════════════
    def _update_hint(self):
        selected = self._get_strategies()
        hints    = [STRATEGY_HINTS[k] for k in selected if k in STRATEGY_HINTS]
        self.trade_form.lbl_hint.setText(
            "\n─────\n".join(hints) if hints
            else "전략을 선택하면 리스크 힌트가 표시됩니다."
        )

    def _get_strategies(self) -> list[str]:
        return [k for k, chk in self.trade_form._chk_strategies.items()
                if chk.isChecked()]

    # ══════════════════════════════════════════════════════════
    # 차트 이미지 (복기 폼 전용)
    # ══════════════════════════════════════════════════════════
    def _pick_chart(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "차트 이미지 선택", str(CHART_DIR),
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if path:
            self._set_chart_image(path)

    def _clear_chart(self):
        self._set_chart_image("")

    def _set_chart_image(self, path: str):
        tf = self.trade_form
        if path and os.path.isfile(path):
            tf.lbl_chart_path.setText(path)
            tf.lbl_chart_path.setStyleSheet("color:#7df;font-size:14px;")
            px = QPixmap(path)
            if not px.isNull():
                tf.lbl_chart_img.setPixmap(
                    px.scaled(960, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        tf.lbl_chart_path.setText("(선택된 이미지 없음)")
        tf.lbl_chart_path.setStyleSheet("color:#666;font-size:14px;")
        tf.lbl_chart_img.clear()
        tf.lbl_chart_img.setText("차트 이미지를 선택하세요")

    # ══════════════════════════════════════════════════════════
    # 시장 데이터 자동 채우기
    # ══════════════════════════════════════════════════════════
    def _auto_fill_market_data(self, overwrite: bool = True):
        if not self.dashboard:
            return
        tf = self.trade_form
        try:
            tab_cp  = getattr(self.dashboard, 'tab_callput', None)
            spx_val = getattr(tab_cp, '_und_price', 0.0) or 0.0
            if spx_val and (overwrite or tf.edt_spx.text() in ("0.00", "0", "")):
                tf.edt_spx.setText(f"{spx_val:.2f}")
        except Exception:
            pass
        # VIX 확장 준비 (주석 해제로 즉시 연동)
        # try:
        #     vix_val = getattr(self.dashboard, 'vix_price', 0.0) or 0.0
        #     if vix_val and (overwrite or tf.edt_vix.text() in ("0.00","0","")):
        #         tf.edt_vix.setText(f"{vix_val:.2f}")
        # except Exception:
        #     pass

    # ══════════════════════════════════════════════════════════
    # 유틸
    # ══════════════════════════════════════════════════════════
    @staticmethod
    def _safe_float(text: str) -> float:
        try:
            return float(text.replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    def on_tab_activate(self):
        self._load_list()

    def on_tab_deactivate(self):
        pass

    def closeEvent(self, event):
        if self.conn:
            self.conn.close()
        super().closeEvent(event)