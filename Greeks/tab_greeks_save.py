"""
tab_greeks_save.py — 자동저장·베이스라인·저장주기  S12
═══════════════════════════════════════════════════
autosave()               : 1분 주기 DB 저장 + 이벤트 감지
save_baseline()          : 15:00 기준 IV/Gamma 평균 저장
on_save_interval_changed(): 저장 주기 콤보박스 변경
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import List

import greeks_db as gdb

log = logging.getLogger(__name__)


def autosave(self):
    # und_price 갱신 (callput 탭 참조)
    if not self._cell_data and self._callput:
        und = getattr(self._callput, "und_price", 0.0)
        if und and und > 0: self._und_price = und
    if not self._cell_data: return
    try:
        from call_put_tab.chain_saver.buffer import now_et
        ts = now_et().strftime("%Y-%m-%d %H:%M:%S")
    except ImportError:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = [{**d, "ts": ts, "sym": self._sym} for d in self._cell_data.values()]
    try:
        gdb.save_snapshot(self._conn, rows)
        evts  = gdb.detect_spike(self._day, self._sym, rows, self._und_price, self._econn)
        evts += self._ctx.detect(rows, self._day, self._sym)
        if evts: self._banner.setText(" | ".join(evts[-3:]))
    except Exception as e:
        log.error("[GreeksGrid] autosave: %s", e)

    now = datetime.now()
    if now.hour == 15 and now.minute == 0:
        save_baseline(self, rows)


def save_baseline(self, rows: List[dict]):
    cutoff = datetime.now() - timedelta(minutes=gdb.BASELINE_CUT_MIN)
    valid  = [r for r in rows
              if datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S") < cutoff]
    if not valid: return
    agg: dict = {}
    for r in valid:
        k = (r["sym"], r["expiry"], r["strike"], r["side"])
        agg.setdefault(k, {"iv": [], "gamma": []})
        if r.get("iv"):    agg[k]["iv"].append(r["iv"])
        if r.get("gamma"): agg[k]["gamma"].append(r["gamma"])
    bl = [dict(sym=k[0], expiry=k[1], strike=k[2], side=k[3],
               iv_avg   =sum(v["iv"])   / len(v["iv"])    if v["iv"]    else 0.0,
               gamma_avg=sum(v["gamma"])/ len(v["gamma"]) if v["gamma"] else 0.0)
          for k, v in agg.items()]
    try: gdb.save_baseline(bl)
    except Exception as e: log.error("[GreeksGrid] save_baseline: %s", e)


def on_save_interval_changed(self, idx: int):
    ms = self.cmb_save_interval.itemData(idx)
    try:
        sched = getattr(self._main, "_chain_sched", None)
        if sched and hasattr(sched, "_t5"):
            sched._t5.setInterval(ms)
            log.info("[GreeksGrid] 저장 주기 변경 → %dms", ms)
            self._banner.setText(f"💾 저장 주기 변경: {self.cmb_save_interval.currentText()}")
    except Exception as e:
        log.error("[GreeksGrid] 저장 주기 변경 실패: %s", e)
