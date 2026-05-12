"""
chart_tick_updater.py — 틱 속도 2초 업데이트 + DB 저장 + 바 정리
[분리] chart_tick_speed.py 에서 분리 (_update, _save_to_db, _trim_bars)
"""
import time

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from chart_tick_speed import (
    WINDOWS, HISTORY_LEN, COLOR_SURGE, COLOR_FAST, COLOR_NORMAL,
    _tick_times, _quote_times, _db_batch, _current_sym,
    _purge, _count, _get_color, _ratio_str
)

def _update(self):
    """2초마다 호출 — 집계 + 라벨 갱신 + DB 저장."""
    if not PG:
        return

    now = time.time()
    _purge(now - max(WINDOWS) - 5)

    counts = {}
    for w in WINDOWS:
        qc = _count(_quote_times, w)   # 호가
        ec = _count(_tick_times,  w)   # 체결 (Last)
        counts[w] = {"quote": qc, "exec": ec}

        hist = self._ts_hist[w]
        hist["quote"].append(qc)
        hist["exec"].append(ec)
        if len(hist["quote"]) > HISTORY_LEN: hist["quote"].pop(0)
        if len(hist["exec"])  > HISTORY_LEN: hist["exec"].pop(0)

    x = self._ts_x
    self._ts_x += 1

    # ── 윈도우별 라벨 갱신 ──────────────────────────────────
    # y 위치: 호가=상단(0.68), 체결=하단(0.35)
    # x 위치: 10s=좌, 30s=중, 60s=우
    vr    = self.p3.getViewBox().viewRange()
    x_min = vr[0][0]
    x_span = max(vr[0][1] - vr[0][0], 1)
    col_w  = x_span / len(WINDOWS)

    for i, w in enumerate(WINDOWS):
        qc = counts[w]["quote"]
        ec = counts[w]["exec"]
        hist = self._ts_hist[w]

        q_color = _get_color(qc, hist["quote"])
        e_color = _get_color(ec, hist["exec"])
        q_ratio = _ratio_str(qc, hist["quote"])
        e_ratio = _ratio_str(ec, hist["exec"])

        lx = x_min + col_w * i + col_w * 0.02
        lbl = self._ts_labels[w]

        # 호가: 상단, 체결: 하단
        lbl["quote"].setText(f"{w}s 호가 {qc:>3} {q_ratio}", color=q_color)
        lbl["exec"].setText( f"{w}s 체결 {ec:>3} {e_ratio}", color=e_color)
        lbl["quote"].setPos(lx, 1.0)
        lbl["exec"].setPos( lx, 0.5)

        # 히스토리 바: 10s 윈도우만 (호가=상단 절반, 체결=하단 절반)
        if w == 10:
            if qc > 0:
                b = pg.BarGraphItem(x=[x], height=[0.44], width=0.8,
                                     y0=0.55, brush=q_color, pen=pg.mkPen(None))
                self.p3.addItem(b)
                self._ts_bars[w]["quote"].append(b)
            if ec > 0:
                b2 = pg.BarGraphItem(x=[x], height=[0.44], width=0.8,
                                      y0=0.05, brush=e_color, pen=pg.mkPen(None))
                self.p3.addItem(b2)
                self._ts_bars[w]["exec"].append(b2)
            _trim_bars(self.p3, self._ts_bars[w]["quote"], HISTORY_LEN)
            _trim_bars(self.p3, self._ts_bars[w]["exec"],  HISTORY_LEN)

    # ── DB 저장 ───────────────────────────────────────────────
    _save_to_db(counts)


def _save_to_db(counts: dict):
    """
    tick_speed 테이블에 집계값 저장.
    [수정] 30초치(15건)를 배치로 모아 한 번에 커밋 (기존: 2초마다 단건 커밋)
    """
    global _db_batch, _current_sym
    _db_batch.append({
        "symbol":    _current_sym or "UNKNOWN",
        "w10_tick":  counts[10]["exec"],
        "w10_quote": counts[10]["quote"],
        "w30_tick":  counts[30]["exec"],
        "w30_quote": counts[30]["quote"],
        "w60_tick":  counts[60]["exec"],
        "w60_quote": counts[60]["quote"],
    })
    if len(_db_batch) >= 15:   # 2초 × 15 = 30초치
        try:
            from db_manager import DBManager
            DBManager.get().insert_tick_speed_batch(_db_batch)
            _db_batch.clear()
        except Exception:
            _db_batch.clear()   # DB 오류 시 버퍼 비워 무한 증가 방지


def _trim_bars(plot, bar_list: list, max_len: int):
    while len(bar_list) > max_len:
        try:
            plot.removeItem(bar_list.pop(0))
        except Exception:
            bar_list.pop(0) if bar_list else None