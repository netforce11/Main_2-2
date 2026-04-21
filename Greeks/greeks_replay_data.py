"""
greeks_replay_data.py — 리플레이 데이터 로드 · 프레임 구성 · 렌더
════════════════════════════════════════════════════════════════
ReplayPanel 에서 분리된 데이터 처리 모듈.

- load_replay_data(panel, day, t_fr, t_to, expiry_raw) → bool
    DB 머지 로드 후 panel 상태 갱신. 실패 시 False 반환.

- render_frame(panel, idx)
    idx 번째 타임스탬프 데이터를 현재 뷰 모드(_cur_view)에 맞게 렌더.
"""

from datetime import datetime, timedelta
from greeks_db import load_merged_snapshots
try:
    from call_put_tab.chain_saver.buffer import et_to_kst
except ImportError:
    def et_to_kst(s): return s

from greeks_render_replay import (
    init_row_replay, render_rows_replay, apply_view_mode,
)
from greeks_replay_ctrl import VIEW_MODES


# ── 공개 API ──────────────────────────────────────────────────

def load_replay_data(panel, day: str, t_fr: str, t_to: str,
                     expiry_raw: str, expiry_label: str) -> bool:
    """
    DB에서 데이터 로드 후 panel._frames / _ts_list / _strikes / _atm 갱신.
    성공 시 True, 실패 시 lbl_ts 에 오류 메시지 출력 후 False 반환.
    """
    try:
        from_ts, to_ts, range_str = _parse_range(day, t_fr, t_to)
    except Exception as e:
        panel.lbl_ts.setText(f"시간 형식 오류: {e}")
        return False

    panel.lbl_ts.setText(
        f"로딩 중... [{day} {range_str}] 만기:{expiry_label}")

    rows = load_merged_snapshots(day, from_ts, to_ts, expiry=expiry_raw)
    if not rows:
        panel.lbl_ts.setText(f"데이터 없음  [{day} {range_str}]")
        return False

    _build_frames(panel, rows)

    # 테이블 행 초기화
    panel.tbl.setRowCount(len(panel._strikes))
    for i, st in enumerate(panel._strikes):
        init_row_replay(panel.tbl, i, st, panel._atm)

    panel.slider.setMaximum(max(0, len(panel._ts_list) - 1))
    panel.slider.setValue(0)
    panel._cur_idx = 0
    panel._prev    = {}

    panel.lbl_ts.setText(
        f"로드 완료: {len(panel._ts_list)}개 시점 / "
        f"{len(panel._strikes)}개 행사가 / 총 {len(rows)}행  "
        f"[{day} {range_str}] 만기:{expiry_label}"
    )
    return True


def render_frame(panel, idx: int):
    """idx 번째 프레임을 현재 뷰 모드(_cur_view)로 렌더."""
    if not panel._ts_list or idx >= len(panel._ts_list):
        return

    ts     = panel._ts_list[idx]
    kst    = et_to_kst(ts)
    panel.lbl_ts.setText(f"{kst} (KST)  /  {ts} (ET)")

    cell_d = panel._frames.get(ts, {})
    mode   = getattr(panel, "_cur_view", "greeks")
    cols   = VIEW_MODES[mode]["cols"]

    apply_view_mode(panel.tbl, mode)   # 뷰 모드별 컬럼 show/hide
    render_rows_replay(
        panel.tbl,
        panel._strikes,
        panel._atm,
        cell_d,
        panel._prev,
        view_cols=cols,
    )


# ── 내부 헬퍼 ─────────────────────────────────────────────────

def _parse_range(day: str, t_fr: str, t_to: str):
    """
    day(YYYYMMDD), t_fr/t_to(HH:MM) → (from_ts, to_ts, range_str).
    비어있으면 당일 전체(00:00 ~ 23:59) 자동 설정. ET 기준 저장.
    """
    base_dt  = datetime.strptime(day, "%Y%m%d")
    next_dt  = base_dt + timedelta(days=1)
    date_str = base_dt.strftime("%Y-%m-%d")
    next_str = next_dt.strftime("%Y-%m-%d")

    def _fmt(t: str, end: bool = False) -> str:
        parts = t.split(":")
        hh    = int(parts[0])
        mm    = parts[1].zfill(2) if len(parts) > 1 else "00"
        ss    = parts[2].zfill(2) if len(parts) > 2 else ("59" if end else "00")
        return f"{date_str} {hh:02d}:{mm}:{ss}"

    if t_fr or t_to:
        from_ts   = _fmt(t_fr, end=False)
        to_ts     = _fmt(t_to, end=True)
        range_str = f"{t_fr}~{t_to}"
    else:
        from_ts   = f"{date_str} 00:00:00"
        to_ts     = f"{date_str} 23:59:59"
        range_str = "전체"

    return from_ts, to_ts, range_str


def _build_frames(panel, rows: list):
    """rows → panel._frames / _ts_list / _strikes / _atm 구성."""
    ts_set      = dict.fromkeys(r["ts"] for r in rows)
    panel._ts_list = list(ts_set.keys())

    strikes_set    = sorted({r["strike"] for r in rows})
    panel._strikes = strikes_set

    und = next((r["und_price"] for r in rows if r.get("und_price")), 0)
    panel._atm = (
        min(strikes_set, key=lambda s: abs(s - und)) if und and strikes_set else 0.0
    )

    frames: dict = {}
    for r in rows:
        ts   = r["ts"]
        st   = r["strike"]
        side = r["side"]
        row  = strikes_set.index(st)

        # 등락률: mid 기준 전 프레임 대비 % (첫 프레임은 0)
        prev_mid = panel._prev.get((row, side, "mid"), None)
        mid_val  = r.get("mid")
        if prev_mid and mid_val:
            chg_pct = (mid_val - prev_mid) / prev_mid * 100
        else:
            chg_pct = None

        frames.setdefault(ts, {})[(row, side)] = {
            # Greeks
            "delta":   r.get("delta")  or 0.0,
            "gamma":   r.get("gamma")  or 0.0,
            "iv":      r.get("iv")     or 0.0,
            "vanna":   r.get("vanna")  or 0.0,
            # 프리미엄
            "bid":     r.get("bid"),
            "ask":     r.get("ask"),
            "mid":     mid_val,
            "last":    r.get("last"),
            # 이론가
            "theo":    r.get("theo"),
            "mispct":  r.get("mispct"),
            "chg_pct": chg_pct,
        }

    panel._frames = frames