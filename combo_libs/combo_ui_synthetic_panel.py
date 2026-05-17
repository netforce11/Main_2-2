"""combo_ui_synthetic_panel.py — SyntheticStatusPanel 위젯  v3.0
탭1: 📊 증거금 확인  탭2: 📋 합성 잔고  탭3: 📋 미체결  탭4: 📈 시나리오

변경 이력:
  [FIX-J]      지정가 청산 UI 추가
  [FIX-K]      update_position_prices — oid 기준으로 변경
  [FIX-L]      remove_position_by_oid 추가
  [FIX-M]      add_position 에서 _enrich_strategy_name 적용
  [FIX-BANNER] Wolf System 배너 + 수익률 경고 배너 추가
  [FIX-DELTA]  지수 5P당 예상 손익률 칼럼 추가
  [FIX-SCENARIO] 📈 시나리오 탭 추가
  [FIX-BS]     Black-Scholes 재계산 방식으로 정확도 향상

분리된 모듈:
  combo_ui_panel_constants.py  — 공통 상수/스타일/_f()
  combo_ui_panel_utils.py      — 순수 유틸 함수
  combo_ui_scenario_tab.py     — ScenarioTab 위젯
  combo_ui_panel_build.py      — UI 빌드 믹스인
  combo_ui_synthetic_panel.py  — SyntheticStatusPanel (이벤트·공개 API)
"""
from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QTableWidgetItem,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

from combo_ui_panel_constants import _f
from combo_ui_panel_utils import (
    _calc_delta_pnl_pct,
    _enrich_strategy_name,
    _format_expiry,
)
from combo_ui_panel_build import _SyntheticPanelBuildMixin

# [FIX-BANNER] 배너 임포트
try:
    from combo_wolf_system_banner import WolfSystemBanner
    _HAS_WOLF = True
except ImportError:
    _HAS_WOLF = False

try:
    from combo_profit_alert_banner import ProfitAlertBanner
    _HAS_PROFIT = True
except ImportError:
    _HAS_PROFIT = False


class SyntheticStatusPanel(_SyntheticPanelBuildMixin, QWidget):
    """합성 주문 상태 패널 (v3.0)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setStyleSheet("background:#07070f;")

        self._positions              = []
        self._close_pos_callback     = None
        self._chaser_mode_callback   = None
        self._manual_modify_callback = None
        self._margin_mode_callback   = None
        self._selected_pos_row       = -1

        self._build_ui()

        # [FIX-BANNER] 배너 생성 및 잔고 탭 하단에 추가
        self.wolf_banner         = WolfSystemBanner(self)  if _HAS_WOLF   else None
        self.profit_alert_banner = ProfitAlertBanner(
            self, wolf_banner=self.wolf_banner)             if _HAS_PROFIT else None

        if self.wolf_banner and hasattr(self, '_banner_layout'):
            self._banner_layout.addWidget(self.wolf_banner)
        if self.profit_alert_banner and hasattr(self, '_banner_layout'):
            self._banner_layout.addWidget(self.profit_alert_banner)

        # [FIX-BANNER] Chaser 자동 모드 기본값 OFF
        try:
            from combo_order_chaser import ensure_chaser_auto_off
            ensure_chaser_auto_off(self)
        except Exception:
            pass

        # [SLEEP] 예약 주문 버튼 ref 지연 주입
        try:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, self._inject_sleep_ref)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # 잔고 탭 이벤트
    # ══════════════════════════════════════════════════════════

    def _on_pos_row_clicked(self, row, col):
        """행 클릭 → 체결완료: 지정가/MKT 활성 + 현재가 스핀 자동입력
                    미체결:  주문취소 활성"""
        if row < 0 or row >= len(self._positions):
            self._selected_pos_row = -1
            self._btn_close_lmt.setEnabled(False)
            self._btn_close_mkt.setEnabled(False)
            self._btn_cancel_pos.setEnabled(False)
            self._spin_close_price.setEnabled(False)
            self._lbl_pos_hint.setText("행을 클릭하세요")
            return

        self._selected_pos_row = row
        pos       = self._positions[row]
        status    = pos.get("status", "미체결")
        strat     = pos.get("strategy", "―")
        current   = float(pos.get("current", pos.get("entry", 0)))
        is_filled = status in ("체결완료", "보유")

        self._lbl_pos_hint.setText(
            f"{'📌 보유' if is_filled else '⏳ 미체결'}: {strat}")
        self._btn_cancel_pos.setEnabled(not is_filled)
        self._btn_close_lmt.setEnabled(is_filled)
        self._btn_close_mkt.setEnabled(is_filled)
        self._spin_close_price.setEnabled(is_filled)

        if is_filled and current > 0:
            self._spin_close_price.setValue(round(current, 2))

    def _on_close_lmt(self):
        """[FIX-J] 지정가 청산."""
        row = getattr(self, '_selected_pos_row', -1)
        if row < 0 or row >= len(self._positions):
            return
        lmt_price = round(self._spin_close_price.value(), 2)
        if lmt_price <= 0:
            return
        pos = self._positions[row]
        if callable(self._close_pos_callback):
            self._close_pos_callback(pos, lmt_price=lmt_price)

    def _on_close_mkt(self):
        """[FIX-J] MKT 청산."""
        row = getattr(self, '_selected_pos_row', -1)
        if row < 0 or row >= len(self._positions):
            return
        pos = self._positions[row]
        if callable(self._close_pos_callback):
            self._close_pos_callback(pos, lmt_price=None)

    def _on_close_position(self):
        """하위 호환 — MKT 청산으로 위임."""
        self._on_close_mkt()

    def _on_cancel_pos_order(self):
        row = getattr(self, '_selected_pos_row', -1)
        if row < 0 or row >= len(self._positions):
            return
        oid = self._positions[row].get("oid")
        if oid and callable(getattr(self, '_cancel_order_callback', None)):
            self._cancel_order_callback(oid)

    # ══════════════════════════════════════════════════════════
    # 미체결 탭 이벤트
    # ══════════════════════════════════════════════════════════

    def _on_chaser_mode_toggle(self):
        is_manual = self._rb_chaser_manual.isChecked()
        self._spin_manual_price.setVisible(is_manual)
        self._btn_manual_send.setVisible(is_manual)
        self._btn_modify_p1.setVisible(not is_manual)
        self._btn_modify_m1.setVisible(not is_manual)
        self._lbl_chaser_desc.setText(
            "✏ 선택 행 가격 직접 입력 후 전송" if is_manual
            else "⏱ 미체결 5초 후 자동 1틱 정정 (최대 3회)")
        if callable(getattr(self, '_chaser_mode_callback', None)):
            self._chaser_mode_callback("manual" if is_manual else "auto")

    def _on_order_row_clicked(self, row, col):
        if not self._rb_chaser_manual.isChecked():
            return
        price_item = self._tbl_open_orders.item(row, 4)
        if price_item:
            try:
                self._spin_manual_price.setValue(
                    float(price_item.text().replace("$", "")))
            except ValueError:
                pass

    def _on_manual_price_send(self):
        new_price = self._spin_manual_price.value()
        row = self._tbl_open_orders.currentRow()
        if row < 0:
            return
        oid_item = self._tbl_open_orders.item(row, 0)
        if not oid_item:
            return
        try:
            oid = int(oid_item.text())
        except ValueError:
            return
        if callable(getattr(self, '_manual_modify_callback', None)):
            self._manual_modify_callback(oid, new_price)

    def _on_modify_tick(self, direction: int) -> None:
        """[FIX-MB1] +1호가 / -1호가 정정 버튼 핸들러."""
        row = self._tbl_open_orders.currentRow()
        if row < 0:
            return
        oid_item   = self._tbl_open_orders.item(row, 0)
        price_item = self._tbl_open_orders.item(row, 4)
        if not oid_item or not price_item:
            return
        try:
            oid = int(oid_item.text())
        except ValueError:
            return
        try:
            current_price = float(price_item.text().replace("$", ""))
        except ValueError:
            return

        try:
            from combo_order_chaser import _get_tick_size, _snap_to_tick
            tick      = _get_tick_size(current_price)
            raw_price = current_price + direction * tick
            snap_dir  = "buy" if direction > 0 else "sell"
            new_price = _snap_to_tick(raw_price, tick, snap_dir)
            new_price = max(round(new_price, 2), tick)
        except Exception:
            new_price = round(max(current_price + direction * 0.05, 0.05), 2)

        if callable(getattr(self, '_manual_modify_callback', None)):
            self._manual_modify_callback(oid, new_price)

    # ══════════════════════════════════════════════════════════
    # 증거금 모드 토글
    # ══════════════════════════════════════════════════════════

    def _on_margin_mode_toggle(self):
        is_server = self._rb_margin_server.isChecked()
        self._lbl_margin_mode_desc.setText(
            "서버 whatIf (느림)" if is_server else "즉시 계산")
        if callable(self._margin_mode_callback):
            self._margin_mode_callback(is_server)

    # ══════════════════════════════════════════════════════════
    # [SLEEP] 예약 주문 버튼 ref 지연 주입
    # ══════════════════════════════════════════════════════════

    def _inject_sleep_ref(self):
        """SleepOrderButton 에 ref 주입 (parent 체인 탐색)."""
        try:
            btn = getattr(self, '_sleep_btn', None)
            if btn is None:
                return
            ref = None
            w   = self
            for depth in range(10):
                w = w.parent()
                if w is None:
                    print(f"[SyntheticPanel] parent 체인 끊김 at depth {depth}")
                    break
                print(f"[SyntheticPanel] depth={depth} type={type(w).__name__} "
                      f"has_sleep={hasattr(w, '_sleep_get_chain')}")
                if hasattr(w, '_sleep_get_chain'):
                    ref = w
                    break
            if ref is not None:
                btn.set_ref(ref)
                print(f"[SyntheticPanel] sleep ref 주입 완료: {type(ref).__name__}")
            else:
                from PyQt5.QtCore import QTimer as _QT
                _QT.singleShot(1000, self._inject_sleep_ref)
                print("[SyntheticPanel] sleep ref 탐색 실패 — 1초 후 재시도")
        except Exception as e:
            print(f"[SyntheticPanel] _inject_sleep_ref 실패: {e}")

    # ══════════════════════════════════════════════════════════
    # 테이블 갱신
    # ══════════════════════════════════════════════════════════

    def _refresh_pos_table(self):
        tbl = self._tbl_pos
        tbl.setRowCount(0)
        if not self._positions:
            self._lbl_no_pos.setVisible(True)
            tbl.setVisible(False)
            self._lbl_total_pnl.setText("$0.00")
            self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
            return

        self._lbl_no_pos.setVisible(False)
        tbl.setVisible(True)
        tbl.setRowCount(len(self._positions))
        total_pnl = 0.0

        for r, pos in enumerate(self._positions):
            qty        = pos.get("qty", 1)
            entry      = pos.get("entry", 0.0)
            current    = pos.get("current", entry)
            status     = pos.get("status", "미체결")
            is_filled  = status in ("체결완료", "보유")
            is_closing = status == "청산중"
            pnl        = ((current - entry) * qty * 100
                          if is_filled and not is_closing else 0.0)
            total_pnl += pnl
            pnl_col    = ("#00ff88" if pnl > 0
                          else "#ff4444" if pnl < 0 else "#888899")

            def _it(text, color="#cccccc", align=Qt.AlignCenter):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            if is_filled and not is_closing and entry > 0:
                pnl_rate     = (current - entry) / entry * 100
                pnl_rate_txt = f"{pnl_rate:+.1f}%"
                pnl_rate_col = ("#00ff88" if pnl_rate > 0
                                else "#ff4444" if pnl_rate < 0 else "#888899")
            else:
                pnl_rate_txt = "―"
                pnl_rate_col = "#888899"

            if is_closing:
                st_col, st_text = "#888888", "🔄 청산중"
            elif is_filled:
                st_col, st_text = "#00ff88", "📌 보유"
            else:
                st_col, st_text = "#ffaa44", "⏳ 미체결"

            expiry_txt, expiry_col = _format_expiry(pos.get("legs", []))
            tbl.setItem(r, 0, _it(expiry_txt, expiry_col))
            tbl.setItem(r, 1, _it(
                pos.get("strategy", "―"), "#e0e0ff",
                Qt.AlignLeft | Qt.AlignVCenter))
            tbl.setItem(r, 2, _it(str(qty),           "#aaaaaa"))
            tbl.setItem(r, 3, _it(f"${entry:.2f}",    "#aaaaaa"))
            tbl.setItem(r, 4, _it(f"${current:.2f}",  "#e0e0e0"))
            tbl.setItem(r, 5, _it(
                f"${pnl:+,.2f}" if is_filled else "―", pnl_col))
            tbl.setItem(r, 6, _it(pnl_rate_txt, pnl_rate_col))

            # [FIX-DELTA] 칼럼 7: 지수 5P당 예상 손익률
            delta_pct_txt, delta_pct_col = _calc_delta_pnl_pct(pos)
            delta_it = QTableWidgetItem(delta_pct_txt)
            delta_it.setTextAlignment(Qt.AlignCenter)
            delta_it.setForeground(QColor(delta_pct_col))
            delta_it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            delta_font = QFont(); delta_font.setPointSize(14)
            delta_it.setFont(delta_font)
            tbl.setItem(r, 7, delta_it)

            tbl.setItem(r, 8, _it(st_text, st_col))

        tc = ("#00ff88" if total_pnl > 0
              else "#ff4444" if total_pnl < 0 else "#888899")
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")

        # [FIX-BANNER] 수익률 배너 갱신 — 최대 수익률 포지션 기준
        if self.profit_alert_banner and self._positions:
            try:
                best_pct = 0.0
                for pos in self._positions:
                    if pos.get("status") not in ("체결완료", "보유"):
                        continue
                    entry   = float(pos.get("entry", 0) or 0)
                    current = float(pos.get("current", entry) or entry)
                    side    = pos.get("side", "SELL")
                    if entry <= 0:
                        continue
                    pct = ((entry - current) / entry * 100
                           if side == "SELL"
                           else (current - entry) / entry * 100)
                    if pct > best_pct:
                        best_pct = pct
                self.profit_alert_banner.update_pct(best_pct)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════

    def set_cancel_order_callback(self, fn):
        self._cancel_order_callback = fn

    def set_close_pos_callback(self, fn):
        """청산 콜백. fn(pos_dict, lmt_price=None)"""
        self._close_pos_callback = fn

    def set_close_position_callback(self, fn):
        """하위 호환 별칭."""
        self.set_close_pos_callback(fn)

    def set_margin_mode_callback(self, fn):
        self._margin_mode_callback = fn

    def set_chaser_mode_callback(self, fn):
        self._chaser_mode_callback = fn

    def set_manual_modify_callback(self, fn):
        self._manual_modify_callback = fn

    def is_auto_chaser(self) -> bool:
        return self._rb_chaser_auto.isChecked()

    def set_current_order_price(self, price: float):
        self._spin_manual_price.setValue(round(price, 2))

    def mark_position_filled(self, oid: int):
        for pos in self._positions:
            if pos.get("oid") == oid:
                pos["status"] = "보유"
        self._refresh_pos_table()

    def mark_position_cancelled(self, oid: int):
        self._positions = [p for p in self._positions if p.get("oid") != oid]
        self._refresh_pos_table()

    def mark_position_closing(self, oid: int):
        """[FIX-CLOSE] 청산 주문 접수 → 해당 행 '청산중' 상태로 변경."""
        for pos in self._positions:
            if pos.get("oid") == oid:
                pos["status"] = "청산중"
                break
        self._refresh_pos_table()
        self._btn_close_lmt.setEnabled(False)
        self._btn_close_mkt.setEnabled(False)
        self._spin_close_price.setEnabled(False)
        self._lbl_pos_hint.setText("🔄 청산 주문 접수됨 — 체결 대기 중")

    def remove_position_by_oid(self, oid: int):
        """[FIX-L] 청산 Filled 콜백에서 oid 기준으로 패널 포지션 제거."""
        self._positions = [p for p in self._positions if p.get("oid") != oid]
        self._refresh_pos_table()

    def add_position(self, fill_info: dict):
        """[FIX-M] 신규 포지션 추가 + 전략명 행사가 보강."""
        fill_info = dict(fill_info)
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        fill_info["strategy"] = _enrich_strategy_name(fill_info)
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def update_position_prices(self, oid: int, current_price: float):
        """[FIX-K] oid 기준으로 가격 갱신."""
        for pos in self._positions:
            if pos.get("oid") == oid:
                pos["current"] = current_price
                break
        self._refresh_pos_table()

    def clear_positions(self):
        self._positions.clear()
        self._refresh_pos_table()

    def update_margin(self, available: float, required: float,
                      strategy: str = "―", cost: str = "―"):
        self._lbl_m_strategy.setText(strategy or "―")
        self._lbl_m_cost.setText(cost or "―")
        self._lbl_m_available.setText(f"${available:,.2f}")
        self._lbl_m_required.setText(f"${required:,.2f}")
        if required <= 0:
            st, col, bg, bc = "— 데이터 없음 —", "#555577", "#0a0a1e", "#2a2a4a"
        elif available >= required:
            surplus = available - required
            st  = f"✅  주문 가능  (여유 ${surplus:,.2f})"
            col, bg, bc = "#00ff88", "#071a0e", "#00ff88"
        else:
            shortage = required - available
            st  = f"❌  증거금 부족  (${shortage:,.2f} 부족)"
            col, bg, bc = "#ff4444", "#1a0707", "#ff4444"
        self._lbl_margin_status.setText(st)
        self._lbl_margin_status.setStyleSheet(
            f"color:{col};padding:7px;border:1px solid {bc};"
            f"border-radius:4px;background:{bg};")
        self._tabs.setCurrentIndex(0)

    def update_open_orders(self, orders: list):
        tbl = self._tbl_open_orders
        tbl.setRowCount(0)
        for o in orders:
            r = tbl.rowCount(); tbl.insertRow(r)

            def _it(text, color="#ccc"):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            action_col = "#00ff88" if o.get("action") == "BUY" else "#ff6666"
            tbl.setItem(r, 0, _it(o.get("oid", ""),   "#888"))
            tbl.setItem(r, 1, _it(o.get("sym", ""),   "#ffd700"))
            tbl.setItem(r, 2, _it(o.get("action", ""),action_col))
            tbl.setItem(r, 3, _it(o.get("qty", ""),   "#ccc"))
            tbl.setItem(r, 4, _it(
                f"{o.get('lmt', 0):.2f}" if o.get('lmt') else "MKT", "#ffaa44"))
            st     = o.get("status", "")
            st_col = ("#00ff88" if "Submit" in st
                      else "#ffaa44" if "Pending" in st else "#888")
            tbl.setItem(r, 5, _it(st, st_col))
        self._tabs.setCurrentIndex(2)

    def get_selected_order(self):
        return self._tbl_open_orders.currentRow()

    def update_scenario_greeks(self, legs: list, entry: float = 0.0,
                               und_price: float = 0.0) -> None:
        """[FIX-SCENARIO] 레그 설정 완료 시 호출 → 시나리오 탭 Greeks 갱신."""
        if hasattr(self, '_scenario_tab'):
            self._scenario_tab.set_greeks(legs, entry, und_price)
