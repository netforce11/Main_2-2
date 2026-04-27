"""
SPY 일봉 - 기준 요일 종가 대비 다음 거래일 하락 탐색기
의존성: pip install PyQt5 yfinance pandas
"""

import sys
import pandas as pd
import yfinance as yf
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QDoubleSpinBox, QDateEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QStatusBar, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPalette


# ── 요일 매핑 ────────────────────────────────────────────────
WEEKDAY_MAP = {
    "월요일": 0,
    "화요일": 1,
    "수요일": 2,
    "목요일": 3,
    "금요일": 4,
}

# ── 백그라운드 데이터 로드 스레드 ────────────────────────────
class FetchThread(QThread):
    result_ready = pyqtSignal(list)   # 결과 rows
    error_signal  = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, start_date, end_date, weekday_no, pct_threshold):
        super().__init__()
        self.start_date    = start_date      # str "YYYY-MM-DD"
        self.end_date      = end_date        # str "YYYY-MM-DD"
        self.weekday_no    = weekday_no      # int 0=월 … 4=금
        self.pct_threshold = pct_threshold  # float  e.g. 1.0

    def run(self):
        try:
            self.status_signal.emit("📥 SPY 데이터 다운로드 중…")

            # yfinance는 end_date 당일 미포함 → +3일 여유
            end_ext = (pd.Timestamp(self.end_date) + pd.Timedelta(days=3)).strftime("%Y-%m-%d")
            df = yf.download(
                "SPY",
                start=self.start_date,
                end=end_ext,
                auto_adjust=True,
                progress=False,
            )

            if df.empty:
                self.error_signal.emit("데이터를 가져올 수 없습니다. 날짜 범위를 확인하세요.")
                return

            # 컬럼 정리
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # 종료일 필터링
            df = df[df.index <= pd.Timestamp(self.end_date)]

            self.status_signal.emit(f"✅ {len(df)}개 거래일 로드 완료. 분석 중…")

            rows = []
            dates = df.index.tolist()

            for i, dt in enumerate(dates):
                # 기준 요일 체크
                if dt.weekday() != self.weekday_no:
                    continue

                base_close = float(df.loc[dt, "Close"])

                # 다음 거래일 찾기 (공휴일 자동 스킵 - yfinance엔 거래일만 있음)
                if i + 1 >= len(dates):
                    continue
                next_dt    = dates[i + 1]
                next_close = float(df.loc[next_dt, "Close"])
                next_open  = float(df.loc[next_dt, "Open"])
                next_high  = float(df.loc[next_dt, "High"])
                next_low   = float(df.loc[next_dt, "Low"])

                pct_chg = (next_close - base_close) / base_close * 100.0

                # 임계값 이상 하락 여부
                if pct_chg <= -self.pct_threshold:
                    rows.append({
                        "기준일":        dt.strftime("%Y-%m-%d"),
                        "기준요일":      ["월","화","수","목","금"][dt.weekday()],
                        "기준 종가":     round(base_close, 2),
                        "다음 거래일":   next_dt.strftime("%Y-%m-%d"),
                        "다음요일":      ["월","화","수","목","금"][next_dt.weekday()],
                        "시가":          round(next_open,  2),
                        "고가":          round(next_high,  2),
                        "저가":          round(next_low,   2),
                        "종가":          round(next_close, 2),
                        "변동(%)":       round(pct_chg,    2),
                    })

            self.result_ready.emit(rows)
            self.status_signal.emit(
                f"🔍 총 {len(rows)}건 발견 (기준: -{self.pct_threshold:.2f}% 이하)"
            )

        except Exception as e:
            self.error_signal.emit(f"오류 발생: {e}")


# ── 메인 윈도우 ──────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SPY 요일별 하락 탐색기")
        self.setMinimumSize(1050, 680)
        self._thread = None
        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ── 타이틀 ──────────────────────────────────────────
        title = QLabel("📊 SPY 일봉  ·  요일별 하락 탐색기")
        tf = QFont()
        tf.setPointSize(14)
        tf.setBold(True)
        title.setFont(tf)
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # ── 조건 패널 ────────────────────────────────────────
        grp = QGroupBox("검색 조건")
        grp_layout = QHBoxLayout(grp)
        grp_layout.setSpacing(16)

        # 기준 요일
        grp_layout.addWidget(QLabel("기준 요일:"))
        self.cb_weekday = QComboBox()
        self.cb_weekday.addItems(list(WEEKDAY_MAP.keys()))
        self.cb_weekday.setCurrentText("수요일")
        self.cb_weekday.setFixedWidth(90)
        grp_layout.addWidget(self.cb_weekday)

        # 하락 임계값
        grp_layout.addWidget(QLabel("하락 임계값 (%):"))
        self.sp_pct = QDoubleSpinBox()
        self.sp_pct.setRange(0.1, 20.0)
        self.sp_pct.setSingleStep(0.1)
        self.sp_pct.setValue(1.0)
        self.sp_pct.setDecimals(1)
        self.sp_pct.setFixedWidth(80)
        self.sp_pct.setToolTip("기준일 종가 대비 다음 거래일 종가 하락 %")
        grp_layout.addWidget(self.sp_pct)

        grp_layout.addSpacing(20)

        # 시작일
        grp_layout.addWidget(QLabel("시작일:"))
        self.de_start = QDateEdit()
        self.de_start.setCalendarPopup(True)
        self.de_start.setDate(QDate(2010, 1, 1))
        self.de_start.setDisplayFormat("yyyy-MM-dd")
        self.de_start.setFixedWidth(110)
        grp_layout.addWidget(self.de_start)

        # 종료일
        grp_layout.addWidget(QLabel("종료일:"))
        self.de_end = QDateEdit()
        self.de_end.setCalendarPopup(True)
        self.de_end.setDate(QDate.currentDate())
        self.de_end.setDisplayFormat("yyyy-MM-dd")
        self.de_end.setFixedWidth(110)
        grp_layout.addWidget(self.de_end)

        grp_layout.addSpacing(20)

        # 검색 버튼
        self.btn_search = QPushButton("🔍  검색")
        self.btn_search.setFixedHeight(34)
        self.btn_search.setFixedWidth(110)
        self.btn_search.setStyleSheet(
            "QPushButton { background:#1a73e8; color:white; border-radius:5px; font-size:13px; }"
            "QPushButton:hover { background:#1558b0; }"
            "QPushButton:disabled { background:#aaa; }"
        )
        self.btn_search.clicked.connect(self._on_search)
        grp_layout.addWidget(self.btn_search)

        # 초기화 버튼
        self.btn_clear = QPushButton("초기화")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.setFixedWidth(70)
        self.btn_clear.clicked.connect(self._on_clear)
        grp_layout.addWidget(self.btn_clear)

        grp_layout.addStretch()
        root.addWidget(grp)

        # ── 요약 레이블 ──────────────────────────────────────
        self.lbl_summary = QLabel("")
        self.lbl_summary.setAlignment(Qt.AlignRight)
        sf = QFont()
        sf.setPointSize(10)
        self.lbl_summary.setFont(sf)
        root.addWidget(self.lbl_summary)

        # ── 결과 테이블 ──────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        headers = [
            "기준일", "기준\n요일", "기준\n종가",
            "다음 거래일", "다음\n요일",
            "시가", "고가", "저가", "종가",
            "변동(%)",
        ]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        # 헤더 폰트
        hf = QFont()
        hf.setBold(True)
        self.table.horizontalHeader().setFont(hf)

        root.addWidget(self.table)

        # ── 상태바 ────────────────────────────────────────────
        self.statusBar().showMessage("조건을 설정하고 검색을 눌러주세요.")

    # ── 이벤트 핸들러 ────────────────────────────────────────
    def _on_search(self):
        # 날짜 검증
        start = self.de_start.date().toPyDate()
        end   = self.de_end.date().toPyDate()
        if start >= end:
            self.statusBar().showMessage("⚠ 시작일이 종료일보다 앞서야 합니다.")
            return

        weekday_no    = WEEKDAY_MAP[self.cb_weekday.currentText()]
        pct_threshold = self.sp_pct.value()

        self.btn_search.setEnabled(False)
        self.table.setRowCount(0)
        self.lbl_summary.setText("")

        self._thread = FetchThread(
            start_date    = start.strftime("%Y-%m-%d"),
            end_date      = end.strftime("%Y-%m-%d"),
            weekday_no    = weekday_no,
            pct_threshold = pct_threshold,
        )
        self._thread.result_ready.connect(self._on_result)
        self._thread.error_signal.connect(self._on_error)
        self._thread.status_signal.connect(lambda m: self.statusBar().showMessage(m))
        self._thread.finished.connect(lambda: self.btn_search.setEnabled(True))
        self._thread.start()

    def _on_clear(self):
        self.table.setRowCount(0)
        self.lbl_summary.setText("")
        self.statusBar().showMessage("초기화 완료.")

    def _on_result(self, rows):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            vals = [
                row["기준일"],
                row["기준요일"],
                f"{row['기준 종가']:,.2f}",
                row["다음 거래일"],
                row["다음요일"],
                f"{row['시가']:,.2f}",
                f"{row['고가']:,.2f}",
                f"{row['저가']:,.2f}",
                f"{row['종가']:,.2f}",
                f"{row['변동(%)']:+.2f}%",
            ]
            for c_idx, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)

                # 변동(%) 열 색상
                if c_idx == 9:
                    item.setForeground(QColor("#cc0000"))
                    item.setFont(self._bold_font())

                self.table.setItem(r_idx, c_idx, item)

        self.table.setSortingEnabled(True)

        # 요약
        if rows:
            avg_chg = sum(r["변동(%)"] for r in rows) / len(rows)
            self.lbl_summary.setText(
                f"총 <b>{len(rows)}</b>건 발견  |  평균 변동: "
                f"<b style='color:#cc0000'>{avg_chg:+.2f}%</b>"
            )
        else:
            self.lbl_summary.setText("검색 결과가 없습니다.")

    def _on_error(self, msg):
        self.statusBar().showMessage(f"❌ {msg}")

    @staticmethod
    def _bold_font():
        f = QFont()
        f.setBold(True)
        return f


# ── 진입점 ───────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 밝은 팔레트
    pal = QPalette()
    pal.setColor(QPalette.Window,          QColor("#f5f5f5"))
    pal.setColor(QPalette.WindowText,      QColor("#212121"))
    pal.setColor(QPalette.Base,            QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase,   QColor("#eef2fb"))
    pal.setColor(QPalette.Highlight,       QColor("#1a73e8"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())