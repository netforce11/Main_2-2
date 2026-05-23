"""
combo_profit_alert_banner.py — 수익률 경고 배너 + 테스트 UI  v3.0
──────────────────────────────────────────────────────────────────
수익률 계산 공식 (매도 스프레드 기준):
  entry   = 체결 시 수취한 CREDIT  (예: $3.00)
  current = 실시간 BAG net mid     (예: $0.50)
  pct = (entry - current) / entry × 100   → 83%
  500% = current ≤ entry / 6

구간:
    0 ~ 399% : 회색  — 정상 보유
  400 ~ 449% : 노랑  — 반대 포지션 선매수 고려
  450 ~ 499% : 주황  — 전략 전환 검토
  500%  이상 : 빨강  — 즉시 반대 포지션 권고

테스트 버튼 (우측 하단 ▶ TEST 클릭 시 펼침):
  [ 0% ] [ 400% ] [ 460% ] [ 510% ] [ TG ] [ Wolf ON ] [ Wolf OFF ] [ 리셋 ]

사용법:
  from combo_profit_alert_banner import ProfitAlertBanner
  self.profit_alert_banner = ProfitAlertBanner(wolf_banner=self.wolf_banner)
  layout.addWidget(self.profit_alert_banner)
──────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout,
                              QLabel, QPushButton, QFrame)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont

# ── 구간 정의 ──────────────────────────────────────────────────────
_LEVELS = [
    (500, 9999, "#3b0000", "#ff4444", "🚨", "수익 500%+  즉시 반대 포지션 매수 권고"),
    (450,  499, "#2d1a00", "#ff8c00", "⚠️",  "수익 450%+  전략 전환 검토 구간"),
    (400,  449, "#2a2200", "#f0c040", "💡", "수익 400%+  반대 포지션 선매수 고려"),
    (  0,  399, "#0d1520", "#3a4a5a", "📊", "수익률 정상 보유 구간"),
]
_BTN_BASE = (
    "QPushButton{background:#111827;color:#778899;border:1px solid #334455;"
    "border-radius:3px;padding:2px 7px;font-size:10px;}"
    "QPushButton:hover{background:#1e2d3d;color:#aabbcc;}"
    "QPushButton:pressed{background:#0d1a26;}"
)


def calc_sell_pct(entry: float, current: float) -> float:
    if not entry or entry <= 0:
        return 0.0
    return round((entry - current) / entry * 100, 1)


def calc_buy_pct(entry: float, current: float) -> float:
    if not entry or entry <= 0:
        return 0.0
    return round((current - entry) / entry * 100, 1)


# ══════════════════════════════════════════════════════════════════
class ProfitAlertBanner(QWidget):
    """수익률 경고 배너 + 접이식 테스트 패널."""

    def __init__(self, parent=None, wolf_banner=None):
        super().__init__(parent)
        self._pct         = 0.0
        self._wolf        = wolf_banner   # WolfSystemBanner 참조 (선택)
        self._test_open   = False
        self._build()

    # ── 빌드 ────────────────────────────────────────────────────────

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(2)

        # ── 메인 배너 행 ─────────────────────────────────────────
        self._banner_row = QWidget()
        self._banner_row.setFixedHeight(46)
        hl = QHBoxLayout(self._banner_row)
        hl.setContentsMargins(12, 4, 8, 4)
        hl.setSpacing(8)

        self._lbl_icon = QLabel("📊")
        self._lbl_icon.setFixedWidth(22)
        self._lbl_icon.setAlignment(Qt.AlignCenter)
        self._lbl_icon.setFont(QFont("Segoe UI Emoji", 13))

        self._lbl_msg = QLabel("포지션 없음")
        self._lbl_msg.setFont(QFont("Malgun Gothic", 10, QFont.Bold))
        self._lbl_msg.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self._lbl_pct = QLabel("")
        self._lbl_pct.setFont(QFont("Consolas", 12, QFont.Bold))
        self._lbl_pct.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._lbl_pct.setFixedWidth(72)

        self._btn_test_toggle = QPushButton("▶ TEST")
        self._btn_test_toggle.setFixedSize(62, 22)
        self._btn_test_toggle.setStyleSheet(_BTN_BASE)
        self._btn_test_toggle.clicked.connect(self._toggle_test)

        hl.addWidget(self._lbl_icon)
        hl.addWidget(self._lbl_msg, stretch=1)
        hl.addWidget(self._lbl_pct)
        hl.addWidget(self._btn_test_toggle)

        # ── 테스트 패널 (접이식) ─────────────────────────────────
        self._test_panel = QFrame()
        self._test_panel.setFixedHeight(0)   # 초기 숨김
        self._test_panel.setStyleSheet(
            "QFrame{background:#080e18;border:1px solid #1a2a3a;"
            "border-radius:4px;}")
        tl = QHBoxLayout(self._test_panel)
        tl.setContentsMargins(8, 4, 8, 4)
        tl.setSpacing(6)

        lbl = QLabel("수익률 테스트:")
        lbl.setStyleSheet("color:#556677;font-size:10px;border:none;background:transparent;")
        tl.addWidget(lbl)

        for pct_val, label, color in [
            (50,   "  0%",  "#445566"),
            (400,  "400%",  "#c8a000"),
            (460,  "460%",  "#cc6600"),
            (510,  "500%",  "#cc2222"),
        ]:
            btn = QPushButton(label)
            btn.setFixedSize(46, 22)
            btn.setStyleSheet(
                f"QPushButton{{background:#0d1520;color:{color};"
                f"border:1px solid {color}55;border-radius:3px;"
                f"font-size:10px;font-weight:bold;}}"
                f"QPushButton:hover{{background:{color}22;}}"
            )
            btn.clicked.connect(lambda _, v=pct_val: self.update_pct(v))
            tl.addWidget(btn)

        tl.addSpacing(8)

        # TG 테스트
        btn_tg = QPushButton("📨 TG")
        btn_tg.setFixedSize(52, 22)
        btn_tg.setStyleSheet(_BTN_BASE)
        btn_tg.clicked.connect(self._test_tg)
        btn_tg.setToolTip("텔레그램 알림 테스트 발송")
        tl.addWidget(btn_tg)

        # Wolf ON/OFF 테스트
        btn_wolf_on = QPushButton("🐺 ON")
        btn_wolf_on.setFixedSize(58, 22)
        btn_wolf_on.setStyleSheet(
            "QPushButton{background:#001a00;color:#00cc66;"
            "border:1px solid #00cc6655;border-radius:3px;font-size:10px;}"
            "QPushButton:hover{background:#002800;}")
        btn_wolf_on.clicked.connect(self._test_wolf_on)
        btn_wolf_on.setToolTip("Wolf System ON 테스트")
        tl.addWidget(btn_wolf_on)

        btn_wolf_off = QPushButton("○ OFF")
        btn_wolf_off.setFixedSize(52, 22)
        btn_wolf_off.setStyleSheet(_BTN_BASE)
        btn_wolf_off.clicked.connect(self._test_wolf_off)
        btn_wolf_off.setToolTip("Wolf System OFF 테스트")
        tl.addWidget(btn_wolf_off)

        # SpecialFillWatcher 테스트
        btn_watcher = QPushButton("⏱ 감시")
        btn_watcher.setFixedSize(52, 22)
        btn_watcher.setStyleSheet(_BTN_BASE)
        btn_watcher.clicked.connect(self._test_watcher)
        btn_watcher.setToolTip("SpecialFillWatcher 10초 타이머 테스트")
        tl.addWidget(btn_watcher)

        tl.addStretch()

        # 리셋
        btn_reset = QPushButton("↺ 리셋")
        btn_reset.setFixedSize(52, 22)
        btn_reset.setStyleSheet(_BTN_BASE)
        btn_reset.clicked.connect(self.clear)
        tl.addWidget(btn_reset)

        vl.addWidget(self._banner_row)
        vl.addWidget(self._test_panel)

        self._apply_style("#0d1520", "#3a4a5a", "📊", "포지션 없음", "")

    # ── Public API ───────────────────────────────────────────────────

    def update_pct(self, pct: float) -> None:
        """수익률(%) 갱신. _on_tick 에서 자동 호출."""
        self._pct = pct
        bg, fg, icon, msg = "#0d1520", "#3a4a5a", "📊", "수익률 정상 보유 구간"
        for min_p, max_p, bg_, fg_, icon_, msg_ in _LEVELS:
            if min_p <= pct <= max_p:
                bg, fg, icon, msg = bg_, fg_, icon_, msg_
                break
        sign = "+" if pct >= 0 else ""
        self._apply_style(bg, fg, icon, msg, f"{sign}{pct:.0f}%")

    def clear(self) -> None:
        self._pct = 0.0
        self._apply_style("#0d1520", "#3a4a5a", "📊", "포지션 없음", "")

    # ── 내부: 테스트 핸들러 ──────────────────────────────────────────

    def _toggle_test(self) -> None:
        self._test_open = not self._test_open
        target_h = 36 if self._test_open else 0
        self._btn_test_toggle.setText("▼ TEST" if self._test_open else "▶ TEST")

        anim = QPropertyAnimation(self._test_panel, b"maximumHeight", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setStartValue(self._test_panel.height())
        anim.setEndValue(target_h)
        anim.start()
        self._anim = anim   # GC 방지

    def _test_tg(self) -> None:
        """텔레그램 테스트 메시지 발송."""
        try:
            from combo_order_special_condition import notify_filled
            notify_filled({
                "strategy": "[TEST] 풋 스프레드 7270/7265",
                "side": "SELL", "qty": 1, "oid": 0,
                "legs": [{"expiry": "20260516"}],
            }, avg_price=3.00)
        except Exception as e:
            print(f"[TEST] TG 발송 실패: {e}")

    def _test_wolf_on(self) -> None:
        if self._wolf and hasattr(self._wolf, 'set_on'):
            self._wolf.set_on(target_price=3.00, strategy="[TEST] 풋 스프레드")
        else:
            print("[TEST] WolfSystemBanner 미연결 — wolf_banner 파라미터 확인")

    def _test_wolf_off(self) -> None:
        if self._wolf and hasattr(self._wolf, 'set_off'):
            self._wolf.set_off()
        else:
            print("[TEST] WolfSystemBanner 미연결")

    def _test_watcher(self) -> None:
        """SpecialFillWatcher 10초 타이머 테스트."""
        try:
            from combo_order_special_condition import SpecialFillWatcher
            w = SpecialFillWatcher.get()
            TEST_OID = 99999
            w.unwatch(TEST_OID)
            w.watch(None, oid=TEST_OID, target=3.0, action="SELL",
                    legs=[], strat="[TEST] 풋 스프레드")
            w.on_net_price_update(TEST_OID, net_price=3.05)
            print("[TEST] SpecialFillWatcher 시작 — 10초 후 TG 메시지 확인")
        except Exception as e:
            print(f"[TEST] Watcher 테스트 실패: {e}")

    # ── 내부: 스타일 ────────────────────────────────────────────────

    def _apply_style(self, bg, fg, icon, msg, pct_text) -> None:
        self._banner_row.setStyleSheet(
            f"QWidget{{background:{bg};border-radius:4px;"
            f"border:1px solid {fg}44;}}")
        self._lbl_icon.setText(icon)
        _ns = f"color:{fg};background:transparent;border:none;"
        self._lbl_msg.setText(msg)
        self._lbl_msg.setStyleSheet(_ns)
        self._lbl_pct.setText(pct_text)
        self._lbl_pct.setStyleSheet(_ns)
