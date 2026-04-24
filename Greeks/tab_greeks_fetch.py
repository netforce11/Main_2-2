"""
tab_greeks_fetch.py — 조회·자동조회·chain_buf  S12
══════════════════════════════════════════════════
BUG-1 수정: _fetch() 에서 clear 전에 cancelMktData 호출
BUG-5 수정: _status_req_count 에 누적 덧셈 제거 → 이번 조회 건수만 표시
BUG-6 수정: _fetch_next_expiry 에 실패 카운터 추가
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from PyQt5.QtCore    import QTimer, QMetaObject, Q_ARG, Qt, pyqtSlot

import greeks_db as gdb
from greeks_db import _is_market_hours
from core import (REQ_CHAIN, REQ_CHAIN_P, make_opt_contract,
                  SYMBOL_CFG, DEFAULT_CFG)

REQ_NEXT_C = REQ_CHAIN_P + 200   # 4400
REQ_NEXT_P = REQ_CHAIN_P + 400   # 4600

ATM_WING      = 10
SNAPSHOT_MODE = True
NEXT_EXPIRY_DELAY_MS = 600_000

log = logging.getLogger(__name__)

def fetch(self):
    """당일 만기 Greeks 조회 (IBKR 직접 or chain_buf 대기)."""
    self._sym, (self._expiry, self._tag) = (
        self._sym_cb.currentText(), self._current_expiry())

    if not self._expiry:
        self._banner.setText("⚠ 만기 미선택 — 만기갱신 버튼을 누르세요"); return
    if self._und_price <= 0:
        self._banner.setText(
            f"⚠ 기초자산 가격 미수신 (und={self._und_price}) — IBKR 연결 확인"); return

    cfg    = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
    step   = cfg[3]
    strikes = self._calc_strikes(self._und_price, ATM_WING, step)
    atm_check = round(self._und_price / (step or 5)) * (step or 5)

    if self._use_chain_buf:
        self._cell_data.clear(); self._prev_data.clear()
        msg = (f"🔗 chain_buf 대기 중 | {self._sym} {self._expiry} "
               f"ATM={atm_check} ±{ATM_WING} | {len(strikes)*2}개")
        self._banner.setText(msg); return

    # ── BUG-1 수정: clear 전에 기존 구독 취소 ──────────────
    for rid in list(self._req_map.keys()):
        try: self._main.ib.cancelMktData(rid)
        except Exception: pass
    self._req_map.clear()
    self._rid_c = REQ_CHAIN
    self._rid_p = REQ_CHAIN_P

    ok = 0; fail = 0; snap = SNAPSHOT_MODE
    for s in strikes:
        for side, counter_attr, end in [
                ("C", "_rid_c", REQ_CHAIN_P   - 1),
                ("P", "_rid_p", REQ_CHAIN_P + 199)]:
            rid = getattr(self, counter_attr)
            if rid > end:
                log.warning("[GreeksGrid] reqId 블록 초과 side=%s", side); continue
            self._req_map[rid] = (s, side, self._expiry)
            setattr(self, counter_attr, rid + 1)
            try:
                self._main.ib.reqMktData(
                    rid, make_opt_contract(self._sym, s, side, self._expiry, self._tag),
                    "", snap, False, [])
                ok += 1
            except Exception as e:
                log.error("[GreeksGrid] reqMktData 오류 %s %s: %s", s, side, e)
                fail += 1

    mode_str = "📸 스냅샷" if snap else "📡 스트림"
    msg = (f"{mode_str} {self._sym} {self._expiry} | ATM={atm_check} ±{ATM_WING} | "
           f"요청 {ok}건" + (f" (실패 {fail}건)" if fail else ""))
    self._banner.setText(msg)
    # BUG-5 수정: 누적이 아닌 이번 조회 건수만
    self._snap_count_0dte = 0
    self._status_saving(0, 0, f"당일 만기 조회 중… ({ok}건 요청)")
    self._status_req_count(ok)

def fetch_next_expiry(self):
    """장 시작 10분 후 — +1DTE 스냅샷 요청 후 3초 뒤 cancel."""
    nxt = self._next_trading_expiry()
    if not nxt:
        log.info("[GreeksGrid] 내일 만기 없음"); return
    if self._und_price <= 0:
        log.warning("[GreeksGrid] 내일 만기 스킵 — 기초자산 미수신"); return
    self._next_map.clear()
    self._rid_nc = REQ_NEXT_C; self._rid_np = REQ_NEXT_P
    cfg  = SYMBOL_CFG.get(self._sym, DEFAULT_CFG); step = cfg[3]
    ok = 0; fail = 0   # BUG-6 수정: 실패 카운터 추가
    for s in self._calc_strikes(self._und_price, ATM_WING, step):
        for side, counter_attr, end in [
                ("C", "_rid_nc", REQ_NEXT_P   - 1),
                ("P", "_rid_np", REQ_NEXT_P + 199)]:
            rid = getattr(self, counter_attr)
            if rid > end: continue
            self._next_map[rid] = (s, side, nxt)
            setattr(self, counter_attr, rid + 1)
            try:
                self._main.ib.reqMktData(
                    rid, make_opt_contract(self._sym, s, side, nxt, ""),
                    "", False, False, [])
                ok += 1
            except Exception as e:
                log.error("[GreeksGrid] 내일만기 reqMktData 오류: %s", e)
                fail += 1
    self._snap_count_1dte = 0
    self._status_saving(1, 0, f"+1DTE 조회 중… ({ok}건 요청)"
                        + (f" 실패{fail}" if fail else ""))
    self._status_req_count(ok)
    QTimer.singleShot(3000, self._cancel_next_expiry)

def cancel_next_expiry(self):
    for rid in list(self._next_map):
        try: self._main.ib.cancelMktData(rid)
        except Exception: pass
    log.info("[GreeksGrid] 내일 만기 cancel (%d건)", len(self._next_map))
    self._next_map.clear()
    self._status_done(1, self._snap_count_1dte, "+1DTE 저장 완료")

def auto_fetch_if_market_hours(self):
    """앱 시작 1분 후 자동 실행 — 장 중이면 조회·SnapshotManager 시작."""
    if not _is_market_hours():
        log.info("[GreeksGrid] 장외 시간 — 자동 조회 생략")
        self._status_offhour(True)
        for s in range(3): self._status_idle(s, "장외시간")
        return
    self._status_offhour(False)
    if self._und_price <= 0:
        log.info("[GreeksGrid] 기초자산 미수신 — 30초 후 재시도")
        QTimer.singleShot(30_000, self._auto_fetch_if_market_hours); return
    log.info("[GreeksGrid] 장 중 자동 조회 시작")
    self._banner.setText("🕐 장 중 자동 조회 시작...")
    self._fetch()
    if self._snap_mgr and self._expiry:
        self._snap_mgr.start(sym=self._sym, und_price=self._und_price,
                             expiry_0dte=self._expiry)
        log.info("[GreeksGrid] SnapshotManager 자동 시작")

# ── chain_saver 버퍼 연동 ────────────────────────────────────

def attach_chain_buffer(self, buf):
    from call_put_tab.chain_saver.buffer import ChainBuffer
    self._chain_buf = buf; self._use_chain_buf = True
    buf.register_greeks_subscriber(self._on_chain_buf_update)
    log.info("[GreeksGrid] chain_saver 버퍼 연동 완료 ✅")

def on_chain_buf_update(self, expiry: str, strike: float, side: str, data: dict):
    """★ IBKR EClient 스레드 호출 — UI 접근 금지 → invokeMethod 마샬링."""
    if expiry != self._expiry: return
    iv = data.get("iv")
    if not iv or not (0 < iv < 10): return
    try:
        payload = json.dumps({
            "expiry": expiry, "strike": strike, "side": side,
            "iv": iv, "delta": data.get("delta"), "gamma": data.get("gamma"),
            "vega": data.get("vega"), "theta": data.get("theta"),
            "und_price": data.get("und_price"),
            "theo": data.get("theo"), "mid": data.get("mid"),
            "mispct": data.get("mispct"),
        })
    except Exception: return
    QMetaObject.invokeMethod(self, "_apply_chain_buf_update",
                             Qt.QueuedConnection, Q_ARG(str, payload))

@pyqtSlot(str)
def apply_chain_buf_update(self, payload: str):
    try: data = json.loads(payload)
    except Exception: return
    expiry = data["expiry"]; strike = data["strike"]; side = data["side"]
    cfg    = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
    strikes = self._calc_strikes(self._und_price, cfg[3])
    if strike not in strikes: return
    iv    = data.get("iv"); delta = data.get("delta")
    gamma = data.get("gamma"); vega = data.get("vega")
    vanna = (vega * delta) if (vega and delta) else 0.0
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    k     = (expiry, strike, side)
    self._prev_data[k] = self._cell_data.get(k, {}).copy()
    self._cell_data[k] = dict(
        expiry=expiry, strike=strike, side=side,
        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
        und_price=data.get("und_price") or self._und_price, ts=ts,
        theo=data.get("theo"), mid=data.get("mid"), mispct=data.get("mispct"),
    )
    n = len(self._cell_data); total = len(self._calc_strikes(self._und_price, ATM_WING, cfg[3])) * 2
    if n % 10 == 0 or n == total:
        pct = int(n / total * 100) if total else 0
        self._banner.setText(f"🔗 버퍼 수신 {n}/{total} ({pct}%) | {side}{int(strike)}")
    if not self._flush_t.isActive(): self._flush_t.start(300)
