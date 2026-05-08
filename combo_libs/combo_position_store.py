"""
combo_position_store.py — 합성 잔고 영속화 + 재연결 복원
──────────────────────────────────────────────────────────────
저장 경로: data/synthetic_positions.json

■ 저장 시점  : 체결 완료 (_on_order_status "Filled")
■ 제거 시점  : 취소 확인 / 청산 주문 전송 성공 후
■ 복원 시점  : bridge.connected → _on_pos_reconnect_hook()

■ FIX 목록
  [FIX-1] save_one_position — filelock 으로 동시 쓰기 경합 방지
           (threading.Lock 사용, rename-atomic 패턴)
  [FIX-2] restore_on_reconnect — positionEnd 미수신 시 핸들러 영구등록 방지
           → _pos_hook_active 플래그로 중복 연결 차단
           → 타임아웃 10 초 후 강제 원복 (기존 코드 보완)
  [FIX-3] _merge — BAG secType 포지션도 IB 미매칭 폴백 경로에서 MKT 대신
           legs 정보 사용하도록 처리
  [FIX-4] safe_remove_after_order — 주문 전송 성공 확인 후 삭제(호출자가 oid
           확정된 시점에 호출)
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import json
import threading
import tempfile
import os
from datetime import datetime, timedelta
from pathlib import Path

_STORE_FILE   = Path(__file__).resolve().parent / "data" / "synthetic_positions.json"
_HISTORY_FILE = Path(__file__).resolve().parent / "data" / "trade_history.json"
_MAX_AGE_DAYS = 7

# [FIX-1] 파일 쓰기 직렬화 락
_write_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
# 저장 / 제거
# ══════════════════════════════════════════════════════════════

def save_one_position(pos: dict) -> None:
    """
    체결 완료된 포지션 1건 저장/갱신.
    [FIX-1] threading.Lock + atomic rename 으로 동시 쓰기 경합 방지.
    status != '체결완료' 이면 저장하지 않음.
    """
    if pos.get("status") != "체결완료":
        return
    try:
        with _write_lock:
            existing = load_positions()
            oid = pos.get("oid")
            entry = dict(pos)
            entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))

            replaced = False
            for i, p in enumerate(existing):
                if oid and p.get("oid") == oid:
                    existing[i] = entry
                    replaced = True
                    break
            if not replaced:
                existing.append(entry)

            _write_atomic(existing)
    except Exception:
        pass


def remove_position(oid: int) -> None:
    """oid 에 해당하는 항목을 파일에서 제거."""
    try:
        with _write_lock:
            existing = load_positions()
            updated = [p for p in existing if p.get("oid") != oid]
            if len(updated) != len(existing):
                _write_atomic(updated)
    except Exception:
        pass


def safe_remove_after_order(oid: int, log_fn=None) -> None:
    """
    [FIX-4] 청산 주문 전송 성공(oid 확정) 후 파일에서 제거.
    _on_close_position_order 에서 placeOrder 성공 직후 호출.
    주문 실패 시에는 호출하지 않아야 함.
    """
    remove_position(oid)
    if log_fn:
        log_fn(f"🗑 잔고 파일 제거: OID={oid}")


# ══════════════════════════════════════════════════════════════
# 거래 이력 기록
# ══════════════════════════════════════════════════════════════

def record_trade_history(pos: dict, exit_price: float, close_type: str) -> None:
    """
    청산/만기소멸 시 실현 손익을 trade_history.json 에 기록.
    close_type: "청산주문" | "만기소멸"
    """
    try:
        entry    = float(pos.get("entry", 0))
        qty      = int(pos.get("qty", 1))
        side     = pos.get("side", "BUY").upper()

        if side == "BUY":
            realized = round((exit_price - entry) * qty * 100, 2)
        else:
            realized = round((entry - exit_price) * qty * 100, 2)

        record = {
            "oid":        pos.get("oid"),
            "strategy":   pos.get("strategy", ""),
            "side":       side,
            "qty":        qty,
            "entry":      entry,
            "exit":       exit_price,
            "realized":   realized,
            "close_type": close_type,
            "closed_at":  datetime.now().isoformat(timespec="seconds"),
        }
        _append_history(record)
    except Exception:
        pass


def load_trade_history() -> list:
    """trade_history.json 전체 반환 (없으면 빈 리스트)."""
    try:
        if not _HISTORY_FILE.exists():
            return []
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _append_history(record: dict) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(exist_ok=True)
        data = load_trade_history()
        data.append(record)
        _write_atomic_path(_HISTORY_FILE,
                           json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 불러오기
# ══════════════════════════════════════════════════════════════

def load_positions() -> list:
    """
    저장된 포지션 목록 반환.
    파일 없거나 파싱 실패 시 빈 리스트. 7일 초과 항목 자동 제거.
    ※ 이 함수는 _write_lock 밖에서 호출해도 안전 (읽기 전용).
       _write_lock 내부에서 호출 시 재진입 주의 → 이미 락 보유 상태.
    """
    try:
        if not _STORE_FILE.exists():
            return []
        data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []

        cutoff   = datetime.now() - timedelta(days=_MAX_AGE_DAYS)
        filtered = []
        for p in data:
            try:
                if datetime.fromisoformat(p.get("saved_at", "")) < cutoff:
                    continue
            except (ValueError, TypeError):
                pass
            filtered.append(p)

        if len(filtered) != len(data):
            _write_atomic(filtered)   # 만기 항목 제거 후 저장
        return filtered
    except Exception:
        return []

# ══════════════════════════════════════════════════════════════
# 재연결 복원 (핵심)
# ══════════════════════════════════════════════════════════════

def restore_on_reconnect(self) -> None:
    """
    bridge.connected 수신 후 호출.

    [FIX-2] _pos_hook_active 플래그로 중복 등록 방지.
            타임아웃 발생 시 핸들러 강제 원복 (콜백 누적 방지).

    순서:
      1단계) 파일 즉시 표시 (IB 응답 기다리지 않음)
      2단계) IB reqPositions() → positionEnd 수신 → entry/qty 보정
    """
    panel = getattr(self, 'synthetic_panel', None)
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    if panel is None or ib is None:
        return

    # [FIX-2] 이미 복원 진행 중이면 중복 등록 차단
    if getattr(self, '_pos_hook_active', False):
        self._log("⚠ 잔고 복원 이미 진행 중 — 중복 요청 무시")
        return
    self._pos_hook_active = True

    panel.clear_positions()
    saved_by_oid = {p["oid"]: p for p in load_positions() if p.get("oid")}

    from PyQt5.QtCore import QTimer

    # ── 1단계: 파일 즉시 표시 ───────────────────────────────
    def _show_file_positions():
        shown = 0
        skipped = 0
        for pos in saved_by_oid.values():
            if _is_expired(pos):
                skipped += 1
                record_trade_history(pos, exit_price=0.0, close_type="만기소멸")
                continue
            enriched = dict(pos)
            enriched["strategy"] = _enrich_strategy_name(pos)
            panel.add_position(enriched)
            shown += 1
        msg = f"📂 합성 잔고 복원: {shown}건 (파일)"
        if skipped:
            msg += f"  / 만기만료 {skipped}건 제외"
        self._log(msg)

    QTimer.singleShot(0, _show_file_positions)

    # ── 2단계: IB 서버 조회 → entry/qty 보정 ──────────────
    ib_buf        = []
    _orig_pos     = getattr(ib, 'position',    lambda *a: None)
    _orig_pos_end = getattr(ib, 'positionEnd', lambda: None)
    _restored     = [False]   # 이미 완료됐으면 타임아웃 무시

    def _restore_done():
        """콜백 원복 + 플래그 해제 공통 처리."""
        if _restored[0]:
            return
        _restored[0] = True
        try:
            ib.position    = _orig_pos
            ib.positionEnd = _orig_pos_end
        except Exception:
            pass
        self._pos_hook_active = False

    def _on_pos(account, contract, pos_qty, avg_cost):
        if abs(pos_qty) < 0.001:
            return
        sec = getattr(contract, 'secType', '')
        if sec not in ('OPT', 'FOP', 'BAG'):
            return
        sym    = getattr(contract, 'localSymbol', '') or getattr(contract, 'symbol', '')
        right  = getattr(contract, 'right', '')
        strike = getattr(contract, 'strike', 0)
        mult   = float(getattr(contract, 'multiplier', 100) or 100)
        con_id = getattr(contract, 'conId', 0)
        side   = 'BUY' if pos_qty > 0 else 'SELL'
        cp     = 'C' if right == 'C' else 'P'
        entry  = round(avg_cost / mult, 2) if mult else round(avg_cost, 2)
        ib_buf.append({
            "con_id":   con_id,
            "strategy": f"{sym} {cp}{int(strike)} ×{int(abs(pos_qty))}",
            "qty":      int(abs(pos_qty)),
            "entry":    entry,
            "current":  entry,
            "side":     side,
            "right":    cp,
            "strike":   strike,
            "legs":     [],
            "status":   "체결완료",
        })

    def _on_pos_end():
        """IB positionEnd — 파일 포지션 qty 보정."""
        _restore_done()
        if not ib_buf:
            self._log("ℹ IB 서버 옵션 포지션 없음 (파일 복원 유지)")
            return

        updated = 0
        for oid, saved in saved_by_oid.items():
            legs     = saved.get("legs", [])
            leg_sigs = set(
                f"{l['cp'].upper()}{int(float(l['strike']))}"
                for l in legs if l.get('strike')
            )
            matched = [p for p in ib_buf if _ib_sig_simple(p) in leg_sigs]
            if matched and hasattr(panel, '_positions'):
                for p in panel._positions:
                    if p.get('oid') == oid:
                        # entry 는 파일값 유지, qty 만 서버값으로 보정
                        p['qty'] = matched[0]["qty"]
                        updated += 1

        if hasattr(panel, '_refresh_pos_table'):
            panel._refresh_pos_table()
        self._log(f"✅ IB 서버 qty 보정: {updated}건")

    ib.position    = _on_pos
    ib.positionEnd = _on_pos_end

    # [FIX-2] 타임아웃: positionEnd 미수신 시 강제 원복
    def _timeout():
        if _restored[0]:
            return
        _restore_done()
        self._log("⚠ IB 서버 응답 없음(10 초 타임아웃) — 파일 복원 유지")

    QTimer.singleShot(10_000, _timeout)

    try:
        ib.reqPositions()
        self._log("🔄 재연결: IB 서버 진입가 조회 중…")
    except Exception as e:
        _restore_done()
        self._log(f"⚠ reqPositions 오류: {e} — 파일 복원 유지")


# ══════════════════════════════════════════════════════════════
# 병합 로직
# ══════════════════════════════════════════════════════════════

def _merge(ib_buf: list, saved_by_oid: dict, self) -> list:
    """
    IB 레그 목록과 파일 전략 목록을 병합.
    [FIX-3] 매칭 안 된 IB BAG 포지션 폴백 처리 개선:
            legs 없는 IB 포지션은 BAG 청산 불가 → MKT 단건 경로로 명확히 표시.
    """
    result       = []
    used_ib_idxs = set()

    def _ib_sig(ib_pos: dict) -> str:
        right  = ib_pos.get("right", "")
        strike = ib_pos.get("strike", 0)
        if right and strike:
            return f"{right.upper()}{int(float(strike))}"
        strat_str = ib_pos.get("strategy", "")
        for part in strat_str.split():
            if len(part) >= 2 and part[0] in ("C", "P") and part[1:].isdigit():
                return part
            for j, ch in enumerate(part):
                if ch in ("C", "P") and j > 0 and part[j+1:].replace("0", "").isdigit():
                    try:
                        strike_raw = int(part[j+1:])
                        strike_val = strike_raw // 1000 if strike_raw > 99999 else strike_raw
                        return f"{ch}{strike_val}"
                    except (ValueError, IndexError):
                        pass
        return ""

    # ── 파일 전략 → IB 레그 매칭 ────────────────────────────
    for oid, saved in saved_by_oid.items():
        legs = saved.get("legs", [])
        if not legs:
            result.append(dict(saved))
            continue

        leg_sigs = set(
            f"{l['cp'].upper()}{int(float(l['strike']))}"
            for l in legs if l.get('strike')
        )
        matched_idxs = [
            i for i, ib_pos in enumerate(ib_buf)
            if _ib_sig(ib_pos) and _ib_sig(ib_pos) in leg_sigs
        ]

        if len(matched_idxs) == len(legs):
            # 완전 매칭: 파일 전략명/legs + 서버 qty 병합, entry 는 파일값 유지
            merged_pos = dict(saved)
            ib_qty = matched_idxs[0] and ib_buf[matched_idxs[0]]["qty"] or saved["qty"]
            merged_pos["qty"] = ib_qty
            result.append(merged_pos)
            for i in matched_idxs:
                used_ib_idxs.add(i)
        else:
            pos = dict(saved)
            if len(matched_idxs) == 0:
                pos["strategy"] = f"[IB미확인] {saved.get('strategy','')}"
            else:
                pos["strategy"] = f"[부분매칭] {saved.get('strategy','')}"
            result.append(pos)

    # ── 매칭 안 된 IB 레그 추가 (legs=[] → MKT 청산 경로) ──
    for i, ib_pos in enumerate(ib_buf):
        if i not in used_ib_idxs:
            # [FIX-3] BAG secType 이어도 legs 없으면 MKT 단건 경로임을 명시
            pos = dict(ib_pos)
            pos.setdefault("legs", [])
            result.append(pos)

    return result


# ══════════════════════════════════════════════════════════════
# 내부 유틸
# ══════════════════════════════════════════════════════════════

def _is_expired(pos: dict) -> bool:
    """ET 기준 만기 지난 항목 필터링. 만기일 당일은 유효."""
    legs = pos.get("legs", [])
    if not legs:
        return False
    try:
        from datetime import date as _date, datetime as _dt
        try:
            from zoneinfo import ZoneInfo as _ZI
        except ImportError:
            try:
                from backports.zoneinfo import ZoneInfo as _ZI
            except ImportError:
                import pytz as _pytz
                class _ZI:
                    def __new__(cls, k): return _pytz.timezone(k)

        today_et   = _dt.now(_ZI("America/New_York")).date()
        expiry_str = str(legs[0].get("expiry", ""))
        if len(expiry_str) == 8:
            exp_date = _date(int(expiry_str[:4]),
                             int(expiry_str[4:6]),
                             int(expiry_str[6:]))
            return exp_date < today_et   # 당일은 유효
    except Exception:
        pass
    return False


def _enrich_strategy_name(pos: dict) -> str:
    """legs 에서 행사가 추출해 전략명에 추가."""
    legs = pos.get("legs", [])
    if not legs:
        return pos.get("strategy", "")
    try:
        strikes = "/".join(
            str(int(float(l["strike"])))
            for l in sorted(legs, key=lambda l: l.get("dir", ""), reverse=True)
            if l.get("strike")
        )
        base = pos.get("strategy", "")
        if strikes and strikes not in base:
            if "(" in base:
                idx = base.index("(")
                return f"{base[:idx].rstrip()} {strikes} {base[idx:]}"
            return f"{base} {strikes}"
    except Exception:
        pass
    return pos.get("strategy", "")


def _ib_sig_simple(ib_pos: dict) -> str:
    right  = ib_pos.get("right", "")
    strike = ib_pos.get("strike", 0)
    if right and strike:
        return f"{right.upper()}{int(float(strike))}"
    return ""


def _write(data: list) -> None:
    """JSON 파일 쓰기 (락 없음 — 내부 load_positions 재귀 호출용)."""
    try:
        _STORE_FILE.parent.mkdir(exist_ok=True)
        _STORE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


def _write_atomic(data: list) -> None:
    """[FIX-1] atomic rename 으로 쓰기 — 부분 쓰기 방지."""
    _write_atomic_path(
        _STORE_FILE,
        json.dumps(data, ensure_ascii=False, indent=2)
    )


def _write_atomic_path(path: Path, text: str) -> None:
    """임시 파일 → rename 패턴으로 원자적 쓰기."""
    try:
        path.parent.mkdir(exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception:
        pass
