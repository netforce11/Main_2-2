"""
tab_greeks_fetch.py — 조회·자동조회·chain_buf  S12-fix2
══════════════════════════════════════════════════════════
S12  BUG-1: _fetch() 에서 clear 전에 cancelMktData 호출
S12  BUG-5: _status_req_count 누적 덧셈 제거 → 이번 조회 건수만 표시
S12  BUG-6: _fetch_next_expiry 실패 카운터 추가
S12-patch1:
  [논리결함2] fetch_next_expiry() 제거, snap_mgr 단독 +1DTE 담당
  [심각2]     auto_fetch_if_market_hours() snap_mgr.start() 에 expiry_0dte 명시
S12-fix1:
  [BUG-A] chain_store/chain_buf 모드에서 snap_mgr.start() 미호출 수정
  [BUG-B] expiry 미설정 시 _refresh_expiry() 후 재시도
  [BUG-C] _chain_store_timer 중복 start() 방지

S12-fix2:
  [FIX-9]  _poll_chain_store() und_price 이상값 필터 추가
  [FIX-10] _poll_chain_store() 배너에 chain_store.size() 출력 추가
  [FIX-11] fetch() expiry 형식 정규화 — combo에서 읽은 값이 "YYYYMMDD" 형식인지 검증
  [FIX-12] _poll_chain_store() cell_data sym 필드 보장
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from PyQt5.QtCore    import QMetaObject, Q_ARG, Qt, pyqtSlot

import greeks_db as gdb
from greeks_db import _is_market_hours, UND_PRICE_MIN, UND_PRICE_MAX
from core import (REQ_CHAIN, REQ_CHAIN_P, make_opt_contract,
                  SYMBOL_CFG, DEFAULT_CFG)
from PyQt5.QtCore import QTimer

ATM_WING      = 10
SNAPSHOT_MODE = True

log = logging.getLogger(__name__)


def _start_snap_mgr(self, label: str = ""):
    """
    snap_mgr.start() 공통 헬퍼.
    expiry / und_price 조건을 통합 체크하고 start() 호출.
    """
    if not self._snap_mgr:
        return
    if not self._expiry:
        log.warning("[GreeksGrid] snap_mgr.start() 건너뜀 — expiry 미설정 (%s)", label)
        return
    if self._und_price <= 0:
        log.warning("[GreeksGrid] snap_mgr.start() 건너뜀 — und_price 미수신 (%s)", label)
        return
    self._snap_mgr.start(
        sym=self._sym,
        und_price=self._und_price,
        expiry_0dte=self._expiry,
    )
    log.info("[GreeksGrid] SnapshotManager 시작 (0DTE=%s, 경로=%s)", self._expiry, label)


def _normalize_expiry(expiry: str) -> str:
    """
    [FIX-11] expiry 형식 정규화.
    IBKR/combo에서 YYYYMMDD 또는 YYYY-MM-DD 형식으로 오는 경우 통일.
    [🟠 FIX] 8자리 숫자가 아닌 비표준 값('TODAY','0DTE','CUSTOM' 등)은
             빈 문자열 반환 → autosave expiry 필터에서 의도치 않게 통과하지 않도록.
    """
    if not expiry:
        return ""
    # YYYY-MM-DD → YYYYMMDD
    cleaned = expiry.replace("-", "").strip()
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned
    # 비표준 값: 경고 후 빈 문자열
    log.warning("[GreeksGrid] _normalize_expiry: 비표준 expiry 값 '%s' → '' 반환", expiry)
    return ""


def fetch(self):
    """당일 만기 Greeks 조회 (IBKR 직접 or chain_buf/chain_store 대기)."""
    self._sym = self._sym_cb.currentText()
    raw_expiry, self._tag = self._current_expiry()
    # [FIX-11] expiry 정규화
    self._expiry = _normalize_expiry(raw_expiry)

    if not self._expiry:
        self._banner.setText("⚠ 만기 미선택 — 만기갱신 버튼을 누르세요"); return
    if self._und_price <= 0:
        self._banner.setText(
            f"⚠ 기초자산 가격 미수신 (und={self._und_price}) — IBKR 연결 확인"); return

    cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
    step    = cfg[3]
    strikes = self._calc_strikes(self._und_price, ATM_WING, step)
    atm_check = round(self._und_price / (step or 5)) * (step or 5)

    log.info("[GreeksGrid] fetch() sym=%s expiry=%s und=%.2f ATM=%s",
             self._sym, self._expiry, self._und_price, atm_check)

    if self._use_chain_buf:
        self._cell_data.clear(); self._prev_data.clear()
        msg = (f"🔗 chain_buf 대기 중 | {self._sym} {self._expiry} "
               f"ATM={atm_check} ±{ATM_WING} | {len(strikes)*2}개")
        self._banner.setText(msg)
        _start_snap_mgr(self, "chain_buf 모드")
        return

    if getattr(self, '_use_chain_store', False):
        self._cell_data.clear(); self._prev_data.clear()
        msg = (f"🔗 chain_store 대기 중 | {self._sym} {self._expiry} "
               f"ATM={atm_check} ±{ATM_WING} | {len(strikes)*2}개")
        self._banner.setText(msg)
        log.info("[GreeksGrid] chain_store 모드 — reqMktData 생략 (%d개)", len(strikes)*2)
        _start_snap_mgr(self, "chain_store 모드")
        return

    # ── BUG-1 수정(S12): clear 전에 기존 구독 취소 ─────────────────────────
    for rid in list(self._req_map.keys()):
        try:
            self._main.ib.cancelMktData(rid)
        except Exception as e:
            # [🟢 FIX] 연결 끊긴 상태에서 cancelMktData 실패 — 로그 기록
            log.debug("[GreeksGrid] cancelMktData rid=%d 실패 (무시): %s", rid, e)
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
    self._snap_count_0dte = 0
    self._status_saving(0, 0, f"당일 만기 조회 중… ({ok}건 요청)")
    self._status_req_count(ok)

    _start_snap_mgr(self, "직접구독 모드")


def auto_fetch_if_market_hours(self):
    """
    앱 시작 1분 후 자동 실행 — 장 중이면 조회·SnapshotManager 시작.
    S12-fix1 [BUG-B]: expiry 없으면 _refresh_expiry() 후 재시도.
    """
    if not _is_market_hours():
        log.info("[GreeksGrid] 장외 시간 — 자동 조회 생략")
        self._status_offhour(True)
        for s in range(3): self._status_idle(s, "장외시간")
        return

    self._status_offhour(False)

    if self._und_price <= 0:
        log.info("[GreeksGrid] 기초자산 미수신 — 30초 후 재시도")
        QTimer.singleShot(30_000, self._auto_fetch_if_market_hours); return

    if not self._expiry:
        log.info("[GreeksGrid] expiry 미설정 — _refresh_expiry() 후 10초 재시도")
        try:
            self._refresh_expiry()
            self._expiry, self._tag = self._current_expiry()
            self._expiry = _normalize_expiry(self._expiry)
        except Exception as e:
            log.error("[GreeksGrid] _refresh_expiry 오류: %s", e)
        if not self._expiry:
            QTimer.singleShot(10_000, self._auto_fetch_if_market_hours)
            return

    log.info("[GreeksGrid] 장 중 자동 조회 시작")
    self._banner.setText("🕐 장 중 자동 조회 시작...")
    self._fetch()


# ── chain_saver 버퍼 연동 ────────────────────────────────────────────────────

def attach_chain_buffer(self, buf):
    from call_put_tab.chain_saver.buffer import ChainBuffer
    self._chain_buf = buf; self._use_chain_buf = True
    buf.register_greeks_subscriber(self._on_chain_buf_update)
    log.info("[GreeksGrid] chain_saver 버퍼 연동 완료 ✅")


def on_chain_buf_update(self, expiry: str, strike: float, side: str, data: dict):
    """★ IBKR EClient 스레드 호출 — UI 접근 금지 → invokeMethod 마샬링."""
    # [FIX-11] expiry 정규화
    expiry = _normalize_expiry(expiry)
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
    expiry = _normalize_expiry(data["expiry"])
    strike = data["strike"]; side = data["side"]
    cfg    = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
    strikes = self._calc_strikes(self._und_price, cfg[3])
    if strike not in strikes: return
    iv    = data.get("iv"); delta = data.get("delta")
    gamma = data.get("gamma"); vega = data.get("vega")
    vanna = (vega * delta) if (vega and delta) else 0.0
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    k     = (expiry, strike, side)
    self._prev_data[k] = self._cell_data.get(k, {}).copy()
    # [FIX-12] sym 항상 명시
    self._cell_data[k] = dict(
        sym=self._sym, expiry=expiry, strike=strike, side=side,
        delta=delta, gamma=gamma, iv=iv, vanna=vanna,
        und_price=data.get("und_price") or self._und_price, ts=ts,
        theo=data.get("theo"), mid=data.get("mid"), mispct=data.get("mispct"),
    )
    n = len(self._cell_data); total = len(self._calc_strikes(self._und_price, ATM_WING, cfg[3])) * 2
    if n % 10 == 0 or n == total:
        pct = int(n / total * 100) if total else 0
        self._banner.setText(f"🔗 버퍼 수신 {n}/{total} ({pct}%) | {side}{int(strike)}")
    if not self._flush_t.isActive(): self._flush_t.start(300)


# ── SharedChainStore 연동 ─────────────────────────────────────────────────────

def attach_chain_store(self, store):
    """
    콜-풋탭의 SharedChainStore 를 Greeks탭에 연결.
    S12-fix1 [BUG-C]: 중복 start() 방지.
    [🟠 FIX] attach 시점에 expiry/und_price 조건 갖춰지면 snap_mgr 즉시 시작.
             이전에는 fetch() 호출 전까지 snap_mgr 미시작 가능했음.
    """
    self._chain_store     = store
    self._use_chain_store = True
    if self._chain_store_timer.isActive():
        self._chain_store_timer.stop()
        log.debug("[GreeksGrid] chain_store_timer 재시작 (중복 방지)")
    self._chain_store_timer.start()
    log.info("[GreeksGrid] SharedChainStore 연동 완료 ✅ (reqMktData 구독 생략)")

    # [🟠 FIX] expiry와 und_price가 이미 준비됐으면 snap_mgr 즉시 시작
    # fetch()가 나중에 호출되더라도 이중 start는 snap_mgr 내부에서 방어
    _start_snap_mgr(self, "attach_chain_store")


def _poll_chain_store(self):
    """
    2초 타이머 콜백 — SharedChainStore 에서 현재 만기 데이터를 읽어
    _cell_data 를 갱신하고 렌더 flush 를 트리거한다.

    S12-fix2 [FIX-9]:  und_price 이상값 필터 추가.
    S12-fix2 [FIX-10]: 배너에 chain_store.size() 표시.
    S12-fix2 [FIX-11]: expiry 정규화 후 비교.
    S12-fix2 [FIX-12]: _cell_data sym 필드 항상 명시.
    """
    store = getattr(self, '_chain_store', None)
    if not store:
        return

    # [FIX-11] self._expiry 정규화 확인
    expiry = _normalize_expiry(self._expiry)
    if not expiry:
        return

    from core import SYMBOL_CFG, DEFAULT_CFG
    cfg     = SYMBOL_CFG.get(self._sym, DEFAULT_CFG)
    step    = cfg[3] if cfg else 5
    strikes = self._calc_strikes(self._und_price, ATM_WING, step)

    updated = 0
    skipped_und = 0
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for strike in strikes:
        for side in ("C", "P"):
            if not store.has_fresh(expiry, strike, side, max_age=5.0):
                continue
            data = store.get(expiry, strike, side)
            if not data:
                continue
            iv = data.get("iv")
            if not iv or not (0 < iv < 10):
                continue

            delta = data.get("delta", 0.0)
            gamma = data.get("gamma", 0.0)
            vega  = data.get("vega",  0.0)
            theta = data.get("theta", 0.0)
            vanna = vega * delta if (vega and delta) else 0.0

            # [FIX-9] und_price 이상값 필터
            und_price = data.get("und_price")
            if und_price is not None:
                if und_price < UND_PRICE_MIN or und_price > UND_PRICE_MAX:
                    log.warning("[GreeksGrid] poll chain_store: und_price 이상값 무시 %.2f "
                                "(strike=%s side=%s)", und_price, strike, side)
                    und_price = None   # 이상값은 None으로
                    skipped_und += 1
            # und_price가 None이면 self._und_price 사용 (단, 이상값이면 None 유지)
            if und_price is None and UND_PRICE_MIN <= self._und_price <= UND_PRICE_MAX:
                und_price = self._und_price

            k = (expiry, strike, side)
            self._prev_data[k] = self._cell_data.get(k, {}).copy()
            # [FIX-12] sym 항상 명시
            self._cell_data[k] = dict(
                sym=self._sym, expiry=expiry,
                strike=strike, side=side,
                delta=delta, gamma=gamma, iv=iv,
                vanna=vanna, vega=vega, theta=theta,
                und_price=und_price,
                ts=ts,
            )
            updated += 1

    if updated > 0:
        n     = len(self._cell_data)
        total = len(strikes) * 2
        pct   = int(n / total * 100) if total else 0
        # [FIX-10] chain_store 전체 크기 표시
        store_size = store.size() if hasattr(store, 'size') else '?'
        warn_str = f" ⚠und이상{skipped_und}" if skipped_und else ""
        self._banner.setText(
            f"🔗 chain_store 동기화 {n}/{total} ({pct}%) | "
            f"{self._sym} {expiry} | store={store_size}{warn_str}")
        if not self._flush_t.isActive():
            self._flush_t.start(300)
