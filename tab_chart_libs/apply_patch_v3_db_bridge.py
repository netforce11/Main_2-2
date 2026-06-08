#!/usr/bin/env python3
"""
apply_patch_v3_db_bridge.py — 체결 → DB + 차트 마커 연동 패치
────────────────────────────────────────────────────────────────
사용법:
  python3 apply_patch_v3_db_bridge.py [combo_position_store.py 경로]

  예) python3 apply_patch_v3_db_bridge.py
      python3 apply_patch_v3_db_bridge.py /home/netforce/trading_terminal/Main2_1/combo_position_store.py

패치 내용:
  combo_position_store.py — record_trade_history() 함수 내부에
    ① trades.db (pnl_history) INSERT  — 차트 마커 [📥 체결 로드] 버튼 연동
    ② bridge.exec_filled emit         — 실시간 마커 표시 (선택)
  를 추가합니다. 기존 trade_history.json 저장 로직은 그대로 유지합니다.

롤백:
  수정 전 .bak 자동 생성
"""

import sys
import shutil
from pathlib import Path

# ── ANSI 색상 ─────────────────────────────────────────────────
def _c(code, text): return f"\033[{code}m{text}\033[0m"
OK   = lambda t: print(_c("32",   f"  ✅ {t}"))
FAIL = lambda t: print(_c("31",   f"  ❌ {t}"))
INFO = lambda t: print(_c("36",   f"  ℹ  {t}"))
HEAD = lambda t: print(_c("1;33", f"\n{'━'*55}\n  {t}\n{'━'*55}"))

SCRIPT_DIR = Path(__file__).resolve().parent

# ── 삽입할 코드 ───────────────────────────────────────────────
# record_trade_history() 내부,  _append_history(record) 바로 다음에 삽입
_ANCHOR = "        _append_history(record)"

_MARKER = "# [PATCH-v3] trades.db + bridge.exec_filled"

_INSERT = """
        # [PATCH-v3] trades.db + bridge.exec_filled ─────────────
        # 청산 체결 → pnl_history 테이블 INSERT (차트 마커 연동)
        try:
            from db_manager import DBManager
            _db = DBManager.get()
            # strategy 에서 symbol 추출: "XSP C5800 ×1" → "XSP"
            _sym = str(pos.get("strategy", "SPX")).split()[0].upper()
            _action = "SELL" if side == "BUY" else "BUY"   # 청산 방향
            _db.insert_trade(
                symbol     = _sym,
                action     = _action,
                qty        = qty,
                price      = exit_price,
                pnl        = realized,
                strategy   = str(pos.get("strategy", "")),
                note       = close_type,
            )
        except Exception as _e:
            pass   # DB 실패해도 기존 흐름 유지

        # bridge.exec_filled emit — 실시간 차트 마커 반영
        try:
            import time as _time
            from core import bridge as _bridge
            _ts_ms  = int(_time.time() * 1000)
            _action = "SELL" if side == "BUY" else "BUY"
            _sym    = str(pos.get("strategy", "SPX")).split()[0].upper()
            _bridge.exec_filled.emit(_ts_ms, _action, exit_price, _sym, qty)
        except Exception:
            pass   # bridge 미연결 시 무시
        # [PATCH-v3 끝] ─────────────────────────────────────────
"""

# 진입 체결(BUY) 기록 위치 — save_one_position() 내부, 파일 저장 직후
_ANCHOR2  = "            if not replaced:\n                existing.append(entry)\n\n            _write_atomic(existing)"
_MARKER2  = "# [PATCH-v3] entry BUY insert"
_INSERT2  = """
            # [PATCH-v3] entry BUY insert ─────────────────────
            # 진입 체결 → pnl_history INSERT (매수 마커)
            try:
                from db_manager import DBManager
                _db2  = DBManager.get()
                _sym2 = str(entry.get("strategy","SPX")).split()[0].upper()
                _side2 = str(entry.get("side","BUY")).upper()
                _db2.insert_trade(
                    symbol   = _sym2,
                    action   = _side2,
                    qty      = int(entry.get("qty", 1)),
                    price    = float(entry.get("entry", 0)),
                    pnl      = 0.0,
                    strategy = str(entry.get("strategy", "")),
                    note     = "진입",
                )
            except Exception:
                pass
            # [PATCH-v3 entry 끝] ─────────────────────────────
"""


def find_target(hint: str = None) -> Path:
    """combo_position_store.py 위치 탐색."""
    _PROBE = "combo_position_store.py"

    candidates = []
    if hint:
        p = Path(hint).resolve()
        if p.is_file() and p.name == _PROBE:
            return p
        candidates.append(p)

    candidates += [
        Path.cwd(),
        Path.cwd().parent,
        Path.cwd().parent.parent,
        SCRIPT_DIR.parent,
        SCRIPT_DIR.parent.parent,
    ]
    for base in candidates:
        f = base / _PROBE
        if f.exists():
            return f
    return None


def patch_record_trade_history(fpath: Path) -> bool:
    HEAD("패치 [A] — 청산 체결 → DB INSERT + bridge emit")
    text = fpath.read_text(encoding="utf-8")

    if _MARKER in text:
        INFO("이미 패치 적용됨 — 건너뜀"); return True
    if _ANCHOR not in text:
        FAIL(f"앵커를 찾을 수 없습니다: {_ANCHOR!r}")
        INFO("combo_position_store.py 버전이 다를 수 있습니다.")
        return False

    bak = fpath.with_suffix(".py.bak")
    shutil.copy2(fpath, bak)
    INFO(f"백업: {bak.name}")

    new_text = text.replace(_ANCHOR, _ANCHOR + _INSERT, 1)
    fpath.write_text(new_text, encoding="utf-8")

    if _MARKER in fpath.read_text(encoding="utf-8"):
        OK("record_trade_history() 패치 완료")
        return True
    FAIL("검증 실패 — 롤백")
    shutil.copy2(bak, fpath)
    return False


def patch_save_one_position(fpath: Path) -> bool:
    HEAD("패치 [B] — 진입 체결 → DB INSERT")
    text = fpath.read_text(encoding="utf-8")

    if _MARKER2 in text:
        INFO("이미 패치 적용됨 — 건너뜀"); return True
    if _ANCHOR2 not in text:
        FAIL(f"앵커를 찾을 수 없습니다 (save_one_position)")
        INFO("진입 마커는 수동 패치가 필요할 수 있습니다.")
        INFO("PATCH_GUIDE_v3.py 의 [B] 섹션을 참고하세요.")
        return False   # 실패해도 전체 패치는 계속

    new_text = text.replace(_ANCHOR2, _ANCHOR2 + _INSERT2, 1)
    fpath.write_text(new_text, encoding="utf-8")

    if _MARKER2 in fpath.read_text(encoding="utf-8"):
        OK("save_one_position() 패치 완료")
        return True
    FAIL("검증 실패 — 롤백")
    return False


def main():
    print(_c("1;36", "\n🔧  체결→DB→차트마커 연동 패치 (v3)"))
    print(_c("90",   "    combo_position_store.py 수정\n"))

    hint = sys.argv[1] if len(sys.argv) > 1 else None
    fpath = find_target(hint)

    if fpath is None:
        FAIL("combo_position_store.py 를 찾을 수 없습니다.")
        INFO("사용법: python3 apply_patch_v3_db_bridge.py [경로]")
        INFO("예)     python3 apply_patch_v3_db_bridge.py "
             "/home/netforce/trading_terminal/Main2_1/combo_position_store.py")
        sys.exit(1)

    INFO(f"대상 파일: {fpath}")

    ok_a = patch_record_trade_history(fpath)
    ok_b = patch_save_one_position(fpath)

    HEAD("패치 결과 요약")
    OK("청산 체결 → DB + bridge emit") if ok_a else FAIL("청산 체결 패치 실패")
    OK("진입 체결 → DB INSERT")        if ok_b else INFO("진입 마커 패치 건너뜀 (수동 필요)")

    if ok_a:
        print(_c("1;32", "\n  🎉 핵심 패치 완료!\n"))
        print(_c("90", "  동작 흐름:"))
        print(_c("90", "    XSP/SPX 청산 → record_trade_history()"))
        print(_c("90", "    → trades.db pnl_history INSERT"))
        print(_c("90", "    → bridge.exec_filled emit → 차트 실시간 마커"))
        print(_c("90", "    → [📥 체결 로드] 버튼으로 과거 체결도 차트에 표시"))
        print()
        print(_c("90", "  ℹ  롤백: combo_position_store.py.bak → 원본명으로 덮어쓰기"))
    else:
        print(_c("1;31", "\n  ⚠  패치 실패 — 위 오류를 확인하세요.\n"))
        sys.exit(1)


if __name__ == "__main__":
    main()
