"""
tab_greeks_replay.py — 리플레이 모드 제어  S12
══════════════════════════════════════════════
set_replay_mode(), rp_refresh_days(), rp_load(),
rp_toggle_play(), rp_stop(), replay_step(), rp_render()
"""
from __future__ import annotations
import logging
from datetime import datetime as _dt, timedelta as _td

from greeks_db import (load_merged_snapshots, available_days_merged,
                       available_expiries_for_day)
from greeks_render_replay import init_row_replay

try:
    from call_put_tab.chain_saver.buffer import et_to_kst
except ImportError:
    def et_to_kst(s): return s

log = logging.getLogger(__name__)


def set_replay_mode(self, on: bool):
    self._replay_mode = on
    self._stack.setCurrentIndex(1 if on else 0)
    self.btn_live.setChecked(not on)
    self.btn_replay_mode.setChecked(on)
    widgets = [self.rp_cmb_day, self.rp_cmb_expiry,
               self.rp_edit_from, self.rp_edit_to,
               self.rp_btn_load, self.rp_cmb_speed,
               self.rp_btn_play, self.rp_btn_stop, self.rp_lbl_ts]
    for w in widgets: w.setVisible(on)
    self._rp_slider.setVisible(on)
    if on: rp_refresh_days(self)
    else:  rp_stop(self)


def rp_refresh_days(self):
    self.rp_cmb_day.clear()
    for d in reversed(available_days_merged()):
        self.rp_cmb_day.addItem(d)
    rp_refresh_expiries(self, self.rp_cmb_day.currentText())


def rp_on_day_changed(self, day: str):
    self.rp_edit_from.clear(); self.rp_edit_to.clear()
    rp_refresh_expiries(self, day)


def rp_refresh_expiries(self, day: str):
    self.rp_cmb_expiry.clear()
    if not day: return
    self.rp_cmb_expiry.addItem("전체 만기", "")
    for exp in available_expiries_for_day(day):
        try:
            diff = (_dt.strptime(exp, "%Y%m%d") - _dt.strptime(day, "%Y%m%d")).days
            if diff == 0:   label = f"{exp[4:6]}/{exp[6:8]} (당일)"
            elif diff == 1: label = f"{exp[4:6]}/{exp[6:8]} (내일)"
            elif diff > 0:  label = f"{exp[4:6]}/{exp[6:8]} (+{diff}일)"
            else:           label = f"{exp[4:6]}/{exp[6:8]} (만료)"
        except Exception: label = exp
        self.rp_cmb_expiry.addItem(label, exp)


def rp_load(self):
    rp_stop(self)
    day    = self.rp_cmb_day.currentText()
    t_fr   = self.rp_edit_from.text().strip()
    t_to   = self.rp_edit_to.text().strip()
    expiry = self.rp_cmb_expiry.currentData() or ""
    if not day: self.rp_lbl_ts.setText("날짜 선택 필요"); return
    try:
        base_dt  = _dt.strptime(day, "%Y%m%d")
        next_dt  = base_dt + _td(days=1)
        date_str = base_dt.strftime("%Y-%m-%d")
        next_str = next_dt.strftime("%Y-%m-%d")

        def _to_full(t, end=False):
            if not t: return ""
            parts = t.split(":"); hh = int(parts[0])
            mm = parts[1].zfill(2) if len(parts) > 1 else "00"
            ss = "59" if end else "00"
            d  = next_str if hh <= 8 else date_str
            return f"{d} {hh:02d}:{mm}:{ss}"

        from_ts = _to_full(t_fr) if (t_fr or t_to) else f"{date_str} 09:00:00"
        to_ts   = _to_full(t_to, True) if (t_fr or t_to) else f"{next_str} 16:30:00"
    except Exception as e:
        self.rp_lbl_ts.setText(f"시간 오류: {e}"); return

    self.rp_lbl_ts.setText("로딩 중...")
    rows = load_merged_snapshots(day, from_ts, to_ts, expiry=expiry)
    if not rows: self.rp_lbl_ts.setText("데이터 없음"); return

    self._replay_ts_list = list(dict.fromkeys(r["ts"] for r in rows))
    strikes_set = sorted({r["strike"] for r in rows})
    self._replay_strikes = strikes_set
    und = next((r["und_price"] for r in rows if r["und_price"]), 0)
    self._replay_atm = (min(strikes_set, key=lambda s: abs(s - und))
                        if und and strikes_set else 0.0)

    self._replay_frames = {}
    for r in rows:
        row = strikes_set.index(r["strike"])
        self._replay_frames.setdefault(r["ts"], {})[(row, r["side"])] = {
            "delta": r.get("delta") or 0.0, "gamma": r.get("gamma") or 0.0,
            "iv":    r.get("iv")    or 0.0, "vanna": r.get("vanna") or 0.0,
        }

    self._replay_table.setRowCount(len(strikes_set))
    for i, st in enumerate(strikes_set):
        init_row_replay(self._replay_table, i, st, self._replay_atm)

    self._rp_slider.setMaximum(max(0, len(self._replay_ts_list) - 1))
    self._rp_slider.setValue(0)
    self._replay_cur = 0; self._replay_prev = {}
    self.rp_lbl_ts.setText(
        f"로드완료: {len(self._replay_ts_list)}시점 / {len(strikes_set)}행사가")
    rp_render(self, 0)


def rp_toggle_play(self):
    speeds = {"x1": 1000, "x5": 200, "x10": 100}
    if self._replay_playing:
        self._replay_playing = False
        self._replay_timer.stop()
        self.rp_btn_play.setText("▶ 재생")
    else:
        if not self._replay_ts_list: return
        self._replay_playing = True
        self._replay_timer.start(speeds.get(self.rp_cmb_speed.currentText(), 1000))
        self.rp_btn_play.setText("⏸ 일시정지")


def rp_stop(self):
    self._replay_playing = False
    self._replay_timer.stop()
    self.rp_btn_play.setText("▶ 재생")
    self._replay_cur = 0
    if self._replay_ts_list: self._rp_slider.setValue(0)


def replay_step(self):
    if self._replay_cur >= len(self._replay_ts_list) - 1:
        rp_stop(self); return
    self._replay_cur += 1
    self._rp_slider.blockSignals(True)
    self._rp_slider.setValue(self._replay_cur)
    self._rp_slider.blockSignals(False)
    rp_render(self, self._replay_cur)


def rp_on_slider(self, val: int):
    self._replay_cur = val
    rp_render(self, val)


def rp_render(self, idx: int):
    if not self._replay_ts_list or idx >= len(self._replay_ts_list): return
    ts     = self._replay_ts_list[idx]
    cell_d = self._replay_frames.get(ts, {})
    self.rp_lbl_ts.setText(f"{et_to_kst(ts)} (KST)  /  {ts} (ET)")
    from greeks_render_replay import render_rows_replay, apply_view_mode
    from greeks_replay_ctrl   import VIEW_MODES
    mode = getattr(self._replay_panel, "_cur_view", "greeks")
    apply_view_mode(self._replay_table, mode)
    render_rows_replay(self._replay_table, self._replay_strikes,
                       self._replay_atm, cell_d, self._replay_prev,
                       view_cols=VIEW_MODES[mode]["cols"])
    try:
        gex_data = {(i, side): cell_d[(i, side)]
                    for i, s in enumerate(self._replay_strikes)
                    for side in ("C", "P") if (i, side) in cell_d}
        self._replay_gex.update(self._replay_strikes, gex_data)
    except Exception: pass