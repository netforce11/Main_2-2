"""
Main_config.py — 기본 설정 탭  v1.0
════════════════════════════════════════════════════════════════
[설정 탭] ConfigTab (QWidget)
  - 탭1 콜-풋 탭의 ConfigMixin 을 통해 통합

기능 목록:
  1. 텔레그램 Heartbeat 주기 설정 + 송신 기능
  2. 기초자산 저장 경로 출력 + 저장 주기 변경
  3. 기타 경로 정보 출력
  4. 옵션 체인 초기 조회 갯수 설정
  5. ATM ± 범위 조정 (추가 입력 필드)
  6. 콜/풋 체인 표시 컬럼 선택 (체크박스)

사용법:
  from Main_config import ConfigTab, ConfigMixin
  # ConfigMixin → CallPutGrid 에 mixin
  # ConfigTab → main.py 에서 탭으로 등록
════════════════════════════════════════════════════════════════
"""

import json
import threading
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QGroupBox, QScrollArea, QFrame, QCheckBox,
    QSizePolicy, QComboBox, QSplitter,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont

# ── 경로 상수 (core.py 와 동일) ──────────────────────────────
from core import SAVE_DIR, GREEKS_HISTORY_DIR, BASE_DATA_DIR, N_STRIKES

# config 파일 경로 (설정 탭 전용)
_CONFIG_FILE = SAVE_DIR / "main_config_settings.json"

# ── 기본값 ──────────────────────────────────────────────────
_DEFAULTS = {
    "heartbeat_interval_min": 3,       # 텔레그램 heartbeat 주기 (분)
    "chain_save_interval_sec": 10,     # 기초자산 저장 주기 (초)
    "chain_initial_count": 20,         # 옵션 체인 초기 조회 갯수
    "atm_extra_above": 0,              # ATM 위쪽 추가 범위
    "atm_extra_below": 0,              # ATM 아래쪽 추가 범위
    "chain_columns": [                 # 체인 표시 컬럼 선택
        "행사가", "가격", "등락%", "델타", "쎄타", "감마", "잔고"
    ],
    # ── 1분봉 차트탭 — 미니 차트 오버레이 설정 ───────────────
    "overlay_candle_half": 10,         # 앞뒤 캔들 수 ±N봉 (총 2N+1봉)
    "overlay_width_pct":   31,         # 오버레이 너비 (p1 폭 대비 %)
    "overlay_height_pct":  33,         # 오버레이 높이 (p1 높이 대비 %)
}

# 선택 가능한 전체 컬럼 목록
ALL_COLUMNS = [
    "행사가", "가격", "등락%", "지수대비거리%",
    "델타", "쎄타", "감마", "베가", "잔고", "미결제", "IV",
]


# ══════════════════════════════════════════════════════════════
# 설정값 싱글톤 저장소
# ══════════════════════════════════════════════════════════════
class MainConfigStore:
    """설정값 JSON 저장/로드 싱글톤.

    [FIX-B9] QObject 상속 금지:
    QObject 에 __new__ 오버라이드 싱글톤 패턴을 적용하면
    super().__init__() 미호출로 RuntimeError 발생.
    (HeartbeatManager 주석 참조)
    이 클래스는 반드시 일반 object 만 상속해야 함.
    싱글톤은 모듈 레벨 config_store 인스턴스로 관리.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._load()
        return cls._instance

    def _load(self):
        import copy
        self._data = copy.deepcopy(_DEFAULTS)
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def save(self):
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[MainConfig] 저장 실패: {e}")

    def get(self, key, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key, value):
        self._data[key] = value

    # ── 편의 프로퍼티 ──────────────────────────────────────────
    @property
    def heartbeat_interval_min(self) -> int:
        return int(self._data.get("heartbeat_interval_min", 3))

    @property
    def chain_save_interval_sec(self) -> int:
        return int(self._data.get("chain_save_interval_sec", 10))

    @property
    def chain_initial_count(self) -> int:
        return int(self._data.get("chain_initial_count", 20))

    @property
    def atm_extra_above(self) -> int:
        return int(self._data.get("atm_extra_above", 0))

    @property
    def atm_extra_below(self) -> int:
        return int(self._data.get("atm_extra_below", 0))

    @property
    def chain_columns(self) -> list:
        return self._data.get("chain_columns", _DEFAULTS["chain_columns"])

    # ── 1분봉 차트탭 오버레이 프로퍼티 ───────────────────────
    @property
    def overlay_candle_half(self) -> int:
        return int(self._data.get("overlay_candle_half", 10))

    @property
    def overlay_width_pct(self) -> int:
        return int(self._data.get("overlay_width_pct", 31))

    @property
    def overlay_height_pct(self) -> int:
        return int(self._data.get("overlay_height_pct", 33))


# 전역 싱글톤
config_store = MainConfigStore()


# ══════════════════════════════════════════════════════════════
# Heartbeat 관리자
# QObject 에 __new__ 싱글톤 패턴을 쓰면 super().__init__ 미호출
# RuntimeError 가 발생하므로, 클래스는 일반 QObject 로 두고
# 모듈 레벨 팩토리(_get_heartbeat_mgr)로 단일 인스턴스를 관리.
# ══════════════════════════════════════════════════════════════
class HeartbeatManager(QObject):
    """QTimer 기반 텔레그램 heartbeat 송신."""
    status_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._send_heartbeat)
        self._active = False
        self._interval_min = config_store.heartbeat_interval_min

    def start(self, interval_min: int = None):
        if interval_min is not None:
            self._interval_min = interval_min
        ms = self._interval_min * 60 * 1000
        self._timer.start(ms)
        self._active = True
        self.status_changed.emit(f"✅ Heartbeat 활성 ({self._interval_min}분 주기)")
        print(f"[Heartbeat] 시작: {self._interval_min}분 주기")

    def stop(self):
        self._timer.stop()
        self._active = False
        self.status_changed.emit("⏸ Heartbeat 비활성")

    def set_interval(self, interval_min: int):
        self._interval_min = interval_min
        if self._active:
            self._timer.stop()
            self._timer.start(interval_min * 60 * 1000)
            self.status_changed.emit(f"✅ Heartbeat 활성 ({interval_min}분 주기)")

    def is_active(self) -> bool:
        return self._active

    def attach_dashboard(self, dashboard):
        """
        TradingDashboard 참조 주입.
        2초마다 연결 상태를 폴링해서
        IBKR 연결이 확인되는 순간 heartbeat 를 자동 시작한다.
        """
        self._dashboard = dashboard
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(2000)
        self._auto_timer.timeout.connect(self._check_auto_start)
        self._auto_timer.start()
        print("[Heartbeat] IBKR 연결 감시 타이머 등록")

    def _check_auto_start(self):
        """IBKR 연결 확인 시 heartbeat 자동 시작 (1회)."""
        if self._active:
            if hasattr(self, '_auto_timer'):
                self._auto_timer.stop()
            return
        dashboard = getattr(self, '_dashboard', None)
        if dashboard is None:
            return
        try:
            connected = getattr(dashboard, 'connected', False)
        except Exception:
            return
        if connected:
            self._auto_timer.stop()
            interval = config_store.heartbeat_interval_min
            self.start(interval)
            print(f"[Heartbeat] IBKR 연결 감지 → 자동 시작 ({interval}분 주기)")

    def send_now(self):
        """즉시 한 번 전송 (테스트용)."""
        threading.Thread(target=self._send_heartbeat, daemon=True).start()

    def _send_heartbeat(self):
        try:
            from telegram_bot.tg_client import TelegramClient
            from datetime import datetime
            # zoneinfo: Python 3.9+ 표준 라이브러리 (pytz 불필요)
            try:
                from zoneinfo import ZoneInfo
            except ImportError:
                try:
                    from backports.zoneinfo import ZoneInfo
                except ImportError:
                    ZoneInfo = None
            if ZoneInfo:
                now_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S ET")
            else:
                now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            msg = (
                f"💓 서버 정상 동작 중\n"
                f"⏰ {now_str}\n"
                f"📡 0DTE Dashboard — Heartbeat"
            )
            ok = TelegramClient.get()._send_raw(msg)
            if ok:
                self.status_changed.emit(f"💓 마지막 송신: {now_str}")
                print(f"[Heartbeat] 전송 완료: {now_str}")
            else:
                self.status_changed.emit("⚠️ Heartbeat 전송 실패")
        except Exception as e:
            self.status_changed.emit(f"⚠️ 오류: {e}")
            print(f"[Heartbeat] 오류: {e}")


# ── 전역 인스턴스 (lazy, QApplication 생성 이후 최초 접근 시 생성) ──
_heartbeat_mgr_instance: "HeartbeatManager | None" = None

def _get_heartbeat_mgr() -> "HeartbeatManager":
    global _heartbeat_mgr_instance
    if _heartbeat_mgr_instance is None:
        _heartbeat_mgr_instance = HeartbeatManager()
    return _heartbeat_mgr_instance

# 편의용 모듈 속성 — import 시 즉시 생성하지 않음
# 사용: from Main_config import _get_heartbeat_mgr; mgr = _get_heartbeat_mgr()
# 또는: import Main_config; Main_config.heartbeat_mgr  (아래 __getattr__ 참조)
heartbeat_mgr: "HeartbeatManager | None" = None  # 초기화 전 placeholder


# ══════════════════════════════════════════════════════════════
# 스타일 헬퍼
# ══════════════════════════════════════════════════════════════
def _gb(title: str, color: str = "#5dade2") -> QGroupBox:
    gb = QGroupBox(title)
    gb.setStyleSheet(
        f"QGroupBox{{font-size:14px;color:{color};font-weight:bold;"
        f"border:1px solid #2a2a5a;border-radius:6px;"
        f"margin-top:10px;padding-top:8px;}}"
        f"QGroupBox::title{{subcontrol-origin:margin;left:10px;}}"
    )
    return gb


def _lbl(text: str, color: str = "#dde0f0", size: int = 14) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{color};font-size:{size}px;border:none;")
    return lbl


def _open_path(path: str):
    """경로(파일 or 폴더)를 파일 매니저로 열기."""
    import subprocess, os
    from pathlib import Path as _Path
    p = _Path(path)
    # 파일이면 부모 폴더를 열고 파일 선택, 폴더면 그 폴더를 열기
    target = str(p.parent) if p.is_file() else str(p)
    try:
        # Linux: nautilus / xdg-open 순서로 시도
        for cmd in (["nautilus", "--select", str(p)],
                    ["xdg-open", target],
                    ["thunar", target],
                    ["dolphin", "--select", str(p)]):
            try:
                subprocess.Popen(cmd, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
    except Exception as e:
        print(f"[Config] 폴더 열기 실패: {e}")


def _path_lbl(path: str) -> QLabel:
    """경로 표시 전용 라벨. 클릭 시 파일 매니저로 열기."""
    lbl = QLabel(path)
    lbl.setStyleSheet(
        "color:#00e676;font-size:13px;font-family:Consolas,monospace;"
        "background:#03030a;border:1px solid #1a1a3a;border-radius:3px;"
        "padding:3px 6px;"
        "text-decoration: underline;"
    )
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lbl.setCursor(Qt.PointingHandCursor)
    lbl.setToolTip("클릭하면 폴더를 엽니다\n" + path)
    # 클릭 이벤트 — path 를 클로저로 캡처
    _p = path
    lbl.mousePressEvent = lambda e, p=_p: _open_path(p) if e.button() == Qt.LeftButton else None
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("border:none;background:#2a2a5a;max-height:1px;margin:4px 0;")
    return f


def _btn(text: str, color: str = "#1c1c3a", fg: str = "#dde0f0") -> QPushButton:
    b = QPushButton(text)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:{fg};font-size:14px;"
        f"border:1px solid #3a3a7a;border-radius:4px;padding:4px 14px;}}"
        f"QPushButton:hover{{background:#2a2a5a;color:#fff;}}"
        f"QPushButton:pressed{{background:#0e0e2a;}}"
    )
    return b


def _spinbox(min_val: int, max_val: int, val: int, suffix: str = "") -> QSpinBox:
    sb = QSpinBox()
    sb.setMinimum(min_val)
    sb.setMaximum(max_val)
    sb.setValue(val)
    if suffix:
        sb.setSuffix(f" {suffix}")
    sb.setFixedWidth(100)
    sb.setStyleSheet(
        "QSpinBox{background:#0a0a18;border:1px solid #2e3060;font-size:14px;"
        "border-radius:4px;padding:3px;color:#dde0f0;}"
    )
    return sb


# ══════════════════════════════════════════════════════════════
# 메인 설정 탭 위젯
# ══════════════════════════════════════════════════════════════
class ConfigTab(QWidget):
    """
    기본 설정 탭.
    main.py 에서: self.tab_config = ConfigTab(); tabs.addTab(self.tab_config, "⚙️ 설정")
    """

    # 외부에서 연결할 시그널
    chain_save_interval_changed = pyqtSignal(int)
    chain_initial_count_changed = pyqtSignal(int)
    atm_range_changed           = pyqtSignal(int, int)
    chain_columns_changed       = pyqtSignal(list)
    overlay_settings_changed    = pyqtSignal(int, int, int)  # (candle_half, w_pct, h_pct)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = config_store
        self._callput_ref = None   # CallPutGrid 참조 (attach_callput 으로 주입)
        self._build()

    def attach_callput(self, callput_grid):
        """main.py 에서 CallPutGrid 참조를 주입. 컬럼 즉시 반영에 사용."""
        self._callput_ref = callput_grid

    # ── Layout ───────────────────────────────────────────────
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ══ 슬라이딩 테마 패널 (좌측 외부, 기본 숨김) ════════
        self._theme_panel = self._build_theme_panel()
        self._theme_panel.setFixedWidth(0)          # 초기 숨김
        self._theme_panel.setMinimumWidth(0)
        root.addWidget(self._theme_panel)

        # ══ 테마 토글 탭 버튼 ═════════════════════════════════
        self._theme_tab_btn = QPushButton("⚙\n테\n마\n설\n정")
        self._theme_tab_btn.setFixedWidth(22)
        self._theme_tab_btn.setCheckable(True)
        self._theme_tab_btn.setStyleSheet(
            "QPushButton{background:#1a1a2e;color:#ffd700;font-size:11px;"
            "font-weight:bold;border:none;border-right:1px solid #2a2a5a;"
            "padding:6px 2px;letter-spacing:1px;}"
            "QPushButton:checked{background:#2a2a0a;color:#ffee44;"
            "border-right:2px solid #ffd700;}"
            "QPushButton:hover{background:#2a2a3a;}"
        )
        self._theme_tab_btn.clicked.connect(self._toggle_theme_panel)
        root.addWidget(self._theme_tab_btn)

        # ══ 메인 Splitter (좌=설정, 우=수면주문) ══════════════
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setStyleSheet(
            "QSplitter::handle{background:#2a2a5a;width:5px;}"
            "QSplitter::handle:hover{background:#5a5aaa;}"
            "QSplitter::handle:pressed{background:#8080dd;}"
        )
        self._splitter.setHandleWidth(5)

        # ── 좌측: 기본 설정 스크롤 영역 ──────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#0a0a18;}"
            "QScrollBar:vertical{width:8px;background:#06060e;}"
            "QScrollBar::handle:vertical{background:#3a3a7a;border-radius:4px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        inner = QWidget()
        inner.setStyleSheet("background:#0a0a18;")
        vlay = QVBoxLayout(inner)
        vlay.setContentsMargins(16, 12, 16, 16)
        vlay.setSpacing(10)

        hdr = QLabel("⚙️  기본 설정 관리")
        hdr.setStyleSheet(
            "color:#5dade2;font-size:18px;font-weight:bold;border:none;"
            "padding:6px 0 2px 0;")
        vlay.addWidget(hdr)
        vlay.addWidget(_sep())
        vlay.addWidget(self._build_heartbeat_section())
        vlay.addWidget(self._build_paths_section())
        vlay.addWidget(self._build_chain_save_section())
        vlay.addWidget(self._build_chain_count_section())
        vlay.addWidget(self._build_atm_range_section())
        vlay.addWidget(self._build_column_select_section())
        vlay.addWidget(self._build_overlay_section())
        vlay.addStretch()
        scroll.setWidget(inner)
        self._splitter.addWidget(scroll)

        # ── 우측: 수면 예약 주문 설정 패널 ───────────────────
        try:
            import sys, os as _os
            _this_dir = _os.path.dirname(_os.path.abspath(__file__))
            if _this_dir not in sys.path:
                sys.path.insert(0, _this_dir)
            from Sleep_Order.sleep_order_ui import SleepOrderRightPanel
            self._sleep_right_panel = SleepOrderRightPanel()
            self._splitter.addWidget(self._sleep_right_panel)
        except Exception as e:
            print(f"[ConfigTab] SleepOrderRightPanel 로드 실패: {e}")
            import traceback; traceback.print_exc()
            placeholder = QLabel("🌙 수면 예약 주문\n로드 실패: " + str(e))
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet("color:#ff6666;font-size:13px;border:none;padding:10px;")
            self._splitter.addWidget(placeholder)

        self._splitter.setSizes([500, 900])   # 기본 비율 (픽셀, 실제 크기에 맞게 비례)
        root.addWidget(self._splitter)

    # ── 슬라이딩 테마 패널 ──────────────────────────────────
    def _build_theme_panel(self) -> QWidget:
        """기존 ThemeConfigPanel 을 슬라이딩 컨테이너로 감싸서 반환."""
        try:
            from main_config_theme import ThemeConfigPanel
            panel = ThemeConfigPanel(
                parent=self,
                apply_callback=self._apply_theme,
            )
            self._theme_config_panel = panel   # sync_preset_buttons 호출용
        except Exception as e:
            print(f"[ConfigTab] ThemeConfigPanel 로드 실패: {e}")
            panel = QLabel(f"테마 패널 로드 실패\n{e}")
            panel.setStyleSheet("color:#ff6666;font-size:12px;padding:8px;")
        panel.setStyleSheet(panel.styleSheet() +
                            "border-right:1px solid #2a2a5a;")
        return panel

    def _apply_theme(self, key: str) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app and hasattr(app, 'apply_theme'):
                app.apply_theme(key)
        except Exception as e:
            print(f"[ConfigTab] 테마 적용 실패: {e}")

    def _toggle_theme_panel(self, checked: bool) -> None:
        """테마 패널 슬라이딩 애니메이션 (열림 220px / 닫힘 0px)."""
        OPEN_W = 220
        self._theme_panel.setMaximumWidth(99999)
        self._theme_panel.setMinimumWidth(0)
        start = self._theme_panel.width()
        target = OPEN_W if checked else 0
        self._anim = QPropertyAnimation(self._theme_panel, b"maximumWidth")
        self._anim.setDuration(220)
        self._anim.setStartValue(start)
        self._anim.setEndValue(target)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        if not checked:
            self._anim.finished.connect(
                lambda: self._theme_panel.setFixedWidth(0))
        self._anim.start()

    # ─────────────────────────────────────────────────────────
    # 섹션 1: 텔레그램 Heartbeat
    # ─────────────────────────────────────────────────────────
    def _build_heartbeat_section(self) -> QGroupBox:
        gb = _gb("📡  텔레그램 Heartbeat (서버 생존 신호)")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        # 주기 설정
        lay.addWidget(_lbl("송신 주기:"), 0, 0, Qt.AlignRight)
        self._hb_spin = _spinbox(1, 60, self._cfg.heartbeat_interval_min, "분")
        lay.addWidget(self._hb_spin, 0, 1)

        lay.addWidget(_lbl("(기본: 3분, 범위: 1~60분)", "#888", 11), 0, 2)

        # 상태 라벨
        self._hb_status = QLabel("⏸ Heartbeat 비활성")
        self._hb_status.setStyleSheet(
            "color:#ffd700;font-size:14px;border:none;padding:2px 6px;"
            "background:#08080f;border-radius:3px;border:1px solid #2a2a3a;"
        )
        lay.addWidget(self._hb_status, 1, 0, 1, 3)

        # 버튼 행
        btn_row = QHBoxLayout()
        self._hb_start_btn = _btn("▶  시작", "#1a3a1a", "#00ff88")
        self._hb_stop_btn  = _btn("■  정지", "#3a1a1a", "#ff6666")
        self._hb_test_btn  = _btn("📨  지금 전송", "#1a1a3a", "#90caf9")

        self._hb_start_btn.clicked.connect(self._on_hb_start)
        self._hb_stop_btn.clicked.connect(self._on_hb_stop)
        self._hb_test_btn.clicked.connect(self._on_hb_test)

        btn_row.addWidget(self._hb_start_btn)
        btn_row.addWidget(self._hb_stop_btn)
        btn_row.addWidget(self._hb_test_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row, 2, 0, 1, 3)

        # heartbeat 상태 시그널 연결
        _get_heartbeat_mgr().status_changed.connect(self._hb_status.setText)

        return gb

    def _on_hb_start(self):
        interval = self._hb_spin.value()
        self._cfg.set("heartbeat_interval_min", interval)
        self._cfg.save()
        _get_heartbeat_mgr().start(interval)

    def _on_hb_stop(self):
        _get_heartbeat_mgr().stop()

    def _on_hb_test(self):
        self._hb_status.setText("📨 전송 중...")
        _get_heartbeat_mgr().send_now()

    # ─────────────────────────────────────────────────────────
    # 섹션 2: 경로 정보
    # ─────────────────────────────────────────────────────────
    def _build_paths_section(self) -> QGroupBox:
        gb = _gb("📁  경로 설정 현황", "#ffd700")
        lay = QVBoxLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(6)

        paths = [
            ("기초자산 저장 경로 (SAVE_DIR)",      str(SAVE_DIR)),
            ("Greeks 히스토리 경로 (GREEKS_HISTORY_DIR)", str(GREEKS_HISTORY_DIR)),
            ("베이스 데이터 경로 (BASE_DATA_DIR)",  str(BASE_DATA_DIR)),
            ("설정 파일 경로 (main_config_settings.json)", str(_CONFIG_FILE)),
        ]

        for title, path in paths:
            row = QHBoxLayout()
            row.setSpacing(6)
            name_lbl = _lbl(f"• {title}", "#90caf9", 13)
            name_lbl.setFixedWidth(330)
            name_lbl.setWordWrap(True)
            row.addWidget(name_lbl)
            row.addWidget(_path_lbl(path), 1)
            lay.addLayout(row)

        # tg_config.json 경로
        try:
            from telegram_bot.tg_config import CONFIG_PATH as TG_CFG_PATH
            row2 = QHBoxLayout()
            name_lbl2 = _lbl("• 텔레그램 설정 파일 (tg_config.json)", "#90caf9", 13)
            name_lbl2.setFixedWidth(310)
            row2.addWidget(name_lbl2)
            row2.addWidget(_path_lbl(str(TG_CFG_PATH)), 1)
            lay.addLayout(row2)
        except Exception:
            pass

        return gb

    # ─────────────────────────────────────────────────────────
    # 섹션 3: 기초자산 저장 주기
    # ─────────────────────────────────────────────────────────
    def _build_chain_save_section(self) -> QGroupBox:
        gb = _gb("💾  기초자산 저장 주기")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        lay.addWidget(_lbl("저장 주기:"), 0, 0, Qt.AlignRight)
        self._save_spin = _spinbox(1, 300, self._cfg.chain_save_interval_sec, "초")
        lay.addWidget(self._save_spin, 0, 1)
        lay.addWidget(_lbl("(기본: 10초, 범위: 1~300초)", "#888", 11), 0, 2)

        self._save_status = _lbl("현재 적용: 미변경", "#aaa", 13)
        lay.addWidget(self._save_status, 1, 0, 1, 3)

        btn = _btn("✔  적용", "#1a2a1a", "#00e676")
        btn.clicked.connect(self._on_save_interval_apply)
        lay.addWidget(btn, 2, 0)

        return gb

    def _on_save_interval_apply(self):
        val = self._save_spin.value()
        self._cfg.set("chain_save_interval_sec", val)
        self._cfg.save()
        self._save_status.setText(f"✅ 적용됨: {val}초  (재시작 후 완전 반영)")
        self.chain_save_interval_changed.emit(val)
        print(f"[Config] 기초자산 저장 주기 변경: {val}초")

    # ─────────────────────────────────────────────────────────
    # 섹션 4: 옵션 체인 초기 조회 갯수
    # ─────────────────────────────────────────────────────────
    def _build_chain_count_section(self) -> QGroupBox:
        gb = _gb("🔢  옵션 체인 초기 조회 갯수")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        lay.addWidget(_lbl("초기 조회 갯수:"), 0, 0, Qt.AlignRight)
        self._count_spin = _spinbox(
            5, 100, self._cfg.chain_initial_count, "개"
        )
        lay.addWidget(self._count_spin, 0, 1)
        lay.addWidget(
            _lbl(f"(기본: 20개, 범위: 5~100개  |  core.py N_STRIKES={N_STRIKES})", "#888", 11),
            0, 2
        )

        self._count_status = _lbl("현재 적용: 미변경", "#aaa", 13)
        lay.addWidget(self._count_status, 1, 0, 1, 3)

        btn = _btn("✔  적용", "#1a2a1a", "#00e676")
        btn.clicked.connect(self._on_chain_count_apply)
        lay.addWidget(btn, 2, 0)

        return gb

    def _on_chain_count_apply(self):
        val = self._count_spin.value()
        self._cfg.set("chain_initial_count", val)
        self._cfg.save()
        self._count_status.setText(f"✅ 적용됨: {val}개  (다음 조회 시 반영)")
        self.chain_initial_count_changed.emit(val)
        print(f"[Config] 체인 초기 조회 갯수 변경: {val}")

    # ─────────────────────────────────────────────────────────
    # 섹션 5: ATM 범위 설정
    # ─────────────────────────────────────────────────────────
    def _build_atm_range_section(self) -> QGroupBox:
        gb = _gb("🎯  ATM 조회 범위 설정 (± 추가)")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        note = _lbl(
            "ATM 위아래 기본 범위에 추가로 더 볼 행사가 수를 설정합니다.\n"
            "ex) 위+2, 아래+2 → 기존 ATM±N 에서 위 2개, 아래 2개 추가 표시",
            "#aaa", 11
        )
        note.setWordWrap(True)
        lay.addWidget(note, 0, 0, 1, 4)

        lay.addWidget(_lbl("ATM 위쪽 추가 (행사가↑):"), 1, 0, Qt.AlignRight)
        self._atm_above_spin = _spinbox(0, 20, self._cfg.atm_extra_above, "개")
        lay.addWidget(self._atm_above_spin, 1, 1)

        lay.addWidget(_lbl("ATM 아래쪽 추가 (행사가↓):"), 1, 2, Qt.AlignRight)
        self._atm_below_spin = _spinbox(0, 20, self._cfg.atm_extra_below, "개")
        lay.addWidget(self._atm_below_spin, 1, 3)

        self._atm_status = _lbl("현재 적용: 미변경", "#aaa", 13)
        lay.addWidget(self._atm_status, 2, 0, 1, 4)

        btn = _btn("✔  적용", "#1a2a1a", "#00e676")
        btn.clicked.connect(self._on_atm_apply)
        lay.addWidget(btn, 3, 0)

        return gb

    def _on_atm_apply(self):
        above = self._atm_above_spin.value()
        below = self._atm_below_spin.value()
        self._cfg.set("atm_extra_above", above)
        self._cfg.set("atm_extra_below", below)
        self._cfg.save()
        self._atm_status.setText(f"✅ 적용됨: 위+{above}  아래+{below}  (다음 조회 시 반영)")
        self.atm_range_changed.emit(above, below)
        print(f"[Config] ATM 범위 변경: 위+{above}, 아래+{below}")

    # ─────────────────────────────────────────────────────────
    # 섹션 6: 체인 컬럼 선택
    # ─────────────────────────────────────────────────────────
    def _build_column_select_section(self) -> QGroupBox:
        gb = _gb("📋  콜/풋 체인 표시 컬럼 선택")
        lay = QVBoxLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(8)

        note = _lbl(
            "체크박스로 표시할 컬럼을 선택하고 [조회 반영] 버튼을 눌러주세요.\n"
            "※ '행사가'는 항상 표시됩니다. 순서는 위 목록 순서로 고정됩니다.",
            "#aaa", 11
        )
        note.setWordWrap(True)
        lay.addWidget(note)

        # 체크박스 그리드 (4열)
        cb_grid = QGridLayout()
        cb_grid.setSpacing(6)
        self._col_checkboxes: dict[str, QCheckBox] = {}
        active_cols = self._cfg.chain_columns

        for i, col in enumerate(ALL_COLUMNS):
            cb = QCheckBox(col)
            cb.setChecked(col in active_cols)
            cb.setEnabled(col != "행사가")   # 행사가는 비활성(항상 선택)
            cb.setStyleSheet(
                "QCheckBox{color:#dde0f0;font-size:14px;}"
                "QCheckBox::indicator{width:14px;height:14px;}"
                "QCheckBox::indicator:checked{background:#5dade2;"
                "border:1px solid #3a9ad2;border-radius:2px;}"
                "QCheckBox::indicator:unchecked{background:#0a0a18;"
                "border:1px solid #3a3a7a;border-radius:2px;}"
            )
            row, col_idx = divmod(i, 4)
            cb_grid.addWidget(cb, row, col_idx)
            self._col_checkboxes[col] = cb

        lay.addLayout(cb_grid)

        # 미리보기 라벨
        self._col_preview = _lbl("", "#90caf9", 13)
        self._col_preview.setWordWrap(True)
        lay.addWidget(self._col_preview)
        self._update_col_preview()

        # 체크박스 변경 시 미리보기 갱신
        for cb in self._col_checkboxes.values():
            cb.stateChanged.connect(self._update_col_preview)

        # 버튼
        btn_row = QHBoxLayout()
        apply_btn  = _btn("🔍  조회 반영", "#1a2a3a", "#5dade2")
        reset_btn  = _btn("↩  기본값", "#1a1a2a", "#888")
        apply_btn.clicked.connect(self._on_col_apply)
        reset_btn.clicked.connect(self._on_col_reset)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._col_status = _lbl("", "#aaa", 13)
        lay.addWidget(self._col_status)

        return gb

    def _update_col_preview(self):
        selected = [c for c in ALL_COLUMNS if self._col_checkboxes[c].isChecked()]
        self._col_preview.setText("선택된 컬럼: " + "  →  ".join(selected))

    def _on_col_apply(self):
        selected = [c for c in ALL_COLUMNS if self._col_checkboxes[c].isChecked()]
        if not selected:
            self._col_status.setText("⚠️ 최소 1개 이상 선택하세요.")
            return
        self._cfg.set("chain_columns", selected)
        self._cfg.save()

        # ── CallPutGrid 직접 참조가 있으면 즉시 반영 ─────────
        applied = self._apply_columns_to_callput(selected)

        status = f"✅ 적용됨: {len(selected)}개 컬럼"
        status += " (즉시 반영)" if applied else " (다음 조회 시 반영)"
        self._col_status.setText(status)
        self.chain_columns_changed.emit(selected)
        print(f"[Config] 체인 컬럼 변경: {selected}")

    def _apply_columns_to_callput(self, columns: list) -> bool:
        """
        CallPutGrid 의 콜/풋 테이블 헤더를 즉시 변경.
        테이블이 존재하면 True 반환.
        """
        cp = self._callput_ref
        if cp is None:
            return False
        try:
            # 콜 테이블: tbl_call / 풋 테이블: tbl_put
            for tbl_name in ("tbl_call", "tbl_put"):
                tbl = getattr(cp, tbl_name, None)
                if tbl is None:
                    continue
                # 행사가는 항상 포함, 나머지는 선택값
                headers = [c for c in columns]
                if "행사가" not in headers:
                    headers.insert(0, "행사가")
                tbl.setColumnCount(len(headers))
                tbl.setHorizontalHeaderLabels(headers)
                # 숨김 컬럼 해제 후 선택된 컬럼만 표시
                for i in range(tbl.columnCount()):
                    tbl.setColumnHidden(i, False)
            return True
        except Exception as e:
            print(f"[Config] 컬럼 즉시 반영 실패: {e}")
            return False

    def _on_col_reset(self):
        defaults = _DEFAULTS["chain_columns"]
        for col, cb in self._col_checkboxes.items():
            cb.setChecked(col in defaults)
        self._col_status.setText("↩ 기본값으로 초기화됨 (적용 버튼 눌러야 저장)")

    # ─────────────────────────────────────────────────────────
    # 섹션 7: 1분봉 차트탭 — 미니 차트 오버레이 설정
    # ─────────────────────────────────────────────────────────
    def _build_overlay_section(self) -> QGroupBox:
        gb = _gb("📊  1분봉 차트탭 — 미니 차트 오버레이", color="#f9a825")
        lay = QGridLayout(gb)
        lay.setContentsMargins(12, 14, 12, 10)
        lay.setSpacing(10)

        note = _lbl(
            "1분봉 차트 우측에 표시되는 일봉 인셋 오버레이 크기와 캔들 수를 설정합니다.\n"
            "✔ 적용 후 캘린더 날짜를 클릭하면 즉시 반영됩니다.",
            "#aaa", 11)
        note.setWordWrap(True)
        lay.addWidget(note, 0, 0, 1, 4)

        # ── 가로 (너비) ───────────────────────────────────────
        lay.addWidget(_lbl("미니 차트 오버레이  가로:"), 1, 0, Qt.AlignRight)
        self._ov_w_spin = _spinbox(10, 70, self._cfg.overlay_width_pct, "%")
        lay.addWidget(self._ov_w_spin, 1, 1)
        lay.addWidget(_lbl("(기본: 31%  · 범위: 10~70%)", "#888", 11), 1, 2, 1, 2)

        # ── 세로 (높이) ───────────────────────────────────────
        lay.addWidget(_lbl("미니 차트 오버레이  세로:"), 2, 0, Qt.AlignRight)
        self._ov_h_spin = _spinbox(10, 70, self._cfg.overlay_height_pct, "%")
        lay.addWidget(self._ov_h_spin, 2, 1)
        lay.addWidget(_lbl("(기본: 33%  · 범위: 10~70%)", "#888", 11), 2, 2, 1, 2)

        # ── 캔들 출력 갯수 ────────────────────────────────────
        lay.addWidget(_lbl("미니 차트 캔들 출력 갯수:"), 3, 0, Qt.AlignRight)
        self._ov_half_spin = _spinbox(3, 60, self._cfg.overlay_candle_half, "봉")
        lay.addWidget(self._ov_half_spin, 3, 1)
        lay.addWidget(_lbl("앞뒤 ±N봉  (기본: ±10, 총 21봉)", "#888", 11), 3, 2, 1, 2)

        # ── 현재값 미리보기 ───────────────────────────────────
        self._ov_status = _lbl("", "#aaa", 12)
        self._ov_status.setWordWrap(True)
        lay.addWidget(self._ov_status, 4, 0, 1, 4)
        self._ov_update_preview()

        # 값 바뀔 때마다 미리보기 갱신
        self._ov_w_spin.valueChanged.connect(lambda _: self._ov_update_preview())
        self._ov_h_spin.valueChanged.connect(lambda _: self._ov_update_preview())
        self._ov_half_spin.valueChanged.connect(lambda _: self._ov_update_preview())

        # ── 버튼 ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        apply_btn = _btn("✔  적용", "#1a2a1a", "#f9a825")
        reset_btn = _btn("↩  기본값", "#1a1a2a", "#888")
        apply_btn.clicked.connect(self._on_overlay_apply)
        reset_btn.clicked.connect(self._on_overlay_reset)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row, 5, 0, 1, 4)

        return gb

    def _ov_update_preview(self):
        try:
            half  = self._ov_half_spin.value()
            w_pct = self._ov_w_spin.value()
            h_pct = self._ov_h_spin.value()
            self._ov_status.setText(
                f"현재 설정:  가로 {w_pct}%  세로 {h_pct}%  "
                f"캔들 ±{half}봉 (총 {2*half+1}봉)")
        except Exception:
            pass

    def _on_overlay_apply(self):
        half  = self._ov_half_spin.value()
        w_pct = self._ov_w_spin.value()
        h_pct = self._ov_h_spin.value()
        self._cfg.set("overlay_candle_half", half)
        self._cfg.set("overlay_width_pct",   w_pct)
        self._cfg.set("overlay_height_pct",  h_pct)
        self._cfg.save()
        self._ov_status.setText(
            f"✅ 저장됨:  가로 {w_pct}%  세로 {h_pct}%  "
            f"캔들 ±{half}봉 (총 {2*half+1}봉)  — 캘린더 날짜 클릭 시 반영")
        self.overlay_settings_changed.emit(half, w_pct, h_pct)
        print(f"[Config] 오버레이 변경: ±{half}봉, {w_pct}%×{h_pct}%")

    def _on_overlay_reset(self):
        self._ov_w_spin.setValue(_DEFAULTS["overlay_width_pct"])
        self._ov_h_spin.setValue(_DEFAULTS["overlay_height_pct"])
        self._ov_half_spin.setValue(_DEFAULTS["overlay_candle_half"])
        self._ov_status.setText("↩ 기본값 복원 — ✔ 적용을 눌러야 저장됩니다")


# ══════════════════════════════════════════════════════════════
# ConfigMixin — CallPutGrid 에 mixin 하여 설정값 접근 제공
# ══════════════════════════════════════════════════════════════
class ConfigMixin:
    """
    CallPutGrid 에 mixin.
    설정 탭 위젯 빌드 + config_store 프로퍼티 접근.
    """

    def _build_config_widget(self) -> QWidget:
        """
        콜-풋 탭 사이드바 하단 'config 위젯' 빌드.
        기존 저장 주기 표시 영역 대체.
        """
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(2)

        # 저장 주기 표시
        self._cfg_save_lbl = QLabel(
            f"저장주기: {config_store.chain_save_interval_sec}초"
        )
        self._cfg_save_lbl.setAlignment(Qt.AlignCenter)
        self._cfg_save_lbl.setStyleSheet(
            "color:#666;font-size:10px;border:none;"
        )
        v.addWidget(self._cfg_save_lbl)

        return w

    @property
    def cfg_chain_initial_count(self) -> int:
        return config_store.chain_initial_count

    @property
    def cfg_atm_extra_above(self) -> int:
        return config_store.atm_extra_above

    @property
    def cfg_atm_extra_below(self) -> int:
        return config_store.atm_extra_below

    @property
    def cfg_chain_columns(self) -> list:
        return config_store.chain_columns

    # ── 1분봉 차트탭 오버레이 ────────────────────────────────
    @property
    def cfg_overlay_candle_half(self) -> int:
        return config_store.overlay_candle_half

    @property
    def cfg_overlay_width_pct(self) -> int:
        return config_store.overlay_width_pct

    @property
    def cfg_overlay_height_pct(self) -> int:
        return config_store.overlay_height_pct