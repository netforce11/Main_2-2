"""
order_panel.py — 빠른 주문 패널 UI  v6.9
변경:
  - 잔고 버튼 → 플로팅 잔고창 토글 (항상 위, X버튼 없음)
  - 버튼 클릭 시 QPropertyAnimation 피드백
  - 정정/취소 탭 우측 KST 시각 표시 (1초 갱신)
  - +1호가 매수 버튼
  - 긴급 매도 버튼 (잔고 전체 + 미체결 취소)
  - 체결 시 잔고창 자동 팝업
"""
import re
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QRadioButton, QButtonGroup,
    QSpinBox, QTabWidget, QTableWidget,
    QHeaderView, QAbstractItemView, QFrame,
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QRect, pyqtProperty
from PyQt5.QtGui import QColor


# ── KST 헬퍼 ────────────────────────────────────────────────
def _kst_now() -> str:
    return (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M:%S")


# ── 버튼 클릭 애니메이션 (1~2px 아래로 눌림) ─────────────────
def _animate_press(btn):
    """버튼을 순간적으로 2px 아래로 밀었다가 복귀."""
    geo = btn.geometry()
    anim = QPropertyAnimation(btn, b"geometry")
    anim.setDuration(80)
    pressed = QRect(geo.x(), geo.y()+2, geo.width(), geo.height())
    anim.setKeyValueAt(0,   geo)
    anim.setKeyValueAt(0.5, pressed)
    anim.setKeyValueAt(1,   geo)
    anim.start()
    btn._anim = anim   # GC 방지


# ── SPX trading class 판별 헬퍼 ─────────────────────────────
def _spx_tag(sym: str, expiry: str) -> str:
    """sym/expiry 기반으로 tradingClass(tag) 결정.
    core_contract.make_opt_contract 가 NANOS/SPX/SPXW 분기를 내부 처리하므로
    여기서는 tag 힌트만 반환하면 됨.
    """
    s = (sym or "").upper()
    if s == "NANOS":
        return "SPXW"   # make_opt_contract 내부에서 NANOS 전용 분기로 처리됨
    if s in ("SPX", "SPXW"):
        try:
            from core_contract import _resolve_spx_trading_class
            return _resolve_spx_trading_class(s, expiry)
        except Exception:
            pass
    return "SPXW"


class OrderPanelMixin:
    """빠른 주문 패널 UI. CallPutGrid에 mixin된다."""

    def _build_quick_order_panel(self) -> QWidget:
        gb = QGroupBox("⚡ 빠른 주문")
        gb_v = QVBoxLayout(gb)
        gb_v.setSpacing(3); gb_v.setContentsMargins(4,6,4,4)

        _tab_s = (
            "QTabWidget::pane{border:1px solid #2a2a4a;background:#07070f;}"
            "QTabBar::tab{background:#0a0a1e;color:#aaa;padding:4px 8px;"
            "border:1px solid #2a2a4a;border-bottom:none;font-size:13px;}"
            "QTabBar::tab:selected{background:#12122a;color:#ffd700;"
            "border-bottom:1px solid #12122a;}"
            "QTabBar::tab:hover{background:#1a1a3a;color:#fff;}")
        tab_w = QTabWidget(); tab_w.setStyleSheet(_tab_s)
        self._qord_tab_widget = tab_w

        # ── 탭1: 신규 ────────────────────────────────────────
        new_w  = QWidget()
        root_v = QVBoxLayout(new_w)
        root_v.setSpacing(5); root_v.setContentsMargins(6,6,6,6)

        tgt_row = QHBoxLayout()
        tgt_row.addWidget(QLabel("대상:"))
        self.qord_side = QLineEdit(); self.qord_side.setReadOnly(True)
        self.qord_side.setFixedWidth(28)
        self.qord_side.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #333;")
        self.qord_strike = QLineEdit(); self.qord_strike.setReadOnly(True)
        self.qord_strike.setFixedWidth(62)
        self.qord_strike.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #333;")
        tgt_row.addWidget(self.qord_side); tgt_row.addWidget(self.qord_strike)

        # ── 주문 확인창 체크박스 (행사가 우측) ───────────────────
        from PyQt5.QtWidgets import QCheckBox
        self.chk_order_confirm = QCheckBox("주문확인")
        self.chk_order_confirm.setChecked(True)   # 기본값 ON
        self.chk_order_confirm.setStyleSheet(
            "QCheckBox{color:#aaa;font-size:12px;spacing:4px;}"
            "QCheckBox::indicator{width:14px;height:14px;"
            "border:1px solid #555;border-radius:3px;background:#0a0a1e;}"
            "QCheckBox::indicator:checked{background:#1a5c2e;"
            "border:1px solid #00ff88;}"
            "QCheckBox::indicator:checked:hover{background:#2a7c3e;}")
        self.chk_order_confirm.setToolTip(
            "체크: 주문 전 확인창 표시\n미체크: 바로 주문 전송")
        self.chk_order_confirm.toggled.connect(
            lambda on: setattr(self, '_skip_order_confirm', not on))
        tgt_row.addWidget(self.chk_order_confirm)

        # ── [S11] 계좌번호 / 모드 표시 라벨 ─────────────────────
        self.lbl_acct_mode = QLabel("계좌: ―")
        self.lbl_acct_mode.setStyleSheet(
            "color:#666;font-size:11px;font-weight:bold;border:none;"
            "background:#0a0a1e;border-radius:3px;padding:1px 5px;")
        self.lbl_acct_mode.setToolTip("연결된 계좌번호 / 모드 (DU=모의투자)")
        tgt_row.addStretch()
        tgt_row.addWidget(self.lbl_acct_mode)
        root_v.addLayout(tgt_row)

        self.lbl_qord_src = QLabel("")
        self.lbl_qord_src.setStyleSheet("color:#ff8800;font-size:12px;border:none;")
        self.lbl_qord_src.setWordWrap(True)
        root_v.addWidget(self.lbl_qord_src)

        line = QLabel(); line.setFixedHeight(1)
        line.setStyleSheet("background:#333;border:none;")
        root_v.addWidget(line)

        gl = QGridLayout(); gl.setSpacing(4)
        _ls = "color:#aaa;font-size:13px;border:none;"

        type_w = QWidget(); type_h = QHBoxLayout(type_w)
        type_h.setContentsMargins(0,0,0,0); type_h.setSpacing(6)
        self.qord_lmt = QRadioButton("지정가")
        self.qord_mkt = QRadioButton("시장가")
        self.qord_lmt.setChecked(True)
        self.qord_lmt.setStyleSheet("color:#ffd700;font-size:13px;")
        self.qord_mkt.setStyleSheet("color:#ffd700;font-size:13px;")
        qord_grp = QButtonGroup(self)
        qord_grp.addButton(self.qord_lmt); qord_grp.addButton(self.qord_mkt)
        self.qord_lmt.toggled.connect(self._on_qord_type_toggle)
        type_h.addWidget(self.qord_lmt); type_h.addWidget(self.qord_mkt)

        # ── 어댑티브: 녹색 인디케이터 ● + 체크박스 + Normal/Urgent 콤보 ──
        from PyQt5.QtWidgets import QCheckBox
        self.lbl_adapt_dot = QLabel("●")
        self.lbl_adapt_dot.setFixedWidth(12)
        self.lbl_adapt_dot.setStyleSheet("color:#1a1a3a;font-size:10px;border:none;")
        self.chk_adaptive = QCheckBox("어댑티브")
        self.chk_adaptive.setStyleSheet(
            "QCheckBox{color:#a0c4ff;font-size:12px;font-weight:bold;spacing:3px;}"
            "QCheckBox::indicator{width:13px;height:13px;"
            "border:1px solid #4a6a9a;border-radius:2px;background:#0a0a1e;}"
            "QCheckBox::indicator:checked{background:#3060cc;border:1px solid #60a0ff;}")
        self.chk_adaptive.setToolTip(
            "IBKR Adaptive Algorithm 사용\n"
            "Normal: 체결률 우선  |  Urgent: 속도 우선")
        self.combo_adapt_priority = QComboBox()
        self.combo_adapt_priority.addItems(["Normal", "Urgent"])
        self.combo_adapt_priority.setFixedHeight(22)
        self.combo_adapt_priority.setFixedWidth(64)
        self.combo_adapt_priority.setEnabled(False)
        self.combo_adapt_priority.setStyleSheet(
            "QComboBox{background:#0d0d22;color:#a0c4ff;border:1px solid #2a4a6a;"
            "font-size:11px;padding:1px 3px;}"
            "QComboBox QAbstractItemView{background:#0d0d22;color:#a0c4ff;font-size:11px;}"
            "QComboBox::drop-down{border:none;width:10px;}"
            "QComboBox:disabled{color:#4a6a8a;border:1px solid #1a2a4a;background:#08081a;}")
        def _on_adpt_toggle(checked):
            self.combo_adapt_priority.setEnabled(checked)
            self.lbl_adapt_dot.setStyleSheet(
                "color:#00ff88;font-size:10px;border:none;" if checked else
                "color:#1a1a3a;font-size:10px;border:none;")
        self.chk_adaptive.toggled.connect(_on_adpt_toggle)
        type_h.addSpacing(6)
        type_h.addWidget(self.lbl_adapt_dot)
        type_h.addWidget(self.chk_adaptive)
        type_h.addWidget(self.combo_adapt_priority)

        type_h.addStretch()
        _abtn_s = ("QPushButton{background:#1a2a3a;color:#90caf9;font-size:12px;"
                   "font-weight:bold;padding:1px 5px;border-radius:3px;"
                   "border:1px solid #2a4a6a;}"
                   "QPushButton:hover{background:#2a3a5a;}"
                   "QPushButton:pressed{background:#0a1a2a;}")
        self.btn_qty_max = QPushButton("MAX"); self.btn_qty_max.setFixedHeight(22); self.btn_qty_max.setFixedWidth(38)
        self.btn_qty_200 = QPushButton("$200"); self.btn_qty_200.setFixedHeight(22); self.btn_qty_200.setFixedWidth(38)
        self.btn_qty_max.setStyleSheet(_abtn_s); self.btn_qty_200.setStyleSheet(_abtn_s)
        self.btn_qty_max.clicked.connect(self._calc_qty_max)
        self.btn_qty_200.clicked.connect(self._calc_qty_200)
        type_h.addWidget(self.btn_qty_max); type_h.addWidget(self.btn_qty_200)

        self.qord_price = QLineEdit(); self.qord_price.setPlaceholderText("가격 입력")
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;")

        qty_w = QWidget(); qty_h = QHBoxLayout(qty_w)
        qty_h.setContentsMargins(0,0,0,0); qty_h.setSpacing(3)
        self.qord_qty = QSpinBox(); self.qord_qty.setRange(1,9999); self.qord_qty.setValue(1)
        self.qord_qty.setFixedHeight(26)
        self.qord_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:14px;")
        _QS = ("QPushButton{background:#2d2d5e;color:#ffd700;"
               "border:1px solid #4a4a8a;border-radius:3px;font-size:13px;font-weight:bold;}"
               "QPushButton:hover{background:#3d4d6e;}"
               "QPushButton:pressed{background:#1d1d4e;}")
        for lbl2,v2 in [("1",1),("5",5),("10",10)]:
            bq=QPushButton(lbl2); bq.setFixedWidth(28); bq.setFixedHeight(26)
            bq.setStyleSheet(_QS)
            bq.clicked.connect(lambda _,v=v2: self.qord_qty.setValue(v))
            qty_h.addWidget(bq)
        qty_h.insertWidget(0, self.qord_qty)

        gl.addWidget(QLabel("유형:",styleSheet=_ls),0,0); gl.addWidget(type_w,0,1)
        gl.addWidget(QLabel("가격:",styleSheet=_ls),1,0); gl.addWidget(self.qord_price,1,1)
        gl.addWidget(QLabel("수량:",styleSheet=_ls),2,0); gl.addWidget(qty_w,2,1)
        root_v.addLayout(gl)

        self.lbl_commission = QLabel("")
        self.lbl_commission.setStyleSheet(
            "color:#FFA500;font-size:13px;border:none;"
            "background:#0d0d20;padding:2px 4px;border-radius:3px;")
        self.lbl_commission.setAlignment(Qt.AlignRight)
        root_v.addWidget(self.lbl_commission)
        self.qord_qty.valueChanged.connect(self._update_commission_label)
        self._update_commission_label(self.qord_qty.value())

        tif_row = QHBoxLayout()
        tif_row.addWidget(QLabel("TIF:",styleSheet=_ls))
        self.qord_tif = QComboBox(); self.qord_tif.addItems(["DAY","GTC","IOC","GTD"])
        self.qord_tif.setFixedHeight(24)
        self.qord_tif.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:13px;padding:1px;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
            "QComboBox::drop-down{border:none;}")
        tif_row.addWidget(self.qord_tif); tif_row.addStretch()
        root_v.addLayout(tif_row)

        # ── 매수 / 매도 버튼 ─────────────────────────────────
        _buy_s  = ("QPushButton{background:#1a5c2e;color:#00ff88;font-size:16px;"
                   "font-weight:bold;padding:10px 4px;border-radius:4px;}"
                   "QPushButton:pressed{background:#0a3c1e;padding-top:12px;padding-bottom:8px;}")
        _sell_s = ("QPushButton{background:#6b1a1a;color:#ff6666;font-size:16px;"
                   "font-weight:bold;padding:10px 4px;border-radius:4px;}"
                   "QPushButton:pressed{background:#4b0a0a;padding-top:12px;padding-bottom:8px;}")
        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        self.btn_qord_buy  = QPushButton("▲ 매수");  self.btn_qord_buy.setStyleSheet(_buy_s)
        self.btn_qord_sell = QPushButton("▼ 매도");  self.btn_qord_sell.setStyleSheet(_sell_s)
        self.btn_qord_buy.clicked.connect(lambda _: (
            _animate_press(self.btn_qord_buy), self._qord_place("BUY")))
        self.btn_qord_sell.clicked.connect(lambda _: (
            _animate_press(self.btn_qord_sell), self._qord_place("SELL")))
        btn_row.addWidget(self.btn_qord_buy, 1); btn_row.addWidget(self.btn_qord_sell, 1)
        root_v.addLayout(btn_row)

        # ── +1호가 매수 버튼 ─────────────────────────────────
        _p1_s = ("QPushButton{background:#1a3a5c;color:#90caf9;font-size:13px;"
                 "font-weight:bold;padding:5px;border-radius:4px;"
                 "border:1px solid #2a5a8c;}"
                 "QPushButton:hover{background:#2a4a7c;}"
                 "QPushButton:pressed{background:#0a2a4c;padding-top:7px;padding-bottom:3px;}")
        self.btn_plus1tick = QPushButton("+1호가 매수")
        self.btn_plus1tick.setStyleSheet(_p1_s)
        self.btn_plus1tick.setToolTip("미체결 주문 중 최고가 매수 주문을 +$0.05 올려 정정")
        self.btn_plus1tick.clicked.connect(lambda: (
            _animate_press(self.btn_plus1tick), self._plus1tick_buy()))
        root_v.addWidget(self.btn_plus1tick)

        # ── 긴급 매도 버튼들 ──────────────────────────────────
        sep2 = QLabel(); sep2.setFixedHeight(1)
        sep2.setStyleSheet("background:#4a1a1a;border:none;")
        root_v.addWidget(sep2)

        _emrg_all_s = ("QPushButton{background:#8b0000;color:#ff4444;font-size:13px;"
                       "font-weight:bold;padding:6px;border-radius:4px;"
                       "border:2px solid #ff4444;}"
                       "QPushButton:hover{background:#aa0000;}"
                       "QPushButton:pressed{background:#660000;padding-top:8px;padding-bottom:4px;}")
        _emrg_pos_s = ("QPushButton{background:#5a0a0a;color:#ff8888;font-size:12px;"
                       "font-weight:bold;padding:4px;border-radius:3px;"
                       "border:1px solid #aa4444;}"
                       "QPushButton:hover{background:#7a1a1a;}"
                       "QPushButton:pressed{background:#3a0000;padding-top:6px;padding-bottom:2px;}")

        self.btn_emrg_all = QPushButton("🚨 긴급매도 ALL (잔고+미체결)")
        self.btn_emrg_all.setStyleSheet(_emrg_all_s)
        self.btn_emrg_all.setToolTip("보유 포지션 전체 시장가 매도 + 미체결 매수 취소")
        self.btn_emrg_all.clicked.connect(lambda: (
            _animate_press(self.btn_emrg_all), self._emergency_sell_all()))
        root_v.addWidget(self.btn_emrg_all)

        emrg_row = QHBoxLayout(); emrg_row.setSpacing(4)
        self.btn_emrg_pos  = QPushButton("잔고만 매도")
        self.btn_emrg_open = QPushButton("미체결만 취소")
        self.btn_emrg_pos.setStyleSheet(_emrg_pos_s)
        self.btn_emrg_open.setStyleSheet(_emrg_pos_s)
        self.btn_emrg_pos.clicked.connect(lambda: (
            _animate_press(self.btn_emrg_pos), self._emergency_sell_positions()))
        self.btn_emrg_open.clicked.connect(lambda: (
            _animate_press(self.btn_emrg_open), self._emergency_cancel_orders()))
        emrg_row.addWidget(self.btn_emrg_pos, 1); emrg_row.addWidget(self.btn_emrg_open, 1)
        root_v.addLayout(emrg_row)

        self.lbl_qord_status = QLabel("대기 중")
        self.lbl_qord_status.setAlignment(Qt.AlignCenter)
        self.lbl_qord_status.setStyleSheet(
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        root_v.addWidget(self.lbl_qord_status)
        root_v.addStretch()
        tab_w.addTab(new_w, "⚡ 신규")

        # ── 단축키 / Enter 포커스 체인 설정 ─────────────────────
        self._setup_quick_order_shortcuts()

        # ── 정정/취소 공통 ────────────────────────────────────
        _tbl_s = (
            "QTableWidget{background:#05050f;color:#ccc;"
            "gridline-color:#1a1a3a;font-size:13px;}"
            "QHeaderView::section{background:#0a0a1e;color:#90caf9;"
            "border:1px solid #1a1a3a;font-size:12px;}"
            "QTableWidget::item:selected{background:#1a3a6b;color:#ffd700;}")
        _es  = "background:#0a0a1e;color:#ffd700;border:1px solid #444;font-size:15px;"
        _ls2 = "color:#aaa;font-size:13px;border:none;"
        _fetch_s = ("background:#1a3a1a;color:#00ff88;font-size:13px;font-weight:bold;"
                    "padding:5px;border-radius:3px;border:1px solid #2a6a2a;")

        def _make_order_tbl(sel_color="#1a3a6b"):
            tbl=QTableWidget(0,4)
            tbl.setHorizontalHeaderLabels(["OID","종목","방향","가격"])
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            tbl.setMaximumHeight(110)
            tbl.setStyleSheet(_tbl_s.replace("#1a3a6b",sel_color))
            return tbl

        # ── 탭2: 정정 ────────────────────────────────────────
        amend_w = QWidget()
        av = QVBoxLayout(amend_w); av.setSpacing(5); av.setContentsMargins(8,8,8,8)

        # 헤더: 미체결조회 버튼 + KST 시각
        ah = QHBoxLayout()
        btn_fetch_a = QPushButton("📋 미체결 주문 조회")
        btn_fetch_a.setStyleSheet(_fetch_s)
        btn_fetch_a.clicked.connect(lambda: (
            _animate_press(btn_fetch_a), self._fetch_open_orders()))
        ah.addWidget(btn_fetch_a, 1)
        self.lbl_amend_time = QLabel(_kst_now())
        self.lbl_amend_time.setStyleSheet("color:#5dade2;font-size:13px;font-weight:bold;border:none;")
        ah.addWidget(self.lbl_amend_time)
        av.addLayout(ah)

        self.tbl_open_orders_a = _make_order_tbl("#1a3a6b")
        self.tbl_open_orders_a.cellClicked.connect(lambda r,c: self._fill_amend_from_table(r))
        av.addWidget(self.tbl_open_orders_a)
        av.addWidget(QLabel("주문 ID:",styleSheet=_ls2))
        self.amend_oid = QLineEdit(); self.amend_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.amend_oid.setStyleSheet(_es); self.amend_oid.setFixedHeight(26); av.addWidget(self.amend_oid)
        av.addWidget(QLabel("새 가격:",styleSheet=_ls2))
        self.amend_price = QLineEdit(); self.amend_price.setPlaceholderText("새 지정가")
        self.amend_price.setStyleSheet(_es); self.amend_price.setFixedHeight(26); av.addWidget(self.amend_price)
        av.addWidget(QLabel("새 수량:",styleSheet=_ls2))
        self.amend_qty = QSpinBox(); self.amend_qty.setRange(1,9999); self.amend_qty.setValue(1)
        self.amend_qty.setFixedHeight(26)
        self.amend_qty.setStyleSheet("background:#0a0a1e;color:#fff;border:1px solid #444;font-size:15px;")
        av.addWidget(self.amend_qty)
        btn_amend = QPushButton("✏ 정정 전송")
        btn_amend.setStyleSheet(
            "QPushButton{background:#1a4a6b;color:#90caf9;font-size:15px;"
            "font-weight:bold;padding:8px;border-radius:4px;}"
            "QPushButton:pressed{background:#0a2a4b;padding-top:10px;padding-bottom:6px;}")
        btn_amend.clicked.connect(lambda: (_animate_press(btn_amend), self._amend_order()))
        av.addWidget(btn_amend)
        self.lbl_amend_status = QLabel("대기 중"); self.lbl_amend_status.setAlignment(Qt.AlignCenter)
        self.lbl_amend_status.setStyleSheet(
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        av.addWidget(self.lbl_amend_status); av.addStretch()
        tab_w.addTab(amend_w, "✏ 정정")

        # ── 탭3: 취소 ────────────────────────────────────────
        cancel_w = QWidget()
        cv = QVBoxLayout(cancel_w); cv.setSpacing(5); cv.setContentsMargins(8,8,8,8)

        ch = QHBoxLayout()
        btn_fetch_c = QPushButton("📋 미체결 주문 조회")
        btn_fetch_c.setStyleSheet(_fetch_s)
        btn_fetch_c.clicked.connect(lambda: (
            _animate_press(btn_fetch_c), self._fetch_open_orders()))
        ch.addWidget(btn_fetch_c, 1)
        self.lbl_cancel_time = QLabel(_kst_now())
        self.lbl_cancel_time.setStyleSheet("color:#5dade2;font-size:13px;font-weight:bold;border:none;")
        ch.addWidget(self.lbl_cancel_time)
        cv.addLayout(ch)

        self.tbl_open_orders_c = _make_order_tbl("#3a1a1a")
        self.tbl_open_orders_c.setStyleSheet(
            _tbl_s+"QTableWidget::item:selected{background:#3a1a1a;color:#ff6666;}")
        self.tbl_open_orders_c.cellClicked.connect(lambda r,c: self._fill_cancel_from_table(r))
        cv.addWidget(self.tbl_open_orders_c)
        cv.addWidget(QLabel("주문 ID:",styleSheet=_ls2))
        self.cancel_oid = QLineEdit(); self.cancel_oid.setPlaceholderText("위 목록 클릭 or 직접 입력")
        self.cancel_oid.setStyleSheet(_es); self.cancel_oid.setFixedHeight(26); cv.addWidget(self.cancel_oid)
        btn_cancel = QPushButton("✕ 취소 전송")
        btn_cancel.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff6666;font-size:15px;"
            "font-weight:bold;padding:10px;border-radius:4px;}"
            "QPushButton:pressed{background:#4b0a0a;padding-top:12px;padding-bottom:8px;}")
        btn_cancel.clicked.connect(lambda: (_animate_press(btn_cancel), self._cancel_order()))
        cv.addWidget(btn_cancel)
        self.lbl_cancel_status = QLabel("대기 중"); self.lbl_cancel_status.setAlignment(Qt.AlignCenter)
        self.lbl_cancel_status.setStyleSheet(
            "color:#888;font-size:13px;border:1px solid #333;border-radius:3px;padding:2px;")
        cv.addWidget(self.lbl_cancel_status)

        sep_gc = QLabel(); sep_gc.setFixedHeight(1)
        sep_gc.setStyleSheet("background:#5a2a2a;border:none;margin-top:4px;")
        cv.addWidget(sep_gc)

        btn_global_cancel = QPushButton("🚨 전체 주문 강제 취소 (reqGlobalCancel)")
        btn_global_cancel.setFixedHeight(38)
        btn_global_cancel.setStyleSheet(
            "QPushButton{background:#8B0000;color:#ffffff;font-size:13px;"
            "font-weight:bold;border-radius:4px;border:1px solid #cc2222;}"
            "QPushButton:hover{background:#aa0000;}"
            "QPushButton:pressed{background:#660000;}")
        btn_global_cancel.setToolTip(
            "현재 API 세션의 모든 미체결 주문을 즉시 취소합니다.\n"
            "TWS UI 상태와 무관하게 서버에 직접 전달됩니다.")
        btn_global_cancel.clicked.connect(self._on_global_cancel)
        cv.addWidget(btn_global_cancel)

        cv.addStretch()
        tab_w.addTab(cancel_w, "✕ 취소")

        # ── 탭4: 빠른매도 ─────────────────────────────────────
        sell_w = QWidget()
        sv = QVBoxLayout(sell_w); sv.setSpacing(4); sv.setContentsMargins(8,2,8,8)

        # ── bump 버튼 (상단) ─────────────────────────────────
        _sell_up = ("QPushButton{background:#1a3a1a;color:#00cc66;font-size:12px;"
                    "font-weight:bold;border:1px solid #2a6a2a;border-radius:3px;}"
                    "QPushButton:hover{background:#2a5a2a;}")
        _sell_dn = ("QPushButton{background:#3a1a1a;color:#ff6666;font-size:12px;"
                    "font-weight:bold;border:1px solid #6a2a2a;border-radius:3px;}"
                    "QPushButton:hover{background:#5a2a2a;}")
        bump_row2 = QHBoxLayout(); bump_row2.setSpacing(3)
        for lbl3, delta, st2 in [("+0.05",+0.05,_sell_dn),("+0.10",+0.10,_sell_dn),
                                  ("-0.05",-0.05,_sell_up),("-0.10",-0.10,_sell_up)]:
            b2 = QPushButton(lbl3); b2.setFixedHeight(26); b2.setStyleSheet(st2)
            b2.clicked.connect(lambda _, d=delta: self._bump_sell_price(d))
            bump_row2.addWidget(b2)
        sv.addLayout(bump_row2)

        sep_s1 = QLabel(); sep_s1.setFixedHeight(1)
        sep_s1.setStyleSheet("background:#3a1a1a;border:none;")
        sv.addWidget(sep_s1)

        # ── 가격 / 수량 ───────────────────────────────────────
        sell_gl = QGridLayout(); sell_gl.setSpacing(4)

        self.sell_price = QLineEdit()
        self.sell_price.setPlaceholderText("매도가격")
        self.sell_price.setStyleSheet(
            "color:#ff9999;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #6a2a2a;")

        sell_qty_w2 = QWidget(); sell_qty_h2 = QHBoxLayout(sell_qty_w2)
        sell_qty_h2.setContentsMargins(0,0,0,0); sell_qty_h2.setSpacing(3)
        self.sell_qty = QSpinBox()
        self.sell_qty.setRange(1, 9999); self.sell_qty.setValue(1)
        self.sell_qty.setFixedHeight(26)
        self.sell_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #6a2a2a;font-size:14px;")
        sell_qty_h2.addWidget(self.sell_qty)

        sell_gl.addWidget(QLabel("매도가격:", styleSheet=_ls2), 0, 0)
        sell_gl.addWidget(self.sell_price, 0, 1)
        sell_gl.addWidget(QLabel("수량:", styleSheet=_ls2), 1, 0)
        sell_gl.addWidget(sell_qty_w2, 1, 1)
        sv.addLayout(sell_gl)

        # ── 매도 버튼 2개 (가격/수량 바로 아래 붙여서) ──────────
        btn_sell_mkt = QPushButton("▼ Bid가 즉시 매도 (LMT)")
        btn_sell_mkt.setFixedHeight(40)
        btn_sell_mkt.setMaximumHeight(40)
        btn_sell_mkt.setStyleSheet(
            "QPushButton{background:#8b0000;color:#ff4444;font-size:15px;"
            "font-weight:bold;border-radius:4px;border:2px solid #ff4444;}"
            "QPushButton:hover{background:#aa1a1a;}"
            "QPushButton:pressed{background:#5a0000;}")
        btn_sell_mkt.clicked.connect(self._sell_selected_order)
        sv.addWidget(btn_sell_mkt)

        btn_sell_lmt = QPushButton("▼ 지정가 매도 전송")
        btn_sell_lmt.setFixedHeight(36)
        btn_sell_lmt.setMaximumHeight(36)
        btn_sell_lmt.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff9999;font-size:14px;"
            "font-weight:bold;border-radius:4px;border:1px solid #9a2a2a;}"
            "QPushButton:hover{background:#8b2a2a;}"
            "QPushButton:pressed{background:#4b0a0a;}")
        btn_sell_lmt.clicked.connect(self._sell_limit_order)
        sv.addWidget(btn_sell_lmt)

        self.lbl_sell_status = QLabel("잔고창(📊 잔고) 행 클릭 → 자동입력 후 매도")
        self.lbl_sell_status.setAlignment(Qt.AlignCenter)
        self.lbl_sell_status.setStyleSheet(
            "color:#888;font-size:12px;border:1px solid #333;border-radius:3px;padding:2px;")
        sv.addWidget(self.lbl_sell_status)


        sv.addStretch()
        tab_w.addTab(sell_w, "▼ 빠른매도")

        # ── 탭5: 스나이퍼 주문 ───────────────────────────────
        sniper_w = QWidget()
        sn_v = QVBoxLayout(sniper_w)
        sn_v.setSpacing(4); sn_v.setContentsMargins(6, 6, 6, 6)

        _sn_ls = "color:#aaa;font-size:13px;border:none;"
        _sn_es = ("color:#ffd700;font-weight:bold;font-size:14px;"
                  "background:#0a0a1e;border:1px solid #444;")

        # ── 행사가 / C-P / 만기 (콜풋탭 클릭 시 자동 입력) ──
        sn_v.addWidget(QLabel("▶ 조건 설정  (콜-풋 체인 클릭 시 자동 입력)",
            styleSheet="color:#5dade2;font-size:12px;font-weight:bold;border:none;"))

        sn_g1 = QGridLayout(); sn_g1.setSpacing(4)
        sn_g1.addWidget(QLabel("행사가:", styleSheet=_sn_ls), 0, 0)
        self.snp_strike = QLineEdit()
        self.snp_strike.setPlaceholderText("콜풋탭 클릭 시 자동 입력")
        self.snp_strike.setStyleSheet(_sn_es)
        sn_g1.addWidget(self.snp_strike, 0, 1, 1, 3)

        sn_g1.addWidget(QLabel("C/P:", styleSheet=_sn_ls), 1, 0)
        self.snp_right = QComboBox()
        self.snp_right.addItems(["C", "P"])
        self.snp_right.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:14px;font-weight:bold;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:14px;}"
            "QComboBox::drop-down{border:none;}")
        sn_g1.addWidget(self.snp_right, 1, 1)

        sn_g1.addWidget(QLabel("만기:", styleSheet=_sn_ls), 1, 2)
        self.snp_expiry = QLineEdit()
        self.snp_expiry.setPlaceholderText("YYYYMMDD")
        self.snp_expiry.setStyleSheet(_sn_es)
        sn_g1.addWidget(self.snp_expiry, 1, 3)
        sn_v.addLayout(sn_g1)

        # ── 목표가 + 비교 조건 ────────────────────────────────
        sep_sn1 = QLabel(); sep_sn1.setFixedHeight(1)
        sep_sn1.setStyleSheet("background:#2a3a2a;border:none;")
        sn_v.addWidget(sep_sn1)

        sn_g2 = QGridLayout(); sn_g2.setSpacing(4)
        sn_g2.addWidget(QLabel("목표가($):", styleSheet=_sn_ls), 0, 0)
        self.snp_price = QLineEdit()
        self.snp_price.setPlaceholderText("예: 0.20")
        self.snp_price.setStyleSheet(
            "color:#00ff88;font-weight:bold;font-size:14px;"
            "background:#0a0a1e;border:1px solid #2a6a2a;")
        sn_g2.addWidget(self.snp_price, 0, 1)

        self.snp_cmp = QComboBox()
        self.snp_cmp.addItems(["<=  이하일 때", ">=  이상일 때"])
        self.snp_cmp.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#00ff88;border:1px solid #2a6a2a;"
            "font-size:12px;font-weight:bold;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#00ff88;font-size:12px;}"
            "QComboBox::drop-down{border:none;}")
        sn_g2.addWidget(self.snp_cmp, 0, 2, 1, 2)

        # ── 한국시간 조건 ─────────────────────────────────────
        sn_g2.addWidget(QLabel("한국시간(KST):", styleSheet=_sn_ls), 1, 0)
        self.snp_time = QLineEdit()
        self.snp_time.setPlaceholderText("HH:MM  예) 04:46 / 18:30")
        self.snp_time.setMaxLength(5)
        self.snp_time.setStyleSheet(_sn_es)
        # ── ":" 자동 입력 이벤트 필터 ─────────────────────────
        from PyQt5.QtCore import QObject, QEvent
        class _TimeFilter(QObject):
            def eventFilter(self_, obj, ev):
                if ev.type() == QEvent.KeyPress:
                    from PyQt5.QtCore import Qt as _Qt
                    key = ev.key()
                    txt = obj.text()
                    # 숫자 2자리 입력 후 자동 ":" 삽입
                    if (len(txt) == 2 and key not in (
                            _Qt.Key_Backspace, _Qt.Key_Delete,
                            _Qt.Key_Left, _Qt.Key_Right, _Qt.Key_Colon)
                            and ":" not in txt):
                        obj.setText(txt + ":")
                        obj.setCursorPosition(3)
                return False
        _tf = _TimeFilter(self.snp_time)
        self.snp_time.installEventFilter(_tf)
        self.snp_time._time_filter = _tf   # GC 방지
        sn_g2.addWidget(self.snp_time, 1, 1)
        sn_g2.addWidget(QLabel("허용오차(분):", styleSheet=_sn_ls), 1, 2)
        self.snp_margin = QSpinBox()
        self.snp_margin.setRange(0, 60); self.snp_margin.setValue(0)
        self.snp_margin.setFixedHeight(26)
        self.snp_margin.setToolTip(
            "0분 = 해당 분(HH:MM:00 ~ HH:MM:59) 안에만 발동\n"
            "1분 = ±1분 허용 (설정시각 전후 1분)")
        self.snp_margin.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:13px;")
        sn_g2.addWidget(self.snp_margin, 1, 3)
        sn_v.addLayout(sn_g2)

        # ── 주문 방향 / 유형 / 가격 / 수량 ───────────────────
        sep_sn2 = QLabel(); sep_sn2.setFixedHeight(1)
        sep_sn2.setStyleSheet("background:#2a2a4a;border:none;")
        sn_v.addWidget(sep_sn2)

        sn_g3 = QGridLayout(); sn_g3.setSpacing(4)
        sn_g3.addWidget(QLabel("방향:", styleSheet=_sn_ls), 0, 0)
        self.snp_action = QComboBox()
        self.snp_action.addItems(["BUY", "SELL"])
        self.snp_action.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:13px;font-weight:bold;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
            "QComboBox::drop-down{border:none;}")
        sn_g3.addWidget(self.snp_action, 0, 1)

        sn_g3.addWidget(QLabel("유형:", styleSheet=_sn_ls), 0, 2)
        self.snp_otype = QComboBox()
        self.snp_otype.addItems(["LMT", "MKT"])
        self.snp_otype.setStyleSheet(
            "QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
            "font-size:13px;font-weight:bold;}"
            "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:13px;}"
            "QComboBox::drop-down{border:none;}")
        sn_g3.addWidget(self.snp_otype, 0, 3)

        sn_g3.addWidget(QLabel("주문가:", styleSheet=_sn_ls), 1, 0)
        self.snp_oprice = QLineEdit()
        self.snp_oprice.setPlaceholderText("LMT 가격 (MKT=생략)")
        self.snp_oprice.setStyleSheet(_sn_es)
        sn_g3.addWidget(self.snp_oprice, 1, 1)

        sn_g3.addWidget(QLabel("수량:", styleSheet=_sn_ls), 1, 2)
        self.snp_qty = QSpinBox()
        self.snp_qty.setRange(1, 9999); self.snp_qty.setValue(1)
        self.snp_qty.setFixedHeight(26)
        self.snp_qty.setStyleSheet(
            "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:13px;")
        sn_g3.addWidget(self.snp_qty, 1, 3)
        sn_v.addLayout(sn_g3)

        # ── 버튼 행 ───────────────────────────────────────────
        sn_btn_row = QHBoxLayout(); sn_btn_row.setSpacing(4)
        btn_snp_add  = QPushButton("＋ 등록")
        btn_snp_save = QPushButton("💾 저장")
        btn_snp_clr  = QPushButton("🗑 전체해제")
        btn_snp_add.setStyleSheet(
            "QPushButton{background:#1a6b3c;color:#00ff88;font-size:13px;"
            "font-weight:bold;padding:6px;border-radius:3px;}"
            "QPushButton:hover{background:#2a8b5c;}"
            "QPushButton:pressed{background:#0a4b1c;}")
        btn_snp_save.setStyleSheet(
            "QPushButton{background:#1a3a6b;color:#90caf9;font-size:13px;"
            "font-weight:bold;padding:6px;border-radius:3px;}"
            "QPushButton:hover{background:#2a4a8b;}"
            "QPushButton:pressed{background:#0a2a4b;}")
        btn_snp_clr.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff6666;font-size:13px;"
            "font-weight:bold;padding:6px;border-radius:3px;}"
            "QPushButton:hover{background:#8b2a2a;}"
            "QPushButton:pressed{background:#4b0a0a;}")
        btn_snp_add.clicked.connect(self._sniper_add)
        btn_snp_save.clicked.connect(self._sniper_save)
        btn_snp_clr.clicked.connect(self._sniper_clear_all)
        sn_btn_row.addWidget(btn_snp_add, 2)
        sn_btn_row.addWidget(btn_snp_save, 2)
        sn_btn_row.addWidget(btn_snp_clr, 2)
        sn_v.addLayout(sn_btn_row)

        # ── 활성 스나이퍼 목록 ────────────────────────────────
        sn_v.addWidget(QLabel("▼ 활성 스나이퍼  (행 클릭 → 개별 해제)",
            styleSheet="color:#5dade2;font-size:11px;font-weight:bold;border:none;"))

        self.snp_tbl = QTableWidget(0, 5)
        self.snp_tbl.setHorizontalHeaderLabels(
            ["행사가", "조건", "현재가", "시간(KST)", "상태"])
        _snp_hh = self.snp_tbl.horizontalHeader()
        _snp_hh.setSectionResizeMode(QHeaderView.Stretch)
        self.snp_tbl.verticalHeader().setVisible(False)
        self.snp_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.snp_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.snp_tbl.setMaximumHeight(150)
        self.snp_tbl.setStyleSheet(
            "QTableWidget{background:#05050f;color:#ccc;"
            "gridline-color:#1a1a3a;font-size:12px;}"
            "QHeaderView::section{background:#0a0a1e;color:#5dade2;"
            "border:1px solid #1a1a3a;font-size:11px;}"
            "QTableWidget::item:selected{background:#1a3a2a;color:#00ff88;}")
        self.snp_tbl.cellClicked.connect(self._sniper_row_click)
        sn_v.addWidget(self.snp_tbl)

        # 상태 라벨
        self.snp_status = QLabel("대기 중")
        self.snp_status.setAlignment(Qt.AlignCenter)
        self.snp_status.setStyleSheet(
            "color:#aaa;font-size:11px;border:1px solid #333;"
            "border-radius:3px;padding:2px;")
        sn_v.addWidget(self.snp_status)
        sn_v.addStretch()

        tab_w.addTab(sniper_w, "🎯 스나이퍼")

        # ── 스나이퍼 내부 상태 초기화 ────────────────────────
        self._snipers: dict = {}
        self._sniper_next_rid = 8100   # REQ_TRADE_SNP
        self._sniper_timer = QTimer(self)
        self._sniper_timer.setInterval(2000)
        self._sniper_timer.timeout.connect(self._sniper_check)
        # JSON 복원은 연결 후 실행 (500ms 지연)
        QTimer.singleShot(800, self._sniper_load)

        gb_v.addWidget(tab_w)
        gb_v.setSpacing(0)   # tab_w ↔ pos_sell_panel 간격 제거 → 패널 위로 올라옴

        # ── 잔고 매도 패널 (하단 슬라이드) ──────────────────────
        self._pos_sell_panel = QWidget()
        self._pos_sell_panel.setVisible(False)
        self._pos_sell_panel.setStyleSheet(
            "background:#1a0a0a;border:1px solid #6b1a1a;border-radius:4px;"
            "margin-top:-20px;")   # ← 2cm 위로 끌어올림
        ps_v = QVBoxLayout(self._pos_sell_panel)
        ps_v.setContentsMargins(6,5,6,5); ps_v.setSpacing(4)
        ps_hdr = QHBoxLayout()
        self._ps_lbl_title = QLabel("▼ 잔고 청산 매도")
        self._ps_lbl_title.setStyleSheet("color:#ff6666;font-weight:bold;font-size:13px;border:none;")
        ps_hdr.addWidget(self._ps_lbl_title); ps_hdr.addStretch()
        ps_v.addLayout(ps_hdr)
        ps_info = QHBoxLayout()
        self._ps_lbl_sym = QLabel("―")
        self._ps_lbl_sym.setStyleSheet("color:#ffd700;font-size:13px;font-weight:bold;border:none;")
        ps_info.addWidget(QLabel("종목:",styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_info.addWidget(self._ps_lbl_sym); ps_info.addStretch()
        ps_v.addLayout(ps_info)
        ps_qty_row = QHBoxLayout()
        self._ps_qty = QSpinBox(); self._ps_qty.setRange(1,9999); self._ps_qty.setValue(1)
        self._ps_qty.setFixedHeight(24)
        self._ps_qty.setStyleSheet("background:#0a0a1e;color:#fff;border:1px solid #6b1a1a;font-size:13px;")
        ps_qty_row.addWidget(QLabel("수량:",styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_qty_row.addWidget(self._ps_qty); ps_qty_row.addStretch()
        ps_v.addLayout(ps_qty_row)
        ps_price_row = QHBoxLayout()
        self._ps_price = QLineEdit(); self._ps_price.setPlaceholderText("지정가 (비워두면 시장가)")
        self._ps_price.setFixedHeight(24)
        self._ps_price.setStyleSheet("color:#ffd700;font-size:13px;background:#0a0a1e;border:1px solid #6b1a1a;")
        ps_price_row.addWidget(QLabel("가격:",styleSheet="color:#aaa;font-size:12px;border:none;"))
        ps_price_row.addWidget(self._ps_price)
        ps_v.addLayout(ps_price_row)
        ps_btn = QPushButton("▼ 매도 주문 전송")
        ps_btn.setStyleSheet(
            "QPushButton{background:#6b1a1a;color:#ff6666;font-size:14px;"
            "font-weight:bold;padding:8px;border-radius:4px;}"
            "QPushButton:pressed{background:#4b0a0a;padding-top:10px;padding-bottom:6px;}")
        ps_btn.clicked.connect(lambda: (_animate_press(ps_btn), self._pos_sell_execute()))
        ps_v.addWidget(ps_btn)
        gb_v.addWidget(self._pos_sell_panel)

        # ── KST 시각 타이머 (1초) ────────────────────────────
        self._kst_timer = QTimer(self)
        self._kst_timer.setInterval(1000)
        self._kst_timer.timeout.connect(self._update_kst_labels)
        self._kst_timer.start()

        # ── 체결 감지 → 잔고 자동 갱신 연결 ─────────────────
        # mw.ib 연결 완료 후 실행되어야 하므로 500ms 지연
        QTimer.singleShot(500, self._try_connect_exec_refresh)

        return gb

    def _try_connect_exec_refresh(self):
        """연결 상태 확인 후 _connect_exec_auto_refresh 호출.
        미연결 상태면 _on_connected 에서 재시도 예약."""
        if getattr(getattr(self, 'mw', None), 'connected', False):
            self._connect_exec_auto_refresh()
        else:
            # 연결 시점에 자동 호출되도록 예약 (이미 등록되어 있으면 중복 무시)
            if not getattr(self, '_exec_refresh_hook_set', False):
                self._exec_refresh_hook_set = True
                _orig = getattr(self, '_on_connected', None)
                if _orig:
                    def _hooked_on_connected(*a, **kw):
                        _orig(*a, **kw)
                        self._connect_exec_auto_refresh()
                    self._on_connected = _hooked_on_connected

    # ── KST 시각 갱신 ───────────────────────────────────────
    def _update_kst_labels(self):
        t = _kst_now()
        if hasattr(self, 'lbl_amend_time'):  self.lbl_amend_time.setText(t)
        if hasattr(self, 'lbl_cancel_time'): self.lbl_cancel_time.setText(t)

    # ── 수수료 표시 ─────────────────────────────────────────
    def _update_commission_label(self, qty=1):
        fee = max(qty*0.65, 1.00)
        self.lbl_commission.setText(f"예상 수수료: ${fee:.2f}  ({qty}계약 × $0.65)")

    # ── 유형 토글 ────────────────────────────────────────────
    def _on_qord_type_toggle(self):
        is_lmt = self.qord_lmt.isChecked()
        self.qord_price.setEnabled(is_lmt)
        self.qord_price.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:15px;"
            "background:#0a0a1e;border:1px solid #444;" if is_lmt else
            "color:#555;font-weight:bold;font-size:15px;"
            "background:#070710;border:1px solid #222;")

    # ── 미체결 조회 ──────────────────────────────────────────
    def _fetch_open_orders(self):
        from PyQt5.QtWidgets import QMessageBox
        if not self.mw.connected:
            QMessageBox.warning(self,"미연결","TWS에 먼저 연결하세요."); return
        self._open_orders_buf = []
        self._fetch_oo_done = False   # 중복 복원 방지 플래그
        ib = self.mw.ib

        def _on_open_order(orderId, contract, order, orderState):
            self._open_orders_buf.append({
                "oid": orderId,
                "symbol": getattr(contract,"localSymbol","") or getattr(contract,"symbol",""),
                "action": getattr(order,"action",""),
                "price":  getattr(order,"lmtPrice",0.0),
                "qty":    getattr(order,"totalQuantity",0),
                "type":   getattr(order,"orderType",""),
                "tif":    getattr(order,"tif","DAY"),
                "contract": contract,
            })

        def _restore_handlers():
            if not self._fetch_oo_done:
                self._fetch_oo_done = True
                ib.openOrder    = ib._orig_openOrder
                ib.openOrderEnd = ib._orig_openOrderEnd

        def _on_open_order_end():
            # openOrderEnd 수신 즉시 콜백 복원 → 데이터 유실 없음
            _restore_handlers()
            QTimer.singleShot(0, self._populate_open_order_tables)

        ib._orig_openOrder    = getattr(ib,'openOrder',    lambda *a: None)
        ib._orig_openOrderEnd = getattr(ib,'openOrderEnd', lambda: None)
        ib.openOrder    = _on_open_order
        ib.openOrderEnd = _on_open_order_end
        try: ib.reqOpenOrders(); self._log("📋 미체결 주문 조회 요청...")
        except Exception as e: self._log(f"❌ 주문 조회 오류: {e}")
        # 안전망: 5초 후에도 openOrderEnd 미수신 시 강제 복원 후 테이블 갱신
        QTimer.singleShot(5000, lambda: (
            _restore_handlers(),
            self._populate_open_order_tables()
            ) if not self._fetch_oo_done else None)

    def _populate_open_order_tables(self):
        from PyQt5.QtWidgets import QTableWidgetItem as _QTI
        from PyQt5.QtGui import QColor as _QC
        def _mk(text, color="#ccc"):
            item = _QTI(str(text)); item.setForeground(_QC(color)); return item
        orders = getattr(self,'_open_orders_buf',[])
        for tbl in (self.tbl_open_orders_a, self.tbl_open_orders_c):
            tbl.setRowCount(0)
            for o in orders:
                r=tbl.rowCount(); tbl.insertRow(r)
                price_str=f"{o['price']:.2f}" if o['price'] else o['type']
                col="#00ff88" if o['action']=="BUY" else "#ff6666"
                tbl.setItem(r,0,_mk(str(o['oid']),"#ffd700"))
                tbl.setItem(r,1,_mk(o['symbol'],"#ccc"))
                tbl.setItem(r,2,_mk(f"{o['action']} {o['qty']}",col))
                tbl.setItem(r,3,_mk(price_str,"#90caf9"))
        self._log(f"📋 미체결 주문 {len(orders)}건 수신")

    def _fill_amend_from_table(self, row):
        tbl=self.tbl_open_orders_a
        oid_item=tbl.item(row,0); prc_item=tbl.item(row,3); dir_item=tbl.item(row,2)
        if oid_item: self.amend_oid.setText(oid_item.text())
        if prc_item:
            try: self.amend_price.setText(f"{float(prc_item.text()):.2f}")
            except ValueError: pass
        if dir_item:
            parts=dir_item.text().split()
            if len(parts)>=2:
                try: self.amend_qty.setValue(int(parts[1]))
                except ValueError: pass

    def _fill_cancel_from_table(self, row):
        oid_item=self.tbl_open_orders_c.item(row,0)
        if oid_item: self.cancel_oid.setText(oid_item.text())

    # ── 잔고 매도 패널 ───────────────────────────────────────
    def _show_pos_sell_panel(self, side, strike, qty=1, price=None):
        label = "CALL" if side == "C" else "PUT"
        self._ps_lbl_title.setText(f"▼ 잔고 청산 매도  [{label}]")
        self._ps_lbl_sym.setText(f"{label}  {strike}")
        self._ps_qty.setValue(max(1, qty))
        self._ps_price.setText(f"{price:.2f}" if price else "")
        self._ps_side   = side
        self._ps_strike = strike
        self._pos_sell_panel.setVisible(True)
        # 빠른매도 탭으로 자동 전환 + 가격·수량 자동입력
        tab_w = getattr(self, '_qord_tab_widget', None)
        if tab_w:
            for i in range(tab_w.count()):
                if "매도" in tab_w.tabText(i):
                    tab_w.setCurrentIndex(i)
                    break
        sell_price_w = getattr(self, 'sell_price', None)
        sell_qty_w   = getattr(self, 'sell_qty',   None)
        if sell_price_w and price:
            sell_price_w.setText(f"{price:.2f}")
        if sell_qty_w:
            sell_qty_w.setValue(max(1, qty))
        lbl = getattr(self, 'lbl_sell_status', None)
        if lbl:
            lbl.setStyleSheet(
                "color:#ffa500;font-size:12px;"
                "border:1px solid #333;border-radius:3px;padding:2px;")
            lbl.setText(f"선택: {label} {strike}  {qty}계약  — 가격 확인 후 매도")

    def _pos_sell_execute(self):
        side=getattr(self,'_ps_side',None); strike=getattr(self,'_ps_strike',None)
        if not side or not strike:
            self._log("⚠ 매도 대상 없음"); return
        price_txt=self._ps_price.text().strip()
        self._qord_fill(side, strike,
                        float(price_txt) if price_txt else None,
                        source="← 잔고 청산")
        self.qord_qty.setValue(self._ps_qty.value())
        self._pos_sell_panel.setVisible(False)
        self._qord_place("SELL")

    # ── +1호가 매수 ──────────────────────────────────────────
    def _plus1tick_buy(self):
        """미체결 BUY 주문 중 가장 최근 것을 +$0.05 올려 정정."""
        if not self.mw.connected:
            self._log("⚠ +1호가: 미연결"); return
        orders = getattr(self, '_open_orders_buf', [])
        buy_orders = [o for o in orders if o.get('action') == 'BUY' and o.get('price',0) > 0]
        if not buy_orders:
            self._log("⚠ +1호가: 미체결 BUY 주문 없음 (먼저 [미체결 조회] 클릭)"); return
        # 가장 최근 BUY 주문 (OID 최대값)
        target = max(buy_orders, key=lambda o: o['oid'])
        new_price = round(target['price'] + 0.05, 2)
        self._log(f"+1호가 매수 정정: OID={target['oid']}  {target['price']:.2f} → {new_price:.2f}")
        try:
            from ibapi.order import Order as IBOrder
            order = IBOrder()
            order.action       = "BUY"
            order.orderType    = "LMT"
            order.totalQuantity = target['qty']
            order.lmtPrice     = new_price
            order.tif          = target.get('tif','DAY')
            order.eTradeOnly   = False
            order.firmQuoteOnly= False
            self.mw.ib.placeOrder(target['oid'], target['contract'], order)
            self._log(f"✅ +1호가 정정 전송: {new_price:.2f}")
            if hasattr(self, 'lbl_amend_status'):
                self.lbl_amend_status.setText(f"+1호가 정정 → {new_price:.2f}")
        except Exception as e:
            self._log(f"❌ +1호가 정정 오류: {e}")

    # ── 빠른매도 탭 로직 ─────────────────────────────────────
    def _sell_selected_order(self):
        """빠른매도: Bid 가격 기준 LMT SELL 주문.
        IBKR은 옵션 MKT 주문을 reject하므로 현재 Bid로 LMT 전송.
        Bid 없으면 sell_price 입력값 → 그것도 없으면 차단."""
        side       = getattr(self, '_ps_side',   None)
        strike_txt = getattr(self, '_ps_strike', None)
        lbl        = getattr(self, 'lbl_sell_status', None)
        sell_qty_w = getattr(self, 'sell_qty', None)

        self._log(f"📤 빠른매도 버튼 클릭: _ps_side={side} _ps_strike={strike_txt} "
                  f"_ps_sym={getattr(self,'_ps_sym',None)} _ps_expiry={getattr(self,'_ps_expiry',None)}")

        if not side or not strike_txt:
            if lbl: lbl.setText("⚠ 잔고 행을 먼저 클릭하세요")
            self._log("⚠ 빠른매도: _ps_side/_ps_strike 없음 — 잔고 행 클릭 필요")
            return

        qty = sell_qty_w.value() if sell_qty_w else 1

        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
            return

        # ── Bid 가격 결정 ─────────────────────────────────────
        # 1순위: 현재가 패널에 표시 중인 옵션 Bid (_pp_opt_bid)
        # 2순위: sell_price 입력 필드
        # 3순위: 차단
        bid_price = getattr(self, '_pp_opt_bid', None)
        if bid_price and bid_price > 0:
            price = round(float(bid_price), 2)
            price_src = f"Bid ${price:.2f}"
        else:
            sell_price_w = getattr(self, 'sell_price', None)
            price_txt = sell_price_w.text().strip() if sell_price_w else ""
            if price_txt:
                try:
                    price = round(float(price_txt), 2)
                    if price <= 0: raise ValueError
                    price_src = f"입력가 ${price:.2f}"
                except ValueError:
                    if lbl: lbl.setText("⚠ 유효한 가격을 입력하거나 체인을 클릭하세요")
                    return
            else:
                if lbl: lbl.setText("⚠ Bid 가격 없음 — 체인 행 클릭 or 가격 직접 입력")
                self._log("⚠ 빠른매도: _pp_opt_bid 없고 sell_price 비어있음")
                return

        sym   = getattr(self, '_ps_sym', None) or (
                self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "")
        label = "CALL" if side == "C" else "PUT"
        msg   = f"매도 LMT  {sym} {label} {strike_txt}  {qty}계약  {price_src}"

        try:
            from ibapi.order import Order as IbOrder
            from core import make_opt_contract

            expiry = getattr(self, '_ps_expiry', None)
            if not expiry:
                expiry, tag = self._get_expiry()
                if expiry is None:
                    if lbl: lbl.setText("❌ 만기일을 확인할 수 없습니다")
                    return
            else:
                tag = _spx_tag(sym, expiry)

            contract = make_opt_contract(sym, float(strike_txt), side, expiry, tag)

            ibord = IbOrder()
            ibord.action        = "SELL"
            ibord.orderType     = "LMT"   # ← Bid 기준 지정가 (IBKR 옵션 MKT reject 회피)
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = "DAY"
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            oid = self.mw.ib.get_next_id()
            if oid is None:
                if lbl: lbl.setText("❌ 주문 ID 없음")
                return

            _orig_err = getattr(self.mw.ib, 'error', None)
            def _catch_err(reqId, errorCode, errorString, *a):
                self._log(f"‼ IB ERROR  reqId={reqId}  code={errorCode}  msg={errorString}")
                if _orig_err:
                    try: _orig_err(reqId, errorCode, errorString, *a)
                    except Exception: pass
            self.mw.ib.error = _catch_err

            self.mw.ib.placeOrder(oid, contract, ibord)
            result_msg = f"✅ 빠른매도: {msg}  (OID={oid})"
            if lbl:
                lbl.setStyleSheet(
                    "color:#ff6666;font-size:11px;"
                    "border:1px solid #333;border-radius:3px;padding:2px;")
                lbl.setText(result_msg)
            self._log(f"📤 {result_msg}")
            QTimer.singleShot(1500, self._fetch_open_orders)

        except Exception as e:
            if lbl: lbl.setText(f"❌ 오류: {e}")
            self._log(f"❌ 빠른매도 오류: {e}")

    def _sell_limit_order(self):
        """빠른매도: sell_price 입력값으로 LMT SELL 주문 전송."""
        side       = getattr(self, '_ps_side',   None)
        strike_txt = getattr(self, '_ps_strike', None)
        lbl        = getattr(self, 'lbl_sell_status', None)
        sell_price_w = getattr(self, 'sell_price', None)
        sell_qty_w   = getattr(self, 'sell_qty',   None)

        self._log(f"📤 지정가매도 버튼: _ps_side={side} _ps_strike={strike_txt} "
                  f"_ps_sym={getattr(self,'_ps_sym',None)} _ps_expiry={getattr(self,'_ps_expiry',None)}")

        if not side or not strike_txt:
            if lbl: lbl.setText("⚠ 잔고 행을 먼저 클릭하세요")
            return

        price_txt = sell_price_w.text().strip() if sell_price_w else ""
        qty       = sell_qty_w.value()           if sell_qty_w   else 1

        if not price_txt:
            if lbl: lbl.setText("⚠ 매도 가격을 입력하세요")
            return
        try:
            price = float(price_txt)
            if price <= 0: raise ValueError
        except ValueError:
            if lbl: lbl.setText("⚠ 유효한 가격을 입력하세요")
            return

        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
            return

        sym   = getattr(self, '_ps_sym', None) or (
                self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else "")
        label = "CALL" if side == "C" else "PUT"
        msg   = f"매도 LMT  {sym} {label} {strike_txt}  {qty}계약  ${price:.2f}"

        try:
            from ibapi.order import Order as IbOrder
            from core import make_opt_contract

            expiry = getattr(self, '_ps_expiry', None)
            if not expiry:
                expiry, tag = self._get_expiry()
                if expiry is None:
                    if lbl: lbl.setText("❌ 만기일을 확인할 수 없습니다")
                    return
            else:
                tag = _spx_tag(sym, expiry)

            contract = make_opt_contract(sym, float(strike_txt), side, expiry, tag)

            ibord = IbOrder()
            ibord.action        = "SELL"
            ibord.orderType     = "LMT"
            ibord.totalQuantity = qty
            ibord.lmtPrice      = price
            ibord.tif           = "DAY"
            ibord.eTradeOnly    = False
            ibord.firmQuoteOnly = False

            oid = self.mw.ib.get_next_id()
            if oid is None:
                if lbl: lbl.setText("❌ 주문 ID 없음")
                return

            _orig_err = getattr(self.mw.ib, 'error', None)
            def _catch_err(reqId, errorCode, errorString, *a):
                self._log(f"‼ IB ERROR  reqId={reqId}  code={errorCode}  msg={errorString}")
                if _orig_err:
                    try: _orig_err(reqId, errorCode, errorString, *a)
                    except Exception: pass
            self.mw.ib.error = _catch_err

            self.mw.ib.placeOrder(oid, contract, ibord)
            result_msg = f"✅ 지정가매도: {msg}  (OID={oid})"
            if lbl:
                lbl.setStyleSheet(
                    "color:#ff9999;font-size:11px;"
                    "border:1px solid #333;border-radius:3px;padding:2px;")
                lbl.setText(result_msg)
            self._log(f"📤 {result_msg}")
            QTimer.singleShot(1500, self._fetch_open_orders)

        except Exception as e:
            if lbl: lbl.setText(f"❌ 오류: {e}")
            self._log(f"❌ 지정가매도 오류: {e}")

    def _bump_sell_price(self, delta: float):
        """빠른매도 탭: 전체 미체결 주문 가격에 delta 일괄 적용."""
        buf = getattr(self, '_open_orders_buf', [])
        lbl = getattr(self, 'lbl_sell_status', None)
        if not buf:
            if lbl: lbl.setText("⚠ 미체결 주문 없음 — 먼저 조회하세요"); return
        if not self.mw.connected:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요."); return
        sign_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
        success, fail = 0, 0
        for o in buf:
            new_price = round(o["price"] + delta, 2)
            if new_price <= 0: fail += 1; continue
            try:
                from ibapi.order import Order as IbOrder
                ibord = IbOrder()
                ibord.action        = "SELL"
                ibord.orderType     = "LMT"
                ibord.totalQuantity = o["qty"]
                ibord.lmtPrice      = new_price
                ibord.tif           = o.get("tif","DAY")
                ibord.eTradeOnly    = False
                ibord.firmQuoteOnly = False
                self.mw.ib.placeOrder(o["oid"], o["contract"], ibord)
                o["price"] = new_price
                if o["oid"] == getattr(self, '_sell_selected_oid', None):
                    sell_price_w = getattr(self, 'sell_price', None)
                    if sell_price_w: sell_price_w.setText(f"{new_price:.2f}")
                success += 1
            except Exception as e:
                self._log(f"❌ OID={o['oid']} bump 오류: {e}"); fail += 1
        msg = f"✅ 전체 bump({sign_str}): {success}건 성공"
        if fail: msg += f" / {fail}건 실패"
        if lbl: lbl.setText(msg)
        self._log(msg)

    def _on_global_cancel(self):
        """취소 탭: 전체 미체결 주문 강제 취소 (reqGlobalCancel)."""
        from PyQt5.QtWidgets import QMessageBox
        ret = QMessageBox.warning(
            self, "⚠ 전체 취소 확인",
            "현재 API 세션의 모든 미체결 주문을 즉시 취소합니다.\n"
            "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
            return
        try:
            self.mw.ib.reqGlobalCancel()
            if hasattr(self, 'lbl_cancel_status'):
                self.lbl_cancel_status.setText("✅ reqGlobalCancel 전송 완료 — 전체 주문 취소 요청됨")
            self._log("🚨 reqGlobalCancel 전송 완료")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"reqGlobalCancel 실패: {e}")
            self._log(f"❌ reqGlobalCancel 오류: {e}")

    def _emergency_sell_all(self):
        """잔고 전체 시장가 매도 + 미체결 매수 전부 취소."""
        self._emergency_sell_positions()
        self._emergency_cancel_orders()

    def _emergency_sell_positions(self):
        """IBKR 포지션 전체를 시장가(MKT)로 즉시 매도."""
        if not self.mw.connected:
            self._log("🚨 긴급매도: 미연결"); return
        ib = self.mw.ib
        _pos_buf = []

        def _on_pos(account, contract, pos, avg_cost):
            if getattr(contract,'secType','') == 'OPT' and int(pos) > 0:
                _pos_buf.append((contract, int(pos)))

        def _on_pos_end():
            if not _pos_buf:
                self._log("🚨 긴급매도: 보유 포지션 없음"); return
            from ibapi.order import Order as IBOrder
            for contract, qty in _pos_buf:
                order = IBOrder()
                order.action        = "SELL"
                order.orderType     = "MKT"
                order.totalQuantity = qty
                order.tif           = "DAY"
                order.eTradeOnly    = False
                order.firmQuoteOnly = False
                try:
                    oid = ib.nextOrderId if hasattr(ib,'nextOrderId') else 0
                    ib.placeOrder(oid, contract, order)
                    sym = getattr(contract,'localSymbol','') or getattr(contract,'symbol','')
                    self._log(f"🚨 긴급매도 전송: {sym} {qty}계약 시장가")
                except Exception as e:
                    self._log(f"❌ 긴급매도 오류: {e}")

        ib._orig_pos    = getattr(ib,'position',    lambda *a:None)
        ib._orig_posEnd = getattr(ib,'positionEnd', lambda:None)
        ib.position    = _on_pos
        ib.positionEnd = _on_pos_end
        try: ib.reqPositions()
        except Exception as e: self._log(f"❌ 긴급매도 포지션조회 오류: {e}")

        # [v1.2] 튜플 반환 람다 → def 교체 (sipBadCatcherResult 방지)
        def _restore_emrg_handlers():
            ib.position    = ib._orig_pos
            ib.positionEnd = ib._orig_posEnd
        QTimer.singleShot(3000, _restore_emrg_handlers)

    def _emergency_cancel_orders(self):
        """미체결 전체 주문(BUY + SELL) 취소."""
        if not self.mw.connected:
            self._log("🚨 미체결취소: 미연결"); return
        orders = getattr(self,'_open_orders_buf',[])
        if not orders:
            self._log("🚨 미체결취소: 미체결 주문 없음 (먼저 [미체결 조회] 클릭)"); return
        for o in orders:
            try:
                self.mw.ib.cancelOrder(o['oid'])
                self._log(f"🚨 취소 전송: OID={o['oid']} {o['action']} {o['symbol']}")
            except Exception as e:
                self._log(f"❌ 취소 오류 OID={o['oid']}: {e}")

    # ── 빠른 주문 단축키 / Enter 포커스 체인 ─────────────────────
    def _setup_quick_order_shortcuts(self):
        """
        단축키 등록 + Enter 포커스 흐름 설정.
          Alt+[     → 가격 필드 포커스
          Alt+]     → 수량 필드 포커스
          Alt+Enter → 매수 버튼 클릭
          가격 Enter → 수량 이동 → 매수 버튼 포커스 → Enter = 주문
        """
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui     import QKeySequence

        sc_price = QShortcut(QKeySequence("Alt+["), self)
        sc_price.setContext(Qt.WidgetWithChildrenShortcut)
        sc_price.activated.connect(self._sc_focus_price)

        sc_qty = QShortcut(QKeySequence("Alt+]"), self)
        sc_qty.setContext(Qt.WidgetWithChildrenShortcut)
        sc_qty.activated.connect(self._sc_focus_qty)

        sc_buy = QShortcut(QKeySequence("Alt+Return"), self)
        sc_buy.setContext(Qt.WidgetWithChildrenShortcut)
        sc_buy.activated.connect(self.btn_qord_buy.click)

        # 가격 Enter → 수량 / 수량 Enter → 매수 버튼
        self._install_enter_next(self.qord_price, self.qord_qty)
        self._install_enter_next(self.qord_qty,   self.btn_qord_buy)

    def _sc_focus_price(self):
        self.qord_price.setFocus(); self.qord_price.selectAll()

    def _sc_focus_qty(self):
        self.qord_qty.setFocus(); self.qord_qty.selectAll()

    @staticmethod
    def _install_enter_next(src, dst):
        """src 위젯에서 Enter/Return 키 → dst 위젯으로 포커스 이동."""
        from PyQt5.QtCore    import QObject, QEvent

        class _Filter(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.KeyPress and ev.key() in (
                        Qt.Key_Return, Qt.Key_Enter):
                    dst.setFocus()
                    if hasattr(dst, 'selectAll'):
                        dst.selectAll()
                    return True
                return False

        f = _Filter(src)
        src.installEventFilter(f)
        src._ef_enter = f   # GC 방지