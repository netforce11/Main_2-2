"""
combo_second_logic.py — 추세 점수(Trend Score) 연산 모듈  v1.0
════════════════════════════════════════════════════════════════
역할:
  - 순수 연산 모듈 (UI 코드 없음)
  - main.py의 TradingDashboard 또는 임의 탭에서 호출 가능
  - importlib.reload()로 핫-리로드 지원

연결 구조:
  main.py (TradingDashboard)
    └── tab_combo_strategy.py (ComboStrategyGrid)
          └── combo_second_logic.execute_logic(df)  ← 여기

데이터 흐름:
  IBKR reqMktData / reqHistoricalData
    → core_fetch.py (CoreFetchMixin)
      → pandas DataFrame (open/high/low/close/volume)
        → combo_second_logic.execute_logic(df)
          → dict { total_score, details, signals }
════════════════════════════════════════════════════════════════
"""

import pandas as pd

try:
    import pandas_ta as ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    print("[combo_second_logic] ⚠ pandas_ta 미설치 — pip install pandas_ta")


# ════════════════════════════════════════════════════════════════
# 상수 — 점수 기준값 (이 파일만 수정해도 핫-리로드로 즉시 반영)
# ════════════════════════════════════════════════════════════════
MIN_BARS        = 60      # 최소 필요 봉 수
ADX_THRESHOLD   = 25      # ADX 추세 판단 기준
RSI_THRESHOLD   = 60      # RSI 에너지 판단 기준
SMA_SHORT       = 5
SMA_MID         = 20
SMA_LONG        = 60
ADX_LEN         = 14
RSI_LEN         = 14
BB_LEN          = 20
BB_STD          = 2.0

# 배점
SCORE_DIRECTION = 30      # 정배열
SCORE_ADX_BASE  = 25      # ADX >= 25
SCORE_ADX_RISE  = 15      # ADX 상승 추가
SCORE_BB_BREAK  = 15      # BB 상단 돌파
SCORE_RSI_HIGH  = 15      # RSI > 60


# ════════════════════════════════════════════════════════════════
# 메인 분석 클래스
# ════════════════════════════════════════════════════════════════
class TrendAnalyzer:
    """
    추세 점수 연산기.

    사용 예:
        from combo_second_logic import TrendAnalyzer
        result = TrendAnalyzer().calculate_score(df)
    """

    tab_name = "추세분석"          # TabWrapper / 로그 출력용 이름

    # ── 점수 계산 ────────────────────────────────────────────────
    def calculate_score(self, df: pd.DataFrame) -> dict:
        """
        Parameters
        ----------
        df : pd.DataFrame
            필수 컬럼: open, high, low, close, volume
            (core_fetch.py 혹은 tab_chart.py에서 넘겨주는 1분봉 DF)

        Returns
        -------
        dict
            total_score  : int   0~100
            details      : dict  { direction, strength, energy }
            signals      : dict  adx / rsi / is_alignment / bb_break
            message      : str   상태 메시지
        """
        # ── 전처리 ───────────────────────────────────────────────
        if df is None or len(df) < MIN_BARS:
            return {
                "total_score": 0,
                "details": {"direction": 0, "strength": 0, "energy": 0},
                "signals": {},
                "message": f"데이터 부족 (필요 {MIN_BARS}봉 / 현재 {len(df) if df is not None else 0}봉)"
            }
        if not TA_AVAILABLE:
            return {
                "total_score": 0,
                "details": {},
                "signals": {},
                "message": "pandas_ta 미설치"
            }

        df = df.copy()

        # 컬럼명 소문자 통일 (core_fetch.py → DF 컬럼이 대소문자 섞일 수 있음)
        df.columns = [c.lower() for c in df.columns]

        # ── 지표 계산 ────────────────────────────────────────────
        df["sma_s"]  = ta.sma(df["close"], length=SMA_SHORT)
        df["sma_m"]  = ta.sma(df["close"], length=SMA_MID)
        df["sma_l"]  = ta.sma(df["close"], length=SMA_LONG)

        adx_df       = ta.adx(df["high"], df["low"], df["close"], length=ADX_LEN)
        df["adx"]    = adx_df[f"ADX_{ADX_LEN}"]

        df["rsi"]    = ta.rsi(df["close"], length=RSI_LEN)

        bbands       = ta.bbands(df["close"], length=BB_LEN, std=BB_STD)
        df["bb_upper"] = bbands[f"BBU_{BB_LEN}_{BB_STD}"]

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        # ── ① 방향 점수 (30점) : 완전 정배열 ────────────────────
        direction_score = 0
        is_alignment = (
            curr["close"] > curr["sma_s"] > curr["sma_m"] > curr["sma_l"]
        )
        if is_alignment:
            direction_score = SCORE_DIRECTION

        # ── ② 강도 점수 (40점) : ADX ────────────────────────────
        strength_score = 0
        if curr["adx"] >= ADX_THRESHOLD:
            strength_score += SCORE_ADX_BASE
            if curr["adx"] > prev["adx"]:       # ADX 상승 중
                strength_score += SCORE_ADX_RISE

        # ── ③ 에너지 점수 (30점) : RSI + BB ─────────────────────
        energy_score = 0
        bb_break = curr["close"] >= curr["bb_upper"]
        if bb_break:
            energy_score += SCORE_BB_BREAK
        if curr["rsi"] > RSI_THRESHOLD:
            energy_score += SCORE_RSI_HIGH

        total_score = direction_score + strength_score + energy_score

        return {
            "total_score": total_score,
            "details": {
                "direction": direction_score,
                "strength":  strength_score,
                "energy":    energy_score,
            },
            "signals": {
                "adx":          round(float(curr["adx"]),  2),
                "rsi":          round(float(curr["rsi"]),  2),
                "is_alignment": is_alignment,
                "bb_break":     bb_break,
                "sma_s":        round(float(curr["sma_s"]), 2),
                "sma_m":        round(float(curr["sma_m"]), 2),
                "sma_l":        round(float(curr["sma_l"]), 2),
            },
            "message": self._grade(total_score),
        }

    # ── 등급 문자열 ──────────────────────────────────────────────
    @staticmethod
    def _grade(score: int) -> str:
        if score >= 85:  return "🔥 강한 추세 (매수 우위)"
        if score >= 60:  return "📈 추세 형성 중"
        if score >= 40:  return "⚡ 추세 약함 (관망)"
        return               "😴 추세 없음 (횡보)"


# ════════════════════════════════════════════════════════════════
# 외부 호출 인터페이스
# (importlib.reload 후에도 이 함수로 호출하면 최신 로직 적용)
# ════════════════════════════════════════════════════════════════
def execute_logic(data_frame: pd.DataFrame) -> dict:
    """
    tab_combo_strategy.py / main.py에서 단일 진입점으로 사용.

    예:
        import combo_second_logic as csl
        result = csl.execute_logic(df)
        print(result["total_score"], result["message"])
    """
    return TrendAnalyzer().calculate_score(data_frame)


# ════════════════════════════════════════════════════════════════
# main.py 연결 헬퍼
# ════════════════════════════════════════════════════════════════
def reload_and_run(mw, df: pd.DataFrame) -> dict:
    """
    main.py (TradingDashboard) 의 Refresh 버튼에서 직접 호출 가능.

    Parameters
    ----------
    mw : TradingDashboard
        main.py의 메인 윈도우 인스턴스 (연결 상태 확인용)
    df : pd.DataFrame
        1분봉 데이터프레임

    Returns
    -------
    dict  execute_logic() 결과
    """
    import importlib, sys

    # 이 모듈 자신을 핫-리로드
    module_name = __name__
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])

    # 리로드 후 최신 모듈에서 execute_logic 재호출
    fresh_module = sys.modules[module_name]
    result = fresh_module.execute_logic(df)

    # main.py 로그 출력 (tab_callput._log 패턴 재사용)
    analyzer_name = fresh_module.TrendAnalyzer.tab_name
    if mw and hasattr(mw, "tab_callput") and mw.tab_callput:
        try:
            mw.tab_callput._log(
                f"[{analyzer_name}] 점수={result['total_score']}  "
                f"{result.get('message','')}"
            )
        except Exception:
            pass

    return result


# ════════════════════════════════════════════════════════════════
# tab_combo_strategy.py 연결 예시 코드 (주석)
# ════════════════════════════════════════════════════════════════
#
# class ComboStrategyGrid(GridTab):
#     def __init__(self, mw):
#         super().__init__()
#         self.mw = mw
#         self._df = None           # core_fetch → 1분봉 DF 저장용
#         self._build_ui()
#         self._setup_refresh_button()
#
#     def _setup_refresh_button(self):
#         from PyQt5.QtWidgets import QPushButton
#         btn = QPushButton("🔄 추세 분석 새로고침")
#         btn.clicked.connect(self._on_refresh)
#         self.add(btn, row=0, col=0)
#
#     def _on_refresh(self):
#         import combo_second_logic as csl
#         result = csl.reload_and_run(self.mw, self._df)
#
#         score   = result["total_score"]
#         msg     = result.get("message", "")
#         details = result.get("details", {})
#         signals = result.get("signals", {})
#
#         # UI 업데이트 (라벨/테이블 등)
#         self.lbl_score.setText(f"총점: {score} / 100")
#         self.lbl_msg.setText(msg)
#         self.lbl_dir.setText(f"방향: {details.get('direction',0)}")
#         self.lbl_str.setText(f"강도: {details.get('strength',0)}")
#         self.lbl_eng.setText(f"에너지: {details.get('energy',0)}")
#
#     def set_df(self, df):
#         """core_fetch 또는 tab_chart에서 DF 수신 시 호출."""
#         self._df = df
#
