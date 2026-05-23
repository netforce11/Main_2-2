"""
combo_op_dialog.py — Cost Optimizer 독립 팝업 창 (v2.3 신규)
────────────────────────────────────────────────────────────
위치: main2/combo_libs/combo_op/combo_op_dialog.py
포함:
  OptimizerDialog  — 별도 QDialog 팝업 (화면 덮어쓰기 방지)
  _toggle_optimizer_panel()  — 🔍 Optimiser 버튼 핸들러
────────────────────────────────────────────────────────────
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy,
)
from PyQt5.QtCore import Qt


class OptimizerDialog(QDialog):
    """
    Cost Optimizer를 메인 UI와 분리된 독립 창으로 표시.

    구조:
      부모(ComboStrategyGrid)의 _build_optimizer_panel()을 호출하여
      조건 그리드 + 결과 테이블을 이 창 안에 임베드한다.
      모든 탐색 로직은 부모의 OptimizerPanelMixin 메서드를 그대로 사용.
    """

    def __init__(self, parent_widget):
        """
        parent_widget: ComboStrategyGrid 인스턴스.
        parent를 넘기지 않아야 독립 창(태스크바 별도 표시)으로 뜸.
        parent를 넘기면 자식 창이 되어 부모 뒤에 숨거나 같이 최소화됨.
        setWindowFlags 재호출 금지 — super().__init__ 이후 재호출 시 창이 숨겨짐.
        """
        # parent=None → 독립 최상위 창, Qt.Window는 기본값
        super().__init__(None)
        self._pw = parent_widget

        self.setWindowTitle("🔍 Cost Optimizer")
        # ※ setWindowFlags 재호출 금지 (창 숨김 버그 원인)
        # 최소화/최대화/닫기 버튼은 기본 Qt.Window에 포함됨
        self.setMinimumSize(900, 520)
        self.resize(1100, 620)
        self.setStyleSheet(
            "QDialog{background:#07070f;color:#ccc;}"
            "QGroupBox{color:#90caf9;border:1px solid #2a2a5a;"
            "border-radius:4px;margin-top:6px;font-size:12px;font-weight:bold;}"
            "QGroupBox::title{subcontrol-origin:margin;left:8px;top:3px;}"
        )

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # 부모의 _build_optimizer_panel 결과를 이 창 안에 배치
        gb = parent_widget._build_optimizer_panel()
        gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(gb)

        # 하단 닫기 버튼
        close_row = QHBoxLayout()
        close_row.addStretch()
        btn_close = QPushButton("✕  닫기")
        btn_close.setFixedHeight(28)
        btn_close.setStyleSheet(
            "QPushButton{background:#2a0a0a;color:#ff6666;font-size:11px;"
            "font-weight:bold;padding:4px 16px;border-radius:4px;"
            "border:1px solid #5a1a1a;}"
            "QPushButton:hover{background:#4a1a1a;}")
        btn_close.clicked.connect(self.close)
        close_row.addWidget(btn_close)
        v.addLayout(close_row)

    def closeEvent(self, event):
        """닫을 때 부모의 _optimizer_dialog 참조 초기화."""
        self._pw._optimizer_dialog = None
        super().closeEvent(event)


# ── 토글 함수 (RightPanelMixin에 바인딩) ─────────────────────

def _toggle_optimizer_panel(self):
    """
    🔍 Optimiser 버튼 핸들러.
    이미 창이 열려 있으면 앞으로 가져오고, 없으면 새로 생성한다.
    기존 슬라이드 패널 방식 대신 팝업 방식으로 동작하여
    메인 화면을 가리지 않는다.
    """
    dlg = getattr(self, '_optimizer_dialog', None)

    if dlg is not None and dlg.isVisible():
        dlg.raise_()
        dlg.activateWindow()
        return

    dlg = OptimizerDialog(self)
    self._optimizer_dialog = dlg
    dlg.show()