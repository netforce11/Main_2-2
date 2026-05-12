"""
chart_time_utils.py — ET/KST 변환 + 줌 범위 라벨 유틸
[분리] chart_data.py 에서 분리 (et_to_kst_str, fmt_time, on_range_changed)
"""
from datetime import date, timedelta


def et_to_kst_str(self, et_dt) -> str:
    """ET datetime → KST 문자열 변환. zoneinfo 기반으로 DST 자동 처리."""
    try:
        try:
            from zoneinfo import ZoneInfo
            _ET  = ZoneInfo("America/New_York")
            _KST = ZoneInfo("Asia/Seoul")
            et_aware = et_dt.replace(tzinfo=_ET) if et_dt.tzinfo is None else et_dt
            kst = et_aware.astimezone(_KST)
            return kst.strftime('%m/%d %H:%M')
        except ImportError:
            d = et_dt.date() if hasattr(et_dt, 'date') else et_dt
            mar1 = date(d.year, 3, 1)
            sun_count = 0; dst_start = None
            for off in range(31):
                dd = mar1 + timedelta(days=off)
                if dd.weekday() == 6:
                    sun_count += 1
                    if sun_count == 2: dst_start = dd; break
            nov1 = date(d.year, 11, 1); dst_end = None
            for off in range(7):
                dd = nov1 + timedelta(days=off)
                if dd.weekday() == 6: dst_end = dd; break
            is_dst = (dst_start is not None and dst_end is not None
                      and dst_start <= d < dst_end)
            kst = et_dt + timedelta(hours=13 if is_dst else 14)
            return kst.strftime('%m/%d %H:%M')
    except Exception:
        return "??:??"


def fmt_time(self, et_dt) -> str:
    use_kst = hasattr(self, 'kst_chk') and self.kst_chk.isChecked()
    return et_to_kst_str(self, et_dt) if use_kst else et_dt.strftime('%m/%d %H:%M')


def on_range_changed(self, vb, ranges):
    if not hasattr(self, 'lbl_zoom_time'): return
    if not hasattr(self, '_x_time_map') or not self._x_time_map: return
    try:
        xmin, xmax = ranges[0]
        keys = sorted(self._x_time_map.keys())
        vis  = [k for k in keys if xmin <= k <= xmax]
        if vis:
            t_start = self._x_time_map.get(vis[0], "")
            t_end   = self._x_time_map.get(vis[-1], "")
            self.lbl_zoom_time.setText(f"📊 {t_start} ~ {t_end}  ({len(vis)}봉)")
    except Exception:
        pass
