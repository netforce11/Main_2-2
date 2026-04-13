"""
combo_order_logic.py — 합성 주문 버튼 핸들러
──────────────────────────────────────────────
포함:
  _on_synthetic_order  — ⚡ 합성 주문 버튼
  _on_check_margin     — 💰 증거금 조회 버튼

위임:
  combo_order_whatif   — whatIf 콜백 & 전송
  combo_order_bag      — BAG 주문 전송
  combo_order_chaser   — Smart Chaser
  combo_order_utils    — 레그 파싱 / 증거금 추정
──────────────────────────────────────────────
"""

from PyQt5.QtWidgets import QMessageBox

# ── 위임 모듈 (RightPanelMixin에 주입되는 함수들) ───────────────
from combo_order_utils import _parse_legs_from_table, _parse_expiry_display, _calc_required_margin  # noqa
from combo_order_whatif import (                                                                      # noqa
    _on_whatif_acct_value, _on_whatif_acct_end,
    _on_whatif_result, _finish_whatif, _send_whatif_order,
)
from combo_order_bag    import _place_combo_legs, _place_bag_with_conids                             # noqa
from combo_order_chaser import register_chaser, deactivate_chaser, on_chase_click                    # noqa


# ── 공개 핸들러 ────────────────────────────────────────────────

def _on_synthetic_order(self):
    """⚡ 합성 주문 버튼 핸들러."""
    panel = getattr(self, 'synthetic_panel', None)
    if not panel:
        return self._log("⚠ synthetic_panel 없음")
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")

    strat    = self.combo_strat.currentText()
    cost_str = (self._kpi_widgets.get('cost',
                type('', (), {'text': lambda s: '―'})()).text()
                if hasattr(self, '_kpi_widgets') else "―")
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가/만기가 입력되지 않았습니다.\n"
            "체인 클릭 또는 수동 입력 후 다시 시도하세요.")

    def _on_margin_checked(available, required, margin_ok):
        if not margin_ok:
            return QMessageBox.warning(self, "증거금 부족",
                f"가용: ${available:,.2f}  /  필요: ${required:,.2f}\n"
                "증거금 부족으로 주문 취소.")
        leg_summary = "\n".join(
            f"  레그{i+1}: {lg['dir']} {lg['qty']}계약  "
            f"{lg['cp']} {lg['strike']}  @${lg['prem']}  만기:{lg['expiry']}"
            for i, lg in enumerate(legs))
        reply = QMessageBox.question(self, "⚡ 합성 주문 확인",
            f"전략: {strat}\n순비용: {cost_str}\n\n{leg_summary}\n\n"
            f"가용 증거금: ${available:,.2f}\n"
            f"필요 증거금: ${required:,.2f}\n\n"
            f"총 {len(legs)}개 레그를 주문하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            _place_combo_legs(self, legs, strat)

    _send_whatif_order(self, legs, strat, cost_str, on_done=_on_margin_checked)


def _on_check_margin(self):
    """💰 증거금 조회 버튼 핸들러."""
    if not getattr(getattr(self, 'mw', None), 'connected', False):
        return QMessageBox.warning(self, "미연결", "TWS에 먼저 연결하세요.")
    strat    = self.combo_strat.currentText()
    cost_str = (self._kpi_widgets.get('cost',
                type('', (), {'text': lambda s: '―'})()).text()
                if hasattr(self, '_kpi_widgets') else "―")
    legs = _parse_legs_from_table(self)
    if not legs:
        return QMessageBox.warning(self, "레그 오류",
            "행사가·프리미엄·만기를 입력한 후 다시 시도하세요.")
    self._log("💰 whatIf 증거금 조회 요청 중...")
    _send_whatif_order(self, legs, strat, cost_str, on_done=None)
