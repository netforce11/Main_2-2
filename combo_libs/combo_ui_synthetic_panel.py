"""combo_ui_synthetic_panel.py — SyntheticStatusPanel 위젯  v3.0
탭1: 📊 증거금 확인  탭2: 📋 합성 잔고  탭3: 📋 미체결  탭4: 📈 시나리오

[FIX-J] 지정가 청산 UI 추가
[FIX-K] update_position_prices — oid 기준으로 변경
[FIX-L] remove_position_by_oid 추가
[FIX-M] add_position 에서 _enrich_strategy_name 적용
[FIX-BANNER] Wolf System 배너 + 수익률 경고 배너 추가
  · WolfSystemBanner  — 선주문 ON / 체결·취소 OFF
  · ProfitAlertBanner — 수익률 400/450/500% 구간 경고 + 테스트 UI
  · Chaser 자동 모드 기본값 OFF (수동 모드로 시작)
[FIX-DELTA] 지수 5P당 예상 손익률 칼럼 추가
  · _calc_delta_pnl_pct() — 포지션 델타 × 5P × 100 / DEBIT 가격
  · 테이블 칼럼 8→9 ("5P손익%" 신규, 형광색 #ffff44, 14pt)
  · legs[i]['delta'] 필드 활용 (combo_ui_left_chain.py 에서 주입)
[FIX-SCENARIO] 📈 시나리오 탭 추가 (Mode B + C안)
  · ScenarioTab 위젯 — 지수 이동/만기까지 남은 시간/IV 변화 슬라이더
  · Δ+Γ 보정, Θ 세타 손실, ν 베가 효과 종합 계산
  · 스프레드 상한 처리 (max_spread = 행사가 차이)
  · 시나리오 매트릭스 (지수 이동 × 만기까지 남은 시간)
  · update_scenario_greeks(legs, entry) 외부 API
  · 만기까지 남은 시간 ET 기준 자동 계산 + 슬라이더 기본값 설정
[FIX-BS] Black-Scholes 재계산 방식으로 정확도 향상
  · _bs_price() — 순수 Python BS 공식 (외부 라이브러리 불필요)
  · _bs_spread_price() — 스프레드 포지션 BS 재계산
  · IV 있으면 BS 사용, 없으면 Δ+½Γ 폴백 (자동 전환)
  · 상한 클램프 유지 (스프레드 최대 수익 한계)
  · 계산 모드 표시 (BS / 근사)
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTabWidget, QTableWidget, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QSizePolicy, QPushButton, QDoubleSpinBox,
    QSlider, QScrollArea, QGridLayout,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
import math

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


def _f(pt, bold=False):
    f = QFont(); f.setPointSize(pt)
    if bold: f.setBold(True)
    return f

_TAB_STYLE = """
QTabWidget::pane { border:1px solid #1a1a3a; background:#07070f; }
QTabBar::tab { background:#0d0d22; color:#666688;
    padding:5px 12px; border:1px solid #1a1a3a; border-bottom:none; }
QTabBar::tab:selected { background:#07070f; color:#e0e0ff; border-top:2px solid #00ff88; }
QTabBar::tab:hover { color:#aaaacc; }
"""
_TBL_STYLE = """
QTableWidget { background:#07070f; alternate-background-color:#0c0c20;
    color:#cccccc; gridline-color:#1a1a3a; border:none; }
QTableWidget::item:selected { background:#1a1a3a; color:#ffffff; }
QHeaderView::section { background:#0a0a1e; color:#90caf9;
    border:1px solid #1a1a3a; font-weight:bold; padding:3px 6px; }
"""


class SyntheticStatusPanel(QWidget):
    """합성 주문 상태 패널 (v2.6)."""

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

        # [FIX-BANNER] 배너 생성 후 잔고 탭 레이아웃에 추가
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

        # ── [SLEEP] 예약 주문 버튼에 ref 주입 (parent 확정 후) ─
        # showEvent 에서 주입하면 더 안전하므로 여기서는 타이머 사용
        try:
            from PyQt5.QtCore import QTimer as _QT
            _QT.singleShot(0, self._inject_sleep_ref)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # UI 빌드
    # ══════════════════════════════════════════════════════════

    def _build_ui(self):
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(6, 4, 6, 2); mode_row.setSpacing(8)
        lbl = QLabel("💰 증거금:")
        lbl.setStyleSheet("color:#888;font-size:11px;border:none;")
        mode_row.addWidget(lbl)

        self._rb_margin_local  = QRadioButton("🖥 로컬")
        self._rb_margin_server = QRadioButton("☁ 서버")
        self._rb_margin_local.setChecked(True)
        for rb in (self._rb_margin_local, self._rb_margin_server):
            rb.setStyleSheet(
                "color:#ccc;font-size:11px;border:none;"
                "QRadioButton::indicator{width:12px;height:12px;}")
        self._margin_grp = QButtonGroup(self)
        self._margin_grp.addButton(self._rb_margin_local,  0)
        self._margin_grp.addButton(self._rb_margin_server, 1)
        mode_row.addWidget(self._rb_margin_local)
        mode_row.addWidget(self._rb_margin_server)

        self._lbl_margin_mode_desc = QLabel("즉시 계산")
        self._lbl_margin_mode_desc.setStyleSheet("color:#445566;font-size:10px;border:none;")
        mode_row.addWidget(self._lbl_margin_mode_desc)

        # ── [SLEEP] 예약 주문 버튼 우측 상단 ───────────────────
        try:
            import sys, os as _os
            _this_dir = _os.path.dirname(_os.path.abspath(__file__))
            if _this_dir not in sys.path:
                sys.path.insert(0, _this_dir)
            from Sleep_Order.sleep_order_ui import SleepOrderButton
            self._sleep_btn = SleepOrderButton(ref=None, parent=self)
            mode_row.addWidget(self._sleep_btn)
        except Exception as _e:
            print(f"[SyntheticPanel] sleep_order 버튼 오류: {_e}")
            import traceback; traceback.print_exc()

        mode_row.addStretch()

        self._rb_margin_local.toggled.connect(self._on_margin_mode_toggle)
        self._rb_margin_server.toggled.connect(self._on_margin_mode_toggle)

        mode_widget = QWidget(); mode_widget.setStyleSheet("background:#07070f;")
        mode_widget.setLayout(mode_row)
        root.addWidget(mode_widget)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color:#1a1a3a;border:none;"); root.addWidget(sep)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.tabBar().setFont(_f(12, bold=True))
        self._tabs.addTab(self._build_margin_tab(),      "📊 증거금 확인")
        self._tabs.addTab(self._build_position_tab(),    "📋 합성 잔고")
        self._tabs.addTab(self._build_open_orders_tab(), "📋 미체결")

        # [FIX-SCENARIO] 시나리오 탭 추가
        self._scenario_tab = ScenarioTab()
        self._tabs.addTab(self._scenario_tab, "📈 시나리오")

        root.addWidget(self._tabs)

    def _build_margin_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(5)

        def kv(label):
            row = QHBoxLayout()
            lk = QLabel(label); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
            lv = QLabel("―");   lv.setStyleSheet("color:#e0e0e0;border:none;"); lv.setFont(_f(13, True))
            row.addWidget(lk); row.addStretch(); row.addWidget(lv)
            return row, lv

        row_s, self._lbl_m_strategy  = kv("전략명")
        row_c, self._lbl_m_cost      = kv("순 비용")
        row_a, self._lbl_m_available = kv("주문가능")
        row_r, self._lbl_m_required  = kv("필요증거금")

        for row in (row_s, row_c): lay.addLayout(row)
        sep1 = QFrame(); sep1.setFrameShape(QFrame.HLine)
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background-color:#1a1a3a;border:none;"); lay.addWidget(sep1)
        for row in (row_a, row_r): lay.addLayout(row)
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color:#1a1a3a;border:none;"); lay.addWidget(sep2)

        self._lbl_margin_status = QLabel("―")
        self._lbl_margin_status.setAlignment(Qt.AlignCenter)
        self._lbl_margin_status.setFont(_f(13, bold=True))
        self._lbl_margin_status.setStyleSheet(
            "color:#555577;padding:7px;border:1px solid #2a2a4a;"
            "border-radius:4px;background:#0a0a1e;")
        lay.addWidget(self._lbl_margin_status)
        lay.addStretch()
        return w

    def _build_position_tab(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(4)

        summary = QHBoxLayout()
        lk = QLabel("총 손익"); lk.setStyleSheet("color:#888;border:none;"); lk.setFont(_f(12))
        self._lbl_total_pnl = QLabel("$0.00")
        self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
        self._lbl_total_pnl.setFont(_f(14, bold=True))
        summary.addWidget(lk); summary.addStretch(); summary.addWidget(self._lbl_total_pnl)
        lay.addLayout(summary)

        self._lbl_no_pos = QLabel("합성 주문 내역이 없습니다.")
        self._lbl_no_pos.setAlignment(Qt.AlignCenter)
        self._lbl_no_pos.setFont(_f(12))
        self._lbl_no_pos.setStyleSheet("color:#333355;padding:14px;")
        lay.addWidget(self._lbl_no_pos)

        self._tbl_pos = QTableWidget(0, 9)
        self._tbl_pos.setHorizontalHeaderLabels(
            ["만기", "전략명", "수량", "진입가", "현재가", "손익", "수익률", "5P손익(%)", "상태"])
        self._tbl_pos.setFont(_f(12))
        self._tbl_pos.horizontalHeader().setFont(_f(11, bold=True))
        self._tbl_pos.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_pos.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(2, 9):
            self._tbl_pos.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeToContents)
        self._tbl_pos.verticalHeader().setVisible(False)
        self._tbl_pos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_pos.setAlternatingRowColors(True)
        self._tbl_pos.setStyleSheet(_TBL_STYLE)
        self._tbl_pos.setVisible(False)
        self._tbl_pos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_pos.cellClicked.connect(self._on_pos_row_clicked)
        lay.addWidget(self._tbl_pos, 1)

        # [FIX-J] 청산 컨트롤 행
        lay.addWidget(self._build_close_control_row())

        # [FIX-BANNER] Wolf + 수익률 배너 (탭 내부 하단)
        # 메인 레이아웃(lay)을 직접 재사용하면 여백/경계가 틀어지므로
        # 전용 서브 레이아웃을 만들어 lay 에 추가하고 저장
        self._banner_layout = QVBoxLayout()
        self._banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_layout.setSpacing(2)
        lay.addLayout(self._banner_layout)

        return w

    def _build_close_control_row(self) -> QWidget:
        """[FIX-J] 지정가/MKT 청산 컨트롤 행."""
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        row = QHBoxLayout(w)
        row.setContentsMargins(2, 2, 2, 2); row.setSpacing(6)

        self._lbl_pos_hint = QLabel("행을 클릭하세요")
        self._lbl_pos_hint.setStyleSheet("color:#444466;font-size:11px;border:none;")
        row.addWidget(self._lbl_pos_hint)
        row.addStretch()

        lbl_price = QLabel("가격:")
        lbl_price.setStyleSheet("color:#888;font-size:11px;border:none;")
        row.addWidget(lbl_price)

        self._spin_close_price = QDoubleSpinBox()
        self._spin_close_price.setRange(0.01, 999.99)
        self._spin_close_price.setSingleStep(0.05)
        self._spin_close_price.setDecimals(2)
        self._spin_close_price.setPrefix("$")
        self._spin_close_price.setFixedWidth(80)
        self._spin_close_price.setFixedHeight(26)
        self._spin_close_price.setEnabled(False)
        self._spin_close_price.setStyleSheet(
            "background:#0a1a2a;color:#ffdd88;border:1px solid #3a5a9a;"
            "border-radius:3px;font-size:12px;font-weight:bold;")
        row.addWidget(self._spin_close_price)

        self._btn_close_lmt = QPushButton("📌 지정가 청산")
        self._btn_close_lmt.setFixedHeight(26)
        self._btn_close_lmt.setEnabled(False)
        self._btn_close_lmt.setStyleSheet(
            "background:#1a2a0a;color:#aaffaa;font-size:12px;"
            "font-weight:bold;border:1px solid #3a6a2a;border-radius:3px;padding:2px 10px;")
        self._btn_close_lmt.clicked.connect(self._on_close_lmt)
        row.addWidget(self._btn_close_lmt)

        self._btn_close_mkt = QPushButton("🔴 MKT 청산")
        self._btn_close_mkt.setFixedHeight(26)
        self._btn_close_mkt.setEnabled(False)
        self._btn_close_mkt.setStyleSheet(
            "background:#2a0a0a;color:#ff6666;font-size:12px;"
            "font-weight:bold;border:1px solid #6a1a1a;border-radius:3px;padding:2px 10px;")
        self._btn_close_mkt.clicked.connect(self._on_close_mkt)
        row.addWidget(self._btn_close_mkt)

        self._btn_cancel_pos = QPushButton("✖ 주문 취소")
        self._btn_cancel_pos.setFixedHeight(26)
        self._btn_cancel_pos.setEnabled(False)
        self._btn_cancel_pos.setStyleSheet(
            "background:#2a1a0a;color:#ffaa44;font-size:12px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;padding:2px 10px;")
        self._btn_cancel_pos.clicked.connect(self._on_cancel_pos_order)
        row.addWidget(self._btn_cancel_pos)
        return w

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

        # 버튼 클릭 시 currentRow()가 -1이 될 수 있으므로 별도 저장
        self._selected_pos_row = row

        pos       = self._positions[row]
        status    = pos.get("status", "미체결")
        strat     = pos.get("strategy", "―")
        current   = float(pos.get("current", pos.get("entry", 0)))
        is_filled = status in ("체결완료", "보유")   # [FIX-S]

        self._lbl_pos_hint.setText(
            f"{'📌 보유' if is_filled else '⏳ 미체결'}: {strat}")

        self._btn_cancel_pos.setEnabled(not is_filled)
        self._btn_close_lmt.setEnabled(is_filled)
        self._btn_close_mkt.setEnabled(is_filled)
        self._spin_close_price.setEnabled(is_filled)

        # [FIX-J] 현재가를 스핀박스에 자동 입력
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
    # Public API
    # ══════════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════════
    # [FIX-SCENARIO] 시나리오 탭 외부 API
    # ══════════════════════════════════════════════════════════

    def update_scenario_greeks(self, legs: list, entry: float = 0.0,
                               und_price: float = 0.0) -> None:
        """[FIX-SCENARIO] 레그 설정 완료 시 호출 → 시나리오 탭 Greeks 갱신."""
        if hasattr(self, '_scenario_tab'):
            self._scenario_tab.set_greeks(legs, entry, und_price)

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
                pos["status"] = "보유"   # [FIX-S] "체결완료" → "보유"
        self._refresh_pos_table()

    def mark_position_cancelled(self, oid: int):
        self._positions = [p for p in self._positions if p.get("oid") != oid]
        self._refresh_pos_table()

    def mark_position_closing(self, oid: int):
        """[FIX-CLOSE] 청산 주문 접수 → 해당 행 '청산중' 상태로 변경.
        체결 완료 전까지 행을 유지하되 총 손익 계산에서 제외하고
        청산 버튼을 비활성화해 중복 청산을 방지한다."""
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
        """
        [FIX-M] add_position 에서 _enrich_strategy_name 적용.
        신규 체결 직후에도 행사가가 전략명에 자동으로 붙음.
        """
        fill_info = dict(fill_info)
        fill_info.setdefault("current", fill_info.get("entry", 0.0))
        fill_info["strategy"] = _enrich_strategy_name(fill_info)
        self._positions.append(fill_info)
        self._refresh_pos_table()
        self._tabs.setCurrentIndex(1)

    def update_position_prices(self, oid: int, current_price: float):
        """
        [FIX-K] oid 기준으로 가격 갱신.
        strategy 문자열 기준일 때 같은 전략명 포지션 2개가 모두 같은 가격으로
        덮어씌워지던 버그 수정.
        """
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
            st, col, bg, bc = f"✅  주문 가능  (여유 ${surplus:,.2f})", "#00ff88", "#071a0e", "#00ff88"
        else:
            shortage = required - available
            st, col, bg, bc = f"❌  증거금 부족  (${shortage:,.2f} 부족)", "#ff4444", "#1a0707", "#ff4444"
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
            tbl.setItem(r, 0, _it(o.get("oid",""),    "#888"))
            tbl.setItem(r, 1, _it(o.get("sym",""),    "#ffd700"))
            tbl.setItem(r, 2, _it(o.get("action",""), action_col))
            tbl.setItem(r, 3, _it(o.get("qty",""),    "#ccc"))
            tbl.setItem(r, 4, _it(f"{o.get('lmt',0):.2f}" if o.get('lmt') else "MKT", "#ffaa44"))
            st     = o.get("status","")
            st_col = "#00ff88" if "Submit" in st else "#ffaa44" if "Pending" in st else "#888"
            tbl.setItem(r, 5, _it(st, st_col))
        self._tabs.setCurrentIndex(2)

    def get_selected_order(self):
        return self._tbl_open_orders.currentRow()

    # ══════════════════════════════════════════════════════════
    # 테이블 갱신
    # ══════════════════════════════════════════════════════════

    def _refresh_pos_table(self):
        tbl = self._tbl_pos
        tbl.setRowCount(0)
        if not self._positions:
            self._lbl_no_pos.setVisible(True); tbl.setVisible(False)
            self._lbl_total_pnl.setText("$0.00")
            self._lbl_total_pnl.setStyleSheet("color:#e0e0e0;border:none;")
            return

        self._lbl_no_pos.setVisible(False); tbl.setVisible(True)
        tbl.setRowCount(len(self._positions))
        total_pnl = 0.0

        for r, pos in enumerate(self._positions):
            qty       = pos.get("qty", 1)
            entry     = pos.get("entry", 0.0)
            current   = pos.get("current", entry)
            status    = pos.get("status", "미체결")
            is_filled  = status in ("체결완료", "보유")   # [FIX-S] 두 값 모두 체결로 처리
            is_closing = status == "청산중"               # [FIX-CLOSE] 청산 주문 접수됨
            pnl       = (current - entry) * qty * 100 if is_filled and not is_closing else 0.0
            total_pnl += pnl
            pnl_col   = "#00ff88" if pnl > 0 else "#ff4444" if pnl < 0 else "#888899"

            def _it(text, color="#cccccc", align=Qt.AlignCenter):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setForeground(QColor(color))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                return it

            # 수익률: (현재가 - 진입가) / 진입가 × 100
            if is_filled and not is_closing and entry > 0:
                pnl_rate     = (current - entry) / entry * 100
                pnl_rate_txt = f"{pnl_rate:+.1f}%"
                pnl_rate_col = "#00ff88" if pnl_rate > 0 else "#ff4444" if pnl_rate < 0 else "#888899"
            else:
                pnl_rate_txt = "―"
                pnl_rate_col = "#888899"

            # 상태 표시 [FIX-CLOSE]
            if is_closing:
                st_col  = "#888888"
                st_text = "🔄 청산중"
            elif is_filled:
                st_col  = "#00ff88"
                st_text = "📌 보유"   # [FIX-S] "✅ 체결" → "📌 보유"
            else:
                st_col  = "#ffaa44"
                st_text = "⏳ 미체결"
            # 만기 필드 추가
            expiry_txt, expiry_col = _format_expiry(pos.get("legs", []))
            tbl.setItem(r, 0, _it(expiry_txt, expiry_col))

            tbl.setItem(r, 1, _it(pos.get("strategy","―"), "#e0e0ff", Qt.AlignLeft|Qt.AlignVCenter))
            tbl.setItem(r, 2, _it(str(qty),                  "#aaaaaa"))
            tbl.setItem(r, 3, _it(f"${entry:.2f}",           "#aaaaaa"))
            tbl.setItem(r, 4, _it(f"${current:.2f}",         "#e0e0e0"))
            tbl.setItem(r, 5, _it(f"${pnl:+,.2f}" if is_filled else "―", pnl_col))
            tbl.setItem(r, 6, _it(pnl_rate_txt,              pnl_rate_col))

            # [FIX-DELTA] 칼럼 7: 지수 5P당 예상 손익률
            delta_pct_txt, delta_pct_col = _calc_delta_pnl_pct(pos)
            delta_it = QTableWidgetItem(delta_pct_txt)
            delta_it.setTextAlignment(Qt.AlignCenter)
            delta_it.setForeground(QColor(delta_pct_col))
            delta_it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            delta_font = QFont(); delta_font.setPointSize(14)
            delta_it.setFont(delta_font)
            tbl.setItem(r, 7, delta_it)

            tbl.setItem(r, 8, _it(st_text,                   st_col))

        tc = "#00ff88" if total_pnl > 0 else "#ff4444" if total_pnl < 0 else "#888899"
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
    # [SLEEP] 예약 주문 버튼 ref 지연 주입
    # ══════════════════════════════════════════════════════════

    def _inject_sleep_ref(self):
        """
        SleepOrderButton 에 ref 주입.
        ref = _sleep_get_chain / _sleep_place_order 를 가진 ComboTab.
        parent() 체인을 타고 올라가며 해당 메서드가 있는 객체를 찾음.
        """
        try:
            btn = getattr(self, '_sleep_btn', None)
            if btn is None:
                return

            # parent() 체인을 타고 올라가며 _sleep_get_chain 이 있는 객체 탐색
            ref = None
            w = self
            # combo_ui_synthetic_panel.py 659번줄 for 루프를 이렇게 수정
            for _ in range(10):   # 6 → 10으로 늘리기
                w = w.parent()
                if w is None:
                    print(f"[SyntheticPanel] parent 체인 끊김 at depth {_}")
                    break
                print(f"[SyntheticPanel] depth={_} type={type(w).__name__} has_sleep={hasattr(w, '_sleep_get_chain')}")
                if hasattr(w, '_sleep_get_chain'):
                    ref = w
                    break
            if ref is not None:
                btn.set_ref(ref)
                print(f"[SyntheticPanel] sleep ref 주입 완료: {type(ref).__name__}")
            else:
                # 찾지 못하면 1초 후 재시도 (탭이 완전히 붙기 전일 수 있음)
                from PyQt5.QtCore import QTimer as _QT
                _QT.singleShot(1000, self._inject_sleep_ref)
                print("[SyntheticPanel] sleep ref 탐색 실패 — 1초 후 재시도")
        except Exception as e:
            print(f"[SyntheticPanel] _inject_sleep_ref 실패: {e}")

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
    # 미체결 탭
    # ══════════════════════════════════════════════════════════

    def _build_open_orders_tab(self) -> QWidget:
        from PyQt5.QtWidgets import QRadioButton, QButtonGroup
        w = QWidget(); w.setStyleSheet("background:#07070f;")
        lay = QVBoxLayout(w); lay.setContentsMargins(4,4,4,4); lay.setSpacing(4)

        chaser_row = QHBoxLayout(); chaser_row.setSpacing(6)
        mode_lbl = QLabel("정정 모드:")
        mode_lbl.setStyleSheet("color:#888;border:none;font-size:11px;")
        chaser_row.addWidget(mode_lbl)

        self._rb_chaser_auto   = QRadioButton("🤖 자동")
        self._rb_chaser_manual = QRadioButton("✏ 수동")
        self._rb_chaser_manual.setChecked(True)   # [FIX-BANNER] 기본값 수동 모드
        for rb in (self._rb_chaser_auto, self._rb_chaser_manual):
            rb.setStyleSheet("color:#ccc;font-size:11px;border:none;")
        self._chaser_mode_grp = QButtonGroup(w)
        self._chaser_mode_grp.addButton(self._rb_chaser_auto,   0)
        self._chaser_mode_grp.addButton(self._rb_chaser_manual, 1)
        chaser_row.addWidget(self._rb_chaser_auto)
        chaser_row.addWidget(self._rb_chaser_manual)

        self._spin_manual_price = QDoubleSpinBox()
        self._spin_manual_price.setRange(0.01, 999.99)
        self._spin_manual_price.setSingleStep(0.05)
        self._spin_manual_price.setDecimals(2)
        self._spin_manual_price.setPrefix("$")
        self._spin_manual_price.setFixedWidth(80)
        self._spin_manual_price.setFixedHeight(24)
        self._spin_manual_price.setVisible(False)
        self._spin_manual_price.setStyleSheet(
            "background:#0a1a2a;color:#ffdd88;border:1px solid #3a5a9a;"
            "border-radius:3px;font-size:12px;font-weight:bold;")
        chaser_row.addWidget(self._spin_manual_price)

        self._btn_manual_send = QPushButton("전송")
        self._btn_manual_send.setFixedSize(46, 24)
        self._btn_manual_send.setVisible(False)
        self._btn_manual_send.setStyleSheet(
            "background:#1a3a1a;color:#aaffaa;font-size:11px;"
            "font-weight:bold;border:1px solid #3a8a3a;border-radius:3px;")
        self._btn_manual_send.clicked.connect(self._on_manual_price_send)
        chaser_row.addWidget(self._btn_manual_send)
        chaser_row.addStretch()
        lay.addLayout(chaser_row)

        self._rb_chaser_auto.toggled.connect(self._on_chaser_mode_toggle)
        self._rb_chaser_manual.toggled.connect(self._on_chaser_mode_toggle)

        self._lbl_chaser_desc = QLabel("⏱ 미체결 5초 후 자동 1틱 정정 (최대 3회)")
        self._lbl_chaser_desc.setStyleSheet("color:#556677;font-size:10px;border:none;")
        lay.addWidget(self._lbl_chaser_desc)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self._btn_refresh_orders = QPushButton("↺ 조회")
        self._btn_refresh_orders.setFixedHeight(24)
        self._btn_refresh_orders.setStyleSheet(
            "background:#1a2a4a;color:#90caf9;font-size:11px;"
            "font-weight:bold;border:1px solid #3a5a9a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_refresh_orders)
        self._btn_modify_p1 = QPushButton("+1호가 정정")
        self._btn_modify_p1.setFixedHeight(24)
        self._btn_modify_p1.setStyleSheet(
            "background:#1a2a0a;color:#aaffaa;font-size:11px;"
            "font-weight:bold;border:1px solid #3a6a2a;border-radius:3px;padding:2px 8px;")
        # [FIX-MB1] clicked.connect 추가 — 기존 누락으로 버튼 동작 안 하던 버그 수정
        self._btn_modify_p1.clicked.connect(lambda: self._on_modify_tick(+1))
        btn_row.addWidget(self._btn_modify_p1)
        self._btn_modify_m1 = QPushButton("-1호가 정정")
        self._btn_modify_m1.setFixedHeight(24)
        self._btn_modify_m1.setStyleSheet(
            "background:#2a1a0a;color:#ffaa44;font-size:11px;"
            "font-weight:bold;border:1px solid #6a3a0a;border-radius:3px;padding:2px 8px;")
        # [FIX-MB1] clicked.connect 추가
        self._btn_modify_m1.clicked.connect(lambda: self._on_modify_tick(-1))
        btn_row.addWidget(self._btn_modify_m1)
        self._btn_cancel_all = QPushButton("✖ 전체 취소")
        self._btn_cancel_all.setFixedHeight(24)
        self._btn_cancel_all.setStyleSheet(
            "background:#2a0a0a;color:#ff4444;font-size:11px;"
            "font-weight:bold;border:1px solid #6a1a1a;border-radius:3px;padding:2px 8px;")
        btn_row.addWidget(self._btn_cancel_all)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._tbl_open_orders = QTableWidget(0, 6)
        self._tbl_open_orders.setHorizontalHeaderLabels(
            ["OID","종목","방향","수량","지정가","상태"])
        self._tbl_open_orders.setFont(_f(11))
        self._tbl_open_orders.horizontalHeader().setFont(_f(10, bold=True))
        self._tbl_open_orders.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._tbl_open_orders.verticalHeader().setVisible(False)
        self._tbl_open_orders.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_open_orders.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_open_orders.setAlternatingRowColors(True)
        self._tbl_open_orders.setStyleSheet(_TBL_STYLE)
        self._tbl_open_orders.cellClicked.connect(self._on_order_row_clicked)
        lay.addWidget(self._tbl_open_orders, 1)
        return w

    def _on_chaser_mode_toggle(self):
        is_manual = self._rb_chaser_manual.isChecked()
        self._spin_manual_price.setVisible(is_manual)
        self._btn_manual_send.setVisible(is_manual)
        self._btn_modify_p1.setVisible(not is_manual)
        self._btn_modify_m1.setVisible(not is_manual)
        self._lbl_chaser_desc.setText(
            "✏ Net Price를 직접 입력 후 [전송] 클릭" if is_manual
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
                    float(price_item.text().replace("$","")))
            except ValueError:
                pass

    def _on_manual_price_send(self):
        new_price = self._spin_manual_price.value()
        row = self._tbl_open_orders.currentRow()
        if row < 0: return
        oid_item = self._tbl_open_orders.item(row, 0)
        if not oid_item: return
        try:
            oid = int(oid_item.text())
        except ValueError:
            return
        if callable(getattr(self, '_manual_modify_callback', None)):
            self._manual_modify_callback(oid, new_price)

    def _on_modify_tick(self, direction: int) -> None:
        """
        [FIX-MB1] +1호가 / -1호가 정정 버튼 핸들러.

        미체결 주문 탭에서 선택된 행의 OID + 현재 지정가를 읽어
        direction(+1 또는 -1) 틱만큼 가격을 조정한 뒤 정정 주문 전송.

        direction = +1 : 가격 1틱 올림 (매수 유리 / 매도 불리 방향)
        direction = -1 : 가격 1틱 내림 (매도 유리 / 매수 불리 방향)
        """
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

        # 틱 사이즈 계산 후 1틱 조정
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


# ══════════════════════════════════════════════════════════════
# 모듈 레벨 유틸
# ══════════════════════════════════════════════════════════════

def _calc_delta_pnl_pct(pos: dict) -> tuple:
    """
    [FIX-DELTA] 지수 5P 당 포지션 예상 손익률 계산.

    공식:
      포지션 델타 = Σ( leg_delta × leg_qty × 방향계수 )
                    (BUY: 부호 유지, SELL: 부호 반전)
      5P 손익($) = 포지션 델타 × 5 × 100          (SPX 승수 100)
      손익률(%)  = 5P 손익 / (entry × 100) × 100

    Args:
        pos: 포지션 딕셔너리. legs[i]['delta'] 필드 필요.
             delta 필드가 없거나 모두 0 이면 "―" 반환.

    Returns:
        (표시 문자열, 색상 hex)
        예: ("+95%", "#ffff44")  /  ("-45%", "#ff6666")  /  ("―", "#888899")
    """
    entry = float(pos.get("entry", 0) or 0)
    legs  = pos.get("legs", [])

    if not legs or entry <= 0:
        return ("―", "#888899")

    try:
        pos_delta = 0.0
        has_delta = False
        for leg in legs:
            raw = leg.get("delta")
            if raw is None:
                continue
            leg_delta = float(raw)
            leg_qty   = float(leg.get("qty", 1) or 1)
            leg_dir   = str(leg.get("dir", "BUY")).upper()
            if leg_dir == "SELL":
                leg_delta = -leg_delta
            pos_delta += leg_delta * leg_qty
            has_delta = True

        if not has_delta:
            return ("―", "#888899")

        five_p_pnl   = pos_delta * 5.0 * 100.0        # 달러
        debit_dollars = entry * 100.0                   # $1.05 → $105
        pnl_pct      = (five_p_pnl / debit_dollars) * 100.0

        if pnl_pct >= 0:
            txt = f"+{pnl_pct:.0f}%"
            col = "#ffff44"     # 형광 노랑
        else:
            txt = f"{pnl_pct:.0f}%"
            col = "#ff6666"     # 연한 빨강

        return (txt, col)

    except Exception:
        return ("―", "#888899")


def _enrich_strategy_name(pos: dict) -> str:
    """
    [FIX-M] legs 에서 행사가 추출해 전략명에 추가.
    예) "풋 스프레드 (풋매수+풋매도)" + legs[6700, 6705]
        → "풋 스프레드 6700/6705 (풋매수+풋매도)"
    이미 행사가가 포함된 경우 중복 추가 방지.
    """
    legs = pos.get("legs", [])
    if not legs:
        return pos.get("strategy", "")
    try:
        strikes = "/".join(
            str(int(float(l["strike"])))
            for l in sorted(legs, key=lambda l: l.get("dir", ""), reverse=True)
            if l.get("strike")
        )
        base = pos.get("strategy", "")
        if strikes and strikes not in base:
            if "(" in base:
                idx = base.index("(")
                return f"{base[:idx].rstrip()} {strikes} {base[idx:]}"
            return f"{base} {strikes}"
    except Exception:
        pass
    return pos.get("strategy", "")


def _format_expiry(legs: list) -> tuple:
    """
    [FIX-N] legs 에서 만기일 추출 후 포맷.
    ET 기준으로 남은 일수 계산 후 색상과 함께 반환.
    
    반환: (표시 텍스트, 색상) 튜플
    
    예시:
      - expiry = "20260509" (내일) → ("1일", "#ffaa44")
      - expiry = "20260510" (3일 후) → ("3일", "#aabbff")
      - expiry = "20260601" (1개월 후) → ("52일", "#88dd55")
      - 만기 지난 경우 → ("만료", "#888888")
    """
    if not legs:
        return ("―", "#888899")
    
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # 첫 레그의 만기일 사용 (모두 같다고 가정)
        expiry_str = str(legs[0].get("expiry", "")).strip()
        if not expiry_str or len(expiry_str) != 8:
            return ("―", "#888899")
        
        try:
            exp_year  = int(expiry_str[:4])
            exp_month = int(expiry_str[4:6])
            exp_day   = int(expiry_str[6:8])
            exp_date = datetime(exp_year, exp_month, exp_day,
                               16, 0, 0,  # ET 시간 16:00 (마감)
                               tzinfo=ZoneInfo("America/New_York")).date()
        except (ValueError, TypeError):
            return ("―", "#888899")
        
        # 현재 ET 날짜
        now_et = datetime.now(ZoneInfo("America/New_York")).date()
        
        # 만기일 계산
        if exp_date < now_et:
            # 만료됨
            return ("만료", "#888888")
        elif exp_date == now_et:
            # 오늘 만기 (긴급)
            return ("0일", "#ff6666")
        else:
            # 남은 일수 계산
            delta = (exp_date - now_et).days
            if delta == 1:
                color = "#ffaa44"  # 황색 경고 (내일 만기)
            elif delta <= 7:
                color = "#ff9999"  # 연한 빨강 (1주일 이내)
            elif delta <= 14:
                color = "#ffdd88"  # 주황색 (2주 이내)
            elif delta <= 30:
                color = "#aabbff"  # 하늘색 (1달 이내)
            else:
                color = "#88dd55"  # 녹색 (장기)
            
            return (f"{delta}일", color)
    
    except Exception:
        return ("―", "#888899")


# ══════════════════════════════════════════════════════════════
# [FIX-SCENARIO] ScenarioTab 위젯
# ══════════════════════════════════════════════════════════════

class ScenarioTab(QWidget):
    """
    📈 시나리오 탭 — Mode B + C안.

    슬라이더 3개 (지수 이동 / 경과 시간 / IV 변화) 로 조건을 설정하면
    Δ+Γ 보정, Θ 세타 손실, ν 베가 효과를 종합한 예상 수익률과
    시나리오 매트릭스(지수 이동 × 경과 시간)를 실시간 갱신.

    외부 연동:
        set_greeks(legs, entry) — 레그 Greeks 주입 (combo_ui_left_chain 에서 호출)
    """

    # 시나리오 매트릭스 행/열 고정
    _MOVES = [-50, -40, -30, -20, -15, -10, -5, 0, 5, 10, 15, 20, 30, 40, 50]
    _TIMES = [4.0, 3.0, 2.0, 1.0, 0.5]   # 만기까지 남은 시간 (많은→적은)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#07070f;")
        from PyQt5.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Greeks 초기값 (데이터 수신 전)
        self._entry        = 0.0
        self._pos_delta    = 0.0
        self._pos_gamma    = 0.0
        self._pos_theta    = 0.0   # 일 기준
        self._pos_vega     = 0.0
        self._max_val      = 5.0   # 스프레드 상한 (행사가 차이)
        self._expiry_str   = ""    # [FIX-SCENARIO] 만기일 (YYYYMMDD)
        self._hours_left   = 4.0   # [FIX-SCENARIO] 만기까지 남은 시간 (기본 4h)

        # [FIX-BS] Black-Scholes 계산용 원본 데이터
        self._legs_raw     = []    # 레그 원본 리스트 (strike, iv, dir, qty, cp)
        self._und_price    = 0.0   # 현재 지수 가격 (BS 기준가)

        self._build_ui()

    # ── UI 구성 ───────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── 포지션 요약 행 ────────────────────────────────────
        info_row = QHBoxLayout()
        self._lbl_entry  = self._mk_info("DEBIT: ―")
        self._lbl_greeks = self._mk_info("δ ―  γ ―  θ ―  ν ―")
        self._lbl_cap    = self._mk_info("상한: ―")
        self._lbl_und    = self._mk_info("지수: ―")   # [FIX-BS] und_price
        info_row.addWidget(self._lbl_entry)
        info_row.addStretch()
        info_row.addWidget(self._lbl_und)
        info_row.addStretch()
        info_row.addWidget(self._lbl_greeks)
        info_row.addStretch()
        info_row.addWidget(self._lbl_cap)
        root.addLayout(info_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep)

        # ── 슬라이더 3개 ──────────────────────────────────────
        root.addLayout(self._mk_slider_row(
            "지수 이동(P)", -30, 30, 5, 1, "sl_move", "v_move",
            lambda v: (f"+{v}P" if v >= 0 else f"{v}P")))
        root.addLayout(self._mk_slider_row(
            "남은 시간(h)", 0, 16, 8, 1, "sl_time", "v_time",
            lambda v: f"{v/2:.1f}h"))
        root.addLayout(self._mk_slider_row(
            "IV 변화(%)", -10, 20, 4, 1, "sl_iv", "v_iv",
            lambda v: (f"+{v}%" if v >= 0 else f"{v}%")))

        # [FIX-SCENARIO] 만기까지 남은 시간 자동 계산 표시
        self._lbl_time_auto = QLabel("⏱ ET 기준 자동 계산 중...")
        self._lbl_time_auto.setStyleSheet(
            "color:#445566;font-size:10px;border:none;")
        root.addWidget(self._lbl_time_auto)

        # 자동 갱신 타이머 (1분마다)
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(60_000)
        self._time_timer.timeout.connect(self._auto_update_time)
        self._time_timer.start()
        self._auto_update_time()   # 즉시 1회 실행

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep2)

        # ── 결과 카드 4개 ──────────────────────────────────────
        card_row = QHBoxLayout(); card_row.setSpacing(4)
        self._card_dg  = self._mk_card("Δ+Γ 수익")
        self._card_th  = self._mk_card("Θ 손실")
        self._card_vg  = self._mk_card("ν 효과")
        self._card_pct = self._mk_card("예상 수익률", big=True)
        for c in (self._card_dg, self._card_th, self._card_vg, self._card_pct):
            card_row.addWidget(c[0])
        root.addLayout(card_row)

        # ── 상세 분해 ─────────────────────────────────────────
        detail = QGridLayout(); detail.setSpacing(2)
        def _kv(row, col_k, col_v, k, v_id):
            lk = QLabel(k); lk.setStyleSheet("color:#555;font-size:10px;border:none;")
            lv = QLabel("―"); lv.setStyleSheet("color:#aaa;font-size:10px;border:none;")
            lv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            detail.addWidget(lk, row, col_k)
            detail.addWidget(lv, row, col_v)
            return lv
        self._lv_delta  = _kv(0, 0, 1, "Δ×ΔS",         "delta_term")
        self._lv_gamma  = _kv(0, 2, 3, "½Γ×ΔS²",        "gamma_term")
        self._lv_theta  = _kv(1, 0, 1, "Θ×Δt",          "theta_term")
        self._lv_vega   = _kv(1, 2, 3, "ν×ΔIV",         "vega_term")
        self._lv_price  = _kv(2, 0, 1, "예상가",         "price")
        self._lv_return = _kv(2, 2, 3, "수익률",         "pct")
        self._lbl_cap_warn = QLabel("")
        self._lbl_cap_warn.setStyleSheet(
            "color:#ffaa44;font-size:10px;border:none;")
        detail.addWidget(self._lbl_cap_warn, 3, 0, 1, 4)
        root.addLayout(detail)

        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine)
        sep3.setFixedHeight(1)
        sep3.setStyleSheet("background-color:#1a1a3a;border:none;")
        root.addWidget(sep3)

        # ── 시나리오 매트릭스 ─────────────────────────────────
        lbl_mat = QLabel("시나리오 매트릭스 (지수 이동 × 만기까지 남은 시간)")
        lbl_mat.setStyleSheet("color:#4466aa;font-size:10px;border:none;")
        root.addWidget(lbl_mat)

        self._matrix_tbl = QTableWidget(
            len(self._MOVES), len(self._TIMES))
        self._matrix_tbl.setHorizontalHeaderLabels(
            [f"{t:.1f}h 남음" for t in self._TIMES])
        self._matrix_tbl.setVerticalHeaderLabels(
            [f"{m:+d}P" for m in self._MOVES])
        self._matrix_tbl.setFont(_f(10))
        self._matrix_tbl.horizontalHeader().setFont(_f(9, bold=True))
        self._matrix_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._matrix_tbl.verticalHeader().setFont(_f(9))
        self._matrix_tbl.verticalHeader().setDefaultSectionSize(20)
        self._matrix_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 4~5행만 보이도록 고정 (헤더 26px + 행 22px × 5)
        self._matrix_tbl.setFixedHeight(136)
        self._matrix_tbl.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._matrix_tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._matrix_tbl.setStyleSheet(_TBL_STYLE)
        root.addWidget(self._matrix_tbl)

        lbl_note = QLabel(
            "* IV 변화는 슬라이더 값 고정 적용  "
            "· 스프레드 상한 초과 시 MAX 표시  "
            "· 남은 시간 0h = 만기 직전")
        lbl_note.setStyleSheet("color:#333355;font-size:9px;border:none;")
        root.addWidget(lbl_note)


        # 초기 렌더
        self._refresh()

    # ── 슬라이더/카드 헬퍼 ───────────────────────────────────

    def _mk_info(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#556677;font-size:10px;border:none;")
        return lbl

    def _mk_slider_row(self, label, mn, mx, default, step,
                       sl_attr, val_attr, fmt_fn) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)
        lk = QLabel(label)
        lk.setFixedWidth(80)
        lk.setStyleSheet("color:#888;font-size:10px;border:none;")
        sl = QSlider(Qt.Horizontal)
        sl.setRange(mn, mx); sl.setValue(default); sl.setSingleStep(step)
        sl.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#1a1a3a;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#4488ff;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#2255aa;border-radius:2px;}")
        lv = QLabel(fmt_fn(default))
        lv.setFixedWidth(46)
        lv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lv.setStyleSheet("color:#ffff44;font-size:11px;font-weight:bold;border:none;")
        setattr(self, sl_attr, sl)
        setattr(self, val_attr, lv)
        sl.valueChanged.connect(lambda v, f=fmt_fn, l=lv: (
            l.setText(f(v)), self._refresh()))
        row.addWidget(lk); row.addWidget(sl); row.addWidget(lv)
        return row

    def _mk_card(self, title: str, big: bool = False):
        w = QWidget()
        w.setStyleSheet(
            "background:#0a0a1e;border:1px solid #1a1a3a;border-radius:4px;")
        v = QVBoxLayout(w); v.setContentsMargins(6, 4, 6, 4); v.setSpacing(1)
        lt = QLabel(title)
        lt.setAlignment(Qt.AlignCenter)
        lt.setStyleSheet("color:#446688;font-size:9px;border:none;")
        lv = QLabel("―")
        lv.setAlignment(Qt.AlignCenter)
        sz = 16 if big else 13
        lv.setFont(_f(sz, bold=True))
        lv.setStyleSheet("color:#888899;border:none;")
        v.addWidget(lt); v.addWidget(lv)
        return w, lv

    # ── 외부 API ──────────────────────────────────────────────

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

        # [FIX-BS] 원본 레그 저장 (BS 계산용)
        self._legs_raw = legs
        if und_price > 0:
            self._und_price = und_price

        # [FIX-SCENARIO] 만기일 저장 (첫 레그에서)
        for leg in legs:
            exp = str(leg.get("expiry", "")).strip()
            if exp and len(exp) == 8:
                self._expiry_str = exp
                self._auto_update_time()   # 만기 바뀌면 남은 시간 즉시 재계산
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

        # IV 없어도 strike는 있으면 진행
        if not has_data:
            iv_check = any(leg.get("iv") for leg in legs)
            if not iv_check:
                return

        self._pos_delta = pos_delta
        self._pos_gamma = pos_gamma
        self._pos_theta = pos_theta
        self._pos_vega  = pos_vega

        # 스프레드 상한 = 행사가 차이 (없으면 5.0 기본)
        if len(strikes) >= 2:
            self._max_val = abs(max(strikes) - min(strikes))
        else:
            self._max_val = 5.0

        # 헤더 라벨 갱신
        self._lbl_entry.setText(
            f"DEBIT: ${self._entry:.2f}" if self._entry > 0 else "DEBIT: ―")
        self._lbl_und.setText(
            f"지수: {self._und_price:.1f}" if self._und_price > 0 else "지수: ―")
        self._lbl_greeks.setText(
            f"δ {pos_delta:+.3f}  γ {pos_gamma:+.4f}  "
            f"θ {pos_theta:+.4f}  ν {pos_vega:+.4f}")
        self._lbl_cap.setText(f"상한: ${self._max_val:.2f}")

        self._refresh()

    # ── [FIX-BS] Black-Scholes 계산 엔진 ────────────────────────

    @staticmethod
    def _bs_price(S: float, K: float, T: float,
                  sigma: float, cp: str = 'C') -> float:
        """
        순수 Python Black-Scholes 옵션 가격 계산.
        외부 라이브러리 불필요 (math 표준 라이브러리만 사용).

        Args:
            S     : 현재 지수 가격
            K     : 행사가
            T     : 만기까지 남은 시간 (연 단위)
                    예) 2시간 = 2 / (252 * 6.5)  ← 거래일 기준
            sigma : IV (소수. 예: 0.15 = 15%)
            cp    : 'C' (콜) / 'P' (풋)

        Returns:
            float: 옵션 가격 (달러)
        """
        if S <= 0 or K <= 0 or sigma <= 0:
            return 0.0

        # 만기 도달 → 내재가치만
        if T <= 1e-6:
            if cp == 'C':
                return max(S - K, 0.0)
            else:
                return max(K - S, 0.0)

        try:
            sqrtT = math.sqrt(T)
            d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
            d2 = d1 - sigma * sqrtT

            def _N(x: float) -> float:
                return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

            if cp == 'C':
                return S * _N(d1) - K * _N(d2)
            else:
                return K * _N(-d2) - S * _N(-d1)
        except Exception:
            return 0.0

    def _bs_spread_price(self, S_new: float, T_new: float,
                         div: float) -> tuple:
        """
        [FIX-BS] 스프레드 포지션 전체 BS 재계산.

        지수가 S_new 로 이동하고 남은 시간이 T_new 일 때
        각 레그를 BS로 재계산해 포지션 가격 반환.

        IV 조정: 현재 IV + div(%) 반영 (베가 효과 내재)
        IV 없는 레그: 폴백 → Δ+½Γ 근사 사용

        Args:
            S_new  : 이동 후 지수 가격
            T_new  : 남은 시간 (연 단위)
            div    : IV 변화 (%. 예: +2 = IV 2%p 상승)

        Returns:
            (포지션 가격, 계산 모드 str)
            계산 모드: 'BS' | '근사' | 'BS+근사'
        """
        if not self._legs_raw or self._und_price <= 0:
            return (None, '근사')

        total_price = 0.0
        bs_count    = 0
        approx_count = 0

        for leg in self._legs_raw:
            try:
                strike = float(leg.get('strike', 0) or 0)
                iv_raw = leg.get('iv')
                qty    = float(leg.get('qty', 1) or 1)
                cp     = str(leg.get('cp', 'C')).upper()
                direction = str(leg.get('dir', 'BUY')).upper()
                coeff  = 1.0 if direction == 'BUY' else -1.0

                if strike <= 0:
                    continue

                if iv_raw is not None and float(iv_raw) > 0:
                    # ── BS 계산 ──────────────────────────────
                    sigma = float(iv_raw) + div / 100.0
                    sigma = max(sigma, 0.001)   # 음수 방지
                    leg_price = self._bs_price(S_new, strike, T_new,
                                               sigma, cp)
                    total_price += leg_price * qty * coeff * 100.0
                    bs_count += 1
                else:
                    # ── Δ+½Γ 폴백 ────────────────────────────
                    d   = float(leg.get('delta', 0) or 0)
                    g   = float(leg.get('gamma', 0) or 0)
                    ds  = S_new - self._und_price
                    leg_change = (d * ds + 0.5 * g * ds * ds) * qty * coeff * 100.0
                    total_price += leg_change
                    approx_count += 1

            except Exception:
                continue

        # 폴백 케이스: BS 레그 없음
        if bs_count == 0:
            return (None, '근사')

        # 포지션 가격 = entry 기준 + BS 변화분
        # BS 결과가 달러 단위이므로 /100 해서 옵션 가격 환산
        pos_price = total_price / 100.0

        mode = 'BS' if approx_count == 0 else 'BS+근사'
        return (pos_price, mode)

    # ── 계산 엔진 ─────────────────────────────────────────────

    def _calc(self, move: float, hours_left: float, div: float) -> dict:
        """
        [FIX-BS] 단일 시나리오 계산 — BS 우선, 폴백 Δ+½Γ.

        Args:
            move       : 지수 이동 (포인트)
            hours_left : 만기까지 남은 시간 (시간, 슬라이더 값)
            div        : IV 변화 (%)

        BS 계산:
            IV 있는 레그 → Black-Scholes 재계산
            IV 없는 레그 → Δ+½Γ 근사 폴백
            세타는 BS 안에 내재되어 별도 계산 불필요
            베가는 IV+div 로 BS에 반영

        폴백(Δ+½Γ):
            IV 전혀 없을 때 → 기존 Greeks 근사 공식 사용
        """
        entry = self._entry if self._entry > 0 else 0.01

        # 경과 시간 (세타용, 폴백에서만 사용)
        elapsed = max(self._hours_left - hours_left, 0.0)

        # ── BS 시도 ───────────────────────────────────────────
        S_new = self._und_price + move   # 이동 후 지수 가격
        # 남은 시간 연 환산 (1거래일 = 6.5h, 연 252거래일)
        T_new = max(hours_left / (252.0 * 6.5), 1e-6)

        bs_result, mode = self._bs_spread_price(S_new, T_new, div)

        if bs_result is not None:
            # ── BS 성공 ───────────────────────────────────────
            expected_price = bs_result

            # 세타/감마 분해값 (참고용 — BS에 내재됨)
            dg_dollars = (self._pos_delta * move +
                          0.5 * self._pos_gamma * move * move) * 100.0
            th_dollars = self._pos_theta * (elapsed / 24.0) * 100.0
            vg_dollars = self._pos_vega * div * 100.0

        else:
            # ── Δ+½Γ 폴백 ─────────────────────────────────────
            mode = '근사'
            dg_dollars = (self._pos_delta * move +
                          0.5 * self._pos_gamma * move * move) * 100.0
            th_dollars = self._pos_theta * (elapsed / 24.0) * 100.0
            vg_dollars = self._pos_vega * div * 100.0
            expected_price = entry + (dg_dollars + th_dollars + vg_dollars) / 100.0

        # 스프레드 상한 처리
        max_price = self._max_val
        capped    = expected_price > max_price
        expected_price = min(max(expected_price, 0.0), max_price)

        # 수익률
        pnl_pct = ((expected_price - entry) / entry * 100.0) if entry > 0 else 0.0

        return {
            "dg":      dg_dollars,
            "th":      th_dollars,
            "vg":      vg_dollars,
            "price":   expected_price,
            "pct":     pnl_pct,
            "capped":  capped,
            "elapsed": elapsed,
            "mode":    mode,        # 'BS' | '근사' | 'BS+근사'
        }

    def _auto_update_time(self) -> None:
        """
        [FIX-SCENARIO] ET 기준 만기까지 남은 시간 자동 계산.
        만기 시각 = 만기일 16:00 ET (옵션 마감)
        1분마다 타이머로 호출, 만기일이 없으면 장 마감 기준(16:00) 사용.
        슬라이더 기본값도 자동 업데이트.
        """
        try:
            from datetime import datetime
            try:
                from zoneinfo import ZoneInfo
                _tz = ZoneInfo("America/New_York")
            except Exception:
                import pytz
                _tz = pytz.timezone("America/New_York")

            now_et = datetime.now(_tz)

            # 만기 시각 계산
            if self._expiry_str and len(self._expiry_str) == 8:
                y = int(self._expiry_str[:4])
                mo = int(self._expiry_str[4:6])
                d  = int(self._expiry_str[6:8])
                exp_dt = datetime(y, mo, d, 16, 0, 0, tzinfo=_tz)
            else:
                # 만기일 없으면 오늘 16:00 ET 기준
                exp_dt = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

            diff_sec = (exp_dt - now_et).total_seconds()
            hours_left = max(diff_sec / 3600.0, 0.0)
            self._hours_left = hours_left

            # 슬라이더 기본값 갱신 (ticks = hours × 2, 범위 0~16)
            ticks = min(int(round(hours_left * 2)), 16)
            if hasattr(self, 'sl_time'):
                self.sl_time.setValue(ticks)

            # 라벨 갱신
            if diff_sec <= 0:
                msg = "⏱ 만기 도달 (0h)"
                color = "#ff4444"
            elif hours_left < 1.0:
                msg = f"⏱ 만기까지 {hours_left*60:.0f}분 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#ff6666"
            elif hours_left < 2.0:
                msg = f"⏱ 만기까지 {hours_left:.1f}h 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#ffaa44"
            else:
                msg = f"⏱ 만기까지 {hours_left:.1f}h 남음 (ET {now_et.strftime('%H:%M')})"
                color = "#445566"

            if hasattr(self, '_lbl_time_auto'):
                self._lbl_time_auto.setText(msg)
                self._lbl_time_auto.setStyleSheet(
                    f"color:{color};font-size:10px;border:none;")

        except Exception:
            pass

    def _refresh(self):
        """슬라이더 값으로 현재 시나리오 갱신."""
        move  = float(getattr(self, 'sl_move', None).value()
                      if hasattr(self, 'sl_move') else 5)
        time_ticks = float(getattr(self, 'sl_time', None).value()
                           if hasattr(self, 'sl_time') else 8)
        hours_left = time_ticks / 2.0   # 슬라이더 1tick = 0.5h (남은 시간)
        div   = float(getattr(self, 'sl_iv', None).value()
                      if hasattr(self, 'sl_iv') else 0)

        if self._entry <= 0:
            # 데이터 없음 — 카드만 초기화
            for card_w, card_lv in (self._card_dg, self._card_th,
                                    self._card_vg, self._card_pct):
                card_lv.setText("―")
                card_lv.setStyleSheet("color:#888899;border:none;")
            return

        r = self._calc(move, hours_left, div)

        # 카드 갱신
        def _set_card(pair, val, unit="$"):
            _, lv = pair
            txt = f"{unit}{val:+.2f}" if unit == "$" else f"{val:+.1f}%"
            col = "#44ffaa" if val > 0 else "#ff6666" if val < 0 else "#888899"
            lv.setText(txt); lv.setStyleSheet(f"color:{col};border:none;")

        _set_card(self._card_dg,  r["dg"])
        _set_card(self._card_th,  r["th"])
        _set_card(self._card_vg,  r["vg"])
        _, pct_lv = self._card_pct
        pct_col = "#ffff44" if r["pct"] > 0 else "#ff6666" if r["pct"] < 0 else "#888899"
        pct_txt = ("MAX" if r["capped"]
                   else f"{r['pct']:+.1f}%")
        pct_lv.setText(pct_txt)
        pct_lv.setStyleSheet(
            f"color:{pct_col};border:none;font-weight:bold;")

        # 상세 분해 갱신
        entry = self._entry
        dg_pure = self._pos_delta * move * 100.0
        gm_pure = 0.5 * self._pos_gamma * move * move * 100.0

        def _fmt_val(lbl, v, unit="$"):
            if unit == "$":
                txt = f"${v:+.3f}"
            else:
                txt = f"{v:+.2f}%"
            col = "#44ffaa" if v > 0 else "#ff6666" if v < 0 else "#888899"
            lbl.setText(txt)
            lbl.setStyleSheet(f"color:{col};font-size:10px;border:none;")

        _fmt_val(self._lv_delta, dg_pure)
        _fmt_val(self._lv_gamma, gm_pure)
        _fmt_val(self._lv_theta, r["th"])
        _fmt_val(self._lv_vega,  r["vg"])

        self._lv_price.setText(f"${r['price']:.2f}"
                                + (" ★" if r["capped"] else ""))
        self._lv_price.setStyleSheet("color:#ffff44;font-size:10px;border:none;")
        self._lv_return.setText(pct_txt)
        self._lv_return.setStyleSheet(
            f"color:{pct_col};font-size:10px;border:none;font-weight:bold;")

        elapsed = r.get("elapsed", 0.0)
        mode    = r.get("mode", "근사")
        mode_color = "#44aaff" if mode == "BS" else \
                     "#44ccaa" if mode == "BS+근사" else "#886644"

        cap_txt = ""
        if r["capped"]:
            cap_txt = f"⚠ 예상가 상한 ${self._max_val:.2f} 초과 → MAX 고정  "
        cap_txt += (f"경과 {elapsed:.1f}h  "
                    f"({self._hours_left:.1f}h → {hours_left:.1f}h 남음)  ")

        self._lbl_cap_warn.setText(cap_txt)
        self._lbl_cap_warn.setStyleSheet(
            f"color:#ffaa44;font-size:10px;border:none;"
            if r["capped"] else
            f"color:#445566;font-size:10px;border:none;")

        # 매트릭스 갱신 (남은 시간 기준)
        for ri, m in enumerate(self._MOVES):
            for ci, t in enumerate(self._TIMES):
                rv = self._calc(float(m), t, div)
                if rv["capped"]:
                    txt = "MAX"
                    bg  = "#0a2a0a"
                    fg  = "#44ff44"
                elif rv["pct"] > 50:
                    bg, fg = "#0a2a0a", "#88ff44"
                elif rv["pct"] > 0:
                    bg, fg = "#1a1a08", "#ffcc44"
                elif rv["pct"] > -50:
                    bg, fg = "#1a0808", "#ff8844"
                else:
                    bg, fg = "#2a0808", "#ff4444"

                if not rv["capped"]:
                    txt = f"{rv['pct']:+.0f}%"

                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor(fg))
                it.setBackground(QColor(bg))
                it.setFlags(Qt.ItemIsEnabled)
                self._matrix_tbl.setItem(ri, ci, it)