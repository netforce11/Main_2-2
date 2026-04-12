"""
core.py — 공통 상수 / 시그널 브릿지 / IBKR 래퍼 / 헬퍼 함수
════════════════════════════════════════════════════════════════
모든 탭 모듈이 이 파일에서 import 합니다.
변경 사항: 설정 상수, reqId 범위, 종목 파라미터, 스타일
"""

import os, json, csv
from datetime import datetime, timedelta, time as dt_time, date as dt_date
from pathlib import Path
try:
    from zoneinfo import ZoneInfo          # Python 3.9+
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo   # pip install backports.zoneinfo
    except ImportError:
        # 최후 fallback: pytz 사용
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

# ── ibapi ─────────────────────────────────────────────────────
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    from ibapi.order import Order
    IBAPI_AVAILABLE = True
except ModuleNotFoundError:
    IBAPI_AVAILABLE = False
    print("[경고] ibapi 미설치 → pip install ibapi")

# ── pyqtgraph ─────────────────────────────────────────────────
try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QPushButton, QSlider, QSizeGrip, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QSize
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor, QBrush

# ══════════════════════════════════════════════════════════════
# 1. 전역 설정 상수
# ══════════════════════════════════════════════════════════════
TWS_HOST   = "127.0.0.1"
TWS_PORT   = 4001
CLIENT_ID  = 1
SAVE_DIR   = Path("data")          # 저장 디렉터리
SAVE_DIR.mkdir(exist_ok=True)

DEFAULT_FONT_SIZE  = 16
ALERT_COOLDOWN     = 600           # 추적기 재알림 쿨다운 (초)
N_STRIKES          = 30            # 콜/풋 테이블 최대 행 수 (SpinBox로 실제 사용 수 조절)
GREEKS_MATRIX_N    = 20            # Greeks Matrix ATM 기준 상하 개수
GREEKS_AUTOSAVE_S  = 15            # Greeks 자동저장 주기 (초)

# ── reqId 범위 (겹치지 않게 100 단위로 구분) ──────────────────
REQ_UND       = 1          # 기초자산 현재가
REQ_CALL      = 1000       # 콜 옵션 1000~1099
REQ_PUT       = 2000       # 풋 옵션 2000~2099
REQ_MULTI     = 3000       # 복수현재가 3000~3299 (슬롯당 100)
REQ_CHAIN     = 4000       # Greeks Matrix 콜 4000~4199
REQ_CHAIN_P   = 4200       # Greeks Matrix 풋 4200~4399
REQ_OI        = 5000       # OI 조회 5000~5499
REQ_HIST      = 6000       # IBKR 히스토리 6000~6099
REQ_SNIPER    = 7000       # 스나이퍼 시세 7000~7499
REQ_ACCT      = 9001

# ── 종목 파라미터 ─────────────────────────────────────────────
# symbol → (secType, exchange, multiplier, strike_step)
SYMBOL_CFG = {
    # symbol → (secType, exchange, multiplier, strike_step)
    # exchange는 reqMktData 기준 → 인덱스/주식 옵션 모두 SMART
    # tradingClass는 make_opt_contract에서 별도 설정
    "SPX":   ("OPT", "SMART", "100",  5),
    "SPXW":  ("OPT", "SMART", "100",  5),
    "NDX":   ("OPT", "SMART", "100", 25),
    "RUT":   ("OPT", "SMART", "100",  5),
    "VIX":   ("OPT", "SMART", "100",  1),
    "XSP":   ("OPT", "SMART", "100",  1),
    "AAPL":  ("OPT", "SMART", "100",  1),
    "TSLA":  ("OPT", "SMART", "100",  2),
    "NVDA":  ("OPT", "SMART", "100",  2),
    "AMZN":  ("OPT", "SMART", "100",  2),
    "MSFT":  ("OPT", "SMART", "100",  2),
    "META":  ("OPT", "SMART", "100",  2),
    "GOOG":  ("OPT", "SMART", "100",  2),
    "GOOGL": ("OPT", "SMART", "100",  2),
    "QQQ":   ("OPT", "SMART", "100",  1),
    "SPY":   ("OPT", "SMART", "100",  1),
    "IWM":   ("OPT", "SMART", "100",  1),
}
DEFAULT_CFG  = ("OPT", "SMART", "100", 1)
INDEX_SYM    = {"SPX","SPXW","NDX","RUT","VIX","DJX","XSP"}

ACCT_TAGS = ("NetLiquidation,TotalCashValue,BuyingPower,"
             "UnrealizedPnL,RealizedPnL,GrossPositionValue,"
             "MaintMarginReq,InitMarginReq")

# ══════════════════════════════════════════════════════════════
# 2. 스타일
# ══════════════════════════════════════════════════════════════
BASE_STYLE = """
QMainWindow,QDialog{{background:#0e0e1a;}}
QWidget{{background:#0e0e1a;color:#dde0f0;font-size:{fs}px;}}
QGroupBox{{border:1px solid #2e3060;border-radius:5px;
           margin-top:10px;padding-top:6px;font-weight:bold;}}
QGroupBox::title{{subcontrol-origin:margin;left:8px;color:#5dade2;}}
QPushButton{{background:#1c1c3a;color:#dde0f0;border:1px solid #3a3a7a;
             border-radius:4px;padding:4px 10px;font-size:{fs}px;}}
QPushButton:hover{{background:#2a2a5a;}}
QPushButton:pressed{{background:#0e0e2a;}}
QLineEdit,QComboBox,QSpinBox{{background:#0a0a18;border:1px solid #2e3060;
              border-radius:4px;padding:3px;color:#dde0f0;font-size:{fs}px;}}
QComboBox::drop-down{{border:none;}}
QComboBox QAbstractItemView{{background:#0a0a18;color:#dde0f0;
                              selection-background-color:#1c1c3a;}}
QListWidget{{background:#0a0a18;border:1px solid #2e3060;border-radius:4px;
             font-size:{fs}px;}}
QTextEdit{{background:#050510;border:1px solid #2e3060;border-radius:4px;
           color:#00e676;font-family:Consolas,monospace;font-size:{logfs}px;}}
QTableWidget{{background:#08080f;gridline-color:#1e1e3a;
              border:1px solid #2e3060;font-size:{fs}px;}}
QTableWidget::item{{padding:2px;}}
QTableWidget::item:selected{{background:#1c3a6a;}}
QHeaderView::section{{background:#141430;color:#5dade2;
                      border:1px solid #1e1e3a;padding:3px;font-size:{fs}px;}}
QRadioButton,QCheckBox{{color:#dde0f0;font-size:{fs}px;}}
QTabBar::tab{{background:#141430;color:#888;padding:5px 12px;
              border:1px solid #2e3060;border-bottom:none;font-size:{tfs}px;}}
QTabBar::tab:selected{{background:#1c1c3a;color:#fff;font-weight:bold;}}
QTabWidget::pane{{border:1px solid #2e3060;}}
QSplitter::handle{{background:#1e1e3a;}}
QSlider::groove:horizontal{{height:4px;background:#1e1e3a;border-radius:2px;}}
QSlider::handle:horizontal{{width:14px;height:14px;background:#5dade2;
                             border-radius:7px;margin:-5px 0;}}
"""

def make_style(fs: int = DEFAULT_FONT_SIZE) -> str:
    return BASE_STYLE.format(fs=fs, logfs=max(10, fs-4), tfs=max(11, fs-2))


# ══════════════════════════════════════════════════════════════
# 3. 시그널 브릿지 (스레드 → Qt UI 안전 통신)
# ══════════════════════════════════════════════════════════════
class SignalBridge(QObject):
    tick_price     = pyqtSignal(int, int, float)
    tick_option    = pyqtSignal(int, int, float, float, float, float, float, float)
    connected      = pyqtSignal()
    error_sig      = pyqtSignal(int, int, str)
    # 계좌
    acct_value     = pyqtSignal(str, str, str, str)   # tag,val,cur,acct
    acct_end       = pyqtSignal()
    # 포지션
    position_sig   = pyqtSignal(str, str, str, float, float)
    position_end   = pyqtSignal()
    # 미체결
    open_order_sig = pyqtSignal(int, str, str, str, float, float, str)
    # 체결 (execDetails)
    exec_sig       = pyqtSignal(int, str, str, float, float)  # oid,sym,side,qty,price
    # 주문 상태
    order_status_sig = pyqtSignal(int, str, float, float)     # oid,status,filled,remaining
    # whatIf 증거금 조회 결과
    whatif_sig = pyqtSignal(int, float, float, float, float, str)  # oid,initBefore,initAfter,maintBefore,maintAfter,commission
    # 히스토리
    hist_bar       = pyqtSignal(int, dict)   # bar를 dict로 직렬화 후 emit (object는 cross-thread 크래시)
    hist_end       = pyqtSignal(int)
    hist_ticks     = pyqtSignal(int, list, bool)  # reqId, ticks(list of dict), done
    hist_bar_update = pyqtSignal(int, dict)  # ← 이 줄만 추가

# 전역 브릿지 싱글턴
bridge = SignalBridge()

# ══════════════════════════════════════════════════════════════
# 비동기 tick 라우터
# ── 탭별 reqId 범위를 등록해두고 tick이 오면 해당 탭의
#    전용 슬롯으로만 emit → 탭 간 상호 간섭·처리 지연 최소화
# ══════════════════════════════════════════════════════════════
class TickRouter(QObject):
    """
    tick_price / tick_option 시그널을 reqId 범위로 분기한다.
    각 탭은 register(rid_start, rid_end, slot) 으로 구독,
    전역 bridge.tick_price 를 직접 연결하는 대신 이 라우터를
    경유하면 불필요한 탭까지 wake-up 되는 현상을 방지한다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._price_routes  = []   # [(start,end,slot), ...]
        self._option_routes = []
        bridge.tick_price.connect(self._route_price,  Qt.QueuedConnection)
        bridge.tick_option.connect(self._route_option, Qt.QueuedConnection)

    def register_price(self, rid_start: int, rid_end: int, slot):
        self._price_routes.append((rid_start, rid_end, slot))

    def register_option(self, rid_start: int, rid_end: int, slot):
        self._option_routes.append((rid_start, rid_end, slot))

    def unregister_price(self, slot):
        self._price_routes = [(s,e,fn) for s,e,fn in self._price_routes if fn!=slot]

    def unregister_option(self, slot):
        self._option_routes = [(s,e,fn) for s,e,fn in self._option_routes if fn!=slot]

    def _route_price(self, rid: int, tt: int, price: float):
        for start, end, slot in self._price_routes:
            if start <= rid <= end:
                try: slot(rid, tt, price)
                except Exception as ex: print(f"[Router] price slot err: {ex}")

    def _route_option(self, rid: int, tt: int, iv, delta, op, gamma, vega, theta):
        for start, end, slot in self._option_routes:
            if start <= rid <= end:
                try: slot(rid, tt, iv, delta, op, gamma, vega, theta)
                except Exception as ex: print(f"[Router] option slot err: {ex}")

# 전역 라우터 싱글턴 (main.py 에서 초기화 후 각 탭이 사용)
router = TickRouter()


# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
# Re-export — 기존 import 호환성 유지
# 다른 모듈에서 "from core import ..." 가 그대로 동작하도록
# ══════════════════════════════════════════════════════════════
from core_expiry import (
    _easter, _us_market_holidays, _HOLIDAY_CACHE,
    is_trading_day, next_wd, next_trading_friday, build_expiry_list,
)
from core_io import (
    save_json, load_json, append_csv, load_csv,
    is_market_open, auto_mdt,
)
from core_ui import (
    _all_tables, _apply_table_theme, make_table, tbl_set,
    ts, ts_full, _FloatWin, _ResizableFrame, GridTab,
)
from core_tab_wrapper import TabWrapper
from core_contract import IBapi, make_opt_contract, make_und_contract, _resolve_spx_trading_class
