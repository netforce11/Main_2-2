# call_put_tab/tab_options_chain_b_fetch.py
"""
B 모드 전용 데이터 요청 관리.

- reqId 대역: 콜 5000~5099 / 풋 5100~5199  (A 모드와 충돌 없음)
- 요청 필드 : genericTickList "100,106"
    100 → Implied Volatility
    106 → Delta
  + tickPrice 콜백으로 last 수신
- 모드 전환 시 cancel() → request() 순으로 호출하면 됨
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from ibapi.contract import Contract


def _mk_contract(symbol: str, expiry: str,
                 strike: float, right: str) -> Contract:
    """IB 옵션 Contract 생성 헬퍼 (순환 임포트 방지용 로컬 구현)."""
    c = Contract()
    c.symbol       = symbol
    c.secType      = "OPT"
    c.exchange     = "SMART"
    c.currency     = "USD"
    c.lastTradeDateOrContractMonth = expiry
    c.strike       = strike
    c.right        = right          # "C" or "P"
    c.multiplier   = "100"
    return c

REQID_B_CALL_BASE = 5000   # 콜 전용 reqId 시작
REQID_B_PUT_BASE  = 5100   # 풋 전용 reqId 시작
MAX_STRIKES       = 100    # 대역 크기 (한 쪽당 최대 100개 행사가)


class ChainBFetch:
    """
    B 모드 reqMktData 요청 / 해제 담당.

    사용 예
    -------
    fetch = ChainBFetch(conn)
    fetch.request(strikes, expiry="20250417", symbol="SPX")
    ...
    fetch.cancel()
    """

    def __init__(self, conn):
        """
        Parameters
        ----------
        conn : IB EClient 인스턴스 (reqMktData / cancelMktData 보유)
        """
        self._conn = conn
        # reqId → (strike: float, side: str)
        self._active: Dict[int, Tuple[float, str]] = {}

    # ──────────────────────────────────────────────────────
    # 공개 메서드
    # ──────────────────────────────────────────────────────
    def request(self, strikes: List[float],
                expiry: str,
                symbol: str = "SPX"):
        """
        B 모드 데이터 요청 시작.
        기존 구독이 있으면 먼저 cancel() 후 재요청.

        Parameters
        ----------
        strikes : 행사가 리스트
        expiry  : 만기일 문자열 (예: "20250417")
        symbol  : 기초자산 심볼 (기본 "SPX")
        """
        self.cancel()

        strikes_sorted = sorted(strikes)
        if len(strikes_sorted) > MAX_STRIKES:
            strikes_sorted = strikes_sorted[:MAX_STRIKES]

        for i, strike in enumerate(strikes_sorted):
            for side, base in (("C", REQID_B_CALL_BASE),
                               ("P", REQID_B_PUT_BASE)):
                req_id   = base + i
                contract = _mk_contract(symbol, expiry, strike, side)
                self._conn.reqMktData(
                    req_id, contract,
                    "100,106",   # IV + Delta
                    False,       # snapshot=False (스트림)
                    False,
                    []
                )
                self._active[req_id] = (strike, side)

    def cancel(self):
        """현재 활성화된 B 모드 구독 전부 해제"""
        for req_id in list(self._active):
            try:
                self._conn.cancelMktData(req_id)
            except Exception:
                pass
        self._active.clear()

    def get_info(self, req_id: int) -> Optional[Tuple[float, str]]:
        """
        reqId가 B 모드 구독인지 확인.

        Returns
        -------
        (strike, side) 또는 None (A 모드 reqId인 경우)
        """
        return self._active.get(req_id)

    @property
    def is_active(self) -> bool:
        """B 모드 구독이 하나라도 살아있으면 True"""
        return bool(self._active)

    def active_req_ids(self) -> List[int]:
        """현재 활성 reqId 목록 반환"""
        return list(self._active.keys())