"""
chain_saver/scheduler.py — 저장 스케줄러
════════════════════════════════════════
역할:
  - 5초마다: OTM/ITM 스냅샷 요청 → 버퍼 flush → 저장 enqueue
  - 60초마다: 내일 만기 스냅샷 요청
  - 장중(is_market_open)일 때만 저장 실행
  - 사이드바 상태 라벨 업데이트
  ── v6.6: 수신 통계 상태 라벨 표시 추가

스냅샷 요청 로직은 snapshot.py 에 분리됨.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, date
from typing import Dict, Tuple

from PyQt5.QtCore import QTimer, QObject

from core_io import is_market_open
from call_put_tab.chain_saver.buffer import ChainBuffer
from call_put_tab.chain_saver.worker import SaveWorker
from call_put_tab.chain_saver import snapshot as snap
from call_put_tab.chain_saver.db import check_recent
from call_put_tab.chain_saver.buffer import today_et

log = logging.getLogger(__name__)


class ChainScheduler(QObject):
    def __init__(self, cp, buf: ChainBuffer, worker: SaveWorker,
                 parent=None):
        super().__init__(parent)
        self._cp      = cp
        self._buf     = buf
        self._worker  = worker
        self._status_lbl  = None
        self._detail_lbl  = None   # 수신 통계 전용 라벨 (선택)
        self._snap_map: Dict[int, Tuple] = {}
        self._next_map: Dict[int, Tuple] = {}
        self._save_count_total = 0   # 누적 저장 건수
        self._bulk_buf: list = []    # ★ bulk INSERT 버퍼
        self._bulk_tick: int = 0     # flush 주기 카운터

        # ── 파일 로거 초기화 ─────────────────────────────────
        self._log_dir  = r"C:\data\Greeks_history"
        self._file_log = logging.getLogger("chainsaver_file")
        self._file_log.propagate = False   # 콘솔 중복 출력 방지
        self._setup_file_logger()

        self._t5  = QTimer(self); self._t5.setInterval(5_000)   # ★ 기본 5초
        self._t60 = QTimer(self); self._t60.setInterval(60_000)
        # 30초마다 수신 통계 로그 출력
        self._t_stat = QTimer(self); self._t_stat.setInterval(30_000)

        self._t5.timeout.connect(self._on_5s)
        self._t60.timeout.connect(self._on_60s)
        self._t_stat.timeout.connect(self._on_stat)

    # ── 외부 인터페이스 ──────────────────────────────────────
    def set_status_label(self, lbl):
        self._status_lbl = lbl

    def set_detail_label(self, lbl):
        """수신 통계 전용 라벨. 없어도 동작."""
        self._detail_lbl = lbl

    def set_save_interval(self, ms: int):
        """저장 주기 변경 (UI 콤보박스에서 호출)."""
        ms = max(500, ms)   # 최소 0.5초
        self._t5.setInterval(ms)
        log.info("[ChainScheduler] 저장 주기 변경 → %dms (%.1f초)", ms, ms/1000)

    # ── 파일 로거 셋업 ───────────────────────────────────────
    def _setup_file_logger(self):
        """일별 chainsaver_YYYYMMDD.log 파일 핸들러 등록."""
        os.makedirs(self._log_dir, exist_ok=True)
        today    = today_et().strftime("%Y%m%d")   # ★ ET 날짜
        log_path = os.path.join(self._log_dir, f"chainsaver_{today}.log")

        # 이미 같은 파일 핸들러가 붙어있으면 재등록 생략
        for h in self._file_log.handlers:
            if getattr(h, 'baseFilename', '') == log_path:
                return

        # 기존 핸들러 제거 후 오늘 파일 핸들러 등록
        self._file_log.handlers.clear()
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self._file_log.setLevel(logging.INFO)
        self._file_log.addHandler(fh)

    def log_path_today(self) -> str:
        """오늘 로그 파일 전체 경로 반환 (버튼 열기용)."""
        today = today_et().strftime("%Y%m%d")   # ★ ET 날짜
        return os.path.join(self._log_dir, f"chainsaver_{today}.log")

    def start(self):
        self._t5.start()
        self._t60.start()
        self._t_stat.start()

    def stop(self):
        self._t5.stop()
        self._t60.stop()
        self._t_stat.stop()

    # ── 5초 tick ────────────────────────────────────────────
    def _on_5s(self):
        if not is_market_open():
            self._set_status("pause"); return

        cp  = self._cp
        sym = cp.edit_sym.text().strip().upper() or "SPX"
        und = cp.und_price or 0.0
        self._buf.set_context(sym, und)

        expiry, tag = cp._get_expiry(silent=True)
        if not expiry or und <= 0:
            return

        n_atm = getattr(cp, '_n_strikes', 10)
        snap.request_otm(cp.mw.ib, sym, expiry, tag,
                         und, n_atm, self._snap_map)
        QTimer.singleShot(3_500, self._flush_and_save)

    def _flush_and_save(self):
        rows = self._buf.flush()
        if rows:
            # ★ bulk 버퍼에 누적 후 10초마다 한번에 INSERT
            self._bulk_buf.extend(rows)
            self._bulk_tick += 1
            now_ms = self._t5.interval()
            # 저장주기 × 10 마다 또는 500행 초과 시 flush
            bulk_every = max(1, 10_000 // now_ms)
            if self._bulk_tick >= bulk_every or len(self._bulk_buf) >= 500:
                self._worker.enqueue(self._bulk_buf.copy())
                self._save_count_total += len(self._bulk_buf)
                self._set_status("saving", len(self._bulk_buf))
                self._bulk_buf.clear()
                self._bulk_tick = 0

    # ── 60초 tick — 내일 만기 ────────────────────────────────
    def _on_60s(self):
        if not is_market_open():
            return
        cp  = self._cp
        sym = cp.edit_sym.text().strip().upper() or "SPX"
        und = cp.und_price or 0.0
        if und <= 0:
            return
        nxt = snap.request_next(cp.mw.ib, sym, und, self._next_map)
        if nxt:
            QTimer.singleShot(3_000, self._cancel_next)

    def _cancel_next(self):
        snap.cancel_map(self._cp.mw.ib, self._next_map)

    # ── 30초 tick — 수신 통계 ────────────────────────────────
    def _on_stat(self):
        """30초마다 버퍼 통계 + DB 통계를 콘솔과 파일에 출력."""
        # 날짜 바뀌면 파일 핸들러 갱신
        self._setup_file_logger()

        buf_stat = self._buf.stats()

        # 콘솔 + 파일 동시 기록
        buf_line = (
            f"[ChainSaver] 버퍼 엔트리={buf_stat['entries']} | "
            f"price_ticks={buf_stat['price_ticks']} "
            f"greeks_ticks={buf_stat['greeks_ticks']} "
            f"snap_ticks={buf_stat['snap_ticks']} | "
            f"이론가 커버리지={buf_stat['theo_coverage']}"
        )
        log.info(buf_line)
        self._file_log.info(buf_line)

        # DB 저장 현황 (최근 5분)
        day = today_et().strftime("%Y%m%d")   # ★ ET 날짜
        db_stat = check_recent(day, minutes=5)
        if "error" not in db_stat:
            db_line = (
                f"[ChainSaver] DB 최근5분 rows={db_stat['total_rows']} | "
                f"IV커버={db_stat['coverage_iv']:<6} "
                f"이론가커버={db_stat['coverage_theo']} | "
                f"stream={db_stat['streams']} snap={db_stat['snapshots']} | "
                f"최근저장={db_stat['latest_ts']}"
            )
            log.info(db_line)
            self._file_log.info(db_line)

        # 선택 라벨 업데이트
        if self._detail_lbl:
            txt = (
                f"엔트리 {buf_stat['entries']}  "
                f"이론가 {buf_stat['theo_coverage']}  "
                f"누적 {self._save_count_total}건"
            )
            self._detail_lbl.setText(txt)
            self._detail_lbl.setStyleSheet(
                "color:#888;font-size:9px;border:none;"
            )

    # ── tick 수신 (router 에서 호출) ─────────────────────────
    def on_tick_price(self, req_id: int, tick_type: int, price: float):
        entry = self._snap_map.get(req_id) or self._next_map.get(req_id)
        if not entry:
            return
        expiry, strike, side = entry
        bid = ask = last = None
        if   tick_type == 1: bid  = price
        elif tick_type == 2: ask  = price
        elif tick_type == 4: last = price
        else: return
        self._buf.update_snapshot(expiry, strike, side,
                                  bid=bid, ask=ask, last=last)

    def on_tick_option(self, req_id: int, tick_type: int,
                       iv: float, delta: float, option_price: float,
                       gamma: float, vega: float, theta: float):
        if tick_type not in (10, 11, 12, 13):
            return
        entry = self._snap_map.get(req_id) or self._next_map.get(req_id)
        if not entry:
            return
        expiry, strike, side = entry
        self._buf.update_snapshot(
            expiry, strike, side,
            iv=iv if iv and 0 < iv < 10 else None,
            delta=delta, gamma=gamma, vega=vega, theta=theta)

    # ── 상태 라벨 ────────────────────────────────────────────
    def _set_status(self, state: str, count: int = 0):
        if not self._status_lbl:
            return
        now = datetime.now().strftime("%H:%M:%S")
        if state == "saving":
            txt = f"💾 저장 중  {now}  ({count}건)"
            css = "color:#00e676;font-size:10px;border:none;"
        else:
            txt = "⏸ 장 마감 — 저장 중지"
            css = "color:#555;font-size:10px;border:none;"
        self._status_lbl.setText(txt)
        self._status_lbl.setStyleSheet(css)