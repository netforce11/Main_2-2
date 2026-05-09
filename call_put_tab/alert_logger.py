"""
alert_logger.py — SPX 알람 파일 로거  v1.1
════════════════════════════════════════════════════
역할:
  - 알람 발생 시 일별 .log 파일에 기록
  - 저장 경로: /home/netforce/trading_terminal/Main2_1/data/Greeks_history/
  - 포맷: 2026-04-16 14:23:05 [LV3] SPX -18.0P | 풋옵션 급등
  - 오늘 로그 불러오기: load_today() → List[str]

[v1.1 수정]
  - DEFAULT_LOG_DIR: 윈도우 하드코딩 경로(C:\\data\\...) → 리눅스 호환 경로로 변경
    C:\\data\\Greeks_history → /home/netforce/trading_terminal/Main2_1/data/Greeks_history
  - pathlib.Path 기반으로 교체하여 OS 독립적 경로 처리
  - 폴더 생성 실패 시 상세 에러 메시지 출력 (조용한 무시 → 원인 파악 가능)
  - write() OSError 무시 → 에러 내용 print로 출력 (로그 미기록 원인 추적용)
Python 3.8 호환
════════════════════════════════════════════════════
"""

from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from typing import List


# [v1.1] 리눅스 호환 경로로 변경 (기존: r"C:\data\Greeks_history")
# pathlib.Path 사용으로 OS 독립적 처리
DEFAULT_LOG_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/Greeks_history")


class AlertLogger:
    """
    일별 알람 로그 파일 관리.

    사용 예:
        logger = AlertLogger()
        logger.write("LV3", "SPX -18.0P | 풋옵션 +520%")
        lines = logger.load_today()
    """

    def __init__(self, log_dir=DEFAULT_LOG_DIR):
        # [v1.1] str/Path 모두 수용
        self.log_dir = Path(log_dir)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # 폴더 생성 실패 시 원인 출력 (조용히 무시하면 로그 미기록 원인 불명)
            print(f"[AlertLogger] ⚠ 로그 폴더 생성 실패: {self.log_dir} — {e}")

    # ── 경로 헬퍼 ────────────────────────────────────────────

    def _log_path(self, date_str: str = "") -> Path:
        """date_str: 'YYYYMMDD' 형식. 비어있으면 오늘."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        return self.log_dir / f"alert_{date_str}.log"

    def today_path(self) -> Path:
        return self._log_path()

    # ── 쓰기 ─────────────────────────────────────────────────

    def write(self, level: str, msg: str) -> None:
        """알람 한 줄 기록."""
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{level}] {msg}\n"
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(line)
        except OSError as e:
            # [v1.1] 조용한 무시 대신 원인 출력 — 로그 미기록 디버깅용
            print(f"[AlertLogger] ⚠ 로그 쓰기 실패: {self._log_path()} — {e}")

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

    def _load(self, path: Path) -> List[str]:
        if not path.exists():
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
                f.name for f in self.log_dir.iterdir()
                if f.name.startswith("alert_") and f.name.endswith(".log")
            ]
            return sorted(files, reverse=True)
        except OSError:
            return []