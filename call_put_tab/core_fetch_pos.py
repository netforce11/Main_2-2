"""
core_fetch_pos.py — 포지션 조회 / 잔고 컬럼 갱신  v1.6

[v1.6 수정]
  ① _pnl_req_id_counter 재연결 시 리셋 (_on_pos_reconnect_hook):
    - 기존: 카운터가 세션 재시작 없이 누적 → reqId 범위(9900~) 무한 증가
    - 수정: _on_pos_reconnect_hook 호출 전 카운터 초기화
    - _stop_server_pnl()에서 _pnl_req_ids 딕셔너리도 함께 초기화

[버그 #4 수정] 실시간 잔고 엉킴 3가지 원인 수정:
  (A) _refresh_positions(): 중복 호출 레이스 — 2초 cooling 추가
  (B) _refresh_positions(): 핸들러 복원 실패 — 이중 복원 방지 + try-finally
  (C) _start_server_pnl(): req_to_row → self._pnl_req_to_row (instance 변수)
  (D) _stop_server_pnl(): self._pnl_req_to_row = {} 추가 (in-flight 콜백 무효화)
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QBrush, QColor

_MULTIPLIER = 100


def _normalize_sym(sym: str) -> str:
    return sym.upper().replace("SPXW", "SPX").replace("NANOS", "SPX")


def _fmt_expiry_short(expiry8: str) -> str:
    return expiry8[4:] if len(expiry8) >= 8 else expiry8


class CoreFetchPosMixin:
    """포지션 조회 전용 Mixin. CoreFetchMixin에 포함된다."""

    @staticmethod
    def _is_expired(expiry_str: str) -> bool:
        try:
            import pytz
            from datetime import datetime as _dt
            clean = expiry_str.replace("-", "")
            if len(clean) < 8:
                return False
            exp_date = _dt.strptime(clean[:8], "%Y%m%d").date()
            et_tz    = pytz.timezone("America/New_York")
            today_et = _dt.now(et_tz).date()
            return exp_date < today_et
        except Exception:
            return False

    @staticmethod
    def _calc_expiry_pnl(qty: int, avg_cost: float) -> float:
        if qty < 0:
            return abs(qty) * avg_cost * 100.0
        else:
            return -qty * avg_cost * 100.0

    # ── _refresh_positions ───────────────────────────────────────────────────

    def _refresh_positions(self):
        """
        [버그 #4 수정] IBKR reqPositions() → 콜-풋 테이블 잔고 컬럼(col=6) + 잔고 패널 갱신.

        수정 (A): 2초 cooling — 직전 완료 후 2초 미경과 시 재시도 예약
        수정 (B): 핸들러 복원 이중 방지 + try-finally 보강
        """
        if not self.mw.connected:
            return

        # ── [#4-A] 중복 호출 플래그 ───────────────────────────────
        if getattr(self, '_pos_request_in_progress', False):
            self._log("⚠ 포지션 조회 이미 진행 중 — 중복 호출 무시")
            return

        # ── [#4-A] cooling 체크 (직전 완료 후 2초) ───────────────
        now      = time.monotonic()
        last_end = getattr(self, '_pos_last_end_ts', 0)
        if now - last_end < 2.0:
            self._log("⚠ 잔고 조회 쿨다운 중 — 2초 후 재시도")
            QTimer.singleShot(2000, self._refresh_positions)
            return

        self._pos_request_in_progress = True
        ib = self.mw.ib
        self._ensure_pnl_checkbox()

        _pos_buf           = {}
        _avg_buf           = {}
        _con_id_buf        = {}
        _sym_raw_buf       = {}
        _end_called        = [False]
        _handlers_restored = [False]   # [#4-B] 이중 복원 방지

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
            # ── [#4-B] 이중 복원 방지 ─────────────────────────────
            if _handlers_restored[0]:
                return
            _handlers_restored[0] = True

            # cooling 기준 시각 갱신
            self._pos_last_end_ts = time.monotonic()

            # ── [#4-B] try-finally 로 반드시 플래그 해제 ─────────
            try:
                ib.position    = ib._orig_position
                ib.positionEnd = ib._orig_positionEnd
            except Exception as e:
                self._log(f"⚠ 포지션 핸들러 복원 오류: {e}")
            finally:
                self._pos_request_in_progress = False

            # 타임아웃 타이머 중지
            try:
                t = getattr(self, '_pos_timeout_timer', None)
                if t:
                    t.stop()
            except Exception:
                pass

        def _timeout_flush():
            if not _end_called[0]:
                self._log("⚠ positionEnd 미수신 — 타임아웃으로 잔고 강제 반영")
                _flush()
            _restore_pos_handlers()

        # 이전 핸들러 보존 (None 방어)
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

        if not hasattr(self, '_pos_timeout_timer'):
            self._pos_timeout_timer = QTimer(self)
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

        # [v1.6 ①] PnL reqId 카운터 리셋
        # 재연결마다 누적되면 reqId 범위(9900~)가 무한 증가
        # _stop_server_pnl()에서 기존 구독 해제 + 딕셔너리 초기화 후 카운터 리셋
        try:
            self._stop_server_pnl()
        except Exception:
            pass
        self._pnl_req_id_counter = 9900
        self._pnl_req_ids        = {}
        self._log("🔄 PnL reqId 카운터 리셋 완료 (9900부터 재시작)")

        self._refresh_positions()

    # ── _ensure_pnl_checkbox ────────────────────────────────────────────────

    def _ensure_pnl_checkbox(self):
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
            parent = self.tbl_positions.parentWidget()
            if parent and parent.layout():
                parent.layout().addWidget(chk)
            self._log("✅ PnL 모드 체크박스 자동 추가됨")
        except Exception as e:
            self._log(f"⚠ 체크박스 자동 추가 실패: {e}")

    # ── _apply_positions ─────────────────────────────────────────────────────

    def _apply_positions(self, pos_buf: dict):
        """포지션 데이터를 콜-풋 테이블(col=6) + 잔고 패널에 반영."""
        try:
            from call_put_tab.tab_options import _mk
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

            # 콜-풋 테이블 잔고 컬럼 전체 초기화
            if hasattr(self, 'tbl_call'):
                for r in range(self.tbl_call.rowCount()):
                    self.tbl_call.setItem(r, 6, _mk("―", "#aaaaaa"))
            if hasattr(self, 'tbl_put'):
                for r in range(self.tbl_put.rowCount()):
                    self.tbl_put.setItem(r, 6, _mk("―", "#aaaaaa"))

            if hasattr(self, 'tbl_positions'):
                self.tbl_positions.setRowCount(0)

            self._pos_snapshot = {}

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
                sym_raw = sym_raw_map.get(key, "")

                is_exp     = self._is_expired(p_expiry)
                expiry_pnl = self._calc_expiry_pnl(qty, avg) if is_exp else None

                self._pos_snapshot[key] = {
                    "qty": qty, "avg": avg, "con_id": con_id, "sym_raw": sym_raw,
                    "expired": is_exp, "expiry_pnl": expiry_pnl,
                }

                # [A] 콜-풋 테이블 col=6 갱신
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

                # [B] 잔고 패널
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

                        if is_exp and expiry_pnl is not None:
                            if expiry_pnl >= 0:
                                pnl_text  = f"▲ +${expiry_pnl:,.0f} [만기소멸]"
                                pnl_color = "#00ff88"
                                bg_color  = "#1a2e1a"
                            else:
                                pnl_text  = f"▼ -${abs(expiry_pnl):,.0f} [만기소멸]"
                                pnl_color = "#ff4444"
                                bg_color  = "#2e1a1a"

                            pnl_item = _mk(pnl_text, pnl_color)
                            pnl_item.setBackground(QBrush(QColor(bg_color)))
                            exp_label = p_expiry[:8] if len(p_expiry) >= 8 else p_expiry
                            direction = "이익" if expiry_pnl >= 0 else "손실"
                            pnl_item.setToolTip(
                                f"만기일 {exp_label} 경과 — {direction} 확정")
                            self.tbl_positions.setItem(row, 4, pnl_item)
                        else:
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
        if checked:
            self._log("🔀 PnL 모드: 서버 실시간 (reqPnLSingle)")
            self._start_server_pnl()
        else:
            self._log("🔀 PnL 모드: 로컬 계산 (bid/ask 중간값)")
            self._stop_server_pnl()
            self._update_pos_pnl()

    # ── _start_server_pnl ────────────────────────────────────────────────────

    def _start_server_pnl(self):
        """
        [버그 #4 수정 C] _pos_snapshot 각 포지션에 reqPnLSingle 구독 시작.

        수정: req_to_row 지역변수 → self._pnl_req_to_row (instance 변수)
              pnlSingle 콜백이 재구독 후에도 최신 매핑을 참조.
        """
        if not self.mw.connected:
            return
        if not hasattr(self, '_pos_snapshot') or not self._pos_snapshot:
            return

        ib      = self.mw.ib
        account = getattr(self.mw, 'account_id', '')

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

        if not hasattr(self, '_pnl_req_ids'):
            self._pnl_req_ids = {}

        orig_pnl_single = getattr(ib, 'pnlSingle', lambda *a: None)
        ib._orig_pnl_single = orig_pnl_single

        # ── [#4-C] instance 변수로 승격 ─────────────────────────
        self._pnl_req_to_row: Dict[int, tuple] = {}

        def _on_pnl_single(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value):
            """IBKR pnlSingle 콜백 — col=4 평가손익 갱신."""
            # ── [#4-C] 항상 최신 매핑 참조 ──────────────────────
            entry = getattr(self, '_pnl_req_to_row', {}).get(reqId)
            if entry is None:
                return
            key, row_idx = entry
            if not hasattr(self, 'tbl_positions'):
                return
            if row_idx >= self.tbl_positions.rowCount():
                return

            snap_info = self._pos_snapshot.get(key, {})
            if snap_info.get("expired"):
                return

            from call_put_tab.tab_options import _mk
            pnl = unrealizedPnL
            if pnl is None or pnl != pnl:
                return
            if pnl > 0:
                pnl_text, pnl_color = f"+${pnl:,.0f}", "#00ff88"
            elif pnl < 0:
                pnl_text, pnl_color = f"-${abs(pnl):,.0f}", "#ff4444"
            else:
                pnl_text, pnl_color = "$0", "#888888"

            self.tbl_positions.setItem(row_idx, 4, _mk(pnl_text, pnl_color))

        ib.pnlSingle = _on_pnl_single

        snapshot_items = list(self._pos_snapshot.items())
        for row_idx, (key, info) in enumerate(snapshot_items):
            con_id = info.get('con_id')
            if not con_id:
                self._update_pos_pnl_single(row_idx, key, info)
                continue

            req_id = self._pnl_req_ids.get(key)
            if req_id is None:
                if not hasattr(self, '_pnl_req_id_counter'):
                    self._pnl_req_id_counter = 9900
                req_id = self._pnl_req_id_counter
                self._pnl_req_id_counter += 1
                self._pnl_req_ids[key] = req_id

            # ── [#4-C] instance 변수에 저장 ──────────────────────
            self._pnl_req_to_row[req_id] = (key, row_idx)

            try:
                ib.reqPnLSingle(req_id, account, "", con_id)
            except Exception as e:
                self._log(f"⚠ reqPnLSingle 오류 (row={row_idx}): {e}")
                self._update_pos_pnl_single(row_idx, key, info)

        self._log(f"📡 서버 PnL 구독: {len(self._pnl_req_to_row)}개 포지션")

    # ── _stop_server_pnl ─────────────────────────────────────────────────────

    def _stop_server_pnl(self):
        """
        [버그 #4 수정 D] 구독 중인 모든 reqPnLSingle 취소 및 콜백 복원.
        _pnl_req_to_row 초기화 추가 → in-flight 콜백 무효화.
        """
        ib        = getattr(getattr(self, 'mw', None), 'ib', None)
        connected = getattr(getattr(self, 'mw', None), 'connected', False)

        req_ids = getattr(self, '_pnl_req_ids', {})
        for key, req_id in list(req_ids.items()):
            if connected and ib:
                try:
                    ib.cancelPnLSingle(req_id)
                except Exception:
                    pass
        self._pnl_req_ids    = {}
        # ── [#4-D] 매핑 초기화 → in-flight pnlSingle 콜백 무효화 ─
        self._pnl_req_to_row = {}

        if ib:
            orig = getattr(ib, '_orig_pnl_single', None)
            if orig is not None:
                ib.pnlSingle = orig
                del ib._orig_pnl_single

    # ── _update_pos_pnl (로컬 계산 — 전체) ──────────────────────────────────

    def _update_pos_pnl(self):
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
        from call_put_tab.tab_options import _mk
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

    # ── 체결 자동 감지 → 잔고 갱신 ──────────────────────────────────────────

    def _connect_exec_auto_refresh(self):
        if getattr(self, '_exec_auto_refresh_connected', False):
            return
        self._exec_auto_refresh_connected = True

        ib = self.mw.ib
        _orig_exec = getattr(ib, 'execDetails', lambda *a: None)

        def _on_exec_details(reqId, contract, execution):
            try:
                _orig_exec(reqId, contract, execution)
            except Exception:
                pass

            if getattr(contract, 'secType', '') not in ('OPT', 'FOP'):
                return

            sym  = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
            side = getattr(execution, 'side', '')
            qty  = getattr(execution, 'shares', 0)
            self._log(f"✅ 체결 감지: {sym}  {side}  {qty}계약 → 잔고 자동 갱신")

            QTimer.singleShot(2000, self._refresh_positions)

        ib.execDetails = _on_exec_details
        self._log("🔗 execDetails 자동 잔고 갱신 연결 완료")