"""
call_put_tab/_init_saver.py — chain_saver 초기화 + Greeks_Matrix 연동
═══════════════════════════════════════════════════════════════════
v6.6 변경:
  - init_chain_saver() 에서 tab_greeks 자동 감지 후 버퍼 연동
  - Greeks_Matrix 가 IBKR 직접 구독을 하지 않아도 chain_saver 콜백으로 수신
"""
from __future__ import annotations
import logging
from call_put_tab.chain_saver.buffer   import ChainBuffer
from call_put_tab.chain_saver.worker   import SaveWorker
from call_put_tab.chain_saver.scheduler import ChainScheduler

log = logging.getLogger(__name__)


def init_chain_saver(main_win) -> ChainScheduler:
    """
    main.py 에서 CallPutGrid 생성 직후 호출.

    main.py 예시:
        self.tab_callput = add(CallPutGrid, '1. 콜-풋 (Main)', self)
        init_chain_saver(self)

    Greeks_Matrix(tab_greeks) 가 main_win 에 있으면 자동 연동.
    연동 이후 Greeks_Matrix 는 IBKR 직접 구독 없이 chain_saver 콜백 수신.
    """
    cp     = main_win.tab_callput
    buf    = ChainBuffer()
    worker = SaveWorker()
    sched  = ChainScheduler(cp, buf, worker)

    worker.start()
    sched.start()

    # ── 상태 라벨 연결 ────────────────────────────────────
    lbl = getattr(cp, "_side_save_status", None)
    if lbl:
        sched.set_status_label(lbl)

    # ── Greeks_Matrix 버퍼 연동 ───────────────────────────
    tab_greeks = getattr(main_win, "tab_greeks", None)
    if tab_greeks is not None:
        try:
            tab_greeks.attach_chain_buffer(buf)
            log.info("[init_saver] Greeks_Matrix 버퍼 연동 완료 ✅")
        except AttributeError:
            log.warning("[init_saver] tab_greeks.attach_chain_buffer() 없음 — 연동 생략")
    else:
        log.info("[init_saver] tab_greeks 없음 — Greeks 연동 생략")

    # main_win 에 참조 저장 (외부에서 접근 가능)
    main_win._chain_buf    = buf
    main_win._chain_worker = worker
    main_win._chain_sched  = sched

    # 앱 종료 시 worker 정상 종료
    app = getattr(main_win, "app", None)
    if app:
        app.aboutToQuit.connect(worker.stop)

    log.info("[init_saver] chain_saver 초기화 완료")
    return sched
