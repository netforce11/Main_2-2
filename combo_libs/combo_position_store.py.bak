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
  [FIX-ENTRY] save_one_position — current(현재가) 함께 저장
              재접속 후 스트림 재개 전까지 마지막 현재가로 수익률 표시
              load_positions — current 없으면 entry 로 폴백 (하위호환)
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
    [FIX-ENTRY] current(현재가)도 함께 저장 → 재접속 후 수익률 즉시 표시.
    status != '체결완료'/'보유' 이면 저장하지 않음.
    """
    if pos.get("status") not in ("체결완료", "보유"):
        return
    try:
        with _write_lock:
            existing = load_positions()
            oid   = pos.get("oid")
            entry = dict(pos)
            entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))
            # [FIX-ENTRY] current 가 0 이거나 없으면 entry 값으로 보존
            if not entry.get("current"):
                entry["current"] = entry.get("entry", 0.0)

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


def update_position_current(oid: int, current: float) -> None:
    """
    [FIX-ENTRY] 실시간 현재가 갱신 시 파일도 업데이트.
    combo_order_callbacks._on_tick 에서 update_position_prices 호출 후 연동.
    쓰기 빈도 최적화: 값이 바뀌었을 때만 저장 (0.01 이상 차이).
    """
    try:
        with _write_lock:
            existing = load_positions()
            for p in existing:
                if p.get("oid") == oid:
                    old = float(p.get("current", 0))
                    if abs(old - current) < 0.01:
                        return   # 변화 미미 → 저장 스킵
                    p["current"] = round(current, 2)
                    _write_atomic(existing)
                    return
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


def manual_remove_position(oid: int, panel=None, ref=None,
                            log_fn=None) -> None:
    """
    [MANUAL-DEL] UI 🗑 버튼에서 호출 — 파일 + 패널 + 스트림 동시 정리.
    주문 없이 쓰레기 잔고를 수동으로 즉시 삭제할 때 사용.
    """
    # 1. 파일 제거
    remove_position(oid)

    # 2. 패널 행 제거
    if panel and hasattr(panel, 'remove_position_by_oid'):
        panel.remove_position_by_oid(oid)

    # 3. 가격 스트림 해제
    if ref:
        try:
            from combo_order_callbacks import stop_position_price_stream
            stop_position_price_stream(ref, oid)
        except Exception:
            pass

    if log_fn:
        log_fn(f"🗑 [수동삭제] OID={oid} 제거 완료")


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
            # [FIX-S] 기존 파일의 "체결완료" → "보유" 마이그레이션
            if p.get("status") == "체결완료":
                p["status"] = "보유"
            # [FIX-ENTRY] current 없거나 0 이면 entry 로 폴백 (하위호환)
            if not p.get("current"):
                p["current"] = p.get("entry", 0.0)
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
            "status":   "보유",   # [FIX-S] "체결완료" → "보유"
        })

    def _on_pos_end():
        """IB positionEnd — 파일 포지션 qty 보정 + 파일 미저장 포지션 추가.

        [FIX-Q] 기존: 파일 기준 qty 보정만
                → 파일에 없는 IB 포지션(FIX-P 이전 버그 등)은 재연결 후에도 누락
                수정: ib_buf 중 파일 미매칭 항목을 패널에 직접 추가 + 파일 저장
        [FIX-EXEC] IB 서버 포지션 없음 → reqExecutions 로 오늘 청산 여부 확인
                   청산 체결 내역 있으면 파일/패널에서 해당 포지션 제거
        """
        _restore_done()

        if not ib_buf:
            self._log("ℹ IB 서버 옵션 포지션 없음 — 거래내역 조회로 청산 여부 확인")
            _check_executions_and_clean(self, panel, saved_by_oid)
            return

        # ── 파일 포지션들의 레그 시그니처 집합 (매칭 판별용) ───
        file_leg_sigs = set()
        for saved in saved_by_oid.values():
            for l in saved.get("legs", []):
                if l.get("strike"):
                    file_leg_sigs.add(
                        f"{l['cp'].upper()}{int(float(l['strike']))}")

        # ── IB 서버에 없는 파일 포지션 → 청산 완료로 판단 ──────
        # [FIX-EXEC-A] IB 포지션 시그니처에 만기 포함 — 같은 행사가 다른 만기 오매칭 방지
        ib_sigs = set()
        for ib_pos in ib_buf:
            sig = _ib_sig_simple(ib_pos)
            expiry = str(ib_pos.get("expiry", "")).replace('-', '')[:8]
            if sig:
                # 만기 있으면 "P7405:20260514", 없으면 "P7405" (하위호환)
                ib_sigs.add(f"{sig}:{expiry}" if expiry else sig)
                ib_sigs.add(sig)   # 만기 없는 매칭도 허용 (IB 응답 형식 차이 대응)

        for oid, saved in list(saved_by_oid.items()):
            legs = saved.get("legs", [])
            leg_sigs = set(
                f"{l['cp'].upper()}{int(float(l['strike']))}:"
                f"{str(l.get('expiry','')).replace('-','')[:8]}"
                for l in legs if l.get("strike")
            )
            # 모든 레그 시그니처(만기 포함)가 IB 서버에 없으면 → 청산 완료
            if leg_sigs and not any(
                sig in ib_sigs or sig.split(':')[0] in ib_sigs
                for sig in leg_sigs
            ):
                self._log(f"🗑 [FIX-EXEC] IB 서버 미존재 → 청산 완료 판단: OID={oid}  {saved.get('strategy','')}")
                if panel and hasattr(panel, 'remove_position_by_oid'):
                    panel.remove_position_by_oid(oid)
                remove_position(oid)
                del saved_by_oid[oid]
                try:
                    from combo_order_callbacks import stop_position_price_stream
                    stop_position_price_stream(self, oid)
                except Exception:
                    pass

        # ── 기존: 파일 포지션 qty 보정 ─────────────────────────
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
                        p['qty'] = matched[0]["qty"]
                        updated += 1

        # ── [FIX-Q] IB 서버에만 있는 포지션 → 패널/파일 추가 ──
        added = 0
        for ib_pos in ib_buf:
            sig = _ib_sig_simple(ib_pos)
            if sig and sig not in file_leg_sigs:
                enriched = dict(ib_pos)
                enriched.setdefault("status", "보유")
                enriched.setdefault(
                    "oid", int(datetime.now().timestamp() * 1000) % 100000)
                enriched["strategy"] = (
                    f"[서버복원] {enriched.get('strategy', sig)}")
                if panel and hasattr(panel, 'add_position'):
                    panel.add_position(enriched)
                try:
                    save_one_position(enriched)
                except Exception:
                    pass
                self._log(
                    f"⚠ [FIX-Q] 파일 미저장 포지션 복원: "
                    f"{enriched['strategy']}")
                added += 1

        if hasattr(panel, '_refresh_pos_table'):
            panel._refresh_pos_table()
        self._log(
            f"✅ IB 서버 qty 보정: {updated}건"
            + (f"  / 누락 포지션 추가: {added}건" if added else ""))

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

    # [FIX-R] 장외 시간 포함 delayed quote 허용 + 복원 포지션 conId 직접 확보
    # 체인 동기화 없이도 실시간 손익 스트림이 시작될 수 있도록
    try:
        ib.reqMarketDataType(3)   # 3=delayed → 장외에도 시세 수신
    except Exception:
        pass

    # 저장된 legs 의 conId 를 캐시에서 보완 후 스트림 시작
    QTimer.singleShot(500, lambda: _ensure_restored_streams(self, saved_by_oid))


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


# ══════════════════════════════════════════════════════════════
# [FIX-EXEC] 거래내역 조회 → 청산 완료 포지션 파일/패널 제거
# ══════════════════════════════════════════════════════════════

def _check_executions_and_clean(self, panel, saved_by_oid: dict) -> None:
    """
    IB reqExecutions() 로 오늘 체결 내역을 조회.
    파일에 남아있는 포지션 중 청산 체결(반대 방향 매도/매수)이 확인되면
    파일과 패널에서 제거한다.

    [FIX-EXEC-A] 시그니처에 만기(expiry) 포함 — 같은 행사가 다른 만기 오매칭 방지
    [FIX-EXEC-C] ExecutionFilter.time 으로 오늘 날짜 필터 — 이전 날 체결 내역 혼입 방지

    호출 시점: _on_pos_end 에서 IB 서버 포지션이 없을 때.
    """
    from PyQt5.QtCore import QTimer as _QT
    ib = getattr(getattr(self, 'mw', None), 'ib', None)
    if not ib or not saved_by_oid:
        return

    exec_buf  = []   # {side, strike, right, expiry_date} 체결 목록
    _orig_exec     = getattr(ib, 'execDetails',    lambda *a: None)
    _orig_exec_end = getattr(ib, 'execDetailsEnd', lambda *a: None)
    _done          = [False]

    def _cleanup():
        if _done[0]:
            return
        _done[0] = True
        try: ib.execDetails    = _orig_exec
        except Exception: pass
        try: ib.execDetailsEnd = _orig_exec_end
        except Exception: pass

    def _on_exec(req_id, contract, execution):
        sec = getattr(contract, 'secType', '')
        if sec not in ('OPT', 'FOP'):
            return
        side   = getattr(execution, 'side', '')      # 'BOT' or 'SLD'
        strike = getattr(contract, 'strike', 0)
        right  = getattr(contract, 'right', '').upper()

        # [FIX-EXEC-A] 만기 추출 — contract.lastTradeDateOrContractMonth (YYYYMMDD)
        expiry = str(getattr(contract, 'lastTradeDateOrContractMonth', '') or '')
        expiry = expiry.replace('-', '')[:8]   # "20260514-..." → "20260514"

        exec_buf.append({
            "side":   'BUY' if side == 'BOT' else 'SELL',
            "strike": float(strike),
            "right":  right,
            "expiry": expiry,
        })

    def _on_exec_end(req_id):
        _cleanup()
        if not exec_buf:
            self._log("ℹ 오늘 체결 내역 없음 — 파일 포지션 유지")
            return

        # [FIX-EXEC-A] 시그니처: right + strike + side + expiry 모두 포함
        # → 같은 행사가 다른 만기 포지션 오매칭 완전 차단
        closed_sigs = set()
        for e in exec_buf:
            closed_sigs.add(
                f"{e['right']}{int(e['strike'])}:{e['side']}:{e['expiry']}")

        removed = 0
        for oid, saved in list(saved_by_oid.items()):
            legs = saved.get("legs", [])
            if not legs:
                continue

            # 모든 레그에 대해 반대 방향 체결이 오늘 있는지 확인
            close_confirmed = all(
                f"{l['cp'].upper()}{int(float(l['strike']))}:"
                f"{'SELL' if l['dir'] == 'BUY' else 'BUY'}:"
                f"{str(l.get('expiry', '')).replace('-','')[:8]}"
                in closed_sigs
                for l in legs if l.get("strike")
            )
            if close_confirmed:
                self._log(
                    f"🗑 [FIX-EXEC] 거래내역 청산 확인 → 제거: "
                    f"OID={oid}  {saved.get('strategy','')}")
                if panel and hasattr(panel, 'remove_position_by_oid'):
                    panel.remove_position_by_oid(oid)
                remove_position(oid)
                try:
                    from combo_order_callbacks import stop_position_price_stream
                    stop_position_price_stream(self, oid)
                except Exception:
                    pass
                removed += 1

        if removed:
            self._log(f"✅ [FIX-EXEC] 거래내역 기반 청산 포지션 {removed}건 제거")
        else:
            self._log("ℹ [FIX-EXEC] 거래내역 확인 — 청산 미매칭, 파일 포지션 유지")

    ib.execDetails    = _on_exec
    ib.execDetailsEnd = _on_exec_end

    # 타임아웃 10초
    _QT.singleShot(10_000, _cleanup)

    try:
        from ibapi.execution import ExecutionFilter
        from datetime import date as _date
        ef = ExecutionFilter()
        # [FIX-EXEC-C] 오늘 날짜 이후 체결만 조회 — 이전 날 내역 혼입 방지
        ef.time = _date.today().strftime("%Y%m%d-00:00:00")
        ib.reqExecutions(9001, ef)
        self._log("🔍 [FIX-EXEC] 오늘 거래내역 조회 중…")
    except Exception as e:
        _cleanup()
        self._log(f"⚠ reqExecutions 오류: {e}")

def _ensure_restored_streams(self, saved_by_oid: dict) -> None:
    """
    [FIX-R] 재연결 후 복원 포지션의 실시간 스트림을 보장.

    문제: 장외 시간에는 체인 동기화(_bulk_fetch_conids)가 실행되지 않아
          conId 조회 → 스트림 시작 훅이 트리거되지 않는다.
    해결: restore_on_reconnect 완료 500ms 후 이 함수를 직접 호출해
          캐시에 conId 가 있는 레그는 즉시 스트림 시작.
          없는 레그는 reqContractDetails 로 개별 조회 후 스트림 시작.
    """
    panel = getattr(self, 'synthetic_panel', None)
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    if panel is None or ib is None or not saved_by_oid:
        return

    try:
        from combo_order_callbacks import _start_position_price_stream
        from combo_order_bag import _CONID_CACHE, _conid_key
    except ImportError:
        return

    # 심볼 확인
    sym_w  = getattr(self, 'edit_sym_combo', None)
    symbol = sym_w.text().strip().upper() if sym_w else "SPX"
    symbol = symbol.replace("SPXW", "SPX")

    already = set(getattr(self, '_pos_stream_tids', {}).keys())
    missing_legs = []   # (oid, leg_idx, pos, leg) — conId 미비 레그

    for oid, pos in saved_by_oid.items():
        if oid in already:
            continue
        if _is_expired(pos):
            continue
        legs = pos.get("legs", [])
        if not legs:
            continue

        all_have_conid = True
        for i, leg in enumerate(legs):
            if leg.get("con_id"):
                continue
            key = _conid_key(
                symbol,
                str(leg.get("cp", "")),
                float(leg.get("strike", 0)),
                str(leg.get("expiry", "")),
            )
            cid = _CONID_CACHE.get(key, 0)
            if cid:
                leg["con_id"] = cid
            else:
                all_have_conid = False
                missing_legs.append((oid, i, pos, leg))

        if all_have_conid:
            _start_position_price_stream(self, pos)
            self._log(f"📡 복원 스트림 시작(캐시): OID={oid}")

    if not missing_legs:
        return

    # conId 미비 레그 → reqContractDetails 개별 조회
    self._log(f"🔍 복원 스트림: conId 미비 {len(missing_legs)}레그 개별 조회")

    try:
        from core_contract import make_opt_contract
        from core import bridge as _bridge
    except ImportError:
        return

    from PyQt5.QtCore import QTimer

    _base_rid = 8800
    _rid_map  = {}   # rid → (oid, leg_idx, pos, leg)
    _oid_done = {}   # oid → set of resolved leg indices
    _oid_total = {}  # oid → total leg count needing resolution

    for seq, (oid, i, pos, leg) in enumerate(missing_legs):
        rid = _base_rid + seq
        _rid_map[rid] = (oid, i, pos, leg)
        _oid_done.setdefault(oid, set())
        _oid_total[oid] = _oid_total.get(oid, 0) + 1

    _conn = [None, None]

    def _cleanup():
        try:
            if _conn[0]: _bridge.contract_details_sig.disconnect(_conn[0])
        except Exception: pass
        try:
            if _conn[1]: _bridge.contract_details_end_sig.disconnect(_conn[1])
        except Exception: pass

    def _on_cd(req_id, cd):
        if req_id not in _rid_map: return
        oid, i, pos, leg = _rid_map[req_id]
        cid = cd.contract.conId
        if cid > 0:
            leg["con_id"] = cid
            from combo_order_bag import _CONID_CACHE, _conid_key, _save_conid_cache
            key = _conid_key(symbol, str(leg.get("cp", "")),
                             float(leg.get("strike", 0)),
                             str(leg.get("expiry", "")))
            _CONID_CACHE[key] = cid
        _oid_done[oid].add(i)

    def _on_cd_end(req_id):
        if req_id not in _rid_map: return
        oid, i, pos, leg = _rid_map[req_id]
        if len(_oid_done.get(oid, set())) >= _oid_total.get(oid, 1):
            if oid not in getattr(self, '_pos_stream_tids', {}):
                _start_position_price_stream(self, pos)
                self._log(f"📡 복원 스트림 시작(조회): OID={oid}")
        if len(_oid_done) >= len(_oid_total) and \
                all(len(v) >= _oid_total[k] for k, v in _oid_done.items()):
            _cleanup()

    _conn[0] = _on_cd
    _conn[1] = _on_cd_end
    _bridge.contract_details_sig.connect(_on_cd)
    _bridge.contract_details_end_sig.connect(_on_cd_end)

    def _send(idx):
        if idx >= len(missing_legs): return
        oid, i, pos, leg = missing_legs[idx]
        rid = _base_rid + idx
        try:
            ib.reqContractDetails(
                rid,
                make_opt_contract(
                    symbol=symbol,
                    strike=float(leg.get("strike", 0)),
                    right=str(leg.get("cp", "")),
                    expiry=str(leg.get("expiry", "")),
                )
            )
        except Exception as e:
            self._log(f"⚠ 복원 conId 조회 실패 레그{i}: {e}")
        QTimer.singleShot(100, lambda: _send(idx + 1))

    _send(0)
    QTimer.singleShot(len(missing_legs) * 100 + 8000, _cleanup)