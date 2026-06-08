"""
chart_memo_io.py — 메모 JSON 저장/로드 헬퍼
[분리] chart_memo.py 에서 분리 (_load_memos, _save_memos, _date_key)
"""
import json
from pathlib import Path
from PyQt5.QtCore import QDate

_MEMO_FILE = Path("/home/netforce/US_Data/chart_memos.json")

def _load_memos() -> dict:
    """JSON 파일에서 메모 딕셔너리 로드. {날짜문자열: 메모내용}"""
    try:
        if _MEMO_FILE.exists():
            return json.loads(_MEMO_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Memo] 로드 오류: {e}")
    return {}


def _save_memos(memos: dict):
    """메모 딕셔너리를 JSON 파일로 저장."""
    try:
        _MEMO_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MEMO_FILE.write_text(
            json.dumps(memos, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[Memo] 저장 오류: {e}")


def _date_key(qdate) -> str:
    """QDate → 'YYYY-MM-DD' 문자열"""
    if isinstance(qdate, QDate):
        return qdate.toString("yyyy-MM-dd")
    return str(qdate)


# ══════════════════════════════════════════════════════════════
# 패널 빌드
# ══════════════════════════════════════════════════════════════
