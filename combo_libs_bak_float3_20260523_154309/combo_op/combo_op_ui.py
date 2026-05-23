"""
combo_op_ui.py — Cost Optimizer 패널 UI 빌드
────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_ui.py
포함:
  _build_optimizer_panel()  — QGroupBox 반환
  _opt_label()              — 레이블 스타일 헬퍼
  _opt_spin_style()         — 스핀박스 스타일 헬퍼
────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox,
    QTableWidget, QHeaderView,
    QAbstractItemView, QSpinBox, QDoubleSpinBox,
)


def _build_optimizer_panel(self) -> QGroupBox:
    """Cost Optimizer 조건 입력 + 결과 테이블 QGroupBox 반환."""
    gb = QGroupBox("🔍 Cost Optimizer  (허용 손실 기반 행사가 탐색)")
    v  = QVBoxLayout(gb)
    v.setSpacing(6); v.setContentsMargins(8, 8, 8, 8)

    # ── 조건 입력 그리드 ─────────────────────────────────────
    cond_grid = QGridLayout(); cond_grid.setSpacing(8)

    # Row 0 — 최대 허용 손실 / 최소 수익률 / 계약 수량
    cond_grid.addWidget(_opt_label("최대 허용 손실 ($)"), 0, 0)
    self.opt_max_loss = QDoubleSpinBox()
    self.opt_max_loss.setRange(1, 999999); self.opt_max_loss.setValue(300)
    self.opt_max_loss.setPrefix("$ "); self.opt_max_loss.setSingleStep(50)
    self.opt_max_loss.setFixedHeight(26)
    self.opt_max_loss.setStyleSheet(_opt_spin_style())
    cond_grid.addWidget(self.opt_max_loss, 0, 1)

    cond_grid.addWidget(_opt_label("최소 수익률 (%)"), 0, 2)
    self.opt_min_ror = QDoubleSpinBox()
    self.opt_min_ror.setRange(0, 9999); self.opt_min_ror.setValue(0)
    self.opt_min_ror.setSuffix(" %"); self.opt_min_ror.setSpecialValueText("미적용")
    self.opt_min_ror.setSingleStep(10); self.opt_min_ror.setFixedHeight(26)
    self.opt_min_ror.setStyleSheet(_opt_spin_style())
    cond_grid.addWidget(self.opt_min_ror, 0, 3)

    cond_grid.addWidget(_opt_label("계약 수량"), 0, 4)
    self.opt_qty = QSpinBox()
    self.opt_qty.setRange(1, 100); self.opt_qty.setValue(1)
    self.opt_qty.setSuffix(" 계약"); self.opt_qty.setFixedHeight(26)
    self.opt_qty.setStyleSheet(_opt_spin_style())
    cond_grid.addWidget(self.opt_qty, 0, 5)

    # Row 1 — 상위 N개 / ATM 거리 / IV
    cond_grid.addWidget(_opt_label("상위 결과"), 1, 0)
    self.opt_top_n = QSpinBox()
    self.opt_top_n.setRange(5, 200); self.opt_top_n.setValue(20)
    self.opt_top_n.setSuffix(" 개"); self.opt_top_n.setFixedHeight(26)
    self.opt_top_n.setStyleSheet(_opt_spin_style())
    cond_grid.addWidget(self.opt_top_n, 1, 1)

    cond_grid.addWidget(_opt_label("ATM 거리 (%)"), 1, 2)
    self.opt_atm_dist = QDoubleSpinBox()
    self.opt_atm_dist.setRange(0, 50); self.opt_atm_dist.setValue(0)
    self.opt_atm_dist.setSuffix(" %"); self.opt_atm_dist.setSpecialValueText("미적용")
    self.opt_atm_dist.setSingleStep(0.5); self.opt_atm_dist.setDecimals(1)
    self.opt_atm_dist.setFixedHeight(26)
    self.opt_atm_dist.setStyleSheet(_opt_spin_style())
    self.opt_atm_dist.setToolTip(
        "행사가(들)의 ATM 거리 상한.\n"
        "예: 2.0% → 현재가 ±2% 이내 행사가만 탐색.\n"
        "0 = 미적용 (전체 탐색)")
    cond_grid.addWidget(self.opt_atm_dist, 1, 3)

    cond_grid.addWidget(_opt_label("IV (%)"), 1, 4)
    self.opt_iv = QDoubleSpinBox()
    self.opt_iv.setRange(1, 300); self.opt_iv.setValue(20)
    self.opt_iv.setSuffix(" %"); self.opt_iv.setSingleStep(1)
    self.opt_iv.setDecimals(1); self.opt_iv.setFixedHeight(26)
    self.opt_iv.setStyleSheet(_opt_spin_style())
    self.opt_iv.setToolTip("POP 계산에 사용할 내재 변동성(IV).\nIBKR 옵션 체인에서 확인 후 입력.")
    cond_grid.addWidget(self.opt_iv, 1, 5)

    # Row 2 — 잔존일 / 최소 POP / 정렬 안내
    cond_grid.addWidget(_opt_label("잔존일 (DTE)"), 2, 0)
    self.opt_dte = QSpinBox()
    self.opt_dte.setRange(0, 365); self.opt_dte.setValue(1)
    self.opt_dte.setSuffix(" 일"); self.opt_dte.setFixedHeight(26)
    self.opt_dte.setStyleSheet(_opt_spin_style())
    self.opt_dte.setToolTip("만기까지 잔존일. 0DTE = 0.")
    cond_grid.addWidget(self.opt_dte, 2, 1)

    cond_grid.addWidget(_opt_label("최소 POP (%)"), 2, 2)
    self.opt_min_pop = QDoubleSpinBox()
    self.opt_min_pop.setRange(0, 99); self.opt_min_pop.setValue(0)
    self.opt_min_pop.setSuffix(" %"); self.opt_min_pop.setSpecialValueText("미적용")
    self.opt_min_pop.setSingleStep(5); self.opt_min_pop.setDecimals(0)
    self.opt_min_pop.setFixedHeight(26)
    self.opt_min_pop.setStyleSheet(_opt_spin_style())
    self.opt_min_pop.setToolTip("이 확률 미만 조합 제외.\n예: 70 → POP 70% 이상만 표시.")
    cond_grid.addWidget(self.opt_min_pop, 2, 3)

    sort_lbl = QLabel("정렬: 최대 이익 ↓  (동률 시 수익률 ↓)")
    sort_lbl.setStyleSheet("color:#aaa;font-size:10px;border:none;")
    cond_grid.addWidget(sort_lbl, 2, 4, 1, 2)

    v.addLayout(cond_grid)

    # ── 실행 / 적용 버튼 행 ─────────────────────────────────
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

    # ── 결과 테이블 (10컬럼) ────────────────────────────────
    self.tbl_opt_result = QTableWidget(0, 10)
    self.tbl_opt_result.setHorizontalHeaderLabels([
        "전략", "매수 행사가", "매도 행사가",
        "순 프리미엄($)", "최대 이익($)", "최대 손실($)",
        "수익률(%)", "R:R", "ATM 거리(%)", "POP(%)",
    ])
    hh = self.tbl_opt_result.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.Stretch)
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


def _opt_label(text: str) -> QLabel:
    """조건 입력 레이블 공용 스타일."""
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#aaa;font-size:11px;border:none;")
    return lbl


def _opt_spin_style() -> str:
    """스핀박스 공용 스타일 문자열."""
    return (
        "QDoubleSpinBox, QSpinBox{"
        "background:#0a0a1e;color:#ffd700;"
        "border:1px solid #3a3a6a;border-radius:3px;"
        "font-size:12px;padding:2px 4px;}"
    )
