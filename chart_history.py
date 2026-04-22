"""
chart_history.py — HistoryMixin: daily/intraday fetch + render  [S10]

[S10] 변경사항:
  - _fetch_intraday(): is_market_open() 제거 → chk_live 체크박스 상태로 판단
    · chk_live 체크 + end_date 없음 → _ibkr_hist_live() (keepUpToDate=True)
    · chk_live 미체크 or end_date 지정 → 기존 _ibkr_hist() (과거 조회)
  - _on_und_label_clicked(): 동일하게 chk_live 상태 참조

[S9] 변경사항:
  - _fetch_intraday(): 장중(is_market_open) 이면 _ibkr_hist_live() 호출
  - 장외/캘린더 날짜 조회: 기존 _ibkr_hist() 그대로 유지
  - _on_und_label_clicked(): 장중 분봉탭 클릭 → live 모드로 진입

[S9 bugfix] pyqtgraph AxisItem TypeError 수정:
  - _on_intra_done(): pyqtgraph 호출 직전 rows에서 None/NaN 값 최종 필터링
  - _render_mini_chart(): times/opens/highs/lows/closes 전달 전 유효성 검사

롤백 기준 (S6/S7):
  - _fetch_intraday() 내부에 is_market_open 분기 없음
  - _ibkr_hist_live 호출 없음
"""

import math
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any

from PyQt5.QtCore import QTimer

from chart_utils import polygon_aggs, _FetchSignal
from chart_ibkr import IbkrHistMixin
from chart_history_vline import VlineMixin
from chart_ohlc import draw_ohlc_candles, _bars_to_rows


def _is_valid_row(row: dict) -> bool:
    """[S9 bugfix] rows 딕셔너리의 숫자 필드에 None/NaN/Inf 없는지 확인."""
    for k in ("open", "high", "low", "close"):
        v = row.get(k)
        if v is None:
            return False
        try:
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return False
        except (TypeError, ValueError):
            return False
    return True


# ──────────────────────────────────────────────────────────────
# HistoryMixin
# ──────────────────────────────────────────────────────────────
class HistoryMixin(VlineMixin, IbkrHistMixin):

    def _on_und_label_clicked(self):
        live_checked = (getattr(self, 'chk_live', None) is not None
                        and self.chk_live.isChecked())
        cur_tab = self._chart_tabs.currentIndex() if hasattr(self, '_chart_tabs') else 1

        if live_checked:
            if cur_tab == 2:
                self._fetch_intraday()
            else:
                self._log("⚡ 실시간 모드 — 실시간 탭으로 전환합니다.")
                if hasattr(self, '_chart_tabs'):
                    self._chart_tabs.setCurrentIndex(0)
            return

        if cur_tab == 2:
            self._fetch_intraday()
        else:
            if hasattr(self, '_chart_tabs'):
                self._chart_tabs.setCurrentIndex(1)
            self._fetch_daily(on_done_extra=self._fetch_intraday)

    # ── Daily ─────────────────────────────────────────────────
    def _fetch_daily(self, on_done_extra=None):
        sym = (self.edit_sym.text().strip().upper().replace("SPXW", "SPX")
               if hasattr(self, 'edit_sym') else "SPX")
        days_map = {"1개월": 30, "3개월": 90, "6개월": 180, "1년": 365}
        days  = days_map.get(self.combo_daily_period.currentText(), 365)
        end   = datetime.today().date()
        start = end - timedelta(days=days)

        # ── 장외 선물 모드: /ES 일봉 직접 조회 ──────────────────
        use_fut = getattr(self, '_und_is_futures', False) and sym == "SPX"
        if use_fut:
            fut_expiry = getattr(self, '_es_front_month', lambda: "")()
            self.lbl_daily_status.setText(f"⏳ IBKR 일봉 조회 중… /ES({fut_expiry})")
            days_map2 = {"1개월": "1 M", "3개월": "3 M", "6개월": "6 M", "1년": "1 Y"}
            dur = days_map2.get(self.combo_daily_period.currentText(), "6 M")

            def _on_fut_daily(bars):
                self._on_daily_done(bars, f"/ES({fut_expiry})")
                if callable(on_done_extra):
                    on_done_extra()

            self._ibkr_hist(sym, dur, "1 day", 9800,
                            _on_fut_daily, self.lbl_daily_status,
                            on_timeout=on_done_extra,
                            use_futures=True, fut_expiry=fut_expiry)
            return

        # ── 기존 Polygon → IBKR 폴백 ────────────────────────────
        self.lbl_daily_status.setText(f"조회 중… {sym} 일봉")
        sig = _FetchSignal()

        def _done(bars):
            self._on_daily_done(bars, sym)
            if callable(on_done_extra):
                on_done_extra()

        def _err(e):
            self._on_daily_err(e, sym, start, end, on_done_extra=on_done_extra)

        sig.done.connect(_done)
        sig.err.connect(_err)

        def _run():
            bars = polygon_aggs(sym, start, end, 1, "day")
            if bars: sig.done.emit(bars)
            else:    sig.err.emit("Polygon 실패 → IBKR 시도")

        threading.Thread(target=_run, daemon=True).start()

    def _on_daily_done(self, bars, sym):
        self.lbl_daily_status.setText(f"✅ {sym} 일봉  {len(bars)}봉")
        draw_ohlc_candles(self._pw_daily, self._daily_items, bars,
                          bar_width_sec=60 * 60 * 18)

    def _on_daily_err(self, msg, sym, start, end, on_done_extra=None):
        self.lbl_daily_status.setText(f"⚠ {msg}")
        days_map = {"1개월": "1 M", "3개월": "3 M", "6개월": "6 M", "1년": "1 Y"}
        dur = days_map.get(self.combo_daily_period.currentText(), "6 M")

        def _after_ibkr(bars):
            self._on_daily_done(bars, sym)
            if callable(on_done_extra):
                on_done_extra()

        self._ibkr_hist(sym, dur, "1 day", 9800,
                        _after_ibkr, self.lbl_daily_status,
                        on_timeout=on_done_extra,
                        use_futures=False, fut_expiry="")

    def _get_chart_sym(self) -> str:
        for attr in ("edit_sym",):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    return w.text().strip().upper().replace("SPXW", "SPX") or "SPX"
                except AttributeError:
                    pass
        for attr in ("_current_sym", "_chart_sym", "und_sym", "_sym"):
            v = getattr(self, attr, None)
            if isinstance(v, str) and v.strip():
                return v.strip().upper().replace("SPXW", "SPX")
        return "SPX"

    # ── Intraday ──────────────────────────────────────────────
    def _fetch_intraday(self, end_date: str = ""):
        """
        [S9] 분봉 조회 진입점.
        - end_date 지정(캘린더 조회) → 기존 _ibkr_hist() 그대로
        - 장중 + end_date 없음       → _ibkr_hist_live() (keepUpToDate=True)
        - 장외 + end_date 없음       → 기존 _ibkr_hist()
        """
        if not getattr(self, 'mw', None) or not self.mw.connected:
            if hasattr(self, 'lbl_intra_status'):
                self.lbl_intra_status.setText("❌ TWS/Gateway 연결 필요")
            return

        sym = self._get_chart_sym()
        tf_map  = {"1분": 1, "5분": 5, "15분": 15, "30분": 30, "60분": 60}
        tf      = tf_map.get(self.combo_intra_tf.currentText(), 1)
        max_bars = (self.spin_intra_bars.value()
                    if hasattr(self, 'spin_intra_bars') else 399)
        bar_size = ("1 min" if tf == 1 else
                    f"{tf} mins" if tf < 60 else "1 hour")

        self._intra_cache_sym     = sym
        self._intra_cache_tf      = tf
        self._intra_cache_bars    = None
        self._intra_cache_maxbars = max_bars

        # ── [S10] 실시간 체크박스 + 분봉 → live 모드 ────────
        live_checked = (getattr(self, 'chk_live', None) is not None
                        and self.chk_live.isChecked())
        if live_checked and not end_date:
            # 과거 조회 잔여 스트림 정리 (live → live 재진입 포함)
            self._stop_live()
            def _on_initial(bars):
                self._intra_cache_bars = bars
                self._on_intra_done(bars, sym, tf, max_bars)

            self._ibkr_hist_live(sym, bar_size, _on_initial,
                                 self.lbl_intra_status)
            return

        # ── 장외 선물 모드: /ES 분봉 실시간 스트림 (keepUpToDate=True) ──
        use_fut = getattr(self, '_und_is_futures', False) and sym == "SPX"
        if use_fut and not end_date:
            self._stop_live()
            fut_expiry = getattr(self, '_es_front_month', lambda: "")()
            sym_label  = f"/ES({fut_expiry})"

            def _on_fut_initial(bars):
                self._intra_cache_bars  = bars
                self._intra_cache_sym   = sym_label
                self._on_intra_done(bars, sym_label, tf, max_bars)

            self._ibkr_hist_live(sym, bar_size, _on_fut_initial,
                                 self.lbl_intra_status,
                                 use_futures=True, fut_expiry=fut_expiry)
            return

        # ── 장외 or 캘린더 날짜 지정 조회 (기존 로직) ────────
        # 실시간 스트림 반드시 먼저 정지
        self._stop_live()

        need_days = max(1, int(max_bars * tf / 390))
        if need_days <= 1:   dur = "1 D"
        elif need_days <= 2: dur = "2 D"
        elif need_days <= 5: dur = "1 W"
        else:                dur = "2 W"

        date_label = f"  [{end_date[:8]}]" if end_date else ""
        self.lbl_intra_status.setText(
            f"⏳ IBKR {bar_size} 조회 중… {sym} (최대 {max_bars}봉){date_label}")

        def _on_done(bars):
            self._intra_cache_bars = bars
            self._on_intra_done(bars, sym, tf, max_bars)

        def _do_request():
            ibkr_kwargs = {"end_date_time": end_date} if end_date else {}
            self._ibkr_hist(sym, dur, bar_size, 9802,  # 9801은 _LIVE_ID — 충돌 방지
                            _on_done, self.lbl_intra_status,
                            on_timeout=None, **ibkr_kwargs)

        # cancel 처리 완료 후 요청 — Access Violation 방지
        QTimer.singleShot(300, _do_request)

    # ── [S6] Calendar date fetch ──────────────────────────────
    def _on_intra_date_fetch(self):
        """캘린더 날짜 변경 시 즉시 조회. 실시간 체크박스를 자동 해제."""
        if not hasattr(self, 'intra_date_edit'):
            return
        # [S10] 날짜 지정 조회 시 실시간 체크박스 자동 해제
        if getattr(self, 'chk_live', None) and self.chk_live.isChecked():
            self.chk_live.setChecked(False)
        qdate  = self.intra_date_edit.date()
        # IBKR 형식: yyyymmdd-HH:MM:SS (UTC) — 해당 날짜 ET 23:59를 UTC로 변환
        try:
            from zoneinfo import ZoneInfo as _ZI
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo as _ZI
            except ImportError:
                import pytz as _pytz
                class _ZI:
                    def __new__(cls, key): return _pytz.timezone(key)
        from datetime import datetime as _dt, timezone as _tz
        local_end = _dt(qdate.year(), qdate.month(), qdate.day(),
                        23, 59, 59,
                        tzinfo=_ZI("America/New_York"))
        utc_end = local_end.astimezone(_tz.utc)
        end_dt  = utc_end.strftime("%Y%m%d-%H:%M:%S")   # e.g. 20240405-03:59:59
        self._fetch_intraday(end_date=end_dt)

    def _on_intra_done(self, bars: list, sym: str, tf: int, max_bars: int = 300):
        include_ext = (self.chk_intra_ext.isChecked()
                       if hasattr(self, 'chk_intra_ext') else False)
        use_kst = (self.chk_kst.isChecked()
                   if hasattr(self, 'chk_kst') else False)
        rows = _bars_to_rows(bars, include_ext=include_ext, tf_min=tf,
                             use_kst=use_kst)
        if len(rows) > max_bars:
            rows = rows[-max_bars:]

        # [S9 bugfix] pyqtgraph 전달 전 None/NaN 포함 row 최종 필터링
        rows = [r for r in rows if _is_valid_row(r)]

        if not rows:
            self.lbl_intra_status.setText(f"❌ {sym} — 데이터 없음")
            return
        t0, t1 = rows[0]["time"], rows[-1]["time"]
        ext_label = "(시간외포함)" if include_ext else "(정규장)"
        kst_label = " [KST]" if use_kst else ""
        self.lbl_intra_status.setText(
            f"✅ {sym}  {tf}분봉  {len(rows)}봉  ({t0}~{t1})  {ext_label}{kst_label}")
        self._render_mini_chart(rows)

    def _render_mini_chart(self, rows: List[Dict[str, Any]]):
        canvas = getattr(self, 'mini_chart_intra', None)
        if canvas is None:
            self.lbl_intra_status.setText("⚠ MiniChartCanvas 미초기화")
            return

        times  = [r["time"]          for r in rows]
        opens  = [r["open"]          for r in rows]
        highs  = [r["high"]          for r in rows]
        lows   = [r["low"]           for r in rows]
        closes = [r["close"]         for r in rows]
        vols   = [r.get("volume", 0) for r in rows]

        # [S9 bugfix] pyqtgraph에 넘기기 직전 리스트 레벨 최종 방어
        # opens/highs/lows/closes 중 하나라도 None이면 해당 봉 전체 제외
        valid_indices = [
            i for i in range(len(rows))
            if all(
                v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))
                for v in (opens[i], highs[i], lows[i], closes[i])
            )
        ]
        if not valid_indices:
            self.lbl_intra_status.setText(f"❌ 유효한 봉 데이터 없음")
            return
        if len(valid_indices) < len(rows):
            times  = [times[i]  for i in valid_indices]
            opens  = [opens[i]  for i in valid_indices]
            highs  = [highs[i]  for i in valid_indices]
            lows   = [lows[i]   for i in valid_indices]
            closes = [closes[i] for i in valid_indices]
            vols   = [vols[i]   for i in valid_indices]

        vol_thresh_units = (self.spin_vol_threshold.value()
                            if hasattr(self, 'spin_vol_threshold') else 0)
        vol_thresh = vol_thresh_units * 10_000

        try:
            mode = (self.combo_intra_chart_mode.currentText()
                    if hasattr(self, 'combo_intra_chart_mode') else "캔들")
            if mode == "캔들":
                canvas.plot_candles(times, opens, highs, lows, closes,
                                    volumes=vols,
                                    vol_highlight=vol_thresh if vol_thresh > 0 else None)
            else:
                canvas.plot_line(times, closes, volumes=vols)
        except Exception as e:
            self.lbl_intra_status.setText(f"⚠ 차트 오류: {e}")
            return

        for time_str, cb in getattr(self, '_vlines', []):
            try:
                canvas.add_vline(time_str)
                if cb and not cb.isChecked():
                    canvas.set_vline_visible(time_str, False)
            except Exception:
                pass

    def _redraw_intraday_cache(self):
        bars = getattr(self, '_intra_cache_bars', None)
        if not bars:
            return
        self._on_intra_done(bars,
                            getattr(self, '_intra_cache_sym', ""),
                            getattr(self, '_intra_cache_tf', 1),
                            getattr(self, '_intra_cache_maxbars', 300))

    def on_tab_activate(self):
        """
        탭 복귀 시 main.py _on_tab_changed()에서 호출됨.
        - 실시간 스트림 중이면 dirty 플래그 강제 설정 → 즉시 재렌더
        - 캐시 데이터가 있으면 강제 redraw (matplotlib 숨김 억제 해소)
        - live_render_timer 재시작 보장
        """
        # ① 실시간 스트림 중 → dirty 강제 설정 후 즉시 렌더
        if getattr(self, '_live_render_timer', None):
            self._live_dirty = True
            live_buf = getattr(self, '_live_buf', [])
            # _is_valid_bar와 동일 로직: o/h/l/c/v/t 모두 유효한 것만
            import math as _math
            def _ok(b):
                for k in ("o", "h", "l", "c", "v", "t"):
                    v = b.get(k)
                    if v is None: return False
                    try:
                        f = float(v)
                        if _math.isnan(f) or _math.isinf(f): return False
                    except (TypeError, ValueError): return False
                return True
            valid_bars = [b for b in live_buf if _ok(b)]
            if valid_bars:
                try:
                    self._on_intra_done(
                        valid_bars,
                        getattr(self, '_live_sym', ""),
                        getattr(self, '_intra_cache_tf', 1),
                        getattr(self, '_intra_cache_maxbars', 399))
                except Exception as e:
                    print(f"[on_tab_activate] live redraw 오류: {e}")
            # 타이머가 살아있지만 멈춘 경우 재시작
            t = self._live_render_timer
            if t and not t.isActive():
                t.start()
            return

        # ② 실시간 아님 → 캐시 데이터로 강제 redraw
        self._redraw_intraday_cache()

    # ── Tick Chart (변경 없음) ────────────────────────────────
    def _fetch_tick_chart(self):
        if not getattr(self, 'mw', None) or not self.mw.connected:
            if hasattr(self, 'lbl_tick_status'):
                self.lbl_tick_status.setText("❌ TWS/Gateway 연결 필요")
            return
        sym      = self._get_chart_sym()
        num_ticks = getattr(self.spin_tick_count, 'value', lambda: 20)()

        def _on_done(ticks):
            n = len(ticks)
            self.lbl_tick_status.setText(f"✅ {sym}  {n}틱 수신")
            if not hasattr(self, '_pw_tick'):
                return
            try:
                import pyqtgraph as pg
                xs = list(range(n))
                ys = [t["p"] for t in ticks]
                sz = [max(1, min(int(t["s"]) // 10, 20)) for t in ticks]
                self._tick_line.setData(xs, ys)
                self._tick_dots.setData(x=xs, y=ys, size=sz,
                    brush=[pg.mkBrush('#00e676') for _ in ticks])
                if ys:
                    pad = (max(ys) - min(ys)) * 0.1 or min(ys) * 0.001
                    self._pw_tick.setYRange(min(ys) - pad, max(ys) + pad, padding=0)
            except Exception as e:
                self.lbl_tick_status.setText(f"⚠ 틱 차트 오류: {e}")

        self._ibkr_tick_chart(sym, num_ticks, 9802,
                              _on_done, self.lbl_tick_status)