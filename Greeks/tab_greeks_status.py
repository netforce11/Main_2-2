"""
tab_greeks_status.py — 신호등 상태 패널 (빌드 + 헬퍼)  S12
════════════════════════════════════════════════════════
_build_status_panel(), _blink_tick(), _status_saving/done/idle/offhour/req_count

BUG-4 수정: _status_done 에서 모든 슬롯 완료 시 blink 타이머 정지
"""
from __future__ import annotations
from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import QFrame, QGridLayout, QLabel


_BLINK_ATTRS = ("_blink_0dte", "_blink_1dte", "_blink_2dte")
_SLOT_NAMES  = ("당일 만기", "+1DTE", "D+2")

_L_GREY  = ("border-radius:6px;min-width:12px;max-width:12px;"
            "min-height:12px;max-height:12px;background:#2a2a2a;")
_L_GREEN = ("border-radius:6px;min-width:12px;max-width:12px;"
            "min-height:12px;max-height:12px;background:#00e676;")
_L_DIM   = ("border-radius:6px;min-width:12px;max-width:12px;"
            "min-height:12px;max-height:12px;background:#005522;")


def _make_light(parent=None):
    lbl = QLabel(parent)
    lbl.setFixedSize(12, 12)
    lbl.setStyleSheet(_L_GREY)
    return lbl


def _make_txt(text: str, color: str = "#888888", parent=None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"color:{color};font-size:10px;font-weight:bold;"
        "background:transparent;border:none;padding:0;")
    return lbl


def build_status_panel(host) -> QFrame:
    """
    신호등 패널을 생성하고 host(GreeksGrid) 에 위젯 레퍼런스를 주입.
    반환값: QFrame (ctrl 바에 addWidget 용)
    """
    panel = QFrame()
    panel.setStyleSheet(
        "QFrame{background:#0d1117;border:1px solid #2a3a2a;"
        "border-radius:4px;padding:2px;}")
    panel.setFixedHeight(56)

    grid = QGridLayout(panel)
    grid.setContentsMargins(6, 2, 6, 2)
    grid.setHorizontalSpacing(4)
    grid.setVerticalSpacing(1)

    # ── 신호등 3행 ──────────────────────────────────────────
    for row, (attr_l, attr_lbl, attr_cnt, name) in enumerate([
        ("_sl_0dte", "_sl_0dte_lbl", "_sl_0dte_cnt", "당일 만기 — 대기"),
        ("_sl_1dte", "_sl_1dte_lbl", "_sl_1dte_cnt", "+1DTE — 대기"),
        ("_sl_2dte", "_sl_2dte_lbl", "_sl_2dte_cnt", "D+2 — 대기"),
    ]):
        light = _make_light(); lbl = _make_txt(name); cnt = _make_txt("0건", "#555555")
        setattr(host, attr_l, light)
        setattr(host, attr_lbl, lbl)
        setattr(host, attr_cnt, cnt)
        grid.addWidget(light, row, 0, Qt.AlignCenter)
        grid.addWidget(lbl,   row, 1)
        grid.addWidget(cnt,   row, 2)

    # ── 세로 구분선 + 총 요청 수 ────────────────────────────
    sep = QFrame(); sep.setFrameShape(QFrame.VLine)
    sep.setStyleSheet("color:#2a4a2a;")
    grid.addWidget(sep, 0, 3, 3, 1)

    req_title = _make_txt("요청", "#aaaaaa"); req_title.setAlignment(Qt.AlignCenter)
    host._sl_req_total = QLabel("0")
    host._sl_req_total.setStyleSheet(
        "color:#ffd700;font-size:14px;font-weight:bold;"
        "background:transparent;border:none;padding:0;")
    host._sl_req_total.setAlignment(Qt.AlignCenter)
    req_unit = _make_txt("건", "#888888"); req_unit.setAlignment(Qt.AlignCenter)
    grid.addWidget(req_title,          0, 4, Qt.AlignCenter)
    grid.addWidget(host._sl_req_total, 1, 4, Qt.AlignCenter)
    grid.addWidget(req_unit,           2, 4, Qt.AlignCenter)

    # ── 장외 경고 ───────────────────────────────────────────
    host._sl_offhour = _make_txt("⛔ 장외시간", "#ff5555")
    host._sl_offhour.setVisible(False)
    grid.addWidget(host._sl_offhour, 0, 5, 3, 1, Qt.AlignCenter)

    # ── 점멸 타이머 ─────────────────────────────────────────
    host._blink_state = False
    host._blink_0dte = host._blink_1dte = host._blink_2dte = False
    host._blink_timer = QTimer(host)
    host._blink_timer.setInterval(600)
    host._blink_timer.timeout.connect(host._blink_tick)

    return panel


# ── 신호등 헬퍼 메서드 (GreeksGrid 에 mixin 형태로 주입) ──────

def blink_tick(self):
    self._blink_state = not self._blink_state
    for light, active in [
            (self._sl_0dte, self._blink_0dte),
            (self._sl_1dte, self._blink_1dte),
            (self._sl_2dte, self._blink_2dte)]:
        if active:
            light.setStyleSheet(_L_GREEN if self._blink_state else _L_DIM)


def status_saving(self, slot: int, count: int, label: str):
    """저장 중 — 녹색 점멸 시작."""
    lights = (self._sl_0dte, self._sl_1dte, self._sl_2dte)
    lbls   = (self._sl_0dte_lbl, self._sl_1dte_lbl, self._sl_2dte_lbl)
    cnts   = (self._sl_0dte_cnt, self._sl_1dte_cnt, self._sl_2dte_cnt)
    setattr(self, _BLINK_ATTRS[slot], True)
    lights[slot].setStyleSheet(_L_GREEN)
    lbls[slot].setText(label)
    lbls[slot].setStyleSheet(
        "color:#00e676;font-size:10px;font-weight:bold;"
        "background:transparent;border:none;padding:0;")
    cnts[slot].setText(f"{count}건")
    cnts[slot].setStyleSheet(
        "color:#00e676;font-size:10px;background:transparent;border:none;padding:0;")
    if not self._blink_timer.isActive():
        self._blink_timer.start()


def status_done(self, slot: int, count: int, label: str):
    """저장 완료 — 고정 녹색 + BUG-4 수정: 전체 완료 시 타이머 정지."""
    lights = (self._sl_0dte, self._sl_1dte, self._sl_2dte)
    lbls   = (self._sl_0dte_lbl, self._sl_1dte_lbl, self._sl_2dte_lbl)
    cnts   = (self._sl_0dte_cnt, self._sl_1dte_cnt, self._sl_2dte_cnt)
    setattr(self, _BLINK_ATTRS[slot], False)
    lights[slot].setStyleSheet(_L_GREEN)
    lbls[slot].setText(label)
    lbls[slot].setStyleSheet(
        "color:#aaffaa;font-size:10px;font-weight:bold;"
        "background:transparent;border:none;padding:0;")
    cnts[slot].setText(f"{count}건 ✓")
    cnts[slot].setStyleSheet(
        "color:#aaffaa;font-size:10px;background:transparent;border:none;padding:0;")
    # BUG-4: 모든 슬롯 완료 시 타이머 정지
    if not any([self._blink_0dte, self._blink_1dte, self._blink_2dte]):
        self._blink_timer.stop()


def status_idle(self, slot: int, reason: str = "대기"):
    """회색 — 비활성."""
    lights = (self._sl_0dte, self._sl_1dte, self._sl_2dte)
    lbls   = (self._sl_0dte_lbl, self._sl_1dte_lbl, self._sl_2dte_lbl)
    cnts   = (self._sl_0dte_cnt, self._sl_1dte_cnt, self._sl_2dte_cnt)
    setattr(self, _BLINK_ATTRS[slot], False)
    lights[slot].setStyleSheet(_L_GREY)
    lbls[slot].setText(f"{_SLOT_NAMES[slot]} — {reason}")
    lbls[slot].setStyleSheet(
        "color:#888888;font-size:10px;font-weight:bold;"
        "background:transparent;border:none;padding:0;")
    cnts[slot].setText("0건")
    cnts[slot].setStyleSheet(
        "color:#555555;font-size:10px;background:transparent;border:none;padding:0;")
    if not any([self._blink_0dte, self._blink_1dte, self._blink_2dte]):
        self._blink_timer.stop()


def status_offhour(self, is_offhour: bool):
    self._sl_offhour.setVisible(is_offhour)


def status_req_count(self, total: int):
    self._sl_req_total.setText(str(total))


def on_snap_status(self, slot: int, event: str, count: int, label: str):
    """SnapshotManager → 신호등 연결 콜백."""
    if event == "saving":
        self._status_saving(slot, count, label)
    elif event == "done":
        self._status_done(slot, count, label)
    # queue_done 은 pass (record_received 에서 done 처리됨)
