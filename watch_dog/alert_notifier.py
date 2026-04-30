"""
alert_notifier.py — 알람 통보 처리 (소리·UI 전달)
- AlertEngine 의 on_alert 콜백을 받아 실제 통보 수행
- 이 파일만 교체하면 알람 방식 변경 가능

[수정 내역]
- notify() 내 logger.warning() 제거
  → 파일 로그는 AlertLogger, UI 로그는 _on_alert_ui 에서 처리
  → 3중 로깅 → 단일 경로로 정리
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

LEVEL_COLORS = {1: "#FFD700", 2: "#FF8C00", 3: "#FF3333"}
LEVEL_LABELS = {1: "LV1",    2: "LV2",    3: "LV3"}


class AlertNotifier:
    """
    on_notify(level, msg) 호출 → 등록된 UI 콜백에 전달.
    소리/팝업은 추후 이 클래스만 수정.
    """

    def __init__(self):
        self._ui_callback: Optional[callable] = None

    def set_ui_callback(self, cb: callable):
        """UI(WatchAlertPanel)에서 등록: cb(level:int, msg:str)"""
        self._ui_callback = cb

    def notify(self, level: int, msg: str):
        """
        AlertEngine → 여기 → UI
        ✅ FIX: logger.warning() 제거 — 파일 로그는 AlertLogger 에서 단독 처리
        """
        self._play_sound(level)
        if self._ui_callback:
            self._ui_callback(level, msg)

    # ── 소리 (추후 교체 대상) ──────────────────────────────

    def _play_sound(self, level: int):
        """
        현재: winsound Beep (없으면 무시)
        추후: winsound.PlaySound / pygame / QSound 등으로 교체
        """
        try:
            import winsound
            freq = {1: 800, 2: 1000, 3: 1200}.get(level, 800)
            winsound.Beep(freq, 300)
        except Exception:
            pass
