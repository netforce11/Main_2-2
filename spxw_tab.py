# -*- coding: utf-8 -*-
"""
spxw_tab.py — ZeroDayTab 위젯 (1초봉 수집/조회/저장 UI)
"""
from __future__ import annotations

import os
import sys
import threading
import queue as _queue_module

from datetime import date as dt_date, datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional, Set, Union
from concurrent.futures import ThreadPoolExecutor

try:
    import numpy as np
except ImportError:
    np = None

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QHBoxLayout,
    QTabWidget, QTableWidget, QHeaderView, QTableWidgetItem,
    QSplitter, QGroupBox, QMessageBox, QDateEdit, QShortcut,
    QSizePolicy, QPlainTextEdit, QListWidget, QListWidgetItem,
    QSpinBox, QProgressBar, QCalendarWidget
)
from PyQt5.QtCore import Qt, QDate, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QKeySequence

from spxw_core import (
    # zday_core
    build_spx_zero_day_symbol, opt_ticker,
    normalize_rows, filter_night_session, limit_rows,
    cache_file_path, save_rows_csv, load_rows_csv,
    fetch_minutes_polygon, merge_call_put,
    scan_windows, is_us_trading_day, _index_existing_for_expiry,
    # chart
    MiniChartCanvas,
    # provider
    PolygonDataProvider, RateLimiter, _load_api_key_from_file,
    # 섬머타임 / 1초봉
    _is_summer_time, _session_bounds,
    _hhmmss_to_seconds, _hhmm_to_seconds,
    _filter_display_window, _fetch_second_bars_polygon,
    # xlsx 유틸
    _SAVE_BASE_DIR, _make_save_path, _save_rows_xlsx,
    _load_rows_xlsx, _list_xlsx_for_date,
)

#  PART 5: ZeroDayTab 메인 위젯
# ═══════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────
#  1초봉 수집: threading.Thread + queue.Queue + QTimer 폴링
#  (QThread/pyqtSignal(list) 크래시 완전 제거)
# ─────────────────────────────────────────────────────────

class ZeroDayTab(QWidget):
    # ★ list 타입 시그널 없음 — 모두 Queue 폴링 방식 사용 (크래시 방지)
    sig_log           = pyqtSignal(str)
    sig_auto_progress = pyqtSignal(str, int, int)
    sig_auto_finished = pyqtSignal()
    sig_second_log    = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from concurrent.futures import ThreadPoolExecutor
        self._pool = ThreadPoolExecutor(max_workers=2)
        self.provider_map = {"Polygon.io": PolygonDataProvider()}

        _file_key = _load_api_key_from_file("CD-KEY.txt")
        self.api_key = _file_key if _file_key else ""

        self.rows_by_strike_side: Dict[float, Dict[str, List[Dict[str, Any]]]] = {}
        self.widgets_by_strike:   Dict[float, Tuple[QTableWidget, MiniChartCanvas]] = {}
        self._auto_running = False

        # ── Queue 기반 스레드 통신 (list 시그널 크래시 완전 제거) ──
        self._second_result_queue: _queue_module.Queue = _queue_module.Queue()
        self._fetch_result_queue:  _queue_module.Queue = _queue_module.Queue()
        self._scan_result_queue:   _queue_module.Queue = _queue_module.Queue()

        self._build_ui()
        self._wire_shortcuts()
        self._apply_styles()

        self.api_key_edit.setText(self.api_key)
        self.api_key_edit.textChanged.connect(self._on_api_key_changed)

        # sig_fetch_done / sig_scan_done 은 Queue 폴링 방식으로 직접 호출됨
        # (list 타입 시그널 크래시 방지)
        self.sig_log.connect(lambda msg: self.log_box.appendPlainText(msg))
        self.sig_auto_progress.connect(self._on_auto_progress)
        self.sig_auto_finished.connect(self._on_auto_finished)
        self.sig_second_log.connect(lambda msg: self.second_log.appendPlainText(msg))

        # ── QTimer: 50ms마다 Queue 폴링 ──
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_result_queues)
        self._poll_timer.start()

    # ── UI ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ══════════════════════════════════════════
        # 행 1: API Key 바 (최상단)
        # ══════════════════════════════════════════
        api_bar = QHBoxLayout()
        api_bar.addWidget(QLabel("🔑 API Key (CD-KEY.txt 자동 로드):"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Polygon API 키 — CD-KEY.txt 파일이 있으면 자동 로드")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_show_btn = QPushButton("보기")
        self.api_key_show_btn.setFixedWidth(48)
        self.api_key_show_btn.setCheckable(True)
        self.api_key_show_btn.toggled.connect(
            lambda on: self.api_key_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        api_bar.addWidget(self.api_key_edit, 1)
        api_bar.addWidget(self.api_key_show_btn)
        root.addLayout(api_bar)

        # ══════════════════════════════════════════
        # 행 2: 상단 패널 3분할
        #   [컨트롤 -30% = 2] | [테이블 -50% = 2] | [캘린더+파일리스트 = 3]
        # ══════════════════════════════════════════
        top_splitter = QSplitter(Qt.Horizontal)

        # ─ ①: 1초봉 수집 컨트롤 패널 ─
        ctrl_box = QGroupBox("1초봉 실시간 수집")
        gr = QGridLayout(ctrl_box)
        gr.setSpacing(5)
        rr = 0

        gr.addWidget(self._pl("심볼 (Ticker)"), rr, 0)
        self.second_symbol_edit = QLineEdit()
        self.second_symbol_edit.setPlaceholderText("자동 생성 또는 직접 입력")
        gr.addWidget(self.second_symbol_edit, rr, 1, 1, 3); rr += 1

        gr.addWidget(self._pl("만기일"), rr, 0)
        self.second_expiry = QDateEdit()
        self.second_expiry.setCalendarPopup(True)
        self.second_expiry.setDisplayFormat("yyyy-MM-dd")
        self.second_expiry.setDate(QDate.currentDate())
        gr.addWidget(self.second_expiry, rr, 1)
        gr.addWidget(self._pl("행사가"), rr, 2)
        self.second_strike_edit = QLineEdit()
        self.second_strike_edit.setPlaceholderText("예: 6800")
        gr.addWidget(self.second_strike_edit, rr, 3); rr += 1

        gr.addWidget(self._pl("콜/풋"), rr, 0)
        self.second_side_combo = QComboBox()
        self.second_side_combo.addItems(["CALL", "PUT"])
        gr.addWidget(self.second_side_combo, rr, 1)
        gr.addWidget(self._pl("조회 날짜"), rr, 2)
        self.second_date_edit = QDateEdit()
        self.second_date_edit.setCalendarPopup(True)
        self.second_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.second_date_edit.setDate(QDate.currentDate())
        gr.addWidget(self.second_date_edit, rr, 3); rr += 1

        gr.addWidget(self._pl("차트 모드"), rr, 0)
        self.second_chart_mode = QComboBox()
        self.second_chart_mode.addItems(["캔들", "라인"])
        gr.addWidget(self.second_chart_mode, rr, 1); rr += 1

        # 표시 구간 콤보: 04:30~06:00 (섬머/비섬머 모두 커버)
        _start_times = (
            [f"04:{m:02d}" for m in range(30, 60)] +   # 04:30~04:59
            [f"05:{m:02d}" for m in range(0,  60)] +   # 05:00~05:59
            ["06:00"]                                   # 06:00
        )
        _end_times = (
            [f"04:{m:02d}" for m in range(30, 60)] +
            [f"05:{m:02d}" for m in range(0,  60)] +
            ["06:00"]
        )
        gr.addWidget(self._pl("표시 시작"), rr, 0)
        self.disp_start_combo = QComboBox()
        self.disp_start_combo.addItems(_start_times)
        self.disp_start_combo.setCurrentText("05:57")
        gr.addWidget(self.disp_start_combo, rr, 1)
        gr.addWidget(self._pl("표시 종료"), rr, 2)
        self.disp_end_combo = QComboBox()
        self.disp_end_combo.addItems(_end_times)
        self.disp_end_combo.setCurrentText("05:59")
        gr.addWidget(self.disp_end_combo, rr, 3); rr += 1

        self.disp_start_combo.currentIndexChanged.connect(self._on_display_range_changed)
        self.disp_end_combo.currentIndexChanged.connect(self._on_display_range_changed)

        # 조회 날짜 변경 시 세션 구간 안내 레이블 자동 갱신
        self.second_date_edit.dateChanged.connect(self._on_query_date_changed)

        # 수집 갯수 (1~10, 기본 1) : 콜N개+풋N개 = 총2N개
        gr.addWidget(self._pl("수집 갯수 (콜+풋)"), rr, 0)
        self.auto_fetch_count = QSpinBox()
        self.auto_fetch_count.setRange(1, 10)
        self.auto_fetch_count.setValue(1)
        self.auto_fetch_count.setToolTip(
            "1 = 콜1+풋1 (기준가만)\n2 = 콜2+풋2 (+5 포함)\n최대 10 = 콜10+풋10")
        gr.addWidget(self.auto_fetch_count, rr, 1)

        # 캐시 로딩 개수 (기본 500)
        gr.addWidget(self._pl("캐시 봉 수"), rr, 2)
        self.cache_row_count = QSpinBox()
        self.cache_row_count.setRange(100, 50000)
        self.cache_row_count.setValue(500)
        self.cache_row_count.setSingleStep(100)
        self.cache_row_count.setToolTip("캐시 생성 시 저장할 마지막 봉 개수 (기본 500)")
        gr.addWidget(self.cache_row_count, rr, 3); rr += 1

        # 캐시 만들기 버튼 (해당 폴더 전체 → _cache.xlsx)
        self.make_cache_btn = QPushButton("📦 해당폴더 캐시 만들기")
        self.make_cache_btn.setToolTip("캘린더 날짜 폴더의 모든 원본 파일에 캐시 일괄 생성")
        self.make_cache_btn.clicked.connect(self._on_make_cache)
        gr.addWidget(self.make_cache_btn, rr, 0, 1, 4); rr += 1

        # ★ 자동생성 버튼: 생성 + 수집 + 저장 한 번에
        self.second_gen_btn = QPushButton("▶ 심볼 자동생성 + 수집 + 저장")
        self.second_gen_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;font-weight:bold;padding:5px;border-radius:4px;}"
            "QPushButton:hover{background:#1976d2;}"
        )
        self.second_gen_btn.clicked.connect(self._on_gen_fetch_save)
        gr.addWidget(self.second_gen_btn, rr, 0, 1, 4); rr += 1

        second_btn_row = QHBoxLayout()
        self.second_fetch_btn = QPushButton("🔄 수집만 실행")
        self.second_fetch_btn.clicked.connect(self.on_second_fetch_clicked)
        second_btn_row.addWidget(self.second_fetch_btn)
        self.second_clear_btn = QPushButton("🗑 초기화")
        self.second_clear_btn.clicked.connect(self._clear_second_panel)
        second_btn_row.addWidget(self.second_clear_btn)
        gr.addLayout(second_btn_row, rr, 0, 1, 4); rr += 1

        self.session_info_lbl = QLabel("📌 세션: 섬머 22:30~05:00 / 비섬머 23:30~06:00")
        self.session_info_lbl.setStyleSheet("font-size:10px; color:#666;")
        self.session_info_lbl.setWordWrap(True)
        gr.addWidget(self.session_info_lbl, rr, 0, 1, 4); rr += 1

        self.second_status = QLabel("수집 대기 중")
        self.second_status.setStyleSheet("font-size:10px; color:#1565c0; font-weight:bold;")
        self.second_status.setWordWrap(True)
        gr.addWidget(self.second_status, rr, 0, 1, 4); rr += 1

        self.second_log = QPlainTextEdit()
        self.second_log.setReadOnly(True)
        self.second_log.setPlaceholderText("수집 로그")
        gr.addWidget(self.second_log, rr, 0, 1, 4)

        # ─ ②: 1초봉 데이터 테이블 ─
        table_box = QGroupBox("1초봉 데이터 테이블")
        self._table_box = table_box
        tv = QVBoxLayout(table_box)
        self.second_table = QTableWidget()
        self.second_table.setColumnCount(6)
        self.second_table.setHorizontalHeaderLabels(
            ["Time (KST)", "Open", "High", "Low", "Close", "Volume"])
        self.second_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.second_table.verticalHeader().setVisible(False)
        self.second_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.second_table.setAlternatingRowColors(True)
        self.second_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tv.addWidget(self.second_table)

        # ─ ③: 캘린더 + 파일 리스트박스 ─
        cal_box = QGroupBox("날짜 선택 & 저장 파일 목록")
        cal_v = QVBoxLayout(cal_box)

        self.file_calendar = QCalendarWidget()
        self.file_calendar.setGridVisible(True)
        self.file_calendar.setMaximumHeight(200)
        self.file_calendar.clicked.connect(self._on_calendar_date_clicked)
        cal_v.addWidget(self.file_calendar)

        cal_v.addWidget(self._pl("📁  저장된 옵션 파일  (클릭→차트 / Ctrl+클릭→다중선택)"))
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)  # Ctrl+클릭 다중선택
        self.file_list.itemDoubleClicked.connect(self._on_file_list_double_clicked)
        self.file_list.itemClicked.connect(self._on_file_list_clicked)
        cal_v.addWidget(self.file_list, 1)

        # 파일 조작 버튼 행
        file_btn_row = QHBoxLayout()
        self.file_delete_btn = QPushButton("🗑 선택 파일 삭제")
        self.file_delete_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border-radius:3px;padding:3px 6px;}"
            "QPushButton:hover{background:#d32f2f;}"
        )
        self.file_delete_btn.clicked.connect(self._on_delete_selected_file)
        file_btn_row.addWidget(self.file_delete_btn)
        self.file_refresh_btn = QPushButton("🔄 목록 새로고침")
        self.file_refresh_btn.clicked.connect(self._on_refresh_file_list_btn)
        file_btn_row.addWidget(self.file_refresh_btn)
        cal_v.addLayout(file_btn_row)

        self.file_status = QLabel("날짜를 클릭하면 파일 목록이 표시됩니다.")
        self.file_status.setStyleSheet("font-size:10px; color:#555;")
        self.file_status.setWordWrap(True)
        cal_v.addWidget(self.file_status)

        top_splitter.addWidget(ctrl_box)
        top_splitter.addWidget(table_box)
        top_splitter.addWidget(cal_box)
        top_splitter.setStretchFactor(0, 2)   # 컨트롤 ~29%
        top_splitter.setStretchFactor(1, 2)   # 테이블 ~29%
        top_splitter.setStretchFactor(2, 3)   # 캘린더+파일 ~43%

        root.addWidget(top_splitter, 4)

        # ══════════════════════════════════════════
        # 행 3: 1초봉 차트 (하단 풀 너비)
        # ══════════════════════════════════════════
        self.second_chart = MiniChartCanvas(parent=self)
        self.second_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(self.second_chart, 6)

        # ── 1분봉 탭 / 검색용 더미 위젯 (기능은 유지, 숨김) ──
        # source_combo, start_edit 등은 on_load_clicked 등에서 참조하므로 생성은 하되 숨김
        self.source_combo = QComboBox()
        self.source_combo.addItems(self.provider_map.keys())
        self.source_combo.hide()

        self.start_edit = QDateEdit()
        self.start_edit.setDate(QDate.currentDate())
        self.start_edit.hide()

        self.end_edit = QDateEdit()
        self.end_edit.setDate(QDate.currentDate())
        self.end_edit.hide()

        self.expiry_edit = QDateEdit()
        self.expiry_edit.setDate(QDate.currentDate())
        self.expiry_edit.hide()

        self.center_edit = QLineEdit()
        self.center_edit.hide()

        self.range_combo = QComboBox()
        self.range_combo.addItems([str(x) for x in [2, 3, 4, 5, 8, 10, 15, 20, 30, 50]])
        self.range_combo.hide()

        self.show_range = QSpinBox()
        self.show_range.setRange(1, 50)
        self.show_range.setValue(6)
        self.show_range.hide()

        self.side_filter = QComboBox()
        self.side_filter.addItems(["양쪽 모두", "콜만", "풋만"])
        self.side_filter.setCurrentIndex(1)
        self.side_filter.currentIndexChanged.connect(self.on_side_mode_changed)
        self.side_filter.hide()

        self.chart_mode = QComboBox()
        self.chart_mode.addItems(["라인", "캔들"])
        self.chart_mode.hide()

        self.chart_count = QSpinBox()
        self.chart_count.setRange(10, 399)
        self.chart_count.setValue(399)
        self.chart_count.valueChanged.connect(self._on_chart_count_changed)
        self.chart_count.hide()

        self.auto_prog = QProgressBar()
        self.auto_prog.hide()
        self.auto_status = QLabel()
        self.auto_status.hide()

        self.log_box = QPlainTextEdit()
        self.log_box.hide()

        self.scan_interval = QComboBox()
        self.scan_interval.addItems(["1", "5", "10", "30"])
        self.scan_interval.hide()

        self.threshold_edit = QLineEdit("200,300,500")
        self.threshold_edit.hide()

        self.result_list = QListWidget()
        self.result_list.itemClicked.connect(self.on_result_clicked)
        self.result_list.hide()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_close_tab)
        self.tabs.hide()

    def _apply_styles(self):
        self.setStyleSheet("""
        QWidget { background:#fff; color:#000; font-size:12px; }
        QGroupBox { border:1px solid #d0d0d0; border-radius:4px;
                    margin-top:8px; padding-top:8px; background:#fff; }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
        QTabWidget::pane { border:0; }
        QTabBar::tab { padding:6px 10px; background:#f5f5f5;
                       border:1px solid #d0d0d0; border-bottom:none; }
        QTabBar::tab:selected { background:#fff; }
        QTableWidget { border:1px solid #d0d0d0; gridline-color:#e0e0e0; }
        QHeaderView::section { background:#f5f5f5; padding:4px;
            border-right:1px solid #d0d0d0; border-bottom:1px solid #d0d0d0; }
        QPlainTextEdit, QLineEdit, QComboBox, QDateEdit {
            border:1px solid #c0c0c0; border-radius:4px; }
        QPushButton { background:#f0f0f0; border:1px solid #bbb;
                      border-radius:4px; padding:4px 8px; }
        QPushButton:hover  { background:#e0e8ff; }
        QPushButton:pressed{ background:#c8d8ff; }
        """)

    def _wire_shortcuts(self):
        QShortcut(QKeySequence("Alt+Return"), self, activated=self.on_load_clicked)
        QShortcut(QKeySequence("Alt+Enter"),  self, activated=self.on_load_clicked)

    def _pl(self, text: str) -> QLabel:
        lb = QLabel(text)
        lb.setTextFormat(Qt.PlainText)
        return lb

    def _on_api_key_changed(self, text: str):
        self.api_key = text.strip()

    # ── 초기화 ──
    def _clear_all(self):
        self.tabs.clear()
        self.result_list.clear()
        self.rows_by_strike_side.clear()
        self.widgets_by_strike.clear()
        self.log_box.clear()

    def _clear_second_panel(self):
        self._all_rows_cache = []
        self._pending_save = False
        self.second_table.setRowCount(0)
        self.second_chart.plot_line([], [])
        self.second_log.clear()
        self._table_box.setTitle("1초봉 데이터 테이블")
        start_hhmm, end_hhmm = self._get_display_range()
        self.second_status.setText(
            f"수집 대기 중  — 표시 구간: {start_hhmm} ~ {end_hhmm}:59")

    # ── 심볼 테스트 ──
    def on_test_clicked(self):
        expiry = self.expiry_edit.date().toString("yyyy-MM-dd")
        try:
            center = float(self.center_edit.text())
        except Exception:
            QMessageBox.warning(self, "입력 오류", "중심 행사가를 숫자로 입력하세요.")
            return
        r = int(self.range_combo.currentText())
        want = self._want_sides(self.side_filter.currentText())
        strikes = self._make_strikes(center, r)
        syms = [build_spx_zero_day_symbol(s, side, expiry)
                for s in strikes for side in want]
        self.log_box.clear()
        self.log_box.appendPlainText("🧾 생성 심볼 미리보기:")
        for s in syms:
            self.log_box.appendPlainText(f"  {s}")

    def _want_sides(self, side_mode: str) -> List[str]:
        want: List[str] = []
        if side_mode in ("양쪽 모두", "콜만"): want.append("CALL")
        if side_mode in ("양쪽 모두", "풋만"): want.append("PUT")
        return want

    def _on_query_date_changed(self):
        """조회 날짜 변경 시 섬머타임 세션 안내 레이블 갱신."""
        date_str = self.second_date_edit.date().toString("yyyy-MM-dd")
        summer = _is_summer_time(date_str)
        if summer:
            self.session_info_lbl.setText(
                f"📌 {date_str}  【섬머타임】 세션: KST 22:30 ~ 익일 05:00")
        else:
            self.session_info_lbl.setText(
                f"📌 {date_str}  【표준시간】 세션: KST 23:30 ~ 익일 06:00")

    # ── 심볼만 생성 (내부 유틸) ──
    def _gen_symbol(self) -> str:
        """만기일 + 행사가 + 콜풋으로 심볼 생성. 실패 시 빈 문자열 반환."""
        expiry = self.second_expiry.date().toString("yyyy-MM-dd")
        try:
            strike = float(self.second_strike_edit.text())
        except Exception:
            return ""
        side = self.second_side_combo.currentText()
        return build_spx_zero_day_symbol(strike, side, expiry)

    # ── 자동생성 + 순차 수집 + 저장 (메인 버튼) ──
    def _on_gen_fetch_save(self):
        """
        콤보박스(콜/풋)에 지정된 대로 기준 행사가 1개만 수집.
        수집 갯수 N은 미사용 (단일 심볼).
        파일이 이미 존재하면 API 수집 건너뛰고 기존 파일 로드.
        """
        expiry   = self.second_expiry.date().toString("yyyy-MM-dd")
        date_str = self.second_date_edit.date().toString("yyyy-MM-dd")
        try:
            base_strike = float(self.second_strike_edit.text())
        except Exception:
            QMessageBox.warning(self, "입력 오류", "행사가를 숫자로 입력하세요.")
            return
        if not self.api_key:
            QMessageBox.warning(self, "API Key 오류", "API Key가 비어 있습니다.")
            return

        side = self.second_side_combo.currentText()   # 콤보박스 그대로
        sym  = build_spx_zero_day_symbol(base_strike, side, expiry)
        if not sym:
            QMessageBox.warning(self, "심볼 오류", "심볼 생성 실패. 입력값을 확인하세요.")
            return

        task_list = [(sym, base_strike, side)]
        total = 1
        self.second_log.appendPlainText(
            f"🚀 수집 시작: {sym}  [{side}]  날짜:{date_str}")
        self.second_gen_btn.setEnabled(False)
        self.second_fetch_btn.setEnabled(False)

        self._auto_task_queue   = list(task_list)
        self._auto_task_total   = total
        self._auto_task_done    = 0
        self._auto_expiry       = expiry
        self._auto_date_str     = date_str
        self._auto_active       = True
        self._run_next_auto_task()

    def _run_next_auto_task(self):
        """큐에서 다음 태스크를 꺼내 수집 실행.
        파일이 이미 존재하면 API 호출 없이 기존 파일 로드 후 다음 태스크로."""
        if not getattr(self, "_auto_active", False):
            return
        if not self._auto_task_queue:
            self._on_auto_all_done()
            return

        sym, strike, side = self._auto_task_queue.pop(0)
        self._auto_task_done += 1
        idx  = self._auto_task_done
        total = self._auto_task_total
        expiry   = self._auto_expiry
        date_str = self._auto_date_str

        self.second_symbol_edit.setText(sym)
        self._pending_expiry_override = expiry

        # ── 파일 존재 체크: 있으면 API 건너뜀 ──
        save_path = _make_save_path(expiry, sym)
        if os.path.exists(save_path):
            self.second_log.appendPlainText(
                f"  [{idx}/{total}] ✅ 이미 존재 (스킵): {os.path.basename(save_path)}")
            self.second_status.setText(
                f"⏭ [{idx}/{total}] 스킵 (파일 존재): {sym}")
            # 마지막 항목이면 완료 처리, 아니면 다음 태스크
            if self._auto_task_queue:
                self._run_next_auto_task()
            else:
                self._on_auto_all_done()
            return

        self.second_log.appendPlainText(f"  [{idx}/{total}] 🔄 수집: {sym}")
        self.second_status.setText(f"🔄 자동조회 [{idx}/{total}]: {sym}")

        self._pending_save = True
        self._start_second_worker(sym, date_str)

    def _on_auto_all_done(self):
        """전체 자동조회 완료."""
        self._auto_active = False
        self.second_gen_btn.setEnabled(True)
        self.second_fetch_btn.setEnabled(True)
        total = getattr(self, "_auto_task_total", 0)
        self.second_log.appendPlainText(
            f"✅ 자동조회 완료: {total}개 심볼 수집·저장 완료")
        self.second_status.setText(f"✅ 자동조회 완료 ({total}개)")
        # 캘린더 날짜 파일 목록 갱신
        expiry = getattr(self, "_auto_expiry", "")
        if expiry:
            self._refresh_file_list(expiry)

    # ── 저장 실행 ──
    def _save_current_data(self, symbol: str, rows: List[Dict[str, Any]]):
        """전체 봉을 xlsx로 저장 + 자동 캐시 생성."""
        if not rows:
            self.second_log.appendPlainText("⚠ 저장할 데이터 없음")
            return
        if not _HAS_OPENPYXL:
            self.second_log.appendPlainText("❌ openpyxl 미설치 — pip install openpyxl")
            return
        expiry = getattr(self, "_pending_expiry_override", None) or                  self.second_expiry.date().toString("yyyy-MM-dd")
        try:
            path = _make_save_path(expiry, symbol)
            _save_rows_xlsx(path, rows)
            fname = os.path.basename(path)
            self.second_log.appendPlainText(f"💾 저장: {fname}")

            # ★ 자동 캐시 생성 (수집 직후)
            n_cache = getattr(self, 'cache_row_count', None)
            cache_n = n_cache.value() if n_cache else 500
            cache_rows = rows[-cache_n:] if len(rows) > cache_n else rows
            base, ext = os.path.splitext(path)
            cache_path = base + "_cache" + ext
            _save_rows_xlsx(cache_path, cache_rows)
            self.second_log.appendPlainText(
                f"📦 캐시 자동생성: {os.path.basename(cache_path)} ({len(cache_rows)}봉)")

            self.second_status.setText(
                self.second_status.text() + f"  │  💾{fname}")
            cal_date = self.file_calendar.selectedDate().toString("yyyy-MM-dd")
            if cal_date == expiry:
                self._refresh_file_list(expiry)
        except Exception as e:
            self.second_log.appendPlainText(f"❌ 저장 실패: {e}")

    # ── 파일 삭제 ──
    def _on_delete_selected_file(self):
        item = self.file_list.currentItem()
        if not item:
            self.file_status.setText("⚠ 삭제할 파일을 먼저 선택하세요.")
            return
        path = item.data(Qt.UserRole)
        fname = os.path.basename(path)
        reply = QMessageBox.question(
            self, "파일 삭제 확인",
            f"다음 파일을 삭제하시겠습니까?\n\n{fname}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            os.remove(path)
            self.file_status.setText(f"🗑 삭제 완료: {fname}")
            self.second_log.appendPlainText(f"🗑 삭제: {path}")
            # 목록 갱신
            expiry = getattr(self, "_current_cal_date", "")
            if expiry:
                self._refresh_file_list(expiry)
        except Exception as e:
            self.file_status.setText(f"❌ 삭제 실패: {e}")

    # ── 파일 목록 새로고침 버튼 ──
    def _on_refresh_file_list_btn(self):
        expiry = getattr(self, "_current_cal_date", "")
        if expiry:
            self._refresh_file_list(expiry)
            self.file_status.setText(f"🔄 새로고침: {expiry}")
        else:
            self.file_status.setText("⚠ 날짜를 먼저 선택하세요.")

    # ── 해당폴더 캐시 만들기: 캘린더 날짜 폴더의 모든 원본 파일 일괄 처리 ──
    def _on_make_cache(self):
        expiry = getattr(self, "_current_cal_date", "")
        if not expiry:
            self.file_status.setText("⚠ 캘린더에서 날짜를 먼저 선택하세요.")
            return

        cache_n = self.cache_row_count.value()
        folder  = os.path.join(_SAVE_BASE_DIR, expiry)
        if not os.path.isdir(folder):
            self.file_status.setText(f"❌ 폴더 없음: {folder}")
            return

        files = sorted([f for f in os.listdir(folder)
                        if f.endswith(".xlsx") and "_cache" not in f])
        if not files:
            self.file_status.setText("⚠ 원본 xlsx 파일 없음")
            return

        ok, skip, fail = 0, 0, 0
        self.make_cache_btn.setEnabled(False)
        self.file_status.setText(f"⏳ 캐시 생성 중... ({len(files)}개)")
        QApplication.processEvents()

        for fname in files:
            path = os.path.join(folder, fname)
            try:
                rows = _load_rows_xlsx(path)
                if not rows:
                    skip += 1
                    continue
                cache_rows = rows[-cache_n:] if len(rows) > cache_n else rows
                base, ext = os.path.splitext(path)
                cache_path = base + "_cache" + ext
                _save_rows_xlsx(cache_path, cache_rows)
                self.second_log.appendPlainText(
                    f"📦 {os.path.basename(cache_path)} ({len(cache_rows)}봉)")
                ok += 1
            except Exception as e:
                self.second_log.appendPlainText(f"❌ {fname}: {e}")
                fail += 1

        self.make_cache_btn.setEnabled(True)
        self.file_status.setText(
            f"✅ 캐시 완료: 성공{ok}  스킵{skip}  실패{fail}  (봉수:{cache_n})")
        self._refresh_file_list(expiry)

    # ── 캘린더 날짜 클릭 → 파일 목록 갱신 ──
    def _on_calendar_date_clicked(self, qdate: QDate):
        expiry = qdate.toString("yyyy-MM-dd")
        self._refresh_file_list(expiry)

    def _refresh_file_list(self, expiry: str):
        files = _list_xlsx_for_date(expiry)
        self.file_list.clear()
        self._current_cal_date = expiry
        if files:
            for f in files:
                # _cache 파일은 아이콘으로 구분
                label = f"📦 {f}" if "_cache" in f else f"📄 {f}"
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, os.path.join(_SAVE_BASE_DIR, expiry, f))
                self.file_list.addItem(item)
            cache_cnt  = sum(1 for f in files if "_cache" in f)
            normal_cnt = len(files) - cache_cnt
            self.file_status.setText(
                f"📅 {expiry}  —  원본:{normal_cnt}  캐시:{cache_cnt}  총:{len(files)}개")
        else:
            self.file_status.setText(f"📅 {expiry}  —  저장된 파일 없음")

    # ── 파일 리스트 클릭 → 차트 출력 ──
    def _on_file_list_clicked(self, item: QListWidgetItem):
        self._load_and_render_file(item)

    def _on_file_list_double_clicked(self, item: QListWidgetItem):
        self._load_and_render_file(item)

    def _load_and_render_file(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            self.file_status.setText(f"❌ 파일 없음: {path}")
            return
        try:
            # _cache 파일이 있으면 우선 로드 (단, 이미 _cache이면 그냥 로드)
            actual_path = path
            if "_cache" not in os.path.basename(path):
                base, ext = os.path.splitext(path)
                cache_path = base + "_cache" + ext
                if os.path.exists(cache_path):
                    actual_path = cache_path
                    self.second_log.appendPlainText(
                        f"📦 캐시 파일 우선 로드: {os.path.basename(cache_path)}")
            rows = _load_rows_xlsx(actual_path)
            if not rows:
                self.file_status.setText("❌ 데이터 없음")
                return
            # 전체 캐시 갱신
            self._all_rows_cache = rows
            self.second_log.appendPlainText(
                f"📂 로드: {os.path.basename(path)}  ({len(rows)}봉)")
            # 표시 구간 필터 적용 후 렌더링 (파일명에서 날짜 추출 시도)
            start_hhmm, end_hhmm = self._get_display_range()
            fname = os.path.basename(path)
            date_str = getattr(self, "_current_date_str", "")
            # 파일명에서 날짜 추출: YYYY-MM-DD_SPXW...xlsx
            try:
                date_str = fname[:10]  # 'YYYY-MM-DD'
            except Exception:
                pass
            self._current_date_str = date_str
            display_rows = _filter_display_window(rows, start_hhmm, end_hhmm, date_str)
            self._render_display_rows(display_rows, start_hhmm, end_hhmm, date_str)
            total_n = len(rows)
            t0 = rows[0]["time"]; t1 = rows[-1]["time"]
            self.second_status.setText(
                f"📂 {os.path.basename(path)}  전체:{total_n}봉 ({t0}~{t1})")
            self.file_status.setText(
                f"✅ {os.path.basename(path)}  →  차트 출력 완료")
        except Exception as e:
            self.file_status.setText(f"❌ 로드 오류: {e}")
            self.second_log.appendPlainText(f"❌ 로드 오류: {e}")

    # ── 1초봉 수집 실행 (QThread 안전 버전) ──
    def on_second_fetch_clicked(self):
        symbol = self.second_symbol_edit.text().strip()
        date_str = self.second_date_edit.date().toString("yyyy-MM-dd")

        if not symbol:
            QMessageBox.warning(self, "입력 오류", "심볼을 입력하거나 자동 생성하세요.")
            return
        if not self.api_key:
            QMessageBox.warning(self, "API Key 오류",
                                "API Key가 비어 있습니다.\n화면 상단에서 입력하거나 CD-KEY.txt 파일을 생성하세요.")
            return

        self._current_date_str = date_str
        summer = _is_summer_time(date_str)
        s_tag = "섬머(22:30~05:00)" if summer else "비섬머(23:30~06:00)"
        self.second_status.setText(f"🔄 [{s_tag}] 수집 중...")
        self.second_log.appendPlainText(f"📡 [{s_tag}] 수집: {symbol}  날짜: {date_str}")
        self.session_info_lbl.setText(f"📌 {date_str} [{s_tag}]")
        self.second_fetch_btn.setEnabled(False)
        self.second_gen_btn.setEnabled(False)

        self._start_second_thread(symbol, date_str)

    def _start_second_thread(self, symbol: str, date_str: str):
        """threading.Thread로 수집 → Queue.put (시그널/QThread 없음 — 크래시 방지)."""
        api_key  = self.api_key
        result_q = self._second_result_queue

        def _worker():
            try:
                rows = _fetch_second_bars_polygon(api_key, symbol, date_str, limit=50000)
            except Exception as e:
                rows = []
                print(f"[fetch] 오류: {e}")
            result_q.put((symbol, rows))   # GUI 접근 없이 Queue에만 저장

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _poll_result_queues(self):
        """QTimer(50ms) 콜백 — 메인 스레드에서 Queue 소비, 완전 안전."""
        # 1초봉 결과
        try:
            while True:
                symbol, rows = self._second_result_queue.get_nowait()
                self._on_second_done_main(symbol, rows)
        except _queue_module.Empty:
            pass
        # 1분봉 결과
        try:
            while True:
                strike, side, rows = self._fetch_result_queue.get_nowait()
                self._on_fetch_done_main(strike, side, rows)
        except _queue_module.Empty:
            pass
        # 스캔 결과
        try:
            while True:
                results = self._scan_result_queue.get_nowait()
                self._on_scan_done_main(results)
        except _queue_module.Empty:
            pass

    def _start_second_worker(self, symbol: str, date_str: str):
        """하위 호환용 — _start_second_thread 호출."""
        self._start_second_thread(symbol, date_str)

    def _get_display_range(self):
        """콤보박스에서 현재 선택된 표시 시작/종료 (HH:MM 문자열) 반환."""
        return self.disp_start_combo.currentText(), self.disp_end_combo.currentText()

    def _render_with_current_range(self):
        """현재 캐시된 전체 봉(_all_rows_cache)을 현재 콤보 설정으로 재렌더링."""
        rows = getattr(self, "_all_rows_cache", None)
        if not rows:
            return
        start_hhmm, end_hhmm = self._get_display_range()
        date_str = getattr(self, "_current_date_str", "")
        display_rows = _filter_display_window(rows, start_hhmm, end_hhmm, date_str)
        self._render_display_rows(display_rows, start_hhmm, end_hhmm, date_str)

    def _on_display_range_changed(self):
        """표시 구간 콤보 변경 시 즉시 재렌더링."""
        self._render_with_current_range()

    def _render_display_rows(self, display_rows: List[Dict[str, Any]],
                              start_hhmm: str, end_hhmm: str, date_str: str = ""):
        """필터된 봉을 테이블+차트에 출력."""
        disp_n = len(display_rows)
        t0 = display_rows[0]["time"] if display_rows else "??"
        t1 = display_rows[-1]["time"] if display_rows else "??"
        summer_tag = "섬머" if _is_summer_time(date_str) else "비섬머" if date_str else ""
        tag_str = f"  [{summer_tag}]" if summer_tag else ""

        # GroupBox 타이틀 갱신
        self._table_box.setTitle(
            f"1초봉 데이터 테이블{tag_str}  KST {start_hhmm} ~ {end_hhmm}:59  │  {disp_n}봉")

        # 테이블
        self.second_table.setRowCount(disp_n)
        for i, r in enumerate(display_rows):
            self.second_table.setItem(i, 0, QTableWidgetItem(r["time"]))
            self.second_table.setItem(i, 1, QTableWidgetItem(f"{r['open']:.4f}"))
            self.second_table.setItem(i, 2, QTableWidgetItem(f"{r['high']:.4f}"))
            self.second_table.setItem(i, 3, QTableWidgetItem(f"{r['low']:.4f}"))
            self.second_table.setItem(i, 4, QTableWidgetItem(f"{r['close']:.4f}"))
            self.second_table.setItem(i, 5, QTableWidgetItem(f"{r.get('volume', 0):.0f}"))
        self.second_table.scrollToBottom()

        # 차트
        times  = [r["time"]  for r in display_rows]
        opens  = [r["open"]  for r in display_rows]
        highs  = [r["high"]  for r in display_rows]
        lows   = [r["low"]   for r in display_rows]
        closes = [r["close"] for r in display_rows]
        vols   = [r.get("volume", 0) for r in display_rows]

        if self.second_chart_mode.currentText() == "캔들":
            self.second_chart.plot_candles(times, opens, highs, lows, closes, volumes=vols)
        else:
            self.second_chart.plot_line(times, closes, volumes=vols)

    @pyqtSlot(str, list)
    def _on_second_done_main(self, symbol: str, rows: List[Dict[str, Any]]):
        # 자동조회 진행 중이 아닐 때만 버튼 활성화
        if not getattr(self, "_auto_active", False):
            self.second_fetch_btn.setEnabled(True)
            self.second_gen_btn.setEnabled(True)
        if not rows:
            self.second_status.setText("❌ 데이터 없음 (유료 플랜 확인 필요)")
            self.second_log.appendPlainText(
                f"✗ {symbol}: 결과 없음 — Polygon 1초봉은 Starter 이상 플랜 필요")
            self._pending_save = False
            return

        # 전체 봉 캐시 저장 (구간 변경 시 재렌더링에 사용)
        self._all_rows_cache = rows
        total_n = len(rows)
        t_all_0 = rows[0]["time"]
        t_all_1 = rows[-1]["time"]

        start_hhmm, end_hhmm = self._get_display_range()
        date_str = getattr(self, "_current_date_str", "")
        display_rows = _filter_display_window(rows, start_hhmm, end_hhmm, date_str)
        disp_n = len(display_rows)
        t0 = display_rows[0]["time"] if display_rows else "??"
        t1 = display_rows[-1]["time"] if display_rows else "??"
        summer_info = "섬머" if _is_summer_time(date_str) else "비섬머" if date_str else ""

        self.second_status.setText(
            f"✅ [{summer_info}] 전체:{total_n}봉 ({t_all_0}~{t_all_1})  "
            f"│  표시({start_hhmm}~{end_hhmm}): {disp_n}봉 ({t0}~{t1})")
        self.second_log.appendPlainText(
            f"✓ {symbol}: 전체 {total_n}봉  →  표시 {disp_n}봉 ({t0}~{t1})  [{summer_info}]")

        self._render_display_rows(display_rows, start_hhmm, end_hhmm, date_str)

        # ★ _pending_save 플래그가 있으면 자동 저장
        if getattr(self, "_pending_save", False):
            self._pending_save = False
            self._save_current_data(symbol, rows)
            # 자동조회 중이면 다음 태스크 실행
            if getattr(self, "_auto_active", False):
                self._run_next_auto_task()
                return

    # ── 1분봉 조회 ──
    def on_load_clicked(self):
        provider = self.provider_map[self.source_combo.currentText()]
        expiry = self.expiry_edit.date().toString("yyyy-MM-dd")
        try:
            center = float(self.center_edit.text())
        except Exception:
            QMessageBox.warning(self, "입력 오류", "중심 행사가를 숫자로 입력하세요.")
            return

        r_fetch = int(self.range_combo.currentText())
        r_show = int(self.show_range.value())
        side_mode = self.side_filter.currentText()
        want_sides = self._want_sides(side_mode)
        strikes_all = self._make_strikes(center, r_fetch)
        strikes_show = self._make_strikes(center, r_show)

        self.tabs.clear()
        self.result_list.clear()
        self.rows_by_strike_side.clear()
        self.widgets_by_strike.clear()
        self.log_box.clear()

        base_dir = os.path.join("data", "spxw")

        for strike in strikes_show:
            table, chart, tab = self._create_tab_widgets()
            self.tabs.addTab(tab, f"SPXW {strike:.1f}")
            self.widgets_by_strike[strike] = (table, chart)

            side_rows: Dict[str, List[Dict[str, Any]]] = {}
            for side in want_sides:
                cpath = cache_file_path(base_dir, expiry, strike, side)
                if os.path.exists(cpath) or os.path.exists(
                        cpath.replace(".csv", ".npz")):
                    rows = load_rows_csv(cpath)
                    if rows:
                        side_rows[side] = rows

            if side_rows:
                self.rows_by_strike_side[strike] = dict(
                    self.rows_by_strike_side.get(strike, {}), **side_rows)
                final_rows = self._pick_rows_for_view(strike, side_mode)
                self._apply_rows_to_widgets(
                    self.widgets_by_strike[strike][0],
                    self.widgets_by_strike[strike][1], final_rows)
                self.sig_log.emit(
                    f"📦 캐시: {strike:.1f} ({', '.join(side_rows.keys())})")

        to_fetch: List[Tuple[float, str]] = []
        existing = _index_existing_for_expiry(base_dir, expiry)
        for strike in strikes_all:
            for side in want_sides:
                if (strike, side) in existing:
                    continue
                to_fetch.append((strike, side))

        if to_fetch:
            self.sig_log.emit(f"🔍 {len(to_fetch)}건 API 조회 시작...")
            for strike, side in to_fetch:
                self._pool.submit(self._fetch_worker, provider, expiry, strike, side)

    # ── 자동조회 ──
    def on_auto_clicked(self):
        if self._auto_running:
            QMessageBox.information(self, "알림", "이미 자동 조회가 진행 중입니다.")
            return
        try:
            center = float(self.center_edit.text())
        except Exception:
            QMessageBox.warning(self, "입력 오류", "중심 행사가를 숫자로 입력하세요.")
            return

        r_fetch = int(self.range_combo.currentText())
        side_mode = self.side_filter.currentText()
        want_sides = self._want_sides(side_mode)
        provider = self.provider_map[self.source_combo.currentText()]
        s_q = self.start_edit.date()
        e_q = self.end_edit.date()
        if e_q < s_q:
            s_q, e_q = e_q, s_q

        trading_days: List[QDate] = []
        cur = QDate(s_q)
        while cur <= e_q:
            d_py = dt_date(cur.year(), cur.month(), cur.day())
            if is_us_trading_day(d_py):
                trading_days.append(QDate(cur))
            cur = cur.addDays(1)

        if not trading_days:
            QMessageBox.information(self, "알림", "영업일이 없습니다.")
            return

        strikes_all = self._make_strikes(center, r_fetch)
        base_dir = os.path.join("data", "spxw")
        self._auto_running = True
        self.auto_btn.setEnabled(False)
        self.auto_prog.setMaximum(len(trading_days))
        self.auto_prog.setValue(0)
        self.auto_status.setText("자동조회 시작...")

        def _auto_worker():
            submitted = 0
            total = len(trading_days)
            for i, qd in enumerate(trading_days, 1):
                expiry = qd.toString("yyyy-MM-dd")
                self.sig_auto_progress.emit(expiry, i, total)
                existing = _index_existing_for_expiry(base_dir, expiry)
                for strike in strikes_all:
                    for side in want_sides:
                        if (strike, side) in existing:
                            continue
                        self._pool.submit(self._fetch_worker, provider, expiry, strike, side)
                        submitted += 1
                self.sig_log.emit(f"📅 {expiry} (누적:{submitted})")
            self.sig_log.emit("✅ 자동조회 제출 완료")
            self.sig_auto_finished.emit()

        self._pool.submit(_auto_worker)

    # ── 1분봉 워커 ──
    def _fetch_worker(self, provider, expiry: str, strike: float, side: str):
        # list 시그널 emit 제거 → Queue.put (크래시 방지)
        try:
            base_dir = os.path.join("data", "spxw")
            cpath = cache_file_path(base_dir, expiry, strike, side)
            sym = build_spx_zero_day_symbol(strike, side, expiry)
            rows: List[Dict[str, Any]] = []
            if sym:
                _POLYGON_RL.acquire()
                rows = fetch_minutes_polygon(
                    provider, sym, expiry, limit=399, api_key=self.api_key)
                if rows:
                    try:
                        save_rows_csv(cpath, rows)
                    except Exception:
                        pass
            self._fetch_result_queue.put((strike, side, rows))
        except Exception as e:
            self.sig_log.emit(f"✗ 워커 예외: {e}")

    def _on_fetch_done_main(self, strike: float, side: str, rows: List[Dict[str, Any]]):
        if rows:
            cur = self.rows_by_strike_side.get(strike, {})
            cur[side] = rows
            self.rows_by_strike_side[strike] = cur
            if strike in self.widgets_by_strike:
                self._refresh_strike_view(strike)
            self.log_box.appendPlainText(f"✓ {strike:.1f} [{side}] {len(rows)}행")
        else:
            self.log_box.appendPlainText(f"✗ {strike:.1f} [{side}] 데이터 없음")

    # ── 검색1 ──
    def on_scan_clicked(self):
        self.result_list.clear()
        try:
            thresholds = [float(x.strip())
                          for x in (self.threshold_edit.text() or "").split(",")
                          if x.strip()]
        except Exception:
            thresholds = [200.0, 300.0, 500.0]
        try:
            window = int(self.scan_interval.currentText())
        except Exception:
            window = 10

        side_mode = self.side_filter.currentText()
        strikes_snapshot: List[Tuple[float, List[Dict[str, Any]]]] = []
        for strike in list(self.widgets_by_strike.keys()):
            rows = self._pick_rows_for_view(strike, side_mode) or []
            strikes_snapshot.append((strike, list(rows)))

        def _scan_worker(snapshot, wv, ths):
            out: List[Dict[str, Any]] = []
            try:
                for strike, rows in snapshot:
                    for idx, pct in scan_windows(rows, wv, ths):
                        out.append(dict(strike=strike, row=idx, pct=pct,
                                        time=rows[idx]['time']))
            except Exception as e:
                out.append(dict(error=str(e)))
            return out

        scan_q = self._scan_result_queue
        def _submit():
            result = _scan_worker(strikes_snapshot, window, thresholds)
            scan_q.put(result)
        threading.Thread(target=_submit, daemon=True).start()

    def _on_scan_done_main(self, items: List[Dict[str, Any]]):
        if not items:
            self.log_box.appendPlainText("🔎 검색 결과 없음")
            return
        if 'error' in items[0]:
            self.log_box.appendPlainText(f"✗ 검색 오류: {items[0]['error']}")
            return
        for it in items:
            txt = f"[{it['strike']:.1f}] {it['time']} (+{it['pct']:.1f}%)"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, dict(strike=it['strike'], row=it['row']))
            self.result_list.addItem(item)
        self.log_box.appendPlainText(f"🔎 검색 완료: {len(items)}건")

    def on_result_clicked(self, item: QListWidgetItem):
        info = item.data(Qt.UserRole) or {}
        strike = info.get("strike")
        row = info.get("row")
        if strike is None or row is None:
            return
        for ti in range(self.tabs.count()):
            if f"{strike:.1f}" in self.tabs.tabText(ti):
                self.tabs.setCurrentIndex(ti)
                container = self.tabs.widget(ti)
                splitter = container.layout().itemAt(0).widget()
                table = splitter.widget(0)
                if isinstance(table, QTableWidget):
                    table.setCurrentCell(row, 0)
                    table.scrollToItem(table.item(row, 0),
                                       QTableWidget.PositionAtCenter)
                break

    # ── 렌더링 유틸 ──
    def _pick_rows_for_view(self, strike: float, side_mode: str) -> List[Dict[str, Any]]:
        sd = self.rows_by_strike_side.get(strike, {})
        if side_mode == "콜만":  return sd.get("CALL", [])
        if side_mode == "풋만":  return sd.get("PUT", [])
        call_rows = sd.get("CALL", [])
        put_rows = sd.get("PUT", [])
        if call_rows and put_rows:
            return merge_call_put([call_rows, put_rows])
        return call_rows or put_rows or []

    def on_side_mode_changed(self):
        for strike in list(self.widgets_by_strike.keys()):
            self._refresh_strike_view(strike)

    def _create_tab_widgets(self):
        splitter = QSplitter(Qt.Horizontal)
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            ["Time(KST)", "Open", "High", "Low", "Close", "Volume"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)

        chart = MiniChartCanvas(parent=self)
        chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        splitter.addWidget(table)
        splitter.addWidget(chart)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        cont = QWidget()
        v = QVBoxLayout(cont)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(splitter)
        return table, chart, cont

    def _apply_rows_to_widgets(self, table: QTableWidget,
                               chart: MiniChartCanvas,
                               rows: List[Dict[str, Any]]):
        rows = rows[: self.chart_count.value()]
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(r["time"]))
            table.setItem(i, 1, QTableWidgetItem(f"{r['open']:.2f}"))
            table.setItem(i, 2, QTableWidgetItem(f"{r['high']:.2f}"))
            table.setItem(i, 3, QTableWidgetItem(f"{r['low']:.2f}"))
            table.setItem(i, 4, QTableWidgetItem(f"{r['close']:.2f}"))
            table.setItem(i, 5, QTableWidgetItem(f"{r.get('volume', 0.0):.0f}"))

        times  = [r["time"]  for r in rows]
        opens  = [r["open"]  for r in rows]
        highs  = [r["high"]  for r in rows]
        lows   = [r["low"]   for r in rows]
        closes = [r["close"] for r in rows]
        vols   = [r.get("volume", 0.0) for r in rows]

        if self.chart_mode.currentText() == "라인":
            chart.plot_line(times, closes, volumes=vols)
        else:
            chart.plot_candles(times, opens, highs, lows, closes, volumes=vols)

    def _refresh_strike_view(self, strike: float):
        rows = self._pick_rows_for_view(strike, self.side_filter.currentText())
        if not rows:
            return
        tc = self.widgets_by_strike.get(strike)
        if tc:
            self._apply_rows_to_widgets(tc[0], tc[1], rows)
            return
        for ti in range(self.tabs.count()):
            if f"{strike:.1f}" in self.tabs.tabText(ti):
                container = self.tabs.widget(ti)
                splitter = container.layout().itemAt(0).widget()
                t = splitter.widget(0)
                c = splitter.widget(1)
                if isinstance(t, QTableWidget) and isinstance(c, MiniChartCanvas):
                    self._apply_rows_to_widgets(t, c, rows)
                break

    def _on_chart_count_changed(self, *_):
        for strike in list(self.widgets_by_strike.keys()):
            self._refresh_strike_view(strike)

    def _on_close_tab(self, index: int):
        if index < 0 or index >= self.tabs.count():
            return
        label = self.tabs.tabText(index)
        try:
            parts = label.split()
            if len(parts) >= 2:
                sp = parts[1].split("(")[0]
                strike = float(sp)
                if strike in self.widgets_by_strike:
                    del self.widgets_by_strike[strike]
        except Exception:
            pass
        w = self.tabs.widget(index)
        self.tabs.removeTab(index)
        if w:
            w.deleteLater()

    def _on_auto_progress(self, date_str: str, current: int, total: int):
        self.auto_prog.setMaximum(total)
        self.auto_prog.setValue(current)
        self.auto_status.setText(f"{date_str} 처리 중... ({current}/{total})")

    def _on_auto_finished(self):
        self._auto_running = False
        self.auto_btn.setEnabled(True)
        self.auto_status.setText("자동조회 완료")

    def _make_strikes(self, center: float, r: int) -> List[float]:
        step = 5.0
        c = round(center / step) * step
        vals = [c + i * step for i in range(-r, r + 1)]
        return sorted(list({round(v, 1) for v in vals}))


# ═══════════════════════════════════════════════════════════════════
