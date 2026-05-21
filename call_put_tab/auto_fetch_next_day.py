"""
auto_fetch_next_day.py  —  AutoFetchNextDayMixin
────────────────────────────────────────────────
사이드바 [기초자산] 패널 하단 빈 공간에
"D+1 옵션 자동 조회" 시간 설정 위젯을 추가한다.

설정한 시각이 되면 D+1 만기(다음 거래일) SPXW 콜-풋 체인을
자동으로 조회한다.

통합 방법
─────────
1. CallPutGrid 상속 목록에 AutoFetchNextDayMixin 추가
2. _build_watchlist_panel() 또는 _build_layout_group() 직후
   self._build_auto_fetch_panel()  호출 추가
3. _connect_signals() 내부에서
   self._af_timer.timeout.connect(self._af_tick)  연결 추가
   (또는 _build_auto_fetch_panel 내부에서 직접 연결 — 아래 코드 참고)

의존 항목
─────────
- PyQt5 (QGroupBox, QHBoxLayout, QVBoxLayout, QTimeEdit, QCheckBox,
          QLabel, QTimer, QPushButton)
- core.py 내 build_next_trading_day(date) 또는 아래 로컬 구현 사용
- _on_spxw_select() 또는 (edit_sym, combo_exp, date_edit) 직접 조작
- _fetch() : 옵션 체인 조회 함수
- _log()   : 하단 로그 박스 출력
"""

from __future__ import annotations

import datetime
from typing import Optional

from PyQt5.QtCore import QTime, QTimer, Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

# ──────────────────────────────────────────────
# 헬퍼: 다음 거래일 계산 (core.py 에 이미 있으면 import 로 교체)
# ──────────────────────────────────────────────

def _now_kst() -> datetime.datetime:
    """KST(UTC+9) 기준 현재 datetime 반환 (pytz 불필요)."""
    from datetime import timezone, timedelta
    KST = timezone(timedelta(hours=9))
    return datetime.datetime.now(tz=KST)


def _today_kst() -> datetime.date:
    """KST 기준 오늘 날짜 반환."""
    return _now_kst().date()


def _next_trading_day(ref: Optional[datetime.date] = None) -> datetime.date:
    """ref(기본: KST 오늘) 기준 다음 미국 증시 거래일 반환 (토→월, 일→월)."""
    if ref is None:
        ref = _today_kst()
    nxt = ref + datetime.timedelta(days=1)
    while nxt.weekday() >= 5:          # 5=토, 6=일
        nxt += datetime.timedelta(days=1)
    return nxt


def _date_to_expiry_str(d: datetime.date) -> str:
    """YYYYMMDD 문자열 반환 (IBKR 만기 형식)."""
    return d.strftime("%Y%m%d")


# ──────────────────────────────────────────────
# Mixin
# ──────────────────────────────────────────────

class AutoFetchNextDayMixin:
    """
    사이드바 기초자산 패널 아래에 D+1 자동 조회 설정 패널을 추가하는 Mixin.

    사용하는 self 속성 (CallPutGrid 가 제공해야 함)
    ─────────────────────────────────────────────
    edit_sym      : QLineEdit  — 현재 종목 (예: "SPXW")
    combo_exp     : QComboBox  — 만기 콤보
    date_edit     : QDateEdit  — CUSTOM 날짜 입력
    _fetch        : callable   — 옵션 체인 조회
    _log          : callable   — 로그 출력
    _on_spxw_select (선택)     — SPXW 날짜 설정 편의 함수

    추가되는 self 속성
    ──────────────────
    _af_enabled   : bool       — 자동 조회 ON/OFF
    _af_target    : QTime      — 목표 시각 (현지 시각 기준)
    _af_fired     : bool       — 오늘 이미 실행됐는지 여부
    _af_timer     : QTimer     — 1분 주기 체크 타이머
    _af_panel     : QGroupBox  — 사이드바에 삽입되는 패널 위젯
    """

    # ── 초기화 ────────────────────────────────

    def _init_auto_fetch(self) -> None:
        """__init__ 말미에 호출."""
        self._af_enabled: bool = True
        self._af_target: QTime = QTime(4, 30)    # 기본값 04:30
        self._af_fired: bool = False
        self._af_last_fired_date: Optional[datetime.date] = None

        self._af_timer = QTimer(self)
        self._af_timer.setInterval(30_000)        # 30초마다 체크
        self._af_timer.timeout.connect(self._af_tick)
        self._af_timer.start()

    # ── UI 빌더 ──────────────────────────────

    def _build_auto_fetch_panel(self) -> QGroupBox:
        """
        사이드바에 삽입할 GroupBox 위젯을 생성·반환한다.
        호출부에서 반환값을 사이드바 레이아웃에 addWidget() 하면 된다.

        예)
            panel = self._build_auto_fetch_panel()
            side_layout.addWidget(panel)
        """
        grp = QGroupBox("⏰ D+1 자동 조회")
        grp.setStyleSheet("""
            QGroupBox {
                font-size: 11px;
                font-weight: bold;
                color: #a0c8ff;
                border: 1px solid #2a4060;
                border-radius: 4px;
                margin-top: 6px;
                padding-top: 4px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
            }
        """)

        vbox = QVBoxLayout(grp)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        # ── 1행: 체크박스 + 시간 입력 ─────────
        row1 = QHBoxLayout()

        self._af_chk = QCheckBox("자동 조회")
        self._af_chk.setStyleSheet("font-size: 11px; color: #d0e8ff;")
        self._af_chk.setToolTip("체크 시 지정 시각에 D+1 만기 옵션 체인 자동 조회")
        self._af_chk.setChecked(True)                # ← 기본값 체크
        self._af_chk.toggled.connect(self._af_on_toggle)
        row1.addWidget(self._af_chk)

        self._af_time_edit = QTimeEdit()
        self._af_time_edit.setDisplayFormat("HH:mm")
        self._af_time_edit.setTime(self._af_target)
        self._af_time_edit.setFixedWidth(58)
        self._af_time_edit.setStyleSheet("""
            QTimeEdit {
                background: #0d1f33;
                color: #7ecfff;
                border: 1px solid #1e4070;
                border-radius: 3px;
                font-size: 12px;
                padding: 1px 3px;
            }
        """)
        self._af_time_edit.timeChanged.connect(self._af_on_time_changed)
        row1.addWidget(self._af_time_edit)
        row1.addStretch()
        vbox.addLayout(row1)

        # ── 2행: 상태 레이블 ──────────────────
        self._af_status_lbl = QLabel("대기 중")
        self._af_status_lbl.setStyleSheet(
            "font-size: 10px; color: #607080; padding-left: 2px;"
        )
        vbox.addWidget(self._af_status_lbl)

        # ── 3행: 지금 즉시 실행 버튼 ──────────
        self._af_btn_now = QPushButton("▶ D+1 지금 조회")
        self._af_btn_now.setFixedHeight(22)
        self._af_btn_now.setStyleSheet("""
            QPushButton {
                background: #0e2a44;
                color: #5ab4ff;
                border: 1px solid #1e5080;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover { background: #163d60; color: #88ccff; }
            QPushButton:pressed { background: #0a1e30; }
        """)
        self._af_btn_now.setToolTip("D+1 만기 옵션 체인 즉시 조회")
        self._af_btn_now.clicked.connect(self._af_do_fetch)
        vbox.addWidget(self._af_btn_now)

        self._af_panel = grp
        return grp

    # ── 슬롯 ─────────────────────────────────

    def _af_on_toggle(self, checked: bool) -> None:
        self._af_enabled = checked
        if checked:
            # 활성화 시 오늘(KST) 이미 실행했으면 내일 실행 대기로 리셋
            today = _today_kst()
            if self._af_last_fired_date == today:
                self._af_status_lbl.setText("오늘 이미 실행됨 · 내일 대기")
            else:
                t = self._af_time_edit.time()
                self._af_status_lbl.setText(
                    f"⏳ {t.toString('HH:mm')} D+1 조회 대기 중"
                )
            self._log(
                f"[AutoFetch] D+1 자동 조회 활성화 — "
                f"{self._af_time_edit.time().toString('HH:mm')} 에 실행 예정"
            )
        else:
            self._af_status_lbl.setText("비활성")
            self._log("[AutoFetch] D+1 자동 조회 비활성화")

    def _af_on_time_changed(self, t: QTime) -> None:
        self._af_target = t
        # 시간이 바뀌면 오늘 실행 플래그 초기화 (재실행 허용)
        self._af_last_fired_date = None
        if self._af_enabled:
            self._af_status_lbl.setText(
                f"⏳ {t.toString('HH:mm')} D+1 조회 대기 중"
            )

    def _af_tick(self) -> None:
        """30초마다 호출. 지정 시각 도달 여부 확인 (KST 기준)."""
        if not self._af_enabled:
            return

        now_kst = _now_kst()
        today = now_kst.date()

        # 오늘 이미 실행했으면 skip
        if self._af_last_fired_date == today:
            return

        # KST 현재 시각을 QTime 으로 변환
        now = QTime(now_kst.hour, now_kst.minute, now_kst.second)

        # 목표 시각 ±90초 이내면 실행
        target = self._af_target
        diff = abs(now.secsTo(target))
        within_window = diff <= 90

        if within_window:
            self._log(
                f"[AutoFetch] 지정 시각 도달 ({target.toString('HH:mm')}) "
                f"→ D+1 만기 체인 자동 조회 시작"
            )
            self._af_last_fired_date = today
            self._af_do_fetch()

    def _af_do_fetch(self) -> None:
        """D+1 만기를 설정하고 _fetch() 호출."""
        next_day = _next_trading_day()           # KST 기준 다음 거래일
        expiry_str = _date_to_expiry_str(next_day)   # YYYYMMDD

        self._log(
            f"[AutoFetch] D+1 만기 = {next_day.strftime('%Y-%m-%d')} "
            f"({expiry_str}) 체인 조회"
        )

        # ── 종목 고정 ─────────────────────────
        # SPXW 이외 종목을 쓰는 경우: edit_sym.text() 유지
        # 필요하면 아래 줄을 주석 해제
        # self.edit_sym.setText("SPXW")

        # ── 만기 설정 ─────────────────────────
        self._af_set_expiry(next_day)

        # ── 체인 조회 ─────────────────────────
        QTimer.singleShot(200, self._fetch)

        # ── 상태 업데이트 (KST 시각 표시) ────
        now_str = _now_kst().strftime("%H:%M")
        self._af_status_lbl.setText(
            f"✅ {now_str} "
            f"D+1({next_day.strftime('%m/%d')}) 조회 완료"
        )
        self._af_status_lbl.setStyleSheet(
            "font-size: 10px; color: #44cc88; padding-left: 2px;"
        )
        QTimer.singleShot(
            3000,
            lambda: self._af_status_lbl.setStyleSheet(
                "font-size: 10px; color: #607080; padding-left: 2px;"
            ),
        )

    def _af_set_expiry(self, target_date: datetime.date) -> None:
        """
        combo_exp 에서 CUSTOM 항목을 찾아 선택하고
        date_edit 에 target_date 를 입력한다.

        기존 _on_exp_change() 가 CUSTOM 선택 시 date_edit 표시를 처리하므로
        여기서는 콤보 인덱스만 바꾸고 date_edit 값만 설정한다.
        """
        from PyQt5.QtCore import QDate

        # combo_exp 에서 "CUSTOM" 텍스트가 포함된 항목 인덱스 탐색
        cb = self.combo_exp
        custom_idx = -1
        for i in range(cb.count()):
            if "CUSTOM" in cb.itemText(i).upper():
                custom_idx = i
                break

        if custom_idx == -1:
            # CUSTOM 항목이 없으면 마지막 인덱스 사용 (폴백)
            custom_idx = cb.count() - 1
            self._log(
                "[AutoFetch] ⚠ combo_exp 에 CUSTOM 항목 없음 — "
                f"인덱스 {custom_idx} 선택"
            )

        cb.setCurrentIndex(custom_idx)

        # date_edit 에 날짜 설정
        qdate = QDate(target_date.year, target_date.month, target_date.day)
        self.date_edit.setDate(qdate)

    # ── 설정 저장/복원 (SettingsMixin 연동) ──

    def _af_get_settings(self) -> dict:
        """_get_extra_settings() 확장용. 호출부에서 dict 에 merge 하면 된다."""
        return {
            "af_enabled": self._af_enabled,
            "af_time": self._af_target.toString("HH:mm"),
        }

    def _af_apply_settings(self, d: dict) -> None:
        """_apply_extra_settings() 확장용."""
        if "af_time" in d:
            t = QTime.fromString(d["af_time"], "HH:mm")
            if t.isValid():
                self._af_time_edit.setTime(t)
        # 저장값 없을 때 기본값 True (체크 유지)
        enabled = d.get("af_enabled", True)
        self._af_chk.setChecked(enabled)
