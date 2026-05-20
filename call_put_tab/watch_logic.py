"""
watch_logic.py — 감시 규칙 등록·삭제·평가·체크 로직  v6.5
════════════════════════════════════════════════════════
수정 대상: 감시 조건 평가 방식, 알람 트리거 동작
포함 메서드:
  _add_watch_rule()          감시 규칙 등록
  _del_watch_rule()          단건 삭제
  _clear_watch_rules()       전체 삭제
  _eval_op()                 연산자 평가 (<, <=, >, >=)
  _check_watch_rules()       2초 타이머 체크
  _save_watch_rules()        규칙 + 활성 상태 JSON 저장  ★ v6.5
  _load_watch_rules_from_file() 앱 시작 시 자동 복원    ★ v6.5
  _load_watch_log()          로그 파일 불러오기
  _open_watch_log_folder()   저장 폴더 열기
════════════════════════════════════════════════════════
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtWidgets import QMessageBox, QFileDialog

from core import tbl_set, SAVE_DIR

# 저장 파일 경로
_WATCH_RULES_FILE = Path(SAVE_DIR) / "watch_rules.json"


class WatchLogicMixin:
    """감시 규칙 등록·삭제·평가 로직. CallPutGrid에 mixin된다."""

    # ─────────────────────────────────────────────────────
    # 감시 규칙 등록
    # ─────────────────────────────────────────────────────
    def _add_watch_rule(self):
        side   = self.watch_side.text().strip()
        strike = self.watch_strike.text().strip()
        if not side or not strike:
            QMessageBox.warning(self, "입력 오류",
                "콜-풋 테이블에서 행을 먼저 클릭하세요."); return

        def _flt(chk, ed):
            if not chk.isChecked(): return None
            try: return float(ed.text().strip())
            except: return None

        cond = {
            "price":    _flt(self.wc_price_chk, self.wc_price_val),
            "price_op": self.wc_price_op.currentText(),
            "delta":    _flt(self.wc_delta_chk, self.wc_delta_val),
            "delta_op": self.wc_delta_op.currentText(),
            "theta":    _flt(self.wc_theta_chk, self.wc_theta_val),
            "theta_op": self.wc_theta_op.currentText(),
            "gamma":    _flt(self.wc_gamma_chk, self.wc_gamma_val),
            "gamma_op": self.wc_gamma_op.currentText(),
        }
        and_c = {
            "time":     self.wa_time_val.text().strip()
                        if self.wa_time_chk.isChecked() else None,
            "time_op":  self.wa_time_op.currentText(),
            "delta":    _flt(self.wa_delta_chk, self.wa_delta_val),
            "delta_op": self.wa_delta_op.currentText(),
            "gamma":    _flt(self.wa_gamma_chk, self.wa_gamma_val),
            "gamma_op": self.wa_gamma_op.currentText(),
            "theta":    _flt(self.wa_theta_chk, self.wa_theta_val),
            "theta_op": self.wa_theta_op.currentText(),
        }

        if all(cond.get(k) is None for k in ("price","delta","theta","gamma")):
            QMessageBox.warning(self, "입력 오류",
                "감시 조건(가격/Delta/Theta/Gamma)을 하나 이상 체크하고 값을 입력하세요.")
            return

        has_and = any(and_c.get(k) is not None
                      for k in ("time","delta","gamma","theta"))
        rule = {"side": side, "strike": strike,
                "cond": cond, "and": and_c,
                "has_and": has_and, "fired": False}
        idx = len(self._watch_rules)
        self._watch_rules.append(rule)
        self._watch_prev[idx] = {
            "price": None, "delta": None, "theta": None, "gamma": None}

        r = self.tbl_watch_rules.rowCount()
        self.tbl_watch_rules.insertRow(r)
        tbl_set(self.tbl_watch_rules, r, 0, f"{side} {strike}", "#ffd700")

        cond_parts = []
        if cond["price"] is not None:
            cond_parts.append(f"P{cond['price_op']}{cond['price']:.2f}")
        if cond["delta"] is not None:
            cond_parts.append(f"Δ{cond['delta_op']}{cond['delta']:.3f}")
        if cond["theta"] is not None:
            cond_parts.append(f"θ{cond['theta_op']}{cond['theta']:.3f}")
        if cond["gamma"] is not None:
            cond_parts.append(f"γ{cond['gamma_op']}{cond['gamma']:.4f}")
        tbl_set(self.tbl_watch_rules, r, 1, " & ".join(cond_parts) or "―")

        and_parts = []
        if and_c["time"]:
            and_parts.append(f"T{and_c['time_op']}{and_c['time']}")
        if and_c["delta"] is not None:
            and_parts.append(f"Δ{and_c['delta_op']}{and_c['delta']:.3f}")
        if and_c["gamma"] is not None:
            and_parts.append(f"γ{and_c['gamma_op']}{and_c['gamma']:.4f}")
        if and_c["theta"] is not None:
            and_parts.append(f"θ{and_c['theta_op']}{and_c['theta']:.3f}")
        tbl_set(self.tbl_watch_rules, r, 2, " & ".join(and_parts) or "―", "#aaa")
        tbl_set(self.tbl_watch_rules, r, 3, "👁 감시 중", "#00ff88")

        self._watch_tabs.setCurrentIndex(2)   # 등록 목록 탭으로
        self._log(f"감시 등록: {side} {strike}  조건={cond_parts}")
        self._save_watch_rules()   # ★ v6.5 자동 저장

    def _del_watch_rule(self, row):
        if row < 0 or row >= len(self._watch_rules): return
        self._watch_rules.pop(row)
        self._watch_prev.pop(row, None)
        self._watch_prev = {
            (k if k < row else k-1): v
            for k, v in self._watch_prev.items() if k != row}
        self.tbl_watch_rules.removeRow(row)
        self._log(f"감시 삭제: row {row}")
        self._save_watch_rules()   # ★ v6.5 자동 저장

    def _clear_watch_rules(self):
        self._watch_rules.clear(); self._watch_prev.clear()
        self.tbl_watch_rules.setRowCount(0)
        self._log("감시 전체 삭제")
        self._save_watch_rules()   # ★ v6.5 자동 저장

    # ─────────────────────────────────────────────────────
    # 연산자 평가
    # ─────────────────────────────────────────────────────
    def _eval_op(self, actual, op: str, threshold) -> bool:
        if actual is None or threshold is None: return False
        if op in ("≤", "<="): return actual <= threshold
        elif op in ("≥", ">="): return actual >= threshold
        elif op == "<":  return actual <  threshold
        elif op == ">":  return actual >  threshold
        return False

    # ─────────────────────────────────────────────────────
    # 2초 감시 체크
    # ─────────────────────────────────────────────────────
    def _check_watch_rules(self):
        if not self._watch_rules: return
        from core import REQ_CALL, REQ_PUT
        now_et  = datetime.utcnow() - timedelta(
            hours=4 if self._is_dst() else 5)
        now_str = now_et.strftime("%H:%M")

        for idx, rule in enumerate(self._watch_rules):
            if rule["fired"]: continue
            side     = rule["side"]
            strike_f = float(rule["strike"])
            rid_base = REQ_CALL if side == "C" else REQ_PUT
            strikes  = self.call_strikes if side == "C" else self.put_strikes
            data_map = self.call_data    if side == "C" else self.put_data
            tbl      = self.tbl_call     if side == "C" else self.tbl_put

            rid = next((rid_base + i for i, st in enumerate(strikes)
                        if abs(st - strike_f) < 0.5), None)
            if rid is None: continue

            cur_price = data_map.get(rid, {}).get("last")
            row_idx   = rid - rid_base

            def _cell(r, c, _t=tbl):
                it = _t.item(r, c)
                if it:
                    try: return float(it.text().replace("―","").replace("+",""))
                    except: pass
                return None

            cur_delta = _cell(row_idx, 3)
            cur_theta = _cell(row_idx, 4)
            cur_gamma = _cell(row_idx, 5)
            cond  = rule["cond"]
            and_c = rule["and"]

            # 감시 조건 평가
            cond_ok = True
            if cond.get("price") is not None:
                if not self._eval_op(cur_price, cond["price_op"], cond["price"]):
                    cond_ok = False
            if cond.get("delta") is not None:
                val = abs(cur_delta) if cur_delta is not None else None
                thr = abs(cond["delta"])
                op_d = cond.get("delta_op", "<=")
                if op_d in ("<=","≤"):
                    if val is None or val > thr: cond_ok = False
                else:
                    if val is None or val < thr: cond_ok = False
            if cond.get("theta") is not None:
                if not self._eval_op(cur_theta, cond["theta_op"], cond["theta"]):
                    cond_ok = False
            if cond.get("gamma") is not None:
                if not self._eval_op(cur_gamma, cond["gamma_op"], cond["gamma"]):
                    cond_ok = False
            if not cond_ok: continue

            # AND 조건 평가
            has_and = rule.get("has_and", False)
            and_ok  = True
            if has_and:
                if and_c.get("time"):
                    try:
                        tp    = and_c["time"].split(":")
                        t_now = now_et.hour * 60 + now_et.minute
                        t_req = int(tp[0]) * 60 + int(tp[1])
                        op_t  = and_c.get("time_op", ">=")
                        if op_t in (">=","≥"):
                            if t_now < t_req: and_ok = False
                        else:
                            if t_now > t_req: and_ok = False
                    except: pass
                if and_c.get("delta") is not None:
                    val = abs(cur_delta) if cur_delta is not None else None
                    thr = abs(and_c["delta"])
                    op_d = and_c.get("delta_op","<=")
                    if op_d in ("<=","≤"):
                        if val is None or val > thr: and_ok = False
                    else:
                        if val is None or val < thr: and_ok = False
                if and_c.get("gamma") is not None:
                    if not self._eval_op(
                            cur_gamma, and_c.get("gamma_op",">="), and_c["gamma"]):
                        and_ok = False
                if and_c.get("theta") is not None:
                    if not self._eval_op(
                            cur_theta, and_c.get("theta_op","<="), and_c["theta"]):
                        and_ok = False
            if not and_ok: continue

            # 조건 성립
            rule["fired"] = True
            tbl_set(self.tbl_watch_rules, idx, 3, "🔥 조건 성립!", "#ff8800")

            p_str = f"{cur_price:.2f}" if cur_price is not None else "―"
            d_str = f"{cur_delta:.4f}" if cur_delta is not None else "―"
            t_str = f"{cur_theta:.4f}" if cur_theta is not None else "―"
            g_str = f"{cur_gamma:.6f}" if cur_gamma is not None else "―"
            mode  = "단일조건" if not has_and else "AND조건"
            msg   = (f"[{now_str} ET] 🔔 감시 조건 성립! ({mode}) "
                     f"{side} {rule['strike']}  "
                     f"P={p_str}  Δ={d_str}  θ={t_str}  γ={g_str}")

            self.watch_log_box.append(msg)
            try:
                self._watch_log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._watch_log_file, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception as e:
                self._log(f"감시 파일 기록 오류: {e}")

            self._log(msg)
            self._play_alert_sound()

            # ── 텔레그램 전송 ──────────────────────────────
            try:
                from telegram_bot.tg_client import TelegramClient
                TelegramClient.get().send("watch_alert", f"🔔 {msg}")
            except Exception:
                pass
            # ──────────────────────────────────────────────

            self._qord_fill(side, rule["strike"], cur_price,
                            source=f"🔔 감시 성립 [{now_str}] P={p_str} Δ={d_str}")
            self._watch_tabs.setCurrentIndex(1)   # 알람 로그 탭으로

    # ─────────────────────────────────────────────────────
    # 로그 불러오기 / 폴더 열기
    # ─────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────
    # ★ v6.5 감시 규칙 저장 / 복원
    # ─────────────────────────────────────────────────────
    def _save_watch_rules(self):
        """_watch_rules + 활성 상태를 watch_rules.json 에 저장."""
        try:
            active = self._watch_timer.isActive() \
                if hasattr(self, '_watch_timer') else True
            data = {
                "active": active,
                "rules":  self._watch_rules,
            }
            _WATCH_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _WATCH_RULES_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self._log(f"감시 규칙 저장 오류: {e}")

    def _load_watch_rules_from_file(self):
        """앱 시작 시 호출. watch_rules.json → _watch_rules 복원 + 테이블 재구성."""
        if not hasattr(self, "tbl_watch_rules"):
            self._log("⚠ 감시 규칙 복원 건너뜀: tbl_watch_rules 미생성")
            return
        if not _WATCH_RULES_FILE.exists():
            # 파일 없음 → OFF 상태 유지
            self._update_watch_status_label(False)
            return
        try:
            data  = json.loads(_WATCH_RULES_FILE.read_text(encoding="utf-8"))
            rules = data.get("rules", [])
            active = data.get("active", True)

            if not rules:
                # 규칙 없음 → OFF 상태 유지
                self._update_watch_status_label(False)
                return

            for rule in rules:
                rule["fired"] = False   # 재시작 시 fired 초기화
                idx = len(self._watch_rules)
                self._watch_rules.append(rule)
                self._watch_prev[idx] = {
                    "price": None, "delta": None,
                    "theta": None, "gamma": None}

                r = self.tbl_watch_rules.rowCount()
                self.tbl_watch_rules.insertRow(r)
                side   = rule.get("side", "")
                strike = rule.get("strike", "")
                tbl_set(self.tbl_watch_rules, r, 0,
                        f"{side} {strike}", "#ffd700")

                cond = rule.get("cond", {})
                cond_parts = []
                if cond.get("price") is not None:
                    cond_parts.append(
                        f"P{cond['price_op']}{cond['price']:.2f}")
                if cond.get("delta") is not None:
                    cond_parts.append(
                        f"Δ{cond['delta_op']}{cond['delta']:.3f}")
                if cond.get("theta") is not None:
                    cond_parts.append(
                        f"θ{cond['theta_op']}{cond['theta']:.3f}")
                if cond.get("gamma") is not None:
                    cond_parts.append(
                        f"γ{cond['gamma_op']}{cond['gamma']:.4f}")
                tbl_set(self.tbl_watch_rules, r, 1,
                        " & ".join(cond_parts) or "―")

                and_c = rule.get("and", {})
                and_parts = []
                if and_c.get("time"):
                    and_parts.append(
                        f"T{and_c['time_op']}{and_c['time']}")
                if and_c.get("delta") is not None:
                    and_parts.append(
                        f"Δ{and_c['delta_op']}{and_c['delta']:.3f}")
                if and_c.get("gamma") is not None:
                    and_parts.append(
                        f"γ{and_c['gamma_op']}{and_c['gamma']:.4f}")
                if and_c.get("theta") is not None:
                    and_parts.append(
                        f"θ{and_c['theta_op']}{and_c['theta']:.3f}")
                tbl_set(self.tbl_watch_rules, r, 2,
                        " & ".join(and_parts) or "―", "#aaa")
                tbl_set(self.tbl_watch_rules, r, 3, "👁 감시 중", "#00ff88")

            # 활성 상태 복원
            if hasattr(self, '_watch_timer'):
                if active:
                    self._watch_timer.start()
                else:
                    self._watch_timer.stop()

            # 상태 라벨 업데이트
            self._update_watch_status_label(active)

            self._log(f"감시 규칙 복원: {len(rules)}건  활성={active}")
        except Exception as e:
            self._log(f"감시 규칙 복원 오류: {e}")

    def _update_watch_status_label(self, active: bool):
        """상태 라벨 텍스트/색상 즉시 갱신. 깜빡임 타이머도 제어."""
        lbl = getattr(self, '_watch_status_lbl', None)
        blink_timer = getattr(self, '_watch_blink_timer', None)
        btn = getattr(self, '_watch_toggle_btn', None)

        if lbl:
            if active:
                lbl.setText("🟢 ON WATCHING ●")
                lbl.setStyleSheet(
                    "color:#00ff88;font-size:11px;font-weight:bold;border:none;")
                if blink_timer:
                    blink_timer.start()
            else:
                lbl.setText("⏸ WATCHING OFF")
                lbl.setStyleSheet(
                    "color:#555;font-size:11px;font-weight:bold;border:none;")
                if blink_timer:
                    blink_timer.stop()

        if btn:
            if active:
                btn.setText("⏸ 감시 끄기")
                btn.setStyleSheet(
                    "QPushButton{background:#1a1a2a;color:#ff8800;font-size:11px;"
                    "border:1px solid #3a3a2a;border-radius:3px;padding:2px 8px;}"
                    "QPushButton:hover{background:#2a2a1a;}")
            else:
                btn.setText("▶ 감시 켜기")
                btn.setStyleSheet(
                    "QPushButton{background:#1a2a1a;color:#00ff88;font-size:11px;"
                    "border:1px solid #2a5a2a;border-radius:3px;padding:2px 8px;}"
                    "QPushButton:hover{background:#2a3a2a;}")

    def _toggle_watch(self):
        """감시 켜기/끄기 토글."""
        if not hasattr(self, '_watch_timer'):
            return
        active = not self._watch_timer.isActive()
        if active:
            self._watch_timer.start()
        else:
            self._watch_timer.stop()
        self._update_watch_status_label(active)
        self._save_watch_rules()   # 활성 상태도 저장
        self._log(f"감시 {'켜짐' if active else '꺼짐'}")

    def _load_watch_log(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "감시 알람 파일 불러오기", str(SAVE_DIR),
            "텍스트 파일 (*.txt);;모든 파일 (*)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.watch_log_box.setPlainText(f.read())
            self._log(f"감시 로그 불러오기: {path}")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"파일 읽기 실패:\n{e}")

    def _open_watch_log_folder(self):
        import subprocess, sys
        try:
            folder = str(self._watch_log_file.parent)
            if sys.platform == "win32":
                subprocess.Popen(["explorer", folder])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            self._log(f"폴더 열기 실패: {e}")