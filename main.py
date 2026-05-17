"""
main.py — 0DTE Master Dashboard  v6.5  메인 진입점
════════════════════════════════════════════════════════════════
파일 구조:
  main.py               ← 메인 윈도우 + 탭 조립 + 실행
  core.py               ← 상수 / 브릿지 / TickRouter / IBKR 래퍼

  [탭1 콜-풋 — 위젯별 세분화]
  tab_options.py          메인 조립 (CallPutGrid, _build)
  tab_options_chart.py    차트 패널 UI + Tick 수신
  tab_options_settings.py 화면설정 저장/복원
  watch_cond_widget.py    감시조건+AND조건 패널 UI
  watch_log_widget.py     알람로그+사운드+등록목록 탭 UI
  watch_logic.py          감시 규칙 등록·평가·체크 로직
  order_panel.py          신규·정정·취소 탭 UI
  order_logic.py          주문 실행 로직
  core_conn.py            연결·MDT·SPXW·Zone·만기
  core_fetch.py           조회·기초자산·테이블클릭·관심종목

  [나머지 탭]
  tab_sniper.py         ← Tab3 스나이퍼 (SniperGrid)
  tab_oi.py             ← Tab8 OI 추적 (OITrackerGrid)
  tab_balance.py        ← Tab2 잔고/PnL (BalanceGrid) — Account_info/ 패키지 사용
  tab_multi_price.py    ← Tab5 복수현재가 (MultiPriceGrid) — Account_info/ 패키지 사용
  tab_greeks.py         ← Tab6 Greeks Matrix (GreeksGrid) — Account_info/ 패키지 사용
  tab_chart.py          ← Tab7 1분봉 차트 (Polygon + IBKR)
  tab_trading.py        ← Tab9 주문/잔고
  tab_kr_futures.py     ← Tab10 한국선물옵션
  tab_combo_strategy.py ← Tab4 복합전략

  [텔레그램 공통 모듈]
  telegram_bot/tg_config.py        ← 설정값 JSON 저장/로드 (싱글톤)
  telegram_bot/tg_client.py        ← 봇 싱글톤 (송신·polling·콜백)
  telegram_bot/tg_command_router.py← 수신 명령 → 각 탭 라우팅
  telegram_bot/tg_config_widget.py ← [📡 텔레그램] 탭 UI + 채팅창

실행:
  python main.py

필수 패키지:
  pip install PyQt5 pyqtgraph ibapi pandas requests websockets
════════════════════════════════════════════════════════════════
탭 목록:
  1  콜-풋 조회 (Main)
  2  잔고 / PnL
  3  스나이퍼 주문
  4  복합 전략
  5  복수 현재가
  6  Greeks Matrix
  7  1분봉 차트
  8  OI 추적
  9  주문/잔고
  10 한국선물옵션
  11 SPX 히스토리
  12 옵션 분봉 차트
  13 텔레그램 설정
════════════════════════════════════════════════════════════════
"""

# ── pyqtgraph / OpenGL Segfault 방지 ─────────────────────────
# QApplication 생성 전, 모든 import 전에 설정해야 효과 있음
import os
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

# ── fcitx 한글 입력기 연동 ────────────────────────────────────
os.environ.setdefault("QT_IM_MODULE",  "fcitx")
os.environ.setdefault("XMODIFIERS",    "@im=fcitx")
os.environ.setdefault("GTK_IM_MODULE", "fcitx")

import sys, threading
from datetime import datetime

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

# ══════════════════════════════════════════════════════════════
# ✅ 핵심 수정: QApplication을 탭 모듈 import 전에 먼저 생성
#    (어느 탭 모듈이든 import 시점에 QWidget을 생성하면 crash 발생)
# ══════════════════════════════════════════════════════════════
if not QApplication.instance():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _default_font = QFont()
    _default_font.setPointSize(10)
    app.setFont(_default_font)

# ── pyqtgraph는 QApplication 생성 후에 import ─────────────────
import pyqtgraph as pg
pg.setConfigOption('useOpenGL', False)
pg.setConfigOption('enableExperimental', False)
pg.setConfigOption('antialias', False)
# ─────────────────────────────────────────────────────────────

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QLabel, QMessageBox,
    QStatusBar, QHBoxLayout, QPushButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut

# ── 공통 코어 ─────────────────────────────────────────────────
from core import (
    IBapi, bridge, router, SignalBridge,
    TWS_HOST, TWS_PORT, CLIENT_ID,
    make_style, set_theme, make_theme_selector,
    THEME_ORDER, THEME_LABELS, CURRENT_THEME,
    DEFAULT_FONT_SIZE,
    GridTab, TabWrapper, SAVE_DIR
)
from core_ui import apply_theme_to_all_tables, apply_theme_to_all_frames
from main_config_theme import apply_light_fg_fix
apply_light_fg_fix()   # 라이트 모드 전경색 누락 버그 즉시 수정

# ── 공유 데이터 저장소 ─────────────────────────────────────────
from shared_chain_store   import SharedChainStore
from price_history_buffer import PriceHistoryBuffer

# ── Greeks 폴더 경로 등록 (Main2/Greeks/) ────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Greeks"))

# ── combo_libs 폴더 경로 등록 (Main2/combo_libs/) ───────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "combo_libs"))

# ── tab_chart_libs 폴더 경로 등록은 tab_chart.py 내부에서 처리 ──────
# (tab_chart.py 는 Main2/ 루트에 위치)

# ── korea_chart_tab 경로 등록 ────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "korea_chart_tab"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "korea_chart_tab", "kr_chart_libs"))

# ── 탭 모듈 ───────────────────────────────────────────────────
from call_put_tab import CallPutGrid, init_chain_saver
from watch_dog    import WatchAlertPanel   # SPX 감시 패널
from telegram_bot import TgConfigWidget    # 텔레그램 설정 탭
from telegram_bot.tg_client import TelegramClient
from tab_sniper  import SniperGrid
from tab_oi      import OITrackerGrid
from tab_combo_strategy import ComboStrategyGrid
from tab_balance      import BalanceGrid        # Account_info/ 패키지 사용
from tab_multi_price  import MultiPriceGrid     # Account_info/ 패키지 사용
from tab_greeks       import GreeksGrid         # Account_info/ 패키지 사용
from tab_chart   import ChartGrid           # tab_chart_libs/ 경로는 tab_chart.py 내부 등록
from tab_trading import TradingGrid
from tab_kr_futures  import KRFuturesGrid
from tab_spx_history import SpxHistoryGrid
from tab_opt_intraday import OptIntradayGrid
from kr_chart_tab import KoreaChartGrid       # ← Korea_1분 차트 탭


# ── spread_tele 경로 등록 (Main2/spread_tele/) ───────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "spread_tele"))

# ── strategy_report 패키지 (IBKR/MAIN2/strategy_report/) ────────────
# __file__ 이 상대경로일 때도 안전하게 Main2/ 절대경로를 확보
_MAIN2_DIR = os.path.dirname(os.path.abspath(os.path.join(os.getcwd(), __file__)))
if _MAIN2_DIR not in sys.path:
    sys.path.insert(0, _MAIN2_DIR)
from strategy_report.tab_report import ReportTab
from Main_config import ConfigTab, _get_heartbeat_mgr   # 기본 설정 탭


# ══════════════════════════════════════════════════════════════
# 빈 탭 (준비중)
# ══════════════════════════════════════════════════════════════
class EmptyGrid(GridTab):
    def __init__(self, title: str = "준비중"):
        super().__init__()
        lbl = QLabel(f"탭 준비중\n\n{title}")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color:#333;font-size:18px;border:none;")
        self.add(lbl, 1, 3, 2, 6)


# HistoryGrid 제거 — 복합 전략(ComboStrategyGrid)으로 대체


# ══════════════════════════════════════════════════════════════
# 메인 윈도우
# ══════════════════════════════════════════════════════════════
class _ChartGrabBridge(QObject):
    """백그라운드 스레드 → 메인스레드로 grab 요청을 전달하는 시그널 브릿지."""
    request = pyqtSignal()


class TradingDashboard(QMainWindow):
    """
    0DTE Master Dashboard v6.1 메인 윈도우.
    - 하단 탭 10개 (QTabWidget.South)
    - 전역 IBKR 연결/해제 관리
    - TickRouter 로 탭 간 tick 간섭 차단
    """

    def __init__(self):
        super().__init__()
        self.ib        = IBapi()
        self.ib_thread = None
        self.connected = False
        self.account_id = ""   # ← managedAccounts 콜백에서 자동 설정

        # 탭 인스턴스 (다른 탭에서 참조 가능하도록 속성으로 저장)
        self.tab_callput  = None
        self.tab_balance  = None
        self.tab_sniper   = None
        self.tab_greeks   = None
        self.tab_report   = None
        self.tab_telegram = None   # 텔레그램 설정 탭
        self.tab_kr_chart = None   # Korea_1분 차트 탭
        self.tab_config   = None   # 기본 설정 탭

        # ── 공유 데이터 저장소 ──────────────────────────────────
        self.chain_store   = SharedChainStore()    # 탭 간 옵션 체인 공유
        self.price_history = PriceHistoryBuffer()  # 기초자산 N분 전 가격 추적

        # 텔레그램 차트 grab 용 시그널 브릿지 (백그라운드→메인스레드)
        self._chart_grab_bridge = _ChartGrabBridge()

        self._init_ui()
        self._init_timers()

    # ── UI 초기화 ────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(
            "0DTE Master Dashboard  v6.5  │  Port 7496  │  "
            + datetime.today().strftime("%Y-%m-%d"))
        self.setGeometry(40, 40, 1700, 980)
        self.setStyleSheet(make_style(DEFAULT_FONT_SIZE))

        # ── 테마 선택 버튼 (상단 메뉴바 우측) ─────────────────────
        self._theme_bar = QWidget()
        _tbar_layout = QHBoxLayout(self._theme_bar)
        _tbar_layout.setContentsMargins(4, 2, 8, 2)
        _tbar_layout.setSpacing(4)

        _tbar_layout.addStretch()

        _lbl_theme = QLabel("테마:")
        _lbl_theme.setStyleSheet("font-size:13px; font-weight:bold; border:none;")
        _tbar_layout.addWidget(_lbl_theme)

        self._theme_btn_group = QButtonGroup(self._theme_bar)
        self._theme_btn_group.setExclusive(True)
        self._theme_buttons = {}

        import core as _core  # 런타임 참조용

        def _apply_theme(theme_name):
            set_theme(theme_name)
            self.setStyleSheet(make_style(DEFAULT_FONT_SIZE))

            # ── ① 전체 QTableWidget / _ResizableFrame 일괄 갱신 ──
            apply_theme_to_all_tables()
            apply_theme_to_all_frames()

            # ── ② combo 모듈 스타일 상수 갱신 ────────────────────
            try:
                import combo_constants as _cc
                import combo_ui_panel_constants as _cp
                _cc.SPLITTER_STYLE = _cc.get_splitter_style()
                _cc.TBL_STYLE      = _cc.get_tbl_style()
                _cp._TAB_STYLE     = _cp.get_tab_style()
                _cp._TBL_STYLE     = _cp.get_tbl_style()
            except Exception as _e:
                print(f"[Theme] combo 스타일 갱신 실패 (무시): {_e}")

            # ── ③ 콜-풋 탭 (tab_callput) ─────────────────────────
            try:
                cp = getattr(self, 'tab_callput', None)
                if cp:
                    # QSS 직접 재적용 (테이블, 패널, 스플리터 등)
                    if hasattr(cp, 'refresh_theme'):
                        cp.refresh_theme()
                    else:
                        cp.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
                    # 체인 테이블 셀 색상 재적용
                    for _tbl_attr in ('tbl_call', 'tbl_put', 'tbl_watch'):
                        _tbl = getattr(cp, _tbl_attr, None)
                        if _tbl:
                            from core_ui import _apply_table_theme
                            _apply_table_theme(_tbl)
            except Exception as _e:
                print(f"[Theme] CallPut 갱신 실패 (무시): {_e}")

            # ── ④ 잔고/PnL 탭 (tab_balance) ──────────────────────
            try:
                bal = getattr(self, 'tab_balance', None)
                if bal:
                    if hasattr(bal, 'refresh_theme'):
                        bal.refresh_theme()
                    else:
                        bal.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
                    # 잔고 테이블들 재적용
                    for _tbl_attr in ('tbl_positions', 'tbl_orders',
                                      'tbl_balance', 'tbl_pnl', 'tbl_trades'):
                        _tbl = getattr(bal, _tbl_attr, None)
                        if _tbl:
                            from core_ui import _apply_table_theme
                            _apply_table_theme(_tbl)
            except Exception as _e:
                print(f"[Theme] Balance 갱신 실패 (무시): {_e}")

            # ── ⑤ Greeks Matrix 탭 (tab_greeks) ──────────────────
            try:
                grk = getattr(self, 'tab_greeks', None)
                if grk:
                    if hasattr(grk, 'refresh_theme'):
                        grk.refresh_theme()
                    else:
                        grk.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
            except Exception as _e:
                print(f"[Theme] Greeks 갱신 실패 (무시): {_e}")

            # ── ⑥ 스나이퍼 탭 (tab_sniper) ───────────────────────
            try:
                snp = getattr(self, 'tab_sniper', None)
                if snp:
                    if hasattr(snp, 'refresh_theme'):
                        snp.refresh_theme()
                    else:
                        snp.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
            except Exception as _e:
                print(f"[Theme] Sniper 갱신 실패 (무시): {_e}")

            # ── ⑦ 복합 전략 탭 (tab_combo) ───────────────────────
            try:
                tab_combo = getattr(self, 'tab_combo', None)
                if tab_combo:
                    if hasattr(tab_combo, 'refresh_theme'):
                        tab_combo.refresh_theme()
                    else:
                        tab_combo.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
                    # SyntheticStatusPanel 갱신
                    sp = getattr(tab_combo, '_synthetic_panel', None)
                    if sp and hasattr(sp, 'refresh_theme'):
                        sp.refresh_theme()
                    # 방향 배너 갱신
                    db = getattr(tab_combo, 'direction_banner', None)
                    if db:
                        if hasattr(db, 'tbl_legs'):
                            db.refresh(tab_combo.tbl_legs)
                        elif hasattr(db, '_apply'):
                            db._apply("none",
                                      "━  레그를 설정하면 방향을 표시합니다  ━",
                                      "C/P · 행사가 · BUY/SELL 조합으로 자동 판단", "")
            except Exception as _e:
                print(f"[Theme] Combo 갱신 실패 (무시): {_e}")

            # ── ⑧ 리포트 탭 (tab_report) ─────────────────────────
            try:
                rep = getattr(self, 'tab_report', None)
                if rep:
                    if hasattr(rep, 'refresh_theme'):
                        rep.refresh_theme()
                    else:
                        rep.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
            except Exception as _e:
                print(f"[Theme] Report 갱신 실패 (무시): {_e}")

            # ── ⑨ 설정 탭 (tab_config) ───────────────────────────
            try:
                cfg = getattr(self, 'tab_config', None)
                if cfg:
                    if hasattr(cfg, 'refresh_theme'):
                        cfg.refresh_theme()
                    else:
                        cfg.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
                    # ThemeConfigPanel 버튼 동기화
                    tcp = getattr(cfg, 'theme_panel', None)
                    if tcp and hasattr(tcp, 'sync_preset_buttons'):
                        tcp.sync_preset_buttons(theme_name)
            except Exception as _e:
                print(f"[Theme] Config 갱신 실패 (무시): {_e}")

            # ── ⑩ 나머지 탭 (TabWidget 전체 순회) ───────────────
            # 위에서 처리 못한 탭까지 setStyleSheet 로 폴백 적용
            try:
                for _i in range(self.tabs.count()):
                    _w = self.tabs.widget(_i)
                    # TabWrapper 안의 실제 그리드 접근
                    _grid = getattr(_w, 'grid_tab', getattr(_w, '_grid', _w))
                    if hasattr(_grid, 'refresh_theme'):
                        _grid.refresh_theme()
                    elif _grid is not None:
                        _grid.setStyleSheet(make_style(DEFAULT_FONT_SIZE))
            except Exception as _e:
                print(f"[Theme] 탭 순회 갱신 실패 (무시): {_e}")

            # ── ⑪ 버튼 체크 상태 동기화 ─────────────────────────
            for k, b in self._theme_buttons.items():
                b.setChecked(k == theme_name)

            print(f"[Theme] 전체 갱신 완료 → {theme_name}")

        for _key in THEME_ORDER:
            _btn = QPushButton(THEME_LABELS[_key], self._theme_bar)
            _btn.setCheckable(True)
            _btn.setChecked(_key == _core.CURRENT_THEME)
            _btn.setFixedHeight(24)
            _btn.setMinimumWidth(80)
            _btn.setStyleSheet(
                "QPushButton { font-size: 12px; border-radius: 3px; padding: 2px 8px; }"
                "QPushButton:checked { font-weight: bold; border: 2px solid #4da6ff; }"
            )
            _btn.clicked.connect(lambda _, k=_key: _apply_theme(k))
            self._theme_btn_group.addButton(_btn)
            _tbar_layout.addWidget(_btn)
            self._theme_buttons[_key] = _btn

        # 메뉴바에 테마 바 삽입
        self.menuBar().setCornerWidget(self._theme_bar, Qt.TopRightCorner)
        self.menuBar().setFixedHeight(32)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.South)
        self.setCentralWidget(self.tabs)

        def add(grid_cls, label, *args, **kwargs):
            grid     = grid_cls(*args, **kwargs)
            tab_name = label.split(".")[0].strip().replace(" ", "_")
            wrapper  = TabWrapper(grid, tab_name=tab_name)
            self.tabs.addTab(wrapper, label)
            return grid

        # ── 탭 등록 ────────────────────────────────────────────
        self.tab_callput = add(CallPutGrid,        "1. 콜-풋 (Main)", self)
        init_chain_saver(self)
        self.tab_balance = add(BalanceGrid,        "2. 잔고/PnL",     self)
        self.tab_combo   = add(ComboStrategyGrid,  "4. 복합 전략",    self)
        self.tab_greeks  = add(GreeksGrid,         "6. Greeks Matrix",self)
        _buf = getattr(self, 'chain_buf', None)
        if _buf and hasattr(self.tab_greeks, 'attach_chain_buffer'):
            self.tab_greeks.attach_chain_buffer(_buf)
        # ✅ 2단계: SharedChainStore → Greeks탭 연동 (reqMktData 400개 제거)
        if hasattr(self.tab_greeks, 'attach_chain_store'):
            self.tab_greeks.attach_chain_store(self.chain_store)
        add(ChartGrid,                             "7. 1분봉 차트",   self)
        add(OITrackerGrid,                         "8. OI 추적",      self)
        self.tab_kr_chart = add(KoreaChartGrid,    "Korea_1분",  self)

        self.tab_report   = ReportTab(self)
        self.tabs.addTab(self.tab_report, "📋 리포트")

        self.tab_telegram = TgConfigWidget()
        self.tabs.addTab(self.tab_telegram, "📡 텔레그램")

        # ── 기본 설정 탭 ──────────────────────────────────────
        self.tab_config = ConfigTab()
        self.tabs.addTab(self.tab_config, "⚙️ 설정")
        # 설정 변경 시그널 연결
        self.tab_config.chain_save_interval_changed.connect(
            self._on_chain_save_interval_changed)
        self.tab_config.chain_initial_count_changed.connect(
            self._on_chain_initial_count_changed)
        self.tab_config.atm_range_changed.connect(
            self._on_atm_range_changed)
        self.tab_config.chain_columns_changed.connect(
            self._on_chain_columns_changed)
        # ── CallPutGrid 참조 주입 (컬럼 즉시 반영용) ─────────
        # tab_callput 이 이미 생성된 후이므로 바로 주입 가능
        self.tab_config.attach_callput(self.tab_callput)

        # ── 테마 패널은 Main_config.py 슬라이딩 패널에서 직접 관리 ──
        # ConfigTab._build_theme_panel() 이 ThemeConfigPanel 을 생성하므로
        # 여기서는 apply_callback 만 주입하고 sync 참조만 저장한다.
        try:
            _tcp = getattr(self.tab_config, '_theme_config_panel', None)
            if _tcp is not None:
                _tcp._callback = _apply_theme   # 콜백 교체
                self.tab_config.theme_panel = _tcp
                print("[Theme] 슬라이딩 ThemeConfigPanel 콜백 연결 완료")
        except Exception as _e:
            print(f"[Theme] 슬라이딩 패널 콜백 연결 실패 (무시): {_e}")

        # ── Heartbeat: dashboard 참조 주입 → IBKR 연결 시 자동 시작
        _get_heartbeat_mgr().attach_dashboard(self)

        # 텔레그램 정보 핸들러 등록
        self._register_tg_info_handler()

        # 단축키 Ctrl+1~10
        for i in range(min(10, self.tabs.count())):
            sc = QShortcut(QKeySequence("Ctrl+" + str(i + 1)), self)
            sc.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _register_tg_info_handler(self):
        """텔레그램 '정보' 번호 선택 시 데이터 수집 후 전송하는 핸들러 등록."""
        from telegram_bot.tg_command_router import TgCommandRouter
        from telegram_bot.tg_client import TelegramClient

        call_put = self.tab_callput

        import threading as _th

        # ── 브릿지 슬롯: 메인스레드에서 grab 후 백그라운드로 전송 ──
        def _on_grab_requested():
            """메인스레드에서 실행됨 (QueuedConnection 보장)."""
            try:
                img = call_put.grab_chart_image()
                bar_type = getattr(call_put, 'combo_bar', None)
                bar_text = bar_type.currentText() if bar_type else "1분"
            except Exception as e:
                img = b""
                bar_text = "1분"
            _th.Thread(target=_do_send, args=(img, bar_text), daemon=True).start()

        def _do_send(img, bar_text):
            """백그라운드 스레드에서 HTTP 전송."""
            client = TelegramClient.get()
            if img:
                ok = client._send_photo_raw(img, "📊 실시간 " + bar_text + " 캔들차트")
                if not ok:
                    client._send_raw("⚠️ 차트 전송 실패")
            else:
                client._send_raw("⚠️ 차트 캡처 실패 (차트 데이터 없음)")

        # 브릿지에 슬롯 연결 (QueuedConnection → 항상 메인스레드에서 실행)
        self._chart_grab_bridge.request.connect(
            _on_grab_requested, Qt.QueuedConnection)

        def _handle_info(item_no, chat_id):
            """백그라운드 스레드에서 호출."""
            client = TelegramClient.get()

            # ── 1번: 실시간 캔들 차트 ───────────────────────────
            if item_no == 1:
                if call_put is None:
                    client._send_raw("⚠️ 차트 탭을 찾을 수 없습니다.")
                    return
                # 시그널 emit → QueuedConnection → 메인스레드 _on_grab_requested 실행
                self._chart_grab_bridge.request.emit()

            # ── 2번: 옵션 체인 ATM ──────────────────────────────
            elif item_no == 2:
                try:
                    from core import REQ_CALL, REQ_PUT
                    und     = getattr(call_put, 'und_price', None)
                    strikes = getattr(call_put, 'call_strikes', [])
                    cdata   = getattr(call_put, 'call_data', {})
                    pdata   = getattr(call_put, 'put_data',  {})
                    if not strikes or und is None:
                        client._send_raw("⚠️ 옵션 체인 미조회 상태입니다.")
                        return
                    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - und))
                    rows = []
                    for i in range(max(0, atm - 2), min(len(strikes), atm + 3)):
                        c_last = cdata.get(REQ_CALL + i, {}).get('last', '―')
                        p_last = pdata.get(REQ_PUT  + i, {}).get('last', '―')
                        mark   = " <ATM" if i == atm else ""
                        cl = "{:.2f}".format(c_last) if isinstance(c_last, float) else str(c_last)
                        pl = "{:.2f}".format(p_last) if isinstance(p_last, float) else str(p_last)
                        rows.append("C {:>7} | {:>5} | {:<7} P{}".format(
                            cl, int(strikes[i]), pl, mark))
                    header = "📋 옵션체인 ATM  SPX {:,.2f}\n콜       | 행사가 | 풋\n".format(und)
                    client._send_raw(header + "\n".join(rows))
                except Exception as e:
                    client._send_raw("⚠️ ATM 조회 오류: " + str(e))

            # ── 3번: 옵션 체인 OTM ──────────────────────────────
            elif item_no == 3:
                try:
                    from core import REQ_CALL, REQ_PUT
                    und     = getattr(call_put, 'und_price', None)
                    strikes = getattr(call_put, 'call_strikes', [])
                    cdata   = getattr(call_put, 'call_data', {})
                    pdata   = getattr(call_put, 'put_data',  {})
                    if not strikes or und is None:
                        client._send_raw("⚠️ 옵션 체인 미조회 상태입니다.")
                        return
                    atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - und))
                    rows = []
                    for off in range(1, 6):
                        ci = atm + off
                        pi = atm - off
                        if ci >= len(strikes) or pi < 0:
                            break
                        cl = cdata.get(REQ_CALL + ci, {}).get('last', '―')
                        pl = pdata.get(REQ_PUT  + pi, {}).get('last', '―')
                        cl = "{:.2f}".format(cl) if isinstance(cl, float) else str(cl)
                        pl = "{:.2f}".format(pl) if isinstance(pl, float) else str(pl)
                        rows.append("C OTM {:>7} | +{} / -{} | {:<7} P OTM".format(cl, off, off, pl))
                    header = "📋 옵션체인 OTM  SPX {:,.2f}\n콜 OTM  | 거리 | 풋 OTM\n".format(und)
                    client._send_raw(header + "\n".join(rows))
                except Exception as e:
                    client._send_raw("⚠️ OTM 조회 오류: " + str(e))

            # ── 4번: 잔고 ───────────────────────────────────────
            elif item_no == 4:
                try:
                    bal = self.tab_balance
                    if bal is None:
                        client._send_raw("⚠️ 잔고 탭 로딩 중입니다. 잠시 후 다시 시도해주세요.")
                        return
                    lines_out = ["💰 잔고 요약"]
                    for attr_name in ('lbl_netliq', 'lbl_cash', 'lbl_unrealized', 'lbl_realized'):
                        w = getattr(bal, attr_name, None)
                        if w:
                            lines_out.append(attr_name.replace('lbl_', '').upper() + ": " + w.text())
                    msg = "\n".join(lines_out) if len(lines_out) > 1 else "⚠️ 잔고 데이터를 읽을 수 없습니다."
                    client._send_raw(msg)
                except Exception as e:
                    client._send_raw("⚠️ 잔고 조회 오류: " + str(e))

            # ── 5번: 현재 선물 지수 (/ES) ───────────────────────
            elif item_no == 5:
                und    = getattr(call_put, 'und_price', None)
                is_fut = getattr(call_put, '_und_is_futures', False)
                if und is None:
                    client._send_raw("⚠️ 선물 지수 미수신 (IBKR 연결 확인)")
                elif not is_fut:
                    client._send_raw("ℹ️ 현재 장중 — 현물 SPX 사용 중\nSPX: {:,.2f}".format(und))
                else:
                    prev = getattr(call_put, 'und_prev', None)
                    if prev and prev > 0:
                        chg  = und - prev
                        pct  = chg / prev * 100
                        sign = "+" if chg >= 0 else ""
                        client._send_raw(
                            "📈 /ES 선물 지수\n현재가: {:,.2f}\n등락: {}{:,.2f} ({}{}%)".format(
                                und, sign, chg, sign, round(pct, 2)))
                    else:
                        client._send_raw("📈 /ES 선물 지수\n현재가: {:,.2f}".format(und))

            # ── 6번: 실시간 현물 지수 (SPX) ─────────────────────
            elif item_no == 6:
                und    = getattr(call_put, 'und_price', None)
                is_fut = getattr(call_put, '_und_is_futures', False)
                if und is None:
                    client._send_raw("⚠️ 현물 지수 미수신 (장외 또는 IBKR 연결 확인)")
                elif is_fut:
                    client._send_raw(
                        "ℹ️ 현재 장외 — /ES 선물 구독 중\n/ES: {:,.2f} (현물 SPX 아님)".format(und))
                else:
                    prev = getattr(call_put, 'und_prev', None)
                    if prev and prev > 0:
                        chg  = und - prev
                        pct  = chg / prev * 100
                        sign = "+" if chg >= 0 else ""
                        client._send_raw(
                            "📊 SPX 현물 지수\n현재가: {:,.2f}\n등락: {}{:,.2f} ({}{}%)".format(
                                und, sign, chg, sign, round(pct, 2)))
                    else:
                        client._send_raw("📊 SPX 현물 지수\n현재가: {:,.2f}".format(und))

            # ── 7번: 스프레드 조회 (콜/풋 선택) ─────────────────
            elif item_no == 7:
                try:
                    from spread_tele.spread_config import CB_CALL, CB_PUT, CB_CANCEL
                    client._send_inline_keyboard(
                        "스프레드 종류를 선택하세요:",
                        [
                            [
                                {"text": "📈 콜 스프레드", "callback_data": CB_CALL},
                                {"text": "📉 풋 스프레드", "callback_data": CB_PUT},
                            ],
                            [{"text": "❌ 취소", "callback_data": CB_CANCEL}],
                        ]
                    )
                except Exception as e:
                    client._send_raw(f"⚠️ 스프레드 모듈 오류: {e}")

            else:
                client._send_raw("⚠️ 알 수 없는 번호입니다. (1~7)")

        TgCommandRouter().register_info_handler(_handle_info)

        # ── spread_tele 탭 참조 주입 ────────────────────────────
        try:
            from spread_tele.spread_tele_bot import set_tab as spread_set_tab
            spread_set_tab(call_put)
            print("[spread_tele] 탭 참조 주입 완료")
        except Exception as e:
            print(f"[spread_tele] 탭 참조 주입 실패: {e}")


    # ── 설정 탭 시그널 핸들러 ───────────────────────────────────
    def _on_chain_save_interval_changed(self, sec: int):
        """기초자산 저장 주기 변경 → chain_saver 에 반영."""
        try:
            from call_put_tab.chain_saver import set_save_interval
            set_save_interval(sec)
        except Exception as e:
            print(f"[Config] 저장 주기 반영 실패 (chain_saver): {e}")

    def _on_chain_initial_count_changed(self, count: int):
        """체인 초기 조회 갯수 변경 — 다음 조회 시 자동 반영 (config_store 경유)."""
        print(f"[Config] 체인 초기 조회 갯수: {count}개 (다음 조회 시 반영)")

    def _on_atm_range_changed(self, above: int, below: int):
        """ATM 범위 변경 — 다음 조회 시 자동 반영 (config_store 경유)."""
        print(f"[Config] ATM 범위 변경: 위+{above}, 아래+{below} (다음 조회 시 반영)")

    def _on_chain_columns_changed(self, columns: list):
        """체인 컬럼 변경 → 콜-풋 탭 갱신 시도."""
        print(f"[Config] 체인 컬럼 변경: {columns}")
        try:
            if self.tab_callput and hasattr(self.tab_callput, '_refresh_chain_columns'):
                self.tab_callput._refresh_chain_columns(columns)
        except Exception as e:
            print(f"[Config] 체인 컬럼 반영 실패: {e}")

    # ── 탭 전환 제어 ────────────────────────────────────────
    def _on_tab_changed(self, idx: int):
        """탭 전환 시 비활성 탭의 타이머/구독 일시 중단, 활성 탭 재개."""
        for i in range(self.tabs.count()):
            wrapper = self.tabs.widget(i)
            # TabWrapper 안의 실제 그리드 위젯 접근
            grid = getattr(wrapper, 'grid_tab', getattr(wrapper, '_grid', wrapper))
            if i == idx:
                if hasattr(grid, 'on_tab_activate'):
                    try: grid.on_tab_activate()
                    except Exception as e:
                        print(f"[TabChange] activate tab {i} error: {e}")
            else:
                if hasattr(grid, 'on_tab_deactivate'):
                    try: grid.on_tab_deactivate()
                    except Exception as e:
                        print(f"[TabChange] deactivate tab {i} error: {e}")

    # ── 타이머 ──────────────────────────────────────────────────
    def _init_timers(self):
        # 연결 상태 감시 (2초)
        self._conn_timer = QTimer(self)
        self._conn_timer.timeout.connect(self._check_conn)
        self._conn_timer.start(2000)

        # 앱 시작 2초 후 자동 연결 (1회성)
        QTimer.singleShot(2000, self._auto_connect)

        # 앱 시작 3초 후 price_history 복원 (greeks_db → 과거 60분치)
        QTimer.singleShot(3000, self._restore_price_history)

        # 텔레그램 polling 시작 (백그라운드 스레드, daemon)
        TelegramClient.get().start_polling()

    def _restore_price_history(self):
        """앱 시작 3초 후 greeks_db에서 과거 60분치 und_price 복원.
        장중 재시작 시 AlertEngine이 즉시 N분 전 가격을 쓸 수 있게 함.
        """
        try:
            from greeks_db import load_und_price_history
            rows = load_und_price_history(minutes=60)
            if rows:
                self.price_history.restore_from_db(rows)
                print(f"[Dashboard] price_history 복원 완료: {self.price_history.size()}분치")
        except Exception as e:
            print(f"[Dashboard] price_history 복원 실패 (무시): {e}")

    def _auto_connect(self):
        """앱 시작 2초 후 자동으로 TWS 연결 시도 (팝업 없이)."""
        if not self.connected:
            self.connect_ibkr(silent=True)

    # ── IBKR 연결 / 해제 ────────────────────────────────────────
    def connect_ibkr(self, silent: bool = False):
        """TWS 연결.
        silent=True: 자동 연결 시 — ibapi 미설치/실패 팝업 없이 조용히 처리.
        """
        from core import IBAPI_AVAILABLE
        if not IBAPI_AVAILABLE:
            if not silent:
                QMessageBox.critical(self, "ibapi 미설치",
                    "pip install ibapi\n"
                    "또는 TWS API 패키지 설치:\n"
                    "  source/pythonclient → python setup.py install")
            return
        if self.connected:
            return
        try:
            self.ib = IBapi()
            self.ib.connect(TWS_HOST, TWS_PORT, CLIENT_ID)

            # ── 계좌번호 자동 저장 (managedAccounts 콜백) ──────────
            _mw = self
            _orig_managed = getattr(self.ib, 'managedAccounts', lambda accts: None)
            def _on_managed_accounts(accountsList: str):
                try: _orig_managed(accountsList)
                except Exception: pass
                if accountsList:
                    acct = accountsList.strip().split(',')[0].strip()
                    if acct:
                        _mw.account_id = acct
                        print(f"[Dashboard] account_id 설정: {acct}")
            self.ib.managedAccounts = _on_managed_accounts

            self.ib_thread = threading.Thread(target=self.ib.run, daemon=True)
            self.ib_thread.start()
        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "연결 실패", str(e))

    def disconnect_ibkr(self):
        try:
            if self.connected and self.ib:
                self.ib.disconnect()
                self.connected = False
                if self.tab_callput:
                    self.tab_callput.lbl_status.setText("● 미연결")
                    self.tab_callput.lbl_status.setStyleSheet(
                        "color:#ff4444;font-weight:bold;border:none;")
        except Exception as e:
            print(f"[Dashboard] 연결 해제 오류: {e}")

    def _check_conn(self):
        from core import IBAPI_AVAILABLE
        if not IBAPI_AVAILABLE or not self.ib:
            return
        try:
            prev = self.connected
            self.connected = self.ib.isConnected()
            if prev and not self.connected:
                if self.tab_callput:
                    self.tab_callput.lbl_status.setText("● 끊김")
                    self.tab_callput.lbl_status.setStyleSheet(
                        "color:#ff8800;font-weight:bold;border:none;")
        except:
            
            pass

    def closeEvent(self, event):
        TelegramClient.get().stop_polling()   # 텔레그램 수신 루프 종료
        # ✅ 수정: 종료 시 관심종목 명시적 저장
        # _w_save()는 CoreFetchWatchlistMixin에 정의됨
        try:
            if self.tab_callput and hasattr(self.tab_callput, '_w_save'):
                self.tab_callput._w_save()
        except Exception as e:
            print(f"[closeEvent] 관심종목 저장 실패 (무시): {e}")
        self.disconnect_ibkr()
        event.accept()


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("0DTE Master Dashboard  v")
    print(f"저장 경로: {SAVE_DIR.resolve()}")
    print("=" * 60)

    # ✅ 이미 모듈 최상단에서 생성된 QApplication 인스턴스를 재사용
    app = QApplication.instance()

    win = TradingDashboard()
    win.app = app   # chain_saver worker 종료 연결용
    win.show()
    sys.exit(app.exec_())