"""
chart_server.py — 1분봉 차트 웹 서버 v1.0
════════════════════════════════════════════════════════
Flask 기반 HTTP 서버 → 외부 IP 접속 가능
포트: 8765 (기본)

실행:
  python chart_server.py
  python chart_server.py --port 8765 --host 0.0.0.0

접속:
  로컬:  http://localhost:8765
  외부:  http://[내IP]:8765

Polygon.io REST API로 1분봉 데이터 조회
════════════════════════════════════════════════════════
"""

import os, json, csv, argparse, threading
from datetime import datetime, timedelta, date
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
import requests as http_req

# ── 경로 설정 ──────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
HTML_FILE      = BASE_DIR / "chart.html"
DATA_ROOT      = Path(r"C:\data\US_StockData")
API_KEY_FILE   = DATA_ROOT / "stock_api_key"
WATCHLIST_FILE = BASE_DIR / "data" / "chart_watchlist.json"
SAVE_DIR       = BASE_DIR / "data"
SAVE_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(BASE_DIR))

# ── API 키 로드 ────────────────────────────────────────
def load_api_key():
    try: return API_KEY_FILE.read_text(encoding="utf-8").strip()
    except:
        try: return (BASE_DIR / "data" / "api_key.txt").read_text(encoding="utf-8").strip()
        except: return ""

API_KEY = load_api_key()

# ── 관심종목 ───────────────────────────────────────────
def load_watchlist():
    try:
        if WATCHLIST_FILE.exists():
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except: pass
    return ["SPY", "QQQ", "SPX", "NVDA", "TSLA", "AAPL"]

def save_watchlist(items):
    WATCHLIST_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

# ── Polygon REST API ──────────────────────────────────
def fetch_polygon_1min(symbol: str, date_str: str, api_key: str) -> list:
    """YYYY-MM-DD 날짜의 1분봉 데이터 조회"""
    url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/minute"
           f"/{date_str}/{date_str}?apiKey={api_key}&limit=50000&sort=asc")
    try:
        r = http_req.get(url, timeout=15)
        data = r.json()
        if "results" in data:
            return data["results"]
    except Exception as e:
        print(f"[Polygon] {e}")
    return []

def fetch_polygon_range(symbol: str, from_date: str, to_date: str, api_key: str) -> list:
    """기간 1분봉 조회 (연속보기 등)"""
    url = (f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/minute"
           f"/{from_date}/{to_date}?apiKey={api_key}&limit=50000&sort=asc")
    try:
        r = http_req.get(url, timeout=20)
        data = r.json()
        if "results" in data:
            return data["results"]
    except Exception as e:
        print(f"[Polygon range] {e}")
    return []

def fetch_polygon_rt(symbol: str, api_key: str) -> list:
    """실시간(오늘~최근 2일) 1분봉"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    return fetch_polygon_range(symbol, yesterday, today, api_key)

# ── CSV 캐시 ──────────────────────────────────────────
def get_csv_path(symbol: str, year: int, month: int) -> Path:
    p = DATA_ROOT / symbol.upper() / f"{year}{month:02d}.csv"
    return p

def load_from_csv(symbol: str, tgt_date: date) -> list:
    """CSV 캐시에서 특정 날짜 데이터 로드"""
    try:
        import pandas as pd
        csv_path = get_csv_path(symbol, tgt_date.year, tgt_date.month)
        if not csv_path.exists(): return []
        df = pd.read_csv(str(csv_path))
        df['_d'] = (pd.to_datetime(df['t'], unit='ms')
                    .dt.tz_localize('UTC')
                    .dt.tz_convert('America/New_York').dt.date)
        res = df[df['_d'] == tgt_date]
        return res.drop(columns=['_d']).to_dict('records')
    except Exception as e:
        print(f"[CSV load] {e}")
        return []

def save_to_csv(symbol: str, tgt_date: date, bars: list):
    """1분봉 데이터를 CSV에 저장/병합"""
    if not bars: return
    try:
        import pandas as pd
        csv_path = get_csv_path(symbol, tgt_date.year, tgt_date.month)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        ndf = pd.DataFrame(bars)
        if csv_path.exists():
            existing = pd.read_csv(str(csv_path))
            ndf = pd.concat([existing, ndf]).drop_duplicates(subset=['t']).reset_index(drop=True)
        ndf.to_csv(str(csv_path), index=False)
    except Exception as e:
        print(f"[CSV save] {e}")

# ══════════════════════════════════════════════════════
# API 엔드포인트
# ══════════════════════════════════════════════════════

@app.route("/")
def index():
    """메인 HTML 페이지"""
    return send_from_directory(str(BASE_DIR), "chart.html")

@app.route("/api/bars")
def api_bars():
    """
    1분봉 데이터 조회
    params:
      symbol: 종목 (예: SPY)
      date:   날짜 YYYY-MM-DD (없으면 오늘~최근)
      days:   연속보기 일수 (1=단일, 2/3/4=연속)
      mode:   polygon (기본)
    """
    symbol = request.args.get("symbol", "SPY").upper().strip()
    date_str = request.args.get("date", "")
    days = int(request.args.get("days", 1))
    api_key = request.args.get("apikey", API_KEY)

    if not api_key:
        return jsonify({"error": "API 키 없음. data/api_key.txt에 Polygon API 키를 저장하세요."}), 400

    bars = []

    if not date_str:
        # 실시간: 오늘~최근 2일
        bars = fetch_polygon_rt(symbol, api_key)
    elif days > 1:
        # 연속보기: date 기준 days일 치
        end_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        all_bars = []
        collected = 0
        d = end_d
        attempts = 0
        while collected < days and attempts < days + 14:
            attempts += 1
            # CSV 캐시 먼저
            cached = load_from_csv(symbol, d)
            if cached:
                all_bars = cached + all_bars
                collected += 1
            else:
                # Polygon API
                ds = d.strftime("%Y-%m-%d")
                day_bars = fetch_polygon_1min(symbol, ds, api_key)
                if day_bars:
                    save_to_csv(symbol, d, day_bars)
                    all_bars = day_bars + all_bars
                    collected += 1
            d -= timedelta(days=1)
        bars = all_bars
    else:
        # 단일 날짜
        tgt = datetime.strptime(date_str, "%Y-%m-%d").date()
        bars = load_from_csv(symbol, tgt)
        if not bars:
            bars = fetch_polygon_1min(symbol, date_str, api_key)
            if bars:
                save_to_csv(symbol, tgt, bars)

    return jsonify({"symbol": symbol, "count": len(bars), "bars": bars})

@app.route("/api/watchlist", methods=["GET"])
def api_get_watchlist():
    return jsonify(load_watchlist())

@app.route("/api/watchlist", methods=["POST"])
def api_set_watchlist():
    data = request.get_json()
    items = data.get("items", [])
    save_watchlist(items)
    return jsonify({"ok": True})

@app.route("/api/apikey", methods=["GET"])
def api_get_key():
    """API 키가 설정되어 있는지 확인 (키 자체는 반환 안 함)"""
    key = load_api_key()
    return jsonify({"set": bool(key), "prefix": key[:4] + "..." if key else ""})

@app.route("/api/apikey", methods=["POST"])
def api_set_key():
    """API 키 저장"""
    data = request.get_json()
    key = data.get("key", "").strip()
    if key:
        key_path = BASE_DIR / "data" / "api_key.txt"
        key_path.write_text(key, encoding="utf-8")
        global API_KEY
        API_KEY = key
        return jsonify({"ok": True})
    return jsonify({"error": "키가 비어있습니다"}), 400

@app.route("/api/status")
def api_status():
    return jsonify({
        "server": "chart_server v1.0",
        "api_key_set": bool(API_KEY),
        "time": datetime.now().isoformat()
    })

# ══════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="바인딩 주소 (기본: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8766, help="포트 (기본: 8765)")
    args = parser.parse_args()

    print("=" * 55)
    print("  1분봉 차트 웹 서버  v1.0")
    print(f"  로컬 접속: http://localhost:{args.port}")
    print(f"  외부 접속: http://[내 IP]:{args.port}")
    print(f"  API 키: {'설정됨 ✓' if API_KEY else '미설정 ✗  (data/api_key.txt)'}")
    print("=" * 55)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)