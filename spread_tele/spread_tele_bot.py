# spread_tele_bot.py  (Python 3.8 호환)
"""
v1.8 변경:
  - [BUG-FIX] "tomorrow" → "next" 오타 수정.
    resolve_expiry() 의 which 키와 불일치하여 다음 만기가 항상 오류.
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
    """버그④: 4096자 초과 방어 — limit 단위로 분할."""
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
    """계산 결과를 텔레그램으로 전송 (동기/비동기 공통 출구)."""
    from telegram_bot.tg_client import TelegramClient
    client = TelegramClient.get()

    msg    = _build_spread_msg(spreads, price_lbl, expiry_lbl, base, is_call)
    chunks = _chunk_text(msg)
    if len(chunks) == 1:
        client._edit_inline_message(chat_id, message_id, chunks[0])
    else:
        client._edit_inline_message(chat_id, message_id, chunks[0])
        for chunk in chunks[1:]:
            client._send_raw(chunk)


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
        client._edit_inline_message(chat_id, message_id, "취소되었습니다.")
        return True

    if data in (CB_CALL, CB_PUT):
        if _tab_ref is None or getattr(_tab_ref, "und_price", None) is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 기초자산 가격 미수신.\nIBKR 연결 후 다시 시도해 주세요."
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
            client._edit_inline_message(chat_id, message_id, "⚠️ 탭 연결 오류.")
            _clear(chat_id)
            return True

        which = "today" if data == CB_TODAY else "next"

        # 버그⑦: _sel_type 없으면 세션 만료 안내
        spread_type = _sel_type.get(chat_id)
        if spread_type is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 세션이 만료되었습니다.\n처음부터 다시 시도해 주세요."
            )
            _clear(chat_id)
            return True

        _clear(chat_id)

        expiry_code, expiry_lbl = resolve_expiry(_tab_ref, which)
        if expiry_code is None:
            client._edit_inline_message(
                chat_id, message_id,
                "⚠️ 유효한 만기가 없습니다.\n콜-풋 탭에서 먼저 조회해 주세요."
            )
            return True

        # 버그⑧: 계산 전 "처리 중" 메시지로 Telegram timeout 방어
        client._edit_inline_message(chat_id, message_id, "📊 계산 중...")

        base      = get_base_price(_tab_ref)
        price_lbl = get_price_label(_tab_ref)
        is_call   = (spread_type == CB_CALL)

        # ★ v1.6: on_done 콜백 방식으로 호출
        # - 탭 현재 만기 == expiry_code → 즉시 동기 계산 후 on_done 호출
        # - 다른 만기 → TWS 별도 구독 → 4초 후 on_done 호출
        def on_done(spreads: List[dict]) -> None:
            _send_result(spreads, price_lbl, expiry_lbl, base, is_call,
                         chat_id, message_id)

        if is_call:
            result = get_call_spreads(_tab_ref, expiry_code, on_done=on_done)
        else:
            result = get_put_spreads(_tab_ref, expiry_code, on_done=on_done)

        # result가 None이 아니면 동기 계산 완료 (on_done이 이미 호출됨)
        # None이면 비동기 진행 중 — 아무것도 하지 않음 (on_done에서 전송)
        return True

    return False


def _clear(chat_id: str) -> None:
    _state.pop(chat_id, None)
    _sel_type.pop(chat_id, None)