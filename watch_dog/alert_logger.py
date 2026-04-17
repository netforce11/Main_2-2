"""
alert_logger.py — 알람 로그 파일 기록
- 일별 alert_YYYYMMDD.log 자동 생성
- 자정 넘어가면 새 파일로 자동 전환
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_DIR = Path(r"C:\data\Greeks_history")
logger  = logging.getLogger(__name__)


class AlertLogger:
    def __init__(self, log_dir: Path = LOG_DIR):
        self._log_dir  = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._cur_date: str = ""
        self._fh: Optional[logging.FileHandler] = None
        self._file_logger = logging.getLogger("alert_file")
        self._file_logger.setLevel(logging.INFO)
        self._file_logger.propagate = False

    # ── 외부 진입점 ────────────────────────────────────────

    def write(self, level: int, msg: str):
        self._rotate_if_needed()
        ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [LV{level}] {msg}"
        self._file_logger.info(line)

    def log_path_today(self) -> Path:
        date_str = datetime.now().strftime("%Y%m%d")
        return self._log_dir / f"alert_{date_str}.log"

    # ── 내부 ──────────────────────────────────────────────

    def _rotate_if_needed(self):
        today = datetime.now().strftime("%Y%m%d")
        if today == self._cur_date:
            return
        self._close_handler()
        path = self._log_dir / f"alert_{today}.log"
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))
        self._file_logger.addHandler(fh)
        self._fh = fh
        self._cur_date = today
        logger.info("알람 로그 파일 전환: %s", path)

    def _close_handler(self):
        if self._fh:
            self._file_logger.removeHandler(self._fh)
            self._fh.close()
            self._fh = None