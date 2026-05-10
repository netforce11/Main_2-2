"""
core_conn_ibkr.py — 연결 이벤트·MDT 관리  v6.6

[v6.6 수정]
  ① 체결 콜백 재패치 누락 (_on_connected):
    - 재연결 시 _fill_hooks_applied = False 명시 초기화
    - 기존: _hook_fill_callbacks가 이미 패치됐다고 판단 → 재패치 안 함
    - 수정: 연결 시마다 강제 재패치 보장

  ② MDT 토글 충돌 방지 (_apply_mdt_manual):
    - VIX·CL 등 지연 필수 종목(_DELAYED_SYMS)은 수동으로 실시간(1)을 선택해도
      MDT=3으로 강제 유지
    - 사용자에게 안내 메시지 출력 후 라디오 버튼 자동 복원
"""

from PyQt5.QtCore import QTimer
from core import bridge, auto_mdt, is_trading_day
from call_put_tab.core_conn_spxw import _today_et


class ConnIbkrMixin:
    """연결 이벤트·MDT 관리. CoreConnMixin에 통합된다."""

    def _on_connected(self):
        self.lbl_status.setText("● 연결됨")
        self.lbl_status.setStyleSheet("color:#00ff88;font-weight:bold;border:none;")
        self._log("TWS 연결 성공 ✓")

        # ✅ 이전 세션 잔류값 초기화
        self.und_price        = None
        self.und_prev         = None
        self._last_tick_time  = None   # [v6.5-1] 타임스탬프 리셋
        self._err354_count    = 0      # reset: clean session, MDT state unknown
        self._spxw_today_selected = False  # 만기 자동선택 덮어쓰기 방지 플래그 리셋

        # [v6.6 ①] 체결 콜백 재패치 보장 — 재연결 시 반드시 재패치
        # 기존 _fill_hooks_applied=True 상태로 남아있으면 _hook_fill_callbacks가
        # 재패치를 건너뛰므로, 연결할 때마다 명시적으로 False로 초기화
        self._fill_hooks_applied = False

        if hasattr(self, 'lbl_und'):
            self.lbl_und.setText("조회 중…")

        def _step2_req_und():
            self._apply_mdt()
            self._req_und(self.edit_sym.text().upper())
            from core import is_market_open
            if not is_market_open():
                self._und_timer.start()

        def _step3_setup():
            self._auto_fetch_spxw_today()
            # [v1.1] 초기 연결 시 잔고 자동 조회
            if hasattr(self, '_on_pos_reconnect_hook'):
                QTimer.singleShot(1500, self._on_pos_reconnect_hook)

        QTimer.singleShot(300,  _step2_req_und)
        QTimer.singleShot(2500, _step3_setup)

        # [S11] 계좌번호 → lbl_acct_mode 갱신 (즉시 시도 + 500ms 재시도)
        self._fetch_and_show_account()
        QTimer.singleShot(500, self._fetch_and_show_account)

    def _auto_fetch_spxw_today(self):
        """연결 후 SPXW 0DTE 콤보만 자동 선택."""
        today = _today_et()   # ★ ET 기준
        if not is_trading_day(today):
            self._log("오늘은 거래일이 아닙니다. SPXW 자동 선택 건너뜀."); return
        today_str = today.strftime("%Y%m%d")
        found_idx = next(
            (i for i in range(self.combo_spxw.count())
             if self.combo_spxw.itemData(i) == today_str), -1)
        if found_idx < 0:
            self._log(f"SPXW 0DTE 오늘({today_str}) 항목 없음 — 조회 버튼으로 수동 조회하세요."); return
        self.combo_spxw.blockSignals(True)
        self.combo_spxw.setCurrentIndex(found_idx)
        self.combo_spxw.blockSignals(False)
        self._on_spxw_select(found_idx)
        self._log(f"🔄 SPXW 0DTE 자동 선택: {today_str}  ← 조회 버튼을 눌러 체인을 로드하세요.")

        # ★ _auto_select_next_expiry 가 이 날짜를 덮어쓰지 못하도록 플래그 설정
        # _req_und() → _next_expiry_timer(1초) → _auto_select_next_expiry 경로가
        # _auto_fetch_spxw_today(2500ms) 이전에 발화되어 combo_exp 를 내일 날짜로
        # 변경하는 버그 방지. 플래그가 True 이면 _auto_select_next_expiry 는 skip.
        self._spxw_today_selected = True

        # 혹시 타이머가 아직 살아있으면 즉시 취소
        t_exp = getattr(self, '_next_expiry_timer', None)
        if t_exp is not None:
            t_exp.stop()

    def _on_error(self, rid, code, msg):
        # 정상 알림 / 무해한 에러 무시
        if code in (2104,2106,2108,2158,2119,2176,300,10167): return
        if code == 354:
            cnt = getattr(self, '_err354_count', 0) + 1
            self._err354_count = cnt
            if cnt <= 3:
                self._log(f"ERR 354 ({cnt}/3): MDT 타이밍 이슈 — 데이터 수신 중이면 무시")
            return
        self._err354_count = 0

        # ── [v6.5-4] Fatal error → auto-reconnect flow ──────────
        if code in (1100, 100):
            if getattr(self, '_reconnecting', False):
                return   # reconnect already in progress, skip duplicate
            self._log(f"🚨 ERR {code}: {msg} — 자동 재연결 시작")
            QTimer.singleShot(1000, self._reconnect_flow)
            return

        self._log(f"ERR {code}: {msg}")

    def _apply_mdt(self):
        if not self.mw.connected: return
        mdt = auto_mdt(self.mw.ib)
        self.radio_delay.blockSignals(True); self.radio_live.blockSignals(True)
        self.radio_live.setChecked(mdt == 1)
        self.radio_delay.setChecked(mdt != 1)
        self.radio_delay.blockSignals(False); self.radio_live.blockSignals(False)

    def _apply_mdt_manual(self):
        """
        수동 MDT 전환.
        [v6.5-3] 전환 후 첫 틱 타입으로 실제 실시간/지연 여부 검증.
        [v6.6 ②] VIX·CL 등 지연 필수 종목은 실시간(1) 선택 시 강제 차단.
        """
        if not self.mw.connected: return

        # [v6.6 ②] 지연 필수 종목 충돌 방지
        # _DELAYED_SYMS (VIX, CL 등)는 core_fetch._mdt_for_sym에서 MDT=3 강제
        # 수동으로 실시간(1)을 선택하면 354 에러 반복 또는 데이터 미수신 발생
        try:
            from call_put_tab.core_fetch import _DELAYED_SYMS
        except ImportError:
            _DELAYED_SYMS = {"VIX", "CL"}

        cur_sym = self.edit_sym.text().strip().upper() if hasattr(self, 'edit_sym') else ""
        if self.radio_live.isChecked() and cur_sym in _DELAYED_SYMS:
            self._log(
                f"⚠ {cur_sym}은 지연(MDT=3) 필수 종목입니다 — 실시간 전환 차단. "
                f"지연 모드를 유지합니다.")
            # 라디오 버튼 원상 복원 (지연으로)
            self.radio_live.blockSignals(True)
            self.radio_delay.blockSignals(True)
            self.radio_delay.setChecked(True)
            self.radio_live.setChecked(False)
            self.radio_live.blockSignals(False)
            self.radio_delay.blockSignals(False)
            return

        mdt = 1 if self.radio_live.isChecked() else 3
        self._requested_live  = (mdt == 1)   # [v6.5-3] 검증용 플래그
        self._mdt_verify_mode = True          # [v6.5-3] 다음 틱에서 검증
        self._err354_count = 0   # reset: new MDT subscription starts fresh
        try:
            self.mw.ib.reqMarketDataType(mdt)
            self._log(f"시세모드 전환: {'실시간(1)' if mdt==1 else '지연(3)'} — 첫 틱 수신 후 검증")
        except Exception as e:
            self._log(f"MDT 전환 실패: {e}")
            self._mdt_verify_mode = False
            return
        from PyQt5.QtCore import QTimer as _QT
        _QT.singleShot(300, lambda: self._req_und(self.edit_sym.text().upper()))

    # ── SPXW 0DTE 콤보 ──────────────────────────────────────────