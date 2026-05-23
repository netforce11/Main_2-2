"""
combo_ui_left_chain_sync.py — 콜-풋 체인 자동 동기화 타이머 패치  v1.0
════════════════════════════════════════════════════════════════
문제:
  combo_ui_left.py 의 _auto_sync_chain() 이 정의만 되어 있고
  아무 타이머에도 연결되지 않아 수동 버튼 클릭 시에만 동기화됨.
  → combo_tab._chain_call/_chain_put 이 stale 상태 유지.

해결:
  이 모듈을 LeftPanelMixin 초기화 후 한 번 호출하면
  3초 주기 타이머로 _auto_sync_chain() 이 자동 실행됨.

  core_conn_tick_cache v1.2 의 _patch_chain_price 와 역할 분리:
    · _patch_chain_price : 틱 수신 즉시 O(1) 단일 행사가 갱신 (수십 ms)
    · _auto_sync_chain   : 3초 주기 전체 체인 풀 동기화 (폴백·안전망)

사용법 (combo_ui_right_panel.py 또는 메인 조립 파일에서):
    from combo_libs.combo_ui_left_chain_sync import attach_chain_sync_timer
    attach_chain_sync_timer(left_panel_instance)
════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
from PyQt5.QtCore import QTimer

_CHAIN_SYNC_INTERVAL_MS = 3_000   # 3초


def attach_chain_sync_timer(panel) -> QTimer | None:
    """
    LeftPanelMixin 인스턴스에 체인 자동 동기화 타이머를 붙인다.

    Args:
        panel: LeftPanelMixin 을 상속한 위젯 인스턴스
               (_auto_sync_chain 메서드가 있어야 함)

    Returns:
        생성된 QTimer (이미 붙어 있으면 기존 타이머 반환, 실패 시 None)
    """
    if not hasattr(panel, '_auto_sync_chain'):
        return None

    # 중복 부착 방지
    existing = getattr(panel, '_chain_sync_timer', None)
    if existing is not None and existing.isActive():
        return existing

    timer = QTimer(panel)
    timer.setInterval(_CHAIN_SYNC_INTERVAL_MS)
    timer.timeout.connect(panel._auto_sync_chain)
    timer.start()
    panel._chain_sync_timer = timer
    return timer


def detach_chain_sync_timer(panel) -> None:
    """타이머 정지 및 제거 (탭 비활성화·종료 시 호출)."""
    timer = getattr(panel, '_chain_sync_timer', None)
    if timer is not None:
        timer.stop()
        panel._chain_sync_timer = None
