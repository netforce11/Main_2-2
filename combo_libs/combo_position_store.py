"""
combo_position_store.py — 합성 잔고 영속화 + 재연결 복원
──────────────────────────────────────────────────────────────
저장 경로: data/synthetic_positions.json

■ 저장 시점
  - 체결 완료 (_on_order_status "Filled")

■ 제거 시점
  - 취소 확인 (_on_order_status "Cancelled")
  - 청산 주문 전송 직전 (_on_close_position_order)

■ 복원 시점 (재연결)
  - bridge.connected → _on_pos_reconnect_hook()
    1) IB reqPositions()  → 실제 수량 / 진입가 (서버 정확값)
    2) load_positions()   → 전략명 / legs 배열 (파일 보존값)
    3) oid 매칭 → 두 값 병합 → panel.add_position()

■ 저장 포맷 (체결완료 항목만)
  [
    {
      "strategy": "아이언 콘도르",
      "qty": 1,
      "entry": 2.35,
      "current": 2.35,
      "side": "BUY",
      "oid": 12345,
      "legs": [
        {"dir":"BUY","cp":"P","strike":5440,"prem":"1.10","qty":1,"expiry":"20250502"},
        ...
      ],
      "status": "체결완료",
      "saved_at": "2025-05-02T14:30:00"
    }
  ]

■ 설계 원칙
  - 파일 I/O 실패는 조용히 무시 (거래 로직에 영향 없음)
  - "체결완료" 상태만 저장
  - 7일 이상 지난 항목 자동 purge
──────────────────────────────────────────────────────────────
"""

from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path

# 실행 디렉토리와 무관하게 항상 이 파일 기준 상위/data 폴더에 저장
_STORE_FILE    = Path(__file__).resolve().parent / "data" / "synthetic_positions.json"
_HISTORY_FILE  = Path(__file__).resolve().parent / "data" / "trade_history.json"
_MAX_AGE_DAYS  = 7


# ══════════════════════════════════════════════════════════════
# 저장 / 제거
# ══════════════════════════════════════════════════════════════

def save_one_position(pos: dict) -> None:
    """
    체결 완료된 포지션 1건을 파일에 추가/갱신.
    status != '체결완료' 이면 저장하지 않음.
    같은 oid가 이미 있으면 덮어씀.
    """
    if pos.get("status") != "체결완료":
        return
    try:
        existing = load_positions()
        oid = pos.get("oid")
        entry = dict(pos)
        entry.setdefault("saved_at", datetime.now().isoformat(timespec="seconds"))

        for i, p in enumerate(existing):
            if oid and p.get("oid") == oid:
                existing[i] = entry
                _write(existing)
                return

        existing.append(entry)
        _write(existing)
    except Exception:
        pass


def remove_position(oid: int) -> None:
    """oid에 해당하는 항목을 파일에서 제거."""
    try:
        existing = load_positions()
        updated  = [p for p in existing if p.get("oid") != oid]
        if len(updated) != len(existing):
            _write(updated)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 거래 이력 기록
# ══════════════════════════════════════════════════════════════

def record_trade_history(pos: dict, exit_price: float, close_type: str) -> None:
    """
    청산/만기소멸 시 실현 손익을 trade_history.json 에 기록.

    close_type: "청산주문" | "만기소멸"

    손익 계산:
      - BUY(데빗) 전략: 청산가 - 진입가 → 양수=이익 / 음수=손실
      - SELL(크레딧) 전략: 진입가 - 청산가 → 양수=이익 / 음수=손실
      - 만기소멸: exit_price=0 고정 (전액 손실 or 전액 이익)
      - 단위: 1계약 = 100배수
    """
    try:
        entry  = float(pos.get("entry",   0))
        qty    = int(pos.get("qty",       1))
        side   = pos.get("side", "BUY").upper()

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
    """trade_history.json 에 1건 추가."""
    try:
        _HISTORY_FILE.parent.mkdir(exist_ok=True)
        data = load_trade_history()
        data.append(record)
        _HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# 불러오기
# ══════════════════════════════════════════════════════════════

def load_positions() -> list:
    """
    저장된 포지션 목록 반환.
    파일 없거나 파싱 실패 시 빈 리스트.
    7일 초과 항목은 자동 제거.
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
            _write(filtered)

        return filtered
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════
# 재연결 복원 (핵심)
# ══════════════════════════════════════════════════════════════

def restore_on_reconnect(self) -> None:
    """
    bridge.connected 수신 후 호출.

    순서:
      1) panel 초기화
      2) IB reqPositions() 요청
      3) positionEnd 수신 후 파일과 oid 매칭
      4) 병합 결과를 panel.add_position()으로 표시

    병합 규칙:
      - oid 매칭 성공 → 파일(전략명/legs) + 서버(qty/entry) 병합
      - oid 매칭 실패 → 서버 데이터만 (레그 단위 표시)
    """
    panel = getattr(self, 'synthetic_panel', None)
    ib    = getattr(getattr(self, 'mw', None), 'ib', None)
    if panel is None or ib is None:
        return

    panel.clear_positions()

    # ── 1단계: 파일 데이터 즉시 표시 ───────────────────────
    saved_by_oid = {p["oid"]: p for p in load_positions() if p.get("oid")}

    from PyQt5.QtCore import QTimer
    from datetime import date as _date

    def _is_expired(pos: dict) -> bool:
        """ET 기준 만기 지난 항목 필터링."""
        legs = pos.get("legs", [])
        if not legs:
            return False
        try:
            from datetime import datetime as _dt
            try:
                from zoneinfo import ZoneInfo as _ZI
            except ImportError:
                try:
                    from backports.zoneinfo import ZoneInfo as _ZI
                except ImportError:
                    import pytz as _pytz
                    class _ZI:
                        def __new__(cls, k): return _pytz.timezone(k)
            # ET 기준 오늘 날짜
            today_et = _dt.now(_ZI("America/New_York")).date()
            expiry_str = str(legs[0].get("expiry", ""))
            if len(expiry_str) == 8:
                exp_date = _date(int(expiry_str[:4]),
                                 int(expiry_str[4:6]),
                                 int(expiry_str[6:]))
                # 만기일 당일은 유효 (ET 16:00 마감이므로)
                return exp_date < today_et
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
                for l in sorted(legs, key=lambda l: l.get("dir",""), reverse=True)
                if l.get("strike")
            )
            base = pos.get("strategy", "")
            # 이미 행사가 포함된 경우 중복 방지
            if strikes and strikes not in base:
                # 괄호 앞에 행사가 삽입: "풋 스프레드 (풋매수+풋매도)" → "풋 스프레드 7270/7265 (풋매수+풋매도)"
                if "(" in base:
                    idx = base.index("(")
                    return f"{base[:idx].rstrip()} {strikes} {base[idx:]}"
                return f"{base} {strikes}"
        except Exception:
            pass
        return pos.get("strategy", "")

    def _show_file_positions():
        shown = 0
        skipped = 0
        for pos in saved_by_oid.values():
            if _is_expired(pos):
                skipped += 1
                # 만기 소멸 → 실현손익 기록 (exit=0, 전액 손실/이익)
                record_trade_history(pos, exit_price=0.0, close_type="만기소멸")
                continue
            # 행사가 전략명 보강
            enriched = dict(pos)
            enriched["strategy"] = _enrich_strategy_name(pos)
            panel.add_position(enriched)
            shown += 1

            # 실시간 스트림은 conId 준비 후 시작
            # → combo_ui_left_chain._start_restored_position_streams() 에서 처리

        msg = f"📂 합성 잔고 복원: {shown}건 (파일)"
        if skipped:
            msg += f"  / 만기만료 {skipped}건 제외"
        self._log(msg)
    QTimer.singleShot(0, _show_file_positions)

    # ── 2단계: IB 서버 조회 → 진입가 업데이트 ──────────────
    # positionEnd 수신 시 파일 항목의 entry/current 를 서버 값으로 갱신
    ib_buf = []
    _orig_pos     = getattr(ib, 'position',    lambda *a: None)
    _orig_pos_end = getattr(ib, 'positionEnd', lambda: None)

    def _on_pos(account, contract, pos_qty, avg_cost):
        """IB position 콜백 — OPT/FOP/BAG 수집."""
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
        """IB positionEnd — 파일 포지션 진입가 업데이트."""
        try:
            ib.position    = _orig_pos
            ib.positionEnd = _orig_pos_end
        except Exception:
            pass

        if not ib_buf:
            self._log("ℹ IB 서버 옵션 포지션 없음 (파일 복원 유지)")
            return

        # 파일 포지션 진입가를 IB 서버값으로 업데이트
        updated = 0
        for oid, saved in saved_by_oid.items():
            legs = saved.get("legs", [])
            leg_sigs = set(
                f"{l['cp'].upper()}{int(float(l['strike']))}"
                for l in legs if l.get('strike')
            )
            matched = [ib_p for ib_p in ib_buf
                       if _ib_sig_simple(ib_p) in leg_sigs]
            if matched:
                # IB avg_cost 는 레그별 개별 가격이라 BAG net 과 다름
                # → 파일에 저장된 entry (체결 당시 BAG net price) 우선 사용
                # IB 서버는 포지션 존재 확인 용도로만 사용
                avg_e = saved["entry"]  # 파일 저장값 유지
                if hasattr(panel, '_positions'):
                    for p in panel._positions:
                        if p.get('oid') == oid:
                            # entry 는 파일값 유지, qty 만 서버값으로 보정
                            ib_qty = matched[0]["qty"] if matched else p.get("qty", 1)
                            p['qty'] = ib_qty
                            updated += 1
        if hasattr(panel, '_refresh_pos_table'):
            panel._refresh_pos_table()
        self._log(f"✅ IB 서버 진입가 업데이트: {updated}건")

    def _ib_sig_simple(ib_pos: dict) -> str:
        right  = ib_pos.get("right", "")
        strike = ib_pos.get("strike", 0)
        if right and strike:
            return f"{right.upper()}{int(float(strike))}"
        return ""

    ib.position    = _on_pos
    ib.positionEnd = _on_pos_end

    # 10초 타임아웃 — 응답 없으면 콜백 원복만
    def _timeout():
        if ib.position is _on_pos:
            ib.position    = _orig_pos
            ib.positionEnd = _orig_pos_end
            self._log("⚠ IB 서버 응답 없음 — 파일 복원 유지")
    QTimer.singleShot(10000, _timeout)

    try:
        ib.reqPositions()
        self._log("🔄 재연결: IB 서버 진입가 조회 중…")
    except Exception as e:
        ib.position    = _orig_pos
        ib.positionEnd = _orig_pos_end
        self._log(f"⚠ reqPositions 오류: {e} — 파일 복원 유지")


# ══════════════════════════════════════════════════════════════
# 병합 로직
# ══════════════════════════════════════════════════════════════

def _merge(ib_buf: list, saved_by_oid: dict, self) -> list:
    """
    IB 레그 목록과 파일 전략 목록을 병합.

    매칭 방법:
      파일의 legs 배열에 있는 strike/cp 조합이
      ib_buf의 strategy/right/strike 에 모두 포함되면 같은 전략으로 판단.

    IB localSymbol 형식 예: "SPXW  260502C05500000"
      → right='C', strike=5500 으로 파싱.

    반환:
      - 매칭된 전략: 파일 전략명/legs + 서버 qty/entry 로 병합한 dict
      - 매칭 안 된 IB 레그: 서버 데이터 그대로
      - 매칭 안 된 파일 전략: 서버 없이 파일만으로 표시
    """
    result       = []
    used_ib_idxs = set()

    def _ib_sig(ib_pos: dict) -> str:
        """
        IB 포지션 dict에서 'C5500' 형태의 식별 문자열 추출.

        strategy 문자열 예:
          "SPX C5500 ×1"        → parts[1] = "C5500"  (정상 케이스)
          "SPXW  260502C05500000 ×1" → 파싱 실패 가능

        IB reqPositions의 localSymbol 은 contract 객체에서 직접 오므로
        strategy 문자열 외에 right/strike 필드도 함께 저장된 경우 활용.
        """
        # 직접 right/strike 필드가 있으면 우선 사용 (가장 신뢰성 높음)
        right  = ib_pos.get("right", "")
        strike = ib_pos.get("strike", 0)
        if right and strike:
            return f"{right.upper()}{int(float(strike))}"

        # strategy 문자열에서 파싱 시도
        strat_str = ib_pos.get("strategy", "")
        parts = strat_str.split()
        for part in parts:
            # "C5500", "P5400" 패턴 직접 탐색
            if len(part) >= 2 and part[0] in ("C", "P") and part[1:].isdigit():
                return part
            # "SPXW  260502C05500000" 형태: 대문자+숫자 중 C/P 위치 탐색
            for j, ch in enumerate(part):
                if ch in ("C", "P") and j > 0 and part[j+1:].replace("0","").isdigit():
                    try:
                        strike_raw = int(part[j+1:])
                        # IB는 strike를 1000배로 인코딩 (5500000 → 5500)
                        strike_val = strike_raw // 1000 if strike_raw > 99999 else strike_raw
                        return f"{ch}{strike_val}"
                    except (ValueError, IndexError):
                        pass
        return ""

    # ── 파일 전략 → IB 레그와 매칭 ──────────────────────────
    for oid, saved in saved_by_oid.items():
        legs = saved.get("legs", [])

        if not legs:
            result.append(dict(saved))
            continue

        # 이 전략의 레그 특징 (strike + cp 집합)
        leg_sigs = set(
            f"{l['cp'].upper()}{int(float(l['strike']))}"
            for l in legs if l.get('strike')
        )

        # IB 버퍼에서 같은 레그 집합을 가진 항목들 찾기
        matched_idxs = []
        for i, ib_pos in enumerate(ib_buf):
            sig = _ib_sig(ib_pos)
            if sig and sig in leg_sigs:
                matched_idxs.append(i)

        if len(matched_idxs) == len(legs):
            # 완전 매칭: 파일 전략명/legs + 서버 진입가 병합
            total_entry = sum(ib_buf[i]["entry"] * ib_buf[i]["qty"]
                              for i in matched_idxs)
            total_qty   = sum(ib_buf[i]["qty"] for i in matched_idxs)
            avg_entry   = round(total_entry / total_qty, 2) if total_qty else saved["entry"]

            merged_pos = dict(saved)
            merged_pos["entry"]   = avg_entry
            merged_pos["current"] = avg_entry
            result.append(merged_pos)

            for i in matched_idxs:
                used_ib_idxs.add(i)
        else:
            # 부분 매칭 or 미매칭 → 파일 데이터 그대로 표시
            # (IB 서버 미매칭이어도 파일에 있으면 표시)
            pos = dict(saved)
            if len(matched_idxs) == 0:
                # IB 서버에 없음 → 만기됐거나 청산된 포지션
                pos["strategy"] = f"[IB미확인] {saved.get('strategy','')}"
            else:
                # 일부 레그만 매칭
                pos["strategy"] = f"[부분매칭] {saved.get('strategy','')}"
            result.append(pos)

    # ── 매칭 안 된 IB 레그 → 그냥 추가 ─────────────────────
    for i, ib_pos in enumerate(ib_buf):
        if i not in used_ib_idxs:
            result.append(ib_pos)

    return result


# ══════════════════════════════════════════════════════════════
# 내부 유틸
# ══════════════════════════════════════════════════════════════

def _write(data: list) -> None:
    """JSON 파일 쓰기. 실패 시 무시."""
    try:
        _STORE_FILE.parent.mkdir(exist_ok=True)
        _STORE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass