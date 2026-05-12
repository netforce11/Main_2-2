"""
order_panel/helpers.py — 공용 헬퍼 함수
════════════════════════════════════════
포함:
  _kst_now()       KST 현재 시각 문자열 반환
  _animate_press() 버튼 클릭 2px 눌림 애니메이션
  _spx_tag()       sym/expiry → tradingClass(tag) 결정
"""

from datetime import datetime, timedelta

from PyQt5.QtCore import QRect, QPropertyAnimation


def _kst_now() -> str:
    """KST(UTC+9) 현재 시각을 HH:MM:SS 문자열로 반환."""
    return (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M:%S")


def _animate_press(btn):
    """버튼을 순간적으로 2px 아래로 밀었다가 복귀 (클릭 피드백)."""
    geo  = btn.geometry()
    anim = QPropertyAnimation(btn, b"geometry")
    anim.setDuration(80)
    pressed = QRect(geo.x(), geo.y() + 2, geo.width(), geo.height())
    anim.setKeyValueAt(0,   geo)
    anim.setKeyValueAt(0.5, pressed)
    anim.setKeyValueAt(1,   geo)
    anim.start()
    btn._anim = anim   # GC 방지


def _spx_tag(sym: str, expiry: str) -> str:
    """sym/expiry 기반으로 tradingClass(tag) 결정.
    core_contract.make_opt_contract 가 NANOS/SPX/SPXW 분기를
    내부 처리하므로 여기서는 tag 힌트만 반환한다.
    """
    s = (sym or "").upper()
    if s == "NANOS":
        return "SPXW"
    if s in ("SPX", "SPXW"):
        try:
            from core_contract import _resolve_spx_trading_class
            return _resolve_spx_trading_class(s, expiry)
        except Exception:
            pass
    return "SPXW"
