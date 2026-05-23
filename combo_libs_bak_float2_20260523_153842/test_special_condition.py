"""
test_special_condition.py — SpecialFillWatcher 단위 테스트
─────────────────────────────────────────────────────────
실행: python test_special_condition.py
─────────────────────────────────────────────────────────
"""
import sys, time, threading, types, importlib

# ── IBKR / TG / Qt 목(Mock) ─────────────────────────────────────────

class FakeOrder:
    def __init__(self):
        self.action = ""; self.orderType = ""; self.totalQuantity = 0
        self.lmtPrice = 0.0; self.tif = ""; self.eTradeOnly = False
        self.firmQuoteOnly = False; self.transmit = False

class FakeIB:
    def __init__(self):
        self.orders = []
    def placeOrder(self, oid, bag, order):
        self.orders.append({"oid": oid, "bag": bag,
                            "price": order.lmtPrice,
                            "action": order.action,
                            "qty": order.totalQuantity})
        print(f"  [FakeIB] placeOrder OID={oid} price=${order.lmtPrice:.2f}"
              f"  action={order.action}  qty={order.totalQuantity}")

class FakeMW:
    def __init__(self):
        self.ib = FakeIB()

class FakeRef:
    def __init__(self):
        self.mw = FakeMW()

class FakeBag:
    symbol = "SPX"

# ibapi.order mock
ibapi_mod   = types.ModuleType("ibapi")
order_mod   = types.ModuleType("ibapi.order")
order_mod.Order = FakeOrder
ibapi_mod.order = order_mod
sys.modules["ibapi"]       = ibapi_mod
sys.modules["ibapi.order"] = order_mod

# telegram mock
tg_pkg    = types.ModuleType("telegram_bot")
tg_client = types.ModuleType("telegram_bot.tg_client")
_tg_msgs  = []
class FakeTG:
    @classmethod
    def get(cls): return cls()
    def send(self, ch, msg):
        _tg_msgs.append(msg)
        print(f"  [TG] {msg[:60].replace(chr(10),' ')}...")
tg_client.TelegramClient = FakeTG
tg_pkg.tg_client         = tg_client
sys.modules["telegram_bot"]           = tg_pkg
sys.modules["telegram_bot.tg_client"] = tg_client

# ── 모듈 로드 ────────────────────────────────────────────────────────
import combo_order_special_condition as sc
# 싱글톤 리셋 (테스트 격리)
sc.SpecialFillWatcher._inst = None

W = sc.SpecialFillWatcher.get()

# ── 공용 픽스처 ──────────────────────────────────────────────────────
def make_watch(oid=1055, target=3.00, action="SELL", qty=1):
    ref = FakeRef()
    bag = FakeBag()
    W.watch(ref, oid, target, action, [], "풋스프레드 테스트",
            bag_contract=bag, qty=qty)
    return ref, bag

PASS = 0; FAIL = 0
def ok(name):
    global PASS; PASS += 1; print(f"  ✅ PASS  {name}")
def ng(name, reason=""):
    global FAIL; FAIL += 1; print(f"  ❌ FAIL  {name}  {reason}")

# ════════════════════════════════════════════════════════════════════
# TC-01  watch() — bag_contract / qty 저장 확인
# ════════════════════════════════════════════════════════════════════
print("\n[TC-01] watch() 저장 확인")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref, bag = make_watch(oid=1001, target=3.00, qty=2)
w = W._watches.get(1001)
assert w is not None,               "watch 등록 실패"
assert w["bag_contract"] is bag,    "bag_contract 불일치"
assert w["qty"] == 2,               "qty 불일치"
assert w["action"] == "SELL",       "action 불일치"
assert w["target"] == 3.00,         "target 불일치"
ok("bag_contract / qty / action / target 모두 저장됨")
W.unwatch(1001)

# ════════════════════════════════════════════════════════════════════
# TC-02  on_net_price_update — 목표가 미달 시 트리거 안 됨
# ════════════════════════════════════════════════════════════════════
print("\n[TC-02] 목표가 미달 → 트리거 없음")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
make_watch(oid=1002, target=3.00)
W.on_net_price_update(1002, 2.50)   # 아직 미달
w = W._watches[1002]
if not w["triggered"]:
    ok("net_price $2.50 < target $3.00 → triggered=False")
else:
    ng("목표가 미달인데 triggered=True")
W.unwatch(1002)

# ════════════════════════════════════════════════════════════════════
# TC-03  on_net_price_update — 목표가 도달 시 트리거
# ════════════════════════════════════════════════════════════════════
print("\n[TC-03] 목표가 도달 → triggered=True")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
make_watch(oid=1003, target=3.00)
W.on_net_price_update(1003, 3.00)
w = W._watches[1003]
if w["triggered"]:
    ok("net_price $3.00 >= target $3.00 → triggered=True")
else:
    ng("목표가 도달인데 triggered=False")
# 타이머 정리
W.unwatch(1003)

# ════════════════════════════════════════════════════════════════════
# TC-04  1차 정정 — placeOrder 전송 확인 (타이머 직접 실행)
# ════════════════════════════════════════════════════════════════════
print("\n[TC-04] 1차 정정 (-3틱) placeOrder 전송")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref, bag = make_watch(oid=1004, target=3.00, qty=1)
ib = ref.mw.ib
ib.orders.clear()
_tg_msgs.clear()

# 타이머 없이 _fire 직접 호출 (step=0)
W._fire(1004)

if ib.orders:
    o = ib.orders[-1]
    expected_price = round(3.00 - 0.10 * 3, 2)   # $2.70
    if o["oid"] == 1004 and abs(o["price"] - expected_price) < 0.001:
        ok(f"1차 정정 placeOrder OID=1004 price=${o['price']:.2f} (기대 ${expected_price:.2f})")
    else:
        ng("1차 정정 가격 불일치", f"got ${o['price']:.2f} expected ${expected_price:.2f}")
    if o["action"] == "SELL":
        ok("action=SELL 유지")
    else:
        ng("action 오류", f"got {o['action']}")
    if o["qty"] == 1:
        ok("qty=1 유지")
    else:
        ng("qty 오류", f"got {o['qty']}")
else:
    ng("placeOrder 미호출 — bag_contract 문제 가능성")

step = W._watches.get(1004, {}).get("step", -1)
if step == 1:
    ok("step 0→1 진행됨")
else:
    ng("step 오류", f"got {step}")
W.unwatch(1004)

# ════════════════════════════════════════════════════════════════════
# TC-05  2차 정정 — step=1 에서 _fire
# ════════════════════════════════════════════════════════════════════
print("\n[TC-05] 2차 정정 (-5틱 누적) placeOrder 전송")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref, bag = make_watch(oid=1005, target=3.00, qty=1)
W._watches[1005]["step"] = 1          # 1차 이미 완료 상태 가정
ib = ref.mw.ib
ib.orders.clear()

W._fire(1005)

if ib.orders:
    o = ib.orders[-1]
    expected_price = round(3.00 - 0.10 * 5, 2)   # $2.50
    if abs(o["price"] - expected_price) < 0.001:
        ok(f"2차 정정 price=${o['price']:.2f} (기대 ${expected_price:.2f})")
    else:
        ng("2차 정정 가격 불일치", f"got ${o['price']:.2f}")
else:
    ng("2차 정정 placeOrder 미호출")
W.unwatch(1005)

# ════════════════════════════════════════════════════════════════════
# TC-06  bag_contract=None 이면 placeOrder 미호출 (경고만)
# ════════════════════════════════════════════════════════════════════
print("\n[TC-06] bag_contract=None → placeOrder 미호출")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref = FakeRef()
W.watch(ref, 9999, 3.00, "SELL", [], "테스트",
        bag_contract=None, qty=1)   # 의도적으로 None
ib = ref.mw.ib
ib.orders.clear()
W._fire(9999)
if not ib.orders:
    ok("bag=None → placeOrder 미호출 (안전하게 실패)")
else:
    ng("bag=None인데 placeOrder 호출됨")
W.unwatch(9999)

# ════════════════════════════════════════════════════════════════════
# TC-07  unwatch 후 _fire 무시
# ════════════════════════════════════════════════════════════════════
print("\n[TC-07] unwatch 후 _fire 무시")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref, bag = make_watch(oid=1007, target=3.00)
ib = ref.mw.ib
ib.orders.clear()
W.unwatch(1007)
W._fire(1007)   # 해제 후 호출
if not ib.orders:
    ok("unwatch 후 _fire → placeOrder 미호출")
else:
    ng("unwatch 후에도 placeOrder 호출됨")

# ════════════════════════════════════════════════════════════════════
# TC-08  포기(step=2) — placeOrder 없이 TG만
# ════════════════════════════════════════════════════════════════════
print("\n[TC-08] 포기(step=2) → placeOrder 없음, TG 발송")
sc.SpecialFillWatcher._inst = None
W = sc.SpecialFillWatcher.get()
ref, bag = make_watch(oid=1008, target=3.00)
W._watches[1008]["step"] = 2
ib = ref.mw.ib
ib.orders.clear()
_tg_msgs.clear()
W._fire(1008)
if not ib.orders:
    ok("포기 단계 → placeOrder 미호출")
else:
    ng("포기 단계인데 placeOrder 호출됨")
if any("수동 대응" in m for m in _tg_msgs):
    ok("포기 TG '수동 대응 필요' 발송됨")
else:
    ng("포기 TG 미발송")
W.unwatch(1008)

# ════════════════════════════════════════════════════════════════════
# 결과
# ════════════════════════════════════════════════════════════════════
print(f"\n{'─'*50}")
print(f"결과: PASS {PASS}  FAIL {FAIL}  합계 {PASS+FAIL}")
if FAIL == 0:
    print("✅ 전체 통과")
else:
    print("❌ 실패 항목 있음 — 위 로그 확인")
sys.exit(0 if FAIL == 0 else 1)
