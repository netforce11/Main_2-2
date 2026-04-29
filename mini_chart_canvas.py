# -*- coding: utf-8 -*-
"""
mini_chart_canvas.py — MiniChartCanvas (matplotlib 기반 캔들/라인 차트)
spxw_core.py에서 분리 [≤300줄 규칙 준수]

추가 기능:
  - add_vline(hhmm)        : 세로선 추가 (X축 HH:MM 인덱스 매핑)
  - set_vline_visible(hhmm, bool) : 세로선 표시/숨김
  - clear_vlines()         : 모든 세로선 삭제
  - plot_candles(..., vol_highlight=N) : N주 이상 거래량 봉 굵게 강조
"""
from __future__ import annotations

from typing import List, Optional, Dict

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches
import matplotlib.lines as mlines


class MiniChartCanvas(FigureCanvas):
    """1분봉/1초봉 캔들+라인 차트 (vline + vol_highlight 지원)"""

    def __init__(self, parent=None, width=5, height=3, dpi=100):
        self._fig = Figure(figsize=(width, height), dpi=dpi)
        self._fig.patch.set_facecolor("#ffffff")
        self._ax = self._fig.add_subplot(111)
        self._ax_vol = self._ax.twinx()
        # 거래량 축(ax_vol)을 왼쪽으로 이동
        self._ax_vol.yaxis.set_label_position("left")
        self._ax_vol.yaxis.tick_left()
        super().__init__(self._fig)
        self.setParent(parent)
        self._fig.subplots_adjust(left=0.02, right=0.88, top=0.92, bottom=0.14)

        # 가격 Y축을 우측으로 이동
        self._ax.yaxis.set_label_position("right")
        self._ax.yaxis.tick_right()

        # vline state: {hhmm: {"line": Line2D, "visible": bool}}
        self._vline_map: Dict[str, dict] = {}
        # current time labels for X-axis mapping
        self._current_times: List[str] = []

    def _reset(self):
        self._ax.cla()
        self._ax_vol.cla()
        self._ax.set_facecolor("#fafafa")
        self._ax_vol.set_facecolor("#fafafa")
        # 가격 Y축 우측 유지 (cla() 후 초기화되므로 재설정)
        self._ax.yaxis.set_label_position("right")
        self._ax.yaxis.tick_right()
        # 거래량 Y축 좌측 유지
        self._ax_vol.yaxis.set_label_position("left")
        self._ax_vol.yaxis.tick_left()
        # vline objects are gone after cla() — clear refs but keep keys/visibility
        for hhmm, v in self._vline_map.items():
            v["line"] = None

    def _redraw_vlines(self):
        """Re-draw all registered vlines after chart reset."""
        for hhmm, v in self._vline_map.items():
            x = self._hhmm_to_x(hhmm)
            if x is None:
                continue
            line = self._ax.axvline(
                x=x, color="#ffd700", linewidth=1.2,
                linestyle="--", alpha=0.85, zorder=10
            )
            self._ax.text(
                x, self._ax.get_ylim()[1], hhmm,
                color="#ffd700", fontsize=7, ha="center", va="bottom",
                zorder=11, clip_on=True
            )
            line.set_visible(v.get("visible", True))
            v["line"] = line

    def _hhmm_to_x(self, hhmm: str) -> Optional[float]:
        """Convert HH:MM string to X-axis integer index."""
        if not self._current_times:
            return None
        # Exact match first
        if hhmm in self._current_times:
            return float(self._current_times.index(hhmm))
        # Nearest match (within ±2 steps)
        try:
            h, m = int(hhmm[:2]), int(hhmm[3:5])
            target_min = h * 60 + m
            best_i, best_d = None, 999
            for i, t in enumerate(self._current_times):
                try:
                    th, tm = int(t[:2]), int(t[3:5])
                    d = abs(th * 60 + tm - target_min)
                    if d < best_d:
                        best_d, best_i = d, i
                except Exception:
                    continue
            if best_i is not None and best_d <= 2:
                return float(best_i)
        except Exception:
            pass
        return None

    # ── Public vline API ──────────────────────────────────────

    def add_vline(self, hhmm: str):
        """Add a vertical line at HH:MM. If already exists, just redraw."""
        if hhmm not in self._vline_map:
            self._vline_map[hhmm] = {"line": None, "visible": True}
        x = self._hhmm_to_x(hhmm)
        if x is None:
            return  # chart not loaded yet — will be drawn on next plot_candles
        line = self._ax.axvline(
            x=x, color="#ffd700", linewidth=1.2,
            linestyle="--", alpha=0.85, zorder=10
        )
        ylim = self._ax.get_ylim()
        self._ax.text(
            x, ylim[1], hhmm,
            color="#ffd700", fontsize=7, ha="center", va="bottom",
            zorder=11, clip_on=True
        )
        visible = self._vline_map[hhmm].get("visible", True)
        line.set_visible(visible)
        self._vline_map[hhmm]["line"] = line
        try:
            self._fig.canvas.draw_idle()
        except Exception:
            pass

    def set_vline_visible(self, hhmm: str, visible: bool):
        """Show or hide an existing vline."""
        if hhmm not in self._vline_map:
            return
        self._vline_map[hhmm]["visible"] = visible
        line = self._vline_map[hhmm].get("line")
        if line is not None:
            line.set_visible(visible)
            try:
                self._fig.canvas.draw_idle()
            except Exception:
                pass

    def clear_vlines(self):
        """Remove all vlines from chart and internal registry."""
        for v in self._vline_map.values():
            line = v.get("line")
            if line is not None:
                try:
                    line.remove()
                except Exception:
                    pass
        self._vline_map.clear()
        try:
            self._fig.canvas.draw_idle()
        except Exception:
            pass

    # ── Chart renderers ───────────────────────────────────────

    def plot_line(self, times: List[str], closes: List[float],
                  volumes: Optional[List[float]] = None):
        self._reset()
        self._current_times = list(times)
        if not times:
            self._fig.canvas.draw_idle()
            return
        xs = list(range(len(times)))
        self._ax.plot(xs, closes, color="#1565c0", linewidth=1.4, zorder=3)
        step = max(1, len(xs) // 10)
        self._ax.set_xticks(xs[::step])
        self._ax.set_xticklabels([times[i] for i in xs[::step]],
                                  rotation=30, fontsize=7)
        self._ax.grid(True, alpha=0.25, linestyle="--")
        if volumes:
            self._ax_vol.bar(xs, volumes, color="#90caf9", alpha=0.35, zorder=1)
            self._ax_vol.set_ylabel("Vol", fontsize=7, color="#90caf9")
        self._ax_vol.yaxis.set_tick_params(labelsize=6)
        self._ax.yaxis.set_tick_params(labelsize=7)
        self._ax.autoscale_view()
        self._redraw_vlines()
        try:
            self._fig.canvas.draw_idle()
        except Exception:
            pass

    def plot_candles(self, times: List[str], opens: List[float],
                     highs: List[float], lows: List[float], closes: List[float],
                     volumes: Optional[List[float]] = None,
                     vol_highlight: Optional[float] = None):
        """
        Render candlestick chart.
        vol_highlight: if set, candles with volume >= vol_highlight are drawn
                       with thicker wick (lw=2.5) and brighter border.
        """
        self._reset()
        self._current_times = list(times)
        if not times:
            self._fig.canvas.draw_idle()
            return
        xs = list(range(len(times)))
        vols = volumes or [0] * len(times)

        for i, (o, h, l, c, v) in enumerate(
                zip(opens, highs, lows, closes, vols)):
            color = "#e53935" if c >= o else "#1e88e5"
            is_big = (vol_highlight is not None and v >= vol_highlight)
            is_last = (i == len(times) - 1)
            # 마지막 봉: 더 넓고 굵게
            lw_wick = 3.0 if is_last else (2.5 if is_big else 0.8)
            lw_body = 2.5 if is_last else (1.5 if is_big else 0.5)
            body_half = 0.45 if is_last else 0.3
            # Wick
            self._ax.plot([i, i], [l, h], color=color,
                          linewidth=lw_wick, zorder=2)
            # Body
            body_h = max(abs(c - o), 1e-9)
            edge_color = "#ffffff" if (is_last or is_big) else color
            rect = matplotlib.patches.Rectangle(
                (i - body_half, min(o, c)), body_half * 2, body_h,
                facecolor=color, edgecolor=edge_color,
                linewidth=lw_body, zorder=3
            )
            self._ax.add_patch(rect)

        step = max(1, len(xs) // 10)
        self._ax.set_xticks(xs[::step])
        self._ax.set_xticklabels([times[i] for i in xs[::step]],
                                  rotation=30, fontsize=7)
        self._ax.set_xlim(-0.5, len(xs) - 0.5)
        self._ax.grid(True, alpha=0.25, linestyle="--")

        if volumes:
            bar_colors = ["#ef9a9a" if closes[i] >= opens[i] else "#90caf9"
                          for i in range(len(volumes))]
            # Big-volume bars drawn with full opacity
            alpha_list = [0.75 if (vol_highlight and volumes[i] >= vol_highlight)
                          else 0.35 for i in range(len(volumes))]
            for xi, bv, bc, ba in zip(xs, volumes, bar_colors, alpha_list):
                self._ax_vol.bar(xi, bv, color=bc, alpha=ba, zorder=1)
            self._ax_vol.set_ylabel("Vol", fontsize=7)

        self._ax_vol.yaxis.set_tick_params(labelsize=6)
        self._ax.yaxis.set_tick_params(labelsize=7)
        self._ax.autoscale_view()
        self._redraw_vlines()
        try:
            self._fig.canvas.draw_idle()
        except Exception:
            pass