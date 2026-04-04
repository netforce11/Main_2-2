# tab_opt_intraday.py — 탭12: 옵션 분봉 차트 + Greeks + 엑셀 저장
# ═══════════════════════════════════════════════════════════════
#  기능
#    · 기초자산(SPX/AAPL 등) + 행사가(직접 입력) + Call/Put 선택
#    · IBKR reqHistoricalData → 1분봉 OHLC
#    · pyqtgraph 캔들차트 (상단) + Delta / Gamma 서브플롯 (하단)
#    · 엑셀 저장 (.xlsx, openpyxl)
#
#  main.py 추가 방법:
#    from tab_opt_intraday import OptIntradayGrid
#    self.tabs.addTab(OptIntradayGrid(self), "📊 옵션 분봉")
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
import datetime, threading, os
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLabel, QPushButton, QComboBox,
    QLineEdit, QProgressBar, QFileDialog, QMessageBox,
    QSizePolicy,
)
from PyQt5.QtCore  import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui   import QFont, QColor

import pyqtgraph as pg
from pyqtgraph import QtCore

# ── core 상수 ──────────────────────────────────────────────────
try:
    from core import (
        IBapi, bridge, router,
        TWS_HOST, TWS_PORT, CLIENT_ID,
        DEFAULT_FONT_SIZE, make_opt_contract,
        IBAPI_AVAILABLE,
    )
except ImportError:
    IBapi            = None
    bridge           = None
    router           = None
    TWS_HOST         = "127.0.0.1"
    TWS_PORT         = 7496
    CLIENT_ID        = 1
    DEFAULT_FONT_SIZE = 13
    IBAPI_AVAILABLE  = False
    def make_opt_contract(sym, expiry, strike, right, exchange="SMART",
                          currency="USD", trading_class=""):
        return None

# ── openpyxl (엑셀) ──────────────────────────────────────────
try:
    import openpyxl
    from openpyxl.styles import Font as XFont, PatternFill, Alignment, Border, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ── IBKR bar_size (1분봉 고정) ────────────────────────────────
BAR_SIZE   = "1 min"
REQ_ID_OPT = 9820      # 다른 탭 reqId 와 충돌 방지
REQ_ID_UND = 9821
REQ_ID_GRK = 9822

# ═══════════════════════════════════════════════════════════════
#  내부 시그널 브리지
# ═══════════════════════════════════════════════════════════════
class _Bridge(QObject):
    bar_ready   = pyqtSignal(dict)    # 분봉 1개 수신
    bars_done   = pyqtSignal()        # 히스토리 완료
    greek_ready = pyqtSignal(dict)    # Greeks tick 1개
    error_sig   = pyqtSignal(str)


# ═══════════════════════════════════════════════════════════════
#  CandlestickItem — pyqtgraph 캔들 아이템
#  ※ QPicture 방식은 pyqtgraph Y축 반전으로 글씨/그림 뒤집힘 발생
#     → paint() 에서 직접 QPainter 로 그리는 방식으로 수정
# ═══════════════════════════════════════════════════════════════
class CandlestickItem(pg.GraphicsObject):
    """bars: list of dict {t, o, h, l, c, v}"""

    COLOR_UP = pg.mkColor("#26a69a")   # 양봉 청록
    COLOR_DN = pg.mkColor("#ef5350")   # 음봉 빨강
    BODY_W   = 0.35                    # 캔들 반너비 (인덱스 단위)

    def __init__(self):
        super().__init__()
        self._bars: list[dict] = []
        self._bounding = QtCore.QRectF()

    def set_bars(self, bars: list[dict]):
        self._bars = bars
        self._update_bounding()
        self.prepareGeometryChange()
        self.update()

    def _update_bounding(self):
        if not self._bars:
            self._bounding = QtCore.QRectF()
            return
        lows  = [b["l"] for b in self._bars]
        highs = [b["h"] for b in self._bars]
        n     = len(self._bars)
        pad   = (max(highs) - min(lows)) * 0.02 or 0.5
        self._bounding = QtCore.QRectF(
            -self.BODY_W,
            min(lows) - pad,
            n + self.BODY_W * 2,
            (max(highs) - min(lows)) + pad * 2,
        )

    def boundingRect(self):
        return self._bounding

    def paint(self, painter, option, widget=None):
        # ── pyqtgraph ViewBox 좌표계에서 직접 그림 → Y축 정상
        if not self._bars:
            return

        w = self.BODY_W
        for i, b in enumerate(self._bars):
            o, h, l, c = b["o"], b["h"], b["l"], b["c"]
            is_up  = c >= o
            color  = self.COLOR_UP if is_up else self.COLOR_DN

            painter.setPen(pg.mkPen(color, width=1))
            painter.setBrush(pg.mkBrush(color))

            # 심지 (wick)
            painter.drawLine(
                QtCore.QPointF(i, l),
                QtCore.QPointF(i, h),
            )

            # 몸통 (body)
            body_top    = max(o, c)
            body_bottom = min(o, c)
            body_h      = body_top - body_bottom
            if body_h < 1e-9:
                body_h = max(h - l, 0.01) * 0.1   # 최소 높이 보정

            painter.drawRect(QtCore.QRectF(
                i - w,
                body_bottom,
                w * 2,
                body_h,
            ))


# ═══════════════════════════════════════════════════════════════
#  메인 탭 위젯
# ═══════════════════════════════════════════════════════════════
class OptIntradayGrid(QWidget):
    """탭12: 옵션 1분봉 차트 + Greeks (IBKR reqHistoricalData)"""

    def __init__(self, mw=None):
        super().__init__()
        self._mw       = mw
        self._bridge   = _Bridge()
        self._bars: list[dict]   = []     # OHLC 분봉 버퍼
        self._greeks: list[dict] = []     # Greeks 버퍼
        self._req_pending = False
        self._ib_ref = None               # IBapi 참조

        self._build_ui()
        self._connect_signals()

    # ══════════════════════════════════════════════════════════
    #  UI 빌드
    # ══════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(4)

        # ── 컨트롤 바 ────────────────────────────────────────
        ctrl_box = QGroupBox("조회 설정")
        ctrl_box.setFixedHeight(64)
        ctrl_lay = QHBoxLayout(ctrl_box)
        ctrl_lay.setSpacing(10)

        # 기초자산
        ctrl_lay.addWidget(QLabel("기초자산:"))
        self._edit_sym = QLineEdit("SPX")
        self._edit_sym.setFixedWidth(80)
        self._edit_sym.setToolTip("예: SPX  AAPL  QQQ  TSLA")
        ctrl_lay.addWidget(self._edit_sym)

        # 만기
        ctrl_lay.addWidget(QLabel("만기:"))
        self._edit_exp = QLineEdit(
            datetime.date.today().strftime("%Y%m%d"))
        self._edit_exp.setFixedWidth(95)
        self._edit_exp.setToolTip("YYYYMMDD")
        ctrl_lay.addWidget(self._edit_exp)

        # 행사가
        ctrl_lay.addWidget(QLabel("행사가:"))
        self._edit_strike = QLineEdit("5500")
        self._edit_strike.setFixedWidth(80)
        ctrl_lay.addWidget(self._edit_strike)

        # Call / Put
        ctrl_lay.addWidget(QLabel("구분:"))
        self._cmb_right = QComboBox()
        self._cmb_right.addItems(["CALL", "PUT"])
        self._cmb_right.setFixedWidth(75)
        ctrl_lay.addWidget(self._cmb_right)

        # 기간 (몇 일치)
        ctrl_lay.addWidget(QLabel("기간:"))
        self._cmb_dur = QComboBox()
        self._cmb_dur.addItems(["1 D", "2 D", "3 D", "5 D"])
        self._cmb_dur.setFixedWidth(65)
        ctrl_lay.addWidget(self._cmb_dur)

        ctrl_lay.addSpacing(10)

        # 조회 버튼
        self._btn_fetch = QPushButton("📥 조회")
        self._btn_fetch.setFixedWidth(80)
        self._btn_fetch.clicked.connect(self._on_fetch)
        ctrl_lay.addWidget(self._btn_fetch)

        # 엑셀 저장
        self._btn_excel = QPushButton("💾 엑셀 저장")
        self._btn_excel.setFixedWidth(100)
        self._btn_excel.setEnabled(False)
        self._btn_excel.clicked.connect(self._save_excel)
        ctrl_lay.addWidget(self._btn_excel)

        ctrl_lay.addStretch()

        # 진행 표시
        self._prog = QProgressBar()
        self._prog.setRange(0, 0)
        self._prog.setVisible(False)
        self._prog.setFixedWidth(110)
        self._prog.setFixedHeight(16)
        ctrl_lay.addWidget(self._prog)

        # 상태
        self._lbl_status = QLabel("대기 중")
        self._lbl_status.setFixedWidth(180)
        self._lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ctrl_lay.addWidget(self._lbl_status)

        root.addWidget(ctrl_box)

        # ── 차트 영역 (Splitter) ─────────────────────────────
        self._splitter = QSplitter(Qt.Vertical)

        # 상단: 캔들차트
        self._setup_candle_chart()
        # 하단: Greeks (Delta / Gamma)
        self._setup_greek_chart()

        self._splitter.setSizes([600, 220])
        root.addWidget(self._splitter)

        # ── 하단 로그 ─────────────────────────────────────────
        self._lbl_log = QLabel("—")
        self._lbl_log.setFixedHeight(22)
        self._lbl_log.setContentsMargins(4, 0, 4, 0)
        self._lbl_log.setStyleSheet(
            "background:#111122; color:#7788bb; font-size:12px;")
        root.addWidget(self._lbl_log)

    # ── 캔들 차트 셋업 ───────────────────────────────────────
    def _setup_candle_chart(self):
        self._pw_candle = pg.PlotWidget(background="#0d1117")
        self._pw_candle.showGrid(x=True, y=True, alpha=0.2)
        self._pw_candle.setLabel("left",  "Price",  color="#aaaacc")
        self._pw_candle.setLabel("bottom","Bar idx", color="#aaaacc")

        # X축 tick → 시간 레이블
        self._x_axis = pg.AxisItem("bottom")
        self._pw_candle.setAxisItems({"bottom": self._x_axis})

        self._candle_item = CandlestickItem()
        self._pw_candle.addItem(self._candle_item)

        # 종가 라인 (반투명)
        self._close_line = self._pw_candle.plot(
            pen=pg.mkPen("#ffdd88", width=1, style=Qt.DashLine))

        # 제목 레이블
        self._lbl_title = pg.LabelItem(
            text="— 옵션 1분봉 —",
            color="#ccccff", size="11pt")
        self._pw_candle.addItem(self._lbl_title)

        self._splitter.addWidget(self._pw_candle)

    # ── Greeks 차트 셋업 ─────────────────────────────────────
    def _setup_greek_chart(self):
        self._pw_greek = pg.PlotWidget(background="#0d1117")
        self._pw_greek.showGrid(x=True, y=True, alpha=0.2)
        self._pw_greek.setLabel("left", "Greek value", color="#aaaacc")
        self._pw_greek.addLegend(offset=(10, 10))

        self._delta_line = self._pw_greek.plot(
            pen=pg.mkPen("#66ccff", width=1.5), name="Delta")
        self._gamma_line = self._pw_greek.plot(
            pen=pg.mkPen("#ff9966", width=1.5), name="Gamma ×100")

        # X축 캔들과 연동
        self._pw_greek.setXLink(self._pw_candle)

        self._splitter.addWidget(self._pw_greek)

    # ══════════════════════════════════════════════════════════
    #  시그널 연결
    # ══════════════════════════════════════════════════════════
    def _connect_signals(self):
        self._bridge.bar_ready.connect(self._on_bar)
        self._bridge.bars_done.connect(self._on_bars_done)
        self._bridge.greek_ready.connect(self._on_greek)
        self._bridge.error_sig.connect(self._on_error)

    # ══════════════════════════════════════════════════════════
    #  조회
    # ══════════════════════════════════════════════════════════
    def _on_fetch(self):
        sym    = self._edit_sym.text().strip().upper()
        exp    = self._edit_exp.text().strip()
        strike_txt = self._edit_strike.text().strip()
        right  = self._cmb_right.currentText()   # "CALL" / "PUT"
        dur    = self._cmb_dur.currentText()      # "1 D" 등

        # 입력 검증
        if not sym:
            self._log("❌ 기초자산을 입력하세요"); return
        if len(exp) != 8 or not exp.isdigit():
            self._log("❌ 만기 형식 오류 (YYYYMMDD)"); return
        try:
            strike = float(strike_txt)
        except ValueError:
            self._log("❌ 행사가를 숫자로 입력하세요"); return

        # IBKR 참조
        ib = self._get_ib()
        if ib is None:
            self._log("❌ IBKR 미연결 — TWS/Gateway 연결 후 재시도"); return

        self._bars.clear()
        self._greeks.clear()
        self._btn_fetch.setEnabled(False)
        self._btn_excel.setEnabled(False)
        self._prog.setVisible(True)
        self._lbl_status.setText("조회 중…")

        # 차트 초기화
        self._candle_item.set_bars([])
        self._close_line.setData([], [])
        self._delta_line.setData([], [])
        self._gamma_line.setData([], [])

        title = f"{sym}  {exp}  {right}  K={strike:.0f}"
        self._lbl_title.setText(title)
        self._log(f"⏳ {title} — IBKR 1분봉 요청 중...")

        # IBKR 계약 생성
        # core_contract.make_opt_contract(symbol, strike, right, expiry, tag="")
        contract = make_opt_contract(
            sym,        # symbol
            strike,     # strike (float)
            right[0],   # right: "C" / "P"
            exp,        # expiry: "YYYYMMDD"
        )
        if contract is None:
            self._log("❌ contract 생성 실패 — core.make_opt_contract 확인"); return

        # IBKR 콜백 패치 (임시 등록)
        self._req_pending = True
        self._patch_ib_callbacks(ib)

        # 백그라운드 요청
        end_dt = ""   # 비워두면 현재 시각
        threading.Thread(
            target=self._do_hist_request,
            args=(ib, contract, dur, end_dt),
            daemon=True,
        ).start()

    def _do_hist_request(self, ib, contract, dur, end_dt):
        try:
            ib.reqHistoricalData(
                REQ_ID_OPT,
                contract,
                end_dt,           # endDateTime: "" = now
                dur,              # durationStr: "1 D", "2 D" …
                BAR_SIZE,         # barSizeSetting: "1 min"
                "TRADES",         # whatToShow
                1,                # useRTH: 1=장중만
                1,                # formatDate: 1=yyyyMMdd HH:mm:ss
                False,            # keepUpToDate
                [],
            )
        except Exception as e:
            self._bridge.error_sig.emit(f"reqHistoricalData 오류: {e}")

    # ── bridge 시그널 연결 (monkeypatch 대신) ──────────────────
    def _patch_ib_callbacks(self, ib):
        """
        IBapi 클래스를 직접 수정하지 않는다.
        core_contract.historicalData() 는 이미 bar → dict 변환 후
        bridge.hist_bar(reqId, dict) 를 emit한다.
        bridge.hist_end(reqId) 도 마찬가지.

        여기서는 전역 bridge 시그널에 슬롯을 연결하고,
        reqId 가 REQ_ID_OPT 인 경우만 내부 _bridge 로 중계한다.
        중복 연결 방지 플래그 _opt_intraday_patched 를 사용한다.

        주의: IBapi 클래스 레벨 monkeypatch는 core_contract.py 의
        dict-emit 픽스를 덮어써 0xC0000005 를 재발시킨다 → 절대 금지.
        """
        if getattr(self, '_opt_intraday_patched', False):
            return
        self._opt_intraday_patched = True

        from core import bridge as _core_bridge
        from PyQt5.QtCore import Qt

        bridge_ = self._bridge

        def _on_hist_bar(reqId, bar_dict):
            # bar_dict 는 core_contract.historicalData 에서 이미 변환된 dict
            if reqId != REQ_ID_OPT:
                return
            try:
                bridge_.bar_ready.emit({
                    "t": str(bar_dict["date"]),
                    "o": float(bar_dict["open"]),
                    "h": float(bar_dict["high"]),
                    "l": float(bar_dict["low"]),
                    "c": float(bar_dict["close"]),
                    "v": int(bar_dict["volume"]),
                })
            except Exception as e:
                bridge_.error_sig.emit(f"bar 파싱 오류: {e}")

        def _on_hist_end(reqId):
            if reqId == REQ_ID_OPT:
                bridge_.bars_done.emit()

        _core_bridge.hist_bar.connect(_on_hist_bar, Qt.QueuedConnection)
        _core_bridge.hist_end.connect(_on_hist_end, Qt.QueuedConnection)

        # tick_option 은 전역 bridge 에서 reqId 필터링
        def _on_tick_option(reqId, tickType, iv, delta, optPrice, gamma, vega, theta):
            if reqId != REQ_ID_GRK:
                return
            def _safe(v): return float(v) if v not in (None, -1e308) else 0.0
            bridge_.greek_ready.emit({
                "delta": _safe(delta),
                "gamma": _safe(gamma),
                "vega":  _safe(vega),
                "theta": _safe(theta),
                "iv":    _safe(iv),
            })

        _core_bridge.tick_option.connect(_on_tick_option, Qt.QueuedConnection)

    # ══════════════════════════════════════════════════════════
    #  데이터 수신 콜백
    # ══════════════════════════════════════════════════════════
    def _on_bar(self, bar: dict):
        self._bars.append(bar)
        n = len(self._bars)
        # 10봉마다 진행 상황 로그 출력
        if n % 10 == 0 or n == 1:
            self._lbl_status.setText(f"수신 중… {n}봉")
            self._log(f"📡 {n}봉 수신 중 — 최근: {bar['t']}  C={bar['c']:.2f}")

    def _on_bars_done(self):
        self._btn_fetch.setEnabled(True)
        self._prog.setVisible(False)
        n = len(self._bars)
        self._lbl_status.setText(f"완료 ({n}봉)")
        if n == 0:
            self._log("⚠ 수신된 봉 없음 — 만기/행사가/권리 확인 또는 시세 미구독 (ERR 354)")
        else:
            t0 = self._bars[0]["t"]
            t1 = self._bars[-1]["t"]
            self._log(f"✅ {n}봉 완료  {t0} ~ {t1}  (차트 갱신 중...)")
            self._draw_charts()
            self._btn_excel.setEnabled(True)
        self._req_pending = False

    def _on_greek(self, g: dict):
        self._greeks.append(g)
        # 실시간 Greeks 수신 시 즉시 라인 갱신
        self._draw_greeks()

    def _on_error(self, msg: str):
        self._btn_fetch.setEnabled(True)
        self._prog.setVisible(False)
        self._lbl_status.setText("오류")
        # IBKR 에러 코드별 힌트
        hint = ""
        if "354" in msg:
            hint = " → 시세 미구독: TWS에서 해당 옵션 시세 구독 필요"
        elif "200" in msg:
            hint = " → Contract 불명확: exchange/tradingClass 확인"
        elif "321" in msg:
            hint = " → bar_size 형식 오류"
        elif "162" in msg:
            hint = " → 히스토리 데이터 없음 (장외 시간 또는 만기 오류)"
        elif "10314" in msg:
            hint = " → 시세 구독 권한 없음"
        self._log(f"❌ {msg}{hint}")
        self._req_pending = False

    # ══════════════════════════════════════════════════════════
    #  차트 렌더링
    # ══════════════════════════════════════════════════════════
    def _draw_charts(self):
        if not self._bars:
            return

        # 캔들 차트
        self._candle_item.set_bars(self._bars)

        # 종가 점선 오버레이
        xs = list(range(len(self._bars)))
        cs = [b["c"] for b in self._bars]
        self._close_line.setData(xs, cs)

        # X축 시간 레이블 (20봉마다)
        ticks = {}
        for i, b in enumerate(self._bars):
            t = b["t"]   # "20241225 09:31:00" 형태
            try:
                label = t[9:14]  # HH:MM
            except Exception:
                label = str(i)
            if i % 20 == 0:
                ticks[i] = label
        self._x_axis.setTicks([list(ticks.items())])
        self._pw_candle.autoRange()

        # Greeks 차트 (히스토리에서 Greeks 없으면 빈 상태)
        self._draw_greeks()

    def _draw_greeks(self):
        if not self._greeks:
            return
        xs = list(range(len(self._greeks)))
        deltas = [g["delta"] for g in self._greeks]
        gammas = [g["gamma"] * 100 for g in self._greeks]   # ×100 스케일
        self._delta_line.setData(xs, deltas)
        self._gamma_line.setData(xs, gammas)
        self._pw_greek.autoRange()

    # ══════════════════════════════════════════════════════════
    #  엑셀 저장
    # ══════════════════════════════════════════════════════════
    def _save_excel(self):
        if not self._bars:
            self._log("저장할 데이터가 없습니다"); return
        if not HAS_OPENPYXL:
            QMessageBox.critical(self, "openpyxl 없음",
                "pip install openpyxl  설치 후 재시도하세요")
            return

        sym    = self._edit_sym.text().strip().upper()
        exp    = self._edit_exp.text().strip()
        strike = self._edit_strike.text().strip()
        right  = self._cmb_right.currentText()
        default_name = f"{sym}_{exp}_{right}_{strike}_1min.xlsx"

        path, _ = QFileDialog.getSaveFileName(
            self, "엑셀 저장", default_name,
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not path:
            return

        try:
            self._write_excel(path)
            self._log(f"💾 저장 완료: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))
            self._log(f"❌ 저장 실패: {e}")

    def _write_excel(self, path: str):
        wb  = openpyxl.Workbook()

        # ── 시트1: 분봉 OHLC ─────────────────────────────────
        ws_ohlc = wb.active
        ws_ohlc.title = "1분봉 OHLC"

        sym    = self._edit_sym.text().strip().upper()
        exp    = self._edit_exp.text().strip()
        strike = self._edit_strike.text().strip()
        right  = self._cmb_right.currentText()

        # 헤더 스타일
        hdr_fill  = PatternFill("solid", fgColor="1F3864")
        hdr_font  = XFont(name="Consolas", bold=True, color="FFFFFF", size=10)
        hdr_align = Alignment(horizontal="center", vertical="center")
        thin = Side(border_style="thin", color="444444")
        bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)

        # 제목행
        ws_ohlc.merge_cells("A1:H1")
        title_cell = ws_ohlc["A1"]
        title_cell.value = f"{sym}  만기:{exp}  행사가:{strike}  {right}  1분봉 OHLC"
        title_cell.font  = XFont(name="Consolas", bold=True, size=12, color="CCE5FF")
        title_cell.fill  = PatternFill("solid", fgColor="0D1B2A")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws_ohlc.row_dimensions[1].height = 22

        # 컬럼 헤더
        headers_ohlc = ["#", "DateTime", "Open", "High", "Low", "Close", "Volume", "방향"]
        for col_i, h in enumerate(headers_ohlc, 1):
            cell = ws_ohlc.cell(row=2, column=col_i, value=h)
            cell.font      = hdr_font
            cell.fill      = hdr_fill
            cell.alignment = hdr_align
            cell.border    = bdr

        # 데이터
        up_fill   = PatternFill("solid", fgColor="0D2B0D")   # 양봉 배경
        dn_fill   = PatternFill("solid", fgColor="2B0D0D")   # 음봉 배경
        num_font  = XFont(name="Consolas", size=10)
        num_align = Alignment(horizontal="right", vertical="center")

        col_widths = [5, 20, 10, 10, 10, 10, 12, 6]

        for row_i, b in enumerate(self._bars, 3):
            direction = "▲" if b["c"] >= b["o"] else "▼"
            row_fill  = up_fill if b["c"] >= b["o"] else dn_fill
            values    = [row_i - 2, b["t"], b["o"], b["h"], b["l"], b["c"], b["v"], direction]

            for col_i, val in enumerate(values, 1):
                cell = ws_ohlc.cell(row=row_i, column=col_i, value=val)
                cell.font      = num_font
                cell.fill      = row_fill
                cell.alignment = num_align
                cell.border    = bdr

                # 숫자 포맷
                if col_i in (3, 4, 5, 6):
                    cell.number_format = "#,##0.00"
                elif col_i == 7:
                    cell.number_format = "#,##0"

        # 컬럼 폭
        for ci, w in enumerate(col_widths, 1):
            ws_ohlc.column_dimensions[
                openpyxl.utils.get_column_letter(ci)].width = w

        ws_ohlc.freeze_panes = "A3"

        # ── 시트2: Greeks ─────────────────────────────────────
        if self._greeks:
            ws_grk = wb.create_sheet("Greeks")
            grk_hdrs = ["#", "Delta", "Gamma", "Theta", "Vega", "IV"]
            for col_i, h in enumerate(grk_hdrs, 1):
                cell = ws_grk.cell(row=1, column=col_i, value=h)
                cell.font      = hdr_font
                cell.fill      = hdr_fill
                cell.alignment = hdr_align
                cell.border    = bdr

            grk_fmt = {"Delta": "0.0000", "Gamma": "0.00000",
                       "Theta": "0.0000", "Vega":  "0.0000", "IV": "0.00%"}
            grk_keys = ["delta", "gamma", "theta", "vega", "iv"]

            for row_i, g in enumerate(self._greeks, 2):
                values = [row_i - 1] + [g.get(k, 0) for k in grk_keys]
                for col_i, val in enumerate(values, 1):
                    cell = ws_grk.cell(row=row_i, column=col_i, value=val)
                    cell.font   = num_font
                    cell.border = bdr
                    cell.alignment = num_align
                    if col_i > 1:
                        key = grk_keys[col_i - 2]
                        cell.number_format = grk_fmt.get(
                            grk_keys[col_i - 2].capitalize(), "0.0000")

            for ci, w in enumerate([5, 12, 12, 12, 12, 12], 1):
                ws_grk.column_dimensions[
                    openpyxl.utils.get_column_letter(ci)].width = w
            ws_grk.freeze_panes = "A2"

        wb.save(path)

    # ══════════════════════════════════════════════════════════
    #  유틸
    # ══════════════════════════════════════════════════════════
    def _get_ib(self):
        """main window 에서 IBapi 인스턴스 가져오기"""
        if self._mw and hasattr(self._mw, "ib"):
            return self._mw.ib
        return None

    def _log(self, msg: str):
        self._lbl_log.setText(msg)
        if self._mw and hasattr(self._mw, "statusBar"):
            try:
                self._mw.statusBar().showMessage(msg, 5000)
            except Exception:
                pass