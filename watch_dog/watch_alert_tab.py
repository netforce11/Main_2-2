"""
watch_alert_tab.py — SPX 감시 패널 (항상 위, 좌측 하단 고정)
- 조건A: 두 행 독립, 각각 방향 선택 (상승/하락/양방향), N분 전 대비
- 조건B: 최대 5개 행사가 (콜-풋 탭 클릭 → 자동 추가)
- 조건C: VIX 급등 감시
- 신호등: 감시중(초록) / 정지(회색) / 알람(빨강)
- 알람 횟수 표시 / 억제 조건 개별 해제 / 로그 확인 버튼
- X 버튼 → hide() (종료 아님)

[수정 내역]
1. _on_tick() 구현:
   - und_saver.get_context() 로 N분 전 SPX 가격 조회 → push_spx() 호출
   - 조건A 두 행의 minutes 값을 각각 독립으로 조회 (10/20/30/40분 모두 지원)
   - VIX 데이터 연동 (mw 참조 경로)
2. 타이머 간격 60s → 58s (COOLDOWN_SEC=55 과 여유 확보)
3. 기준%/방향 변경 시 기존 등록 행사가 전체 갱신 (_on_pct_dir_changed)
4. 억제 조건 개별 해제 버튼 추가 (_make_suppress_bar)
5. add_strike_from_chain(): 추가 시 현재 UI 값 반영 확인 토스트 메시지
6. mw(메인윈도우) 참조 주입: set_main_window()

[v7 수정]
7. ✅ 조건B ATM 자동 탐색 (_auto_add_atm_strike / _find_atm_by_premium):
   - 목표 프리미엄(기본 $2.0) ± 허용오차%(기본 25%) 범위의 행사가 자동 탐색
   - mw.call_data / put_data 캐시에서 mid=(bid+ask)/2 또는 last 로 필터
   - P / C / both 선택 가능, target 에 가까운 순 등록
   - 이미 등록된 행사가 중복 스킵
8. ✅ 주기적 heartbeat 알림 제거 (_check_session_auto else 브랜치):
   - 상태 유지 중 1분마다 보내던 텔레그램/로그 완전 제거
   - 알람은 오직 AlertEngine → _on_alert 경로(조건 성립 시)에서만 발화
"""

import os, sys, subprocess
from pathlib import Path
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit,
    QListWidget, QListWidgetItem, QGroupBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

_WATCH_DOG_DIR = str(Path(__file__).resolve().parent)
if _WATCH_DOG_DIR not in sys.path:
    sys.path.insert(0, _WATCH_DOG_DIR)

from alert_engine   import AlertEngine, CondARow
from alert_notifier import AlertNotifier, LEVEL_COLORS
from alert_logger   import AlertLogger


# ─────────────────────────────────────────────────────────
#  감시 패널 메인 위젯
# ─────────────────────────────────────────────────────────

class WatchAlertPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SPX 감시 패널")
        # ✅ FIX: 기본 닫기/최소화 버튼 숨기고 커스텀 타이틀바 사용
        self.setWindowFlags(
            Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setFixedWidth(560)
        # 드래그 이동용 변수
        self._drag_pos = None

        # ✅ NEW: 메인윈도우 참조 (나중에 set_main_window()로 주입)
        self._mw = None

        # 의존성 초기화
        self._logger   = AlertLogger()
        self._notifier = AlertNotifier()
        self._engine   = AlertEngine(on_alert=self._on_alert)
        self._notifier.set_ui_callback(self._on_alert_ui)

        self._alert_total = 0

        # ✅ NEW: 새벽 알림 발동 체커
        try:
            from night_alert_checker import NightAlertChecker
            self._night_checker = NightAlertChecker(log_fn=self._log_deferred)
        except Exception as e:
            self._night_checker = None
            print(f"[WatchAlertPanel] NightAlertChecker 로드 실패: {e}")

        self._build_ui()
        # ── 자동 세션 감시 타이머 (1분 주기) ────────────
        from PyQt5.QtCore import QTimer
        self._auto_session_timer = QTimer(self)
        self._auto_session_timer.setInterval(60_000)
        self._auto_session_timer.timeout.connect(self._check_session_auto)
        self._auto_session_timer.start()
        self._session_was_open = False
        self._position_bottom_left()

        # ✅ FIX: 타이머 58초 (COOLDOWN_SEC=55 과 여유 확보)
        self._timer = QTimer(self)
        self._timer.setInterval(58_000)
        self._timer.timeout.connect(self._on_tick)

        # ✅ NEW: 새벽알림 독립 타이머 — 감시 ON/OFF 무관, 패널 열리면 항상 작동
        self._night_timer = QTimer(self)
        self._night_timer.setInterval(60_000)
        self._night_timer.timeout.connect(self._on_night_tick)
        self._night_timer.start()
        self._log_deferred("🌙 새벽알림 타이머 시작 (감시 독립)")

    # ── 메인윈도우 주입 ────────────────────────────────────

    def set_main_window(self, mw):
        """
        ✅ NEW: 메인윈도우 참조 주입.
        und_saver / VIX 데이터 접근에 사용.
        사용 예) panel.set_main_window(self)
        """
        self._mw = mw
        # ✅ NEW: NightAlertChecker 에도 mw 주입
        if self._night_checker is not None:
            self._night_checker.set_main_window(mw)
        # ✅ NEW: NightAlertTab 에도 mw 주입 (프리미엄 탐색용)
        nt = getattr(self, "_night_alert_tab", None)
        if nt is not None:
            nt.set_main_window(mw)

    # ── UI 구성 ────────────────────────────────────────────

    def _build_ui(self):
        from PyQt5.QtWidgets import QTabWidget
        # ✅ 프레임리스 전체 배경 + 테두리
        self.setStyleSheet(
            "WatchAlertPanel{background:#1e1e1e;border:1px solid #555;border-radius:4px;}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 6)
        root.setSpacing(0)

        # ── 커스텀 타이틀바 래퍼 ──────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet(
            "background:#2d2d2d;border-bottom:1px solid #555;"
            "border-top-left-radius:4px;border-top-right-radius:4px;"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(6, 0, 4, 0)
        # _make_header() 반환값(QHBoxLayout)의 아이템들을 title_bar 레이아웃에 옮기기
        hdr = self._make_header()
        while hdr.count():
            item = hdr.takeAt(0)
            if item.widget():
                tb_layout.addWidget(item.widget())
            elif item.spacerItem():
                tb_layout.addStretch()
        root.addWidget(title_bar)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(6, 4, 6, 0)
        inner_layout.setSpacing(4)
        tabs = QTabWidget()
        spx_w = QWidget()
        vb = QVBoxLayout(spx_w)
        vb.setContentsMargins(0,0,0,0); vb.setSpacing(4)
        vb.addWidget(self._make_cond_a_box())
        vb.addWidget(self._make_cond_b_box())
        vb.addLayout(self._make_control_bar())
        vb.addLayout(self._make_suppress_bar())
        vb.addWidget(self._make_log_box())
        tabs.addTab(spx_w, '📡 SPX감시')
        try:
            import sys, os
            _wd = os.path.dirname(__file__)
            if _wd not in sys.path: sys.path.insert(0, _wd)
            from night_alert_tab import NightAlertTab
            self._night_alert_tab = NightAlertTab()
            if self._night_checker is not None:
                self._night_alert_tab.set_checker(self._night_checker)
            # mw 가 이미 주입된 경우 NightAlertTab 에도 즉시 전달
            if self._mw is not None:
                self._night_alert_tab.set_main_window(self._mw)
            tabs.addTab(self._night_alert_tab, '🌙 새벽알림')
            print('[WatchAlertPanel] 새벽알림 탭 추가 완료')
        except Exception as e:
            import traceback; traceback.print_exc()
        inner_layout.addWidget(tabs)
        root.addWidget(inner)
    def _make_header(self) -> QHBoxLayout:
        # ✅ FIX: 커스텀 타이틀바 — 드래그 가능 + HIDE/X 버튼
        hb = QHBoxLayout()

        # 타이틀바 드래그용 레이블
        title = QLabel("🔍 SPX 감시")
        title.setFont(QFont("Arial", 10, QFont.Bold))
        title.setStyleSheet("color:#ddd;")
        # 드래그 이벤트는 위젯 레벨에서 처리
        hb.addWidget(title)
        hb.addStretch()

        self._light = QLabel("●")
        self._light.setStyleSheet("color: #888; font-size: 18px;")
        hb.addWidget(self._light)

        self._cnt_label = QLabel("알람 0회")
        self._cnt_label.setStyleSheet("color: #aaa; font-size: 10px;")
        hb.addWidget(self._cnt_label)

        # ✅ HIDE 버튼 (숨기기 — tray/호출로 복원 가능)
        _BTN_SS = (
            "QPushButton{font-size:11px;font-weight:bold;padding:0 4px;"
            "background:#2a2a2a;color:#ccc;border:1px solid #555;border-radius:3px;}"
            "QPushButton:hover{background:#444;color:#fff;}"
        )
        btn_hide = QPushButton("▁")
        btn_hide.setFixedSize(24, 20)
        btn_hide.setToolTip("숨기기 (패널 닫기 — 감시는 계속 실행)\n다시 표시: 메인 메뉴 또는 tray 아이콘 클릭")
        btn_hide.setStyleSheet(_BTN_SS)
        btn_hide.clicked.connect(self.hide)
        hb.addWidget(btn_hide)

        # ✅ X 버튼 (hide — 프로세스 종료 아님)
        btn_x = QPushButton("✕")
        btn_x.setFixedSize(24, 20)
        btn_x.setToolTip("창 닫기 (감시는 계속 실행)\n다시 표시: 메인 메뉴 또는 tray 아이콘 클릭")
        btn_x.setStyleSheet(
            "QPushButton{font-size:11px;font-weight:bold;padding:0;"
            "background:#2a2a2a;color:#ccc;border:1px solid #555;border-radius:3px;}"
            "QPushButton:hover{background:#c0392b;color:#fff;}"
        )
        btn_x.clicked.connect(self.hide)
        hb.addWidget(btn_x)
        return hb

    # ✅ 커스텀 타이틀바 드래그 이동
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _make_cond_a_box(self) -> QGroupBox:
        box = QGroupBox("조건A — SPX 등락 (N분 전 대비)")
        vb  = QVBoxLayout(box)
        self._cond_a_rows: list[dict] = []
        for i in range(2):
            row = self._make_cond_a_row(i)
            vb.addLayout(row["layout"])
            self._cond_a_rows.append(row)
        return box

    def _make_cond_a_row(self, idx: int) -> dict:
        hb  = QHBoxLayout()
        lbl = QLabel(f"A{idx+1}")
        lbl.setFixedWidth(22)

        min_sp = QSpinBox()
        min_sp.setRange(1, 60)
        # ✅ 기본값: 행1=5분, 행2=20분 (일반적 사용 패턴)
        min_sp.setValue(5 if idx == 0 else 20)
        min_sp.setSuffix("분")
        min_sp.setFixedWidth(62)

        pt_sp = QDoubleSpinBox()
        pt_sp.setRange(0.1, 999)
        pt_sp.setValue(5.0)
        pt_sp.setSuffix("pt")
        pt_sp.setFixedWidth(72)

        dir_cb = QComboBox()
        dir_cb.addItems(["하락", "상승", "양방향"])
        dir_cb.setFixedWidth(72)

        hb.addWidget(lbl)
        hb.addWidget(min_sp)
        hb.addWidget(pt_sp)
        hb.addWidget(dir_cb)
        hb.addStretch()
        return {"layout": hb, "min": min_sp, "pt": pt_sp, "dir": dir_cb}

    def _make_cond_b_box(self) -> QGroupBox:
        box = QGroupBox("조건B — 옵션 등락 (행사가 최대 5개)")
        vb  = QVBoxLayout(box)

        self._strike_list = QListWidget()
        self._strike_list.setMaximumHeight(90)
        self._strike_list.setToolTip("콜-풋 탭에서 행사가 클릭 시 자동 추가")

        btn_rm = QPushButton("선택 제거")
        btn_rm.setFixedHeight(22)
        btn_rm.clicked.connect(self._remove_selected_strike)

        pct_hb = QHBoxLayout()
        pct_hb.addWidget(QLabel("기준%:"))
        self._pct_sp = QDoubleSpinBox()
        self._pct_sp.setRange(10, 9999)
        self._pct_sp.setValue(500)
        self._pct_sp.setSuffix("%")
        self._pct_sp.setFixedWidth(80)

        self._dir_b = QComboBox()
        self._dir_b.addItems(["양방향", "상승", "하락"])

        # ✅ FIX: 기준%/방향 변경 시 기존 등록 항목에도 즉시 반영
        self._pct_sp.valueChanged.connect(self._on_pct_dir_changed)
        self._dir_b.currentIndexChanged.connect(self._on_pct_dir_changed)

        pct_hb.addWidget(self._pct_sp)
        pct_hb.addWidget(self._dir_b)
        pct_hb.addStretch()

        vb.addWidget(self._strike_list)
        vb.addWidget(btn_rm)
        vb.addLayout(pct_hb)
        return box

    def _make_control_bar(self) -> QHBoxLayout:
        hb = QHBoxLayout()
        self._btn_start = QPushButton("▶ 감시 시작")
        self._btn_stop  = QPushButton("■ 중지")
        btn_log         = QPushButton("📂 로그")
        self._btn_stop.setEnabled(False)

        self._btn_start.clicked.connect(self._start)
        self._btn_stop.clicked.connect(self._stop)
        btn_log.clicked.connect(self._open_log)

        for b in (self._btn_start, self._btn_stop, btn_log):
            b.setFixedHeight(26)
            hb.addWidget(b)
        return hb

    def _make_suppress_bar(self) -> QHBoxLayout:
        """✅ NEW: 억제 조건 개별 해제 버튼 바"""
        hb = QHBoxLayout()
        lbl = QLabel("억제 해제:")
        lbl.setStyleSheet("color: #aaa; font-size: 10px;")
        lbl.setFixedWidth(55)

        btn_a1 = QPushButton("A1")
        btn_a2 = QPushButton("A2")
        btn_b  = QPushButton("조건B 전체")
        btn_c  = QPushButton("VIX")

        btn_a1.setFixedHeight(20)
        btn_a2.setFixedHeight(20)
        btn_b.setFixedHeight(20)
        btn_c.setFixedHeight(20)

        btn_a1.setToolTip("조건A 1행 억제 해제")
        btn_a2.setToolTip("조건A 2행 억제 해제")
        btn_b.setToolTip("조건B 모든 행사가 억제 해제")
        btn_c.setToolTip("조건C(VIX) 억제 해제")

        btn_a1.clicked.connect(lambda: self._reset_suppress("A0"))
        btn_a2.clicked.connect(lambda: self._reset_suppress("A1"))
        btn_b.clicked.connect(self._reset_suppress_b)
        btn_c.clicked.connect(lambda: self._reset_suppress("C"))

        for b in (btn_a1, btn_a2, btn_b, btn_c):
            b.setStyleSheet("font-size: 10px; padding: 0 4px;")
            hb.addWidget(b)

        hb.insertWidget(0, lbl)
        return hb

    def _make_log_box(self) -> QTextEdit:
        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setMaximumHeight(120)
        self._log_box.setStyleSheet("background:#1a1a1a; color:#ddd; font-size:10px;")
        return self._log_box

    # ── 제어 ──────────────────────────────────────────────

    def _check_session_auto(self):
        """1분마다 야간세션 여부 체크 → 자동 시작/종료."""
        try:
            from datetime import datetime
            from spxw_core import _session_bounds
            now = datetime.now()
            start_hm, end_hm = _session_bounds(now.strftime("%Y%m%d"))
            sh, sm = map(int, start_hm.split(":"))
            eh, em = map(int, end_hm.split(":"))
            t = now.hour * 60 + now.minute
            s = sh * 60 + sm
            e = eh * 60 + em
            # 야간세션: 시작~자정 or 자정~종료
            if s > e:  # 예: 22:30~05:00
                in_session = (t >= s) or (t <= e)
            else:
                in_session = s <= t <= e
        except Exception:
            in_session = False

        from datetime import datetime
        now_str = datetime.now().strftime("%H:%M")
        if in_session and not self._session_was_open:
            self._session_was_open = True
            if not self._engine.is_running():
                self._start()
                self._log(f"🟢 [{now_str}] 야간세션 시작 — 감시 자동 시작")
                self._try_snapshot_base_price()
        elif not in_session and self._session_was_open:
            self._session_was_open = False
            if self._engine.is_running():
                self._stop()
                self._log(f"🔴 [{now_str}] 야간세션 종료 — 감시 자동 종료")
        else:
            # ✅ FIX: 상태 유지 중에는 조용히 대기 — 주기적 heartbeat 알림 제거
            # (알람은 조건 성립 시에만 AlertEngine → _on_alert 경로로 발화)
            pass

    def _try_snapshot_base_price(self):
        """22:30 시가 기준 ATM 프리미엄 스냅샷 저장."""
        try:
            import sys, os
            _wd = os.path.dirname(__file__)
            if _wd not in sys.path:
                sys.path.insert(0, _wd)
            from night_alert_template import load_config, save_config
            cfg = load_config()
            if cfg.snapshot_done:
                return
            mw = self._mw
            if mw is None:
                return
            und = getattr(mw, "und_price", None)
            if not und:
                return
            # ATM 행사가 결정
            atm = round(und / 5) * 5 if cfg.atm_auto else cfg.atm_manual
            # 콜-풋탭 프리미엄 캐시에서 조회
            chain_put = getattr(mw, "_chain_put", None) or getattr(mw, "chain_put", None)
            if chain_put and atm in chain_put:
                base = chain_put[atm]
                cfg.snapshot_done = True
                cfg.snapshot_time = __import__("datetime").datetime.now().strftime("%H:%M")
                cfg.atm_manual    = atm
                save_config(cfg)
                self._log(f"📸 기준가 스냅샷: ATM={atm} P=${base:.2f} @ {cfg.snapshot_time}")
                # NightAlertTab 에 기준가 전달
                nt = getattr(self, "_night_alert_tab", None)
                if nt:
                    nt._base_price = base
                    nt._base_atm   = atm
        except Exception as e:
            self._log(f"⚠ 스냅샷 실패: {e}")

    def _start(self):
        self._apply_cond_a()
        self._engine.reset_counts()
        self._alert_total = 0
        self._cnt_label.setText("알람 0회")
        self._engine.start()
        self._timer.start()
        self._set_light("green")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._log("🟢 감시 시작")

    def _stop(self):
        self._engine.stop()
        self._timer.stop()
        self._set_light("gray")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._log("⬛ 감시 중지")

    def _apply_cond_a(self):
        for idx, row in enumerate(self._cond_a_rows):
            self._engine.cond_a[idx] = CondARow(
                minutes   = row["min"].value(),
                points    = row["pt"].value(),
                direction = row["dir"].currentText(),
                enabled   = True,
            )

    # ── 억제 해제 ─────────────────────────────────────────

    def _reset_suppress(self, key: str):
        """✅ NEW: 특정 조건 억제 해제"""
        self._engine.reset_count_for(key)
        self._log(f"🔓 억제 해제: {key}")

    def _reset_suppress_b(self):
        """✅ NEW: 조건B 전체 행사가 억제 해제"""
        for b in self._engine.cond_b:
            key = f"B{b.strike}{b.opt_type}"
            self._engine.reset_count_for(key)
        self._log("🔓 조건B 억제 전체 해제")

    # ── 행사가 추가/변경 (외부 콜-풋 탭에서 호출) ──────────

    def add_strike_from_chain(self, strike: float, opt_type: str):
        """콜-풋 탭 클릭 시 외부에서 호출"""
        pct       = self._pct_sp.value()
        direction = self._dir_b.currentText()
        added     = self._engine.add_strike(strike, opt_type, pct, direction)
        if added:
            label = f"{opt_type}  {strike:.1f}  ±{pct:.0f}%  [{direction}]"
            item  = QListWidgetItem(label)
            item.setData(Qt.UserRole, (strike, opt_type))
            self._strike_list.addItem(item)
            self._log(f"✅ 조건B 추가: {opt_type} {strike:.1f}")
        else:
            self._log(f"⚠ 최대 5개 / 중복: {opt_type} {strike}")

    def _remove_selected_strike(self):
        item = self._strike_list.currentItem()
        if not item:
            return
        strike, opt_type = item.data(Qt.UserRole)
        self._engine.remove_strike(strike, opt_type)
        self._strike_list.takeItem(self._strike_list.row(item))
        self._log(f"🗑 조건B 제거: {opt_type} {strike:.1f}")

    def _on_pct_dir_changed(self):
        """
        ✅ FIX: 기준%/방향 변경 시 이미 등록된 모든 행사가에 즉시 반영.
        리스트 라벨도 갱신.
        """
        pct       = self._pct_sp.value()
        direction = self._dir_b.currentText()
        self._engine.update_all_strikes(pct, direction)

        # 리스트 라벨 갱신
        for i in range(self._strike_list.count()):
            item = self._strike_list.item(i)
            strike, opt_type = item.data(Qt.UserRole)
            item.setText(f"{opt_type}  {strike:.1f}  ±{pct:.0f}%  [{direction}]")

    # ── 알람 수신 ─────────────────────────────────────────

    def _on_alert(self, level: int, msg: str):
        """AlertEngine 콜백 → logger + notifier (단일 경로)"""
        self._logger.write(level, msg)   # 파일 로그
        self._notifier.notify(level, msg) # 소리 + UI 콜백

    def _on_alert_ui(self, level: int, msg: str):
        """AlertNotifier UI 콜백 → 화면 갱신"""
        self._alert_total += 1
        self._cnt_label.setText(f"알람 {self._alert_total}회")
        self._set_light("red")
        color = LEVEL_COLORS.get(level, "#fff")
        ts    = datetime.now().strftime("%H:%M:%S")
        html  = f'<span style="color:{color}">[{ts}] LV{level} {msg}</span>'
        self._log_box.append(html)
        QTimer.singleShot(2000, self._restore_light)

    # ── 핵심: _on_tick 구현 ───────────────────────────────

    def _on_tick(self):
        """
        ✅ FIX: 58초 주기 타이머 콜백.
        조건A 두 행의 N분 전 SPX 가격을 und_saver 에서 조회하여 push_spx() 호출.
        조건C VIX 데이터도 연동.

        연동 전제:
          - mw(메인윈도우)에 und_saver 접근 경로 존재
            예) from trade_log.und_saver import get_context as get_und_context
                또는 mw 가 und_saver 참조를 갖고 있을 때
          - mw.und_price: 현재 SPX 가격 (float | None)
          - mw.vix_price / mw.vix_prev: VIX 현재/이전 가격 (있을 때만 연동)
        """
        if not self._engine.is_running():
            return
        if self._mw is None:
            return

        # ── SPX 현재가 ────────────────────────────────────
        price_now = getattr(self._mw, "und_price", None)
        if price_now is None or price_now <= 0:
            return

        # ── 조건A: 두 행 독립 조회 ───────────────────────
        exec_time = datetime.now()
        try:
            from trade_log.und_saver import get_context as get_und_context
            _get_ctx = get_und_context
        except ImportError:
            # und_saver 미연동 시 조용히 스킵
            _get_ctx = None

        if _get_ctx is not None:
            seen_minutes = set()
            for idx, row_ui in enumerate(self._cond_a_rows):
                minutes = row_ui["min"].value()
                if not self._engine.cond_a[idx].enabled:
                    continue
                if minutes in seen_minutes:
                    # 같은 분 값 중복 조회 방지 (두 행이 동일 분 설정 시)
                    # 단, push_spx 는 두 행 각각 평가하므로 중복 push 는 OK
                    pass
                seen_minutes.add(minutes)

                ctx = _get_ctx(exec_time)
                # get_context 반환 형식: {"m5": price, "m20": price}
                # 또는 직접 minutes 키로 조회 가능한 경우
                price_then = self._get_price_n_min_ago(ctx, minutes, exec_time, _get_ctx)
                if price_then is None:
                    self._log(f"⚠ {minutes}분 전 가격 없음 (버퍼/DB 부족)")
                    continue
                self._engine.push_spx(minutes, price_then, price_now)

        # ── 조건C: VIX 연동 ──────────────────────────────
        vix_now  = getattr(self._mw, "vix_price", None)
        vix_prev = getattr(self._mw, "vix_prev",  None)
        if vix_now and vix_prev and vix_now > 0 and vix_prev > 0:
            self._engine.push_vix(vix_now, vix_prev)

    def _on_night_tick(self):
        """
        ✅ NEW: 새벽알림 독립 타이머 콜백 (60초 주기).
        감시 ON/OFF, 야간세션 여부 무관하게 패널이 열려 있으면 항상 호출.
        샘플링(기준가 수집) + 알림 평가 모두 처리.
        """
        if self._night_checker is None:
            return
        if self._mw is None:
            return
        self._night_checker.tick()

    def _get_price_n_min_ago(self, ctx, minutes: int, exec_time: datetime, get_ctx_fn) -> float | None:
        """
        und_saver.get_context() 반환값에서 N분 전 가격 추출.

        get_context() 시그니처에 따라 두 가지 방식 지원:
          방식1) get_context(exec_time) → {"m5": p, "m20": p} (고정 5/20분만)
          방식2) get_context(exec_time, minutes=N) → float | None  (임의 분 지원)

        und_saver 가 방식2 를 지원하면 10/20/30/40분 전 모두 정확히 조회 가능.
        현재 und_saver 가 방식1 (고정 5/20분)이라면 방식2 로 업그레이드 권장.
        """
        # 방식2 시도: get_context(exec_time, minutes=N) 형식
        try:
            result = get_ctx_fn(exec_time, minutes=minutes)
            if isinstance(result, (int, float)) and result > 0:
                return float(result)
        except TypeError:
            pass

        # 방식1 폴백: {"m5": ..., "m20": ...} 딕셔너리
        if isinstance(ctx, dict):
            key = f"m{minutes}"
            val = ctx.get(key)
            if val and val > 0:
                return float(val)

        return None

    # ── UI 보조 ───────────────────────────────────────────

    def _set_light(self, state: str):
        color = {"green": "#00e676", "red": "#ff1744", "gray": "#888"}.get(state, "#888")
        self._light.setStyleSheet(f"color: {color}; font-size: 18px;")

    def _restore_light(self):
        if self._engine.is_running():
            self._set_light("green")

    def _log_deferred(self, msg: str):
        """build_ui 완료 전에도 안전하게 로그 출력."""
        try:
            self._log(msg)
        except Exception:
            print(f"[WatchAlertPanel] {msg}")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_box.append(f'<span style="color:#aaa">[{ts}] {msg}</span>')

    def _open_log(self):
        path = self._logger.log_path_today()
        if not path.exists():
            path.touch()
        try:
            os.startfile(str(path))
        except Exception:
            subprocess.Popen(["notepad.exe", str(path)])

    def _position_bottom_left(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.left() + 8
        y = screen.bottom() - self.sizeHint().height() - 8
        self.move(x, y)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
