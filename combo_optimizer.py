"""
combo_optimizer.py — 복합 전략 탭: Cost Optimizer
════════════════════════════════════════════════════════════════
v2.2 변경사항:
  - ATM 거리 기준 필터 추가 (ATM Dist %)
  - POP (Probability of Profit) 컬럼 추가
    · IV% 수동 입력 스핀박스 + 잔존일 입력
    · scipy 없이 math.erf 로 N(d2) 계산
  - QThread 백그라운드 탐색 (_SearchWorker)
    · 아이언 콘도르 O(n⁴) UI 프리징 해결
    · 모든 전략 일관되게 Worker 로 실행
════════════════════════════════════════════════════════════════
"""

import math
from itertools import combinations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSpinBox, QDoubleSpinBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QBrush

from combo_constants import mk_item


# ── 전략별 레그 방향 정의 ──────────────────────────────────────
_STRAT_LEGS = {
    "콜 스프레드":        [("C", "BUY"),  ("C", "SELL")],
    "콜 데빗 스프레드":   [("C", "BUY"),  ("C", "SELL")],
    "풋 스프레드":        [("P", "BUY"),  ("P", "SELL")],
    "풋 데빗 스프레드":   [("P", "BUY"),  ("P", "SELL")],
    "스트래들":           [("C", "BUY"),  ("P", "BUY")],
    "스트랭글":           [("C", "BUY"),  ("P", "BUY")],
    "아이언 콘도르":      [("P", "BUY"),  ("P", "SELL"),
                           ("C", "SELL"), ("C", "BUY")],
}

_CALL_SPREAD_TYPES = {"콜 스프레드", "콜 데빗 스프레드"}
_PUT_SPREAD_TYPES  = {"풋 스프레드", "풋 데빗 스프레드"}


def _strat_key(strat_text: str) -> str:
    for key in _STRAT_LEGS:
        if key in strat_text:
            return key
    return ""


# ══════════════════════════════════════════════════════════════
# POP 계산 (Black-Scholes N(d2), scipy 불필요)
# ══════════════════════════════════════════════════════════════
def _norm_cdf(x: float) -> float:
    """표준 정규 누적분포 — math.erf 이용."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _calc_pop(S: float, K: float, T_days: float,
              iv_pct: float, cp: str = "C") -> float:
    """
    만기 시 해당 레그가 OTM(수익)으로 끝날 확률.
    콜 매도 POP = 1 - N(d2)  / 풋 매도 POP = N(-d2) = 1 - N(d2)
    매수 전략(스트래들/스트랭글) = ITM 확률 근사 = N(|d2|)
    """
    T     = T_days / 365.0
    sigma = iv_pct  / 100.0
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d2 = (math.log(S / K) + (-0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    except (ValueError, ZeroDivisionError):
        return 0.0
    if cp.upper() == "C":
        return (1.0 - _norm_cdf(d2)) * 100.0   # 콜이 OTM 으로 끝날 확률
    else:
        return _norm_cdf(d2) * 100.0            # 풋이 OTM 으로 끝날 확률


# ══════════════════════════════════════════════════════════════
# QThread Worker
# ══════════════════════════════════════════════════════════════
class _SearchWorker(QThread):
    """탐색 로직을 백그라운드 스레드에서 실행."""
    done    = pyqtSignal(list)   # 결과 리스트
    error   = pyqtSignal(str)    # 에러 메시지

    def __init__(self, fn, *args):
        super().__init__()
        self._fn   = fn
        self._args = args

    def run(self):
        try:
            result = self._fn(*self._args)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ══════════════════════════════════════════════════════════════
class OptimizerPanelMixin:
    """Cost Optimizer 패널 빌드 + 탐색 로직 Mixin."""

    # ──────────────────────────────────────────────────────────
    # UI 빌드
    # ──────────────────────────────────────────────────────────
    def _build_optimizer_panel(self) -> QGroupBox:
        gb = QGroupBox("🔍 Cost Optimizer  (허용 손실 기반 행사가 탐색)")
        v  = QVBoxLayout(gb)
        v.setSpacing(6); v.setContentsMargins(8, 8, 8, 8)

        # ── 조건 입력 그리드 ────────────────────────────────
        cond_grid = QGridLayout(); cond_grid.setSpacing(8)

        # Row 0 ─────────────────────────────────────────────
        # 최대 허용 손실
        cond_grid.addWidget(self._opt_label("최대 허용 손실 ($)"), 0, 0)
        self.opt_max_loss = QDoubleSpinBox()
        self.opt_max_loss.setRange(1, 999999)
        self.opt_max_loss.setValue(300)
        self.opt_max_loss.setPrefix("$ ")
        self.opt_max_loss.setSingleStep(50)
        self.opt_max_loss.setFixedHeight(26)
        self.opt_max_loss.setStyleSheet(self._opt_spin_style())
        cond_grid.addWidget(self.opt_max_loss, 0, 1)

        # 최소 수익률
        cond_grid.addWidget(self._opt_label("최소 수익률 (%)"), 0, 2)
        self.opt_min_ror = QDoubleSpinBox()
        self.opt_min_ror.setRange(0, 9999)
        self.opt_min_ror.setValue(0)
        self.opt_min_ror.setSuffix(" %")
        self.opt_min_ror.setSpecialValueText("미적용")
        self.opt_min_ror.setSingleStep(10)
        self.opt_min_ror.setFixedHeight(26)
        self.opt_min_ror.setStyleSheet(self._opt_spin_style())
        cond_grid.addWidget(self.opt_min_ror, 0, 3)

        # 수량
        cond_grid.addWidget(self._opt_label("계약 수량"), 0, 4)
        self.opt_qty = QSpinBox()
        self.opt_qty.setRange(1, 100)
        self.opt_qty.setValue(1)
        self.opt_qty.setSuffix(" 계약")
        self.opt_qty.setFixedHeight(26)
        self.opt_qty.setStyleSheet(self._opt_spin_style())
        cond_grid.addWidget(self.opt_qty, 0, 5)

        # Row 1 ─────────────────────────────────────────────
        # 상위 N개
        cond_grid.addWidget(self._opt_label("상위 결과"), 1, 0)
        self.opt_top_n = QSpinBox()
        self.opt_top_n.setRange(5, 200)
        self.opt_top_n.setValue(20)
        self.opt_top_n.setSuffix(" 개")
        self.opt_top_n.setFixedHeight(26)
        self.opt_top_n.setStyleSheet(self._opt_spin_style())
        cond_grid.addWidget(self.opt_top_n, 1, 1)

        # ★ ATM 거리 필터 (신규)
        cond_grid.addWidget(self._opt_label("ATM 거리 (%)"), 1, 2)
        self.opt_atm_dist = QDoubleSpinBox()
        self.opt_atm_dist.setRange(0, 50)
        self.opt_atm_dist.setValue(0)
        self.opt_atm_dist.setSuffix(" %")
        self.opt_atm_dist.setSpecialValueText("미적용")
        self.opt_atm_dist.setSingleStep(0.5)
        self.opt_atm_dist.setDecimals(1)
        self.opt_atm_dist.setFixedHeight(26)
        self.opt_atm_dist.setStyleSheet(self._opt_spin_style())
        self.opt_atm_dist.setToolTip(
            "행사가(들)의 ATM 거리 상한.\n"
            "예: 2.0% → 현재가 ±2% 이내 행사가만 탐색.\n"
            "0 = 미적용 (전체 탐색)")
        cond_grid.addWidget(self.opt_atm_dist, 1, 3)

        # ★ IV 입력 (POP 계산용, 신규)
        cond_grid.addWidget(self._opt_label("IV (%)"), 1, 4)
        self.opt_iv = QDoubleSpinBox()
        self.opt_iv.setRange(1, 300)
        self.opt_iv.setValue(20)
        self.opt_iv.setSuffix(" %")
        self.opt_iv.setSingleStep(1)
        self.opt_iv.setDecimals(1)
        self.opt_iv.setFixedHeight(26)
        self.opt_iv.setStyleSheet(self._opt_spin_style())
        self.opt_iv.setToolTip("POP 계산에 사용할 내재 변동성(IV).\nIBKR 옵션 체인에서 확인 후 입력.")
        cond_grid.addWidget(self.opt_iv, 1, 5)

        # Row 2 ─────────────────────────────────────────────
        # ★ 잔존일 (POP 계산용, 신규)
        cond_grid.addWidget(self._opt_label("잔존일 (DTE)"), 2, 0)
        self.opt_dte = QSpinBox()
        self.opt_dte.setRange(0, 365)
        self.opt_dte.setValue(1)
        self.opt_dte.setSuffix(" 일")
        self.opt_dte.setFixedHeight(26)
        self.opt_dte.setStyleSheet(self._opt_spin_style())
        self.opt_dte.setToolTip("만기까지 잔존일. 0DTE = 0.")
        cond_grid.addWidget(self.opt_dte, 2, 1)

        # ★ 최소 POP 필터 (신규)
        cond_grid.addWidget(self._opt_label("최소 POP (%)"), 2, 2)
        self.opt_min_pop = QDoubleSpinBox()
        self.opt_min_pop.setRange(0, 99)
        self.opt_min_pop.setValue(0)
        self.opt_min_pop.setSuffix(" %")
        self.opt_min_pop.setSpecialValueText("미적용")
        self.opt_min_pop.setSingleStep(5)
        self.opt_min_pop.setDecimals(0)
        self.opt_min_pop.setFixedHeight(26)
        self.opt_min_pop.setStyleSheet(self._opt_spin_style())
        self.opt_min_pop.setToolTip("이 확률 미만 조합 제외.\n예: 70 → POP 70% 이상만 표시.")
        cond_grid.addWidget(self.opt_min_pop, 2, 3)

        sort_lbl = QLabel("정렬: 최대 이익 ↓  (동률 시 수익률 ↓)")
        sort_lbl.setStyleSheet("color:#aaa;font-size:10px;border:none;")
        cond_grid.addWidget(sort_lbl, 2, 4, 1, 2)

        v.addLayout(cond_grid)

        # ── 실행 버튼 ──────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self.btn_opt_run = QPushButton("🔍 탐색 실행")
        self.btn_opt_run.setStyleSheet(
            "background:#1a3a6a;color:#90caf9;font-size:13px;"
            "font-weight:bold;padding:7px 18px;border-radius:4px;"
            "border:1px solid #3a5a9a;")
        self.btn_opt_run.clicked.connect(self._run_optimizer)

        self.btn_opt_apply = QPushButton("✅ 선택 → 레그 적용")
        self.btn_opt_apply.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-size:12px;"
            "font-weight:bold;padding:7px 14px;border-radius:4px;"
            "border:1px solid #2a8a4a;")
        self.btn_opt_apply.clicked.connect(self._fill_legs_from_result)
        self.btn_opt_apply.setEnabled(False)

        self.lbl_opt_status = QLabel("체인 데이터 수신 후 탐색 가능합니다.")
        self.lbl_opt_status.setStyleSheet("color:#888;font-size:11px;border:none;")

        btn_row.addWidget(self.btn_opt_run)
        btn_row.addWidget(self.btn_opt_apply)
        btn_row.addStretch()
        btn_row.addWidget(self.lbl_opt_status)
        v.addLayout(btn_row)

        # ── 결과 테이블 (10컬럼) ───────────────────────────
        # 기존 8 + ATM Dist + POP
        self.tbl_opt_result = QTableWidget(0, 10)
        self.tbl_opt_result.setHorizontalHeaderLabels([
            "전략", "매수 행사가", "매도 행사가",
            "순 프리미엄($)", "최대 이익($)", "최대 손실($)",
            "수익률(%)", "R:R",
            "ATM 거리(%)",   # ★ 신규
            "POP(%)",        # ★ 신규
        ])
        hh = self.tbl_opt_result.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        # ATM거리·POP 컬럼은 약간 좁게
        hh.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(9, QHeaderView.ResizeToContents)
        self.tbl_opt_result.verticalHeader().setVisible(False)
        self.tbl_opt_result.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_opt_result.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_opt_result.setAlternatingRowColors(True)
        self.tbl_opt_result.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-weight:bold;font-size:11px;}"
            "QTableWidget::item:selected{background:#1a3a6a;color:#fff;}")
        self.tbl_opt_result.cellClicked.connect(self._on_opt_result_click)
        self.tbl_opt_result.setMinimumHeight(180)
        v.addWidget(self.tbl_opt_result, 1)

        gb.setMinimumHeight(320)
        return gb

    # ── 스타일 헬퍼 ───────────────────────────────────────
    @staticmethod
    def _opt_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#aaa;font-size:11px;border:none;")
        return lbl

    @staticmethod
    def _opt_spin_style() -> str:
        return (
            "QDoubleSpinBox, QSpinBox{"
            "background:#0a0a1e;color:#ffd700;"
            "border:1px solid #3a3a6a;border-radius:3px;"
            "font-size:12px;padding:2px 4px;}"
        )

    # ──────────────────────────────────────────────────────
    # 공통 파라미터 수집
    # ──────────────────────────────────────────────────────
    def _opt_params(self) -> dict:
        return {
            "budget":   self.opt_max_loss.value(),
            "min_ror":  self.opt_min_ror.value(),
            "qty":      self.opt_qty.value(),
            "atm_dist": self.opt_atm_dist.value(),   # 0 = 미적용
            "iv":       self.opt_iv.value(),
            "dte":      self.opt_dte.value(),
            "min_pop":  self.opt_min_pop.value(),     # 0 = 미적용
        }

    # ──────────────────────────────────────────────────────
    # ATM 거리 계산 헬퍼
    # ──────────────────────────────────────────────────────
    def _atm_dist_pct(self, strike: float) -> float:
        """현재가 대비 행사가 거리 (%)."""
        if not self._und_price:
            return 0.0
        return abs(strike - self._und_price) / self._und_price * 100.0

    def _atm_ok(self, strike: float, limit: float) -> bool:
        """ATM 거리 필터 통과 여부."""
        if limit == 0:
            return True
        return self._atm_dist_pct(strike) <= limit

    # ──────────────────────────────────────────────────────
    # 탐색 실행 (Worker 로 비동기)
    # ──────────────────────────────────────────────────────
    def _run_optimizer(self):
        strat_text = self.combo_strat.currentText()
        skey       = _strat_key(strat_text)

        if not skey:
            self.lbl_opt_status.setText(
                "⚠️  커버드콜·프로텍티브풋은 탐색 대상 아닙니다.")
            return
        if not self._call_strikes and not self._put_strikes:
            self.lbl_opt_status.setText("⚠️  먼저 체인 데이터를 동기화하세요.")
            return

        p = self._opt_params()

        # 전략별 탐색 함수 선택
        if skey in _CALL_SPREAD_TYPES:
            fn   = self._search_vertical
            args = (self._call_strikes, self._chain_call, "C",
                    "콜 데빗 스프레드", p["qty"], p["budget"],
                    p["min_ror"], True, p)
        elif skey in _PUT_SPREAD_TYPES:
            fn   = self._search_vertical
            args = (self._put_strikes, self._chain_put, "P",
                    "풋 데빗 스프레드", p["qty"], p["budget"],
                    p["min_ror"], False, p)
        elif skey == "스트래들":
            fn   = self._search_straddle
            args = (p["qty"], p["budget"], p["min_ror"], p)
        elif skey == "스트랭글":
            fn   = self._search_strangle
            args = (p["qty"], p["budget"], p["min_ror"], p)
        elif skey == "아이언 콘도르":
            fn   = self._search_iron_condor
            args = (p["qty"], p["budget"], p["min_ror"], p)
        else:
            return

        # UI 잠금
        self.btn_opt_run.setEnabled(False)
        self.lbl_opt_status.setText("🔄 탐색 중...")

        self._search_worker = _SearchWorker(fn, *args)
        self._search_worker.done.connect(self._on_search_done)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_done(self, results: list):
        self.btn_opt_run.setEnabled(True)
        top_n   = self.opt_top_n.value()
        p       = self._opt_params()
        min_pop = p["min_pop"]

        # POP 필터
        if min_pop > 0:
            results = [r for r in results if r.get("pop", 0) >= min_pop]

        results.sort(key=lambda x: (-x["max_profit"], -x["ror"]))
        results = results[:top_n]

        self._populate_opt_table(results)
        count = len(results)
        self.lbl_opt_status.setText(
            f"✅ {count}개 조합 발견  |  예산 ${p['budget']:,.0f}"
            + (f"  |  ATM±{p['atm_dist']}%" if p['atm_dist'] else "")
            + (f"  |  POP≥{p['min_pop']:.0f}%" if min_pop else ""))
        self.btn_opt_apply.setEnabled(count > 0)
        self._log(
            f"[Optimizer] {self.combo_strat.currentText()} — "
            f"{count}개 결과 (예산 ${p['budget']:,.0f}"
            + (f", ATM±{p['atm_dist']}%" if p['atm_dist'] else "")
            + (f", POP≥{p['min_pop']:.0f}%" if min_pop else "") + ")")

    def _on_search_error(self, msg: str):
        self.btn_opt_run.setEnabled(True)
        self.lbl_opt_status.setText(f"❌ 오류: {msg}")
        self._log(f"[Optimizer] 오류: {msg}")

    # ──────────────────────────────────────────────────────
    # 수직 스프레드 탐색
    # ──────────────────────────────────────────────────────
    def _search_vertical(self, strikes, chain, cp, label,
                         qty, budget, min_ror, buy_lower, p) -> list:
        results   = []
        atm_limit = p["atm_dist"]
        iv        = p["iv"]
        dte       = p["dte"]
        und       = self._und_price or 0

        valid = [(k, v) for k, v in chain.items() if v and k in strikes]
        valid.sort(key=lambda x: x[0])

        for (k1, p1), (k2, p2) in combinations(valid, 2):
            if buy_lower:
                buy_k, buy_p   = k1, p1
                sell_k, sell_p = k2, p2
            else:
                buy_k, buy_p   = k2, p2
                sell_k, sell_p = k1, p1

            # ★ ATM 거리 필터: 매수 레그 기준
            if atm_limit and und and self._atm_dist_pct(buy_k) > atm_limit:
                continue

            width    = abs(buy_k - sell_k)
            net_prem = buy_p - sell_p
            if net_prem <= 0:
                continue
            max_loss   = net_prem * qty * 100
            max_profit = (width - net_prem) * qty * 100
            if max_profit <= 0 or max_loss > budget:
                continue
            ror = (max_profit / max_loss * 100) if max_loss else 0
            if min_ror and ror < min_ror:
                continue

            # ★ ATM 거리 표시값 (매수 레그 기준)
            atm_d = self._atm_dist_pct(buy_k) if und else 0.0

            # ★ POP: 매도 레그가 OTM으로 끝날 확률
            pop = _calc_pop(und or buy_k, sell_k, dte, iv, cp) if und else 0.0

            results.append({
                "label":      label,
                "buy_k":      buy_k,
                "sell_k":     sell_k,
                "net_prem":   net_prem,
                "max_profit": max_profit,
                "max_loss":   max_loss,
                "ror":        ror,
                "rr":         max_profit / max_loss if max_loss else 0,
                "cp":         cp,
                "qty":        qty,
                "atm_dist":   atm_d,
                "pop":        pop,
            })
        return results

    # ──────────────────────────────────────────────────────
    # 스트래들 탐색
    # ──────────────────────────────────────────────────────
    def _search_straddle(self, qty, budget, min_ror, p) -> list:
        results   = []
        atm_limit = p["atm_dist"]
        iv        = p["iv"]
        dte       = p["dte"]
        und       = self._und_price or 0

        call_map = {k: v for k, v in self._chain_call.items() if v}
        put_map  = {k: v for k, v in self._chain_put.items()  if v}

        for strike in set(call_map) & set(put_map):
            if atm_limit and und and self._atm_dist_pct(strike) > atm_limit:
                continue

            cp_ = call_map[strike]
            pp_ = put_map[strike]
            total_prem = (cp_ + pp_) * qty * 100
            if total_prem > budget:
                continue

            be_range   = cp_ + pp_
            max_loss   = total_prem
            max_profit = be_range * qty * 100 * 2  # 근사
            ror = max_profit / max_loss * 100 if max_loss else 0
            if min_ror and ror < min_ror:
                continue

            atm_d = self._atm_dist_pct(strike) if und else 0.0
            # 스트래들: 콜/풋 양방향 → 평균 POP (참고용)
            pop_c = _calc_pop(und or strike, strike, dte, iv, "C") if und else 0.0
            pop_p = _calc_pop(und or strike, strike, dte, iv, "P") if und else 0.0
            pop   = (pop_c + pop_p) / 2

            results.append({
                "label":      "스트래들",
                "buy_k":      strike,
                "sell_k":     strike,
                "net_prem":   cp_ + pp_,
                "max_profit": max_profit,
                "max_loss":   max_loss,
                "ror":        ror,
                "rr":         max_profit / max_loss if max_loss else 0,
                "cp":         "C+P",
                "qty":        qty,
                "atm_dist":   atm_d,
                "pop":        pop,
            })
        return results

    # ──────────────────────────────────────────────────────
    # 스트랭글 탐색
    # ──────────────────────────────────────────────────────
    def _search_strangle(self, qty, budget, min_ror, p) -> list:
        results   = []
        atm_limit = p["atm_dist"]
        iv        = p["iv"]
        dte       = p["dte"]
        und       = self._und_price or 0

        call_valid = [(k, v) for k, v in self._chain_call.items() if v]
        put_valid  = [(k, v) for k, v in self._chain_put.items()  if v]

        for (ck, cp_) in call_valid:
            for (pk, pp_) in put_valid:
                if ck <= pk:
                    continue
                if und and (ck < und or pk > und):
                    continue   # OTM 필터

                # ★ ATM 거리: 콜/풋 각각 체크
                if atm_limit and und:
                    if (self._atm_dist_pct(ck) > atm_limit or
                            self._atm_dist_pct(pk) > atm_limit):
                        continue

                total_prem = (cp_ + pp_) * qty * 100
                if total_prem > budget:
                    continue
                max_loss   = total_prem
                max_profit = (ck - pk - cp_ - pp_) * qty * 100
                if max_profit <= 0:
                    continue
                ror = max_profit / max_loss * 100 if max_loss else 0
                if min_ror and ror < min_ror:
                    continue

                # ATM 거리: 중간값
                atm_d = (self._atm_dist_pct(ck) + self._atm_dist_pct(pk)) / 2 if und else 0.0
                # POP: 콜/풋 각각 OTM 확률 평균
                pop_c = _calc_pop(und, ck, dte, iv, "C") if und else 0.0
                pop_p = _calc_pop(und, pk, dte, iv, "P") if und else 0.0
                pop   = (pop_c + pop_p) / 2

                results.append({
                    "label":      "스트랭글",
                    "buy_k":      pk,
                    "sell_k":     ck,
                    "net_prem":   cp_ + pp_,
                    "max_profit": max_profit,
                    "max_loss":   max_loss,
                    "ror":        ror,
                    "rr":         max_profit / max_loss if max_loss else 0,
                    "cp":         "C+P",
                    "qty":        qty,
                    "atm_dist":   atm_d,
                    "pop":        pop,
                })
        return results

    # ──────────────────────────────────────────────────────
    # 아이언 콘도르 탐색 (O(n⁴) — Worker 필수)
    # ──────────────────────────────────────────────────────
    def _search_iron_condor(self, qty, budget, min_ror, p) -> list:
        results   = []
        atm_limit = p["atm_dist"]
        iv        = p["iv"]
        dte       = p["dte"]
        und       = self._und_price or 0

        call_valid = sorted(
            [(k, v) for k, v in self._chain_call.items() if v],
            key=lambda x: x[0])
        put_valid  = sorted(
            [(k, v) for k, v in self._chain_put.items() if v],
            key=lambda x: x[0])

        for (bp_k, bp_p), (sp_k, sp_p) in combinations(put_valid, 2):
            if bp_k >= sp_k:
                continue
            # ★ ATM 거리: sell_put 기준
            if atm_limit and und and self._atm_dist_pct(sp_k) > atm_limit:
                continue

            for (sc_k, sc_p), (bc_k, bc_p) in combinations(call_valid, 2):
                if sc_k >= bc_k:
                    continue
                if sp_k >= sc_k:
                    continue
                # ★ ATM 거리: sell_call 기준
                if atm_limit and und and self._atm_dist_pct(sc_k) > atm_limit:
                    continue

                credit     = (sp_p - bp_p + sc_p - bc_p) * qty * 100
                if credit <= 0:
                    continue
                put_width  = (sp_k - bp_k) * qty * 100
                call_width = (bc_k - sc_k) * qty * 100
                max_loss   = max(put_width, call_width) - credit
                if max_loss <= 0 or max_loss > budget:
                    continue
                max_profit = credit
                ror = max_profit / max_loss * 100 if max_loss else 0
                if min_ror and ror < min_ror:
                    continue

                # ATM 거리: sell_put + sell_call 평균
                atm_d = (self._atm_dist_pct(sp_k) + self._atm_dist_pct(sc_k)) / 2 if und else 0.0
                # POP: 매도 레그 두 개 모두 OTM 확률 평균
                pop_p = _calc_pop(und, sp_k, dte, iv, "P") if und else 0.0
                pop_c = _calc_pop(und, sc_k, dte, iv, "C") if und else 0.0
                pop   = (pop_p + pop_c) / 2

                results.append({
                    "label":      "아이언 콘도르",
                    "buy_k":      f"{bp_k}/{sp_k}",
                    "sell_k":     f"{sc_k}/{bc_k}",
                    "net_prem":   -(sp_p - bp_p + sc_p - bc_p),
                    "max_profit": max_profit,
                    "max_loss":   max_loss,
                    "ror":        ror,
                    "rr":         max_profit / max_loss if max_loss else 0,
                    "cp":         "IC",
                    "qty":        qty,
                    "atm_dist":   atm_d,
                    "pop":        pop,
                })
        return results

    # ──────────────────────────────────────────────────────
    # 결과 테이블 채우기
    # ──────────────────────────────────────────────────────
    def _populate_opt_table(self, results: list):
        self.tbl_opt_result.setRowCount(0)
        for res in results:
            r = self.tbl_opt_result.rowCount()
            self.tbl_opt_result.insertRow(r)

            profit_col = "#00ff88" if res["max_profit"] > 0 else "#ff4444"
            ror_col    = "#00ff88" if res["ror"] >= 50  else "#ffd700"

            # POP 컬러: 70%↑ 초록 / 50%↑ 노랑 / 미만 빨강
            pop = res.get("pop", 0)
            pop_col = ("#00ff88" if pop >= 70
                       else "#ffd700" if pop >= 50
                       else "#ff6666")

            # ATM 거리 컬러: 2% 이내 초록 / 5% 이내 노랑 / 그 외 기본
            atm_d = res.get("atm_dist", 0)
            atm_col = ("#00e676" if atm_d <= 2
                       else "#ffd700" if atm_d <= 5
                       else "#aaaaaa")

            self.tbl_opt_result.setItem(r, 0, mk_item(res["label"],           "#90caf9"))
            self.tbl_opt_result.setItem(r, 1, mk_item(str(res["buy_k"]),      "#ffd700"))
            self.tbl_opt_result.setItem(r, 2, mk_item(str(res["sell_k"]),     "#ff9999"))
            self.tbl_opt_result.setItem(r, 3, mk_item(f"${res['net_prem']:.2f}", "#aaa"))
            self.tbl_opt_result.setItem(r, 4, mk_item(
                f"${res['max_profit']:,.2f}", profit_col))
            self.tbl_opt_result.setItem(r, 5, mk_item(
                f"${res['max_loss']:,.2f}", "#ff4444"))
            self.tbl_opt_result.setItem(r, 6, mk_item(
                f"{res['ror']:.1f}%", ror_col))
            self.tbl_opt_result.setItem(r, 7, mk_item(
                f"{res['rr']:.2f}:1", "#ff8844"))
            self.tbl_opt_result.setItem(r, 8, mk_item(          # ★ ATM 거리
                f"{atm_d:.1f}%", atm_col))
            self.tbl_opt_result.setItem(r, 9, mk_item(          # ★ POP
                f"{pop:.1f}%" if pop > 0 else "—", pop_col))

        self._opt_results = results

    # ──────────────────────────────────────────────────────
    # 행 클릭
    # ──────────────────────────────────────────────────────
    def _on_opt_result_click(self, row, col):
        self._opt_selected_row = row
        self.btn_opt_apply.setEnabled(True)

    # ──────────────────────────────────────────────────────
    # 선택 결과 → 레그 테이블 자동 입력
    # ──────────────────────────────────────────────────────
    def _fill_legs_from_result(self):
        if not hasattr(self, "_opt_results") or not self._opt_results:
            return
        row = getattr(self, "_opt_selected_row",
                      self.tbl_opt_result.currentRow())
        if row < 0 or row >= len(self._opt_results):
            row = 0

        res        = self._opt_results[row]
        qty        = str(res["qty"])
        cp         = res["cp"]
        expiry     = (self._expiry_list[0][0] if self._expiry_list else "")

        from combo_ui_right import _fmt_expiry
        exp_display = _fmt_expiry(expiry)

        for i in range(self.combo_strat.count()):
            if res["label"] in self.combo_strat.itemText(i):
                self.combo_strat.blockSignals(True)
                self.combo_strat.setCurrentIndex(i)
                self.combo_strat.blockSignals(False)
                self._on_strat_change(i)
                break

        from PyQt5.QtCore import QTimer
        def _apply():
            n      = self.tbl_legs.rowCount()
            buy_k  = res["buy_k"]
            sell_k = res["sell_k"]

            if cp in ("C", "P"):
                if n >= 1:
                    self._set_leg_row(0, str(int(buy_k)),
                                      f"{self._get_chain_price(cp, buy_k):.2f}",
                                      qty, exp_display)
                if n >= 2:
                    self._set_leg_row(1, str(int(sell_k)),
                                      f"{self._get_chain_price(cp, sell_k):.2f}",
                                      qty, exp_display)

            elif cp == "C+P":
                if n >= 1:
                    self._set_leg_row(0, str(int(sell_k)),
                                      f"{self._get_chain_price('C', sell_k):.2f}",
                                      qty, exp_display)
                if n >= 2:
                    self._set_leg_row(1, str(int(buy_k)),
                                      f"{self._get_chain_price('P', buy_k):.2f}",
                                      qty, exp_display)

            elif cp == "IC":
                try:
                    bp, sp = [float(x) for x in str(buy_k).split("/")]
                    sc, bc = [float(x) for x in str(sell_k).split("/")]
                    for idx, (k, c) in enumerate([(bp, "P"), (sp, "P"),
                                                   (sc, "C"), (bc, "C")]):
                        if idx < n:
                            self._set_leg_row(
                                idx, str(int(k)),
                                f"{self._get_chain_price(c, k):.2f}",
                                qty, exp_display)
                except Exception:
                    pass

            pop_str = (f"  POP {res['pop']:.1f}%"
                       if res.get("pop", 0) > 0 else "")
            atm_str = (f"  ATM±{res['atm_dist']:.1f}%"
                       if res.get("atm_dist", 0) > 0 else "")
            self._log(
                f"[Optimizer] 레그 적용: {res['label']}  "
                f"매수{buy_k} / 매도{sell_k}  "
                f"최대이익 ${res['max_profit']:,.2f}  "
                f"최대손실 ${res['max_loss']:,.2f}"
                + pop_str + atm_str)

        QTimer.singleShot(50, _apply)

    # ──────────────────────────────────────────────────────
    # 헬퍼
    # ──────────────────────────────────────────────────────
    def _set_leg_row(self, row: int, strike: str,
                     prem: str, qty: str, expiry: str):
        def _s(col, val):
            it = self.tbl_legs.item(row, col)
            if it:
                it.setText(val)
        _s(3, strike); _s(4, prem); _s(5, qty); _s(6, expiry)

    def _get_chain_price(self, cp: str, strike: float) -> float:
        chain = self._chain_call if cp == "C" else self._chain_put
        return chain.get(strike) or 0.0