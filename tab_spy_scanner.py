"""
tab_spy_scanner.py  —  SPY 요일별 하락 탐색기  (GridTab 버전)
════════════════════════════════════════════════════════════════
main.py 탭으로 붙이는 방법:
  from tab_spy_scanner import SpyScannerGrid
  add(SpyScannerGrid, "📉 SPY 탐색")   ← _init_ui 의 탭 등록부에 추가

데이터 경로: /home/netforce/US_Data/SPY/YYYYMM.csv  (1분봉)
의존성: PyQt5, pandas  (ibapi 불필요)
════════════════════════════════════════════════════════════════
"""

import os
import pandas as pd
import traceback

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QDoubleSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFrame, QCalendarWidget, QDialog, QDialogButtonBox,
    QLineEdit, QCheckBox, QStatusBar,
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal, QLocale
from PyQt5.QtGui import QColor, QFont

# core.py 의 GridTab import
from core import GridTab


# ── 설정 ─────────────────────────────────────────────────────
SPY_DATA_DIR = "/home/netforce/US_Data/SPY"

WEEKDAY_MAP = {
    "월요일": 0,
    "화요일": 1,
    "수요일": 2,
    "목요일": 3,
    "금요일": 4,
}
KO_DAY = ["월", "화", "수", "목", "금", "토", "일"]


# ── 로컬 CSV → 일봉 DataFrame ─────────────────────────────────
def load_daily_df(start_date: str, end_date: str) -> pd.DataFrame:
    """YYYYMM.csv 1분봉 파일들을 읽어 일봉 OHLC DataFrame 반환."""
    s = pd.Timestamp(start_date)
    e = pd.Timestamp(end_date)

    months = pd.period_range(
        start=s.to_period("M"), end=e.to_period("M"), freq="M"
    )

    frames = []
    for period in months:
        fpath = os.path.join(SPY_DATA_DIR, f"{period.strftime('%Y%m')}.csv")
        if not os.path.exists(fpath):
            print(f"[SPY탐색] 파일 없음: {fpath}")
            continue
        try:
            with open(fpath, "r") as f:
                first_line = f.readline()
            if "," in first_line:
                sep = ","
            elif "\t" in first_line:
                sep = "\t"
            else:
                sep = r"\s+"

            df = pd.read_csv(fpath, sep=sep, header=0, engine="python")
            df.columns = [c.strip().lower() for c in df.columns]
            print(f"[SPY탐색] {os.path.basename(fpath)}  컬럼: {list(df.columns)}  행수: {len(df)}")
            frames.append(df)
        except Exception as ex:
            print(f"[SPY탐색] {fpath} 읽기 실패: {ex}")

    if not frames:
        return pd.DataFrame()

    raw = pd.concat(frames, ignore_index=True)

    # 타임스탬프 컬럼 탐색
    ts_col = next((c for c in ["t", "timestamp", "time", "ts"] if c in raw.columns), None)
    if ts_col is None:
        raise ValueError(f"타임스탬프 컬럼 없음. 실제 컬럼: {list(raw.columns)}")

    # OHLCV 컬럼 매핑
    col_map = {}
    for need, candidates in {
        "o": ["o", "open"],
        "h": ["h", "high"],
        "l": ["l", "low"],
        "c": ["c", "close"],
        "v": ["v", "volume"],
    }.items():
        for cand in candidates:
            if cand in raw.columns:
                col_map[need] = cand
                break
        if need not in col_map:
            raise ValueError(f"'{need}' 컬럼 없음. 실제 컬럼: {list(raw.columns)}")

    raw["dt"]   = pd.to_datetime(raw[ts_col], unit="ms", utc=True)
    raw["dt"]   = raw["dt"].dt.tz_convert("America/New_York")
    raw["date"] = raw["dt"].dt.date
    raw         = raw.sort_values("dt")

    daily = raw.groupby("date").agg(
        open  =(col_map["o"], "first"),
        high  =(col_map["h"], "max"),
        low   =(col_map["l"], "min"),
        close =(col_map["c"], "last"),
        volume=(col_map["v"], "sum"),
    ).reset_index()

    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily[(daily["date"] >= s) & (daily["date"] <= e)]
    daily = daily.sort_values("date").reset_index(drop=True)
    return daily


# ── 캘린더 다이얼로그 ─────────────────────────────────────────
class _CalendarDialog(QDialog):
    def __init__(self, current_date: QDate, parent=None, title="날짜 선택"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(340, 300)
        layout = QVBoxLayout(self)
        self.cal = QCalendarWidget()
        self.cal.setGridVisible(True)
        self.cal.setSelectedDate(current_date)
        self.cal.setLocale(QLocale(QLocale.Korean, QLocale.SouthKorea))
        self.cal.activated.connect(lambda _: self.accept())
        layout.addWidget(self.cal)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_date(self) -> QDate:
        return self.cal.selectedDate()


# ── 날짜 버튼 위젯 ────────────────────────────────────────────
class _DateButton(QPushButton):
    def __init__(self, default_date: QDate, title="날짜 선택", parent=None):
        super().__init__(parent)
        self._date  = default_date
        self._title = title
        self._refresh()
        self.setFixedWidth(130)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "QPushButton{background:#fff;border:1px solid #aaa;"
            "border-radius:4px;padding:2px 8px;text-align:left;font-size:11px;}"
            "QPushButton:hover{border:1px solid #1a73e8;color:#1a73e8;}"
        )
        self.clicked.connect(self._open)

    def _refresh(self):
        self.setText(f"📅 {self._date.toString('yyyy-MM-dd')}")

    def _open(self):
        dlg = _CalendarDialog(self._date, self, self._title)
        if dlg.exec_() == QDialog.Accepted:
            self._date = dlg.selected_date()
            self._refresh()

    def get_str(self) -> str:
        return self._date.toString("yyyy-MM-dd")


# ── 분석 스레드 ───────────────────────────────────────────────
class _AnalyzeThread(QThread):
    result_ready  = pyqtSignal(list)
    error_signal  = pyqtSignal(str)
    status_signal = pyqtSignal(str)

    def __init__(self, start_date, end_date, weekday_no, pct, use_low, use_close):
        super().__init__()
        self.start_date = start_date
        self.end_date   = end_date
        self.weekday_no = weekday_no
        self.pct        = pct
        self.use_low    = use_low
        self.use_close  = use_close

    def run(self):
        try:
            self.status_signal.emit("📂 로컬 CSV 로딩 중…")
            df = load_daily_df(self.start_date, self.end_date)

            if df.empty:
                self.error_signal.emit(f"데이터 없음 → 경로 확인: {SPY_DATA_DIR}")
                return

            self.status_signal.emit(f"✅ {len(df)}개 거래일 로드. 분석 중…")

            rows  = []
            dates = df["date"].tolist()

            for i, dt in enumerate(dates):
                if dt.weekday() != self.weekday_no:
                    continue
                if i + 1 >= len(dates):
                    continue

                base_close = float(df.loc[i, "close"])
                nr         = df.iloc[i + 1]
                next_dt    = dates[i + 1]
                next_low   = float(nr["low"])
                next_close = float(nr["close"])

                pct_low   = (next_low   - base_close) / base_close * 100.0
                pct_close = (next_close - base_close) / base_close * 100.0

                hit_low   = self.use_low   and pct_low   <= -self.pct
                hit_close = self.use_close and pct_close <= -self.pct

                if hit_low or hit_close:
                    rows.append({
                        "기준일":      dt.strftime("%Y-%m-%d"),
                        "기준요일":    KO_DAY[dt.weekday()],
                        "기준종가":    round(base_close,        2),
                        "다음거래일":  next_dt.strftime("%Y-%m-%d"),
                        "다음요일":    KO_DAY[next_dt.weekday()],
                        "시가":        round(float(nr["open"]),  2),
                        "고가":        round(float(nr["high"]),  2),
                        "저가":        round(next_low,           2),
                        "종가":        round(next_close,         2),
                        "저가변동(%)": round(pct_low,            2),
                        "종가변동(%)": round(pct_close,          2),
                        "저가hit":     hit_low,
                        "종가hit":     hit_close,
                    })

            self.result_ready.emit(rows)
            self.status_signal.emit(
                f"🔍 총 {len(rows)}건 발견  (임계: -{self.pct:.1f}% 이하)"
            )
        except Exception as e:
            self.error_signal.emit(f"오류: {e}\n{traceback.format_exc()}")


# ══════════════════════════════════════════════════════════════
# GridTab 기반 메인 위젯
# ══════════════════════════════════════════════════════════════
class SpyScannerGrid(GridTab):
    """
    SPY 요일별 하락 탐색기 — GridTab 버전.
    main.py 에서 add(SpyScannerGrid, "📉 SPY 탐색") 으로 등록.
    IBKR 연결 불필요.
    """

    def __init__(self, main_win=None):
        super().__init__()
        self._main   = main_win
        self._thread = None
        self._build()

    # ── UI 구성 ──────────────────────────────────────────────
    def _build(self):
        # GridTab 은 QGridLayout 기반 → 내부에 QWidget 컨테이너로 래핑
        container = QWidget()
        root = QVBoxLayout(container)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 6)

        # ── 헤더 ─────────────────────────────────────────────
        hdr = QLabel("📉  SPY 일봉  ·  요일별 하락 탐색기")
        hf = QFont(); hf.setPointSize(13); hf.setBold(True)
        hdr.setFont(hf)
        hdr.setAlignment(Qt.AlignCenter)
        root.addWidget(hdr)

        path_lbl = QLabel(f"데이터:  {SPY_DATA_DIR}/YYYYMM.csv")
        path_lbl.setAlignment(Qt.AlignCenter)
        path_lbl.setStyleSheet("color:#888;font-size:10px;border:none;")
        root.addWidget(path_lbl)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        # ── 검색 제목 ────────────────────────────────────────
        title_row = QHBoxLayout()
        lbl_sname = QLabel("검색 제목:")
        tf = QFont(); tf.setBold(True)
        lbl_sname.setFont(tf)
        lbl_sname.setFixedWidth(70)
        lbl_sname.setStyleSheet("border:none;")
        title_row.addWidget(lbl_sname)

        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("예) 메가 써스데이")
        self.edit_title.setFixedHeight(30)
        self.edit_title.setMaximumWidth(280)
        self.edit_title.setStyleSheet(
            "QLineEdit{border:1px solid #aaa;border-radius:4px;"
            "padding:2px 8px;font-size:12px;}"
            "QLineEdit:focus{border:1px solid #1a73e8;}"
        )
        title_row.addWidget(self.edit_title)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── 조건 패널 ────────────────────────────────────────
        grp = QGroupBox("검색 조건")
        row = QHBoxLayout(grp)
        row.setSpacing(10)

        row.addWidget(QLabel("기준 요일:"))
        self.cb_weekday = QComboBox()
        self.cb_weekday.addItems(list(WEEKDAY_MAP.keys()))
        self.cb_weekday.setCurrentText("수요일")
        self.cb_weekday.setFixedWidth(88)
        row.addWidget(self.cb_weekday)

        row.addSpacing(6)
        row.addWidget(QLabel("하락 임계값(%):"))
        self.sp_pct = QDoubleSpinBox()
        self.sp_pct.setRange(0.1, 20.0)
        self.sp_pct.setSingleStep(0.1)
        self.sp_pct.setValue(1.0)
        self.sp_pct.setDecimals(1)
        self.sp_pct.setFixedWidth(72)
        row.addWidget(self.sp_pct)

        row.addSpacing(8)
        sep_v = QFrame(); sep_v.setFrameShape(QFrame.VLine); sep_v.setFrameShadow(QFrame.Sunken)
        row.addWidget(sep_v)

        row.addWidget(QLabel("비교 기준:"))
        self.chk_low = QCheckBox("다음날 저가")
        self.chk_low.setChecked(True)
        self.chk_low.setStyleSheet("font-size:11px;")
        row.addWidget(self.chk_low)

        self.chk_close = QCheckBox("다음날 종가")
        self.chk_close.setChecked(True)
        self.chk_close.setStyleSheet("font-size:11px;")
        row.addWidget(self.chk_close)

        row.addSpacing(8)
        sep_v2 = QFrame(); sep_v2.setFrameShape(QFrame.VLine); sep_v2.setFrameShadow(QFrame.Sunken)
        row.addWidget(sep_v2)

        row.addWidget(QLabel("시작일:"))
        self.btn_start = _DateButton(QDate(2022, 1, 1), "시작일 선택")
        row.addWidget(self.btn_start)

        row.addSpacing(4)
        row.addWidget(QLabel("종료일:"))
        self.btn_end = _DateButton(QDate.currentDate(), "종료일 선택")
        row.addWidget(self.btn_end)

        row.addSpacing(12)

        self.btn_search = QPushButton("🔍 검색")
        self.btn_search.setFixedSize(100, 32)
        self.btn_search.setStyleSheet(
            "QPushButton{background:#1a73e8;color:white;border-radius:5px;"
            "font-size:12px;font-weight:bold;border:none;}"
            "QPushButton:hover{background:#1558b0;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self.btn_search.clicked.connect(self._on_search)
        row.addWidget(self.btn_search)

        self.btn_clear = QPushButton("초기화")
        self.btn_clear.setFixedSize(65, 32)
        self.btn_clear.setStyleSheet("border-radius:4px;")
        self.btn_clear.clicked.connect(self._on_clear)
        row.addWidget(self.btn_clear)

        row.addStretch()
        root.addWidget(grp)

        # ── 결과 제목 + 요약 ─────────────────────────────────
        sum_row = QHBoxLayout()
        self.lbl_result_title = QLabel("")
        rf = QFont(); rf.setPointSize(11); rf.setBold(True)
        self.lbl_result_title.setFont(rf)
        self.lbl_result_title.setStyleSheet("color:#1a73e8;border:none;")
        sum_row.addWidget(self.lbl_result_title)
        sum_row.addStretch()
        self.lbl_summary = QLabel("")
        self.lbl_summary.setAlignment(Qt.AlignRight)
        self.lbl_summary.setStyleSheet("border:none;")
        sum_row.addWidget(self.lbl_summary)
        root.addLayout(sum_row)

        # ── 결과 테이블 ──────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "기준일", "기준\n요일", "기준\n종가",
            "다음 거래일", "다음\n요일",
            "시가", "고가", "저가", "종가",
            "저가\n변동(%)", "종가\n변동(%)",
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdf = QFont(); hdf.setBold(True)
        hh.setFont(hdf)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        root.addWidget(self.table)

        # ── 상태바 (탭 내부 전용 QLabel) ─────────────────────
        self.lbl_status = QLabel("조건을 설정하고 검색 버튼을 눌러주세요.")
        self.lbl_status.setStyleSheet(
            "background:#f0f0f0;border-top:1px solid #ccc;"
            "padding:3px 8px;font-size:10px;color:#444;"
        )
        root.addWidget(self.lbl_status)

        # GridTab 의 add() 로 컨테이너 삽입 (row=1, col=1, rowspan=1, colspan=12)
        self.add(container, 1, 1, 1, 12)

    # ── 상태 메시지 헬퍼 ─────────────────────────────────────
    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)

    # ── 핸들러 ───────────────────────────────────────────────
    def _on_search(self):
        s = self.btn_start.get_str()
        e = self.btn_end.get_str()

        if s >= e:
            self._set_status("⚠  시작일이 종료일보다 앞서야 합니다.")
            return

        use_low   = self.chk_low.isChecked()
        use_close = self.chk_close.isChecked()
        if not use_low and not use_close:
            self._set_status("⚠  비교 기준을 하나 이상 선택해주세요.")
            return

        self.btn_search.setEnabled(False)
        self.table.setRowCount(0)
        self.lbl_summary.setText("")
        self.lbl_result_title.setText("")

        self._thread = _AnalyzeThread(
            start_date = s,
            end_date   = e,
            weekday_no = WEEKDAY_MAP[self.cb_weekday.currentText()],
            pct        = self.sp_pct.value(),
            use_low    = use_low,
            use_close  = use_close,
        )
        self._thread.result_ready.connect(self._on_result)
        self._thread.error_signal.connect(self._on_error)
        self._thread.status_signal.connect(lambda m: self._set_status(m))
        self._thread.finished.connect(lambda: self.btn_search.setEnabled(True))
        self._thread.start()

    def _on_clear(self):
        self.table.setRowCount(0)
        self.lbl_summary.setText("")
        self.lbl_result_title.setText("")
        self._set_status("초기화 완료.")

    def _on_result(self, rows):
        search_title = self.edit_title.text().strip()
        if search_title:
            self.lbl_result_title.setText(f"🔖  {search_title}")

        use_low   = self.chk_low.isChecked()
        use_close = self.chk_close.isChecked()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        bold     = QFont(); bold.setBold(True)
        red      = QColor("#cc0000")
        green_bg = QColor("#e8f5e9")

        for r, row in enumerate(rows):
            vals = [
                row["기준일"],
                row["기준요일"],
                f"{row['기준종가']:,.2f}",
                row["다음거래일"],
                row["다음요일"],
                f"{row['시가']:,.2f}",
                f"{row['고가']:,.2f}",
                f"{row['저가']:,.2f}",
                f"{row['종가']:,.2f}",
                f"{row['저가변동(%)']:+.2f}%",
                f"{row['종가변동(%)']:+.2f}%",
            ]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                if c == 9:
                    item.setFont(bold)
                    item.setForeground(red if row["저가hit"] else QColor("#999"))
                    if row["저가hit"]:
                        item.setBackground(green_bg)
                elif c == 10:
                    item.setFont(bold)
                    item.setForeground(red if row["종가hit"] else QColor("#999"))
                    if row["종가hit"]:
                        item.setBackground(green_bg)
                self.table.setItem(r, c, item)

        self.table.setSortingEnabled(True)

        if rows:
            cnt        = len(rows)
            low_hits   = sum(1 for r in rows if r["저가hit"])
            close_hits = sum(1 for r in rows if r["종가hit"])
            avg_low    = sum(r["저가변동(%)"]  for r in rows) / cnt
            avg_close  = sum(r["종가변동(%)"] for r in rows) / cnt
            parts = [f"총 <b>{cnt}</b>건"]
            if use_low:
                parts.append(
                    f"저가 달성 <b style='color:#cc0000'>{low_hits}</b>건 "
                    f"(평균 <b style='color:#cc0000'>{avg_low:+.2f}%</b>)"
                )
            if use_close:
                parts.append(
                    f"종가 달성 <b style='color:#e65c00'>{close_hits}</b>건 "
                    f"(평균 <b style='color:#e65c00'>{avg_close:+.2f}%</b>)"
                )
            self.lbl_summary.setText("  |  ".join(parts))
        else:
            self.lbl_summary.setText("조건에 해당하는 결과가 없습니다.")

    def _on_error(self, msg):
        self._set_status(f"❌  {msg}")
        self.lbl_summary.setText(f"<span style='color:red'>{msg}</span>")

    # ── GridTab 생명주기 훅 (선택적) ─────────────────────────
    def on_tab_activate(self):
        """탭 활성화 시 호출 (main.py _on_tab_changed)."""
        pass

    def on_tab_deactivate(self):
        """탭 비활성화 시 호출."""
        pass
