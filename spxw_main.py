# -*- coding: utf-8 -*-
"""
spxw_main.py — 실행 진입점
실행: python spxw_main.py
필요 패키지: pip install PyQt5 matplotlib requests pytz numpy openpyxl
"""
from __future__ import annotations

import sys
import os
import traceback
import datetime
import threading

# ── 에러 로그 파일 ──────────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error_log.txt")

def _log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def _global_exc_hook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _log(f"[UNCAUGHT EXCEPTION]\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_exc_hook

def _thread_exc_hook(args):
    msg = "".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback))
    _log(f"[THREAD EXCEPTION thread={args.thread}]\n{msg}")

threading.excepthook = _thread_exc_hook
# ────────────────────────────────────────────────────────────────────

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget,
                              QVBoxLayout, QTabWidget, QStatusBar)
from PyQt5.QtCore import Qt

from spxw_core import _load_api_key_from_file
from spxw_tab import ZeroDayTab
from spxw_1min_tab import OneMiniTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPXW 0DTE 분석 툴 v2.0")
        self.resize(1600, 900)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        self.zday_tab  = ZeroDayTab()
        self.min1_tab  = OneMiniTab()
        tabs.addTab(self.zday_tab,  "SPXW 0DTE")
        tabs.addTab(self.min1_tab,  "SPXW 0DTE-1Min")
        layout.addWidget(tabs)
        sb = QStatusBar()
        self.setStatusBar(sb)
        key_loaded = bool(_load_api_key_from_file("CD-KEY.txt"))
        sb.showMessage("✅ CD-KEY.txt API 키 로드 완료" if key_loaded
                       else "⚠️  CD-KEY.txt 없음 — 화면 상단에서 API 키를 입력하세요")


def main():
    _log("=== 프로그램 시작 ===")
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    try:
        win = MainWindow()
        win.show()
        _log("=== UI 완료, 이벤트 루프 시작 ===")
        code = app.exec_()
        _log(f"=== 정상 종료 code={code} ===")
        sys.exit(code)
    except Exception:
        _log(f"[MAIN EXCEPTION]\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
