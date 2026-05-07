"""
core_conn_expiry.py — 만기 목록 조회·Zone·행사가 계산  v6.5
CL/VIX: IBKR reqContractDetails로 실제 만기 조회
"""

from datetime import datetime, timedelta, timezone, date
from PyQt5.QtCore import QDate, QTimer
from call_put_tab.core_conn_spxw import _today_et
# core_conn_expiry.py 상단에 추가
from core import build_expiry_list

class ConnExpiryMixin:
    """만기 목록·Zone·행사가 계산. CoreConnMixin에 통합된다."""

    _REQ_EXPIRY = 8870

    # CL/VIX: IBKR에서 실시간 조회 / 나머지: 로컬 달력 계산
    _IBKR_EXPIRY_SYMS = {"CL", "VIX"}

    def _refresh_expiry_list(self):
        sym = self.edit_sym.text().strip().upper().replace("SPXW", "SPX")

        # ── CL / VIX: IBKR reqContractDetails로 실제 만기 조회 ──
        if sym in self._IBKR_EXPIRY_SYMS:
            self._fetch_expiry_from_ibkr(sym)
            return   # 콜백(_apply_ibkr_expiry)에서 combo_exp 갱신

        # ── SPX 등 기존 로컬 계산 경로 ───────────────────────────
        self._expiry_list = build_expiry_list(sym)
        self._apply_expiry_combo()

    def _fetch_expiry_from_ibkr(self, sym: str):
        """
        IBKR reqContractDetails로 CL/VIX 만기 목록을 조회한다.
        결과는 비동기 콜백(_apply_ibkr_expiry)으로 수신한다.
        """
        if not self.mw.connected or not self.mw.ib:
            self._log(f"⚠ {sym} 만기 조회 실패 — TWS 미연결")
            return

        from ibapi.contract import Contract
        # ── CL: FOP 계약 조회 시 tradingClass 없이 먼저 시도 ──
        # tradingClass="LO" 를 지정하면 일부 TWS 버전에서 0건 반환.
        # 지정하지 않으면 IBKR이 해당 심볼의 모든 FOP 만기를 반환함.
        c = Contract()
        c.symbol   = sym
        c.currency = "USD"
        if sym == "CL":
            c.secType  = "FOP"
            c.exchange = "NYMEX"
            # tradingClass 미지정 → IBKR이 LO 포함 전체 FOP 반환
        else:  # VIX
            c.secType  = "OPT"
            c.exchange = "CBOE"

        ib      = self.mw.ib
        req_id  = self._REQ_EXPIRY
        collected = []

        _orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
        _orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)

        def _on_cd(rid, cd):
            try: _orig_cd(rid, cd)
            except: pass
            if rid != req_id: return
            exp = getattr(cd.contract, 'lastTradeDateOrContractMonth', '')
            if exp and exp not in collected:
                collected.append(exp)

        def _on_cd_end(rid):
            try: _orig_cd_end(rid)
            except: pass
            if rid != req_id: return
            ib.contractDetails    = _orig_cd
            ib.contractDetailsEnd = _orig_cd_end
            if _t_out and _t_out.isActive():
                _t_out.stop()
            QTimer.singleShot(0, lambda: self._apply_ibkr_expiry(sym, collected))

        ib.contractDetails    = _on_cd
        ib.contractDetailsEnd = _on_cd_end

        # 10초 타임아웃 — contractDetailsEnd 미수신 시 강제 처리
        _t_out = QTimer(self)
        _t_out.setSingleShot(True)
        def _on_timeout():
            ib.contractDetails    = _orig_cd
            ib.contractDetailsEnd = _orig_cd_end
            if collected:
                self._log(f"⚠ {sym} 만기 조회 타임아웃 — 수신 {len(collected)}건으로 진행")
                QTimer.singleShot(0, lambda: self._apply_ibkr_expiry(sym, collected))
            else:
                # IBKR에서 아무것도 못 받은 경우 → 로컬 계산 fallback
                self._log(f"⚠ {sym} 만기 조회 실패 — 로컬 계산 만기로 대체합니다")
                QTimer.singleShot(0, lambda: self._apply_local_expiry_fallback(sym))
        _t_out.timeout.connect(_on_timeout)
        _t_out.start(15_000)   # 10→15초로 여유 확보

        self._log(f"🔍 {sym} 만기 목록 조회 중…")
        try:
            ib.reqContractDetails(req_id, c)
        except Exception as e:
            self._log(f"⚠ reqContractDetails 오류: {e}")
            ib.contractDetails    = _orig_cd
            ib.contractDetailsEnd = _orig_cd_end
            _t_out.stop()

    def _apply_ibkr_expiry(self, sym: str, raw_list: list):
        """
        IBKR 콜백에서 수집한 만기 문자열(YYYYMMDD)을
        _expiry_list 형식으로 변환하고 combo_exp에 반영한다.
        """
        today_str = _today_et().strftime("%Y%m%d")

        # YYYYMMDD 8자리만 유효, 오늘 이후만 표시
        exps = sorted({e for e in raw_list if len(e) == 8 and e >= today_str})

        if not exps:
            self._log(f"⚠ {sym} 유효 만기 없음 — 수동 날짜 입력을 사용하세요.")
            self._expiry_list = [("📅 날짜 입력", "CUSTOM", "")]
            self._apply_expiry_combo()
            return

        from datetime import datetime as _dt
        today_obj = _today_et()
        built = []
        for e in exps:
            try:
                d    = _dt.strptime(e, "%Y%m%d").date()
                diff = (d - today_obj).days
                if diff == 0:    pfx = "🔴 오늘 "
                elif diff == 1:  pfx = "내일 "
                elif diff <= 7:  pfx = f"D+{diff} "
                else:            pfx = ""
                label = pfx + d.strftime("%m/%d(%a)")
                built.append((label, e, ""))
            except Exception:
                built.append((e, e, ""))

        built.append(("📅 날짜 입력", "CUSTOM", ""))
        self._expiry_list = built
        self._apply_expiry_combo()
        self._log(f"✅ {sym} 만기 {len(exps)}건 로드 완료")

    def _apply_expiry_combo(self):
        """
        _expiry_list → combo_exp 반영 + date_edit 초기값 세팅.
        기존 _refresh_expiry_list() 하단 로직을 공통 메서드로 분리.
        SPX 경로와 CL/VIX 콜백 경로 모두 이 메서드로 마무리한다.
        """
        self.combo_exp.blockSignals(True)
        self.combo_exp.clear()
        for label, _, _ in self._expiry_list:
            self.combo_exp.addItem(label)
        self.combo_exp.blockSignals(False)

        if not self._expiry_list:
            return

        # 첫 번째 비-CUSTOM 항목을 기본 선택
        best_idx = 0
        for i, (_, code, _) in enumerate(self._expiry_list):
            if code != "CUSTOM":
                best_idx = i
                break
        self.combo_exp.setCurrentIndex(best_idx)
        _, code, _ = self._expiry_list[best_idx]

        if code == "CUSTOM":
            today = _today_et()
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(today.year, today.month, today.day))
            self.date_edit.blockSignals(False)
            self.date_edit.setVisible(True)
        else:
            try:
                y, m, d = int(code[:4]), int(code[4:6]), int(code[6:8])
                self.date_edit.blockSignals(True)
                self.date_edit.setDate(QDate(y, m, d))
                self.date_edit.blockSignals(False)
            except: pass
            self.date_edit.setVisible(False)

    def _apply_local_expiry_fallback(self, sym: str):
        """
        IBKR reqContractDetails 실패 시 로컬 계산으로 만기 목록을 구성한다.

        VIX: 매달 세 번째 수요일 30일 전의 금요일이 옵션 만기일.
             향후 6개월치 YYYYMMDD 8자리로 생성.
        CL:  매월 25일의 3영업일 전 → YYYYMMDD
        """
        from datetime import date, timedelta

        today = _today_et()

        def _third_wednesday(y: int, m: int) -> date:
            """해당 연월의 세 번째 수요일 반환."""
            d = date(y, m, 1)
            # 첫 번째 수요일
            days_to_wed = (2 - d.weekday()) % 7   # 2 = 수요일
            first_wed = d + timedelta(days=days_to_wed)
            return first_wed + timedelta(weeks=2)  # 세 번째 수요일

        def _third_friday(y: int, m: int) -> date:
            """해당 연월의 세 번째 금요일 반환."""
            d = date(y, m, 1)
            days_to_fri = (4 - d.weekday()) % 7
            first_fri = d + timedelta(days=days_to_fri)
            return first_fri + timedelta(weeks=2)

        def _vix_expiry(y: int, m: int) -> date:
            """
            VIX 옵션 만기일 계산 (CBOE 공식).
            규칙: 다음 달 세 번째 금요일(SPX 결제일) 30일 전 수요일.
            예) 5월 VIX 만기 = 6월 세 번째 금요일(6/19) - 30일 = 5/20(수)
            """
            if m == 12:
                next_y, next_m = y + 1, 1
            else:
                next_y, next_m = y, m + 1
            third_fri_next = _third_friday(next_y, next_m)
            target = third_fri_next - timedelta(days=30)
            # 가장 가까운 수요일(이전 방향, 2=수요일)
            days_back = (target.weekday() - 2) % 7
            wednesday = target - timedelta(days=days_back)
            return wednesday

        def _cl_expiry(y: int, m: int) -> date:
            """CL 만기일: 해당 월 25일의 3영업일 전."""
            d = date(y, m, 25)
            biz = 0
            while biz < 3:
                d -= timedelta(days=1)
                if d.weekday() < 5:
                    biz += 1
            return d

        exps = []
        y, m = today.year, today.month
        for _ in range(7):   # 현재 달 포함 7개월
            if sym == "VIX":
                exp_date = _vix_expiry(y, m)
                if exp_date >= today:
                    exps.append(exp_date.strftime("%Y%m%d"))
            elif sym == "CL":
                exp_date = _cl_expiry(y, m)
                if exp_date >= today:
                    exps.append(exp_date.strftime("%Y%m%d"))
            else:
                # 기타: YYYYMMDD 01일로 placeholder
                exps.append(f"{y}{m:02d}01")
            if m == 12:
                y, m = y + 1, 1
            else:
                m += 1

        if not exps:
            self._expiry_list = [("📅 날짜 입력", "CUSTOM", "")]
            self._apply_expiry_combo()
        else:
            self._apply_ibkr_expiry(sym, exps)

    def _on_exp_change(self, idx):
        _, code, _ = self._expiry_list[idx]
        self.edit_custom.setVisible(False)
        self.date_edit.setVisible(code == "CUSTOM")
        self.btn_cal.setVisible(True)

    def _open_calendar(self):
        custom_idx = next(
            (i for i,(_, c, _) in enumerate(self._expiry_list) if c == "CUSTOM"),
            len(self._expiry_list)-1)
        self.combo_exp.blockSignals(True)
        self.combo_exp.setCurrentIndex(custom_idx)
        self.combo_exp.blockSignals(False)
        self.edit_custom.setVisible(False)
        self.date_edit.setVisible(True)
        try: self.date_edit.calendarWidget()
        except: pass
        self.date_edit.setFocus()

    def _on_date_edit_changed(self, qdate):
        self.edit_custom.setText(qdate.toString("yyyyMMdd"))

    def _get_expiry(self, silent: bool = False):
        """
        현재 선택된 만기일 (code, tag) 반환.
        silent=True 또는 UI 초기화 중일 때는 QMessageBox 없이
        None 반환만 하고 로그에만 기록한다 (시작 시 랙 방지).
        """
        if not getattr(self, '_expiry_list', None):
            return None, ""

        idx = self.combo_exp.currentIndex()
        if idx < 0 or idx >= len(self._expiry_list):
            return None, ""

        _, code, tag = self._expiry_list[idx]
        if code == "CUSTOM":
            raw = (self.date_edit.date().toString("yyyyMMdd")
                   if self.date_edit.isVisible()
                   else self.edit_custom.text().strip())
            if len(raw) == 8 and raw.isdigit():
                self._current_expiry = raw   # ← chain_saver 연동용
                return raw, ""
            if not silent:
                self._log("⚠ 만기일 형식 오류 (YYYYMMDD). 날짜를 다시 선택하세요.")
            return None, ""
        self._current_expiry = code          # ← chain_saver 연동용
        return code, tag
    def _strikes_for_zone(self, atm, step, n):
        # B안: 재접속 시 ATM 이동 대비 — 양쪽 12개씩 여유 추가 (±30pt 커버)
        n = n + 12

        if self._zone == "ITM":
            return ([atm - i*step for i in range(n)],
                    [atm + i*step for i in range(n)])
        elif self._zone == "ATM":
            return ([atm + i*step for i in range(n)],
                    [atm - i*step for i in range(n)])
        else:   # OTM
            dynamic_skip_pt = atm * 0.015
            skip = max(1, round(dynamic_skip_pt / step))
            return ([atm + (skip+i)*step for i in range(n)],
                    [atm - (skip+i)*step for i in range(n)])
        # ═══════════════════════════════════════════════════════════
        # [S11] 모의/실제 모드 포트 전환 지원
        # ═══════════════════════════════════════════════════════════

        # 포트 매핑 상수