"""
kr_chart_tab.py — 한국 주식 1분봉 차트 탭  v1.0
════════════════════════════════════════════════════════════════
데이터 소스 : 키움증권 OpenAPI+ (pykiwoom)
TR          : opt10080 — 주식분봉차트조회 (연속 요청)
실시간      : opt10080 주기적 갱신 (KrBarTimer)
저장 경로   : C:\\data\\Korea\\stock_1M\\{종목코드}\\{YYYYMM}.csv
               완료 마커: .downloaded\\{YYYYMMDD}

파일 구조:
  kr_chart_libs/
    kr_build_side.py   — 사이드바 UI
    kr_build_main.py   — 테이블·차트 영역
    kr_chart_theme.py  — 다크/라이트 팔레트
    kr_chart_data.py   — 데이터 로드·표시·캘린더
    kr_chart_kiwoom.py — opt10080 TR 연속 요청
    kr_chart_workers.py— CandlestickItem + 폴링 타이머
    kr_chart_markers.py— 시간 마커 + 캡쳐
    kr_chart_hlines.py — 가로 라인
    kr_chart_labels.py — 텍스트 레이블
    kr_chart_peaks.py  — 수급 피크 분석
    kr_chart_daily.py  — 일봉 추가 보기
════════════════════════════════════════════════════════════════
"""

import os, sys, json
from pathlib import Path
from datetime import date

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter,
    QInputDialog, QMessageBox, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QFont

try:
    import pyqtgraph as pg; PG = True
except ImportError:
    PG = False

# ── libs 경로 등록 ────────────────────────────────────────────
_LIBS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kr_chart_libs")
if _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from kr_chart_theme    import apply_theme, c_up, c_dn
from kr_chart_data     import (
    on_calendar, do_fetch_date, update_display,
    push_trend_df, fmt_kst, on_range_changed,
)
from kr_chart_kiwoom   import (
    fetch_history, fetch_max, fetch_20days,
    force_redownload, load_day_df,
)
from kr_chart_workers  import CandlestickItem, KrBarTimer
from kr_chart_markers  import (
    add_time_marker, on_marker_chk,
    redraw_time_markers, capture_chart,
)
from kr_chart_hlines   import on_chart_click, on_hline_chk, del_hlines, redraw_hlines
from kr_chart_labels   import on_chart_label_click, on_label_chk, del_labels, redraw_labels
from kr_chart_peaks    import peak1, peak2, update_peak3
from kr_chart_daily    import toggle_daily_view, load_daily_data, render_daily
from kr_chart_overlay  import (
    init_overlays, on_overlay_chk,
    redraw_overlays, clear_all_overlays,
)

KR_DATA_ROOT   = Path(r"C:\data\Korea\stock_1M")
CHART_SAVE_DIR = Path(r"C:\data\chart_save")
WATCHLIST_FILE = KR_DATA_ROOT / "kr_watchlist.json"

# 필수 관심종목 (코드: 표시명)
DEFAULT_WATCH = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "069500": "KODEX200",   # KOSPI200 ETF
}


class KoreaChartGrid(QWidget):
    """Tab: Korea_1분 — 한국 주식 1분봉 차트."""

    def __init__(self, mw):
        super().__init__()
        self.mw              = mw
        self.kiwoom          = getattr(mw, 'kiwoom', None)  # 이미 연결된 경우만 재사용
        self.mode            = "kiwoom"
        self.df_raw          = []          # list[dict]: t,o,h,l,c,v
        self.df              = None        # pandas DataFrame
        self.is_rt           = False
        self.selected_date   = None
        self.current_sym     = "005930"    # 삼성전자
        self.current_name    = "삼성전자"
        self._right_row      = 0
        self.current_processed = []
        self.dark_mode         = False
        self._multi_day_active = False
        self._multi_day_count  = 1
        self._hlines:        dict = {}
        self._time_markers:  dict = {}
        self._chart_labels:  dict = {}
        self._daily_view_active   = False
        self._daily_worker        = None
        # 연속 조회 상태
        self._fetch_next_key  = ""
        self._fetch_pages     = 0
        self._fetch_max_mode  = False
        self._kr_bar_timer    = None
        self._build()
        self._load_watchlist()
        self._apply_theme()
        init_overlays(self)   # 오버레이 상태 초기화

    # ── 위임 바인딩 ───────────────────────────────────────────
    _apply_theme          = apply_theme
    _c_up                 = c_up
    _c_dn                 = c_dn
    _on_calendar          = on_calendar
    _do_fetch_date        = do_fetch_date
    _update_display       = update_display
    _push_trend_df        = push_trend_df
    _fmt_kst              = fmt_kst
    _on_range_changed     = on_range_changed
    _fetch_history        = fetch_history
    _fetch_max            = fetch_max
    _fetch_20days         = fetch_20days
    _force_redownload     = force_redownload
    _load_day_df          = load_day_df
    _add_time_marker      = add_time_marker
    _on_marker_chk        = on_marker_chk
    _redraw_time_markers  = redraw_time_markers
    capture_chart         = capture_chart
    _on_chart_click       = on_chart_click
    _on_hline_chk         = on_hline_chk
    _del_hlines           = del_hlines
    _redraw_hlines        = redraw_hlines
    _on_chart_label_click = on_chart_label_click
    _on_label_chk         = on_label_chk
    _del_labels           = del_labels
    _redraw_labels        = redraw_labels
    _peak1                = peak1
    _peak2                = peak2
    _update_peak3         = update_peak3
    _toggle_daily_view    = toggle_daily_view
    _load_daily_data      = load_daily_data
    _render_daily         = render_daily
    _on_overlay_chk       = on_overlay_chk
    _redraw_overlays      = redraw_overlays
    _clear_all_overlays   = clear_all_overlays

    def _on_multi_chk(self, days, chk, state):
        from kr_chart_data import on_multi_chk
        on_multi_chk(self, days, chk, state)

    def _clr_right(self):
        self.table_r.setRowCount(0)

    # ── 관심종목 저장·복원 ────────────────────────────────────
    def _load_watchlist(self):
        items = dict(DEFAULT_WATCH)
        try:
            if WATCHLIST_FILE.exists():
                saved = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
                items.update(saved)
        except Exception:
            pass
        for code, name in items.items():
            self._add_watch_item(code, name)

    def _save_watchlist(self):
        items = {}
        for i in range(self.watch_list.count()):
            txt = self.watch_list.item(i).text()
            if "(" in txt and txt.endswith(")"):
                name = txt[:txt.rfind("(")]
                code = txt[txt.rfind("(")+1:-1]
                items[code] = name
        WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        WATCHLIST_FILE.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _w_add(self):
        txt, ok = QInputDialog.getText(self, "추가", "종목코드 또는 코드(이름):\n예) 005930 또는 005930(삼성전자)")
        if not ok or not txt.strip():
            return
        txt = txt.strip()
        if "(" in txt and txt.endswith(")"):
            name = txt[:txt.rfind("(")]
            code = txt[txt.rfind("(")+1:-1]
        else:
            code = txt.zfill(6)
            name = "종목"
        self._add_watch_item(code, name)
        self._save_watchlist()

    def _w_del(self):
        r = self.watch_list.currentRow()
        if r >= 0:
            txt = self.watch_list.item(r).text()
            if "(" in txt and txt.endswith(")"):
                code = txt[txt.rfind("(")+1:-1]
                # 오버레이 활성이면 제거
                if code in getattr(self, '_overlays', {}):
                    self._clear_all_overlays()
                # 체크박스 위젯 제거
                chk = self._overlay_chks.pop(code, None)
                if chk:
                    self._watch_overlay_layout.removeWidget(chk)
                    chk.deleteLater()
            self.watch_list.takeItem(r)
            self._save_watchlist()

    def _add_watch_item(self, code, name):
        """관심종목 리스트에 아이템 + 오버레이 체크박스 추가."""
        from PyQt5.QtWidgets import QCheckBox
        self.watch_list.addItem(f"{name}({code})")
        chk = QCheckBox(f"  {name}({code})")
        chk.setFixedHeight(20)
        chk.setStyleSheet(
            "QCheckBox{color:#00BFFF;font-size:10px;}"
            "QCheckBox::indicator{width:13px;height:13px;}"
            "QCheckBox::indicator:unchecked{border:1px solid #446688;"
            "background:#111122;border-radius:2px;}"
            "QCheckBox::indicator:checked{border:1px solid #00BFFF;"
            "background:#003366;border-radius:2px;}")
        chk.setToolTip(f"{name} 오버레이 ON/OFF (우측 Y축 라인차트)")
        chk.stateChanged.connect(
            lambda state, c=code, n=name:
                self._on_overlay_chk(c, n, state == 2))
        self._overlay_chks[code] = chk
        self._watch_overlay_layout.addWidget(chk)

    def _on_watch_click(self, item):
        txt = item.text()
        if "(" in txt and txt.endswith(")"):
            self.current_name = txt[:txt.rfind("(")]
            self.current_sym  = txt[txt.rfind("(")+1:-1]
            self.sym_in.setText(self.current_sym)
            self._on_calendar()

    # ── 종목코드 입력 변경 ────────────────────────────────────
    def _on_sym_changed(self):
        self.current_sym = self.sym_in.text().strip().zfill(6)

    # ── 날짜 직접 입력 (Alt+Enter) ───────────────────────────
    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Return and
                event.modifiers() == Qt.AltModifier):
            self._ask_date_input()
        else:
            super().keyPressEvent(event)

    def _ask_date_input(self):
        txt, ok = QInputDialog.getText(
            self, "날짜 입력",
            "날짜를 입력하세요 (YYYYMMDD 또는 YYYY-MM-DD):")
        if not ok or not txt.strip():
            return
        raw = txt.strip().replace("-", "")
        try:
            d = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except Exception:
            QMessageBox.warning(self, "형식 오류", "날짜 형식이 올바르지 않습니다.\n예) 20250418")
            return
        self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))
        self._on_calendar()

    # ── RT 버튼 ───────────────────────────────────────────────
    def _on_rt_btn(self, checked):
        if checked:
            if not self.kiwoom:
                self.status_lbl.setText("⚠ 키움 미연결 — 연결 버튼을 눌러주세요.")
                self.btn_rt.setChecked(False)
                return
            self._start_rt()
        else:
            self._stop_rt()

    def _start_rt(self):
        sym = self.sym_in.text().strip().zfill(6)
        self.current_sym = sym
        if self._kr_bar_timer:
            self._kr_bar_timer.stop()
        interval_ms = self.rt_interval_spin.value() * 1000
        self._kr_bar_timer = KrBarTimer(self, sym, interval_ms)
        self._kr_bar_timer.bar_updated.connect(self._on_rt_bar)
        self._kr_bar_timer.start()
        self.is_rt = True
        self.btn_rt.setStyleSheet(
            "background:#8b0000;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
        self.status_lbl.setText(f"🔴 실시간 {sym} ({interval_ms//1000}초 갱신)")

    def _stop_rt(self):
        if self._kr_bar_timer:
            self._kr_bar_timer.stop()
            self._kr_bar_timer = None
        self.is_rt = False
        self.btn_rt.setChecked(False)
        self.btn_rt.setStyleSheet(
            "background:#1a6b3c;color:#fff;font-weight:bold;padding:4px;border-radius:3px;")
        self.status_lbl.setText("상태: 대기")

    def _on_rt_bar(self, records):
        """KrBarTimer 에서 갱신된 레코드 리스트 수신."""
        if not records:
            return
        self.df_raw = records
        self._update_display()
        if PG:
            self.p1.autoRange()

    # ── Splitter 설정 저장/복원 ───────────────────────────────
    def _get_extra_settings(self) -> dict:
        d = {}
        try:
            d["h_split"]   = list(self._h_splitter.sizes())
            d["v_split"]   = list(self._v_splitter.sizes())
            d["tbl_split"] = list(self._tbl_splitter.sizes())
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        def _restore():
            try:
                if s.get("h_split"):   self._h_splitter.setSizes(s["h_split"])
                if s.get("v_split"):   self._v_splitter.setSizes(s["v_split"])
                if s.get("tbl_split"): self._tbl_splitter.setSizes(s["tbl_split"])
            except Exception:
                pass
        QTimer.singleShot(100, _restore)

    # ── UI 빌드 ──────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        self._h_splitter = QSplitter(Qt.Horizontal)
        self._h_splitter.setHandleWidth(5)
        self._h_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")

        from kr_build_side import build_sidebar
        from kr_build_main import build_tables, build_chart_area

        self._h_splitter.addWidget(build_sidebar(self))

        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.setHandleWidth(5)
        self._v_splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a4a;}"
            "QSplitter::handle:hover{background:#5dade2;}")
        self._v_splitter.addWidget(build_tables(self))
        self._v_splitter.addWidget(build_chart_area(self))
        self._v_splitter.setSizes([280, 520])

        self._h_splitter.addWidget(self._v_splitter)
        self._h_splitter.setSizes([255, 1200])
        root.addWidget(self._h_splitter)

    def _connect_kiwoom(self):
        """사이드바 연결 버튼 클릭 시 키움 API 초기화·로그인."""
        # 이미 연결된 인스턴스 재사용
        existing = getattr(self.mw, 'kiwoom', None)
        if existing is not None:
            self.kiwoom = existing
            self.status_lbl.setText("✅ 키움 이미 연결됨")
            self._update_connect_ui(True)
            return
        try:
            from pykiwoom.kiwoom import Kiwoom
            self.status_lbl.setText("🔄 키움 로그인 중…")
            kw = Kiwoom()
            kw.CommConnect(block=True)
            self.kiwoom = kw
            self.mw.kiwoom = kw   # 메인 윈도우에도 등록
            self.status_lbl.setText("✅ 키움 연결 완료")
            print("[KoreaChart] 키움 API 연결 완료")
            self._update_connect_ui(True)
        except ImportError:
            self.status_lbl.setText("⚠ pykiwoom 미설치 — pip install pykiwoom")
        except Exception as e:
            self.status_lbl.setText(f"⚠ 키움 연결 실패: {e}")
            print(f"[KoreaChart] 키움 연결 실패: {e}")

    def _update_connect_ui(self, connected: bool):
        """연결 상태에 따라 버튼 스타일 변경."""
        if hasattr(self, 'btn_kiwoom_connect'):
            if connected:
                self.btn_kiwoom_connect.setText("✅ 키움 연결됨")
                self.btn_kiwoom_connect.setStyleSheet(
                    "background:#1a3a1a;color:#44ff44;"
                    "border:1px solid #2a6a2a;border-radius:3px;"
                    "font-weight:bold;padding:4px;")
            else:
                self.btn_kiwoom_connect.setText("🔌 키움 연결")
                self.btn_kiwoom_connect.setStyleSheet(
                    "background:#1a1a3a;color:#8888ff;"
                    "border:1px solid #3a3a7a;border-radius:3px;"
                    "font-weight:bold;padding:4px;")

    def _clear_all_markers(self):
        """현재 종목의 .downloaded 마커 전체 삭제 → 재수집 유도."""
        import shutil
        code = self.sym_in.text().strip().zfill(6)
        marker_dir = KR_DATA_ROOT / code / ".downloaded"
        if marker_dir.exists():
            shutil.rmtree(str(marker_dir))
            self.status_lbl.setText(
                f"🗑 {code} 마커 초기화 완료 — 20일 조회로 재수집하세요.")
        else:
            self.status_lbl.setText(f"ℹ {code} 마커 없음")

    def _on_force_reload(self):
        tgt = self.calendar.selectedDate().toPyDate()
        sym = self.sym_in.text().strip().zfill(6)
        if not sym:
            QMessageBox.warning(self, "종목 없음", "종목코드를 입력하세요.")
            return
        self.status_lbl.setText(f"🔄 {sym} {tgt} 재다운로드 중…")
        self._force_redownload(sym, tgt)