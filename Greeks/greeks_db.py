# greeks_db.py  — SQLite 저장 / 불러오기 / 이벤트 감지
# Python 3.8 호환  |  S11 patch 기준
from __future__ import annotations
import os, sqlite3, logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

GAMMA_SPIKE_MULT   = 2.5
IV_CHANGE_PCT      = 5.0
DELTA_JUMP         = 0.05
BASELINE_CUT_MIN   = 30

def _resolve_greeks_dir() -> str:
    for p in [r"C:\data\Greeks_history",
              os.path.join(os.path.expanduser("~"), "Downloads"),
              os.path.join(os.path.expanduser("~"), "Documents")]:
        if os.path.isdir(p): return p
    os.makedirs(r"C:\data\Greeks_history", exist_ok=True)
    return r"C:\data\Greeks_history"

GREEKS_DIR: str = _resolve_greeks_dir()

def _db_path(day: str) -> str:       return os.path.join(GREEKS_DIR, f"greeks_{day}.db")
def _events_path() -> str:           return os.path.join(GREEKS_DIR, "events_log.db")
def _baseline_path() -> str:         return os.path.join(GREEKS_DIR, "baseline.db")

def open_db(day: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(day))
    conn.execute("""CREATE TABLE IF NOT EXISTS greeks (
        ts TEXT, sym TEXT, expiry TEXT, strike REAL, side TEXT,
        delta REAL, gamma REAL, iv REAL, vanna REAL, und_price REAL)""")
    conn.commit(); return conn

def open_events_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_events_path())
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        ts TEXT, sym TEXT, trigger_type TEXT, strike REAL,
        value REAL, prev_avg REAL, und_price REAL)""")
    conn.commit(); return conn

def open_baseline_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_baseline_path())
    conn.execute("""CREATE TABLE IF NOT EXISTS baseline (
        day TEXT, sym TEXT, expiry TEXT, strike REAL, side TEXT,
        iv_avg REAL, gamma_avg REAL,
        PRIMARY KEY (day, sym, expiry, strike, side))""")
    conn.commit(); return conn

# ── 저장 ────────────────────────────────────────────────
def save_snapshot(conn: sqlite3.Connection, rows: List[Dict]) -> None:
    conn.executemany("INSERT INTO greeks VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(r["ts"],r["sym"],r["expiry"],r["strike"],r["side"],
          r.get("delta"),r.get("gamma"),r.get("iv"),
          r.get("vanna"),r.get("und_price")) for r in rows])
    conn.commit()

def save_event(ec: sqlite3.Connection, ts: str, sym: str, ttype: str,
               strike: float, value: float, prev: float, und: float) -> None:
    ec.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
               (ts, sym, ttype, strike, value, prev, und)); ec.commit()

def save_baseline(rows: List[Dict], day: Optional[str] = None) -> None:
    day = day or date.today().strftime("%Y%m%d")
    conn = open_baseline_db()
    conn.executemany("INSERT OR REPLACE INTO baseline VALUES (?,?,?,?,?,?,?)",
        [(day,r["sym"],r["expiry"],r["strike"],r["side"],
          r.get("iv_avg",0.0),r.get("gamma_avg",0.0)) for r in rows])
    conn.commit(); conn.close()
    log.info("[GreeksDB] 기준선 저장 %d rows (day=%s)", len(rows), day)

# ── 조회 ────────────────────────────────────────────────
_COLS = ["ts","sym","expiry","strike","side","delta","gamma","iv","vanna","und_price"]

def load_snapshots(day: str, from_ts: str = "", to_ts: str = "") -> List[Dict]:
    path = _db_path(day)
    if not os.path.exists(path): return []
    conn = sqlite3.connect(path)
    q, p = "SELECT * FROM greeks", ()
    if from_ts and to_ts:
        q += " WHERE ts BETWEEN ? AND ?"; p = (from_ts, to_ts)
    rows = conn.execute(q, p).fetchall(); conn.close()
    return [dict(zip(_COLS, r)) for r in rows]

def available_days() -> List[str]:
    return sorted([f[8:16] for f in os.listdir(GREEKS_DIR)
                   if f.startswith("greeks_") and f.endswith(".db")])

def load_timestamps(day: str) -> List[str]:
    path = _db_path(day)
    if not os.path.exists(path): return []
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT DISTINCT ts FROM greeks ORDER BY ts").fetchall()
    conn.close(); return [r[0] for r in rows]

def load_baseline(day: str, sym: str) -> List[Dict]:
    conn = open_baseline_db()
    cols = ["day","sym","expiry","strike","side","iv_avg","gamma_avg"]
    rows = conn.execute("SELECT * FROM baseline WHERE day=? AND sym=?",
                        (day, sym)).fetchall()
    conn.close(); return [dict(zip(cols, r)) for r in rows]

# ── 감지 ────────────────────────────────────────────────
def detect_spike(day: str, sym: str, current_rows: List[Dict],
                 und_price: float, econn: sqlite3.Connection) -> List[str]:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    win_end = datetime.now()
    win_st  = win_end - timedelta(minutes=20)
    past    = load_snapshots(day,
                             win_st.strftime("%Y-%m-%d %H:%M:%S"),
                             win_end.strftime("%Y-%m-%d %H:%M:%S"))

    gamma_h: Dict[Tuple, List[float]] = {}
    iv_h:    Dict[Tuple, List[float]] = {}
    for r in past:
        k = (r["expiry"], r["strike"], r["side"])
        if r["gamma"]: gamma_h.setdefault(k, []).append(r["gamma"])
        if r["iv"]:    iv_h.setdefault(k, []).append(r["iv"])

    prev_delta: Dict[Tuple, float] = {}
    events: List[str] = []

    for r in current_rows:
        k = (r["expiry"], r["strike"], r["side"])
        g  = r.get("gamma"); iv = r.get("iv"); d = r.get("delta")

        # ① Gamma 급등
        if g and k in gamma_h:
            avg = sum(gamma_h[k]) / len(gamma_h[k])
            if avg > 0 and g >= avg * GAMMA_SPIKE_MULT:
                events.append(f"[Gamma↑] {r['side']} {r['strike']} "
                               f"Gamma={g:.4f}(avg={avg:.4f}×{GAMMA_SPIKE_MULT})")
                save_event(econn, now_str, sym, "Gamma",
                           r["strike"], g, avg, und_price)

        # ② IV 급변
        if iv and k in iv_h and len(iv_h[k]) >= 2:
            prev_iv = iv_h[k][-1]
            if prev_iv > 0:
                pct = abs(iv - prev_iv) / prev_iv * 100
                if pct >= IV_CHANGE_PCT:
                    events.append(f"[IV급변] {r['side']} {r['strike']} "
                                  f"IV={iv:.3f}(Δ{pct:.1f}%)")
                    save_event(econn, now_str, sym, f"IV_{r['side']}",
                               r["strike"], iv, prev_iv, und_price)

        # ③ Delta 이상 점프
        if d is not None and k in prev_delta:
            jump = abs(d - prev_delta[k])
            if jump >= DELTA_JUMP:
                events.append(f"[Delta↑] {r['side']} {r['strike']} "
                               f"Δdelta={jump:.3f}")
                save_event(econn, now_str, sym, "Delta",
                           r["strike"], d, prev_delta[k], und_price)
        if d is not None:
            prev_delta[k] = d

    return events