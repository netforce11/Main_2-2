"""
combo_ui_left.py — 복합 전략 탭: 좌측 패널
════════════════════════════════════════════════════════════════
포함:
  - LeftPanelMixin : 옵션 체인 (콜·풋) 패널 빌드
  - 체인 동기화 (_sync_chain, _auto_sync_chain, _sync_chain_from_cp)
  - 현재가 조회 (_req_sym_price)
  - 체인 클릭 → 레그 자동 입력 (_on_chain_click)

v2.3 변경:
  - 관심종목 패널 제거 (공간 확보 → 추세점수판으로 대체)
  - edit_sym_combo / lbl_sym_price / ▶현재가조회 버튼을
    _build_chain_panel() 헤더 행으로 이동
════════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit,
    QGroupBox, QMessageBox,
    QTableWidget, QHeaderView, QAbstractItemView,
    QSplitter,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from combo_constants import SPLITTER_STYLE, mk_item
from core import REQ_CALL, REQ_PUT


class LeftPanelMixin:
    """좌측 패널(옵션 체인) 빌드·로직 Mixin."""

    # ──────────────────────────────────────────────────────────
    # 빌드
    # ──────────────────────────────────────────────────────────
    def _build_left_panel(self) -> QGroupBox:
        """좌측: 옵션 체인 패널만 반환 (관심종목 제거)."""
        return self._build_chain_panel()

    # ── 옵션 체인 패널 ─────────────────────────────────────────
    def _build_chain_panel(self) -> QGroupBox:
        gb = QGroupBox("📊 옵션 체인  (콜-풋 탭 3초 동기화)")
        v  = QVBoxLayout(gb)
        v.setSpacing(3); v.setContentsMargins(4, 6, 4, 4)

        # ── 헤더 행 1: 종목 입력 + 현재가 조회 (관심종목에서 이동) ──
        sym_row = QHBoxLayout()
        sym_row.setSpacing(6)

        sym_row.addWidget(QLabel("종목:"))

        self.edit_sym_combo = QLineEdit("SPX")
        self.edit_sym_combo.setFixedHeight(24)
        self.edit_sym_combo.setStyleSheet(
            "background:#0a0a1e;color:#ffd700;border:1px solid #3a3a6a;"
            "border-radius:3px;font-weight:bold;")
        sym_row.addWidget(self.edit_sym_combo)

        btn_req = QPushButton("▶ 현재가 조회")
        btn_req.setFixedHeight(24)
        btn_req.setStyleSheet(
            "background:#1a5c2e;color:#00ff88;font-weight:bold;padding:3px 8px;")
        btn_req.clicked.connect(self._req_sym_price)
        sym_row.addWidget(btn_req)

        self.lbl_sym_price = QLabel("현재가: ―")
        self.lbl_sym_price.setFont(QFont("Arial", 12, QFont.Bold))
        self.lbl_sym_price.setStyleSheet("color:#ffd700;border:none;")
        sym_row.addWidget(self.lbl_sym_price)

        # 만기 날짜 자동 입력 필드
        sym_row.addWidget(QLabel("만기:"))
        self.edit_expiry_combo = QLineEdit()
        self.edit_expiry_combo.setFixedWidth(72)
        self.edit_expiry_combo.setFixedHeight(24)
        self.edit_expiry_combo.setPlaceholderText("YYYYMMDD")
        self.edit_expiry_combo.setReadOnly(True)
        self.edit_expiry_combo.setStyleSheet(
            "background:#0a0a1e;color:#aaffaa;border:1px solid #3a6a3a;"
            "border-radius:3px;font-size:11px;font-weight:bold;")
        self.edit_expiry_combo.setToolTip("콜-풋 탭 만기 자동 수신")
        sym_row.addWidget(self.edit_expiry_combo)
        sym_row.addStretch()

        v.addLayout(sym_row)

        # ── 헤더 행 2: 체인 심볼 표시 + 즉시 동기화 버튼 ──
        hdr = QHBoxLayout()
        self.lbl_chain_sym = QLabel("종목: ―  |  현재가: ―")
        self.lbl_chain_sym.setStyleSheet(
            "color:#ffd700;font-weight:bold;font-size:11px;border:none;")
        btn_sync = QPushButton("↺ 즉시 동기화")
        btn_sync.setFixedHeight(22)
        btn_sync.clicked.connect(self._sync_chain)
        hdr.addWidget(self.lbl_chain_sym)
        hdr.addStretch()
        hdr.addWidget(btn_sync)
        v.addLayout(hdr)

        # ── 콜/풋 체인 테이블 ──
        inner = QSplitter(Qt.Horizontal)
        inner.setHandleWidth(4)
        inner.setStyleSheet(SPLITTER_STYLE)
        inner.setChildrenCollapsible(False)
        inner.addWidget(self._build_call_chain())
        inner.addWidget(self._build_put_chain())
        inner.setSizes([300, 300])

        v.addWidget(inner, 1)
        gb.setMinimumWidth(300)
        return gb

    def _build_call_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)

        lbl = QLabel("▲ CALL")
        lbl.setStyleSheet("color:#33aaff;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)

        self.tbl_chain_call = QTableWidget(0, 3)
        self.tbl_chain_call.setHorizontalHeaderLabels(["행사가", "현재가", "IV"])
        self._apply_chain_style(self.tbl_chain_call, "#90caf9")
        self.tbl_chain_call.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "C"))

        lv.addWidget(lbl)
        lv.addWidget(self.tbl_chain_call)
        return w

    def _build_put_chain(self) -> QWidget:
        w = QWidget(); lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(1)

        lbl = QLabel("▼ PUT")
        lbl.setStyleSheet("color:#ff6666;font-weight:bold;border:none;")
        lbl.setAlignment(Qt.AlignCenter)

        self.tbl_chain_put = QTableWidget(0, 3)
        self.tbl_chain_put.setHorizontalHeaderLabels(["행사가", "현재가", "IV"])
        self._apply_chain_style(self.tbl_chain_put, "#ff9999")
        self.tbl_chain_put.cellClicked.connect(
            lambda r, c: self._on_chain_click(r, c, "P"))

        lv.addWidget(lbl)
        lv.addWidget(self.tbl_chain_put)
        return w

    @staticmethod
    def _apply_chain_style(tbl: QTableWidget, hdr_color: str):
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            "QTableWidget{background:#07070f;alternate-background-color:#0c0c20;"
            "color:#ccc;gridline-color:#1a1a3a;}"
            f"QHeaderView::section{{background:#0a0a1e;color:{hdr_color};"
            "border:1px solid #1a1a3a;font-weight:bold;}")

    # ──────────────────────────────────────────────────────────
    # 현재가 조회
    # ──────────────────────────────────────────────────────────
    def _req_sym_price(self):
        """종목 입력 → 현재가 조회.
        탭1(콜-풋) 심볼과 동일하면 캐시 즉시 사용.
        심볼이 다르면 콤보탭 전용 reqId(8500)로 직접 reqMktData 구독.
        """
        sym = self.edit_sym_combo.text().strip().upper()
        if not sym:
            return

        cp = self.mw.tab_callput

        # ── Case 1: 탭1과 심볼 동일 → 캐시 즉시 사용 ──────────
        if cp and cp.und_price and cp.edit_sym.text().strip().upper() == sym:
            price = cp.und_price
            self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
            if hasattr(self, 'edit_stock_price'):
                self.edit_stock_price.setText(f"{price:.2f}")
            self._und_price = price
            self._log(f"현재가 수신 (콜-풋탭): {sym} = {price:,.2f}")
            return

        # ── Case 2: 심볼 다름 → 직접 reqMktData 구독 ───────────
        ib = getattr(self.mw, 'ib', None)
        if not ib or not getattr(self.mw, 'connected', False):
            self._log("❌ TWS 미연결 — 먼저 연결하세요.")
            return

        REQ_COMBO_UND = 8500  # 콤보탭 전용 reqId (탭1 REQ_UND=1과 충돌 방지)

        # 심볼 변경 시 기존 구독 해지
        prev_sym = getattr(self, '_combo_und_sym', None)
        if prev_sym and prev_sym != sym:
            try:
                ib.cancelMktData(REQ_COMBO_UND)
            except Exception:
                pass
            from core import router
            router.unregister_price(self._on_combo_und_tick)
            self._log(f"🔌 이전 구독 해지: {prev_sym}")

        self._combo_und_sym = sym
        self.lbl_sym_price.setText("현재가: 조회 중…")
        self._log(f"🔍 {sym} 현재가 직접 구독 중... (REQ_ID={REQ_COMBO_UND})")

        # router에 콤보탭 전용 슬롯 등록
        from core import router
        router.register_price(REQ_COMBO_UND, REQ_COMBO_UND, self._on_combo_und_tick)

        try:
            from core_contract import make_und_contract
            contract = make_und_contract(sym)
            ib.reqMktData(REQ_COMBO_UND, contract, "", False, False, [])
        except Exception as e:
            self._log(f"❌ reqMktData 오류: {e}")

    def _on_combo_und_tick(self, rid, tt, price):
        """콤보탭 전용 기초자산 실시간 tick 수신 슬롯 (REQ_COMBO_UND=8500).

        router → 이 슬롯은 IB 백그라운드 스레드에서 호출될 수 있으므로
        Qt 위젯 접근은 QTimer.singleShot(0) 으로 메인 스레드에 위임.
        """
        if tt not in (4, 68, 75) or price <= 0:
            return
        self._und_price = price  # float 대입은 GIL로 스레드 안전

        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, lambda p=price: self._apply_und_price_ui(p))

    def _apply_und_price_ui(self, price: float):
        """메인 스레드에서 UI 위젯 갱신 (0xC0000005 크래시 방지)."""
        try:
            self.lbl_sym_price.setText(f"현재가: {price:,.2f}")
            if hasattr(self, 'edit_stock_price') and not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{price:.2f}")
        except RuntimeError:
            pass  # 위젯이 이미 소멸된 경우 무시

    # ──────────────────────────────────────────────────────────
    # 체인 동기화
    # ──────────────────────────────────────────────────────────
    def _auto_sync_chain(self):
        """3초마다 자동 동기화."""
        cp = self.mw.tab_callput
        if not cp or (not cp.call_strikes and not cp.put_strikes):
            return
        self._sync_chain_from_cp(cp, silent=True)

    def _sync_chain(self):
        """수동 동기화 버튼."""
        cp = self.mw.tab_callput
        if not cp:
            return
        if not cp.call_strikes and not cp.put_strikes:
            QMessageBox.information(self, "안내",
                "콜-풋 탭(탭1)에서 먼저 ▶ 조회 버튼을 눌러 데이터를 수신하세요.")
            return
        self._sync_chain_from_cp(cp, silent=False)

    def _sync_chain_from_cp(self, cp, silent=False):
        """콜-풋 탭 → 체인 테이블 동기화."""
        sym       = cp.edit_sym.text().strip().upper()
        und_price = cp.und_price

        header = (f"종목: {sym}  |  현재가: {und_price:,.2f}"
                  if und_price else f"종목: {sym}")
        self.lbl_chain_sym.setText(header)

        if und_price:
            self._und_price = und_price
            self.lbl_sym_price.setText(f"현재가: {und_price:,.2f}")
            if hasattr(self, 'edit_stock_price') and not self.edit_stock_price.text().strip():
                self.edit_stock_price.setText(f"{und_price:.2f}")

        # CALL 체인 갱신
        self._call_strikes = list(cp.call_strikes)
        self._chain_call   = {}
        self.tbl_chain_call.setRowCount(0)
        for i, st in enumerate(cp.call_strikes):
            rid = REQ_CALL + i
            lp  = cp.call_data.get(rid, {}).get("last")
            self._chain_call[st] = lp
            r = self.tbl_chain_call.rowCount()
            self.tbl_chain_call.insertRow(r)
            self.tbl_chain_call.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_call.setItem(r, 1, mk_item(
                f"{lp:.2f}" if lp else "―", "#33aaff"))
            self.tbl_chain_call.setItem(r, 2, mk_item("―"))

        # PUT 체인 갱신
        self._put_strikes = list(cp.put_strikes)
        self._chain_put   = {}
        self.tbl_chain_put.setRowCount(0)
        for i, st in enumerate(cp.put_strikes):
            rid = REQ_PUT + i
            lp  = cp.put_data.get(rid, {}).get("last")
            self._chain_put[st] = lp
            r = self.tbl_chain_put.rowCount()
            self.tbl_chain_put.insertRow(r)
            self.tbl_chain_put.setItem(r, 0, mk_item(f"{int(st)}", "#ffd700"))
            self.tbl_chain_put.setItem(r, 1, mk_item(
                f"{lp:.2f}" if lp else "―", "#ff6666"))
            self.tbl_chain_put.setItem(r, 2, mk_item("―"))

        # 만기 날짜 자동 수신 — 탭1의 현재 만기 읽기
        try:
            expiry_code = ""
            if hasattr(cp, '_expiry_list') and cp._expiry_list:
                idx = getattr(cp, 'combo_exp', None)
                if idx is not None:
                    ci = idx.currentIndex()
                    if 0 <= ci < len(cp._expiry_list):
                        _, expiry_code, _ = cp._expiry_list[ci]
                        if expiry_code and expiry_code != "CUSTOM":
                            pass
                        else:
                            expiry_code = getattr(cp, 'edit_custom', None)
                            if expiry_code:
                                expiry_code = expiry_code.text().strip()
            elif hasattr(cp, 'date_edit'):
                expiry_code = cp.date_edit.date().toString("yyyyMMdd")
            if expiry_code and len(expiry_code) == 8:
                lbl = f"{expiry_code[4:6]}/{expiry_code[6:8]}"
                lbl_full = f"{expiry_code[:4]}-{expiry_code[4:6]}-{expiry_code[6:8]}"
                ed = getattr(self, 'edit_expiry_combo', None)
                if ed:
                    ed.setText(expiry_code)
                    ed.setToolTip(f"만기: {lbl_full}")
                self._current_expiry = expiry_code
        except Exception:
            pass

        if not silent:
            self._log(
                f"체인 동기화: {sym}  C{len(cp.call_strikes)} / P{len(cp.put_strikes)}")

        # ★ 당일 conId 일괄 조회
        # 첫 자동 동기화(앱 시작 후 1회) 또는 수동 동기화 시에만 실행
        # 이후 3초 자동 동기화는 코드 실행 안 함
        raw_expiry = getattr(self, '_current_expiry', '')
        first_run  = not getattr(self, '_conid_bulk_done', False)
        if (not silent or first_run) and raw_expiry and (self._call_strikes or self._put_strikes):
            self._conid_bulk_done = True
            _bulk_fetch_conids(
                self, sym, raw_expiry,
                self._call_strikes, self._put_strikes)

    # ──────────────────────────────────────────────────────────
    # 체인 클릭 → 레그 자동 입력
    # ──────────────────────────────────────────────────────────
    def _on_chain_click(self, row: int, col: int, side: str):
        strikes = self._call_strikes if side == "C" else self._put_strikes
        prices  = self._chain_call   if side == "C" else self._chain_put

        if row >= len(strikes):
            return
        strike = strikes[row]
        price  = prices.get(strike)

        leg_row = self.tbl_legs.currentRow()
        if leg_row < 0:
            leg_row = 0
        if leg_row >= self.tbl_legs.rowCount():
            return

        self.tbl_legs.item(leg_row, 2).setText(side)
        self.tbl_legs.item(leg_row, 3).setText(str(int(strike)))
        if price:
            self.tbl_legs.item(leg_row, 4).setText(f"{price:.2f}")

        # 만기 자동 입력
        expiry = getattr(self, '_current_expiry', '')
        if expiry and self.tbl_legs.item(leg_row, 6):
            fmt = f"{expiry[4:6]}/{expiry[6:8]}" if len(expiry) == 8 else expiry
            self.tbl_legs.item(leg_row, 6).setText(fmt)

        price_str = f"{price:.2f}" if price else "0.00"
        self._log(f"레그{leg_row+1} 자동 입력: {side} {int(strike)}  ${price_str}")

        # ★ 방향 배너 갱신
        banner = getattr(self, 'direction_banner', None)
        if banner is not None:
            banner.refresh(self.tbl_legs)

# ── 당일 conId 일괄 조회 ────────────────────────────────────────

def _bulk_fetch_conids(self, symbol: str, expiry: str,
                       call_strikes: list, put_strikes: list):
    """
    체인 동기화 완료 시 당일 conId가 캐시에 없으면 일괄 조회.

    - data/conid_cache.json 에 오늘 날짜(YYYYMMDD) 키로 저장 여부 확인
    - 없으면 reqContractDetails 일괄 요청 (80ms 간격)
    - 진행률을 로그창에 출력, 완료 시 최종 결과 출력
    - 조회 중 중복 실행 방지 (_conid_bulk_running 플래그)
    """
    from datetime import date
    today = date.today().strftime("%Y%m%d")

    # 오늘 만기와 expiry가 일치하는 경우에만 날짜 키 체크
    # (내일만기 등 다른 만기도 저장하므로 expiry 단위로 체크)
    try:
        from combo_order_bag import _CONID_CACHE, _conid_key, _save_conid_cache
    except ImportError:
        return

    bag_sym = symbol.replace("SPXW", "SPX")

    # 이미 전부 캐시에 있으면 스킵
    all_strikes = (
        [(st, "C") for st in call_strikes] +
        [(st, "P") for st in put_strikes]
    )
    missing = [
        (st, cp) for st, cp in all_strikes
        if _conid_key(bag_sym, cp, st, expiry) not in _CONID_CACHE
    ]
    if not missing:
        self._log(f"✅ conId 캐시 완비 ({len(all_strikes)}개) — 조회 생략")
        return

    # 중복 실행 방지
    if getattr(self, '_conid_bulk_running', False):
        return
    self._conid_bulk_running = True

    ib = getattr(self.mw, 'ib', None)
    if not ib or not getattr(self.mw, 'connected', False):
        self._conid_bulk_running = False
        return

    total     = len(missing)
    done_cnt  = [0]
    saved_cnt = [0]
    base_rid  = 8900   # 8900~8979 (최대 80개)

    self._log(f"🔍 conId 일괄 조회 시작: {total}개 "
              f"(기존 캐시 {len(all_strikes)-total}개 재사용)")

    from PyQt5.QtCore import QTimer
    from core_contract import make_opt_contract

    _orig_cd     = getattr(ib, 'contractDetails',    lambda *a: None)
    _orig_cd_end = getattr(ib, 'contractDetailsEnd', lambda *a: None)
    _rid_map     = {}   # rid → (strike, cp)

    for i, (st, cp_side) in enumerate(missing):
        rid = base_rid + i
        _rid_map[rid] = (st, cp_side)

    def _on_cd(req_id, cd):
        if req_id not in _rid_map:
            return
        st, cp_side = _rid_map[req_id]
        con_id = cd.contract.conId
        if con_id > 0:
            key = _conid_key(bag_sym, cp_side, st, expiry)
            _CONID_CACHE[key] = con_id
            saved_cnt[0] += 1

    def _on_cd_end(req_id):
        if req_id not in _rid_map:
            return
        done_cnt[0] += 1
        # 진행률 로그 (10개마다 + 마지막)
        if done_cnt[0] % 10 == 0 or done_cnt[0] == total:
            self._log(f"  conId 조회 중... {done_cnt[0]}/{total}")
        if done_cnt[0] >= total:
            _save_conid_cache()
            ib.contractDetails    = _orig_cd
            ib.contractDetailsEnd = _orig_cd_end
            self._conid_bulk_running = False
            self._log(
                f"✅ conId 일괄 조회 완료: "
                f"신규 저장 {saved_cnt[0]}개 / 전체 {len(all_strikes)}개 캐시 완비")

    ib.contractDetails    = _on_cd
    ib.contractDetailsEnd = _on_cd_end

    # 80ms 간격으로 순차 요청 (IB 서버 부하 방지)
    def _send(idx):
        if idx >= total:
            return
        st, cp_side = missing[idx]
        rid = base_rid + idx
        try:
            opt = make_opt_contract(
                symbol=symbol, strike=st, right=cp_side, expiry=expiry)
            ib.reqContractDetails(rid, opt)
        except Exception as e:
            done_cnt[0] += 1
            self._log(f"  ⚠ conId 조회 오류 {cp_side}{int(st)}: {e}")
        QTimer.singleShot(80, lambda: _send(idx + 1))

    _send(0)

    # 전체 타임아웃 (total × 80ms + 10초 여유)
    def _timeout():
        if not getattr(self, '_conid_bulk_running', False):
            return
        _save_conid_cache()
        ib.contractDetails    = _orig_cd
        ib.contractDetailsEnd = _orig_cd_end
        self._conid_bulk_running = False
        self._log(
            f"⚠ conId 일괄 조회 타임아웃 — "
            f"저장 완료 {saved_cnt[0]}/{total}개")

    QTimer.singleShot(total * 80 + 10_000, _timeout)