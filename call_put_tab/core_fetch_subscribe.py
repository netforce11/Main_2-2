"""
core_fetch_subscribe.py — 기초자산 구독 로직
════════════════════════════════════════════════════════
포함 내용:
  - CoreFetchSubscribeMixin
      _req_und()     기초자산 시세 구독 (장외→/ES 선물 전환 포함)
      _refresh_und() 장외→장중 전환 감지·재구독 (5초 타이머 콜백)
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer

from core import make_und_contract
from call_put_tab.core_fetch_contracts import (
    CoreFetchContractsMixin,
    _mdt_for_sym, _alive, _DELAYED_SYMS,
)
from call_put_tab.core_fetch_chain import CoreFetchChainMixin


class CoreFetchSubscribeMixin(CoreFetchChainMixin, CoreFetchContractsMixin):
    """기초자산 구독 및 옵션 체인 조회 통합 Mixin."""

    def _req_und(self, sym: str):
        """
        기초자산 시세 구독.

        [장외 선물 전환 로직]
        - sym이 SPX/SPXW이고 is_market_open()==False 이면
          /ES 최근월물 FUT으로 대체 구독한다.
        - 장중에는 항상 SPX 현물로 구독하고 플래그를 False로 복원한다.
        """
        sym = sym.upper().replace("SPXW", "SPX").replace("NANOS", "SPX")
        if not self.mw.connected:
            return

        if not hasattr(self, '_und_is_futures'):
            self._und_is_futures = False

        from core import is_market_open
        use_futures = (sym in self._SPX_SYMS) and (not is_market_open())

        if use_futures:
            contract = self._make_fut_contract("ES")
            self._und_is_futures = True
            exp_label = contract.lastTradeDateOrContractMonth
            self._log(f"🌙 장외 시간 — /ES 선물({exp_label}) 기초자산 전환")
            t_exp = getattr(self, '_next_expiry_timer', None)
            if t_exp is None:
                self._next_expiry_timer = QTimer(self)
                self._next_expiry_timer.setSingleShot(True)
                self._next_expiry_timer.timeout.connect(self._auto_select_next_expiry)
            else:
                self._next_expiry_timer.stop()
            self._next_expiry_timer.start(1000)
        elif sym in self._FUT_UND_CFG:
            contract = self._make_fut_contract(sym)
            self._und_is_futures = True
            self._log(f"📌 {sym} 기초자산: FUT {contract.lastTradeDateOrContractMonth}")
        else:
            contract = make_und_contract(sym)
            self._und_is_futures = False

        _mdt_for_sym(sym, self.mw.ib)
        try:
            from core import REQ_UND
            self.mw.ib.cancelMktData(REQ_UND)
        except Exception:
            pass

        gen = getattr(self, '_und_gen', 0) + 1
        self._und_gen = gen

        def _send(g=gen, c=contract):
            if not _alive(self): return
            if getattr(self, '_und_gen', 0) != g: return
            if not self.mw.connected: return
            try:
                from core import REQ_UND
                self.mw.ib.reqMktData(REQ_UND, c, "232", False, False, [])
            except Exception as e:
                self._log(f"⚠ _req_und reqMktData 오류: {e}")

        delay = 300 if sym in _DELAYED_SYMS else 0
        if delay:
            QTimer.singleShot(delay, _send)
        else:
            _send()

    def _refresh_und(self):
        """
        장외 5초 타이머 콜백.

        - _und_is_futures=True이고 is_market_open()=True가 되면
          /ES 해제 후 SPX 현물로 재구독한다.
        """
        if not self.mw.connected:
            return

        from core import is_market_open

        if is_market_open():
            self._und_timer.stop()
            if getattr(self, '_und_is_futures', False):
                sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
                self._log(f"☀ 정규장 개장 — {sym} 현물로 전환합니다.")
                self._und_is_futures = False
                self.und_price = None
                self.und_prev  = None
                self._req_und(sym)
                if hasattr(self, 'lbl_und'):
                    self.lbl_und.setText("조회 중…")
            return

        # 장외: 선물 구독 중이고 가격이 이미 수신됐으면 재구독 불필요
        if getattr(self, '_und_is_futures', False) and self.und_price is not None:
            return

        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
        self._req_und(sym)
