"""
tab_chart.py 패치 가이드  v1.0
════════════════════════════════════════════════════════════════
목적:
  Tab7(ChartGrid) → Tab4(ComboStrategyGrid._trend_panel) 으로
  1분봉 DataFrame을 자동 push하는 연결 코드.

  아래 ① ② ③ 세 곳에 코드를 추가하면 됩니다.
  (원본 tab_chart.py 수정 최소화 — 각 3~5줄씩만 삽입)
════════════════════════════════════════════════════════════════
"""

# ══════════════════════════════════════════════════════════════
# [공통 헬퍼] — ChartGrid 클래스 안에 메서드로 추가
# _push_trend_df() 를 한 번만 정의하고 세 곳에서 호출합니다.
# ══════════════════════════════════════════════════════════════

HELPER_METHOD = '''
    # ── [v6.3 추가] Tab4 추세판으로 DF push ──────────────────────
    def _push_trend_df(self):
        """
        현재 self.df (1분봉 DataFrame)를 Tab4 TrendScorePanel로 전달.
        df 컬럼: t(ms timestamp), o, h, l, c, v
                 → TrendAnalyzer 내부에서 소문자 컬럼으로 rename됨
        """
        if not PANDAS or self.df is None or self.df.empty:
            return
        try:
            combo = getattr(self.mw, 'tab_combo', None)
            if combo and hasattr(combo, 'set_trend_df'):
                # Polygon/IBKR 컬럼명 통일 (o→open 등)
                col_map = {'o':'open','h':'high','l':'low','c':'close','v':'volume'}
                df_out = self.df.rename(columns=col_map)
                combo.set_trend_df(df_out)
        except Exception as e:
            print(f"[ChartGrid] _push_trend_df 오류: {e}")
'''

# ══════════════════════════════════════════════════════════════
# ① _fetch_polygon_history() 끝부분에 추가
#    (캘린더 클릭 → Polygon 과거 데이터 로드 완료 시점)
# ══════════════════════════════════════════════════════════════

PATCH_1_ORIGINAL = '''    def _fetch_polygon_history(self, symbol, tgt):
        """캘린더 클릭 → _load_day_df 삼단 fallback 사용"""
        df = self._load_day_df(symbol, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict('records')
            self.status_lbl.setText(f"📅 {tgt} 복기 (ET)")
            self._update_display()
            self.p1.autoRange()
        else:'''

PATCH_1_PATCHED = '''    def _fetch_polygon_history(self, symbol, tgt):
        """캘린더 클릭 → _load_day_df 삼단 fallback 사용"""
        df = self._load_day_df(symbol, tgt)
        if df is not None and not df.empty:
            self.df = df
            self.df_raw = df.to_dict('records')
            self.status_lbl.setText(f"📅 {tgt} 복기 (ET)")
            self._update_display()
            self.p1.autoRange()
            self._push_trend_df()          # ← [v6.3 추가] Tab4 push
        else:'''

# ══════════════════════════════════════════════════════════════
# ② _on_ibkr_hist_end() 끝부분에 추가
#    (IBKR reqHistoricalData 수신 완료 시점)
# ══════════════════════════════════════════════════════════════

PATCH_2_ORIGINAL = '''    def _on_ibkr_hist_end(self, rid):
        if rid!=REQ_HIST: return
        try: bridge.hist_bar.disconnect(self._on_ibkr_hist_bar)
        except: pass
        try: bridge.hist_end.disconnect(self._on_ibkr_hist_end)
        except: pass
        self._update_display()'''

PATCH_2_PATCHED = '''    def _on_ibkr_hist_end(self, rid):
        if rid!=REQ_HIST: return
        try: bridge.hist_bar.disconnect(self._on_ibkr_hist_bar)
        except: pass
        try: bridge.hist_end.disconnect(self._on_ibkr_hist_end)
        except: pass
        self._update_display()
        # ── [v6.3 추가] IBKR 수신 완료 후 Tab4 push ──────────────
        if PANDAS and self.df_raw:
            try:
                self.df = pd.DataFrame(self.df_raw)
            except Exception:
                pass
        self._push_trend_df()'''

# ══════════════════════════════════════════════════════════════
# ③ _do_multi_day() 끝부분에 추가
#    (연속보기 2~4일 차트 완성 시점)
# ══════════════════════════════════════════════════════════════

PATCH_3_ORIGINAL = '''        self.status_lbl.setText(f"📅 {num_days}일 연속 (ET, 정규장)")
        self._update_display(force_regular=True)
        if PG: self.p1.autoRange()'''

PATCH_3_PATCHED = '''        self.status_lbl.setText(f"📅 {num_days}일 연속 (ET, 정규장)")
        self._update_display(force_regular=True)
        if PG: self.p1.autoRange()
        self._push_trend_df()              # ← [v6.3 추가] Tab4 push'''

# ══════════════════════════════════════════════════════════════
# ④ main.py — tab_combo 속성 등록 (1줄 수정)
# ══════════════════════════════════════════════════════════════

MAIN_ORIGINAL = '''        add(ComboStrategyGrid,                "4. 복합 전략",    self)'''

MAIN_PATCHED  = '''        self.tab_combo = add(ComboStrategyGrid, "4. 복합 전략",    self)'''


# ══════════════════════════════════════════════════════════════
# 자동 패치 스크립트 (선택 사항)
# python apply_patch.py 로 실행하면 4개 수정을 자동으로 적용합니다.
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import re
    from pathlib import Path

    def patch_file(path: str, original: str, patched: str, label: str):
        p = Path(path)
        if not p.exists():
            print(f"[SKIP] {path} 파일 없음")
            return
        src = p.read_text(encoding="utf-8")
        if original not in src:
            print(f"[SKIP] {label} — 이미 적용됐거나 코드가 다릅니다.")
            return
        p.write_text(src.replace(original, patched, 1), encoding="utf-8")
        print(f"[OK]   {label}")

    # ChartGrid에 헬퍼 메서드 삽입
    chart_path = "tab_chart.py"
    p = Path(chart_path)
    if p.exists():
        src = p.read_text(encoding="utf-8")
        marker = "    def _push_trend_df"
        if marker not in src:
            # _fetch_polygon_history 정의 바로 앞에 삽입
            insert_before = "    def _fetch_polygon_history"
            if insert_before in src:
                src = src.replace(insert_before,
                                  HELPER_METHOD.lstrip('\n') + "\n    def _fetch_polygon_history",
                                  1)
                p.write_text(src, encoding="utf-8")
                print("[OK]   _push_trend_df 헬퍼 메서드 삽입")
            else:
                print("[WARN] _fetch_polygon_history를 찾지 못함 — 수동 삽입 필요")
        else:
            print("[SKIP] _push_trend_df 이미 존재")

    patch_file("tab_chart.py",  PATCH_1_ORIGINAL, PATCH_1_PATCHED, "① Polygon 과거 로드 후 push")
    patch_file("tab_chart.py",  PATCH_2_ORIGINAL, PATCH_2_PATCHED, "② IBKR hist 완료 후 push")
    patch_file("tab_chart.py",  PATCH_3_ORIGINAL, PATCH_3_PATCHED, "③ 연속보기 완료 후 push")
    patch_file("main.py",       MAIN_ORIGINAL,    MAIN_PATCHED,    "④ main.py tab_combo 속성 등록")

    print("\n패치 완료! 기존 파일은 수정됐습니다.")
    print("문제 발생 시 git diff 또는 백업본으로 복원하세요.")
