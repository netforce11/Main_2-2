# 코드맵 — Main2_1 트레이딩 터미널

> 생성: `20260602_203608`  |  소스: `/home/netforce/trading_terminal/Main2_1`

## 📊 요약 통계

| 항목 | 수치 |
|------|------|
| Python 파일 수 | 438 |
| 클래스 수 | 272 |
| 최상위 함수 수 | 1235 |
| 메서드 수 | 2631 |

## 🏗 패키지 구조

| 패키지 | 역할 |
|---|---|
| `main.py` | 진입점 |
| `core.py` / `core_ui.py` | 핵심 UI 컨트롤러 |
| `call_put_tab/` | 옵션 체인, 주문, IBKR 연결 |
| `combo_libs/` | 콤보 주문/전략/UI |
| `combo_libs/Sleep_Order/` | 슬립 오더, 스파이크 감지 |
| `tab_chart_libs/` | 차트 렌더링/데이터 |
| `Greeks/` | Greeks 저장/렌더/리플레이 |
| `trade_log/` | 체결 로그, DB |
| `telegram_bot/` | 텔레그램 알림 |
| `watch_dog/` | 야간 알림/감시 |
| `tab_account/` | 잔고/멀티가격 |
| `korea_chart_tab/` | 키움 한국 차트 |

## ⚙️ 주요 외부 의존성
- ib_insync / ibapi — IBKR 연결
- PyQt5 / PyQt6 — UI
- pyqtgraph — 실시간 차트
- pandas / numpy / scipy — 데이터
- python-telegram-bot — 알림
- sqlite3 — 체결/Greeks DB
