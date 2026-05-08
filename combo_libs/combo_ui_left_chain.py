"""
combo_ui_left_chain.py — 체인 클릭 · 거리% 셀 · conId 일괄 조회
combo_ui_left.py 에서 분리. v3.2

[FIX-I] _start_restored_position_streams 추가
  conId 일괄 조회 완료(_bulk_fetch_conids 끝) 시점에
  복원된 포지션의 실시간 스트림을 시작.
  이미 스트림 중인 oid 는 스킵.
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt, QTimer


# ── 체인 클릭 → 레그 자동 입력 ──────────────────────────────────

def _on_chain_click(self, row: int, col: int, side: str):
    """
    체인 테이블 셀 클릭 → 레그 자동 입력.
    스프레드 전략: 클릭 행사가(레그1 BUY) + +1단계(레그2 SELL) 동시 입력.
    그 외: 현재 포커스 레그에 단독 입력.
    """
    strikes = self._call_strikes if side == "C" else self._put_strikes
    prices  = self._chain_call   if side == "C" else self._chain_put

    if row >= len(strikes):
        return

    strat = ""
    combo = getattr(self, 'combo_strat', None)
    if combo:
        strat = combo.currentText()

    is_spread = (
        (side == "C" and ("콜 스프레드" in strat or "콜 데빗 스프레드" in strat)) or
        (side == "P" and ("풋 스프레드" in strat or "풋 데빗 스프레드" in strat))
    )

    self._log(f"🖱 체인 클릭: {side} row={row}  전략={strat!r}  "
              f"is_spread={is_spread}  tbl_rows={self.tbl_legs.rowCount()}")

    if is_spread and self.tbl_legs.rowCount() >= 2:
        row2 = min(row + 1, len(strikes) - 1)
        plan = [
            (0, side, strikes[row]),
            (1, side, strikes[row2]),
        ]
        _write_and_fetch_plan(self, plan, prices)
    else:
        strike  = strikes[row]
        price   = prices.get(strike)
        leg_row = self.tbl_legs.currentRow()
        if leg_row < 0:
            leg_row = 0
        if leg_row >= self.tbl_legs.rowCount():
            return
        _write_single(self, leg_row, side, strike, price)
        _fetch_single(self, leg_row, side, strike)

    banner = getattr(self, 'direction_banner', None)
    if banner:
        banner.refresh(self.tbl_legs)


def _write_single(self, leg_row: int, side: str, strike: float, price):
    """단일 레그 행 기록."""
    from PyQt5.QtWidgets import QTableWidgetItem
    expiry = getattr(self, '_current_expiry', '')

    def _set(col, text, _r=leg_row):
        it = self.tbl_legs.item(_r, col)
        if it is None:
            it = QTableWidgetItem()
            it.setTextAlignment(Qt.AlignCenter)
            self.tbl_legs.setItem(_r, col, it)
        it.setText(text)

    _set(2, side)
    _set(3, str(int(strike)))
    if price:
        _set(4, f"{price:.2f}")
    if expiry:
        _set(6, expiry)
    price_str = f"{price:.2f}" if price else "0.00"
    self._log(f"레그{leg_row+1} 자동 입력: {side} {int(strike)}  ${price_str}")


def _write_and_fetch_plan(self, plan: list, prices: dict):
    """스프레드 전략용: 레그 플랜 전체 기록 + Mid-price 일괄 조회."""
    from tab_combo_shortcut import _trigger_premium
    from PyQt5.QtWidgets import QTableWidgetItem

    expiry = getattr(self, '_current_expiry', '')

    self._leg_item_changing = True
    try:
        for leg_row, side, strike in plan:
            if leg_row >= self.tbl_legs.rowCount():
                self._log(f"⚠ 레그{leg_row+1} 행 없음 (rowCount={self.tbl_legs.rowCount()})")
                continue

            def _set(col, text, _r=leg_row):
                it = self.tbl_legs.item(_r, col)
                if it is None:
                    it = QTableWidgetItem()
                    it.setTextAlignment(Qt.AlignCenter)
                    self.tbl_legs.setItem(_r, col, it)
                it.setText(text)

            price = prices.get(strike)
            _set(2, side)
            _set(3, str(int(strike)))
            if price:
                _set(4, f"{price:.2f}")
            if expiry:
                _set(6, expiry)
            price_str = f"{price:.2f}" if price else "0.00"
            self._log(f"레그{leg_row+1} 자동 입력: {side} {int(strike)}  ${price_str}")
    finally:
        self._leg_item_changing = False

    self.tbl_legs.setCurrentCell(plan[0][0], 3)
    _trigger_premium(self, plan)

    def _auto_calc():
        fn = getattr(self, '_calc_pnl', None)
        if fn:
            self._log("📊 손익 계산 자동 실행")
            fn()
    QTimer.singleShot(1500, _auto_calc)


def _fetch_single(self, leg_row: int, cp: str, strike: float):
    from tab_combo_shortcut import _trigger_premium
    _trigger_premium(self, [(leg_row, cp, strike)])


# ── 거리% 셀 생성 ────────────────────────────────────────────────

def _make_dist_item(strike: float, und_price: float, side: str) -> QTableWidgetItem:
    """
    기초자산 현재가 대비 행사가 거리% 셀.
    ITM→붉은 / ATM(1%이내)→노랑 / OTM3%→연두 / OTM7%→연파 / 심층OTM→회색
    """
    from PyQt5.QtGui import QColor

    item = QTableWidgetItem("―")
    item.setTextAlignment(Qt.AlignCenter)
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    if not und_price or und_price <= 0:
        return item

    dist_pct = (strike - und_price) / und_price * 100
    is_itm   = (strike < und_price) if side == "C" else (strike > und_price)
    abs_dist = abs(dist_pct)

    if is_itm:
        color = "#ff7755"
    elif abs_dist < 1.0:
        color = "#ffd700"
    elif abs_dist < 3.0:
        color = "#88dd55"
    elif abs_dist < 7.0:
        color = "#55aadd"
    else:
        color = "#888888"

    item.setText(f"{dist_pct:+.2f}%")
    item.setForeground(QColor(color))
    return item


# ── conId 일괄 조회 ──────────────────────────────────────────────

def _bulk_fetch_conids(self, symbol: str, expiry: str,
                       call_strikes: list, put_strikes: list):
    """
    체인 동기화 완료 시 conId 캐시 미비분 일괄 조회.
    완료 시 _start_restored_position_streams() 호출 [FIX-I].
    """
    try:
        from combo_order_bag import _CONID_CACHE, _conid_key, _save_conid_cache
    except ImportError:
        return

    bag_sym     = symbol.replace("SPXW", "SPX")
    all_strikes = [(st, "C") for st in call_strikes] + [(st, "P") for st in put_strikes]
    missing     = [(st, cp) for st, cp in all_strikes
                   if _conid_key(bag_sym, cp, st, expiry) not in _CONID_CACHE]

    if not missing:
        self._log(f"✅ conId 캐시 완비 ({len(all_strikes)}개) — 조회 생략")
        # 캐시 완비여도 복원 스트림은 시작해야 함
        QTimer.singleShot(0, lambda: _start_restored_position_streams(self))
        return

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
    base_rid  = 8900
    _rid_map  = {base_rid + i: (st, cp) for i, (st, cp) in enumerate(missing)}
    _cd_conn  = [None, None]

    from core import bridge as _bridge

    def _finish():
        try:
            if _cd_conn[0]: _bridge.contract_details_sig.disconnect(_on_cd)
        except Exception: pass
        try:
            if _cd_conn[1]: _bridge.contract_details_end_sig.disconnect(_on_cd_end)
        except Exception: pass
        _cd_conn[0] = _cd_conn[1] = None

    def _on_cd(req_id, cd):
        if req_id not in _rid_map: return
        st, cp_side = _rid_map[req_id]
        con_id = cd.contract.conId
        if con_id > 0:
            _CONID_CACHE[_conid_key(bag_sym, cp_side, st, expiry)] = con_id
            saved_cnt[0] += 1

    def _on_cd_end(req_id):
        if req_id not in _rid_map: return
        done_cnt[0] += 1
        if done_cnt[0] % 10 == 0 or done_cnt[0] == total:
            self._log(f"  conId 조회 중... {done_cnt[0]}/{total}")
        if done_cnt[0] >= total:
            _save_conid_cache()
            _finish()
            self._conid_bulk_running = False
            self._log(f"✅ conId 완료: 신규 {saved_cnt[0]}개 / 전체 {len(all_strikes)}개")
            # [FIX-I] conId 완료 시점에 복원 포지션 스트림 시작
            QTimer.singleShot(0, lambda: _start_restored_position_streams(self))

    _bridge.contract_details_sig.connect(_on_cd)
    _bridge.contract_details_end_sig.connect(_on_cd_end)
    _cd_conn[0] = _on_cd; _cd_conn[1] = _on_cd_end

    self._log(f"🔍 conId 일괄 조회: {total}개 (캐시 {len(all_strikes)-total}개 재사용)")

    from core_contract import make_opt_contract

    def _send(idx):
        if idx >= total: return
        st, cp_side = missing[idx]
        try:
            ib.reqContractDetails(base_rid + idx,
                                  make_opt_contract(symbol=symbol, strike=st,
                                                    right=cp_side, expiry=expiry))
        except Exception as e:
            done_cnt[0] += 1
            self._log(f"  ⚠ conId 오류 {cp_side}{int(st)}: {e}")
        QTimer.singleShot(80, lambda: _send(idx + 1))

    _send(0)

    def _timeout():
        if not getattr(self, '_conid_bulk_running', False): return
        _save_conid_cache(); _finish()
        self._conid_bulk_running = False
        self._log(f"⚠ conId 타임아웃 — {saved_cnt[0]}/{total}개 저장")
        # 타임아웃 후에도 가용한 conId 로 스트림 시작 시도
        QTimer.singleShot(0, lambda: _start_restored_position_streams(self))

    QTimer.singleShot(total * 80 + 10_000, _timeout)


# ── 복원 포지션 실시간 스트림 시작 ──────────────────────────────

def _start_restored_position_streams(self) -> None:
    """
    [FIX-I] conId 일괄 조회 완료 후 호출.
    panel._positions 에서 복원된 포지션 중 아직 스트림이 없는 것만
    reqMktData 구독 시작.
    이미 스트림 중인 oid 는 스킵하여 중복 구독 방지.
    """
    panel = getattr(self, 'synthetic_panel', None)
    if panel is None:
        return

    positions = getattr(panel, '_positions', [])
    if not positions:
        return

    try:
        from combo_order_callbacks import _start_position_price_stream
    except ImportError:
        return

    already_streaming = set(getattr(self, '_pos_stream_tids', {}).keys())
    started = 0

    for pos in positions:
        oid  = pos.get('oid')
        legs = pos.get('legs', [])
        if not oid or not legs:
            continue
        if oid in already_streaming:
            continue

        # legs 에 conId 주입 (캐시에서 보완)
        _inject_conids_to_legs(self, legs, pos)

        _start_position_price_stream(self, pos)
        started += 1

    if started:
        self._log(f"📡 복원 포지션 실시간 스트림 시작: {started}건")


def _inject_conids_to_legs(self, legs: list, pos: dict) -> None:
    """
    legs 딕셔너리에 conId 가 없는 레그를 캐시에서 채워 넣음.
    _start_position_price_stream 이 conId 없이 스킵하지 않도록 보완.
    """
    try:
        from combo_order_bag import _CONID_CACHE, _conid_key
        sym_w  = getattr(self, 'edit_sym_combo', None)
        symbol = sym_w.text().strip().upper() if sym_w else "SPX"
        symbol = symbol.replace("SPXW", "SPX")
    except ImportError:
        return

    for leg in legs:
        if leg.get('con_id'):
            continue
        try:
            key = _conid_key(
                symbol,
                str(leg.get('cp', '')),
                float(leg.get('strike', 0)),
                str(leg.get('expiry', '')),
            )
            cid = _CONID_CACHE.get(key, 0)
            if cid:
                leg['con_id'] = cid
        except Exception:
            pass
