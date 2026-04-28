"""
SPX 0DTE Option  1분봉 히스토리 Fetcher  v4.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· ibapi (공식 TWS API)  /  IB Gateway 포트 4001
· 만기일 16:15 ET 자동 실행 + 수동 버튼
· 장 마감 후 프로그램 시작 시 자동 조회 1회
· ATM ±100pt 행사가 범위 (5pt 간격)
· 당일 / +1영업일 / +2영업일 만기 옵션
· reqHistoricalData → 1분봉 OHLCV 전체
· CSV 컬럼:
    expiry, strike, right, datetime,
    open, high, low, close, volume
· 폴더 구조:
    OUTPUT_DIR/
      YYYYMMDD/          ← D+0 (당일 만기)
        D+1/             ← D+1 만기
        D+2/             ← D+2 만기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[v4.1 수정]
· error() — 2107 코드 추가 (HMDS inactive 정보성 메시지)
· error() — reqId=-1 시스템 전반 메시지 별도 분기
· connect() — HMDS 서버 워밍업 딜레이 3초 추가
· fetch_expiry() — 첫 번째 요청 타임아웃 60초로 연장
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
TWS_HOST      = "127.0.0.1"
TWS_PORT      = 4001          # IB Gateway: 4001 / TWS: 7497
CLIENT_ID     = 15
STRIKE_RANGE  = 100           # ATM ± pt
STRIKE_STEP   = 5
ET_TZ         = ZoneInfo("America/New_York")
AUTO_HOUR     = 16
AUTO_MIN      = 15
OUTPUT_DIR    = Path("/home/netforce/US_Data/Data/SPX_0DTE")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REQ_UND_ID     = 8001
REQ_HIST_START = 8100         # 히스토리 reqId 시작값
BAR_SIZE       = "1 min"
WHAT_TO_SHOW   = "TRADES"

# 정보성 에러 코드 (무시 대상)
# 2104: Market data farm connection OK
# 2106: HMDS data farm connection OK
# 2107: HMDS data farm connection inactive (★ v4.1 추가)
# 2119: Market data farm is connecting
# 2158: Sec-def data farm connection OK
INFO_CODES = {2104, 2106, 2107, 2119, 2158}

# 폴더 레이블
EXPIRY_LABELS = ["D+0", "D+1", "D+2"]

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

            # ① 정보성 메시지 — 완전 무시
            if errorCode in INFO_CODES:
                return

            # ② reqId=-1: 특정 요청과 무관한 시스템 전반 상태 메시지
            #    (연결 상태, 팜 서버 알림 등) → 로그만 출력하고 종료
            if reqId == -1:
                print(f"[IBKR 시스템] code={errorCode} {errorString}")
                return

            # ③ 특정 요청에 대한 실제 에러
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
        self.sig     = sig
        self.app: "_IBApp | None" = None
        self._req_id = REQ_HIST_START

    def _next_req_id(self) -> int:
        rid = self._req_id
        self._req_id += 1
        return rid

    # ── 연결 ──────────────────────────────────
    def connect(self):
        if not IBAPI_OK:
            raise RuntimeError("ibapi 미설치: pip install ibapi")
        self.app = _IBApp()
        self._req_id = REQ_HIST_START
        self.app.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
        threading.Thread(target=self.app.run, daemon=True).start()
        time.sleep(1.5)
        if not self.app.isConnected():
            raise ConnectionError(f"IBKR 연결 실패 ({TWS_HOST}:{TWS_PORT})")
        self.sig.log.emit(f"[연결] IBKR 연결 성공 ({TWS_HOST}:{TWS_PORT})")

        # ★ HMDS 서버 워밍업 대기
        # 연결 직후 2107 메시지가 발생할 수 있음
        # 서버가 "demand" 시 자동 연결되므로 3초 여유를 준 뒤 데이터 요청
        self.sig.log.emit("[연결] HMDS 서버 준비 대기 중... (3초)")
        time.sleep(3.0)

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
        """당일 포함 3 영업일 만기 반환 (인덱스 0=당일)"""
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
    def fetch_expiry(self, expiry: str, atm: float, is_first_expiry: bool = False) -> list:
        lo      = int((atm - STRIKE_RANGE) / STRIKE_STEP) * STRIKE_STEP
        hi      = int((atm + STRIKE_RANGE) / STRIKE_STEP) * STRIKE_STEP + STRIKE_STEP
        strikes = list(range(lo, hi + 1, STRIKE_STEP))
        total   = len(strikes) * 2
        self.sig.log.emit(
            f"[조회] {expiry} | {lo}~{hi} "
            f"({len(strikes)}행사가 × 2 = {total}계약)"
        )

        from datetime import timezone
        naive  = datetime.strptime(f"{expiry} 16:15:00", "%Y%m%d %H:%M:%S")
        et     = naive.replace(tzinfo=ET_TZ)
        utc    = et.astimezone(timezone.utc)
        end_dt = utc.strftime("%Y%m%d-%H:%M:%S")

        rows, skip_cnt, empty_cnt = [], 0, 0
        is_first_req = is_first_expiry   # 전체 첫 번째 요청 여부 추적

        for strike in strikes:
            for right in ("C", "P"):
                contract = self._contract(strike, right, expiry)
                rid      = self._next_req_id()
                ev       = threading.Event()
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

                # ★ 첫 번째 요청은 HMDS 서버 깨어나는 시간을 고려해 60초
                #   이후 요청은 30초로 복귀
                timeout = 60 if is_first_req else 30
                ev.wait(timeout=timeout)
                is_first_req = False     # 이후 요청부터 30초 적용

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

    # ── 폴더 경로 결정 ────────────────────────
    @staticmethod
    def _resolve_dir(base_date: str, label: str) -> Path:
        """
        label = 'D+0' → OUTPUT_DIR/YYYYMMDD/
        label = 'D+1' → OUTPUT_DIR/YYYYMMDD/D+1/
        label = 'D+2' → OUTPUT_DIR/YYYYMMDD/D+2/
        """
        root = OUTPUT_DIR / base_date
        d    = root if label == "D+0" else root / label
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── 전체 실행 ─────────────────────────────
    def run(self):
        try:
            self.connect()
            self.sig.progress.emit(10)

            atm      = self.get_spx_price()
            self.sig.progress.emit(20)

            expiries  = self.expiry_dates()   # [D+0, D+1, D+2]
            base_date = expiries[0]           # 당일 YYYYMMDD → 루트 폴더명
            self.sig.log.emit(
                f"[만기일] {', '.join(expiries)}  "
                f"(기준폴더: {base_date})"
            )

            ts     = datetime.now(ET_TZ).strftime("%Y%m%d_%H%M%S")
            fields = [
                "expiry", "strike", "right",
                "datetime", "open", "high", "low", "close", "volume"
            ]

            for i, (exp, label) in enumerate(zip(expiries, EXPIRY_LABELS)):
                self.sig.status.emit(
                    f"조회 중: {exp} [{label}] ({i+1}/3)..."
                )
                # D+0 첫 번째 만기에서만 첫 요청 타임아웃 60초 적용
                rows = self.fetch_expiry(exp, atm, is_first_expiry=(i == 0))
                self.sig.progress.emit(30 + i * 22)

                save_dir  = self._resolve_dir(base_date, label)
                filepath  = save_dir / f"SPX_{label}_{exp}_{ts}.csv"
                with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    w.writerows(rows)
                self.sig.log.emit(
                    f"  [저장] [{label}] {len(rows)}행 → {filepath}"
                )

            self.sig.progress.emit(100)
            self.sig.log.emit(
                f"[완료] 3개 만기 저장 완료\n"
                f"  폴더: {OUTPUT_DIR / base_date}"
            )
            self.sig.done.emit(str(OUTPUT_DIR / base_date))

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
        self._auto_done = None   # 마지막 자동 조회 완료 날짜 (YYYYMMDD)
        self._ui()
        self._bind()
        self._sched_start()

    def _ui(self):
        self.setWindowTitle("SPX 0DTE  1분봉 Fetcher  v4.1  ·  IBKR")
        self.setMinimumSize(860, 680)
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
            ("폴더 구조",  "날짜/D+0,D+1,D+2",        "#ce93d8"),
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
        self.log_te = QTextEdit()
        self.log_te.setReadOnly(True)
        self.log_te.setFont(QFont("Consolas", 10))
        self.log_te.setStyleSheet("background:#0d0d0d;color:#b0bec5;border:none;")
        ll.addWidget(self.log_te)
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
        self.btn_clr.clicked.connect(self.log_te.clear)

    def _sched_start(self):
        self.timer.timeout.connect(self._tick)
        self.timer.start(30_000)
        self._tick()   # 시작 즉시 1회 체크 (마감 후 기동 감지 포함)

    def _tick(self):
        now     = datetime.now(ET_TZ)
        today_s = now.strftime("%Y%m%d")
        tgt     = now.replace(
            hour=AUTO_HOUR, minute=AUTO_MIN, second=0, microsecond=0
        )

        # ── 장 마감 후 자동 조회 판정 ──────────────────────────
        # 조건: 영업일 + 16:15 ET 이후 + 당일 미조회 + 미실행 중
        market_closed_today = (
            now.weekday() < 5
            and now >= tgt
            and self._auto_done != today_s
            and not self.running
        )
        if market_closed_today:
            self._auto_done = today_s
            self._log(
                f"[자동] 장 마감 후 자동 조회 시작  "
                f"({now.strftime('%H:%M')} ET)"
            )
            self._go()
            tgt += timedelta(days=1)

        # ── 다음 자동 실행 표시 ────────────────────────────────
        diff   = tgt - now if now < tgt else tgt + timedelta(days=1) - now
        h, rem = divmod(int(diff.total_seconds()), 3600)
        m      = rem // 60
        self.next_lbl.setText(
            f"다음 자동 실행: {tgt.strftime('%m/%d %H:%M')} ET  "
            f"(약 {h}시간 {m}분 후)"
        )

    def _manual(self):
        if self.running:
            return
        self._log("[수동] 수동 조회 시작")
        self._go()

    def _go(self):
        self.running = True
        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("⏳  조회 중...")
        self.sb.showMessage("IBKR 연결 중...")
        threading.Thread(target=self.fetcher.run, daemon=True).start()

    def _on_done(self, folder: str):
        self.running = False
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("▶  지금 즉시 조회")
        self.sb.showMessage(f"완료 → {folder}")

    def _on_err(self, msg: str):
        self.running = False
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("▶  지금 즉시 조회")
        self.sb.showMessage(f"오류: {msg}")

    def _log(self, msg: str):
        ts = datetime.now(ET_TZ).strftime("%H:%M:%S ET")
        self.log_te.append(f"[{ts}]  {msg}")
        self.log_te.ensureCursorVisible()

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