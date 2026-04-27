"""
watchlist_font_patch.py — 관심종목 패널 폰트 +3 패치  [참고용]
════════════════════════════════════════════════════════════════
core_fetch.py 의 _build_watchlist_panel() 내
QListWidget 폰트 설정 부분을 아래와 같이 수정하세요.

【적용 방법】
core_fetch.py 파일을 열어 _build_watchlist_panel() 함수를 찾고,
아래 패턴으로 수정합니다.
════════════════════════════════════════════════════════════════
"""

# ── 수정 전 (기존 코드 패턴) ────────────────────────────────
# self.list_watch = QListWidget()
# self.list_watch.setStyleSheet(
#     "QListWidget{background:#05050f;color:#dde0f0;"
#     "font-size:13px;border:1px solid #2a2a5a;}"   ← 기존 사이즈 예시
#     ...)

# ── 수정 후 (폰트 +3 적용) ──────────────────────────────────
# 기존 font-size 에 +3 을 더합니다 (예: 13px → 16px)
#
# self.list_watch = QListWidget()
# self.list_watch.setStyleSheet(
#     "QListWidget{background:#05050f;color:#dde0f0;"
#     "font-size:16px;border:1px solid #2a2a5a;}"   ← +3 적용
#     ...)
#
# 또는 QFont 를 직접 설정하는 방식:
# from PyQt5.QtGui import QFont
# fnt = self.list_watch.font()
# fnt.setPointSize(fnt.pointSize() + 3)
# self.list_watch.setFont(fnt)

# ── 범용 런타임 패치 함수 (core_fetch.py 수정 없이 적용 가능) ──
# CallPutGrid.__init__ 또는 _on_connected 에서 호출하면 됩니다.

def patch_watchlist_font(grid_instance, delta: int = 3):
    """
    CallPutGrid 인스턴스의 list_watch 폰트를 런타임에 +delta 키웁니다.
    core_fetch.py 수정 없이 tab_options.py 에서 호출 가능.

    사용 예 (tab_options.py CallPutGrid.__init__ 말미):
        from watchlist_font_patch import patch_watchlist_font
        patch_watchlist_font(self, delta=3)
    """
    from PyQt5.QtGui import QFont
    widget = getattr(grid_instance, 'list_watch', None)
    if widget is None:
        return
    fnt: QFont = widget.font()
    current_pt = fnt.pointSize()
    if current_pt <= 0:
        # pixelSize 방식으로 설정된 경우
        px = widget.fontMetrics().height()
        fnt.setPixelSize(px + delta)
    else:
        fnt.setPointSize(current_pt + delta)
    widget.setFont(fnt)
