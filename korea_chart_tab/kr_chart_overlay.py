"""
kr_chart_overlay.py — 오버레이 종목 라인차트 (우측 Y축)
────────────────────────────────────────────────────────
기능:
  - 관심종목 옆 체크박스 ON → 해당 종목 1분봉을 p1에 라인차트로 오버레이
  - 메인 종목: 캔들차트 (좌측 Y축)
  - 오버레이 종목: 라인차트 (우측 별도 Y축, 하늘색 계열)
  - 최대 2개 오버레이 동시 표시
  - 체크 OFF → 해당 라인 + Y축 제거

색상:
  오버레이 1번: #00BFFF (딥스카이블루)
  오버레이 2번: #87CEEB (스카이블루)

사용:
  on_overlay_chk(self, code, name, checked) — 체크박스 상태 변경 시 호출
  redraw_overlays(self)                     — 차트 재렌더링 후 오버레이 복원
  clear_all_overlays(self)                  — 전체 오버레이 제거
"""

import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from datetime import date

try:
    import pyqtgraph as pg
    import numpy as np
    PG = True
except ImportError:
    PG = False

try:
    import pandas as pd; PANDAS = True
except ImportError:
    PANDAS = False; pd = None

# 오버레이 색상 (하늘색 계열 2종)
OVERLAY_COLORS = ["#00BFFF", "#87CEEB"]


# ── 오버레이 초기화 ───────────────────────────────────────────

def init_overlays(self):
    """KoreaChartGrid.__init__() 마지막에 호출. 오버레이 상태 초기화."""
    self._overlays = {}   # {code: {"name": str, "vb": ViewBox, "line": PlotDataItem, "slot": int}}


# ── 체크박스 토글 핸들러 ──────────────────────────────────────

def on_overlay_chk(self, code, name, checked):
    """관심종목 체크박스 상태 변경 시 호출."""
    if not PG:
        return

    if checked:
        # 이미 오버레이 중인 종목이면 무시
        if code in self._overlays:
            return

        # 최대 2개 제한
        if len(self._overlays) >= 2:
            # 체크박스를 다시 해제
            _uncheck_by_code(self, code)
            self.lbl_hline_info.setText("⚠ 오버레이는 최대 2개까지 가능합니다.")
            return

        _add_overlay(self, code, name)
    else:
        _remove_overlay(self, code)


def _uncheck_by_code(self, code):
    """해당 종목코드의 오버레이 체크박스를 해제."""
    if not hasattr(self, '_overlay_chks'):
        return
    chk = self._overlay_chks.get(code)
    if chk:
        chk.blockSignals(True)
        chk.setChecked(False)
        chk.blockSignals(False)


# ── 오버레이 추가 ─────────────────────────────────────────────

def _add_overlay(self, code, name):
    """데이터 로드 후 라인차트 + 우측 Y축 추가."""
    records = _load_overlay_records(self, code)
    if not records:
        self.lbl_hline_info.setText(
            f"⚠ {name}({code}) 데이터 없음 — 먼저 조회하세요.")
        _uncheck_by_code(self, code)
        return

    # 슬롯 번호 결정 (0 또는 1)
    used_slots = {v["slot"] for v in self._overlays.values()}
    slot = next((s for s in [0, 1] if s not in used_slots), 0)
    color = OVERLAY_COLORS[slot]

    # x축 매핑: 메인 차트의 _x_time_map 기준으로 x 인덱스 맞추기
    x_vals, y_vals = _align_to_main(self, records)
    if x_vals is None or len(x_vals) == 0:
        self.lbl_hline_info.setText(
            f"⚠ {name}({code}) 날짜가 메인 차트와 맞지 않습니다.")
        _uncheck_by_code(self, code)
        return

    # 우측 Y축용 ViewBox 생성
    vb = pg.ViewBox()
    self.p1.scene().addItem(vb)
    vb.setXLink(self.p1)

    # 우측 축 추가
    ax = pg.AxisItem("right")
    ax.setLabel(f"{name}", color=color)
    ax.setPen(pg.mkPen(color, width=1))
    ax.setTextPen(pg.mkPen(color))
    self.gfx.ci.addItem(ax, row=0, col=1)
    ax.linkToView(vb)

    # 라인차트
    pen = pg.mkPen(color=color, width=1.5)
    line = pg.PlotDataItem(x=x_vals, y=y_vals, pen=pen, antialias=True)
    vb.addItem(line)

    # 뷰 크기 동기화
    def _sync_vb():
        vb.setGeometry(self.p1.getViewBox().sceneBoundingRect())
    self.p1.getViewBox().sigResized.connect(_sync_vb)
    _sync_vb()

    self._overlays[code] = {
        "name":  name,
        "slot":  slot,
        "color": color,
        "vb":    vb,
        "ax":    ax,
        "line":  line,
        "records": records,
    }
    self.lbl_hline_info.setText(
        f"오버레이 [{slot+1}] {name}({code}) 추가됨  "
        f"(총 {len(self._overlays)}개)")


# ── 오버레이 제거 ─────────────────────────────────────────────

def _remove_overlay(self, code):
    if code not in self._overlays:
        return
    info = self._overlays.pop(code)
    try:
        info["vb"].removeItem(info["line"])
        self.p1.scene().removeItem(info["vb"])
        self.gfx.ci.removeItem(info["ax"])
    except Exception as ex:
        print(f"[Overlay] 제거 오류: {ex}")
    self.lbl_hline_info.setText(
        f"오버레이 [{info['slot']+1}] {info['name']}({code}) 제거됨")


def clear_all_overlays(self):
    """전체 오버레이 제거 (차트 재렌더링 전 호출)."""
    for code in list(self._overlays.keys()):
        _remove_overlay(self, code)


# ── 재렌더링 후 복원 ──────────────────────────────────────────

def redraw_overlays(self):
    """update_display() 후 오버레이 복원."""
    if not hasattr(self, '_overlays') or not self._overlays:
        return
    # 기존 뷰박스/축/라인 제거 후 재추가
    snapshot = {code: info.copy() for code, info in self._overlays.items()}
    for code in list(self._overlays.keys()):
        try:
            info = self._overlays[code]
            info["vb"].removeItem(info["line"])
            self.p1.scene().removeItem(info["vb"])
            self.gfx.ci.removeItem(info["ax"])
        except Exception:
            pass
    self._overlays.clear()

    for code, info in snapshot.items():
        _add_overlay(self, code, info["name"])


# ── 데이터 정렬 ───────────────────────────────────────────────

def _align_to_main(self, records):
    """
    오버레이 records의 각 봉을 메인 차트의 _x_time_map 기준으로
    x 인덱스에 맞춰 정렬.
    시간 문자열(MM/DD HH:MM) 기준으로 매핑.
    """
    if not hasattr(self, '_x_time_map') or not self._x_time_map:
        return None, None
    if not PANDAS:
        return None, None

    # 메인 차트 시간 → x 인덱스 역맵
    time_to_x = {v: k for k, v in self._x_time_map.items()}

    try:
        df = pd.DataFrame(records)
        df["kst"] = (pd.to_datetime(df["t"], unit="ms")
                     .dt.tz_localize("UTC")
                     .dt.tz_convert("Asia/Seoul"))
        df["t_str"] = df["kst"].dt.strftime("%m/%d %H:%M")
        df["x"] = df["t_str"].map(time_to_x)
        df = df.dropna(subset=["x"])
        if df.empty:
            return None, None
        df = df.sort_values("x")
        return df["x"].astype(float).tolist(), df["c"].astype(float).tolist()
    except Exception as ex:
        print(f"[Overlay] 정렬 오류: {ex}")
        return None, None


# ── 데이터 로드 ───────────────────────────────────────────────

def _load_overlay_records(self, code):
    """
    오버레이 종목의 분봉 데이터 로드.
    메인 차트의 selected_date 기준으로 CSV에서 로드.
    연속보기(_multi_day_active) 상태도 반영.
    """
    if not PANDAS:
        return []

    tgt = getattr(self, 'selected_date', None) or date.today()

    from kr_chart_kiwoom import _csv_path, KR_DATA_ROOT
    import pandas as _pd

    if getattr(self, '_multi_day_active', False):
        # 연속보기: 메인 df_raw 의 날짜 범위와 동일하게
        days = getattr(self, '_multi_day_count', 1)
        from datetime import timedelta
        records = []
        d = tgt
        collected = 0
        attempts  = 0
        while collected < days and attempts < days + 14:
            attempts += 1
            if d.weekday() < 5:
                fp = _csv_path(code, d)
                if fp.exists():
                    try:
                        full = _pd.read_csv(str(fp))
                        full["_d"] = (_pd.to_datetime(full["t"], unit="ms")
                                      .dt.tz_localize("UTC")
                                      .dt.tz_convert("Asia/Seoul").dt.date)
                        day_recs = full[full["_d"] == d].drop(columns=["_d"])
                        if not day_recs.empty:
                            records = day_recs.to_dict("records") + records
                            collected += 1
                    except Exception:
                        pass
            d -= timedelta(days=1)
        return records
    else:
        fp = _csv_path(code, tgt)
        if not fp.exists():
            return []
        try:
            full = _pd.read_csv(str(fp))
            full["_d"] = (_pd.to_datetime(full["t"], unit="ms")
                          .dt.tz_localize("UTC")
                          .dt.tz_convert("Asia/Seoul").dt.date)
            res = full[full["_d"] == tgt].drop(columns=["_d"])
            return res.to_dict("records") if not res.empty else []
        except Exception as ex:
            print(f"[Overlay] 데이터 로드 실패: {ex}")
            return []
