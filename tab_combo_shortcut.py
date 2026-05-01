"""
tab_combo_shortcut.py — 복합 전략 탭 단축키 모듈
────────────────────────────────────────────────────────────
포함:
  ShortcutMixin   — ComboStrategyGrid에 mixin
  install()       — QApplication eventFilter 설치
  uninstall()     — 위젯 소멸 시 해제

단축키:
  Alt+↑           — 현재 전략 ATM 기준 전체 레그 +1단계
  Alt+↓           — 현재 전략 ATM 기준 전체 레그 -1단계
  Shift+1~4       — 전략 빠른 변경 (기존 유지)

지원 전략 (레그 자동 배치):
  콜 스프레드:  레그1 C(ATM-1+off), 레그2 C(ATM+off)
  풋 스프레드:  레그1 P(ATM-1+off), 레그2 P(ATM+off)
  그 외:        현재 포커스 레그 단독

핵심 수정사항:
  - QApplication.installEventFilter → 포커스 위치 무관 동작
  - itemChanged 블로킹 → 입력 중 연쇄 콜백 차단
  - 레그 직접 쓰기(_write_leg_row) → currentRow 의존 제거
  - fill_premium_from_market 직접 호출 → _on_strike_changed 우회
    (포커스 날아가는 원인 제거)
  - setCurrentCell 복원 → 입력 완료 후 포커스 명시 복원
────────────────────────────────────────────────────────────
"""

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtWidgets import QTableWidgetItem, QApplication


# ══════════════════════════════════════════════════════════════
class ShortcutMixin:
    """단축키 이벤트 필터 Mixin — ComboStrategyGrid에 추가."""

    def _install_shortcuts(self):
        """_build() 완료 후 호출. QApplication 레벨 필터 설치."""
        QApplication.instance().installEventFilter(self)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    # ── QApplication 레벨 이벤트 필터 ────────────────────────
    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        if not self.isVisible():
            return False
        # 레그 쓰기 중 재진입 방지
        if getattr(self, '_leg_item_changing', False):
            return False

        mods = event.modifiers()
        key  = event.key()

        # Alt+↑/↓ — ATM 단축키
        if (mods & Qt.AltModifier) and key in (Qt.Key_Up, Qt.Key_Down):
            offset = +1 if key == Qt.Key_Up else -1
            _atm_shortcut(self, offset)
            return True   # 이벤트 소비

        return False

    def keyPressEvent(self, event):
        super().keyPressEvent(event)


# ══════════════════════════════════════════════════════════════
# ATM 단축키 핵심 로직
# ══════════════════════════════════════════════════════════════

def _atm_shortcut(self, offset: int):
    """
    Alt+↑/↓ 진입점.
    1. 전략 판별 → 레그 플랜 생성
    2. itemChanged 블로킹 ON
    3. 레그 테이블 직접 쓰기 (currentRow 의존 없음)
    4. 블로킹 OFF
    5. 포커스 복원 (레그0 행)
    6. Mid-price 직접 호출 (fill_premium_from_market)
    """
    und_price = getattr(self, '_und_price', None)
    if not und_price or und_price <= 0:
        self._log("⚠ Alt+↑↓: 현재가 미수신 — ▶현재가 조회 먼저 실행하세요")
        return

    call_strikes = getattr(self, '_call_strikes', [])
    put_strikes  = getattr(self, '_put_strikes',  [])
    if not call_strikes and not put_strikes:
        self._log("⚠ Alt+↑↓: 체인 데이터 없음 — ↺ 즉시 동기화를 먼저 실행하세요")
        return

    strat = getattr(self, 'combo_strat', None)
    strat = strat.currentText() if strat else ""

    # 레그 플랜: [(leg_row, cp, strike), ...]
    plan = _build_plan(self, strat, offset, und_price, call_strikes, put_strikes)
    if not plan:
        return

    # ── itemChanged 블로킹 ON ─────────────────────────────────
    self._leg_item_changing = True
    try:
        for leg_row, cp, strike in plan:
            _write_leg_row(self, leg_row, cp, strike)
    finally:
        self._leg_item_changing = False

    # ── 포커스 복원 (레그0 행, 행사가 컬럼) ───────────────────
    self.tbl_legs.setCurrentCell(plan[0][0], 3)

    # ── 방향 배너 갱신 ────────────────────────────────────────
    banner = getattr(self, 'direction_banner', None)
    if banner:
        banner.refresh(self.tbl_legs)

    # ── Mid-price 직접 호출 (100ms 간격, _on_strike_changed 우회) ──
    # _on_strike_changed 경로를 타면 setItem → itemChanged → 포커스 초기화
    # fill_premium_from_market를 직접 호출해 해당 경로를 완전히 우회
    _trigger_premium(self, plan)

    # Mid-price 수신 대기 후 손익 계산 자동 실행
    def _auto_calc():
        fn = getattr(self, '_calc_pnl', None)
        if fn:
            self._log("📊 손익 계산 자동 실행")
            fn()
    QTimer.singleShot(1500, _auto_calc)

    direction = "▲" if offset > 0 else "▼"
    self._log(
        f"⌨ Alt+{direction} [{strat}]  "
        + "  ".join(f"레그{r+1} {cp} {int(st)}" for r, cp, st in plan)
    )


# ── 전략별 레그 플랜 ─────────────────────────────────────────────

def _build_plan(self, strat: str, offset: int, und_price: float,
                call_strikes: list, put_strikes: list):
    """
    전략명 + offset → [(leg_row, cp, strike), ...] 반환.
    실패 시 None 반환.
    """
    def _pick(strikes, rel_offset):
        """ATM 인덱스 + rel_offset, 경계 클리핑."""
        if not strikes:
            return None
        atm = min(range(len(strikes)), key=lambda i: abs(strikes[i] - und_price))
        idx = max(0, min(len(strikes) - 1, atm + rel_offset))
        return strikes[idx]

    rows = self.tbl_legs.rowCount()

    if "콜 스프레드" in strat and rows >= 2:
        s1 = _pick(call_strikes, -1 + offset)
        s2 = _pick(call_strikes,  0 + offset)
        if s1 is None or s2 is None:
            return None
        return [(0, "C", s1), (1, "C", s2)]

    if "풋 스프레드" in strat and rows >= 2:
        s1 = _pick(put_strikes, -1 + offset)
        s2 = _pick(put_strikes,  0 + offset)
        if s1 is None or s2 is None:
            return None
        return [(0, "P", s1), (1, "P", s2)]

    # 그 외: 현재 포커스 레그 단독
    leg_row = self.tbl_legs.currentRow()
    if leg_row < 0:
        leg_row = 0
    if leg_row >= rows:
        self._log("⚠ Alt+↑↓: 레그 테이블에 포커스를 먼저 두세요")
        return None
    cp_item = self.tbl_legs.item(leg_row, 2)
    cp      = cp_item.text().strip().upper() if cp_item else "C"
    if cp not in ("C", "P"):
        cp = "C"
    strikes = call_strikes if cp == "C" else put_strikes
    st = _pick(strikes, offset)
    if st is None:
        return None
    return [(leg_row, cp, st)]


# ── 레그 행 직접 쓰기 ────────────────────────────────────────────

def _write_leg_row(self, leg_row: int, cp: str, strike: float):
    """
    지정한 leg_row에 cp·strike·price·expiry를 직접 기록.
    currentRow에 의존하지 않으므로 포커스 위치와 무관하게 동작.
    itemChanged는 호출 전 이미 블로킹 상태.
    """
    if leg_row >= self.tbl_legs.rowCount():
        return

    expiry  = getattr(self, '_current_expiry', '')
    prices  = self._chain_call if cp == "C" else self._chain_put
    price   = prices.get(strike)

    def _set(col, text, _r=leg_row):
        it = self.tbl_legs.item(_r, col)
        if it is None:
            it = QTableWidgetItem()
            it.setTextAlignment(Qt.AlignCenter)
            self.tbl_legs.setItem(_r, col, it)
        it.setText(text)

    _set(2, cp)
    _set(3, str(int(strike)))
    if price:
        _set(4, f"{price:.2f}")
    if expiry:
        _set(6, expiry)


# ── Mid-price 직접 호출 ──────────────────────────────────────────

def _trigger_premium(self, plan: list):
    """
    각 레그 conId 캐시 조회 → fill_premium_from_market 직접 호출.
    캐시 미스 시 _fetch_conid_then_premium 폴백.
    _on_strike_changed / itemChanged 경로를 타지 않으므로
    포커스·블로킹 영향 없음.
    """
    from combo_ui_leg_panel import fill_premium_from_market

    expiry  = getattr(self, '_current_expiry', '')
    sym_w   = getattr(self, 'edit_sym_combo', None)
    symbol  = sym_w.text().strip().upper() if sym_w else "SPX"
    bag_sym = symbol.replace("SPXW", "SPX")

    for i, (leg_row, cp, strike) in enumerate(plan):
        def _do(r=leg_row, c=cp, st=strike):
            con_id = 0
            try:
                from combo_order_bag import _CONID_CACHE, _conid_key
                con_id = _CONID_CACHE.get(_conid_key(bag_sym, c, st, expiry), 0)
            except Exception:
                pass

            if con_id > 0:
                fill_premium_from_market(self, r, con_id)
            else:
                try:
                    from combo_ui_leg_extra import _fetch_conid_then_premium
                    from combo_order_utils import _parse_expiry_display
                    raw = _parse_expiry_display(expiry)
                    if raw:
                        _fetch_conid_then_premium(self, r, symbol, st, c, raw)
                except Exception:
                    pass

        QTimer.singleShot(i * 120, _do)