"""
call_put_tab/_init_saver.py — chain_saver 초기화
════════════════════════════════════════════════
main.py 에서 탭 생성 직후 한 번만 호출:

    from call_put_tab import init_chain_saver
    self.tab_callput = CallPutGrid(self)
    init_chain_saver(self)
"""
from __future__ import annotations
import logging
from call_put_tab.chain_saver import ChainBuffer, SaveWorker, ChainScheduler
from call_put_tab.chain_saver.snapshot import (
    SNAP_C_START, SNAP_P_START, SNAP_SLOTS,
    NEXT_C_START, NEXT_P_START, NEXT_SLOTS,
)

log = logging.getLogger(__name__)


def init_chain_saver(main_win) -> ChainScheduler:
    """
    chain_saver 전체 초기화.

    main_win : TradingDashboard (MainWindow) 인스턴스
    반환값  : ChainScheduler (필요 시 참조용)
    """
    cp = main_win.tab_callput

    # 1. 버퍼 + 저장 스레드
    buf    = ChainBuffer()
    worker = SaveWorker()
    worker.start()

    # 2. 스케줄러
    scheduler = ChainScheduler(cp, buf, worker, parent=cp)

    # 3. 사이드바 저장 상태 라벨 연결
    if hasattr(cp, '_side_save_status'):
        scheduler.set_status_label(cp._side_save_status)

    # 4. TickRouter 에 스냅샷 reqId 범위 등록
    from core import router
    _ranges = [
        (SNAP_C_START, SNAP_C_START + SNAP_SLOTS - 1),
        (SNAP_P_START, SNAP_P_START + SNAP_SLOTS - 1),
        (NEXT_C_START, NEXT_C_START + NEXT_SLOTS - 1),
        (NEXT_P_START, NEXT_P_START + NEXT_SLOTS - 1),
    ]
    for start, end in _ranges:
        router.register_price(start, end, scheduler.on_tick_price)
        router.register_option(start, end, scheduler.on_tick_option)

    # 5. main_win 에 참조 저장 (tab_options_chart.py 에서 접근)
    main_win.chain_scheduler = scheduler
    main_win.chain_worker    = worker
    main_win.chain_buf       = buf

    # 6. 앱 종료 시 worker 정리
    try:
        main_win.app.aboutToQuit.connect(worker.stop)
    except AttributeError:
        pass  # app 참조 없는 환경

    # 7. 스케줄러 시작 (장외엔 저장 자동 스킵)
    scheduler.start()

    log.info("[init_chain_saver] 초기화 완료")
    return scheduler
