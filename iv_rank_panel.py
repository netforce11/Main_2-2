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

[수정]
  ① 굵은 글씨: font-weight:bold 테이블 전체 + 헤더에 추가
  ② C평균/P평균 버그: DB의 side 값 'CALL'/'PUT' → 'C'/'P' 로 정규화
  ③ strike 타입 불일치(int vs float) fallback 조회 추가
  ④ 상태 표시에 실제 로딩 건수 표시
════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush, QFont


# ── 색상 상수 ────────────────────────────────────────────────────
_C_HEADER  = "#06060e"
_C_BG      = "#05050f"
_C_STRIKE  = "#ffd700"
_C_CALL    = "#4fc3f7"
_C_PUT     = "#ff8a80"
_C_AVG     = "#888"
_C_UP      = "#00e676"
_C_DOWN    = "#ff5252"
_C_FLAT    = "#aaa"

# ① 굵은 글씨: font-weight:bold 테이블 전체 + 헤더에 추가
_TBL_SS = (
    "QTableWidget{background:#05050f;color:#ccc;"
    "gridline-color:#1a1a3a;font-size:11px;font-weight:bold;"
    "border:1px solid #2a2a5a;}"
    "QHeaderView::section{background:#06060e;color:#5dade2;"
    "border:1px solid #1a1a3a;font-size:10px;font-weight:bold;padding:1px;}"
    "QTableWidget::item{padding:1px;}"
    "QTableWidget::item:selected{background:#1c3a6a;color:#fff;}"
)

_BOLD_FONT = QFont()
_BOLD_FONT.setBold(True)


def _mk(text: str, color: str = "#ccc") -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    it.setFont(_BOLD_FONT)                      # ① 굵은 글씨
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return it


def _norm_side(raw: str) -> str:
    """② 'CALL' → 'C',  'PUT' → 'P',  이미 'C'/'P' 는 그대로."""
    r = (raw or "").strip().upper()
    if r in ("CALL", "C"): return "C"
    if r in ("PUT",  "P"): return "P"
    return r


def _flt(val) -> float:
    """③ strike 를 float 으로 통일 (int/str/float 혼합 대응)."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


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
        self._callput   = None
        self._greeks    = None
        self._hist_avg: Dict[Tuple[float, str], float] = {}
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

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        self._lbl_title = QLabel("📊 IV 비교")
        self._lbl_title.setStyleSheet(
            "color:#5dade2;font-size:11px;font-weight:bold;border:none;")
        self._lbl_status = QLabel("―")
        self._lbl_status.setStyleSheet("color:#555;font-size:9px;border:none;")
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

        leg = QHBoxLayout(); leg.setSpacing(8)
        for txt, col in [("↑ 평균 초과", _C_UP), ("↓ 평균 미만", _C_DOWN), ("― 데이터없음", _C_FLAT)]:
            lb = QLabel(txt); lb.setStyleSheet(f"color:{col};font-size:9px;border:none;")
            leg.addWidget(lb)
        leg.addStretch()
        root.addLayout(leg)

        self._tbl = QTableWidget(0, 7)
        self._tbl.setHorizontalHeaderLabels(
            ["행사가", "C IV%", "C 평균", "C↑↓", "P IV%", "P 평균", "P↑↓"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.verticalHeader().setDefaultSectionSize(22)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setMinimumHeight(0)
        self._tbl.setStyleSheet(_TBL_SS)        # ① 굵은 글씨 스타일시트
        root.addWidget(self._tbl, 1)

    # ── 외부 연결 ────────────────────────────────────────────────
    def set_source(self, callput_grid):
        self._callput = callput_grid
        self._greeks  = getattr(self._main, 'tab_greeks', None)
        self._reload_hist()

    # ── 5일 평균 계산 ────────────────────────────────────────────
    def _reload_hist(self):
        """② side 정규화 + ③ strike float 통일 적용."""
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
                    if not row.get('iv'):
                        continue
                    side_raw   = row.get('side', '')
                    strike_raw = row.get('strike', 0)
                    side_norm  = _norm_side(side_raw)       # ② 정규화
                    strike_flt = _flt(strike_raw)           # ③ float 통일
                    k = (strike_flt, side_norm)
                    acc.setdefault(k, []).append(float(row['iv']))

            self._hist_avg = {k: sum(v) / len(v) for k, v in acc.items()}
            self._hist_loaded = bool(self._hist_avg)
            # ④ 실제 로딩 건수 표시
            self._lbl_status.setText(
                f"5일평균: {len(past_days)}일치 {len(self._hist_avg)}건")
        except Exception as e:
            self._lbl_status.setText(f"DB 오류: {e}")

    # ── 갱신 ─────────────────────────────────────────────────────
    def refresh(self):
        if not self._callput:
            return

        iv_now = self._collect_iv_from_greeks()
        if not iv_now:
            iv_now = self._collect_iv_from_chain()
        if not iv_now:
            return

        strikes = sorted({s for s, _ in iv_now.keys()})
        if not strikes:
            return

        if self._tbl.rowCount() != len(strikes):
            self._tbl.setRowCount(len(strikes))

        cp  = self._callput
        atm = getattr(cp, 'und_price', None)

        for r, st in enumerate(strikes):
            iv_c  = iv_now.get((st, 'C'))
            iv_p  = iv_now.get((st, 'P'))
            # ③ float 키로 조회, 없으면 int 키로 fallback
            avg_c = self._hist_avg.get((st, 'C')) or self._hist_avg.get((int(st), 'C'))
            avg_p = self._hist_avg.get((st, 'P')) or self._hist_avg.get((int(st), 'P'))

            st_color = "#ffd700"
            if atm and abs(st - atm) < 2.5:
                st_color = "#ffffff"
            self._tbl.setItem(r, 0, _mk(f"{int(st)}", st_color))

            self._tbl.setItem(r, 1, _mk(
                f"{iv_c*100:.1f}" if iv_c else "―",
                _C_CALL if iv_c else _C_FLAT))
            self._tbl.setItem(r, 2, _mk(
                f"{avg_c*100:.1f}" if avg_c else "―",
                _C_AVG))
            self._tbl.setItem(r, 3, self._diff_item(iv_c, avg_c))

            self._tbl.setItem(r, 4, _mk(
                f"{iv_p*100:.1f}" if iv_p else "―",
                _C_PUT if iv_p else _C_FLAT))
            self._tbl.setItem(r, 5, _mk(
                f"{avg_p*100:.1f}" if avg_p else "―",
                _C_AVG))
            self._tbl.setItem(r, 6, self._diff_item(iv_p, avg_p))

        # ④ 상태에 실제 로딩 건수
        self._lbl_status.setText(
            f"IV 비교  현재 {len(strikes)}행  평균DB {len(self._hist_avg)}건")

    def _diff_item(self, iv_now: Optional[float],
                   iv_avg: Optional[float]) -> QTableWidgetItem:
        if iv_now is None:
            return _mk("―", _C_FLAT)
        if iv_avg is None or iv_avg == 0:
            return _mk("N/A", _C_FLAT)
        diff_pct = (iv_now - iv_avg) / iv_avg * 100
        if diff_pct > 2.0:
            return _mk(f"↑{diff_pct:+.1f}%", _C_UP)
        elif diff_pct < -2.0:
            return _mk(f"↓{diff_pct:+.1f}%", _C_DOWN)
        else:
            return _mk(f"{diff_pct:+.1f}%", _C_FLAT)

    # ── IV 수집 헬퍼 ────────────────────────────────────────────
    def _collect_iv_from_greeks(self) -> Dict[Tuple[float, str], float]:
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
                result[(_flt(strike), _norm_side(side))] = iv   # ②③
        return result

    def _collect_iv_from_chain(self) -> Dict[Tuple[float, str], float]:
        cp = self._callput
        if not cp:
            return {}
        result = {}
        for i, st in enumerate(getattr(cp, 'call_strikes', [])):
            from core import REQ_CALL
            d = cp.call_data.get(REQ_CALL + i, {})
            iv = d.get('iv')
            if iv and 0 < iv < 10:
                result[(_flt(st), 'C')] = iv                    # ③
        for i, st in enumerate(getattr(cp, 'put_strikes', [])):
            from core import REQ_PUT
            d = cp.put_data.get(REQ_PUT + i, {})
            iv = d.get('iv')
            if iv and 0 < iv < 10:
                result[(_flt(st), 'P')] = iv                    # ③
        return result