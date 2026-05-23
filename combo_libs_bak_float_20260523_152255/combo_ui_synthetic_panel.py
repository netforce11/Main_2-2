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
        from combo_ui_panel_constants import _pal
        from combo_ui_panel_utils import _calc_delta_pnl_pct, _format_expiry
        from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QWidget, QTableWidgetItem
        from PyQt5.QtGui import QColor, QFont
        from PyQt5.QtCore import Qt

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

        # [BUG-4] 테마 팔레트에서 모든 색상 동적 참조
        t         = _pal()
        fg_normal = t.get("widget_fg", "#111827")
        fg_dim    = t.get("tbl_grid",  "#9ca3af")

        # 테마별 수익/손실/중립 색상
        # light: 진한색 계열 / dark계열: 형광색 계열
        _is_dark  = t.get("win_bg", "#fff")[1:3].lower() < "88"
        col_gain  = "#00bb66" if _is_dark else "#15803d"
        col_loss  = "#ff4444" if _is_dark else "#dc2626"
        col_neut  = t.get("tbl_grid", "#9ca3af")
        col_warn  = "#ffaa44" if _is_dark else "#d97706"
        col_close = t.get("hdr_fg",   "#6b7280")

        total_pnl = 0.0

        for r, pos in enumerate(self._positions):
            qty        = pos.get("qty", 1)
            entry      = pos.get("entry", 0.0)
            current    = pos.get("current", entry)
            status     = pos.get("status", "미체결")
            is_filled  = status in ("체결완료", "보유")
            is_closing = status == "청산중"

            # [BUG-2] 청산중에도 pnl/수익률 계산 유지
            if is_filled or is_closing:
                pnl = (current - entry) * qty * 100
            else:
                pnl = 0.0
            total_pnl += pnl
            pnl_col = (col_gain if pnl > 0 else col_loss if pnl < 0 else col_neut)

            show_rate = (is_filled or is_closing) and entry > 0
            if show_rate:
                pnl_rate     = (current - entry) / entry * 100
                pnl_rate_txt = f"{pnl_rate:+.1f}%"
                pnl_rate_col = (col_gain if pnl_rate > 0
                                else col_loss if pnl_rate < 0 else col_neut)
            else:
                pnl_rate_txt = "―"
                pnl_rate_col = fg_dim

            if is_closing:
                st_col, st_text = col_close, "🔄 청산중"
            elif is_filled:
                st_col, st_text = col_gain,  "📌 보유"
            else:
                st_col, st_text = col_warn,  "⏳ 미체결"

            # [BUG-4] 기본 색상을 테마 팔레트에서 가져오는 _it 헬퍼
            def _it(text, color=None, align=Qt.AlignCenter,
                    _fg=fg_normal):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color if color else _fg))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            expiry_txt, expiry_col = _format_expiry(pos.get("legs", []))
            tbl.setItem(r, 0, _it(expiry_txt, expiry_col))
            tbl.setItem(r, 1, _it(
                pos.get("strategy", "―"), fg_normal,
                Qt.AlignLeft | Qt.AlignVCenter))
            tbl.setItem(r, 2, _it(str(qty),          fg_dim))
            tbl.setItem(r, 3, _it(f"${entry:.2f}",   fg_dim))
            tbl.setItem(r, 4, _it(f"${current:.2f}", fg_normal))
            tbl.setItem(r, 5, _it(
                f"${pnl:+,.2f}" if (is_filled or is_closing) else "―", pnl_col))
            tbl.setItem(r, 6, _it(pnl_rate_txt, pnl_rate_col))

            tbl.setItem(r, 7, _it(st_text, st_col))

            _cell_w   = QWidget()
            _cell_lay = QHBoxLayout(_cell_w)
            _cell_lay.setContentsMargins(1, 0, 1, 0)
            _cell_lay.setSpacing(2)
            _cell_w.setStyleSheet("background:transparent;")

            if is_filled and not is_closing:
                _btn_close_rsv = QPushButton("📌 예약")
                _btn_close_rsv.setFixedHeight(22)
                _btn_close_rsv.setStyleSheet(
                    "QPushButton{background:#1a0a1a;color:#ff6b6b;"
                    "font-size:11px;font-weight:bold;"
                    "border:1px solid #5a1a3a;border-radius:3px;padding:1px 4px;}"
                    "QPushButton:hover{background:#2a0a2a;color:#ff8888;}")
                _p = dict(pos)
                _btn_close_rsv.clicked.connect(
                    lambda _, p=_p: self._open_close_reserve_dialog(p))
                _cell_lay.addWidget(_btn_close_rsv)

            _btn_del = QPushButton("🗑")
            _btn_del.setFixedSize(24, 22)
            _btn_del.setToolTip("잔고에서 수동 삭제 (주문 없이 즉시 제거)")
            _btn_del.setStyleSheet(
                "QPushButton{background:#1a0808;color:#ff4444;"
                "font-size:12px;border:1px solid #3a1010;"
                "border-radius:3px;padding:0px;}"
                "QPushButton:hover{background:#2a0808;color:#ff6666;}")
            _pos_oid = pos.get("oid")
            _btn_del.clicked.connect(
                lambda _, o=_pos_oid: self._manual_delete_position(o))
            _cell_lay.addWidget(_btn_del)
            tbl.setCellWidget(r, 8, _cell_w)

        tc = ("#00ff88" if total_pnl > 0
              else "#ff4444" if total_pnl < 0 else "#888899")
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")

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

    def update_position_prices(self, oid: int, current_price: float):
        """[BUG-3] oid 행만 직접 갱신 — 테이블 전체 rebuild 제거."""
        from combo_ui_panel_constants import _pal
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import Qt

        row_idx = None
        for i, pos in enumerate(self._positions):
            if pos.get("oid") == oid:
                pos["current"] = current_price
                row_idx = i
                break

        if row_idx is None:
            return

        pos        = self._positions[row_idx]
        entry      = pos.get("entry", 0.0)
        qty        = pos.get("qty", 1)
        status     = pos.get("status", "미체결")
        is_filled  = status in ("체결완료", "보유")
        is_closing = status == "청산중"

        t         = _pal()
        fg_dim    = t.get("tbl_grid",  "#9ca3af")
        _is_dark  = t.get("win_bg", "#fff")[1:3].lower() < "88"
        col_gain  = "#00bb66" if _is_dark else "#15803d"
        col_loss  = "#ff4444" if _is_dark else "#dc2626"
        col_neut  = t.get("tbl_grid", "#9ca3af")

        tbl = self._tbl_pos
        if row_idx >= tbl.rowCount():
            self._refresh_pos_table()
            return

        def _set(col, text, color):
            item = tbl.item(row_idx, col)
            if item is None:
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tbl.setItem(row_idx, col, item)
            item.setText(str(text))
            item.setForeground(QColor(color))

        _set(4, f"${current_price:.2f}", t.get("widget_fg", "#111827"))

        if is_filled or is_closing:
            pnl     = (current_price - entry) * qty * 100
            pnl_col = (col_gain if pnl > 0 else col_loss if pnl < 0 else col_neut)
            _set(5, f"${pnl:+,.2f}", pnl_col)
        else:
            _set(5, "―", fg_dim)

        # [BUG-2] 청산중에도 수익률 표시
        show_rate = (is_filled or is_closing) and entry > 0
        if show_rate:
            pnl_rate = (current_price - entry) / entry * 100
            rate_col = (col_gain if pnl_rate > 0 else col_loss if pnl_rate < 0 else col_neut)
            _set(6, f"{pnl_rate:+.1f}%", rate_col)
        else:
            _set(6, "―", fg_dim)

        total_pnl = 0.0
        for p in self._positions:
            s = p.get("status", "")
            if s in ("체결완료", "보유", "청산중"):
                e = p.get("entry", 0.0)
                c = p.get("current", e)
                q = p.get("qty", 1)
                total_pnl += (c - e) * q * 100
        tc = (col_gain if total_pnl > 0 else col_loss if total_pnl < 0 else col_neut)
        self._lbl_total_pnl.setText(f"${total_pnl:+,.2f}")
        self._lbl_total_pnl.setStyleSheet(f"color:{tc};border:none;")

    def add_position(self, fill_info: dict):
        """[FIX-M] 신규 포지션 추가 + 전략명 행사가 보강."""
        fill_info = dict(fill_info)
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        # [FIX-STRAT] 실시간 체결/복원 모두 행사가 포함 전략명으로 보강
        fill_info["strategy"] = _enrich_strategy_name(fill_info)
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def _open_close_reserve_dialog(self, pos: dict) -> None:
        """청산 예약 다이얼로그 — 행의 📌 예약 버튼 클릭 시 호출."""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
            QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
            QTimeEdit, QMessageBox,
        )
        from PyQt5.QtCore import QTime

        # [FIX] parent를 최상위 윈도우로 설정 — 탭 레이아웃 재조정 시 floating 방지
        _top = self
        while _top.parent() is not None:
            _top = _top.parent()
        dlg = QDialog(_top)
        dlg.setWindowTitle("📌 청산 예약 설정")
        dlg.setFixedWidth(360)
        dlg.setStyleSheet(
            "QDialog{background:#0a0a18;}"
            "QLabel{color:#dde0f0;font-size:13px;border:none;}"
            "QTimeEdit,QDoubleSpinBox,QSpinBox{"
            "background:#0a0a18;color:#dde0f0;font-size:13px;"
            "border:1px solid #2e3060;border-radius:4px;padding:3px;}"
        )

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        # 포지션 정보
        strat = pos.get("strategy", "")
        oid   = pos.get("oid", "")
        current = float(pos.get("current", pos.get("entry", 0)))

        info = QLabel(f"📌 {strat}\nOID = {oid}")
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#ffd700;font-size:13px;border:none;"
            "background:#0d0d20;border-radius:4px;padding:6px 8px;")
        lay.addWidget(info)

        # 설정 그리드
        grid = QGridLayout()
        grid.setSpacing(8)

        # From
        grid.addWidget(QLabel("From (KST):"), 0, 0)
        te_from = QTimeEdit()
        te_from.setDisplayFormat("HH:mm")
        te_from.setTime(QTime(23, 0))
        grid.addWidget(te_from, 0, 1)

        # To
        grid.addWidget(QLabel("To (KST):"), 0, 2)
        te_to = QTimeEdit()
        te_to.setDisplayFormat("HH:mm")
        te_to.setTime(QTime(1, 30))
        grid.addWidget(te_to, 0, 3)

        # 목표가
        grid.addWidget(QLabel("선매도 목표가:"), 1, 0)
        dsb = QDoubleSpinBox()
        dsb.setRange(0.01, 99.99)
        dsb.setSingleStep(0.05)
        dsb.setDecimals(2)
        dsb.setPrefix("$")
        dsb.setValue(round(current, 2) if current > 0 else 1.00)
        grid.addWidget(dsb, 1, 1)

        # 사정권 미리보기
        thresh_lbl = QLabel()
        thresh_lbl.setStyleSheet("color:#ffaa44;font-size:11px;border:none;")
        def _update_thresh(v):
            tick = 0.10 if v >= 3.00 else 0.05
            thresh_lbl.setText(f"사정권 ≤${v - 2*tick:.2f}")
        dsb.valueChanged.connect(_update_thresh)
        _update_thresh(dsb.value())
        grid.addWidget(thresh_lbl, 1, 2, 1, 2)

        # 최대 정정
        grid.addWidget(QLabel("최대 정정:"), 2, 0)
        sb = QSpinBox()
        sb.setRange(1, 10)
        sb.setValue(3)
        sb.setSuffix(" 회")
        grid.addWidget(sb, 2, 1)
        grid.addWidget(QLabel("초과 시 시장가"), 2, 2, 1, 2)

        lay.addLayout(grid)

        # 슬롯 안내
        slot_lbl = QLabel()
        slot_lbl.setStyleSheet("color:#90caf9;font-size:11px;border:none;")
        lay.addWidget(slot_lbl)

        # 빈 슬롯 찾기
        def _find_empty_slot() -> int:
            try:
                from Sleep_Order.position_close_config import pos_close_cfg
                for i in range(3):
                    if not pos_close_cfg.is_slot_active(i):
                        return i
            except Exception:
                pass
            return -1

        empty = _find_empty_slot()
        if empty >= 0:
            slot_lbl.setText(f"→ 슬롯 {empty+1} 에 등록됩니다")
        else:
            slot_lbl.setText("⚠️ 빈 슬롯 없음 (최대 3개)")

        # 버튼 행
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("📌 등록")
        ok_btn.setFixedHeight(28)
        ok_btn.setStyleSheet(
            "QPushButton{background:#0a2a0a;color:#00ff88;font-size:13px;"
            "font-weight:bold;border:1px solid #00ff44;border-radius:4px;padding:2px 16px;}"
            "QPushButton:hover{background:#1a3a1a;}"
            "QPushButton:disabled{background:#0a0a0a;color:#333;border-color:#222;}")
        ok_btn.setEnabled(empty >= 0)

        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(28)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#1a0a0a;color:#ff6666;font-size:13px;"
            "border:1px solid #5a1a1a;border-radius:4px;padding:2px 16px;}"
            "QPushButton:hover{background:#2a0a0a;}")

        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        def _on_ok():
            idx = _find_empty_slot()
            if idx < 0:
                QMessageBox.warning(dlg, "슬롯 없음", "빈 슬롯이 없습니다.")
                return
            try:
                from Sleep_Order.position_close_config  import pos_close_cfg
                from Sleep_Order.position_close_watcher import PositionCloseWatcher

                frm   = te_from.time().toString("HH:mm")
                to    = te_to.time().toString("HH:mm")
                price = dsb.value()
                max_c = sb.value()

                pos_close_cfg.set_slot(idx, "close_from_kst",        frm)
                pos_close_cfg.set_slot(idx, "close_to_kst",          to)
                pos_close_cfg.set_slot(idx, "close_premium_price",   price)
                pos_close_cfg.set_slot(idx, "close_max_corrections", max_c)

                # ref 탐색 (parent 체인)
                ref = None
                w   = self
                for _ in range(10):
                    w = w.parent() if w else None
                    if w and hasattr(w, "synthetic_panel") and \
                            hasattr(w, "_sleep_get_chain"):
                        ref = w
                        break

                PositionCloseWatcher.get().register(idx, pos, ref)
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "오류", str(e))

        ok_btn.clicked.connect(_on_ok)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec_()

    def _manual_delete_position(self, oid: int) -> None:
        """[MANUAL-DEL] 🗑 버튼 — 확인 후 파일·패널·스트림 동시 삭제."""
        from PyQt5.QtWidgets import QMessageBox
        pos = next((p for p in self._positions if p.get("oid") == oid), None)
        strat = pos.get("strategy", f"OID={oid}") if pos else f"OID={oid}"

        ret = QMessageBox.question(
            self, "잔고 수동 삭제",
            (f"아래 포지션을 잔고에서 삭제합니다.\n\n"
             f"  {strat}\n\n"
             f"\u26a0 주문 없이 화면에서만 제거됩니다.\n"
             f"실제 IB 포지션이 남아있다면 직접 청산하세요.\n\n"
             f"계속하시겠습니까?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        # ref 탐색 (스트림 해제용)
        ref = None
        w = self
        for _ in range(10):
            w = w.parent() if w else None
            if w and hasattr(w, 'synthetic_panel'):
                ref = w
                break

        try:
            from combo_position_store import manual_remove_position
            manual_remove_position(oid, panel=self, ref=ref,
                                   log_fn=None)
        except Exception as e:
            QMessageBox.warning(self, "삭제 오류", str(e))

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