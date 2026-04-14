"""
tab_options_settings.py — 화면 설정 저장/복원  v6.4
════════════════════════════════════════════════════════════════
  CallPutGrid 에서 분리 (tab_options.py 에 mixin으로 사용)

  포함 기능:
  - _save_window_geometry() / _restore_window_geometry()
  - _hook_window_geometry()
  - _get_extra_settings() / _apply_extra_settings()
  - _get_layout_snapshot() / _apply_layout_snapshot()
  - _refresh_layout_presets()
  - _save_layout_preset() / _load_layout_preset() / _del_layout_preset()
════════════════════════════════════════════════════════════════
"""

from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from core import save_json, load_json, SAVE_DIR


class SettingsMixin:
    """화면설정 저장/복원 전용 메서드. CallPutGrid에 mixin된다."""

    _GEO_FILE    = "window_geometry.json"
    _LAYOUT_FILE = "callput_layouts.json"

    # ─────────────────────────────────────────────────────────
    # 윈도우 geometry 저장/복원/후킹
    # ─────────────────────────────────────────────────────────
    def _save_window_geometry(self):
        win = self.mw
        if win is None: return
        geo = win.geometry()
        data = {"x": geo.x(), "y": geo.y(), "w": geo.width(), "h": geo.height()}
        try: save_json(self._GEO_FILE, data)
        except Exception as e: self._log(f"[geometry] 저장 실패: {e}")

    def _restore_window_geometry(self):
        win = self.mw
        if win is None: return
        data = load_json(self._GEO_FILE, {})
        if not data: return
        try:
            win.setGeometry(int(data.get("x",100)), int(data.get("y",100)),
                            int(data.get("w",1400)), int(data.get("h",900)))
            self._log(f"[geometry] 복원: ({data['x']},{data['y']})  {data['w']}×{data['h']}")
        except Exception as e: self._log(f"[geometry] 복원 실패: {e}")

    def _hook_window_geometry(self):
        win = self.mw
        if win is None or getattr(win, "_geo_hooked", False): return
        win._geo_hooked = True
        _orig_resize = win.resizeEvent
        _orig_move   = win.moveEvent
        def _on_resize(ev): _orig_resize(ev); self._save_window_geometry()
        def _on_move(ev):   _orig_move(ev);   self._save_window_geometry()
        win.resizeEvent = _on_resize
        win.moveEvent   = _on_move

    # ─────────────────────────────────────────────────────────
    # TabWrapper 저장/복원 인터페이스
    # ─────────────────────────────────────────────────────────
    def _get_extra_settings(self) -> dict:
        _, code, tag = self._expiry_list[self.combo_exp.currentIndex()]
        d = {
            "sym":    self.edit_sym.text().strip().upper(),
            "expiry": code,
            "zone":   self._zone,
            "n":      self.spin_n.value(),
        }
        if hasattr(self, 'fx_in'):   d["fx"]     = self.fx_in.text().strip()
        if hasattr(self, 'high_in'): d["filter"] = self.high_in.text().strip()
        try:
            d["h_main_split"]  = list(self._h_main.sizes())
            d["ctrl_split"]    = list(self._ctrl_splitter.sizes())
            d["v_split"]       = list(self._v_splitter.sizes())
            d["tbl_split"]     = list(self._tbl_splitter.sizes())
            d["watch_split"]   = list(self._watch_splitter.sizes())
            d["bot_split"]     = list(self._bot_splitter.sizes())
        except Exception: pass
        d["alert_sound"] = self._alert_sound_path
        if hasattr(self, '_watch_font_slider'):
            d["watch_font_size"] = self._watch_font_slider.value()
        return d

    def _apply_extra_settings(self, s: dict):
        if s.get("sym"):    self.edit_sym.setText(s["sym"])
        if s.get("fx") and hasattr(self, 'fx_in'):     self.fx_in.setText(s["fx"])
        if s.get("filter") and hasattr(self, 'high_in'): self.high_in.setText(s["filter"])
        if s.get("n"):      self.spin_n.setValue(int(s["n"]))
        zone = s.get("zone", "ATM")
        if zone in self._zone_btns:
            self._zone = zone
            self._zone_btns[zone].blockSignals(True)
            self._zone_btns[zone].setChecked(True)
            self._zone_btns[zone].blockSignals(False)
        expiry = s.get("expiry","")
        for i, (_, code, _) in enumerate(self._expiry_list):
            if code == expiry:
                self.combo_exp.blockSignals(True)
                self.combo_exp.setCurrentIndex(i)
                self.combo_exp.blockSignals(False)
                break
        snd = s.get("alert_sound","")
        if snd and Path(snd).exists():
            self._alert_sound_path = snd
            self.lbl_sound_file.setText(Path(snd).name)
            self.lbl_sound_file.setToolTip(snd)
        wfs = s.get("watch_font_size")
        if wfs and hasattr(self, '_watch_font_slider'):
            self._watch_font_slider.setValue(int(wfs))

        def _restore_split():
            try:
                if s.get("h_main_split"):  self._h_main.setSizes(s["h_main_split"])
                if s.get("ctrl_split"):    self._ctrl_splitter.setSizes(s["ctrl_split"])
                if s.get("v_split"):       self._v_splitter.setSizes(s["v_split"])
                if s.get("tbl_split"):     self._tbl_splitter.setSizes(s["tbl_split"])
                if s.get("watch_split"):   self._watch_splitter.setSizes(s["watch_split"])
                if s.get("bot_split"):     self._bot_splitter.setSizes(s["bot_split"])
            except Exception: pass

        QTimer.singleShot(100, _restore_split)
        QTimer.singleShot(50,  self._restore_window_geometry)
        QTimer.singleShot(200, self._hook_window_geometry)

    # ─────────────────────────────────────────────────────────
    # 화면설정 프리셋 저장/불러오기/삭제
    # ─────────────────────────────────────────────────────────
    def _get_layout_snapshot(self) -> dict:
        snap = {}
        try:
            snap["h_main_split"]  = list(self._h_main.sizes())
            snap["ctrl_split"]    = list(self._ctrl_splitter.sizes())
            snap["v_split"]       = list(self._v_splitter.sizes())
            snap["tbl_split"]     = list(self._tbl_splitter.sizes())
            snap["watch_split"]   = list(self._watch_splitter.sizes())
            snap["bot_split"]     = list(self._bot_splitter.sizes())
        except Exception: pass
        if hasattr(self, '_watch_font_slider'):
            snap["watch_font_size"] = self._watch_font_slider.value()
        return snap

    def _apply_layout_snapshot(self, snap: dict):
        def _do():
            try:
                if snap.get("h_main_split"):  self._h_main.setSizes(snap["h_main_split"])
                if snap.get("ctrl_split"):     self._ctrl_splitter.setSizes(snap["ctrl_split"])
                if snap.get("v_split"):        self._v_splitter.setSizes(snap["v_split"])
                if snap.get("tbl_split"):      self._tbl_splitter.setSizes(snap["tbl_split"])
                if snap.get("watch_split"):    self._watch_splitter.setSizes(snap["watch_split"])
                if snap.get("bot_split"):      self._bot_splitter.setSizes(snap["bot_split"])
            except Exception: pass
            wfs = snap.get("watch_font_size")
            if wfs and hasattr(self, '_watch_font_slider'):
                self._watch_font_slider.setValue(int(wfs))
        QTimer.singleShot(80, _do)

    def _refresh_layout_presets(self):
        if not hasattr(self, 'combo_layout_preset'): return
        data = load_json(self._LAYOUT_FILE, {})
        self.combo_layout_preset.blockSignals(True)
        self.combo_layout_preset.clear()
        for name in sorted(data.keys()):
            self.combo_layout_preset.addItem(name)
        self.combo_layout_preset.blockSignals(False)

    def _save_layout_preset(self):
        name = self.combo_layout_name.text().strip()
        if not name:
            QMessageBox.warning(self, "이름 없음", "프리셋 이름을 입력하세요."); return
        data = load_json(self._LAYOUT_FILE, {})
        data[name] = self._get_layout_snapshot()
        save_json(self._LAYOUT_FILE, data)
        self._refresh_layout_presets()
        idx = self.combo_layout_preset.findText(name)
        if idx >= 0: self.combo_layout_preset.setCurrentIndex(idx)
        self._log(f"💾 화면설정 저장: [{name}]")

    def _load_layout_preset(self):
        name = self.combo_layout_preset.currentText().strip()
        if not name: return
        data = load_json(self._LAYOUT_FILE, {})
        snap = data.get(name)
        if not snap:
            QMessageBox.warning(self, "없음", f"프리셋 [{name}]을 찾을 수 없습니다."); return
        self._apply_layout_snapshot(snap)
        self._log(f"📂 화면설정 불러오기: [{name}]")

    def _del_layout_preset(self):
        name = self.combo_layout_preset.currentText().strip()
        if not name: return
        ret = QMessageBox.question(self, "삭제 확인",
            f"프리셋 [{name}]을 삭제하시겠습니까?", QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes: return
        data = load_json(self._LAYOUT_FILE, {})
        data.pop(name, None)
        save_json(self._LAYOUT_FILE, data)
        self._refresh_layout_presets()
        self._log(f"✕ 화면설정 삭제: [{name}]")
