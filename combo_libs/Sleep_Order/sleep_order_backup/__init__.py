"""
Sleep_Order — 수면 예약 주문 패키지  v1.1
════════════════════════════════════════════
파일 구성:
  sleep_order_config.py   설정 저장소 (JSON)
  sleep_order_spike.py    급락 캐치 + 정정
  sleep_order_watcher.py  시간 감시 + 체인 스캔
  sleep_order_ui.py       설정 패널 + 버튼 위젯
  sleep_order_mixin.py    LeftPanelMixin 주입 메서드

사용:
  from Sleep_Order.sleep_order_config  import sleep_cfg
  from Sleep_Order.sleep_order_ui      import SleepOrderRightPanel, SleepOrderButton
  from Sleep_Order.sleep_order_mixin   import SleepOrderMixin
  from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
  from Sleep_Order.sleep_order_spike   import SleepSpikeWatcher
"""

# config 만 최상단 import (PyQt5 불필요 → 항상 안전)
from Sleep_Order.sleep_order_config import sleep_cfg, SleepOrderConfigStore
from Sleep_Order.sleep_order_mixin  import SleepOrderMixin

# PyQt5 의존 모듈은 lazy — 필요한 곳에서 직접 import
# from Sleep_Order.sleep_order_spike   import SleepSpikeWatcher
# from Sleep_Order.sleep_order_watcher import SleepOrderWatcher
# from Sleep_Order.sleep_order_ui      import SleepOrderRightPanel

__all__ = [
    "sleep_cfg",
    "SleepOrderConfigStore",
    "SleepOrderMixin",
]
