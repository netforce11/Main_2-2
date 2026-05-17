#!/usr/bin/env python3
"""
delta_band_standalone.py — SPX 옵션 델타 밴드 뷰어 (단독 실행 버전)

■ 이 파일 하나로 완전히 동작합니다.
  greek_calculator.py, config.py 등 외부 모듈 불필요.

■ 필요 패키지 (없으면 pip 설치):
    pip install PyQt5 matplotlib

■ 실행:
    python delta_band_standalone.py

■ 저장 경로 설정 (아래 SPX_INDEX_DIR 변수만 수정하세요):
    SPX_INDEX_DIR = "/home/netforce/US_Data/Data/SPX_0DTE/Es"
"""

import sys
import csv
import math
import re
from pathlib import Path
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

# ══════════════════════════════════════════════════════════════════
# ① 경로 설정 — 이 부분만 이식 환경에 맞게 수정하세요
# ══════════════════════════════════════════════════════════════════

SPX_INDEX_DIR = Path("/home/netforce/US_Data/Data/SPX_0DTE/Es")  # SPX(ES) 지수 CSV 루트

# ══════════════════════════════════════════════════════════════════
# ② Black-Scholes Greeks (greek_calculator.py 내장)
# ══════════════════════════════════════════════════════════════════

ET = ZoneInfo("America/New_York")
RISK_FREE_RATE = 0.053
_TRADING_MINS  = 390.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_delta(S, K, T, r, sigma, right):
    if T <= 1e-8 or sigma <= 1e-8 or S <= 0 or K <= 0:
        if right == "C":
            return 1.0 if S > K else (0.5 if S == K else 0.0)
        else:
            return -1.0 if S < K else (-0.5 if S == K else 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1) if right == "C" else _norm_cdf(d1) - 1.0


def bs_gamma(S, K, T, r, sigma):
    if T <= 1e-8 or sigma <= 1e-8 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def bs_theta(S, K, T, r, sigma, right):
    if T <= 1e-8 or sigma <= 1e-8 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    term1 = -(S * _norm_pdf(d1) * sigma) / (2 * math.sqrt(T))
    if right == "C":
        term2 = -r * K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        term2 = r * K * math.exp(-r * T) * _norm_cdf(-d2)
    return (term1 + term2) / 365.0


def bs_vega(S, K, T, r, sigma):
    if T <= 1e-8 or sigma <= 1e-8 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return S * _norm_pdf(d1) * math.sqrt(T) / 100.0


def implied_vol_bisect(market_price, S, K, T, r, right,
                       lo=0.001, hi=5.0, tol=1e-5, max_iter=100):
    if T <= 1e-8 or S <= 0 or K <= 0 or market_price <= 0:
        return None

    def price(sig):
        d1 = (math.log(S / K) + (r + 0.5 * sig ** 2) * T) / (sig * math.sqrt(T))
        d2 = d1 - sig * math.sqrt(T)
        if right == "C":
            return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
        else:
            return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)

    f_lo = price(lo) - market_price
    f_hi = price(hi) - market_price
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid  = (lo + hi) / 2
        f_mid = price(mid) - market_price
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi = mid; f_hi = f_mid
        else:
            lo = mid; f_lo = f_mid
    return (lo + hi) / 2


_FNAME_RE = re.compile(
    r"(?P<tc>[A-Z]+)_(?P<exp>\d{8})_(?P<strike>\d+)_(?P<right>[CP])\.csv$"
)


def parse_option_fname(fname: str):
    m = _FNAME_RE.search(Path(fname).name)
    if not m:
        return None
    return {
        "tc":       m.group("tc"),
        "exp_date": datetime.strptime(m.group("exp"), "%Y%m%d").date(),
        "strike":   int(m.group("strike")),
        "right":    m.group("right"),
    }


def time_to_expiry_years(bar_dt: datetime, exp_date: date) -> float:
    # CSV 시간이 KST(한국시간)로 저장됨
    # 만기 16:00 ET = 익일 05:00 KST
    from zoneinfo import ZoneInfo as _ZI
    from datetime import timedelta
    _KST = _ZI("Asia/Seoul")
    exp_date_kst = exp_date + timedelta(days=1)  # 익일 05:00 KST
    exp_close_kst = datetime(exp_date_kst.year, exp_date_kst.month, exp_date_kst.day,
                             5, 0, 0, tzinfo=_KST)
    if bar_dt.tzinfo is None:
        bar_dt = bar_dt.replace(tzinfo=_KST)
    remaining_mins = max((exp_close_kst - bar_dt).total_seconds() / 60, 0)
    return remaining_mins / (252 * _TRADING_MINS)


def load_delta_series(csv_path, underlying_prices=None, r=RISK_FREE_RATE):
    path   = Path(csv_path)
    meta   = parse_option_fname(path.name)
    if not meta:
        raise ValueError(f"파일명 파싱 실패: {path.name}")

    K      = meta["strike"]
    right  = meta["right"]
    exp_dt = meta["exp_date"]

    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                dt_str = row["datetime"]
                close  = float(row["close"])
                if close <= 0:
                    continue
                for fmt in ("%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d  %H:%M:%S"):
                    try:
                        dt = datetime.strptime(dt_str.strip(), fmt); break
                    except ValueError:
                        continue
                else:
                    continue

                # raw 문자열 그대로 키 사용 → ES 지수 키(공백 2개)와 정확히 매칭
                dt_key = dt_str.strip()

                if underlying_prices:
                    S = underlying_prices.get(dt_key)
                    if not S:
                        # 보간: ±5분 이내 가장 가까운 값
                        best_diff, best_val = float("inf"), None
                        for k, v in underlying_prices.items():
                            try:
                                kt   = datetime.strptime(k.strip(), "%Y%m%d  %H:%M:%S")
                                diff = abs((kt - dt).total_seconds())
                                if diff < best_diff:
                                    best_diff = diff; best_val = v
                            except ValueError:
                                try:
                                    kt   = datetime.strptime(k.strip(), "%Y%m%d %H:%M:%S")
                                    diff = abs((kt - dt).total_seconds())
                                    if diff < best_diff:
                                        best_diff = diff; best_val = v
                                except ValueError:
                                    continue
                        if best_val and best_diff <= 300:
                            S = best_val
                    if not S:
                        continue
                else:
                    S = float(K) * 1.005

                T  = time_to_expiry_years(dt, exp_dt)
                iv = implied_vol_bisect(close, S, K, T, r, right)
                if iv is None:
                    iv = 0.20

                rows.append({
                    "dt":    dt,
                    "close": close,
                    "delta": round(bs_delta(S, K, T, r, iv, right), 4),
                    "gamma": round(bs_gamma(S, K, T, r, iv), 6),
                    "theta": round(bs_theta(S, K, T, r, iv, right), 4),
                    "vega":  round(bs_vega(S, K, T, r, iv), 4),
                    "iv":    round(iv, 4),
                })
            except (ValueError, KeyError):
                continue
    return rows


# ══════════════════════════════════════════════════════════════════
# ③ PyQt5 / matplotlib UI (delta_band_viewer.py 내장)
# ══════════════════════════════════════════════════════════════════

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QPushButton, QLabel, QComboBox, QFileDialog, QGroupBox,
        QStatusBar, QDoubleSpinBox, QCheckBox, QFrame,
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
except ModuleNotFoundError:
    raise SystemExit("[오류] PyQt5 미설치:  pip install PyQt5")

try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavToolbar
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ModuleNotFoundError:
    raise SystemExit("[오류] matplotlib 미설치:  pip install matplotlib")

# 한글 폰트 설정
import matplotlib.font_manager as _fm
_KOREAN_FONTS = ["NanumGothic", "NanumBarunGothic", "Malgun Gothic", "AppleGothic", "UnDotum"]
_found_font = next(
    (f for f in _KOREAN_FONTS
     if any(f.lower() in p.name.lower() for p in _fm.fontManager.ttflist)),
    None,
)
if _found_font:
    plt.rcParams["font.family"] = _found_font
plt.rcParams["axes.unicode_minus"] = False


# ── 밴드 설정 기본값 ──────────────────────────────────────────────

DEFAULT_BAND = {
    "neutral_lo":  0.40,
    "neutral_hi":  0.60,
    "hot_lo":      0.60,
    "hot_hi":      1.00,
    "cold_lo":    -1.00,
    "cold_hi":     0.40,
}

COLORS = {
    "neutral":      "#2196F3",
    "hot":          "#F44336",
    "cold":         "#4CAF50",
    "band_hot":     "#FFEBEE",
    "band_cold":    "#E8F5E9",
    "band_neutral": "#E3F2FD",
    "grid":         "#E0E0E0",
    "bg":           "#FAFAFA",
}


# ── 백그라운드 계산 스레드 ────────────────────────────────────────

class CalcThread(QThread):
    done   = pyqtSignal(list)
    error  = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, files: list, basis: float = 24.0):
        super().__init__()
        self.files = files
        self.basis = basis  # ES-SPX 베이시스 보정값 (ES - basis = SPX 추정)

    def _load_spx_prices(self, date_str: str) -> dict:
        fpath = SPX_INDEX_DIR / date_str / "spx_index.csv"
        if not fpath.exists():
            return {}
        result = {}
        _fmts  = ("%Y%m%d  %H:%M:%S", "%Y%m%d %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                  "%Y%m%d-%H:%M:%S", "%Y/%m/%d %H:%M:%S")
        with open(fpath, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                try:
                    raw = row["datetime"].strip()
                    val = float(row["close"])
                    normalized = raw
                    for fmt in _fmts:
                        try:
                            normalized = raw  # raw 문자열 그대로 키 사용 (공백 2개 유지)
                            break
                        except ValueError:
                            continue
                    result[normalized] = val - self.basis  # ES → SPX 보정
                except (KeyError, ValueError):
                    continue
        return result

    def run(self):
        results = []
        for fp in self.files:
            self.status.emit(f"계산 중: {fp.name}")
            try:
                meta = parse_option_fname(fp.name)
                underlying = {}
                if meta:
                    date_str   = meta["exp_date"].strftime("%Y%m%d")
                    underlying = self._load_spx_prices(date_str)
                    if not underlying:
                        parent_name = fp.parent.name
                        if parent_name.isdigit() and len(parent_name) == 8:
                            underlying = self._load_spx_prices(parent_name)
                    if underlying:
                        self.status.emit(f"계산 중: {fp.name} (SPX 지수 {len(underlying)}봉 로드)")
                rows = load_delta_series(fp, underlying_prices=underlying or None)
                if rows:
                    results.append({"label": fp.stem, "rows": rows})
            except Exception as e:
                self.status.emit(f"[스킵] {fp.name}: {e}")
        self.done.emit(results)


# ── 메인 뷰어 ────────────────────────────────────────────────────

class DeltaBandViewer(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        # 탭에 embed — 창 크기는 부모가 결정

        self._data   = []
        self._band   = dict(DEFAULT_BAND)
        self._thread = None

        self._build_ui()

    # ── UI ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 27, 8, 27)  # 상하 +19 → 내부 세로 -38px
        root.setSpacing(8)

        # 왼쪽 컨트롤 패널
        ctrl_panel = QWidget()
        ctrl_panel.setFixedWidth(260)
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(10)

        # 파일 열기
        file_grp = QGroupBox("데이터")
        file_lay = QVBoxLayout(file_grp)
        self.btn_open_file   = QPushButton("CSV 파일 열기")
        self.btn_open_folder = QPushButton("폴더 열기 (일괄)")
        self.btn_open_file.clicked.connect(self._open_files)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.lbl_loaded = QLabel("파일 0개 로드됨")
        self.lbl_loaded.setStyleSheet("color: gray; font-size: 11px;")
        file_lay.addWidget(self.btn_open_file)
        file_lay.addWidget(self.btn_open_folder)
        file_lay.addWidget(self.lbl_loaded)
        ctrl_layout.addWidget(file_grp)

        # ES-SPX 베이시스 보정
        basis_grp = QGroupBox("ES-SPX 베이시스 보정")
        basis_lay = QHBoxLayout(basis_grp)
        basis_lay.addWidget(QLabel("ES - SPX (pt):"))
        self.spin_basis = QDoubleSpinBox()
        self.spin_basis.setRange(0, 100)
        self.spin_basis.setSingleStep(1.0)
        self.spin_basis.setDecimals(1)
        self.spin_basis.setValue(24.0)
        self.spin_basis.setSuffix(" pt")
        basis_lay.addWidget(self.spin_basis)
        ctrl_layout.addWidget(basis_grp)

        # 밴드 설정
        band_grp = QGroupBox("델타 밴드 설정")
        band_lay = QVBoxLayout(band_grp)

        def spin_row(label, key, lo, hi, step, val):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            sp = QDoubleSpinBox()
            sp.setRange(lo, hi)
            sp.setSingleStep(step)
            sp.setValue(val)
            sp.setDecimals(2)
            sp.valueChanged.connect(lambda v, k=key: self._on_band_change(k, v))
            row.addWidget(sp)
            return row

        band_lay.addLayout(spin_row("중립 하단", "neutral_lo", -1, 1, 0.05, 0.40))
        band_lay.addLayout(spin_row("중립 상단", "neutral_hi", -1, 1, 0.05, 0.60))

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        band_lay.addWidget(sep)

        band_lay.addLayout(spin_row("과열 기준",  "hot_lo",   0,  1, 0.05, 0.60))
        band_lay.addLayout(spin_row("과냉 기준",  "cold_hi", -1,  1, 0.05, 0.40))
        ctrl_layout.addWidget(band_grp)

        # 표시 옵션
        disp_grp = QGroupBox("표시 옵션")
        disp_lay = QVBoxLayout(disp_grp)
        self.chk_show_band  = QCheckBox("밴드 영역 표시")
        self.chk_show_band.setChecked(True)
        self.chk_show_gamma = QCheckBox("Gamma 오버레이")
        self.chk_show_gamma.setChecked(False)
        self.chk_show_iv    = QCheckBox("IV 오버레이")
        self.chk_show_iv.setChecked(False)
        self.chk_rth        = QCheckBox("본장만 표시 (09:30~16:00 ET)")
        self.chk_rth.setChecked(True)
        for chk in (self.chk_show_band, self.chk_show_gamma,
                    self.chk_show_iv, self.chk_rth):
            chk.stateChanged.connect(self._refresh_plot)
            disp_lay.addWidget(chk)
        ctrl_layout.addWidget(disp_grp)

        # 시리즈 선택
        series_grp = QGroupBox("시리즈 선택")
        series_lay = QVBoxLayout(series_grp)
        self.combo_series = QComboBox()
        self.combo_series.addItem("전체 (겹치기)")
        self.combo_series.currentIndexChanged.connect(self._refresh_plot)
        series_lay.addWidget(self.combo_series)
        ctrl_layout.addWidget(series_grp)

        # 스프레드 설정
        spread_grp = QGroupBox("스프레드 설정")
        spread_lay = QVBoxLayout(spread_grp)

        # 스프레드 폭
        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("스프레드 폭:"))
        self.spin_spread_width = QDoubleSpinBox()
        self.spin_spread_width.setRange(1, 200)
        self.spin_spread_width.setSingleStep(5)
        self.spin_spread_width.setDecimals(0)
        self.spin_spread_width.setValue(5)
        self.spin_spread_width.setSuffix(" pt")
        self.spin_spread_width.valueChanged.connect(lambda _: (
            self._on_call_leg1_changed(self.combo_call_leg1.currentIndex()),
            self._on_put_leg1_changed(self.combo_put_leg1.currentIndex()),
        ))
        width_row.addWidget(self.spin_spread_width)
        spread_lay.addLayout(width_row)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color:#E0E0E0;"); spread_lay.addWidget(sep2)

        # 콜 스프레드
        self.chk_call_spread = QCheckBox("콜 스프레드 표시")
        self.chk_call_spread.setChecked(False)
        self.chk_call_spread.stateChanged.connect(self._refresh_plot)
        spread_lay.addWidget(self.chk_call_spread)

        spread_lay.addWidget(QLabel("레그1 (Long Call):"))
        self.combo_call_leg1 = QComboBox()
        self.combo_call_leg1.addItem("-- 선택 --")
        self.combo_call_leg1.currentIndexChanged.connect(self._on_call_leg1_changed)
        spread_lay.addWidget(self.combo_call_leg1)
        self.lbl_call_leg2 = QLabel("레그2: --")
        self.lbl_call_leg2.setStyleSheet("color:#555; font-size:11px;")
        spread_lay.addWidget(self.lbl_call_leg2)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color:#E0E0E0;"); spread_lay.addWidget(sep3)

        # 풋 스프레드
        self.chk_put_spread = QCheckBox("풋 스프레드 표시")
        self.chk_put_spread.setChecked(False)
        self.chk_put_spread.stateChanged.connect(self._refresh_plot)
        spread_lay.addWidget(self.chk_put_spread)

        spread_lay.addWidget(QLabel("레그1 (Long Put):"))
        self.combo_put_leg1 = QComboBox()
        self.combo_put_leg1.addItem("-- 선택 --")
        self.combo_put_leg1.currentIndexChanged.connect(self._on_put_leg1_changed)
        spread_lay.addWidget(self.combo_put_leg1)
        self.lbl_put_leg2 = QLabel("레그2: --")
        self.lbl_put_leg2.setStyleSheet("color:#555; font-size:11px;")
        spread_lay.addWidget(self.lbl_put_leg2)

        ctrl_layout.addWidget(spread_grp)

        # 그리기 버튼
        self.btn_plot = QPushButton("▶  그리기")
        self.btn_plot.setFixedHeight(38)
        self.btn_plot.setStyleSheet(
            "QPushButton { background: #1565C0; color: white; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #1976D2; }"
            "QPushButton:disabled { background: #BDBDBD; }"
        )
        self.btn_plot.clicked.connect(self._refresh_plot)
        ctrl_layout.addWidget(self.btn_plot)
        ctrl_layout.addStretch()

        # 오른쪽 차트 패널
        chart_panel  = QWidget()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)

        self.fig, self.axes = plt.subplots(
            2, 1, figsize=(10, 7),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor=COLORS["bg"],
        )
        self.fig.tight_layout(pad=3.0)
        self.canvas = FigureCanvas(self.fig)
        self.nav    = NavToolbar(self.canvas, self)
        chart_layout.addWidget(self.nav)
        chart_layout.addWidget(self.canvas)

        root.addWidget(ctrl_panel)
        root.addWidget(chart_panel, stretch=1)

        self.status_bar = QStatusBar(self)
        self.status_bar.showMessage("CSV 파일 또는 폴더를 열어주세요.")
        chart_layout.addWidget(self.status_bar)

    # ── 이벤트 ───────────────────────────────────────────────────

    def _on_band_change(self, key, val):
        self._band[key] = val

    def _open_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "옵션 CSV 선택", "", "CSV Files (*.csv)")
        if files:
            self._load_files([Path(f) for f in files])

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder:
            return
        csvs = sorted(Path(folder).glob("*.csv"))
        if not csvs:
            self.status_bar.showMessage("CSV 파일 없음")
            return
        self._load_files(csvs)

    def _load_files(self, files: list):
        if self._thread and self._thread.isRunning():
            return
        self.btn_plot.setEnabled(False)
        self.status_bar.showMessage(f"{len(files)}개 파일 로드 중...")
        self._thread = CalcThread(files, basis=self.spin_basis.value())
        self._thread.done.connect(self._on_load_done)
        self._thread.error.connect(lambda e: self.status_bar.showMessage(f"오류: {e}"))
        self._thread.status.connect(self.status_bar.showMessage)
        self._thread.start()

    def _on_load_done(self, results: list):
        self._data = results
        self.btn_plot.setEnabled(True)
        self.combo_series.blockSignals(True)
        self.combo_series.clear()
        self.combo_series.addItem("전체 (겹치기)")
        for r in results:
            self.combo_series.addItem(r["label"])
        self.combo_series.blockSignals(False)
        self.lbl_loaded.setText(f"파일 {len(results)}개 로드됨")
        self.status_bar.showMessage(f"로드 완료: {len(results)}개 시리즈")
        self._update_spread_panel()
        self._refresh_plot()

    def _update_spread_panel(self):
        """로드된 데이터로 스프레드 레그1 콤보 업데이트"""
        calls = sorted([d["label"] for d in self._data if d["label"].endswith("_C")],
                       key=lambda x: parse_option_fname(x+".csv")["strike"] if parse_option_fname(x+".csv") else 0)
        puts  = sorted([d["label"] for d in self._data if d["label"].endswith("_P")],
                       key=lambda x: parse_option_fname(x+".csv")["strike"] if parse_option_fname(x+".csv") else 0)

        self.combo_call_leg1.blockSignals(True)
        self.combo_call_leg1.clear()
        self.combo_call_leg1.addItem("-- 선택 --")
        for c in calls:
            self.combo_call_leg1.addItem(c)
        self.combo_call_leg1.blockSignals(False)

        self.combo_put_leg1.blockSignals(True)
        self.combo_put_leg1.clear()
        self.combo_put_leg1.addItem("-- 선택 --")
        for p in puts:
            self.combo_put_leg1.addItem(p)
        self.combo_put_leg1.blockSignals(False)

    def _on_call_leg1_changed(self, idx):
        """콜 레그1 선택 시 레그2 자동 설정"""
        if idx <= 0:
            self.lbl_call_leg2.setText("레그2: --")
            return
        label = self.combo_call_leg1.currentText()
        meta  = parse_option_fname(label + ".csv")
        if not meta:
            return
        width  = int(self.spin_spread_width.value())
        k2     = meta["strike"] + width
        leg2   = f"SPXW_{meta['exp_date'].strftime('%Y%m%d')}_{k2}_C"
        exists = any(d["label"] == leg2 for d in self._data)
        self.lbl_call_leg2.setText(f"레그2: {leg2}" + ("" if exists else " ⚠없음"))
        self._refresh_plot()

    def _on_put_leg1_changed(self, idx):
        """풋 레그1 선택 시 레그2 자동 설정"""
        if idx <= 0:
            self.lbl_put_leg2.setText("레그2: --")
            return
        label = self.combo_put_leg1.currentText()
        meta  = parse_option_fname(label + ".csv")
        if not meta:
            return
        width  = int(self.spin_spread_width.value())
        k2     = meta["strike"] - width
        leg2   = f"SPXW_{meta['exp_date'].strftime('%Y%m%d')}_{k2}_P"
        exists = any(d["label"] == leg2 for d in self._data)
        self.lbl_put_leg2.setText(f"레그2: {leg2}" + ("" if exists else " ⚠없음"))
        self._refresh_plot()

    def _get_series_by_label(self, label):
        for d in self._data:
            if d["label"] == label:
                return d
        return None

    def _compute_spread_rows(self, leg1_label, leg2_label, rth_filter_fn, spread_type="C"):
        """두 레그의 델타 차이(스프레드 델타) 계산.
        유동성 부족으로 음수가 나오는 경우 0으로 클리핑.
        콜 스프레드: 0 이상, 풋 스프레드: 0 이하로 클리핑.
        """
        s1 = self._get_series_by_label(leg1_label)
        s2 = self._get_series_by_label(leg2_label)
        if not s1 or not s2:
            return []
        r1 = {r["dt"]: r for r in rth_filter_fn(s1["rows"])}
        r2 = {r["dt"]: r for r in rth_filter_fn(s2["rows"])}
        common = sorted(set(r1) & set(r2))
        rows = []
        for dt in common:
            raw_delta = r1[dt]["delta"] - r2[dt]["delta"]
            if spread_type == "C":
                delta = max(raw_delta, 0.0)   # 콜 스프레드: 0 이상
            else:
                delta = min(raw_delta, 0.0)   # 풋 스프레드: 0 이하
            rows.append({
                "dt":    dt,
                "delta": delta,
                "iv":    (r1[dt]["iv"] + r2[dt]["iv"]) / 2,
                "gamma": r1[dt]["gamma"] - r2[dt]["gamma"],
            })
        return rows

    # ── 차트 ─────────────────────────────────────────────────────

    def _refresh_plot(self):
        if not self._data:
            return

        idx = self.combo_series.currentIndex()
        series_list = self._data if idx <= 0 else [self._data[idx - 1]]

        ax_main, ax_sub = self.axes
        ax_main.cla(); ax_sub.cla()

        show_band  = self.chk_show_band.isChecked()
        show_gamma = self.chk_show_gamma.isChecked()
        show_iv    = self.chk_show_iv.isChecked()
        rth_only   = self.chk_rth.isChecked()

        def _rth_filter(rows):
            if not rth_only:
                return rows
            # KST 본장: 22:30~익일05:00 (자정을 넘으므로 or 조건)
            return [r for r in rows
                    if r["dt"].hour * 60 + r["dt"].minute >= 22 * 60 + 30
                    or  r["dt"].hour * 60 + r["dt"].minute <= 5 * 60]

        b       = self._band
        all_dts = []

        for series in series_list:
            label = series["label"]
            rows  = _rth_filter(series["rows"])
            if not rows:
                continue

            meta  = parse_option_fname(label + ".csv")
            right = meta["right"] if meta else "C"

            dts    = [r["dt"]         for r in rows]
            deltas = [r["delta"]      for r in rows]
            gammas = [r["gamma"]      for r in rows]
            ivs    = [r["iv"] * 100   for r in rows]

            all_dts.extend(dts)
            base_color = "#E53935" if right == "C" else "#1E88E5"
            alpha      = 0.7 if len(series_list) > 1 else 1.0

            ax_main.plot(dts, deltas, color=base_color, alpha=alpha,
                         linewidth=1.4, label=label)
            self._highlight_zones(ax_main, dts, deltas, b, right)

            if show_gamma:
                ax_sub.plot(dts, gammas, color=base_color, alpha=alpha,
                            linewidth=1.2, label=f"Gamma {label}")
            if show_iv:
                ax_sub.plot(dts, ivs, color=base_color, alpha=alpha,
                            linewidth=1.2, linestyle="--", label=f"IV% {label}")

        # ── 콜 스프레드 델타 오버레이
        if self.chk_call_spread.isChecked() and self.combo_call_leg1.currentIndex() > 0:
            leg1_label = self.combo_call_leg1.currentText()
            meta1 = parse_option_fname(leg1_label + ".csv")
            if meta1:
                width  = int(self.spin_spread_width.value())
                k2     = meta1["strike"] + width
                leg2_label = f"SPXW_{meta1['exp_date'].strftime('%Y%m%d')}_{k2}_C"
                sp_rows = self._compute_spread_rows(leg1_label, leg2_label, _rth_filter, "C")
                if sp_rows:
                    sp_dts    = [r["dt"]    for r in sp_rows]
                    sp_deltas = [r["delta"] for r in sp_rows]
                    sp_ivs    = [r["iv"]*100 for r in sp_rows]
                    all_dts.extend(sp_dts)
                    ax_main.plot(sp_dts, sp_deltas, color="#FF6F00", linewidth=2.0,
                                 label=f"C-Spread {leg1_label[-6:]}/{k2}")
                    if show_iv:
                        ax_sub.plot(sp_dts, sp_ivs, color="#FF6F00", linewidth=1.2,
                                    linestyle="--", label=f"IV% C-Sprd")
                else:
                    self.status_bar.showMessage(f"콜 스프레드: 레그2({leg2_label}) 데이터 없음")

        # ── 풋 스프레드 델타 오버레이
        if self.chk_put_spread.isChecked() and self.combo_put_leg1.currentIndex() > 0:
            leg1_label = self.combo_put_leg1.currentText()
            meta1 = parse_option_fname(leg1_label + ".csv")
            if meta1:
                width  = int(self.spin_spread_width.value())
                k2     = meta1["strike"] - width
                leg2_label = f"SPXW_{meta1['exp_date'].strftime('%Y%m%d')}_{k2}_P"
                sp_rows = self._compute_spread_rows(leg1_label, leg2_label, _rth_filter, "P")
                if sp_rows:
                    sp_dts    = [r["dt"]    for r in sp_rows]
                    sp_deltas = [r["delta"] for r in sp_rows]
                    sp_ivs    = [r["iv"]*100 for r in sp_rows]
                    all_dts.extend(sp_dts)
                    ax_main.plot(sp_dts, sp_deltas, color="#7B1FA2", linewidth=2.0,
                                 label=f"P-Spread {leg1_label[-6:]}/{k2}")
                    if show_iv:
                        ax_sub.plot(sp_dts, sp_ivs, color="#7B1FA2", linewidth=1.2,
                                    linestyle="--", label=f"IV% P-Sprd")
                else:
                    self.status_bar.showMessage(f"풋 스프레드: 레그2({leg2_label}) 데이터 없음")

        if show_band and all_dts:
            ax_main.axhspan(b["neutral_lo"], b["neutral_hi"],
                            color=COLORS["band_neutral"], alpha=0.4, zorder=0)
            ax_main.axhspan(b["hot_lo"], b["hot_hi"],
                            color=COLORS["band_hot"], alpha=0.35, zorder=0)
            ax_main.axhspan(b["cold_lo"], b["cold_hi"],
                            color=COLORS["band_cold"], alpha=0.35, zorder=0)
            dt_min = min(all_dts)
            for y, lbl, c in [
                (b["neutral_lo"], "중립 하단", "#1565C0"),
                (b["neutral_hi"], "중립 상단", "#1565C0"),
                (b["hot_lo"],     "과열",      "#C62828"),
                (b["cold_hi"],    "과냉",      "#2E7D32"),
            ]:
                ax_main.axhline(y, color=c, linewidth=0.8, linestyle="--", alpha=0.7)
                ax_main.text(dt_min, y + 0.01, lbl, fontsize=8, color=c, alpha=0.8)

        ax_main.axhline(0,   color="#9E9E9E", linewidth=0.6, linestyle=":")
        ax_main.axhline(0.5, color="#9E9E9E", linewidth=0.6, linestyle=":", alpha=0.5)

        ax_main.set_ylabel("Delta", fontsize=10)
        ax_main.set_ylim(-1.05, 1.05)
        ax_main.set_facecolor(COLORS["bg"])
        ax_main.grid(True, color=COLORS["grid"], linewidth=0.5)
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax_main.tick_params(axis="x", labelsize=8)
        if series_list:
            ax_main.legend(loc="upper left", fontsize=7,
                           ncol=min(len(series_list), 4))

        sub_label = []
        if show_gamma: sub_label.append("Gamma")
        if show_iv:    sub_label.append("IV (%)")
        ax_sub.set_ylabel(" / ".join(sub_label) if sub_label else "", fontsize=9)
        ax_sub.set_facecolor(COLORS["bg"])
        ax_sub.grid(True, color=COLORS["grid"], linewidth=0.5)
        ax_sub.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax_sub.tick_params(axis="x", labelsize=8)
        if sub_label:
            ax_sub.legend(loc="upper left", fontsize=7)

        if series_list and series_list[0]["rows"]:
            title_date = series_list[0]["rows"][0]["dt"].strftime("%Y-%m-%d")
            ax_main.set_title(
                f"Delta Band  ·  {title_date}  ({len(series_list)}개 시리즈)",
                fontsize=11, pad=8,
            )

        self.fig.tight_layout(pad=2.5)
        self.canvas.draw()
        self.status_bar.showMessage("차트 업데이트 완료")

    def _highlight_zones(self, ax, dts, deltas, b, right):
        if len(dts) < 2:
            return
        in_zone = None; zone_start = None
        for i, (dt, d) in enumerate(zip(dts, deltas)):
            zone = "hot" if d >= b["hot_lo"] else ("cold" if d <= b["cold_hi"] else None)
            if zone != in_zone:
                if in_zone and zone_start is not None:
                    color = COLORS["band_hot"] if in_zone == "hot" else COLORS["band_cold"]
                    ax.axvspan(zone_start, dts[i - 1], color=color, alpha=0.5, zorder=1)
                in_zone = zone; zone_start = dt
        if in_zone and zone_start is not None:
            color = COLORS["band_hot"] if in_zone == "hot" else COLORS["band_cold"]
            ax.axvspan(zone_start, dts[-1], color=color, alpha=0.5, zorder=1)


# ══════════════════════════════════════════════════════════════════
# ④ DeltaBandGrid — main.py 탭 통합용 별칭
# ══════════════════════════════════════════════════════════════════

# DeltaBandViewer 가 이미 QWidget 이므로 그대로 사용
DeltaBandGrid = DeltaBandViewer

# attach_callput / on_tab_activate / on_tab_deactivate 메서드 패치
def _attach_callput(self, tab):
    pass  # 과거 조회 전용 — 실시간 불필요 시 빈 구현

DeltaBandViewer.attach_callput    = _attach_callput
DeltaBandViewer.on_tab_activate   = lambda self: None
DeltaBandViewer.on_tab_deactivate = lambda self: None


# ══════════════════════════════════════════════════════════════════
# ⑤ 진입점 (단독 실행)
# ══════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SPX 델타 밴드 뷰어")
    viewer = DeltaBandViewer()
    viewer.resize(1280, 800)
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()