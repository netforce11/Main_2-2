"""
combo_ui_left.py — 복합 전략 탭: 좌측 패널 (LeftPanelMixin)
────────────────────────────────────────────────────────────
빌드·동기화만 담당. 세부 로직은 분리된 파일에 위임:
  combo_ui_left_price.py  — 현재가 조회·tick 수신·거리% 갱신
  combo_ui_left_chain.py  — 체인 클릭·conId 일괄 조회·거리% 셀
  tab_combo_shortcut.py   — Alt+↑↓ 단축키 (eventFilter)

v2.9  — BUG-1/3/7 수정
v3.1  — 파일 분리 (200줄 이내)
v3.2  — 기능 추가
  [ADD-1] 폴더열기 버튼: 캡쳐 버튼 오른쪽에 📁 버튼 추가
          클릭 시 캡쳐 저장 폴더를 파일 관리자로 열기
  [ADD-2] 만기일 고정 표시: 헤더 행2에 lbl_expiry 추가
          체인 동기화 시 _current_expiry 와 함께 항상 갱신
          → 조회 후 만기일이 사라지지 않음
  [ADD-3] 델타 체크박스: 헤더 행2에 체크박스 추가
          체크 시 CALL/PUT 체인 테이블에 델타 컬럼 표시
          델타 컬럼: 인덱스2 (행사가=0, 현재가=1, 델타=2, IV=3, 거리%=4)
          동기화 시 call_data/put_data["delta"] 값 자동 반영
────────────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QMessageBox,
    QTableWidget, QHeaderView, QAbstractItemView,
    QSplitter, QSpinBox, QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtGui import QDesktopServices

from combo_constants import SPLITTER_STYLE, mk_item
from core import REQ_CALL, REQ_PUT

# 델타 컬럼 인덱스 상수
_COL_STRIKE = 0
_COL_PRICE  = 1
_COL_DELTA  = 2
_COL_IV     = 3
_COL_DIST   = 4


class LeftPanelMixin:
    """좌측 패널(옵션 체인) 빌드·동기화 Mixin."""

    # ── 빌드 ──────────────────────────────────────────────────
    def _build_left_panel(self) -> QGroupBox:
        return self._build_chain_panel()

    def _build_chain_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 옵션 체인  (콜-풋 탭 3초 동기화)")
        v  = QVBoxLayout(gb)
        v.setSpacing(3); v.setContentsMargins(4, 6, 4, 4)

        # ── 헤더 행 1: 캡쳐 컨트롤 ────────────────────────────
        sym_row = QHBoxLayout(); sym_row.setSpacing(6)

        # 종목/현재가 조회 위젯 (내부 참조용 — 화면 비표시)
        self.edit_sym_combo = QLineEdit("SPX")
        self.edit_sym_combo.setVisible(False)
        self.lbl_sym_price = QLabel("현재가: ―")
        self.lbl_sym_price.setVisible(False)
        self.edit_expiry_combo = QLineEdit()
        self.edit_expiry_combo.setReadOnly(True)
        self.edit_expiry_combo.setVisible(False)

        # 캡쳐 간격
        lbl_interval = QLabel("캡쳐 간격(초):")
        lbl_interval.setStyleSheet("color:#888;font-size:11px;border:none;")
        sym_row.addWidget(lbl_interval)

        self._capture_spin = QSpinBox()
        self._capture_spin.setRange(10, 3600)
        self._capture_spin.setValue(60)
        self._capture_spin.setSuffix(" 초")
        self._capture_spin.setFixedHeight(24)
        self._capture_spin.setFixedWidth(80)
        self._capture_spin.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-size:11px;font-weight:bold;")
        sym_row.addWidget(self._capture_spin)

        # 캡쳐 토글 버튼
        self._btn_capture_toggle = QPushButton("📷 캡쳐 시작")
        self._btn_capture_toggle.setFixedHeight(26)
        self._btn_capture_toggle.setCheckable(True)
        self._btn_capture_toggle.setStyleSheet(
            "QPushButton{background:#1a2a0a;color:#aaffaa;font-weight:bold;"
            "padding:3px 10px;border:1px solid #3a6a2a;border-radius:3px;}"
            "QPushButton:checked{background:#0a3a0a;color:#00ff88;"
            "border:2px solid #00ff88;}")
        self._btn_capture_toggle.clicked.connect(self._on_capture_toggle)
        sym_row.addWidget(self._btn_capture_toggle)

        # [ADD-1] 폴더열기 버튼 ─────────────────────────────
        self._btn_open_folder = QPushButton("📁")
        self._btn_open_folder.setFixedHeight(26)
        self._btn_open_folder.setFixedWidth(32)
        self._btn_open_folder.setToolTip("캡쳐 저장 폴더 열기")
        self._btn_open_folder.setStyleSheet(
            "QPushButton{background:#1a1a2a;color:#aaaaff;font-weight:bold;"
            "border:1px solid #3a3a6a;border-radius:3px;}"
            "QPushButton:hover{background:#2a2a4a;color:#ccccff;}")
        self._btn_open_folder.clicked.connect(self._on_open_capture_folder)
        sym_row.addWidget(self._btn_open_folder)

        # 상태 라벨
        self._lbl_capture_status = QLabel("대기 중")
        self._lbl_capture_status.setStyleSheet(
            "color:#445566;font-size:11px;border:none;")
        sym_row.addWidget(self._lbl_capture_status)
        sym_row.addStretch()

        # 내부 캡쳐 타이머 초기화
        self._capture_timer  = QTimer()
        self._capture_active = False
        self._capture_timer.timeout.connect(self._do_capture)

        v.addLayout(sym_row)

        # ── 헤더 행 2: 심볼·만기·델타체크박스·동기화 버튼 ────
        hdr = QHBoxLayout(); hdr.setSpacing(8)

        self.lbl_chain_sym = QLabel("종목: ―  |  현재가: ―")
        self.lbl_chain_sym.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        hdr.addWidget(self.lbl_chain_sym)

        # [ADD-2] 만기일 고정 표시 라벨 ─────────────────────
        self._lbl_expiry = QLabel("만기: ―")
        self._lbl_expiry.setStyleSheet(
            "color:#88ddff;font-size:11px;font-weight:bold;"
            "border:1px solid #2a4a6a;border-radius:3px;"
            "padding:1px 6px;background:#051525;")
        hdr.addWidget(self._lbl_expiry)

        hdr.addStretch()

        # [ADD-3] 델타 표시 체크박스 ─────────────────────────
        self._chk_delta = QCheckBox("Δ 델타")
        self._chk_delta.setChecked(False)
        self._chk_delta.setStyleSheet(
            "color:#aaffaa;font-size:11px;border:none;"
            "QCheckBox::indicator{width:13px;height:13px;}")
        self._chk_delta.stateChanged.connect(self._on_delta_toggle)
        hdr.addWidget(self._chk_delta)

        btn_sync = QPushButton("↺ 즉시 동기화")
        btn_sync.setFixedHeight(22)
        btn_sync.clicked.connect(self._sync_chain)
        hdr.addWidget(btn_sync)

        v.addLayout(hdr)

        # 콜/풋 체인 테이블
        inner = QSplitter(Qt.Horizontal)
        inner.setHandleWidth(4); inner.setStyleSheet(SPLITTER_STYLE)
        inner.setChildrenCollapsible(False)
        inner.addWidget(self._build_call_chain())
        inner.addWidget(self._build_put_chain())
        inner.setSizes([300, 300])
        v.addWidget(inner, 1)
        gb.setMinimumWidth(300)
        return gb

    def _build_call_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)
        lbl = QLabel("▲ CALL")
        lbl.setStyleSheet("color:#33aaff;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)
        # [ADD-3] 컬럼 4→5개: 델타 컬럼 추가
        self.tbl_chain_call = QTableWidget(0, 5)
        self.tbl_chain_call.setHorizontalHeaderLabels(
            ["행사가", "현재가", "델타", "IV", "거리%"])
        self._apply_chain_style(self.tbl_chain_call, "#90caf9")
        # 델타 컬럼 기본값: 숨김
        self.tbl_chain_call.setColumnHidden(_COL_DELTA, True)
        self.tbl_chain_call.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "C"))
        lv.addWidget(lbl); lv.addWidget(self.tbl_chain_call)
        return w

    def _build_put_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)
        lbl = QLabel("▼ PUT")
        lbl.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)
        # [ADD-3] 컬럼 4→5개: 델타 컬럼 추가
        self.tbl_chain_put = QTableWidget(0, 5)
        self.tbl_chain_put.setHorizontalHeaderLabels(
            ["행사가", "현재가", "델타", "IV", "거리%"])
        self._apply_chain_style(self.tbl_chain_put, "#ff9999")
        # 델타 컬럼 기본값: 숨김
        self.tbl_chain_put.setColumnHidden(_COL_DELTA, True)
        self.tbl_chain_put.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "P"))
        lv.addWidget(lbl); lv.addWidget(self.tbl_chain_put)
        return w

    @staticmethod
    def _apply_chain_style(tbl: QTableWidget, hdr_color: str):
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            f"QHeaderView::section{{background:#0a0a1e;color:{hdr_color};"
            "border:1px solid #1a1a3a;font-weight:bold;}")

    # ── [ADD-1] 폴더열기 ──────────────────────────────────────
    def _on_open_capture_folder(self):
        """캡쳐 저장 폴더를 파일 관리자로 열기."""
        import os
        save_dir = "/home/netforce/US_Data/Data/Account_pic"
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception:
            pass
        url = QUrl.fromLocalFile(save_dir)
        if not QDesktopServices.openUrl(url):
            self._log(f"⚠ 폴더 열기 실패: {save_dir}")

    # ── [ADD-3] 델타 토글 ─────────────────────────────────────
    def _on_delta_toggle(self, state: int):
        """델타 체크박스 토글 → CALL/PUT 테이블 델타 컬럼 show/hide."""
        show = (state == Qt.Checked)
        self.tbl_chain_call.setColumnHidden(_COL_DELTA, not show)
        self.tbl_chain_put.setColumnHidden(_COL_DELTA, not show)

    # ── 위임 메서드: combo_ui_left_price.py ───────────────────
    def _req_sym_price(self):
        from combo_ui_left_price import _req_sym_price as _f; _f(self)

    def _on_combo_und_tick(self, rid, tt, price):
        from combo_ui_left_price import _on_combo_und_tick as _f; _f(self, rid, tt, price)

    def _apply_und_price_ui(self, price: float):
        from combo_ui_left_price import _apply_und_price_ui as _f; _f(self, price)

    def _refresh_dist_col(self, und_price: float):
        from combo_ui_left_price import _refresh_dist_col as _f; _f(self, und_price)

    # ── 체인 동기화 ───────────────────────────────────────────
    def _auto_sync_chain(self):
        cp = self.mw.tab_callput
        if not cp or (not cp.call_strikes and not cp.put_strikes):
            return
        self._sync_chain_from_cp(cp, silent=True)

    def _sync_chain(self):
        cp = self.mw.tab_callput
        if not cp:
            return
        if not cp.call_strikes and not cp.put_strikes:
            QMessageBox.information(self, "안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_chain_from_cp(cp, silent=False)

    def _sync_chain_from_cp(self, cp, silent=False):
        from combo_ui_left_chain import _make_dist_item, _bulk_fetch_conids
        sym       = cp.edit_sym.text().strip().upper()
        und_price = cp.und_price

        # 왼쪽 패널 종목 입력 필드를 콜-풋 탭 종목과 동기화
        if hasattr(self, 'edit_sym_combo'):
            current_sym = self.edit_sym_combo.text().strip().upper()
            if current_sym != sym:
                self.edit_sym_combo.setText(sym)
                if not silent:
                    self._log(f"🔄 왼쪽 패널 종목 동기화: {current_sym} → {sym}")

        self.lbl_chain_sym.setText(
            f"종목: {sym}  |  현재가: {und_price:,.2f}" if und_price else f"종목: {sym}")
        if und_price:
            self._und_price = und_price
            self.lbl_sym_price.setText(f"현재가: {und_price:,.2f}")
            if hasattr(self, 'edit_stock_price') and not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{und_price:.2f}")

        # ── CALL 갱신 ─────────────────────────────────────────
        self._call_strikes = list(cp.call_strikes)
        self._chain_call   = {}
        self.tbl_chain_call.setRowCount(0)
        for i, st in enumerate(cp.call_strikes):
            d    = cp.call_data.get(REQ_CALL + i, {})
            lp   = d.get("last")
            # [ADD-3] 델타: call_data 의 "delta" 키 (없으면 None)
            delta = d.get("delta")
            self._chain_call[st] = lp
            r = self.tbl_chain_call.rowCount()
            self.tbl_chain_call.insertRow(r)
            self.tbl_chain_call.setItem(r, _COL_STRIKE, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_call.setItem(r, _COL_PRICE,  mk_item(f"{lp:.2f}" if lp else "―", "#33aaff"))
            # 델타 셀: 값 있으면 표시, 콜 델타는 양수(0~1)
            if delta is not None:
                delta_txt   = f"{delta:+.3f}"
                delta_color = "#88ff88" if delta >= 0 else "#ff8888"
            else:
                delta_txt   = "―"
                delta_color = "#555577"
            self.tbl_chain_call.setItem(r, _COL_DELTA, mk_item(delta_txt, delta_color))
            self.tbl_chain_call.setItem(r, _COL_IV,   mk_item("―"))
            self.tbl_chain_call.setItem(r, _COL_DIST, _make_dist_item(st, und_price, "C"))

        # ── PUT 갱신 ──────────────────────────────────────────
        self._put_strikes = list(cp.put_strikes)
        self._chain_put   = {}
        self.tbl_chain_put.setRowCount(0)
        for i, st in enumerate(cp.put_strikes):
            d    = cp.put_data.get(REQ_PUT + i, {})
            lp   = d.get("last")
            # [ADD-3] 델타: put_data 의 "delta" 키
            delta = d.get("delta")
            self._chain_put[st] = lp
            r = self.tbl_chain_put.rowCount()
            self.tbl_chain_put.insertRow(r)
            self.tbl_chain_put.setItem(r, _COL_STRIKE, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_put.setItem(r, _COL_PRICE,  mk_item(f"{lp:.2f}" if lp else "―", "#ff6666"))
            # 델타 셀: 풋 델타는 음수(-1~0)
            if delta is not None:
                delta_txt   = f"{delta:+.3f}"
                delta_color = "#ff8888" if delta < 0 else "#88ff88"
            else:
                delta_txt   = "―"
                delta_color = "#555577"
            self.tbl_chain_put.setItem(r, _COL_DELTA, mk_item(delta_txt, delta_color))
            self.tbl_chain_put.setItem(r, _COL_IV,   mk_item("―"))
            self.tbl_chain_put.setItem(r, _COL_DIST, _make_dist_item(st, und_price, "P"))

        # ── 만기 파싱 + [ADD-2] lbl_expiry 갱신 ──────────────
        try:
            expiry_code = ""
            if hasattr(cp, '_expiry_list') and cp._expiry_list:
                idx = getattr(cp, 'combo_exp', None)
                if idx is not None:
                    ci = idx.currentIndex()
                    if 0 <= ci < len(cp._expiry_list):
                        _, expiry_code, _ = cp._expiry_list[ci]
                        if expiry_code == "CUSTOM":
                            ew = getattr(cp, 'edit_custom', None)
                            expiry_code = ew.text().strip() if ew else ""
            elif hasattr(cp, 'date_edit'):
                expiry_code = cp.date_edit.date().toString("yyyyMMdd")

            if expiry_code and len(expiry_code) == 8:
                ed = getattr(self, 'edit_expiry_combo', None)
                if ed:
                    ed.setText(expiry_code)
                    ed.setToolTip(
                        f"만기: {expiry_code[:4]}-{expiry_code[4:6]}-{expiry_code[6:8]}")
                self._current_expiry = expiry_code

                # [ADD-2] 만기 라벨 항상 갱신
                mm = expiry_code[4:6]
                dd = expiry_code[6:8]
                self._lbl_expiry.setText(f"만기: {mm}/{dd}")
                self._lbl_expiry.setStyleSheet(
                    "color:#00ffcc;font-size:11px;font-weight:bold;"
                    "border:1px solid #2a6a5a;border-radius:3px;"
                    "padding:1px 6px;background:#051a15;")
            else:
                # 만기 미확인 시 회색 표시
                self._lbl_expiry.setText("만기: ―")
                self._lbl_expiry.setStyleSheet(
                    "color:#88ddff;font-size:11px;font-weight:bold;"
                    "border:1px solid #2a4a6a;border-radius:3px;"
                    "padding:1px 6px;background:#051525;")
        except Exception:
            pass

        if not silent:
            self._log(f"체인 동기화: {sym}  C{len(cp.call_strikes)} / P{len(cp.put_strikes)}")

        raw_expiry = getattr(self, '_current_expiry', '')
        first_run  = not getattr(self, '_conid_bulk_done', False)
        if (not silent or first_run) and raw_expiry and (self._call_strikes or self._put_strikes):
            self._conid_bulk_done = True
            _bulk_fetch_conids(self, sym, raw_expiry, self._call_strikes, self._put_strikes)

    # ── 위임 메서드: combo_ui_left_chain.py ───────────────────
    def _on_chain_click(self, row: int, col: int, side: str):
        from combo_ui_left_chain import _on_chain_click as _f; _f(self, row, col, side)

    # ── 자동 캡쳐 ─────────────────────────────────────────────
    def _on_capture_toggle(self, checked: bool):
        if checked:
            interval_ms = self._capture_spin.value() * 1000
            self._capture_timer.start(interval_ms)
            self._capture_active = True
            self._btn_capture_toggle.setText("⏹ 캡쳐 정지")
            self._lbl_capture_status.setStyleSheet(
                "color:#00ff88;font-size:11px;border:none;font-weight:bold;")
            self._lbl_capture_status.setText(
                f"●  {self._capture_spin.value()}초마다 저장 중")
            self._log(f"📷 자동 캡쳐 시작: {self._capture_spin.value()}초 간격")
            self._do_capture()
        else:
            self._capture_timer.stop()
            self._capture_active = False
            self._btn_capture_toggle.setText("📷 캡쳐 시작")
            self._lbl_capture_status.setStyleSheet(
                "color:#445566;font-size:11px;border:none;")
            self._lbl_capture_status.setText("대기 중")
            self._log("📷 자동 캡쳐 정지")

    def _do_capture(self):
        """실제 캡쳐 & 저장."""
        import os
        from datetime import datetime
        from PyQt5.QtWidgets import QApplication

        save_dir = "/home/netforce/US_Data/Data/Account_pic"
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            self._log(f"❌ 캡쳐 폴더 생성 실패: {e}")
            return

        now      = datetime.now()
        filename = now.strftime("Account_%Y%m%d_%H%M%S.jpg")
        filepath = os.path.join(save_dir, filename)

        try:
            target = self.mw if hasattr(self, 'mw') else self
            screen  = QApplication.primaryScreen()
            pixmap  = screen.grabWindow(target.winId())
            if pixmap.save(filepath, "JPG", 92):
                self._lbl_capture_status.setText(f"●  저장: {filename}")
                self._log(f"📸 캡쳐 저장: {filepath}")
            else:
                self._log(f"❌ 캡쳐 저장 실패: {filepath}")
        except Exception as e:
            self._log(f"❌ 캡쳐 오류: {e}")