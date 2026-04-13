"""
combo_hot_reload.py — 핫 리로드 패치 시스템
────────────────────────────────────────────────────────────────
사용법:
  1. MainWindow.__init__ 또는 RightPanelMixin._build_* 어딘가에서
     한 번만 호출:

         from combo_hot_reload import install_refresh_button
         install_refresh_button(self, toolbar_widget)

     toolbar_widget : 🔄 버튼을 붙일 QWidget (툴바, 상단 바 등)
     self           : RightPanelMixin 인스턴스 (패널 패치 대상)

  2. 이후 🔄 Refresh 버튼을 누르면:
     - 아래 PATCHABLE_MODULES 목록의 모든 모듈을 importlib.reload()
     - RightPanelMixin 및 self 인스턴스에 메서드 재바인딩
     - 로그에 결과 출력

────────────────────────────────────────────────────────────────
패치 대상 모듈 / 바인딩 대상 메서드 목록은 아래에서 관리.
새 파일 추가 시 PATCHABLE_MODULES 와 METHOD_MAP 에 항목 추가.
────────────────────────────────────────────────────────────────
"""

import importlib
import sys
import traceback
from PyQt5.QtWidgets import QPushButton, QHBoxLayout, QWidget, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

# ── 패치 대상 모듈 목록 ───────────────────────────────────────────
# (모듈 이름, 해당 모듈에서 꺼낼 함수 이름 목록)
PATCHABLE_MODULES = [
    ("combo_ui_leg_logic", [
        "_on_strat_change",
        "_get_leg_template",
        "_rebuild_legs",
        "_reset_legs",
        "_set_leg_mode",
        "_manual_add_leg",
        "_manual_del_leg",
        "_on_strike_changed",
        "_fetch_conid_then_premium",
        "_fmt_expiry",
    ]),
    ("combo_ui_leg_panel", [
        "_build_leg_left",
        "fill_premium_from_market",
        "cancel_all_streams",
    ]),
    ("combo_ui_chaser_row", [
        "_build_chaser_row",
    ]),
    ("combo_ui_right_panels_ext", [
        "_build_result_panel",
        "_build_spread_chart_panel",
        "_show_strat_desc",
        "_toggle_optimizer_panel",
    ]),
    ("combo_ui_synthetic_panel", []),   # 클래스 모듈 — reload만 수행
    ("combo_order_logic", [
        "_on_synthetic_order",
        "_on_check_margin",
    ]),
    ("combo_order_whatif", [
        "_send_whatif_order",
        "_finish_whatif",
    ]),
    ("combo_order_bag", [
        "_place_combo_legs",
        "_place_bag_with_conids",
    ]),
    ("combo_order_chaser", [
        "register_chaser",
        "deactivate_chaser",
        "on_chase_click",
        "init_chaser_state",
    ]),
    ("combo_order_utils", [
        "_parse_legs_from_table",
        "_calc_required_margin",
        "_parse_expiry_display",
    ]),
    ("combo_constants", []),            # 상수 모듈 — reload만 수행
]


# ── 핫 리로드 실행 ────────────────────────────────────────────────

def hot_reload(panel_instance, log_fn=None):
    """
    PATCHABLE_MODULES 의 모든 모듈을 reload 하고
    panel_instance (RightPanelMixin) 에 메서드를 재바인딩.

    Parameters
    ----------
    panel_instance : RightPanelMixin 인스턴스
    log_fn         : 로그 출력 함수 (없으면 print 사용)
    """
    _log = log_fn or print
    ok_list, fail_list = [], []

    for mod_name, func_names in PATCHABLE_MODULES:
        try:
            # 모듈이 이미 임포트되어 있으면 reload, 없으면 import
            if mod_name in sys.modules:
                mod = importlib.reload(sys.modules[mod_name])
            else:
                mod = importlib.import_module(mod_name)

            # 인스턴스에 메서드 재바인딩
            import types
            for fn_name in func_names:
                fn = getattr(mod, fn_name, None)
                if fn is None:
                    continue
                # 인스턴스 메서드로 바인딩
                bound = types.MethodType(fn, panel_instance)
                setattr(panel_instance, fn_name.lstrip('_') if False else fn_name, bound)
                # 이름이 _로 시작하는 경우 그대로 유지 (언더스코어 포함)

            ok_list.append(mod_name)

        except Exception:
            fail_list.append(mod_name)
            _log(f"❌ reload 실패: {mod_name}\n{traceback.format_exc(limit=3)}")

    # 결과 요약 로그
    if ok_list:
        _log(f"🔄 핫 리로드 완료 [{len(ok_list)}개]: {', '.join(ok_list)}")
    if fail_list:
        _log(f"⚠ 실패한 모듈 [{len(fail_list)}개]: {', '.join(fail_list)}")

    return len(fail_list) == 0


# ── Refresh 버튼 생성 및 설치 ────────────────────────────────────

def install_refresh_button(panel_instance, parent_widget, log_fn=None):
    """
    parent_widget 의 레이아웃(QHBoxLayout 가정)에 🔄 Refresh 버튼 삽입.
    버튼 클릭 시 hot_reload() 호출.

    Parameters
    ----------
    panel_instance : RightPanelMixin 인스턴스
    parent_widget  : 버튼을 붙일 QWidget (툴바 등)
    log_fn         : 로그 출력 함수
    """
    _log = log_fn or (getattr(panel_instance, '_log', None)) or print

    btn = QPushButton("🔄")
    btn.setToolTip("핫 리로드 — 모듈 재적용 (재시작 불필요)")
    btn.setFixedSize(28, 22)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet("""
        QPushButton {
            background: #1a1a3a;
            color: #7799ff;
            border: 1px solid #3a3a7a;
            border-radius: 3px;
            font-size: 13px;
            padding: 0px;
        }
        QPushButton:hover {
            background: #2a2a5a;
            color: #aabbff;
            border: 1px solid #6666cc;
        }
        QPushButton:pressed {
            background: #0a0a2a;
            color: #5566cc;
        }
    """)

    def _on_click():
        btn.setEnabled(False)
        btn.setText("⏳")
        # GUI 업데이트 후 실행 (블로킹 방지)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(50, lambda: _do_reload())

    def _do_reload():
        success = hot_reload(panel_instance, _log)
        btn.setEnabled(True)
        btn.setText("🔄" if success else "⚠️")
        if not success:
            # 2초 후 아이콘 복구
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(2000, lambda: btn.setText("🔄"))

    btn.clicked.connect(_on_click)

    # 레이아웃에 삽입 — 다크모드 버튼 옆 좌측
    layout = parent_widget.layout()
    if layout is not None:
        # 기존 레이아웃에서 다크모드 버튼 위치를 찾아 바로 앞에 삽입
        dark_btn_idx = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w and isinstance(w, QPushButton):
                tip = w.toolTip() or w.text() or ""
                if "다크" in tip or "dark" in tip.lower() or "🌙" in tip or "☀" in tip:
                    dark_btn_idx = i
                    break
        if dark_btn_idx >= 0:
            layout.insertWidget(dark_btn_idx, btn)
        else:
            layout.insertWidget(0, btn)   # 못 찾으면 맨 앞에
    else:
        # 레이아웃이 없으면 HBox 새로 만들어 추가
        hbox = QHBoxLayout(parent_widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(btn)

    # 인스턴스에 참조 보관 (외부에서 접근 가능하게)
    panel_instance._btn_hot_reload = btn
    _log("🔄 핫 리로드 버튼 설치 완료")
    return btn


# ── 단독 실행 테스트 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("combo_hot_reload.py — 패치 대상 모듈 목록:")
    for mod_name, funcs in PATCHABLE_MODULES:
        print(f"  {mod_name}: {funcs or '(reload only)'}")
