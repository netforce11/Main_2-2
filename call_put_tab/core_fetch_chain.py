"""
core_fetch_chain.py — 옵션 체인 구독 시퀀스 (_fetch 내부 로직) [수정 버전]
════════════════════════════════════════════════════════
[FIX v6.6.1]
✅ 문제 2 수정: spin_n 값이 26으로 제한되는 버그 제거
  - 기존: n = min(self.spin_n.value(), 26)  ← 26 하드코딩
  - 수정: n = self.spin_n.value()  ← 사용자 입력값 직접 사용

포함 내용:
  - CoreFetchChainMixin
      _arm_fetch_timeout()     구독 타임아웃 타이머 설정
      _force_release_busy()    _fetch_busy 강제 해제
      _fetch()                 옵션 체인 전체 구독 진입점
      _init_tbl()              옵션 테이블 초기화
      on_tab_activate()        탭 활성화 콜백
      on_tab_deactivate()      탭 비활성화 콜백
════════════════════════════════════════════════════════
"""

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from core import SYMBOL_CFG, DEFAULT_CFG, REQ_UND, REQ_CALL, REQ_PUT
from call_put_tab.core_fetch_contracts import (
    make_opt_contract_safe, _mdt_for_sym, _alive, _DELAYED_SYMS,
)


class CoreFetchChainMixin:
    """옵션 체인 구독 시퀀스 및 탭 활성화 로직."""

    def _arm_fetch_timeout(self):
        """_fetch_busy=True 설정 후 호출. 30초 후 강제 해제."""
        t = getattr(self, '_fetch_timeout_timer', None)
        if t is None:
            self._fetch_timeout_timer = QTimer(self)
            self._fetch_timeout_timer.setSingleShot(True)
            self._fetch_timeout_timer.timeout.connect(self._force_release_busy)
        self._fetch_timeout_timer.start(30_000)

    def _force_release_busy(self):
        if getattr(self, '_fetch_busy', False):
            self._fetch_busy = False
            self._log("⚠ 구독 타임아웃 (30초) — _fetch_busy 강제 해제. 재조회 가능합니다.")

    def _fetch(self):
        if not _alive(self):
            return
        if getattr(self, '_fetch_busy', False):
            self._log("⚠ 구독 진행 중 — 중복 조회 요청 무시 (잠시 후 재시도)")
            return
        if not self.mw.connected:
            QMessageBox.warning(self, "미연결", "먼저 TWS에 연결하세요.")
            return
        if self.und_price is None:
            self._fetch_retry_und()
            return

        self._fetch_retry = 0
        expiry, tag = self._get_expiry()
        if not expiry:
            return

        sym = self.edit_sym.text().strip().upper() or "SPX"
        
        # ✅ [FIX v6.6.1] 26 하드코딩 제거 — spin_n 값 직접 사용
        n = max(1, min(self.spin_n.value(), 100))  # 1~100 범위만 허용 (안전 장치)
        # 또는 더 간단하게:
        # n = self.spin_n.value()  # 사용자 입력값 그대로 사용
        
        self._n_strikes = n

        from core import _resolve_spx_trading_class
        display_tc = (_resolve_spx_trading_class(sym, expiry, tag)
                      if sym in ("SPX", "SPXW") else sym)
        _, _, _, step = SYMBOL_CFG.get(sym if sym != "SPXW" else "SPX", DEFAULT_CFG)

        active_rids = list(self.call_data.keys()) + list(self.put_data.keys())
        cancel_ids  = [REQ_UND] + active_rids

        self._fetch_busy = True
        self._arm_fetch_timeout()
        
        # ✅ 로그에서 실제 n 값 확인 가능하게 개선
        self._log(
            f"{display_tc}  구독 초기화 중…  만기={expiry}  "
            f"Zone={self._zone}  n={n} (spin_n={self.spin_n.value()})  cancel={len(cancel_ids)}건")

        gen = getattr(self, '_fetch_gen', 0) + 1
        self._fetch_gen = gen
        self._fetch_chain_seq(gen, cancel_ids, sym, expiry, tag, step, n)

    def _fetch_retry_und(self):
        """und_price 미수신 시 재시도 처리."""
        sym   = self.edit_sym.text().strip().upper() or "SPX"
        retry = getattr(self, '_fetch_retry', 0)
        if retry >= 5:
            self._fetch_retry = 0
            self._log(f"⚠ 현재가 수신 실패 ({sym}) — TWS 연결 상태를 확인하세요.")
            return
        self._fetch_retry = retry + 1
        self._log(f"현재가 수신 중… ({sym}) 잠시 후 재시도합니다. ({self._fetch_retry}/5)")
        if self._fetch_retry == 1:
            self._req_und(sym)
        t = getattr(self, '_fetch_retry_timer', None)
        if t is None:
            self._fetch_retry_timer = QTimer(self)
            self._fetch_retry_timer.setSingleShot(True)
            self._fetch_retry_timer.timeout.connect(self._fetch)
            t = self._fetch_retry_timer
        else:
            t.stop()
        t.start(2000)

    def _fetch_chain_seq(self, gen, cancel_ids, sym, expiry, tag, step, n):
        """체인 구독 시퀀스: cancel → prepare → send_req."""

        def _cancel_seq(idx):
            if self._fetch_gen != gen: return
            if not _alive(self): return
            if idx >= len(cancel_ids):
                QTimer.singleShot(500, _prepare_and_subscribe)
                return
            try:
                self.mw.ib.cancelMktData(cancel_ids[idx])
            except Exception:
                pass
            QTimer.singleShot(80, lambda: _cancel_seq(idx + 1))

        def _prepare_and_subscribe():
            if self._fetch_gen != gen: return
            if not _alive(self): return
            self.call_data.clear()
            self.put_data.clear()
            if PG:
                self._prices.clear()
                self._deltas.clear()
                self._spreads.clear()

            raw_price = self.und_price
            if getattr(self, '_und_is_futures', False) and sym in self._SPX_SYMS:
                ES_BASIS_OFFSET = 5.0
                raw_price = self.und_price - ES_BASIS_OFFSET
                self._log(
                    f"📐 /ES→SPX ATM 보정: {self.und_price:,.2f} → "
                    f"{raw_price:,.2f} (basis -{ES_BASIS_OFFSET}pt)")

            atm = round(raw_price / step) * step
            self.call_strikes, self.put_strikes = self._strikes_for_zone(atm, step, n)
            self._init_tbl(self.tbl_call, self.call_strikes)
            self._init_tbl(self.tbl_put,  self.put_strikes)

            ticks = "100,101,104,106"
            if self.call_strikes:
                _c0 = make_opt_contract_safe(sym, self.call_strikes[0], "C", expiry, tag)
                self._log(
                    f"계약: symbol={_c0.symbol} "
                    f"tc={getattr(_c0,'tradingClass','')} "
                    f"exch={_c0.exchange} ATM={atm}")

            call_reqs = [(REQ_CALL + i, make_opt_contract_safe(sym, st, "C", expiry, tag))
                         for i, st in enumerate(self.call_strikes)]
            put_reqs  = [(REQ_PUT  + i, make_opt_contract_safe(sym, st, "P", expiry, tag))
                         for i, st in enumerate(self.put_strikes)]
            for i, st in enumerate(self.call_strikes):
                self.call_data[REQ_CALL + i] = {"row": i}
            for i, st in enumerate(self.put_strikes):
                self.put_data[REQ_PUT  + i] = {"row": i}

            all_reqs = []
            for i in range(max(len(call_reqs), len(put_reqs))):
                if i < len(call_reqs): all_reqs.append(call_reqs[i])
                if i < len(put_reqs):  all_reqs.append(put_reqs[i])

            self._req_und(sym)
            self._und_timer.start()
            _send_req(0, all_reqs, len(all_reqs), ticks)

        def _send_req(idx, all_reqs, total, ticks):
            if self._fetch_gen != gen: return
            if not _alive(self): return
            if idx >= total:
                self._fetch_busy = False
                t = getattr(self, '_fetch_timeout_timer', None)
                if t: t.stop()
                self._log(f"✅ 구독 완료: 총 {total}개 계약")
                if hasattr(self, 'lbl_status'):
                    self.lbl_status.setText("● 연결됨")
                    self.lbl_status.setStyleSheet(
                        "color:#00ff88;font-weight:bold;border:none;")
                iv = getattr(self, '_iv_panel', None)
                if iv is not None and hasattr(iv, 'update'):
                    QTimer.singleShot(300, iv.update)
                QTimer.singleShot(500, self._notify_sniper_sync)
                return

            done = idx + 1
            if done % 5 == 0 or done == total:
                self._log(f"구독 중… [{done}/{total}]")
            if hasattr(self, 'lbl_status'):
                self.lbl_status.setText(f"● 로딩 [{done}/{total}]")
                self.lbl_status.setStyleSheet(
                    "color:#7c7cff;font-weight:bold;border:none;")

            rid, contract = all_reqs[idx]

            def _do_req(r=rid, c=contract, ni=idx + 1):
                if self._fetch_gen != gen: return
                try:
                    self.mw.ib.reqMktData(r, c, ticks, False, False, [])
                except Exception as e:
                    self._log(f"⚠ reqMktData 오류 rid={r}: {e}")
                QTimer.singleShot(150, lambda: _send_req(ni, all_reqs, total, ticks))

            if idx == 0 and sym in _DELAYED_SYMS:
                _mdt_for_sym(sym, self.mw.ib)
                QTimer.singleShot(200, _do_req)
            elif rid == REQ_PUT:
                QTimer.singleShot(100, _do_req)
            else:
                _do_req()

        _cancel_seq(0)

    def _init_tbl(self, tbl, strikes):
        from call_put_tab.tab_options import _mk
        tbl.clearContents()
        tbl.setRowCount(len(strikes))
        for r, s in enumerate(strikes):
            tbl.setItem(r, 0, _mk(str(int(s)), "#ffd700"))
            for c in range(1, 6):
                tbl.setItem(r, c, _mk("―"))

    def on_tab_deactivate(self):
        old_gen = getattr(self, '_fetch_gen', 0)
        self._fetch_gen = old_gen + 1
        if getattr(self, '_fetch_busy', False):
            self._fetch_busy = False
            t = getattr(self, '_fetch_timeout_timer', None)
            if t: t.stop()
            self._log("⏸ 탭 비활성화 — 구독 루프 중단, _fetch_busy 해제")
        if hasattr(self, '_watch_timer') and self._watch_timer.isActive():
            self._watch_timer.stop()
        if hasattr(self, '_und_timer') and self._und_timer.isActive():
            self._und_timer.stop()

    def on_tab_activate(self):
        if not getattr(getattr(self, 'mw', None), 'connected', False):
            return
        if getattr(self, 'und_price', None) is None:
            return
        if getattr(self, '_fetch_busy', False):
            return
        self._log("▶ 탭 활성화 — 체인 재구독")
        if hasattr(self, '_watch_timer') and not self._watch_timer.isActive():
            self._watch_timer.start()
        if hasattr(self, '_und_timer') and not self._und_timer.isActive():
            self._und_timer.start()
        self._fetch()