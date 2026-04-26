"""
db_manager.py — SQLite 헬퍼 (싱글턴)
────────────────────────────────────────────────────────
테이블:
  pnl_history  — 체결/PnL 이력
  watch_alerts — 감시 알람 이력
  tick_speed   — 틱/호가 속도 집계
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "trades.db")


class DBManager:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    # ── PnL ──────────────────────────────────────────────────
    def insert_trade(self, symbol, action, qty, price,
                     commission=0.0, pnl=0.0, strategy="",
                     spx_price=0.0, vix=0.0, note=""):
        ts = datetime.now().isoformat(timespec="seconds")
        self._conn.execute("""
            INSERT INTO pnl_history
            (ts,symbol,action,qty,price,commission,pnl,strategy,spx_price,vix,note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (ts, symbol, action, qty, price, commission, pnl,
              strategy, spx_price, vix, note))
        self._conn.commit()

    def fetch_pnl(self, symbol=None, date=None, limit=500):
        try:
            import pandas as pd
            sql = "SELECT * FROM pnl_history WHERE 1=1"
            params = []
            if symbol:
                sql += " AND symbol=?"; params.append(symbol)
            if date:
                sql += " AND ts LIKE ?"; params.append(f"{date}%")
            sql += f" ORDER BY ts DESC LIMIT {limit}"
            return pd.read_sql_query(sql, self._conn, params=params)
        except Exception:
            return None

    def today_pnl_summary(self):
        today = datetime.now().strftime("%Y-%m-%d")
        cur = self._conn.execute("""
            SELECT strategy, SUM(pnl) AS total_pnl, COUNT(*) AS trades
            FROM pnl_history WHERE ts LIKE ?
            GROUP BY strategy
        """, (f"{today}%",))
        return cur.fetchall()

    # ── 알람 로그 ─────────────────────────────────────────────
    def insert_alert(self, symbol, alert_type, condition=""):
        ts = datetime.now().isoformat(timespec="seconds")
        self._conn.execute("""
            INSERT INTO watch_alerts (ts,symbol,alert_type,condition,triggered)
            VALUES (?,?,?,?,1)
        """, (ts, symbol, alert_type, condition))
        self._conn.commit()

    def fetch_alerts_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        cur = self._conn.execute(
            "SELECT * FROM watch_alerts WHERE ts LIKE ? ORDER BY ts DESC",
            (f"{today}%",))
        return cur.fetchall()

    # ── 틱 속도 ───────────────────────────────────────────────
    def insert_tick_speed(self, symbol,
                          w10_tick, w10_quote,
                          w30_tick, w30_quote,
                          w60_tick, w60_quote):
        """2초마다 chart_tick_speed._save_to_db() 에서 호출."""
        ts = datetime.now().isoformat(timespec="seconds")
        self._conn.execute("""
            INSERT INTO tick_speed
            (ts, symbol, w10_tick, w10_quote,
                         w30_tick, w30_quote,
                         w60_tick, w60_quote)
            VALUES (?,?,?,?,?,?,?,?)
        """, (ts, symbol,
              w10_tick, w10_quote,
              w30_tick, w30_quote,
              w60_tick, w60_quote))
        self._conn.commit()

    def fetch_tick_speed(self, symbol=None, date=None, limit=1000):
        """
        Pandas DataFrame 반환.
        활용 예:
            df = db.fetch_tick_speed(symbol='SPX', date='2026-04-24')
            surge = df[df['w10_tick'] > df['w10_tick'].mean() * 3]
        """
        try:
            import pandas as pd
            sql = "SELECT * FROM tick_speed WHERE 1=1"
            params = []
            if symbol:
                sql += " AND symbol=?"; params.append(symbol)
            if date:
                sql += " AND ts LIKE ?"; params.append(f"{date}%")
            sql += f" ORDER BY ts DESC LIMIT {limit}"
            return pd.read_sql_query(sql, self._conn, params=params)
        except Exception:
            return None

    def tick_surge_moments(self, symbol, date=None,
                           window="w10_tick", mult=3.0):
        """
        특정 날짜에서 틱 급등 구간 반환.
        window: 'w10_tick' | 'w30_tick' | 'w60_tick'
        """
        df = self.fetch_tick_speed(symbol=symbol, date=date, limit=5000)
        if df is None or df.empty:
            return None
        avg = df[window].mean()
        return df[df[window] > avg * mult][["ts", window]].reset_index(drop=True)

    def close(self):
        self._conn.close()
