"""
combo_ui_spike_tab.py — ⚡ 급변 감시 탭 UI  v1.0
════════════════════════════════════════════════════════
SyntheticStatusPanel 의 5번째 탭.
combo_ui_panel_build.py 에서 addTab() 으로 추가.

구성:
  [설정 행]
    시작: [1112]  종료: [1118]
    간격: [3]초   틱조건: [3]틱  변동조건: [15]%
  [행사가 행]
    풋: [5800] [5795] [5790] [5785]  콜: 입력 (선택)
    ↺ 콜-풋 탭 현재 행사가 자동 채우기
  [버튼]  ▶ 시작  ■ 중지  🗑 로그 지우기  📁 로그 폴더
  [상태 라벨]
  [이벤트 테이블]
    시각 | CP | 행사가 | 이전가 | 현재가 | 틱변동 | 변동% | 기준% | 조건
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame,
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QColor, QBrush, QFont
import os

try:
    from combo_ui_panel_constants import _f, get_tbl_style, _pal
except ImportError:
    from PyQt5.QtGui import QFont as _QFont
    def _f(pt, bold=False):
        f = _QFont(); f.setPointSize(pt)
        if bold: f.setBold(True)
        return f
    def get_tbl_style(): return ""
    def _pal(): return {
        "group_bg": "#0e0e1e", "widget_fg": "#cccccc",
        "pane_bg": "#0a0a18", "pane_border": "#2a2a5a",
    }


# ── 스레드 → 메인 UI 시그널 브릿지 ─────────────────────────────
class _Bridge(QObject):
    status_sig = pyqtSignal(str)
    event_sig  = pyqtSignal(object)   # SpikeEvent


class SpikeMonitorTab(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = _Bridge()
        self._bridge.status_sig.connect(self._on_status)
        self._bridge.event_sig.connect(self._on_event)
        self._build()
        self._wire()

    # ── UI 빌드 ──────────────────────────────────────────────────

    def _build(self) -> None:
        t   = _pal()
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 6)
        root.setSpacing(5)

        # ── 행 1: 시간 설정 ─────────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(self._lbl("시작:", t))
        self._edit_start = self._time_edit("1112")
        r1.addWidget(self._edit_start)
        r1.addWidget(self._lbl("종료:", t))
        self._edit_end = self._time_edit("1118")
        r1.addWidget(self._edit_end)
        r1.addWidget(self._sep_v())
        r1.addWidget(self._lbl("간격:", t))
        self._sb_interval = self._spin(1, 30, 3, "초")
        r1.addWidget(self._sb_interval)
        r1.addStretch()
        root.addLayout(r1)

        # ── 행 2: 조건 설정 ─────────────────────────────────────
        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(self._lbl("틱 조건:", t))
        self._sb_tick = self._spin(1, 50, 3, "틱")
        r2.addWidget(self._sb_tick)
        r2.addWidget(self._lbl("변동 조건:", t))
        self._dsb_pct = self._dspin(1.0, 100.0, 15.0, "%")
        r2.addWidget(self._dsb_pct)
        r2.addWidget(self._lbl("기준 N스냅:", t))
        self._sb_ref = self._spin(1, 20, 5, "회")
        r2.addWidget(self._sb_ref)
        r2.addStretch()
        root.addLayout(r2)

        root.addWidget(self._hline())

        # ── 행 3: 풋 행사가 입력 ────────────────────────────────
        r3 = QHBoxLayout(); r3.setSpacing(6)
        r3.addWidget(self._lbl("PUT 행사가:", t, color="#ff8888"))
        self._put_edits: list[QLineEdit] = []
        for _ in range(4):
            e = self._strike_edit()
            self._put_edits.append(e)
            r3.addWidget(e)
        r3.addStretch()
        root.addLayout(r3)

        # ── 행 4: 콜 행사가 입력 ────────────────────────────────
        r4 = QHBoxLayout(); r4.setSpacing(6)
        r4.addWidget(self._lbl("CALL 행사가:", t, color="#88aaff"))
        self._call_edits: list[QLineEdit] = []
        for _ in range(4):
            e = self._strike_edit()
            self._call_edits.append(e)
            r4.addWidget(e)

        btn_fill = QPushButton("↺ 자동채우기")
        btn_fill.setFixedHeight(24)
        btn_fill.setToolTip("콜-풋 탭 ATM 근접 행사가 자동 입력")
        btn_fill.setStyleSheet(
            f"QPushButton{{background:{t['group_bg']};color:#aaddff;"
            f"border:1px solid #3355aa;border-radius:4px;font-size:11px;"
            f"padding:2px 8px;}}"
            f"QPushButton:hover{{background:#1a2a4a;}}")
        btn_fill.clicked.connect(self._auto_fill_strikes)
        r4.addWidget(btn_fill)
        r4.addStretch()
        root.addLayout(r4)

        root.addWidget(self._hline())

        # ── 행 5: 버튼 + 상태 ───────────────────────────────────
        r5 = QHBoxLayout(); r5.setSpacing(6)

        self._btn_start = QPushButton("▶ 시작")
        self._btn_start.setFixedHeight(28)
        self._btn_start.setCheckable(True)
        self._btn_start.setStyleSheet(self._btn_style(False))
        self._btn_start.clicked.connect(self._on_toggle)
        r5.addWidget(self._btn_start)

        btn_clear = QPushButton("🗑 지우기")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet(
            f"QPushButton{{background:{t['group_bg']};color:#ff6666;"
            f"border:1px solid #5a1a1a;border-radius:4px;font-size:11px;"
            f"padding:2px 8px;}}"
            f"QPushButton:hover{{background:#2a0a0a;}}")
        btn_clear.clicked.connect(self._clear_table)
        r5.addWidget(btn_clear)

        btn_folder = QPushButton("📁 로그 폴더")
        btn_folder.setFixedHeight(28)
        btn_folder.setStyleSheet(
            f"QPushButton{{background:{t['group_bg']};color:#aaaaff;"
            f"border:1px solid #333388;border-radius:4px;font-size:11px;"
            f"padding:2px 8px;}}"
            f"QPushButton:hover{{background:#1a1a3a;}}")
        btn_folder.clicked.connect(self._open_log_folder)
        r5.addWidget(btn_folder)

        self._lbl_status = QLabel("● 비활성")
        self._lbl_status.setStyleSheet(
            "color:#888;font-size:12px;border:none;")
        r5.addWidget(self._lbl_status)
        r5.addStretch()
        root.addLayout(r5)

        # ── 이벤트 테이블 ────────────────────────────────────────
        cols = ["시각(ET)", "CP", "행사가", "이전가($)",
                "현재가($)", "틱변동", "변동%", "기준%", "조건"]
        self._tbl = QTableWidget(0, len(cols))
        self._tbl.setHorizontalHeaderLabels(cols)
        self._tbl.setFont(_f(11))
        self._tbl.horizontalHeader().setFont(_f(10, bold=True))
        self._tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        self._tbl.horizontalHeader().setLastSectionStretch = True
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setStyleSheet(get_tbl_style())
        root.addWidget(self._tbl, 1)

    # ── 토글 ─────────────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        from Sleep_Order.chain_spike_monitor import ChainSpikeMonitor
        mon = ChainSpikeMonitor.get()

        if checked:
            ref = self._find_ref()
            if ref is None:
                self._lbl_status.setText("❌ 콜-풋 탭 연결 필요")
                self._btn_start.setChecked(False); return

            # 행사가 파싱
            def _parse(edits):
                result = []
                for e in edits:
                    txt = e.text().strip()
                    if txt:
                        try: result.append(float(txt))
                        except ValueError: pass
                return result

            put_strikes  = _parse(self._put_edits)
            call_strikes = _parse(self._call_edits)

            if not put_strikes and not call_strikes:
                self._lbl_status.setText("❌ 행사가를 1개 이상 입력하세요")
                self._btn_start.setChecked(False); return

            # 설정 주입
            mon.reconfigure(
                start_hhmm    = self._edit_start.text().strip(),
                end_hhmm      = self._edit_end.text().strip(),
                tick_interval = self._sb_interval.value(),
                min_tick_delta= self._sb_tick.value(),
                min_pct_change= self._dsb_pct.value(),
                ref_pct_window= self._sb_ref.value(),
                strikes_put   = put_strikes,
                strikes_call  = call_strikes,
            )
            started = mon.start(ref)
            if not started:
                self._btn_start.setChecked(False); return
            self._btn_start.setText("■ 중지")
            self._btn_start.setStyleSheet(self._btn_style(True))
        else:
            mon.stop(reason="수동 중지")
            self._btn_start.setText("▶ 시작")
            self._btn_start.setStyleSheet(self._btn_style(False))

    # ── 자동 행사가 채우기 ───────────────────────────────────────

    def _auto_fill_strikes(self) -> None:
        ref = self._find_ref()
        if ref is None: return

        put_strikes  = sorted(
            getattr(ref, '_put_strikes',  []), reverse=True)[:4]
        call_strikes = sorted(
            getattr(ref, '_call_strikes', []))[:4]

        for i, e in enumerate(self._put_edits):
            e.setText(str(int(put_strikes[i]))
                      if i < len(put_strikes) else "")
        for i, e in enumerate(self._call_edits):
            e.setText(str(int(call_strikes[i]))
                      if i < len(call_strikes) else "")

    # ── 이벤트 수신 (메인 스레드) ────────────────────────────────

    def _on_status(self, msg: str) -> None:
        self._lbl_status.setText(msg)
        if msg.startswith("⏹") or msg.startswith("⏰"):
            self._btn_start.setChecked(False)
            self._btn_start.setText("▶ 시작")
            self._btn_start.setStyleSheet(self._btn_style(False))

    def _on_event(self, ev) -> None:
        """SpikeEvent → 테이블 행 추가."""
        t   = _pal()
        row = self._tbl.rowCount()
        self._tbl.insertRow(row)

        # 색상: 하락=파랑, 상승=주황
        is_down = ev.curr < ev.prev
        val_col = "#4499ff" if is_down else "#ff8844"
        trg_col = {"TICK": "#ffdd44",
                   "PCT":  "#ff8844",
                   "BOTH": "#ff4444"}.get(ev.trigger, "#ffffff")
        cp_col  = "#ff8888" if ev.cp == "P" else "#88aaff"

        def _item(txt, color="#dddddd", bold=False):
            it = QTableWidgetItem(str(txt))
            it.setForeground(QBrush(QColor(color)))
            it.setTextAlignment(Qt.AlignCenter)
            if bold:
                f = QFont(); f.setBold(True); it.setFont(f)
            return it

        arrow = "▼" if is_down else "▲"
        self._tbl.setItem(row, 0, _item(ev.time_str))
        self._tbl.setItem(row, 1, _item(ev.cp, cp_col, bold=True))
        self._tbl.setItem(row, 2, _item(int(ev.strike)))
        self._tbl.setItem(row, 3, _item(f"${ev.prev:.2f}"))
        self._tbl.setItem(row, 4, _item(f"${ev.curr:.2f}", val_col, bold=True))
        self._tbl.setItem(row, 5, _item(f"{arrow}{ev.tick_delta}틱", val_col))
        self._tbl.setItem(row, 6, _item(f"{ev.pct_change:+.1f}%", val_col))
        self._tbl.setItem(row, 7, _item(f"{ev.ref_pct:+.1f}%"))
        self._tbl.setItem(row, 8, _item(ev.trigger, trg_col, bold=True))

        self._tbl.scrollToBottom()

    # ── 유틸 ─────────────────────────────────────────────────────

    def _wire(self) -> None:
        from Sleep_Order.chain_spike_monitor import ChainSpikeMonitor
        mon = ChainSpikeMonitor.get()
        mon.on_status = lambda m: self._bridge.status_sig.emit(m)
        mon.on_event  = lambda e: self._bridge.event_sig.emit(e)

    def _find_ref(self):
        """ref 탐색 — strategy_panel / combo_tab / LeftPanelMixin 모두 지원."""
        try:
            # 1) 부모 위젯 트리 탐색
            parent = self.parent()
            while parent is not None:
                # LeftPanelMixin / SleepOrderMixin 직접 상속
                if hasattr(parent, '_sleep_get_chain'):
                    return parent
                # mw.tab_combo 경유
                mw = getattr(parent, 'mw', None)
                if mw:
                    for attr in ('tab_combo', 'combo_tab', 'tab_strategy'):
                        t = getattr(mw, attr, None)
                        if t and hasattr(t, '_sleep_get_chain'):
                            return t
                    # mw 자신이 _chain_put/_chain_call 보유 시
                    if hasattr(mw, '_chain_put'):
                        return mw
                parent = parent.parent() if callable(
                    getattr(parent, 'parent', None)) else None
        except Exception:
            pass
        # 2) strategy_panel 자신이 _chain_put 보유하는 경우
        try:
            p = self.parent()
            while p is not None:
                if hasattr(p, '_chain_put') or hasattr(p, 'tbl_chain_put'):
                    return p
                p = p.parent() if callable(getattr(p, 'parent', None)) else None
        except Exception:
            pass
        return None

    def _clear_table(self) -> None:
        self._tbl.setRowCount(0)

    def _open_log_folder(self) -> None:
        from Sleep_Order.chain_spike_monitor import ChainSpikeMonitor
        path = ChainSpikeMonitor.get().log_dir
        os.makedirs(path, exist_ok=True)
        try:
            from PyQt5.QtGui import QDesktopServices
            from PyQt5.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass

    # ── 위젯 헬퍼 ────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str, t: dict, color: str = "") -> QLabel:
        lbl = QLabel(text)
        col = color or t.get("widget_fg", "#cccccc")
        lbl.setStyleSheet(
            f"color:{col};font-size:12px;border:none;")
        return lbl

    @staticmethod
    def _time_edit(default: str) -> QLineEdit:
        e = QLineEdit(default)
        e.setFixedWidth(52)
        e.setFixedHeight(24)
        e.setMaxLength(4)
        e.setPlaceholderText("HHMM")
        e.setStyleSheet(
            "background:#0e0e24;color:#ffd700;"
            "border:1px solid #333388;border-radius:3px;"
            "font-size:13px;font-weight:bold;padding:1px 4px;")
        return e

    @staticmethod
    def _strike_edit() -> QLineEdit:
        e = QLineEdit()
        e.setFixedWidth(54)
        e.setFixedHeight(24)
        e.setPlaceholderText("행사가")
        e.setStyleSheet(
            "background:#0e0e1e;color:#eeeeee;"
            "border:1px solid #333355;border-radius:3px;"
            "font-size:12px;padding:1px 3px;")
        return e

    @staticmethod
    def _spin(mn, mx, val, suffix="") -> QSpinBox:
        s = QSpinBox()
        s.setRange(mn, mx); s.setValue(val)
        s.setSuffix(" " + suffix if suffix else "")
        s.setFixedHeight(24); s.setFixedWidth(70)
        s.setStyleSheet(
            "background:#0e0e24;color:#ccccff;"
            "border:1px solid #333388;border-radius:3px;"
            "font-size:12px;")
        return s

    @staticmethod
    def _dspin(mn, mx, val, suffix="") -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(mn, mx); s.setValue(val)
        s.setDecimals(1)
        s.setSuffix(" " + suffix if suffix else "")
        s.setFixedHeight(24); s.setFixedWidth(74)
        s.setStyleSheet(
            "background:#0e0e24;color:#ccccff;"
            "border:1px solid #333388;border-radius:3px;"
            "font-size:12px;")
        return s

    @staticmethod
    def _btn_style(active: bool) -> str:
        if active:
            return ("QPushButton{background:#1a0a0a;color:#ff4444;"
                    "border:2px solid #ff4444;border-radius:5px;"
                    "font-size:12px;font-weight:bold;padding:3px 10px;}"
                    "QPushButton:hover{background:#3a0a0a;}")
        return ("QPushButton{background:#0a1a0a;color:#44cc44;"
                "border:1px solid #2a6a2a;border-radius:5px;"
                "font-size:12px;font-weight:bold;padding:3px 10px;}"
                "QPushButton:hover{background:#0a2a0a;}")

    @staticmethod
    def _hline() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setFixedHeight(1)
        f.setStyleSheet("background:#1e1e3a;border:none;")
        return f

    @staticmethod
    def _sep_v() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.VLine)
        f.setFixedWidth(1)
        f.setStyleSheet("background:#2a2a5a;border:none;")
        return f
