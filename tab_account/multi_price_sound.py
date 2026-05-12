"""
multi_price_sound.py — MultiPriceGrid 알람 사운드·파일 로직
════════════════════════════════════════════════════════
포함 내용:
  - MultiPriceSoundMixin
      _pick_alert_sound()      .wav 파일 선택 + 기본값 저장
      _clear_alert_sound()     사운드 초기화
      _play_alert_sound()      재생 (QSound→winsound→aplay→beep)
      _save_sound_setting()    경로 JSON 저장
      _restore_sound_setting() 앱 시작 시 경로 복원
      _save_log()              트리거 로그 JSON 저장
      _load_log()              트리거 로그 JSON 불러오기
      _w_add() / _w_del()      관심종목 추가/삭제
      _apply_theme()           다크/라이트 테이블 재적용
════════════════════════════════════════════════════════
"""

import json
from pathlib import Path

from PyQt5.QtWidgets import QFileDialog, QInputDialog

from core import save_json, load_json


class MultiPriceSoundMixin:
    """알람 사운드·파일 저장·관심종목 로직 Mixin."""

    def _pick_alert_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "알람 사운드 파일 선택",
            str(Path.home()), "WAV 파일 (*.wav);;모든 파일 (*)")
        if not path: return
        self._alert_sound_path = path
        fname = Path(path).name
        self.lbl_snd_file.setText(fname)
        self.lbl_snd_file.setToolTip(path)
        if self.chk_snd_default.isChecked():
            self._save_sound_setting(path)

    def _clear_alert_sound(self):
        self._alert_sound_path = ""
        self.lbl_snd_file.setText("기본 비프음")
        self.lbl_snd_file.setToolTip("")
        self._save_sound_setting("")

    def _play_alert_sound(self):
        """사운드 재생 — .wav 있으면 파일, 없으면 비프."""
        if self._alert_sound_path and Path(self._alert_sound_path).exists():
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
                cmd = ["afplay" if sys.platform == "darwin" else "aplay",
                       self._alert_sound_path]
                subprocess.Popen(cmd); return
            except Exception:
                pass
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass

    def _save_sound_setting(self, path: str):
        try:
            cfg = load_json("multiprice_sound.json", {})
            cfg["alert_sound"] = path
            save_json("multiprice_sound.json", cfg)
        except Exception:
            pass

    def _restore_sound_setting(self):
        try:
            cfg  = load_json("multiprice_sound.json", {})
            path = cfg.get("alert_sound", "")
            if path and Path(path).exists():
                self._alert_sound_path = path
                self.lbl_snd_file.setText(Path(path).name)
                self.lbl_snd_file.setToolTip(path)
        except Exception:
            pass

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "저장", "trigger_log.json", "JSON (*.json)")
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.trigger_logs, f, ensure_ascii=False, indent=2)
        self.lbl_file.setText(f"저장: {Path(path).name}")

    def _load_log(self):
        path, _ = QFileDialog.getOpenFileName(self, "불러오기", "", "JSON (*.json)")
        if not path: return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.trigger_logs = data; self.trg_log.clear()
        for d in data:
            self.trg_log.append(f"[{d.get('time','')}] {d.get('msg','')}")
        self.lbl_file.setText(f"불러옴: {Path(path).name}")

    def _w_add(self):
        t, ok = QInputDialog.getText(self, "추가", "심볼:")
        if ok and t.strip():
            self.watch.addItem(t.strip().upper())

    def _w_del(self):
        r = self.watch.currentRow()
        if r >= 0:
            self.watch.takeItem(r)

    def _apply_theme(self):
        from core import _apply_table_theme
        dark = getattr(self, 'dark_mode', True)
        for s in self.slot_w:
            _apply_table_theme(s["tbl"], dark)
        _apply_table_theme(self.tbl_trg, dark)
