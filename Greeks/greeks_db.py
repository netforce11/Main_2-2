# greeks_db.py  — SQLite 저장 / 불러오기 / 이벤트 감지
# Python 3.8 호환  |  S11 patch 기준
# ── 수정 이력 ──────────────────────────────────────────────────
# S12-fix1: _is_market_hours() fallback이 UTC를 ET처럼 사용하는 버그 수정
#           now_et import 실패 시 UTC-4(EDT)/UTC-5(EST) 정확 변환
# S12-fix2: [FIX-1] _is_market_hours() now_et()가 KST 반환 시 ET로 오판하는 버그 수정
#                   → now_et() 결과가 UTC 기준인지 검증 후 사용
#           [FIX-2] save_snapshot() 날짜 변경 시 conn 자동 재오픈 지원 (_open_conn_for_today)
#           [FIX-3] save_snapshot() und_price 이상값(SPX 범위 외) 저장 차단
#           [FIX-4] _conn_cache: 날짜별 커넥션 캐시로 재오픈 최소화
from __future__ import annotations
import os, sqlite3, logging, threading
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

GAMMA_SPIKE_MULT   = 2.5
IV_CHANGE_PCT      = 5.0
DELTA_JUMP         = 0.05
BASELINE_CUT_MIN   = 30

# [FIX-3] SPX/SPXW 기초자산 가격 정상 범위
UND_PRICE_MIN = 3000.0   # SPX가 이 이하면 비정상 (125 같은 /ES·SPY 혼입 차단)
UND_PRICE_MAX = 12000.0  # SPX가 이 이상이면 비정상

def _resolve_greeks_dir() -> str:
    for p in [r"/home/netforce/US_Data/Greeks_history",
              os.path.join(os.path.expanduser("~"), "Downloads"),
              os.path.join(os.path.expanduser("~"), "Documents")]:
        if os.path.isdir(p): return p
    os.makedirs(r"/home/netforce/US_Data/Greeks_history", exist_ok=True)
    return r"/home/netforce/US_Data/Greeks_history"

GREEKS_DIR: str = _resolve_greeks_dir()

def _db_path(day: str) -> str:       return os.path.join(GREEKS_DIR, f"greeks_{day}.db")
def _events_path() -> str:           return os.path.join(GREEKS_DIR, "events_log.db")
def _baseline_path() -> str:         return os.path.join(GREEKS_DIR, "baseline.db")

def open_db(day: str, db_dir: Optional[str] = None) -> sqlite3.Connection:
    if db_dir:
        path = os.path.join(db_dir, f"greeks_{day}.db")
    else:
        path = _db_path(day)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS greeks (
        ts TEXT, sym TEXT, expiry TEXT, strike REAL, side TEXT,
        delta REAL, gamma REAL, iv REAL, vanna REAL, und_price REAL)""")
    conn.commit(); return conn

def open_events_db(db_dir: Optional[str] = None) -> sqlite3.Connection:
    if db_dir:
        path = os.path.join(db_dir, "events_log.db")
    else:
        path = _events_path()
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        ts TEXT, sym TEXT, trigger_type TEXT, strike REAL,
        value REAL, prev_avg REAL, und_price REAL)""")
    conn.commit(); return conn

def open_baseline_db(db_dir: Optional[str] = None) -> sqlite3.Connection:
    if db_dir:
        path = os.path.join(db_dir, "baseline.db")
    else:
        path = _baseline_path()
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS baseline (
        day TEXT, sym TEXT, expiry TEXT, strike REAL, side TEXT,
        iv_avg REAL, gamma_avg REAL,
        PRIMARY KEY (day, sym, expiry, strike, side))""")
    conn.commit(); return conn

# ── 정규장 시간 체크 (ET 기준) ──────────────────────────────
def _et_offset_hours() -> int:
    """
    미국 ET 오프셋 반환 (UTC 기준).
    DST(3월 두 번째 일요일 ~ 11월 첫 번째 일요일): UTC-4 (EDT)
    그 외: UTC-5 (EST)
    Python 3.9+ zoneinfo 사용, 실패 시 근사 계산.
    """
    try:
        from zoneinfo import ZoneInfo
        from datetime import timezone
        utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
        et_dt = utc_dt.astimezone(ZoneInfo("America/New_York"))
        offset_seconds = et_dt.utcoffset().total_seconds()
        return int(offset_seconds / 3600)  # -4 (EDT) or -5 (EST)
    except Exception:
        pass

    # fallback: DST 근사 계산 (미국 기준)
    now = datetime.utcnow()
    y = now.year
    mar1 = datetime(y, 3, 1)
    first_sun_mar = mar1 + timedelta(days=(6 - mar1.weekday()) % 7)
    dst_start = first_sun_mar + timedelta(weeks=1)
    nov1 = datetime(y, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    if dst_start <= now < dst_end:
        return -4
    return -5


def _now_et() -> datetime:
    """
    현재 ET 시각 반환. now_et() import 성공 여부와 관계없이 항상 올바른 ET 반환.

    [FIX-1] 기존 문제:
      now_et()가 KST(UTC+9)를 반환하는 환경에서 ET로 오판 → _is_market_hours() 오동작.
      예) 한국 시간 14:00 KST → ET로 착각 → 09:30~16:00 범위에 포함 → 장중 판단 오류.

    해결:
      now_et() 결과와 UTC 기반 계산값을 비교해서 4시간 이상 차이나면
      now_et()를 신뢰하지 않고 UTC 계산값을 사용.
    """
    offset = _et_offset_hours()
    et_from_utc = datetime.utcnow() + timedelta(hours=offset)

    try:
        from call_put_tab.chain_saver.buffer import now_et
        result = now_et()
        # 신뢰성 검증: UTC 계산값과 4시간 이상 차이나면 오염된 값으로 간주
        diff_hours = abs((result - et_from_utc).total_seconds()) / 3600
        if diff_hours > 4:
            log.warning(
                "[GreeksDB] now_et() 결과(%s)가 UTC 기반 ET(%s)와 %.1f시간 차이 — "
                "UTC 계산값 사용",
                result.strftime("%H:%M"), et_from_utc.strftime("%H:%M"), diff_hours
            )
            return et_from_utc
        return result
    except ImportError:
        pass
    except Exception as e:
        log.debug("[GreeksDB] now_et() 오류 (무시): %s", e)

    log.debug("[GreeksDB] ET 시간 UTC 계산 (UTC%+d): %s",
              offset, et_from_utc.strftime("%H:%M"))
    return et_from_utc


def _is_market_hours() -> bool:
    """
    미국 ET 기준 정규장: 09:30 ~ 16:00
    16:00 이후 저장 차단.

    [FIX-1] _now_et() 로 교체 — KST/UTC 혼입 버그 완전 해소.
    """
    now = _now_et()
    h, m = now.hour, now.minute
    if h < 9:                return False
    if h == 9 and m < 30:   return False
    if h >= 16:              return False
    return True


def _today_et() -> str:
    """ET 기준 오늘 날짜 반환 (YYYYMMDD). 자정 넘김 대응."""
    return _now_et().strftime("%Y%m%d")


# ── [FIX-4] 날짜별 커넥션 캐시 ─────────────────────────────────────────────
# save_snapshot()이 매번 open_db()를 새로 열지 않아도 되도록 캐시.
# 날짜가 바뀌면 자동으로 새 DB 커넥션 생성.
# [FIX 🔴] threading.Lock으로 race condition 방지
#   autosave(Qt 메인스레드) + snap_mgr tick(IBKR EClient 스레드)이
#   동시에 _conn_cache에 접근하면 dict 변형 오류 발생 가능.
_conn_cache: Dict[str, sqlite3.Connection] = {}
_conn_cache_lock = threading.Lock()

def _get_today_conn() -> sqlite3.Connection:
    """
    [FIX-2] ET 기준 오늘 날짜에 맞는 DB 커넥션 반환.
    날짜가 바뀌면 이전 커넥션을 닫고 새 커넥션 생성.
    tab_greeks.py의 self._conn 과 별도로, 외부에서 conn 없이 호출하는
    save_snapshot()용 글로벌 캐시.
    [🔴 FIX] Lock으로 스레드 안전 보장.
    """
    today = _today_et()
    with _conn_cache_lock:
        if today not in _conn_cache:
            # 이전 날짜 커넥션 정리
            for old_day in list(_conn_cache.keys()):
                if old_day != today:
                    try:
                        _conn_cache[old_day].close()
                        log.info("[GreeksDB] 이전 날짜 커넥션 닫음: %s", old_day)
                    except Exception:
                        pass
                    del _conn_cache[old_day]
            _conn_cache[today] = open_db(today)
            log.info("[GreeksDB] 새 날짜 커넥션 생성: greeks_%s.db", today)
        return _conn_cache[today]


# ── 저장 ────────────────────────────────────────────────
def save_snapshot(conn: Optional[sqlite3.Connection], rows: List[Dict]) -> None:
    """
    Greeks 스냅샷 저장.

    [FIX-2] conn=None 허용 → _get_today_conn()으로 날짜 자동 전환 커넥션 사용.
            tab_greeks.py에서 self._conn을 넘기는 기존 방식도 그대로 동작.
    [FIX-3] und_price 이상값(SPX 범위 밖) 필터링 후 저장.
    """
    if not _is_market_hours():
        log.debug("[GreeksDB] 장외 시간 — 스냅샷 저장 생략 (%s ET)",
                  _now_et().strftime("%H:%M"))
        return

    if not rows:
        return

    # [FIX-3] und_price 이상값 필터링
    valid_rows = []
    skipped = 0
    for r in rows:
        und = r.get("und_price")
        if und is not None and (und < UND_PRICE_MIN or und > UND_PRICE_MAX):
            log.warning("[GreeksDB] und_price 이상값 저장 차단: %.2f "
                        "(strike=%s side=%s) — SPX 범위 아님",
                        und, r.get("strike"), r.get("side"))
            skipped += 1
            # und_price만 None으로 교체하고 나머지는 저장 (Greeks는 유효)
            r = dict(r); r["und_price"] = None
        valid_rows.append(r)

    if skipped:
        log.warning("[GreeksDB] %d건 und_price 이상값 → None으로 대체 저장", skipped)

    # [FIX-2] conn이 None이면 날짜 자동 전환 캐시 커넥션 사용
    # [🟠 FIX] conn이 None이 아닌 경우에도 날짜 불일치 경고 로그 추가
    if conn is not None:
        target_conn = conn
        # conn이 날짜 안 맞을 수 있으므로 경고 (치명적이진 않으나 추적 가능)
        today = _today_et()
        try:
            db_file = conn.execute("PRAGMA database_list").fetchone()
            if db_file and today not in (db_file[2] or ""):
                log.warning("[GreeksDB] save_snapshot: conn이 오늘(%s) 날짜 DB가 아닐 수 있음 — %s",
                            today, db_file[2])
        except Exception:
            pass
    else:
        target_conn = _get_today_conn()

    try:
        target_conn.executemany("INSERT INTO greeks VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["ts"], r.get("sym") or "", r["expiry"], r["strike"], r["side"],
              r.get("delta"), r.get("gamma"), r.get("iv"),
              r.get("vanna"), r.get("und_price")) for r in valid_rows])
        target_conn.commit()
    except Exception as e:
        log.error("[GreeksDB] save_snapshot INSERT 실패: %s", e)
        raise


def save_event(ec: sqlite3.Connection, ts: str, sym: str, ttype: str,
               strike: float, value: float, prev: float, und: float) -> None:
    ec.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
               (ts, sym, ttype, strike, value, prev, und)); ec.commit()

def save_baseline(rows: List[Dict], day: Optional[str] = None) -> None:
    day = day or _today_et()
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

        if g and k in gamma_h:
            avg = sum(gamma_h[k]) / len(gamma_h[k])
            if avg > 0 and g >= avg * GAMMA_SPIKE_MULT:
                events.append(f"[Gamma↑] {r['side']} {r['strike']} "
                               f"Gamma={g:.4f}(avg={avg:.4f}×{GAMMA_SPIKE_MULT})")
                save_event(econn, now_str, sym, "Gamma",
                           r["strike"], g, avg, und_price)

        if iv and k in iv_h and len(iv_h[k]) >= 2:
            prev_iv = iv_h[k][-1]
            if prev_iv > 0:
                pct = abs(iv - prev_iv) / prev_iv * 100
                if pct >= IV_CHANGE_PCT:
                    events.append(f"[IV급변] {r['side']} {r['strike']} "
                                  f"IV={iv:.3f}(Δ{pct:.1f}%)")
                    save_event(econn, now_str, sym, f"IV_{r['side']}",
                               r["strike"], iv, prev_iv, und_price)

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

# ── chain_YYYYMMDD.db 조회 ───────────────────────────────────
def _chain_db_path(day: str) -> str:
    return os.path.join(GREEKS_DIR, f"chain_{day}.db")

def load_chain_snapshots(day: str, from_ts: str = "", to_ts: str = "") -> List[Dict]:
    """chain_YYYYMMDD.db에서 가격+Greeks 로드. 구버전 DB(mid/theo/mispct 없음) 호환."""
    path = _chain_db_path(day)
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(chain_data)").fetchall()}
    base_cols = ["ts", "sym", "expiry", "strike", "side",
                 "bid", "ask", "last", "iv",
                 "delta", "gamma", "vega", "theta", "und_price"]
    extra_cols = [c for c in ["mid", "theo", "mispct"] if c in existing]
    all_cols = base_cols + extra_cols
    select = ", ".join(all_cols)
    q = f"SELECT {select} FROM chain_data"
    p: tuple = ()
    if from_ts and to_ts:
        q += " WHERE ts BETWEEN ? AND ?"; p = (from_ts, to_ts)
    elif from_ts:
        q += " WHERE ts >= ?"; p = (from_ts,)
    elif to_ts:
        q += " WHERE ts <= ?"; p = (to_ts,)
    q += " ORDER BY ts, strike, side"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(zip(all_cols, r)) for r in rows]


def available_expiries_for_day(day: str) -> List[str]:
    expiries: set = set()
    chain_path = _chain_db_path(day)
    if os.path.exists(chain_path):
        try:
            conn = sqlite3.connect(chain_path)
            rows = conn.execute(
                "SELECT DISTINCT expiry FROM chain_data WHERE expiry IS NOT NULL AND expiry != ''"
            ).fetchall()
            conn.close()
            expiries.update(r[0] for r in rows)
        except Exception:
            pass
    greeks_path = _db_path(day)
    if os.path.exists(greeks_path):
        try:
            conn = sqlite3.connect(greeks_path)
            rows = conn.execute(
                "SELECT DISTINCT expiry FROM greeks WHERE expiry IS NOT NULL AND expiry != ''"
            ).fetchall()
            conn.close()
            expiries.update(r[0] for r in rows)
        except Exception:
            pass
    return sorted(expiries)


def load_merged_snapshots(day: str, from_ts: str = "", to_ts: str = "",
                          expiry: str = "") -> List[Dict]:
    greeks_rows = load_snapshots(day, from_ts, to_ts)
    chain_rows  = load_chain_snapshots(day, from_ts, to_ts)
    if expiry:
        greeks_rows = [r for r in greeks_rows if r.get("expiry") == expiry]
        chain_rows  = [r for r in chain_rows  if r.get("expiry") == expiry]
    chain_idx: Dict[tuple, dict] = {}
    for r in chain_rows:
        key = (r["ts"], r["strike"], r["side"]); chain_idx[key] = r
    greeks_idx: Dict[tuple, dict] = {}
    for r in greeks_rows:
        key = (r["ts"], r["strike"], r["side"]); greeks_idx[key] = r
    all_keys = set(chain_idx.keys()) | set(greeks_idx.keys())
    merged = []
    for key in sorted(all_keys):
        c = chain_idx.get(key, {}); g = greeks_idx.get(key, {})
        merged.append({
            "ts": key[0], "strike": key[1], "side": key[2],
            "sym":       c.get("sym")    or g.get("sym", ""),
            "expiry":    c.get("expiry") or g.get("expiry", ""),
            "bid":       c.get("bid"),   "ask":   c.get("ask"),
            "last":      c.get("last"),  "mid":   c.get("mid"),
            "theo":      c.get("theo"),  "mispct":c.get("mispct"),
            "iv":        c.get("iv")    or g.get("iv"),
            "delta":     c.get("delta") or g.get("delta"),
            "gamma":     c.get("gamma") or g.get("gamma"),
            "vega":      c.get("vega"),  "theta": c.get("theta"),
            "vanna":     g.get("vanna"),
            "und_price": c.get("und_price") or g.get("und_price"),
        })
    return merged


def available_days_merged() -> List[str]:
    days = set()
    for f in os.listdir(GREEKS_DIR):
        if not f.endswith(".db"): continue
        if f.startswith("greeks_"):
            day = f[7:-3]
            if len(day) == 8 and day.isdigit(): days.add(day)
        elif f.startswith("chain_"):
            day = f[6:-3]
            if len(day) == 8 and day.isdigit(): days.add(day)
    return sorted(days)


# ── PriceHistoryBuffer 복원용 ────────────────────────────────────────────────

def load_und_price_history(minutes: int = 60) -> List[Dict]:
    """
    오늘 greeks_YYYYMMDD.db 에서 최근 N분치 und_price 조회.
    앱 재시작 시 PriceHistoryBuffer 복원에 사용.
    [FIX-2] _today_et() 로 날짜 기준을 ET로 통일.
    """
    today = _today_et()
    path  = _db_path(today)
    if not os.path.exists(path):
        return []
    cutoff = (_now_et() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(path)
        rows = conn.execute(
            "SELECT ts, und_price FROM greeks "
            "WHERE ts >= ? AND und_price IS NOT NULL "
            "AND und_price >= ? AND und_price <= ? "
            "ORDER BY ts ASC",
            (cutoff, UND_PRICE_MIN, UND_PRICE_MAX)
        ).fetchall()
        conn.close()
        return [{"ts": r[0], "und_price": r[1]} for r in rows]
    except Exception as e:
        log.warning("[GreeksDB] load_und_price_history 오류 (무시): %s", e)
        return []
