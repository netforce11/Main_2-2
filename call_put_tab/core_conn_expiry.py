"""
core_conn_expiry.py — 만기 목록 조회·Zone·행사가 계산  v6.6
CL/VIX: IBKR reqContractDetails로 실제 만기 조회
v6.6 변경:
  · _is_monthly_expiry() 유틸 추가
  · SPXW 요청 시 Monthly 만기일(매월 세 번째 금요일)은
    자동으로 SPX 로 분기하여 체인 조회 가능하게 수정
  · combo_spxw / _apply_ibkr_expiry 라벨에 [Monthly] 표기 추가
"""

from datetime import datetime, timedelta, timezone, date
from PyQt5.QtCore import QDate, QTimer
from call_put_tab.core_conn_spxw import _today_et
from call_put_tab.core_expiry_utils import _is_monthly_expiry  # 순환 의존 없는 유틸
from core import build_expiry_list

class ConnExpiryMixin:
    """만기 목록·Zone·행사가 계산. CoreConnMixin에 통합된다."""

    _REQ_EXPIRY     = 8870
    _REQ_SECDEF     = 8871   # ✅ 추가: reqSecDefOptParams용 reqId

    # CL/VIX: reqContractDetails(FOP/OPT)로 실제 만기 조회
    _IBKR_EXPIRY_SYMS = {"CL", "VIX"}

    # ✅ 추가: SPX 등 지수는 로컬 달력 계산으로 충분
    _LOCAL_EXPIRY_SYMS = {"SPX", "SPXW", "NDX", "RUT", "XSP", "DJX"}

    def _refresh_expiry_list(self):
        """
        종목별 만기 목록 조회.

        SPXW 요청이라도 날짜가 Monthly 만기(세 번째 금요일)이면
        내부적으로 SPX로 처리해야 하므로, build_expiry_list 결과의
        각 날짜를 검사해 Monthly 항목에 [Monthly/SPX] 태그를 부여한다.
        실제 체인 조회(edit_sym 설정)는 core_conn_spxw._on_spxw_select()
        에서 _is_monthly_expiry()로 분기한다.
        """
        raw_sym = self.edit_sym.text().strip().upper()
        sym     = raw_sym.replace("SPXW", "SPX")

        # ── CL / VIX: IBKR reqContractDetails로 실제 만기 조회 ──
        if sym in self._IBKR_EXPIRY_SYMS:
            self._fetch_expiry_from_ibkr(sym)
            return   # 콜백(_apply_ibkr_expiry)에서 combo_exp 갱신

        # ── SPX/SPXW 등 지수: 기존 로컬 달력 계산 ──────────────
        if sym in self._LOCAL_EXPIRY_SYMS:
            self._expiry_list = build_expiry_list(sym)
            # SPXW 요청이거나 Monthly pending 플래그가 설정된 경우 태깅
            # (Monthly 만기일에 edit_sym="SPX"로 바뀐 뒤 호출되는 경우 포함)
            if raw_sym == "SPXW" or getattr(self, '_spxw_monthly_pending', False):
                self._expiry_list = self._tag_monthly_expiries(self._expiry_list)
            self._apply_expiry_combo()
            return

        # ✅ 추가: 개별 종목(AAPL, TSLA 등) → reqSecDefOptParams 조회
        # 위클리/월간 만기를 IBKR에서 실제로 가져옴
        if self.mw.connected and self.mw.ib:
            self._fetch_expiry_secdef(sym)
        else:
            # TWS 미연결 시 로컬 달력 fallback
            self._expiry_list = build_expiry_list(sym)
            self._apply_expiry_combo()

    def _tag_monthly_expiries(self, expiry_list: list) -> list:
        """
        _expiry_list 항목 중 Monthly 만기(세 번째 금요일)에
        라벨 뒤에 "[Monthly]" 표기와 태그 "MONTHLY"를 부여해 반환.

        반환 형식: [(label, code, tag), ...]
          tag == "MONTHLY"  → _on_spxw_select()에서 edit_sym="SPX" 로 분기
          tag == ""         → 일반 SPXW
        """
        result = []
        for label, code, tag in expiry_list:
            if code not in ("CUSTOM",) and len(code) == 8 and code.isdigit():
                if _is_monthly_expiry(code):
                    label = label + "  [Monthly]"
                    tag   = "MONTHLY"
            result.append((label, code, tag))
        return result

    def _fetch_expiry_secdef(self, sym: str):
        """
        ✅ 신규: reqSecDefOptParams 로 개별 종목(STK) 옵션 만기 목록 조회.

        - reqContractDetails 와 달리 파생상품 파라미터(만기 목록, 행사가 목록)를
          한 번에 반환하므로 STK 옵션에 훨씬 빠르고 정확함.
        - 위클리/월간 구분 없이 IBKR이 실제 거래 가능한 모든 만기를 반환.
        - secDefOptParams 콜백: (reqId, underlyingSymbol, futFopExchange,
                                 underlyingSecType, underlyingConId,
                                 expirations, strikes)
          expirations: frozenset of "YYYYMMDD" strings
        """
        self._log(f"🔍 {sym} 옵션 만기 조회 중… (STK)")

        ib     = self.mw.ib
        req_id = self._REQ_SECDEF
        collected_exps = []

        _orig_sdop    = getattr(ib, 'securityDefinitionOptionParameter',    lambda *a: None)
        _orig_sdop_end = getattr(ib, 'securityDefinitionOptionParameterEnd', lambda *a: None)

        def _on_sdop(rid, underlyingSym, futFopExchange, underlyingSecType,
                     underlyingConId, expirations, strikes):
            try: _orig_sdop(rid, underlyingSym, futFopExchange,
                            underlyingSecType, underlyingConId, expirations, strikes)
            except Exception: pass
            if rid != req_id:
                return
            # expirations은 frozenset 또는 set
            for exp in expirations:
                if exp and exp not in collected_exps:
                    collected_exps.append(exp)

        def _on_sdop_end(rid):
            try: _orig_sdop_end(rid)
            except Exception: pass
            if rid != req_id:
                return
            ib.securityDefinitionOptionParameter    = _orig_sdop
            ib.securityDefinitionOptionParameterEnd = _orig_sdop_end
            if _t_out and _t_out.isActive():
                _t_out.stop()
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, lambda: self._apply_ibkr_expiry(sym, collected_exps))

        ib.securityDefinitionOptionParameter    = _on_sdop
        ib.securityDefinitionOptionParameterEnd = _on_sdop_end

        # 10초 타임아웃
        _t_out = QTimer(self)
        _t_out.setSingleShot(True)
        def _on_timeout():
            ib.securityDefinitionOptionParameter    = _orig_sdop
            ib.securityDefinitionOptionParameterEnd = _orig_sdop_end
            if collected_exps:
                self._log(f"⚠ {sym} 만기 조회 타임아웃 — 수신 {len(collected_exps)}건으로 진행")
                from PyQt5.QtCore import QTimer as _QT
                _QT.singleShot(0, lambda: self._apply_ibkr_expiry(sym, collected_exps))
            else:
                self._log(f"⚠ {sym} 만기 조회 실패 — 로컬 계산으로 대체")
                from PyQt5.QtCore import QTimer as _QT
                _QT.singleShot(0, lambda: self._apply_local_expiry_fallback(sym))
        _t_out.timeout.connect(_on_timeout)
        _t_out.start(10_000)

        try:
            # conId=0, exchange="", includeExpired=False
            ib.reqSecDefOptParams(req_id, sym, "", "STK", 0)
        except Exception as e:
            self._log(f"⚠ reqSecDefOptParams 오류: {e}")
            ib.securityDefinitionOptionParameter    = _orig_sdop
            ib.securityDefinitionOptionParameterEnd = _orig_sdop_end
            _t_out.stop()
            # fallback: 로컬 달력 계산
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
        SPXW 요청 컨텍스트에서는 Monthly 만기 항목에 [Monthly] 태그 부여.
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

        # SPXW 요청 컨텍스트 여부 확인 (edit_sym 현재값 기준)
        is_spxw_ctx = (
            getattr(self, 'edit_sym', None) is not None
            and self.edit_sym.text().strip().upper() == "SPXW"
        )

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
                # SPXW 컨텍스트에서 Monthly 만기 표기
                if is_spxw_ctx and _is_monthly_expiry(e):
                    label += "  [Monthly]"
                    tag = "MONTHLY"
                else:
                    tag = ""
                built.append((label, e, tag))
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

        tag 값:
          ""         : 일반 만기 (SPXW 티커로 조회)
          "MONTHLY"  : Monthly 만기(세 번째 금요일) → SPX 티커로 조회해야 함
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
                # CUSTOM 날짜도 Monthly 여부 체크
                custom_tag = "MONTHLY" if _is_monthly_expiry(raw) else ""
                return raw, custom_tag
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

    # ═══════════════════════════════════════════════════════════════
    # core_conn_spxw.py 의 _on_spxw_select() 수정 가이드
    # ═══════════════════════════════════════════════════════════════
    #
    # combo_spxw 에서 날짜를 선택할 때 Monthly 만기이면 edit_sym="SPX",
    # 그 외에는 "SPXW" 로 설정해야 체인 조회가 정상 동작한다.
    #
    # core_conn_spxw.py 의 _on_spxw_select() 안에 아래 로직을 적용:
    #
    #   from call_put_tab.core_conn_expiry import _is_monthly_expiry
    #
    #   def _on_spxw_select(self, idx: int) -> None:
    #       date_str = self.combo_spxw.itemData(idx)   # "YYYYMMDD"
    #       if not date_str:
    #           return
    #       # Monthly 만기(세 번째 금요일)는 SPX, 나머지는 SPXW
    #       sym = "SPX" if _is_monthly_expiry(date_str) else "SPXW"
    #       self.edit_sym.setText(sym)
    #       # combo_exp → CUSTOM + date_edit 설정 (기존 로직 그대로 유지)
    #       ...
    #
    # ───────────────────────────────────────────────────────────────
    # _fetch() 내부에서 _get_expiry() 의 tag 를 활용하는 방법 (대안):
    #
    #   expiry, tag = self._get_expiry()
    #   if tag == "MONTHLY":
    #       sym = "SPX"
    #   elif self.edit_sym.text().strip().upper() == "SPXW":
    #       sym = "SPXW"
    #   else:
    #       sym = self.edit_sym.text().strip().upper()
    #
    # ═══════════════════════════════════════════════════════════════