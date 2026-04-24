"""
SPX 0DTE Option  1분봉 히스토리 Fetcher  v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· ibapi (공식 TWS API)  /  IB Gateway 포트 4001
· 만기일 16:15 ET 자동 실행 + 수동 버튼
· ATM ±100pt 행사가 범위 (5pt 간격)
· 당일 / +1영업일 / +2영업일 만기 옵션
· reqHistoricalData → 1분봉 OHLCV 전체
· CSV 컬럼:
    expiry, strike, right, datetime,
    open, high, low, close, volume
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[v3 수정]
· req_id 전역 카운터로 변경 → 만기 간 reqId 충돌 방지
· 빈 응답(데이터 없음)도 정상 처리
· 에러 코드별 상세 로그
· 장 마감 후 테스트: useRTH=1 로 자동 전환
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys, os, csv, threading, time
from datetime import datetime, timedelta
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo
    except ImportError:
        import pytz as _pytz
        class ZoneInfo:
            def __new__(cls, key): return _pytz.timezone(key)

# ── PyQt5 ─────────────────────────────────────
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget,
        QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit,
        QGroupBox, QStatusBar, QProgressBar, QFrame,
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
    from PyQt5.QtGui import QFont
except ModuleNotFoundError:
    print("[오류] PyQt5 미설치: pip install PyQt5")
    sys.exit(1)

# ── ibapi ─────────────────────────────────────
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    IBAPI_OK = True
except ModuleNotFoundError:
    IBAPI_OK = False

# ═══════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════
TWS_HOST     = "127.0.0.1"
TWS_PORT     = 4001          # IB Gateway: 4001 / TWS: 7497
CLIENT_ID    = 15            # core.py(1) 와 겹치지 않게

STRIKE_RANGE = 100           # ATM ± pt
STRIKE_STEP  = 5
ET_TZ        = ZoneInfo("America/New_York")
AUTO_HOUR    = 16
AUTO_MIN     = 15

OUTPUT_DIR   = Path("/home/netforce/US_Data/Data/SPX_0DTE")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# reqId — 8100부터 시작하는 전역 카운터 (만기 간 충돌 방지)
REQ_UND_ID   = 8001
REQ_HIST_START = 8100        # 히스토리 reqId 시작값

BAR_SIZE     = "1 min"
WHAT_TO_SHOW = "TRADES"


# ═══════════════════════════════════════════════
# 신호 (스레드 → Qt)
# ═══════════════════════════════════════════════
class Sig(QObject):
    log      = pyqtSignal(str)
    status   = pyqtSignal(str)
    progress = pyqtSignal(int)
    done     = pyqtSignal(str)
    err      = pyqtSignal(str)


# ═══════════════════════════════════════════════
# IBapi 래퍼
# ═══════════════════════════════════════════════
if IBAPI_OK:
    class _IBApp(EWrapper, EClient):
        def __init__(self):
            EWrapper.__init__(self)
            EClient.__init__(self, self)

            self.und_price: float = 0.0
            self.und_ready        = threading.Event()

            # 히스토리 버퍼 — reqId 키
            self.hist_buf:    dict = {}   # reqId → [bar, ...]
            self.hist_events: dict = {}   # reqId → Event
            self.hist_error:  dict = {}   # reqId → str

        # ── SPX 현재가 ────────────────────────
        def tickPrice(self, reqId, tickType, price, attrib):
            if reqId != REQ_UND_ID:
                return
            if price and price > 0:
                if tickType == 4:
                    self.und_price = price
                    self.und_ready.set()
                elif tickType in (1, 2) and not self.und_price:
                    self.und_price = price
                    self.und_ready.set()
                elif tickType == 9 and not self.und_price:
                    self.und_price = price
                    self.und_ready.set()

        # ── 히스토리 bar 수신 ─────────────────
        def historicalData(self, reqId, bar):
            if reqId not in self.hist_buf:
                self.hist_buf[reqId] = []
            self.hist_buf[reqId].append({
                "datetime": bar.date,
                "open":     bar.open,
                "high":     bar.high,
                "low":      bar.low,
                "close":    bar.close,
                "volume":   int(bar.volume),
            })

        def historicalDataEnd(self, reqId, start, end):
            if reqId in self.hist_events:
                self.hist_events[reqId].set()

        # ── 에러 ──────────────────────────────
        def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
            if errorCode in (2104, 2106, 2158, 2119):
                return
            print(f"[IBKR] reqId={reqId} code={errorCode} {errorString}")
            if reqId in self.hist_events:
                self.hist_error[reqId] = f"[{errorCode}] {errorString}"
                self.hist_events[reqId].set()

        def connectionClosed(self):
            print("[IBKR] 연결 끊김")


# ═══════════════════════════════════════════════
# 조회 엔진
# ═══════════════════════════════════════════════
class Fetcher:
    def __init__(self, sig: Sig):
        self.sig    = sig
        self.app: "_IBApp | None" = None
        self._req_id = REQ_HIST_START   # ← 전역 카운터 (리셋 안 함)

    def _next_req_id(self) -> int:
        rid = self._req_id
        self._req_id += 1
        return rid

    # ── 연결 ──────────────────────────────────
    def connect(self):
        if not IBAPI_OK:
            raise RuntimeError("ibapi 미설치: pip install ibapi")
        self.app = _IBApp()
        self._req_id = REQ_HIST_START   # 재연결 시 리셋
        self.app.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
        threading.Thread(target=self.app.run, daemon=True).start()
        time.sleep(1.5)
        if not self.app.isConnected():
            raise ConnectionError(f"IBKR 연결 실패 ({TWS_HOST}:{TWS_PORT})")
        self.sig.log.emit(f"[연결] IBKR 연결 성공 ({TWS_HOST}:{TWS_PORT})")

    def disconnect(self):
        if self.app and self.app.isConnected():
            self.app.disconnect()
            self.sig.log.emit("[연결] IBKR 연결 해제")

    # ── SPX 현재가 ────────────────────────────
    def get_spx_price(self) -> float:
        c = Contract()
        c.symbol   = "SPX"
        c.secType  = "IND"
        c.exchange = "CBOE"
        c.currency = "USD"
        self.app.und_price = 0.0
        self.app.und_ready.clear()
        self.app.reqMktData(REQ_UND_ID, c, "", False, False, [])
        ok = self.app.und_ready.wait(timeout=15)
        self.app.cancelMktData(REQ_UND_ID)
        time.sleep(0.3)
        if not ok or not self.app.und_price:
            raise ValueError(
                "SPX 현재가 수신 실패\n"
                "→ 시장 마감이거나 IBKR 시세 구독 미설정"
            )
        p = self.app.und_price
        self.sig.log.emit(f"[시세] SPX 현재가: {p:.2f}")
        return p

    # ── 영업일 만기 목록 ──────────────────────
    def expiry_dates(self) -> list:
        today = datetime.now(ET_TZ).date()
        result, d = [], today
        while len(result) < 3:
            if d.weekday() < 5:
                result.append(d.strftime("%Y%m%d"))
            d += timedelta(days=1)
        return result

    # ── 옵션 계약 생성 ─────────────────────────
    @staticmethod
    def _contract(strike: int, right: str, expiry: str) -> Contract:
        c = Contract()
        c.symbol       = "SPX"
        c.secType      = "OPT"
        c.exchange     = "SMART"
        c.currency     = "USD"
        c.lastTradeDateOrContractMonth = expiry
        c.strike       = float(strike)
        c.right        = right
        c.multiplier   = "100"
        c.tradingClass = "SPXW"
        return c

    # ── 만기 하루치 1분봉 조회 ─────────────────
    def fetch_expiry(self, expiry: str, atm: float) -> list:
        lo      = int((atm - STRIKE_RANGE) / STRIKE_STEP) * STRIKE_STEP
        hi      = int((atm + STRIKE_RANGE) / STRIKE_STEP) * STRIKE_STEP + STRIKE_STEP
        strikes = list(range(lo, hi + 1, STRIKE_STEP))
        total   = len(strikes) * 2
        self.sig.log.emit(
            f"[조회] {expiry} | {lo}~{hi} "
            f"({len(strikes)}행사가 × 2 = {total}계약)"
        )

        # endDateTime: 만기일 16:15 ET → UTC 변환 (IBKR 권장 형식)
        from datetime import timezone
        naive = datetime.strptime(f"{expiry} 16:15:00", "%Y%m%d %H:%M:%S")
        et    = naive.replace(tzinfo=ET_TZ)
        utc   = et.astimezone(timezone.utc)
        end_dt = utc.strftime("%Y%m%d-%H:%M:%S")  # UTC: yyyymmdd-hh:mm:ss
        rows       = []
        skip_cnt   = 0
        empty_cnt  = 0

        for strike in strikes:
            for right in ("C", "P"):
                contract = self._contract(strike, right, expiry)
                rid      = self._next_req_id()   # ← 매번 새 reqId

                ev = threading.Event()
                self.app.hist_buf[rid]    = []
                self.app.hist_events[rid] = ev
                self.app.hist_error.pop(rid, None)

                self.app.reqHistoricalData(
                    rid,
                    contract,
                    end_dt,
                    "1 D",
                    BAR_SIZE,
                    WHAT_TO_SHOW,
                    1,       # useRTH=1: 정규장 (09:30~16:15)
                    1,       # formatDate=1: 문자열
                    False,
                    [],
                )

                ev.wait(timeout=30)

                bars = self.app.hist_buf.pop(rid, [])
                err  = self.app.hist_error.pop(rid, None)
                self.app.hist_events.pop(rid, None)

                if err:
                    skip_cnt += 1
                    self.sig.log.emit(
                        f"  [스킵] {strike}{'C' if right=='C' else 'P'} → {err}"
                    )
                elif not bars:
                    empty_cnt += 1
                else:
                    for bar in bars:
                        rows.append({
                            "expiry":   expiry,
                            "strike":   strike,
                            "right":    "Call" if right == "C" else "Put",
                            "datetime": bar["datetime"],
                            "open":     bar["open"],
                            "high":     bar["high"],
                            "low":      bar["low"],
                            "close":    bar["close"],
                            "volume":   bar["volume"],
                        })

                time.sleep(0.2)   # pacing: 60req/10sec 제한

        self.sig.log.emit(
            f"  → {expiry} 완료: {len(rows)}행 "
            f"(스킵={skip_cnt} 빈응답={empty_cnt})"
        )
        return rows

    # ── 전체 실행 ─────────────────────────────
    def run(self):
        try:
            self.connect()
            self.sig.progress.emit(10)

            atm      = self.get_spx_price()
            self.sig.progress.emit(20)

            expiries = self.expiry_dates()
            self.sig.log.emit(f"[만기일] {', '.join(expiries)}")

            all_rows = []
            for i, exp in enumerate(expiries):
                self.sig.status.emit(f"조회 중: {exp} ({i+1}/3)...")
                rows = self.fetch_expiry(exp, atm)
                all_rows.extend(rows)
                self.sig.progress.emit(30 + i * 22)

            # ── CSV 저장 ──────────────────────
            ts       = datetime.now(ET_TZ).strftime("%Y%m%d_%H%M%S")
            filepath = OUTPUT_DIR / f"SPX_0DTE_1min_{ts}.csv"
            fields   = [
                "expiry", "strike", "right",
                "datetime", "open", "high", "low", "close", "volume"
            ]
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(all_rows)

            self.sig.progress.emit(100)
            self.sig.log.emit(f"[완료] 총 {len(all_rows)}행 저장")
            self.sig.log.emit(f"[파일] {filepath}")
            self.sig.done.emit(str(filepath))

        except Exception as e:
            self.sig.err.emit(str(e))
            self.sig.log.emit(f"[오류] {e}")
        finally:
            self.disconnect()
            self.sig.progress.emit(0)


# ═══════════════════════════════════════════════
# 메인 GUI
# ═══════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.sig        = Sig()
        self.fetcher    = Fetcher(self.sig)
        self.timer      = QTimer(self)
        self.running    = False
        self._auto_done = None

        self._ui()
        self._bind()
        self._sched_start()

    def _ui(self):
        self.setWindowTitle("SPX 0DTE  1분봉 Fetcher  v3  ·  IBKR")
        self.setMinimumSize(840, 660)

        root = QWidget(); self.setCentralWidget(root)
        vb = QVBoxLayout(root)
        vb.setSpacing(10); vb.setContentsMargins(12, 12, 12, 8)

        info = QGroupBox("설정 정보")
        hl   = QHBoxLayout(info)
        for title, val, col in [
            ("포트",       f"{TWS_PORT}",             "#00bcd4"),
            ("ClientID",  f"{CLIENT_ID}",             "#00bcd4"),
            ("행사가 범위", f"ATM ±{STRIKE_RANGE}pt", "#00bcd4"),
            ("데이터",     "1분봉 OHLCV",             "#00e676"),
            ("자동 실행",  f"{AUTO_HOUR:02d}:{AUTO_MIN:02d} ET", "#ffa726"),
            ("저장 경로",   str(OUTPUT_DIR),           "#888"),
        ]:
            fr = QFrame(); fl = QVBoxLayout(fr); fl.setSpacing(1)
            tl = QLabel(title); tl.setStyleSheet("color:#888;font-size:10px;")
            vl = QLabel(val);   vl.setStyleSheet(
                f"color:{col};font-size:12px;font-weight:bold;"
            )
            vl.setWordWrap(True)
            fl.addWidget(tl); fl.addWidget(vl); hl.addWidget(fr)
        vb.addWidget(info)

        self.next_lbl = QLabel("다음 자동 실행: 계산 중...")
        self.next_lbl.setAlignment(Qt.AlignCenter)
        self.next_lbl.setStyleSheet(
            "color:#ffa726;font-size:12px;padding:5px;"
            "background:#1e1e1e;border-radius:4px;"
        )
        vb.addWidget(self.next_lbl)

        br = QHBoxLayout()
        self.btn_fetch = QPushButton("▶  지금 즉시 조회")
        self.btn_fetch.setFixedHeight(46)
        self.btn_fetch.setStyleSheet("""
            QPushButton{background:#1976d2;color:white;border-radius:6px;
                        font-size:14px;font-weight:bold;}
            QPushButton:hover{background:#1565c0;}
            QPushButton:disabled{background:#444;color:#777;}
        """)
        self.btn_dir = QPushButton("📁  저장 폴더 열기")
        self.btn_dir.setFixedHeight(46)
        self.btn_dir.setStyleSheet("""
            QPushButton{background:#2e7d32;color:white;
                        border-radius:6px;font-size:13px;}
            QPushButton:hover{background:#1b5e20;}
        """)
        self.btn_clr = QPushButton("🗑  로그 지우기")
        self.btn_clr.setFixedHeight(46)
        self.btn_clr.setStyleSheet("""
            QPushButton{background:#424242;color:#ccc;
                        border-radius:6px;font-size:13px;}
            QPushButton:hover{background:#616161;}
        """)
        br.addWidget(self.btn_fetch, 3)
        br.addWidget(self.btn_dir,   2)
        br.addWidget(self.btn_clr,   1)
        vb.addLayout(br)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setFixedHeight(10)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet("""
            QProgressBar{border-radius:5px;background:#333;}
            QProgressBar::chunk{background:#1976d2;border-radius:5px;}
        """)
        vb.addWidget(self.pbar)

        lg = QGroupBox("실행 로그")
        ll = QVBoxLayout(lg)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 10))
        self.log.setStyleSheet("background:#0d0d0d;color:#b0bec5;border:none;")
        ll.addWidget(self.log)
        vb.addWidget(lg, 1)

        self.sb = QStatusBar()
        self.setStatusBar(self.sb)
        self.sb.showMessage("대기 중")

        self.setStyleSheet("""
            QMainWindow,QWidget{background:#1a1a2e;color:#e0e0e0;}
            QGroupBox{border:1px solid #333;border-radius:6px;
                      margin-top:8px;font-size:11px;color:#666;}
            QGroupBox::title{subcontrol-origin:margin;left:8px;}
            QStatusBar{background:#111;color:#555;}
        """)

        if not IBAPI_OK:
            self._log("[경고] ibapi 미설치 → pip install ibapi")
            self.btn_fetch.setEnabled(False)
            self.btn_fetch.setText("⚠  ibapi 미설치")

    def _bind(self):
        self.sig.log.connect(self._log)
        self.sig.status.connect(self.sb.showMessage)
        self.sig.progress.connect(self.pbar.setValue)
        self.sig.done.connect(self._on_done)
        self.sig.err.connect(self._on_err)
        self.btn_fetch.clicked.connect(self._manual)
        self.btn_dir.clicked.connect(self._open_dir)
        self.btn_clr.clicked.connect(self.log.clear)

    def _sched_start(self):
        self.timer.timeout.connect(self._tick)
        self.timer.start(30_000)
        self._tick()

    def _tick(self):
        now = datetime.now(ET_TZ)
        s   = now.strftime("%Y%m%d")
        tgt = now.replace(hour=AUTO_HOUR, minute=AUTO_MIN, second=0, microsecond=0)
        if now >= tgt:
            tgt += timedelta(days=1)
        diff   = tgt - now
        h, rem = divmod(int(diff.total_seconds()), 3600)
        m      = rem // 60
        self.next_lbl.setText(
            f"다음 자동 실행: {tgt.strftime('%m/%d %H:%M')} ET  (약 {h}시간 {m}분 후)"
        )
        if (now.weekday() < 5
                and now.hour   == AUTO_HOUR
                and now.minute == AUTO_MIN
                and self._auto_done != s
                and not self.running):
            self._auto_done = s
            self._log("[자동] 만기 시간 도달 → 자동 조회 시작")
            self._go()

    def _manual(self):
        if self.running: return
        self._log("[수동] 수동 조회 시작")
        self._go()

    def _go(self):
        self.running = True
        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("⏳  조회 중...")
        self.sb.showMessage("IBKR 연결 중...")
        threading.Thread(target=self.fetcher.run, daemon=True).start()

    def _on_done(self, path: str):
        self.running = False
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("▶  지금 즉시 조회")
        self.sb.showMessage(f"완료 → {os.path.basename(path)}")

    def _on_err(self, msg: str):
        self.running = False
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("▶  지금 즉시 조회")
        self.sb.showMessage(f"오류: {msg}")

    def _log(self, msg: str):
        ts = datetime.now(ET_TZ).strftime("%H:%M:%S ET")
        self.log.append(f"[{ts}]  {msg}")
        self.log.ensureCursorVisible()

    def _open_dir(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        p = str(OUTPUT_DIR)
        if   sys.platform == "win32":  os.startfile(p)
        elif sys.platform == "darwin": os.system(f'open "{p}"')
        else:                          os.system(f'xdg-open "{p}"')


# ═══════════════════════════════════════════════
# 진입점
# ═══════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SPX 0DTE 1분봉 Fetcher")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
