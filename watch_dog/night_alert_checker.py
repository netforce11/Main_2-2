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
                cache_key = slot.label if slot.label else slot.start_hhmm
                rt    = self._slots.get(cache_key, slot)
                flag  = "✅" if slot.label in active else "⏸"
                base_s = (
                    f"기준가 {rt.opt_type}{int(rt.base_strike)} {rt.base_prem:.2f}pt@{rt.base_set_at}"
                    f" [{self._alert_count.get(cache_key, 0)}/{rt.max_alerts}회]"
                    + (f" → 추적:{rt.tracked_type}{int(rt.tracked_strike)}" if rt.tracked_strike > 0 else "")
                ) if rt.base_prem > 0 else "기준가 수집중"
                lines.append(
                    f"  {flag} {cache_key} [{slot.start_hhmm}~{slot.end_hhmm}]"
                    f" {slot.opt_type}/{slot.multiplier}x  {base_s}"
                )
            for key, (ot, strike, pct) in self._last_best.items():
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

        cp_tab = getattr(mw, "tab_callput", mw)
        chain_put, chain_call = self._build_chain_dicts(cp_tab)
        und = getattr(cp_tab, "und_price", None) or 0.0
        # ✅ NEW: ES 선물 지수 (장외 구간용)
        es_price = getattr(cp_tab, "es_price", None) or getattr(mw, "es_price", None) or 0.0
        atm_spx  = round(und    / _STRIKE_STEP) * _STRIKE_STEP if und    > 0 else 0.0

        if not getattr(self, "_chain_logged", False):
            self._log_fn(
                f"[진단] und={und:.1f} atm={atm_spx:.0f} es={es_price:.1f} "
                f"put체인={len(chain_put)}개 call체인={len(chain_call)}개"
            )
            if chain_put:
                self._chain_logged = True

        cfg = load_config()
        for slot in cfg.slots:
            # ✅ FIX BUG3: label 빈 문자열이면 start_hhmm을 키로 사용 (충돌 방지)
            cache_key = slot.label if slot.label else slot.start_hhmm
            if cache_key not in self._slots:
                self._slots[cache_key] = slot

        for slot in cfg.slots:
            if not slot.enabled:
                continue
            cache_key = slot.label if slot.label else slot.start_hhmm
            rt = self._slots[cache_key]

            is_active  = slot.is_active_now()
            was_active = self._slot_active.get(cache_key, False)

            if is_active and not was_active:
                self._alert_count[cache_key] = 0
                self._fired.pop(cache_key, None)
                self._fired.pop(f"{cache_key}_pre", None)
                self._log_fn(f"🔄 [{cache_key}] 새 구간 진입 — 알람 카운터 리셋")
            self._slot_active[cache_key] = is_active

            # ✅ NEW: 구간별 ATM 결정 (ES 기준 or SPX 기준)
            if rt.use_es and es_price > 0:
                # ES - es_offset(기본 -25) = 행사가 기준
                target_strike = round((es_price + rt.es_offset) / _STRIKE_STEP) * _STRIKE_STEP
                atm = target_strike
            else:
                atm = atm_spx

            if slot.is_in_sampling_window():
                self._collect_sample(rt, atm, chain_put, chain_call)
            elif is_active:
                if rt.base_prem <= 0:
                    self._log_fn(f"⚠ [{cache_key}] 기준가 미확정 — 샘플 없음")
                    continue
                self._check_slot(rt, cache_key, atm, chain_put, chain_call, cfg.tg_fmt)

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
        # ✅ FIX BUG7: both 타입일 때 P 우선, C는 P 없을 때만 (elif → 독립 if)
        if rt.opt_type in ("P", "both") and base_strike in chain_put:
            prem = chain_put[base_strike]
        if prem is None and rt.opt_type in ("C", "both") and base_strike in chain_call:
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
        self, rt: NightSlot, cache_key: str, atm: float,
        chain_put: dict, chain_call: dict, tg_fmt: str,
    ):
        # 최대 알람 횟수 초과
        if rt.max_alerts > 0 and self._alert_count[cache_key] >= rt.max_alerts:
            return

        # 본 알림 재발화 억제
        last = self._fired.get(cache_key)
        if last and (datetime.now() - last).total_seconds() / 60 < self._cooldown_min:
            return

        candidates = self._scan_range(rt, atm, chain_put, chain_call)

        # 추적 행사가 항상 갱신 (UI 표시용)
        if candidates:
            best_tracked = max(candidates, key=lambda x: x[2])
            rt.tracked_strike = best_tracked[1]
            rt.tracked_type   = best_tracked[0]
        elif rt.pre_alert_pct > 0:
            pre_candidates = self._scan_pre_alert(rt, atm, chain_put, chain_call)
            if pre_candidates:
                best_pre = max(pre_candidates, key=lambda x: x[2])
                rt.tracked_strike = best_pre[1]
                rt.tracked_type   = best_pre[0]

        # ── pre_alert 스캔 (본 알림 미충족 시) ─────────────
        if not candidates and rt.pre_alert_pct > 0:
            pre_candidates = self._scan_pre_alert(rt, atm, chain_put, chain_call)
            if pre_candidates:
                best = max(pre_candidates, key=lambda x: x[2])
                opt_type, strike, pct = best
                msg = f"⚠️ [{cache_key}] 접근중 {opt_type}{int(strike)} {pct:.0f}%"
                self._log_fn(msg)
                pre_key = f"{cache_key}_pre"
                last_pre = self._fired.get(pre_key)
                if not last_pre or (datetime.now() - last_pre).total_seconds() / 60 >= self._cooldown_min:
                    self._send_tg(msg)
                    self._fired[pre_key] = datetime.now()
            return

        if not candidates:
            return

        # no_dup: 이미 같은 구간에서 알람 발생했으면 억제
        if rt.no_dup and self._alert_count[cache_key] > 0:
            return

        best = max(candidates, key=lambda x: x[2])
        opt_type, strike, pct = best
        curr_prem = (pct / 100) * rt.base_prem

        self._last_best[cache_key] = best
        self._fire(rt, cache_key, opt_type, strike, curr_prem, pct, tg_fmt)
        self._fired[cache_key] = datetime.now()
        self._alert_count[cache_key] += 1

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

    def _send_tg(self, msg: str):
        """
        TG 전송 헬퍼 — _fire() 를 거치지 않는 pre_alert / adjust_base 메시지용.
        전송 실패는 조용히 로그만 남김.
        """
        try:
            _p = os.path.join(_DIR, "..")
            if _p not in sys.path:
                sys.path.insert(0, _p)
            from telegram_bot.tg_client import TelegramClient
            TelegramClient.get().send("NIGHT_ALERT", msg)
        except Exception as e:
            self._log_fn(f"⚠ TG 전송 실패: {e}")

    def _fire(self, rt, cache_key: str, opt_type, strike, curr_prem, pct, tg_fmt):
        label = cache_key  # 로그/메시지 표시용
        try:
            msg = tg_fmt.format(
                slot=label, opt_type=opt_type, strike=int(strike), pct=pct,
            )
        except KeyError:
            msg = f"🚨 [{label}] {opt_type}{int(strike)} {pct:.0f}% 급등 ({curr_prem:.2f}pt)"
        self._log_fn(f"🚨 새벽알림 발동: {msg}")
        self._send_tg(msg)
