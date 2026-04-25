"""
tab_multi_price.py — 복수 현재가 탭  v2.0  (Tab 5: MultiPriceGrid)
"""

import json, csv
from datetime import datetime, date, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QGroupBox, QListWidget, QTextEdit, QMessageBox,
    QInputDialog, QFileDialog, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QCheckBox, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor, QBrush

try:
    import pyqtgraph as pg
    PG = True
except ImportError:
    PG = False

from core import (
    bridge, router, GridTab, make_table, tbl_set, ts, ts_full,
    SYMBOL_CFG, DEFAULT_CFG, INDEX_SYM,
    REQ_UND, REQ_CHAIN, REQ_CHAIN_P, REQ_MULTI, REQ_ACCT,
    GREEKS_MATRIX_N, GREEKS_AUTOSAVE_S,
    build_expiry_list, make_opt_contract, make_und_contract,
    save_json, load_json, append_csv, load_csv, SAVE_DIR, ACCT_TAGS,
    auto_mdt, is_market_open,
)

# Tab 5: 복수 현재가
# 트리거: 등록 테이블 (수정 가능) + 등록 상태 표시
# ══════════════════════════════════════════════════════════════
class MultiPriceGrid(GridTab):
    """
    복수 현재가 탭 v2.0
    레이아웃 (12열 × 4행):
      [0,0-1]  관심종목 (좁게)
      [0,2-5]  슬롯1
      [0,6-9]  슬롯2
      [0,10-11] 슬롯3 (우측)
      [1,2-5]  슬롯3 (슬롯3은 행1에 배치)
      ↓ 실제 배치:
      행0: 관심종목(0-1) | 슬롯1(2-5) | 슬롯2(6-9) | 슬롯3(10-11+행1)
      행1: 관심종목이어짐 | 트리거등록(2-5) | 트리거등록이어짐
      행2: 등록된 트리거(0-7) | [우측여백]
      행3: 트리거 이벤트 로그(0-7) | 저장버튼(8-11)

    → 슬롯 3개 가로 나란히, 관심종목 좁게, 트리거는 하단
    """
    SLOTS = 3

    def __init__(self, mw):
        super().__init__()
        self.mw        = mw
        self.slot_data = [{} for _ in range(self.SLOTS)]
        self.slot_rids = [REQ_MULTI + i*100 for i in range(self.SLOTS)]
        self.trigger_logs = []
        self._alert_sound_path = ""   # 트리거 발동 알람 사운드 경로
        self._build()
        self._connect_signals()
        self._restore_sound_setting()

    def _build(self):
        """UI 구성 로직은 multi_price_build.py 참조."""
        from Account_info.multi_price_build import build_multi_price
        build_multi_price(self)

    def _connect_signals(self):
        router.register_price(REQ_MULTI, REQ_MULTI+299, self._on_tick)
        router.register_option(REQ_MULTI, REQ_MULTI+299, self._on_tick_opt)

    # ── 슬롯 로딩 ────────────────────────────────────────────────
    def _on_watch_click(self, item):
        sym  = item.text().split()[0]
        slot = next((i for i,d in enumerate(self.slot_data) if not d.get("sym")), 0)
        self._load_slot(slot, sym)

    def _load_from_input(self, idx):
        sym = self.slot_w[idx]["input"].text().strip().upper()
        if sym: self._load_slot(idx, sym)

    def _load_slot(self, idx, sym):
        if not self.mw.connected:
            self.slot_w[idx]["price"].setText("미연결")
            return
        auto_mdt(self.mw.ib)
        rid = self.slot_rids[idx]
        try: self.mw.ib.cancelMktData(rid)
        except: pass
        self.slot_data[idx] = {"sym": sym}
        self.slot_w[idx]["sym"].setText(sym)
        self.slot_w[idx]["price"].setText("조회 중…")
        self.slot_w[idx]["input"].setText(sym)
        self.mw.ib.reqMktData(rid, make_und_contract(sym), "232", False, False, [])

    # ── Tick 수신 ────────────────────────────────────────────────
    def _on_tick(self, rid, tt, price):
        if price <= 0: return
        for i, base in enumerate(self.slot_rids):
            if rid != base: continue
            if tt in (4, 14, 68):
                self.slot_w[i]["price"].setText(f"{price:,.2f}")
                tbl_set(self.slot_w[i]["tbl"], 0, 1, f"{price:,.2f}", "#00ff88")
                self.slot_data[i]["price"] = price
                self._check_triggers(i, price)
            elif tt == 8:
                tbl_set(self.slot_w[i]["tbl"], 1, 1, f"{int(price):,}")
            elif tt in (9, 75):
                prev = self.slot_data[i].get("prev_close")
                cur  = self.slot_data[i].get("price")
                tbl_set(self.slot_w[i]["tbl"], 5, 1, f"{price:,.2f}")
                self.slot_data[i]["prev_close"] = price
                # 등락률 표시
                if cur and price > 0:
                    chg = cur - price; pct = chg / price * 100
                    col = "#00e676" if chg >= 0 else "#ff5252"
                    sign = "+" if chg >= 0 else ""
                    self.slot_w[i]["price"].setStyleSheet(
                        f"color:{col};background:#07070f;"
                        "border-radius:6px;padding:6px;border:1px solid #1e2050;")
                    self.slot_w[i]["sym"].setText(
                        f"{self.slot_data[i].get('sym','―')}  "
                        f"{sign}{chg:,.2f} ({sign}{pct:.2f}%)")

    def _on_tick_opt(self, rid, tt, iv, delta, op, gamma, vega, theta):
        if tt not in (12, 13): return
        for i, base in enumerate(self.slot_rids):
            if rid != base: continue
            tbl_set(self.slot_w[i]["tbl"], 2, 1, f"{delta:+.4f}", "#aaddff")
            tbl_set(self.slot_w[i]["tbl"], 3, 1, f"{gamma:.6f}", "#88ff44")
            tbl_set(self.slot_w[i]["tbl"], 4, 1, f"{theta:.4f}", "#ff8844")

    # ── 트리거 ────────────────────────────────────────────────────
    def _add_trigger(self):
        p = self.trg_price.text().strip()
        t = self.trg_time.text().strip()
        d = self.trg_desc.text().strip() or "―"
        r = self.tbl_trg.rowCount(); self.tbl_trg.insertRow(r)
        for c, v in enumerate([p, t, d]):
            item = QTableWidgetItem(v); item.setTextAlignment(Qt.AlignCenter)
            self.tbl_trg.setItem(r, c, item)
        st = QTableWidgetItem("대기중"); st.setTextAlignment(Qt.AlignCenter)
        st.setForeground(QBrush(QColor("#00ff88")))
        st.setFlags(st.flags() & ~Qt.ItemIsEditable)
        self.tbl_trg.setItem(r, 3, st)
        self.trg_log.append(f"[{ts()}] 트리거 등록: 가격≤{p}  시간≥{t}  ({d})")

    def _on_trg_dbl(self, row, col):
        if col == 3: return
        self.tbl_trg.editItem(self.tbl_trg.item(row, col))

    def _trg_keypress(self, event):
        if event.key() == Qt.Key_Delete: self._del_trigger()
        else: QTableWidget.keyPressEvent(self.tbl_trg, event)

    def _del_trigger(self):
        rows = sorted(set(i.row() for i in self.tbl_trg.selectedItems()), reverse=True)
        for r in rows: self.tbl_trg.removeRow(r)

    def _clr_triggers(self):
        ret = QMessageBox.question(self,"초기화","모든 트리거를 삭제합니까?",
            QMessageBox.Yes|QMessageBox.No)
        if ret == QMessageBox.Yes: self.tbl_trg.setRowCount(0)

    def _check_triggers(self, slot_idx, price):
        now_s = datetime.now().strftime("%H:%M:%S")
        for r in range(self.tbl_trg.rowCount()):
            st_item = self.tbl_trg.item(r, 3)
            if not st_item or st_item.text() == "발동!": continue
            p_item = self.tbl_trg.item(r, 0)
            t_item = self.tbl_trg.item(r, 1)
            d_item = self.tbl_trg.item(r, 2)
            price_ok = True; time_ok = True
            if p_item and p_item.text().strip():
                try:
                    if float(p_item.text()) < price: price_ok = False
                except: pass
            if t_item and t_item.text().strip():
                time_ok = now_s >= t_item.text().strip()
            if price_ok and time_ok:
                st_item.setText("발동!")
                st_item.setForeground(QBrush(QColor("#ffd700")))
                desc = d_item.text() if d_item else "―"
                msg  = f"★ 트리거 발동! 슬롯{slot_idx+1} {price:,.2f} ({desc})"
                self.trg_log.append(f"[{ts()}] {msg}")
                self.trigger_logs.append({"time": ts(), "msg": msg})
                self._play_alert_sound()   # 알람 사운드 재생

    # ─────────────────────────────────────────────────────────
    # 알람 사운드 관련 메서드
    # ─────────────────────────────────────────────────────────
    def _pick_alert_sound(self):
        """파일 다이얼로그로 .wav 선택."""
        from pathlib import Path as _Path
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택",
            str(_Path.home()), "WAV 파일 (*.wav);;모든 파일 (*)")
        if not path:
            return
        self._alert_sound_path = path
        fname = _Path(path).name
        self.lbl_snd_file.setText(fname)
        self.lbl_snd_file.setToolTip(path)
        # 기본값 저장 체크 시 JSON에 저장
        if self.chk_snd_default.isChecked():
            self._save_sound_setting(path)

    def _clear_alert_sound(self):
        self._alert_sound_path = ""
        self.lbl_snd_file.setText("기본 비프음")
        self.lbl_snd_file.setToolTip("")
        self._save_sound_setting("")

    def _play_alert_sound(self):
        """사운드 재생 — .wav 있으면 파일, 없으면 비프."""
        from pathlib import Path as _Path
        if self._alert_sound_path and _Path(self._alert_sound_path).exists():
            try:
                from PyQt5.QtMultimedia import QSound
                QSound.play(self._alert_sound_path); return
            except ImportError:
                pass
            try:
                import winsound
                winsound.PlaySound(self._alert_sound_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC); return
            except Exception:
                pass
            try:
                import subprocess, sys
                if sys.platform == "darwin":
                    subprocess.Popen(["afplay", self._alert_sound_path])
                else:
                    subprocess.Popen(["aplay", self._alert_sound_path])
                return
            except Exception:
                pass
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass

    def _save_sound_setting(self, path: str):
        """사운드 경로를 설정 JSON에 저장."""
        try:
            cfg = load_json("multiprice_sound.json", {})
            cfg["alert_sound"] = path
            save_json("multiprice_sound.json", cfg)
        except Exception:
            pass

    def _restore_sound_setting(self):
        """앱 시작 시 저장된 사운드 경로 복원."""
        try:
            from pathlib import Path as _Path
            cfg = load_json("multiprice_sound.json", {})
            path = cfg.get("alert_sound", "")
            if path and _Path(path).exists():
                self._alert_sound_path = path
                self.lbl_snd_file.setText(_Path(path).name)
                self.lbl_snd_file.setToolTip(path)
        except Exception:
            pass

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self,"저장","trigger_log.json","JSON (*.json)")
        if not path: return
        with open(path,"w",encoding="utf-8") as f:
            json.dump(self.trigger_logs, f, ensure_ascii=False, indent=2)
        self.lbl_file.setText(f"저장: {Path(path).name}")

    def _load_log(self):
        path, _ = QFileDialog.getOpenFileName(self,"불러오기","","JSON (*.json)")
        if not path: return
        with open(path,"r",encoding="utf-8") as f: data=json.load(f)
        self.trigger_logs = data; self.trg_log.clear()
        for d in data: self.trg_log.append(f"[{d.get('time','')}] {d.get('msg','')}")
        self.lbl_file.setText(f"불러옴: {Path(path).name}")

    def _w_add(self):
        t, ok = QInputDialog.getText(self,"추가","심볼:")
        if ok and t.strip(): self.watch.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watch.currentRow()
        if r >= 0: self.watch.takeItem(r)

    def _apply_theme(self):
        """TabWrapper 다크/라이트 전환 시 호출."""
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        tbls = [s["tbl"] for s in self.slot_w] + [self.tbl_trg]
        for tbl in tbls:
            _apply_table_theme(tbl, dark)

    def _get_extra_settings(self) -> dict:
        """스플리터 비율 저장."""
        d = {}
        try:
            d["slots_hsplit"]    = list(self._slots_hsplit.sizes())
            d["bot_hsplit"]      = list(self._bot_hsplit.sizes())
            d["bot_left_vsplit"] = list(self._bot_left_vsplit.sizes())
            d["bot_right_vsplit"]= list(self._bot_right_vsplit.sizes())
            d["slot_vsplits"]    = [list(v.sizes()) for v in self._slot_splitters]
        except Exception:
            pass
        return d

    def _apply_extra_settings(self, s: dict):
        """스플리터 비율 복원."""
        def _restore():
            try:
                if s.get("slots_hsplit"):     self._slots_hsplit.setSizes(s["slots_hsplit"])
                if s.get("bot_hsplit"):        self._bot_hsplit.setSizes(s["bot_hsplit"])
                if s.get("bot_left_vsplit"):   self._bot_left_vsplit.setSizes(s["bot_left_vsplit"])
                if s.get("bot_right_vsplit"):  self._bot_right_vsplit.setSizes(s["bot_right_vsplit"])
                if s.get("slot_vsplits"):
                    for i, sz in enumerate(s["slot_vsplits"]):
                        if i < len(self._slot_splitters):
                            self._slot_splitters[i].setSizes(sz)
            except Exception:
                pass
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, _restore)

