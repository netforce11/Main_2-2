"""
tab_report.py — 매매 복기 & 전략 저장소  v1.1
════════════════════════════════════════════════════════════════
위치: IBKR/MAIN2/STRATEGY_REPORT/tab_report.py

main.py 에서 사용:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "STRATEGY_REPORT"))
    from tab_report import ReportTab
    ...
    self.tab_report = ReportTab(self)
    self.tabs.addTab(self.tab_report, "📋 리포트")

변경 이력:
  v1.1 — 파일 분할 (report_const / report_left / report_right)
         폰트 사이즈 +3 적용
         저장 경로: C:\\data\\Report_save\\
════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import os
import json
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QSplitter,
    QMessageBox, QFileDialog,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QPixmap, QKeySequence
from PyQt5.QtWidgets import QShortcut

# ── 같은 패키지 내 모듈 ──────────────────────────────────────
from .report_const  import init_db, STRATEGY_HINTS, CHART_DIR
from .report_left   import ReportLeftPanel
from .report_right  import ReportRightPanel


# ══════════════════════════════════════════════════════════════
# 메인 탭 위젯
# ══════════════════════════════════════════════════════════════
class ReportTab(QWidget):
    """
    매매 복기 & 전략 저장소 탭.
    좌측(ReportLeftPanel) + 우측(ReportRightPanel)을 조립하고
    모든 비즈니스 로직(DB CRUD, 이미지, 힌트)을 담당한다.
    """

    def __init__(self, dashboard=None):
        super().__init__()
        self.dashboard    = dashboard
        self.conn         = init_db()
        self._current_id: int | None = None

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

        self.left  = ReportLeftPanel(self)
        self.right = ReportRightPanel(self)

        self.splitter.addWidget(self.left)
        self.splitter.addWidget(self.right)
        self.splitter.setSizes([310, 1100])

        root.addWidget(self.splitter)

    # ══════════════════════════════════════════════════════════
    # 시그널 연결
    # ══════════════════════════════════════════════════════════
    def _connect_signals(self):
        # 좌측 패널 → 우측 폼 갱신
        self.left.item_selected.connect(self._load_detail)
        self.left.btn_add.clicked.connect(self._new_report)
        self.left.btn_del.clicked.connect(self._delete_report)
        self.left.edt_search.textChanged.connect(self._load_list)
        self.left.cmb_filter_imp.currentIndexChanged.connect(self._load_list)

        # 전략 체크박스 → 힌트 갱신
        for key, chk in self.right._chk_strategies.items():
            chk.stateChanged.connect(lambda _, k=key: self._update_hint())

        # 차트 버튼
        self.right.btn_chart_pick.clicked.connect(self._pick_chart)
        self.right.btn_chart_clear.clicked.connect(self._clear_chart)

        # 저장 버튼
        self.right.btn_save.clicked.connect(self._save_report)
        self.right.btn_save_new.clicked.connect(self._save_and_new)

        # Ctrl+S 단축키
        sc = QShortcut(QKeySequence("Ctrl+S"), self)
        sc.activated.connect(self._save_report)

    # ══════════════════════════════════════════════════════════
    # 리스트 관리
    # ══════════════════════════════════════════════════════════
    def _load_list(self):
        self.left.load_list(self.conn)

    def _new_report(self):
        """빈 폼으로 초기화."""
        self._current_id = None
        self._clear_form()
        self._auto_fill_market_data()

    def _delete_report(self):
        report_id = self.left.current_report_id()
        if not report_id:
            return
        ret = QMessageBox.question(
            self, "삭제 확인",
            "선택한 리포트를 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret == QMessageBox.Yes:
            self.conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
            self.conn.commit()
            self._current_id = None
            self._clear_form()
            self._load_list()

    # ══════════════════════════════════════════════════════════
    # 상세 폼 — 로드 / 클리어
    # ══════════════════════════════════════════════════════════
    def _load_detail(self, report_id: int):
        """DB 단건 조회 → 우측 폼 바인딩."""
        row = self.conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not row:
            return

        r = self.right
        self._current_id = report_id

        r.edt_date.setDate(QDate.fromString(row["date"], "yyyy-MM-dd"))
        r.edt_title.setText(row["title"] or "")
        r.wgt_stars.setValue(row["importance"] or 3)

        tag = row["event_tag"] or ""
        idx = r.cmb_event_tag.findText(tag)
        r.cmb_event_tag.setCurrentIndex(idx if idx >= 0 else 0)

        r.edt_spx.setText(f"{row['spx_price']:.2f}" if row["spx_price"] else "0.00")
        r.edt_vix.setText(f"{row['vix_level']:.2f}" if row["vix_level"] else "0.00")

        r.txt_event.setPlainText(row["event_analysis"]  or "")
        r.txt_product.setPlainText(row["product_detail"] or "")
        r.txt_difficult.setPlainText(row["difficult_zone"] or "")
        r.txt_response.setPlainText(row["response_plan"]  or "")
        r.txt_memo.setPlainText(row["memo"] or "")

        # 전략 체크박스
        try:
            strats = json.loads(row["strategies"] or "[]")
        except Exception:
            strats = []
        for key, chk in r._chk_strategies.items():
            chk.blockSignals(True)
            chk.setChecked(key in strats)
            chk.blockSignals(False)
        self._update_hint()

        self._set_chart_image(row["chart_path"] or "")

    def _clear_form(self):
        r = self.right
        r.edt_date.setDate(QDate.currentDate())
        r.edt_title.clear()
        r.wgt_stars.setValue(3)
        r.cmb_event_tag.setCurrentIndex(0)
        r.edt_spx.setText("0.00")
        r.edt_vix.setText("0.00")
        r.txt_event.clear()
        r.txt_product.clear()
        r.txt_difficult.clear()
        r.txt_response.clear()
        r.txt_memo.clear()
        for chk in r._chk_strategies.values():
            chk.setChecked(False)
        r.lbl_hint.setText("전략을 선택하면 리스크 힌트가 표시됩니다.")
        self._set_chart_image("")

    # ══════════════════════════════════════════════════════════
    # 저장 로직
    # ══════════════════════════════════════════════════════════
    def _save_report(self):
        """현재 폼 내용을 DB에 저장 (신규 또는 수정)."""
        self._auto_fill_market_data(overwrite=False)

        r    = self.right
        path = r.lbl_chart_path.text()

        data = {
            "date":           r.edt_date.date().toString("yyyy-MM-dd"),
            "title":          r.edt_title.text().strip(),
            "importance":     r.wgt_stars.value(),
            "spx_price":      self._safe_float(r.edt_spx.text()),
            "vix_level":      self._safe_float(r.edt_vix.text()),
            "event_tag":      r.cmb_event_tag.currentText(),
            "event_analysis": r.txt_event.toPlainText(),
            "strategies":     json.dumps(self._get_selected_strategies()),
            "product_detail": r.txt_product.toPlainText(),
            "difficult_zone": r.txt_difficult.toPlainText(),
            "response_plan":  r.txt_response.toPlainText(),
            "memo":           r.txt_memo.toPlainText(),
            "chart_path":     "" if path == "(선택된 이미지 없음)" else path,
            "created_at":     datetime.now().isoformat(),
        }

        if self._current_id is None:
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
            self._current_id = cur.lastrowid
        else:
            data["id"] = self._current_id
            self.conn.execute("""
                UPDATE reports SET
                  date=:date, title=:title, importance=:importance,
                  spx_price=:spx_price, vix_level=:vix_level,
                  event_tag=:event_tag, event_analysis=:event_analysis,
                  strategies=:strategies, product_detail=:product_detail,
                  difficult_zone=:difficult_zone, response_plan=:response_plan,
                  memo=:memo, chart_path=:chart_path, created_at=:created_at
                WHERE id=:id
            """, data)

        self.conn.commit()
        self._load_list()
        self.left.select_item(self._current_id)

    def _save_and_new(self):
        self._save_report()
        self._new_report()

    # ══════════════════════════════════════════════════════════
    # 전략 힌트
    # ══════════════════════════════════════════════════════════
    def _update_hint(self):
        selected = self._get_selected_strategies()
        hints    = [STRATEGY_HINTS[k] for k in selected if k in STRATEGY_HINTS]
        self.right.lbl_hint.setText(
            "\n─────\n".join(hints) if hints
            else "전략을 선택하면 리스크 힌트가 표시됩니다."
        )

    def _get_selected_strategies(self) -> list[str]:
        return [k for k, chk in self.right._chk_strategies.items() if chk.isChecked()]

    # ══════════════════════════════════════════════════════════
    # 차트 이미지
    # ══════════════════════════════════════════════════════════
    def _pick_chart(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "차트 이미지 선택",
            str(CHART_DIR),
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if path:
            self._set_chart_image(path)

    def _clear_chart(self):
        self._set_chart_image("")

    def _set_chart_image(self, path: str):
        r = self.right
        if path and os.path.isfile(path):
            r.lbl_chart_path.setText(path)
            r.lbl_chart_path.setStyleSheet("color:#7df;font-size:14px;")
            px = QPixmap(path)
            if not px.isNull():
                r.lbl_chart_img.setPixmap(
                    px.scaled(960, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        r.lbl_chart_path.setText("(선택된 이미지 없음)")
        r.lbl_chart_path.setStyleSheet("color:#666;font-size:14px;")
        r.lbl_chart_img.clear()
        r.lbl_chart_img.setText("차트 이미지를 선택하세요")

    # ══════════════════════════════════════════════════════════
    # 시장 데이터 자동 채우기
    # ══════════════════════════════════════════════════════════
    def _auto_fill_market_data(self, overwrite: bool = True):
        """
        dashboard.tab_callput._und_price → SPX 자동 입력.
        overwrite=False → 이미 값이 있으면 건드리지 않음.

        VIX: DB 컬럼·UI 필드 모두 확보됨.
        연동 방법: dashboard에 vix_price 속성 추가 후
                   아래 주석 블록 해제.
        """
        if not self.dashboard:
            return
        r = self.right

        # SPX
        try:
            tab_cp  = getattr(self.dashboard, 'tab_callput', None)
            spx_val = getattr(tab_cp, '_und_price', 0.0) or 0.0
            if spx_val and (overwrite or r.edt_spx.text() in ("0.00", "0", "")):
                r.edt_spx.setText(f"{spx_val:.2f}")
        except Exception:
            pass

        # VIX — 확장 준비 완료 (주석 해제 후 즉시 연동 가능)
        # try:
        #     vix_val = getattr(self.dashboard, 'vix_price', 0.0) or 0.0
        #     if vix_val and (overwrite or r.edt_vix.text() in ("0.00", "0", "")):
        #         r.edt_vix.setText(f"{vix_val:.2f}")
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

    # ── GridTab / TabWrapper 호환 ────────────────────────────
    def on_tab_activate(self):
        self._load_list()

    def on_tab_deactivate(self):
        pass

    def closeEvent(self, event):
        if self.conn:
            self.conn.close()
        super().closeEvent(event)
