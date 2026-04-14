"""
chart_tick.py — Tick 수신 처리 (가격 / 옵션 Greeks)
"""

from PyQt5.QtCore import QTimer

from core import REQ_UND, REQ_CALL, REQ_PUT, tbl_set
from tab_options_price_patch import render_chain_chg   # [S10-A] 등락% 색상


class TickMixin:
    """Tick 수신 전용 메서드. ChartMixin에 포함된다."""

    # ─────────────────────────────────────────────────────────
    # 가격 Tick
    # ─────────────────────────────────────────────────────────
    def _on_tick_price(self, rid, tt, price):
        if price <= 0:
            return
        QTimer.singleShot(0, lambda: self._apply_tick_price(rid, tt, price))

    def _apply_tick_price(self, rid, tt, price):
        if rid == REQ_UND:
            self._apply_tick_und(tt, price)
            return
        if REQ_CALL <= rid < REQ_CALL + self._MAX_STRIKES:
            self._apply_tick_call(rid, tt, price)
        elif REQ_PUT <= rid < REQ_PUT + self._MAX_STRIKES:
            self._apply_tick_put(rid, tt, price)

    def _apply_tick_und(self, tt, price):
        if tt in (4, 68, 75, 14, 9):
            self.und_price = price
            if tt == 9:
                self.und_prev = price
            self._update_und_display()
        if tt in (1, 66) and hasattr(self, '_pp_bid'):
            self._pp_bid = price
            if hasattr(self, '_update_price_panel'):
                self._update_price_panel()
        elif tt in (2, 67) and hasattr(self, '_pp_ask'):
            self._pp_ask = price
            if hasattr(self, '_update_price_panel'):
                self._update_price_panel()

    def _apply_tick_call(self, rid, tt, price):
        row = rid - REQ_CALL
        if row >= len(self.call_strikes):
            return
        strike = self.call_strikes[row]
        if tt in (4, 68):
            tbl_set(self.tbl_call, row, 1, f"{price:.2f}", "#33aaff")
            self.call_data[rid]["last"] = price
            # [S10-A] 전일종가 있으면 등락% 즉시 갱신
            prev = self.call_data[rid].get("prev_close")
            render_chain_chg(self.tbl_call, row, price, prev)
            self._upd_spread()
            if self._chart_strike == strike and self._chart_side == "C":
                self._push_price(price)
                if hasattr(self, '_pp_opt_ask'):
                    if tt == 4:
                        self._pp_opt_ask = price
                    self._refresh_opt_panel("C", strike)
            for idx, rule in enumerate(self._watch_rules):
                if rule["side"] == "C" and abs(float(rule["strike"]) - strike) < 0.5:
                    self._watch_prev.setdefault(idx, {})["price"] = price
        elif tt in (1, 66):
            if self._chart_strike == strike and self._chart_side == "C":
                if hasattr(self, '_pp_opt_bid'):
                    self._pp_opt_bid = price
                self._refresh_opt_panel("C", strike)
        elif tt in (2, 67):
            if self._chart_strike == strike and self._chart_side == "C":
                if hasattr(self, '_pp_opt_ask'):
                    self._pp_opt_ask = price
                self._refresh_opt_panel("C", strike)
        elif tt in (9, 75):
            # [S10-A] 전일종가 저장 — 등락% 계산용
            self.call_data[rid]["prev_close"] = price
            cur = self.call_data[rid].get("last")
            render_chain_chg(self.tbl_call, row, cur, price)

    def _apply_tick_put(self, rid, tt, price):
        row = rid - REQ_PUT
        if row >= len(self.put_strikes):
            return
        strike = self.put_strikes[row]
        if tt in (4, 68):
            tbl_set(self.tbl_put, row, 1, f"{price:.2f}", "#ff6666")
            self.put_data[rid]["last"] = price
            # [S10-A] 전일종가 있으면 등락% 즉시 갱신
            prev = self.put_data[rid].get("prev_close")
            render_chain_chg(self.tbl_put, row, price, prev)
            self._upd_spread()
            if self._chart_strike == strike and self._chart_side == "P":
                self._push_price(price)
            for idx, rule in enumerate(self._watch_rules):
                if rule["side"] == "P" and abs(float(rule["strike"]) - strike) < 0.5:
                    self._watch_prev.setdefault(idx, {})["price"] = price
        elif tt in (1, 66):
            if self._chart_strike == strike and self._chart_side == "P":
                if hasattr(self, '_pp_opt_bid'):
                    self._pp_opt_bid = price
                self._refresh_opt_panel("P", strike)
        elif tt in (2, 67):
            if self._chart_strike == strike and self._chart_side == "P":
                if hasattr(self, '_pp_opt_ask'):
                    self._pp_opt_ask = price
                self._refresh_opt_panel("P", strike)
        elif tt in (9, 75):
            # [S10-A] 전일종가 저장 — 등락% 계산용
            self.put_data[rid]["prev_close"] = price
            cur = self.put_data[rid].get("last")
            render_chain_chg(self.tbl_put, row, cur, price)

    def _refresh_opt_panel(self, side: str, strike: float):
        if not hasattr(self, '_pp_mode') or self._pp_mode != 'opt':
            return
        if getattr(self, '_pp_opt_side', '') != side:
            return
        try:
            if abs(float(getattr(self, '_pp_opt_strike', '0')) - strike) > 0.5:
                return
        except Exception:
            return
        if not hasattr(self, '_update_price_panel_opt'):
            return
        delta = None
        try:
            tbl     = self.tbl_call if side == "C" else self.tbl_put
            strikes = self.call_strikes if side == "C" else self.put_strikes
            row     = min(range(len(strikes)), key=lambda i: abs(strikes[i] - strike))
            item    = tbl.item(row, 3)
            if item and item.text() not in ("―", ""):
                delta = float(item.text())
        except Exception:
            pass
        self._update_price_panel_opt(
            side, str(int(strike)),
            self._pp_opt_bid, self._pp_opt_ask, delta)

    # ─────────────────────────────────────────────────────────
    # 옵션 Greeks Tick
    # ─────────────────────────────────────────────────────────
    def _on_tick_option(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (10, 11, 12, 13, 80, 81):
            return
        try:
            if delta is None or abs(delta) > 1.5:
                return
        except Exception:
            return
        QTimer.singleShot(0, lambda: self._apply_tick_option(rid, tt, delta, theta, gamma))

    def _apply_tick_option(self, rid, tt, delta, theta, gamma):
        if REQ_CALL <= rid < REQ_CALL + self._MAX_STRIKES:
            row = rid - REQ_CALL
            if row >= len(self.call_strikes):
                return
            tbl_set(self.tbl_call, row, 3, f"{delta:+.4f}", "#aaddff")
            tbl_set(self.tbl_call, row, 4, f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_call, row, 5, f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike == self.call_strikes[row] and self._chart_side == "C":
                self._push_greeks(delta)
            self._update_watch_prev("C", self.call_strikes[row], delta, theta, gamma)

        elif REQ_PUT <= rid < REQ_PUT + self._MAX_STRIKES:
            row = rid - REQ_PUT
            if row >= len(self.put_strikes):
                return
            tbl_set(self.tbl_put, row, 3, f"{delta:+.4f}", "#ffaaaa")
            tbl_set(self.tbl_put, row, 4, f"{theta:.4f}" if theta else "―")
            tbl_set(self.tbl_put, row, 5, f"{gamma:.6f}" if gamma else "―")
            if self._chart_strike == self.put_strikes[row] and self._chart_side == "P":
                self._push_greeks(delta)
            self._update_watch_prev("P", self.put_strikes[row], delta, theta, gamma)

    def _update_watch_prev(self, side, strike, delta, theta, gamma):
        for idx, rule in enumerate(self._watch_rules):
            if rule["side"] == side and abs(float(rule["strike"]) - strike) < 0.5:
                self._watch_prev.setdefault(idx, {}).update(
                    {"delta": delta, "theta": theta, "gamma": gamma})