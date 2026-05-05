"""
shared_chain_store.py — 탭 간 옵션 체인 데이터 공유 저장소

콜-풋탭이 수신한 틱 데이터(Greeks 포함)를 여기에 쓰고,
Greeks탭 / chain_saver / IVPanel 등은 여기서 읽기만 한다.

사용법:
    # main.py TradingDashboard.__init__ 에서
    from shared_chain_store import SharedChainStore
    self.chain_store = SharedChainStore()

    # 콜-풋탭 _apply_tick_option 에서 (쓰기)
    self.mw.chain_store.update(expiry, strike, side,
                               iv=iv, delta=delta, gamma=gamma,
                               vega=vega, theta=theta,
                               und_price=self.und_price)

    # Greeks탭 / IVPanel 에서 (읽기)
    data = self.mw.chain_store.get(expiry, strike, 'C')
    all_rows = self.mw.chain_store.iter_fresh(max_age=5.0)
"""

import time
import threading
from typing import Dict, Iterator, Optional, Tuple


class SharedChainStore:
    """
    옵션 체인 데이터 공유 저장소.

    키: (expiry: str, strike: float, side: str)
        expiry — YYYYMMDD 문자열
        strike — float (5500.0 등)
        side   — 'C' 또는 'P'

    값: dict
        bid, ask, last          : 가격
        iv, delta, gamma,
        vega, theta             : Greeks
        und_price               : 기초자산 현재가
        ts                      : 마지막 갱신 시각 (time.time())
    """

    def __init__(self):
        self._data: Dict[Tuple, dict] = {}
        self._lock = threading.Lock()   # 멀티스레드 안전

    # ── 쓰기 ────────────────────────────────────────────────────
    def update(self, expiry: str, strike: float, side: str, **kwargs):
        """
        데이터 갱신. 기존 키가 있으면 merge, 없으면 신규 생성.

        예)
            store.update('20260505', 5500.0, 'C',
                         bid=2.30, ask=2.35, iv=0.15, delta=0.45)
        """
        key = (expiry, float(strike), side)
        with self._lock:
            if key not in self._data:
                self._data[key] = {}
            self._data[key].update(kwargs)
            self._data[key]['ts'] = time.time()

    def update_price(self, expiry: str, strike: float, side: str,
                     bid=None, ask=None, last=None):
        """가격만 업데이트하는 편의 메서드."""
        kw = {}
        if bid  is not None: kw['bid']  = bid
        if ask  is not None: kw['ask']  = ask
        if last is not None: kw['last'] = last
        if kw:
            self.update(expiry, strike, side, **kw)

    def update_greeks(self, expiry: str, strike: float, side: str,
                      iv=None, delta=None, gamma=None,
                      vega=None, theta=None, und_price=None):
        """Greeks만 업데이트하는 편의 메서드."""
        kw = {}
        if iv        is not None: kw['iv']        = iv
        if delta     is not None: kw['delta']     = delta
        if gamma     is not None: kw['gamma']     = gamma
        if vega      is not None: kw['vega']      = vega
        if theta     is not None: kw['theta']     = theta
        if und_price is not None: kw['und_price'] = und_price
        if kw:
            self.update(expiry, strike, side, **kw)

    # ── 읽기 ────────────────────────────────────────────────────
    def get(self, expiry: str, strike: float, side: str) -> dict:
        """단일 키 조회. 없으면 빈 dict 반환."""
        key = (expiry, float(strike), side)
        with self._lock:
            return dict(self._data.get(key, {}))

    def has_fresh(self, expiry: str, strike: float, side: str,
                  max_age: float = 5.0) -> bool:
        """
        데이터가 존재하고 max_age 초 이내에 갱신됐으면 True.
        Greeks탭이 자체 구독 없이도 데이터가 있는지 확인할 때 사용.
        """
        key = (expiry, float(strike), side)
        with self._lock:
            d = self._data.get(key)
            if not d:
                return False
            return (time.time() - d.get('ts', 0)) < max_age

    def iter_fresh(self, max_age: float = 15.0) -> Iterator[Tuple[Tuple, dict]]:
        """
        max_age 초 이내에 갱신된 항목만 순회.
        chain_saver가 10초마다 flush할 때 사용.

        yields: ((expiry, strike, side), data_dict)
        """
        now = time.time()
        with self._lock:
            snapshot = list(self._data.items())
        for key, data in snapshot:
            if (now - data.get('ts', 0)) < max_age:
                yield key, dict(data)

    def get_all_fresh(self, max_age: float = 15.0) -> list:
        """
        iter_fresh()를 리스트로 반환.
        chain_saver SaveWorker 큐에 넣을 때 사용.

        반환: [{'expiry', 'strike', 'side', 'iv', 'delta', ...}, ...]
        """
        rows = []
        for (expiry, strike, side), data in self.iter_fresh(max_age):
            row = {'expiry': expiry, 'strike': strike, 'side': side}
            row.update(data)
            rows.append(row)
        return rows

    def get_expiry_keys(self, expiry: str) -> list:
        """
        특정 만기의 모든 (strike, side) 목록 반환.
        Greeks탭이 현재 만기 데이터 전체를 로드할 때 사용.
        """
        with self._lock:
            return [(s, sd) for (e, s, sd) in self._data if e == expiry]

    # ── 관리 ────────────────────────────────────────────────────
    def clear_expiry(self, expiry: str):
        """특정 만기 데이터 전체 삭제 (만기 교체 시)."""
        with self._lock:
            keys = [k for k in self._data if k[0] == expiry]
            for k in keys:
                del self._data[k]

    def clear_all(self):
        """전체 초기화."""
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        """저장된 항목 수."""
        with self._lock:
            return len(self._data)

    def __repr__(self):
        return f"<SharedChainStore size={self.size()}>"
