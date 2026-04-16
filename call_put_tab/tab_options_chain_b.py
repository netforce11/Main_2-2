# call_put_tab/tab_options_chain_b.py
"""
B 모드 체인 테이블:
  행사가 | 현재가 | 등락률 | 델타 | 이론가 | 차이

- 이론가 : 블랙숄즈(Black-Scholes) 직접 계산
- 차이   : 이론가 - 현재가
- scipy 없이 순수 수식으로 구현 (외부 의존성 없음)
"""
import math
from typing import Dict, List, Optional
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

COLS_B = ["행사가", "현재가", "등락률", "델타", "이론가", "차이"]

_COL_IDX = {c: i for i, c in enumerate(COLS_B)}

# ──────────────────────────────────────────────────────────────
# 블랙숄즈 수식 (scipy 불필요 — 순수 Python)
# ──────────────────────────────────────────────────────────────
def _norm_cdf(x: float) -> float:
    """표준정규 누적분포 (Abramowitz & Stegun 근사)"""
    a = (0.319381530, -0.356563782, 1.781477937,
         -1.821255978, 1.330274429)
    k = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = k * (a[0] + k * (a[1] + k * (a[2] + k * (a[3] + k * a[4]))))
    pdf  = math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    cdf  = 1.0 - pdf * poly
    return cdf if x >= 0 else 1.0 - cdf


def black_scholes(S: float, K: float, T: float,
                  r: float, sigma: float,
                  option_type: str = "C") -> float:
    """
    블랙숄즈 이론가 계산.

    Parameters
    ----------
    S           : 기초자산 현재가
    K           : 행사가
    T           : 잔존 연수 (예: 0.5 = 6개월)
    r           : 무위험 이자율 (소수, 예: 0.045)
    sigma       : 내재변동성 IV (소수, 예: 0.20)
    option_type : "C" 콜 / "P" 풋
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if option_type == "C":
        return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


# ──────────────────────────────────────────────────────────────
# B 모드 테이블 위젯
# ──────────────────────────────────────────────────────────────
class ChainBTable(QWidget):
    """
    B 모드 전용 콜 또는 풋 체인 테이블.
    reset(strikes) → 행사가 목록 세팅
    update_row(...)  → tick 수신 시 호출
    """

    def __init__(self, side: str = "C", parent=None):
        """side: "C" (콜) / "P" (풋)"""
        super().__init__(parent)
        self.side = side
        self._row_map: Dict[float, int] = {}   # strike → row index
        self._build_ui()

    # ──────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────
    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        title_text = "콜 (B)" if self.side == "C" else "풋 (B)"
        title = QLabel(title_text)
        title.setStyleSheet(
            "color:#90caf9; font-size:11px; font-weight:bold;"
            "padding:2px 4px; background:#1e2a3a;"
        )
        lay.addWidget(title)

        self._tbl = QTableWidget(0, len(COLS_B))
        self._tbl.setHorizontalHeaderLabels(COLS_B)
        self._tbl.setStyleSheet(
            "QTableWidget{background:#0f0f1e; color:#ddd;"
            "  font-size:11px; gridline-color:#2a2a3a;}"
            "QHeaderView::section{background:#1e1e3a; color:#aaa;"
            "  font-size:10px; padding:2px;}"
            "QTableWidget::item{padding:1px 3px;}"
        )
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        lay.addWidget(self._tbl)

    # ──────────────────────────────────────────────────────
    # 외부 인터페이스
    # ──────────────────────────────────────────────────────
    def reset(self, strikes: List[float]):
        """행사가 목록으로 테이블 초기화 (행 순서: 오름차순)"""
        sorted_k = sorted(strikes)
        self._tbl.setRowCount(len(sorted_k))
        self._row_map.clear()
        for i, k in enumerate(sorted_k):
            self._row_map[k] = i
            self._set(i, _COL_IDX["행사가"], f"{k:.1f}")
            # 나머지 컬럼 초기화
            for col in range(1, len(COLS_B)):
                self._set(i, col, "-")

    def update_row(self,
                   strike: float,
                   last: Optional[float],
                   prev_close: Optional[float],
                   delta: Optional[float],
                   iv: Optional[float],
                   und_price: float,
                   T: float,
                   r: float = 0.045):
        """
        한 행 데이터 업데이트 + 블랙숄즈 이론가 계산.

        Parameters
        ----------
        strike     : 행사가
        last       : 현재가 (최근 체결가)
        prev_close : 전일 종가 (등락률 계산용)
        delta      : IB에서 수신한 Delta 값
        iv         : 내재변동성 (소수)
        und_price  : 기초자산 현재가
        T          : 잔존 연수
        r          : 무위험 이자율 (기본 4.5%)
        """
        row = self._row_map.get(strike)
        if row is None:
            return

        # 이론가 계산
        _iv    = iv if iv and iv > 0 else 0.2
        theo   = black_scholes(und_price, strike, T, r, _iv, self.side)

        # 현재가
        last_v = last if last and last > 0 else None
        self._set(row, _COL_IDX["현재가"],
                  f"{last_v:.2f}" if last_v else "-")

        # 등락률
        if last_v and prev_close and prev_close > 0:
            pct = (last_v - prev_close) / prev_close * 100
            self._set(row, _COL_IDX["등락률"], f"{pct:+.2f}%",
                      color="#ef5350" if pct < 0 else "#26a69a")
        else:
            self._set(row, _COL_IDX["등락률"], "-")

        # 델타
        self._set(row, _COL_IDX["델타"],
                  f"{delta:.3f}" if delta is not None else "-")

        # 이론가
        self._set(row, _COL_IDX["이론가"], f"{theo:.2f}")

        # 차이 = 이론가 - 현재가
        if last_v:
            diff = theo - last_v
            self._set(row, _COL_IDX["차이"], f"{diff:+.2f}",
                      color="#ef5350" if diff < 0 else "#26a69a")
        else:
            self._set(row, _COL_IDX["차이"], "-")

    # ──────────────────────────────────────────────────────
    # 헬퍼
    # ──────────────────────────────────────────────────────
    def _set(self, row: int, col: int, text: str, color: Optional[str] = None):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        self._tbl.setItem(row, col, item)