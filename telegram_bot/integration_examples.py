"""
각 탭에서 텔레그램 연동하는 방법 예제
=====================================================

1. 스나이퍼 탭 — 알람 전송만
2. 복합주문 탭 — 알람 전송 + 주문 수신
"""

# ─────────────────────────────────────────────────────────────
# 1. 스나이퍼 탭 예제 (sniper_tab/sniper_logic.py 안에서)
# ─────────────────────────────────────────────────────────────

from telegram_bot.tg_client import TelegramClient


class SniperLogicMixin:
    """스나이퍼 탭 기존 클래스에 mixin 방식으로 적용."""

    def _fire_sniper_alert(self, strike: float, opt_type: str, price: float):
        """스나이퍼 조건 발동 시 호출."""
        # 기존 팝업/소리 처리 ...

        # ── 텔레그램 알람 (한 줄 추가)
        msg = f"🎯 스나이퍼 발동: {opt_type} {strike} @ {price:.2f}"
        TelegramClient.get().send("sniper_alert", msg)


# ─────────────────────────────────────────────────────────────
# 2. 복합주문 탭 예제 (combo_tab/combo_order_handler.py 안에서)
# ─────────────────────────────────────────────────────────────

from telegram_bot.tg_command_router import TgCommandRouter


class ComboOrderHandler:
    """복합주문 탭 핸들러."""

    def __init__(self):
        self._tg = TelegramClient.get()
        self._register_tg_commands()

    # ── 초기화 시 텔레그램 명령 등록
    def _register_tg_commands(self):
        router = TgCommandRouter()
        router.register("/buy",    self._tg_buy)
        router.register("/sell",   self._tg_sell)
        router.register("/status", self._tg_status)
        router.register("/cancel", self._tg_cancel)

    # ── 텔레그램 → 주문 수신 핸들러
    def _tg_buy(self, text: str, from_id: str) -> str:
        """
        /buy C 5000 1
             │  │    └─ 수량
             │  └─ 행사가
             └─ C/P
        """
        parts = text.split()
        if len(parts) < 4:
            return "[오류] 형식: /buy C|P 행사가 수량"
        try:
            opt_type = parts[1].upper()   # C or P
            strike   = float(parts[2])
            qty      = int(parts[3])
        except ValueError:
            return "[오류] 숫자 형식 확인"

        # 실제 주문 로직 호출
        result = self._place_order("BUY", opt_type, strike, qty)

        # 체결 알람
        msg = f"✅ 텔레그램 주문 접수: BUY {opt_type} {strike} x{qty}"
        self._tg.send("order_confirm", msg)
        return result

    def _tg_sell(self, text: str, from_id: str) -> str:
        parts = text.split()
        if len(parts) < 4:
            return "[오류] 형식: /sell C|P 행사가 수량"
        try:
            opt_type = parts[1].upper()
            strike   = float(parts[2])
            qty      = int(parts[3])
        except ValueError:
            return "[오류] 숫자 형식 확인"

        result = self._place_order("SELL", opt_type, strike, qty)
        msg = f"✅ 텔레그램 주문 접수: SELL {opt_type} {strike} x{qty}"
        self._tg.send("order_confirm", msg)
        return result

    def _tg_status(self, text: str, from_id: str) -> str:
        return "현재 포지션: (연동 필요)"

    def _tg_cancel(self, text: str, from_id: str) -> str:
        return "주문 취소: (연동 필요)"

    def _place_order(self, side: str, opt_type: str, strike: float, qty: int) -> str:
        """실제 주문 로직 — 기존 복합주문 탭 메서드 호출."""
        # self.submit_order(side, opt_type, strike, qty) 형태로 연결
        return f"주문 전달 완료: {side} {opt_type} {strike} x{qty}"

    # ── 체결 완료 시 알람 (기존 체결 콜백에서 호출)
    def on_order_filled(self, side: str, opt_type: str, strike: float,
                        qty: int, fill_price: float):
        msg = (
            f"📋 체결 완료\n"
            f"{side} {opt_type} {strike} x{qty}\n"
            f"체결가: {fill_price:.2f}"
        )
        self._tg.send("order_confirm", msg)


# ─────────────────────────────────────────────────────────────
# 3. main.py 에서 앱 시작 시 polling 시작
# ─────────────────────────────────────────────────────────────

def start_telegram():
    """main.py 의 앱 초기화 부분에서 1회 호출."""
    TelegramClient.get().start_polling()


# ─────────────────────────────────────────────────────────────
# 4. 탭바에 텔레그램 탭 추가 (main.py 또는 메인 윈도우 클래스)
# ─────────────────────────────────────────────────────────────
#
#   from telegram_bot.tg_config_widget import TgConfigWidget
#   self.tab_widget.addTab(TgConfigWidget(), "📡 텔레그램")
#
# ─────────────────────────────────────────────────────────────
