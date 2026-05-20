#!/usr/bin/env python3
"""
patch_auto_fetch.py
사용법: python patch_auto_fetch.py [프로젝트루트]
예)     python patch_auto_fetch.py C:/dev/call_put_tab
"""
import sys, re, shutil
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

PATCHES = {
    # ── tab_options.py ──────────────────────────────────────────
    "tab_options.py": [
        # 1) import
        ("from call_put_tab.core_fetch import CoreFetchMixin",
         "from call_put_tab.core_fetch import CoreFetchMixin\nfrom call_put_tab.auto_fetch_next_day import AutoFetchNextDayMixin"),
        # 2) 상속 목록 (CoreFetchMixin 뒤에 삽입)
        ("CoreFetchMixin,",
         "CoreFetchMixin,\n    AutoFetchNextDayMixin,"),
        # 3) __init__ 말미 — _connect_signals() 바로 뒤
        ("self._connect_signals()",
         "self._connect_signals()\n        self._init_auto_fetch()"),
    ],

    # ── tab_options_panels.py ───────────────────────────────────
    "tab_options_panels.py": [
        # 화면설정 그룹 추가 직후에 삽입
        ("side_vbox.addWidget(self._layout_grp)",
         "side_vbox.addWidget(self._layout_grp)\n        side_vbox.addWidget(self._build_auto_fetch_panel())"),
    ],

    # ── tab_options_settings.py ─────────────────────────────────
    "tab_options_settings.py": [
        # _get_extra_settings return 직전
        ("        return d\n",
         "        d.update(self._af_get_settings())\n        return d\n"),
        # _apply_extra_settings 마지막 줄 뒤
        ("    def _apply_extra_settings(self, d: dict)",
         "    def _apply_extra_settings(self, d: dict)"),
    ],
}

# settings 파일은 apply 함수 끝에 한 줄 추가하는 별도 처리
SETTINGS_APPLY_PATCH = (
    # 마지막 self._apply_layout_snapshot 호출 뒤에 삽입
    "self._apply_layout_snapshot(d)",
    "self._apply_layout_snapshot(d)\n        self._af_apply_settings(d)",
)

def backup(p: Path):
    bak = p.with_suffix(p.suffix + ".bak")
    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"  backup → {bak.name}")

def apply(path: Path, old: str, new: str) -> bool:
    txt = path.read_text(encoding="utf-8")
    if old not in txt:
        print(f"  [SKIP] 패턴 없음: {repr(old[:60])}")
        return False
    if new in txt:
        print(f"  [SKIP] 이미 적용됨")
        return False
    path.write_text(txt.replace(old, new, 1), encoding="utf-8")
    return True

errors = []
for fname, patches in PATCHES.items():
    p = ROOT / fname
    if not p.exists():
        # 서브디렉토리도 탐색
        found = list(ROOT.rglob(fname))
        p = found[0] if found else None
    if not p or not p.exists():
        print(f"[NOT FOUND] {fname} — 건너뜀")
        errors.append(fname)
        continue

    print(f"\n▶ {p}")
    backup(p)
    for old, new in patches:
        ok = apply(p, old, new)
        print(f"  {'✓' if ok else '○'} {repr(old[:50])}")

# settings 파일 apply 함수 추가 패치
settings_path = ROOT / "tab_options_settings.py"
if not settings_path.exists():
    found = list(ROOT.rglob("tab_options_settings.py"))
    settings_path = found[0] if found else None
if settings_path and settings_path.exists():
    apply(settings_path, *SETTINGS_APPLY_PATCH)

print("\n" + ("✅ 패치 완료" if not errors else f"⚠ 일부 파일 없음: {errors}"))
print("※ .bak 파일로 롤백 가능")
