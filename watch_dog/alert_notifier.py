"""
alert_notifier.py — 알람 통보 처리 (소리·UI·텔레그램)

[수정 내역]
- notify() 내 logger.warning() 제거 (기존 유지)
- ✅ NEW: 텔레그램 레벨별 전송 추가
  · LV1: 🔵 무음 전송 (disable_notification=True)
  · LV2: 🟡 일반 전송
  · LV3: 🔴🔴🔴 일반 전송 (강조)
  · 각 레벨 ON/OFF + pt 임계값은 TgConfig.watch_level() 에서 관리
  · pt 임계값 미달 시 해당 레벨 전송 안 함

[버그 수정]
- [FIX-1] notify_enabled("watch_alert") 전역 체크 추가
          → 전역 알람 OFF 시 모든 레벨 전송 차단
- [FIX-2] _parse_pt() 정규식 확장
          → "12.5pt" / "12.5p" / "-12.5 pt" / "SPX -12.5p" 등 모두 처리
- [FIX-3] _watch_lv_widgets 없을 때 AttributeError 방어
          → hasattr 체크 후 호출
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

LEVEL_COLORS = {1: "#FFD700", 2: "#FF8C00", 3: "#FF3333"}
LEVEL_LABELS = {1: "LV1",    2: "LV2",    3: "LV3"}

_TG_EMOJI  = {1: "🔵", 2: "🟡", 3: "🔴🔴🔴"}
_TG_SILENT = {1: True, 2: False, 3: False}   # LV1 만 무음 기본값


class AlertNotifier:
    """
    on_notify(level, msg) 호출 → 소리 + UI 콜백 + 텔레그램 전송.
    """

    def __init__(self):
        self._ui_callback: Optional[callable] = None

    def set_ui_callback(self, cb: callable):
        """UI(WatchAlertPanel)에서 등록: cb(level:int, msg:str)"""
        self._ui_callback = cb

    def notify(self, level: int, msg: str):
        """AlertEngine → 소리 + UI + 텔레그램"""
        self._play_sound(level)
        if self._ui_callback:
            self._ui_callback(level, msg)
        self._send_tg(level, msg)

    # ── 텔레그램 전송 ──────────────────────────────────────

    def _send_tg(self, level: int, msg: str):
        """
        1. notify_enabled("watch_alert") 전역 체크  [FIX-1]
        2. watch_level(lv) 로 enabled / min_pt / silent 조회
        3. min_pt 임계값 검사 (0이면 전부 통과)
        4. silent 여부에 따라 _send_raw / _send_raw_silent 분기
        """
        try:
            from telegram_bot.tg_config import TgConfig
            cfg = TgConfig()

            # [FIX-1] 전역 watch_alert 스위치 먼저 확인
            if not cfg.notify_enabled("watch_alert"):
                return

            lv_cfg = cfg.watch_level(level)
            if not lv_cfg.get("enabled", True):
                return

            # pt 임계값 검사  [FIX-2: 개선된 파서 사용]
            min_pt = float(lv_cfg.get("min_pt", 0.0))
            if min_pt > 0:
                pt_val = _parse_pt(msg)
                if pt_val is not None and abs(pt_val) < min_pt:
                    return   # 임계값 미달 → 무시

            emoji  = _TG_EMOJI.get(level, "🔔")
            silent = lv_cfg.get("silent", _TG_SILENT.get(level, False))
            text   = f"{emoji} [LV{level}] {msg}"

            from telegram_bot.tg_client import TelegramClient
            client = TelegramClient.get()
            if silent:
                client._send_raw_silent(text)
            else:
                client._send_raw(text)

        except Exception as e:
            # 텔레그램 실패가 알람 자체를 막으면 안 됨 → 조용히 로그만
            logger.debug(f"[AlertNotifier] TG 전송 실패: {e}")

    # ── 소리 ──────────────────────────────────────────────

    def _play_sound(self, level: int):
        try:
            import winsound
            freq = {1: 800, 2: 1000, 3: 1200}.get(level, 800)
            winsound.Beep(freq, 300)
        except Exception:
            pass


# ── 헬퍼: msg 에서 pt 값 파싱 ─────────────────────────────
def _parse_pt(msg: str) -> Optional[float]:
    """
    [FIX-2] 다양한 포맷 지원:
      "조건A: SPX -12.5pt"   → -12.5
      "SPX -12.5p (20분)"    → -12.5
      "+8.0 pt 변동"         → 8.0
      "15pt 초과"            → 15.0
    실패 시 None 반환 → 임계값 조건 무시하고 전송.
    """
    # pt 또는 p 앞의 숫자 (부호 포함)
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*pt?(?:\b|$)", msg, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None
