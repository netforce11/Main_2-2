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
_STORE_FILE  = Path(__file__).resolve().parent / "data" / "synthetic_positions.json"
_MAX_AGE_DAYS = 7


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

    # 파일에서 전략명/legs 보존 데이터 로드
    saved_by_oid = {p["oid"]: p for p in load_positions() if p.get("oid")}

    # IB 포지션 수집 버퍼
    ib_buf = []

    _orig_pos     = getattr(ib, 'position',    lambda *a: None)
    _orig_pos_end = getattr(ib, 'positionEnd', lambda: None)

    def _on_pos(account, contract, pos_qty, avg_cost):
        """IB position 콜백 — OPT/FOP 만 수집."""
        if abs(pos_qty) < 0.001:
            return
        sec = getattr(contract, 'secType', '')
        if sec not in ('OPT', 'FOP'):
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
            "right":    cp,       # 매칭용: 'C' or 'P'
            "strike":   strike,   # 매칭용: float
            "legs":     [],
            "status":   "체결완료",
        })

    def _on_pos_end():
        """IB positionEnd 콜백 — 매칭 후 패널 갱신."""
        # 콜백 원복
        try:
            ib.position    = _orig_pos
            ib.positionEnd = _orig_pos_end
        except Exception:
            pass

        merged = _merge(ib_buf, saved_by_oid, self)

        from PyQt5.QtCore import QTimer
        def _apply():
            for pos in merged:
                panel.add_position(pos)
            count = len(merged)
            self._log(
                f"📂 합성 잔고 복원: {count}건 "
                f"(IB {len(ib_buf)}레그 / 파일 {len(saved_by_oid)}전략)")
        QTimer.singleShot(0, _apply)

    ib.position    = _on_pos
    ib.positionEnd = _on_pos_end

    # 타임아웃 안전망 (5초)
    from PyQt5.QtCore import QTimer
    def _timeout():
        if ib.position is _on_pos:        # 아직 콜백 대기 중
            ib.position    = _orig_pos
            ib.positionEnd = _orig_pos_end
            self._log("⚠ reqPositions 타임아웃 — 파일 데이터만 복원")
            # 파일 데이터만이라도 표시
            for pos in saved_by_oid.values():
                panel.add_position(pos)
    QTimer.singleShot(5000, _timeout)

    try:
        ib.reqPositions()
        self._log("🔄 재연결: IB 포지션 조회 중…")
    except Exception as e:
        ib.position    = _orig_pos
        ib.positionEnd = _orig_pos_end
        self._log(f"❌ reqPositions 오류: {e}")
        # 파일 데이터 폴백
        for pos in saved_by_oid.values():
            panel.add_position(pos)


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
            # 부분 매칭 or 미매칭 → 파일 데이터만 표시
            pos = dict(saved)
            pos["strategy"] = f"[미확인] {saved.get('strategy','')}"
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