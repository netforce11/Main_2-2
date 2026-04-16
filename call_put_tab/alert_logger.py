"""
alert_logger.py — SPX 알람 파일 로거  v1.0
════════════════════════════════════════════════════
역할:
  - 알람 발생 시 일별 .log 파일에 기록
  - 저장 경로: C:\\data\\Greeks_history\\alert_YYYYMMDD.log
  - 포맷: 2026-04-16 14:23:05 [LV3] SPX -18.0P | 풋옵션 급등
  - 오늘 로그 불러오기: load_today() → List[str]
Python 3.8 호환
════════════════════════════════════════════════════
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import List


# 로그 저장 기본 경로 (없으면 자동 생성)
DEFAULT_LOG_DIR = r"C:\data\Greeks_history"


class AlertLogger:
    """
    일별 알람 로그 파일 관리.

    사용 예:
        logger = AlertLogger()
        logger.write("LV3", "SPX -18.0P | 풋옵션 +520%")
        lines = logger.load_today()
    """

    def __init__(self, log_dir: str = DEFAULT_LOG_DIR):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    # ── 경로 헬퍼 ────────────────────────────────────────────

    def _log_path(self, date_str: str = "") -> str:
        """date_str: 'YYYYMMDD' 형식. 비어있으면 오늘."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.log_dir, f"alert_{date_str}.log")

    def today_path(self) -> str:
        return self._log_path()

    # ── 쓰기 ─────────────────────────────────────────────────

    def write(self, level: str, msg: str) -> None:
        """알람 한 줄 기록."""
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{level}] {msg}\n"
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass   # 디스크 쓰기 실패 시 조용히 무시

    def write_info(self, msg: str) -> None:
        """감시 시작/중지 등 시스템 메시지 기록."""
        self.write("INFO", msg)

    # ── 읽기 ─────────────────────────────────────────────────

    def load_today(self) -> List[str]:
        """오늘 로그 전체 읽기. 파일 없으면 빈 리스트."""
        return self._load(self._log_path())

    def load_date(self, date_str: str) -> List[str]:
        """특정 날짜 로그 읽기. date_str: 'YYYYMMDD'."""
        return self._load(self._log_path(date_str))

    def _load(self, path: str) -> List[str]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                return [ln.rstrip("\n") for ln in f.readlines()]
        except OSError:
            return []

    # ── 파일 목록 ─────────────────────────────────────────────

    def list_log_files(self) -> List[str]:
        """alert_*.log 파일 목록 (최신순)."""
        try:
            files = [
                f for f in os.listdir(self.log_dir)
                if f.startswith("alert_") and f.endswith(".log")
            ]
            return sorted(files, reverse=True)
        except OSError:
            return []
