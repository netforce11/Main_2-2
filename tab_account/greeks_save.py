"""
greeks_save.py — Greeks 스냅샷 저장 로직
════════════════════════════════════════════════════════
포함 내용:
  - GreeksSaveMixin
      _snapshot()     현재 테이블 데이터 → list[dict]
      _autosave()     15초 자동 CSV 저장
      _manual_save()  즉시 저장 버튼 핸들러
════════════════════════════════════════════════════════
"""

import csv as _csv
from datetime import date

from PyQt5.QtWidgets import QMessageBox

from core import SAVE_DIR, ts

GREEKS_CSV = "greeks_{date}_{sym}.csv"


class GreeksSaveMixin:
    """Greeks 스냅샷 저장 로직. GreeksGrid에 mixin된다."""

    def _snapshot(self):
        rows   = []
        ts_now = ts()
        for r in range(self.tbl.rowCount()):
            def g(c):
                return self.tbl.item(r, c).text() if self.tbl.item(r, c) else ""
            rows.append({
                "time": ts_now, "strike": g(0),
                "c_price": g(1), "c_delta": g(2),
                "c_gamma": g(3), "c_dgamma": g(4),
                "p_price": g(5), "p_delta": g(6),
                "p_gamma": g(7), "p_dgamma": g(8),
                "iv_c": g(9), "iv_p": g(10),
            })
        return rows

    def _autosave(self):
        if not self.strikes: return
        snap = self._snapshot()
        if not snap: return
        sym       = self.edit_sym.text().strip().upper()
        fname     = GREEKS_CSV.format(date=date.today().isoformat(), sym=sym)
        path      = SAVE_DIR / fname
        write_hdr = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=snap[0].keys())
            if write_hdr: w.writeheader()
            w.writerows(snap)
        self.lbl_save.setText(f"자동저장: {ts()}")

    def _manual_save(self):
        self._autosave()
        QMessageBox.information(self, "저장", "Greeks 스냅샷 저장 완료")
