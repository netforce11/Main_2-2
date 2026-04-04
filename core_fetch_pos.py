"""
core_fetch_pos.py — 포지션 조회 / 잔고 컬럼 갱신  v1.0
════════════════════════════════════════════════════
core_fetch.py 300줄 초과로 분리.
CoreFetchPosMixin 을 CoreFetchMixin 이 상속한다.
포함 메서드:
  _refresh_positions()
  _apply_positions()
════════════════════════════════════════════════════
"""

from PyQt5.QtCore import QTimer


class CoreFetchPosMixin:
    """포지션 조회 전용 Mixin. CoreFetchMixin에 포함된다."""

    def _refresh_positions(self):
        """IBKR reqPositions() 호출 → 콜-풋 테이블 잔고 컬럼(col=6) 갱신."""
        if not self.mw.connected:
            return
        ib = self.mw.ib

        # 백그라운드(IBKR 콜백)에서만 쓰고, 메인 스레드는 복사본만 읽는다.
        # 기존: _pos_buf['avg_cost'] = _avg_buf 를 백그라운드+메인이 동시 수정
        #       → 딕셔너리 뮤테이션 충돌 → 0xC0000005 크래시
        # 수정: _on_position_end 에서 dict() 복사본을 만들어 메인 스레드로 전달
        _pos_buf = {}
        _avg_buf = {}

        def _on_position(account, contract, pos, avg_cost):
            if getattr(contract, 'secType', '') != 'OPT':
                return
            key = (
                getattr(contract, 'symbol', ''),
                getattr(contract, 'right', ''),
                int(getattr(contract, 'strike', 0)),
                getattr(contract, 'lastTradeDateOrContractMonth', '')[:8],
            )
            _pos_buf[key] = int(pos)
            _avg_buf[key] = avg_cost

        def _on_position_end():
            # 복사본을 만들어 메인 스레드로 전달 (원본 동시 수정 방지)
            pos_snap = dict(_pos_buf)
            avg_snap = dict(_avg_buf)
            combined = {"_avg_cost_map": avg_snap, **pos_snap}
            QTimer.singleShot(0, lambda: self._apply_positions(combined))

        # 기존 콜백 임시 교체
        ib._orig_position    = getattr(ib, 'position',    lambda *a: None)
        ib._orig_positionEnd = getattr(ib, 'positionEnd', lambda: None)
        ib.position    = _on_position
        ib.positionEnd = _on_position_end

        try:
            ib.reqPositions()
        except Exception as e:
            self._log(f"⚠ 포지션 조회 오류: {e}")

        # 3초 후 콜백 복원
        QTimer.singleShot(3000, lambda: (
            setattr(ib, 'position',    ib._orig_position),
            setattr(ib, 'positionEnd', ib._orig_positionEnd),
        ))

    def _apply_positions(self, pos_buf: dict):
        """포지션 데이터를 콜-풋 테이블 잔고 컬럼(col=6) + 잔고 패널에 반영."""
        from tab_options import _mk
        sym    = self.edit_sym.text().strip().upper().replace('SPXW', 'SPX')
        expiry, _ = self._get_expiry()
        if not expiry:
            return

        # 콜-풋 테이블 잔고 컬럼 전체 초기화
        for r in range(self.tbl_call.rowCount()):
            self.tbl_call.setItem(r, 6, _mk("―", "#aaaaaa"))
        for r in range(self.tbl_put.rowCount()):
            self.tbl_put.setItem(r, 6, _mk("―", "#aaaaaa"))

        # 잔고 패널 테이블 초기화
        if hasattr(self, 'tbl_positions'):
            self.tbl_positions.setRowCount(0)

        found = 0
        avg_cost_map = pos_buf.get('_avg_cost_map', {})
        for key, qty in pos_buf.items():
            if not isinstance(key, tuple):
                continue   # _avg_cost_map 키 건너뜀
            p_sym, p_right, p_strike, p_expiry = key
            if p_sym != sym or p_expiry != expiry[:8]:
                continue
            if qty == 0:
                continue

            color = "#00ff88" if qty > 0 else "#ff6666"
            text  = str(qty)

            # 콜-풋 테이블 잔고 컬럼 갱신
            if p_right == 'C':
                for r, st in enumerate(self.call_strikes):
                    if int(st) == p_strike:
                        self.tbl_call.setItem(r, 6, _mk(text, color))
                        break
            elif p_right == 'P':
                for r, st in enumerate(self.put_strikes):
                    if int(st) == p_strike:
                        self.tbl_put.setItem(r, 6, _mk(text, color))
                        break

            # 잔고 패널 테이블에 행 추가
            if hasattr(self, 'tbl_positions'):
                avg = avg_cost_map.get(key, 0)
                r = self.tbl_positions.rowCount()
                self.tbl_positions.insertRow(r)
                cp_color = "#33aaff" if p_right == "C" else "#ff6666"
                self.tbl_positions.setItem(
                    r, 0, _mk("CALL" if p_right == "C" else "PUT", cp_color))
                self.tbl_positions.setItem(r, 1, _mk(str(p_strike), "#ffd700"))
                self.tbl_positions.setItem(r, 2, _mk(text, color))
                self.tbl_positions.setItem(
                    r, 3, _mk(f"{avg:.2f}" if avg else "―", "#aaa"))

            found += 1

        if found:
            self._log(f"📊 잔고 갱신: {found}개 포지션 반영")
        else:
            self._log("📊 현재 만기 포지션 없음")