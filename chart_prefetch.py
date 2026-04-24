"""
chart_prefetch.py — 관심종목 1분봉 선행 다운로드  v6.5
────────────────────────────────────────────────────────
1분봉 탭이 처음 포커스될 때(하루 1회) 관심종목 전체에 대해
최근 7 거래일치 1분봉 데이터를 백그라운드로 다운로드한다.

흐름:
  on_tab_activate() 호출
    → 오늘 이미 실행했으면 skip
    → PrefetchManager.start() → 종목별 PrefetchWorker(QThread) 순차 실행
      ① Polygon 시도 → 성공 시 CSV+마커 저장
      ② Polygon 실패 + IBKR 연결 + 7거래일 이내 → IBKR 요청
      ③ IBKR 미연결 시 팝업 1회 표시 후 Polygon 결과만 저장
"""

import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import requests
from typing import List, Optional
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from PyQt5.QtCore  import QThread, pyqtSignal, QObject
from PyQt5.QtWidgets import QMessageBox

try:
    from common import DATA_ROOT
except Exception:
    DATA_ROOT = Path("/home/netforce/US_Data/US_stockData")

try:
    from common import API_KEY_FILE
    _API_KEY = API_KEY_FILE.read_text(encoding="utf-8").strip()
except Exception:
    _API_KEY = ""

# ── 마커 헬퍼 (chart_tab_ibkr.py 와 동일 구조) ────────────────

def _marker_path(sym: str, d: date) -> Path:
    return DATA_ROOT / sym / ".downloaded" / d.strftime("%Y%m%d")

def _has_marker(sym: str, d: date) -> bool:
    return _marker_path(sym, d).exists()

def _set_marker(sym: str, d: date):
    mp = _marker_path(sym, d)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.touch()


# ── 거래일 목록 계산 ───────────────────────────────────────────

def _last_n_trading_days(n: int = 7) -> List[date]:
    """오늘 포함 최근 n 거래일 (월~금) 목록, 오래된 순."""
    result, d = [], date.today()
    while len(result) < n:
        if d.weekday() < 5:   # 월(0)~금(4)
            result.append(d)
        d -= timedelta(days=1)
    return list(reversed(result))


# ── 단일 종목 / 단일 날짜 다운로드 ───────────────────────────

def _download_polygon(sym: str, tgt: date, api_key: str) -> Optional[pd.DataFrame]:
    """Polygon /1/minute → DataFrame. 실패 시 None."""
    ds  = tgt.strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{sym}"
           f"/range/1/minute/{ds}/{ds}"
           f"?apiKey={api_key}&limit=50000")
    try:
        r = requests.get(url, timeout=15).json()
        results = r.get("results", [])
        if results:
            return pd.DataFrame(results)
    except Exception as e:
        print(f"[Prefetch] Polygon 오류 {sym} {tgt}: {e}")
    return None


def _save_to_csv(sym: str, tgt: date, df: pd.DataFrame):
    """DataFrame → {SYM}/{YYYYMM}.csv 병합 저장 + 마커 생성."""
    fp = DATA_ROOT / sym / f"{tgt.strftime('%Y%m')}.csv"
    fp.parent.mkdir(parents=True, exist_ok=True)
    if fp.exists():
        try:
            merged = (pd.concat([pd.read_csv(str(fp)), df])
                      .drop_duplicates(subset=["t"])
                      .reset_index(drop=True))
        except Exception:
            merged = df
    else:
        merged = df
    merged.to_csv(str(fp), index=False)
    _set_marker(sym, tgt)
    print(f"[Prefetch] {sym} {tgt} 저장 완료 ({len(df)}행)")


# ══════════════════════════════════════════════════════════════
# 단일 종목 워커 (QThread)
# ══════════════════════════════════════════════════════════════

class PrefetchWorker(QThread):
    """한 종목의 7거래일치 데이터를 백그라운드에서 다운로드."""
    progress = pyqtSignal(str)   # 상태 메시지
    finished = pyqtSignal(str)   # 종목명 (완료 시)
    need_ibkr = pyqtSignal(str, object)   # (sym, [missing dates]) → IBKR 요청용

    def __init__(self, sym: str, trading_days: List[date], api_key: str):
        super().__init__()
        self.sym          = sym.upper()
        self.trading_days = trading_days
        self.api_key      = api_key

    def run(self):
        missing_for_ibkr = []   # Polygon 실패 날짜 → IBKR 후보

        for tgt in self.trading_days:
            if _has_marker(self.sym, tgt):
                continue   # 이미 완료

            self.progress.emit(f"📥 {self.sym} {tgt} 다운로드 중…")

            df = _download_polygon(self.sym, tgt, self.api_key)
            if df is not None:
                _save_to_csv(self.sym, tgt, df)
            else:
                # Polygon 결과 없음 → IBKR 후보에 추가
                missing_for_ibkr.append(tgt)

        if missing_for_ibkr:
            self.need_ibkr.emit(self.sym, missing_for_ibkr)

        self.finished.emit(self.sym)


# ══════════════════════════════════════════════════════════════
# 전체 관리자
# ══════════════════════════════════════════════════════════════

class PrefetchManager(QObject):
    """
    관심종목 리스트를 받아 PrefetchWorker 를 순차 실행.
    병목 방지: 한 번에 1개 워커만 실행 (큐 방식).
    """
    all_done   = pyqtSignal()
    status_msg = pyqtSignal(str)
    ibkr_alert = pyqtSignal(str)   # IBKR 미연결 팝업 요청

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue:   List  = []
        self._worker:  Optional[PrefetchWorker] = None
        self._ibkr_warned = False   # 팝업 중복 방지

    def start(self, symbols: List[str], api_key: str, mw=None):
        self._mw       = mw
        self._api_key  = api_key
        self._ibkr_warned = False
        trading_days   = _last_n_trading_days(7)

        # 마커 미완성 종목만 큐에 추가
        pending = []
        for sym in symbols:
            missing = [d for d in trading_days if not _has_marker(sym.upper(), d)]
            if missing:
                pending.append((sym.upper(), trading_days))

        if not pending:
            self.status_msg.emit("✅ 관심종목 전체 캐시 완료 (다운로드 불필요)")
            self.all_done.emit()
            return

        self._queue = pending
        self.status_msg.emit(
            f"📥 관심종목 선행 다운로드 시작 ({len(pending)}종목)…")
        self._next()

    def _next(self):
        if not self._queue:
            self.status_msg.emit("✅ 관심종목 선행 다운로드 완료")
            self.all_done.emit()
            return

        sym, days = self._queue.pop(0)
        self._worker = PrefetchWorker(sym, days, self._api_key)
        self._worker.progress.connect(self.status_msg)
        self._worker.finished.connect(self._on_finished)
        self._worker.need_ibkr.connect(self._on_need_ibkr)
        self._worker.start()

    def _on_finished(self, sym: str):
        remaining = len(self._queue)
        if remaining:
            self.status_msg.emit(
                f"✅ {sym} 완료 · 남은 종목 {remaining}개…")
        self._next()

    def _on_need_ibkr(self, sym: str, missing_dates: list):
        """Polygon 실패 날짜 → IBKR 연결 여부 확인 후 마커만 생성(휴장일)하거나 경고."""
        mw = getattr(self, '_mw', None)
        connected = getattr(mw, 'connected', False) if mw else False

        if not connected:
            if not self._ibkr_warned:
                self._ibkr_warned = True
                self.ibkr_alert.emit(
                    f"IBKR 미연결 상태입니다.\n"
                    f"Polygon에서 가져오지 못한 날짜({len(missing_dates)}일)는\n"
                    f"IBKR 연결 후 수동으로 조회하거나\n"
                    f"다음 실행 시 자동 재시도됩니다.\n\n"
                    f"해당 종목: {sym}")
            # 마커 없이 두면 다음 실행 시 재시도됨
            return

        # IBKR 연결 중 → 7거래일 이내 날짜만 마커 생성 예약
        # (실제 IBKR 분봉 요청은 사용자가 직접 클릭 시 fetch_ibkr_history 에서 처리)
        # 여기서는 휴장일로 간주하고 마커 생성 → 재시도 방지
        today = date.today()
        for d in missing_dates:
            delta = sum(1 for i in range((today - d).days + 1)
                        if (today - timedelta(days=i)).weekday() < 5)
            if delta > 7:
                # 7거래일 초과 + Polygon 없음 → 휴장일로 간주, 마커 생성
                _set_marker(sym, d)
                print(f"[Prefetch] {sym} {d} 휴장일 추정 → 마커 생성")