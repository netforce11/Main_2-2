"""
order_panel/tab_sniper.py — 탭5 「🎯 스나이퍼」 + 잔고매도패널 UI 빌드
════════════════════════════════════════════════════════════════
포함:
  build_sniper_tab(mixin, tab_w)  → 스나이퍼 탭 위젯을 tab_w에 추가
    - 행사가 / C-P / 만기 (자동 입력)
    - 목표가 + 비교 조건 + KST 시간 + 허용오차
    - 방향/유형/주문가/수량 + 버튼 + 목록 (tab_sniper_order.py)
  build_pos_sell_panel(mixin)     → 잔고 청산 매도 패널 반환
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QSpinBox,
)
from PyQt5.QtCore import Qt, QObject, QEvent

from order_panel.helpers          import _animate_press
from order_panel.tab_sniper_order import build_sniper_order_section


def build_sniper_tab(m, tab_w) -> None:
    """스나이퍼 탭 위젯을 생성하여 tab_w에 추가."""
    sniper_w = QWidget()
    sn_v = QVBoxLayout(sniper_w)
    sn_v.setSpacing(4); sn_v.setContentsMargins(6, 6, 6, 6)

    _sn_ls = "color:#aaa;font-size:13px;border:none;"
    _sn_es = ("color:#ffd700;font-weight:bold;font-size:14px;"
              "background:#0a0a1e;border:1px solid #444;")
    _cmb_s = ("QComboBox{background:#0a0a1e;color:#ffd700;border:1px solid #444;"
              "font-size:14px;font-weight:bold;}"
              "QComboBox QAbstractItemView{background:#0a0a1e;color:#ffd700;font-size:14px;}"
              "QComboBox::drop-down{border:none;}")

    # ── 조건 설정: 행사가 / C-P / 만기 ─────────────────────
    sn_v.addWidget(QLabel("▶ 조건 설정  (콜-풋 체인 클릭 시 자동 입력)",
        styleSheet="color:#5dade2;font-size:12px;font-weight:bold;border:none;"))

    sn_g1 = QGridLayout(); sn_g1.setSpacing(4)
    sn_g1.addWidget(QLabel("행사가:", styleSheet=_sn_ls), 0, 0)
    m.snp_strike = QLineEdit(); m.snp_strike.setPlaceholderText("콜풋탭 클릭 시 자동 입력")
    m.snp_strike.setStyleSheet(_sn_es)
    sn_g1.addWidget(m.snp_strike, 0, 1, 1, 3)
    sn_g1.addWidget(QLabel("C/P:", styleSheet=_sn_ls), 1, 0)
    m.snp_right = QComboBox(); m.snp_right.addItems(["C", "P"])
    m.snp_right.setStyleSheet(_cmb_s); sn_g1.addWidget(m.snp_right, 1, 1)
    sn_g1.addWidget(QLabel("만기:", styleSheet=_sn_ls), 1, 2)
    m.snp_expiry = QLineEdit(); m.snp_expiry.setPlaceholderText("YYYYMMDD")
    m.snp_expiry.setStyleSheet(_sn_es); sn_g1.addWidget(m.snp_expiry, 1, 3)
    sn_v.addLayout(sn_g1)

    # ── 목표가 + 비교 조건 + KST 시간 + 허용오차 ───────────
    sep1 = QLabel(); sep1.setFixedHeight(1)
    sep1.setStyleSheet("background:#2a3a2a;border:none;")
    sn_v.addWidget(sep1)

    sn_g2 = QGridLayout(); sn_g2.setSpacing(4)
    sn_g2.addWidget(QLabel("목표가($):", styleSheet=_sn_ls), 0, 0)
    m.snp_price = QLineEdit(); m.snp_price.setPlaceholderText("예: 0.20")
    m.snp_price.setStyleSheet(
        "color:#00ff88;font-weight:bold;font-size:14px;"
        "background:#0a0a1e;border:1px solid #2a6a2a;")
    sn_g2.addWidget(m.snp_price, 0, 1)
    m.snp_cmp = QComboBox(); m.snp_cmp.addItems(["<=  이하일 때", ">=  이상일 때"])
    m.snp_cmp.setStyleSheet(
        "QComboBox{background:#0a0a1e;color:#00ff88;border:1px solid #2a6a2a;"
        "font-size:12px;font-weight:bold;}"
        "QComboBox QAbstractItemView{background:#0a0a1e;color:#00ff88;font-size:12px;}"
        "QComboBox::drop-down{border:none;}")
    sn_g2.addWidget(m.snp_cmp, 0, 2, 1, 2)

    sn_g2.addWidget(QLabel("한국시간(KST):", styleSheet=_sn_ls), 1, 0)
    m.snp_time = QLineEdit(); m.snp_time.setPlaceholderText("HH:MM  예) 04:46 / 18:30")
    m.snp_time.setMaxLength(5); m.snp_time.setStyleSheet(_sn_es)

    class _TimeFilter(QObject):
        def eventFilter(self_, obj, ev):
            if ev.type() == QEvent.KeyPress:
                key = ev.key(); txt = obj.text()
                if (len(txt) == 2 and key not in (
                        Qt.Key_Backspace, Qt.Key_Delete,
                        Qt.Key_Left, Qt.Key_Right, Qt.Key_Colon)
                        and ":" not in txt):
                    obj.setText(txt + ":"); obj.setCursorPosition(3)
            return False
    _tf = _TimeFilter(m.snp_time)
    m.snp_time.installEventFilter(_tf)
    m.snp_time._time_filter = _tf
    sn_g2.addWidget(m.snp_time, 1, 1)

    sn_g2.addWidget(QLabel("허용오차(분):", styleSheet=_sn_ls), 1, 2)
    m.snp_margin = QSpinBox(); m.snp_margin.setRange(0, 60); m.snp_margin.setValue(0)
    m.snp_margin.setFixedHeight(26)
    m.snp_margin.setToolTip(
        "0분 = 해당 분(HH:MM:00 ~ HH:MM:59) 안에만 발동\n"
        "1분 = ±1분 허용 (설정시각 전후 1분)")
    m.snp_margin.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #444;font-size:13px;")
    sn_g2.addWidget(m.snp_margin, 1, 3)
    sn_v.addLayout(sn_g2)

    # ── 주문 설정·버튼·목록 (별도 모듈) ─────────────────────
    build_sniper_order_section(m, sn_v)
    tab_w.addTab(sniper_w, "🎯 스나이퍼")


def build_pos_sell_panel(m) -> QWidget:
    """잔고 청산 매도 패널(하단 슬라이드) 위젯을 생성하여 반환."""
    panel = QWidget()
    panel.setVisible(False)
    panel.setStyleSheet(
        "background:#1a0a0a;border:1px solid #6b1a1a;border-radius:4px;margin-top:-20px;")
    ps_v = QVBoxLayout(panel)
    ps_v.setContentsMargins(6, 5, 6, 5); ps_v.setSpacing(4)

    ps_hdr = QHBoxLayout()
    m._ps_lbl_title = QLabel("▼ 잔고 청산 매도")
    m._ps_lbl_title.setStyleSheet(
        "color:#ff6666;font-weight:bold;font-size:13px;border:none;")
    ps_hdr.addWidget(m._ps_lbl_title); ps_hdr.addStretch()
    ps_v.addLayout(ps_hdr)

    ps_info = QHBoxLayout()
    m._ps_lbl_sym = QLabel("―")
    m._ps_lbl_sym.setStyleSheet(
        "color:#ffd700;font-size:13px;font-weight:bold;border:none;")
    ps_info.addWidget(QLabel("종목:", styleSheet="color:#aaa;font-size:12px;border:none;"))
    ps_info.addWidget(m._ps_lbl_sym); ps_info.addStretch()
    ps_v.addLayout(ps_info)

    ps_qty_row = QHBoxLayout()
    from PyQt5.QtWidgets import QSpinBox as _QSB
    m._ps_qty = _QSB(); m._ps_qty.setRange(1, 9999); m._ps_qty.setValue(1)
    m._ps_qty.setFixedHeight(24)
    m._ps_qty.setStyleSheet(
        "background:#0a0a1e;color:#fff;border:1px solid #6b1a1a;font-size:13px;")
    ps_qty_row.addWidget(QLabel("수량:", styleSheet="color:#aaa;font-size:12px;border:none;"))
    ps_qty_row.addWidget(m._ps_qty); ps_qty_row.addStretch()
    ps_v.addLayout(ps_qty_row)

    ps_price_row = QHBoxLayout()
    from PyQt5.QtWidgets import QLineEdit as _QLE
    m._ps_price = _QLE(); m._ps_price.setPlaceholderText("지정가 (비워두면 시장가)")
    m._ps_price.setFixedHeight(24)
    m._ps_price.setStyleSheet(
        "color:#ffd700;font-size:13px;background:#0a0a1e;border:1px solid #6b1a1a;")
    ps_price_row.addWidget(QLabel("가격:", styleSheet="color:#aaa;font-size:12px;border:none;"))
    ps_price_row.addWidget(m._ps_price)
    ps_v.addLayout(ps_price_row)

    ps_btn = QPushButton("▼ 매도 주문 전송")
    ps_btn.setStyleSheet(
        "QPushButton{background:#6b1a1a;color:#ff6666;font-size:14px;"
        "font-weight:bold;padding:8px;border-radius:4px;}"
        "QPushButton:pressed{background:#4b0a0a;padding-top:10px;padding-bottom:6px;}")
    ps_btn.clicked.connect(lambda: (_animate_press(ps_btn), m._pos_sell_execute()))
    ps_v.addWidget(ps_btn)
    return panel
