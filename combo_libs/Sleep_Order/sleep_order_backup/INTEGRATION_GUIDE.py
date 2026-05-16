# ════════════════════════════════════════════════════════════════
# Sleep_Order 패키지 연동 가이드  v1.0
# ════════════════════════════════════════════════════════════════
#
# 폴더 구조:
#   프로젝트루트/
#   ├── Sleep_Order/
#   │   ├── __init__.py
#   │   ├── sleep_order_config.py
#   │   ├── sleep_order_spike.py
#   │   ├── sleep_order_watcher.py
#   │   ├── sleep_order_ui.py
#   │   └── sleep_order_mixin.py   ← _sleep_get_chain 등 완성 버전
#   ├── combo_ui_left.py           ← [수정 1] Mixin 추가
#   ├── combo_ui_synthetic_panel.py ← [수정 2] 버튼 추가
#   ├── combo_order_callbacks.py   ← [수정 3] unwatch 2줄 추가
#   └── Main_config.py             ← [수정 4] 우측 패널 패치 1줄
#
# ════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────
# [수정 1] combo_ui_left.py
# LeftPanelMixin 에 SleepOrderMixin 상속 추가
# ──────────────────────────────────────────────────────────────

# 파일 상단 import 추가:
"""
from Sleep_Order.sleep_order_mixin import SleepOrderMixin
"""

# 클래스 선언 변경:
"""
# 변경 전
class LeftPanelMixin:

# 변경 후
class LeftPanelMixin(SleepOrderMixin):
"""

# 끝. _sleep_get_underlying_price, _sleep_get_chain,
# _sleep_place_order, _sleep_modify_order 모두 자동 포함.


# ──────────────────────────────────────────────────────────────
# [수정 2] combo_ui_synthetic_panel.py
# SyntheticStatusPanel._build_ui() — mode_row.addStretch() 직전
# ──────────────────────────────────────────────────────────────

"""
        # ── [SLEEP] 예약 주문 버튼 우측 상단 ───────────────────
        try:
            from Sleep_Order.sleep_order_ui import SleepOrderButton
            # ref = SyntheticStatusPanel 의 부모 (LeftPanelMixin 인스턴스)
            # parent() 를 통해 combo tab 참조
            _sleep_ref = self.parent() if self.parent() else self
            self._sleep_btn = SleepOrderButton(ref=_sleep_ref, parent=self)
            mode_row.addWidget(self._sleep_btn)
        except Exception as e:
            print(f"[SyntheticPanel] sleep_order 버튼 오류: {e}")

        mode_row.addStretch()   # ← 기존 코드 (이 줄 앞에 위 블록 삽입)
"""


# ──────────────────────────────────────────────────────────────
# [수정 3] combo_order_callbacks.py
# _on_order_status() — Filled 블록 끝 (SpecialFillWatcher.unwatch 바로 아래)
# ──────────────────────────────────────────────────────────────

"""
        # [SLEEP] 급락 캐치 체결 통보
        try:
            from Sleep_Order.sleep_order_spike import SleepSpikeWatcher
            SleepSpikeWatcher.get().unwatch_by_oid(oid)
        except Exception:
            pass
"""

# _on_order_status() — Cancelled 블록 끝에도 동일하게 추가:
"""
        # [SLEEP] 급락 캐치 취소 통보
        try:
            from Sleep_Order.sleep_order_spike import SleepSpikeWatcher
            SleepSpikeWatcher.get().unwatch_by_oid(oid)
        except Exception:
            pass
"""


# ──────────────────────────────────────────────────────────────
# [수정 4] Main_config.py
# ConfigTab.__init__() — self._build() 다음 줄
# ──────────────────────────────────────────────────────────────

"""
        # ── [SLEEP] Main_config 우측 패널 2단 레이아웃 패치 ────
        try:
            from Sleep_Order.sleep_order_ui import patch_main_config_layout
            patch_main_config_layout(self)
        except Exception as e:
            print(f"[ConfigTab] sleep_order 패치 실패: {e}")
"""


# ──────────────────────────────────────────────────────────────
# 주의사항
# ──────────────────────────────────────────────────────────────
#
# 1. SleepOrderButton(ref=_sleep_ref) 의 ref 는
#    _sleep_get_chain / _sleep_place_order 를 가진 객체여야 함.
#    SleepOrderMixin 을 상속한 LeftPanelMixin 인스턴스가 ref.
#    → SyntheticStatusPanel 의 부모가 ComboTab(LeftPanelMixin) 이면
#      self.parent() 로 충분.
#    → 구조가 다르면 ComboTab 참조를 직접 전달:
#      SleepOrderButton(ref=self.mw.tab_combo, parent=self)
#
# 2. _sleep_get_chain 은 현재 동기화된 만기(_current_expiry) 기준.
#    expiry_offset 은 영업일 단순 계산(공휴일 미처리).
#    정확한 만기가 필요하면 콜-풋 탭의 _expiry_list 를 직접 참조하도록
#    sleep_order_mixin.py 의 _offset_expiry() 를 커스텀하세요.
#
# 3. _sleep_place_order 는 combo_order_bag._build_bag_contract 를 사용.
#    이 함수가 없으면 직접 BAG 컨트랙트 빌드 로직 추가 필요.