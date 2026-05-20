"""
night_alert_checker.py — 새벽 알림 발동 로직  v2.0
변경(v2.0):
  - 구간마다 독립 기준가: 시작 15분 전부터 ATM 풋 최저가 수집
  - 기준가 확정 후 ATM ±10개 스캔 → 상승률 최고 1개 대표 알림
  - status_summary() → 1분 TG 상태 메시지 삽입용
"""

from __future__ import annotations
import sys, os
from datetime import datetime
from collections import defaultdict

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from night_alert_template import load_config, NightSlot, get_active_slots

_STRIKE_STEP = 5
_SCAN_RANGE  = 10


class NightAlertChecker:

    def __init__(self, log_fn=None):
        self._log_fn       = log_fn or (lambda m: None)
        self._mw           = None
        self._fired:  dict[str, datetime] = {}
        self._cooldown_min = 10
        self._last_best: dict[str, tuple] = {}
        # 구간별 알람 카운터 & 활성 구간 추적 (세션 리셋용)
        self._alert_count: dict[str, int]      = defaultdict(int)
        self._slot_active:  dict[str, bool]    = {}  # label → 이전 tick 활성 여부
        # 구간별 샘플 버퍼: label → [(timestamp, prem), ...]
        self._samples: dict[str, list] = defaultdict(list)
        # 런타임 슬롯 캐시 (base_prem 보존용)
        self._slots:  dict[str, NightSlot] = {}

    # ── 주입 ─────────────────────────────────────────────────

    def set_main_window(self, mw):
        self._mw = mw

    def adjust_base(self, label: str, direction: int) -> str:
        """
        기준가 수동 조정. direction=+1 → 행사가 +5pt, -1 → -5pt.
        반환: 결과 메시지 문자열
        """
        rt = self._slots.get(label)
        if rt is None or rt.base_prem <= 0:
            return f"⚠️ [{label}] 기준가 미설정"
        mw = self._mw
        if mw is None:
            return f"⚠️ [{label}] mw 없음"
        cp_tab = getattr(mw, "tab_callput", mw)
        chain_put, chain_call = self._build_chain_dicts(cp_tab)
        new_strike = rt.base_strike + direction * 5
        chain = chain_put if rt.opt_type in ("P", "both") else chain_call
        new_prem = chain.get(new_strike)
        if new_prem is None:
            return f"⚠️ [{label}] {int(new_strike)} 행사가 데이터 없음"
        rt.base_strike = new_strike
        rt.base_prem   = new_prem
        rt.base_set_at = datetime.now().strftime("%H:%M") + "✋"
        msg = f"✋ [{label}] 기준가 수동조정: {rt.opt_type}{int(new_strike)} ${new_prem:.2f}"
        self._log_fn(msg)
        self._send_tg(msg)
        return msg

    # ── 외부 조회 ────────────────────────────────────────────

    def status_summary(self) -> str:
        """1분 TG 상태 메시지에 삽입할 새벽알림 요약."""
        try:
            cfg    = load_config()
            active = {s.label for s in get_active_slots(cfg)}
            lines  = ["🌙 새벽알림"]
            for slot in cfg.slots:
                rt    = self._slots.get(slot.label, slot)
                flag  = "✅" if slot.label in active else "⏸"
                base_s = (
                    f"기준가 {rt.opt_type}{int(rt.base_strike)} ${rt.base_prem:.2f}@{rt.base_set_at}"
                    f" [{self._alert_count.get(slot.label,0)}/{rt.max_alerts}회]"
                ) if rt.base_prem > 0 else "기준가 수집중"
                lines.append(
                    f"  {flag} {slot.label} [{slot.start_hhmm}~{slot.end_hhmm}]"
                    f" {slot.opt_type}/{slot.multiplier}x  {base_s}"
                )
            for label, (ot, strike, pct) in self._last_best.items():
                lines.append(f"  └ 최고감지: {ot}{int(strike)} {pct:.0f}%")
            return "\n".join(lines)
        except Exception as e:
            return f"🌙 새벽알림 오류: {e}"

    # ── 핵심 호출 ────────────────────────────────────────────

    def tick(self):
        """_on_tick() 에서 매 58초마다 호출."""
        try:
            self._run()
        except Exception as e:
            self._log_fn(f"⚠ NightAlertChecker 오류: {e}")

    # ── 내부 ─────────────────────────────────────────────────

    def _run(self):
        mw = self._mw
        if mw is None:
            return

        # ── 체인 데이터 접근 ─────────────────────────────────────
        # mw = TradingDashboard, 실제 데이터는 mw.tab_callput 안에 있음
        # put_data  = {REQ_PUT+i:  {'last': price, ...}}
        # call_data = {REQ_CALL+i: {'last': price, ...}}
        # put_strikes / call_strikes = [strike, ...] (인덱스 i 대응)
        cp_tab = getattr(mw, "tab_callput", mw)   # mw 자체가 CallPutGrid일 경우 대비
        chain_put, chain_call = self._build_chain_dicts(cp_tab)
        und = getattr(cp_tab, "und_price", None) or 0.0
        atm = round(und / _STRIKE_STEP) * _STRIKE_STEP if und > 0 else 0.0

        # 진단 로그 (최초 1회 또는 체인이 비어있을 때)
        if not getattr(self, "_chain_logged", False):
            self._log_fn(
                f"[진단] und={und:.1f} atm={atm:.0f} "
                f"put체인={len(chain_put)}개 call체인={len(chain_call)}개"
            )
            if chain_put:
                self._chain_logged = True

        cfg = load_config()
        # 런타임 슬롯 캐시 동기화 (새 구간 추가 대응)
        for slot in cfg.slots:
            if slot.label not in self._slots:
                self._slots[slot.label] = slot

        for slot in cfg.slots:
            if not slot.enabled:
                continue
            rt = self._slots[slot.label]

            is_active = slot.is_active_now()
            was_active = self._slot_active.get(slot.label, False)

            # 구간 새로 진입 시 카운터 리셋
            if is_active and not was_active:
                self._alert_count[slot.label] = 0
                self._fired.pop(slot.label, None)
                self._fired.pop(f"{slot.label}_pre", None)
                self._log_fn(f"🔄 [{slot.label}] 새 구간 진입 — 알람 카운터 리셋")
            self._slot_active[slot.label] = is_active

            # ── Phase 1: 샘플링 구간 ───────────────────────
            if slot.is_in_sampling_window():
                self._collect_sample(rt, atm, chain_put, chain_call)

            # ── Phase 2: 활성 구간 → 알림 평가 ────────────
            elif is_active:
                if rt.base_prem <= 0:
                    self._log_fn(f"⚠ [{slot.label}] 기준가 미확정 — 샘플 없음")
                    continue
                self._check_slot(rt, atm, chain_put, chain_call, cfg.tg_fmt)

    def _collect_sample(
        self, rt: NightSlot, atm: float,
        chain_put: dict, chain_call: dict,
    ):
        """샘플링 구간: ATM(또는 OTM) 프리미엄 수집 → 최저가로 base_prem 갱신."""
        if atm <= 0:
            return

        # OTM% 설정 시 해당 행사가 사용, 0이면 ATM
        if rt.otm_pct > 0:
            otm_pt  = round(atm * rt.otm_pct / 100 / _STRIKE_STEP) * _STRIKE_STEP
            base_strike = atm - otm_pt if rt.opt_type in ("P", "both") else atm + otm_pt
        else:
            base_strike = atm

        prem = None
        if rt.opt_type in ("P", "both") and base_strike in chain_put:
            prem = chain_put[base_strike]
        elif rt.opt_type in ("C", "both") and base_strike in chain_call:
            prem = chain_call[base_strike]

        if prem and prem > 0:
            self._samples[rt.label].append(prem)
            # 최저가로 실시간 갱신
            new_min = min(self._samples[rt.label])
            if new_min != rt.base_prem:
                rt.base_prem   = new_min
                rt.base_strike = base_strike
                rt.base_set_at = datetime.now().strftime("%H:%M")
                self._log_fn(
                    f"📊 [{rt.label}] 기준가 갱신: "
                    f"{rt.opt_type}{int(base_strike)} ${new_min:.2f} @ {rt.base_set_at}"
                )

    def _check_slot(
        self, rt: NightSlot, atm: float,
        chain_put: dict, chain_call: dict, tg_fmt: str,
    ):
        # 최대 알람 횟수 초과
        if rt.max_alerts > 0 and self._alert_count[rt.label] >= rt.max_alerts:
            return

        # 본 알림 재발화 억제
        last = self._fired.get(rt.label)
        if last and (datetime.now() - last).total_seconds() / 60 < self._cooldown_min:
            return

        candidates = self._scan_range(rt, atm, chain_put, chain_call)

        # ── 사전경보 스캔 (본 알림 미충족 시) ──────────────
        if not candidates and rt.pre_alert_pct > 0:
            pre_candidates = self._scan_pre_alert(rt, atm, chain_put, chain_call)
            if pre_candidates:
                best = max(pre_candidates, key=lambda x: x[2])
                opt_type, strike, pct = best
                msg = f"⚠️ [{rt.label}] 접근중 {opt_type}{int(strike)} {pct:.0f}%"
                self._log_fn(msg)
                pre_key = f"{rt.label}_pre"
                last_pre = self._fired.get(pre_key)
                if not last_pre or (datetime.now() - last_pre).total_seconds() / 60 >= self._cooldown_min:
                    self._send_tg(msg)
                    self._fired[pre_key] = datetime.now()
            return

        if not candidates:
            return

        # no_dup: 이미 같은 구간에서 알람 발생했으면 억제
        if rt.no_dup and self._alert_count[rt.label] > 0:
            return

        best = max(candidates, key=lambda x: x[2])
        opt_type, strike, pct = best
        curr_prem = (pct / 100) * rt.base_prem

        self._last_best[rt.label] = best
        self._fire(rt, opt_type, strike, curr_prem, pct, tg_fmt)
        self._fired[rt.label] = datetime.now()
        self._alert_count[rt.label] += 1

    def _scan_range(
        self, rt: NightSlot, atm: float,
        chain_put: dict, chain_call: dict,
    ) -> list[tuple[str, float, float]]:
        """ATM ±10개 행사가 스캔 → should_fire() 충족 목록."""
        if atm <= 0:
            return []
        hits    = []
        strikes = [atm + i * _STRIKE_STEP for i in range(-_SCAN_RANGE, _SCAN_RANGE + 1)]
        for strike in strikes:
            if rt.opt_type in ("P", "both") and strike in chain_put:
                curr = chain_put[strike]
                if rt.should_fire(curr):
                    hits.append(("P", strike, (curr / rt.base_prem) * 100))
            if rt.opt_type in ("C", "both") and strike in chain_call:
                curr = chain_call[strike]
                if rt.should_fire(curr):
                    hits.append(("C", strike, (curr / rt.base_prem) * 100))
        return hits

    def _scan_pre_alert(
        self, rt: NightSlot, atm: float,
        chain_put: dict, chain_call: dict,
    ) -> list[tuple[str, float, float]]:
        """pre_alert_pct 충족 행사가 목록 반환."""
        if atm <= 0 or rt.base_prem <= 0:
            return []
        hits    = []
        strikes = [atm + i * _STRIKE_STEP for i in range(-_SCAN_RANGE, _SCAN_RANGE + 1)]
        for strike in strikes:
            if rt.opt_type in ("P", "both") and strike in chain_put:
                curr = chain_put[strike]
                pct  = (curr / rt.base_prem) * 100
                if pct >= rt.pre_alert_pct * 100:
                    hits.append(("P", strike, pct))
            if rt.opt_type in ("C", "both") and strike in chain_call:
                curr = chain_call[strike]
                pct  = (curr / rt.base_prem) * 100
                if pct >= rt.pre_alert_pct * 100:
                    hits.append(("C", strike, pct))
        return hits

    def _build_chain_dicts(self, cp_tab) -> tuple[dict, dict]:
        """
        CallPutGrid.put_data / call_data + put_strikes / call_strikes 를
        {strike: price} 딕셔너리로 변환.

        원본 구조: {REQ_PUT+i: {'last': p, 'bid': p, 'ask': p, 'row': i, ...}}

        가격 우선순위:
          1. mid = (bid+ask)/2  — 야간세션은 last 거래 드물고 호가만 형성
          2. last               — mid 없을 때 폴백
        """
        try:
            from core import REQ_PUT, REQ_CALL
        except ImportError:
            self._log_fn("⚠ core 모듈 import 실패 — REQ_PUT/CALL 없음")
            return {}, {}

        put_dict, call_dict = {}, {}
        put_strikes  = getattr(cp_tab, "put_strikes",  [])
        call_strikes = getattr(cp_tab, "call_strikes", [])
        raw_put      = getattr(cp_tab, "put_data",  {})
        raw_call     = getattr(cp_tab, "call_data", {})

        for i, strike in enumerate(put_strikes):
            price = self._best_price(raw_put.get(REQ_PUT + i, {}))
            if price:
                put_dict[strike] = price

        for i, strike in enumerate(call_strikes):
            price = self._best_price(raw_call.get(REQ_CALL + i, {}))
            if price:
                call_dict[strike] = price

        return put_dict, call_dict

    @staticmethod
    def _best_price(rec: dict) -> float | None:
        """bid/ask mid 우선, 없으면 last. 둘 다 없으면 None."""
        if not isinstance(rec, dict):
            return None
        bid = rec.get("bid")
        ask = rec.get("ask")
        if isinstance(bid, float) and isinstance(ask, float) and bid > 0 and ask > 0:
            return (bid + ask) / 2
        last = rec.get("last")
        if isinstance(last, float) and last > 0:
            return last
        return None

    def _fire(self, rt, opt_type, strike, curr_prem, pct, tg_fmt):
        label = rt.label or rt.start_hhmm
        try:
            msg = tg_fmt.format(
                slot=label, opt_type=opt_type, strike=int(strike), pct=pct,
            )
        except KeyError:
            msg = f"🚨 [{label}] {opt_type}{int(strike)} {pct:.0f}% 급등 (${curr_prem:.2f})"
        self._log_fn(f"🚨 새벽알림 발동: {msg}")
        try:
            _p = os.path.join(_DIR, "..")
            if _p not in sys.path:
                sys.path.insert(0, _p)
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get().send("NIGHT_ALERT", msg)
        except Exception as e:
            self._log_fn(f"⚠ TG 전송 실패: {e}")
