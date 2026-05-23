"""combo_ui_scenario_logic.py — ScenarioTab 데이터/갱신 로직 믹스인

포함:
  set_greeks()       — 레그 Greeks 주입 및 헤더 갱신
  _auto_update_time()— ET 기준 만기까지 남은 시간 자동 계산
  _refresh()         — 슬라이더 값으로 시나리오 갱신
"""
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class _ScenarioLogicMixin:
    """데이터·갱신 전용 믹스인. ScenarioTab 이 단독 상속."""


    def set_greeks(self, legs: list, entry: float = 0.0,
                   und_price: float = 0.0) -> None:
        """
        레그 Greeks 주입 → 탭 갱신.
        legs 각 원소: {'dir','qty','delta','gamma','theta','vega',
                       'strike','iv','cp','expiry'}
        und_price: 현재 지수 가격 (BS 계산 기준가)
        """
        if not legs:
            return

        if entry > 0:
            self._entry = entry

        self._legs_raw = legs
        if und_price > 0:
            self._und_price = und_price

        # 만기일 저장 (첫 레그에서)
        for leg in legs:
            exp = str(leg.get("expiry", "")).strip()
            if exp and len(exp) == 8:
                self._expiry_str = exp
                self._auto_update_time()
                break

        # 포지션 Greeks 합산
        pos_delta = pos_gamma = pos_theta = pos_vega = 0.0
        strikes = []
        has_data = False

        for leg in legs:
            try:
                d   = float(leg.get("delta", 0) or 0)
                g   = float(leg.get("gamma", 0) or 0)
                th  = float(leg.get("theta", 0) or 0)
                v   = float(leg.get("vega",  0) or 0)
                qty = float(leg.get("qty",   1) or 1)
                direction = str(leg.get("dir", "BUY")).upper()
                coeff = 1.0 if direction == "BUY" else -1.0

                pos_delta += d  * qty * coeff
                pos_gamma += g  * qty * coeff
                pos_theta += th * qty * coeff
                pos_vega  += v  * qty * coeff

                sk = leg.get("strike")
                if sk:
                    strikes.append(float(sk))
                if d != 0 or g != 0:
                    has_data = True
            except Exception:
                pass

        if not has_data:
            iv_check = any(leg.get("iv") for leg in legs)
            if not iv_check:
                return

        self._pos_delta = pos_delta
        self._pos_gamma = pos_gamma
        self._pos_theta = pos_theta
        self._pos_vega  = pos_vega

        if len(strikes) >= 2:
            self._max_val = abs(max(strikes) - min(strikes))
        else:
            self._max_val = 5.0

        self._lbl_entry.setText(
            f"DEBIT: ${self._entry:.2f}" if self._entry > 0 else "DEBIT: ―")
        self._lbl_und.setText(
            f"지수: {self._und_price:.1f}" if self._und_price > 0 else "지수: ―")
        self._lbl_greeks.setText(
            f"δ {pos_delta:+.3f}  γ {pos_gamma:+.4f}  "
            f"θ {pos_theta:+.4f}  ν {pos_vega:+.4f}")
        self._lbl_cap.setText(f"상한: ${self._max_val:.2f}")

        self._refresh()

    # ══════════════════════════════════════════════════════════
    # 시간 자동 계산 (1분 타이머)
    # ══════════════════════════════════════════════════════════

    def _auto_update_time(self) -> None:
        """ET 기준 만기까지 남은 시간 자동 계산 및 슬라이더 기본값 갱신."""
        try:
            from datetime import datetime
            try:
                from zoneinfo import ZoneInfo
                _tz = ZoneInfo("America/New_York")
            except Exception:
                import pytz
                _tz = pytz.timezone("America/New_York")

            now_et = datetime.now(_tz)

            if self._expiry_str and len(self._expiry_str) == 8:
                y  = int(self._expiry_str[:4])
                mo = int(self._expiry_str[4:6])
                d  = int(self._expiry_str[6:8])
                exp_dt = datetime(y, mo, d, 16, 0, 0, tzinfo=_tz)
            else:
                exp_dt = now_et.replace(
                    hour=16, minute=0, second=0, microsecond=0)

            diff_sec   = (exp_dt - now_et).total_seconds()
            hours_left = max(diff_sec / 3600.0, 0.0)
            self._hours_left = hours_left

            ticks = min(int(round(hours_left * 2)), 16)
            if hasattr(self, 'sl_time'):
                self.sl_time.setValue(ticks)

            if diff_sec <= 0:
                msg, color = "⏱ 만기 도달 (0h)", "#ff4444"
            elif hours_left < 1.0:
                msg   = f"⏱ 만기까지 {hours_left*60:.0f}분 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#ff6666"
            elif hours_left < 2.0:
                msg   = f"⏱ 만기까지 {hours_left:.1f}h 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#ffaa44"
            else:
                msg   = f"⏱ 만기까지 {hours_left:.1f}h 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#445566"

            if hasattr(self, '_lbl_time_auto'):
                self._lbl_time_auto.setText(msg)
                self._lbl_time_auto.setStyleSheet(
                    f"color:{color};font-size:10px;border:none;")

        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # 화면 갱신
    # ══════════════════════════════════════════════════════════

    def _refresh(self):
        """슬라이더 값으로 현재 시나리오 갱신."""
        if not hasattr(self, '_card_dg'):
            return

        move       = float(self.sl_move.value() if hasattr(self, 'sl_move') else 5)
        time_ticks = float(self.sl_time.value() if hasattr(self, 'sl_time') else 8)
        hours_left = time_ticks / 2.0
        div        = float(self.sl_iv.value()   if hasattr(self, 'sl_iv')   else 0)

        if self._entry <= 0:
            for card_w, card_lv in (self._card_dg, self._card_th,
                                    self._card_vg, self._card_pct):
                card_lv.setText("―")
                card_lv.setStyleSheet("color:#888899;border:none;")
            return

        r = self._calc(move, hours_left, div)

        def _set_card(pair, val, unit="$"):
            _, lv = pair
            txt = f"{unit}{val:+.2f}" if unit == "$" else f"{val:+.1f}%"
            col = "#44ffaa" if val > 0 else "#ff6666" if val < 0 else "#888899"
            lv.setText(txt); lv.setStyleSheet(f"color:{col};border:none;")

        _set_card(self._card_dg, r["dg"])
        _set_card(self._card_th, r["th"])
        _set_card(self._card_vg, r["vg"])

        _, pct_lv = self._card_pct
        pct_col = "#ffff44" if r["pct"] > 0 else "#ff6666" if r["pct"] < 0 else "#888899"
        pct_txt = "MAX" if r["capped"] else f"{r['pct']:+.1f}%"
        pct_lv.setText(pct_txt)
        pct_lv.setStyleSheet(
            f"color:{pct_col};border:none;font-weight:bold;")

        # 상세 분해 갱신
        dg_pure = self._pos_delta * move * 100.0
        gm_pure = 0.5 * self._pos_gamma * move * move * 100.0

        def _fmt_val(lbl, v, unit="$"):
            txt = f"${v:+.3f}" if unit == "$" else f"{v:+.2f}%"
            col = "#44ffaa" if v > 0 else "#ff6666" if v < 0 else "#888899"
            lbl.setText(txt)
            lbl.setStyleSheet(f"color:{col};font-size:10px;border:none;")

        _fmt_val(self._lv_delta, dg_pure)
        _fmt_val(self._lv_gamma, gm_pure)
        _fmt_val(self._lv_theta, r["th"])
        _fmt_val(self._lv_vega,  r["vg"])

        self._lv_price.setText(
            f"${r['price']:.2f}" + (" ★" if r["capped"] else ""))
        self._lv_price.setStyleSheet(
            "color:#ffff44;font-size:10px;border:none;")
        self._lv_return.setText(pct_txt)
        self._lv_return.setStyleSheet(
            f"color:{pct_col};font-size:10px;border:none;font-weight:bold;")

        elapsed    = r.get("elapsed", 0.0)
        cap_txt    = ""
        if r["capped"]:
            cap_txt = f"⚠ 예상가 상한 ${self._max_val:.2f} 초과 → MAX 고정  "
        cap_txt += (f"경과 {elapsed:.1f}h  "
                    f"({self._hours_left:.1f}h → {hours_left:.1f}h 남음)  ")

        self._lbl_cap_warn.setText(cap_txt)
        self._lbl_cap_warn.setStyleSheet(
            "color:#ffaa44;font-size:10px;border:none;"
            if r["capped"] else
            "color:#445566;font-size:10px;border:none;")

        # 매트릭스 갱신
        for ri, m in enumerate(self._MOVES):
            for ci, t in enumerate(self._TIMES):
                rv = self._calc(float(m), t, div)
                if rv["capped"]:
                    txt, bg, fg = "MAX", "#0a2a0a", "#44ff44"
                elif rv["pct"] > 50:
                    txt, bg, fg = f"{rv['pct']:+.0f}%", "#0a2a0a", "#88ff44"
                elif rv["pct"] > 0:
                    txt, bg, fg = f"{rv['pct']:+.0f}%", "#1a1a08", "#ffcc44"
                elif rv["pct"] > -50:
                    txt, bg, fg = f"{rv['pct']:+.0f}%", "#1a0808", "#ff8844"
                else:
                    txt, bg, fg = f"{rv['pct']:+.0f}%", "#2a0808", "#ff4444"

                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(fg))
                it.setBackground(QColor(bg))
                it.setFlags(Qt.ItemIsEnabled)
                self._matrix_tbl.setItem(ri, ci, it)
