# spread_tele_bot.py  (Python 3.8 호환)
"""
v1.9 변경 (버그 수정):
  ★ [BUG-FIX-4] handle_callback — CB_TODAY/CB_TOMORROW 분기에서
    result is not None 조건 제거.
    get_call/put_spreads(on_done=...) 는 이제 항상 None 반환(spread_calc v1.9).
    기존 코드에서 result = get_call_spreads(...) 가 [] 를 반환하는 경우
    on_done 이 이미 내부에서 호출됐음에도 result is not None 이 True 가 되어
    _send_result 가 이중 호출되거나, on_done 이 호출 안 된 채 조용히 종료.

  ★ [BUG-FIX-5] _send_result — _edit_inline_message 호출 시
    buttons=[] (빈 리스트) 전달하여 인라인 버튼 명시적 제거.
    기존: buttons=None → Telegram API 가 기존 버튼을 그대로 유지,
    메시지 길이에 따라 400 Bad Request 발생 가능.

  ★ [BUG-FIX-6] _send_result — 결과 전송 전 예외를 잡아 텔레그램으로 전달.
    기존: 예외 발생 시 조용히 무시 → 응답 없음.

  v1.8 대비 로직 변경:
    on_done 콜백 이후 result 분기 완전 제거.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Dict

from .spread_calc import get_base_price, get_price_label, resolve_expiry
from .spread_calc import get_call_spreads, get_put_spreads
from .spread_config import (
    CB_CALL, CB_PUT, CB_TODAY, CB_TOMORROW, CB_CANCEL,
    CALL_RANGE_PCT, PUT_RANGE_PCT, SPREAD_STEP,
)

if TYPE_CHECKING:
    from call_put_tab.tab_options import CallPutGrid

_tab_ref:  Optional["CallPutGrid"] = None
_state:    Dict[str, str] = {}
_sel_type: Dict[str, str] = {}


def set_tab(tab: "CallPutGrid") -> None:
    global _tab_ref
    _tab_ref = tab


# ── 포맷 헬퍼 ────────────────────────────────────────────

def _fmt(val: Optional[float], decimals: int = 2) -> str:
    return f"{val:.{decimals}f}" if val is not None else "―"


def _dist_arrow(pct: float, is_call: bool) -> str:
    return f"+{pct:.2f}%  ↑" if is_call else f"{pct:.2f}%  ↓"


def _chunk_text(text: str, limit: int = 4000) -> List[str]:
    """4096자 초과 방어 — limit 단위로 분할."""
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


def _build_spread_msg(spreads: List[dict], price_lbl: str,
                      expiry_lbl: str, base: float, is_call: bool) -> str:
    kind      = "콜 불 스프레드" if is_call else "풋 베어 스프레드"
    emoji     = "📈" if is_call else "📉"
    limit_pct = CALL_RANGE_PCT if is_call else PUT_RANGE_PCT
    limit_px  = base * (1 + limit_pct) if is_call else base * (1 - limit_pct)
    dir_str   = f"+0.8% 이하 ({limit_px:,.0f})" if is_call \
                else f"-0.8% 이상 ({limit_px:,.0f})"

    lines = [
        f"{'='*32}",
        f"{emoji}  {kind}  리포트",
        f"{'='*32}",
        f"기준가  : {price_lbl}",
        f"만기    : {expiry_lbl}",
        f"조회범위: {dir_str}",
        f"{'─'*32}",
    ]

    if not spreads:
        lines += ["조회 가능한 스프레드 없음", f"{'='*32}"]
        return "\n".join(lines)

    for i, s in enumerate(spreads, 1):
        mid      = s["mid"]
        mp       = s["max_profit"]
        ml       = s["max_loss"]
        be       = s["breakeven"]
        rr       = s["rr"]
        dist_pct = s["dist_pct"]
        long_k   = int(s["long"])
        short_k  = int(s["short"])

        if mid is None:
            lines += [
                f"[ {i} ]  {long_k} / {short_k}",
                f"  현재가 거리 : {_dist_arrow(dist_pct, is_call)}",
                f"  틱 미수신 (장외/미조회)",
                f"{'─'*32}",
            ]
            continue

        lines += [
            f"[ {i} ]  {long_k} / {short_k}",
            f"  현재가 거리 : {_dist_arrow(dist_pct, is_call)}",
            f"  진입비용(mid): {_fmt(mid)} pt",
            f"  최대이익     : +{_fmt(mp)} pt" if mp is not None else "  최대이익     : ―",
            f"  최대손실     : -{_fmt(ml)} pt" if ml is not None else "  최대손실     : ―",
            f"  손익분기     : {_fmt(be, 0)}"  if be is not None else "  손익분기     : ―",
            f"  손익비(R:R)  : {rr}",
            f"{'─'*32}",
        ]

    valid_rr = [s for s in spreads
                if s["max_profit"] is not None
                and s["max_loss"] is not None
                and s["max_loss"] > 0]
    if valid_rr:
        best = max(valid_rr, key=lambda x: x["max_profit"] / x["max_loss"])
        lines += [
            f"총 {len(spreads)}쌍  |  간격 {SPREAD_STEP}pt",
            f"★ 최고 R:R : {int(best['long'])} / {int(best['short'])}  ({best['rr']})",
        ]
    else:
        lines.append(f"총 {len(spreads)}쌍  |  간격 {SPREAD_STEP}pt  (틱 미수신)")

    lines.append(f"{'='*32}")
    return "\n".join(lines)


def _send_result(spreads: List[dict], price_lbl: str,
                 expiry_lbl: str, base: float, is_call: bool,
                 chat_id: str, message_id: int) -> None:
    """계산 결과를 텔레그램으로 전송."""
    try:
        from telegram_bot.tg_client import TelegramClient
        client = TelegramClient.get()

        msg    = _build_spread_msg(spreads, price_lbl, expiry_lbl, base, is_call)
        chunks = _chunk_text(msg)

        # [BUG-FIX-5] buttons=[] 로 명시적 버튼 제거 (None 이면 기존 버튼 유지)
        if len(chunks) == 1:
            client._edit_inline_message(chat_id, message_id, chunks[0], buttons=[])
        else:
            client._edit_inline_message(chat_id, message_id, chunks[0], buttons=[])
            for chunk in chunks[1:]:
                client._send_raw(chunk)

    except Exception as e:
        # [BUG-FIX-6] 예외 발생 시 텔레그램으로 오류 전달
        import traceback
        err_msg = f"⚠️ 스프레드 결과 전송 오류:\n{type(e).__name__}: {e}"
        print(f"[spread_tele_bot] _send_result 오류:\n{traceback.format_exc()}")
        try:
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get()._send_raw(err_msg)
        except Exception:
            pass


# ── 인라인 버튼 ──────────────────────────────────────────

_TYPE_BUTTONS = [
    [
        {"text": "📈 콜 스프레드", "callback_data": CB_CALL},
        {"text": "📉 풋 스프레드", "callback_data": CB_PUT},
    ],
    [{"text": "❌ 취소", "callback_data": CB_CANCEL}],
]

_EXPIRY_BUTTONS = [
    [
        {"text": "📅 오늘/최근 만기", "callback_data": CB_TODAY},
        {"text": "📅 다음 만기",      "callback_data": CB_TOMORROW},
    ],
    [{"text": "❌ 취소", "callback_data": CB_CANCEL}],
]


# ── 콜백 진입점 ──────────────────────────────────────────

def handle_callback(data: str, chat_id: str, message_id: int) -> bool:
    from telegram_bot.tg_client import TelegramClient
    client = TelegramClient.get()

    if data == CB_CANCEL:
        _clear(chat_id)
        client._edit_inline_message(chat_id, message_id, "취소되었습니다.", buttons=[])
        return True

    if data in (CB_CALL, CB_PUT):
        if _tab_ref is None or getattr(_tab_ref, "und_price", None) is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 기초자산 가격 미수신.\nIBKR 연결 후 다시 시도해 주세요.",
                buttons=[],
            )
            _clear(chat_id)
            return True

        _state[chat_id]    = "expiry_select"
        _sel_type[chat_id] = data
        kind      = "콜" if data == CB_CALL else "풋"
        price_lbl = get_price_label(_tab_ref)
        client._edit_inline_message(
            chat_id, message_id,
            f"{kind} 스프레드 — 만기를 선택하세요.\n현재가: {price_lbl}",
            _EXPIRY_BUTTONS,
        )
        return True

    if data in (CB_TODAY, CB_TOMORROW):
        if _tab_ref is None:
            client._edit_inline_message(chat_id, message_id, "⚠️ 탭 연결 오류.", buttons=[])
            _clear(chat_id)
            return True

        which = "today" if data == CB_TODAY else "next"

        spread_type = _sel_type.get(chat_id)
        if spread_type is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 세션이 만료되었습니다.\n처음부터 다시 시도해 주세요.",
                buttons=[],
            )
            _clear(chat_id)
            return True

        _clear(chat_id)

        expiry_code, expiry_lbl = resolve_expiry(_tab_ref, which)
        if expiry_code is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 유효한 만기가 없습니다.\n콜-풋 탭에서 먼저 조회해 주세요.",
                buttons=[],
            )
            return True

        # 계산 전 "처리 중" 메시지 (버튼 제거)
        client._edit_inline_message(chat_id, message_id, "📊 계산 중...", buttons=[])

        base      = get_base_price(_tab_ref)
        price_lbl = get_price_label(_tab_ref)
        is_call   = (spread_type == CB_CALL)

        def on_done(spreads: List[dict]) -> None:
            _send_result(spreads, price_lbl, expiry_lbl, base, is_call,
                         chat_id, message_id)

        # [BUG-FIX-4] get_call/put_spreads(on_done=...) 는 항상 None 반환.
        # result 분기 완전 제거 — on_done 콜백에서만 결과 전달.
        if is_call:
            get_call_spreads(_tab_ref, expiry_code, on_done=on_done)
        else:
            get_put_spreads(_tab_ref, expiry_code, on_done=on_done)

        return True

    return False


def _clear(chat_id: str) -> None:
    _state.pop(chat_id, None)
    _sel_type.pop(chat_id, None)