"""
telegram_bot/tg_config_widget.py
[📡 텔레그램] 탭 전체 UI.
  - 좌측: 실시간 수신 채팅창 (incoming / outgoing 말풍선)
  - 우측: 봇 설정 / 알람 설정 / 주문 수신 설정
메인 탭바에서:
    from telegram_bot.tg_config_widget import TgConfigWidget
    self.tab_widget.addTab(TgConfigWidget(), "📡 텔레그램")
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QScrollArea, QSizePolicy,
    QSplitter, QFrame,
)
from PyQt5.QtCore import Qt, QDateTime, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QColor, QPalette
from .tg_config import TgConfig
from .tg_client import TelegramClient

_F      = 12   # 기본 폰트 크기
_F_MONO = 11   # 원문 폰트 크기


# ─────────────────────────────────────────────────────────────
# 채팅 메시지 하나를 표시하는 위젯
# ─────────────────────────────────────────────────────────────
class _BubbleWidget(QWidget):
    TAG_COLORS = {
        "ORDER":   ("#FEF3C7", "#92400E"),   # 노랑
        "ALERT":   ("#FEE2E2", "#991B1B"),   # 빨강
        "CONFIRM": ("#D1FAE5", "#065F46"),   # 초록
        "INFO":    ("#E0E7FF", "#3730A3"),   # 보라
    }

    def __init__(self, direction: str, tag: str, text: str, raw: str, parent=None):
        super().__init__(parent)
        self._build(direction, tag, text, raw)

    def _build(self, direction: str, tag: str, text: str, raw: str):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        is_out = (direction == "outgoing")

        # ── 말풍선 컨테이너
        bubble = QFrame()
        bubble.setMaximumWidth(460)
        bg, fg = ("#2AABEE", "#ffffff") if is_out else ("#ffffff", "#1a1a1a")
        border_color = "#2AABEE" if is_out else "#e0e0e0"
        bubble.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {border_color}; "
            f"border-radius:14px; padding:6px 10px; }}"
        )
        v = QVBoxLayout(bubble)
        v.setSpacing(3)
        v.setContentsMargins(0, 0, 0, 0)

        # 태그 뱃지
        tag_bg, tag_fg = self.TAG_COLORS.get(tag, ("#e5e7eb", "#374151"))
        tag_lbl = QLabel(tag)
        tag_lbl.setStyleSheet(
            f"QLabel {{ background:{tag_bg}; color:{tag_fg}; "
            f"border-radius:6px; padding:1px 7px; font-size:11px; font-weight:bold; }}"
        )
        tag_lbl.setFixedHeight(18)
        tag_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        v.addWidget(tag_lbl)

        # 본문
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"QLabel {{ color:{fg}; font-size:{_F}px; background:transparent; border:none; }}"
        )
        v.addWidget(lbl)

        # 원문 (raw)
        if raw:
            raw_lbl = QLabel(raw)
            raw_lbl.setWordWrap(True)
            raw_bg = "rgba(255,255,255,0.18)" if is_out else "#f3f4f6"
            raw_fg = "#ffffff" if is_out else "#374151"
            raw_lbl.setStyleSheet(
                f"QLabel {{ background:{raw_bg}; color:{raw_fg}; "
                f"border-radius:6px; padding:4px 8px; font-size:{_F_MONO}px; "
                f"font-family:monospace; border:none; }}"
            )
            v.addWidget(raw_lbl)

        # 시각
        ts = QDateTime.currentDateTime().toString("HH:mm")
        time_lbl = QLabel(ts)
        time_lbl.setStyleSheet(
            f"QLabel {{ color:{'rgba(255,255,255,0.7)' if is_out else '#9ca3af'}; "
            f"font-size:11px; background:transparent; border:none; }}"
        )
        v.addWidget(time_lbl)

        # 정렬: outgoing → 오른쪽, incoming → 왼쪽
        if is_out:
            outer.addStretch()
            outer.addWidget(bubble)
        else:
            outer.addWidget(bubble)
            outer.addStretch()


# ─────────────────────────────────────────────────────────────
# 채팅창 위젯
# ─────────────────────────────────────────────────────────────
class _ChatPanel(QWidget):
    """실시간 수신 채팅창 (좌측 사이드바)."""

    # 스레드에서 안전하게 UI 업데이트하기 위한 시그널
    _append_signal = pyqtSignal(str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._append_signal.connect(self._append_bubble)

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # 헤더
        hdr = QFrame()
        hdr.setStyleSheet("QFrame { background:#2AABEE; border-radius:0px; }")
        hdr.setFixedHeight(44)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 0, 12, 0)

        avatar = QLabel("T")
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            "QLabel { background:rgba(255,255,255,0.3); color:#fff; "
            "border-radius:15px; font-size:14px; font-weight:bold; }"
        )
        hdr_lay.addWidget(avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        name_lbl = QLabel("Trading Bot")
        name_lbl.setStyleSheet(
            "QLabel { color:#fff; font-size:13px; font-weight:bold; background:transparent; }"
        )
        sub_lbl = QLabel("@my_trading_bot")
        sub_lbl.setStyleSheet(
            "QLabel { color:rgba(255,255,255,0.75); font-size:11px; background:transparent; }"
        )
        name_col.addWidget(name_lbl)
        name_col.addWidget(sub_lbl)
        hdr_lay.addLayout(name_col)
        hdr_lay.addStretch()

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            "QLabel { color:#22c55e; font-size:14px; background:transparent; }"
        )
        self._status_lbl = QLabel("연결됨")
        self._status_lbl.setStyleSheet(
            "QLabel { color:rgba(255,255,255,0.85); font-size:12px; background:transparent; }"
        )
        hdr_lay.addWidget(self._status_dot)
        hdr_lay.addWidget(self._status_lbl)
        v.addWidget(hdr)

        # 스크롤 영역
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background:#f0f0f0; }")

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("QWidget { background:#f0f0f0; }")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.setSpacing(4)
        self._msg_layout.setContentsMargins(8, 8, 8, 8)

        # 날짜 구분선
        today = QDateTime.currentDateTime().toString("yyyy-MM-dd")
        date_lbl = QLabel(today)
        date_lbl.setAlignment(Qt.AlignCenter)
        date_lbl.setStyleSheet(
            "QLabel { color:#9ca3af; font-size:11px; background:transparent; }"
        )
        self._msg_layout.addWidget(date_lbl)

        self._scroll.setWidget(self._msg_container)
        v.addWidget(self._scroll)

        # 하단 입력창
        inp_row = QHBoxLayout()
        inp_row.setContentsMargins(8, 6, 8, 6)

        self._inp = QLineEdit()
        self._inp.setPlaceholderText("메시지 입력 (테스트용)...")
        self._inp.setFixedHeight(34)
        self._inp.setStyleSheet(
            "QLineEdit { border-radius:17px; padding:0 12px; "
            "font-size:13px; border:1px solid #d1d5db; }"
        )
        self._inp.returnPressed.connect(self._on_send)

        send_btn = QPushButton("전송")
        send_btn.setFixedSize(60, 34)
        send_btn.setStyleSheet(
            "QPushButton { background:#2AABEE; color:#fff; border-radius:17px; "
            "font-size:13px; font-weight:bold; border:none; } "
            "QPushButton:hover { background:#1a9bde; }"
        )
        send_btn.clicked.connect(self._on_send)

        inp_row.addWidget(self._inp)
        inp_row.addWidget(send_btn)
        v.addLayout(inp_row)

    def append(self, direction: str, tag: str, text: str, raw: str):
        """스레드 세이프 — polling 스레드에서 호출 가능."""
        self._append_signal.emit(direction, tag, text, raw)

    def set_status(self, connected: bool):
        if connected:
            self._status_dot.setStyleSheet(
                "QLabel { color:#22c55e; font-size:14px; background:transparent; }"
            )
            self._status_lbl.setText("연결됨")
        else:
            self._status_dot.setStyleSheet(
                "QLabel { color:#9ca3af; font-size:14px; background:transparent; }"
            )
            self._status_lbl.setText("연결 안됨")

    def _append_bubble(self, direction: str, tag: str, text: str, raw: str):
        bubble = _BubbleWidget(direction, tag, text, raw, self._msg_container)
        self._msg_layout.addWidget(bubble)
        # 스크롤 맨 아래로
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _on_send(self):
        txt = self._inp.text().strip()
        if not txt:
            return
        self._inp.clear()
        # UI 말풍선 표시 (즉시)
        self.append("outgoing", "INFO", txt, txt)
        # 실제 텔레그램으로 전송
        cfg = TgConfig()
        if not cfg.token or not cfg.chat_id:
            self.append("incoming", "INFO",
                        "⚠️ 토큰 또는 Chat ID가 설정되지 않았습니다.", "")
            return
        # enabled 여부와 관계없이 채팅창 직접 전송은 항상 허용
        ok = TelegramClient.get()._send_raw(txt)
        if not ok:
            self.append("incoming", "INFO",
                        "⚠️ 전송 실패. 토큰/Chat ID 또는 네트워크를 확인하세요.", "")


# ─────────────────────────────────────────────────────────────
# 설정 패널 (우측)
# ─────────────────────────────────────────────────────────────
class _SettingsPanel(QWidget):
    def __init__(self, chat_panel: _ChatPanel, parent=None):
        super().__init__(parent)
        self._cfg  = TgConfig()
        self._chat = chat_panel
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        # ── 봇 설정 그룹
        grp_bot = QGroupBox("봇 설정")
        grp_bot.setFont(QFont("", _F, QFont.Bold))
        g = QVBoxLayout(grp_bot)

        def row(label, widget):
            h = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(90)
            lbl.setFont(QFont("", _F))
            h.addWidget(lbl)
            h.addWidget(widget)
            g.addLayout(h)

        self._token_inp = QLineEdit(self._cfg.token)
        self._token_inp.setPlaceholderText("123456:ABC-DEF...")
        self._token_inp.setEchoMode(QLineEdit.Password)
        self._token_inp.setFont(QFont("", _F))
        row("Bot Token", self._token_inp)

        self._chatid_inp = QLineEdit(self._cfg.chat_id)
        self._chatid_inp.setPlaceholderText("주인님 chat_id")
        self._chatid_inp.setFont(QFont("", _F))
        row("Chat ID", self._chatid_inp)

        btn_row = QHBoxLayout()
        self._enabled_chk = QCheckBox("채팅창 수신 활성화")
        self._enabled_chk.setFont(QFont("", _F))
        self._enabled_chk.setChecked(self._cfg.enabled)
        self._enabled_chk.setToolTip(
            "알람 자동 전송은 아래 개별 설정으로 제어됩니다.\n"
            "이 체크박스는 채팅창 수신 ON/OFF 전용입니다."
        )

        self._status_lbl = QLabel("")
        self._status_lbl.setFont(QFont("", _F))

        test_btn = QPushButton("연결 테스트")
        test_btn.setFont(QFont("", _F))
        test_btn.clicked.connect(self._test_connection)

        save_btn = QPushButton("저장")
        save_btn.setFont(QFont("", _F, QFont.Bold))
        save_btn.clicked.connect(self._save)

        btn_row.addWidget(self._enabled_chk)
        btn_row.addWidget(self._status_lbl)
        btn_row.addStretch()
        btn_row.addWidget(test_btn)
        btn_row.addWidget(save_btn)
        g.addLayout(btn_row)
        v.addWidget(grp_bot)

        # ── 알람 전송 설정
        grp_notify = QGroupBox("알람 전송 설정")
        grp_notify.setFont(QFont("", _F, QFont.Bold))
        gn = QVBoxLayout(grp_notify)

        self._chk_watch  = QCheckBox("감시패널 알람 전송")
        self._chk_sniper = QCheckBox("스나이퍼 알람 전송")
        self._chk_order  = QCheckBox("주문 체결 알람 전송")

        for chk, tag in [
            (self._chk_watch,  "watch_alert"),
            (self._chk_sniper, "sniper_alert"),
            (self._chk_order,  "order_confirm"),
        ]:
            chk.setChecked(self._cfg.notify_enabled(tag))
            chk.setFont(QFont("", _F))
            gn.addWidget(chk)

        v.addWidget(grp_notify)

        # ── 명령 수신 설정
        grp_cmd = QGroupBox("명령 수신 설정  ⚠️ 실제 주문이 실행됩니다")
        grp_cmd.setFont(QFont("", _F, QFont.Bold))
        gc = QVBoxLayout(grp_cmd)

        self._chk_order_rcv = QCheckBox("텔레그램 주문 수신 허용")
        self._chk_order_rcv.setFont(QFont("", _F))
        self._chk_order_rcv.setChecked(self._cfg.order_enabled)
        self._chk_order_rcv.setStyleSheet("QCheckBox { color: #dc2626; }")
        gc.addWidget(self._chk_order_rcv)

        warn = QLabel("※ 활성화 시 /buy /sell 명령으로 실제 주문이 실행됩니다.")
        warn.setFont(QFont("", 11))
        warn.setStyleSheet("QLabel { color:#dc2626; }")
        gc.addWidget(warn)

        v.addWidget(grp_cmd)
        v.addStretch()

    # ──────────────────────────────────────────
    def _save(self):
        self._cfg.token        = self._token_inp.text().strip()
        self._cfg.chat_id      = self._chatid_inp.text().strip()
        self._cfg.enabled      = self._enabled_chk.isChecked()
        self._cfg.set_notify("watch_alert",   self._chk_watch.isChecked())
        self._cfg.set_notify("sniper_alert",  self._chk_sniper.isChecked())
        self._cfg.set_notify("order_confirm", self._chk_order.isChecked())
        self._cfg.order_enabled = self._chk_order_rcv.isChecked()
        self._cfg.save()
        self._status_lbl.setText("저장 완료 ✓")
        self._status_lbl.setStyleSheet("QLabel { color:#16a34a; }")

    def _test_connection(self):
        self._cfg.token   = self._token_inp.text().strip()
        self._cfg.chat_id = self._chatid_inp.text().strip()
        result = TelegramClient.get().test_connection()
        ok = "성공" in result
        self._status_lbl.setText(result)
        color = "#16a34a" if ok else "#dc2626"
        self._status_lbl.setStyleSheet(f"QLabel {{ color:{color}; }}")
        self._chat.set_status(ok)


# ─────────────────────────────────────────────────────────────
# 최종 탭 위젯
# ─────────────────────────────────────────────────────────────
class TgConfigWidget(QWidget):
    """
    메인 탭바에 추가하는 [📡 텔레그램] 탭.
    사용:
        from telegram_bot.tg_config_widget import TgConfigWidget
        tab_widget.addTab(TgConfigWidget(), "📡 텔레그램")
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._register_callback()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ✅ Horizontal splitter — 채팅창 좌측 사이드바, 설정 우측
        splitter = QSplitter(Qt.Horizontal)

        self._chat_panel = _ChatPanel()
        self._chat_panel.setMinimumWidth(220)
        self._chat_panel.setMaximumWidth(300)  # 사이드바 너비 제한

        self._settings = _SettingsPanel(self._chat_panel)

        settings_wrap = QWidget()
        sw = QVBoxLayout(settings_wrap)
        sw.setContentsMargins(4, 4, 4, 0)
        sw.addWidget(self._settings)

        # 채팅창(좌) → 설정(우)
        splitter.addWidget(self._chat_panel)
        splitter.addWidget(settings_wrap)
        splitter.setSizes([260, 600])   # 초기 좌:우 비율
        splitter.setStretchFactor(0, 0) # 채팅창 고정
        splitter.setStretchFactor(1, 1) # 설정창이 창 크기에 따라 늘어남

        v.addWidget(splitter)

    def _register_callback(self):
        """TelegramClient 의 채팅 콜백으로 채팅창 연결."""
        TelegramClient.get().register_chat_callback(self._chat_panel.append)

    def closeEvent(self, event):
        TelegramClient.get().unregister_chat_callback(self._chat_panel.append)
        super().closeEvent(event)