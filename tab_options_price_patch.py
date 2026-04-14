"""
tab_options_price_patch.py — [S10-A] 등락% 색상 강조 패치
════════════════════════════════════════════════════════════
적용 방법:
  tab_options_price.py 의 PricePanelMixin 클래스에
  아래 두 메서드를 추가한다.

  그리고 core_tick.py (또는 tickOptionComputation 콜백이 있는 파일)에서
  옵션 가격 업데이트 시 _render_chain_row() 를 호출하도록 연결한다.

호출 위치 (core_tick.py 또는 tickPrice 콜백):
  # 기존: tbl_set(tbl, row, col, value)
  # 추가: self._render_chain_row(tbl, row, price, prev_close)

컬럼 인덱스 (tbl_call / tbl_put 공통):
  0=행사가  1=가격  2=등락%  3=Delta  4=Theta  5=Gamma  6=잔고
════════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush

# 등락% 색상 임계값
_PCT_STRONG  = 3.0   # ±3% 초과 → 진한 강조
_PCT_MILD    = 1.0   # ±1~3%    → 연한 강조
_COL_UP_STR  = "#00e676"   # 강한 상승
_COL_UP_MLD  = "#69f0ae"   # 약한 상승
_COL_DN_STR  = "#ff5252"   # 강한 하락
_COL_DN_MLD  = "#ff8a80"   # 약한 하락
_COL_FLAT    = "#aaaaaa"   # 보합


def _mk_chg(text: str, color: str) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(Qt.AlignCenter)
    it.setForeground(QBrush(QColor(color)))
    return it


# ── 이 두 메서드를 PricePanelMixin 에 추가 ────────────────────

def _chg_color(pct: float) -> str:
    """등락률 → 색상 코드."""
    if pct >= _PCT_STRONG:   return _COL_UP_STR
    if pct >= _PCT_MILD:     return _COL_UP_MLD
    if pct <= -_PCT_STRONG:  return _COL_DN_STR
    if pct <= -_PCT_MILD:    return _COL_DN_MLD
    return _COL_FLAT


def render_chain_chg(tbl, row: int, price, prev_close):
    """
    옵션 체인 테이블의 col=2(등락%) 셀을 색상 강조로 갱신.

    Parameters
    ----------
    tbl        : QTableWidget  (tbl_call 또는 tbl_put)
    row        : int           행 인덱스
    price      : float|None   현재가 (last or mid)
    prev_close : float|None   전일 종가
    """
    if price is None or prev_close is None or prev_close == 0:
        tbl.setItem(row, 2, _mk_chg("―", _COL_FLAT))
        return

    chg = price - prev_close
    pct = chg / prev_close * 100
    sign = "+" if chg >= 0 else ""
    txt  = f"{sign}{pct:.1f}%"
    col  = _chg_color(pct)
    it   = _mk_chg(txt, col)

    # ±3% 초과 시 배경색도 살짝 강조
    if abs(pct) >= _PCT_STRONG:
        bg = QColor("#0d2a1a") if chg >= 0 else QColor("#2a0d0d")
        it.setBackground(QBrush(bg))

    tbl.setItem(row, 2, it)


# ════════════════════════════════════════════════════════════
# 아래는 core_tick.py (tickPrice / tickOptionComputation 콜백)
# 수정 가이드입니다. 실제 콜백 파일명이 다를 수 있으므로
# 패턴만 참고하세요.
# ════════════════════════════════════════════════════════════
"""
[ core_tick.py 수정 가이드 ]

1. call_data / put_data 딕셔너리에 'prev_close' 키 저장
   → tickType==75 (CLOSE) 수신 시:

   # tickPrice 콜백 내부 (예시)
   if tick_type == 75:   # CLOSE
       data_dict[rid]['prev_close'] = price

2. 가격 업데이트(tickType==4 LAST 또는 2 BID/3 ASK) 시 등락% 갱신:

   # tickPrice 콜백 내부 (예시)
   if tick_type in (2, 3, 4):
       data_dict[rid]['last'] = price
       row   = data_dict[rid].get('row')
       prev  = data_dict[rid].get('prev_close')
       if row is not None:
           tbl = self.tbl_call if is_call else self.tbl_put
           from tab_options_price_patch import render_chain_chg
           render_chain_chg(tbl, row, price, prev)

※ tickType 번호 (IBKR TWS API):
   1=BID  2=BID  3=ASK  4=LAST  9=CLOSE(일부)  14=OPEN  75=CLOSE
   실제 수신되는 번호는 TWS 설정에 따라 다를 수 있음.
"""
