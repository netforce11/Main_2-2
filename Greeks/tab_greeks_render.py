"""
tab_greeks_render.py — 렌더·필터·밴드 갱신  S12
══════════════════════════════════════════════
flush()               : throttle 후 테이블 렌더 + GexSkew 갱신
apply_delta_filter()  : 델타 슬라이더 필터
update_band()         : 1분 주기 NormalBandPanel 갱신
render_dirty_cells()  : RenderThrottle 콜백
"""
from __future__ import annotations
import logging

import greeks_db as gdb
from greeks_render import init_row, render_rows
from core import SYMBOL_CFG, DEFAULT_CFG

log = logging.getLogger(__name__)


def flush(self):
    try:
        if not self._cell_data: return
        cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step    = cfg[3]
        strikes = self._calc_strikes(self._und_price, 10, step)
        atm     = min(strikes, key=lambda s: abs(s - self._und_price))
        s_idx   = {s: i for i, s in enumerate(strikes)}

        rd = {}
        for (exp, strike, side), d in self._cell_data.items():
            if exp == self._expiry and strike in s_idx:
                rd[(s_idx[strike], side)] = d

        n = len(rd)
        if self._table.rowCount() != len(strikes):
            self._table.setRowCount(len(strikes))
            for r, st in enumerate(strikes):
                init_row(self._table, r, st, atm)

        render_rows(self._table, strikes, atm, rd, self._prev_data)

        if n == len(strikes) * 2:
            self._banner.setText(
                f"✅ {self._sym} {self._expiry} | ATM={int(atm)} | {n}개 수신 완료")
            self._snap_count_0dte = n
            self._status_done(0, n, "당일 만기 수신 완료")
        else:
            self._snap_count_0dte = n
            self._status_saving(0, n, "당일 만기 저장 중…")

    except Exception as e:
        log.error("[GreeksGrid] flush render_rows: %s", e)

    # GexSkewPanel 갱신
    try:
        cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
        step    = cfg[3]
        strikes = self._calc_strikes(self._und_price, 10, step)
        gex_data = {}
        for i, s in enumerate(strikes):
            for side in ("C", "P"):
                k = (self._expiry, s, side)
                if k in self._cell_data:
                    gex_data[(i, side)] = self._cell_data[k]
        self._gex.update(strikes, gex_data)
    except Exception as e:
        log.error("[GreeksGrid] gex update: %s", e)


def apply_delta_filter(self, val: int):
    thresh = val / 100.0
    for row in range(self._table.rowCount()):
        item = self._table.item(row, 0)
        if item:
            try: self._table.setRowHidden(row, abs(float(item.text())) < thresh)
            except ValueError: pass


def update_band(self):
    """1분 주기 — DB에서 오늘 ATM Gamma/IV 시계열 + 과거 평균 → NormalBandPanel."""
    if not self._cell_data: return
    try:
        snaps = gdb.load_snapshots(self._day)
        if not snaps: return
        und     = self._und_price
        strikes = sorted({r["strike"] for r in snaps})
        if not strikes: return
        atm = min(strikes, key=lambda s: abs(s - und))
        atm_rows = sorted([r for r in snaps if r["strike"] == atm and r["side"] == "C"],
                          key=lambda r: r["ts"])
        if not atm_rows: return
        today_ts    = list(range(len(atm_rows)))
        today_gamma = [r["gamma"] or 0.0 for r in atm_rows]
        today_iv    = [r["iv"]    or 0.0 for r in atm_rows]
        hist_gamma: list = []; hist_iv: list = []
        for past_day in gdb.available_days()[-6:-1]:
            for r in gdb.load_snapshots(past_day):
                if r["strike"] == atm and r["side"] == "C":
                    if r["gamma"]: hist_gamma.append(r["gamma"])
                    if r["iv"]:    hist_iv.append(r["iv"])
        self._band.update_band(today_ts, today_gamma, today_iv, hist_gamma, hist_iv)
    except Exception as e:
        log.error("[GreeksGrid] band update: %s", e)


def render_dirty_cells(self, dirty_cells: list):
    """RenderThrottle 콜백 — 변경된 셀만 렌더."""
    if not self._cell_data: return
    cfg    = SYMBOL_CFG.get(self._sym, DEFAULT_CFG); step = cfg[3]
    strikes = self._calc_strikes(self._und_price, 10, step)
    atm     = min(strikes, key=lambda s: abs(s - self._und_price))
    s_idx   = {s: i for i, s in enumerate(strikes)}
    rd = {}
    for (exp, strike, side), d in self._cell_data.items():
        if exp == self._expiry and strike in s_idx:
            rd[(s_idx[strike], side)] = d
    if self._viewport_clip:
        top, bot = self._viewport_clip.visible_row_range()
        dirty_cells = [(r, c) for r, c in dirty_cells if top <= r <= bot]
    if not dirty_cells: return
    render_rows(self._table, strikes, atm, rd, self._prev_data)
