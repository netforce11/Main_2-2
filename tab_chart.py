"""
tab_chart.py — 1분봉 차트 탭  v6.4
════════════════════════════════════════════════════════════════
v6.3 변경:
  - tab_chart_libs/ 로 로직 분리 (200줄 단위)
  - 시간 입력: ":" 없이 숫자만 입력 가능 (1030 → 10:30 자동 변환)
  - 📷 차트 캡쳐 버튼: 마커 우측에 추가
    저장 경로: /home/netforce/US_Data/chart_save/{날짜}_{시각}_{심볼}.png

v6.4 변경:
  - 🔤 레이블 기능 추가 (chart_labels.py 신규)
    차트 클릭으로 숫자(1~5) / 문자(A~E) 레이블을 원하는 위치에 배치
    체크박스 해제로 개별 삭제, 🗑 버튼으로 전체 삭제
  - 📈 일봉 추가 보기 버튼 (chart_daily.py 신규)
    사이드바 하단 버튼 클릭 → 분차트 테이블 숨기고 일봉 캔들 표시
    캘린더 날짜 기준 ±50봉 (~100봉), 날짜 중앙 정렬

파일 구조:
  tab_chart_libs/
    chart_workers.py  — CandlestickItem / PolygonWorker / IBKRBarTimer
    chart_theme.py    — _THEME / apply_theme / c_up / c_dn
    chart_markers.py  — 시간 마커 + 숫자 입력 + 📷 캡쳐
    chart_hlines.py   — 가로 라인 (레이블 모드 분기 포함)
    chart_labels.py   — 텍스트 레이블 (숫자/문자)
    chart_rt.py       — 실시간 스트림
    chart_data.py     — 데이터 로드·표시·KST
    chart_peaks.py    — 수급 피크 + FTD/공매도
    chart_daily.py    — 일봉 추가 보기 ← v6.4 신규
════════════════════════════════════════════════════════════════
"""

import os, sys, json
from pathlib import Path
from datetime import date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QCheckBox, QSpinBox, QSplitter,
    QAbstractItemView, QMessageBox,
    QCalendarWidget, QFrame, QRadioButton, QButtonGroup,
    QInputDialog, QTableWidget, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QFont

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, make_table, tbl_set, ts,
    REQ_HIST, SAVE_DIR, INDEX_SYM,
    make_und_contract, auto_mdt, is_market_open,
)

# ── tab_chart_libs 경로 등록 ─────────────────────────────────
_LIBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tab_chart_libs")
if _LIBS_DIR not in sys.path:
    sys.path.insert(0, _LIBS_DIR)

from chart_workers  import CandlestickItem, PolygonWorker, IBKRBarTimer
from chart_theme    import _THEME, apply_theme, c_up, c_dn
from chart_markers  import add_time_marker, on_marker_chk, \
                           redraw_time_markers, capture_chart
from chart_hlines   import on_chart_click, on_hline_chk, \
                           del_hlines, redraw_hlines
from chart_labels   import on_chart_label_click, on_label_chk, \
                           del_labels, redraw_labels
from chart_rt       import on_rt_btn, start_stream, stop_rt, \
                           on_bar_in, fetch_missing_polygon
from chart_data     import (
    on_calendar, on_multi_chk, do_multi_day,
    fetch_ibkr_history, fetch_polygon_history,
    load_day_df, download_day, update_display,
    append_right, clr_right, push_trend_df,
    et_to_kst_str, fmt_time, on_range_changed,
)
from chart_tab_ibkr import force_redownload
from chart_peaks    import (
    peak1, peak2, update_peak3,
    load_aux_file, on_aux_date_click,
)
# ── v6.4 신규 ────────────────────────────────────────────────
from chart_daily    import toggle_daily_view, load_daily_data, \
                           render_daily, center_on_calendar
# ── v6.5 신규 ────────────────────────────────────────────────
from chart_prefetch import PrefetchManager
# ── 기능 추가: 거래량급증 / 체결마커 / 틱속도 ────────────────
from chart_vol_surge   import draw_vol_surge, clear_vol_surge
from chart_exec_marker import (init_exec_markers, add_exec_marker,
                                redraw_exec_markers, clear_exec_markers,
                                load_exec_markers_from_db)
from chart_tick_speed  import stop_tick_speed
# ── v6.7 신규: 날짜별 메모 ───────────────────────────────────
from chart_memo import toggle_memo_panel, on_memo_date_changed

try:
    from common import (DATA_ROOT, API_KEY_FILE, WATCHLIST_FILE,
                        DARK_BG, PANEL_BG, CARD_BG, BLUE, RED,
                        GREEN, ORANGE, GRAY, TEXT, GLOBAL_STYLE)
except Exception:
    DATA_ROOT      = Path("/home/netforce/US_Data/US_stockData")
    API_KEY_FILE   = DATA_ROOT / "stock_api_key"
    WATCHLIST_FILE = DATA_ROOT / "watchlist.json"

CHART_WATCHLIST = SAVE_DIR / "chart_watchlist.json"


# ══════════════════════════════════════════════════════════════
class ChartGrid(QWidget):
    """Tab 7: 1분봉 차트."""

    def __init__(self, mw):
        super().__init__()
        self.mw             = mw
        self.api_key        = self._load_api_key()
        self.worker         = None
        self.ibkr_timer     = None
        self.mode           = "polygon"
        self.df_raw         = []
        self.df             = None
        self.is_rt          = False
        self.selected_date  = None
        self.current_sym    = "SPY"
        self._right_row     = 0
        self.current_processed = []
        self.dark_mode         = False
        self._multi_day_active = False
        self._multi_day_count  = 1
        self._hlines: dict        = {}
        self._time_markers: dict  = {}
        self._chart_labels: dict  = {}
        # ── v6.4: 일봉 보기 상태 ─────────────────────────
        self._daily_worker         = None
        self._daily_view_active    = False
        # ── v6.5: 선행 다운로드 ──────────────────────────
        self._prefetch_manager     = None
        self._prefetch_done_today  = None   # 마지막 실행 date
        self._build()
        self._load_watchlist()
        self._apply_theme()
        # ── 체결 마커 초기화 (SignalBridge 연결 포함) ─────────
        init_exec_markers(self)

    # ── 위임 메서드 바인딩 ────────────────────────────────────
    _apply_theme         = apply_theme
    _c_up                = c_up
    _c_dn                = c_dn
    _add_time_marker     = add_time_marker
    _on_marker_chk       = on_marker_chk
    _redraw_time_markers = redraw_time_markers
    capture_chart        = capture_chart
    _on_chart_click      = on_chart_click
    _on_hline_chk        = on_hline_chk
    _del_hlines          = del_hlines
    _redraw_hlines       = redraw_hlines
    _on_chart_label_click = on_chart_label_click
    _on_label_chk         = on_label_chk
    _del_labels           = del_labels
    _redraw_labels        = redraw_labels
    _on_rt_btn             = on_rt_btn
    start_stream           = start_stream
    _stop_rt               = stop_rt
    _on_bar_in             = on_bar_in
    _fetch_missing_polygon = fetch_missing_polygon
    _on_calendar           = on_calendar
    _on_multi_chk          = on_multi_chk
    _do_multi_day          = do_multi_day
    _fetch_ibkr_history    = fetch_ibkr_history
    _fetch_polygon_history = fetch_polygon_history
    _load_day_df           = load_day_df
    _download_day          = download_day
    _update_display        = update_display
    _append_right          = append_right
    _clr_right             = clr_right
    _push_trend_df         = push_trend_df
    _et_to_kst_str         = et_to_kst_str
    _fmt_time              = fmt_time
    _on_range_changed      = on_range_changed
    _peak1                 = peak1
    _peak2                 = peak2
    _update_peak3          = update_peak3
    _load_aux_file         = load_aux_file
    _on_aux_date_click     = on_aux_date_click
    _force_redownload      = force_redownload
    # ── v6.4 일봉 바인딩 ──────────────────────────────────────
    _toggle_daily_view     = toggle_daily_view
    _load_daily_data       = load_daily_data
    _render_daily          = render_daily
    _center_on_calendar    = center_on_calendar
    # ── 기능 추가 바인딩 ──────────────────────────────────────
    _draw_vol_surge        = draw_vol_surge
    _clear_vol_surge       = clear_vol_surge
    _add_exec_marker       = add_exec_marker
    _redraw_exec_markers   = redraw_exec_markers
    _clear_exec_markers    = clear_exec_markers
    _load_exec_from_db     = load_exec_markers_from_db
    _stop_tick_speed       = stop_tick_speed
    # ── v6.7 메모 바인딩 ──────────────────────────────────────
    _toggle_memo_panel     = toggle_memo_panel
    _on_memo_date_changed  = on_memo_date_changed

    # ── API 키 / 관심종목 ─────────────────────────────────────
    def _load_api_key(self):
        try: return API_KEY_FILE.read_text(encoding="utf-8").strip()
        except: return ""

    def _load_watchlist(self):
        try:
            if CHART_WATCHLIST.exists():
                items = json.loads(
                    CHART_WATCHLIST.read_text(encoding="utf-8"))
                for sym in items: self.watch_list.addItem(sym)
        except: pass

    def _save_watchlist(self):
        items = [self.watch_list.item(i).text()
                 for i in range(self.watch_list.count())]
        CHART_WATCHLIST.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def _w_add(self):
        t, ok = QInputDialog.getText(self, "추가", "심볼:")
        if ok and t.strip():
            self.watch_list.addItem(t.strip().upper())
            self._save_watchlist()

    def _w_del(self):
        r = self.watch_list.currentRow()
        if r >= 0:
            self.watch_list.takeItem(r); self._save_watchlist()

    def _on_mode_change(self):
        self.mode = "ibkr" if self.radio_ibkr.isChecked() else "polygon"
        self.lbl_mode.setText(
            "IBKR API" if self.mode == "ibkr" else "Polygon.io")

    def _on_dark(self, dark: bool = None):
        if dark is not None: self.dark_mode = dark
        self._apply_theme(); self._update_display()

    # ── Splitter 설정 저장/복원 ───────────────────────────────
    def _get_extra_settings(self) -> dict:
        d = {}
        try:
            d["h_split"]   = list(self._h_splitter.sizes())
            d["v_split"]   = list(self._v_splitter.sizes())
            d["tbl_split"] = list(self._tbl_splitter.sizes())
        except Exception: pass
        return d

    def _apply_extra_settings(self, s: dict):
        def _restore():
            try:
                if s.get("h_split"):   self._h_splitter.setSizes(s["h_split"])
                if s.get("v_split"):   self._v_splitter.setSizes(s["v_split"])
                if s.get("tbl_split"): self._tbl_splitter.setSizes(s["tbl_split"])
            except Exception: pass
        QTimer.singleShot(100, _restore)

    # ── UI 빌드 ──────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4); root.setSpacing(0)

        self._h_splitter = QSplitter(Qt.Horizontal)
        self._h_splitter.setHandleWidth(5)
        self._h_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        self._h_splitter.addWidget(self._build_sidebar())
        self._h_splitter.addWidget(self._build_content())
        self._h_splitter.setSizes([255, 1200])
        root.addWidget(self._h_splitter)

    def _build_sidebar(self) -> QScrollArea:
        from chart_build_side import build_sidebar
        return build_sidebar(self)

    def _build_content(self) -> QSplitter:
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(5)
        self._v_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")
        self._v_splitter.addWidget(self._build_tables())
        self._v_splitter.addWidget(self._build_chart_area())
        self._v_splitter.setSizes([280, 520])
        return self._v_splitter

    def _build_tables(self):
        from chart_build_main import build_tables
        return build_tables(self)

    def _build_chart_area(self):
        from chart_build_main import build_chart_area
        return build_chart_area(self)

    def _on_force_reload(self):
        tgt = self.calendar.selectedDate().toPyDate()
        sym = self.sym_in.text().strip().upper()
        if not sym:
            QMessageBox.warning(self, "종목 없음", "종목을 입력하세요."); return
        self.status_lbl.setText(f"🔄 {sym} {tgt} 재다운로드 중…")
        self._force_redownload(sym, tgt)

    # ── v6.5: 탭 포커스 → 선행 다운로드 ─────────────────────
    def on_tab_activate(self):
        """main.py _on_tab_changed() 에서 탭 활성 시 호출됨.
        하루 1회만 관심종목 선행 다운로드 실행."""
        from datetime import date as _date
        today = _date.today()
        if self._prefetch_done_today == today:
            return   # 오늘 이미 실행

        # 이전 매니저가 아직 실행 중이면 중복 시작 방지
        if self._prefetch_manager is not None:
            try:
                if self._prefetch_manager.is_running():
                    return
            except Exception:
                pass
            self._prefetch_manager = None

        symbols = [self.watch_list.item(i).text().strip().upper()
                   for i in range(self.watch_list.count())
                   if self.watch_list.item(i).text().strip()]
        if not symbols:
            return

        self._prefetch_done_today = today
        mgr = PrefetchManager(self)
        mgr.status_msg.connect(self._safe_status)
        mgr.ibkr_alert.connect(
            lambda msg: QMessageBox.warning(self, "IBKR 미연결", msg))
        mgr.all_done.connect(self._on_prefetch_done)
        self._prefetch_manager = mgr
        mgr.start(symbols, self.api_key, mw=self.mw)

    def _on_prefetch_done(self):
        print("[Prefetch] 전체 완료")
        # all_done 시점에 매니저 참조 해제 → GC 가능 상태로 전환
        # (바로 None으로 세우면 시그널 disconnect 전 파괴 위험 → singleShot으로 지연)
        QTimer.singleShot(500, self._clear_prefetch_manager)

    def _clear_prefetch_manager(self):
        self._prefetch_manager = None

    def _safe_status(self, msg: str):
        """QThread → GUI 안전 상태 메시지 업데이트.
        status_lbl 이 QLabel 이면 setText, QTextEdit 이면 append 대신 setPlainText.
        QTextCursor 를 워커 스레드에서 건드리지 않도록 이 메서드 경유 필수."""
        from PyQt5.QtWidgets import QLabel, QTextEdit
        try:
            lbl = self.status_lbl
            if isinstance(lbl, QLabel):
                lbl.setText(msg)
            elif isinstance(lbl, QTextEdit):
                # QTextEdit 은 메인 스레드에서만 수정 가능
                # 시그널이 Qt.QueuedConnection 으로 큐잉되므로 여기서는 안전하지만
                # setText 대신 setPlainText 로 QTextCursor 생성을 최소화
                lbl.setPlainText(msg)
            else:
                lbl.setText(msg)
        except Exception:
            pass