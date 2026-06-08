"""
chart_capture.py — 차트 캡처 기능
[분리] chart_markers.py 에서 분리 (capture_chart)
"""
import platform as _platform
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import QMessageBox

if _platform.system() == "Windows":
    CAPTURE_DIR = Path(r"C:\data\chart_save")
else:
    CAPTURE_DIR = Path("/home/netforce/US_Data/chart_save")

def capture_chart(self):
    """
    📷 차트 영역(gfx 위젯)만 캡쳐 → C:\\data\\chart_save\\ 저장.
    파일명: {조회날짜}_{캡쳐시각}_{심볼}.png
    예)    20260413_143022_SPY.png
    """
    if not PG or not hasattr(self, 'gfx'):
        QMessageBox.warning(self, "캡쳐 불가", "차트가 초기화되지 않았습니다.")
        return

    try:
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        QMessageBox.critical(self, "캡쳐 오류", f"저장 폴더 생성 실패:\n{e}")
        return

    # 파일명 구성
    chart_date = (self.selected_date.strftime("%Y%m%d")
                  if self.selected_date else
                  datetime.now().strftime("%Y%m%d"))
    capture_ts = datetime.now().strftime("%H%M%S")
    sym        = getattr(self, 'current_sym', 'chart').upper()
    fname      = f"{chart_date}_{capture_ts}_{sym}.png"
    fpath      = CAPTURE_DIR / fname

    try:
        # gfx 위젯 전체를 QPixmap으로 grab
        pixmap = self.gfx.grab()
        if pixmap.isNull():
            QMessageBox.warning(self, "캡쳐 오류", "빈 이미지가 반환되었습니다.")
            return
        pixmap.save(str(fpath), "PNG")
        if hasattr(self, 'lbl_hline_info'):
            self.lbl_hline_info.setText(f"📷 캡쳐 저장: {fname}")
        print(f"[ChartCapture] 저장 완료: {fpath}")
    except Exception as e:
        QMessageBox.critical(self, "캡쳐 오류", f"저장 실패:\n{e}")
