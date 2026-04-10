"""
core_fetch_pos.py — 포지션 조회 / 잔고 컬럼 갱신  v1.4
════════════════════════════════════════════════════
포함 메서드:
  _refresh_positions()
  _apply_positions()
  _update_pos_pnl()
  _start_server_pnl()       ← NEW v1.4  reqPnLSingle 구독
  _stop_server_pnl()        ← NEW v1.4  cancelPnLSingle 전체 해제
  _on_pnl_mode_changed()    ← NEW v1.4  체크박스 토글 핸들러
  _on_pos_reconnect_hook()

v1.1: positionEnd 타임아웃 / 재연결 훅 / 튜플람다→def
v1.2: tbl_positions 필터 완화 / _normalize_sym / 길이 방어
v1.3: sym_label "SPX 0410 C" / 5컬럼 / _update_pos_pnl 로컬계산
v1.4: 서버 PnL 모드 (reqPnLSingle) 추가
      체크박스 `chk_server_pnl` ON  → IBKR reqPnLSingle 구독, 콜백이 col=4 갱신
      체크박스 `chk_server_pnl` OFF → cancelPnLSingle 후 로컬계산(_update_pos_pnl)

════════════════════════════════════════════════════
[tab_options_price.py / order_panel_util.py 수정 가이드]

1) 테이블 5컬럼으로 확장 (v1.3과 동일):
   self.tbl_positions = QTableWidget(0, 5)
   self.tbl_positions.setHorizontalHeaderLabels(
       ["종목·만기·CP", "행사가", "수량", "평균가", "평가손익"])
   self.tbl_positions.setColumnWidth(0, 110)

2) 패널 하단에 PnL 모드 체크박스 추가 (v1.4 신규):
   from PyQt5.QtWidgets import QCheckBox
   self.chk_server_pnl = QCheckBox("서버 PnL (실시간)")
   self.chk_server_pnl.setChecked(True)          # 기본값: 서버 모드
   self.chk_server_pnl.setStyleSheet(
       "color:#90caf9;font-size:12px;")
   self.chk_server_pnl.toggled.connect(self._on_pnl_mode_changed)
   v.addWidget(self.chk_server_pnl)               # v = 패널의 QVBoxLayout

   ※ chk_server_pnl 이 없으면 항상 로컬계산 모드로 동작합니다.
════════════════════════════════════════════════════
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
from PyQt5.QtCore import QTimer

_MULTIPLIER = 100   # SPX/SPXW 옵션 승수 (평가손익 로컬 계산용)


def _normalize_sym(sym: str) -> str:
    return sym.upper().replace("SPXW", "SPX").replace("NANOS", "SPX")


def _fmt_expiry_short(expiry8: str) -> str:
    """'20260410' → '0410'."""
    return expiry8[4:] if len(expiry8) >= 8 else expiry8


class CoreFetchPosMixin:
    """포지션 조회 전용 Mixin. CoreFetchMixin에 포함된다."""

    # ── 내부 상태 ────────────────────────────────────────────────────────────
    # _pnl_req_ids : { key(tuple) → reqId(int) }  — 구독 중인 reqPnLSingle 목록
    # _pos_snapshot: { key(tuple) → {qty, avg} }  — _apply_positions 에서 채워짐

    # ── _refresh_positions ───────────────────────────────────────────────────

    def _refresh_positions(self):
        """IBKR reqPositions() → 콜-풋 테이블 잔고 컬럼(col=6) + 잔고 패널 갱신."""
        if not self.mw.connected:
            return
        if getattr(self, '_pos_request_in_progress', False):
            self._log("⚠ 포지션 조회 이미 진행 중 — 중복 호출 무시")
            return
        self._pos_request_in_progress = True
        ib = self.mw.ib
        self._ensure_pnl_checkbox()

        _pos_buf     = {}
        _avg_buf     = {}
        _con_id_buf  = {}
        _sym_raw_buf = {}
        _end_called  = [False]

        def _flush():
            if _end_called[0]:
                return
            _end_called[0] = True
            combined = {
                "_avg_cost_map": dict(_avg_buf),
                "_con_id_map":   dict(_con_id_buf),
                "_sym_raw_map":  dict(_sym_raw_buf),
                **dict(_pos_buf),
            }
            # ✅ singleShot 대신 직접 호출 — GC 소멸 방지
            self._apply_positions(combined)

        def _on_position(account, contract, pos, avg_cost):
            sec     = getattr(contract, 'secType', '')
            raw_sym = getattr(contract, 'symbol', '')
            if sec not in ('OPT', 'FOP'):
                self._log(f"  skip secType={sec} sym={raw_sym}")
                return
            raw_expiry = getattr(contract, 'lastTradeDateOrContractMonth', '')
            expiry_key = raw_expiry[:8] if len(raw_expiry) >= 8 else raw_expiry
            key = (
                _normalize_sym(raw_sym),
                getattr(contract, 'right', ''),
                int(getattr(contract, 'strike', 0)),
                expiry_key,
            )
            _pos_buf[key]     = int(pos)
            _avg_buf[key]     = avg_cost
            _con_id_buf[key]  = getattr(contract, 'conId', None)
            _sym_raw_buf[key] = raw_sym.upper()
            self._log(f"  ✔ 포지션 수신: {raw_sym} {getattr(contract,'right','')} "
                      f"{getattr(contract,'strike','')} × {int(pos)}")

        def _on_position_end():
            self._log("  positionEnd 수신 — flush 실행")
            _flush()
            _restore_pos_handlers()

        def _restore_pos_handlers():
            ib.position    = ib._orig_position
            ib.positionEnd = ib._orig_positionEnd
            self._pos_request_in_progress = False

        def _timeout_flush():
            if not _end_called[0]:
                self._log("⚠ positionEnd 미수신 — 타임아웃으로 잔고 강제 반영")
                _flush()
            _restore_pos_handlers()

        ib._orig_position    = getattr(ib, 'position',    lambda *a: None)
        ib._orig_positionEnd = getattr(ib, 'positionEnd', lambda: None)
        ib.position    = _on_position
        ib.positionEnd = _on_position_end

        try:
            ib.reqPositions()
        except Exception as e:
            self._log(f"⚠ 포지션 조회 오류: {e}")
            _restore_pos_handlers()
            return

        # ✅ self에 타이머 붙여서 GC 소멸 방지
        if not hasattr(self, '_pos_timeout_timer'):
            from PyQt5.QtCore import QTimer as _QT
            self._pos_timeout_timer = _QT(self)
            self._pos_timeout_timer.setSingleShot(True)
        else:
            try:
                self._pos_timeout_timer.timeout.disconnect()
            except Exception:
                pass
        self._pos_timeout_timer.timeout.connect(_timeout_flush)
        self._pos_timeout_timer.start(3000)

    # ── _on_pos_reconnect_hook ───────────────────────────────────────────────

    def _on_pos_reconnect_hook(self):
        if not self.mw.connected:
            return
        self._log("🔄 재연결 감지 — 잔고 자동 재조회")
        self._refresh_positions()

    # ── _ensure_pnl_checkbox ────────────────────────────────────────────────

    def _ensure_pnl_checkbox(self):
        """tbl_positions 부모 레이아웃에 chk_server_pnl 체크박스가 없으면 자동 추가.

        order_panel_util.py 를 수정하지 않아도 됩니다.
        _refresh_positions() 첫 호출 시 자동으로 한 번만 실행됩니다.
        """
        if hasattr(self, 'chk_server_pnl'):
            return
        if not hasattr(self, 'tbl_positions'):
            return
        try:
            from PyQt5.QtWidgets import QCheckBox, QVBoxLayout
            chk = QCheckBox("서버 PnL (실시간)")
            chk.setChecked(True)
            chk.setStyleSheet("color:#90caf9;font-size:12px;margin-top:4px;")
            chk.toggled.connect(self._on_pnl_mode_changed)
            self.chk_server_pnl = chk

            # tbl_positions 의 부모 위젯 레이아웃에 삽입
            parent = self.tbl_positions.parentWidget()
            if parent and parent.layout():
                parent.layout().addWidget(chk)
            self._log("✅ PnL 모드 체크박스 자동 추가됨")
        except Exception as e:
            self._log(f"⚠ 체크박스 자동 추가 실패: {e}")

    # ── _apply_positions ─────────────────────────────────────────────────────

    def _apply_positions(self, pos_buf: dict):
        """포지션 데이터를 콜-풋 테이블(col=6) + 잔고 패널에 반영.

        tbl_positions 컬럼 (5개):
          0: 종목·만기·CP  ("SPX 0410 C")
          1: 행사가
          2: 수량
          3: 평균가
          4: 평가손익  ← 이 메서드 완료 후 _start_server_pnl 또는 _update_pos_pnl 이 채움
        """
        try:
            from tab_options import _mk
        except Exception as e:
            self._log(f"⚠ _apply_positions: _mk 임포트 실패 → {e}")
            return

        try:
            avg_cost_map  = pos_buf.get('_avg_cost_map', {})
            con_id_map    = pos_buf.get('_con_id_map',   {})
            sym_raw_map   = pos_buf.get('_sym_raw_map',  {})

            # 기존 서버 PnL 구독 해제
            try:
                self._stop_server_pnl()
            except Exception:
                pass

            # 콜-풋 테이블 잔고 컬럼 전체 초기화 (체인 테이블이 있을 때만)
            if hasattr(self, 'tbl_call'):
                for r in range(self.tbl_call.rowCount()):
                    self.tbl_call.setItem(r, 6, _mk("―", "#aaaaaa"))
            if hasattr(self, 'tbl_put'):
                for r in range(self.tbl_put.rowCount()):
                    self.tbl_put.setItem(r, 6, _mk("―", "#aaaaaa"))

            if hasattr(self, 'tbl_positions'):
                self.tbl_positions.setRowCount(0)

            self._pos_snapshot = {}

            # screen_sym / screen_expiry — 체인 테이블 매핑용 (없어도 패널은 동작)
            try:
                screen_sym    = _normalize_sym(self.edit_sym.text().strip())
                expiry, _     = self._get_expiry()
                screen_expiry = expiry[:8] if expiry and len(expiry) >= 8 else (expiry or "")
            except Exception:
                screen_sym    = ""
                screen_expiry = ""

            chain_found = 0
            pos_found   = 0

            for key, qty in pos_buf.items():
                if not isinstance(key, tuple):
                    continue
                p_sym, p_right, p_strike, p_expiry = key
                if qty == 0:
                    continue

                avg    = avg_cost_map.get(key, 0)
                con_id = con_id_map.get(key)
                color  = "#00ff88" if qty > 0 else "#ff6666"

                sym_raw = sym_raw_map.get(key, "")  # "NANOS", "SPXW" 등 IB 원본 심볼
                self._pos_snapshot[key] = {"qty": qty, "avg": avg, "con_id": con_id, "sym_raw": sym_raw}

                # [A] 콜-풋 테이블 col=6 갱신 (화면 sym·expiry 필터)
                if (screen_sym and p_sym == screen_sym
                        and screen_expiry and p_expiry == screen_expiry
                        and hasattr(self, 'tbl_call') and hasattr(self, 'tbl_put')):
                    try:
                        tbl     = self.tbl_call if p_right == 'C' else self.tbl_put
                        strikes = self.call_strikes if p_right == 'C' else self.put_strikes
                        for r, st in enumerate(strikes):
                            if int(st) == p_strike:
                                tbl.setItem(r, 6, _mk(str(qty), color))
                                break
                        chain_found += 1
                    except Exception:
                        pass

                # [B] 잔고 패널 — 모든 OPT/FOP 포지션
                if hasattr(self, 'tbl_positions'):
                    try:
                        row = self.tbl_positions.rowCount()
                        self.tbl_positions.insertRow(row)

                        cp_color = "#33aaff" if p_right == "C" else "#ff6666"
                        cp_label = "C" if p_right == "C" else "P"

                        self.tbl_positions.setItem(row, 0, _mk(cp_label,      cp_color))
                        self.tbl_positions.setItem(row, 1, _mk(str(p_strike), "#ffd700"))
                        self.tbl_positions.setItem(row, 2, _mk(str(qty),      color))
                        self.tbl_positions.setItem(
                            row, 3, _mk(f"{avg:.2f}" if avg else "―", "#aaaaaa"))
                        self.tbl_positions.setItem(row, 4, _mk("⏳", "#555555"))

                        pos_found += 1
                    except Exception as e:
                        self._log(f"⚠ tbl_positions 행 삽입 오류 (key={key}): {e}")

            if pos_found:
                self._log(f"📊 잔고 갱신: 패널={pos_found}개 / 체인={chain_found}개 반영")
                use_server = getattr(
                    getattr(self, 'chk_server_pnl', None), 'isChecked', lambda: False)()
                if use_server:
                    self._start_server_pnl()
                else:
                    self._update_pos_pnl()
            else:
                self._log("📊 보유 포지션 없음 (수신된 OPT/FOP 포지션 0개)")

        except Exception as e:
            self._log(f"⚠ _apply_positions 예외: {e}")

    # ── _on_pnl_mode_changed ─────────────────────────────────────────────────

    def _on_pnl_mode_changed(self, checked: bool):
        """체크박스 토글 핸들러.

        체크 ON  → 서버 PnL 구독 시작 (reqPnLSingle)
        체크 OFF → 서버 구독 해제 후 로컬 계산으로 즉시 갱신
        """
        if checked:
            self._log("🔀 PnL 모드: 서버 실시간 (reqPnLSingle)")
            self._start_server_pnl()
        else:
            self._log("🔀 PnL 모드: 로컬 계산 (bid/ask 중간값)")
            self._stop_server_pnl()
            self._update_pos_pnl()

    # ── _start_server_pnl ────────────────────────────────────────────────────

    def _start_server_pnl(self):
        """_pos_snapshot 의 각 포지션에 대해 reqPnLSingle 구독 시작.

        IBKR API 동작:
          reqPnLSingle(reqId, account, modelCode, conId)
          → pnlSingle(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value) 콜백

        account : self.mw.account_id (str)  ← MainWindow 에 저장된 계좌번호
        conId   : contract.conId  ← _pos_snapshot 에 저장된 contract 오브젝트 필요

        ⚠ 현재 _pos_snapshot 에는 conId 가 없습니다.
          _on_position 콜백에서 contract 오브젝트 전체를 저장해야 합니다.
          아래 _on_position 수정 예시를 참고하세요.

        conId 가 없는 포지션은 로컬 계산(_update_pos_pnl_single)으로 폴백합니다.
        """
        if not self.mw.connected:
            return
        if not hasattr(self, '_pos_snapshot') or not self._pos_snapshot:
            return

        ib      = self.mw.ib
        account = getattr(self.mw, 'account_id', '')

        # account_id 미설정 시 ib.managedAccounts 에서 자동 탐색
        if not account:
            try:
                accts = getattr(ib, 'managedAccounts', None)
                if callable(accts):
                    accts = accts()
                if isinstance(accts, str) and accts.strip():
                    account = accts.strip().split(',')[0].strip()
                elif isinstance(accts, (list, tuple)) and accts:
                    account = str(accts[0]).strip()
                if account:
                    self.mw.account_id = account
                    self._log(f"✅ account_id 자동 설정: {account}")
            except Exception:
                pass

        if not account:
            self._log("⚠ account_id 미설정 — 로컬 계산으로 폴백")
            self._update_pos_pnl()
            return

        # 기존 구독 ID 맵 초기화
        if not hasattr(self, '_pnl_req_ids'):
            self._pnl_req_ids = {}

        # 기존 콜백 보존 (reqId → row_idx 를 클로저로 처리하므로 원본 복원 필요)
        orig_pnl_single = getattr(ib, 'pnlSingle', lambda *a: None)
        ib._orig_pnl_single = orig_pnl_single

        # reqId → (key, row_idx) 역매핑 테이블
        req_to_row: Dict[int, tuple] = {}

        snapshot_items = list(self._pos_snapshot.items())

        def _on_pnl_single(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value):
            """IBKR pnlSingle 콜백 — col=4 평가손익 갱신."""
            entry = req_to_row.get(reqId)
            if entry is None:
                return
            key, row_idx = entry
            if not hasattr(self, 'tbl_positions'):
                return
            if row_idx >= self.tbl_positions.rowCount():
                return

            from tab_options import _mk
            # unrealizedPnL: float (달러 단위, IBKR가 이미 multiplier 반영해서 줌)
            pnl = unrealizedPnL
            if pnl is None or pnl != pnl:   # NaN 방어
                return
            if pnl > 0:
                pnl_text, pnl_color = f"+${pnl:,.0f}", "#00ff88"
            elif pnl < 0:
                pnl_text, pnl_color = f"-${abs(pnl):,.0f}", "#ff4444"
            else:
                pnl_text, pnl_color = "$0", "#888888"

            self.tbl_positions.setItem(row_idx, 4, _mk(pnl_text, pnl_color))

        ib.pnlSingle = _on_pnl_single

        # 각 포지션에 reqPnLSingle 요청
        for row_idx, (key, info) in enumerate(snapshot_items):
            con_id = info.get('con_id')   # _on_position 에서 저장된 conId
            if not con_id:
                # conId 없으면 로컬 계산으로 해당 행만 폴백
                self._update_pos_pnl_single(row_idx, key, info)
                continue

            # reqId 발급 — _next_req_id 없는 환경 대비 자체 카운터
            req_id = self._pnl_req_ids.get(key)
            if req_id is None:
                if not hasattr(self, '_pnl_req_id_counter'):
                    self._pnl_req_id_counter = 9900  # PnL 전용 reqId 범위
                req_id = self._pnl_req_id_counter
                self._pnl_req_id_counter += 1
                self._pnl_req_ids[key] = req_id

            req_to_row[req_id] = (key, row_idx)

            try:
                ib.reqPnLSingle(req_id, account, "", con_id)
            except Exception as e:
                self._log(f"⚠ reqPnLSingle 오류 (row={row_idx}): {e}")
                self._update_pos_pnl_single(row_idx, key, info)

        self._log(f"📡 서버 PnL 구독: {len(req_to_row)}개 포지션")

    # ── _stop_server_pnl ─────────────────────────────────────────────────────

    def _stop_server_pnl(self):
        """구독 중인 모든 reqPnLSingle 취소 및 콜백 복원."""
        ib = getattr(getattr(self, 'mw', None), 'ib', None)
        connected = getattr(getattr(self, 'mw', None), 'connected', False)

        req_ids = getattr(self, '_pnl_req_ids', {})
        for key, req_id in list(req_ids.items()):
            if connected and ib:
                try:
                    ib.cancelPnLSingle(req_id)
                except Exception:
                    pass
        self._pnl_req_ids = {}

        # 원본 콜백 복원
        if ib:
            orig = getattr(ib, '_orig_pnl_single', None)
            if orig is not None:
                ib.pnlSingle = orig
                del ib._orig_pnl_single

    # ── _update_pos_pnl (로컬 계산 — 전체) ──────────────────────────────────

    def _update_pos_pnl(self):
        """잔고 패널 col=4 평가손익 갱신 (로컬 계산 모드).

        현재가 탐색 우선순위:
          1순위 — tbl_call/put 의 bid·ask 중간값 (col 0=행사가, col 1=bid, col 2=ask 가정)
          2순위 — self._price_cache.get(key)
          3순위 — "―"

        평가손익 = (현재가 − 평균매입가) × 수량 × 100
        """
        if not hasattr(self, 'tbl_positions') or not hasattr(self, '_pos_snapshot'):
            return
        if self.tbl_positions.rowCount() == 0:
            return

        screen_sym    = _normalize_sym(self.edit_sym.text().strip())
        expiry, _     = self._get_expiry()
        screen_expiry = expiry[:8] if expiry and len(expiry) >= 8 else (expiry or "")
        price_cache   = getattr(self, '_price_cache', {})

        def _mid_from_chain(table, strike: int):
            for r in range(table.rowCount()):
                st_item = table.item(r, 0)
                if st_item is None:
                    continue
                try:
                    if int(st_item.text()) == strike:
                        b = table.item(r, 1)
                        a = table.item(r, 2)
                        if b and a:
                            bv, av = float(b.text()), float(a.text())
                            if bv > 0 and av > 0:
                                return (bv + av) / 2.0
                except (ValueError, TypeError):
                    pass
            return None

        for row_idx, (key, info) in enumerate(self._pos_snapshot.items()):
            if row_idx >= self.tbl_positions.rowCount():
                break
            p_sym, p_right, p_strike, p_expiry = key
            cur_price = None
            if p_sym == screen_sym and p_expiry == screen_expiry:
                tbl = self.tbl_call if p_right == 'C' else self.tbl_put
                cur_price = _mid_from_chain(tbl, p_strike)
            if cur_price is None:
                cur_price = price_cache.get(key)
            self._update_pos_pnl_single(row_idx, key, info, cur_price)

        self._log("💹 평가손익 갱신 완료 (로컬 계산)")

    # ── _update_pos_pnl_single (로컬 계산 — 단일 행) ────────────────────────

    def _update_pos_pnl_single(self, row_idx: int, key: tuple,
                               info: dict, cur_price: Optional[float] = None):
        """단일 행의 평가손익을 로컬 계산으로 갱신.

        서버 PnL 모드에서 conId 미보유 포지션의 폴백으로도 사용됨.
        cur_price 가 None 이면 price_cache 에서 재탐색.
        """
        from tab_options import _mk
        if not hasattr(self, 'tbl_positions'):
            return
        if row_idx >= self.tbl_positions.rowCount():
            return

        qty = info["qty"]
        avg = info["avg"]

        if cur_price is None:
            cur_price = getattr(self, '_price_cache', {}).get(key)

        if cur_price is not None and avg:
            pnl = (cur_price - avg) * qty * _MULTIPLIER
            if pnl > 0:
                pnl_text, pnl_color = f"+${pnl:,.0f}", "#00ff88"
            elif pnl < 0:
                pnl_text, pnl_color = f"-${abs(pnl):,.0f}", "#ff4444"
            else:
                pnl_text, pnl_color = "$0", "#888888"
        elif cur_price is not None:
            pnl_text, pnl_color = f"@{cur_price:.2f}", "#aaaaaa"
        else:
            pnl_text, pnl_color = "―", "#555555"

        self.tbl_positions.setItem(row_idx, 4, _mk(pnl_text, pnl_color))