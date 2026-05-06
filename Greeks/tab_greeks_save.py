"""
tab_greeks_save.py — 자동저장·베이스라인  S12-fix1
══════════════════════════════════════════════════════════
S12-fix1 수정 사항:
  [BUG-D] autosave() 가 self._expiry(0DTE) 필터만 적용해서
          chain_store 모드 시 _cell_data에 데이터가 있어도
          expiry 불일치로 저장이 0건이 되는 경우 방지.
          → expiry 필터를 "현재 만기(0DTE)"로 유지하되,
            _cell_data 자체가 이미 올바른 expiry로 채워져 있음을 확인.
          → 저장 전 rows 수 로그 추가로 빈 저장 감지 용이하게.
  [BUG-E] save_baseline rows 비어있을 때 예외 없이 early return.
"""
from __future__ import annotations
import logging
from datetime import datetime

import greeks_db as gdb

log = logging.getLogger(__name__)


def autosave(self):
    """
    1분 주기 자동저장.
    - 0DTE _cell_data → greeks_YYYYMMDD.db
    - +1DTE/+2DTE 는 tick 수신 시 즉시 저장 (tab_greeks_tick 경로 3b)
    - chain_store 모드에서도 _cell_data에 데이터가 있으면 저장됨

    S12-fix1 [BUG-D]:
      저장 대상 필터: expiry == self._expiry (0DTE)
      _cell_data는 _poll_chain_store() 또는 on_tick_opt()가 채움.
      어느 경로든 key=(expiry, strike, side) 형태이므로 필터 로직은 동일.
      단, self._expiry가 비어있을 경우 전체 저장 방지 → 로그만 출력.
    """
    if not self._expiry:
        log.debug("[GreeksGrid] autosave 건너뜀 — expiry 미설정")
        return

    rows = [
        v for (exp, strike, side), v in self._cell_data.items()
        if exp == self._expiry and v.get("iv")
    ]

    # BUG-D: 저장 전 rows 수 로그로 빈 저장 감지
    if not rows:
        log.debug("[GreeksGrid] autosave: 저장할 0DTE 데이터 없음 "
                  "(expiry=%s, cell_data 총 %d건)", self._expiry, len(self._cell_data))
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in rows:
        r["ts"] = ts

    try:
        gdb.save_snapshot(self._conn, rows)
        log.info("[GreeksGrid] autosave 완료: %d건 (expiry=%s)", len(rows), self._expiry)
    except Exception as e:
        log.error("[GreeksGrid] autosave 저장 실패: %s", e)
        return

    # 이벤트 감지
    try:
        events = gdb.detect_spike(
            self._day, self._sym, rows,
            self._und_price, self._econn)
        for ev in events:
            log.warning("[GreeksGrid] 이벤트 감지: %s", ev)
    except Exception as e:
        log.debug("[GreeksGrid] detect_spike 오류 (무시): %s", e)

    self._status_saving(0, len(rows), f"저장 완료 {len(rows)}건")


def save_baseline(self, rows):
    """
    현재 _cell_data 기반 베이스라인 저장.
    S12-fix1 [BUG-E]: rows 비어있을 때 early return.
    """
    if not rows:
        log.debug("[GreeksGrid] save_baseline: rows 비어있음 — 건너뜀")
        return
    try:
        gdb.save_baseline(rows, self._day)
        log.info("[GreeksGrid] 베이스라인 저장 %d건", len(rows))
    except Exception as e:
        log.error("[GreeksGrid] 베이스라인 저장 실패: %s", e)


def on_save_interval_changed(self, index: int):
    """자동저장 주기 콤보박스 변경 처리."""
    intervals = [30_000, 60_000, 120_000, 300_000]
    if 0 <= index < len(intervals):
        ms = intervals[index]
        if hasattr(self, '_autosave_t'):
            self._autosave_t.setInterval(ms)
        log.info("[GreeksGrid] 자동저장 주기 변경: %dms", ms)