"""
alert_logger.py — SPX 알람 파일 로거  v1.2
════════════════════════════════════════════════════
[v1.2] M-B 버퍼링 적용
  - write() 호출마다 파일 open/close → LogLineBuffer 버퍼에 축적
  - 10개 쌓이거나 1분 경과하면 일괄 flush
  - 앱 종료 시 close() 호출로 잔여 기록 보장
  - write_info()도 동일 버퍼 사용

[v1.1] 리눅스 호환 경로 + pathlib.Path 전환
Python 3.8 호환
════════════════════════════════════════════════════
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List

try:
    from trade_log.logger_buffer import LogLineBuffer
except ImportError:
    from logger_buffer import LogLineBuffer

DEFAULT_LOG_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/Greeks_history")


class AlertLogger:
    """
    일별 알람 로그 파일 관리 (버퍼링 v1.2).

    사용 예:
        logger = AlertLogger()
        logger.write("LV3", "SPX -18.0P | 풋옵션 +520%")
        lines = logger.load_today()
        logger.close()  # 앱 종료 시 반드시 호출
    """

    def __init__(self, log_dir=DEFAULT_LOG_DIR):
        self.log_dir = Path(log_dir)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[AlertLogger] ⚠ 로그 폴더 생성 실패: {self.log_dir} — {e}")

        # [v1.2] 버퍼: 10개 or 60초마다 flush
        self._buf = LogLineBuffer(
            path_fn=self._log_path,   # 날짜 바뀌어도 항상 올바른 경로
            max_count=10,
            max_seconds=60,
        )

    # ── 경로 헬퍼 ─────────────────────────────────────────────

    def _log_path(self, date_str: str = "") -> Path:
        """date_str: 'YYYYMMDD'. 비어있으면 오늘."""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
        return self.log_dir / f"alert_{date_str}.log"

    def today_path(self) -> Path:
        return self._log_path()

    # ── 쓰기 (버퍼 경유) ──────────────────────────────────────

    def write(self, level: str, msg: str) -> None:
        """
        알람 한 줄을 버퍼에 추가.
        [v1.2] open/close 없이 버퍼에만 저장 → 10개 or 1분 후 일괄 flush.
        """
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{level}] {msg}\n"
        self._buf.push(line)

    def write_info(self, msg: str) -> None:
        """감시 시작/중지 등 시스템 메시지 기록."""
        self.write("INFO", msg)

    def flush(self) -> None:
        """버퍼 내용을 즉시 파일에 기록 (수동 flush)."""
        self._buf.flush_all()

    def close(self) -> None:
        """앱 종료 시 호출 — 잔여 버퍼 기록 + 타이머 스레드 종료."""
        self._buf.stop()

    # ── 읽기 ──────────────────────────────────────────────────

    def load_today(self) -> List[str]:
        """오늘 로그 전체 읽기 (flush 후 읽음)."""
        self._buf.flush_all()   # 버퍼에 남은 것도 포함
        return self._load(self._log_path())

    def load_date(self, date_str: str) -> List[str]:
        """특정 날짜 로그 읽기. date_str: 'YYYYMMDD'."""
        self._buf.flush_all()
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
