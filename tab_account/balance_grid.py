"""
balance_grid.py — BalanceGrid (잔고/PnL 탭) 메인 클래스
════════════════════════════════════════════════════════
포함 내용:
  - BalanceGrid(GridTab)
      __init__()            초기화
      _build()              패널별 빌더 호출
      _connect_signals()    bridge 시그널 연결
      _refresh()            계좌·포지션·주문 새로고침
      on_tab_activate()     탭 포커스 자동 로딩
      on_tab_deactivate()   탭 비활성 처리

의존:
  account.balance_pnl      실시간 PnL 구독
  account.balance_data     계좌/포지션/세션 로직
  account.balance_journal  매매일지 DB 조회
════════════════════════════════════════════════════════
"""

from core import bridge, GridTab, REQ_ACCT, ACCT_TAGS, ts, ts_full

from tab_account.balance_pnl     import BalancePnlMixin
from tab_account.balance_data    import BalanceDataMixin
from tab_account.balance_session import BalanceSessionMixin
from tab_account.balance_journal import BalanceJournalMixin


class BalanceGrid(BalancePnlMixin, BalanceDataMixin, BalanceSessionMixin, BalanceJournalMixin, GridTab):
    """
    잔고/PnL 탭 (Tab 2).

    MRO:
      BalanceGrid
        → BalancePnlMixin      (실시간 PnL 구독·수신)
        → BalanceDataMixin     (계좌/포지션/주문/세션)
        → BalanceJournalMixin  (매매일지)
        → GridTab
    """

    def __init__(self, mw):
        GridTab.__init__(self)
        self.mw = mw
        self._acct_rows     = {}
        self._pnl_history   = []
        self._session       = {"trades": [], "start_time": ts_full()}
        self._pnl_acct_id   = ""
        self._pnl_req_id    = 9900
        self._rt_pnl_active = False
        self._build()
        self._connect_signals()
        self._load_history()

    def _build(self):
        """패널별 빌더 호출만. 실제 UI 코드는 Account_info/balance_panel_*.py 참조."""
        from Account_info.balance_style         import CS
        from Account_info.balance_panel_hero    import build_hero
        from Account_info.balance_panel_top     import (build_acct_panel,
                                           build_kpi_panel,
                                           build_position_panel)
        from Account_info.balance_panel_mid     import (build_chart_panel,
                                           build_session_panel,
                                           build_order_panel)
        from Account_info.balance_panel_journal import build_journal

        self.setStyleSheet(CS["root"])
        self.add(build_hero(self),           0, 0, 1, 12)
        self.add(build_acct_panel(self),     1, 0, 1,  4)
        self.add(build_kpi_panel(self),      1, 4, 1,  4)
        self.add(build_position_panel(self), 1, 8, 1,  4)
        self.add(build_chart_panel(self),    2, 0, 1,  4)
        self.add(build_session_panel(self),  2, 4, 1,  4)
        self.add(build_order_panel(self),    2, 8, 1,  4)
        self.add(build_journal(self),        3, 0, 1, 12)

    def _connect_signals(self):
        bridge.acct_value.connect(self._on_acct)
        bridge.position_sig.connect(self._on_pos)
        bridge.open_order_sig.connect(self._on_order)
        if hasattr(bridge, 'pnl_sig'):
            bridge.pnl_sig.connect(self._on_rt_pnl)
        if hasattr(bridge, 'order_status_sig'):
            bridge.order_status_sig.connect(self._on_order_status_log)
        if hasattr(bridge, 'exec_sig'):
            bridge.exec_sig.connect(self._on_exec_log)

    def _refresh(self):
        self.tbl_acct.setRowCount(0)
        self.tbl_pos.setRowCount(0)
        self.tbl_ord.setRowCount(0)
        self._acct_rows.clear()
        if self.mw.connected:
            try:
                self.mw.ib.reqAccountSummary(REQ_ACCT, "All", ACCT_TAGS)
                self.mw.ib.reqPositions()
                self.mw.ib.reqAllOpenOrders()
            except Exception as e:
                print(f"계좌 조회 오류: {e}")
        self.lbl_time.setText(f"마지막: {ts()}")

    def on_tab_activate(self):
        """
        main.py _on_tab_changed() 에서 Tab2 포커스 시 자동 호출.
        연결 상태면 즉시 새로고침 + 실시간 PnL 구독 시작.
        """
        if self.mw.connected:
            self._refresh()
            self._start_rt_pnl()
        self._jnl_load()

    def on_tab_deactivate(self):
        """Tab2 에서 벗어날 때 호출 — 실시간 PnL 구독 해지."""
        self._stop_rt_pnl()
