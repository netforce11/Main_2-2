"""
chart_rt.py — 실시간 스트림 시작 / 중지 / 바 수신
────────────────────────────────────────────────────────
포함:
  on_rt_btn()       — ▶/⏹ 버튼 핸들러
  start_stream()    — Polygon / IBKR 실시간 시작
  stop_rt()         — 스트림 중지
  on_bar_in()       — 바 수신 → 디스플레이 갱신
  fetch_missing_polygon() — 과거 보완 요청
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)


import requests
from datetime import datetime, timedelta

from PyQt5.QtWidgets import QMessageBox

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False

from core import auto_mdt

try:
    from data_io import load_month
    _USE_DATA_IO = True
except Exception:
    _USE_DATA_IO = False

from chart_workers import PolygonWorker, IBKRBarTimer


def on_rt_btn(self):
    if self.is_rt:
        stop_rt(self)
    else:
        start_stream(self, self.sym_in.text())


def start_stream(self, symbol):
    symbol = symbol.upper().strip()
    if not symbol: return
    self.sym_in.setText(symbol)
    self.current_sym = symbol
    stop_rt(self)
    self.is_rt = True
    self.selected_date = None
    self._right_row = 0

    if self.mode == "ibkr":
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "TWS에 연결하세요.")
            self.is_rt = False; return
        auto_mdt(self.mw.ib)
        self.ibkr_timer = IBKRBarTimer(self.mw.ib, symbol, parent=self)
        self.ibkr_timer.bar_updated.connect(self._on_bar_in)
        self.ibkr_timer.start(5000)
        self.lbl_mode.setText(f"▶ IBKR {symbol}")
    else:
        if not self.api_key:
            QMessageBox.warning(self, "API 키 없음",
                "api_key.txt에 Polygon API 키를 저장하세요.")
            self.is_rt = False; return
        fetch_missing_polygon(self, symbol)
        self.worker = PolygonWorker(self.api_key, symbol)
        self.worker.data_received.connect(self._on_bar_in)
        self.worker.start()
        self.lbl_mode.setText(f"▶ Polygon {symbol}")

    self.btn_rt.setText("⏹ 중지")
    self.btn_rt.setChecked(True)
    self.btn_rt.setStyleSheet(
        "background:#8b0000;color:#fff;font-weight:bold;"
        "padding:4px;border-radius:3px;")
    self.status_lbl.setText(f"▶ {symbol} 실시간 (ET)")


def stop_rt(self):
    if self.worker:
        self.worker.stop(); self.worker.wait(); self.worker = None
    if self.ibkr_timer:
        self.ibkr_timer.stop(); self.ibkr_timer = None
    self.is_rt = False
    self.btn_rt.setText("▶ 실시간 시작")
    self.btn_rt.setChecked(False)
    self.btn_rt.setStyleSheet(
        "background:#1a6b3c;color:#fff;font-weight:bold;"
        "padding:4px;border-radius:3px;")
    self.lbl_mode.setText(
        "Polygon.io" if self.mode == "polygon" else "IBKR API")
    self.status_lbl.setText("⏹ 중지됨")


def on_bar_in(self, data):
    if isinstance(data, dict):
        self.df_raw.append(data)
    fx    = float(self.fx_in.text() or 1480)
    limit = float(self.high_in.text() or 3000)
    c     = data.get('c', data.get('close', 0))
    v     = data.get('v', data.get('volume', 0))
    eok   = (c * v * fx) / 100_000_000
    if eok >= limit:
        self._append_right(data, eok)
    self._update_display()


def fetch_missing_polygon(self, symbol):
    if not PANDAS: return
    now = datetime.now()
    if _USE_DATA_IO:
        df = load_month(symbol, now.year, now.month)
        if not df.empty:
            self.df = df
            self.df_raw = df.to_dict('records')
            return
    url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
           f"/{(now - timedelta(days=2)).strftime('%Y-%m-%d')}"
           f"/{now.strftime('%Y-%m-%d')}"
           f"?apiKey={self.api_key}&limit=50000")
    try:
        r = requests.get(url, timeout=10).json()
        if 'results' in r:
            self.df_raw.extend(r['results'])
    except Exception as e:
        print(f"[ChartTab] Polygon 보완: {e}")
