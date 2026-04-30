# -*- coding: utf-8 -*-
"""
spxw_1min_tab.py — SPXW 0DTE 1분봉 수집/조회/저장 탭
1초봉 탭(spxw_tab.py)과 동일한 구조, 1분봉 전용
"""
from __future__ import annotations

import os
import threading
import queue as _queue_module

from datetime import date as dt_date
from typing import List, Dict, Any, Optional, Tuple

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QGroupBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy, QPlainTextEdit,
    QListWidget, QListWidgetItem, QSpinBox,
    QDateEdit, QMessageBox, QCalendarWidget, QApplication
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, pyqtSlot, QTimer

from spxw_core import (
    build_spx_zero_day_symbol,
    _load_api_key_from_file,
    _is_summer_time,
    MiniChartCanvas,
    _OPT_1MIN_DIR,
    _make_save_path, _save_rows_xlsx,
    _load_rows_xlsx, _list_xlsx_for_date,
)

# ── 1분봉 경로 규칙 ──────────────────────────────────────────────────
# /home/netforce/US_Data/Zeroday_option_1Min/{expiry}/{expiry}_{symbol}.csv
_MIN_SAVE_BASE_DIR = _OPT_1MIN_DIR


def _make_1min_save_path(expiry: str, symbol_raw: str) -> str:
    """
    옵션 1분봉 저장 경로 (= spxw_core._make_save_path 와 동일):
      /home/netforce/US_Data/Zeroday_option_1Min/{expiry}/{expiry}_{symbol}.csv
    """
    return _make_save_path(expiry, symbol_raw)


def _list_1min_xlsx_for_date(expiry: str) -> List[str]:
    """옵션 1분봉 폴더의 CSV 파일 목록 반환 (파일명만)."""
    return _list_xlsx_for_date(expiry)


def _load_1min_bars_from_file(expiry: str, symbol_raw: str) -> List[Dict[str, Any]]:
    """
    저장된 CSV 파일에서 1분봉 데이터 로드.
    경로: /home/netforce/US_Data/Zeroday_option_1Min/{expiry}/{expiry}_{symbol}.csv
    캐시 파일(_cache.csv)이 있으면 우선 사용.
    """
    path = _make_1min_save_path(expiry, symbol_raw)
    base, ext = os.path.splitext(path)
    cache_path = base + "_cache" + ext
    if os.path.exists(cache_path):
        return _load_rows_xlsx(cache_path)
    if os.path.exists(path):
        return _load_rows_xlsx(path)
    return []


# ════════════════════════════════════════════════════════════════════
#  OneMiniTab — 1분봉 탭 위젯
# ════════════════════════════════════════════════════════════════════
class OneMiniTab(QWidget):

    sig_log         = pyqtSignal(str)
    sig_second_log  = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        _file_key = _load_api_key_from_file("CD-KEY.txt")
        self.api_key = _file_key if _file_key else ""

        # Queue 기반 스레드 통신 (list 시그널 크래시 방지)
        self._result_queue: _queue_module.Queue = _queue_module.Queue()

        self._all_rows_cache:  List[Dict[str, Any]] = []
        self._current_date_str = ""
        self._auto_task_queue:  list = []
        self._auto_task_total:  int  = 0
        self._auto_task_done:   int  = 0
        self._auto_expiry       = ""
        self._auto_date_str     = ""
        self._auto_active       = False
        self._pending_save      = False
        self._pending_expiry_override = ""

        self._build_ui()

        self.api_key_edit.setText(self.api_key)
        self.api_key_edit.textChanged.connect(lambda t: setattr(self, 'api_key', t.strip()))

        self.sig_log.connect(lambda m: self.log_text.appendPlainText(m))

        # QTimer 폴링 (50ms)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_queues)
        self._poll_timer.start()

    # ────────────────────────────────────────────────────────────────
    #  UI 구성
    # ────────────────────────────────────────────────────────────────
    def _pl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:11px;")
        return lbl

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── API Key 바 ──
        api_bar = QHBoxLayout()
        api_bar.addWidget(QLabel("🔑 API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("CD-KEY.txt 자동 로드")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        show_btn = QPushButton("보기"); show_btn.setFixedWidth(48); show_btn.setCheckable(True)
        show_btn.toggled.connect(lambda on: self.api_key_edit.setEchoMode(
            QLineEdit.Normal if on else QLineEdit.Password))
        api_bar.addWidget(self.api_key_edit, 1)
        api_bar.addWidget(show_btn)
        root.addLayout(api_bar)

        # ── 3분할 스플리터 ──
        top_split = QSplitter(Qt.Horizontal)

        # ① 컨트롤 패널
        ctrl_box = QGroupBox("1분봉 수집")
        gr = QGridLayout(ctrl_box)
        gr.setSpacing(5)
        rr = 0

        gr.addWidget(self._pl("심볼 (Ticker)"), rr, 0)
        self.symbol_edit = QLineEdit()
        self.symbol_edit.setPlaceholderText("자동 생성 또는 직접 입력")
        gr.addWidget(self.symbol_edit, rr, 1, 1, 3); rr += 1

        gr.addWidget(self._pl("만기일"), rr, 0)
        self.expiry_edit = QDateEdit()
        self.expiry_edit.setCalendarPopup(True)
        self.expiry_edit.setDisplayFormat("yyyy-MM-dd")
        self.expiry_edit.setDate(QDate.currentDate())
        gr.addWidget(self.expiry_edit, rr, 1)
        gr.addWidget(self._pl("행사가"), rr, 2)
        self.strike_edit = QLineEdit()
        self.strike_edit.setPlaceholderText("예: 6800")
        gr.addWidget(self.strike_edit, rr, 3); rr += 1

        gr.addWidget(self._pl("콜/풋"), rr, 0)
        self.side_combo = QComboBox()
        self.side_combo.addItems(["CALL", "PUT"])
        gr.addWidget(self.side_combo, rr, 1)
        gr.addWidget(self._pl("조회 날짜"), rr, 2)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        gr.addWidget(self.date_edit, rr, 3); rr += 1

        gr.addWidget(self._pl("차트 모드"), rr, 0)
        self.chart_mode = QComboBox()
        self.chart_mode.addItems(["캔들", "라인"])
        gr.addWidget(self.chart_mode, rr, 1)
        gr.addWidget(self._pl("수집 한도"), rr, 2)
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(50, 5000)
        self.limit_spin.setValue(500)
        self.limit_spin.setSingleStep(50)
        gr.addWidget(self.limit_spin, rr, 3); rr += 1

        # 캐시 봉 수
        gr.addWidget(self._pl("캐시 봉 수"), rr, 0)
        self.cache_row_count = QSpinBox()
        self.cache_row_count.setRange(50, 5000)
        self.cache_row_count.setValue(500)
        self.cache_row_count.setSingleStep(50)
        gr.addWidget(self.cache_row_count, rr, 1)

        # 해당폴더 캐시 만들기 버튼
        self.make_cache_btn = QPushButton("📦 해당폴더 캐시 만들기")
        self.make_cache_btn.clicked.connect(self._on_make_cache)
        gr.addWidget(self.make_cache_btn, rr, 2, 1, 2); rr += 1

        # 메인 수집+저장 버튼
        self.gen_btn = QPushButton("▶ 심볼 자동생성 + 수집 + 저장")
        self.gen_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;font-weight:bold;"
            "padding:5px;border-radius:4px;}"
            "QPushButton:hover{background:#1976d2;}")
        self.gen_btn.clicked.connect(self._on_gen_fetch_save)
        gr.addWidget(self.gen_btn, rr, 0, 1, 4); rr += 1

        btn_row = QHBoxLayout()
        self.fetch_btn = QPushButton("🔄 수집만 실행")
        self.fetch_btn.clicked.connect(self.on_fetch_clicked)
        btn_row.addWidget(self.fetch_btn)
        self.clear_btn = QPushButton("🗑 초기화")
        self.clear_btn.clicked.connect(self._clear_panel)
        btn_row.addWidget(self.clear_btn)
        gr.addLayout(btn_row, rr, 0, 1, 4); rr += 1

        self.session_lbl = QLabel("📌 날짜를 선택하면 세션 정보가 표시됩니다.")
        self.session_lbl.setStyleSheet("font-size:10px; color:#666;")
        self.session_lbl.setWordWrap(True)
        gr.addWidget(self.session_lbl, rr, 0, 1, 4); rr += 1

        self.status_lbl = QLabel("수집 대기 중")
        self.status_lbl.setStyleSheet("font-size:10px; color:#1565c0; font-weight:bold;")
        self.status_lbl.setWordWrap(True)
        gr.addWidget(self.status_lbl, rr, 0, 1, 4); rr += 1

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("수집 로그")
        gr.addWidget(self.log_text, rr, 0, 1, 4)

        # ② 데이터 테이블
        table_box = QGroupBox("1분봉 데이터 테이블")
        self._table_box = table_box
        tv = QVBoxLayout(table_box)
        self.data_table = QTableWidget()
        self.data_table.setColumnCount(6)
        self.data_table.setHorizontalHeaderLabels(
            ["Time (KST)", "Open", "High", "Low", "Close", "Volume"])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tv.addWidget(self.data_table)

        # ③ 캘린더 + 파일 리스트
        cal_box = QGroupBox("날짜 선택 & 저장 파일 목록")
        cal_v = QVBoxLayout(cal_box)

        self.file_calendar = QCalendarWidget()
        self.file_calendar.setGridVisible(True)
        self.file_calendar.setMaximumHeight(200)
        self.file_calendar.clicked.connect(self._on_calendar_clicked)
        cal_v.addWidget(self.file_calendar)

        cal_v.addWidget(self._pl("📁 저장된 1분봉 파일 (클릭→차트 / Ctrl+클릭→다중선택)"))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.itemClicked.connect(self._on_file_clicked)
        self.file_list.itemDoubleClicked.connect(self._on_file_clicked)
        cal_v.addWidget(self.file_list, 1)

        file_btn_row = QHBoxLayout()
        self.del_btn = QPushButton("🗑 선택 파일 삭제")
        self.del_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border-radius:3px;padding:3px 6px;}"
            "QPushButton:hover{background:#d32f2f;}")
        self.del_btn.clicked.connect(self._on_delete_file)
        file_btn_row.addWidget(self.del_btn)
        self.refresh_btn = QPushButton("🔄 목록 새로고침")
        self.refresh_btn.clicked.connect(self._on_refresh_files)
        file_btn_row.addWidget(self.refresh_btn)
        cal_v.addLayout(file_btn_row)

        self.file_status = QLabel("날짜를 클릭하면 파일 목록이 표시됩니다.")
        self.file_status.setStyleSheet("font-size:10px; color:#555;")
        self.file_status.setWordWrap(True)
        cal_v.addWidget(self.file_status)

        top_split.addWidget(ctrl_box)
        top_split.addWidget(table_box)
        top_split.addWidget(cal_box)
        top_split.setStretchFactor(0, 2)
        top_split.setStretchFactor(1, 2)
        top_split.setStretchFactor(2, 3)
        root.addWidget(top_split, 4)

        # ── 하단 차트 ──
        self.chart = MiniChartCanvas(parent=self)
        self.chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.chart, 6)

    # ────────────────────────────────────────────────────────────────
    #  Queue 폴링
    # ────────────────────────────────────────────────────────────────
    def _poll_queues(self):
        try:
            while True:
                symbol, rows = self._result_queue.get_nowait()
                self._on_done(symbol, rows)
        except _queue_module.Empty:
            pass

    # ────────────────────────────────────────────────────────────────
    #  수집 실행
    # ────────────────────────────────────────────────────────────────
    def on_fetch_clicked(self):
        """심볼+만기일로 저장된 CSV 파일을 직접 로드해 화면에 표시."""
        symbol   = self.symbol_edit.text().strip()
        expiry   = self.expiry_edit.date().toString("yyyy-MM-dd")
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        if not symbol:
            QMessageBox.warning(self, "오류", "심볼을 입력하거나 자동 생성하세요.")
            return

        self._current_date_str = date_str
        summer = _is_summer_time(date_str)
        s_tag  = "섬머" if summer else "비섬머"
        self.session_lbl.setText(f"📌 {date_str} [{s_tag}]")
        self.status_lbl.setText(f"🔄 파일 로드 중... {symbol}")
        self.fetch_btn.setEnabled(False)
        self.gen_btn.setEnabled(False)

        rq = self._result_queue

        def _worker():
            try:
                rows = _load_1min_bars_from_file(expiry, symbol)
            except Exception as e:
                rows = []
                print(f"[1min load] {e}")
            rq.put((symbol, rows))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_gen_fetch_save(self):
        """콤보박스에 지정된 콜/풋으로 심볼 자동생성 → 저장된 파일 로드."""
        expiry   = self.expiry_edit.date().toString("yyyy-MM-dd")
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        try:
            strike = float(self.strike_edit.text())
        except Exception:
            QMessageBox.warning(self, "오류", "행사가를 숫자로 입력하세요.")
            return

        side = self.side_combo.currentText()
        sym  = build_spx_zero_day_symbol(strike, side, expiry)
        if not sym:
            QMessageBox.warning(self, "오류", "심볼 생성 실패.")
            return

        self.symbol_edit.setText(sym)
        self._auto_expiry             = expiry
        self._auto_date_str           = date_str
        self._pending_expiry_override = expiry

        self.gen_btn.setEnabled(False)
        self.fetch_btn.setEnabled(False)
        self.log_text.appendPlainText(f"📂 파일 조회: {sym}  [{side}]  날짜:{date_str}")

        self._start_fetch_thread(sym, expiry, date_str)

    def _start_fetch_thread(self, symbol: str, expiry: str, date_str: str):
        """저장된 CSV 파일을 비동기 로드해 Queue에 결과 전달."""
        rq = self._result_queue

        def _worker():
            try:
                rows = _load_1min_bars_from_file(expiry, symbol)
            except Exception as e:
                rows = []
                print(f"[1min load] {e}")
            rq.put((symbol, rows))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_done(self, symbol: str, rows: List[Dict[str, Any]]):
        """Queue 폴링에서 호출 — 메인 스레드에서만 실행."""
        self.fetch_btn.setEnabled(True)
        self.gen_btn.setEnabled(True)

        if not rows:
            self.status_lbl.setText("❌ 데이터 없음")
            self.log_text.appendPlainText(f"✗ {symbol}: 결과 없음")
            self._pending_save = False
            self._auto_active  = False
            return

        self._all_rows_cache = rows
        total_n = len(rows)
        t0 = rows[0]["time"]
        t1 = rows[-1]["time"]
        self.status_lbl.setText(f"✅ {symbol}  {total_n}봉  ({t0}~{t1})")
        self.log_text.appendPlainText(f"✓ {symbol}: {total_n}봉 ({t0}~{t1})")

        self._render_rows(rows)

        if self._pending_save:
            self._pending_save = False
            self._save_data(symbol, rows)

    # ────────────────────────────────────────────────────────────────
    #  렌더링
    # ────────────────────────────────────────────────────────────────
    def _render_rows(self, rows: List[Dict[str, Any]]):
        n = len(rows)
        self._table_box.setTitle(f"1분봉 데이터  ({n}봉)")
        self.data_table.setRowCount(n)
        for i, r in enumerate(rows):
            self.data_table.setItem(i, 0, QTableWidgetItem(r["time"]))
            self.data_table.setItem(i, 1, QTableWidgetItem(f"{r['open']:.4f}"))
            self.data_table.setItem(i, 2, QTableWidgetItem(f"{r['high']:.4f}"))
            self.data_table.setItem(i, 3, QTableWidgetItem(f"{r['low']:.4f}"))
            self.data_table.setItem(i, 4, QTableWidgetItem(f"{r['close']:.4f}"))
            self.data_table.setItem(i, 5, QTableWidgetItem(f"{r.get('volume',0):.0f}"))
        self.data_table.scrollToBottom()

        times  = [r["time"]  for r in rows]
        opens  = [r["open"]  for r in rows]
        highs  = [r["high"]  for r in rows]
        lows   = [r["low"]   for r in rows]
        closes = [r["close"] for r in rows]
        vols   = [r.get("volume", 0) for r in rows]

        try:
            if self.chart_mode.currentText() == "캔들":
                self.chart.plot_candles(times, opens, highs, lows, closes, volumes=vols)
            else:
                self.chart.plot_line(times, closes, volumes=vols)
        except Exception as e:
            self.log_text.appendPlainText(f"⚠ 차트 오류: {e}")

    # ────────────────────────────────────────────────────────────────
    #  저장 / 캐시
    # ────────────────────────────────────────────────────────────────
    def _save_data(self, symbol: str, rows: List[Dict[str, Any]]):
        """봉 데이터를 CSV로 저장 + 자동 캐시 생성."""
        if not rows:
            return
        expiry = self._pending_expiry_override or \
                 self.expiry_edit.date().toString("yyyy-MM-dd")
        try:
            path = _make_1min_save_path(expiry, symbol)   # → .csv
            _save_rows_xlsx(path, rows)                    # 내부적으로 csv 저장
            fname = os.path.basename(path)
            self.log_text.appendPlainText(f"💾 저장: {fname}")

            # 자동 캐시 생성
            cache_n = self.cache_row_count.value()
            cache_rows = rows[-cache_n:] if len(rows) > cache_n else rows
            base, ext = os.path.splitext(path)
            cache_path = base + "_cache" + ext             # _cache.csv
            _save_rows_xlsx(cache_path, cache_rows)
            self.log_text.appendPlainText(
                f"📦 캐시: {os.path.basename(cache_path)} ({len(cache_rows)}봉)")

            cal_date = self.file_calendar.selectedDate().toString("yyyy-MM-dd")
            if cal_date == expiry:
                self._refresh_file_list(expiry)
        except Exception as e:
            self.log_text.appendPlainText(f"❌ 저장 실패: {e}")

    def _on_make_cache(self):
        """캘린더 날짜 폴더 전체 원본 파일 → 캐시 일괄 생성."""
        expiry = getattr(self, "_current_cal_date", "")
        if not expiry:
            self.file_status.setText("⚠ 캘린더에서 날짜를 먼저 선택하세요.")
            return
        cache_n = self.cache_row_count.value()
        folder  = os.path.join(_MIN_SAVE_BASE_DIR, expiry)
        if not os.path.isdir(folder):
            self.file_status.setText(f"❌ 폴더 없음: {folder}")
            return
        files = sorted([f for f in os.listdir(folder)
                        if f.endswith(".xlsx") and "_cache" not in f])
        if not files:
            self.file_status.setText("⚠ 원본 파일 없음")
            return

        self.make_cache_btn.setEnabled(False)
        ok = skip = fail = 0
        for fname in files:
            path = os.path.join(folder, fname)
            try:
                rows = _load_rows_xlsx(path)
                if not rows:
                    skip += 1; continue
                cache_rows = rows[-cache_n:] if len(rows) > cache_n else rows
                base, ext = os.path.splitext(path)
                _save_rows_xlsx(base + "_cache" + ext, cache_rows)
                ok += 1
            except Exception as e:
                self.log_text.appendPlainText(f"❌ {fname}: {e}")
                fail += 1
        self.make_cache_btn.setEnabled(True)
        self.file_status.setText(f"✅ 캐시: 성공{ok} 스킵{skip} 실패{fail} (봉수:{cache_n})")
        self._refresh_file_list(expiry)

    # ────────────────────────────────────────────────────────────────
    #  파일 리스트
    # ────────────────────────────────────────────────────────────────
    def _on_calendar_clicked(self, qdate: QDate):
        expiry = qdate.toString("yyyy-MM-dd")
        self._refresh_file_list(expiry)

    def _refresh_file_list(self, expiry: str):
        self._current_cal_date = expiry
        self.file_list.clear()
        date8 = expiry.replace("-", "")          # 2026-04-27 → 20260427
        files = _list_1min_xlsx_for_date(expiry)
        if files:
            for f in files:
                label = f"📦 {f}" if "_cache" in f else f"📄 {f}"
                item  = QListWidgetItem(label)
                item.setData(Qt.UserRole, os.path.join(_MIN_SAVE_BASE_DIR, date8, f))
                self.file_list.addItem(item)
            nc = sum(1 for f in files if "_cache" in f)
            self.file_status.setText(
                f"📅 {expiry}  원본:{len(files)-nc}  캐시:{nc}  총:{len(files)}")
        else:
            self.file_status.setText(f"📅 {expiry}  저장된 파일 없음")

    def _on_file_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            self.file_status.setText(f"❌ 파일 없음")
            return
        try:
            # _cache 파일 우선 로드
            if "_cache" not in os.path.basename(path):
                base, ext = os.path.splitext(path)
                cp = base + "_cache" + ext
                if os.path.exists(cp):
                    path = cp
                    self.log_text.appendPlainText(f"📦 캐시 우선 로드: {os.path.basename(cp)}")
            rows = _load_rows_xlsx(path)
            if not rows:
                self.file_status.setText("❌ 데이터 없음")
                return
            self._all_rows_cache = rows
            self._render_rows(rows)
            self.status_lbl.setText(
                f"📂 {os.path.basename(path)}  {len(rows)}봉")
            self.file_status.setText(f"✅ {os.path.basename(path)} → 차트 출력")
        except Exception as e:
            self.file_status.setText(f"❌ 로드 오류: {e}")

    def _on_delete_file(self):
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("⚠ 파일을 선택하세요.")
            return
        path  = item.data(Qt.UserRole)
        fname = os.path.basename(path)
        if QMessageBox.question(self, "삭제", f"삭제하시겠습니까?\n{fname}",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            os.remove(path)
            self.file_status.setText(f"🗑 삭제: {fname}")
            expiry = getattr(self, "_current_cal_date", "")
            if expiry:
                self._refresh_file_list(expiry)
        except Exception as e:
            self.file_status.setText(f"❌ 삭제 실패: {e}")

    def _on_refresh_files(self):
        expiry = getattr(self, "_current_cal_date", "")
        if expiry:
            self._refresh_file_list(expiry)
        else:
            self.file_status.setText("⚠ 날짜를 먼저 선택하세요.")

    def _clear_panel(self):
        self._all_rows_cache = []
        self._pending_save   = False
        self.data_table.setRowCount(0)
        self.status_lbl.setText("초기화 완료")
        self.log_text.clear()
        try:
            self.chart.plot_line([], [])
        except Exception:
            pass