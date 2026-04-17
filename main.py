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
  tab_account.py        ← Tab2 잔고PnL / Tab5 복수현재가 / Tab6 Greeks
  tab_chart.py          ← Tab7 1분봉 차트 (Polygon + IBKR)
  tab_trading.py        ← Tab9 주문/잔고
  tab_kr_futures.py     ← Tab10 한국선물옵션
  tab_combo_strategy.py ← Tab4 복합전략

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
════════════════════════════════════════════════════════════════
"""

import sys, threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import QShortcut

# ── 공통 코어 ─────────────────────────────────────────────────
from core import (
    IBapi, bridge, router, SignalBridge,
    TWS_HOST, TWS_PORT, CLIENT_ID,
    make_style, DEFAULT_FONT_SIZE,
    GridTab, TabWrapper, SAVE_DIR
)

# ── Greeks 폴더 경로 등록 (Main2/Greeks/) ────────────────────
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Greeks"))

# ── combo_libs 폴더 경로 등록 (Main2/combo_libs/) ───────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "combo_libs"))

# ── tab_chart_libs 폴더 경로 등록은 tab_chart.py 내부에서 처리 ──────
# (tab_chart.py 는 Main2/ 루트에 위치)

# ── 탭 모듈 ───────────────────────────────────────────────────
from call_put_tab import CallPutGrid, init_chain_saver
from watch_dog    import WatchAlertPanel   # SPX 감시 패널
from tab_sniper  import SniperGrid
from tab_oi      import OITrackerGrid
from tab_combo_strategy import ComboStrategyGrid
from tab_account import BalanceGrid, MultiPriceGrid
from tab_greeks  import GreeksGrid          # ← Main2/Greeks/tab_greeks.py
from tab_chart   import ChartGrid           # tab_chart_libs/ 경로는 tab_chart.py 내부 등록
from tab_trading import TradingGrid
from tab_kr_futures  import KRFuturesGrid
from tab_spx_history import SpxHistoryGrid
from tab_opt_intraday import OptIntradayGrid


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

        self._init_ui()
        self._init_timers()

    # ── UI 초기화 ────────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowTitle(
            "0DTE Master Dashboard  v6.5  │  Port 7496  │  "
            + datetime.today().strftime("%Y-%m-%d"))
        self.setGeometry(40, 40, 1700, 980)
        self.setStyleSheet(make_style(DEFAULT_FONT_SIZE))

        # 탭 위젯 (하단 탭)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.South)
        self.setCentralWidget(self.tabs)

        # 탭 생성 헬퍼 — tab_name을 TabWrapper에 전달해 설정 저장/복원에 사용
        def add(grid_cls, label, *args, **kwargs):
            grid    = grid_cls(*args, **kwargs)
            tab_name = label.split(".")[0].strip().replace(" ", "_")
            wrapper = TabWrapper(grid, tab_name=tab_name)
            self.tabs.addTab(wrapper, label)
            return grid

        # ── 탭 등록 ────────────────────────────────────────────
        self.tab_callput = add(CallPutGrid,   "1. 콜-풋 (Main)", self)
        init_chain_saver(self)   # ← chain_saver 초기화 (저장 스레드 + 스케줄러)
        self.tab_balance = add(BalanceGrid,   "2. 잔고/PnL",     self)
        self.tab_sniper  = add(SniperGrid,    "3. 스나이퍼",     self)
        self.tab_combo = add(ComboStrategyGrid, "4. 복합 전략",    self)
        add(MultiPriceGrid,                   "5. 복수 현재가",  self)
        self.tab_greeks  = add(GreeksGrid,    "6. Greeks Matrix",self)
        # ★ v6.6: Greeks Matrix → chain_saver 버퍼 연동
        # init_chain_saver 호출 시점엔 tab_greeks 미생성이므로 여기서 연결
        _buf = getattr(self, 'chain_buf', None)
        if _buf and hasattr(self.tab_greeks, 'attach_chain_buffer'):
            self.tab_greeks.attach_chain_buffer(_buf)
        add(ChartGrid,                        "7. 1분봉 차트",   self)
        add(OITrackerGrid,                    "8. OI 추적",      self)
        self.tab_trading = add(TradingGrid,   "9. 주문/잔고",    self)
        self.tab_kr      = add(KRFuturesGrid, "10. 한국선물옵션", self)
        self.tabs.addTab(SpxHistoryGrid(self),   "📜 SPX 히스토리")
        self.tabs.addTab(OptIntradayGrid(self),  "📊 옵션 분봉")

        # ── Ctrl+1~10 단축키 — 탭 전환 ────────────────────────
        for i in range(min(10, self.tabs.count())):
            key = f"Ctrl+{i+1}"
            sc  = QShortcut(QKeySequence(key), self)
            sc.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))

        # ── 탭 전환 시 비활성 탭 제어 ───────────────────────────
        # on_tab_activate() / on_tab_deactivate()를 구현한 탭만 호출됨
        self.tabs.currentChanged.connect(self._on_tab_changed)

    # ── 탭 전환 제어 ────────────────────────────────────────
    def _on_tab_changed(self, idx: int):
        """탭 전환 시 비활성 탭의 타이머/구독 일시 중단, 활성 탭 재개."""
        for i in range(self.tabs.count()):
            wrapper = self.tabs.widget(i)
            # TabWrapper 안의 실제 그리드 위젯 접근
            grid = getattr(wrapper, '_grid', wrapper)
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
        self.disconnect_ibkr()
        event.accept()


# ══════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("0DTE Master Dashboard  v6.5")
    print(f"저장 경로: {SAVE_DIR.resolve()}")
    print("=" * 60)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    default_font = QFont()
    default_font.setPointSize(10)
    app.setFont(default_font)

    win = TradingDashboard()
    win.app = app   # chain_saver worker 종료 연결용
    win.show()
    sys.exit(app.exec_())