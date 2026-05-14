"""
tab_greeks_save.py — 자동저장·베이스라인  S12-fix2
══════════════════════════════════════════════════════════
S12-fix1 수정 사항:
  [BUG-D] autosave() chain_store 모드 시 expiry 불일치로 저장 0건 방지.
  [BUG-E] save_baseline rows 비어있을 때 예외 없이 early return.

S12-fix2 수정 사항:
  [FIX-5] self._conn 날짜 자동 갱신
          앱이 자정을 넘겨 실행 중일 때 self._conn이 어제 날짜 DB를 가리키는 문제.
          → autosave() 호출마다 ET 기준 오늘 날짜와 self._day를 비교,
            날짜 바뀌면 self._conn / self._econn / self._day를 모두 재생성.
  [FIX-6] autosave() 저장 시 sym 필드 보장
          _cell_data에 sym이 없는 경우 self._sym으로 채워서 저장.
  [FIX-7] autosave() 상세 진단 로그 추가
          저장 0건 시 원인(expiry 불일치/iv 없음/cell_data 비어있음)을 로그로 출력.
"""
from __future__ import annotations
import logging
from datetime import datetime

import greeks_db as gdb

log = logging.getLogger(__name__)


def _refresh_conn_if_needed(self) -> None:
    """
    [FIX-5] ET 기준 오늘 날짜와 self._day를 비교.
    날짜가 바뀌었으면 self._conn / self._econn / self._day 재생성.
    """
    today = gdb._today_et()
    if today == self._day:
        return

    log.info("[GreeksGrid] 날짜 변경 감지 (%s → %s) — DB 커넥션 재생성",
             self._day, today)
    try:
        self._conn.close()
    except Exception:
        pass
    try:
        self._econn.close()
    except Exception:
        pass

    self._day   = today
    self._conn  = gdb.open_db(self._day)
    self._econn = gdb.open_events_db()
    log.info("[GreeksGrid] DB 커넥션 재생성 완료: greeks_%s.db", self._day)


def autosave(self):
    """
    1분 주기 자동저장.
    - 0DTE _cell_data → greeks_YYYYMMDD.db
    - +1DTE/+2DTE 는 tick 수신 시 즉시 저장 (tab_greeks_tick 경로 3b)

    S12-fix1 [BUG-D]: expiry 필터 유지, 저장 전 rows 수 로그 추가.
    S12-fix2 [FIX-5]: 날짜 변경 시 conn 자동 재생성.
    S12-fix2 [FIX-6]: sym 필드 보장.
    S12-fix2 [FIX-7]: 저장 0건 원인 상세 로그.
    """
    # [FIX-5] 날짜 변경 체크
    _refresh_conn_if_needed(self)

    if not self._expiry:
        log.debug("[GreeksGrid] autosave 건너뜀 — expiry 미설정")
        return

    if not self._cell_data:
        log.debug("[GreeksGrid] autosave 건너뜀 — _cell_data 비어있음")
        return

    # [FIX-7] 진단: expiry별 건수 로그
    expiry_counts: dict = {}
    for (exp, strike, side), v in self._cell_data.items():
        expiry_counts[exp] = expiry_counts.get(exp, 0) + 1

    rows = []
    for (exp, strike, side), v in self._cell_data.items():
        if exp != self._expiry:
            continue
        if not v.get("iv"):
            continue
        # [FIX-6] sym 필드 보장
        row = dict(v)
        if not row.get("sym"):
            row["sym"] = self._sym
        rows.append(row)

    if not rows:
        # [FIX-7] 0건 원인 상세 출력
        total = len(self._cell_data)
        matched_exp = expiry_counts.get(self._expiry, 0)
        no_iv = sum(
            1 for (exp, _, _), v in self._cell_data.items()
            if exp == self._expiry and not v.get("iv")
        )
        log.warning(
            "[GreeksGrid] autosave 저장 0건 — "
            "cell_data 총 %d건 | self._expiry='%s' | "
            "expiry 일치 %d건 | iv 없음 %d건 | expiry 목록: %s",
            total, self._expiry, matched_exp, no_iv,
            list(expiry_counts.keys())
        )
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # [🟠 FIX] r은 이미 dict(v)로 복사된 객체이므로 _cell_data 원본은 변경되지 않음.
    # 명시적으로 확인: rows 리스트 내 dict는 모두 복사본임.
    for r in rows:
        r["ts"] = ts

    try:
        gdb.save_snapshot(self._conn, rows)
        log.info("[GreeksGrid] autosave 완료: %d건 (expiry=%s, day=%s)",
                 len(rows), self._expiry, self._day)
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
    S12-fix2 [FIX-6]: sym 필드 보장.
    """
    if not rows:
        log.debug("[GreeksGrid] save_baseline: rows 비어있음 — 건너뜀")
        return

    # [FIX-6] sym 필드 보장
    for r in rows:
        if not r.get("sym"):
            r["sym"] = self._sym

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
