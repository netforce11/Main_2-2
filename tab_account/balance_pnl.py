"""
balance_pnl.py — 실시간 PnL 구독·수신 로직
════════════════════════════════════════════════════════
포함 내용:
  - BalancePnlMixin
      _start_rt_pnl()       reqPnL 구독 시작 (계좌 ID 자동 추출)
      _stop_rt_pnl()        탭 비활성 시 구독 해지
      _hook_pnl_callback()  IBapi.pnl 콜백 직접 패치
      _apply_rt_pnl()       실시간 PnL 수신 → UI 즉시 갱신
      _on_rt_pnl()          bridge.pnl_sig 연결용 슬롯
════════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer
from core import ts


class BalancePnlMixin:
    """실시간 PnL 구독·수신 로직. BalanceGrid에 mixin된다."""

    def _start_rt_pnl(self):
        """
        IBKR reqPnL() 로 실시간 미실현/실현 PnL 구독 시작.
        계좌 ID는 reqAccountSummary 응답에서 자동 추출.
        """
        if self._rt_pnl_active:
            return
        if not self.mw.connected or not self.mw.ib:
            return
        acct = self._pnl_acct_id
        if not acct:
            # 계좌 ID 아직 미수신 → 2초 후 재시도
            QTimer.singleShot(2000, self._start_rt_pnl)
            return
        try:
            self.mw.ib.reqPnL(self._pnl_req_id, acct, "")
            self._rt_pnl_active = True
            self._hook_pnl_callback()
        except Exception as e:
            print(f"[BalanceGrid] reqPnL 오류: {e}")

    def _stop_rt_pnl(self):
        """탭 비활성 시 실시간 PnL 구독 해지."""
        if not self._rt_pnl_active:
            return
        try:
            if self.mw.ib:
                self.mw.ib.cancelPnL(self._pnl_req_id)
        except Exception:
            pass
        self._rt_pnl_active = False

    def _hook_pnl_callback(self):
        """
        IBapi.pnl 콜백을 직접 패치해 실시간 PnL 수신.
        bridge.pnl_sig 가 없는 환경에서도 동작.
        """
        if not self.mw.ib:
            return
        ib = self.mw.ib
        _orig_pnl = getattr(ib, 'pnl', lambda *a: None)

        def _on_pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL):
            try:
                _orig_pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)
            except Exception:
                pass
            if reqId != self._pnl_req_id:
                return
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._apply_rt_pnl(
                dailyPnL, unrealizedPnL, realizedPnL))

        ib.pnl = _on_pnl

    def _apply_rt_pnl(self, daily_pnl, unrealized, realized):
        """실시간 PnL 수신 → UI 즉시 갱신."""
        try:
            # 미실현 PnL (대형 라벨)
            sign = "+" if unrealized >= 0 else ""
            col  = "#00ff88" if unrealized >= 0 else "#ff4444"
            self.lbl_pnl.setText(f"{sign}${unrealized:,.2f}")
            self.lbl_pnl.setStyleSheet(
                f"color:{col};border:none;font-size:22px;font-weight:bold;")

            # 실현 PnL (주요 지표)
            rcol = "#00ff88" if realized >= 0 else "#ff4444"
            self.lbl_rpnl._val.setText(f"${realized:,.2f}")
            self.lbl_rpnl._val.setStyleSheet(f"color:{rcol};border:none;")

            # 마지막 업데이트 시각
            self.lbl_time.setText(f"실시간: {ts()}")
            self._record_pnl(0.0, unrealized)
        except Exception as e:
            print(f"[BalanceGrid] _apply_rt_pnl 오류: {e}")

    def _on_rt_pnl(self, req_id, daily_pnl, unrealized, realized):
        """bridge.pnl_sig 연결용 슬롯 (core.py 에 pnl_sig 있을 때)."""
        if req_id != self._pnl_req_id:
            return
        self._apply_rt_pnl(daily_pnl, unrealized, realized)
