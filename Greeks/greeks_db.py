"""
greeks_db.py — Greeks 데이터 저장/불러오기/급변동 이벤트 기록
════════════════════════════════════════════════════════════════
저장 경로 (우선순위):
  1. C:\\data\\Greeks_history\\         (신규 기본 경로)
  2. C:\\Users\\<user>\\Downloads\\     (이전 저장 위치 자동 탐색)
  3. 위 둘 다 없으면 C:\\data\\Greeks_history\\ 를 새로 생성
"""

import sqlite3, os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 저장 경로 자동 결정 ────────────────────────────────────────
def _resolve_greeks_dir() -> Path:
    """
    greeks_*.db 파일이 이미 존재하는 폴더를 우선 사용.
    없으면 C:\\data\\Greeks_history\\ 를 생성해서 반환.
    """
    candidates = [
        Path(r"C:\data\Greeks_history"),
        Path.home() / "Downloads",          # C:\Users\상우\Downloads
        Path.home() / "Documents",
        Path(__file__).parent.parent / "data" / "Greeks_history",
    ]
    # 기존 파일이 있는 폴더 우선
    for p in candidates:
        if p.exists() and list(p.glob("greeks_*.db")):
            return p
    # 없으면 첫 번째 경로 생성
    candidates[0].mkdir(parents=True, exist_ok=True)
    return candidates[0]


GREEKS_DIR = _resolve_greeks_dir()
EVENTS_DB  = GREEKS_DIR / "events_log.db"

# ── 급변동 임계값 ─────────────────────────────────────────────
GAMMA_SPIKE_MULT = 2.5   # 과거 평균 대비 N배 이상 → 이벤트
IV_CHANGE_PCT    = 5.0   # 분당 IV 변화율 % 이상
DELTA_JUMP       = 0.05  # 틱당 delta 점프


# ══════════════════════════════════════════════════════════════
# 날짜별 DB 파일명
# ══════════════════════════════════════════════════════════════
def _day_db(day: str = "") -> Path:
    """day='20260412' or '' → 오늘."""
    d = day or datetime.now().strftime("%Y%m%d")
    return GREEKS_DIR / f"greeks_{d}.db"


# ══════════════════════════════════════════════════════════════
# 연결 + 초기화
# ══════════════════════════════════════════════════════════════
def open_db(day: str = "") -> sqlite3.Connection:
    conn = sqlite3.connect(str(_day_db(day)))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS greeks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            sym       TEXT,
            expiry    TEXT,
            strike    REAL,
            side      TEXT,
            delta     REAL,
            gamma     REAL,
            iv        REAL,
            vanna     REAL,
            und_price REAL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ts ON greeks(ts)")
    conn.commit()
    return conn


def open_events_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(EVENTS_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT,
            sym          TEXT,
            trigger_type TEXT,
            strike       REAL,
            value        REAL,
            prev_avg     REAL,
            und_price    REAL
        )""")
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════
# 저장
# ══════════════════════════════════════════════════════════════
def save_snapshot(conn: sqlite3.Connection,
                  sym: str, expiry: str, und_price: float,
                  rows: list):
    """rows: [(strike, side, delta, gamma, iv, vanna), ...]"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.executemany(
        "INSERT INTO greeks(ts,sym,expiry,strike,side,delta,gamma,iv,vanna,und_price) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(now, sym, expiry, st, sd, d, g, iv, va, und_price)
         for st, sd, d, g, iv, va in rows]
    )
    conn.commit()


def save_event(econn: sqlite3.Connection,
               sym: str, trigger: str, strike: float,
               value: float, prev_avg: float, und_price: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    econn.execute(
        "INSERT INTO events(ts,sym,trigger_type,strike,value,prev_avg,und_price) "
        "VALUES(?,?,?,?,?,?,?)",
        (now, sym, trigger, strike, value, prev_avg, und_price)
    )
    econn.commit()


# ══════════════════════════════════════════════════════════════
# 불러오기
# ══════════════════════════════════════════════════════════════
def load_snapshots(day: str, time_from: str = "", time_to: str = "") -> List[Dict]:
    """
    day='20260412', time_from='14:00', time_to='15:00'
    → list of row dicts (ts, sym, expiry, strike, side, delta, gamma, iv, vanna, und_price)
    """
    db = _day_db(day)
    if not db.exists():
        return []
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM greeks WHERE 1=1"
    params = []
    if time_from:
        q += " AND time(ts) >= ?"
        params.append(time_from)
    if time_to:
        q += " AND time(ts) <= ?"
        params.append(time_to)
    q += " ORDER BY ts"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows


def available_days() -> List[str]:
    """저장된 날짜 목록 반환 (YYYYMMDD 문자열)."""
    return sorted(
        p.stem.replace("greeks_", "")
        for p in GREEKS_DIR.glob("greeks_*.db")
    )


def load_timestamps(day: str) -> List[str]:
    """해당 날짜의 저장된 타임스탬프 목록 (중복 제거)."""
    rows = load_snapshots(day)
    seen, result = set(), []
    for r in rows:
        t = r["ts"]
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


# ══════════════════════════════════════════════════════════════
# 급변동 감지
# ══════════════════════════════════════════════════════════════
def detect_spike(day: str, sym: str,
                 cur_gamma: dict,    # {strike: gamma_value}
                 cur_iv: dict,       # {(strike, side): iv}
                 und_price: float,
                 econn: sqlite3.Connection,
                 lookback_min: int = 20) -> List[Dict]:
    """
    과거 lookback_min 분 평균과 비교해 급변동 이벤트를 감지·저장.
    반환: [{'trigger': str, 'strike': float, 'value': float, 'prev_avg': float}, ...]
    """
    events = []
    rows   = load_snapshots(day)
    if not rows:
        return events

    now_ts = datetime.now()

    # 과거 N분 gamma 평균 (ATM 근처)
    gamma_history: Dict[float, List[float]] = {}
    iv_history: Dict[tuple, List[float]] = {}

    for r in rows:
        try:
            row_ts = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        diff_min = (now_ts - row_ts).total_seconds() / 60
        if diff_min > lookback_min:
            continue
        st = r["strike"]
        gamma_history.setdefault(st, []).append(r["gamma"] or 0.0)
        iv_history.setdefault((st, r["side"]), []).append(r["iv"] or 0.0)

    # Gamma spike 검사
    for st, cur_g in cur_gamma.items():
        hist = gamma_history.get(st, [])
        if len(hist) < 3:
            continue
        avg = sum(hist) / len(hist)
        if avg > 0 and cur_g / avg >= GAMMA_SPIKE_MULT:
            ev = {"trigger": "Gamma", "strike": st,
                  "value": cur_g, "prev_avg": avg}
            events.append(ev)
            save_event(econn, sym, "Gamma", st, cur_g, avg, und_price)

    # IV 급변 검사
    for key, cur_iv_val in cur_iv.items():
        hist = iv_history.get(key, [])
        if len(hist) < 2:
            continue
        avg = sum(hist) / len(hist)
        if avg > 0:
            pct = abs(cur_iv_val - avg) / avg * 100
            if pct >= IV_CHANGE_PCT:
                st, side = key
                ev = {"trigger": f"IV_{side}", "strike": st,
                      "value": cur_iv_val, "prev_avg": avg}
                events.append(ev)
                save_event(econn, sym, f"IV_{side}", st, cur_iv_val, avg, und_price)

    return events