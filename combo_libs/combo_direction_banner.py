"""
combo_direction_banner.py — 복합전략 탭 방향 배너  v2.0
══════════════════════════════════════════════════════════
역할:
  레그 구조(C/P · 행사가 · BUY/SELL)만으로 전략 방향 자동 판단.
  가격 입력 없어도 체인 클릭 / 전략 선택 즉시 배너 갱신.

전략 감지 로직:
  ┌─────────────────────────────────────────────────────┐
  │ 2레그 스프레드                                        │
  │  콜 불  스프레드: 낮은K BUY C  + 높은K SELL C → 상승 │
  │  콜 베어 스프레드: 높은K BUY C  + 낮은K SELL C → 하락 │
  │  풋 베어 스프레드: 높은K BUY P  + 낮은K SELL P → 하락 │
  │  풋 불  스프레드: 낮은K BUY P  + 높은K SELL P → 상승 │
  │                                                     │
  │ 변동성 전략 (방향 없음)                               │
  │  스트래들:  BUY C + BUY P (같은 행사가)               │
  │  스트랭글:  BUY C + BUY P (다른 행사가)               │
  │  숏스트래들: SELL C + SELL P                          │
  │                                                     │
  │ 중립 전략 (레인지)                                    │
  │  나비:  3레그 동일 C 또는 P                           │
  │  콘도르: 4레그 동일 C 또는 P                          │
  │  아이언 콘도르: 4레그 C+P 혼합                         │
  │  아이언 나비:   3~4레그 C+P 혼합                      │
  └─────────────────────────────────────────────────────┘

사용법:
  ① 위젯 생성 및 배치 (레그 테이블 아래 빈 공간):
       from combo_direction_banner import DirectionBanner
       self.direction_banner = DirectionBanner(self)
       layout.addWidget(self.direction_banner)

  ② itemChanged 연결 (수동 편집 실시간 갱신):
       self.tbl_legs.itemChanged.connect(
           lambda item: self.direction_banner.refresh(self.tbl_legs))

  ③ 체인 클릭 / conId 완료 후 수동 호출:
       self.direction_banner.refresh(self.tbl_legs)
══════════════════════════════════════════════════════════
"""

from PyQt5.QtWidgets import QLabel, QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


# ══════════════════════════════════════════════════════════
# 스타일 상수
# ══════════════════════════════════════════════════════════
_S = {
    "bull": {
        "main": (
            "background: qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #00001a,stop:0.3 #000855,stop:0.5 #0010aa,"
            "stop:0.7 #000855,stop:1 #00001a);"
            "color:#3af;border:2px solid #22aaff;"
            "border-radius:10px;font-weight:bold;letter-spacing:3px;"
        ),
        "sub":  "color:#88ccff;font-size:11px;border:none;background:transparent;",
        "tag":  "color:#aaddff;font-size:10px;border:none;background:transparent;",
    },
    "bear": {
        "main": (
            "background: qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1a0000,stop:0.3 #550000,stop:0.5 #aa0000,"
            "stop:0.7 #550000,stop:1 #1a0000);"
            "color:#ff4444;border:2px solid #ff2222;"
            "border-radius:10px;font-weight:bold;letter-spacing:3px;"
        ),
        "sub":  "color:#ff9999;font-size:11px;border:none;background:transparent;",
        "tag":  "color:#ffbbbb;font-size:10px;border:none;background:transparent;",
    },
    "neutral": {
        "main": (
            "background: qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0a0a0a,stop:0.5 #1a1a2e,stop:1 #0a0a0a);"
            "color:#aa88ff;border:2px solid #6644aa;"
            "border-radius:10px;font-weight:bold;letter-spacing:3px;"
        ),
        "sub":  "color:#bb99ff;font-size:11px;border:none;background:transparent;",
        "tag":  "color:#ccaaff;font-size:10px;border:none;background:transparent;",
    },
    "vol": {
        "main": (
            "background: qlineargradient("
            "x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0a0a00,stop:0.5 #2a2a00,stop:1 #0a0a00);"
            "color:#ffdd00;border:2px solid #ccaa00;"
            "border-radius:10px;font-weight:bold;letter-spacing:3px;"
        ),
        "sub":  "color:#ffee88;font-size:11px;border:none;background:transparent;",
        "tag":  "color:#ffffaa;font-size:10px;border:none;background:transparent;",
    },
    "none": {
        "main": "",   # 런타임에 _get_none_style()로 생성
        "sub":  "",
        "tag":  "",
    },
}


def _get_none_style() -> dict:
    """'none' 상태 스타일 — 현재 테마 팔레트 참조."""
    try:
        import core as _c
        t = _c.THEME_PALETTES.get(_c.CURRENT_THEME, _c.THEME_PALETTES["light"])
        return {
            "main": (f"background:{t['group_bg']};color:{t['group_title']};"
                     f"border:1px solid {t['group_border']};border-radius:10px;"
                     "font-weight:normal;letter-spacing:1px;"),
            "sub":  f"color:{t['group_title']};font-size:11px;border:none;background:transparent;",
            "tag":  f"color:{t['group_title']};font-size:10px;border:none;background:transparent;",
        }
    except Exception:
        return {
            "main": ("background:#0d0d18;color:#44445a;"
                     "border:1px solid #222238;border-radius:10px;"
                     "font-weight:normal;letter-spacing:1px;"),
            "sub":  "color:#333350;font-size:11px;border:none;background:transparent;",
            "tag":  "color:#333350;font-size:10px;border:none;background:transparent;",
        }


# ══════════════════════════════════════════════════════════
# DirectionBanner 위젯
# ══════════════════════════════════════════════════════════
class DirectionBanner(QWidget):
    """
    레그 구조 기반 방향 배너.
    tbl_legs 아래 빈 공간에 addWidget() 으로 배치.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 10, 8)
        lay.setSpacing(5)

        _ns = _get_none_style()

        self.lbl_tag = QLabel("")
        self.lbl_tag.setAlignment(Qt.AlignCenter)
        self.lbl_tag.setStyleSheet(_ns["tag"])
        lay.addWidget(self.lbl_tag)

        self.lbl_main = QLabel("━  레그를 설정하면 방향을 표시합니다  ━")
        self.lbl_main.setAlignment(Qt.AlignCenter)
        self.lbl_main.setMinimumHeight(72)
        self.lbl_main.setFont(QFont("Arial", 19, QFont.Bold))
        self.lbl_main.setStyleSheet(_ns["main"])
        self.lbl_main.setWordWrap(True)
        lay.addWidget(self.lbl_main)

        self.lbl_sub = QLabel("C/P · 행사가 · BUY/SELL 조합으로 자동 판단")
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        self.lbl_sub.setStyleSheet(_ns["sub"])
        self.lbl_sub.setWordWrap(True)
        lay.addWidget(self.lbl_sub)

    # ── 공개 API ─────────────────────────────────────────────
    def refresh(self, tbl_legs):
        """tbl_legs 전체를 읽어 전략 감지 후 배너 갱신."""
        legs = _parse_all_legs(tbl_legs)
        if not legs:
            self._apply("none",
                        "━  레그를 설정하면 방향을 표시합니다  ━",
                        "C/P · 행사가 · BUY/SELL 조합으로 자동 판단", "")
            return

        result = _detect_strategy(legs)
        self._apply(
            result["mode"],
            result["banner"],
            result["sub"],
            result["tag"],
        )

    # ── 내부 렌더 ────────────────────────────────────────────
    def _apply(self, mode: str, banner: str, sub: str, tag: str):
        # none 모드는 런타임 팔레트 참조
        s = _get_none_style() if mode == "none" else _S.get(mode, _get_none_style())
        self.lbl_tag.setText(tag)
        self.lbl_tag.setStyleSheet(s["tag"])
        self.lbl_main.setText(banner)
        self.lbl_main.setStyleSheet(s["main"])
        self.lbl_sub.setText(sub)
        self.lbl_sub.setStyleSheet(s["sub"])


# ══════════════════════════════════════════════════════════
# 레그 파싱
# ══════════════════════════════════════════════════════════
def _parse_all_legs(tbl) -> list:
    """
    tbl_legs 전체 행 파싱 → 유효한 레그 dict 리스트 반환.
    컬럼: 0=레그명 1=BUY/SELL 2=C/P 3=행사가 4=가격 5=수량 6=만기
    행사가가 없거나 0인 행은 제외.
    """
    legs = []
    for r in range(tbl.rowCount()):
        def cell(c, _r=r):
            it = tbl.item(_r, c)
            return it.text().strip() if it else ""

        direction = cell(1).upper()
        cp        = cell(2).upper()
        strike_s  = cell(3)
        prem_s    = cell(4)

        if not strike_s or strike_s in ("―", ""):
            continue
        try:
            strike = float(strike_s)
        except ValueError:
            continue
        if strike <= 0:
            continue

        try:
            prem = float(prem_s) if prem_s and prem_s not in ("―", "") else 0.0
        except ValueError:
            prem = 0.0

        if direction not in ("BUY", "SELL"):
            direction = "BUY"
        if cp not in ("C", "P"):
            cp = "C"

        legs.append({
            "dir":    direction,
            "cp":     cp,
            "strike": strike,
            "prem":   prem,
            "row":    r,
        })
    return legs


# ══════════════════════════════════════════════════════════
# 전략 감지 엔진
# ══════════════════════════════════════════════════════════
def _detect_strategy(legs: list) -> dict:
    """
    레그 리스트 → 전략명 + 방향 판단.
    반환: { mode, banner, sub, tag }
    """
    n          = len(legs)
    calls      = [l for l in legs if l["cp"] == "C"]
    puts       = [l for l in legs if l["cp"] == "P"]
    call_buys  = [l for l in calls if l["dir"] == "BUY"]
    call_sells = [l for l in calls if l["dir"] == "SELL"]
    put_buys   = [l for l in puts  if l["dir"] == "BUY"]
    put_sells  = [l for l in puts  if l["dir"] == "SELL"]

    # ── 1레그 ─────────────────────────────────────────────
    if n == 1:
        l = legs[0]
        if l["dir"] == "BUY" and l["cp"] == "C":
            return _r("bull",
                      "🔺  상승 베팅 모드  🔺",
                      f"콜 단순 매수  │  {_k(l)} BUY C"
                      f"  →  상승 시 이익, 하락 시 프리미엄 손실",
                      "📈 Long Call")
        if l["dir"] == "BUY" and l["cp"] == "P":
            return _r("bear",
                      "🔻  하락 베팅 모드  🔻",
                      f"풋 단순 매수  │  {_k(l)} BUY P"
                      f"  →  하락 시 이익, 상승 시 프리미엄 손실",
                      "📉 Long Put")
        if l["dir"] == "SELL" and l["cp"] == "C":
            return _r("bear",
                      "🔻  하락 베팅 모드  🔻",
                      f"콜 단순 매도  │  {_k(l)} SELL C"
                      f"  →  하락/횡보 시 이익, 상승 시 무한손실 위험",
                      "📉 Short Call (Naked)")
        if l["dir"] == "SELL" and l["cp"] == "P":
            return _r("bull",
                      "🔺  상승 베팅 모드  🔺",
                      f"풋 단순 매도  │  {_k(l)} SELL P"
                      f"  →  상승/횡보 시 이익, 하락 시 큰 손실 위험",
                      "📈 Short Put (Naked)")

    # ── 2레그 ─────────────────────────────────────────────
    if n == 2:
        # ── 콜 전용 스프레드 ──────────────────────────────
        if len(calls) == 2 and len(puts) == 0:
            if len(call_buys) == 1 and len(call_sells) == 1:
                buy_k  = call_buys[0]["strike"]
                sell_k = call_sells[0]["strike"]
                if buy_k < sell_k:
                    # 낮은 K BUY + 높은 K SELL → 콜 불 스프레드 → 상승
                    return _r("bull",
                              "🔺  상승 베팅 모드  🔺",
                              f"콜 불 스프레드  │  "
                              f"BUY C {_ks(buy_k)}  →  SELL C {_ks(sell_k)}"
                              f"  │  최대이익 = 행사가 차이 − 순 데빗",
                              "📈 Bull Call Spread")
                else:
                    # 높은 K BUY + 낮은 K SELL → 콜 베어 스프레드 → 하락
                    return _r("bear",
                              "🔻  하락 베팅 모드  🔻",
                              f"콜 베어 스프레드  │  "
                              f"SELL C {_ks(sell_k)}  →  BUY C {_ks(buy_k)}"
                              f"  │  최대이익 = 순 크레딧",
                              "📉 Bear Call Spread")

            # 콜 2개 같은 방향
            if len(call_buys) == 2:
                return _r("bull",
                          "🔺  상승 베팅 모드  🔺",
                          f"콜 2개 매수  │  {_ks(calls[0]['strike'])} + {_ks(calls[1]['strike'])} BUY C"
                          f"  →  강한 상승 베팅",
                          "📈 Long 2 Calls")
            if len(call_sells) == 2:
                return _r("bear",
                          "🔻  하락 베팅 모드  🔻",
                          f"콜 2개 매도  │  {_ks(calls[0]['strike'])} + {_ks(calls[1]['strike'])} SELL C"
                          f"  →  하락/횡보 베팅 (리스크 주의)",
                          "📉 Short 2 Calls")

        # ── 풋 전용 스프레드 ──────────────────────────────
        if len(puts) == 2 and len(calls) == 0:
            if len(put_buys) == 1 and len(put_sells) == 1:
                buy_k  = put_buys[0]["strike"]
                sell_k = put_sells[0]["strike"]
                if buy_k > sell_k:
                    # 높은 K BUY P + 낮은 K SELL P → 풋 베어 스프레드 → 하락
                    return _r("bear",
                              "🔻  하락 베팅 모드  🔻",
                              f"풋 베어 스프레드  │  "
                              f"BUY P {_ks(buy_k)}  →  SELL P {_ks(sell_k)}"
                              f"  │  최대이익 = 행사가 차이 − 순 데빗",
                              "📉 Bear Put Spread")
                else:
                    # 낮은 K BUY P + 높은 K SELL P → 풋 불 스프레드 → 상승
                    return _r("bull",
                              "🔺  상승 베팅 모드  🔺",
                              f"풋 불 스프레드  │  "
                              f"SELL P {_ks(sell_k)}  →  BUY P {_ks(buy_k)}"
                              f"  │  최대이익 = 순 크레딧",
                              "📈 Bull Put Spread")

            if len(put_buys) == 2:
                return _r("bear",
                          "🔻  하락 베팅 모드  🔻",
                          f"풋 2개 매수  │  {_ks(puts[0]['strike'])} + {_ks(puts[1]['strike'])} BUY P"
                          f"  →  강한 하락 베팅",
                          "📉 Long 2 Puts")
            if len(put_sells) == 2:
                return _r("bull",
                          "🔺  상승 베팅 모드  🔺",
                          f"풋 2개 매도  │  {_ks(puts[0]['strike'])} + {_ks(puts[1]['strike'])} SELL P"
                          f"  →  상승/횡보 베팅 (리스크 주의)",
                          "📈 Short 2 Puts")

        # ── 스트래들 / 스트랭글 ───────────────────────────
        if len(call_buys) == 1 and len(put_buys) == 1 and len(call_sells) == 0 and len(put_sells) == 0:
            ck, pk = call_buys[0]["strike"], put_buys[0]["strike"]
            if ck == pk:
                return _r("vol",
                          "⚡  변동성 베팅 (방향 중립)  ⚡",
                          f"롱 스트래들  │  BUY C {_ks(ck)} + BUY P {_ks(pk)}"
                          f"  │  큰 변동성 기대, 방향 무관",
                          "⚡ Long Straddle")
            else:
                return _r("vol",
                          "⚡  변동성 베팅 (방향 중립)  ⚡",
                          f"롱 스트랭글  │  BUY C {_ks(ck)} + BUY P {_ks(pk)}"
                          f"  │  큰 변동성 기대, 방향 무관",
                          "⚡ Long Strangle")

        if len(call_sells) == 1 and len(put_sells) == 1 and len(call_buys) == 0 and len(put_buys) == 0:
            ck, pk = call_sells[0]["strike"], put_sells[0]["strike"]
            if ck == pk:
                return _r("neutral",
                          "🔲  레인지 베팅 (방향 중립)  🔲",
                          f"숏 스트래들  │  SELL C {_ks(ck)} + SELL P {_ks(pk)}"
                          f"  │  횡보 기대, 변동성 축소 베팅",
                          "🔲 Short Straddle")
            else:
                return _r("neutral",
                          "🔲  레인지 베팅 (방향 중립)  🔲",
                          f"숏 스트랭글  │  SELL C {_ks(ck)} + SELL P {_ks(pk)}"
                          f"  │  횡보 기대, 변동성 축소 베팅",
                          "🔲 Short Strangle")

    # ── 3레그 이상 → 방향 판단 불가 ──────────────────────
    return _r("none",
              "━  방향 판단 불가  ━",
              f"레그 {n}개 — 나비·콘도르 등 복합 전략은 방향을 자동 판단하지 않습니다",
              f"⚠ {n}-Leg (판단 불가)")


# ══════════════════════════════════════════════════════════
# 내부 헬퍼
# ══════════════════════════════════════════════════════════
def _r(mode, banner, sub, tag) -> dict:
    return {"mode": mode, "banner": banner, "sub": sub, "tag": tag}

def _k(leg) -> str:
    """레그 행사가 포맷 (정수 또는 소수점 1자리)."""
    k = leg["strike"]
    return str(int(k)) if k == int(k) else f"{k:.1f}"

def _ks(k: float) -> str:
    return str(int(k)) if k == int(k) else f"{k:.1f}"