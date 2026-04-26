"""
chart_condition_order.py — 조건부 알림 + 자동 주문 패널 (순수 PyQt5)
════════════════════════════════════════════════════════════════
레이아웃: 시안 B — 3컬럼 그리드 (조건 | 현황 | 주문)

기능:
  · 시간 범위: KST 기준 입력
  · 틱 임계값 / 행사가 조건
  · 현재가 조건 (체크 시만): 이상 / 이하 / 범위
  · BID / LAST / ASK 실시간 수신 (reqMktData 8100)
  · 조건 충족 → 알림음
  · 지정가 체크 ON  → 입력 필드값으로 주문
  · 지정가 체크 OFF → Last + 0.05 (1호가) 자동 계산 LMT
  · 자동 주문 체크 ON → IBKR placeOrder()

reqId 범위: 8100~8109
════════════════════════════════════════════════════════════════
"""

import os, sys, time
from datetime import datetime, date, timezone, timedelta
from pathlib import Path

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QFrame,
    QGroupBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer

try:
    from ibapi.contract import Contract
    from ibapi.order    import Order as IBOrder
    IBAPI_OK = True
except ImportError:
    IBAPI_OK = False

from core import bridge, router

# ── 상수 ─────────────────────────────────────────────────────
REQ_COND_OPT_BASE = 8100
ALERT_SOUND       = Path("/home/netforce/US_Data/alert.wav")
COOLDOWN_S        = 30
TICK_STEP         = 0.05   # 1호가

# ── 색상 ─────────────────────────────────────────────────────
C_BG     = "#0d0d1a"
C_PANEL  = "#0a0a18"
C_BORDER = "#1e1e3a"
C_BORD2  = "#2a2a4a"
C_BLUE   = "#5dade2"
C_GREEN  = "#00e676"
C_ORANGE = "#FF8C00"
C_RED    = "#E24B4A"
C_GRAY   = "#888888"
C_DIM    = "#444444"
C_TEXT   = "#dde0f0"
C_YELLOW = "#ffd700"
C_TEAL   = "#1D9E75"

SS_INPUT = (
    f"background:{C_PANEL}; border:1px solid #2e3060;"
    f"border-radius:3px; color:{C_TEXT}; padding:2px 5px;"
    f"font-size:11px;"
)
SS_GROUP = (
    f"QGroupBox {{"
    f"  border:1px solid {C_BORD2}; border-radius:5px;"
    f"  margin-top:10px; padding-top:6px;"
    f"  color:{C_BLUE}; font-size:11px; font-weight:bold;"
    f"}}"
    f"QGroupBox::title {{"
    f"  subcontrol-origin:margin; left:8px; padding:0 4px;"
    f"}}"
)


# ── 헬퍼 ─────────────────────────────────────────────────────
def _lbl(text: str, color: str = C_GRAY, bold: bool = False) -> QLabel:
    l = QLabel(text)
    w = "bold" if bold else "normal"
    l.setStyleSheet(f"color:{color}; font-size:11px; font-weight:{w};")
    return l


def _inp(default: str = "", width: int = 64) -> QLineEdit:
    e = QLineEdit(default)
    e.setFixedWidth(width); e.setFixedHeight(22)
    e.setStyleSheet(SS_INPUT)
    return e


def _spin(lo: float, hi: float, val: float, w: int = 58,
          decimals: int = 0, step: float = 1) -> QSpinBox | QDoubleSpinBox:
    if decimals == 0:
        s = QSpinBox()
        s.setRange(int(lo), int(hi)); s.setValue(int(val))
    else:
        s = QDoubleSpinBox()
        s.setRange(lo, hi); s.setValue(val)
        s.setDecimals(decimals); s.setSingleStep(step)
    s.setFixedWidth(w); s.setFixedHeight(22)
    s.setStyleSheet(SS_INPUT)
    return s


def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C_BORDER}; margin:3px 0;")
    return f


def _vsep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color:{C_BORD2}; margin:0 4px;")
    return f


def _mini_title(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{C_BLUE}; font-size:10px; font-weight:bold;"
        f"letter-spacing:0.5px; border-bottom:1px solid {C_BORDER};"
        f"padding-bottom:2px; margin-bottom:2px;")
    return l


# ══════════════════════════════════════════════════════════════
# KST ↔ ET 변환
# ══════════════════════════════════════════════════════════════
def _et_now() -> datetime:
    """현재 ET 시각 반환."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        offset = -4 if time.daylight and time.localtime().tm_isdst else -5
        return datetime.now(timezone(timedelta(hours=offset)))


def _kst_str_to_et_str(kst_str: str) -> str:
    """
    'HH:MM' KST 문자열 → 'HH:MM' ET 문자열.
    KST = UTC+9, ET = UTC-4(서머) or UTC-5(동절)
    """
    try:
        h, m = map(int, kst_str.strip().split(":"))
        # KST → UTC → ET
        kst_offset = 9
        et_offset  = -4 if time.daylight and time.localtime().tm_isdst else -5
        total_min  = h * 60 + m - (kst_offset - et_offset) * 60
        total_min  = total_min % (24 * 60)
        eh = total_min // 60; em = total_min % 60
        return f"{eh:02d}:{em:02d}"
    except Exception:
        return kst_str


def _et_now_str() -> str:
    return _et_now().strftime("%H:%M")


# ══════════════════════════════════════════════════════════════
# 조건 모니터
# ══════════════════════════════════════════════════════════════
class _Monitor:
    def __init__(self, mw):
        self.mw          = mw
        self.running     = False
        self._req_id     = REQ_COND_OPT_BASE
        self._price      = {"bid": 0.0, "ask": 0.0, "last": 0.0}
        self._trigger_ts = 0.0
        self._order_sent = False

        try:
            from chart_tick_speed import _tick_times
            self._tick_q = _tick_times
        except Exception:
            self._tick_q = None

        router.register_price(
            REQ_COND_OPT_BASE, REQ_COND_OPT_BASE + 9,
            self._on_tick)

    # ── 구독 ─────────────────────────────────────────────────
    def subscribe(self, strike_str: str):
        if not IBAPI_OK: return
        ibkr = self._ibkr()
        if ibkr is None: return
        try:
            c = self._make_contract(strike_str)
            if c:
                ibkr.reqMktData(self._req_id, c, "", False, False, [])
        except Exception as e:
            print(f"[CondOrder] subscribe err: {e}")

    def unsubscribe(self):
        if not IBAPI_OK: return
        ibkr = self._ibkr()
        if ibkr is None: return
        try:
            ibkr.cancelMktData(self._req_id)
        except Exception:
            pass

    def _make_contract(self, strike_str: str):
        if not strike_str or len(strike_str) < 2:
            return None
        try:
            right  = "C" if strike_str[-1].upper() == "C" else "P"
            strike = float(strike_str[:-1])
            c = Contract()
            c.symbol       = "SPXW"
            c.secType      = "OPT"
            c.exchange     = "SMART"
            c.currency     = "USD"
            c.right        = right
            c.strike       = strike
            c.multiplier   = "100"
            c.tradingClass = "SPXW"
            c.lastTradeDateOrContractMonth = date.today().strftime("%Y%m%d")
            return c
        except Exception as e:
            print(f"[CondOrder] contract err: {e}")
            return None

    def _on_tick(self, rid, tick_type, price):
        if rid != self._req_id: return
        if   tick_type == 1: self._price["bid"]  = price
        elif tick_type == 2: self._price["ask"]  = price
        elif tick_type == 4: self._price["last"] = price

    # ── 조건 검사 ─────────────────────────────────────────────
    def check(self, cfg: dict) -> tuple:
        """반환: (triggered: bool, tick_10s: int, reason: str)"""
        if not self.running:
            return False, 0, ""

        # ① 시간 범위 (ET 변환 후 비교)
        et_now = _et_now_str()
        et_s   = _kst_str_to_et_str(cfg["time_start"])
        et_e   = _kst_str_to_et_str(cfg["time_end"])
        if not (et_s <= et_now <= et_e):
            return False, 0, f"시간 외 ({et_now} ET)"

        # ② 틱 속도
        tick_10s = self.tick_10s()
        if tick_10s <= cfg["tick_thresh"]:
            return False, tick_10s, f"틱 {tick_10s} ≤ {cfg['tick_thresh']}"

        # ③ 현재가 조건 (체크 시만)
        if cfg["price_enabled"]:
            last = self._price["last"]
            op   = cfg["price_op"]
            pv1  = cfg["price_val1"]
            pv2  = cfg["price_val2"]
            if op == "이상" and not (last >= pv1):
                return False, tick_10s, f"현재가 {last:.2f} < {pv1:.2f}"
            elif op == "이하" and not (last <= pv1):
                return False, tick_10s, f"현재가 {last:.2f} > {pv1:.2f}"
            elif op == "범위" and not (pv1 <= last <= pv2):
                return False, tick_10s, f"현재가 {last:.2f} 범위외"

        # ④ 쿨다운
        elapsed = time.time() - self._trigger_ts
        if elapsed < COOLDOWN_S:
            return False, tick_10s, f"쿨다운 {int(COOLDOWN_S - elapsed)}s"

        self._trigger_ts = time.time()
        return True, tick_10s, "OK"

    # ── 주문 ─────────────────────────────────────────────────
    def place_order(self, cfg: dict) -> str:
        ibkr = self._ibkr()
        if ibkr is None or not IBAPI_OK:
            return "IBKR 미연결"
        try:
            c = self._make_contract(cfg["strike"])
            if c is None: return "컨트랙트 오류"

            o = IBOrder()
            o.action        = cfg["order_side"]
            o.totalQuantity = cfg["order_qty"]

            if cfg["limit_enabled"]:
                # 지정가 체크 ON → 입력값 사용
                o.orderType = "LMT"
                o.lmtPrice  = cfg["limit_price"]
            else:
                # 지정가 체크 OFF → Last + 1호가 (0.05)
                last = self._price["last"]
                lmt  = last + TICK_STEP if cfg["order_side"] == "BUY" else last - TICK_STEP
                o.orderType = "LMT"
                o.lmtPrice  = round(lmt * 20) / 20   # 0.05 단위 반올림

            oid = int(time.time()) % 100000
            ibkr.placeOrder(oid, c, o)
            self._order_sent = True
            return (f"주문 #{oid}  {o.action} {o.totalQuantity}계약"
                    f" @ LMT {o.lmtPrice:.2f}")
        except Exception as e:
            return f"주문 오류: {e}"

    def get_price(self) -> dict:
        return dict(self._price)

    def tick_10s(self) -> int:
        if self._tick_q is None: return 0
        cutoff = time.time() - 10
        return sum(1 for t in self._tick_q if t >= cutoff)

    def _ibkr(self):
        try: return self.mw.api
        except AttributeError: return None


# ══════════════════════════════════════════════════════════════
# UI 패널 — 시안 B (3컬럼)
# ══════════════════════════════════════════════════════════════
class ConditionPanel(QWidget):

    def __init__(self, mw, parent=None):
        super().__init__(parent)
        self._mon      = _Monitor(mw)
        self._log_lines = []
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")
        self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    # ── 빌드 ─────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # ════ 3컬럼 그리드 ════
        cols = QHBoxLayout(); cols.setSpacing(0)

        cols.addWidget(self._build_col_cond())
        cols.addWidget(_vsep())
        cols.addWidget(self._build_col_live())
        cols.addWidget(_vsep())
        cols.addWidget(self._build_col_order())

        root.addLayout(cols)

        # ════ 하단: 버튼 + 로그 ════
        root.addWidget(_sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self.btn_start = QPushButton("🔔 감시 시작")
        self.btn_start.setFixedHeight(26)
        self.btn_start.setStyleSheet(
            "QPushButton{background:#1a6b3c;color:#fff;font-weight:bold;"
            "border:1px solid #2a9b5c;border-radius:4px;padding:2px 10px;}"
            "QPushButton:hover{background:#1e8048;}")
        self.btn_start.clicked.connect(self._on_start)

        self.btn_stop = QPushButton("■ 중지")
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#fff;font-weight:bold;"
            "border:1px solid #9b2a2a;border-radius:4px;padding:2px 10px;}"
            "QPushButton:hover{background:#801e1e;}")
        self.btn_stop.clicked.connect(self._on_stop)

        self.lbl_status = QLabel("● STOPPED")
        self.lbl_status.setStyleSheet(
            f"color:{C_DIM}; font-size:11px; font-weight:bold;")

        self.lbl_reason = QLabel("")
        self.lbl_reason.setStyleSheet(
            f"color:{C_GRAY}; font-size:10px;")

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.lbl_status)
        btn_row.addWidget(self.lbl_reason)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # 로그
        self.log_box = QLabel("")
        self.log_box.setTextFormat(Qt.RichText)
        self.log_box.setStyleSheet(
            f"background:#050510; border:1px solid {C_BORDER};"
            f"border-radius:3px; font-size:10px; padding:4px 6px;")
        self.log_box.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.log_box.setWordWrap(True)
        self.log_box.setFixedHeight(62)
        root.addWidget(self.log_box)

    # ── 컬럼 1: 조건 설정 ────────────────────────────────────
    def _build_col_cond(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 4, 8, 4); v.setSpacing(4)

        v.addWidget(_mini_title("조건 설정"))

        # 시간 범위 (KST)
        v.addWidget(_lbl("시간 범위 (KST)"))
        tr = QHBoxLayout(); tr.setSpacing(3)
        self.inp_ts = _inp("10:11", 52); tr.addWidget(self.inp_ts)
        tr.addWidget(_lbl("~"))
        self.inp_te = _inp("10:15", 52); tr.addWidget(self.inp_te)
        tr.addStretch()
        v.addLayout(tr)

        # 틱 임계값
        v.addWidget(_lbl("틱 임계값"))
        tr2 = QHBoxLayout(); tr2.setSpacing(3)
        self.inp_tick = _spin(1, 999, 20, w=52)
        tr2.addWidget(self.inp_tick)
        tr2.addWidget(_lbl("/ 10s 초과"))
        tr2.addStretch()
        v.addLayout(tr2)

        # 행사가
        v.addWidget(_lbl("행사가"))
        sr = QHBoxLayout(); sr.setSpacing(3)
        self.inp_strike = _inp("5200C", 72)
        self.inp_strike.setPlaceholderText("5200C")
        sr.addWidget(self.inp_strike); sr.addStretch()
        v.addLayout(sr)

        v.addWidget(_sep())

        # 현재가 조건 체크박스
        self.chk_price = QCheckBox("현재가 조건 사용")
        self.chk_price.setStyleSheet(
            f"QCheckBox{{color:{C_YELLOW};font-size:11px;font-weight:bold;}}"
            f"QCheckBox::indicator{{width:13px;height:13px;}}"
            f"QCheckBox::indicator:unchecked{{border:1px solid #5a5a1a;"
            f"border-radius:2px;background:#1a1a0a;}}"
            f"QCheckBox::indicator:checked{{border:1px solid {C_YELLOW};"
            f"border-radius:2px;background:#3a3a0a;}}"
        )
        self.chk_price.stateChanged.connect(self._on_price_chk)
        v.addWidget(self.chk_price)

        # 현재가 상세 (기본 숨김)
        self._price_detail = QWidget()
        pd = QVBoxLayout(self._price_detail)
        pd.setContentsMargins(0, 2, 0, 0); pd.setSpacing(3)

        pr = QHBoxLayout(); pr.setSpacing(3)
        self.sel_price_op = QComboBox()
        self.sel_price_op.addItems(["이상", "이하", "범위"])
        self.sel_price_op.setFixedWidth(52); self.sel_price_op.setFixedHeight(22)
        self.sel_price_op.setStyleSheet(SS_INPUT)
        self.sel_price_op.currentTextChanged.connect(self._on_price_op)
        pr.addWidget(self.sel_price_op)

        self.inp_pv1 = _spin(0.01, 9999, 1.00, w=60, decimals=2, step=0.05)
        pr.addWidget(self.inp_pv1)
        self._lbl_tilde = _lbl("~")
        self.inp_pv2 = _spin(0.01, 9999, 2.00, w=60, decimals=2, step=0.05)
        pr.addWidget(self._lbl_tilde); pr.addWidget(self.inp_pv2)
        pr.addStretch()
        pd.addLayout(pr)

        self._lbl_tilde.hide(); self.inp_pv2.hide()
        self._price_detail.hide()
        v.addWidget(self._price_detail)

        v.addStretch(1)
        return w

    # ── 컬럼 2: 실시간 현황 ──────────────────────────────────
    def _build_col_live(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 8, 4); v.setSpacing(4)

        v.addWidget(_mini_title("실시간 현황"))

        # BID / LAST / ASK 카드 (우측 상단 배치)
        card_row = QHBoxLayout(); card_row.setSpacing(4)
        for key, label in [("bid", "BID"), ("last", "LAST"), ("ask", "ASK")]:
            card = QWidget()
            card.setStyleSheet(
                f"background:{C_PANEL}; border:1px solid {C_BORDER};"
                f"border-radius:4px;")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(4, 3, 4, 3); cv.setSpacing(1)
            l1 = QLabel(label)
            l1.setStyleSheet(f"color:{C_DIM}; font-size:9px;")
            l1.setAlignment(Qt.AlignCenter)
            l2 = QLabel("—")
            l2.setStyleSheet(
                f"color:{C_GREEN}; font-size:14px; font-weight:bold;")
            l2.setAlignment(Qt.AlignCenter)
            cv.addWidget(l1); cv.addWidget(l2)
            setattr(self, f"lv_{key}", l2)
            card_row.addWidget(card)
        v.addLayout(card_row)

        # 틱 속도 게이지
        v.addWidget(_lbl("틱 속도 (10s)"))
        gr = QHBoxLayout(); gr.setSpacing(5)
        self.lv_tick = QLabel("0")
        self.lv_tick.setFixedWidth(28)
        self.lv_tick.setStyleSheet(
            f"color:{C_TEAL}; font-size:13px; font-weight:bold;")
        gr.addWidget(self.lv_tick)

        self._gauge_bg = QFrame()
        self._gauge_bg.setFixedHeight(8)
        self._gauge_bg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._gauge_bg.setStyleSheet(
            f"background:{C_PANEL}; border-radius:4px;"
            f"border:1px solid {C_BORDER};")
        self._gauge_fill = QFrame(self._gauge_bg)
        self._gauge_fill.setFixedHeight(8)
        self._gauge_fill.setStyleSheet(
            f"background:{C_TEAL}; border-radius:4px; border:none;")
        self._gauge_fill.setFixedWidth(0)
        gr.addWidget(self._gauge_bg, 1)
        v.addLayout(gr)

        # ET 시간 표시 (참고용)
        self.lbl_et_range = QLabel("")
        self.lbl_et_range.setStyleSheet(
            f"color:{C_DIM}; font-size:10px;")
        v.addWidget(self.lbl_et_range)

        v.addStretch(1)
        return w

    # ── 컬럼 3: 자동 주문 ────────────────────────────────────
    def _build_col_order(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 4, 4, 4); v.setSpacing(4)

        v.addWidget(_mini_title("자동 주문"))

        self.chk_auto = QCheckBox("조건 충족 시 자동 주문")
        self.chk_auto.setStyleSheet(
            f"QCheckBox{{color:{C_TEXT};font-size:11px;}}"
            f"QCheckBox::indicator{{width:13px;height:13px;}}"
            f"QCheckBox::indicator:unchecked{{border:1px solid {C_DIM};"
            f"border-radius:2px;background:{C_PANEL};}}"
            f"QCheckBox::indicator:checked{{border:1px solid {C_BLUE};"
            f"border-radius:2px;background:#0a1a3a;}}"
        )
        v.addWidget(self.chk_auto)

        # 수량
        qr = QHBoxLayout(); qr.setSpacing(4)
        qr.addWidget(_lbl("수량"))
        self.inp_qty = _spin(1, 99, 1, w=50)
        qr.addWidget(self.inp_qty)
        qr.addWidget(_lbl("계약"))
        qr.addStretch()
        v.addLayout(qr)

        # 방향 / 유형
        dr = QHBoxLayout(); dr.setSpacing(4)
        self.sel_side = QComboBox()
        self.sel_side.addItems(["BUY", "SELL"])
        self.sel_side.setFixedWidth(58); self.sel_side.setFixedHeight(22)
        self.sel_side.setStyleSheet(SS_INPUT)
        dr.addWidget(self.sel_side); dr.addStretch()
        v.addLayout(dr)

        v.addWidget(_sep())

        # 지정가 체크박스
        self.chk_limit = QCheckBox("지정가 사용")
        self.chk_limit.setStyleSheet(
            f"QCheckBox{{color:{C_YELLOW};font-size:11px;font-weight:bold;}}"
            f"QCheckBox::indicator{{width:13px;height:13px;}}"
            f"QCheckBox::indicator:unchecked{{border:1px solid #5a5a1a;"
            f"border-radius:2px;background:#1a1a0a;}}"
            f"QCheckBox::indicator:checked{{border:1px solid {C_YELLOW};"
            f"border-radius:2px;background:#3a3a0a;}}"
        )
        self.chk_limit.stateChanged.connect(self._on_limit_chk)
        v.addWidget(self.chk_limit)

        # 지정가 입력 (기본 숨김)
        self._limit_detail = QWidget()
        ld = QHBoxLayout(self._limit_detail)
        ld.setContentsMargins(0, 2, 0, 0); ld.setSpacing(4)
        self.inp_limit = _spin(0.01, 9999, 1.00, w=72, decimals=2, step=0.05)
        ld.addWidget(self.inp_limit)
        ld.addWidget(_lbl("USD"))
        ld.addStretch()
        self._limit_detail.hide()
        v.addWidget(self._limit_detail)

        # 안내 텍스트
        self.lbl_limit_hint = QLabel("미체크: Last + 0.05 자동")
        self.lbl_limit_hint.setStyleSheet(
            f"color:{C_DIM}; font-size:10px;")
        v.addWidget(self.lbl_limit_hint)

        v.addStretch(1)
        return w

    # ── 체크박스 핸들러 ──────────────────────────────────────
    def _on_price_chk(self, state: int):
        self._price_detail.setVisible(bool(state))

    def _on_price_op(self, op: str):
        is_range = (op == "범위")
        self._lbl_tilde.setVisible(is_range)
        self.inp_pv2.setVisible(is_range)

    def _on_limit_chk(self, state: int):
        self._limit_detail.setVisible(bool(state))
        self.lbl_limit_hint.setVisible(not bool(state))

    # ── 설정 수집 ─────────────────────────────────────────────
    def _get_cfg(self) -> dict:
        return {
            "time_start":    self.inp_ts.text().strip() or "09:30",
            "time_end":      self.inp_te.text().strip() or "16:00",
            "tick_thresh":   self.inp_tick.value(),
            "strike":        self.inp_strike.text().strip().upper(),
            "price_enabled": self.chk_price.isChecked(),
            "price_op":      self.sel_price_op.currentText(),
            "price_val1":    self.inp_pv1.value(),
            "price_val2":    self.inp_pv2.value(),
            "auto_order":    self.chk_auto.isChecked(),
            "order_qty":     self.inp_qty.value(),
            "order_side":    self.sel_side.currentText(),
            "limit_enabled": self.chk_limit.isChecked(),
            "limit_price":   self.inp_limit.value(),
        }

    # ── 시작 / 중지 ───────────────────────────────────────────
    def _on_start(self):
        cfg = self._get_cfg()
        if not cfg["strike"]:
            self._log("⚠ 행사가를 입력하세요", warn=True); return

        self._mon.running     = True
        self._mon._order_sent = False
        self._mon.unsubscribe()
        self._mon.subscribe(cfg["strike"])
        self._set_status("WATCHING")

        # ET 환산 표시
        et_s = _kst_str_to_et_str(cfg["time_start"])
        et_e = _kst_str_to_et_str(cfg["time_end"])
        self.lbl_et_range.setText(f"ET: {et_s} ~ {et_e}")

        price_info = ""
        if cfg["price_enabled"]:
            price_info = (f"  현재가 {cfg['price_op']} "
                          f"{cfg['price_val1']:.2f}")
            if cfg["price_op"] == "범위":
                price_info += f"~{cfg['price_val2']:.2f}"

        lmt_info = (f"  지정가={cfg['limit_price']:.2f}"
                    if cfg["limit_enabled"] else "  Last+0.05")

        self._log(
            f"▶ 시작: {cfg['strike']}  틱>{cfg['tick_thresh']}"
            f"  {cfg['time_start']}~{cfg['time_end']}(KST)"
            f"{price_info}{lmt_info}")

    def _on_stop(self):
        self._mon.running = False
        self._mon.unsubscribe()
        self.lbl_et_range.setText("")
        self._set_status("STOPPED")
        self._log("■ 감시 중지", warn=True)

    # ── 1초 폴링 ─────────────────────────────────────────────
    def _tick(self):
        cfg   = self._get_cfg()
        price = self._mon.get_price()
        tick  = self._mon.tick_10s()

        # 가격 카드
        for key in ("bid", "last", "ask"):
            v   = price[key]
            lbl = getattr(self, f"lv_{key}")
            lbl.setText(f"{v:.2f}" if v > 0 else "—")
            lbl.setStyleSheet(
                f"color:{C_GREEN}; font-size:14px; font-weight:bold;"
                if v > 0 else
                f"color:{C_DIM}; font-size:14px; font-weight:bold;")

        # 틱 게이지
        thresh  = max(cfg["tick_thresh"], 1)
        pct     = min(tick / (thresh * 2), 1.0)
        g_color = (C_RED    if tick > thresh * 2 else
                   C_ORANGE if tick > thresh      else C_TEAL)
        self.lv_tick.setText(str(tick))
        self.lv_tick.setStyleSheet(
            f"color:{g_color}; font-size:13px; font-weight:bold;")
        w = int(self._gauge_bg.width() * pct)
        self._gauge_fill.setFixedWidth(max(w, 0))
        self._gauge_fill.setStyleSheet(
            f"background:{g_color}; border-radius:4px; border:none;")

        if not self._mon.running:
            return

        # 조건 검사
        triggered, tick_10s, reason = self._mon.check(cfg)
        self.lbl_reason.setText(
            reason if reason not in ("OK", "", None) else "")

        if triggered:
            self._set_status("TRIGGERED")
            self._log(
                f"🔔 조건 충족! 틱={tick_10s}  "
                f"Last={price['last']:.2f}  {cfg['strike']}", warn=True)
            _play_alert()
            if cfg["auto_order"] and not self._mon._order_sent:
                result = self._mon.place_order(cfg)
                self._log(f"📋 {result}")

    # ── 상태 뱃지 ─────────────────────────────────────────────
    def _set_status(self, status: str):
        s = {
            "WATCHING":  (f"color:{C_BLUE}; font-size:11px; font-weight:bold;",
                          "● WATCHING"),
            "TRIGGERED": (f"color:{C_RED};  font-size:12px; font-weight:bold;",
                          "🔔 TRIGGERED"),
            "STOPPED":   (f"color:{C_DIM};  font-size:11px; font-weight:bold;",
                          "● STOPPED"),
        }
        ss, txt = s.get(status, s["STOPPED"])
        self.lbl_status.setStyleSheet(ss)
        self.lbl_status.setText(txt)

    # ── 로그 ─────────────────────────────────────────────────
    def _log(self, msg: str, warn: bool = False):
        ts    = datetime.now().strftime("%H:%M:%S")
        color = C_ORANGE if warn else C_GREEN
        self._log_lines.append(
            f'<span style="color:{color}">[{ts}] {msg}</span>')
        self._log_lines = self._log_lines[-4:]
        self.log_box.setText("<br>".join(self._log_lines))


# ══════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════
def build_condition_panel(mw) -> QWidget:
    """chart_build_main.py 에서 호출."""
    return ConditionPanel(mw)


def stop_condition_monitor(panel_widget: QWidget):
    """RT 중지 / 탭 전환 시 호출."""
    try:
        panel_widget._mon.unsubscribe()
        panel_widget._mon.running = False
    except Exception:
        pass


# ── 알림음 ───────────────────────────────────────────────────
def _play_alert():
    try:
        if ALERT_SOUND.exists():
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(str(ALERT_SOUND)); return
            except Exception:
                pass
            try:
                import playsound
                playsound.playsound(str(ALERT_SOUND), block=False); return
            except Exception:
                pass
        print("\a", end="", flush=True)
    except Exception:
        pass