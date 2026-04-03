# tab_spx_history.py  — 탭11: SPX 히스토리 옵션 데이터 (당일 마감 기준)
# v1.0  |  ITM/OTM 구분 · Polygon.io REST + IBKR fallback
# ---------------------------------------------------------------
#  main.py 에 추가:
#    from tab_spx_history import SpxHistoryGrid
#    self.tabs.addTab(SpxHistoryGrid(self), "📜 SPX 히스토리")
# ---------------------------------------------------------------

from __future__ import annotations

import os
import threading
import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QPushButton, QComboBox, QGroupBox,
    QProgressBar, QAbstractItemView, QLineEdit,
    QCheckBox, QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QColor, QFont

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── core 상수 (없으면 기본값) ──────────────────────────────────────
try:
    from core import POLYGON_API_KEY, APP_FONT_SIZE, DARK_STYLE
except ImportError:
    POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")
    APP_FONT_SIZE   = 13
    DARK_STYLE      = False

# ── IBKR wrapper (없으면 None) ─────────────────────────────────────
try:
    from core import make_opt_contract          # noqa: F401
    HAS_IBKR = True
except ImportError:
    HAS_IBKR = False


# ══════════════════════════════════════════════════════════════════
#  내부 시그널 브리지
# ══════════════════════════════════════════════════════════════════
class _Bridge(QObject):
    und_ready   = pyqtSignal(float)          # SPX 현재가 수신
    opts_ready  = pyqtSignal(list)           # 옵션 체인 수신 → list[dict]
    error_msg   = pyqtSignal(str)


# ══════════════════════════════════════════════════════════════════
#  Polygon.io 워커 (백그라운드 스레드)
# ══════════════════════════════════════════════════════════════════
class _PolygonWorker(QThread):
    """
    1) SPX 당일 종가  →  Polygon /v2/aggs/ticker/I:SPX/...
    2) SPX 옵션 체인  →  Polygon /v3/snapshot/options/SPX  (만기=today)
    """

    def __init__(self, api_key: str, trade_date: str, bridge: _Bridge):
        super().__init__()
        self._key   = api_key
        self._date  = trade_date   # YYYY-MM-DD
        self._bridge = bridge

    def run(self):
        if not HAS_REQUESTS:
            self._bridge.error_msg.emit("requests 패키지가 없습니다. pip install requests")
            return
        if not self._key:
            self._bridge.error_msg.emit("Polygon API 키 없음 (stock_api_key 파일 또는 환경변수 POLYGON_API_KEY)")
            return

        # ── 1. SPX 종가 ──────────────────────────────────────────
        spx_close = self._fetch_spx_close()
        if spx_close is not None:
            self._bridge.und_ready.emit(spx_close)

        # ── 2. 옵션 체인 ─────────────────────────────────────────
        rows = self._fetch_option_chain(spx_close)
        self._bridge.opts_ready.emit(rows)

    # ── SPX 일봉 종가 ─────────────────────────────────────────────
    def _fetch_spx_close(self) -> Optional[float]:
        url = (
            f"https://api.polygonio.com/v2/aggs/ticker/I:SPX/range/1/day"
            f"/{self._date}/{self._date}"
            f"?adjusted=true&sort=asc&limit=1&apiKey={self._key}"
        )
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            results = data.get("results", [])
            if results:
                return float(results[0]["c"])
        except Exception as e:
            self._bridge.error_msg.emit(f"SPX 종가 조회 실패: {e}")
        return None

    # ── 옵션 체인 ─────────────────────────────────────────────────
    def _fetch_option_chain(self, spot: Optional[float]) -> list:
        """
        Polygon v3 snapshot → 당일 만기(= self._date) 필터
        """
        url = (
            f"https://api.polygonio.com/v3/snapshot/options/SPX"
            f"?expiration_date={self._date}&limit=250&apiKey={self._key}"
        )
        rows: list[dict] = []
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            results = data.get("results", [])
            for item in results:
                d = item.get("details", {})
                g = item.get("greeks", {})
                day = item.get("day", {})
                quote = item.get("last_quote", {})

                strike = float(d.get("strike_price", 0))
                cp     = d.get("contract_type", "").upper()   # "call" / "put"
                expiry = d.get("expiration_date", "")

                # ITM / OTM 판별
                itm = False
                if spot is not None:
                    if cp == "CALL" and strike < spot:
                        itm = True
                    elif cp == "PUT" and strike > spot:
                        itm = True

                rows.append({
                    "ticker":  d.get("ticker", ""),
                    "type":    cp,
                    "expiry":  expiry,
                    "strike":  strike,
                    "itm":     itm,
                    "bid":     float(quote.get("bid", 0) or 0),
                    "ask":     float(quote.get("ask", 0) or 0),
                    "last":    float(day.get("close", 0) or 0),
                    "volume":  int(day.get("volume", 0) or 0),
                    "oi":      int(item.get("open_interest", 0) or 0),
                    "iv":      float(item.get("implied_volatility", 0) or 0),
                    "delta":   float(g.get("delta", 0) or 0),
                    "gamma":   float(g.get("gamma", 0) or 0),
                    "theta":   float(g.get("theta", 0) or 0),
                    "vega":    float(g.get("vega", 0) or 0),
                })
        except Exception as e:
            self._bridge.error_msg.emit(f"옵션 체인 조회 실패: {e}")

        # 행사가 오름차순 정렬
        rows.sort(key=lambda x: (x["type"], x["strike"]))
        return rows


# ══════════════════════════════════════════════════════════════════
#  메인 탭 위젯
# ══════════════════════════════════════════════════════════════════
class SpxHistoryGrid(QWidget):
    """탭11: SPX 히스토리 옵션 (당일 마감 기준)"""

    # 테이블 컬럼 정의
    _COLS = [
        ("Ticker",  120),
        ("Type",     55),
        ("Strike",   85),
        ("ITM/OTM",  75),
        ("Bid",      70),
        ("Ask",      70),
        ("Last",     70),
        ("Volume",   80),
        ("OI",       80),
        ("IV %",     70),
        ("Delta",    65),
        ("Gamma",    65),
        ("Theta",    65),
        ("Vega",     65),
    ]

    def __init__(self, mw=None):
        super().__init__()
        self._mw      = mw
        self._bridge  = _Bridge()
        self._worker: Optional[_PolygonWorker] = None
        self._spot: Optional[float] = None
        self._all_rows: list[dict] = []

        self._build()
        self._connect_signals()

    # ── UI 빌드 ───────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── 상단 컨트롤 바 ─────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        # 날짜 선택
        lbl_date = QLabel("기준일:")
        lbl_date.setFixedWidth(45)
        self._edit_date = QLineEdit()
        self._edit_date.setFixedWidth(105)
        self._edit_date.setPlaceholderText("YYYY-MM-DD")
        today = datetime.date.today().strftime("%Y-%m-%d")
        self._edit_date.setText(today)

        # 조회 버튼
        self._btn_fetch = QPushButton("📥 조회")
        self._btn_fetch.setFixedWidth(80)
        self._btn_fetch.clicked.connect(self._on_fetch)

        # SPX 현재가 표시
        self._lbl_spot = QLabel("SPX: ----")
        self._lbl_spot.setFixedWidth(150)
        font_spot = QFont()
        font_spot.setBold(True)
        font_spot.setPointSize(APP_FONT_SIZE + 1)
        self._lbl_spot.setFont(font_spot)

        # ITM/OTM 필터
        lbl_filter = QLabel("필터:")
        self._cmb_filter = QComboBox()
        self._cmb_filter.addItems(["전체", "ITM만", "OTM만"])
        self._cmb_filter.setFixedWidth(80)
        self._cmb_filter.currentIndexChanged.connect(self._apply_filter)

        # Call/Put 필터
        self._cmb_cp = QComboBox()
        self._cmb_cp.addItems(["CALL+PUT", "CALL만", "PUT만"])
        self._cmb_cp.setFixedWidth(90)
        self._cmb_cp.currentIndexChanged.connect(self._apply_filter)

        # 행 수 제한
        lbl_limit = QLabel("최대행:")
        self._spin_limit = QSpinBox()
        self._spin_limit.setRange(10, 500)
        self._spin_limit.setValue(100)
        self._spin_limit.setFixedWidth(65)
        self._spin_limit.valueChanged.connect(self._apply_filter)

        # 진행바
        self._prog = QProgressBar()
        self._prog.setRange(0, 0)
        self._prog.setVisible(False)
        self._prog.setFixedHeight(16)
        self._prog.setFixedWidth(120)

        # 상태 레이블
        self._lbl_status = QLabel("대기 중")
        self._lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        ctrl.addWidget(lbl_date)
        ctrl.addWidget(self._edit_date)
        ctrl.addWidget(self._btn_fetch)
        ctrl.addSpacing(12)
        ctrl.addWidget(self._lbl_spot)
        ctrl.addSpacing(12)
        ctrl.addWidget(lbl_filter)
        ctrl.addWidget(self._cmb_filter)
        ctrl.addWidget(self._cmb_cp)
        ctrl.addSpacing(6)
        ctrl.addWidget(lbl_limit)
        ctrl.addWidget(self._spin_limit)
        ctrl.addStretch()
        ctrl.addWidget(self._prog)
        ctrl.addWidget(self._lbl_status)

        root.addLayout(ctrl)

        # ── SPX 정보 패널 ──────────────────────────────────────
        info_box = QGroupBox("SPX 기초자산 정보")
        info_lay = QHBoxLayout(info_box)
        info_lay.setSpacing(20)
        self._lbl_info: dict[str, QLabel] = {}
        for key in ["기준일", "종가", "ITM콜", "OTM콜", "ITM풋", "OTM풋", "총행수"]:
            lbl = QLabel(f"{key}: —")
            lbl.setAlignment(Qt.AlignCenter)
            info_lay.addWidget(lbl)
            self._lbl_info[key] = lbl
        info_box.setFixedHeight(50)
        root.addWidget(info_box)

        # ── 테이블 ─────────────────────────────────────────────
        self._tbl = QTableWidget(0, len(self._COLS))
        headers = [c[0] for c in self._COLS]
        self._tbl.setHorizontalHeaderLabels(headers)
        for i, (_, w) in enumerate(self._COLS):
            self._tbl.setColumnWidth(i, w)
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.verticalHeader().setDefaultSectionSize(22)
        self._tbl.setFont(QFont("", APP_FONT_SIZE))
        root.addWidget(self._tbl)

        # ── 하단 로그 ──────────────────────────────────────────
        self._lbl_log = QLabel("—")
        self._lbl_log.setFixedHeight(22)
        self._lbl_log.setContentsMargins(4, 0, 4, 0)
        self._lbl_log.setStyleSheet("background:#1a1a2e; color:#8888cc; font-size:12px;")
        root.addWidget(self._lbl_log)

    # ── 시그널 연결 ───────────────────────────────────────────────
    def _connect_signals(self):
        self._bridge.und_ready.connect(self._on_und_ready)
        self._bridge.opts_ready.connect(self._on_opts_ready)
        self._bridge.error_msg.connect(self._on_error)

    # ── 조회 버튼 ─────────────────────────────────────────────────
    def _on_fetch(self):
        date_str = self._edit_date.text().strip()
        if not date_str:
            self._log("날짜를 입력하세요 (YYYY-MM-DD)")
            return

        # 날짜 유효성 검사
        try:
            dt = datetime.date.fromisoformat(date_str)
        except ValueError:
            self._log("날짜 형식 오류 — YYYY-MM-DD 로 입력하세요")
            return

        # 영업일 경고 (토·일)
        if dt.weekday() >= 5:
            self._log(f"⚠ {date_str} 은 주말입니다 — 데이터가 없을 수 있습니다")

        # 미래 날짜 경고
        if dt > datetime.date.today():
            self._log("⚠ 미래 날짜는 데이터가 없습니다")
            return

        api_key = self._load_api_key()
        if not api_key:
            self._log("❌ Polygon API 키 없음 — stock_api_key 파일 또는 환경변수 POLYGON_API_KEY")
            return

        # 이미 실행 중이면 종료 대기
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)

        self._btn_fetch.setEnabled(False)
        self._prog.setVisible(True)
        self._lbl_status.setText("조회 중…")
        self._tbl.setRowCount(0)
        self._all_rows = []
        self._spot = None
        self._lbl_spot.setText("SPX: ----")

        self._worker = _PolygonWorker(api_key, date_str, self._bridge)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_worker_done(self):
        self._btn_fetch.setEnabled(True)
        self._prog.setVisible(False)

    # ── 데이터 수신 콜백 ─────────────────────────────────────────
    def _on_und_ready(self, price: float):
        self._spot = price
        self._lbl_spot.setText(f"SPX: {price:,.2f}")
        self._log(f"SPX 종가 수신: {price:,.2f}")

    def _on_opts_ready(self, rows: list):
        self._all_rows = rows
        date_str = self._edit_date.text().strip()
        self._apply_filter()

        # 요약 정보 패널 갱신
        itm_c = sum(1 for r in rows if r["type"] == "CALL" and r["itm"])
        otm_c = sum(1 for r in rows if r["type"] == "CALL" and not r["itm"])
        itm_p = sum(1 for r in rows if r["type"] == "PUT"  and r["itm"])
        otm_p = sum(1 for r in rows if r["type"] == "PUT"  and not r["itm"])

        spot_txt = f"{self._spot:,.2f}" if self._spot else "—"
        self._lbl_info["기준일"].setText(f"기준일: {date_str}")
        self._lbl_info["종가"].setText(f"종가: {spot_txt}")
        self._lbl_info["ITM콜"].setText(f"ITM콜: {itm_c}")
        self._lbl_info["OTM콜"].setText(f"OTM콜: {otm_c}")
        self._lbl_info["ITM풋"].setText(f"ITM풋: {itm_p}")
        self._lbl_info["OTM풋"].setText(f"OTM풋: {otm_p}")
        self._lbl_info["총행수"].setText(f"총: {len(rows)}")

        self._lbl_status.setText(f"완료 ({len(rows)}개)")
        self._log(f"✅ 옵션 {len(rows)}개 로드 완료 — ITM콜:{itm_c} OTM콜:{otm_c} ITM풋:{itm_p} OTM풋:{otm_p}")

    def _on_error(self, msg: str):
        self._log(f"❌ {msg}")
        self._lbl_status.setText("오류")

    # ── 필터 적용 → 테이블 렌더링 ─────────────────────────────────
    def _apply_filter(self):
        rows = self._all_rows

        # ITM/OTM 필터
        itm_sel = self._cmb_filter.currentText()
        if itm_sel == "ITM만":
            rows = [r for r in rows if r["itm"]]
        elif itm_sel == "OTM만":
            rows = [r for r in rows if not r["itm"]]

        # Call/Put 필터
        cp_sel = self._cmb_cp.currentText()
        if cp_sel == "CALL만":
            rows = [r for r in rows if r["type"] == "CALL"]
        elif cp_sel == "PUT만":
            rows = [r for r in rows if r["type"] == "PUT"]

        # 행 수 제한
        limit = self._spin_limit.value()
        rows = rows[:limit]

        self._render_table(rows)

    def _render_table(self, rows: list):
        self._tbl.setRowCount(0)
        self._tbl.setRowCount(len(rows))

        # 색상 정의
        clr_itm_call  = QColor("#1a3a1a")   # 짙은 녹색  — ITM Call
        clr_otm_call  = QColor("#1a1a3a")   # 짙은 청색  — OTM Call
        clr_itm_put   = QColor("#3a1a1a")   # 짙은 적색  — ITM Put
        clr_otm_put   = QColor("#2a2a1a")   # 짙은 황갈  — OTM Put

        clr_itm_badge = QColor("#00cc66")
        clr_otm_badge = QColor("#aaaaaa")
        clr_call_txt  = QColor("#66ccff")
        clr_put_txt   = QColor("#ff8866")

        for row_idx, r in enumerate(rows):
            cp  = r["type"]   # "CALL" / "PUT"
            itm = r["itm"]

            # 행 배경
            if cp == "CALL":
                row_bg = clr_itm_call if itm else clr_otm_call
            else:
                row_bg = clr_itm_put if itm else clr_otm_put

            def _cell(text: str, align=Qt.AlignCenter, bold=False) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setTextAlignment(align | Qt.AlignVCenter)
                item.setBackground(row_bg)
                if bold:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                return item

            # 컬럼 채우기
            col = 0
            # 0: Ticker
            self._tbl.setItem(row_idx, col, _cell(r["ticker"], Qt.AlignLeft)); col += 1

            # 1: Type (Call=파랑, Put=빨강)
            item_cp = _cell(cp, bold=True)
            item_cp.setForeground(clr_call_txt if cp == "CALL" else clr_put_txt)
            item_cp.setBackground(row_bg)
            self._tbl.setItem(row_idx, col, item_cp); col += 1

            # 2: Strike
            self._tbl.setItem(row_idx, col, _cell(f"{r['strike']:,.0f}")); col += 1

            # 3: ITM/OTM 배지
            badge_txt = "ITM" if itm else "OTM"
            item_badge = _cell(badge_txt, bold=True)
            item_badge.setForeground(clr_itm_badge if itm else clr_otm_badge)
            item_badge.setBackground(row_bg)
            self._tbl.setItem(row_idx, col, item_badge); col += 1

            # 4-6: Bid / Ask / Last
            for val_key in ("bid", "ask", "last"):
                v = r[val_key]
                self._tbl.setItem(row_idx, col, _cell(f"{v:.2f}" if v else "—")); col += 1

            # 7: Volume
            vol = r["volume"]
            self._tbl.setItem(row_idx, col, _cell(f"{vol:,}" if vol else "—")); col += 1

            # 8: OI
            oi = r["oi"]
            self._tbl.setItem(row_idx, col, _cell(f"{oi:,}" if oi else "—")); col += 1

            # 9: IV%
            iv = r["iv"]
            self._tbl.setItem(row_idx, col, _cell(f"{iv*100:.1f}%" if iv else "—")); col += 1

            # 10-13: Greeks
            for g_key in ("delta", "gamma", "theta", "vega"):
                gv = r[g_key]
                self._tbl.setItem(row_idx, col, _cell(f"{gv:.4f}" if gv else "—")); col += 1

    # ── 유틸 ──────────────────────────────────────────────────────
    def _load_api_key(self) -> str:
        """우선순위: stock_api_key 파일 → core.POLYGON_API_KEY → 환경변수"""
        key = ""
        # 1. 파일
        key_file = os.path.join(os.path.dirname(__file__), "stock_api_key")
        if os.path.isfile(key_file):
            try:
                with open(key_file, "r") as f:
                    key = f.readline().strip()
            except Exception:
                pass
        # 2. core 상수
        if not key:
            key = POLYGON_API_KEY
        # 3. 환경변수
        if not key:
            key = os.environ.get("POLYGON_API_KEY", "")
        return key

    def _log(self, msg: str):
        self._lbl_log.setText(msg)
        # main_window 로그에도 전달
        if self._mw and hasattr(self._mw, "statusBar"):
            try:
                self._mw.statusBar().showMessage(msg, 5000)
            except Exception:
                pass