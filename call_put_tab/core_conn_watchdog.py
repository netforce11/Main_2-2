"""
core_conn_watchdog.py — Watchdog·재연결·텔레그램  v6.7
════════════════════════════════════════════════════════
core_conn_signals.py에서 Watchdog·재연결 로직을 분리.

포함:
  _tg_send()            텔레그램 비동기 전송 (모듈 레벨)
  ConnWatchdogMixin
    · _watch_dog()      3초마다 — 틱 생존 감시 + TG 경고
    · _reconnect_flow() 자동 재연결 흐름 (구독 해지 → 재연결 → 재구독)
════════════════════════════════════════════════════════
"""

from __future__ import annotations
import os
import threading
from PyQt5.QtCore import QTimer
from core import REQ_UND, REQ_CALL, REQ_PUT
from datetime import datetime

# ── 텔레그램 설정 ──────────────────────────────────────────────
# 환경변수 우선, 없으면 아래 상수에 직접 입력
_TG_TOKEN   = os.environ.get("TG_TOKEN",   "")   # 예: "123456:ABC-DEF..."
_TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")   # 예: "-1001234567890"


def _tg_send(msg: str) -> None:
    """
    텔레그램 메시지 비동기 전송.
    TG_TOKEN / TG_CHAT_ID 미설정 시 조용히 무시.
    별도 daemon 스레드 → UI 블로킹 없음.
    """
    if not _TG_TOKEN or not _TG_CHAT_ID:
        return

    def _send():
        try:
            import urllib.request, json
            payload = json.dumps({
                "chat_id":    _TG_CHAT_ID,
                "text":       msg,
                "parse_mode": "HTML",
            }).encode("utf-8")
            url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            print(f"[TG] 전송 실패: {e}")

    threading.Thread(target=_send, daemon=True).start()


class ConnWatchdogMixin:
    """Watchdog + 자동 재연결. ConnSignalsMixin에 통합된다."""

    # ── Watchdog ──────────────────────────────────────────────
    def _watch_dog(self):
        """
        3초마다 호출 — 마지막 틱 수신 시각 기준으로 상태 경고.
        10초 이상 미수신 시 텔레그램 알림 (최초 1회, 복귀 시 플래그 초기화).
        """
        if not self.mw.connected:
            return
        last = getattr(self, '_last_tick_time', None)
        if last is None:
            return

        elapsed = (datetime.now() - last).total_seconds()

        if elapsed > 10:
            self.lbl_status.setText("● 데이터 멈춤!")
            self.lbl_status.setStyleSheet(
                "color:#ff4444;font-weight:bold;border:none;")
            if not getattr(self, '_tg_stale_sent', False):
                self._tg_stale_sent = True
                _tg_send(
                    f"⚠️ <b>시세 멈춤 감지</b>\n"
                    f"마지막 틱 수신 후 {int(elapsed)}초 경과\n"
                    f"자동 재연결을 시도합니다.")

        elif elapsed > 3:
            self.lbl_status.setText("● 지연 발생")
            self.lbl_status.setStyleSheet(
                "color:#ffbb00;font-weight:bold;border:none;")

        else:
            self._tg_stale_sent = False
            cur = self.lbl_status.text()
            if cur in ("● 데이터 멈춤!", "● 지연 발생"):
                self.lbl_status.setText("● 연결됨")
                self.lbl_status.setStyleSheet(
                    "color:#00ff88;font-weight:bold;border:none;")

    # ── 자동 재연결 ───────────────────────────────────────────
    def _reconnect_flow(self):
        """
        ERR 1100 / 100 수신 시 호출되는 자동 재연결 흐름.

        단계:
          0s   : 구독 해지 (cancelMktData)
          5s   : TWS disconnect → 2초 후 connect
          10s  : 재구독 (reqMktData) + 잔고 재조회
        """
        if getattr(self, '_reconnecting', False):
            self._log("⚠ 재연결 이미 진행 중 — 중복 요청 무시")
            return
        self._reconnecting = True

        self._log("🔄 재연결 흐름 시작: 전체 구독 해지 중…")
        self.lbl_status.setText("● 재연결 중…")
        self.lbl_status.setStyleSheet(
            "color:#ff9800;font-weight:bold;border:none;")
        _tg_send("🔄 <b>TWS 재연결 시작</b>\n시세 수신 중단 감지 → 자동 재연결 진행 중")

        # ── 구독 해지 ────────────────────────────────────────
        try:
            if self.mw.ib:
                self.mw.ib.cancelMktData(REQ_UND)
                for i in range(26):
                    self.mw.ib.cancelMktData(REQ_CALL + i)
                    self.mw.ib.cancelMktData(REQ_PUT  + i)
        except Exception as e:
            self._log(f"구독 해지 오류 (무시): {e}")

        def _do_reconnect():
            self._log("🔄 TWS 재연결 시도…")
            try:
                self.mw.disconnect_ibkr()
            except Exception:
                pass
            QTimer.singleShot(2000, lambda: self.mw.connect_ibkr(silent=True))

        def _do_resubscribe():
            self._reconnecting = False
            if not self.mw.connected:
                self._log("⚠ 재연결 실패 — 수동으로 연결 버튼을 눌러주세요.")
                _tg_send("❌ <b>TWS 재연결 실패</b>\n수동으로 연결 버튼을 눌러주세요.")
                return
            self._log("🔄 재구독 시작…")
            _tg_send("✅ <b>TWS 재연결 성공</b>\n시세 재구독을 시작합니다.")
            sym = self.edit_sym.text().strip().upper() or "SPX"
            self._req_und(sym)
            QTimer.singleShot(1000, self._fetch)
            if hasattr(self, '_on_pos_reconnect_hook'):
                QTimer.singleShot(1500, self._on_pos_reconnect_hook)

        QTimer.singleShot(5000,  _do_reconnect)
        QTimer.singleShot(10000, _do_resubscribe)
