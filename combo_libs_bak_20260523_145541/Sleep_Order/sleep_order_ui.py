"""
sleep_order_ui.py — 수면 예약 주문 UI 조립  v2.1
════════════════════════════════════════
SleepOrderRightPanel : 2단 패널
  좌  — 예약주문 + Debit 급락캐치 + 콤보 비중 주문 [신규 ↓ 하단 추가]
  우  — 단일 옵션 급락캐치
SleepOrderButton : combo 탭 우측 상단 버튼 (기존 유지)
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QFrame, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer


# ══════════════════════════════════════════════════════════════
# SleepOrderRightPanel — 좌 / 중 / 우  3단 패널
# ══════════════════════════════════════════════════════════════

class SleepOrderRightPanel(QWidget):
    """
    Main_config.py ConfigTab 우측.
    ┌──────────────┬──────────────┬──────────────┐
    │ 예약주문+Debit│  단일옵션캐치 │ 콤보 비중    │
    └──────────────┴──────────────┴──────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#0a0a18;")
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_left_col(),  stretch=1)
        root.addWidget(_vline())
        root.addWidget(self._make_right_col(), stretch=1)

    # ── 좌측: 예약주문 + Debit + 콤보 비중 ──────────────
    def _make_left_col(self) -> QWidget:
        col = QWidget(); col.setStyleSheet("background:#0a0a18;")
        v   = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        hdr = QLabel("🌙  수면 예약 주문 설정")
        hdr.setStyleSheet(
            "color:#ffd700;font-size:18px;font-weight:bold;border:none;"
            "padding:6px 12px 2px 12px;")
        v.addWidget(hdr)
        scroll = _make_scroll()
        inner  = QWidget(); inner.setStyleSheet("background:#0a0a18;")
        vlay   = QVBoxLayout(inner)
        vlay.setContentsMargins(10, 8, 10, 12); vlay.setSpacing(10)
        vlay.addWidget(self._build_schedule_section())
        vlay.addWidget(self._build_position_close_section())
        from Sleep_Order.ui_panel_debit import DebitSpikePanel
        self._debit_panel = DebitSpikePanel()
        vlay.addWidget(self._debit_panel)
        vlay.addStretch()
        scroll.setWidget(inner); v.addWidget(scroll)
        return col

    # ── 우측: 단일 옵션 급락캐치 ─────────────────────────
    def _make_right_col(self) -> QWidget:
        col = QWidget(); col.setStyleSheet("background:#0a0a18;")
        v   = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        hdr = QLabel("🎯  단일 옵션 급락 캐치")
        hdr.setStyleSheet(
            "color:#2ecc71;font-size:18px;font-weight:bold;border:none;"
            "padding:6px 12px 2px 12px;")
        v.addWidget(hdr)
        scroll = _make_scroll()
        inner  = QWidget(); inner.setStyleSheet("background:#0a0a18;")
        vlay   = QVBoxLayout(inner)
        vlay.setContentsMargins(10, 8, 10, 12); vlay.setSpacing(10)
        from Sleep_Order.ui_panel_single import SingleOptSpikePanel
        self._single_panel = SingleOptSpikePanel()
        vlay.addWidget(self._single_panel)
        vlay.addStretch()
        scroll.setWidget(inner); v.addWidget(scroll)
        return col

    def _build_schedule_section(self):
        from Sleep_Order.sleep_order_section_a import build_schedule_section_a
        return build_schedule_section_a(self)

    def _build_position_close_section(self):
        from Sleep_Order.position_close_section import build_position_close_section
        return build_position_close_section(self)


# ── 공통 헬퍼 ────────────────────────────────────────────────────

def _vline() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.VLine)
    f.setFixedWidth(1)
    f.setStyleSheet("background:#2a2a5a;border:none;")
    return f


def _make_scroll() -> QScrollArea:
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setStyleSheet(
        "QScrollArea{border:none;background:#0a0a18;}"
        "QScrollBar:vertical{width:8px;background:#06060e;}"
        "QScrollBar::handle:vertical{background:#3a3a7a;border-radius:4px;}"
        "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
    return s


# ══════════════════════════════════════════════════════════════
# SleepOrderButton — combo 탭 버튼 (기존 유지)
# ══════════════════════════════════════════════════════════════

class SleepOrderButton(QWidget):
    """SyntheticStatusPanel 우측 상단 예약주문 ON/OFF 버튼."""

    def __init__(self, ref: object, parent=None):
        super().__init__(parent)
        self._ref = ref
        self.setStyleSheet("background:transparent;")
        self._build()
        QTimer.singleShot(0, self._connect_watcher)

    def set_ref(self, ref: object) -> None:
        self._ref = ref

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0); lay.setSpacing(6)
        self._lbl_onoff = QLabel("OFF")
        self._lbl_onoff.setFixedWidth(36); self._lbl_onoff.setAlignment(Qt.AlignCenter)
        self._lbl_onoff.setStyleSheet(
            "color:#ff4444;font-size:11px;font-weight:bold;"
            "background:#2a0a0a;border:1px solid #6a1a1a;border-radius:3px;padding:1px 4px;")
        lay.addWidget(self._lbl_onoff)
        self._lbl_status = QLabel("⏸ 대기")
        self._lbl_status.setStyleSheet("color:#555577;font-size:12px;border:none;")
        lay.addWidget(self._lbl_status)
        self._btn = QPushButton("🌙 예약 주문")
        self._btn.setFixedHeight(26); self._btn.setCheckable(True)
        self._btn.setStyleSheet(
            "QPushButton{background:#1a1a0a;color:#ffd700;font-size:13px;"
            "font-weight:bold;border:1px solid #5a5a1a;border-radius:4px;padding:2px 12px;}"
            "QPushButton:hover{background:#2a2a0a;color:#ffee44;}"
            "QPushButton:checked{background:#0a2a0a;color:#00ff88;border:2px solid #00ff44;}"
            "QPushButton:pressed{background:#080808;}")
        self._btn.clicked.connect(self._on_click)
        lay.addWidget(self._btn)

    def _connect_watcher(self) -> None:
        try:
            from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
            SleepOrderWatcher.get().status_changed.connect(self._on_status)
        except Exception as e:
            print(f"[SleepBtn] watcher 연결 실패: {e}")

    def _on_click(self) -> None:
        try:
            if self._ref is None:
                w = self
                for _ in range(8):
                    w = w.parent()
                    if w is None: break
                    if hasattr(w, '_sleep_get_chain'):
                        self._ref = w; break
            from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
            started = SleepOrderWatcher.get().toggle(self._ref)
            if started:
                self._set_on(); self._btn.setText("🟢 ON  예약감시중")
            else:
                self._set_off(); self._btn.setText("🌙 예약 주문")
                self._lbl_status.setText("⏸ 대기")
        except Exception as e:
            print(f"[SleepBtn] toggle 실패: {e}")

    def _set_on(self) -> None:
        self._lbl_onoff.setText("ON")
        self._lbl_onoff.setStyleSheet(
            "color:#00ff88;font-size:11px;font-weight:bold;"
            "background:#0a2a0a;border:1px solid #00ff44;border-radius:3px;padding:1px 4px;")
        self._btn.setChecked(True)

    def _set_off(self) -> None:
        self._lbl_onoff.setText("OFF")
        self._lbl_onoff.setStyleSheet(
            "color:#ff4444;font-size:11px;font-weight:bold;"
            "background:#2a0a0a;border:1px solid #6a1a1a;border-radius:3px;padding:1px 4px;")
        self._btn.setChecked(False)

    def _on_status(self, text: str) -> None:
        self._lbl_status.setText(text)
        if "주문완료" in text:
            self._set_on(); self._btn.setText("✅ ON  주문완료")
        elif "감시중" in text:
            self._set_on(); self._btn.setText("🟢 ON  예약감시중")
        else:
            self._set_off(); self._btn.setText("🌙 예약 주문")


# ══════════════════════════════════════════════════════════════
# PositionCloseButton — SleepOrderButton 우측 배치
# ══════════════════════════════════════════════════════════════

class PositionCloseButton(QWidget):
    """
    예약주문 버튼 우측 옆 배치.
    설정탭 포지션 청산 슬롯 감시 ON/OFF 상태 표시 전용.
    (실제 등록/취소는 설정탭 슬롯 UI 에서 수행)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self._build()
        QTimer.singleShot(0, self._connect_watcher)

    def _build(self) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(4)

        # 슬롯 3개 상태 뱃지
        self._slot_lbls = []
        for i in range(3):
            lbl = QLabel(f"S{i+1}")
            lbl.setFixedWidth(28)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                "color:#333355;font-size:10px;font-weight:bold;"
                "background:#0a0a18;border:1px solid #222244;"
                "border-radius:3px;padding:1px 3px;")
            lbl.setToolTip(f"슬롯{i+1}: 비활성")
            lay.addWidget(lbl)
            self._slot_lbls.append(lbl)

        self._btn = QPushButton("🎯 청산 예약")
        self._btn.setFixedHeight(26)
        self._btn.setStyleSheet(
            "QPushButton{background:#1a0a0a;color:#ff6b6b;font-size:13px;"
            "font-weight:bold;border:1px solid #5a1a1a;"
            "border-radius:4px;padding:2px 12px;}"
            "QPushButton:hover{background:#2a0a0a;color:#ff8888;}")
        self._btn.setToolTip("설정 탭 → 포지션 청산 설정에서 슬롯 등록")
        lay.addWidget(self._btn)

    def _connect_watcher(self) -> None:
        try:
            from Sleep_Order.position_close_watcher import PositionCloseWatcher
            PositionCloseWatcher.get().slot_status_changed.connect(
                self._on_slot_status)
        except Exception as e:
            print(f"[ClosBtn] watcher 연결 실패: {e}")

    def _on_slot_status(self, idx: int, text: str) -> None:
        if idx >= len(self._slot_lbls):
            return
        lbl = self._slot_lbls[idx]
        lbl.setToolTip(f"슬롯{idx+1}: {text}")

        if text.startswith("✅"):
            style = ("color:#00ff88;background:#071a0e;"
                     "border:1px solid #00ff44;")
        elif "감시" in text or "주문" in text or "정정" in text:
            style = ("color:#ffd700;background:#1a1a0a;"
                     "border:1px solid #5a5a1a;")
        elif "대기" in text:
            style = ("color:#90caf9;background:#0a0a1a;"
                     "border:1px solid #3a3a7a;")
        elif text.startswith("⚠️") or text.startswith("🚨"):
            style = ("color:#ff4444;background:#1a0a0a;"
                     "border:1px solid #6a1a1a;")
        else:
            style = ("color:#333355;background:#0a0a18;"
                     "border:1px solid #222244;")

        lbl.setStyleSheet(
            f"font-size:10px;font-weight:bold;border-radius:3px;"
            f"padding:1px 3px;{style}")