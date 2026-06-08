#!/usr/bin/env python3
"""
apply_patch_v2.py — 체결 마커 v2 패치 자동 적용 스크립트
────────────────────────────────────────────────────────────
사용법:
  python3 apply_patch_v2.py [프로젝트_루트_경로]

  예) python3 apply_patch_v2.py
      python3 apply_patch_v2.py /home/netforce/trading_terminal/Main2_1/tab_chart_libs

패치 내용:
  [1] chart_exec_marker.py    → 프로젝트 lib 폴더에 복사 (교체)
  [2] chart_exec_marker_ui.py → 프로젝트 lib 폴더에 복사 (신규)
  [3] chart_build_side_bottom.py → 체결 마커 UI 패널 삽입 (1곳)

롤백:
  패치 전 .bak 백업 자동 생성 → 실패 시 자동 복원
"""

import sys
import os
import shutil
from pathlib import Path

# ── ANSI 색상 ─────────────────────────────────────────────
def _c(code, text): return f"\033[{code}m{text}\033[0m"
OK   = lambda t: print(_c("32", f"  ✅ {t}"))
FAIL = lambda t: print(_c("31", f"  ❌ {t}"))
INFO = lambda t: print(_c("36", f"  ℹ  {t}"))
HEAD = lambda t: print(_c("1;33", f"\n{'━'*55}\n  {t}\n{'━'*55}"))

# ── 이 스크립트가 위치한 디렉터리 (= tab_chart_libs 폴더) ──
SCRIPT_DIR = Path(__file__).resolve().parent


def find_project_root(hint: str = None) -> Path:
    """
    chart_build_side_bottom.py 가 있는 폴더를 탐색.
    hint 가 주어지면 그 경로를 우선 사용.
    tar 해제 후 tab_chart_libs/tab_chart_libs 처럼 이중 중첩된 경우도 처리.
    """
    _PROBE = "chart_build_side_bottom.py"

    def _probe(p: Path):
        checks = [p, p / "tab_chart_libs", p.parent, p.parent / "tab_chart_libs"]
        for c in checks:
            if c.is_dir() and (c / _PROBE).exists():
                return c
        return None

    candidates = []
    if hint:
        candidates.append(Path(hint).resolve())
    candidates += [
        Path.cwd(),
        SCRIPT_DIR,
        SCRIPT_DIR.parent,
        SCRIPT_DIR.parent.parent,
    ]

    for base in candidates:
        result = _probe(base)
        if result:
            return result

    return None


def backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def restore(bak: Path, original: Path):
    shutil.copy2(bak, original)


# ════════════════════════════════════════════════════════════
# 패치 [1][2] — 신규/교체 파일 복사
# ════════════════════════════════════════════════════════════

def patch_copy_files(target_dir: Path) -> bool:
    HEAD("패치 [1][2] — 신규/교체 파일 복사")
    files = [
        "chart_exec_marker.py",
        "chart_exec_marker_ui.py",
    ]
    all_ok = True
    for fname in files:
        src = SCRIPT_DIR / fname
        dst = target_dir / fname
        if not src.exists():
            FAIL(f"원본 없음: {src}")
            all_ok = False
            continue
        if dst.exists():
            bak = backup(dst)
            INFO(f"백업: {bak.name}")
        shutil.copy2(src, dst)
        OK(f"{fname} → {dst}")
    return all_ok


# ════════════════════════════════════════════════════════════
# 패치 [3] — chart_build_side_bottom.py 수정
# ════════════════════════════════════════════════════════════

# 삽입 앞 기준 문자열 (이 줄 바로 앞에 삽입)
_ANCHOR = '    self.btn_memo_toggle = QPushButton("📝 메모")'

# 삽입할 코드 블록
_INSERT = '''\
    # ── [체결 마커 v2] UI 패널 ─────────────────────────────
    from chart_exec_marker_ui import build_exec_marker_panel
    side.addWidget(build_exec_marker_panel(self))
    side.addWidget(_make_sep())
    # ── [체결 마커 v2] 끝 ─────────────────────────────────

'''

# 이미 패치된 표식
_MARKER = "[체결 마커 v2] UI 패널"


def patch_side_bottom(target_dir: Path) -> bool:
    HEAD("패치 [3] — chart_build_side_bottom.py 수정")
    fpath = target_dir / "chart_build_side_bottom.py"
    if not fpath.exists():
        FAIL(f"파일 없음: {fpath}")
        return False

    text = fpath.read_text(encoding="utf-8")

    if _MARKER in text:
        INFO("이미 패치 적용됨 — 건너뜀")
        return True

    if _ANCHOR not in text:
        FAIL(f"앵커 문자열을 찾을 수 없습니다:\n      {_ANCHOR!r}")
        INFO("chart_build_side_bottom.py 버전이 다를 수 있습니다.")
        INFO("PATCH_GUIDE_v2_exec_marker.py 를 참고해 수동 패치하세요.")
        return False

    bak = backup(fpath)
    INFO(f"백업: {bak.name}")

    new_text = text.replace(_ANCHOR, _INSERT + _ANCHOR, 1)
    fpath.write_text(new_text, encoding="utf-8")
    OK("chart_build_side_bottom.py 패치 완료")

    # 검증
    verify = fpath.read_text(encoding="utf-8")
    if _MARKER in verify:
        OK("삽입 내용 검증 통과")
        return True
    else:
        FAIL("검증 실패 — 롤백")
        restore(bak, fpath)
        return False


# ════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════

def main():
    print(_c("1;36", "\n🔧  체결 마커 v2 패치 스크립트"))
    print(_c("90",   "    XSP/SPX 지수환산 + ET/KST 시간보정 + 사이드바 UI\n"))

    hint = sys.argv[1] if len(sys.argv) > 1 else None
    target = find_project_root(hint)

    if target is None:
        FAIL("프로젝트 폴더를 찾을 수 없습니다.")
        INFO("사용법: python apply_patch_v2.py [프로젝트_경로]")
        INFO("예)     python apply_patch_v2.py /home/netforce/tab_chart")
        sys.exit(1)

    INFO(f"대상 폴더: {target}")

    results = []
    results.append(("파일 복사",        patch_copy_files(target)))
    results.append(("사이드바 UI 삽입", patch_side_bottom(target)))

    HEAD("패치 결과 요약")
    all_ok = True
    for name, ok in results:
        if ok:
            OK(name)
        else:
            FAIL(name)
            all_ok = False

    if all_ok:
        print(_c("1;32", "\n  🎉 모든 패치 완료!\n"))
        print(_c("90", "  적용 내용:"))
        print(_c("90", "    · chart_exec_marker.py    — v2 교체 (XSP↔SPX 환산 + 시간보정)"))
        print(_c("90", "    · chart_exec_marker_ui.py — 신규 (사이드바 UI 패널)"))
        print(_c("90", "    · chart_build_side_bottom.py — 체결 마커 패널 삽입"))
        print()
        print(_c("90", "  ℹ  롤백: .bak 파일을 원본명으로 되돌리면 복원됩니다."))
    else:
        print(_c("1;31", "\n  ⚠  일부 패치 실패 — 위 오류 메시지를 확인하세요.\n"))
        print(_c("90", "  수동 패치: PATCH_GUIDE_v2_exec_marker.py 참고"))
        sys.exit(1)


if __name__ == "__main__":
    main()
