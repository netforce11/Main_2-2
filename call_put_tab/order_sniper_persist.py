"""
order_sniper_persist.py — 스나이퍼 JSON 저장·복원 로직
════════════════════════════════════════════════════════
포함 내용:
  - OrderSniperPersistMixin
      _sniper_save()   조건 JSON 저장 (절대경로 + 날짜 파일명)
      _sniper_load()   가장 최근 날짜 JSON 파일에서 복원
════════════════════════════════════════════════════════
"""


class OrderSniperPersistMixin:
    """스나이퍼 조건 JSON 저장·복원 로직."""

    def _sniper_save(self):
        """스나이퍼 조건 JSON 저장 (절대경로 + 날짜 포함 파일명)."""
        import json
        from pathlib import Path
        from datetime import datetime
        _SNIPER_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/sniper")
        save_path   = _SNIPER_DIR / f"sniper_conditions_{datetime.now().strftime('%Y%m%d')}.json"
        data = [
            {
                "sym": sn["sym"], "strike": sn["strike"],
                "right": sn["right"], "expiry": sn["expiry"],
                "target_price": sn["target_price"], "cmp_op": sn["cmp_op"],
                "time_kst": sn["time_kst"], "time_margin": sn["time_margin"],
                "qty": sn["qty"], "action": sn["action"],
                "order_type": sn["order_type"], "order_price": sn["order_price"],
            }
            for sn in self._snipers.values()
        ]
        try:
            _SNIPER_DIR.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"[스나이퍼] {len(data)}개 저장 → {save_path}")
            self.snp_status.setText(f"💾 {len(data)}개 저장 완료")
            self.snp_status.setStyleSheet(
                "color:#00cfff;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
        except Exception as e:
            self._log(f"[스나이퍼] 저장 오류: {e}")

    def _sniper_load(self):
        """가장 최근 날짜 JSON 파일에서 스나이퍼 조건 복원."""
        import json
        from pathlib import Path
        _SNIPER_DIR = Path("/home/netforce/trading_terminal/Main2_1/data/sniper")
        candidates  = sorted(
            _SNIPER_DIR.glob("sniper_conditions_????????.json"), reverse=True)
        if not candidates:
            self._log("[스나이퍼] 복원할 파일 없음"); return
        try:
            data = json.loads(candidates[0].read_text(encoding="utf-8"))
        except Exception as e:
            self._log(f"[스나이퍼] 복원 오류: {e}"); return
        for item in data:
            self.snp_strike.setText(str(int(item.get("strike", 0))))
            self.snp_right.setCurrentIndex(0 if item.get("right", "C") == "C" else 1)
            self.snp_expiry.setText(item.get("expiry", ""))
            self.snp_price.setText(str(item.get("target_price", "")))
            self.snp_cmp.setCurrentIndex(0 if item.get("cmp_op", "<=") == "<=" else 1)
            self.snp_time.setText(item.get("time_kst", ""))
            self.snp_margin.setValue(item.get("time_margin", 1))
            self.snp_action.setCurrentText(item.get("action", "BUY"))
            self.snp_otype.setCurrentText(item.get("order_type", "LMT"))
            self.snp_oprice.setText(
                str(item.get("order_price", "")) if item.get("order_price") else "")
            self.snp_qty.setValue(item.get("qty", 1))
            self._sniper_add()
        self._log(f"[스나이퍼] {len(data)}개 조건 복원 완료")
        if data:
            self.snp_status.setText(f"📂 {len(data)}개 복원됨")
            self.snp_status.setStyleSheet(
                "color:#00cfff;font-size:11px;border:1px solid #333;"
                "border-radius:3px;padding:2px;")
