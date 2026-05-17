"""
chart_build_handlers.py — 테이블/패널 토글 핸들러
[분리] chart_build_main.py 에서 분리
  _on_order_panel_toggle()
  _toggle_table_panel()
"""
import os as _os, sys as _sys
_here = _os.path.dirname(_os.path.abspath(__file__))
if _here not in _sys.path:
    _sys.path.insert(0, _here)

from PyQt5.QtWidgets import QCheckBox

# ── [피뢰침 포착 비활성화] _on_order_panel_toggle ─────────────
# 조건부 주문 패널(피뢰침 포착) 토글 핸들러 — 전체 주석 처리
# def _on_order_panel_toggle(self, checked: bool):
#     """
#     체크박스 상태 변경 시 호출.
#     checked=True  → 조건부 주문 패널 (page 1)
#     checked=False → 대량체결 테이블  (page 0)
#     """
#     self._right_stack.setCurrentIndex(1 if checked else 0)
#
#     # 로드 행(FTD/파일) 은 테이블 모드일 때만 의미있으므로 시인성 처리
#     _load_visible = not checked
#     self.file_type_combo.setVisible(_load_visible)
#     self.file_sym_in.setVisible(_load_visible)
#     self.file_status_lbl.setVisible(_load_visible)
#
#     # 체크박스 색상 업데이트
#     if checked:
#         self.chk_order_panel.setStyleSheet(
#             "QCheckBox{ color:#FF8C00; font-weight:bold; font-size:11px; }"
#             "QCheckBox::indicator{ width:14px; height:14px; }"
#             "QCheckBox::indicator:checked{"
#             "  border:1px solid #FF8C00; border-radius:3px;"
#             "  background:#3a2a0a; }"
#         )
#     else:
#         self.chk_order_panel.setStyleSheet(
#             "QCheckBox{ color:#888; font-weight:bold; font-size:11px; }"
#             "QCheckBox::indicator{ width:14px; height:14px; }"
#             "QCheckBox::indicator:unchecked{"
#             "  border:1px solid #3a3a3a; border-radius:3px;"
#             "  background:#1a1a1a; }"
#         )
# ── [피뢰침 포착 비활성화 끝] ─────────────────────────────────

def _on_order_panel_toggle(self, checked: bool):
    """피뢰침 포착 비활성화 — 항상 테이블(page 0) 유지."""
    pass


# ── 데이터 테이블 토글 핸들러 (v6.7) ─────────────────────────
def _toggle_table_panel(self, checked: bool):
    """
    데이터 테이블 영역 펼치기 / 닫기.
    checked=True  → 펼쳐진 상태 (버튼이 눌린=체크됨)
    checked=False → 닫힌 상태
    """
    inner = getattr(self, "_tbl_inner", None)
    if inner is None:
        return

    btn = getattr(self, "btn_tbl_toggle", None)

    if checked:
        # 펼치기
        inner.show()
        self._tbl_panel_visible = True
        if btn:
            btn.setText("▲ 데이터 테이블 닫기")
        # 스플리터 비율 복원 (테이블 280 : 차트 520)
        try:
            self._v_splitter.setSizes([280, 520])
        except Exception:
            pass
    else:
        # 닫기 — 현재 스플리터 크기 저장 후 테이블 0으로
        inner.hide()
        self._tbl_panel_visible = False
        if btn:
            btn.setText("▼ 데이터 테이블 열기")
        # 스플리터에서 테이블 영역 높이를 0으로 → 차트가 전체 차지
        try:
            total = sum(self._v_splitter.sizes())
            self._v_splitter.setSizes([0, total])
        except Exception:
            pass


