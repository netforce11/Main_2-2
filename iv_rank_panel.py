"""
iv_rank_panel.py — IVPanel: 행사가별 현재IV / 5일평균 / 대비 테이블  [S10]
════════════════════════════════════════════════════════════════════
데이터 소스:
  - 현재 IV   : tab_greeks._cell_data[(expiry, strike, side)]['iv']
                또는 CallPutGrid.call_data/put_data 의 'iv' 키
  - 5일 평균  : greeks_db.load_snapshots(past_day) → iv 컬럼 평균
  - 갱신 주기 : QTimer 2초 (실시간 tick 반영)

컬럼 구성:
  행사가 | C IV% | C 5일평균 | C 대비 | P IV% | P 5일평균 | P 대비
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush


# ── 색상 상수 ────────────────────────────────────────────────────
_C_HEADER  = "#06060e"
_C_BG      = "#05050f"
_C_STRIKE  = "#ffd700"
_C_CALL    = "#4fc3f7"   # 콜 IV — 하늘색
_C_PUT     = "#ff8a80"   # 풋 IV — 연빨강
_C_AVG     = "#888"
_C_UP      = "#00e676"   # 5일 평균 대비 높음
_C_DOWN    = "#ff5252"   # 5일 평균 대비 낮음
_C_FLAT    = "#aaa"      # 변화 미미 (±2% 이내)

_TBL_SS = (
    "QTableWidget{background:#05050f;color:#ccc;"
    "gridline-color:#1a1a3a;font-size:11px;"
    "border:1px solid #2a2a5a;}"
    "QHeaderView::section{background:#06060e;color:#5dade2;"
    "border:1px solid #1a1a3a;font-size:10px;padding:1px;}"
    "QTableWidget::item{padding:1px;}"
    "QTableWidget::item:selected{background:#1c3a6a;color:#fff;}"
)


def _mk(text: str, color: str = "#ccc") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return it


class IVPanel(QWidget):
    """
    콜-풋 체인 옆에 배치되는 IV 비교 테이블 패널.

    사용법:
        panel = IVPanel(main_win)
        panel.set_source(callput_grid)   # CallPutGrid 인스턴스 연결
        panel.refresh()                  # 수동 갱신
    """

    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self._main      = main_win
        self._callput   = None          # CallPutGrid ref (set_source 로 주입)
        self._greeks    = None          # GreeksGrid ref  (자동 탐색)
        self._hist_avg: Dict[Tuple[float, str], float] = {}   # (strike, side) → 5일 평균 IV
        self._hist_loaded = False
        self._build()

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    # ── UI 구성 ─────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # 헤더 행
        hdr = QHBoxLayout(); hdr.setSpacing(4)
        self._lbl_title = QLabel("📊 IV 비교")
        self._lbl_title.setStyleSheet(
            "color:#5dade2;font-size:11px;font-weight:bold;border:none;")
        self._lbl_status = QLabel("―")
        self._lbl_status.setStyleSheet(
            "color:#555;font-size:9px;border:none;")
        self._lbl_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        btn_reload = QPushButton("↺")
        btn_reload.setFixedSize(22, 20)
        btn_reload.setToolTip("5일 평균 재계산")
        btn_reload.setStyleSheet(
            "QPushButton{background:#1a1a3a;color:#5dade2;font-size:11px;"
            "border:1px solid #2a2a5a;border-radius:3px;}"
            "QPushButton:hover{background:#2a2a5a;}")
        btn_reload.clicked.connect(self._reload_hist)
        hdr.addWidget(self._lbl_title)
        hdr.addStretch()
        hdr.addWidget(self._lbl_status)
        hdr.addWidget(btn_reload)
        root.addLayout(hdr)

        # 범례
        leg = QHBoxLayout(); leg.setSpacing(8)
        for txt, col in [("↑ 평균 초과", _C_UP), ("↓ 평균 미만", _C_DOWN), ("― 데이터없음", _C_FLAT)]:
            lb = QLabel(txt); lb.setStyleSheet(f"color:{col};font-size:9px;border:none;")
            leg.addWidget(lb)
        leg.addStretch()
        root.addLayout(leg)

        # 테이블
        # 컬럼: 행사가 | C IV% | C 5일평균 | C 대비 | P IV% | P 5일평균 | P 대비
        self._tbl = QTableWidget(0, 7)
        self._tbl.setHorizontalHeaderLabels(
            ["행사가", "C IV%", "C 평균", "C↑↓", "P IV%", "P 평균", "P↑↓"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.verticalHeader().setDefaultSectionSize(22)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setMinimumHeight(0)
        self._tbl.setStyleSheet(_TBL_SS)
        root.addWidget(self._tbl, 1)

    # ── 외부 연결 ────────────────────────────────────────────────
    def set_source(self, callput_grid):
        """CallPutGrid 인스턴스를 주입. _greeks도 자동 탐색."""
        self._callput = callput_grid
        # GreeksGrid 탐색 (main_win.tab_greeks 또는 tab_callput._main.tab_greeks)
        self._greeks = getattr(self._main, 'tab_greeks', None)
        # 히스토리 최초 로드
        self._reload_hist()

    # ── 5일 평균 계산 ────────────────────────────────────────────
    def _reload_hist(self):
        """greeks_db에서 최근 5일 스냅샷 로드 → strike/side별 IV 평균."""
        try:
            import greeks_db as gdb
            days = gdb.available_days()
            past_days = days[-6:-1] if len(days) >= 2 else days[:-1]
            if not past_days:
                self._lbl_status.setText("DB 없음")
                return

            acc: Dict[Tuple[float, str], List[float]] = {}
            for day in past_days:
                for row in gdb.load_snapshots(day):
                    if not row.get('iv'): continue
                    k = (row['strike'], row['side'])
                    acc.setdefault(k, []).append(row['iv'])

            self._hist_avg = {k: sum(v) / len(v) for k, v in acc.items()}
            self._hist_loaded = bool(self._hist_avg)
            self._lbl_status.setText(
                f"5일평균: {len(past_days)}일치 {len(self._hist_avg)}건")
        except Exception as e:
            self._lbl_status.setText(f"DB 오류: {e}")

    # ── 갱신 ─────────────────────────────────────────────────────
    def refresh(self):
        """2초마다 호출 — 현재 IV 스냅샷을 읽어 테이블 갱신."""
        if not self._callput:
            return

        # 1) 현재 IV 수집
        # 우선순위: GreeksGrid._cell_data → CallPutGrid.call_data/put_data
        iv_now = self._collect_iv_from_greeks()
        if not iv_now:
            iv_now = self._collect_iv_from_chain()
        if not iv_now:
            return

        # 2) 행사가 목록 (콜+풋 합집합, 정렬)
        strikes = sorted({s for s, _ in iv_now.keys()})
        if not strikes:
            return

        # 3) 테이블 행 수 맞추기
        if self._tbl.rowCount() != len(strikes):
            self._tbl.setRowCount(len(strikes))

        # 4) 행 채우기
        cp = self._callput
        atm = None
        if getattr(cp, 'und_price', None):
            atm = cp.und_price

        for r, st in enumerate(strikes):
            iv_c = iv_now.get((st, 'C'))
            iv_p = iv_now.get((st, 'P'))
            avg_c = self._hist_avg.get((st, 'C'))
            avg_p = self._hist_avg.get((st, 'P'))

            # 행사가 — ATM 강조
            st_color = "#ffd700"
            if atm and abs(st - atm) < 2.5:
                st_color = "#ffffff"
            self._tbl.setItem(r, 0, _mk(f"{int(st)}", st_color))

            # 콜 IV
            self._tbl.setItem(r, 1, _mk(
                f"{iv_c*100:.1f}" if iv_c else "―",
                _C_CALL if iv_c else _C_FLAT))
            # 콜 5일평균
            self._tbl.setItem(r, 2, _mk(
                f"{avg_c*100:.1f}" if avg_c else "―",
                _C_AVG))
            # 콜 대비
            self._tbl.setItem(r, 3, *[self._diff_item(iv_c, avg_c)])

            # 풋 IV
            self._tbl.setItem(r, 4, _mk(
                f"{iv_p*100:.1f}" if iv_p else "―",
                _C_PUT if iv_p else _C_FLAT))
            # 풋 5일평균
            self._tbl.setItem(r, 5, _mk(
                f"{avg_p*100:.1f}" if avg_p else "―",
                _C_AVG))
            # 풋 대비
            self._tbl.setItem(r, 6, *[self._diff_item(iv_p, avg_p)])

    def _diff_item(self, iv_now: Optional[float],
                   iv_avg: Optional[float]) -> QTableWidgetItem:
        """현재 IV vs 5일평균 대비 셀."""
        if iv_now is None:
            return _mk("―", _C_FLAT)
        if iv_avg is None or iv_avg == 0:
            return _mk("N/A", _C_FLAT)

        diff_pct = (iv_now - iv_avg) / iv_avg * 100
        if diff_pct > 2.0:
            txt = f"↑{diff_pct:+.1f}%"
            col = _C_UP
        elif diff_pct < -2.0:
            txt = f"↓{diff_pct:+.1f}%"
            col = _C_DOWN
        else:
            txt = f"{diff_pct:+.1f}%"
            col = _C_FLAT
        return _mk(txt, col)

    # ── IV 수집 헬퍼 ────────────────────────────────────────────
    def _collect_iv_from_greeks(self) -> Dict[Tuple[float, str], float]:
        """GreeksGrid._cell_data에서 현재 만기 IV 수집."""
        g = self._greeks
        if not g or not hasattr(g, '_cell_data') or not g._cell_data:
            return {}
        expiry = getattr(g, '_expiry', '')
        result = {}
        for (exp, strike, side), d in g._cell_data.items():
            if exp != expiry:
                continue
            iv = d.get('iv')
            if iv and 0 < iv < 10:
                result[(strike, side)] = iv
        return result

    def _collect_iv_from_chain(self) -> Dict[Tuple[float, str], float]:
        """CallPutGrid.call_data/put_data에서 IV 수집 (Greeks 없을 때 폴백)."""
        cp = self._callput
        if not cp:
            return {}
        result = {}
        for i, st in enumerate(getattr(cp, 'call_strikes', [])):
            from core import REQ_CALL
            d = cp.call_data.get(REQ_CALL + i, {})
            iv = d.get('iv')
            if iv and 0 < iv < 10:
                result[(float(st), 'C')] = iv
        for i, st in enumerate(getattr(cp, 'put_strikes', [])):
            from core import REQ_PUT
            d = cp.put_data.get(REQ_PUT + i, {})
            iv = d.get('iv')
            if iv and 0 < iv < 10:
                result[(float(st), 'P')] = iv
        return result
