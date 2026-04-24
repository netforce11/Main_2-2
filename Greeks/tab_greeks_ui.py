"""
tab_greeks_ui.py — GreeksGrid UI 빌더  S12
══════════════════════════════════════════
build_ctrl()        → 상단 컨트롤 바 (심볼/만기/조회/저장로그/신호등)
build_replay_bar()  → 실시간·리플레이 전환 바
"""
from __future__ import annotations
import os
import sys
import subprocess
from datetime import date

from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import (QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                              QComboBox, QSlider, QLineEdit, QWidget,
                              QSplitter, QTableWidget, QStackedWidget)

import greeks_db as gdb
from greeks_render        import init_table
from greeks_chart         import GexSkewPanel, NormalBandPanel
from greeks_replay        import ReplayPanel
from core import SYMBOL_CFG
from tab_greeks_status import build_status_panel

def build_ctrl(host) -> QHBoxLayout:
    """상단 컨트롤 바를 빌드하여 host 에 위젯 레퍼런스를 주입."""
    hb = QHBoxLayout()

    host._sym_cb = QComboBox()
    host._sym_cb.addItems(list(SYMBOL_CFG.keys()))
    host._sym_cb.setCurrentText("SPX")
    host._sym_cb.currentTextChanged.connect(host._on_sym_changed)

    host._exp_cb = QComboBox(); host._exp_cb.setMinimumWidth(110)
    host._exp_cb.currentIndexChanged.connect(host._on_expiry_changed)

    host._exp_edit = QLineEdit(); host._exp_edit.setPlaceholderText("YYYYMMDD")
    host._exp_edit.setMaximumWidth(90); host._exp_edit.setVisible(False)

    btn     = QPushButton("조회");    btn.clicked.connect(host._fetch)
    btn_ref = QPushButton("만기갱신"); btn_ref.clicked.connect(host._refresh_expiry)

    host._delta_sl = QSlider(Qt.Horizontal)
    host._delta_sl.setRange(0, 100)
    host._delta_sl.valueChanged.connect(host._apply_delta_filter)

    hb.addWidget(QLabel("심볼")); hb.addWidget(host._sym_cb)
    hb.addWidget(QLabel("만기")); hb.addWidget(host._exp_cb)
    hb.addWidget(host._exp_edit)
    hb.addWidget(btn); hb.addWidget(btn_ref)
    hb.addWidget(QLabel("Delta 필터")); hb.addWidget(host._delta_sl)
    hb.addStretch()
    hb.addWidget(QLabel(f"저장: {gdb.GREEKS_DIR}"))
    hb.addWidget(build_status_panel(host))

    btn_log = QPushButton("📋 저장 로그")
    btn_log.setToolTip("ChainSaver 30초 통계 로그 파일 열기")
    btn_log.setStyleSheet(
        "background:#1a2a1a;color:#00e676;padding:4px 8px;"
        "font-size:11px;border:1px solid #2a5a2a;border-radius:3px;")
    btn_log.clicked.connect(host._open_chainsaver_log)
    hb.addWidget(btn_log)
    return hb

def build_replay_bar(host) -> QHBoxLayout:
    """실시간·리플레이 전환 바를 빌드하여 host 에 위젯 레퍼런스를 주입."""
    hb = QHBoxLayout()

    host.btn_live = QPushButton("📡 실시간")
    host.btn_live.setCheckable(True); host.btn_live.setChecked(True)
    host.btn_live.setStyleSheet(
        "background:#1a4a1a;color:#00e676;font-weight:bold;padding:4px 10px;")
    host.btn_live.clicked.connect(lambda: host._set_replay_mode(False))

    host.btn_replay_mode = QPushButton("⏮ 리플레이")
    host.btn_replay_mode.setCheckable(True)
    host.btn_replay_mode.setStyleSheet(
        "background:#1a1a4a;color:#aaaaff;font-weight:bold;padding:4px 10px;")
    host.btn_replay_mode.clicked.connect(lambda: host._set_replay_mode(True))

    hb.addWidget(host.btn_live); hb.addWidget(host.btn_replay_mode)
    hb.addWidget(QLabel("  |  날짜:"))

    host.rp_cmb_day = QComboBox(); host.rp_cmb_day.setMinimumWidth(90)
    host.rp_cmb_day.currentTextChanged.connect(host._rp_on_day_changed)
    hb.addWidget(host.rp_cmb_day)

    hb.addWidget(QLabel("만기:"))
    host.rp_cmb_expiry = QComboBox(); host.rp_cmb_expiry.setMinimumWidth(100)
    hb.addWidget(host.rp_cmb_expiry)

    hb.addWidget(QLabel("From:"))
    host.rp_edit_from = QLineEdit(); host.rp_edit_from.setPlaceholderText("HH:MM")
    host.rp_edit_from.setFixedWidth(70); hb.addWidget(host.rp_edit_from)

    hb.addWidget(QLabel("To:"))
    host.rp_edit_to = QLineEdit(); host.rp_edit_to.setPlaceholderText("HH:MM")
    host.rp_edit_to.setFixedWidth(70); hb.addWidget(host.rp_edit_to)

    host.rp_btn_load = QPushButton("불러오기")
    host.rp_btn_load.clicked.connect(host._rp_load)
    hb.addWidget(host.rp_btn_load)

    hb.addWidget(QLabel("  속도:"))
    host.rp_cmb_speed = QComboBox()
    for k in ("x1", "x5", "x10"): host.rp_cmb_speed.addItem(k)
    hb.addWidget(host.rp_cmb_speed)

    host.rp_btn_play = QPushButton("▶ 재생")
    host.rp_btn_play.setStyleSheet("background:#1a5a1a;font-weight:bold;padding:4px 10px;")
    host.rp_btn_play.clicked.connect(host._rp_toggle_play)
    hb.addWidget(host.rp_btn_play)

    host.rp_btn_stop = QPushButton("■ 정지")
    host.rp_btn_stop.clicked.connect(host._rp_stop)
    hb.addWidget(host.rp_btn_stop)

    hb.addWidget(QLabel("  |  저장주기:"))
    host.cmb_save_interval = QComboBox()
    for label, ms in [("1초", 1000), ("3초", 3000), ("5초", 5000),
                      ("10초", 10000), ("30초", 30000)]:
        host.cmb_save_interval.addItem(label, ms)
    host.cmb_save_interval.setCurrentIndex(2)
    host.cmb_save_interval.currentIndexChanged.connect(host._on_save_interval_changed)
    hb.addWidget(host.cmb_save_interval)

    host.rp_lbl_ts = QLabel("-")
    host.rp_lbl_ts.setStyleSheet(
        "color:#ffd700;font-weight:bold;padding:0 8px;border:none;")
    hb.addWidget(host.rp_lbl_ts)
    hb.addStretch()

    # 초기 숨김
    for w in [host.rp_cmb_day, host.rp_cmb_expiry, host.rp_edit_from,
              host.rp_edit_to, host.rp_btn_load, host.rp_cmb_speed,
              host.rp_btn_play, host.rp_btn_stop, host.rp_lbl_ts]:
        w.setVisible(False)
    return hb

def open_chainsaver_log(host):
    """ChainSaver 30초 통계 로그 파일을 OS 기본 뷰어로 열기."""
    sched = None
    try: sched = host._main.tab_callput._saver_scheduler
    except AttributeError: pass
    if sched and hasattr(sched, "log_path_today"):
        path = sched.log_path_today()
    else:
        today = date.today().strftime("%Y%m%d")
        # BUG: 하드코딩된 경로 → gdb.GREEKS_DIR 기반으로 수정
        path  = os.path.join(gdb.GREEKS_DIR, f"chainsaver_{today}.log")
    if not os.path.exists(path):
        try: open(path, "w", encoding="utf-8").close()
        except OSError: pass
    try:
        if sys.platform == "win32": os.startfile(path)
        else: subprocess.Popen(["xdg-open", path])
    except Exception as e:
        import logging; logging.getLogger(__name__).error("로그 파일 열기 실패: %s", e)

def build_main(host, AUTOSAVE_MS, THROTTLE_MS,
               _THROTTLE_AVAILABLE, RenderThrottle=None, ViewportClipper=None):
    """메인 레이아웃 조립 — _build() 대체. host 에 위젯 레퍼런스 주입."""
    root = QVBoxLayout(host)
    root.addLayout(build_ctrl(host))
    root.addLayout(build_replay_bar(host))

    from PyQt5.QtWidgets import QSlider
    host._rp_slider = QSlider(Qt.Horizontal)
    host._rp_slider.setMinimum(0); host._rp_slider.setMaximum(0)
    host._rp_slider.valueChanged.connect(host._rp_on_slider)
    host._rp_slider.setVisible(False)
    root.addWidget(host._rp_slider)

    host._stack = QStackedWidget()
    rt_page = QWidget(); rt_v = QVBoxLayout(rt_page)
    sp = QSplitter(Qt.Horizontal)
    host._table = QTableWidget(); init_table(host._table); sp.addWidget(host._table)
    rsp = QSplitter(Qt.Vertical)
    host._gex  = GexSkewPanel(); host._band = NormalBandPanel()
    rsp.addWidget(host._gex); rsp.addWidget(host._band); sp.addWidget(rsp)
    rt_v.addWidget(sp); host._stack.addWidget(rt_page)

    host._replay_panel = ReplayPanel()
    host._replay_table = host._replay_panel.tbl
    host._replay_gex   = getattr(host._replay_panel, "_gex",  GexSkewPanel())
    host._replay_band  = getattr(host._replay_panel, "_band", NormalBandPanel())
    host._stack.addWidget(host._replay_panel)
    root.addWidget(host._stack)

    host._banner = QLabel("")
    host._banner.setStyleSheet("color:orange;font-weight:bold;")
    root.addWidget(host._banner)

    host._replay_mode    = False; host._replay_frames: dict = {}
    host._replay_ts_list: list = []; host._replay_strikes: list = []
    host._replay_atm     = 0.0;  host._replay_prev: dict = {}
    host._replay_cur     = 0;    host._replay_playing = False
    host._replay_timer   = QTimer(host)
    host._replay_timer.timeout.connect(host._replay_step)

    for ms, slot in [(AUTOSAVE_MS, host._autosave), (60_000, host._update_band)]:
        t = QTimer(host); t.timeout.connect(slot); t.start(ms)

    if _THROTTLE_AVAILABLE and RenderThrottle and ViewportClipper:
        host._render_throttle = RenderThrottle(
            table=host._table, render_fn=host._render_dirty_cells,
            throttle_ms=THROTTLE_MS)
        host._viewport_clip = ViewportClipper(host._table)